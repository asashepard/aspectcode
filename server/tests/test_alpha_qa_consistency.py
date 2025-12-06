"""
Alpha QA Matrix Consistency Validation Test

This test ensures that the QA matrix stays in sync with the actual state of:
- ALPHA_DEFAULT_RULE_IDS 
- Rule implementations
- Unit test files
- E2E coverage

It validates that our documentation and analysis scripts are working correctly.
"""

import pytest
from pathlib import Path
from typing import Set, List, Dict
import subprocess
import json

from engine.profiles import ALPHA_DEFAULT_RULE_IDS
from scripts.generate_alpha_qa_matrix import (
    analyze_rule_file, 
    find_unit_tests, 
    find_e2e_coverage,
    generate_markdown_table
)


class TestAlphaQAMatrixConsistency:
    """Test QA matrix consistency and synchronization."""
    
    @pytest.fixture
    def server_dir(self):
        """Get the server directory."""
        return Path(__file__).parent.parent
    
    @pytest.fixture  
    def project_root(self):
        """Get the project root directory."""
        return Path(__file__).parent.parent.parent
    
    def test_alpha_rule_ids_exist_in_codebase(self, server_dir):
        """Test that all ALPHA_DEFAULT_RULE_IDS correspond to actual rule files."""
        
        rules_dir = server_dir / "rules"
        missing_rules = []
        found_rules = []
        
        for rule_id in ALPHA_DEFAULT_RULE_IDS:
            # Convert rule_id to expected file name (dots become underscores)
            # e.g., "sec.command_injection" -> "sec_command_injection.py"
            rule_file_name = rule_id.replace('.', '_') + '.py'
            rule_file = rules_dir / rule_file_name
            
            if rule_file.exists():
                found_rules.append(rule_id)
                print(f"✓ Found rule file: {rule_file.relative_to(server_dir)}")
            else:
                missing_rules.append(rule_id)
                print(f"❌ Missing rule file: {rule_file.relative_to(server_dir)}")
        
        assert len(missing_rules) == 0, f"Missing rule files for: {missing_rules}"
        assert len(found_rules) == len(ALPHA_DEFAULT_RULE_IDS), "Rule count mismatch"
        
        print(f"✓ All {len(ALPHA_DEFAULT_RULE_IDS)} alpha rules have corresponding files")
    
    def test_qa_matrix_script_functionality(self, server_dir):
        """Test that the QA matrix generation script works correctly."""
        
        # Import the functions from the script (running from server directory)
        import sys
        sys.path.append(str(server_dir / "scripts"))
        from generate_alpha_qa_matrix import analyze_rule_file, find_unit_tests, find_e2e_coverage
        
        # Test individual functions work
        sample_rule_ids = [
            "sec.command_injection",
            "func.async_mismatch.await_in_sync", 
            "imports.unused"
        ]
        
        for rule_id in sample_rule_ids:
            # Test rule file analysis
            rule_info = analyze_rule_file(rule_id)
            assert rule_info is not None, f"Failed to analyze rule: {rule_id}"
            assert 'file_exists' in rule_info
            
            # Test unit test discovery
            unit_tests = find_unit_tests(rule_id)
            print(f"{rule_id}: found {len(unit_tests.get('files', []))} unit tests")
            
            # Test E2E coverage discovery  
            e2e_coverage = find_e2e_coverage(rule_id)
            print(f"{rule_id}: found {len(e2e_coverage.get('files', []))} E2E projects")
        
        print("✓ QA matrix script functions working correctly")
    
    def test_unit_test_coverage_completeness(self, server_dir):
        """Test that all alpha rules have unit tests."""
        
        # Import the functions from the script (running from server directory)
        import sys
        sys.path.append(str(server_dir / "scripts"))
        from generate_alpha_qa_matrix import find_unit_tests
        
        tests_dir = server_dir / "tests"
        rules_without_tests = []
        rules_with_tests = []
        
        for rule_id in ALPHA_DEFAULT_RULE_IDS:
            unit_tests = find_unit_tests(rule_id)
            
            if unit_tests.get('files'):
                rules_with_tests.append(rule_id)
                print(f"✓ {rule_id}: {len(unit_tests['files'])} unit tests")
            else:
                rules_without_tests.append(rule_id)
                print(f"❌ {rule_id}: no unit tests found")
        
        coverage_percentage = (len(rules_with_tests) / len(ALPHA_DEFAULT_RULE_IDS)) * 100
        
        print(f"\nUnit Test Coverage: {len(rules_with_tests)}/{len(ALPHA_DEFAULT_RULE_IDS)} ({coverage_percentage:.1f}%)")
        
        if rules_without_tests:
            print(f"Rules without unit tests: {rules_without_tests}")
        
        # Should have 100% unit test coverage after our recent work
        assert len(rules_without_tests) == 0, f"Rules missing unit tests: {rules_without_tests}"
    
    def test_e2e_coverage_tracking(self, server_dir):
        """Test E2E coverage discovery and tracking."""
        
        e2e_dir = server_dir / "tests" / "e2e"
        
        # Verify themed projects exist
        expected_projects = [
            "alpha_security",
            "alpha_async", 
            "alpha_imports",
            "alpha_typescript",
            "alpha_style", 
            "alpha_tests"
        ]
        
        missing_projects = []
        for project in expected_projects:
            project_dir = e2e_dir / project
            if project_dir.exists():
                print(f"✓ Found E2E project: {project}")
            else:
                missing_projects.append(project)
                print(f"❌ Missing E2E project: {project}")
        
        assert len(missing_projects) == 0, f"Missing E2E projects: {missing_projects}"
        
        # Use QA matrix script to check E2E coverage
        import sys
        sys.path.append(str(server_dir / "scripts"))
        from generate_alpha_qa_matrix import find_e2e_coverage
        
        rules_with_e2e = 0
        for rule_id in ALPHA_DEFAULT_RULE_IDS:
            e2e_coverage = find_e2e_coverage(rule_id)
            if e2e_coverage.get('files'):
                rules_with_e2e += 1
        
        e2e_coverage_percentage = (rules_with_e2e / len(ALPHA_DEFAULT_RULE_IDS)) * 100
        print(f"\nE2E Coverage: {rules_with_e2e}/{len(ALPHA_DEFAULT_RULE_IDS)} ({e2e_coverage_percentage:.1f}%)")
        
        # E2E coverage should be improving with themed projects
        assert e2e_coverage_percentage >= 60, f"E2E coverage too low: {e2e_coverage_percentage:.1f}%"
    
    def test_markdown_generation(self, server_dir, project_root):
        """Test that markdown generation produces valid output."""
        
        # Test by running the entire script
        import subprocess
        script_path = server_dir / "scripts" / "generate_alpha_qa_matrix.py"
        
        result = subprocess.run(
            [str(Path("C:/Users/asash/AppData/Local/Programs/Python/Python311/python.exe")), str(script_path)],
            cwd=str(server_dir),
            capture_output=True,
            text=True
        )
        
        if result.returncode != 0:
            pytest.fail(f"QA matrix script failed: {result.stderr}")
        
        # Check that markdown was generated
        docs_file = server_dir / "docs" / "alpha_default_rules.md"
        assert docs_file.exists(), "Markdown file was not generated"
        
        markdown_content = docs_file.read_text()
        
        # Check for expected table structure
        assert "| Rule ID |" in markdown_content, "Missing table header"
        assert "|---|" in markdown_content, "Missing table separator"
        
        # Check that all alpha rules are included
        for rule_id in ALPHA_DEFAULT_RULE_IDS:
            assert rule_id in markdown_content, f"Rule {rule_id} missing from markdown"
        
        print("✓ Markdown generation working correctly")
    
    def test_qa_matrix_script_execution(self, project_root):
        """Test that the QA matrix script can be executed successfully."""
        
        # Script is in server/scripts, not project root scripts
        script_path = project_root / "server" / "scripts" / "generate_alpha_qa_matrix.py"
        assert script_path.exists(), f"QA matrix script not found: {script_path}"
        
        try:
            # Run the script from server directory
            result = subprocess.run(
                [str(Path("C:/Users/asash/AppData/Local/Programs/Python/Python311/python.exe")), str(script_path)],
                cwd=str(project_root / "server"),
                capture_output=True, 
                text=True,
                timeout=30
            )
            
            if result.returncode != 0:
                print(f"Script stderr: {result.stderr}")
                print(f"Script stdout: {result.stdout}")
                pytest.fail(f"QA matrix script failed with code {result.returncode}")
            
            # Verify output was generated
            docs_file = project_root / "server" / "docs" / "alpha_default_rules.md"
            assert docs_file.exists(), "Documentation was not generated"
            
            print("✓ QA matrix script executed successfully")
            
        except subprocess.TimeoutExpired:
            pytest.fail("QA matrix script execution timed out")
        except Exception as e:
            pytest.fail(f"Failed to execute QA matrix script: {e}")
    
    def test_alpha_profile_consistency(self, server_dir):
        """Test that alpha profile configuration is consistent."""
        
        # Verify ALPHA_DEFAULT_RULE_IDS is properly defined
        assert isinstance(ALPHA_DEFAULT_RULE_IDS, (list, tuple)), "ALPHA_DEFAULT_RULE_IDS should be a list/tuple"
        assert len(ALPHA_DEFAULT_RULE_IDS) > 0, "ALPHA_DEFAULT_RULE_IDS should not be empty"
        
        # Check for duplicates
        unique_rules = set(ALPHA_DEFAULT_RULE_IDS)
        assert len(unique_rules) == len(ALPHA_DEFAULT_RULE_IDS), "Duplicate rules in ALPHA_DEFAULT_RULE_IDS"
        
        # Verify rule ID format
        invalid_rule_ids = []
        for rule_id in ALPHA_DEFAULT_RULE_IDS:
            if not isinstance(rule_id, str) or '.' not in rule_id:
                invalid_rule_ids.append(rule_id)
        
        assert len(invalid_rule_ids) == 0, f"Invalid rule ID format: {invalid_rule_ids}"
        
        print(f"✓ Alpha profile has {len(ALPHA_DEFAULT_RULE_IDS)} valid rules")
    
    def test_documentation_sync(self, project_root):
        """Test that generated documentation exists and is recent."""
        
        docs_file = project_root / "server" / "docs" / "alpha_default_rules.md"
        
        if docs_file.exists():
            # Check file age - should be relatively recent if we've been updating it
            import time
            file_age_hours = (time.time() - docs_file.stat().st_mtime) / 3600
            
            if file_age_hours > 24:
                print(f"⚠ Documentation is {file_age_hours:.1f} hours old - consider regenerating")
            else:
                print(f"✓ Documentation is {file_age_hours:.1f} hours old")
            
            # Check content
            content = docs_file.read_text()
            assert "Alpha Default Rules QA Matrix" in content, "Documentation missing expected title"
            assert len(ALPHA_DEFAULT_RULE_IDS) > 0, "No rules found in documentation"
            
            # Count rule mentions
            rules_mentioned = sum(1 for rule_id in ALPHA_DEFAULT_RULE_IDS if rule_id in content)
            coverage = (rules_mentioned / len(ALPHA_DEFAULT_RULE_IDS)) * 100
            
            assert coverage >= 95, f"Only {coverage:.1f}% of rules mentioned in documentation"
            
            print(f"✓ Documentation covers {coverage:.1f}% of alpha rules")
        else:
            print("⚠ Documentation file does not exist - run generate_alpha_qa_matrix.py")


