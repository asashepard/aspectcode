"""Rule: sec.command_injection

Detects command execution built from user/variable input or executed via a shell.
Flags os.system, subprocess.*(shell=True), Node child_process.exec/execSync, Ruby system/backticks, 
Go exec.Command("sh","-c", ...), C# Process.Start/cmd.exe /C, etc.
Recommends argument-vector exec, allowlisting, and strict quoting/escaping.
"""

from dataclasses import dataclass
from typing import Iterator, List, Optional, Set, Dict

from engine.types import Rule, RuleContext, RuleMeta, Finding, Requires


class SecCommandInjectionRule:
    """Rule implementation for detecting command injection vulnerabilities."""
    
    meta = RuleMeta(
        id="sec.command_injection",
        category="sec",
        tier=0,
        priority="P0",
        autofix_safety="suggest-only",
        description="Detects command execution built from user/variable input or executed via a shell",
        langs=["python", "javascript", "typescript", "ruby", "go", "csharp"],
    )
    requires = Requires(syntax=True)
    
    def __init__(self):
        # Command execution sinks by language
        self.SINK_TAILS = {
            "python": {
                "os.system", "os.popen", "subprocess.call", "subprocess.run", 
                "subprocess.Popen", "subprocess.check_call", "subprocess.check_output",
                "commands.getoutput", "commands.getstatusoutput"
            },
            "javascript": {
                "child_process.exec", "child_process.execSync", "child_process.spawn", 
                "child_process.spawnSync", "execa", "exec", "execSync", "spawn", "spawnSync"
            },
            "typescript": {
                "child_process.exec", "child_process.execSync", "child_process.spawn", 
                "child_process.spawnSync", "execa", "exec", "execSync", "spawn", "spawnSync"
            },
            "ruby": {
                "system", "Kernel.system", "IO.popen", "Open3.capture3", "Open3.popen3",
                "`", "%x", "exec"
            },
            "go": {
                "os/exec.Command", "os/exec.CommandContext", "exec.Command", "exec.CommandContext"
            },
            "csharp": {
                "System.Diagnostics.Process.Start", "Process.Start", "ProcessStartInfo"
            }
        }
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Check for command injection vulnerabilities."""
        if not hasattr(ctx, 'tree') or not ctx.tree:
            return
            
        # Get language from adapter
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):
            language = language()
        if language not in self.SINK_TAILS:
            return
        
        for node in ctx.tree.walk():
            # Check if this is a function call
            if not self._is_call_node(node):
                continue
                
            callee = self._get_callee_text(node, ctx)
            if not callee or not self._is_sink(language, callee):
                continue
            
            # Check if this is a vulnerable pattern
            if self._is_shell_mode(language, node, ctx) or self._arg_is_dynamic_command(language, node, ctx):
                start_byte, end_byte = self._get_callee_span(node, ctx)
                message = ("Possible command injection: command is built from variables or executed via a shell. "
                          "Use argument-vector exec (no shell), allowlist, and proper escaping.")
                yield Finding(
                    rule=self.meta.id,
                    message=message,
                    file=ctx.file_path,
                    start_byte=start_byte,
                    end_byte=end_byte,
                    severity="error"
                )
    
    def _is_call_node(self, node) -> bool:
        """Check if node represents a function call."""
        kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
        return kind in {
            'call_expression', 'call', 'function_call', 'method_call',
            'invocation_expression', 'method_invocation',
            'command_substitution', 'backtick_expression'  # For Ruby backticks
        }
    
    def _get_callee_text(self, node, ctx: RuleContext) -> str:
        """Extract the callee text from a call node."""
        # Try to find the function/method being called
        callee_node = None
        
        # Look for common callee patterns
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in {'identifier', 'member_expression', 'attribute', 'qualified_name', 'dotted_name'}:
                callee_node = child
                break
        
        if not callee_node:
            return ""
        
        # Get the text of the callee
        start_byte = getattr(callee_node, 'start_byte', 0)
        end_byte = getattr(callee_node, 'end_byte', start_byte)
        
        return ctx.text[start_byte:end_byte]
    
    def _get_callee_span(self, node, ctx: RuleContext) -> tuple:
        """Get the span of the callee for reporting."""
        # Find callee node
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in {'identifier', 'member_expression', 'attribute', 'qualified_name', 'dotted_name'}:
                return (getattr(child, 'start_byte', 0), getattr(child, 'end_byte', 0))
        
        # Fallback to the whole call node
        return (getattr(node, 'start_byte', 0), getattr(node, 'end_byte', 0))
    
    def _is_sink(self, language: str, callee: str) -> bool:
        """Check if the callee is a command execution sink."""
        sinks = self.SINK_TAILS.get(language, set())
        
        # Direct match
        if callee in sinks:
            return True
        
        # Special case for Ruby backticks - check if the callee starts with backtick
        if language == "ruby" and (callee.startswith('`') or '`' in callee):
            return True
        
        # Suffix match (for qualified names)
        for sink in sinks:
            if callee.endswith('.' + sink) or callee.endswith('::' + sink):
                return True
            if callee.split('(')[0].endswith(sink):
                return True
        
        return False
    
    def _is_shell_mode(self, language: str, node, ctx: RuleContext) -> bool:
        """Check if the command is executed via shell."""
        node_text = self._get_node_text(node, ctx).replace(' ', '').replace('\n', '').replace('\t', '')
        
        # Python: shell=True
        if language == "python" and "shell=True" in node_text:
            return True
        
        # JavaScript/TypeScript: { shell: true } in options
        if language in {"javascript", "typescript"}:
            if "{shell:true" in node_text.lower() or "shell:true" in node_text.lower():
                return True
        
        # Go: exec.Command("sh", "-c", ...) or ("cmd", "/C", ...)
        if language == "go":
            args = self._get_call_arguments(node)
            if len(args) >= 2:
                first_arg = self._get_node_text(args[0], ctx).strip('"\'')
                second_arg = self._get_node_text(args[1], ctx).strip('"\'')
                if first_arg.lower() in {"sh", "bash", "cmd", "cmd.exe"} and second_arg in {"-c", "/C", "/c"}:
                    return True
        
        # C#: cmd.exe /C or powershell -Command
        if language == "csharp":
            node_text_lower = node_text.lower()
            if ("cmd.exe" in node_text_lower and "/c" in node_text_lower) or "powershell" in node_text_lower:
                return True
        
        # Ruby: backticks or %x{} imply shell; system also uses shell if single string arg
        if language == "ruby":
            callee = self._get_callee_text(node, ctx)
            if callee in {"`", "%x"} or callee.startswith("`"):
                return True
            # For system calls, check if it's a single string argument (shell mode)
            # vs multiple arguments (argv mode)  
            if callee.endswith("system"):
                args = self._get_call_arguments(node)
                if len(args) == 1:  # Single string argument = shell mode
                    return True
        
        return False
    
    def _arg_is_dynamic_command(self, language: str, node, ctx: RuleContext) -> bool:
        """Check if the command argument is built via concatenation/interpolation."""
        args = self._get_call_arguments(node)
        if not args:
            return False
        
        cmd_arg = args[0]
        return self._is_dynamic_string(language, cmd_arg, ctx)
    
    def _is_dynamic_string(self, language: str, node, ctx: RuleContext) -> bool:
        """Check if a node represents a dynamically built string."""
        kind = getattr(node, 'kind', '') or getattr(node, 'type', '')
        text = self._get_node_text(node, ctx)
        
        # Binary expression with + operator (concatenation)
        if kind == "binary_expression":
            # Check if it's string concatenation
            if "+" in text:
                return True
        
        # Template strings and interpolation
        if kind in {"template_string", "interpolated_string", "fstring", "f_string"}:
            if any(marker in text for marker in ["${", "#{", "{"]):
                return True
        
        # Language-specific patterns
        if language == "ruby" and "#{" in text:
            return True
        
        if language == "csharp":
            # String.Format calls
            if kind in {"call_expression", "invocation_expression"}:
                callee = self._get_callee_text(node, ctx)
                if "String.Format" in callee or "string.Format" in callee:
                    return True
            # String interpolation
            if '$"' in text or "{0}" in text:
                return True
        
        # Python f-strings
        if language == "python" and (text.startswith('f"') or text.startswith("f'") or "{" in text):
            return True
        
        # Check for concatenation patterns in surrounding context
        if kind in {"identifier", "name"}:
            # This is a simplistic check - in a real implementation, 
            # we might want to do dataflow analysis
            return self._check_identifier_for_dynamic_assignment(node, ctx)
        
        return False
    
    def _check_identifier_for_dynamic_assignment(self, node, ctx: RuleContext) -> bool:
        """Heuristic check if an identifier was assigned a dynamic value."""
        # This is a simplified heuristic - a full implementation would do proper dataflow analysis
        # For now, we'll just check if there's concatenation or interpolation nearby
        node_text = self._get_node_text(node, ctx)
        
        # Get some surrounding context to look for assignment patterns
        start_byte = max(0, getattr(node, 'start_byte', 0) - 200)
        end_byte = getattr(node, 'end_byte', 0) + 200
        
        surrounding_text = ctx.text[start_byte:end_byte]
        
        # Look for assignment patterns with concatenation
        variable_name = node_text.strip()
        patterns = [
            f"{variable_name} = ",
            f"{variable_name}=",
            f"var {variable_name} = ",
            f"let {variable_name} = ",
            f"const {variable_name} = "
        ]
        
        for pattern in patterns:
            if pattern in surrounding_text:
                # Look for concatenation or interpolation after the assignment
                assignment_start = surrounding_text.find(pattern)
                assignment_line = surrounding_text[assignment_start:assignment_start + 100]
                if any(marker in assignment_line for marker in ["+", "${", "#{", "f\"", "f'", "{0}"]):
                    return True
        
        return False
    
    def _get_call_arguments(self, node) -> list:
        """Extract arguments from a call node."""
        args = []
        
        for child in getattr(node, 'children', []):
            child_kind = getattr(child, 'kind', '') or getattr(child, 'type', '')
            if child_kind in {'arguments', 'argument_list', 'parameter_list'}:
                # Get the actual argument nodes from children first
                for arg_child in getattr(child, 'children', []):
                    arg_kind = getattr(arg_child, 'kind', '') or getattr(arg_child, 'type', '')
                    if arg_kind not in {',', '(', ')', 'comma'}:
                        args.append(arg_child)
                
                # If no actual args found but we have argument count metadata, use it
                if not args and hasattr(child, 'arg_count'):
                    arg_count = getattr(child, 'arg_count', 0)
                    # Return a list with None placeholders to indicate count
                    return [None] * arg_count
                break
        
        return args
    
    def _get_node_text(self, node, ctx: RuleContext) -> str:
        """Get the text content of a node."""
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', start_byte)
        
        return ctx.text[start_byte:end_byte]


# Export rule for registration
RULES = [SecCommandInjectionRule()]


