"""
Peer Comparisons Extraction Demo

This script demonstrates how to compute sector peer comparisons
for activist campaign targets, including:
    - GICS sector identification
    - Sector median valuation metrics
    - Discount/premium calculations
    - ROE performance vs. sector

Usage:
    python examples/peer_comps_demo.py

Requirements:
    - Bloomberg Terminal running and logged in
    - Bloomberg DAPI installed
    - Active Bloomberg session
    - Snapshot data for target companies

Author: Bloomberg Activist Pipeline
"""

import sys
from pathlib import Path

# Add src to path
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

import pandas as pd
from bloomberg_session import BloombergSession
from extract_peer_comps import PeerCompTarget, PeerCompsExtractor


def main():
    """Demonstrate peer comparison extraction for Effissimo campaigns."""

    print("=" * 80)
    print("Peer Comparisons Extraction Demo")
    print("=" * 80)

    # Define sample activist campaign targets
    targets = [
        PeerCompTarget(
            ticker="8136 JP Equity",
            company_name="Sanrio Co Ltd",
        ),
        PeerCompTarget(
            ticker="9107 JP Equity",
            company_name="Kawasaki Kisen Kaisha Ltd",
        ),
        PeerCompTarget(
            ticker="8952 JP Equity",
            company_name="Japan Real Estate Investment Corp",
        ),
    ]

    print(f"\nAnalyzing peer comparisons for {len(targets)} companies")
    print("-" * 80)

    # Create sample snapshot data
    # In production, this would come from extract_snapshot.py
    snapshot_df = pd.DataFrame(
        {
            "security": [t.ticker for t in targets],
            "PX_TO_BOOK_RATIO": [2.5, 0.8, 1.2],
            "RETURN_COM_EQY": [15.0, 8.5, 10.2],
            "CUR_MKT_CAP": [200000, 100000, 500000],
            "NET_DEBT": [-30000, 50000, 100000],
            "EBITDA": [25000, 10000, 50000],
        }
    )

    print("\nSnapshot Data:")
    print(snapshot_df.to_string(index=False))

    # Initialize Bloomberg session
    print("\n1. Connecting to Bloomberg...")
    with BloombergSession() as session:
        print("   Connected successfully!")

        # Create extractor
        extractor = PeerCompsExtractor(session, min_peer_count=5)

        # Step 1: Identify sectors
        print("\n2. Identifying GICS sectors...")

        for target in targets:
            sector, industry = extractor.identify_sector(target.ticker)
            target.sector = sector
            target.industry_group = industry

            print(f"   {target.ticker}:")
            print(f"   - Sector:         {sector or 'N/A'}")
            print(f"   - Industry Group: {industry or 'N/A'}")

        # Step 2: Extract peer comparisons
        print("\n3. Computing peer comparisons...")

        try:
            peer_comps_df = extractor.extract_peer_comps(targets, snapshot_df)

            if peer_comps_df.empty:
                print("   WARNING: No peer comparison data generated")
                return

            print(f"   Generated {len(peer_comps_df)} peer comparison records")

            # Display results
            print("\n4. Peer Comparison Results:")
            print("=" * 80)

            for _, row in peer_comps_df.iterrows():
                print(f"\n   Company: {row['company_name']} ({row['ticker']})")
                print(f"   Sector:  {row['sector']}")
                print(f"   Peers:   {row['peer_count']} companies")
                print()

                # PBR comparison
                if pd.notna(row["company_pbr"]) and pd.notna(row["sector_median_pbr"]):
                    print(f"   Price-to-Book Ratio:")
                    print(f"   - Company:        {row['company_pbr']:>8.2f}")
                    print(f"   - Sector Median:  {row['sector_median_pbr']:>8.2f}")
                    if pd.notna(row["pbr_vs_sector"]):
                        discount_text = (
                            "discount" if row["pbr_vs_sector"] < 0 else "premium"
                        )
                        print(
                            f"   - vs. Sector:     {row['pbr_vs_sector']:>8.2%} {discount_text}"
                        )
                else:
                    print(f"   Price-to-Book Ratio: N/A")

                print()

                # ROE comparison
                if pd.notna(row["company_roe"]) and pd.notna(row["sector_median_roe"]):
                    print(f"   Return on Equity:")
                    print(f"   - Company:        {row['company_roe']:>8.2f}%")
                    print(f"   - Sector Median:  {row['sector_median_roe']:>8.2f}%")
                    if pd.notna(row["roe_vs_sector"]):
                        performance_text = (
                            "below sector" if row["roe_vs_sector"] < 0 else "above sector"
                        )
                        print(
                            f"   - vs. Sector:     {row['roe_vs_sector']:>8.2f} pp {performance_text}"
                        )
                else:
                    print(f"   Return on Equity: N/A")

                print()

                # EV/EBITDA comparison
                if pd.notna(row["company_ev_ebitda"]) and pd.notna(
                    row["sector_median_ev_ebitda"]
                ):
                    print(f"   EV/EBITDA Multiple:")
                    print(f"   - Company:        {row['company_ev_ebitda']:>8.2f}x")
                    print(
                        f"   - Sector Median:  {row['sector_median_ev_ebitda']:>8.2f}x"
                    )
                    if pd.notna(row["ev_ebitda_vs_sector"]):
                        discount_text = (
                            "discount" if row["ev_ebitda_vs_sector"] < 0 else "premium"
                        )
                        print(
                            f"   - vs. Sector:     {row['ev_ebitda_vs_sector']:>8.2%} {discount_text}"
                        )
                else:
                    print(f"   EV/EBITDA Multiple: N/A")

                print("-" * 80)

            # Summary statistics
            print("\n5. Summary Statistics:")

            avg_pbr_discount = peer_comps_df["pbr_vs_sector"].mean()
            avg_roe_diff = peer_comps_df["roe_vs_sector"].mean()

            print(f"   Average PBR vs. Sector:  {avg_pbr_discount:>8.2%}")
            print(f"   Average ROE vs. Sector:  {avg_roe_diff:>8.2f} pp")

            # Count companies at discount
            pbr_at_discount = (peer_comps_df["pbr_vs_sector"] < 0).sum()
            print(
                f"   Companies at PBR discount: {pbr_at_discount}/{len(peer_comps_df)}"
            )

            roe_below_sector = (peer_comps_df["roe_vs_sector"] < 0).sum()
            print(f"   Companies below sector ROE: {roe_below_sector}/{len(peer_comps_df)}")

        except Exception as e:
            print(f"   ERROR: {e}")
            import traceback

            traceback.print_exc()

    print("\n" + "=" * 80)
    print("Demo Complete!")
    print("=" * 80)
    print(
        "\nNOTE: This demo uses placeholder sector peer data. "
        "In production, sector peers"
    )
    print(
        "      would be retrieved via Bloomberg EQS screening for all companies in GICS sector."
    )


if __name__ == "__main__":
    main()
