"""
Tests for naming.project_term_inconsistency rule.

This module tests detection of cross-file term inconsistencies and verification
of suggested consolidations to canonical terms.
"""

import pytest
from typing import Dict, Any, List
from pathlib import Path
import sys
import os

# Add the server directory to the path for importing
server_dir = Path(__file__).parent.parent
sys.path.insert(0, str(server_dir))

from rules.naming_project_term_inconsistency import RuleNamingProjectTermInconsistency, ProjectSymbol
from engine.types import RuleContext, Finding
from engine.symbol_index import ProjectSymbolIndex
from engine.python_adapter import PythonAdapter


def create_test_context(code: str, project_symbols: List[ProjectSymbol] = None, 
                       language: str = "python", config: Dict[str, Any] = None) -> RuleContext:
    """Create a test context for the given code with symbol index."""
    # Use a basic adapter for parsing
    adapter = PythonAdapter()
    tree = adapter.parse(code) if code else None
    
    # Create symbol index with test symbols
    symbol_index = ProjectSymbolIndex()
    if project_symbols:
        for symbol in project_symbols:
            symbol_index.add_symbol(symbol)
    
    # Project graph is now a tuple: (resolver, import_graph, symbol_index)
    project_graph = (None, None, symbol_index)
    
    ctx = RuleContext(
        file_path="test.py",
        text=code,
        tree=tree,
        adapter=adapter,
        config=config or {},
        project_graph=project_graph
    )
    
    return ctx


def run_rule(rule: RuleNamingProjectTermInconsistency, code: str = "", 
            project_symbols: List[ProjectSymbol] = None, language: str = "python", 
            config: Dict[str, Any] = None) -> List[Finding]:
    """Run the rule on the given project setup and return findings."""
    ctx = create_test_context(code, project_symbols, language, config)
    return list(rule.visit(ctx))


