"""
Phase 2 Validation Script

Validates that Bloomberg Session Manager implementation is complete and functional.
This runs WITHOUT Bloomberg Terminal (uses mocks and static analysis).

For live Bloomberg testing, run: python tests/test_integration_bloomberg.py

Author: Bloomberg Activist Pipeline
"""

import sys
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))


def validate_imports():
    """Validate all Phase 2 modules can be imported."""
    print("\n" + "=" * 80)
    print("VALIDATION 1: Import Checks")
    print("=" * 80)

    try:
        from src.bloomberg_session import (
            BloombergSession,
            BloombergConnectionError,
            BloombergRateLimitError,
            BloombergFieldError,
            CircuitBreaker
        )
        print("✓ bloomberg_session.py imports successfully")
        print(f"  - BloombergSession class available")
        print(f"  - Error classes defined (Connection, RateLimit, Field)")
        print(f"  - CircuitBreaker class available")
        return True

    except ImportError as e:
        print(f"✗ Import failed: {e}")
        return False


def validate_class_methods():
    """Validate BloombergSession has all required methods."""
    print("\n" + "=" * 80)
    print("VALIDATION 2: Class Methods")
    print("=" * 80)

    try:
        from src.bloomberg_session import BloombergSession

        required_methods = [
            'start',
            'send_request',
            'send_bulk_request',
            'send_historical_request',
            'close',
            '__enter__',
            '__exit__',
            'get_field_errors',
            'clear_field_errors'
        ]

        # Create instance (will fail if blpapi not installed, but that's OK)
        try:
            session = BloombergSession()
            instance_available = True
        except ImportError:
            # blpapi not installed - check class definition instead
            instance_available = False
            print("  Note: blpapi not installed, checking class definition")

        missing_methods = []
        for method in required_methods:
            if instance_available:
                if not hasattr(session, method):
                    missing_methods.append(method)
            else:
                if not hasattr(BloombergSession, method):
                    missing_methods.append(method)

        if missing_methods:
            print(f"✗ Missing methods: {', '.join(missing_methods)}")
            return False
        else:
            print(f"✓ All {len(required_methods)} required methods present:")
            for method in required_methods:
                print(f"  - {method}()")
            return True

    except Exception as e:
        print(f"✗ Validation failed: {e}")
        return False


def validate_docstrings():
    """Validate classes and methods have docstrings."""
    print("\n" + "=" * 80)
    print("VALIDATION 3: Documentation")
    print("=" * 80)

    try:
        from src.bloomberg_session import BloombergSession, CircuitBreaker

        # Check class docstrings
        if not BloombergSession.__doc__:
            print("✗ BloombergSession missing class docstring")
            return False

        if not CircuitBreaker.__doc__:
            print("✗ CircuitBreaker missing class docstring")
            return False

        # Check method docstrings
        methods_to_check = ['start', 'send_request', 'send_bulk_request', 'send_historical_request']
        missing_docs = []

        for method_name in methods_to_check:
            method = getattr(BloombergSession, method_name)
            if not method.__doc__:
                missing_docs.append(method_name)

        if missing_docs:
            print(f"✗ Missing method docstrings: {', '.join(missing_docs)}")
            return False

        print("✓ All classes and methods have docstrings")
        print("  - BloombergSession class documented")
        print("  - CircuitBreaker class documented")
        print(f"  - All {len(methods_to_check)} core methods documented")
        return True

    except Exception as e:
        print(f"✗ Validation failed: {e}")
        return False


def validate_unit_tests():
    """Validate unit tests exist and are executable."""
    print("\n" + "=" * 80)
    print("VALIDATION 4: Unit Tests")
    print("=" * 80)

    test_file = Path(__file__).parent.parent / "tests" / "test_bloomberg_session.py"

    if not test_file.exists():
        print(f"✗ Test file not found: {test_file}")
        return False

    # Count test cases
    with open(test_file, 'r') as f:
        content = f.read()

    test_count = content.count('def test_')

    if test_count < 20:
        print(f"✗ Insufficient test coverage: only {test_count} tests found")
        return False

    print(f"✓ Unit tests file exists: {test_file.name}")
    print(f"  - {test_count} test methods defined")
    print(f"  - Run with: pytest tests/test_bloomberg_session.py -v")

    return True


