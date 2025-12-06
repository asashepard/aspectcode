"""Tests for perf.synchronous_fs_in_server rule."""

import pytest
from unittest.mock import Mock

from rules.perf_synchronous_fs_in_server import PerfSynchronousFsInServerRule


class MockNode:
    """Mock tree-sitter node for testing."""
    
    def __init__(self, kind, text="", start_pos=(0, 0), end_pos=(0, 10), children=None, parent=None):
        self.kind = kind
        self.text = text.encode('utf-8') if isinstance(text, str) else text
        self.start_pos = start_pos
        self.end_pos = end_pos
        self.children = children or []
        self.parent = parent
        
        # Set parent references for children
        for child in self.children:
            child.parent = self

    def __repr__(self):
        return f"MockNode({self.kind})"


class MockSyntaxTree:
    """Mock syntax tree for testing."""
    
    def __init__(self, nodes):
        self.nodes = nodes

    def walk(self):
        """Return all nodes for walking."""
        return self.nodes
    
    def node_span(self, node):
        """Return node span."""
        return node.start_pos, node.end_pos


def create_express_handler_with_sync_fs():
    """Create mock nodes for Express handler with sync fs call."""
    # fs.readFileSync call
    fs_callee = MockNode("member_expression", "fs.readFileSync", start_pos=(3, 15), end_pos=(3, 30))
    fs_call = MockNode("call_expression", 'fs.readFileSync("file.txt")', start_pos=(3, 15), end_pos=(3, 45), children=[fs_callee])
    
    # Function parameters (req, res)
    req_param = MockNode("identifier", "req")
    res_param = MockNode("identifier", "res")
    params = MockNode("formal_parameters", children=[req_param, res_param])
    
    # Arrow function handler
    handler_fn = MockNode("arrow_function", children=[params])
    
    # app.get call
    app_callee = MockNode("member_expression", "app.get")
    get_call = MockNode("call_expression", 'app.get("/path", (req, res) => {...})', children=[app_callee, handler_fn])
    
    # Set up parent relationships
    fs_callee.parent = fs_call
    fs_call.parent = handler_fn
    req_param.parent = params
    res_param.parent = params
    params.parent = handler_fn
    handler_fn.parent = get_call
    app_callee.parent = get_call
    
    return [get_call, app_callee, handler_fn, params, req_param, res_param, fs_call, fs_callee]


def create_startup_sync_fs():
    """Create mock nodes for sync fs call outside request handler."""
    # fs.readFileSync call at module level
    fs_callee = MockNode("member_expression", "fs.readFileSync", start_pos=(1, 10), end_pos=(1, 25))
    fs_call = MockNode("call_expression", 'fs.readFileSync("config.json")', start_pos=(1, 10), end_pos=(1, 40), children=[fs_callee])
    
    # Assignment at module level (not in request handler)
    assignment = MockNode("assignment_expression", children=[fs_call])
    program = MockNode("program", children=[assignment])
    
    # Set up parent relationships
    fs_callee.parent = fs_call
    fs_call.parent = assignment
    assignment.parent = program
    
    return [program, assignment, fs_call, fs_callee]


def create_async_fs_handler():
    """Create mock nodes for async fs usage in handler."""
    # fs.promises.readFile call
    fs_callee = MockNode("member_expression", "fs.promises.readFile", start_pos=(3, 15), end_pos=(3, 35))
    fs_call = MockNode("call_expression", 'await fs.promises.readFile("file.txt")', start_pos=(3, 9), end_pos=(3, 50), children=[fs_callee])
    
    # Function parameters (req, res)
    req_param = MockNode("identifier", "req")
    res_param = MockNode("identifier", "res")
    params = MockNode("formal_parameters", children=[req_param, res_param])
    
    # Async arrow function handler
    handler_fn = MockNode("arrow_function", children=[params])
    
    # app.get call
    app_callee = MockNode("member_expression", "app.get")
    get_call = MockNode("call_expression", 'app.get("/path", async (req, res) => {...})', children=[app_callee, handler_fn])
    
    # Set up parent relationships
    fs_callee.parent = fs_call
    fs_call.parent = handler_fn
    req_param.parent = params
    res_param.parent = params
    params.parent = handler_fn
    handler_fn.parent = get_call
    app_callee.parent = get_call
    
    return [get_call, app_callee, handler_fn, params, req_param, res_param, fs_call, fs_callee]


