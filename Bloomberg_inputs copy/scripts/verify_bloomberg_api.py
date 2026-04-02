"""
Bloomberg API Installation Verification Script

This script checks if the Bloomberg Python API (blpapi) is properly installed
and can connect to a running Bloomberg Terminal.

Steps performed:
1. Check if blpapi package is installed
2. Verify blpapi version
3. Check if Bloomberg Terminal is running
4. Test connection to Bloomberg API
5. Run diagnostic queries

Usage:
    python scripts/verify_bloomberg_api.py

Exit Codes:
    0 = All checks passed, ready for production
    1 = blpapi not installed
    2 = blpapi installed but cannot connect to Terminal
    3 = Other errors

Author: Bloomberg Activist Pipeline
"""

import sys
from datetime import datetime
from pathlib import Path


def print_header(title: str) -> None:
    """Print formatted header."""
    print("\n" + "=" * 80)
    print(title)
    print("=" * 80)


def print_section(title: str) -> None:
    """Print formatted section header."""
    print(f"\n{title}")
    print("-" * 80)


def check_blpapi_installation() -> bool:
    """
    Check if blpapi package is installed.

    Returns:
        True if installed, False otherwise
    """
    print_section("Step 1: Checking blpapi Installation")

    try:
        import blpapi

        version = getattr(blpapi, "__version__", "Unknown")
        print(f"✓ blpapi is installed")
        print(f"  Version: {version}")
        return True

    except ImportError as e:
        print(f"✗ blpapi is NOT installed")
        print(f"  Error: {e}")
        print("\nINSTALLATION REQUIRED:")
        print("  The Bloomberg Python API (blpapi) must be downloaded from Bloomberg Terminal.")
        print("\n  Steps to install:")
        print("  1. Open Bloomberg Terminal")
        print("  2. Type: WAPI<GO>")
        print("  3. Download 'Bloomberg API Python Library'")
        print("  4. Follow installation instructions")
        print("\n  Alternative:")
        print("  pip install --index-url=https://bcms.bloomberg.com/pip/simple blpapi")
        print("\n  Note: You must have Bloomberg Terminal installed and running.")
        return False


def check_terminal_connection() -> bool:
    """
    Check if Bloomberg Terminal is running and accessible.

    Returns:
        True if connected, False otherwise
    """
    print_section("Step 2: Testing Bloomberg Terminal Connection")

    try:
        import blpapi

        # Create session options
        sessionOptions = blpapi.SessionOptions()
        sessionOptions.setServerHost("localhost")
        sessionOptions.setServerPort(8194)  # Default Bloomberg API port

        # Create session
        print("  Attempting to connect to Bloomberg Terminal...")
        print("  Host: localhost")
        print("  Port: 8194")

        session = blpapi.Session(sessionOptions)

        # Try to start session (non-blocking)
        if not session.start():
            print("✗ Failed to start Bloomberg session")
            print("\nTROUBLESHOOTING:")
            print("  - Is Bloomberg Terminal running?")
            print("  - Are you logged in to Bloomberg Terminal?")
            print("  - Is the Bloomberg API service enabled?")
            print("  - Check Terminal settings: API<GO>")
            return False

        # Try to open reference data service
        if not session.openService("//blp/refdata"):
            print("✗ Failed to open Bloomberg reference data service")
            session.stop()
            return False

        print("✓ Successfully connected to Bloomberg Terminal")
        print("✓ Reference data service is accessible")

        # Cleanup
        session.stop()
        return True

    except ImportError:
        print("✗ blpapi not installed (cannot test connection)")
        return False

    except Exception as e:
        print(f"✗ Connection failed: {e}")
        print("\nTROUBLESHOOTING:")
        print("  - Ensure Bloomberg Terminal is running and logged in")
        print("  - Check that Bloomberg API is enabled: API<GO>")
        print("  - Verify firewall/antivirus is not blocking localhost:8194")
        print("  - Try restarting Bloomberg Terminal")
        return False


def run_diagnostic_query() -> bool:
    """
    Run a simple diagnostic query to test Bloomberg API functionality.

    Returns:
        True if query succeeds, False otherwise
    """
    print_section("Step 3: Running Diagnostic Query")

    try:
        import blpapi

        # Create session
        sessionOptions = blpapi.SessionOptions()
        sessionOptions.setServerHost("localhost")
        sessionOptions.setServerPort(8194)

        session = blpapi.Session(sessionOptions)

        if not session.start():
            print("✗ Cannot start session for diagnostic query")
            return False

        if not session.openService("//blp/refdata"):
            print("✗ Cannot open reference data service")
            session.stop()
            return False

        # Get service
        refDataService = session.getService("//blp/refdata")

        # Create request for a simple query
        # Query: Get current price for Sony (6758 JP Equity)
        print("  Testing query: 6758 JP Equity (Sony Group Corp)")
        print("  Field: PX_LAST (Last Price)")

        request = refDataService.createRequest("ReferenceDataRequest")
        request.append("securities", "6758 JP Equity")
        request.append("fields", "PX_LAST")

        # Send request
        session.sendRequest(request)

        # Process response
        response_received = False
        while True:
            event = session.nextEvent(500)  # 500ms timeout

            if event.eventType() == blpapi.Event.RESPONSE or event.eventType() == blpapi.Event.PARTIAL_RESPONSE:
                for msg in event:
                    if msg.hasElement("securityData"):
                        securityDataArray = msg.getElement("securityData")
                        for securityData in securityDataArray.values():
                            ticker = securityData.getElementAsString("security")
                            fieldData = securityData.getElement("fieldData")

                            if fieldData.hasElement("PX_LAST"):
                                price = fieldData.getElementAsFloat("PX_LAST")
                                print(f"\n✓ Diagnostic query successful!")
                                print(f"  Ticker: {ticker}")
                                print(f"  Last Price: ¥{price:,.2f}")
                                response_received = True
                            else:
                                print(f"\n⚠ Query returned no data for PX_LAST")
                                print(f"  This may indicate a data subscription issue")

            if event.eventType() == blpapi.Event.RESPONSE:
                break

        # Cleanup
        session.stop()

        if response_received:
            print("\n✓ Bloomberg API is fully functional")
            return True
        else:
            print("\n✗ Bloomberg API responded but returned no data")
            print("  This may indicate a data entitlement/subscription issue")
            return False

    except ImportError:
        print("✗ blpapi not installed (cannot run diagnostic query)")
        return False

    except Exception as e:
        print(f"✗ Diagnostic query failed: {e}")
        return False


