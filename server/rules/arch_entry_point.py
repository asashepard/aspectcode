"""KB-enriching rule: Detect application entry points.

This rule identifies where code execution begins in the application:
- HTTP/API handlers (Flask, FastAPI, Express, Spring, ASP.NET)
- CLI commands and main functions
- Event listeners and message handlers
- Background job handlers

PURPOSE: This is a KB-enriching rule. It does NOT flag problems - it provides
architectural intelligence that enriches the .aspect/flows.md file to help
AI coding agents understand where code execution starts.

SEVERITY: "info" - These are not issues, they are structural annotations.
"""

from typing import Iterator, Dict, List, Set

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext
except ImportError:
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext


class ArchEntryPointRule:
    """Detect application entry points for KB enrichment."""
    
    meta = RuleMeta(
        id="arch.entry_point",
        category="arch",
        tier=0,  # File-level analysis - no cross-file context needed
        priority="P2",  # KB enrichment, not critical issue
        autofix_safety="suggest-only",  # Informational, no autofix
        description="Detect application entry points (HTTP handlers, CLI commands, main functions, event listeners)",
        langs=["python", "typescript", "javascript", "java", "csharp", "go", "ruby", "rust"],
        surface="kb"  # KB-only: powers .aspect/ architecture knowledge, not shown to users
    )
    requires = Requires(syntax=True, raw_text=True)

    def _get_node_text(self, ctx: RuleContext, node) -> str:
        """Get text content of a syntax node."""
        try:
            if hasattr(node, 'text'):
                text = node.text
                if isinstance(text, bytes):
                    return text.decode('utf-8', errors='ignore')
                return str(text)
            elif hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
                return ctx.text[node.start_byte:node.end_byte]
            elif hasattr(node, 'value'):
                return str(node.value)
            return ""
        except:
            return ""

    # HTTP route decorators by language/framework
    HTTP_DECORATORS: Dict[str, Set[str]] = {
        "python": {
            # Flask
            "route", "get", "post", "put", "delete", "patch", "options", "head",
            # FastAPI
            "api_route",
            # Django
            "api_view",
            # Sanic
            "route", "websocket",
            # Bottle, Tornado, etc.
        },
        "javascript": set(),  # JS uses function calls not decorators
        "typescript": set(),  # TS uses function calls not decorators
        "java": {
            # Spring
            "GetMapping", "PostMapping", "PutMapping", "DeleteMapping", 
            "PatchMapping", "RequestMapping",
            # JAX-RS
            "GET", "POST", "PUT", "DELETE", "PATCH", "Path",
            # Servlet
            "WebServlet",
        },
        "csharp": {
            # ASP.NET Core
            "HttpGet", "HttpPost", "HttpPut", "HttpDelete", "HttpPatch",
            "Route", "ApiController",
        },
        "go": set(),  # Go uses http.HandleFunc
        "ruby": set(),  # Ruby on Rails uses DSL methods
        "rust": {
            # Actix-web
            "get", "post", "put", "delete", "patch",
            # Rocket
            "get", "post", "put", "delete", "patch",
        },
    }

    # Express/Koa/Fastify style - method calls on app/router object
    JS_HTTP_METHODS: Set[str] = {"get", "post", "put", "delete", "patch", "all", "options", "head"}

    # C# Minimal API style - method calls like app.MapGet(), app.MapPost()
    CSHARP_MINIMAL_API_METHODS: Set[str] = {"MapGet", "MapPost", "MapPut", "MapDelete", "MapPatch"}

    # CLI entry point patterns
    CLI_DECORATORS: Dict[str, Set[str]] = {
        "python": {"command", "group", "main", "cli"},  # Click, Typer
        "java": {"Command"},  # Picocli
        "csharp": set(),  # Usually convention-based
        "go": set(),  # Cobra uses cobra.Command
        "ruby": {"desc", "method_option"},  # Thor
        "rust": {"command", "subcommand"},  # Clap
    }

    # Main function patterns
    MAIN_PATTERNS: Dict[str, List[str]] = {
        "python": ["if __name__ == '__main__'", "def main(", "@app.command", "cli.add_command"],
        "javascript": ["module.exports"],  # CommonJS entry
        "typescript": [],  # TS entry points detected via decorators/handlers
        # Note: "export default" is detected separately with path filtering
        "java": ["public static void main(String"],
        "csharp": ["static void Main(", "static async Task Main(", "static int Main("],
        "go": ["func main()"],
        "ruby": ["if __FILE__ == $0", "if __FILE__ == $PROGRAM_NAME"],
        "rust": ["fn main()"],
    }

    # Paths that indicate a file with "export default" is an entry point
    ENTRY_POINT_PATHS = {
        "/pages/", "/app/", "/routes/", "/api/",  # Next.js, Remix, etc.
        "/views/", "/screens/",  # Mobile/SPA
        "/endpoints/", "/handlers/",
    }

    # Event listener patterns
    EVENT_PATTERNS: Dict[str, List[str]] = {
        "python": [
            "on_event", "add_event_handler", "@receiver", "connect", "subscribe",
            "@celery.task", "@shared_task", "@task", "@periodic_task",
            "on_message", "handle_",
        ],
        "javascript": [
            ".on(", "addEventListener", ".subscribe(", "socket.on(",
            "EventEmitter", "@OnEvent", "@SubscribeMessage",
        ],
        "typescript": [
            ".on(", "addEventListener", ".subscribe(", "socket.on(",
            "EventEmitter", "@OnEvent", "@SubscribeMessage",
        ],
        "java": [
            "@EventListener", "@KafkaListener", "@JmsListener", 
            "@RabbitListener", "@SqsListener", "@Scheduled",
        ],
        "csharp": [
            "[EventHandler]", "event ", "+= ", "Subscribe(",
            "[Function]",  # Azure Functions
        ],
        "go": ["HandleFunc", "Handle", "ListenAndServe"],
        "ruby": ["on ", "subscribe", "after_", "before_"],
        "rust": ["#[handler]", "on_event", "subscribe"],
    }

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Detect entry points and emit info-level findings for KB enrichment."""
        if not ctx.syntax:
            return

        lang = ctx.language
        if lang not in self.HTTP_DECORATORS:
            return

        text = ctx.text
        
        # Track what we've found to avoid duplicates
        found_spans: Set[tuple] = set()
        
        # 1. Check for HTTP route handlers (decorators)
        for node in ctx.walk_nodes():
            entry_info = self._check_http_decorator(ctx, node, lang)
            if entry_info:
                span = entry_info['span']
                if span not in found_spans:
                    found_spans.add(span)
                    yield self._make_finding(ctx, entry_info)
                continue

            # 2. Check for Express/Koa style HTTP handlers (JS/TS)
            if lang in ("javascript", "typescript"):
                entry_info = self._check_js_http_handler(ctx, node)
                if entry_info:
                    span = entry_info['span']
                    if span not in found_spans:
                        found_spans.add(span)
                        yield self._make_finding(ctx, entry_info)
                    continue

            # 2b. Check for C# Minimal API style handlers (app.MapGet, etc.)
            if lang == "csharp":
                entry_info = self._check_csharp_minimal_api(ctx, node)
                if entry_info:
                    span = entry_info['span']
                    if span not in found_spans:
                        found_spans.add(span)
                        yield self._make_finding(ctx, entry_info)
                    continue

            # 3. Check for event listeners
            entry_info = self._check_event_listener(ctx, node, lang, text)
            if entry_info:
                span = entry_info['span']
                if span not in found_spans:
                    found_spans.add(span)
                    yield self._make_finding(ctx, entry_info)
                continue

            # 4. Check for CLI commands
            entry_info = self._check_cli_command(ctx, node, lang)
            if entry_info:
                span = entry_info['span']
                if span not in found_spans:
                    found_spans.add(span)
                    yield self._make_finding(ctx, entry_info)
                continue

        # 5. Check for main function patterns (text-based for simplicity)
        for entry_info in self._check_main_patterns(ctx, lang, text, found_spans):
            yield self._make_finding(ctx, entry_info)

    def _check_http_decorator(self, ctx: RuleContext, node, lang: str) -> dict | None:
        """Check if node is an HTTP route decorator."""
        node_type = getattr(node, 'type', '')
        
        # Python: @app.route, @router.get, etc.
        if lang == "python" and node_type == 'decorator':
            decorator_text = self._get_node_text(ctx, node)
            if not decorator_text:
                return None
            
            for pattern in self.HTTP_DECORATORS["python"]:
                if f".{pattern}(" in decorator_text or f"@{pattern}(" in decorator_text:
                    # Get the route path if present
                    route = self._extract_route_path(decorator_text)
                    method = pattern.upper() if pattern in ("get", "post", "put", "delete", "patch") else "HTTP"
                    start, end = ctx.node_span(node)
                    return {
                        'type': 'http_handler',
                        'method': method,
                        'route': route,
                        'span': (start, end),
                        'name': self._get_decorated_function_name(ctx, node),
                    }
        
        # Java: @GetMapping, @PostMapping, etc.
        if lang == "java" and node_type in ('annotation', 'marker_annotation', 'normal_annotation'):
            annotation_text = self._get_node_text(ctx, node)
            if not annotation_text:
                return None
                
            for pattern in self.HTTP_DECORATORS["java"]:
                if pattern in annotation_text:
                    route = self._extract_route_path(annotation_text)
                    method = pattern.replace("Mapping", "").upper() if "Mapping" in pattern else "HTTP"
                    start, end = ctx.node_span(node)
                    return {
                        'type': 'http_handler',
                        'method': method,
                        'route': route,
                        'span': (start, end),
                        'name': self._get_decorated_function_name(ctx, node),
                    }

        # C#: [HttpGet], [Route], etc.
        if lang == "csharp" and node_type in ('attribute', 'attribute_list'):
            attr_text = self._get_node_text(ctx, node)
            if not attr_text:
                return None
                
            for pattern in self.HTTP_DECORATORS["csharp"]:
                if pattern in attr_text:
                    route = self._extract_route_path(attr_text)
                    method = pattern.replace("Http", "").upper() if "Http" in pattern else "HTTP"
                    start, end = ctx.node_span(node)
                    return {
                        'type': 'http_handler',
                        'method': method,
                        'route': route,
                        'span': (start, end),
                        'name': self._get_decorated_function_name(ctx, node),
                    }

        return None

    def _check_js_http_handler(self, ctx: RuleContext, node) -> dict | None:
        """Check for Express/Koa/Fastify style route handlers."""
        node_type = getattr(node, 'type', '')
        
        if node_type not in ('call_expression', 'method_call'):
            return None
        
        call_text = self._get_node_text(ctx, node)
        if not call_text:
            return None
        
        # Look for app.get, router.post, etc.
        for method in self.JS_HTTP_METHODS:
            # Match patterns like app.get(, router.post(, etc.
            patterns = [f".{method}(", f"['{method}'](", f'["{method}"](']
            for pattern in patterns:
                if pattern in call_text:
                    # Must have a route path (string starting with /) to be an HTTP handler
                    # This filters out test framework methods like test.use({...})
                    route = self._extract_route_path(call_text)
                    if not route or route == "/":
                        # Check if there's actually a route string in the call
                        # Look for quoted strings that look like routes
                        import re
                        route_match = re.search(r'["\']/([\w/:*-]*)["\']', call_text)
                        if not route_match:
                            # No route path found - likely not an HTTP handler
                            # (e.g., test.use({config}), app.use(middleware))
                            continue
                        route = "/" + route_match.group(1) if route_match.group(1) else "/"
                    
                    start, end = ctx.node_span(node)
                    return {
                        'type': 'http_handler',
                        'method': method.upper(),
                        'route': route,
                        'span': (start, end),
                        'name': f'{method.upper()} handler',
                    }
        
        return None

    def _check_csharp_minimal_api(self, ctx: RuleContext, node) -> dict | None:
        """Check for C# Minimal API style route handlers (app.MapGet, app.MapPost, etc.)."""
        node_type = getattr(node, 'type', '')
        
        if node_type not in ('invocation_expression', 'call_expression'):
            return None
        
        call_text = self._get_node_text(ctx, node)
        if not call_text:
            return None
        
        # Look for app.MapGet, app.MapPost, etc.
        for method in self.CSHARP_MINIMAL_API_METHODS:
            if f".{method}(" in call_text:
                route = self._extract_route_path(call_text)
                if not route or route == "/":
                    # Look for route string
                    import re
                    route_match = re.search(r'["\']/([\w/:*{}-]*)["\']', call_text)
                    if route_match:
                        route = "/" + route_match.group(1) if route_match.group(1) else "/"
                    else:
                        route = "/"
                
                http_method = method.replace("Map", "").upper()
                start, end = ctx.node_span(node)
                return {
                    'type': 'http_handler',
                    'method': http_method,
                    'route': route,
                    'span': (start, end),
                    'name': f'{http_method} handler (Minimal API)',
                }
        
        return None

    def _check_event_listener(self, ctx: RuleContext, node, lang: str, text: str) -> dict | None:
        """Check for event listener registrations."""
        node_type = getattr(node, 'type', '')
        
        # Check decorators for event handlers
        if node_type in ('decorator', 'annotation', 'marker_annotation', 'attribute'):
            node_text = self._get_node_text(ctx, node)
            if not node_text:
                return None
            
            patterns = self.EVENT_PATTERNS.get(lang, [])
            for pattern in patterns:
                if pattern.startswith("@") and pattern in node_text:
                    start, end = ctx.node_span(node)
                    event_name = self._extract_event_name(node_text)
                    return {
                        'type': 'event_listener',
                        'event': event_name,
                        'span': (start, end),
                        'name': self._get_decorated_function_name(ctx, node),
                    }

        # Check for Celery/background task decorators in Python
        if lang == "python" and node_type == 'decorator':
            node_text = self._get_node_text(ctx, node)
            if node_text and any(p in node_text for p in ["@task", "@celery", "@shared_task", "@periodic_task"]):
                start, end = ctx.node_span(node)
                return {
                    'type': 'background_task',
                    'event': 'celery_task',
                    'span': (start, end),
                    'name': self._get_decorated_function_name(ctx, node),
                }

        return None

    def _check_cli_command(self, ctx: RuleContext, node, lang: str) -> dict | None:
        """Check for CLI command decorators."""
        node_type = getattr(node, 'type', '')
        
        if node_type not in ('decorator', 'annotation', 'attribute'):
            return None
        
        node_text = self._get_node_text(ctx, node)
        if not node_text:
            return None
        
        patterns = self.CLI_DECORATORS.get(lang, set())
        for pattern in patterns:
            if f"@{pattern}" in node_text or f".{pattern}(" in node_text or f"@click.{pattern}" in node_text:
                start, end = ctx.node_span(node)
                cmd_name = self._extract_command_name(node_text)
                return {
                    'type': 'cli_command',
                    'command': cmd_name,
                    'span': (start, end),
                    'name': self._get_decorated_function_name(ctx, node),
                }

        return None

    def _check_main_patterns(self, ctx: RuleContext, lang: str, text: str, found_spans: Set[tuple]) -> Iterator[dict]:
        """Check for main function patterns using text search."""
        patterns = self.MAIN_PATTERNS.get(lang, [])
        
        for pattern in patterns:
            idx = text.find(pattern)
            if idx != -1:
                # Find the line containing this pattern
                line_start = text.rfind('\n', 0, idx) + 1
                line_end = text.find('\n', idx)
                if line_end == -1:
                    line_end = len(text)
                
                span = (idx, idx + len(pattern))
                if span not in found_spans:
                    found_spans.add(span)
                    yield {
                        'type': 'main_function',
                        'pattern': pattern,
                        'span': span,
                        'name': 'main',
                    }
        
        # For JS/TS: Check "export default" only in entry-point paths
        if lang in ("javascript", "typescript"):
            file_path_lower = ctx.file_path.lower().replace('\\', '/')
            is_entry_path = any(p in file_path_lower for p in self.ENTRY_POINT_PATHS)
            
            if is_entry_path and "export default" in text:
                idx = text.find("export default")
                span = (idx, idx + len("export default"))
                if span not in found_spans:
                    found_spans.add(span)
                    # Try to extract the component/function name
                    name = self._extract_export_name(text, idx)
                    yield {
                        'type': 'page_entry',
                        'pattern': 'export default',
                        'span': span,
                        'name': name or 'page',
                    }

    def _make_finding(self, ctx: RuleContext, entry_info: dict) -> Finding:
        """Create a Finding for the entry point."""
        entry_type = entry_info['type']
        name = entry_info.get('name', 'unknown')
        
        if entry_type == 'http_handler':
            method = entry_info.get('method', 'HTTP')
            route = entry_info.get('route', '/')
            message = f"HTTP entry point: {method} {route} → {name}"
        elif entry_type == 'event_listener':
            event = entry_info.get('event', 'event')
            message = f"Event listener: {event} → {name}"
        elif entry_type == 'background_task':
            message = f"Background task: {name}"
        elif entry_type == 'cli_command':
            cmd = entry_info.get('command', 'command')
            message = f"CLI command: {cmd} → {name}"
        elif entry_type == 'main_function':
            message = f"Main entry point: {name}"
        elif entry_type == 'page_entry':
            message = f"Page entry point: {name}"
        else:
            message = f"Entry point: {name}"

        start, end = entry_info['span']
        return Finding(
            rule=self.meta.id,
            message=message,
            file=ctx.file_path,
            start_byte=start,
            end_byte=end,
            severity="info",  # KB enrichment - not an issue
            meta={
                'entry_type': entry_type,
                **{k: v for k, v in entry_info.items() if k not in ('span',)}
            }
        )

    def _extract_route_path(self, text: str) -> str:
        """Extract route path from decorator/attribute text."""
        import re
        # Match quoted strings that look like routes
        patterns = [
            r'["\'](/[^"\']*)["\']',  # "/path/to/route"
            r'path\s*=\s*["\']([^"\']+)["\']',  # path="/route"
            r'value\s*=\s*["\']([^"\']+)["\']',  # value="/route" (Spring)
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                return match.group(1)
        return "/"

    def _extract_event_name(self, text: str) -> str:
        """Extract event name from event decorator."""
        import re
        match = re.search(r'["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)
        return "event"

    def _extract_command_name(self, text: str) -> str:
        """Extract command name from CLI decorator."""
        import re
        match = re.search(r'["\']([^"\']+)["\']', text)
        if match:
            return match.group(1)
        # For Click/Typer, function name is the command name
        return "command"

    def _get_decorated_function_name(self, ctx: RuleContext, decorator_node) -> str:
        """Get the name of the function that has this decorator."""
        # Try to find the parent function definition
        parent = getattr(decorator_node, 'parent', None)
        if parent:
            # Look for function_definition child
            for child in getattr(parent, 'children', []):
                child_type = getattr(child, 'type', '')
                if child_type in ('function_definition', 'method_declaration', 'function_declaration'):
                    # Get the name node
                    for name_child in getattr(child, 'children', []):
                        if getattr(name_child, 'type', '') in ('identifier', 'name'):
                            return self._get_node_text(ctx, name_child) or 'handler'
        return 'handler'

    def _extract_export_name(self, text: str, idx: int) -> str | None:
        """Extract the name from an export default statement."""
        import re
        # Get context after "export default"
        context = text[idx:idx + 100]
        
        # "export default function Name" or "export default class Name"
        match = re.search(r'export\s+default\s+(?:function|class)\s+(\w+)', context)
        if match:
            return match.group(1)
        
        # "export default Name" (identifier)
        match = re.search(r'export\s+default\s+(\w+)', context)
        if match and match.group(1) not in ('function', 'class', 'async'):
            return match.group(1)
        
        return None


# Module-level instance for rule registration
rule = ArchEntryPointRule()