class TestPerfSynchronousFsInServerRule:
    """Test cases for synchronous fs in server rule."""

    def setup_method(self):
        """Set up test fixtures."""
        self.rule = PerfSynchronousFsInServerRule()
        
        self.mock_ctx = Mock()
        self.mock_ctx.language = "javascript"
        self.mock_ctx.file_path = "server.js"

    def test_positive_case_express_get_handler(self):
        """Test detection of sync fs in Express GET handler."""
        nodes = create_express_handler_with_sync_fs()
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Synchronous fs call in request handler" in findings[0].message
        assert "async fs APIs" in findings[0].message
        assert findings[0].severity == "warn"

    def test_positive_case_http_create_server(self):
        """Test detection of sync fs in http.createServer handler."""
        # fs.existsSync call
        fs_callee = MockNode("member_expression", "fs.existsSync", start_pos=(2, 5), end_pos=(2, 18))
        fs_call = MockNode("call_expression", 'fs.existsSync("config.json")', start_pos=(2, 5), end_pos=(2, 35), children=[fs_callee])
        
        # Function parameters (req, res)
        req_param = MockNode("identifier", "req")
        res_param = MockNode("identifier", "res")
        params = MockNode("formal_parameters", children=[req_param, res_param])
        
        # Handler function
        handler_fn = MockNode("function_expression", children=[params])
        
        # http.createServer call
        http_callee = MockNode("member_expression", "http.createServer")
        create_server_call = MockNode("call_expression", "http.createServer((req, res) => {...})", children=[http_callee, handler_fn])
        
        # Set up parent relationships
        fs_callee.parent = fs_call
        fs_call.parent = handler_fn
        req_param.parent = params
        res_param.parent = params
        params.parent = handler_fn
        handler_fn.parent = create_server_call
        http_callee.parent = create_server_call
        
        nodes = [create_server_call, http_callee, handler_fn, params, req_param, res_param, fs_call, fs_callee]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Synchronous fs call in request handler" in findings[0].message

    def test_positive_case_nextjs_api_handler(self):
        """Test detection of sync fs in Next.js API handler."""
        # fs.readdirSync call
        fs_callee = MockNode("member_expression", "fs.readdirSync", start_pos=(2, 5), end_pos=(2, 18))
        fs_call = MockNode("call_expression", 'fs.readdirSync("/var/log")', start_pos=(2, 5), end_pos=(2, 32), children=[fs_callee])
        
        # Function parameters (req, res)
        req_param = MockNode("identifier", "req")
        res_param = MockNode("identifier", "res")
        params = MockNode("formal_parameters", children=[req_param, res_param])
        
        # Exported default function
        handler_fn = MockNode("function_declaration", children=[params])
        export_default = MockNode("export_default_declaration", children=[handler_fn])
        
        # Set up parent relationships
        fs_callee.parent = fs_call
        fs_call.parent = handler_fn
        req_param.parent = params
        res_param.parent = params
        params.parent = handler_fn
        handler_fn.parent = export_default
        
        nodes = [export_default, handler_fn, params, req_param, res_param, fs_call, fs_callee]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Synchronous fs call in request handler" in findings[0].message

    def test_positive_case_cloudflare_worker(self):
        """Test detection of sync fs in Cloudflare Worker."""
        # fs.statSync call
        fs_callee = MockNode("member_expression", "fs.statSync", start_pos=(2, 5), end_pos=(2, 16))
        fs_call = MockNode("call_expression", 'fs.statSync("file")', start_pos=(2, 5), end_pos=(2, 25), children=[fs_callee])
        
        # Event parameter
        event_param = MockNode("identifier", "event")
        params = MockNode("formal_parameters", children=[event_param])
        
        # Event handler function
        handler_fn = MockNode("arrow_function", children=[params])
        
        # addEventListener call
        listener_callee = MockNode("identifier", "addEventListener")
        listener_call = MockNode("call_expression", 'addEventListener("fetch", event => {...})', children=[listener_callee, handler_fn])
        
        # Set up parent relationships
        fs_callee.parent = fs_call
        fs_call.parent = handler_fn
        event_param.parent = params
        params.parent = handler_fn
        handler_fn.parent = listener_call
        listener_callee.parent = listener_call
        
        nodes = [listener_call, listener_callee, handler_fn, params, event_param, fs_call, fs_callee]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Synchronous fs call in request handler" in findings[0].message

    def test_positive_case_deno_serve(self):
        """Test detection of sync fs in Deno serve handler."""
        # fs.readFileSync call
        fs_callee = MockNode("member_expression", "fs.readFileSync", start_pos=(2, 5), end_pos=(2, 20))
        fs_call = MockNode("call_expression", 'fs.readFileSync("file")', start_pos=(2, 5), end_pos=(2, 30), children=[fs_callee])
        
        # Request parameter
        req_param = MockNode("identifier", "req")
        params = MockNode("formal_parameters", children=[req_param])
        
        # Handler function
        handler_fn = MockNode("arrow_function", children=[params])
        
        # serve call
        serve_callee = MockNode("identifier", "serve")
        serve_call = MockNode("call_expression", "serve(req => {...})", children=[serve_callee, handler_fn])
        
        # Set up parent relationships
        fs_callee.parent = fs_call
        fs_call.parent = handler_fn
        req_param.parent = params
        params.parent = handler_fn
        handler_fn.parent = serve_call
        serve_callee.parent = serve_call
        
        nodes = [serve_call, serve_callee, handler_fn, params, req_param, fs_call, fs_callee]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Synchronous fs call in request handler" in findings[0].message

    def test_positive_case_typescript_router(self):
        """Test detection of sync fs in TypeScript router."""
        # fs.openSync call
        fs_callee = MockNode("member_expression", "fs.openSync", start_pos=(2, 5), end_pos=(2, 16))
        fs_call = MockNode("call_expression", 'fs.openSync("file", "r")', start_pos=(2, 5), end_pos=(2, 30), children=[fs_callee])
        
        # TypeScript parameters
        req_param = MockNode("required_parameter", children=[MockNode("identifier", "req")])
        res_param = MockNode("required_parameter", children=[MockNode("identifier", "res")])
        params = MockNode("formal_parameters", children=[req_param, res_param])
        
        # Async function
        handler_fn = MockNode("arrow_function", children=[params])
        
        # router.post call
        router_callee = MockNode("member_expression", "router.post")
        post_call = MockNode("call_expression", 'router.post("/path", async (req, res) => {...})', children=[router_callee, handler_fn])
        
        # Set up parent relationships
        fs_callee.parent = fs_call
        fs_call.parent = handler_fn
        req_param.parent = params
        res_param.parent = params
        params.parent = handler_fn
        handler_fn.parent = post_call
        router_callee.parent = post_call
        
        nodes = [post_call, router_callee, handler_fn, params, req_param, res_param, fs_call, fs_callee]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        self.mock_ctx.language = "typescript"
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Synchronous fs call in request handler" in findings[0].message

    def test_positive_case_fastify_handler(self):
        """Test detection of sync fs in Fastify handler."""
        # fs.writeFileSync call
        fs_callee = MockNode("member_expression", "fs.writeFileSync", start_pos=(2, 5), end_pos=(2, 20))
        fs_call = MockNode("call_expression", 'fs.writeFileSync("/tmp/x", "data")', start_pos=(2, 5), end_pos=(2, 40), children=[fs_callee])
        
        # Function parameters (req, reply)
        req_param = MockNode("identifier", "req")
        reply_param = MockNode("identifier", "reply")
        params = MockNode("formal_parameters", children=[req_param, reply_param])
        
        # Handler function
        handler_fn = MockNode("arrow_function", children=[params])
        
        # fastify.get call
        fastify_callee = MockNode("member_expression", "fastify.get")
        get_call = MockNode("call_expression", 'fastify.get("/path", (req, reply) => {...})', children=[fastify_callee, handler_fn])
        
        # Set up parent relationships
        fs_callee.parent = fs_call
        fs_call.parent = handler_fn
        req_param.parent = params
        reply_param.parent = params
        params.parent = handler_fn
        handler_fn.parent = get_call
        fastify_callee.parent = get_call
        
        nodes = [get_call, fastify_callee, handler_fn, params, req_param, reply_param, fs_call, fs_callee]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Synchronous fs call in request handler" in findings[0].message

    def test_negative_case_startup_sync_fs(self):
        """Test no detection when sync fs is used at startup (module level)."""
        nodes = create_startup_sync_fs()
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 0

    def test_negative_case_async_fs_in_handler(self):
        """Test no detection when using async fs APIs in handler."""
        nodes = create_async_fs_handler()
        
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 0

    def test_negative_case_fs_promises_usage(self):
        """Test no detection when using fs.promises APIs."""
        # fs.promises.access call
        fs_callee = MockNode("member_expression", "fs.promises.access", start_pos=(3, 15), end_pos=(3, 32))
        fs_call = MockNode("call_expression", 'await fs.promises.access("file")', start_pos=(3, 9), end_pos=(3, 42), children=[fs_callee])
        
        # Function parameters (req, res)
        req_param = MockNode("identifier", "req")
        res_param = MockNode("identifier", "res")
        params = MockNode("formal_parameters", children=[req_param, res_param])
        
        # Async handler function
        handler_fn = MockNode("arrow_function", children=[params])
        
        # router.get call
        router_callee = MockNode("member_expression", "router.get")
        get_call = MockNode("call_expression", 'router.get("/path", async (req, res) => {...})', children=[router_callee, handler_fn])
        
        # Set up parent relationships
        fs_callee.parent = fs_call
        fs_call.parent = handler_fn
        req_param.parent = params
        res_param.parent = params
        params.parent = handler_fn
        handler_fn.parent = get_call
        router_callee.parent = get_call
        
        nodes = [get_call, router_callee, handler_fn, params, req_param, res_param, fs_call, fs_callee]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 0

    def test_negative_case_non_fs_sync_call(self):
        """Test no detection for non-fs sync calls."""
        # Some other sync call (not fs)
        other_callee = MockNode("member_expression", "util.parseSync", start_pos=(3, 15), end_pos=(3, 28))
        other_call = MockNode("call_expression", 'util.parseSync(data)', start_pos=(3, 15), end_pos=(3, 35), children=[other_callee])
        
        # Function parameters (req, res)
        req_param = MockNode("identifier", "req")
        res_param = MockNode("identifier", "res")
        params = MockNode("formal_parameters", children=[req_param, res_param])
        
        # Handler function
        handler_fn = MockNode("arrow_function", children=[params])
        
        # app.get call
        app_callee = MockNode("member_expression", "app.get")
        get_call = MockNode("call_expression", 'app.get("/path", (req, res) => {...})', children=[app_callee, handler_fn])
        
        # Set up parent relationships
        other_callee.parent = other_call
        other_call.parent = handler_fn
        req_param.parent = params
        res_param.parent = params
        params.parent = handler_fn
        handler_fn.parent = get_call
        app_callee.parent = get_call
        
        nodes = [get_call, app_callee, handler_fn, params, req_param, res_param, other_call, other_callee]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 0

    def test_multiple_sync_fs_calls_in_handler(self):
        """Test detection of multiple sync fs calls in single handler."""
        # First fs call: fs.readFileSync
        fs_callee1 = MockNode("member_expression", "fs.readFileSync", start_pos=(3, 15), end_pos=(3, 30))
        fs_call1 = MockNode("call_expression", 'fs.readFileSync("file1")', start_pos=(3, 15), end_pos=(3, 40), children=[fs_callee1])
        
        # Second fs call: fs.existsSync
        fs_callee2 = MockNode("member_expression", "fs.existsSync", start_pos=(4, 15), end_pos=(4, 27))
        fs_call2 = MockNode("call_expression", 'fs.existsSync("file2")', start_pos=(4, 15), end_pos=(4, 38), children=[fs_callee2])
        
        # Function parameters (req, res)
        req_param = MockNode("identifier", "req")
        res_param = MockNode("identifier", "res")
        params = MockNode("formal_parameters", children=[req_param, res_param])
        
        # Handler function
        handler_fn = MockNode("arrow_function", children=[params])
        
        # app.post call
        app_callee = MockNode("member_expression", "app.post")
        post_call = MockNode("call_expression", 'app.post("/path", (req, res) => {...})', children=[app_callee, handler_fn])
        
        # Set up parent relationships
        fs_callee1.parent = fs_call1
        fs_call1.parent = handler_fn
        fs_callee2.parent = fs_call2
        fs_call2.parent = handler_fn
        req_param.parent = params
        res_param.parent = params
        params.parent = handler_fn
        handler_fn.parent = post_call
        app_callee.parent = post_call
        
        nodes = [post_call, app_callee, handler_fn, params, req_param, res_param, fs_call1, fs_callee1, fs_call2, fs_callee2]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 2
        for finding in findings:
            assert "Synchronous fs call in request handler" in finding.message

    def test_heuristic_sync_fs_detection(self):
        """Test heuristic detection of sync fs calls (endsWith 'Sync')."""
        # Custom fs sync call: fs.customSync
        fs_callee = MockNode("member_expression", "fs.customSync", start_pos=(3, 15), end_pos=(3, 27))
        fs_call = MockNode("call_expression", 'fs.customSync()', start_pos=(3, 15), end_pos=(3, 30), children=[fs_callee])
        
        # Function parameters (req, res)
        req_param = MockNode("identifier", "req")
        res_param = MockNode("identifier", "res")
        params = MockNode("formal_parameters", children=[req_param, res_param])
        
        # Handler function
        handler_fn = MockNode("arrow_function", children=[params])
        
        # app.get call
        app_callee = MockNode("member_expression", "app.get")
        get_call = MockNode("call_expression", 'app.get("/path", (req, res) => {...})', children=[app_callee, handler_fn])
        
        # Set up parent relationships
        fs_callee.parent = fs_call
        fs_call.parent = handler_fn
        req_param.parent = params
        res_param.parent = params
        params.parent = handler_fn
        handler_fn.parent = get_call
        app_callee.parent = get_call
        
        nodes = [get_call, app_callee, handler_fn, params, req_param, res_param, fs_call, fs_callee]
        syntax_tree = MockSyntaxTree(nodes)
        self.mock_ctx.syntax = syntax_tree
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 1
        assert "Synchronous fs call in request handler" in findings[0].message

    def test_no_syntax_tree(self):
        """Test graceful handling when no syntax tree is available."""
        self.mock_ctx.syntax = None
        
        findings = list(self.rule.visit(self.mock_ctx))
        
        assert len(findings) == 0

    def test_rule_metadata(self):
        """Test rule metadata is correctly set."""
        assert self.rule.meta.id == "perf.synchronous_fs_in_server"
        assert self.rule.meta.category == "perf"
        assert self.rule.meta.tier == 0
        assert self.rule.meta.priority == "P1"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert len(self.rule.meta.langs) == 2
        assert "javascript" in self.rule.meta.langs
        assert "typescript" in self.rule.meta.langs

