"""
Phase 9-10 Demo: Data Validation and Excel Export

This example demonstrates:
    1. Creating sample financial data
    2. Validating data quality with DataValidator
    3. Generating formatted Excel workbook with ExcelWriter
    4. Reviewing validation reports

Run this example:
    python examples/phase9_10_demo.py

Author: Bloomberg Activist Pipeline
"""

import sys
from pathlib import Path
from datetime import date
import pandas as pd
import numpy as np

# Add src directory to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_validator import DataValidator, DataQualityReport
from excel_writer import ExcelWriter


def create_sample_data():
    """Create sample financial snapshot data for Effissimo targets."""
    print("Creating sample financial data...")

    # Sample data for 5 Effissimo targets
    data = {
        "bloomberg_ticker": [
            "9107 JP Equity",  # Kawasaki Kisen
            "9101 JP Equity",  # NYK Line
            "9104 JP Equity",  # Mitsui O.S.K. Lines
            "8001 JP Equity",  # Itochu
            "8002 JP Equity",  # Marubeni
        ],
        "company_name_english": [
            "Kawasaki Kisen Kaisha",
            "Nippon Yusen Kabushiki Kaisha",
            "Mitsui O.S.K. Lines",
            "Itochu Corporation",
            "Marubeni Corporation",
        ],
        "PX_TO_BOOK_RATIO": [1.5, 2.0, 1.8, np.nan, 0.05],  # Last one out of range
        "RETURN_COM_EQY": [10.5, 12.0, 8.5, 15.0, 60.0],  # Last one out of range
        "CUR_MKT_CAP": [1000000, 2000000, 1500000, 3000000, -100],  # Last one invalid
        "NET_DEBT": [100000, -50000, 200000, np.nan, 150000],
        "TRAIL_12M_SALES": [500000, 600000, 550000, np.nan, 700000],
        "net_cash": [-100000, 50000, -200000, np.nan, -150000],
        "net_cash_to_market_cap": [-0.1, 0.025, -0.133, np.nan, 1.5],  # Last one out of range
        "snapshot_date": [date(2021, 3, 31)] * 5,
        "campaign_start": [date(2021, 6, 1)] * 5,
    }

    return pd.DataFrame(data)


def create_sample_ownership():
    """Create sample ownership data."""
    data = {
        "bloomberg_ticker": ["9107 JP Equity"] * 3,
        "holder_name": [
            "Effissimo Capital Management",
            "Japan Trustee Services Bank",
            "The Master Trust Bank of Japan",
        ],
        "pct_held": [9.9, 5.2, 4.1],
        "position_date": [date(2021, 5, 31)] * 3,
        "holder_type": ["Hedge Fund", "Trust Bank", "Trust Bank"],
    }
    return pd.DataFrame(data)


def create_sample_events():
    """Create sample corporate actions data."""
    data = {
        "bloomberg_ticker": ["9107 JP Equity", "9101 JP Equity"],
        "event_type": ["Dividend", "Stock Split"],
        "event_date": [date(2021, 6, 30), date(2021, 9, 30)],
        "description": ["Annual dividend ¥50", "2-for-1 stock split"],
    }
    return pd.DataFrame(data)


def create_sample_price_history():
    """Create sample price history data."""
    dates = pd.date_range(start="2021-01-01", periods=10, freq="D")
    data = {
        "bloomberg_ticker": ["9107 JP Equity"] * 10,
        "date": dates,
        "PX_LAST": [1000, 1010, 1020, 1015, 1025, 1030, 1028, 1035, 1040, 1050],
        "PX_VOLUME": [100000, 110000, 95000, 105000, 120000, 98000, 102000, 115000, 108000, 112000],
    }
    return pd.DataFrame(data)


def create_sample_peer_comps():
    """Create sample peer comparables data."""
    data = {
        "bloomberg_ticker": ["9107 JP Equity", "9101 JP Equity"],
        "company_name_english": ["Kawasaki Kisen", "NYK Line"],
        "peer_ticker": ["9110 JP Equity", "9120 JP Equity"],
        "peer_name": ["Peer Shipping A", "Peer Shipping B"],
        "PX_TO_BOOK_RATIO": [1.5, 1.8],
        "RETURN_COM_EQY": [10.5, 11.0],
    }
    return pd.DataFrame(data)


