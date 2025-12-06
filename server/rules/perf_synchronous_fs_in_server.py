"""Performance rule: Detect synchronous filesystem calls in server request handlers.

Warns when blocking synchronous fs calls are used in Node.js/TypeScript server
request handlers, which can stall the event loop and hurt throughput/latency.
Recommends using async fs APIs, streams, or caching/preloading at startup.
"""

from typing import Iterator
from engine.types import RuleMeta, Rule, RuleContext, Finding, Requires


class PerfSynchronousFsInServerRule:
    """Detect synchronous filesystem calls in server request handlers."""
    
    meta = RuleMeta(
        id="perf.synchronous_fs_in_server",
        category="perf",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detect synchronous fs calls in server request handlers",
        langs=["javascript", "typescript"],
    )
    requires = Requires(syntax=True)

    # Common synchronous fs calls
    SYNC_FS = {
        "fs.readFileSync", "fs.writeFileSync", "fs.appendFileSync", "fs.rmSync", "fs.unlinkSync",
        "fs.mkdirSync", "fs.rmdirSync", "fs.copyFileSync", "fs.renameSync",
        "fs.statSync", "fs.lstatSync", "fs.existsSync", "fs.accessSync",
        "fs.readdirSync", "fs.readlinkSync", "fs.symlinkSync", "fs.openSync", "fs.closeSync", "fs.fsyncSync",
        "fs.chmodSync", "fs.chownSync", "fs.fchmodSync", "fs.fchownSync", "fs.truncateSync",
        "fs.ftruncateSync", "fs.utimesSync", "fs.futimesSync", "fs.realPathSync"
    }

    SERVER_VERBS = ("get", "post", "put", "patch", "delete", "head", "options", "all")

    def visit(self, ctx) -> Iterator[Finding]:
        """Check for synchronous fs calls in server request handlers."""
        if not hasattr(ctx, 'syntax') or not ctx.syntax:
            return
            
        # Walk through all nodes to find fs calls in request contexts
        for node in ctx.walk_nodes():
            if self._is_call_expression(node) and self._is_sync_fs(node) and self._in_request_context(node):
                # Get span for the callee
                callee_node = self._get_callee_node(node)
                start_pos, end_pos = ctx.node_span(callee_node or node)
                
                yield Finding(
                    rule=self.meta.id,
                    message="Synchronous fs call in request handler; use async fs APIs, streams, or cache/preload at startup.",
                    file=ctx.file_path,
                    start_byte=start_pos,
                    end_byte=end_pos,
                    severity="warning",
                )

    def _walk_nodes(self, syntax_tree):
        """Walk all nodes in the tree."""
        return syntax_tree.walk()

    def _is_call_expression(self, node) -> bool:
        """Check if node is a call expression."""
        return hasattr(node, 'kind') and node.kind == "call_expression", "function_call"

    def _is_sync_fs(self, node) -> bool:
        """Check if node is a synchronous fs call."""
        callee_text = self._get_callee_text(node)
        if not callee_text:
            return False
            
        # Direct match with known sync fs calls
        if callee_text in self.SYNC_FS:
            return True
            
        # Heuristic: ends with 'Sync' and starts with 'fs.'
        return callee_text.startswith("fs.") and callee_text.endswith("Sync")

    def _get_callee_text(self, node) -> str:
        """Extract callee text from call expression."""
        if not hasattr(node, 'children') or not node.children:
            return ""
        
        # First child is usually the callee
        callee = node.children[0]
        return self._get_node_text(callee)

    def _get_node_text(self, node) -> str:
        """Get text content of a node."""
        if hasattr(node, 'text'):
            return node.text.decode('utf-8') if isinstance(node.text, bytes) else str(node.text)
        return ""

    def _get_callee_node(self, node):
        """Get the callee node from a call expression."""
        if not hasattr(node, 'children') or not node.children:
            return None
        
        # First child is usually the callee
        callee = node.children[0]
        if hasattr(callee, 'kind') and callee.kind in {
            "identifier", "member_expression", "qualified_name", 
            "scoped_identifier", "field_expression"
        }:
            return callee
        return None

    def _in_request_context(self, node) -> bool:
        """
        Check if node is inside a server request handler.
        
        Heuristics for server request paths:
        - Callback passed to app/router HTTP verb (Express/Koa/Router)
        - Callback to http.createServer(...) or server.on('request', ...)
        - Next.js API: exported function handler(req,res) or default export with (req,res)
        - Cloudflare/Deno: addEventListener('fetch', fn) / serve(fn)
        """
        # Find enclosing function
        fn = self._enclosing_function(node)
        if not fn:
            return False
        
        # A) Check for classic req/res signature
        params = self._get_function_parameters(fn)
        if self._has_request_response_params(params):
            return True
        
        # B) Check if function is used as route/server callback
        parent_call = self._parent_call(fn)
        if parent_call and self._is_server_callback_call(parent_call):
            return True
        
        # C) Check for Next.js API routes: exported handler(req,res)
        if self._is_exported_handler(fn, params):
            return True
        
        return False

    def _enclosing_function(self, node):
        """Find the enclosing function node."""
        current = node
        while current and hasattr(current, 'parent'):
            current = current.parent
            if hasattr(current, 'kind') and current.kind in {
                "function_expression", "arrow_function", "function_declaration", 
                "method_definition", "function_definition"
            }:
                return current
        return None

    def _get_function_parameters(self, fn_node):
        """Extract parameter names from function node."""
        if not hasattr(fn_node, 'children'):
            return []
        
        params = []
        for child in fn_node.children:
            if hasattr(child, 'kind') and child.kind in {"formal_parameters", "parameters"}:
                # Extract parameter identifiers
                for param_child in getattr(child, 'children', []):
                    if hasattr(param_child, 'kind'):
                        if param_child.kind == "identifier":
                            params.append(self._get_node_text(param_child))
                        elif param_child.kind in {"required_parameter", "optional_parameter"}:
                            # TypeScript parameters
                            for nested in getattr(param_child, 'children', []):
                                if hasattr(nested, 'kind') and nested.kind == "identifier":
                                    params.append(self._get_node_text(nested))
                                    break
        return params

    def _has_request_response_params(self, params):
        """Check if parameters include request/response names."""
        param_names = [p.lower() for p in params if p]
        
        # Check for request-like parameters
        has_request = any(
            name in param_name for param_name in param_names 
            for name in ["req", "request", "event"]
        )
        
        # Check for response-like parameters
        has_response = any(
            name in param_name for param_name in param_names 
            for name in ["res", "response", "reply", "ctx", "context"]
        )
        
        return has_request and has_response

    def _parent_call(self, fn_node):
        """Get parent call if function is passed as an argument."""
        if not hasattr(fn_node, 'parent'):
            return None
        
        parent = fn_node.parent
        
        # Check if we're in an arguments list
        if hasattr(parent, 'kind') and parent.kind in {"arguments", "argument_list"}:
            # Get the call expression
            if hasattr(parent, 'parent'):
                call_parent = parent.parent
                if hasattr(call_parent, 'kind') and call_parent.kind in ["call_expression", "function_call"]:
                    return call_parent
        
        # Direct callback case (arrow function as argument)
        if hasattr(parent, 'kind') and parent.kind in ["call_expression", "function_call"]:
            return parent
        
        return None

    def _is_server_callback_call(self, call_node):
        """Check if call is a server callback registration."""
        callee_text = self._get_callee_text(call_node).lower()
        
        # Express/Router HTTP verbs
        if any(callee_text.endswith(f".{verb}") or f".{verb}(" in callee_text for verb in self.SERVER_VERBS):
            return True
        
        # HTTP server creation
        if "createserver" in callee_text:
            return True
        
        # Event listeners
        if ".on" in callee_text:
            call_text = self._get_node_text(call_node).lower()
            if "request" in call_text or "'request'" in call_text or '"request"' in call_text:
                return True
        
        # Fetch event listener (Cloudflare Workers)
        if "addeventlistener" in callee_text:
            call_text = self._get_node_text(call_node).lower()
            if "fetch" in call_text or "'fetch'" in call_text or '"fetch"' in call_text:
                return True
        
        # Deno serve
        if "serve" in callee_text:
            return True
        
        # Fastify/other frameworks
        if any(framework in callee_text for framework in ["fastify", "koa", "hapi"]):
            return True
        
        return False

    def _is_exported_handler(self, fn_node, params):
        """Check if function is an exported API handler (Next.js style)."""
        # Look for export patterns in ancestors
        current = fn_node
        while current and hasattr(current, 'parent'):
            current = current.parent
            if hasattr(current, 'kind'):
                # export default function handler
                if current.kind in {"export_statement", "export_default_declaration"}:
                    # Must have request-like parameter
                    param_names = [p.lower() for p in params if p]
                    has_request = any(
                        name in param_name for param_name in param_names 
                        for name in ["req", "request"]
                    )
                    return has_request
        
        return False


# Export rule for registration
RULES = [PerfSynchronousFsInServerRule()]


