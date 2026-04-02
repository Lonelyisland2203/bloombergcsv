"""
Bloomberg API Demo Mode

This script runs the Bloomberg pipeline using mocked Bloomberg API responses.
Allows testing the full pipeline without requiring Bloomberg Terminal.

Features:
- Realistic sample data for 5 companies from the Effissimo CSV
- Mocked Bloomberg responses for all extractors
- Complete Excel output (5-sheet workbook)
- Data quality validation
- Matches production output format exactly

Usage:
    python scripts/demo_mode.py

    Optional arguments:
    --num-companies N    Number of companies to include (default: 5, max: 29)
    --output PATH        Output path for Excel file

Output:
    - Excel workbook: output/effissimo_demo_YYYYMMDD.xlsx
    - Data quality report: logs/data_quality_report_demo_YYYYMMDD.json

Author: Bloomberg Activist Pipeline
"""

import argparse
import logging
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Dict, List, Optional
import random

import pandas as pd
import numpy as np


# Mock Bloomberg session for demo mode
class MockBloombergSession:
    """
    Mock Bloomberg session that returns realistic sample data.

    This class mimics the BloombergSession interface but returns
    pre-generated sample data instead of querying Bloomberg.
    """

    def __init__(self):
        """Initialize mock session."""
        self.started = False
        random.seed(42)  # For reproducible demo data

    def start(self) -> bool:
        """Mock session start."""
        self.started = True
        return True

    def stop(self) -> None:
        """Mock session stop."""
        self.started = False

    def reference_data(
        self, tickers: List[str], fields: List[str], overrides: Optional[Dict] = None
    ) -> pd.DataFrame:
        """
        Mock reference data query.

        Returns realistic sample data for requested tickers and fields.

        Args:
            tickers: List of Bloomberg tickers
            fields: List of Bloomberg field mnemonics
            overrides: Optional field overrides

        Returns:
            DataFrame with mocked Bloomberg data
        """
        rows = []

        for ticker in tickers:
            row = {"ticker": ticker}

            for field in fields:
                row[field] = self._generate_field_value(ticker, field)

            rows.append(row)

        return pd.DataFrame(rows)

    def historical_data(
        self,
        tickers: List[str],
        fields: List[str],
        start_date: date,
        end_date: date,
        overrides: Optional[Dict] = None,
    ) -> pd.DataFrame:
        """
        Mock historical data query.

        Returns realistic daily price data.

        Args:
            tickers: List of Bloomberg tickers
            fields: List of Bloomberg field mnemonics
            start_date: Start date
            end_date: End date
            overrides: Optional field overrides

        Returns:
            DataFrame with mocked historical data
        """
        rows = []

        # Generate daily prices for date range
        current_date = start_date
        while current_date <= end_date:
            # Skip weekends
            if current_date.weekday() < 5:  # Monday=0, Friday=4
                for ticker in tickers:
                    row = {
                        "ticker": ticker,
                        "date": current_date,
                    }

                    for field in fields:
                        row[field] = self._generate_price_value(ticker, field, current_date)

                    rows.append(row)

            current_date += timedelta(days=1)

        return pd.DataFrame(rows)

    def _generate_field_value(self, ticker: str, field: str):
        """
        Generate realistic mock value for a field.

        Args:
            ticker: Bloomberg ticker
            field: Bloomberg field mnemonic

        Returns:
            Mock value appropriate for the field type
        """
        # Extract numeric ticker code for deterministic random values
        ticker_code = int(ticker.split()[0]) if ticker.split()[0].isdigit() else 1000

        # Set seed based on ticker for consistency
        random.seed(ticker_code)

        # Company name fields
        if field in ["NAME", "LONG_COMP_NAME"]:
            return f"Demo Company {ticker_code}"
        elif field == "LONG_COMP_NAME_ENG":
            return f"Demo Company {ticker_code} Ltd."

        # Fiscal year end
        elif field == "FISCAL_YEAR_END_MONTH_DE":
            return random.choice([3, 12])  # March or December

        # Market cap and financials (in millions JPY)
        elif field == "CUR_MKT_CAP":
            return random.uniform(50000, 500000)
        elif field == "TOTAL_ASSETS":
            return random.uniform(100000, 1000000)
        elif field == "TOT_COMMON_EQY":
            return random.uniform(50000, 500000)
        elif field == "SALES_REV_TURN":
            return random.uniform(100000, 800000)
        elif field == "EBIT":
            return random.uniform(10000, 80000)
        elif field == "NET_INCOME":
            return random.uniform(5000, 50000)
        elif field == "CF_FREE_CASH_FLOW":
            return random.uniform(3000, 40000)

        # Valuation ratios
        elif field == "PE_RATIO":
            return random.uniform(8, 25)
        elif field == "PX_TO_BOOK_RATIO":
            return random.uniform(0.5, 2.5)
        elif field == "EV_TO_T12M_EBITDA":
            return random.uniform(5, 15)
        elif field == "EBITDA_TO_REVENUE":
            return random.uniform(0.05, 0.20)

        # Returns and performance
        elif field == "TOT_RETURN_INDEX_GROSS_DVDS":
            return random.uniform(90, 150)
        elif field == "RETURN_COM_EQY":
            return random.uniform(0.02, 0.15)
        elif field == "RETURN_ON_ASSET":
            return random.uniform(0.01, 0.10)

        # Governance
        elif field == "BOARD_OF_DIRECTORS_SIZE":
            return random.randint(5, 15)
        elif field == "NUM_OF_INDEPENDENT_BOARD_MEMBERS":
            return random.randint(2, 8)
        elif field == "INDEPENDENT_BOARD_MEMBER_RATIO":
            return random.uniform(0.2, 0.6)

        # Sector/industry
        elif field == "GICS_SECTOR_NAME":
            return random.choice([
                "Industrials",
                "Information Technology",
                "Financials",
                "Consumer Discretionary",
                "Materials",
            ])
        elif field == "INDUSTRY_GROUP":
            return "Demo Industry Group"

        # Default: return None
        else:
            return None

    def _generate_price_value(self, ticker: str, field: str, date: date):
        """
        Generate realistic price value for historical data.

        Args:
            ticker: Bloomberg ticker
            field: Price field (PX_LAST, PX_OPEN, etc.)
            date: Date for price

        Returns:
            Mock price value
        """
        # Base price determined by ticker
        ticker_code = int(ticker.split()[0]) if ticker.split()[0].isdigit() else 1000
        base_price = (ticker_code % 100) * 10 + 1000

        # Add some random walk variation based on date
        days_since_epoch = (date - date(2021, 1, 1)).days
        random.seed(ticker_code + days_since_epoch)
        variation = random.uniform(-0.05, 0.05)

        price = base_price * (1 + variation)

        # Different fields return slightly different prices
        if field == "PX_LAST":
            return round(price, 2)
        elif field == "PX_OPEN":
            return round(price * 0.998, 2)
        elif field == "PX_HIGH":
            return round(price * 1.015, 2)
        elif field == "PX_LOW":
            return round(price * 0.985, 2)
        elif field == "PX_VOLUME":
            return random.randint(100000, 5000000)
        else:
            return price