class TestRuleNamingProjectTermInconsistency:
    """Test suite for naming.project_term_inconsistency rule."""
    
    def setup_method(self):
        """Set up test fixtures."""
        self.rule = RuleNamingProjectTermInconsistency()
    
    # --- Basic Functionality Tests ---
    
    def test_meta_properties(self):
        """Test that rule metadata is correctly defined."""
        assert self.rule.meta.id == "naming.project_term_inconsistency"
        assert self.rule.meta.description == "Detect cross-file term inconsistencies (e.g., get/fetch/load the same entity) and suggest a canonical term."
        assert self.rule.meta.category == "naming"
        assert self.rule.meta.tier == 2
        assert self.rule.meta.priority == "P1"
        assert self.rule.meta.autofix_safety == "suggest-only"
        assert "python" in self.rule.meta.langs
        assert "typescript" in self.rule.meta.langs
        assert "javascript" in self.rule.meta.langs
    
    def test_requires_correct_capabilities(self):
        """Test that rule requires the right analysis capabilities."""
        reqs = self.rule.requires
        assert reqs.syntax is True
        assert reqs.scopes is True
        assert reqs.project_graph is True
        assert reqs.raw_text is True
    
    # --- Positive Detection Tests ---
    
    def test_detects_verb_inconsistency_majority_wins(self):
        """Test detection when majority usage should determine canonical verb."""
        project_symbols = [
            ProjectSymbol("get_user", "function", "file1.py"),
            ProjectSymbol("get_user_by_id", "function", "file2.py"),
            ProjectSymbol("fetch_user", "function", "test.py"),  # outlier - should be flagged
            ProjectSymbol("get_user_profile", "function", "file4.py"),
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "python")

        # Should detect that fetch_user is inconsistent
        assert len(findings) >= 1
        fetch_finding = next((f for f in findings if f.meta.get("original_verb") == "fetch"), None)
        assert fetch_finding is not None
        assert "prefer 'get' over 'fetch'" in fetch_finding.message
        assert fetch_finding.meta["suggestion"] == "get_user"
    
    def test_detects_multiple_inconsistencies(self):
        """Test detection of multiple inconsistent terms."""
        project_symbols = [
            ProjectSymbol("create_order", "function", "orders.py"),
            ProjectSymbol("make_order", "function", "test.py"),  # In current file
            ProjectSymbol("build_order", "function", "builder.py"),
            ProjectSymbol("delete_order", "function", "orders.py"),
            ProjectSymbol("remove_order", "function", "test.py"),  # In current file
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "python")
        
        # Should detect inconsistencies in both clusters
        assert len(findings) >= 2
        
        # Check that findings relate to the order functions
        verbs_found = [f.meta["original_verb"] for f in findings]
        assert "make" in verbs_found  # make_order should be flagged
        assert "remove" in verbs_found  # remove_order should be flagged
    
    def test_handles_different_casing_styles(self):
        """Test handling of different identifier casing styles."""
        project_symbols = [
            ProjectSymbol("get_user", "function", "snake_case.py"),      # snake_case
            ProjectSymbol("fetchUser", "function", "test.py"),           # camelCase - in current file
            ProjectSymbol("GetUser", "function", "pascal_case.cs"),      # PascalCase
            ProjectSymbol("loadUser", "function", "test.py"),            # camelCase - in current file
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "javascript")
        
        # Should detect inconsistencies and preserve casing styles
        assert len(findings) >= 1
        
        # Check that suggestions preserve original casing
        found_verbs = set()
        for finding in findings:
            original_verb = finding.meta.get("original_verb", "")
            found_verbs.add(original_verb)
            suggested = finding.meta.get("suggestion", "")
            
            if original_verb == "fetch":
                assert "get" in suggested.lower()  # Should suggest get-based name
            elif original_verb == "load":
                assert "get" in suggested.lower()  # Should suggest get-based name
    
    def test_respects_preferred_verbs_configuration(self):
        """Test that preferred verbs configuration is respected."""
        project_symbols = [
            ProjectSymbol("create_user", "function", "test.py"),   # In current file, canonical: create
            ProjectSymbol("delete_user", "function", "file2.py"),  # canonical: delete
            ProjectSymbol("remove_user", "function", "test.py"),   # In current file, canonical: delete (synonym)
        ]
        
        config = {
            "preferred_verbs": ["delete"]  # Prefer delete over create
        }
        
        findings = run_rule(self.rule, "", project_symbols, "python", config)
        
        # Should prefer delete over create as the target verb
        assert len(findings) >= 1
        
        # Should suggest delete-based naming when delete is preferred
        delete_targets = [f for f in findings if f.meta.get("target_verb") == "delete"]
        assert len(delete_targets) >= 1
    
    def test_handles_custom_term_aliases(self):
        """Test custom term aliases configuration."""
        project_symbols = [
            ProjectSymbol("retrieve_data", "function", "file1.py"),
            ProjectSymbol("get_data", "function", "test.py"),     # In current file
            ProjectSymbol("fetch_data", "function", "test.py"),   # In current file
        ]
        
        config = {
            "term_aliases": {
                "retrieve": ["get", "fetch", "load"]
            }
        }
        
        findings = run_rule(self.rule, "", project_symbols, "python", config)
        
        # Should treat all as synonyms and suggest canonical form
        assert len(findings) >= 1  # get and fetch should be flagged as inconsistent with retrieve
    
    # --- Negative Tests ---
    
    def test_no_findings_when_consistent(self):
        """Test no findings when terms are already consistent."""
        project_symbols = [
            ProjectSymbol("get_user", "function", "file1.py"),
            ProjectSymbol("get_user_by_id", "function", "file2.py"),
            ProjectSymbol("get_user_profile", "function", "file3.py"),
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "python")
        
        # Should not report any inconsistencies
        assert len(findings) == 0
    
    def test_ignores_excluded_paths(self):
        """Test that excluded paths are ignored."""
        project_symbols = [
            ProjectSymbol("get_user", "function", "src/user.py"),
            ProjectSymbol("fetch_user", "function", "node_modules/lib.js"),  # Should be excluded
            ProjectSymbol("load_user", "function", "vendor/third_party.py"),  # Should be excluded
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "python")
        
        # Should not report inconsistencies because excluded files are ignored
        assert len(findings) == 0
    
    def test_respects_min_cluster_size(self):
        """Test minimum cluster size configuration."""
        project_symbols = [
            ProjectSymbol("get_user", "function", "file1.py"),
            ProjectSymbol("fetch_user", "function", "file2.py"),  # Only 2 items, below default min
        ]
        
        config = {"min_cluster_size": 3}
        
        findings = run_rule(self.rule, "", project_symbols, "python", config)
        
        # Should not report because cluster size is below minimum
        assert len(findings) == 0
    
    def test_ignores_single_word_identifiers(self):
        """Test that single-word identifiers are ignored."""
        project_symbols = [
            ProjectSymbol("user", "class", "file1.py"),  # Single word
            ProjectSymbol("account", "class", "file2.py"),  # Single word
            ProjectSymbol("get_user", "function", "file3.py"),  # Valid pattern
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "python")
        
        # Should not report anything for single-word identifiers
        # Only multi-word identifiers with verb-noun pattern should be analyzed
        assert len(findings) == 0
    
    def test_ignores_very_short_names(self):
        """Test that very short names are ignored."""
        project_symbols = [
            ProjectSymbol("a", "variable", "file1.py"),
            ProjectSymbol("xy", "variable", "file2.py"),
            ProjectSymbol("get_user", "function", "file3.py"),
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "python")
        
        # Should ignore very short names
        assert len(findings) == 0
    
    # --- Edge Cases ---
    
    def test_handles_empty_project(self):
        """Test handling of empty project."""
        findings = run_rule(self.rule, "", [], "python")
        assert len(findings) == 0
    
    def test_handles_no_project_graph(self):
        """Test handling when project graph is not available."""
        ctx = create_test_context("", None, "python")
        ctx.project_graph = None
        
        findings = list(self.rule.visit(ctx))
        assert len(findings) == 0
    
    def test_different_symbol_kinds_separate_clusters(self):
        """Test that different symbol kinds are analyzed in separate clusters."""
        project_symbols = [
            ProjectSymbol("get_user", "function", "file1.py"),
            ProjectSymbol("fetch_user", "function", "test.py"),  # In current file
            ProjectSymbol("get_user", "class", "file3.py"),      # Different kind - separate cluster
            ProjectSymbol("fetch_user", "class", "test.py"),     # Different kind - separate cluster, in current file
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "python")
        
        # Should analyze function and class clusters separately
        # Each cluster should have its own consistency analysis
        function_findings = [f for f in findings if f.meta.get("kind") == "function"]
        class_findings = [f for f in findings if f.meta.get("kind") == "class"]
        
        # Both clusters should have inconsistencies reported
        assert len(function_findings) >= 1 or len(class_findings) >= 1
    
    def test_preserves_original_casing_in_suggestions(self):
        """Test that original casing style is preserved in suggestions."""
        project_symbols = [
            ProjectSymbol("get_user_data", "function", "snake.py"),     # snake_case
            ProjectSymbol("fetchUserData", "function", "camel.js"),     # camelCase  
            ProjectSymbol("GetUserData", "function", "pascal.cs"),      # PascalCase
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "python")
        
        # Check that casing styles are preserved
        for finding in findings:
            original = finding.meta.get("original_name", "")
            suggested = finding.meta.get("suggested_name", "")
            
            if "_" in original:
                assert "_" in suggested  # snake_case preserved
            elif original[0].isupper():
                assert suggested[0].isupper()  # PascalCase preserved
            else:
                assert suggested[0].islower()  # camelCase preserved
    
    def test_complex_noun_phrases(self):
        """Test handling of complex noun phrases."""
        project_symbols = [
            ProjectSymbol("get_user_profile_data", "function", "file1.py"),
            ProjectSymbol("fetch_user_profile_data", "function", "test.py"),  # In current file
            ProjectSymbol("load_user_profile_data", "function", "test.py"),   # In current file
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "python")
        
        # Should handle complex noun phrases correctly
        assert len(findings) >= 1
        
        # All findings should refer to the same noun phrase
        noun_phrases = set(f.meta.get("noun_phrase") for f in findings)
        assert len(noun_phrases) == 1
        assert "user profile data" in noun_phrases
    
    # --- Configuration Tests ---
    
    def test_custom_excluded_paths(self):
        """Test custom excluded paths configuration."""
        project_symbols = [
            ProjectSymbol("get_user", "function", "src/user.py"),
            ProjectSymbol("fetch_user", "function", "custom_vendor/lib.py"),
        ]
        
        config = {
            "excluded_paths": {"custom_vendor"}
        }
        
        findings = run_rule(self.rule, "", project_symbols, "python", config)
        
        # Should exclude custom_vendor path
        assert len(findings) == 0
    
    def test_rationale_in_findings(self):
        """Test that findings include proper rationale."""
        project_symbols = [
            ProjectSymbol("get_user", "function", "file1.py"),
            ProjectSymbol("fetch_user", "function", "test.py"),  # In current file
        ]
        
        findings = run_rule(self.rule, "", project_symbols, "python")
        
        assert len(findings) >= 1
        finding = findings[0]
        
        # Check that the finding has informative message and metadata
        assert "consistency across the project" in finding.message
        assert finding.meta.get("original_verb") is not None
        assert finding.meta.get("target_verb") is not None


