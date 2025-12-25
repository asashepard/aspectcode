"""
MCP (Model Context Protocol) endpoints for LLM agent tool access.

Exposes dependency graph and knowledge base information via standardized tool calls.
Shares rate limits with other API endpoints. No streaming.
"""

from typing import Dict, List, Any, Optional, Callable
from fastapi import APIRouter, Depends, HTTPException, status, Request
from pydantic import BaseModel, Field
import logging

from .auth import get_current_user, UserContext
from .rate_limit import limiter
from .settings import settings

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/mcp", tags=["mcp"])


# --- MCP Protocol Models ---


class ToolParameter(BaseModel):
    """Schema for a single tool parameter."""
    name: str = Field(..., description="Parameter name")
    type: str = Field(..., description="Parameter type (string, number, boolean, array)")
    description: str = Field(..., description="What this parameter does")
    required: bool = Field(True, description="Whether parameter is required")


class ToolDefinition(BaseModel):
    """Definition of an available MCP tool."""
    name: str = Field(..., description="Unique tool identifier")
    description: str = Field(..., description="What the tool does")
    parameters: List[ToolParameter] = Field(default_factory=list, description="Tool parameters")


class ToolsListResponse(BaseModel):
    """Response containing available tools."""
    tools: List[ToolDefinition] = Field(..., description="List of available tools")


class ExecuteRequest(BaseModel):
    """Request to execute a tool."""
    tool: str = Field(..., description="Name of the tool to execute")
    arguments: Dict[str, Any] = Field(default_factory=dict, description="Tool arguments")
    snapshot_id: str = Field(..., description="Snapshot ID to query against")


class ExecuteResponse(BaseModel):
    """Response from tool execution."""
    success: bool = Field(..., description="Whether execution succeeded")
    result: Optional[Any] = Field(None, description="Tool result if successful")
    error: Optional[str] = Field(None, description="Error message if failed")


# --- Tool Registry ---


class ToolRegistry:
    """Registry for MCP tools and their handlers."""
    
    def __init__(self):
        self._tools: Dict[str, ToolDefinition] = {}
        self._handlers: Dict[str, Callable] = {}
    
    def register(
        self,
        name: str,
        description: str,
        parameters: List[ToolParameter],
        handler: Callable
    ) -> None:
        """Register a new tool."""
        self._tools[name] = ToolDefinition(
            name=name,
            description=description,
            parameters=parameters
        )
        self._handlers[name] = handler
    
    def get_tools(self) -> List[ToolDefinition]:
        """Get all registered tools."""
        return list(self._tools.values())
    
    def get_handler(self, name: str) -> Optional[Callable]:
        """Get handler for a tool."""
        return self._handlers.get(name)
    
    def has_tool(self, name: str) -> bool:
        """Check if tool exists."""
        return name in self._tools


# Global tool registry
tool_registry = ToolRegistry()


# --- Tool Implementations ---


