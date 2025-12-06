"""
Rule: mut.default_mutable_arg (Python)

Flags mutable default arguments in function definitions which can lead
to shared state bugs. Provides cautious autofix with None + guard pattern.
"""

from typing import Iterator
try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
except ImportError:
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit


class MutDefaultMutableArgRule:
    """Flag mutable default arguments in Python functions."""
    
    meta = RuleMeta(
        id="mut.default_mutable_arg",
        category="mut",
        tier=0,
        priority="P0",
        autofix_safety="caution",
        description="Mutable default argument; use None + guard pattern",
        langs=["python"]
    )
    
    requires = Requires(
        raw_text=False,
        syntax=True,
        scopes=False,
        project_graph=False
    )
    
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Find mutable default arguments in function definitions."""
        if not ctx.tree:
            return
            
        # Walk the tree to find function definitions
        for node in self._walk_tree(ctx.tree.root_node):
            if node.type == "function_definition":
                yield from self._check_function_parameters(node, ctx)
    
    def _walk_tree(self, node):
        """Recursively walk the syntax tree."""
        yield node
        for child in getattr(node, 'children', []):
            yield from self._walk_tree(child)
    
    def _check_function_parameters(self, func_node, ctx: RuleContext):
        """Check function parameters for mutable default arguments."""
        # Find the parameters node
        parameters_node = None
        for child in getattr(func_node, 'children', []):
            if child.type == "parameters":
                parameters_node = child
                break
        
        if not parameters_node:
            return
            
        # Check each parameter for mutable defaults
        for param_node in self._get_parameters(parameters_node):
            if self._has_mutable_default(param_node, ctx):
                yield from self._create_finding_for_parameter(param_node, func_node, ctx)
    
    def _get_parameters(self, parameters_node):
        """Extract individual parameter nodes."""
        for child in getattr(parameters_node, 'children', []):
            if child.type == "default_parameter":
                yield child
            elif child.type == "typed_default_parameter":
                yield child
    
    def _has_mutable_default(self, param_node, ctx: RuleContext) -> bool:
        """Check if parameter has a mutable default value."""
        default_value_node = self._get_default_value_node(param_node)
        if not default_value_node:
            return False
            
        default_text = self._get_node_text(default_value_node, ctx)
        
        # Check for mutable default patterns
        mutable_patterns = [
            # Lists
            r'^\[\s*\]$',  # []
            r'^\[.*\]$',   # [anything]
            # Dictionaries  
            r'^\{\s*\}$',  # {}
            r'^\{.*\}$',   # {anything}
            # Sets
            r'^set\(\s*\)$',  # set()
            r'^set\(.*\)$',   # set(anything)
            # Function calls that return mutable objects
            r'^list\(\s*\)$',  # list()
            r'^dict\(\s*\)$',  # dict()
        ]
        
        import re
        for pattern in mutable_patterns:
            if re.match(pattern, default_text.strip()):
                return True
                
        # Check for specific node types that are mutable
        if default_value_node.type in ["list", "dictionary", "set"]:
            return True
            
        # Check for function calls to list/dict/set constructors
        if default_value_node.type == "call":
            func_name = self._get_function_name_from_call(default_value_node, ctx)
            if func_name in ["list", "dict", "set"]:
                return True
                
        return False
    
    def _get_default_value_node(self, param_node):
        """Extract the default value node from a parameter."""
        # For default_parameter, the structure is: identifier, =, default_value
        children = getattr(param_node, 'children', [])
        
        # Find the equals sign, then the next child should be the default value
        equals_found = False
        for child in children:
            if equals_found and child.type not in ["=", ","]:
                return child
            if child.type == "=":
                equals_found = True
        
        # Fallback: get the last non-operator child
        for child in reversed(children):
            if child.type not in ["identifier", ":", "=", ",", "(", ")"]:
                return child
        return None
    
    def _get_function_name_from_call(self, call_node, ctx: RuleContext) -> str:
        """Extract function name from a call expression."""
        for child in getattr(call_node, 'children', []):
            if child.type == "identifier":
                return self._get_node_text(child, ctx)
        return ""
    
    def _create_finding_for_parameter(self, param_node, func_node, ctx: RuleContext):
        """Create a finding for a parameter with mutable default."""
        param_name = self._get_parameter_name(param_node, ctx)
        default_value_node = self._get_default_value_node(param_node)
        
        if not param_name or not default_value_node:
            return
            
        default_text = self._get_node_text(default_value_node, ctx)
        mutable_type = self._determine_mutable_type(default_value_node, ctx)
        
        # Create autofix
        autofix_edits = self._create_comprehensive_autofix(param_node, func_node, param_name, mutable_type, ctx)
        
        # Build metadata
        guard_mapping = {"list": "[]", "dict": "{}", "set": "set()"}
        mutable_init = guard_mapping.get(mutable_type, "[]")
        
        meta = {
            "param": param_name,
            "default_kind": mutable_type,
            "suggested_guard": f"if {param_name} is None: {param_name} = {mutable_init}",
            "original_default": default_text
        }
        
        start_byte, end_byte = self._get_node_span(param_node)
        
        finding = Finding(
            rule=self.meta.id,
            message=f"Mutable default argument '{param_name}' ({mutable_type}); use None + guard pattern",
            severity="error",
            file=ctx.file_path,
            start_byte=start_byte,
            end_byte=end_byte,
            autofix=autofix_edits,
            meta=meta
        )
        
        yield finding
    
    def _get_parameter_name(self, param_node, ctx: RuleContext) -> str:
        """Extract parameter name from parameter node."""
        for child in getattr(param_node, 'children', []):
            if child.type == "identifier":
                return self._get_node_text(child, ctx)
        return ""
    
    def _determine_mutable_type(self, default_value_node, ctx: RuleContext) -> str:
        """Determine the type of mutable object."""
        if default_value_node.type == "list":
            return "list"
        elif default_value_node.type == "dictionary":
            return "dict"
        elif default_value_node.type == "set":
            return "set"
        elif default_value_node.type == "call":
            func_name = self._get_function_name_from_call(default_value_node, ctx)
            if func_name in ["list", "dict", "set"]:
                return func_name
        
        # Fallback: analyze text
        default_text = self._get_node_text(default_value_node, ctx).strip()
        if default_text.startswith('[') and default_text.endswith(']'):
            return "list"
        elif default_text.startswith('{') and default_text.endswith('}'):
            return "dict"
        elif default_text.startswith('set('):
            return "set"
        
        return "list"  # Default fallback
    
    def _create_comprehensive_autofix(self, param_node, func_node, param_name: str, mutable_type: str, ctx: RuleContext) -> list[Edit]:
        """Create comprehensive autofix with parameter replacement and guard insertion."""
        edits = []
        
        # Edit 1: Replace the default value with None
        default_value_node = self._get_default_value_node(param_node)
        if default_value_node:
            start_byte, end_byte = self._get_node_span(default_value_node)
            edits.append(Edit(
                start_byte=start_byte,
                end_byte=end_byte,
                replacement="None"
            ))
        
        # Edit 2: Insert guard after function signature
        guard_position, guard_text = self._find_guard_insertion_point(func_node, param_name, mutable_type, ctx)
        if guard_position is not None:
            edits.append(Edit(
                start_byte=guard_position,
                end_byte=guard_position,
                replacement=guard_text
            ))
        
        return edits
    
    def _find_guard_insertion_point(self, func_node, param_name: str, mutable_type: str, ctx: RuleContext) -> tuple[int | None, str]:
        """Find where to insert the guard statement and create the guard text."""
        func_start, func_end = self._get_node_span(func_node)
        func_text = ctx.text[func_start:func_end]
        
        # Find the colon that ends the function signature
        colon_pos = func_text.find(':')
        if colon_pos == -1:
            return None, ""
        
        # Find the end of the line after the colon
        line_end = func_text.find('\n', colon_pos)
        if line_end == -1:
            line_end = len(func_text)
        
        # Determine indentation by looking at the next non-empty line
        next_line_start = line_end + 1
        indent = "    "  # Default indentation
        
        if next_line_start < len(func_text):
            # Find the first non-empty line to get indentation
            while next_line_start < len(func_text):
                if func_start + next_line_start >= len(ctx.text):
                    break
                char = ctx.text[func_start + next_line_start]
                if char == '\n':
                    next_line_start += 1
                    # Capture indentation of next line
                    indent_start = next_line_start
                    while (next_line_start < len(func_text) and 
                           func_start + next_line_start < len(ctx.text) and
                           ctx.text[func_start + next_line_start] in ' \t'):
                        next_line_start += 1
                    if next_line_start > indent_start:
                        indent = func_text[indent_start:next_line_start]
                    break
                elif char not in ' \t':
                    break
                else:
                    next_line_start += 1
        
        # Create the guard text
        guard_mapping = {"list": "[]", "dict": "{}", "set": "set()"}
        mutable_init = guard_mapping.get(mutable_type, "[]")
        
        # Detect line ending style
        newline = '\r\n' if '\r\n' in ctx.text else '\n'
        
        guard_text = f"{newline}{indent}if {param_name} is None: {param_name} = {mutable_init}"
        
        # Position is right after the colon line
        insertion_pos = func_start + line_end
        
        return insertion_pos, guard_text
    
    def _get_node_text(self, node, ctx: RuleContext = None) -> str:
        """Extract text from a node."""
        if not node:
            return ""
        
        # Try different ways to get node text
        if hasattr(node, 'text'):
            text = node.text
            if isinstance(text, bytes):
                return text.decode('utf-8', errors='replace')
            return str(text)
        
        # Fallback: use span and context
        if ctx and hasattr(node, 'start_byte') and hasattr(node, 'end_byte'):
            return ctx.text[node.start_byte:node.end_byte]
        
        return ""
    
    def _get_node_span(self, node) -> tuple[int, int]:
        """Get the byte span of a node."""
        if not node:
            return 0, 0
            
        start_byte = getattr(node, 'start_byte', 0)
        end_byte = getattr(node, 'end_byte', 0)
        
        return start_byte, end_byte


# Export rule for auto-discovery
RULES = [MutDefaultMutableArgRule()]


