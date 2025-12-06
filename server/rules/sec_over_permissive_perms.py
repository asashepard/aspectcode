"""Rule: sec.over_permissive_perms

Detects over-permissive file/directory permissions (e.g., 777, 666, a+rwx) in code.
Flags explicit world-writable or group-writable permissions and broad executable bits.
Recommends least-privilege modes and avoiding world-writable/exec permissions.
"""

import re
from typing import Iterator

from engine.types import Rule, RuleContext, RuleMeta, Finding, Requires


class SecOverPermissivePermsRule(Rule):
    """Rule implementation for detecting over-permissive file/directory permissions."""
    
    meta = RuleMeta(
        id="sec.over_permissive_perms",
        category="sec",
        tier=0,
        priority="P1",
        autofix_safety="suggest-only",
        description="Detects over-permissive file/directory permissions (e.g., 777/666/a+rwx)",
        langs=["python", "bash", "javascript"],
    )
    requires = Requires(syntax=True)
    
    # Permission masks for detecting dangerous permissions
    WORLD_WRITABLE_MASK = 0o002  # others write
    GROUP_WRITABLE_MASK = 0o020  # group write  
    DANGEROUS_EXEC_MASK = 0o011  # exec for group/others
    
    # Known dangerous symbolic modes
    SYMBOLIC_BAD = ("a+rwx", "ugo+rwx", "o+w", "go+w", "a+w", "g+w", "o+rwx", "go+rwx")
    
    def __init__(self):
        # Target functions/commands by language
        self.TARGETS = {
            "python": {
                "os.chmod", "os.mkdir", "os.makedirs", "tempfile.NamedTemporaryFile",
                "open", "os.open", "pathlib.Path.mkdir", "pathlib.Path.chmod"
            },
            "javascript": {
                "fs.chmod", "fs.chmodSync", "fs.mkdir", "fs.mkdirSync", 
                "fs.open", "fs.openSync", "fs.writeFile", "fs.writeFileSync"
            },
            "bash": {
                "chmod", "install", "mkdir"
            }
        }
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit AST nodes and detect over-permissive permissions."""
        language = ctx.language
        
        if language in ("python", "javascript"):
            # Use text-based analysis for better compatibility with test setup
            yield from self._analyze_text_permissions(ctx, language)
        elif language == "bash":
            yield from self._analyze_bash_permissions(ctx)
    
    def _analyze_text_permissions(self, ctx: RuleContext, language: str) -> Iterator[Finding]:
        """Analyze permissions in Python/JavaScript using text patterns."""
        code_text = ctx.text
        lines = code_text.split('\n')
        
        targets = self.TARGETS.get(language, set())
        
        for line_num, line in enumerate(lines):
            line = line.strip()
            if not line or line.startswith('#') or line.startswith('//'):
                continue
            
            # Check if line contains permission-setting function
            if any(target.split('.')[-1] in line for target in targets):
                # Extract permission values from the line
                mode_value = self._extract_mode_value_from_text(line)
                if mode_value is not None and self._is_over_permissive(mode_value):
                    yield self._create_finding_from_line(line, ctx, line_num, mode_value, language)
    
    def _analyze_bash_permissions(self, ctx: RuleContext) -> Iterator[Finding]:
        """Analyze permissions in bash scripts."""
        for cmd_node in self._get_shell_commands(ctx):
            cmd_name, args = self._extract_command_info(cmd_node, ctx)
            if cmd_name in self.TARGETS["bash"]:
                mode_values = self._extract_bash_mode_values(cmd_name, args)
                for mode_value in mode_values:
                    if self._is_over_permissive_bash(mode_value):
                        yield self._create_finding(cmd_node, ctx, mode_value, "shell_command")
    
    def _extract_mode_value_from_text(self, text: str):
        """Extract permission mode from text line."""
        # Look for common permission patterns
        
        # Match octal literals: 0o777, 0777
        octal_match = re.search(r'0o?([0-7]{3,4})', text)
        if octal_match:
            try:
                return int(octal_match.group(1), 8)
            except ValueError:
                pass
        
        # Match mode in object notation: {mode: 0o777}
        object_mode_match = re.search(r'mode:\s*0o?([0-7]{3,4})', text)
        if object_mode_match:
            try:
                return int(object_mode_match.group(1), 8)
            except ValueError:
                pass
        
        # Match decimal numbers that might be permissions (without 0o prefix)
        decimal_match = re.search(r'\b([0-7]{3})\b', text)
        if decimal_match:
            try:
                return int(decimal_match.group(1), 8)
            except ValueError:
                pass
        
        return None
    
    def _create_finding_from_line(self, line: str, ctx: RuleContext, line_num: int, mode_value, language: str) -> Finding:
        """Create a Finding from line analysis."""
        # Estimate byte position for the line
        lines_before = ctx.text.split('\n')[:line_num]
        start_byte = sum(len(l) + 1 for l in lines_before)  # +1 for newline
        end_byte = start_byte + len(line)
        
        # Format the mode value for display
        if isinstance(mode_value, int):
            mode_display = oct(mode_value)
        else:
            mode_display = str(mode_value)
        
        message = f"Over-permissive permissions (`{mode_display}`) set explicitly"
        
        # Add language-specific suggestions
        suggestions = {
            "python": "Use least-privilege (e.g., `0o750` for dirs, `0o640` for files) and rely on umask.",
            "javascript": "Use least-privilege (e.g., `0o750` for dirs, `0o640` for files) and rely on process umask.",
            "bash": "Prefer `-m 750` for dirs, `-m 640` for files, or avoid world/group write/exec permissions."
        }
        
        suggestion = suggestions.get(language, "Use least-privilege permissions and avoid world-writable/executable bits.")
        full_message = f"{message}. {suggestion}"
        
        return Finding(
            rule=self.meta.id,
            message=full_message,
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            severity="warning"
        )
    
    def _get_call_nodes(self, ctx: RuleContext) -> list:
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
    
    def _get_shell_commands(self, ctx: RuleContext) -> list:
        """Get shell command nodes for bash."""
        # For bash, we'll analyze the text directly since shell parsing is complex
        commands = []
        if hasattr(ctx, 'text') and ctx.text:
            lines = ctx.text.split('\n')
            for line_num, line in enumerate(lines):
                line = line.strip()
                if line and not line.startswith('#'):
                    # Create a simple command representation
                    command = {
                        'line': line,
                        'line_num': line_num,
                        'start_byte': sum(len(l) + 1 for l in lines[:line_num]),
                        'end_byte': sum(len(l) + 1 for l in lines[:line_num]) + len(line)
                    }
                    commands.append(command)
        
        return commands
    
    def _is_permission_call(self, call_node, ctx: RuleContext, language: str) -> bool:
        """Check if the call is to a function that sets permissions."""
        call_text = self._get_node_text(call_node, ctx)
        targets = self.TARGETS.get(language, set())
        
        # Check for exact matches or contains matches
        for target in targets:
            if target in call_text:
                return True
        
        return False
    
    def _extract_mode_value(self, call_node, ctx: RuleContext, language: str):
        """Extract the mode value from a function call."""
        call_text = self._get_node_text(call_node, ctx)
        
        # Look for common permission patterns
        import re
        
        # Match octal literals: 0o777, 0777
        octal_match = re.search(r'0o?([0-7]{3,4})', call_text)
        if octal_match:
            try:
                return int(octal_match.group(1), 8)
            except ValueError:
                pass
        
        # Match decimal numbers that might be permissions
        decimal_match = re.search(r'\b([0-7]{3})\b', call_text)
        if decimal_match:
            try:
                return int(decimal_match.group(1), 8)
            except ValueError:
                pass
        
        # Match hex literals: 0x1ff (for 777 in hex)
        hex_match = re.search(r'0x([0-9a-fA-F]+)', call_text)
        if hex_match:
            try:
                return int(hex_match.group(1), 16)
            except ValueError:
                pass
        
        return None
    
    def _extract_command_info(self, cmd_node, ctx: RuleContext):
        """Extract command name and arguments from shell command."""
        line = cmd_node['line']
        parts = line.split()
        if parts:
            cmd_name = parts[0]
            args = parts[1:]
            return cmd_name, args
        return None, []
    
    def _extract_bash_mode_values(self, cmd_name: str, args: list) -> list:
        """Extract mode values from bash command arguments."""
        mode_values = []
        
        if cmd_name in ("install", "mkdir"):
            # Look for -m flag
            try:
                if "-m" in args:
                    m_index = args.index("-m")
                    if m_index + 1 < len(args):
                        mode_values.append(args[m_index + 1])
            except (ValueError, IndexError):
                pass
        
        elif cmd_name == "chmod":
            # For chmod, any argument that looks like a mode
            for arg in args:
                if self._looks_like_mode(arg):
                    mode_values.append(arg)
        
        return mode_values
    
    def _looks_like_mode(self, arg: str) -> bool:
        """Check if an argument looks like a file mode."""
        # Numeric modes
        if re.match(r'^[0-7]{3,4}$', arg):
            return True
        
        # Symbolic modes
        symbolic_patterns = [
            r'^[ugoa]*[+\-=][rwxXst]*$',  # u+rwx, go-w, etc.
            r'^[ugoa]*[+\-=][rwxXst]*,[ugoa]*[+\-=][rwxXst]*$',  # u+rw,g+r
        ]
        
        for pattern in symbolic_patterns:
            if re.match(pattern, arg):
                return True
        
        # Common dangerous symbolic modes
        if any(bad in arg for bad in self.SYMBOLIC_BAD):
            return True
        
        return False
    
    def _parse_mode_literal(self, val) -> int:
        """Parse a mode literal value (string or int) to integer."""
        if isinstance(val, int):
            return val
        
        if isinstance(val, str):
            val = val.strip()
            
            # Handle different formats
            if val.startswith("0o"):
                try:
                    return int(val[2:], 8)
                except ValueError:
                    return None
            elif val.startswith("0x"):
                try:
                    return int(val[2:], 16)
                except ValueError:
                    return None
            elif val.isdigit() and len(val) == 3:
                try:
                    return int(val, 8)
                except ValueError:
                    return None
            else:
                try:
                    return int(val, 8)
                except ValueError:
                    return None
        
        return None
    
    def _is_over_permissive(self, mode_value) -> bool:
        """Check if a numeric mode value is over-permissive."""
        if mode_value is None:
            return False
        
        mode_int = self._parse_mode_literal(mode_value) if not isinstance(mode_value, int) else mode_value
        if mode_int is None:
            return False
        
        # Check for world-writable (others write) - this is definitely dangerous
        if mode_int & self.WORLD_WRITABLE_MASK:
            return True
        
        # Check for group-writable in broad contexts
        # Flag 775, 775, 765, etc. but allow 750
        if (mode_int & self.GROUP_WRITABLE_MASK):
            return True
        
        # Allow common safe patterns like 755 (read/execute for all, write for owner only)
        # Only flag execute if it's combined with write permissions for non-owner
        # This allows 755 but flags 777, 771, etc.
        
        return False
    
    def _is_over_permissive_bash(self, mode_value) -> bool:
        """Check if a bash mode value (string) is over-permissive."""
        if not mode_value:
            return False
        
        # Check numeric modes
        if self._is_over_permissive(mode_value):
            return True
        
        # Check symbolic modes
        for bad_symbol in self.SYMBOLIC_BAD:
            if bad_symbol in mode_value:
                return True
        
        # Additional symbolic checks
        dangerous_patterns = [
            "o+w",  # others write
            "g+w",  # group write  
            "a+w",  # all write
            "777",  # full permissions
            "666",  # read/write for all
            "755",  # read/execute for group/others (can be considered permissive for some contexts)
        ]
        
        for pattern in dangerous_patterns:
            if pattern in mode_value:
                return True
        
        return False
    
    def _create_finding(self, node, ctx: RuleContext, mode_value, finding_type: str) -> Finding:
        """Create a Finding for over-permissive permissions."""
        if finding_type == "shell_command":
            start_byte = node['start_byte']
            end_byte = node['end_byte']
        else:
            start_byte, end_byte = self._get_node_span(node)
        
        language = ctx.language
        
        # Format the mode value for display
        if isinstance(mode_value, int):
            mode_display = oct(mode_value)
        else:
            mode_display = str(mode_value)
        
        message = f"Over-permissive permissions (`{mode_display}`) set explicitly"
        
        # Add language-specific suggestions
        suggestions = {
            "python": "Use least-privilege (e.g., `0o750` for dirs, `0o640` for files) and rely on umask.",
            "javascript": "Use least-privilege (e.g., `0o750` for dirs, `0o640` for files) and rely on process umask.",
            "bash": "Prefer `-m 750` for dirs, `-m 640` for files, or avoid world/group write/exec permissions."
        }
        
        suggestion = suggestions.get(language, "Use least-privilege permissions and avoid world-writable/executable bits.")
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
RULES = [SecOverPermissivePermsRule()]