def print_installation_guide() -> None:
    """Print detailed installation guide."""
    print_header("Bloomberg API Installation Guide")

    print("""
The Bloomberg Python API (blpapi) is required to run this pipeline.

PREREQUISITES:
  - Bloomberg Terminal must be installed on this machine
  - Bloomberg Terminal must be running and logged in
  - You must have a valid Bloomberg subscription

INSTALLATION METHOD 1: Download from Terminal (Recommended)
  1. Open Bloomberg Terminal
  2. Type: WAPI<GO> and press Enter
  3. Navigate to: API Downloads → Python
  4. Download the appropriate version for your system:
     - Windows: blpapi-X.X.X-win-py3.X.exe
     - macOS: blpapi-X.X.X-macosx-py3.X.tar.gz
     - Linux: blpapi-X.X.X-linux-py3.X.tar.gz
  5. Follow the installation wizard or extract and run:
     pip install <downloaded_file>

INSTALLATION METHOD 2: Bloomberg PyPI Repository
  pip install --index-url=https://bcms.bloomberg.com/pip/simple blpapi

  Note: This requires Bloomberg network access and may not work outside
        Bloomberg's network or VPN.

VERIFICATION:
  After installation, run this script again:
  python scripts/verify_bloomberg_api.py

TROUBLESHOOTING:
  - If installation fails, ensure Bloomberg Terminal is running
  - Check that you have admin/sudo privileges for installation
  - Verify your Python version matches the blpapi package version
  - For corporate environments, check with IT about proxy settings

For more information:
  - Bloomberg Terminal: WAPI<GO>
  - Bloomberg API Documentation: https://www.bloomberg.com/professional/support/api-library/
    """)


def print_demo_mode_info() -> None:
    """Print information about demo mode."""
    print_header("Demo Mode Available")

    print("""
Cannot install Bloomberg API right now? No problem!

You can test the pipeline in DEMO MODE using mocked Bloomberg responses.

DEMO MODE:
  - Uses realistic sample data for 5 companies
  - Generates Excel output in the same format as production
  - Allows you to test the pipeline without Bloomberg API
  - Perfect for development, testing, and validation

RUN DEMO MODE:
  python scripts/demo_mode.py

WHAT DEMO MODE PROVIDES:
  ✓ Mocked snapshot data (financial metrics, valuation ratios, governance)
  ✓ Mocked ownership data (Top 20 holders)
  ✓ Mocked events data (corporate actions)
  ✓ Mocked price history (daily prices)
  ✓ Mocked peer comparisons (sector medians)
  ✓ Complete Excel output (5-sheet workbook)
  ✓ Data quality report

TRANSITION TO PRODUCTION:
  Once Bloomberg API is installed, simply run:
  python src/run_all.py --input effissimo_summary_by_company_corrected.csv \\
                        --activist "Effissimo Capital Management"

  The pipeline will use real Bloomberg data instead of mocked data.
    """)


def main() -> int:
    """
    Main verification workflow.

    Returns:
        Exit code
    """
    print_header("Bloomberg API Installation Verification")
    print(f"Verification Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")

    # Step 1: Check installation
    blpapi_installed = check_blpapi_installation()

    if not blpapi_installed:
        print_installation_guide()
        print_demo_mode_info()
        return 1

    # Step 2: Check connection
    connected = check_terminal_connection()

    if not connected:
        print_demo_mode_info()
        return 2

    # Step 3: Run diagnostic query
    query_success = run_diagnostic_query()

    # Print summary
    print_header("Verification Summary")

    if blpapi_installed and connected and query_success:
        print("\n✅ ALL CHECKS PASSED")
        print("\nThe Bloomberg API is fully functional and ready for production.")
        print("\nNext Steps:")
        print("  1. Validate your input CSV:")
        print("     python scripts/validate_input_csv.py --input effissimo_summary_by_company_corrected.csv")
        print("\n  2. Run the pipeline:")
        print("     python src/run_all.py --input effissimo_summary_by_company_corrected.csv \\")
        print("                           --activist 'Effissimo Capital Management'")
        print("\n" + "=" * 80)
        return 0

    else:
        print("\n⚠️ SOME CHECKS FAILED")
        print("\nStatus:")
        print(f"  - blpapi installed: {'✓' if blpapi_installed else '✗'}")
        print(f"  - Terminal connected: {'✓' if connected else '✗'}")
        print(f"  - Diagnostic query: {'✓' if query_success else '✗'}")
        print("\nRecommendation:")
        print("  - Review troubleshooting steps above")
        print("  - Try demo mode to test the pipeline: python scripts/demo_mode.py")
        print("\n" + "=" * 80)
        return 3


if __name__ == "__main__":
    sys.exit(main())