def _get_file_dependencies(snapshot, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Get what files a given file depends on (imports from)."""
    file_path = arguments.get("file_path")
    if not file_path:
        return {"error": "file_path is required"}
    
    dependencies = snapshot.get_dependencies(file_path)
    return {
        "file": file_path,
        "depends_on": list(dependencies),
        "count": len(dependencies)
    }


def _get_file_dependents(snapshot, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Get what files depend on (import from) a given file."""
    file_path = arguments.get("file_path")
    if not file_path:
        return {"error": "file_path is required"}
    
    dependents = snapshot.get_dependents(file_path)
    return {
        "file": file_path,
        "imported_by": list(dependents),
        "count": len(dependents)
    }


def _get_architectural_hubs(snapshot, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Get files with the most dependents (high-impact files)."""
    threshold = arguments.get("threshold", 5)
    
    hub_counts: Dict[str, int] = {}
    for file_path in snapshot.files:
        dependents = snapshot.get_dependents(file_path)
        if len(dependents) >= threshold:
            hub_counts[file_path] = len(dependents)
    
    # Sort by count descending
    sorted_hubs = sorted(hub_counts.items(), key=lambda x: x[1], reverse=True)
    
    return {
        "threshold": threshold,
        "hubs": [{"file": f, "dependent_count": c} for f, c in sorted_hubs],
        "count": len(sorted_hubs)
    }


def _get_circular_dependencies(snapshot, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Detect circular dependency chains in the project."""
    cycles: List[List[str]] = []
    visited = set()
    
    def find_cycles(start: str, path: List[str], in_path: set):
        if start in in_path:
            # Found cycle - extract the cyclic portion
            cycle_start = path.index(start)
            cycle = path[cycle_start:] + [start]
            # Normalize cycle to start from smallest element for deduplication
            min_idx = cycle.index(min(cycle[:-1]))  # Exclude last (duplicate of first)
            normalized = cycle[min_idx:-1] + cycle[:min_idx] + [cycle[min_idx]]
            normalized_tuple = tuple(normalized)
            if normalized_tuple not in visited:
                visited.add(normalized_tuple)
                cycles.append(normalized)
            return
        
        if start in path:
            return
            
        deps = snapshot.get_dependencies(start)
        for dep in deps:
            if dep in snapshot.files:  # Only follow internal dependencies
                find_cycles(dep, path + [start], in_path | {start})
    
    for file_path in snapshot.files:
        find_cycles(file_path, [], set())
    
    return {
        "cycles": cycles,
        "count": len(cycles)
    }


def _list_files(snapshot, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """List all indexed files, optionally filtered by language."""
    language = arguments.get("language")
    
    if language:
        files = [
            {"path": f.path, "language": f.language, "size": f.size}
            for f in snapshot.files.values()
            if f.language == language
        ]
    else:
        files = [
            {"path": f.path, "language": f.language, "size": f.size}
            for f in snapshot.files.values()
        ]
    
    # Sort by path
    files.sort(key=lambda x: x["path"])
    
    return {
        "files": files,
        "count": len(files),
        "filter": {"language": language} if language else None
    }


def _get_impact_analysis(snapshot, arguments: Dict[str, Any]) -> Dict[str, Any]:
    """Analyze impact of changing a file - returns affected files transitively."""
    file_path = arguments.get("file_path")
    max_depth = arguments.get("max_depth", 3)
    
    if not file_path:
        return {"error": "file_path is required"}
    
    affected: Dict[str, int] = {}  # file -> depth at which discovered
    current_level = {file_path}
    depth = 0
    
    while current_level and depth < max_depth:
        depth += 1
        next_level = set()
        for f in current_level:
            for dependent in snapshot.get_dependents(f):
                if dependent not in affected and dependent != file_path:
                    affected[dependent] = depth
                    next_level.add(dependent)
        current_level = next_level
    
    # Group by depth
    by_depth: Dict[int, List[str]] = {}
    for f, d in affected.items():
        by_depth.setdefault(d, []).append(f)
    
    return {
        "changed_file": file_path,
        "max_depth": max_depth,
        "affected_files": [
            {"depth": d, "files": sorted(files)}
            for d, files in sorted(by_depth.items())
        ],
        "total_affected": len(affected)
    }


# --- Register Tools ---


def _register_all_tools():
    """Register all MCP tools."""
    
    tool_registry.register(
        name="get_file_dependencies",
        description="Get what files a given file depends on (imports from). Use this to understand what a file needs to function.",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Relative path to the file (e.g., 'src/utils/helpers.ts')",
                required=True
            )
        ],
        handler=_get_file_dependencies
    )
    
    tool_registry.register(
        name="get_file_dependents",
        description="Get what files depend on (import from) a given file. Use this to understand the impact radius of changing a file.",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Relative path to the file (e.g., 'src/utils/helpers.ts')",
                required=True
            )
        ],
        handler=_get_file_dependents
    )
    
    tool_registry.register(
        name="get_architectural_hubs",
        description="Find files that are imported by many other files - these are high-impact architectural components that require careful changes.",
        parameters=[
            ToolParameter(
                name="threshold",
                type="number",
                description="Minimum number of dependents to be considered a hub (default: 5)",
                required=False
            )
        ],
        handler=_get_architectural_hubs
    )
    
    tool_registry.register(
        name="get_circular_dependencies",
        description="Detect circular dependency chains in the codebase. Returns cycles where A imports B imports C imports A.",
        parameters=[],
        handler=_get_circular_dependencies
    )
    
    tool_registry.register(
        name="list_files",
        description="List all indexed files in the project, optionally filtered by programming language.",
        parameters=[
            ToolParameter(
                name="language",
                type="string",
                description="Filter by language (e.g., 'python', 'typescript', 'javascript')",
                required=False
            )
        ],
        handler=_list_files
    )
    
    tool_registry.register(
        name="get_impact_analysis",
        description="Analyze the cascading impact of changing a file. Returns all files that would be affected transitively through the dependency chain.",
        parameters=[
            ToolParameter(
                name="file_path",
                type="string",
                description="Relative path to the file being changed",
                required=True
            ),
            ToolParameter(
                name="max_depth",
                type="number",
                description="Maximum depth to traverse (default: 3)",
                required=False
            )
        ],
        handler=_get_impact_analysis
    )


# Initialize tools on module load
_register_all_tools()


# --- API Endpoints ---


@router.get("/tools", response_model=ToolsListResponse)
@limiter.limit(f"{settings.rate_limit}/minute")
async def list_tools(
    request: Request,  # Required for rate limiter
    user: UserContext = Depends(get_current_user)
) -> ToolsListResponse:
    """
    List all available MCP tools.
    
    Returns tool definitions with names, descriptions, and parameter schemas.
    LLM agents should call this to discover available tools.
    """
    return ToolsListResponse(tools=tool_registry.get_tools())


@router.post("/execute", response_model=ExecuteResponse)
@limiter.limit(f"{settings.rate_limit}/minute")
async def execute_tool(
    request: Request,  # Required for rate limiter  
    body: ExecuteRequest,
    user: UserContext = Depends(get_current_user)
) -> ExecuteResponse:
    """
    Execute an MCP tool.
    
    Requires a valid snapshot_id from a previous indexing operation.
    Tool results are returned synchronously (no streaming).
    """
    from .storage import get_storage
    
    # Validate tool exists
    if not tool_registry.has_tool(body.tool):
        return ExecuteResponse(
            success=False,
            error=f"Unknown tool: {body.tool}. Call GET /mcp/tools to see available tools."
        )
    
    # Get snapshot
    storage = get_storage()
    snapshot = storage.get_snapshot(body.snapshot_id)
    
    if not snapshot:
        return ExecuteResponse(
            success=False,
            error=f"Snapshot not found: {body.snapshot_id}. Index the repository first."
        )
    
    # Execute tool
    try:
        handler = tool_registry.get_handler(body.tool)
        result = handler(snapshot, body.arguments)
        
        # Check if handler returned an error
        if isinstance(result, dict) and "error" in result and len(result) == 1:
            return ExecuteResponse(success=False, error=result["error"])
        
        return ExecuteResponse(success=True, result=result)
        
    except Exception as e:
        logger.exception(f"Tool execution failed: {body.tool}")
        return ExecuteResponse(
            success=False,
            error=f"Tool execution failed: {str(e)}"
        )