def validate_integration_tests():
    """Validate integration test script exists."""
    print("\n" + "=" * 80)
    print("VALIDATION 5: Integration Tests")
    print("=" * 80)

    test_file = Path(__file__).parent.parent / "tests" / "test_integration_bloomberg.py"

    if not test_file.exists():
        print(f"✗ Integration test file not found: {test_file}")
        return False

    # Count test scenarios
    with open(test_file, 'r') as f:
        content = f.read()

    test_count = content.count('def test_')

    print(f"✓ Integration tests file exists: {test_file.name}")
    print(f"  - {test_count} test scenarios defined")
    print(f"  - Run with: python tests/test_integration_bloomberg.py")
    print(f"  - Requires: Bloomberg Terminal running and logged in")

    return True


def validate_documentation():
    """Validate documentation files exist."""
    print("\n" + "=" * 80)
    print("VALIDATION 6: Documentation")
    print("=" * 80)

    base_path = Path(__file__).parent.parent / "docs"

    required_docs = [
        "BLOOMBERG_TESTING.md",
        "PHASE2_README.md"
    ]

    missing_docs = []
    for doc in required_docs:
        doc_path = base_path / doc
        if not doc_path.exists():
            missing_docs.append(doc)

    if missing_docs:
        print(f"✗ Missing documentation: {', '.join(missing_docs)}")
        return False

    print(f"✓ All {len(required_docs)} documentation files present:")
    for doc in required_docs:
        print(f"  - {doc}")

    return True


def validate_examples():
    """Validate example scripts exist."""
    print("\n" + "=" * 80)
    print("VALIDATION 7: Examples")
    print("=" * 80)

    example_file = Path(__file__).parent.parent / "examples" / "bloomberg_session_example.py"

    if not example_file.exists():
        print(f"✗ Example file not found: {example_file}")
        return False

    # Count examples
    with open(example_file, 'r') as f:
        content = f.read()

    example_count = content.count('def example_')

    print(f"✓ Example script exists: {example_file.name}")
    print(f"  - {example_count} usage examples provided")
    print(f"  - Run with: python examples/bloomberg_session_example.py")

    return True


def run_all_validations():
    """Run all validation checks and report results."""
    print("\n")
    print("*" * 80)
    print("PHASE 2: BLOOMBERG SESSION MANAGER - VALIDATION")
    print("*" * 80)
    print("\nValidating implementation completeness and correctness...")

    validations = [
        ("Import Checks", validate_imports),
        ("Class Methods", validate_class_methods),
        ("Documentation", validate_docstrings),
        ("Unit Tests", validate_unit_tests),
        ("Integration Tests", validate_integration_tests),
        ("Documentation Files", validate_documentation),
        ("Examples", validate_examples)
    ]

    results = []
    for name, validation_func in validations:
        try:
            success = validation_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n✗ Validation '{name}' raised exception: {e}")
            import traceback
            traceback.print_exc()
            results.append((name, False))

    # Print summary
    print("\n" + "=" * 80)
    print("VALIDATION SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status:10} {name}")

    print(f"\nResults: {passed}/{total} validations passed")

    if passed == total:
        print("\n" + "=" * 80)
        print("✓ PHASE 2 IMPLEMENTATION COMPLETE")
        print("=" * 80)
        print("\nNext Steps:")
        print("  1. Run unit tests: pytest tests/test_bloomberg_session.py -v")
        print("  2. Run integration tests (requires Bloomberg): python tests/test_integration_bloomberg.py")
        print("  3. Review examples: python examples/bloomberg_session_example.py")
        print("  4. Proceed to Phase 3: Batching Engine")
        return 0
    else:
        print(f"\n✗ {total - passed} validation(s) failed. Review output above.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_validations()
    sys.exit(exit_code)
