"""Rule: sec.open_redirect

Detects redirects that use user-provided URLs without validation, leading to open redirect vulnerabilities.
Flags redirect functions/methods that accept user-controlled input without proper validation or normalization.
Recommends validating/normalizing to same-origin paths or using framework-specific secure redirect helpers.
"""

from typing import Iterator, List, Optional, Set, Dict, Any

from engine.types import Rule, RuleContext, RuleMeta, Finding, Requires


class SecOpenRedirectRule:
    """Rule implementation for detecting open redirect vulnerabilities."""
    
    meta = RuleMeta(
        id="sec.open_redirect",
        category="sec",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects redirects that use user-provided URLs without validation",
        langs=["javascript", "typescript", "python", "ruby", "java", "csharp"],
    )
    requires = Requires(syntax=True, scopes=True, raw_text=True)
    
    def __init__(self):
        # Redirect sink functions/methods by language
        self.REDIRECT_SINKS = {
            "javascript": {
                "res.redirect", "response.redirect", "reply.redirect", "ctx.redirect",
                "koa.ctx.redirect", "fastify.reply.redirect", "express.response.redirect"
            },
            "typescript": {
                "res.redirect", "response.redirect", "reply.redirect", "ctx.redirect",
                "koa.ctx.redirect", "fastify.reply.redirect", "express.response.redirect"
            },
            "python": {
                "flask.redirect", "django.shortcuts.redirect", "django.http.HttpResponseRedirect",
                "starlette.responses.RedirectResponse", "fastapi.responses.RedirectResponse",
                "bottle.redirect", "pyramid.httpexceptions.HTTPFound"
            },
            "ruby": {
                "ActionController.redirect_to", "redirect_to", "Rails.application.routes.url_helpers.redirect_to"
            },
            "java": {
                "javax.servlet.http.HttpServletResponse.sendRedirect",
                "org.springframework.web.servlet.ModelAndView.setViewName",
                "org.springframework.web.servlet.view.RedirectView"
            },
            "csharp": {
                "Microsoft.AspNetCore.Http.HttpResponse.Redirect",
                "System.Web.HttpResponse.Redirect",
                "Microsoft.AspNetCore.Mvc.RedirectResult",
                "Microsoft.AspNetCore.Mvc.Controller.Redirect"
            }
        }
        
        # Known validation functions that make redirects safe
        self.VALIDATION_FUNCTIONS = {
            "javascript": {
                "isSafeRedirect", "isLocalUrl", "isValidRedirect", "validateUrl",
                "isSameOrigin", "isRelativePath"
            },
            "typescript": {
                "isSafeRedirect", "isLocalUrl", "isValidRedirect", "validateUrl",
                "isSameOrigin", "isRelativePath"
            },
            "python": {
                "django.utils.http.url_has_allowed_host_and_scheme",
                "django.utils.http.is_safe_url", "is_safe_url", "is_local_url",
                "validate_redirect_url", "check_redirect_url"
            },
            "ruby": {
                "safe_redirect_path", "local_only", "validate_redirect_url",
                "allow_other_host"
            },
            "java": {
                "isSafeRedirect", "isLocalUrl", "validateRedirectUrl",
                "org.springframework.web.util.UriComponentsBuilder"
            },
            "csharp": {
                "Microsoft.AspNetCore.Mvc.ControllerBase.LocalRedirect",
                "Microsoft.AspNetCore.Mvc.IUrlHelper.IsLocalUrl",
                "IsLocalUrl", "ValidateRedirectUrl"
            }
        }
        
        # User input source patterns by language
        self.USER_INPUT_PATTERNS = {
            "javascript": [
                "req.query", "req.params", "req.body", "request.query", "request.params",
                "ctx.query", "ctx.request.query", "ctx.request.body"
            ],
            "typescript": [
                "req.query", "req.params", "req.body", "request.query", "request.params",
                "ctx.query", "ctx.request.query", "ctx.request.body"
            ],
            "python": [
                "request.args", "request.form", "request.json", "request.GET",
                "request.POST", "request.REQUEST", "flask.request", "django.http.HttpRequest"
            ],
            "ruby": [
                "params", "request.params", "request.query_string", "request.POST",
                "params[:"
            ],
            "java": [
                "request.getParameter", "request.getParameterValues", "request.getQueryString",
                "httpServletRequest.getParameter"
            ],
            "csharp": [
                "Request.Query", "Request.Form", "HttpContext.Request",
                "Request.QueryString", "HttpRequest.Query"
            ]
        }
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit AST nodes and detect open redirect vulnerabilities."""
        
        code_text = ctx.text
        language = ctx.language
        
        # Skip framework library source files that define redirect functionality
        # These provide redirect functions, not vulnerable redirect usage
        file_path = ctx.file_path.lower().replace('\\', '/')
        if self._is_framework_source(file_path, code_text):
            return
        
        # Skip files with only hardcoded redirect paths (not user input)
        # e.g., res.redirect(`${WEBAPP_URL}/settings/profile`) - constant path
        if not self._has_dynamic_redirect_target(code_text, language):
            return
        
        # For cases not caught by whole-file analysis, try line-by-line
        lines = code_text.split('\n')
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith('//') or line.startswith('#') or line.startswith('*') or line.startswith('/*'):
                continue
                
            # Skip JSDoc/docstring example patterns
            if line.startswith('* ') or line.startswith('*\t'):
                continue
                
            # Check for redirect patterns in this line with user input on same line
            if self._contains_redirect_call(line, language) and self._contains_user_input(line, language):
                if not self._is_validated_code(line, language):
                    yield self._create_finding_from_line(line, ctx, line_num, "redirect_call")
            
            # Check for Location header patterns with user input on same line 
            elif self._contains_location_header(line) and self._contains_user_input(line, language):
                if not self._is_validated_code(line, language):
                    yield self._create_finding_from_line(line, ctx, line_num, "location_header")
    
    def _create_finding_from_line(self, line: str, ctx: RuleContext, line_num: int, finding_type: str) -> Finding:
        """Create a Finding from line analysis."""
        language = ctx.language
        
        if finding_type == "redirect_call":
            message = "Possible open redirect: user-controlled URL flows into redirect without validation"
        else:  # location_header
            message = "Possible open redirect via raw 'Location' header set from user input without validation"
        
        # Add language-specific suggestions
        suggestions = {
            "javascript": "Validate and normalize to a relative path (e.g., `isLocalUrl(next) ? next : '/'`).",
            "typescript": "Validate and normalize to a relative path (e.g., `isLocalUrl(next) ? next : '/'`).",
            "python": "Use allow-list or `url_has_allowed_host_and_scheme(next, allowed_hosts, require_https=True)`.",
            "ruby": "Use a path allow-list or Rails 7+: `redirect_to next, allow_other_host: false`.",
            "java": "Validate host/scheme and prefer relative paths; consider allow-list before `sendRedirect`.",
            "csharp": "Use `LocalRedirect(next)` or validate with `Url.IsLocalUrl(next)`."
        }
        
        suggestion = suggestions.get(language, "Validate redirect URLs to prevent open redirect attacks.")
        full_message = f"{message}. {suggestion}"
        
        # Estimate byte position for the line
        lines_before = ctx.text.split('\n')[:line_num]
        start_byte = sum(len(l) + 1 for l in lines_before)  # +1 for newline
        end_byte = start_byte + len(line)
        
        return Finding(
            rule=self.meta.id,
            message=full_message,
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            severity="warning"
        )
    
    def _contains_redirect_call(self, code: str, language: str) -> bool:
        """Check if code contains redirect function calls."""
        redirect_patterns = {
            "javascript": ["redirect(", ".redirect(", "res.redirect", "response.redirect"],
            "typescript": ["redirect(", ".redirect(", "res.redirect", "response.redirect"],
            "python": ["redirect(", "HttpResponseRedirect(", "RedirectResponse("],
            "ruby": ["redirect_to", "redirect("],
            "java": ["sendRedirect(", "RedirectView"],
            "csharp": ["Redirect(", "Response.Redirect", "LocalRedirect"]
        }
        
        patterns = redirect_patterns.get(language, [])
        return any(pattern in code for pattern in patterns)
    
    def _has_dynamic_redirect_target(self, code: str, language: str) -> bool:
        """Check if code has a redirect with a dynamic (potentially user-controlled) target.
        
        Returns False for redirects with only hardcoded paths, which are safe.
        Returns True if there's a redirect that uses a variable or user input.
        """
        import re
        
        lines = code.split('\n')
        
        # Patterns for redirect calls
        redirect_patterns = {
            "javascript": [r'\.redirect\s*\(', r'redirect\s*\('],
            "typescript": [r'\.redirect\s*\(', r'redirect\s*\(', r'NextResponse\.redirect\s*\('],
            "python": [r'redirect\s*\(', r'HttpResponseRedirect\s*\(', r'RedirectResponse\s*\('],
            "ruby": [r'redirect_to\s+', r'redirect_to\s*\('],
            "java": [r'sendRedirect\s*\('],
            "csharp": [r'\.Redirect\s*\(', r'LocalRedirect\s*\(']
        }
        
        # Patterns that indicate a safe/hardcoded redirect target
        safe_patterns = [
            r'redirect\s*\(\s*["\']/',  # redirect("/path")
            r'redirect\s*\(\s*`\$\{[A-Z_]+\}/',  # redirect(`${WEBAPP_URL}/path`)
            r'redirect\s*\(\s*[A-Z_]+\s*\+\s*["\']/',  # redirect(WEBAPP_URL + "/path")
            r'redirect\s*\(\s*["\'][^"\']*["\']',  # redirect("full string literal")
            r'LocalRedirect\s*\(',  # C# LocalRedirect is safe by design
        ]
        
        patterns = redirect_patterns.get(language, [r'redirect\s*\('])
        
        for line in lines:
            stripped = line.strip()
            
            # Skip comments and empty lines
            if not stripped or stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*'):
                continue
            
            # Check if this line has a redirect call
            has_redirect = any(re.search(p, line, re.IGNORECASE) for p in patterns)
            if not has_redirect:
                continue
            
            # Check if the redirect uses a variable (not just a literal)
            # If it has a variable that could be user input, it's potentially dangerous
            
            # Skip if it's clearly a hardcoded safe redirect
            if any(re.search(sp, line) for sp in safe_patterns):
                continue
            
            # Check if redirect has a variable argument (not a string literal)
            # This catches: redirect(userInput), redirect(url), NextResponse.redirect(redirectUrl)
            var_in_redirect = re.search(r'redirect\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)', line, re.IGNORECASE)
            if var_in_redirect:
                var_name = var_in_redirect.group(1).lower()
                # Skip if the variable name suggests it's safe/validated or internal
                safe_var_names = [
                    'safe', 'valid', 'local', 'internal', 'allowed', 'sanitized', 'checked',
                    # Internal navigation paths (not user input)
                    'onboarding', 'getting', 'dashboard', 'home', 'default', 'fallback',
                    'destination', 'new',  # newDestination, newUrl typically internal
                ]
                if any(sv in var_name for sv in safe_var_names):
                    continue  # Safe variable, skip this line
                
                # Only flag if variable name strongly suggests user input source
                user_input_var_patterns = [
                    'userurl', 'userinput', 'user_url', 'user_input',
                    'returnurl', 'return_url', 'returnto', 'return_to',
                    'nexturl', 'next_url', 'nextpath', 'next_path', 'next',
                    'callbackurl', 'callback_url', 'callback',
                    'queryurl', 'query_url', 'paramurl', 'param_url',
                    'externalurl', 'external_url', 'targeturl', 'target_url',
                ]
                if any(uip in var_name for uip in user_input_var_patterns):
                    return True
                # else: generic variable name - skip to reduce false positives
            
            # Check for new URL() pattern with variable
            new_url_match = re.search(r'new\s+URL\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)', line)
            if new_url_match:
                return True
        
        return False

    def _contains_location_header(self, code: str) -> bool:
        """Check if code contains Location header assignments."""
        location_patterns = [
            '"Location"', "'Location'", 'headers["Location"]', "headers['Location']",
            'setHeader("Location"', "setHeader('Location'", 'Location:'
        ]
        return any(pattern in code for pattern in location_patterns)
    
    def _contains_user_input(self, code: str, language: str) -> bool:
        """Check if code contains user input patterns."""
        import re
        
        user_input_patterns = {
            "javascript": ["req.query", "req.params", "req.body", "request.query", "ctx.query"],
            "typescript": ["req.query", "req.params", "req.body", "request.query", "ctx.query"],
            "python": ["request.args", "request.form", "request.GET", "request.POST"],
            "ruby": ["params[", "request.params"],
            "java": ["getParameter(", "getQueryString"],
            "csharp": ["Request.Query", "Request.Form", "HttpContext.Request"]
        }
        
        patterns = user_input_patterns.get(language, [])
        if any(pattern in code for pattern in patterns):
            return True
        
        # Check if redirect is called with a variable (not a literal string)
        # This catches patterns like redirect(userInput) or res.redirect(next)
        redirect_with_var_patterns = [
            r"redirect\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)",  # redirect(varName)
            r"\.redirect\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)",  # .redirect(varName)
            r"redirect_to\s+([a-zA-Z_][a-zA-Z0-9_]*)",  # redirect_to varName
            r"sendRedirect\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)",  # sendRedirect(varName)
            r"Redirect\s*\(\s*([a-zA-Z_][a-zA-Z0-9_]*)\s*\)",  # Redirect(varName)
        ]
        
        for pattern in redirect_with_var_patterns:
            match = re.search(pattern, code)
            if match:
                # Variable is being passed to redirect - check if it's a safe/internal variable
                var_name = match.group(1).lower()
                
                # Skip safe/internal variable names (likely computed from constants)
                safe_var_names = [
                    'safe', 'valid', 'local', 'internal', 'allowed', 'sanitized', 'checked',
                    # Internal navigation paths (not user input)
                    'onboarding', 'getting', 'dashboard', 'home', 'default', 'fallback',
                    'destination', 'new',  # newDestination, newUrl typically internal
                ]
                if any(sv in var_name for sv in safe_var_names):
                    continue  # Skip this, check other patterns
                
                # Only flag if variable name strongly suggests user input source
                user_input_var_patterns = [
                    'userurl', 'userinput', 'user_url', 'user_input',
                    'returnurl', 'return_url', 'returnto', 'return_to',
                    'nexturl', 'next_url', 'nextpath', 'next_path', 'next',
                    'callbackurl', 'callback_url', 'callback',
                    'queryurl', 'query_url', 'paramurl', 'param_url',
                    'externalurl', 'external_url', 'targeturl', 'target_url',
                ]
                if any(uip in var_name for uip in user_input_var_patterns):
                    return True
                # else: generic variable name like 'redirectUrl' - could be user input OR internal
                # Without scope analysis we can't tell, so skip to reduce false positives
        
        # Check for concatenation with potential user input variable
        if "+" in code:
            user_input_hints = ["userInput", "user_input", "returnUrl", "return_url", "nextUrl", "next_url"]
            if any(hint.lower() in code.lower() for hint in user_input_hints):
                return True
            
        return False
    
    def _is_validated_code(self, code: str, language: str) -> bool:
        """Check if code contains validation patterns."""
        # Check for literal paths (safe) - but not if combined with user input
        if self._is_literal_redirect(code) and not ("+" in code and ("req." in code or "request." in code)):
            return True
        
        # Check for validation functions/imports
        validation_patterns = {
            "javascript": ["isLocalUrl", "isSafeRedirect", "validateUrl", "safeRedirect", "safeUrl"],
            "typescript": ["isLocalUrl", "isSafeRedirect", "validateUrl", "safeRedirect", "safeUrl"],
            "python": ["url_has_allowed_host_and_scheme", "is_safe_url", "is_safe_redirect"],
            "ruby": ["allow_other_host: false"],
            "java": ["isLocalUrl", "UriComponentsBuilder"],
            "csharp": ["LocalRedirect", "IsLocalUrl"]
        }
        
        patterns = validation_patterns.get(language, [])
        
        # For whole-file analysis: if code imports/defines a validation function
        # and uses conditional before redirect, consider it validated
        if any(pattern in code for pattern in patterns):
            # Check if there's a conditional (if statement) protecting the redirect
            if "if " in code and self._contains_redirect_call(code, language):
                return True
            # Also accept if validation appears anywhere in code (might be used elsewhere)
            if self._contains_redirect_call(code, language):
                return True
            
        return False
    
    def _is_framework_source(self, file_path: str, code: str) -> bool:
        """Check if this is framework library source code that defines redirect functionality.
        
        Framework code that *implements* redirect functions is not vulnerable to open redirect;
        the vulnerability is in *application* code that calls redirect with user input.
        """
        # Check for framework library paths (code that implements redirect, not uses it)
        framework_lib_patterns = [
            # Express.js and similar frameworks
            '/node_modules/',  # Any npm package source
            'express/lib/',
            'koa/lib/',
            'fastify/lib/',
            # Python frameworks
            '/site-packages/',
            'django/http/',
            'flask/',
            'starlette/',
            # Ruby frameworks
            '/gems/',
            'actionpack/',
            # Java/Spring
            'springframework/',
            # .NET
            'microsoft.aspnetcore.',
        ]
        
        if any(pattern in file_path for pattern in framework_lib_patterns):
            return True
        
        # Also detect if this file DEFINES a redirect function (not uses it)
        # Look for function/method definitions that create redirect functionality
        defining_patterns = [
            'res.redirect = function',  # Express: defines redirect on response
            'module.exports = redirect',  # Node module that exports redirect
            'def redirect(', # Python function definition
            'public.*redirect(', # Java/C# method definition
            '@register.', # Django template tags
        ]
        
        code_lower = code.lower()
        if any(pattern.lower() in code_lower for pattern in defining_patterns):
            return True
            
        return False
    
    def _is_literal_redirect(self, code: str) -> bool:
        """Check if redirect uses literal paths."""
        # Look for patterns like redirect('/path') or redirect("path")
        import re
        literal_patterns = [
            r"redirect\s*\(\s*['\"][^'\"]*['\"]",  # redirect('path') or redirect("path")
            r"Redirect\s*\(\s*['\"][^'\"]*['\"]",  # Redirect('path')
            r"redirect_to\s+['\"][^'\"]*['\"]",  # redirect_to '/path' (Ruby)
            r"redirect_to\s*\(\s*['\"][^'\"]*['\"]",  # redirect_to('/path') (Ruby)
            r"sendRedirect\s*\(\s*['\"][^'\"]*['\"]",  # sendRedirect("/path") (Java)
            r"HttpResponseRedirect\s*\(\s*['\"][^'\"]*['\"]",  # HttpResponseRedirect('/path') (Python/Django)
            r"RedirectResponse\s*\(\s*['\"][^'\"]*['\"]",  # RedirectResponse('/path') (Python/FastAPI)
            r"Response\.Redirect\s*\(\s*['\"][^'\"]*['\"]",  # Response.Redirect("/path") (C#)
            r"LocalRedirect\s*\(\s*['\"][^'\"]*['\"]",  # LocalRedirect("/path") (C#)
        ]
        
        for pattern in literal_patterns:
            if re.search(pattern, code, re.IGNORECASE):
                # Make sure it doesn't contain user input or concatenation
                if "+" not in code and "req." not in code and "request." not in code and "params" not in code:
                    return True
        
        return False
    
    def _create_finding_from_text(self, code: str, ctx: RuleContext, finding_type: str) -> Finding:
        """Create a Finding from text analysis, pointing to the actual redirect line."""
        language = ctx.language
        
        if finding_type == "redirect_call":
            message = "Possible open redirect: user-controlled URL flows into redirect without validation"
        else:  # location_header
            message = "Possible open redirect via raw 'Location' header set from user input without validation"
        
        # Add language-specific suggestions
        suggestions = {
            "javascript": "Validate and normalize to a relative path (e.g., `isLocalUrl(next) ? next : '/'`).",
            "typescript": "Validate and normalize to a relative path (e.g., `isLocalUrl(next) ? next : '/'`).",
            "python": "Use allow-list or `url_has_allowed_host_and_scheme(next, allowed_hosts, require_https=True)`.",
            "ruby": "Use a path allow-list or Rails 7+: `redirect_to next, allow_other_host: false`.",
            "java": "Validate host/scheme and prefer relative paths; consider allow-list before `sendRedirect`.",
            "csharp": "Use `LocalRedirect(next)` or validate with `Url.IsLocalUrl(next)`."
        }
        
        suggestion = suggestions.get(language, "Validate redirect URLs to prevent open redirect attacks.")
        full_message = f"{message}. {suggestion}"
        
        # Find the actual redirect line for accurate positioning
        lines = code.split('\n')
        redirect_patterns = {
            "javascript": ["res.redirect(", "response.redirect(", ".redirect("],
            "typescript": ["res.redirect(", "response.redirect(", ".redirect("],
            "python": [" redirect(", "=redirect(", "(redirect(", "HttpResponseRedirect(", "RedirectResponse("],
            "ruby": ["redirect_to ", "redirect_to("],
            "java": ["sendRedirect(", "RedirectView("],
            "csharp": [".Redirect(", "Response.Redirect(", "LocalRedirect("]
        }
        location_patterns = ['"Location"', "'Location'", 'headers["Location"]', "headers['Location']"]
        
        patterns = redirect_patterns.get(language, [" redirect("]) if finding_type == "redirect_call" else location_patterns
        
        target_line_num = 0
        target_line = lines[0] if lines else ""
        
        for line_num, line in enumerate(lines):
            # Skip function definitions that contain 'redirect' in the name
            stripped = line.strip()
            if stripped.startswith('def ') or stripped.startswith('function ') or stripped.startswith('async function'):
                continue
            # Skip comment lines - JSDoc, docstrings, single-line comments
            if stripped.startswith('//') or stripped.startswith('#') or stripped.startswith('*') or stripped.startswith('/*'):
                continue
            if any(pattern in line for pattern in patterns):
                target_line_num = line_num
                target_line = line
                break
        
        # Calculate byte positions for the target line
        lines_before = lines[:target_line_num]
        start_byte = sum(len(l) + 1 for l in lines_before)  # +1 for newline
        end_byte = start_byte + len(target_line)
        
        return Finding(
            rule=self.meta.id,
            message=full_message,
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            severity="warning"
        )
    
    def _get_call_nodes(self, ctx: RuleContext) -> List:
        """Get all function/method call nodes from the AST."""
        call_nodes = []
        
        def visit_node(node):
            if hasattr(node, 'kind') or hasattr(node, 'type'):
                node_type = getattr(node, 'kind', None) or getattr(node, 'type', None)
                if node_type in ['call', 'call_expression', 'method_call', 'function_call']:
                    call_nodes.append(node)
            
            # Recursively visit children
            children = getattr(node, 'children', [])
            for child in children:
                visit_node(child)
        
        if hasattr(ctx, 'tree') and ctx.tree:
            visit_node(ctx.tree)
        
        return call_nodes
    
    def _get_assignment_nodes(self, ctx: RuleContext) -> List:
        """Get all assignment nodes from the AST."""
        assignment_nodes = []
        
        def visit_node(node):
            if hasattr(node, 'kind') or hasattr(node, 'type'):
                node_type = getattr(node, 'kind', None) or getattr(node, 'type', None)
                if node_type in ['assignment', 'assignment_expression', 'variable_assignment',
                                'assignment_statement', 'expression_statement']:
                    assignment_nodes.append(node)
            
            # Recursively visit children
            children = getattr(node, 'children', [])
            for child in children:
                visit_node(child)
        
        if hasattr(ctx, 'tree') and ctx.tree:
            visit_node(ctx.tree)
        
        return assignment_nodes
    
    def _is_redirect_sink(self, call_node, ctx: RuleContext) -> bool:
        """Check if the call is to a known redirect function/method."""
        language = ctx.language
        if language not in self.REDIRECT_SINKS:
            return False
        
        # Get the function/method name
        call_text = self._get_node_text(call_node, ctx)
        
        # Check for exact matches with known redirect sinks
        sinks = self.REDIRECT_SINKS[language]
        for sink in sinks:
            if sink in call_text:
                return True
        
        # Check for common redirect method names
        if language in ["javascript", "typescript"]:
            if ".redirect(" in call_text or "redirect(" in call_text:
                return True
        
        return False
    
    def _get_redirect_target(self, call_node, ctx: RuleContext) -> Optional[Any]:
        """Extract the redirect target (first argument) from a redirect call."""
        # Try to get the first argument from the call
        args = self._get_call_arguments(call_node)
        if args:
            return args[0]
        return None
    
    def _get_call_arguments(self, call_node) -> List:
        """Extract arguments from a function call node."""
        args = []
        
        # Look for argument list in children
        children = getattr(call_node, 'children', [])
        for child in children:
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ["arguments", "argument_list", "parameter_list"]:
                # Get individual argument nodes
                for arg_child in getattr(child, 'children', []):
                    arg_kind = getattr(arg_child, 'kind', '') or getattr(arg_child, 'type', '')
                    if arg_kind not in [',', '(', ')', 'comma']:
                        args.append(arg_child)
                break
        
        return args
    
    def _is_location_header_assignment(self, assign_node, ctx: RuleContext) -> bool:
        """Check if the assignment is setting a Location header."""
        assign_text = self._get_node_text(assign_node, ctx)
        
        # Look for Location header patterns
        location_patterns = [
            '"Location"', "'Location'", 'Location:', 'location:',
            'setHeader("Location"', "setHeader('Location'",
            'headers["Location"]', "headers['Location']",
            'response.headers.location', 'resp.headers.location'
        ]
        
        return any(pattern in assign_text for pattern in location_patterns)
    
    def _get_assignment_value(self, assign_node, ctx: RuleContext):
        """Get the value being assigned in an assignment expression."""
        # Look for assignment operator and get the right-hand side
        children = getattr(assign_node, 'children', [])
        found_operator = False
        
        for child in children:
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in ['=', 'assignment_operator', ':']:
                found_operator = True
                continue
            
            if found_operator and child_kind not in ['=', 'assignment_operator', ':', ';']:
                return child
        
        return None
    
    def _is_user_controlled(self, node, ctx: RuleContext) -> bool:
        """Check if a node represents user-controlled input."""
        language = ctx.language
        if language not in self.USER_INPUT_PATTERNS:
            return False
        
        node_text = self._get_node_text(node, ctx)
        
        # Check for known user input patterns
        input_patterns = self.USER_INPUT_PATTERNS[language]
        for pattern in input_patterns:
            if pattern in node_text:
                return True
        
        # Additional heuristics for user input
        user_input_keywords = [
            "query", "param", "form", "body", "cookie", "header",
            "request", "req.", "ctx.", "input", "user"
        ]
        
        return any(keyword in node_text.lower() for keyword in user_input_keywords)
    
    def _is_validated_redirect(self, call_node, target_node, ctx: RuleContext) -> bool:
        """Check if the redirect target is properly validated."""
        language = ctx.language
        
        # Check if target is a literal path (safer)
        target_text = self._get_node_text(target_node, ctx)
        if self._is_safe_literal_path(target_text):
            return True
        
        # Check if wrapped by validation function
        if language in self.VALIDATION_FUNCTIONS:
            validators = self.VALIDATION_FUNCTIONS[language]
            call_text = self._get_node_text(call_node, ctx)
            
            for validator in validators:
                if validator in call_text:
                    return True
        
        # Check for framework-specific safe patterns
        if language == "ruby" and "allow_other_host: false" in self._get_node_text(call_node, ctx):
            return True
        
        if language == "csharp" and "LocalRedirect" in self._get_node_text(call_node, ctx):
            return True
        
        return False
    
    def _is_safe_literal_path(self, text: str) -> bool:
        """Check if the text represents a safe literal path."""
        # Remove quotes and whitespace
        clean_text = text.strip().strip('"\'')
        
        # Safe if it's a relative path starting with /
        if clean_text.startswith('/') and not clean_text.startswith('//'):
            return True
        
        # Safe if it's a simple relative path without protocols
        if not any(proto in clean_text.lower() for proto in ['http://', 'https://', 'javascript:', 'data:']):
            if not clean_text.startswith('//'):
                return True
        
        return False
    
    def _create_finding(self, node, ctx: RuleContext, finding_type: str) -> Finding:
        """Create a Finding for an open redirect vulnerability."""
        start_byte, end_byte = self._get_node_span(node)
        language = ctx.language
        
        if finding_type == "redirect_call":
            message = "Possible open redirect: user-controlled URL flows into redirect without validation"
        else:  # location_header
            message = "Possible open redirect via raw 'Location' header set from user input without validation"
        
        # Add language-specific suggestions
        suggestions = {
            "javascript": "Validate and normalize to a relative path (e.g., `isLocalUrl(next) ? next : '/'`).",
            "typescript": "Validate and normalize to a relative path (e.g., `isLocalUrl(next) ? next : '/'`).",
            "python": "Use allow-list or `url_has_allowed_host_and_scheme(next, allowed_hosts, require_https=True)`.",
            "ruby": "Use a path allow-list or Rails 7+: `redirect_to next, allow_other_host: false`.",
            "java": "Validate host/scheme and prefer relative paths; consider allow-list before `sendRedirect`.",
            "csharp": "Use `LocalRedirect(next)` or validate with `Url.IsLocalUrl(next)`."
        }
        
        suggestion = suggestions.get(language, "Validate redirect URLs to prevent open redirect attacks.")
        full_message = f"{message}. {suggestion}"
        
        return Finding(
            rule=self.meta.id,
            message=full_message,
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            severity="warning"
        )
    
    def _get_node_text(self, node, ctx: RuleContext) -> str:
        """Extract text from a node."""
        if not node:
            return ""
            
        # Try different ways to get node text
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='ignore')
            return str(text)
        
        # Fallback: use span to extract from source
        start_byte, end_byte = self._get_node_span(node)
        if hasattr(ctx, 'text') and ctx.text:
            try:
                return ctx.text[start_byte:end_byte]
            except (IndexError, TypeError):
                pass
        
        return ""
    
    def _get_node_span(self, node) -> tuple:
        """Get the start and end byte positions of a node."""
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', 0)
        
        # If no span info, try to estimate
        if start_byte == end_byte == 0:
            # Use a default span
            end_byte = start_byte + 10
            
        return start_byte, end_byte


# Export rule for auto-discovery
RULES = [SecOpenRedirectRule()]


