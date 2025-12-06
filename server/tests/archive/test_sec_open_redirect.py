"""Tests for sec.open_redirect rule

Tests open redirect detection across multiple languages, covering:
- Redirect function/method calls with user input
- Raw Location header assignments
- Validation patterns that should prevent alerts
- Framework-specific secure redirect helpers
"""

import pytest
from unittest.mock import Mock

from engine.types import RuleContext, Finding
from rules.sec_open_redirect import SecOpenRedirectRule


class TestSecOpenRedirectRule:
    """Test suite for SecOpenRedirectRule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = SecOpenRedirectRule()
    
    def _create_mock_context(self, code: str, language: str, file_path: str = "test.py"):
        """Create a mock context for testing."""
        # Create a simple mock node structure
        mock_node = Mock()
        mock_node.kind = "call_expression"
        mock_node.type = "call_expression"
        mock_node.text = code.encode('utf-8')
        mock_node.start_byte = 0
        mock_node.end_byte = len(code)
        mock_node.children = []
        
        # Create argument nodes if it's a function call
        if '(' in code and ')' in code:
            arg_start = code.find('(') + 1
            arg_end = code.rfind(')')
            if arg_start < arg_end:
                arg_text = code[arg_start:arg_end].strip()
                if arg_text:
                    arg_node = Mock()
                    arg_node.kind = "identifier"
                    arg_node.type = "identifier" 
                    arg_node.text = arg_text.encode('utf-8')
                    arg_node.start_byte = arg_start
                    arg_node.end_byte = arg_end
                    arg_node.children = []
                    
                    args_node = Mock()
                    args_node.kind = "arguments"
                    args_node.type = "arguments"
                    args_node.children = [arg_node]
                    
                    mock_node.children = [args_node]
        
        mock_tree = Mock()
        mock_tree.children = [mock_node]
        
        context = Mock(spec=RuleContext)
        context.text = code
        context.language = language
        context.file_path = file_path
        context.tree = mock_tree
        
        return context
    
    def _run_rule(self, code: str, language: str) -> list:
        """Helper to run rule on code and return findings."""
        context = self._create_mock_context(code, language)
        findings = list(self.rule.visit(context))
        return findings
    
    def test_rule_metadata(self):
        """Test that rule has correct metadata."""
        assert self.rule.meta.id == "sec.open_redirect"
        assert self.rule.meta.category == "sec"
        assert self.rule.meta.priority == "P1"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert self.rule.requires.syntax is True
        assert self.rule.requires.scopes is True
        assert self.rule.requires.raw_text is True
        assert "javascript" in self.rule.meta.langs
        assert "python" in self.rule.meta.langs
        assert "ruby" in self.rule.meta.langs
        assert "java" in self.rule.meta.langs
        assert "csharp" in self.rule.meta.langs
        assert len(self.rule.meta.langs) == 6
    
    # Positive test cases (should detect open redirects)
    
    def test_positive_javascript_express_redirect(self):
        """Test detection of Express.js redirect with user input."""
        code = "app.get('/login', (req,res) => { const next = req.query.next; res.redirect(next); });"
        findings = self._run_rule(code, "javascript")
        assert len(findings) > 0
        assert any("open redirect" in f.message.lower() for f in findings)
    
    def test_positive_javascript_query_param(self):
        """Test detection of redirect using query parameter."""
        code = "res.redirect(req.query.next);"
        findings = self._run_rule(code, "javascript")
        assert len(findings) > 0
    
    def test_positive_typescript_redirect(self):
        """Test detection of TypeScript redirect with user input."""
        code = "app.get('/login', (req,res) => { const nxt = req.query['next'] as string; res.redirect(nxt); });"
        findings = self._run_rule(code, "typescript")
        assert len(findings) > 0
    
    def test_positive_python_flask_redirect(self):
        """Test detection of Flask redirect with request args."""
        code = """
from flask import request, redirect
def go():
    return redirect(request.args.get('next'))
"""
        findings = self._run_rule(code, "python")
        assert len(findings) > 0
        assert any("open redirect" in f.message.lower() for f in findings)
    
    def test_positive_python_django_redirect(self):
        """Test detection of Django redirect with user input."""
        code = "from django.shortcuts import redirect; redirect(request.GET.get('next'))"
        findings = self._run_rule(code, "python")
        assert len(findings) > 0
    
    def test_positive_ruby_redirect_to(self):
        """Test detection of Ruby redirect_to with params."""
        code = "def go; redirect_to params[:next]; end"
        findings = self._run_rule(code, "ruby")
        assert len(findings) > 0
        assert any("open redirect" in f.message.lower() for f in findings)
    
    def test_positive_java_servlet_redirect(self):
        """Test detection of Java servlet sendRedirect."""
        code = """
