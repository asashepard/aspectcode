# server/rules/deadcode_duplicate_import.py
"""
Rule: deadcode.duplicate_import

Removes duplicate import statements within a file. The rule finds repeated,
textually-identical imports/usings and deletes the duplicates, keeping the first occurrence.
"""

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
except ImportError:
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit

from typing import List, Dict, Tuple, Set

# Per-language node kinds for import-like declarations (examples; adapter may normalize these)
IMPORT_KINDS = {
    "python": {"import_statement", "import_from_statement"},
    "javascript": {"import_statement"},
    "typescript": {"import_statement"},
    "java": {"import_declaration"},
    "csharp": {"using_directive"},
}

class DeadcodeDuplicateImportRule:
    """Remove duplicate import/using statements that are textually identical."""
    
    meta = RuleMeta(
        id="deadcode.duplicate_import",
        category="deadcode",
        tier=0,  # Syntax only
        priority="P2",
        autofix_safety="safe",
        description="Remove duplicate import/using statements that are textually identical.",
        langs=["python", "javascript", "typescript", "java", "csharp"]
    )

    requires = Requires(
        raw_text=True,
        syntax=True,
        scopes=False,
        project_graph=False
    )

    def visit(self, ctx: RuleContext) -> List[Finding]:
        """Find duplicate imports in the file."""
        findings = []
        
        # Basic language check using file extension
        supported_extensions = {
            'py': 'python', 'js': 'javascript', 'ts': 'typescript', 
            'java': 'java', 'cs': 'csharp'
        }
        
        file_ext = ctx.file_path.split('.')[-1].lower() if '.' in ctx.file_path else ''
        language = supported_extensions.get(file_ext, 'unknown')
        
        if language not in self.meta.langs:
            return findings

        kinds = IMPORT_KINDS.get(language, set())
        if not kinds:
            return findings

        b = ctx.text.encode('utf-8')  # bytes
        seen = {}
        dup_spans = []

        def canonical_slice(s, e):
            """Trim leading/trailing whitespace/newlines around the statement for stable matching."""
            while s > 0 and b[s:s+1] in (b" ", b"\t"):
                s += 1
            while e > s and b[e-1:e] in (b" ", b"\t", b"\n", b"\r"):
                e -= 1
            return s, e

        # Walk the syntax tree looking for import-like nodes
        import_nodes = self._find_import_nodes(ctx, kinds)
        
        for node in import_nodes:
            s, e = canonical_slice(node['start_byte'], node['end_byte'])
            key = b[s:e]
            if key in seen:
                # Mark this duplicate for deletion (keep the first)
                dup_spans.append((s, e))
            else:
                seen[key] = (s, e)

        if not dup_spans:
            return findings

        # Create edits; try to remove trailing newline after the duplicate for cleaner formatting
        edits = []
        n = len(b)
        for s, e in dup_spans:
            end = e
            # Consume a single trailing newline (CRLF or LF) if present
            if end < n and b[end:end+1] == b"\n":
                end += 1
            elif end + 1 < n and b[end:end+2] == b"\r\n":
                end += 2
            edits.append(Edit(
                start_byte=s,
                end_byte=end,
                replacement=""
            ))

        # Create a single finding with all the edits
        finding = Finding(
            rule=self.meta.id,
            message=f"Duplicate import/using statements removed ({len(edits)} duplicate{'s' if len(edits) != 1 else ''}).",
            file=ctx.file_path,
            start_byte=dup_spans[0][0],
            end_byte=dup_spans[-1][1],
            severity="info",
            autofix=edits
        )
        findings.append(finding)
        
        return findings

    def _find_import_nodes(self, ctx: RuleContext, kinds: Set[str]) -> List[Dict]:
        """Find import-like nodes in the syntax tree."""
        import_nodes = []
        
        def traverse_node(node):
            """Recursively traverse the syntax tree to find import nodes."""
            # Check if this node is an import-like node
            node_type = getattr(node, 'type', None) or getattr(node, 'kind', None)
            if node_type in kinds:
                import_nodes.append({
                    'start_byte': node.start_byte,
                    'end_byte': node.end_byte,
                    'type': node_type,
                    'text': node.text if hasattr(node, 'text') else b''
                })
            
            # Traverse children
            if hasattr(node, 'children') and node.children:
                for child in node.children:
                    traverse_node(child)
        
        if ctx.tree and hasattr(ctx.tree, 'root_node'):
            traverse_node(ctx.tree.root_node)
        
        return import_nodes


# Register the rule
try:
    from ..engine.registry import register_rule
    from . import register
    register_rule(DeadcodeDuplicateImportRule())  # Global registry
    register(DeadcodeDuplicateImportRule())       # Local RULES list
except ImportError:
    from engine.registry import register_rule
    from rules import register
    register_rule(DeadcodeDuplicateImportRule())  # Global registry
    register(DeadcodeDuplicateImportRule())       # Local RULES list


