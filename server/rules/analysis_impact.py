"""
Analysis rules for change impact assessment using the dependency graph.

These tier 2 rules demonstrate the power of cross-file dependency tracking to
provide insights about code changes, refactoring safety, and dead code detection.

PERFORMANCE NOTE: These rules must be fast! On large repos (1000+ files), they run
on every file. Key optimizations:
1. Use pre-built indexes (symbol_to_file) instead of iterating all symbols
2. Cache lookups within a file analysis
3. Limit iterations to avoid O(n²) complexity
"""

from typing import Iterator, Set, List, Dict, Any
from engine.types import Rule, RuleMeta, RuleContext, Finding, Requires


class ChangeImpactAnalysisRule(Rule):
    """
    Identify symbols with high change impact in the current file.
    
    This rule analyzes symbols to show how many other parts of the codebase
    would be affected if the symbol is changed or removed. Helps developers
    understand the "blast radius" of potential changes.
    
    PERFORMANCE: O(S) where S is symbols in current file. Uses pre-built index.
    """
    
    meta = RuleMeta(
        id="analysis.change_impact",
        description="Identify symbols with high change impact",
        category="analysis",
        tier=2,
        priority="P2",
        autofix_safety="suggest-only",
        langs=["python", "javascript", "typescript"],
        surface="kb"  # KB-only: powers .aspect/ architecture knowledge, not shown to users
    )
    
    requires = Requires(syntax=True, project_graph=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        # Check if enhanced project graph with dependency tracking is available
        if not isinstance(ctx.project_graph, dict) or 'dependency_graph' not in ctx.project_graph:
            return  # Skip if dependency tracking not enabled
            
        dependency_graph = ctx.project_graph['dependency_graph']
        symbol_index = ctx.project_graph['symbol_index']
        
        # Get impact threshold (default: 5 to reduce noise)
        impact_threshold = ctx.config.get('min_impact_threshold', 5) if isinstance(ctx.config, dict) else 5
        
        # Analyze symbols in current file for impact
        current_symbols = symbol_index.find_by_file(ctx.file_path)
        
        for symbol in current_symbols:
            if symbol.kind not in ['function', 'class', 'method']:
                continue
                
            # Get impacted symbols (O(1) lookup from pre-built graph)
            impacted = dependency_graph.get_impacted_symbols(symbol.qualified_name)
            impact_count = len(impacted)
            
            # Skip low-impact symbols
            if impact_count < impact_threshold:
                continue
            
            # Calculate affected file count from qualified names (no iteration needed)
            # Format: "path/file.py::symbol_name"
            affected_files = set()
            for sym_id in impacted:
                if "::" in sym_id:
                    affected_files.add(sym_id.split("::")[0])
            
            impact_level = self._classify_impact_level(impact_count)
            
            yield Finding(
                rule=self.meta.id,
                message=f"Changes to '{symbol.name}' would affect {impact_count} dependents in {len(affected_files)} files ({impact_level.lower()} impact)",
                file=ctx.file_path,
                start_byte=symbol.start_byte,
                end_byte=symbol.end_byte,
                severity="info",
                meta={
                    "impact_count": impact_count,
                    "impact_level": impact_level,
                    "affected_file_count": len(affected_files),
                    "symbol_kind": symbol.kind,
                    "symbol_name": symbol.name,
                }
            )
    
    def _classify_impact_level(self, impact_count: int) -> str:
        """Classify impact level based on number of dependents"""
        if impact_count > 15:
            return "Critical"
        elif impact_count > 8:
            return "Very high"
        elif impact_count > 5:
            return "High"
        else:
            return "Medium"


class UnusedPublicSymbolRule(Rule):
    """
    Find public symbols that are never used elsewhere in the project.
    
    This rule identifies potentially dead code by finding public functions, classes,
    and methods that have no dependents across the entire codebase.
    
    PERFORMANCE: O(S) where S is symbols in current file. Single lookup per symbol.
    """
    
    meta = RuleMeta(
        id="deadcode.unused_public",
        description="Detect public symbols with no external usage",
        category="deadcode", 
        tier=2,
        priority="P2",
        autofix_safety="suggest-only",
        langs=["python", "javascript", "typescript"],
        surface="kb"
    )
    
    requires = Requires(syntax=True, project_graph=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        # Check if enhanced project graph with dependency tracking is available
        if not isinstance(ctx.project_graph, dict) or 'dependency_graph' not in ctx.project_graph:
            return
            
        dependency_graph = ctx.project_graph['dependency_graph']
        symbol_index = ctx.project_graph['symbol_index']
        
        # Find public symbols in current file
        current_symbols = symbol_index.find_by_file(ctx.file_path)
        
        for symbol in current_symbols:
            if not self._is_public_symbol(symbol):
                continue
                
            # Check if anything depends on this symbol (O(1) lookup)
            dependents = dependency_graph.get_impacted_symbols(symbol.qualified_name)
            
            if len(dependents) == 0:
                confidence = self._assess_confidence(symbol, ctx.file_path)
                
                # Skip low-confidence findings (likely public API components)
                if confidence == "low":
                    continue
                
                yield Finding(
                    rule=self.meta.id,
                    message=f"'{symbol.name}' is exported but never imported elsewhere in the project",
                    file=ctx.file_path,
                    start_byte=symbol.start_byte,
                    end_byte=symbol.end_byte,
                    severity="warning" if confidence == "high" else "info",
                    meta={
                        "symbol_kind": symbol.kind,
                        "symbol_name": symbol.name,
                        "confidence": confidence,
                    }
                )
    
    def _is_public_symbol(self, symbol) -> bool:
        """Check if a symbol is considered public and should be analyzed"""
        return (
            symbol.visibility == 'public' and 
            symbol.kind in ['function', 'class', 'method'] and
            not symbol.name.startswith('_') and  # Skip private symbols
            not symbol.name.startswith('test_') and  # Skip test functions
            not symbol.name in ['main', '__main__', 'setup', 'teardown']  # Skip common entry points
        )
    
    def _assess_confidence(self, symbol, file_path: str) -> str:
        """Assess confidence level that the symbol is truly unused"""
        file_lower = file_path.lower()
        name = symbol.name
        
        # LOW confidence - skip these (re-exports, type definitions)
        # Index/barrel files - these re-export symbols for external consumption
        if file_lower.endswith('/index.ts') or file_lower.endswith('/index.tsx') or \
           file_lower.endswith('/index.js') or file_lower.endswith('\\index.ts') or \
           file_lower.endswith('\\index.tsx') or file_lower.endswith('\\index.js'):
            return "low"
        
        # Type exports (common in .d.ts or interface files)
        if symbol.kind == 'interface' or symbol.kind == 'type':
            return "low"
        
        # MEDIUM confidence - might be intentional
        if (name in ['__init__', '__str__', '__repr__'] or
            name.startswith('__') and name.endswith('__') or
            'api' in file_lower or 'interface' in file_lower or
            'types' in file_lower or 'models' in file_lower):
            return "medium"
        
        # HIGH confidence - likely truly unused
        return "high"


class CriticalDependencyRule(Rule):
    """
    Identify symbols that many others depend on (potential single points of failure).
    
    PERFORMANCE: O(S) where S is symbols in current file. Single lookup per symbol.
    """
    
    meta = RuleMeta(
        id="architecture.critical_dependency",
        description="Identify symbols with many dependents (potential bottlenecks)",
        category="architecture",
        tier=2,
        priority="P2",
        autofix_safety="suggest-only",
        langs=["python", "javascript", "typescript"],
        surface="kb"  # KB-only: powers .aspect/ architecture knowledge, not shown to users
    )
    
    requires = Requires(syntax=True, project_graph=True)
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        # Check if enhanced project graph with dependency tracking is available
        if not isinstance(ctx.project_graph, dict) or 'dependency_graph' not in ctx.project_graph:
            return
            
        dependency_graph = ctx.project_graph['dependency_graph']
        symbol_index = ctx.project_graph['symbol_index']
        
        # Get critical dependency threshold (default: 15 to reduce noise)
        critical_threshold = ctx.config.get('critical_threshold', 15) if isinstance(ctx.config, dict) else 15
        
        current_symbols = symbol_index.find_by_file(ctx.file_path)
        
        for symbol in current_symbols:
            if symbol.kind not in ['function', 'class']:
                continue
                
            # O(1) lookup
            dependents = dependency_graph.get_impacted_symbols(symbol.qualified_name)
            dependent_count = len(dependents)
            
            # Skip non-critical symbols
            if dependent_count < critical_threshold:
                continue
            
            # Count affected files from qualified names (no iteration over all symbols)
            affected_files = set()
            for sym_id in dependents:
                if "::" in sym_id:
                    affected_files.add(sym_id.split("::")[0])
            
            risk_level = self._assess_risk_level(dependent_count)
            
            yield Finding(
                rule=self.meta.id,
                message=f"'{symbol.name}' is used by {dependent_count} other symbols across {len(affected_files)} files—changes here have wide impact",
                file=ctx.file_path,
                start_byte=symbol.start_byte,
                end_byte=symbol.end_byte,
                severity="warning" if risk_level == "critical" else "info",
                meta={
                    "dependent_count": dependent_count,
                    "affected_file_count": len(affected_files),
                    "risk_level": risk_level,
                    "symbol_kind": symbol.kind,
                    "symbol_name": symbol.name,
                }
            )
    
    def _assess_risk_level(self, dependent_count: int) -> str:
        """Assess risk level based on number of dependents"""
        if dependent_count > 30:
            return "critical"
        elif dependent_count > 20:
            return "high"
        else:
            return "medium"


class DependencyCycleImpactRule(Rule):
    """
    Analyze the impact of circular dependencies in the dependency graph.
    
    PERFORMANCE: Limited DFS with max depth and visited set to prevent exponential blowup.
    Only checks cycles up to depth 5 to stay fast.
    """
    
    meta = RuleMeta(
        id="architecture.dependency_cycle_impact",
        description="Analyze impact of circular dependencies",
        category="architecture",
        tier=2,
        priority="P1", 
        autofix_safety="suggest-only",
        langs=["python", "javascript", "typescript"],
        surface="kb"
    )
    
    requires = Requires(syntax=True, project_graph=True)
    
    # Limit cycle detection to prevent exponential blowup
    MAX_CYCLE_DEPTH = 5
    MAX_CYCLES_PER_SYMBOL = 3
    
    def visit(self, ctx: RuleContext) -> Iterator[Finding]:
        # Check if enhanced project graph with dependency tracking is available
        if not isinstance(ctx.project_graph, dict) or 'dependency_graph' not in ctx.project_graph:
            return
            
        dependency_graph = ctx.project_graph['dependency_graph']
        symbol_index = ctx.project_graph['symbol_index']
        
        current_symbols = symbol_index.find_by_file(ctx.file_path)
        
        for symbol in current_symbols:
            if symbol.kind not in ['function', 'class']:
                continue
                
            # Limited cycle detection (O(d^b) where d=depth, b=branching, both bounded)
            cycles = self._find_cycles_limited(symbol.qualified_name, dependency_graph)
            
            if cycles:
                yield Finding(
                    rule=self.meta.id,
                    message=f"'{symbol.name}' is part of a circular dependency ({len(cycles)} cycle{'s' if len(cycles) > 1 else ''} detected)",
                    file=ctx.file_path,
                    start_byte=symbol.start_byte,
                    end_byte=symbol.end_byte,
                    severity="warning",
                    meta={
                        "symbol_name": symbol.name,
                        "cycle_count": len(cycles),
                        "cycles": [self._format_cycle(c) for c in cycles[:3]],
                    }
                )
    
    def _find_cycles_limited(self, start_symbol: str, dependency_graph) -> List[List[str]]:
        """Find cycles involving the symbol with strict limits to prevent exponential blowup."""
        cycles = []
        
        def dfs(current: str, path: List[str], depth: int):
            # Hard limits to prevent exponential blowup
            if depth > self.MAX_CYCLE_DEPTH:
                return
            if len(cycles) >= self.MAX_CYCLES_PER_SYMBOL:
                return
            
            # Check if we've found a cycle back to start
            if current == start_symbol and len(path) > 1:
                cycles.append(path.copy())
                return
            
            # Prevent revisiting within this path (not globally - that's intentional)
            if current in path[1:]:  # Allow start_symbol to appear at end
                return
            
            path.append(current)
            
            # Follow dependencies (outgoing edges)
            dependencies = dependency_graph.get_dependencies_of(current)
            for dep in dependencies:
                if len(cycles) >= self.MAX_CYCLES_PER_SYMBOL:
                    break
                dfs(dep, path, depth + 1)
            
            path.pop()
        
        dfs(start_symbol, [], 0)
        return cycles
    
    def _format_cycle(self, cycle: List[str]) -> str:
        """Format a cycle for display"""
        simplified = []
        for symbol in cycle:
            if "::" in symbol:
                parts = symbol.split("::")
                file_part = parts[0].split("/")[-1] if "/" in parts[0] else parts[0].split("\\")[-1]
                simplified.append(f"{file_part}::{parts[1]}")
            else:
                simplified.append(symbol)
        return " -> ".join(simplified)


# Register all the impact analysis rules
RULES = [
    ChangeImpactAnalysisRule(),
    UnusedPublicSymbolRule(),
    CriticalDependencyRule(),
    DependencyCycleImpactRule()
]