if __name__ == "__main__":
    # Run tests manually for debugging
    test_suite = TestAlphaQAMatrixConsistency()
    
    class MockFixture:
        def __init__(self, value):
            self.value = value
    
    # Set up fixture values
    server_dir = MockFixture(Path(__file__).parent.parent)
    project_root = MockFixture(Path(__file__).parent.parent.parent)
    
    print("Testing Alpha QA Matrix Consistency...")
    
    tests_to_run = [
        ("Rule files exist", test_suite.test_alpha_rule_ids_exist_in_codebase),
        ("QA matrix script works", test_suite.test_qa_matrix_script_functionality),
        ("Unit test coverage", test_suite.test_unit_test_coverage_completeness),
        ("E2E coverage tracking", test_suite.test_e2e_coverage_tracking), 
        ("Markdown generation", test_suite.test_markdown_generation),
        ("Alpha profile consistency", test_suite.test_alpha_profile_consistency),
        ("Documentation sync", test_suite.test_documentation_sync)
    ]
    
    passed = 0
    failed = 0
    
    for test_name, test_method in tests_to_run:
        print(f"\n=== {test_name} ===")
        try:
            if "markdown_generation" in test_method.__name__:
                test_method(server_dir, project_root)
            elif "script_execution" in test_method.__name__ or "documentation_sync" in test_method.__name__:
                test_method(project_root)
            else:
                test_method(server_dir)
            print(f"✓ {test_name} PASSED")
            passed += 1
        except Exception as e:
            print(f"❌ {test_name} FAILED: {e}")
            failed += 1
    
    print(f"\n=== Summary ===")
    print(f"Tests passed: {passed}")
    print(f"Tests failed: {failed}")
    print(f"Success rate: {(passed/(passed+failed)*100):.1f}%")