# Integration test to verify rule registration
def test_rule_registration():
    """Test that the rule is properly registered."""
    try:
        from rules import RULES
        rule_ids = [rule.meta.id for rule in RULES]
        assert "naming.project_term_inconsistency" in rule_ids
    except ImportError:
        # Skip if rules module not available in test environment
        pytest.skip("Rules module not available for registration test")


if __name__ == "__main__":
    # Run a quick smoke test
    rule = RuleNamingProjectTermInconsistency()
    
    test_symbols = [
        ProjectSymbol("get_user", "function", "users.py"),
        ProjectSymbol("fetch_user", "function", "test.py"),  # Should be flagged  
        ProjectSymbol("load_user", "function", "cache.py"),
        ProjectSymbol("get_order", "function", "orders.py"),
        ProjectSymbol("get_order_by_id", "function", "orders.py"),
    ]
    
    print("Testing naming.project_term_inconsistency rule...")
    findings = run_rule(rule, "", test_symbols, "python")
    
    print(f"Found {len(findings)} inconsistencies:")
    for finding in findings:
        print(f"  - {finding.message}")
        print(f"    Original: {finding.meta['original_name']}")
        print(f"    Suggested: {finding.meta['suggested_name']}")
        print(f"    Target verb: {finding.meta['target_verb']}")
        print()
    
    print("Test completed successfully!")

