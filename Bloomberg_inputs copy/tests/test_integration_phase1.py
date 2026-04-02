"""
Integration Tests for Phase 1: Ticker Conversion & Fiscal Alignment

Tests the complete Phase 1 functionality using actual Effissimo campaign data.
Validates end-to-end conversion and alignment for all 30 target companies.

Test Coverage:
- CSV data loading and parsing
- Ticker conversion for all 30 companies
- Fiscal alignment for actual campaign dates
- Output format validation
"""

import pytest
import pandas as pd
import sys
from pathlib import Path
from datetime import date

# Add src directory to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from ticker_converter import convert_ticker, validate_tse_ticker
from fiscal_period_aligner import (
    compute_snapshot_date,
    construct_fund_per_override,
    compute_campaign_fiscal_alignment,
)


class TestEffissimoCSVIntegration:
    """Test integration with actual Effissimo CSV data."""

    @pytest.fixture
    def effissimo_data(self):
        """Load Effissimo campaign CSV data."""
        csv_path = Path(__file__).parent.parent / "effissimo_summary_by_company.csv"
        df = pd.read_csv(csv_path)
        # Parse dates
        df['first_filing'] = pd.to_datetime(df['first_filing']).dt.date
        df['last_filing'] = pd.to_datetime(df['last_filing']).dt.date
        return df

    def test_csv_loaded_successfully(self, effissimo_data):
        """Verify CSV loads with expected structure."""
        assert len(effissimo_data) == 30, "Expected 30 Effissimo target companies"
        assert 'target_ticker' in effissimo_data.columns
        assert 'first_filing' in effissimo_data.columns

    def test_all_tickers_valid_format(self, effissimo_data):
        """Verify all tickers in CSV are valid TSE .T format."""
        for idx, row in effissimo_data.iterrows():
            ticker = row['target_ticker']
            assert validate_tse_ticker(ticker), (
                f"Invalid ticker format at row {idx}: {ticker}"
            )

    def test_all_tickers_convert(self, effissimo_data):
        """Test that all 30 Effissimo tickers convert successfully."""
        for idx, row in effissimo_data.iterrows():
            tse_ticker = row['target_ticker']
            bloomberg_ticker = convert_ticker(tse_ticker)

            # Verify Bloomberg format
            assert bloomberg_ticker.endswith(" JP Equity"), (
                f"Row {idx}: Invalid Bloomberg format: {bloomberg_ticker}"
            )

            # Verify code preserved
            expected_code = tse_ticker[:-2]  # Remove .T
            assert bloomberg_ticker.startswith(expected_code), (
                f"Row {idx}: Code mismatch for {tse_ticker} -> {bloomberg_ticker}"
            )

    def test_fiscal_alignment_for_campaigns(self, effissimo_data):
        """Test fiscal alignment for each campaign (assuming March 31 FYE)."""
        # Most Japanese companies have March 31 FYE
        fye_month = 3

        for idx, row in effissimo_data.iterrows():
            campaign_start = row['first_filing']
            company_name = row['target_company']

            # Compute fiscal alignment
            snapshot_date = compute_snapshot_date(campaign_start, fye_month)
            fund_per = construct_fund_per_override(snapshot_date)

            # Verify snapshot is before campaign start
            assert snapshot_date < campaign_start, (
                f"{company_name}: Snapshot {snapshot_date} is not before "
                f"campaign start {campaign_start} (TEMPORAL VIOLATION)"
            )

            # Verify FUND_PER format
            assert fund_per.startswith("FY"), (
                f"{company_name}: Invalid FUND_PER format: {fund_per}"
            )
            assert len(fund_per) == 6, (
                f"{company_name}: FUND_PER should be 6 characters: {fund_per}"
            )

    def test_kawasaki_kisen_specific(self, effissimo_data):
        """Test specific alignment for Kawasaki Kisen (first campaign)."""
        # Kawasaki Kisen: First filing 2021-06-14
        kk = effissimo_data[effissimo_data['target_ticker'] == '9107.T'].iloc[0]

        tse_ticker = kk['target_ticker']
        campaign_start = kk['first_filing']

        # Convert ticker
        bloomberg_ticker = convert_ticker(tse_ticker)
        assert bloomberg_ticker == "9107 JP Equity"

        # Compute fiscal alignment (March 31 FYE)
        snapshot, fund_per, (fy_start, fy_end) = compute_campaign_fiscal_alignment(
            campaign_start, 3
        )

        # Campaign started 2021-06-14, more than 60 days after March 31, 2021
        # → Should use FY2021
        assert snapshot == date(2021, 3, 31)
        assert fund_per == "FY2021"
        assert fy_start == date(2020, 4, 1)
        assert fy_end == date(2021, 3, 31)

    def test_lifenet_insurance_specific(self, effissimo_data):
        """Test specific alignment for Lifenet Insurance (edge case)."""
        # Lifenet Insurance: First filing 2021-04-06 (within 60-day buffer)
        lifenet = effissimo_data[effissimo_data['target_ticker'] == '7157.T'].iloc[0]

        tse_ticker = lifenet['target_ticker']
        campaign_start = lifenet['first_filing']

        # Convert ticker
        bloomberg_ticker = convert_ticker(tse_ticker)
        assert bloomberg_ticker == "7157 JP Equity"

        # Compute fiscal alignment (March 31 FYE)
        snapshot, fund_per, _ = compute_campaign_fiscal_alignment(campaign_start, 3)

        # Campaign started 2021-04-06, only 6 days after March 31, 2021
        # → Within 60-day buffer, should use FY2020
        assert snapshot == date(2020, 3, 31)
        assert fund_per == "FY2020"

    def test_output_format_for_all_campaigns(self, effissimo_data):
        """Test that output format is consistent for all campaigns."""
        fye_month = 3
        results = []

        for idx, row in effissimo_data.iterrows():
            tse_ticker = row['target_ticker']
            campaign_start = row['first_filing']

            # Convert and align
            bloomberg_ticker = convert_ticker(tse_ticker)
            snapshot, fund_per, (fy_start, fy_end) = compute_campaign_fiscal_alignment(
                campaign_start, fye_month
            )

            results.append({
                'tse_ticker': tse_ticker,
                'bloomberg_ticker': bloomberg_ticker,
                'campaign_start': campaign_start,
                'snapshot_date': snapshot,
                'fund_per': fund_per,
                'fy_start': fy_start,
                'fy_end': fy_end,
            })

        # Verify all results have expected fields
        assert len(results) == 30
        for result in results:
            assert result['bloomberg_ticker'].endswith(' JP Equity')
            assert result['fund_per'].startswith('FY')
            assert result['snapshot_date'] < result['campaign_start']
            assert result['fy_start'] < result['fy_end']


