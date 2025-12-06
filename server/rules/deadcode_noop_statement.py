# server/rules/deadcode_noop_statement.py
"""
Rule: deadcode.noop_statement

Removes no-op statements: standalone `;` empty statements and safe empty blocks `{}` in C-style languages.
Keeps exceptions for control constructs that require the token (e.g., `for ( ; ; )` header, `doâ€¦while(...);`) 
and for labeled empty statements.
"""

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
except ImportError:
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit

import re
from typing import List, Tuple, Optional

# Regex helpers (bytes)
RE_ELSE_EMPTY = re.compile(rb"else\s*\{\s*\}")
RE_IF_EMPTY_BLK = re.compile(rb"(?P<hdr>\bif\b\s*\([^)]*\)\s*)\{\s*\}")
RE_STANDALONE_EMPTY_BLOCK_LINE = re.compile(rb"(?m)^\s*\{\s*\}\s*(?:\r?\n|$)")

class DeadcodeNoopStatementRule(Rule):
    """Remove no-op statements: standalone ';' and safe empty blocks."""
    
    meta = RuleMeta(
        id="deadcode.noop_statement",
        category="deadcode",
        tier=0,
        priority="P2",
        autofix_safety="safe",
        description="Remove no-op statements: standalone ';' and safe empty blocks.",
        langs=["java", "csharp", "cpp", "c", "javascript", "typescript"]
    )

    requires = Requires(syntax=True)

    def visit(self, ctx: RuleContext) -> List[Finding]:
        """Find and remove no-op statements in the file."""
        findings = []
        
        # Check language using adapter language_id
        adapter_language = getattr(ctx.adapter, 'language_id', '')
        if adapter_language not in self.meta.langs:
            return findings

        b = ctx.text.encode('utf-8')  # bytes

        edits = []
        edits += self._collect_semicolon_noops(ctx)          # token-driven (precise)
        edits += self._collect_empty_block_edits(b)          # regex-driven (conservative)

        if not edits:
            return findings

        # sort & merge non-overlapping edits
        edits.sort(key=lambda e: e[0])
        merged = []
        for s, e, r in edits:
            if not merged or s >= merged[-1][1]:
                merged.append([s, e, r])
            else:
                # overlapping; keep earlier span, prefer replacing all with latest r for simplicity
                merged[-1][1] = max(merged[-1][1], e)
                merged[-1][2] = r

        # Create list of Edit objects
        edit_objects = [Edit(
            start_byte=s,
            end_byte=e,
            replacement=self._to_str(r)
        ) for s, e, r in merged]

        finding = Finding(
            rule=self.meta.id,
            message="Removed no-op statements (empty statements/blocks).",
            file=ctx.file_path,
            start_byte=merged[0][0],
            end_byte=merged[-1][1],
            severity="info",
            autofix=edit_objects
        )
        findings.append(finding)

        return findings

    # --- helpers ---

    def _collect_semicolon_noops(self, ctx: RuleContext) -> List[Tuple[int, int, bytes]]:
        """
        Delete semicolons that form empty statements:
        - Not inside a for(;;) header
        - Not the mandatory terminator of 'do {..} while (...);'
        - Not a labeled empty statement: 'label: ;'
        """
        edits = []
        
        if ctx.tree is None:
            return edits
        
        # Use syntax tree traversal to find semicolon tokens
        def traverse_node(node):
            if hasattr(node, 'type') and hasattr(node, 'text'):
                if node.type == ';' or (hasattr(node, 'text') and node.text == b';'):
                    # Found a semicolon token
                    if self._is_noop_semicolon(ctx, node):
                        s, e = node.start_byte, node.end_byte
                        # swallow one trailing newline for cleanliness
                        b = ctx.text.encode('utf-8')
                        if e < len(b) and b[e:e+1] in (b"\n",):
                            e += 1
                        elif e + 1 < len(b) and b[e:e+2] == b"\r\n":
                            e += 2
                        edits.append((s, e, b""))
            
            # Visit children
            if hasattr(node, 'children'):
                for child in node.children:
                    traverse_node(child)
        
        traverse_node(ctx.tree.root_node)
        return edits

    def _is_noop_semicolon(self, ctx: RuleContext, semicolon_node) -> bool:
        """Check if a semicolon is a no-op statement that can be safely removed."""
        
        if not hasattr(semicolon_node, 'parent') or not semicolon_node.parent:
            return False
            
        parent = semicolon_node.parent
        parent_type = getattr(parent, 'type', '')
        
        # Check ancestors up to 4 levels for for loops and labeled statements
        ancestor = parent
        for level in range(4):
            if ancestor:
                ancestor_type = getattr(ancestor, 'type', '')
                # Skip any semicolon inside for loop constructs
                if any(keyword in ancestor_type.lower() for keyword in ['for_statement', 'for_loop', 'for_in_statement', 'c_style_for']):
                    return False
                # Skip semicolons in labeled statements (at any level in the ancestry)
                if 'labeled_statement' in ancestor_type:
                    return False
                # Skip semicolons that are the body of control structures (if, while, etc.)
                if ancestor_type in ['if_statement', 'while_statement', 'for_statement', 'switch_statement']:
                    return False
                ancestor = getattr(ancestor, 'parent', None)
            else:
                break
        
        # Don't remove semicolons that are part of do-while statements
        if any(keyword in parent_type.lower() for keyword in ['do_statement', 'do_while', 'while_statement']):
            return False
        
        # Semicolons that are direct children of blocks/compound statements are usually no-ops
        if parent_type in ['block', 'compound_statement', 'statement_block']:
            return True
        
        # For expression statements, check if they contain meaningful content
        if 'expression_statement' in parent_type or 'empty_statement' in parent_type:
            # If this is an empty_statement that's part of a control structure, preserve it
            if 'empty_statement' in parent_type and hasattr(parent, 'parent'):
                grandparent_type = getattr(parent.parent, 'type', '')
                if grandparent_type in ['if_statement', 'while_statement', 'for_statement', 'switch_statement']:
                    return False
            
            # Count meaningful children (excluding punctuation)
            meaningful_children = []
            if hasattr(parent, 'children'):
                for child in parent.children:
                    child_type = getattr(child, 'type', '')
                    child_text = getattr(child, 'text', b'').decode('utf-8', errors='ignore').strip()
                    # Skip punctuation and whitespace
                    if child_type != ';' and child_text and child_text not in ['{', '}', '(', ')']:
                        meaningful_children.append(child)
            
            # If there are no meaningful children besides the semicolon, it's a no-op
            return len(meaningful_children) == 0
        
        # For other statement types, check if they're really empty
        if hasattr(parent, 'children') and parent.children:
            non_semicolon_children = [
                child for child in parent.children 
                if getattr(child, 'type', '') != ';'
            ]
            # If the only child is the semicolon, it might be a no-op
            return len(non_semicolon_children) == 0
        
        return False

    def _collect_empty_block_edits(self, b: bytes) -> List[Tuple[int, int, bytes]]:
        """
        1) Remove 'else { }' entirely.
        2) Convert 'if (...) { }' â†’ 'if (...) ;' (noop), to be cleaned by semicolon pass.
        3) Remove standalone '{ }' lines.
        Never touch loop/try/switch/function/class bodies (patterns below avoid those).
        """
        edits = []

        # else { }
        for m in RE_ELSE_EMPTY.finditer(b):
            edits.append((m.start(), m.end(), b""))

        # if (...) { }
        for m in RE_IF_EMPTY_BLK.finditer(b):
            hdr = m.group("hdr")
            repl = hdr + b";"
            edits.append((m.start(), m.end(), repl))

        # Standalone '{ }' line
        for m in RE_STANDALONE_EMPTY_BLOCK_LINE.finditer(b):
            edits.append((m.start(), m.end(), b""))

        return edits

    def _to_str(self, s_or_b):
        return s_or_b.decode("utf-8", "ignore") if isinstance(s_or_b, (bytes, bytearray)) else s_or_b


# Register the rule
try:
    from ..engine.registry import register_rule
    register_rule(DeadcodeNoopStatementRule())
except ImportError:
    # Handle local testing
    pass