def generate_mock_ownership_data(tickers: List[str]) -> pd.DataFrame:
    """
    Generate mock ownership data (Top 20 holders).

    Args:
        tickers: List of Bloomberg tickers

    Returns:
        DataFrame with mock ownership data
    """
    rows = []

    for ticker in tickers:
        # Generate 10-20 mock holders per security
        num_holders = random.randint(10, 20)

        for i in range(1, num_holders + 1):
            holder_name = f"Mock Institutional Investor {i}"

            # Generate realistic ownership percentages (decreasing by rank)
            if i == 1:
                ownership_pct = random.uniform(0.08, 0.15)  # 8-15%
            elif i <= 5:
                ownership_pct = random.uniform(0.03, 0.08)  # 3-8%
            else:
                ownership_pct = random.uniform(0.01, 0.03)  # 1-3%

            rows.append({
                "ticker": ticker,
                "holder_rank": i,
                "holder_name": holder_name,
                "ownership_pct": ownership_pct,
                "shares_held": int(ownership_pct * 100000000),  # Mock shares
                "as_of_date": date.today(),
            })

    return pd.DataFrame(rows)


def generate_mock_events_data(
    campaign_periods: List[Dict]
) -> pd.DataFrame:
    """
    Generate mock corporate events data.

    Args:
        campaign_periods: List of campaign period dictionaries

    Returns:
        DataFrame with mock events
    """
    rows = []

    for period in campaign_periods:
        ticker = period["ticker"]
        start = period["campaign_start"]
        end = period["campaign_end"]

        # Generate 5-10 mock events per campaign
        num_events = random.randint(5, 10)

        for i in range(num_events):
            # Random event date within campaign period
            days_range = (end - start).days
            if days_range > 0:
                random_days = random.randint(0, days_range)
                event_date = start + timedelta(days=random_days)
            else:
                event_date = start

            event_type = random.choice([
                "Dividend Announcement",
                "Earnings Release",
                "Share Buyback",
                "Board Changes",
                "Strategic Alliance",
            ])

            rows.append({
                "ticker": ticker,
                "event_date": event_date,
                "event_type": event_type,
                "event_description": f"Mock {event_type} Event",
            })

    return pd.DataFrame(rows)


