"""
Rule to detect cross-file term inconsistencies in naming.

This rule analyzes the entire project to identify when the same concept is referred
to with different terms across files (e.g., get_user vs fetch_user vs load_user)
and suggests consolidations to a canonical term.
"""

from typing import Iterator, Dict, Any, Set, List, Tuple, Optional
import re
from collections import defaultdict
import os

try:
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority
    from engine.scopes import ScopeGraph, Symbol, Scope
except ImportError:
    # Fallback for direct execution
    import sys
    import os
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..'))
    from engine.types import Rule, RuleMeta, Requires, RuleContext, Finding, Edit, Tier, Priority
    from engine.scopes import ScopeGraph, Symbol, Scope


# Default verb synonyms for common patterns
# CONSERVATIVE: Only truly synonymous verbs that mean the same thing
# Intentionally narrow to reduce false positives
DEFAULT_VERB_SYNONYMS = {
    # canonical -> set(synonyms)
    "get": {"fetch", "retrieve"},  # Removed: load (may involve caching), read (implies I/O), pull/obtain/acquire (too generic)
    "create": {"make", "new"},  # Removed: build/construct (imply complex assembly), add/insert (imply collection)
    "update": {"modify", "patch"},  # Removed: edit (UI term), change/set/alter (too generic)
    "delete": {"remove"},  # Removed: rm (abbreviation), destroy/drop/clear/erase (different semantics)
    "save": {"persist", "store"},  # Removed: write (I/O specific), put (REST specific), commit (transaction specific)
    "send": {"dispatch"},  # Removed: post (REST), submit (forms), emit/publish (events/messaging)
}

# Common excluded paths (third-party, vendor, generated code)
DEFAULT_EXCLUDED_PATHS = {
    "node_modules", ".venv", "venv", "env", "vendor", "third_party", 
    "external", "lib", "libs", "dependencies", ".git", "__pycache__",
    "build", "dist", "target", "out", "bin"
}


def _split_identifier(name: str) -> List[str]:
    """
    Split identifier into component words.
    Examples:
    - fooBar -> ["foo", "bar"]
    - FooBar -> ["foo", "bar"] 
    - foo_bar -> ["foo", "bar"]
    - get-user -> ["get", "user"]
    - getUserByEmail -> ["get", "user", "by", "email"]
    """
    if not name:
        return []
    
    # Handle camelCase and PascalCase
    s = re.sub(r"([a-z0-9])([A-Z])", r"\1 \2", name)
    s = re.sub(r"([A-Z]+)([A-Z][a-z])", r"\1 \2", s)
    
    # Split on non-alphanumeric characters and whitespace
    parts = re.split(r"[\W_\s]+", s)
    
    # Clean and normalize
    return [p.lower() for p in parts if p and p.isalpha()]


def _stem_identifier(parts: List[str]) -> Tuple[str, str]:
    """
    Extract verb and noun phrase from identifier parts.
    Returns (verb, noun_phrase) where verb is the first part if it looks like a verb,
    and noun_phrase is the remaining parts joined.
    """
    if not parts:
        return ("", "")
    
    verb = parts[0]
    noun_phrase = " ".join(parts[1:]) if len(parts) > 1 else ""
    
    return (verb, noun_phrase)


def _is_excluded_path(file_path: str, excluded_paths: Set[str]) -> bool:
    """Check if file path should be excluded from analysis."""
    if not file_path:
        return False
    
    path_parts = file_path.replace("\\", "/").split("/")
    return any(part in excluded_paths for part in path_parts)


class ProjectSymbol:
    """Simplified representation of a project symbol for analysis."""
    
    def __init__(self, name: str, kind: str, file_path: str, start_byte: int = 0, end_byte: int = 0, language: str = "python", visibility: str = "public"):
        self.name = name
        self.kind = kind
        self.file_path = file_path
        self.start_byte = start_byte
        self.end_byte = end_byte
        self.language = language
        self.visibility = visibility


# Global cache for project-wide analysis
_PROJECT_ANALYSIS_CACHE = {}


