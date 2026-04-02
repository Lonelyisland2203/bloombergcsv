"""
Price History Extraction Demo

This script demonstrates how to extract daily adjusted price history
for activist campaign targets, including:
    - 6 months pre-entry context
    - Campaign period through exit/present
    - Derived metrics (days_since_entry, cumulative_return)
    - Summary statistics

Usage:
    python examples/price_history_demo.py

Requirements:
    - Bloomberg Terminal running and logged in
    - Bloomberg DAPI installed
    - Active Bloomberg session

Author: Bloomberg Activist Pipeline
"""

import sys
from datetime import date
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from bloomberg_session import BloombergSession
from extract_price_history import PriceHistoryTarget, PriceHistoryExtractor


def main():
    """Demonstrate price history extraction for Effissimo campaigns."""

    print("=" * 80)
    print("Price History Extraction Demo")
    print("=" * 80)

    # Define sample activist campaigns
    campaigns = [
        PriceHistoryTarget(
            ticker="8136 JP Equity",  # Sanrio
            campaign_start=date(2021, 6, 14),
            campaign_end=None,  # Ongoing
        ),
        PriceHistoryTarget(
            ticker="9107 JP Equity",  # Kawasaki Kisen Kaisha
            campaign_start=date(2020, 11, 13),
            campaign_end=date(2023, 4, 7),
        ),
        PriceHistoryTarget(
            ticker="8952 JP Equity",  # Japan Real Estate Investment
            campaign_start=date(2018, 5, 15),
            campaign_end=date(2019, 8, 14),
        ),
    ]

    print(f"\nExtracting price history for {len(campaigns)} campaigns")
    print("-" * 80)

    # Initialize Bloomberg session
    print("\n1. Connecting to Bloomberg...")
    with BloombergSession() as session:
        print("   Connected successfully!")

        # Create extractor
        extractor = PriceHistoryExtractor(session)

        # Extract price history for each campaign
        print("\n2. Extracting price histories...")

        for i, target in enumerate(campaigns, 1):
            print(f"\n   Campaign {i}: {target.ticker}")
            print(f"   Entry: {target.campaign_start}")
            print(f"   Exit:  {target.campaign_end or 'Ongoing'}")

            try:
                # Extract campaign price history
                price_df = extractor.extract_campaign_price_history(target)

                if price_df.empty:
                    print(f"   WARNING: No price data available")
                    continue

                print(f"   Retrieved {len(price_df)} trading days")
                print(f"   Entry price: {target.entry_price:.2f}")

                # Compute summary statistics
                stats = extractor.compute_summary_statistics(price_df)

                print(f"\n   Performance Metrics:")
                print(f"   - Total return:    {stats['total_return']:>8.2%}")
                print(f"   - Max return:      {stats['max_return']:>8.2%}")
                print(f"   - Min return:      {stats['min_return']:>8.2%}")
                print(f"   - Volatility:      {stats['volatility']:>8.2%}")
                print(f"   - Avg volume:      {stats['avg_volume']:>8,.0f}")
                print(f"   - Trading days:    {stats['total_trading_days']:>8,}")

                # Show sample data
                print(f"\n   Sample Price Data (first 5 days):")
                print(price_df[["date", "adjusted_close", "volume", "cumulative_return"]].head())

            except Exception as e:
                print(f"   ERROR: {e}")
                continue

        # Extract all campaigns at once
        print("\n3. Batch extraction for all campaigns...")

        try:
            all_prices_df = extractor.extract_multiple_campaigns(campaigns)

            print(f"   Retrieved {len(all_prices_df)} total records")
            print(f"   Campaigns: {all_prices_df['ticker'].nunique()}")

            # Show summary by ticker
            print("\n   Records by ticker:")
            for ticker, group in all_prices_df.groupby("ticker"):
                print(f"   - {ticker}: {len(group)} days")

        except Exception as e:
            print(f"   ERROR: {e}")

    print("\n" + "=" * 80)
    print("Demo Complete!")
    print("=" * 80)


if __name__ == "__main__":
    main()
