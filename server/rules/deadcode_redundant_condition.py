# server/rules/deadcode_redundant_condition.py
"""
Rule: deadcode.redundant_condition

Constant-folds simple boolean expressions and, when structurally safe, 
removes dead branches (e.g., `if (false) { ... } else { ... } → else-body`).
"""

try:
    from ..engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit
except ImportError:
    from engine.types import Rule, Finding, RuleMeta, Requires, RuleContext, Edit

import re
from typing import List, Tuple, Optional

# Boolean literal patterns (bytes) with optional whitespace
TRUE = rb"(?:true|True)"
FALSE = rb"(?:false|False)"

# 1) Boolean op simplifications (safe, expression-level)
#    - X && true  -> X
#    - true && X  -> X  
#    - X || false -> X
#    - false || X -> X
PAT_BOOL_OPS = [
    (re.compile(rb"(?P<lhs>\w+(?:\.\w+)*(?:\([^)]*\))?)\s*&&\s*(?P<rhs>"+TRUE+b")"), "lhs"),
    (re.compile(rb"(?P<lhs>"+TRUE+b")\s*&&\s*(?P<rhs>\w+(?:\.\w+)*(?:\([^)]*\))?)"), "rhs"),
    (re.compile(rb"(?P<lhs>\w+(?:\.\w+)*(?:\([^)]*\))?)\s*\|\|\s*(?P<rhs>"+FALSE+b")"), "lhs"),
    (re.compile(rb"(?P<lhs>"+FALSE+b")\s*\|\|\s*(?P<rhs>\w+(?:\.\w+)*(?:\([^)]*\))?)"), "rhs"),
]

# 2) Ternary simplifications (C-like `cond ? a : b`)
PAT_TERNARY = re.compile(
    rb"(?P<cond>"+TRUE+b"|"+FALSE+b")\s*\?\s*(?P<t>[^:\n;]+?)\s*:\s*(?P<f>[^;\n]+)"
)

# 3) Python conditional expression:  <t> if <cond> else <f>
PAT_PY_IFEXPR = re.compile(
    rb"(?P<t>\w+(?:\.\w+)*(?:\([^)]*\))?)\s+if\s+(?P<cond>"+TRUE+b"|"+FALSE+b")\s+else\s+(?P<f>\w+(?:\.\w+)*(?:\([^)]*\))?)"
)

# 4) Ultra-conservative if/else with braces:
#    if ( true ) {A} else {B}  -> {A}
#    if ( false ) {A} else {B} -> {B}  
#    if ( true ) {A}           -> {A}
#    if ( false ) {A}          -> (delete whole if-block)
# Only when both branches are single brace blocks (no else-if), same line/nearby, and parentheses directly wrap literal.
PAT_IF_SIMPLE = re.compile(
    rb"""
    (?P<kw>\bif\b) \s* \(\s*(?P<lit>"""+TRUE+b"""|"""+FALSE+b""")\s*\)\s*
    (?P<tb>\{\s*(?P<then>[^{}]*?)\s*\})
    (?:\s*else\s+(?!if)(?P<eb>\{\s*(?P<els>[^{}]*?)\s*\}))?
    (?!\s*else\s+if)
    """,
    re.X
)

