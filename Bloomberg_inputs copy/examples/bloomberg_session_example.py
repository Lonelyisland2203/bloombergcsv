"""
Bloomberg Session Manager - Usage Examples

This script demonstrates how to use the Bloomberg Session Manager
for common data extraction tasks.

Prerequisites:
    - Bloomberg Terminal running and logged in
    - blpapi package installed
    - DAPI service enabled (check DAPI<GO> in Terminal)

Author: Bloomberg Activist Pipeline
"""

import sys
from datetime import date, timedelta
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent))

from src.bloomberg_session import BloombergSession, BloombergConnectionError


def example_1_basic_reference_data():
    """
    Example 1: Retrieve basic reference data for a single security.

    Demonstrates:
        - Context manager usage (automatic cleanup)
        - Simple reference data request
        - DataFrame output
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 1: Basic Reference Data")
    print("=" * 80)

    try:
        # Use context manager for automatic session management
        with BloombergSession() as session:
            df = session.send_request(
                securities=["9107 JP Equity"],  # Kawasaki Kisen
                fields=["PX_TO_BOOK_RATIO", "RETURN_COM_EQY", "CUR_MKT_CAP"]
            )

            print("\nRetrieved Data:")
            print(df.to_string(index=False))

            # Access specific values
            pbr = df.iloc[0]["PX_TO_BOOK_RATIO"]
            roe = df.iloc[0]["RETURN_COM_EQY"]
            print(f"\nKawasaki Kisen: PBR={pbr:.2f}, ROE={roe:.1f}%")

    except BloombergConnectionError as e:
        print(f"\nError: {e}")
        print("Ensure Bloomberg Terminal is running and logged in.")


def example_2_multiple_securities():
    """
    Example 2: Batch request for multiple securities.

    Demonstrates:
        - Efficient batching (single request for multiple securities)
        - Data processing with pandas
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 2: Multiple Securities (Batch Request)")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            # Batch request for 3 shipping companies
            securities = [
                "9107 JP Equity",  # Kawasaki Kisen
                "9104 JP Equity",  # Mitsui OSK Lines
                "9101 JP Equity"   # Nippon Yusen
            ]

            df = session.send_request(
                securities=securities,
                fields=["PX_TO_BOOK_RATIO", "RETURN_COM_EQY", "CUR_MKT_CAP"]
            )

            print("\nShipping Companies Comparison:")
            print(df.to_string(index=False))

            # Find lowest PBR (value opportunity)
            min_pbr_idx = df["PX_TO_BOOK_RATIO"].idxmin()
            print(f"\nLowest PBR: {df.iloc[min_pbr_idx]['security']} "
                  f"(PBR={df.iloc[min_pbr_idx]['PX_TO_BOOK_RATIO']:.2f})")

    except BloombergConnectionError as e:
        print(f"\nError: {e}")


def example_3_point_in_time_data():
    """
    Example 3: Point-in-time data using field overrides.

    Demonstrates:
        - END_DT_OVERRIDE for historical snapshots
        - Comparing current vs historical values
        - Critical for backtesting and analysis
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 3: Point-in-Time Data (Field Overrides)")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            security = "9107 JP Equity"

            # Historical snapshot (as of 2023-03-31)
            df_historical = session.send_request(
                securities=[security],
                fields=["PX_TO_BOOK_RATIO", "CUR_MKT_CAP"],
                overrides={"END_DT_OVERRIDE": "20230331"}
            )

            # Current data
            df_current = session.send_request(
                securities=[security],
                fields=["PX_TO_BOOK_RATIO", "CUR_MKT_CAP"]
            )

            print("\nData as of 2023-03-31:")
            print(df_historical.to_string(index=False))

            print("\nCurrent Data:")
            print(df_current.to_string(index=False))

            # Calculate change
            pbr_change = (
                df_current.iloc[0]["PX_TO_BOOK_RATIO"] -
                df_historical.iloc[0]["PX_TO_BOOK_RATIO"]
            )
            print(f"\nPBR Change: {pbr_change:+.2f}")

    except BloombergConnectionError as e:
        print(f"\nError: {e}")


def example_4_ownership_data():
    """
    Example 4: Bulk data retrieval (ownership table).

    Demonstrates:
        - Bulk reference data requests
        - Long-format DataFrame output
        - Analyzing ownership structure
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 4: Ownership Data (Bulk Request)")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            df = session.send_bulk_request(
                securities=["9107 JP Equity"],
                field="TOP_20_HOLDERS_PUBLIC_FILINGS"
            )

            print(f"\nRetrieved {len(df)} ownership records")
            print("\nTop 5 Holders:")
            # Display first 5 rows with key columns
            cols_to_show = ["security", "Holder Name", "Portfolio % Market Value Held"]
            available_cols = [col for col in cols_to_show if col in df.columns]
            print(df[available_cols].head().to_string(index=False))

            # Calculate institutional ownership
            if "Portfolio % Market Value Held" in df.columns:
                total_ownership = df["Portfolio % Market Value Held"].sum()
                print(f"\nTop 20 Holders Total: {total_ownership:.1f}%")

    except BloombergConnectionError as e:
        print(f"\nError: {e}")


