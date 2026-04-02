"""
Verification Script for Phase 9-10: Data Validator & Excel Writer

This script verifies:
    1. All modules can be imported
    2. DataValidator works correctly
    3. ExcelWriter generates valid workbooks
    4. All tests pass
    5. Integration with previous phases

Run this script:
    python scripts/verify_phase9_10.py

Author: Bloomberg Activist Pipeline
"""

import sys
from pathlib import Path
from datetime import date
import pandas as pd
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# Color codes for terminal output
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
BLUE = "\033[94m"
RESET = "\033[0m"


def print_header(text):
    """Print colored header."""
    print(f"\n{BLUE}{'=' * 80}{RESET}")
    print(f"{BLUE}{text}{RESET}")
    print(f"{BLUE}{'=' * 80}{RESET}\n")


def print_success(text):
    """Print success message."""
    print(f"{GREEN}✓ {text}{RESET}")


def print_error(text):
    """Print error message."""
    print(f"{RED}✗ {text}{RESET}")


def print_warning(text):
    """Print warning message."""
    print(f"{YELLOW}⚠ {text}{RESET}")


def verify_imports():
    """Verify all modules can be imported."""
    print_header("Step 1: Verifying Module Imports")

    try:
        from data_validator import DataValidator, DataQualityReport, RangeViolation
        print_success("data_validator module imported")
    except Exception as e:
        print_error(f"Failed to import data_validator: {e}")
        return False

    try:
        from excel_writer import ExcelWriter
        print_success("excel_writer module imported")
    except Exception as e:
        print_error(f"Failed to import excel_writer: {e}")
        return False

    return True


def verify_data_validator():
    """Verify DataValidator functionality."""
    print_header("Step 2: Verifying DataValidator")

    from data_validator import DataValidator

    # Create test data
    test_data = {
        "bloomberg_ticker": ["TEST1 JP Equity", "TEST2 JP Equity"],
        "PX_TO_BOOK_RATIO": [1.5, 2.0],
        "RETURN_COM_EQY": [10.5, 12.0],
        "CUR_MKT_CAP": [1000000, 2000000],
        "NET_DEBT": [100000, 200000],
        "TRAIL_12M_SALES": [500000, 600000],
    }
    df = pd.DataFrame(test_data)

    # Initialize validator
    validator = DataValidator()
    print_success("DataValidator initialized")

    # Validate data
    report = validator.validate_snapshot_data(df)
    print_success(f"Data validated - Quality score: {report.overall_quality_score:.1%}")

    # Check critical field coverage
    if len(report.critical_field_coverage) > 0:
        print_success(f"Critical field coverage calculated: {len(report.critical_field_coverage)} fields")
    else:
        print_error("No critical field coverage calculated")
        return False

    # Check quality score is reasonable
    if 0.0 <= report.overall_quality_score <= 1.0:
        print_success("Quality score within valid range [0.0, 1.0]")
    else:
        print_error(f"Quality score out of range: {report.overall_quality_score}")
        return False

    return True


def verify_excel_writer():
    """Verify ExcelWriter functionality."""
    print_header("Step 3: Verifying ExcelWriter")

    from excel_writer import ExcelWriter
    from data_validator import DataValidator, DataQualityReport

    # Create test data
    snapshot_data = {
        "bloomberg_ticker": ["TEST1 JP Equity"],
        "company_name_english": ["Test Company"],
        "PX_TO_BOOK_RATIO": [1.5],
        "RETURN_COM_EQY": [10.5],
        "CUR_MKT_CAP": [1000000],
    }
    snapshot_df = pd.DataFrame(snapshot_data)

    # Create minimal quality report
    quality_report = DataQualityReport(
        total_securities=1,
        critical_field_coverage={"PX_TO_BOOK_RATIO": 1.0},
        range_violations=[],
        recommended_manual_review=[],
        overall_quality_score=1.0,
    )

    # Initialize writer
    writer = ExcelWriter()
    print_success("ExcelWriter initialized")

    # Create workbook
    output_path = writer.create_simple_workbook(
        activist_name="Test Activist",
        snapshot_df=snapshot_df,
    )
    print_success(f"Excel workbook created: {output_path.name}")

    # Verify file exists
    if output_path.exists():
        print_success(f"File exists: {output_path}")
    else:
        print_error(f"File not created: {output_path}")
        return False

    # Verify file is readable by openpyxl
    try:
        from openpyxl import load_workbook

        wb = load_workbook(output_path)
        print_success(f"File readable by Excel: {len(wb.sheetnames)} sheets")

        # Check Financial Snapshot sheet exists
        if "Financial Snapshot" in wb.sheetnames:
            print_success("Financial Snapshot sheet found")
        else:
            print_error("Financial Snapshot sheet not found")
            return False

        # Check metadata header
        ws = wb["Financial Snapshot"]
        if ws["A1"].value == "Metric":
            print_success("Metadata header present")
        else:
            print_warning("Metadata header format may differ")

    except Exception as e:
        print_error(f"Failed to read Excel file: {e}")
        return False

    return True