class C {
    void f(javax.servlet.http.HttpServletRequest r, javax.servlet.http.HttpServletResponse resp) {
        String n = r.getParameter("next");
        resp.sendRedirect(n);
    }
}
"""
        findings = self._run_rule(code, "java")
        assert len(findings) > 0
    
    def test_positive_csharp_response_redirect(self):
        """Test detection of C# Response.Redirect with user input."""
        code = """
using Microsoft.AspNetCore.Http;
class C {
    void F(HttpContext ctx) {
        var n = ctx.Request.Query["next"];
        ctx.Response.Redirect(n);
    }
}
"""
        findings = self._run_rule(code, "csharp")
        assert len(findings) > 0
    
    def test_positive_location_header_javascript(self):
        """Test detection of raw Location header assignment."""
        code = 'response.headers["Location"] = req.query.next;'
        findings = self._run_rule(code, "javascript")
        assert len(findings) > 0
        assert any("location" in f.message.lower() and "header" in f.message.lower() for f in findings)
    
    def test_positive_location_header_python(self):
        """Test detection of Location header in Python."""
        code = 'response.headers["Location"] = request.args.get("next")'
        findings = self._run_rule(code, "python")
        assert len(findings) > 0
    
    # Negative test cases (should NOT detect - safe patterns)
    
    def test_negative_javascript_literal_redirect(self):
        """Test that literal redirects are not flagged."""
        code = "app.get('/', (req,res) => { res.redirect('/home'); });"
        findings = self._run_rule(code, "javascript")
        assert len(findings) == 0
    
    def test_negative_typescript_safe_redirect(self):
        """Test that safe literal redirects are not flagged."""
        code = "res.redirect('/safe');"
        findings = self._run_rule(code, "typescript")
        assert len(findings) == 0
    
    def test_negative_python_django_validated(self):
        """Test Django redirect with proper validation."""
        code = """
from django.utils.http import url_has_allowed_host_and_scheme as ok
from django.shortcuts import redirect

def go(req):
    nxt = req.GET.get('next')
    if ok(nxt, allowed_hosts={req.get_host()}, require_https=True):
        return redirect(nxt)
    return redirect('/')
"""
        findings = self._run_rule(code, "python")
        assert len(findings) == 0
    
    def test_negative_python_literal_redirect(self):
        """Test that literal redirects are not flagged."""
        code = "redirect('/home')"
        findings = self._run_rule(code, "python")
        assert len(findings) == 0
    
    def test_negative_ruby_allow_other_host_false(self):
        """Test Ruby redirect with allow_other_host: false."""
        code = "def go; nxt = params[:next]; redirect_to nxt, allow_other_host: false; end"
        findings = self._run_rule(code, "ruby")
        assert len(findings) == 0
    
    def test_negative_ruby_literal_redirect(self):
        """Test Ruby literal redirect."""
        code = "redirect_to '/dashboard'"
        findings = self._run_rule(code, "ruby")
        assert len(findings) == 0
    
    def test_negative_java_literal_redirect(self):
        """Test Java literal redirect."""
        code = "void f(javax.servlet.http.HttpServletResponse resp) { resp.sendRedirect(\"/home\"); }"
        findings = self._run_rule(code, "java")
        assert len(findings) == 0
    
    def test_negative_csharp_local_redirect(self):
        """Test C# LocalRedirect (safe pattern)."""
        code = """
using Microsoft.AspNetCore.Mvc;
class C : Controller {
    IActionResult Go(string next) {
        if (Url.IsLocalUrl(next))
            return LocalRedirect(next);
        return Redirect("/");
    }
}
"""
        findings = self._run_rule(code, "csharp")
        assert len(findings) == 0
    
    def test_negative_csharp_literal_redirect(self):
        """Test C# literal redirect."""
        code = "Response.Redirect(\"/home\")"
        findings = self._run_rule(code, "csharp")
        assert len(findings) == 0
    
    # Edge cases and special scenarios
    
    def test_positive_protocol_relative_url(self):
        """Test detection of protocol-relative URL (//evil.com)."""
        code = 'res.redirect("//" + req.query.host);'
        findings = self._run_rule(code, "javascript")
        assert len(findings) > 0
    
    def test_positive_concatenated_user_input(self):
        """Test detection of concatenated user input."""
        code = "redirect('/base/' + request.args.get('path'))"
        findings = self._run_rule(code, "python")
        assert len(findings) > 0
    
    def test_negative_relative_path_literal(self):
        """Test that relative path literals are safe."""
        code = "res.redirect('/auth/login');"
        findings = self._run_rule(code, "javascript")
        assert len(findings) == 0
    
    def test_suggest_only_no_autofix(self):
        """Test that findings have no autofix (suggest-only)."""
        code = "app.get('/x', (req,res) => res.redirect(req.query.next));"
        findings = self._run_rule(code, "javascript")
        assert len(findings) > 0
        for finding in findings:
            # Findings should not have edit suggestions (suggest-only rule)
            assert not hasattr(finding, 'edit') or finding.edit is None
    
    def test_comprehensive_positive_coverage(self):
        """Test that all major positive patterns are detected."""
        test_cases = {
            "javascript": [
                "res.redirect(req.query.next)",
                "response.redirect(req.params.url)",
                "ctx.redirect(req.body.target)"
            ],
            "python": [
                "redirect(request.args.get('next'))",
                "HttpResponseRedirect(request.GET['url'])",
                "RedirectResponse(request.form.get('target'))"
            ],
            "ruby": [
                "redirect_to params[:next]",
                "redirect_to request.params['url']"
            ]
        }
        
        for language, codes in test_cases.items():
            for code in codes:
                findings = self._run_rule(code, language)
                assert len(findings) > 0, f"Failed to detect: {code} in {language}"
    
    def test_comprehensive_negative_coverage(self):
        """Test that all major negative patterns are not flagged."""
        test_cases = {
            "javascript": [
                "res.redirect('/home')",
                "response.redirect('/dashboard')", 
                "ctx.redirect('/login')"
            ],
            "python": [
                "redirect('/home')",
                "HttpResponseRedirect('/dashboard')",
                "RedirectResponse('/login')"
            ],
            "ruby": [
                "redirect_to '/home'",
                "redirect_to '/dashboard'"
            ]
        }
        
        for language, codes in test_cases.items():
            for code in codes:
                findings = self._run_rule(code, language)
                assert len(findings) == 0, f"False positive on: {code} in {language}"
    
    def test_language_specific_recommendations(self):
        """Test that language-specific recommendations are provided."""
        test_cases = {
            "javascript": "res.redirect(req.query.next)",
            "python": "redirect(request.args.get('next'))", 
            "ruby": "redirect_to params[:next]",
            "java": "resp.sendRedirect(request.getParameter('next'))",
            "csharp": "Response.Redirect(Request.Query['next'])"
        }
        
        for language, code in test_cases.items():
            findings = self._run_rule(code, language)
            assert len(findings) > 0
            
            # Check that language-specific recommendations are included
            message = findings[0].message.lower()
            if language in ["javascript", "typescript"]:
                assert "islocalurl" in message or "relative path" in message
            elif language == "python":
                assert "url_has_allowed_host_and_scheme" in message or "allow-list" in message
            elif language == "ruby":
                assert "allow_other_host: false" in message or "allow-list" in message
            elif language == "java":
                assert "relative paths" in message or "allow-list" in message
            elif language == "csharp":
                assert "localredirect" in message or "islocalurl" in message
    
    def test_severity_and_span_reporting(self):
        """Test that findings have correct severity and span info."""
        code = "res.redirect(req.query.next);"
        findings = self._run_rule(code, "javascript")
        
        assert len(findings) > 0
        finding = findings[0]
        
        # Check severity and priority
        assert finding.severity == "warning"
        assert finding.rule == "sec.open_redirect"
        
        # Check span information
        assert hasattr(finding, 'start_byte')
        assert hasattr(finding, 'end_byte')
        assert finding.start_byte >= 0
        assert finding.end_byte > finding.start_byte
    
    def test_variable_vs_literal_distinction(self):
        """Test that rule distinguishes between variables and literals."""
        # Variable input (should be flagged)
        var_code = "res.redirect(userInput);"
        var_findings = self._run_rule(var_code, "javascript")
        assert len(var_findings) > 0
        
        # Literal string (should not be flagged) 
        literal_code = "res.redirect('/safe-path');"
        literal_findings = self._run_rule(literal_code, "javascript")
        assert len(literal_findings) == 0