def example_5_historical_prices():
    """
    Example 5: Historical price data (time series).

    Demonstrates:
        - Historical data requests
        - Date range specification
        - Time-series analysis
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 5: Historical Price Data")
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
                end_date=end_date,
                periodicity="DAILY"
            )

            print(f"\nRetrieved {len(df)} daily records")
            print("\nRecent Price History:")
            print(df.tail(10).to_string(index=False))

            # Calculate returns
            if len(df) > 1:
                first_price = df.iloc[0]["PX_LAST"]
                last_price = df.iloc[-1]["PX_LAST"]
                returns = ((last_price - first_price) / first_price) * 100
                print(f"\n30-Day Return: {returns:+.2f}%")

    except BloombergConnectionError as e:
        print(f"\nError: {e}")


def example_6_error_handling():
    """
    Example 6: Robust error handling.

    Demonstrates:
        - Handling invalid securities
        - Handling missing fields
        - Field error tracking
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 6: Error Handling")
    print("=" * 80)

    try:
        with BloombergSession() as session:
            # Mix of valid/invalid fields and securities
            df = session.send_request(
                securities=[
                    "9107 JP Equity",        # Valid
                    "INVALID123 JP Equity"   # Invalid security
                ],
                fields=[
                    "PX_TO_BOOK_RATIO",      # Valid field
                    "INVALID_FIELD_XYZ"      # Invalid field
                ]
            )

            print("\nRetrieved Data:")
            print(df.to_string(index=False))

            # Check field errors
            errors = session.get_field_errors()
            if errors:
                print("\nField Errors Detected:")
                for security, fields in errors.items():
                    print(f"  {security}: {', '.join(fields)}")
            else:
                print("\nNo field errors detected")

            print("\nNote: Invalid securities are skipped, invalid fields return None")

    except BloombergConnectionError as e:
        print(f"\nError: {e}")


def example_7_manual_session_management():
    """
    Example 7: Manual session lifecycle (without context manager).

    Demonstrates:
        - Explicit start/close
        - Error handling with cleanup
        - When you need session persistence across multiple operations
    """
    print("\n" + "=" * 80)
    print("EXAMPLE 7: Manual Session Management")
    print("=" * 80)

    session = BloombergSession()

    try:
        # Explicit start
        session.start()
        print("Session started successfully")

        # Multiple requests on same session
        df1 = session.send_request(["9107 JP Equity"], ["PX_TO_BOOK_RATIO"])
        print(f"\nRequest 1: Retrieved {len(df1)} rows")

        df2 = session.send_request(["9104 JP Equity"], ["RETURN_COM_EQY"])
        print(f"Request 2: Retrieved {len(df2)} rows")

        print("\nBoth requests used same session (efficient)")

    except BloombergConnectionError as e:
        print(f"\nError: {e}")

    finally:
        # Always close session (critical!)
        session.close()
        print("\nSession closed")


def main():
    """Run all examples."""
    print("\n")
    print("*" * 80)
    print("BLOOMBERG SESSION MANAGER - USAGE EXAMPLES")
    print("*" * 80)
    print("\nPrerequisites:")
    print("  - Bloomberg Terminal running and logged in")
    print("  - blpapi package installed")
    print("  - DAPI service enabled (check DAPI<GO> in Terminal)")

    examples = [
        ("Basic Reference Data", example_1_basic_reference_data),
        ("Multiple Securities", example_2_multiple_securities),
        ("Point-in-Time Data", example_3_point_in_time_data),
        ("Ownership Data", example_4_ownership_data),
        ("Historical Prices", example_5_historical_prices),
        ("Error Handling", example_6_error_handling),
        ("Manual Session Management", example_7_manual_session_management)
    ]

    for name, func in examples:
        try:
            func()
            input("\nPress Enter to continue to next example...")
        except KeyboardInterrupt:
            print("\n\nExamples interrupted by user")
            break
        except Exception as e:
            print(f"\n✗ Example '{name}' failed: {e}")
            import traceback
            traceback.print_exc()

    print("\n" + "=" * 80)
    print("EXAMPLES COMPLETE")
    print("=" * 80)
    print("\nNext Steps:")
    print("  - Review output above")
    print("  - Modify examples for your specific use case")
    print("  - See docs/BLOOMBERG_TESTING.md for testing guide")


if __name__ == "__main__":
    main()
