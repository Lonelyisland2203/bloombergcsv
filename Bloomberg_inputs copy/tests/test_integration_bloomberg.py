"""
Manual Integration Tests for Bloomberg Session Manager

These tests require a LIVE Bloomberg Terminal connection and should be run manually.
They are NOT part of the automated test suite.

Usage:
    1. Ensure Bloomberg Terminal is running and logged in
    2. Run: python tests/test_integration_bloomberg.py
    3. Review output to verify API connectivity and data quality

Author: Bloomberg Activist Pipeline
"""

import sys
from datetime import date, timedelta
from pathlib import Path

import pandas as pd

# Add src to path for imports
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bloomberg_session import BloombergSession, BloombergConnectionError


def test_connection():
    """Test 1: Verify Bloomberg Terminal connection."""
    print("\n" + "=" * 80)
    print("TEST 1: Bloomberg Terminal Connection")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            print("✓ Successfully connected to Bloomberg API")
            print(f"  Host: {session.host}")
            print(f"  Port: {session.port}")
            return True
    except BloombergConnectionError as e:
        print(f"✗ Connection failed: {e}")
        return False
    except ImportError as e:
        print(f"✗ blpapi not installed: {e}")
        return False


def test_reference_data_single_security():
    """Test 2: Retrieve reference data for single Japanese security."""
    print("\n" + "=" * 80)
    print("TEST 2: Reference Data - Single Security")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            # Test with Kawasaki Kisen (9107 JP Equity)
            df = session.send_request(
                securities=["9107 JP Equity"],
                fields=[
                    "PX_TO_BOOK_RATIO",
                    "RETURN_COM_EQY",
                    "CUR_MKT_CAP",
                    "FISCAL_YEAR_END_MONTH_DE"
                ]
            )

            print(f"✓ Retrieved data for 1 security")
            print(f"\nData Preview:")
            print(df.to_string())

            # Validate data
            assert len(df) == 1, "Should return 1 row"
            assert df.iloc[0]["security"] == "9107 JP Equity"
            print("\n✓ Data validation passed")

            # Check field errors
            errors = session.get_field_errors()
            if errors:
                print(f"\n⚠ Field errors detected: {errors}")
            else:
                print("\n✓ No field errors")

            return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_reference_data_multiple_securities():
    """Test 3: Retrieve reference data for multiple Japanese securities."""
    print("\n" + "=" * 80)
    print("TEST 3: Reference Data - Multiple Securities")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            # Test with 3 Effissimo target companies
            securities = [
                "9107 JP Equity",  # Kawasaki Kisen
                "9104 JP Equity",  # Mitsui OSK Lines
                "9101 JP Equity"   # Nippon Yusen
            ]

            df = session.send_request(
                securities=securities,
                fields=[
                    "PX_TO_BOOK_RATIO",
                    "RETURN_COM_EQY",
                    "CUR_MKT_CAP"
                ]
            )

            print(f"✓ Retrieved data for {len(df)} securities")
            print(f"\nData Preview:")
            print(df.to_string())

            # Validate data
            assert len(df) == len(securities), f"Should return {len(securities)} rows"
            print("\n✓ Data validation passed")

            return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_reference_data_with_overrides():
    """Test 4: Retrieve point-in-time data using field overrides."""
    print("\n" + "=" * 80)
    print("TEST 4: Reference Data with Overrides (Point-in-Time)")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            # Test historical snapshot as of 2023-03-31
            df = session.send_request(
                securities=["9107 JP Equity"],
                fields=["PX_TO_BOOK_RATIO", "CUR_MKT_CAP"],
                overrides={"END_DT_OVERRIDE": "20230331"}
            )

            print(f"✓ Retrieved point-in-time data (as of 2023-03-31)")
            print(f"\nData Preview:")
            print(df.to_string())

            # Compare with current data
            df_current = session.send_request(
                securities=["9107 JP Equity"],
                fields=["PX_TO_BOOK_RATIO", "CUR_MKT_CAP"]
            )

            print(f"\n✓ Current data for comparison:")
            print(df_current.to_string())

            return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_bulk_data():
    """Test 5: Retrieve bulk reference data (ownership table)."""
    print("\n" + "=" * 80)
    print("TEST 5: Bulk Reference Data (TOP_20_HOLDERS)")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            df = session.send_bulk_request(
                securities=["9107 JP Equity"],
                field="TOP_20_HOLDERS_PUBLIC_FILINGS"
            )

            print(f"✓ Retrieved {len(df)} ownership records")
            print(f"\nData Preview (top 10 holders):")
            print(df.head(10).to_string())

            # Validate structure
            assert "security" in df.columns, "Should have security column"
            print("\n✓ Data validation passed")

            return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_historical_data():
    """Test 6: Retrieve historical price data."""
    print("\n" + "=" * 80)
    print("TEST 6: Historical Data (Price History)")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            # Get last 30 days of price data
            end_date = date.today()
            start_date = end_date - timedelta(days=30)

            df = session.send_historical_request(
                security="9107 JP Equity",
                fields=["PX_LAST", "PX_VOLUME"],
                start_date=start_date,
                end_date=end_date
            )

            print(f"✓ Retrieved {len(df)} daily records")
            print(f"\nData Preview (last 10 days):")
            print(df.tail(10).to_string())

            # Validate structure
            assert "date" in df.columns, "Should have date column"
            assert "security" in df.columns, "Should have security column"
            assert "PX_LAST" in df.columns, "Should have PX_LAST field"
            print("\n✓ Data validation passed")

            return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_handling_invalid_security():
    """Test 7: Verify graceful handling of invalid security."""
    print("\n" + "=" * 80)
    print("TEST 7: Error Handling - Invalid Security")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            df = session.send_request(
                securities=["INVALID123 JP Equity"],
                fields=["PX_TO_BOOK_RATIO"]
            )

            print(f"✓ Request completed without exception")
            print(f"  Returned {len(df)} rows (expected 0)")

            # Should return empty DataFrame
            assert len(df) == 0, "Invalid security should return empty result"
            print("\n✓ Error handling validated")

            return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def test_error_handling_invalid_field():
    """Test 8: Verify graceful handling of invalid field."""
    print("\n" + "=" * 80)
    print("TEST 8: Error Handling - Invalid Field")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            df = session.send_request(
                securities=["9107 JP Equity"],
                fields=["PX_TO_BOOK_RATIO", "INVALID_FIELD_XYZ"]
            )

            print(f"✓ Request completed without exception")
            print(f"\nData Preview:")
            print(df.to_string())

            # Valid field should have data, invalid field should be None
            assert df.iloc[0]["PX_TO_BOOK_RATIO"] is not None, "Valid field should return data"
            assert df.iloc[0]["INVALID_FIELD_XYZ"] is None, "Invalid field should return None"

            # Check field errors
            errors = session.get_field_errors()
            assert "9107 JP Equity" in errors, "Should track field error"
            assert "INVALID_FIELD_XYZ" in errors["9107 JP Equity"], "Should track specific field"

            print(f"\n✓ Field errors tracked: {errors}")
            print("✓ Error handling validated")

            return True

    except Exception as e:
        print(f"✗ Test failed: {e}")
        import traceback
        traceback.print_exc()
        return False