class RuleNamingProjectTermInconsistency(Rule):
    """Rule to detect cross-file term inconsistencies and suggest canonical terms."""
    
    meta = RuleMeta(
        id="naming.project_term_inconsistency",
        description="Detect cross-file term inconsistencies (e.g., get/fetch/load the same entity) and suggest a canonical term.",
        category="naming",
        tier=2,
        priority="P2",
        autofix_safety="suggest-only",
        langs=["python", "typescript", "javascript", "go", "java", "cpp", "c", "csharp", "ruby", "rust", "swift"],
        surface="kb"
    )

    requires = Requires(syntax=True, scopes=True, project_graph=True, raw_text=True)

    def _get_project_cache_key(self, ctx: RuleContext) -> str:
        """Generate a cache key for project-wide analysis."""
        # Use the file path to create a simple cache key
        # In a real implementation, this might include project root, config hash, etc.
        return f"project_term_consistency_{hash(ctx.file_path)}"

    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        """Visit the file and analyze project-wide term consistency."""
        # Check language compatibility
        language = getattr(ctx.adapter, 'language_id', 'unknown')
        if callable(language):

            language = language()

        

        if language not in self.meta.langs:
            return

        # Ensure we have project graph with symbol index
        if not ctx.project_graph:
            return
        
        # Extract symbol index from project graph
        # Project graph can be either a dict (new format) or tuple (legacy format)
        symbol_index = None
        if isinstance(ctx.project_graph, dict):
            symbol_index = ctx.project_graph.get('symbol_index')
        else:
            # Legacy tuple format: (resolver, import_graph, symbol_index)
            try:
                resolver, import_graph, symbol_index = ctx.project_graph
            except (ValueError, TypeError):
                return
        
        if not symbol_index:
            return

        config = ctx.config or {}
        
        # Get configuration
        alias_map = config.get("term_aliases", {})
        preferred_verbs = config.get("preferred_verbs", [])
        min_cluster_size = config.get("min_cluster_size", 3)  # Require at least 3 symbols to form a cluster
        
        # Build verb synonym map
        verb_synonyms = self._build_verb_synonyms(alias_map)
        
        # Get all function/method symbols from the symbol index
        all_symbols = self._get_project_symbols(symbol_index)
        
        # Build clusters by (noun_phrase, kind)
        clusters = self._build_clusters_from_project_symbols(all_symbols, verb_synonyms)
        
        # Analyze clusters and generate findings for current file only
        yield from self._analyze_clusters_for_file(ctx, clusters, preferred_verbs, min_cluster_size)

    def _build_verb_synonyms(self, alias_map: Dict[str, List[str]]) -> Dict[str, Set[str]]:
        """Build the verb synonyms dictionary from config and defaults."""
        verb_synonyms = {}
        
        # Start with defaults
        for canonical, synonyms in DEFAULT_VERB_SYNONYMS.items():
            verb_synonyms[canonical] = set(synonyms)
        
        # Add user-provided aliases
        for canonical, aliases in alias_map.items():
            if isinstance(aliases, (list, set)) and canonical.isalpha():
                if canonical not in verb_synonyms:
                    verb_synonyms[canonical] = set()
                verb_synonyms[canonical].update(alias for alias in aliases if isinstance(alias, str) and alias.isalpha())
        
        return verb_synonyms

    def _get_project_symbols(self, symbol_index) -> List:
        """Get all function and method symbols from the project symbol index."""
        # Import the ProjectSymbol class from the symbol index module
        try:
            from engine.symbol_index import ProjectSymbol as IndexProjectSymbol
        except ImportError:
            # Fallback in case of import issues
            IndexProjectSymbol = object
        
        # Get all function and method symbols
        functions = symbol_index.find_by_kind("function")
        methods = symbol_index.find_by_kind("method")
        
        # Convert to our local ProjectSymbol format for backward compatibility
        symbols = []
        for sym in functions + methods:
            symbols.append(ProjectSymbol(
                name=sym.name,
                kind=sym.kind,
                file_path=sym.file_path,
                start_byte=sym.start_byte,
                end_byte=sym.end_byte
            ))
        
        return symbols

    def _build_clusters_from_project_symbols(self, symbols: List[ProjectSymbol], 
                                           verb_synonyms: Dict[str, Set[str]]) -> Dict[Tuple[str, str], List[Tuple[ProjectSymbol, str, str, str]]]:
        """Build clusters of symbols by (noun_phrase, kind) and normalize verbs."""
        clusters = defaultdict(list)
        
        def get_canonical_verb(verb: str) -> str:
            """Get the canonical form of a verb."""
            for canonical, synonyms in verb_synonyms.items():
                if verb == canonical or verb in synonyms:
                    return canonical
            return verb
        
        for symbol in symbols:
            # Skip dunder methods (e.g., __init__, __str__, __modify_schema__)
            # These are often implementing protocol/interface requirements
            if symbol.name.startswith('__') and symbol.name.endswith('__'):
                continue
            
            # Skip private/internal methods (single underscore prefix)
            if symbol.name.startswith('_') and not symbol.name.startswith('__'):
                continue
            
            parts = _split_identifier(symbol.name)
            if len(parts) < 2:
                continue
            
            verb, noun_phrase = _stem_identifier(parts)
            if not verb or not noun_phrase:
                continue
            
            # Skip very short noun phrases (less meaningful clusters)
            if len(noun_phrase) < 3:
                continue
            
            canonical_verb = get_canonical_verb(verb)
            cluster_key = (noun_phrase, symbol.kind)
            
            clusters[cluster_key].append((symbol, verb, noun_phrase, canonical_verb))
        
        return clusters

    def _analyze_clusters_for_file(self, ctx: RuleContext, 
                                 clusters: Dict[Tuple[str, str], List[Tuple[ProjectSymbol, str, str, str]]],
                                 preferred_verbs: List[str], min_cluster_size: int) -> Iterator[Finding]:
        """Analyze clusters and generate findings for symbols in the current file only."""
        for (noun_phrase, kind), items in clusters.items():
            if len(items) < min_cluster_size:
                continue
            
            # Get unique original verbs in this cluster (for detecting inconsistency)
            original_verbs = set(original_verb for _, original_verb, _, _ in items)
            if len(original_verbs) < 2:
                continue  # No inconsistency at original verb level
            
            # Get unique canonical verbs (for determining target)
            canonical_verbs = set(canonical_verb for _, _, _, canonical_verb in items)
            
            # Select target verb from canonical verbs
            target_verb = self._select_target_verb(canonical_verbs, preferred_verbs, items)
            
            # Count how many symbols use the target verb vs other verbs
            # Only flag if there's a clear majority (>= 2x more uses of target verb)
            target_count = sum(1 for _, orig, _, _ in items if orig == target_verb)
            other_count = len(items) - target_count
            
            # Skip if there's no clear consensus (require target to be used at least 2x more)
            if target_count < other_count * 2:
                continue
            
            # Generate findings for symbols in current file where original verb differs from majority
            for symbol, original_verb, _, canonical_verb in items:
                if symbol.file_path == ctx.file_path and original_verb != target_verb:
                    suggestion = self._generate_suggestion(symbol.name, original_verb, target_verb)
                    
                    yield Finding(
                        rule=self.meta.id,
                        message=f"Inconsistent naming: use '{target_verb}' instead of '{original_verb}' to match the rest of the project.",
                        file=ctx.file_path,
                        start_byte=symbol.start_byte,
                        end_byte=symbol.end_byte,
                        severity="warning",
                        autofix=[] if not suggestion else [Edit(
                            start_byte=symbol.start_byte,
                            end_byte=symbol.end_byte,
                            replacement=suggestion
                        )],
                        meta={
                            "noun_phrase": noun_phrase,
                            "kind": kind,
                            "original_verb": original_verb,
                            "target_verb": target_verb,
                            "original_verbs": sorted(original_verbs),
                            "canonical_verbs": sorted(canonical_verbs),
                            "symbol_count": len(items),
                            "suggestion": suggestion
                        }
                    )

    def _select_target_verb(self, canonical_verbs: Set[str], preferred_verbs: List[str], 
                           items: List[Tuple[ProjectSymbol, str, str, str]]) -> str:
        """Select the target canonical verb for a cluster."""
        # 1. Check for explicitly preferred verbs
        preferred_set = set(preferred_verbs)
        intersection = canonical_verbs & preferred_set
        if intersection:
            # Return the first preferred verb found (in order of preference)
            for pref in preferred_verbs:
                if pref in intersection:
                    return pref
        
        # 2. Use majority rule (most common canonical verb)
        verb_counts = defaultdict(int)
        for _, _, _, canonical_verb in items:
            verb_counts[canonical_verb] += 1
        
        # Sort by count (descending) then alphabetically for tie-breaking
        sorted_verbs = sorted(verb_counts.items(), key=lambda x: (-x[1], x[0]))
        return sorted_verbs[0][0]

    def _generate_suggestion(self, original_name: str, from_verb: str, to_verb: str) -> Optional[str]:
        """Generate a suggested name by replacing the verb while preserving casing style."""
        parts = _split_identifier(original_name)
        if not parts or parts[0] != from_verb.lower():
            return None
        
        # Replace the first part (verb) with the target verb
        parts[0] = to_verb.lower()
        
        # Reassemble preserving original casing style
        if "_" in original_name:
            # snake_case
            return "_".join(parts)
        elif re.match(r"^[A-Z]", original_name):
            # PascalCase
            return "".join(p.capitalize() for p in parts)
        else:
            # camelCase (default)
            return parts[0] + "".join(p.capitalize() for p in parts[1:])


# Register the rule
try:
    from engine.registry import register_rule
    register_rule(RuleNamingProjectTermInconsistency())
except ImportError:
    # For test execution - registry may not be available
    def register_rule(rule):
        pass

# Also add to local RULES list for backward compatibility
try:
    from . import register
    register(RuleNamingProjectTermInconsistency())
except ImportError:
    # Handle case where rules module registration isn't available
    pass