class TestEdgeCasesWithRealData:
    """Test edge cases using real campaign dates."""

    def test_campaigns_in_april(self):
        """Test campaigns starting in April (potential buffer zone)."""
        # Multiple campaigns started in April 2021
        april_campaigns = [
            ('7157.T', date(2021, 4, 6)),   # Lifenet (6 days after March FYE)
            ('6707.T', date(2021, 4, 7)),   # Sanken (7 days after)
            ('5741.T', date(2021, 4, 6)),   # UACJ (6 days after)
            ('1813.T', date(2021, 4, 21)),  # Fudo Tetra (21 days after)
        ]

        for tse_ticker, campaign_start in april_campaigns:
            bloomberg = convert_ticker(tse_ticker)
            snapshot = compute_snapshot_date(campaign_start, 3)

            # All these are within 60-day buffer → should use FY2020
            assert snapshot == date(2020, 3, 31), (
                f"{tse_ticker}: Expected FY2020 for April campaign, got {snapshot}"
            )

    def test_campaigns_in_june_july(self):
        """Test campaigns after 60-day buffer expires."""
        # Campaigns in June/July (well after March FYE)
        later_campaigns = [
            ('9107.T', date(2021, 6, 14)),  # Kawasaki Kisen (75 days after)
        ]

        for tse_ticker, campaign_start in later_campaigns:
            bloomberg = convert_ticker(tse_ticker)
            snapshot = compute_snapshot_date(campaign_start, 3)

            # After 60-day buffer → should use FY2021
            assert snapshot == date(2021, 3, 31), (
                f"{tse_ticker}: Expected FY2021 for June campaign, got {snapshot}"
            )


class TestPointInTimeSafetyWithRealData:
    """Verify point-in-time safety using real campaign data."""

    def test_no_future_snapshots(self):
        """Verify no snapshot dates are after their campaign start."""
        # Load CSV
        csv_path = Path(__file__).parent.parent / "effissimo_summary_by_company.csv"
        df = pd.read_csv(csv_path)
        df['first_filing'] = pd.to_datetime(df['first_filing']).dt.date

        fye_month = 3
        violations = []

        for idx, row in df.iterrows():
            campaign_start = row['first_filing']
            snapshot = compute_snapshot_date(campaign_start, fye_month)

            if snapshot >= campaign_start:
                violations.append({
                    'ticker': row['target_ticker'],
                    'campaign_start': campaign_start,
                    'snapshot': snapshot,
                })

        assert len(violations) == 0, (
            f"TEMPORAL VIOLATIONS DETECTED: {len(violations)} campaigns have "
            f"snapshot dates on or after campaign start:\n" +
            "\n".join([f"  {v['ticker']}: {v['campaign_start']} -> {v['snapshot']}"
                      for v in violations])
        )


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