class DeadcodeRedundantConditionRule:
    """Constant-fold trivial boolean expressions and remove dead branches when structurally safe."""
    
    meta = RuleMeta(
        id="deadcode.redundant_condition",
        category="deadcode",
        tier=0,  # Syntax only
        priority="P1",
        autofix_safety="safe",
        description="Constant-fold trivial boolean expressions and remove dead branches when structurally safe.",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"]
    )

    requires = Requires(
        raw_text=True,
        syntax=True,
        scopes=False,
        project_graph=False
    )

    def visit(self, ctx: RuleContext) -> List[Finding]:
        """Find redundant conditions in the file."""
        findings = []
        
        # Basic language check using file extension
        supported_extensions = {
            'py': 'python', 'ts': 'typescript', 'js': 'javascript', 
            'go': 'go', 'java': 'java', 'cpp': 'cpp', 'c': 'c', 
            'cs': 'csharp', 'rb': 'ruby', 'rs': 'rust', 'swift': 'swift'
        }
        
        file_ext = ctx.file_path.split('.')[-1].lower() if '.' in ctx.file_path else ''
        language = supported_extensions.get(file_ext, 'unknown')
        
        if language not in self.meta.langs:
            return findings

        b = ctx.text.encode('utf-8')  # bytes
        edits = []

        # 1) Boolean ops
        for pat, keep in PAT_BOOL_OPS:
            for m in pat.finditer(b):
                start, end = m.span()
                repl = m.group(keep)
                # Trim surrounding whitespace if it becomes parenthesized '() && true' etc. Keep exact replacement span.
                edits.append((start, end, repl))

        # 2) Ternary (C-like)
        if language != 'python':  # Python doesn't use ? : ternary
            for m in PAT_TERNARY.finditer(b):
                start, end = m.span()
                cond = m.group("cond").lower()
                repl = m.group("t") if cond in (b"true", b"True") else m.group("f")
                edits.append((start, end, repl))

        # 3) Python conditional expression
        if language == 'python':
            for m in PAT_PY_IFEXPR.finditer(b):
                start, end = m.span()
                cond = m.group("cond").lower()
                repl = m.group("t") if cond in (b"true", b"True") else m.group("f")
                edits.append((start, end, repl))

        # 4) Simple if/else brace blocks (exclude Python - uses indentation)
        if language != 'python':
            for m in PAT_IF_SIMPLE.finditer(b):
                start, end = m.span()
                lit = m.group("lit").lower()
                then_block = m.group("tb")
                else_block = m.group("eb")
                then_inner = m.group("then")
                else_inner = m.group("els") if else_block else None

                if lit in (b"true", b"True"):
                    # Keep then branch body; if else exists, drop it.
                    repl = then_inner
                else:
                    # false
                    if else_inner is not None:
                        repl = else_inner
                    else:
                        # if(false){...} with no else -> delete entirely
                        repl = b""
                edits.append((start, end, repl))

        if not edits:
            return findings

        # Merge edits (non-overlapping by construction; sort ascending)
        edits.sort(key=lambda e: e[0])
        # Collapse overlapping/adjacent defensively
        merged = []
        for s, e, r in edits:
            if not merged or s >= merged[-1][1]:
                merged.append([s, e, r])
            else:
                # overlap: prefer later/larger span → extend end & replacement to last (keep last winner)
                merged[-1][1] = max(merged[-1][1], e)
                merged[-1][2] = r

        # Create Edit objects for autofix
        autofix_edits = []
        for s, e, r in merged:
            autofix_edits.append(Edit(
                start_byte=s,
                end_byte=e,
                replacement=self._clean_bytes(r)
            ))

        # Create a single finding with all the edits
        finding = Finding(
            rule=self.meta.id,
            message=f"Redundant boolean condition(s) simplified ({len(merged)} change{'s' if len(merged) != 1 else ''}).",
            file=ctx.file_path,
            start_byte=merged[0][0],
            end_byte=merged[-1][1],
            severity="warning",
            autofix=autofix_edits
        )
        findings.append(finding)
        
        return findings

    def _clean_bytes(self, bts):
        """Ensure bytes→str decoding for edit API."""
        if isinstance(bts, bytes):
            return bts.decode("utf-8", "ignore")
        return bts


# Register the rule
try:
    from ..engine.registry import register_rule
    from . import register
    register_rule(DeadcodeRedundantConditionRule())  # Global registry
    register(DeadcodeRedundantConditionRule())       # Local RULES list
except ImportError:
    from engine.registry import register_rule
    from rules import register
    register_rule(DeadcodeRedundantConditionRule())  # Global registry
    register(DeadcodeRedundantConditionRule())       # Local RULES list


