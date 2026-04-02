"""
Ownership & Events Extraction Demo

This example demonstrates how to use the OwnershipExtractor and EventsExtractor
to analyze Japanese activist campaigns.

Example Use Case:
    Extract Top 20 shareholders and corporate actions for 5 Effissimo campaign targets:
    - 9107 JP Equity (Sanrio)
    - 8136 JP Equity (Toshiba)
    - 6502 JP Equity (Sony)
    - 7951 JP Equity (Yamaha)
    - 8252 JP Equity (Takashimaya)

Key Outputs:
    1. Top 20 shareholder data with foreign/cross-shareholding flags
    2. Cross-shareholding ratios per company
    3. Foreign institutional ownership ratios
    4. Corporate events during campaign period ONLY (dividends, buybacks, splits, M&A)
    5. Timeline of events (months after activist entry)

Usage:
    python examples/ownership_and_events_demo.py

Requirements:
    - Bloomberg Terminal running
    - Active Bloomberg API connection
    - blpapi package installed

Author: Bloomberg Activist Pipeline
"""

import sys
from datetime import date
from pathlib import Path

import pandas as pd

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from bloomberg_session import BloombergSession
from extract_ownership import OwnershipExtractor
from extract_events import EventsExtractor, CampaignPeriod


def main():
    """Run ownership and events extraction demo."""
    print("=" * 80)
    print("BLOOMBERG ACTIVIST DATA PIPELINE")
    print("Ownership & Events Extraction Demo")
    print("=" * 80)
    print()

    # Define campaign targets (example: 5 Effissimo companies)
    campaign_targets = [
        {
            "ticker": "9107 JP Equity",
            "company": "Sanrio Co Ltd",
            "campaign_start": date(2021, 6, 14),
            "campaign_end": date(2023, 12, 31),
        },
        {
            "ticker": "8136 JP Equity",
            "company": "Toshiba Corp",
            "campaign_start": date(2020, 3, 1),
            "campaign_end": None,  # Ongoing
        },
        {
            "ticker": "6502 JP Equity",
            "company": "Sony Group Corp",
            "campaign_start": date(2019, 4, 1),
            "campaign_end": date(2022, 6, 30),
        },
        {
            "ticker": "7951 JP Equity",
            "company": "Yamaha Corp",
            "campaign_start": date(2021, 9, 1),
            "campaign_end": None,  # Ongoing
        },
        {
            "ticker": "8252 JP Equity",
            "company": "Takashimaya Co Ltd",
            "campaign_start": date(2022, 3, 15),
            "campaign_end": date(2024, 1, 31),
        },
    ]

    securities = [t["ticker"] for t in campaign_targets]
    company_names = {t["ticker"]: t["company"] for t in campaign_targets}

    # Create campaign periods for events extractor
    campaign_periods = {
        t["ticker"]: CampaignPeriod(
            ticker=t["ticker"],
            company_name=t["company"],
            campaign_start=t["campaign_start"],
            campaign_end=t["campaign_end"],
        )
        for t in campaign_targets
    }

    print(f"Analyzing {len(securities)} activist campaign targets:")
    for target in campaign_targets:
        status = "Ongoing" if target["campaign_end"] is None else "Ended"
        print(f"  - {target['company']} ({target['ticker']}) - {status}")
    print()

    # =========================================================================
    # PART 1: OWNERSHIP EXTRACTION
    # =========================================================================
    print("=" * 80)
    print("PART 1: TOP 20 SHAREHOLDERS & CROSS-SHAREHOLDING ANALYSIS")
    print("=" * 80)
    print()

    try:
        # Start Bloomberg session
        print("Connecting to Bloomberg Terminal...")
        with BloombergSession() as session:
            print("✓ Connected to Bloomberg API")
            print()

            # Create ownership extractor
            ownership_extractor = OwnershipExtractor(session=session)

            # Extract Top 20 holders
            print(f"Extracting TOP_20_HOLDERS for {len(securities)} securities...")
            holders_df = ownership_extractor.extract_top_20_holders(securities)
            print(f"✓ Retrieved {len(holders_df)} holder records")
            print()

            # Generate ownership summary
            print("Computing ownership metrics...")
            ownership_summary = ownership_extractor.generate_ownership_summary(
                securities=securities,
                company_names=company_names,
            )

            # Display summary
            print()
            print("OWNERSHIP SUMMARY")
            print("-" * 80)
            pd.set_option("display.max_columns", None)
            pd.set_option("display.width", None)
            print(ownership_summary.to_string(index=False))
            print()

            # Highlight key insights
            print("KEY INSIGHTS:")
            print("-" * 80)

            # Highest cross-shareholding
            max_cross = ownership_summary.loc[
                ownership_summary["cross_shareholding_ratio"].idxmax()
            ]
            print(
                f"  • Highest cross-shareholding: {max_cross['company_name']} "
                f"({max_cross['cross_shareholding_ratio']:.1f}%)"
            )

            # Highest foreign institutional ownership
            max_foreign = ownership_summary.loc[
                ownership_summary["foreign_institutional_ratio"].idxmax()
            ]
            print(
                f"  • Highest foreign institutional ownership: {max_foreign['company_name']} "
                f"({max_foreign['foreign_institutional_ratio']:.1f}%)"
            )

            # Most concentrated ownership
            max_concentration = ownership_summary.loc[
                ownership_summary["top_5_concentration"].idxmax()
            ]
            print(
                f"  • Most concentrated ownership: {max_concentration['company_name']} "
                f"({max_concentration['top_5_concentration']:.1f}% held by top 5)"
            )
            print()

            # Save detailed ownership data
            output_dir = Path(__file__).parent.parent / "data" / "output"
            output_dir.mkdir(parents=True, exist_ok=True)

            detailed_path = output_dir / "detailed_ownership.csv"
            ownership_extractor.save_detailed_ownership(holders_df, detailed_path)
            print(f"✓ Detailed ownership data saved to: {detailed_path}")

            summary_path = output_dir / "ownership_summary.csv"
            ownership_summary.to_csv(summary_path, index=False)
            print(f"✓ Ownership summary saved to: {summary_path}")
            print()

            # =========================================================================
            # PART 2: EVENTS EXTRACTION
            # =========================================================================
            print("=" * 80)
            print("PART 2: CORPORATE EVENTS DURING CAMPAIGN PERIODS")
            print("=" * 80)
            print()

            # Create events extractor
            events_extractor = EventsExtractor(session=session)

            # Extract all corporate events
            print(f"Extracting corporate events for {len(securities)} securities...")
            print("(Filtering to campaign periods ONLY)")
            print()

            all_events = events_extractor.extract_all_events(
                securities=securities,
                campaign_periods=campaign_periods,
            )

            if all_events.empty:
                print("⚠ No corporate events found during campaign periods")
            else:
                print(f"✓ Retrieved {len(all_events)} events during campaign periods")
                print()

                # Display events summary
                print("EVENTS SUMMARY BY TYPE")
                print("-" * 80)
                event_counts = all_events.groupby("event_type").size().sort_values(ascending=False)
                for event_type, count in event_counts.items():
                    print(f"  • {event_type}: {count}")
                print()

                # Display recent events
                print("RECENT EVENTS (SAMPLE)")
                print("-" * 80)
                recent_events = all_events.sort_values("event_date", ascending=False).head(10)
                display_cols = [
                    "company_name",
                    "event_type",
                    "event_date",
                    "months_after_activist_entry",
                ]
                print(recent_events[display_cols].to_string(index=False))
                print()

                # Analyze dividend trends
                dividend_events = all_events[
                    all_events["event_type"].str.contains("Dividend", na=False)
                ]
                if not dividend_events.empty:
                    print("DIVIDEND TRENDS")
                    print("-" * 80)
                    dividend_summary = dividend_events.groupby("event_type").size()
                    for div_type, count in dividend_summary.items():
                        print(f"  • {div_type}: {count}")
                    print()

                # Analyze buyback activity
                buyback_events = all_events[all_events["event_type"] == "Share Buyback"]
                if not buyback_events.empty:
                    print("BUYBACK ACTIVITY")
                    print("-" * 80)
                    print(f"  • Total buyback announcements: {len(buyback_events)}")
                    buyback_companies = buyback_events["company_name"].unique()
                    print(f"  • Companies with buybacks: {', '.join(buyback_companies)}")
                    print()

                # Save events data
                events_path = output_dir / "corporate_events.csv"
                events_extractor.save_events_to_csv(all_events, events_path)
                print(f"✓ Events data saved to: {events_path}")
                print()

            print("=" * 80)
            print("DEMO COMPLETE")
            print("=" * 80)
            print()
            print("Summary:")
            print(f"  • Ownership data: {len(ownership_summary)} companies analyzed")
            print(f"  • Total holders: {len(holders_df)} records")
            if not all_events.empty:
                print(f"  • Corporate events: {len(all_events)} during campaign periods")
            print()
            print("Output files saved to: data/output/")

    except Exception as e:
        print(f"✗ Error: {e}")
        print()
        print("Troubleshooting:")
        print("  1. Ensure Bloomberg Terminal is running and logged in")
        print("  2. Check DAPI service status: DAPI<GO> in Terminal")
        print("  3. Verify securities are valid Bloomberg tickers")
        print("  4. Check network connection")
        return 1

    return 0


if __name__ == "__main__":
    sys.exit(main())
