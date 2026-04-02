"""
Snapshot Extraction Demo - Effissimo Capital Campaigns

This script demonstrates the complete workflow for extracting point-in-time
financial snapshots for activist campaign targets.

Usage:
    python snapshot_extraction_demo.py

Prerequisites:
    - Bloomberg Terminal running and logged in
    - Bloomberg DAPI configured (localhost:8194)
    - Valid Bloomberg ticker symbols

Output:
    - Snapshot DataFrame with 40+ fields per company
    - Field gap report (JSON)
    - Data quality summary

Author: Bloomberg Activist Pipeline
"""

import logging
from datetime import date
from pathlib import Path
import sys

import pandas as pd

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from bloomberg_session import BloombergSession
from batching_engine import BatchingEngine
from extract_snapshot import CampaignTarget, SnapshotExtractor

# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
)

logger = logging.getLogger(__name__)


def create_effissimo_campaigns():
    """
    Create sample Effissimo campaign targets.

    This represents a subset of Effissimo Capital's actual campaign targets.
    Real data would be loaded from CSV file.

    Returns:
        List of CampaignTarget objects
    """
    campaigns = [
        CampaignTarget(
            company_name_japanese="株式会社サンリオ",
            company_name_english="Sanrio Co Ltd",
            tse_ticker="8136.T",
            bloomberg_ticker="8136 JP Equity",
            campaign_start=date(2021, 6, 14),
            campaign_end=None,
            max_ownership_pct=9.84,
            min_ownership_pct=5.01,
            total_filings=12,
        ),
        CampaignTarget(
            company_name_japanese="川崎汽船株式会社",
            company_name_english="Kawasaki Kisen Kaisha Ltd",
            tse_ticker="9107.T",
            bloomberg_ticker="9107 JP Equity",
            campaign_start=date(2020, 11, 5),
            campaign_end=date(2024, 3, 31),
            max_ownership_pct=9.99,
            min_ownership_pct=5.01,
            total_filings=18,
        ),
        CampaignTarget(
            company_name_japanese="株式会社ディー・エヌ・エー",
            company_name_english="DeNA Co Ltd",
            tse_ticker="2432.T",
            bloomberg_ticker="2432 JP Equity",
            campaign_start=date(2022, 3, 15),
            campaign_end=None,
            max_ownership_pct=7.23,
            min_ownership_pct=5.02,
            total_filings=8,
        ),
    ]

    return campaigns


def print_snapshot_summary(snapshot_df: pd.DataFrame):
    """
    Print summary statistics for snapshot data.

    Args:
        snapshot_df: Snapshot DataFrame
    """
    print("\n" + "=" * 80)
    print("SNAPSHOT EXTRACTION SUMMARY")
    print("=" * 80)

    print(f"\nTotal Companies: {len(snapshot_df)}")
    print(f"Total Fields: {len(snapshot_df.columns)}")

    print("\n--- Data Quality ---")
    avg_quality = snapshot_df["data_quality_score"].mean()
    print(f"Average Data Quality Score: {avg_quality:.1f}%")

    flagged_count = snapshot_df["manual_review_flag"].sum()
    print(f"Companies Flagged for Manual Review: {flagged_count}")

    print("\n--- Point-in-Time Validation ---")
    all_valid = all(
        snapshot_df["snapshot_date"] < snapshot_df["campaign_start"]
    )
    print(f"Point-in-Time Safety: {'PASS' if all_valid else 'FAIL'}")

    print("\n--- Fiscal Year-Ends ---")
    fye_counts = snapshot_df["fye_month"].value_counts()
    for fye_month, count in fye_counts.items():
        month_name = {
            3: "March",
            6: "June",
            9: "September",
            12: "December",
        }.get(fye_month, f"Month {fye_month}")
        print(f"  {month_name}: {count} companies")

    print("\n--- Sample Valuation Metrics ---")
    print(
        snapshot_df[
            [
                "security",
                "PX_TO_BOOK_RATIO",
                "RETURN_COM_EQY",
                "net_cash_to_market_cap",
            ]
        ].head(3)
    )

    print("\n--- Derived Fields ---")
    print(
        f"Companies with Net Cash Position: {(snapshot_df['net_cash'] > 0).sum()}"
    )
    print(
        f"Companies with Net Debt Position: {(snapshot_df['net_cash'] < 0).sum()}"
    )

    print("\n" + "=" * 80)


def main():
    """Main execution function."""
    logger.info("Starting Effissimo snapshot extraction demo")

    # Step 1: Create campaign targets
    logger.info("Loading campaign targets")
    campaigns = create_effissimo_campaigns()
    logger.info(f"Loaded {len(campaigns)} campaigns")

    # Step 2: Initialize Bloomberg session
    logger.info("Initializing Bloomberg session")

    # Note: This will fail if Bloomberg Terminal is not running
    # For demo purposes, we'll show the intended workflow
    try:
        with BloombergSession() as session:
            # Step 3: Initialize batching engine
            logger.info("Initializing batching engine")
            batching_engine = BatchingEngine(
                max_batch_size=20,
                min_delay_seconds=2.0,
                max_retries=3,
            )

            # Step 4: Initialize snapshot extractor
            logger.info("Initializing snapshot extractor")
            extractor = SnapshotExtractor(
                session=session,
                batching_engine=batching_engine,
            )

            # Step 5: Extract snapshot
            logger.info("Extracting snapshot data (this may take a few minutes)")
            snapshot_df = extractor.extract_snapshot(campaigns)

            # Step 6: Print summary
            print_snapshot_summary(snapshot_df)

            # Step 7: Save to CSV (optional)
            output_dir = Path(__file__).parent.parent / "data" / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            output_path = output_dir / "effissimo_snapshot.csv"
            snapshot_df.to_csv(output_path, index=False)
            logger.info(f"Snapshot saved to: {output_path}")

            logger.info("Demo complete!")

    except Exception as e:
        logger.error(f"Demo failed: {e}")
        logger.info(
            "\nNote: This demo requires Bloomberg Terminal to be running.\n"
            "If Bloomberg Terminal is not available, please run the unit tests instead:\n"
            "  python -m pytest tests/test_extract_snapshot.py -v"
        )
        sys.exit(1)


if __name__ == "__main__":
    main()