def run_all_tests():
    """Run all integration tests and report results."""
    print("\n")
    print("*" * 80)
    print("BLOOMBERG SESSION MANAGER - MANUAL INTEGRATION TESTS")
    print("*" * 80)
    print("\nThese tests require Bloomberg Terminal to be running and logged in.")
    print("Tests will verify API connectivity, data retrieval, and error handling.")

    tests = [
        ("Connection Test", test_connection),
        ("Reference Data - Single Security", test_reference_data_single_security),
        ("Reference Data - Multiple Securities", test_reference_data_multiple_securities),
        ("Reference Data with Overrides", test_reference_data_with_overrides),
        ("Bulk Reference Data", test_bulk_data),
        ("Historical Data", test_historical_data),
        ("Error Handling - Invalid Security", test_error_handling_invalid_security),
        ("Error Handling - Invalid Field", test_error_handling_invalid_field)
    ]

    results = []
    for name, test_func in tests:
        try:
            success = test_func()
            results.append((name, success))
        except Exception as e:
            print(f"\n✗ Test '{name}' raised exception: {e}")
            results.append((name, False))

    # Print summary
    print("\n" + "=" * 80)
    print("TEST SUMMARY")
    print("=" * 80)

    passed = sum(1 for _, success in results if success)
    total = len(results)

    for name, success in results:
        status = "✓ PASS" if success else "✗ FAIL"
        print(f"{status:10} {name}")

    print(f"\nResults: {passed}/{total} tests passed")

    if passed == total:
        print("\n✓ All integration tests passed successfully!")
        return 0
    else:
        print(f"\n✗ {total - passed} test(s) failed. Review output above for details.")
        return 1


if __name__ == "__main__":
    exit_code = run_all_tests()
    sys.exit(exit_code)
