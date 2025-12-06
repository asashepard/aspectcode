"""
Project import graph for dependency analysis and cycle detection.

This module provides:
- Import dependency graph construction
- Strongly Connected Components (SCC) detection using Tarjan's algorithm
- Minimal cycle path extraction for reporting
- Graph caching and serialization support
"""

from typing import Dict, List, Set, Tuple, Optional
from collections import defaultdict, deque
import json


class ImportGraph:
    """Directed graph of module import dependencies with cycle detection."""
    
    def __init__(self):
        """Initialize empty import graph."""
        self._modules: Dict[str, Optional[str]] = {}  # module -> file_path (None for external)
        self._edges: Dict[str, Set[str]] = defaultdict(set)  # src -> {dst, ...}
        self._reverse_edges: Dict[str, Set[str]] = defaultdict(set)  # dst -> {src, ...}
        
        # SCC computation state
        self._scc_cache: Optional[List[List[str]]] = None
        self._scc_dirty = False
    
    def add_module(self, module: str, file_path: Optional[str] = None):
        """
        Add a module to the graph.
        
        Args:
            module: Canonical module name
            file_path: File path if it's a project module, None for external
        """
        self._modules[module] = file_path
        self._scc_dirty = True
    
    def add_edge(self, src_module: str, dst_module: str):
        """
        Add an import dependency edge from src_module to dst_module.
        
        Args:
            src_module: Module doing the importing
            dst_module: Module being imported
        """
        if dst_module not in self._edges[src_module]:
            self._edges[src_module].add(dst_module)
            self._reverse_edges[dst_module].add(src_module)
            self._scc_dirty = True
    
    def successors(self, module: str) -> List[str]:
        """Get list of modules that this module imports."""
        return list(self._edges.get(module, set()))
    
    def predecessors(self, module: str) -> List[str]:
        """Get list of modules that import this module."""
        return list(self._reverse_edges.get(module, set()))
    
    def modules(self) -> List[str]:
        """Get list of all modules in the graph."""
        return list(self._modules.keys())
    
    def project_modules(self) -> List[str]:
        """Get list of project modules (those with file paths)."""
        return [mod for mod, path in self._modules.items() if path is not None]
    
    def external_modules(self) -> List[str]:
        """Get list of external modules (stdlib, third-party)."""
        return [mod for mod, path in self._modules.items() if path is None]
    
    def module_file_path(self, module: str) -> Optional[str]:
        """Get file path for a module, or None if external."""
        return self._modules.get(module)
    
    def sccs(self) -> List[List[str]]:
        """
        Compute Strongly Connected Components using Tarjan's algorithm.
        
        Returns:
            List of SCCs, each containing module names in the component
        """
        if not self._scc_dirty and self._scc_cache is not None:
            return self._scc_cache
        
        # Tarjan's SCC algorithm
        index_counter = [0]
        stack = []
        lowlinks = {}
        index = {}
        on_stack = set()
        sccs = []
        
        def strongconnect(node: str):
            # Set the depth index for this node to the smallest unused index
            index[node] = index_counter[0]
            lowlinks[node] = index_counter[0]
            index_counter[0] += 1
            stack.append(node)
            on_stack.add(node)
            
            # Consider successors
            for successor in self._edges.get(node, set()):
                if successor not in index:
                    # Successor has not been visited; recurse on it
                    strongconnect(successor)
                    lowlinks[node] = min(lowlinks[node], lowlinks[successor])
                elif successor in on_stack:
                    # Successor is in stack and hence in the current SCC
                    lowlinks[node] = min(lowlinks[node], index[successor])
            
            # If node is a root node, pop the stack and create an SCC
            if lowlinks[node] == index[node]:
                component = []
                while True:
                    successor = stack.pop()
                    on_stack.remove(successor)
                    component.append(successor)
                    if successor == node:
                        break
                sccs.append(component)
        
        # Run Tarjan for each unvisited node
        for node in self._modules:
            if node not in index:
                strongconnect(node)
        
        self._scc_cache = sccs
        self._scc_dirty = False
        return sccs
    
    def minimal_cycle_example(self, scc: List[str]) -> List[Tuple[str, str]]:
        """
        Find a minimal cycle within an SCC for reporting.
        
        Args:
            scc: List of modules in a strongly connected component
            
        Returns:
            List of (src, dst) edges forming a cycle path
        """
        if len(scc) <= 1:
            return []
        
        # Convert to set for fast lookup
        scc_set = set(scc)
        
        # Find a cycle using BFS from the first node
        start_node = scc[0]
        
        def find_path(start: str, end: str) -> Optional[List[str]]:
            """Find shortest path from start to end within the SCC."""
            if start == end:
                return [start]
            
            queue = deque([(start, [start])])
            visited = {start}
            
            while queue:
                current, path = queue.popleft()
                
                for neighbor in self._edges.get(current, set()):
                    if neighbor in scc_set and neighbor not in visited:
                        new_path = path + [neighbor]
                        if neighbor == end:
                            return new_path
                        queue.append((neighbor, new_path))
                        visited.add(neighbor)
            
            return None
        
        # Find path back to start node from any reachable node
        path = find_path(start_node, start_node)
        if path and len(path) > 1:
            # Convert path to edge list
            edges = []
            for i in range(len(path) - 1):
                edges.append((path[i], path[i + 1]))
            # Add edge back to start to complete the cycle
            if path[0] != path[-1]:
                edges.append((path[-1], path[0]))
            return edges
        
        # Fallback: try to find any cycle in the SCC
        for node in scc:
            path = find_path(node, node)
            if path and len(path) > 1:
                edges = []
                for i in range(len(path) - 1):
                    edges.append((path[i], path[i + 1]))
                return edges
        
        # If no cycle found (shouldn't happen in a real SCC), return empty
        return []
    
    def stats(self) -> Dict[str, int]:
        """Get graph statistics."""
        total_edges = sum(len(dsts) for dsts in self._edges.values())
        project_mods = len(self.project_modules())
        external_mods = len(self.external_modules())
        
        return {
            "modules": len(self._modules),
            "project_modules": project_mods,
            "external_modules": external_mods,
            "edges": total_edges,
            "sccs": len(self.sccs()),
            "cycles": len([scc for scc in self.sccs() if len(scc) > 1])
        }
    
    def to_dict(self) -> Dict:
        """
        Export graph to dictionary for JSON serialization.
        
        Returns:
            Dictionary with nodes, edges, and SCCs
        """
        sccs = self.sccs()
        
        return {
            "nodes": [
                {
                    "module": module,
                    "file_path": file_path,
                    "is_project": file_path is not None
                }
                for module, file_path in self._modules.items()
            ],
            "edges": [
                {"src": src, "dst": dst}
                for src, dsts in self._edges.items()
                for dst in dsts
            ],
            "sccs": [
                {
                    "modules": scc,
                    "size": len(scc),
                    "is_cycle": len(scc) > 1,
                    "minimal_cycle": self.minimal_cycle_example(scc) if len(scc) > 1 else []
                }
                for scc in sccs
            ],
            "stats": self.stats()
        }
    
    def to_json(self, indent: Optional[int] = 2) -> str:
        """Export graph to JSON string."""
        return json.dumps(self.to_dict(), indent=indent)
    
    def save_json(self, file_path: str):
        """Save graph to JSON file."""
        with open(file_path, 'w') as f:
            f.write(self.to_json())


def build_import_graph_signature(file_paths: List[str]) -> str:
    """
    Build a signature for caching based on file paths and modification times.
    
    Args:
        file_paths: List of files to include in signature
        
    Returns:
        String signature suitable for cache keys
    """
    import hashlib
    import os
    
    hasher = hashlib.md5()
    
    # Sort for deterministic results
    sorted_paths = sorted(file_paths)
    
    for path in sorted_paths:
        hasher.update(path.encode('utf-8'))
        try:
            mtime = os.path.getmtime(path)
            hasher.update(str(mtime).encode('utf-8'))
        except OSError:
            # File doesn't exist or can't get mtime
            hasher.update(b'missing')
    
    return hasher.hexdigest()