def main():
    """Run Phase 9-10 demonstration."""
    print("=" * 80)
    print("Phase 9-10 Demo: Data Validation & Excel Export")
    print("=" * 80)
    print()

    # Create sample data
    snapshot_df = create_sample_data()
    ownership_df = create_sample_ownership()
    events_df = create_sample_events()
    price_history_df = create_sample_price_history()
    peer_comps_df = create_sample_peer_comps()

    print(f"Created sample data:")
    print(f"  - Snapshot: {len(snapshot_df)} securities")
    print(f"  - Ownership: {len(ownership_df)} holders")
    print(f"  - Events: {len(events_df)} corporate actions")
    print(f"  - Price History: {len(price_history_df)} daily prices")
    print(f"  - Peer Comps: {len(peer_comps_df)} peer comparisons")
    print()

    # Phase 9: Validate data quality
    print("-" * 80)
    print("PHASE 9: Data Validation")
    print("-" * 80)
    print()

    validator = DataValidator()

    print("Validating snapshot data...")
    snapshot_report = validator.validate_snapshot_data(snapshot_df)

    print("\nValidation Summary:")
    print(snapshot_report.summary())
    print()

    # Save validation report
    validator.save_report(snapshot_report, filename="effissimo_quality_report.json")
    print(f"✓ Quality report saved to: {validator.logs_dir / 'effissimo_quality_report.json'}")
    print()

    # Validate ownership data
    print("Validating ownership data...")
    ownership_report = validator.validate_ownership_data(ownership_df)
    print(f"  Ownership quality score: {ownership_report.overall_quality_score:.1%}")
    print()

    # Phase 10: Generate Excel workbook
    print("-" * 80)
    print("PHASE 10: Excel Export")
    print("-" * 80)
    print()

    writer = ExcelWriter()

    print("Generating 5-sheet Excel workbook...")
    output_path = writer.write_activist_workbook(
        activist_name="Effissimo Capital Management",
        snapshot_df=snapshot_df,
        ownership_df=ownership_df,
        events_df=events_df,
        price_history_df=price_history_df,
        peer_comps_df=peer_comps_df,
        data_quality_report=snapshot_report,
    )

    print(f"\n✓ Excel workbook created: {output_path}")
    print()

    # Verify workbook
    from openpyxl import load_workbook

    wb = load_workbook(output_path)
    print(f"Workbook contains {len(wb.sheetnames)} sheets:")
    for idx, sheet_name in enumerate(wb.sheetnames, 1):
        ws = wb[sheet_name]
        print(f"  {idx}. {sheet_name} ({ws.max_row} rows × {ws.max_column} cols)")

    print()

    # Print key findings
    print("-" * 80)
    print("KEY FINDINGS")
    print("-" * 80)
    print()

    print(f"Data Quality Score: {snapshot_report.overall_quality_score:.1%}")
    print()

    if snapshot_report.range_violations:
        print(f"Range Violations Detected: {len(snapshot_report.range_violations)}")
        for violation in snapshot_report.range_violations[:5]:  # Show first 5
            print(f"  - {violation.ticker}: {violation.field} = {violation.value}")
            print(f"    Expected range: [{violation.min_expected}, {violation.max_expected}]")
        print()

    if snapshot_report.recommended_manual_review:
        print(f"Securities Requiring Manual Review: {len(snapshot_report.recommended_manual_review)}")
        for ticker in snapshot_report.recommended_manual_review:
            print(f"  - {ticker}")
        print()

    print("=" * 80)
    print("Demo Complete!")
    print("=" * 80)
    print()
    print(f"Next Steps:")
    print(f"  1. Review quality report: {validator.logs_dir / 'effissimo_quality_report.json'}")
    print(f"  2. Open Excel workbook: {output_path}")
    print(f"  3. Manually review flagged securities")
    print()


if __name__ == "__main__":
    main()
