"""
perf.repeated_regex_compile rule: Detect regex compilation inside loops.

Warns when regular expressions are constructed/compiled inside loops, which
repeatedly incurs compile cost. Suggests hoisting/precompiling patterns outside
loops or caching when patterns are dynamic.

Examples of problematic patterns:
- Python: for x in items: re.compile(pattern).search(x)
- JavaScript: for (item of items) { new RegExp(pattern).test(item) }
- Java: for (String s : items) { Pattern.compile(regex).matcher(s) }
- C#: foreach (var s in items) { new Regex(pattern).IsMatch(s) }

Suggests alternatives:
- Hoist compilation outside loops for static patterns
- Cache compiled regexes for dynamic patterns
- Use pre-compiled static/module-level patterns
"""

from typing import Iterator
from engine.types import Rule, RuleMeta, Requires, Finding, RuleContext


class PerfRepeatedRegexCompileRule:
    """Detects regex compilation inside loops and suggests optimizations."""
    
    meta = RuleMeta(
        id="perf.repeated_regex_compile",
        category="perf",
        tier=0,
        priority="P2",
        autofix_safety="suggest-only",
        description="Detect regex compilation inside loops",
        langs=["python", "javascript", "java", "csharp", "ruby", "go"],
    )
    
    requires = Requires(syntax=True)
    
    # Regex compilation signatures by language
    COMPILE_SIGS = {
        "python": {"re.compile"},
        "javascript": {"RegExp"},  # new RegExp(...) or RegExp(...)
        "java": {"java.util.regex.Pattern.compile", "Pattern.compile"},
        "csharp": {"System.Text.RegularExpressions.Regex", "Regex"},
        "ruby": {"Regexp.new"},
        "go": {"regexp.MustCompile", "regexp.Compile"},
    }
    
    def visit(self, ctx) -> Iterator[Finding]:
        """Visit file and detect regex compilation inside loops."""
        if not hasattr(ctx, 'syntax') or not ctx.syntax:
            return
        
        lang = ctx.language
        for node in ctx.walk_nodes():
            if not self._in_loop(node):
                continue
                
            # 1) Direct compile/constructor calls
            if self._is_function_call(node):
                if self._is_compile_call(node, lang, ctx):
                    # Get the callee for precise positioning
                    callee_node = self._get_callee_node(node)
                    start_pos, end_pos = ctx.node_span(callee_node or node)
                    
                    yield Finding(
                        rule=self.meta.id,
                        message="Regex compiled inside loop; hoist/precompile outside the loop or cache by pattern.",
                        file=ctx.file_path,
                        start_byte=start_pos,
                        end_byte=end_pos,
                        severity="info",
                    )
                    continue
            
            # 2) Regex literals created each iteration (JS/Ruby)
            if self._regex_literal_in_loop(node, lang, ctx):
                start_pos, end_pos = ctx.node_span(node)
                yield Finding(
                    rule=self.meta.id,
                    message="Regex literal created per-iteration; consider hoisting it outside the loop.",
                    file=ctx.file_path,
                    start_byte=start_pos,
                    end_byte=end_pos,
                    severity="info",
                )
    
    def _in_loop(self, node) -> bool:
        """Check if node is inside a loop by walking up parent chain."""
        current = node
        while current:
            parent = getattr(current, 'parent', None)
            if not parent:
                break
            
            kind = getattr(parent, 'kind', '')
            if kind in {
                'for_statement', 'while_statement', 'for_in_statement', 
                'for_of_statement', 'foreach_statement', 'enhanced_for_statement',
                'range_for_statement', 'for_loop', 'while_loop'
            }:
                return True
            current = parent
        return False
    
    def _is_function_call(self, node) -> bool:
        """Check if node is a function call or constructor."""
        kind = getattr(node, 'kind', '')
        return kind in {
            'call_expression', 'method_call', 'function_call', 
            'call', 'invocation_expression', 'new_expression',
            'constructor_call', 'object_creation_expression'
        }
    
    def _is_compile_call(self, node, lang, ctx) -> bool:
        """Check if node is a regex compilation call."""
        if lang not in self.COMPILE_SIGS:
            return False
        
        callee_text = self._get_callee_text(node, ctx)
        if not callee_text:
            return False
        
        signatures = self.COMPILE_SIGS[lang]
        return any(self._matches_compile_signature(callee_text, sig, lang) for sig in signatures)
    
    def _get_callee_node(self, node):
        """Get the callee node from a function call."""
        # Try different ways to get the callee
        callee = getattr(node, 'callee', None)
        if callee:
            return callee
        
        function = getattr(node, 'function', None)
        if function:
            return function
        
        name = getattr(node, 'name', None)
        if name:
            return name
        
        return None
    
    def _get_callee_text(self, node, ctx) -> str:
        """Extract the function name/callee from a call node."""
        callee_node = self._get_callee_node(node)
        if callee_node:
            return self._node_text(callee_node, ctx)
        
        return ""
    
    def _node_text(self, node, ctx) -> str:
        """Get text representation of a node."""
        try:
            # Try to get tokens and reconstruct text
            tokens = list(ctx.syntax.iter_tokens(node))
            if tokens:
                return ''.join(ctx.syntax.token_text(t) for t in tokens)
        except:
            pass
        
        # Fallback to node text if available
        text = getattr(node, 'text', '')
        if isinstance(text, bytes):
            return text.decode('utf-8', errors='ignore')
        return str(text)
    
    def _matches_compile_signature(self, callee_text: str, signature: str, lang: str) -> bool:
        """Check if callee text matches a regex compilation signature."""
        # Remove whitespace for comparison
        callee_clean = callee_text.replace(' ', '').replace('\n', '')
        
        # Handle different language patterns
        if lang == "javascript":
            # For JavaScript, look for RegExp constructor
            return (callee_clean == "RegExp" or 
                    callee_clean.endswith(".RegExp") or
                    "RegExp" in callee_clean)
        
        elif lang == "csharp":
            # For C#, look for Regex constructor (new Regex or qualified name)
            return (callee_clean == "Regex" or
                    callee_clean.endswith(".Regex") or
                    "Regex" in callee_clean and ("new" in callee_clean or "System.Text" in callee_clean))
        
        else:
            # For other languages, exact or suffix match
            if callee_clean == signature:
                return True
            
            # Check if it ends with the signature (for qualified names)
            if callee_clean.endswith('.' + signature) or callee_clean.endswith('::' + signature):
                return True
            
            # For partial matches
            if '.' in signature:
                short_name = signature.split('.')[-1]
                if callee_clean == short_name or callee_clean.endswith('.' + short_name):
                    return True
        
        return False
    
    def _regex_literal_in_loop(self, node, lang, ctx) -> bool:
        """Check if node is a regex literal in languages that support them."""
        if lang not in {"javascript", "ruby"}:
            return False
        
        kind = getattr(node, 'kind', '')
        
        # Check for explicit regex literal node types
        if kind in {"regex_literal", "regular_expression_literal", "regex"}:
            return True
        
        # For JavaScript and Ruby, check text patterns
        node_text = self._node_text(node, ctx)
        if not node_text:
            return False
        
        # Heuristic: look for /pattern/flags syntax
        if lang in {"javascript", "ruby"}:
            # Simple heuristic: starts and ends with / and looks like a regex
            clean_text = node_text.strip()
            if (clean_text.startswith('/') and 
                clean_text.count('/') >= 2 and
                len(clean_text) > 2):
                return True
        
        return False
    
    def _walk_nodes(self, tree):
        """Walk all nodes in the syntax tree."""
        def walk(node):
            if node is not None:
                yield node
                children = getattr(node, 'children', [])
                for child in children:
                    yield from walk(child)
        
        root = getattr(tree, 'root_node', tree)
        yield from walk(root)


# Export the rule for registration
RULES = [PerfRepeatedRegexCompileRule()]