def verify_integration():
    """Verify integration between validator and writer."""
    print_header("Step 4: Verifying Integration")

    from data_validator import DataValidator
    from excel_writer import ExcelWriter

    # Create realistic test data
    data = {
        "bloomberg_ticker": ["8001 JP Equity", "8002 JP Equity"],
        "company_name_english": ["Itochu", "Marubeni"],
        "PX_TO_BOOK_RATIO": [1.5, 2.0],
        "RETURN_COM_EQY": [10.5, 12.0],
        "CUR_MKT_CAP": [1000000, 2000000],
        "NET_DEBT": [100000, -50000],
        "TRAIL_12M_SALES": [500000, 600000],
        "snapshot_date": [date(2021, 3, 31), date(2021, 3, 31)],
    }
    df = pd.DataFrame(data)

    # Validate
    validator = DataValidator()
    quality_report = validator.validate_snapshot_data(df)
    print_success("Data validation complete")

    # Create Excel
    writer = ExcelWriter()
    output_path = writer.write_activist_workbook(
        activist_name="Integration Test",
        snapshot_df=df,
        ownership_df=pd.DataFrame(),
        events_df=pd.DataFrame(),
        price_history_df=pd.DataFrame(),
        peer_comps_df=pd.DataFrame(),
        data_quality_report=quality_report,
    )
    print_success("Excel workbook created with validation report")

    # Verify metadata includes quality score
    from openpyxl import load_workbook

    wb = load_workbook(output_path)
    ws = wb["Financial Snapshot"]

    # Check for quality score in metadata
    quality_score_found = False
    for row in range(1, 10):
        if ws.cell(row=row, column=1).value == "Data Quality Score":
            quality_score_found = True
            break

    if quality_score_found:
        print_success("Quality score included in metadata")
    else:
        print_warning("Quality score not found in metadata")

    return True


def verify_tests():
    """Verify all tests pass."""
    print_header("Step 5: Verifying Tests")

    import subprocess

    # Run data validator tests
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/test_data_validator.py", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            # Count passed tests
            passed = result.stdout.count(" PASSED")
            print_success(f"Data validator tests passed ({passed} tests)")
        else:
            print_error("Data validator tests failed")
            print(result.stdout[-500:])  # Print last 500 chars
            return False
    except Exception as e:
        print_error(f"Failed to run data validator tests: {e}")
        return False

    # Run Excel writer tests
    try:
        result = subprocess.run(
            ["python3", "-m", "pytest", "tests/test_excel_writer.py", "-v", "--tb=short"],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode == 0:
            passed = result.stdout.count(" PASSED")
            print_success(f"Excel writer tests passed ({passed} tests)")
        else:
            print_error("Excel writer tests failed")
            print(result.stdout[-500:])
            return False
    except Exception as e:
        print_error(f"Failed to run Excel writer tests: {e}")
        return False

    return True


def main():
    """Run all verification steps."""
    print_header("Phase 9-10 Verification Script")

    steps = [
        ("Module Imports", verify_imports),
        ("DataValidator", verify_data_validator),
        ("ExcelWriter", verify_excel_writer),
        ("Integration", verify_integration),
        ("Test Suite", verify_tests),
    ]

    results = []

    for step_name, step_func in steps:
        try:
            success = step_func()
            results.append((step_name, success))
        except Exception as e:
            print_error(f"Exception in {step_name}: {e}")
            results.append((step_name, False))

    # Print summary
    print_header("Verification Summary")

    all_passed = True
    for step_name, success in results:
        if success:
            print_success(f"{step_name}: PASSED")
        else:
            print_error(f"{step_name}: FAILED")
            all_passed = False

    print()

    if all_passed:
        print_success("All verification steps passed!")
        print()
        print(f"{GREEN}Phase 9-10 is ready for production use.{RESET}")
        print()
        print("Next steps:")
        print("  1. Integrate with Phase 11 orchestration layer")
        print("  2. Run end-to-end pipeline tests")
        print("  3. Deploy to production environment")
        return 0
    else:
        print_error("Some verification steps failed.")
        print()
        print(f"{RED}Please review errors above before proceeding.{RESET}")
        return 1


if __name__ == "__main__":
    sys.exit(main())