def generate_mock_peer_comps(tickers: List[str]) -> pd.DataFrame:
    """
    Generate mock peer comparison data.

    Args:
        tickers: List of Bloomberg tickers

    Returns:
        DataFrame with mock peer comp data
    """
    rows = []

    for ticker in tickers:
        rows.append({
            "ticker": ticker,
            "peer_group_size": random.randint(15, 40),
            "sector_median_pe": random.uniform(10, 20),
            "sector_median_pb": random.uniform(0.8, 2.0),
            "sector_median_ev_ebitda": random.uniform(6, 12),
            "sector_median_roe": random.uniform(0.05, 0.12),
            "relative_pe": random.uniform(0.7, 1.3),
            "relative_pb": random.uniform(0.6, 1.4),
        })

    return pd.DataFrame(rows)


def run_demo_pipeline(num_companies: int = 5, output_path: Optional[Path] = None) -> Path:
    """
    Run the full pipeline in demo mode.

    Args:
        num_companies: Number of companies to include in demo
        output_path: Optional output path for Excel file

    Returns:
        Path to generated Excel file
    """
    print("=" * 80)
    print("Bloomberg Pipeline - DEMO MODE")
    print("=" * 80)
    print(f"Demo Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print(f"Companies: {num_companies}")
    print("Data Source: MOCKED (for demonstration purposes)")
    print("=" * 80)

    # Load input CSV
    input_csv = Path(__file__).parent.parent / "effissimo_summary_by_company_corrected.csv"

    if not input_csv.exists():
        print(f"\n✗ Input CSV not found: {input_csv}")
        print("  Please ensure effissimo_summary_by_company_corrected.csv exists")
        sys.exit(1)

    df = pd.read_csv(input_csv)
    print(f"\n✓ Loaded input CSV: {len(df)} companies available")

    # Select first N companies for demo
    if num_companies > len(df):
        num_companies = len(df)
        print(f"⚠ Requested {num_companies} companies, but only {len(df)} available")

    demo_df = df.head(num_companies)
    print(f"✓ Selected {num_companies} companies for demo")

    # Convert tickers to Bloomberg format
    sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
    from ticker_converter import convert_ticker

    demo_df["bloomberg_ticker"] = demo_df["target_ticker"].apply(convert_ticker)

    # Create mock session
    mock_session = MockBloombergSession()
    mock_session.start()

    # Extract snapshot data
    print("\n[1/5] Extracting snapshot data...")
    tickers = demo_df["bloomberg_ticker"].tolist()
    fields = [
        "NAME",
        "LONG_COMP_NAME_ENG",
        "FISCAL_YEAR_END_MONTH_DE",
        "CUR_MKT_CAP",
        "TOTAL_ASSETS",
        "TOT_COMMON_EQY",
        "SALES_REV_TURN",
        "EBIT",
        "NET_INCOME",
        "PE_RATIO",
        "PX_TO_BOOK_RATIO",
        "RETURN_COM_EQY",
        "BOARD_OF_DIRECTORS_SIZE",
        "INDEPENDENT_BOARD_MEMBER_RATIO",
        "GICS_SECTOR_NAME",
    ]

    snapshot_df = mock_session.reference_data(tickers, fields)
    print(f"✓ Snapshot: {len(snapshot_df)} rows extracted")

    # Extract ownership data
    print("\n[2/5] Extracting ownership data...")
    ownership_df = generate_mock_ownership_data(tickers)
    print(f"✓ Ownership: {len(ownership_df)} rows extracted")

    # Extract events data
    print("\n[3/5] Extracting corporate events...")
    demo_df["first_filing_dt"] = pd.to_datetime(demo_df["first_filing"]).dt.date
    demo_df["last_filing_dt"] = pd.to_datetime(demo_df["last_filing"]).dt.date

    campaign_periods = [
        {
            "ticker": row["bloomberg_ticker"],
            "campaign_start": row["first_filing_dt"],
            "campaign_end": row["last_filing_dt"],
        }
        for _, row in demo_df.iterrows()
    ]

    events_df = generate_mock_events_data(campaign_periods)
    print(f"✓ Events: {len(events_df)} rows extracted")

    # Extract price history
    print("\n[4/5] Extracting price history...")
    price_rows = []

    for _, row in demo_df.iterrows():
        ticker = row["bloomberg_ticker"]
        start = row["first_filing_dt"]
        end = row["last_filing_dt"]

        price_data = mock_session.historical_data(
            [ticker],
            ["PX_LAST", "PX_OPEN", "PX_HIGH", "PX_LOW", "PX_VOLUME"],
            start,
            end,
        )

        price_rows.append(price_data)

    price_df = pd.concat(price_rows, ignore_index=True) if price_rows else pd.DataFrame()
    print(f"✓ Price History: {len(price_df)} rows extracted")

    # Extract peer comparisons
    print("\n[5/5] Extracting peer comparisons...")
    peer_comps_df = generate_mock_peer_comps(tickers)
    print(f"✓ Peer Comps: {len(peer_comps_df)} rows extracted")

    # Write Excel output
    print("\n" + "=" * 80)
    print("Writing Excel Output")
    print("=" * 80)

    if output_path is None:
        output_dir = Path(__file__).parent.parent / "output"
        output_dir.mkdir(exist_ok=True)
        timestamp = datetime.now().strftime("%Y%m%d")
        output_path = output_dir / f"effissimo_demo_{timestamp}.xlsx"

    # Use ExcelWriter from src
    from excel_writer import ExcelWriter
    from data_validator import DataValidator

    # Validate data
    print("\nValidating data quality...")
    logs_dir = Path(__file__).parent.parent / "logs"
    validator = DataValidator(logs_dir=logs_dir)
    quality_report = validator.validate_snapshot_data(snapshot_df)
    print(f"✓ Data Quality Score: {quality_report.overall_quality_score * 100:.1f}%")

    # Write Excel
    print("\nWriting Excel workbook...")
    writer = ExcelWriter()
    final_output = writer.write_activist_workbook(
        activist_name="Effissimo Capital Management",
        snapshot_df=snapshot_df,
        ownership_df=ownership_df,
        events_df=events_df,
        price_df=price_df,
        peer_comps_df=peer_comps_df,
        quality_report=quality_report,
        output_path=output_path,
    )

    print(f"✓ Excel workbook written: {final_output}")

    # Cleanup
    mock_session.stop()

    # Print summary
    print("\n" + "=" * 80)
    print("Demo Pipeline Complete")
    print("=" * 80)
    print(f"\nOutput File: {final_output}")
    print(f"Companies Processed: {num_companies}")
    print(f"Data Quality Score: {quality_report.overall_quality_score * 100:.1f}%")
    print("\nNOTE: This is DEMO DATA (mocked Bloomberg responses)")
    print("      For production, install Bloomberg API and run:")
    print("      python src/run_all.py --input effissimo_summary_by_company_corrected.csv")
    print("=" * 80)

    return final_output


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Run Bloomberg pipeline in demo mode (mocked data)",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Run demo with default 5 companies
  python scripts/demo_mode.py

  # Run demo with 10 companies
  python scripts/demo_mode.py --num-companies 10

  # Specify custom output path
  python scripts/demo_mode.py --output demo_output.xlsx
        """,
    )

    parser.add_argument(
        "--num-companies",
        type=int,
        default=5,
        help="Number of companies to include in demo (default: 5, max: 29)",
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Output path for Excel file (default: output/effissimo_demo_YYYYMMDD.xlsx)",
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    try:
        args = parse_arguments()

        # Validate num_companies
        if args.num_companies < 1:
            print("Error: --num-companies must be at least 1")
            return 1

        if args.num_companies > 29:
            print(f"Warning: Maximum 29 companies available, limiting to 29")
            args.num_companies = 29

        # Run demo pipeline
        output_path = run_demo_pipeline(
            num_companies=args.num_companies,
            output_path=args.output,
        )

        return 0

    except Exception as e:
        print(f"\n✗ Demo pipeline failed: {e}")
        import traceback
        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
