"""
Unit Tests for Snapshot Extractor

Test Coverage:
    1. CampaignTarget dataclass validation
    2. Fiscal metadata enrichment
    3. Field extraction by override type
    4. Derived field calculations
    5. Data quality scoring
    6. Point-in-time safety validation
    7. Missing data handling
    8. Gap report generation

Point-in-Time Test Cases:
    - Verify snapshot_date < campaign_start for all companies
    - Verify FUND_PER override corresponds to correct fiscal year
    - Verify no forward-looking data leakage

Author: Bloomberg Activist Pipeline
"""

import unittest
from datetime import date, datetime
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
from io import StringIO

import pandas as pd
import numpy as np

import sys

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from extract_snapshot import (
    CampaignTarget,
    FieldGapEntry,
    SnapshotExtractor,
    validate_point_in_time_safety,
)


class TestCampaignTarget(unittest.TestCase):
    """Test CampaignTarget dataclass validation."""

    def test_valid_campaign_target(self):
        """Test creation of valid campaign target."""
        campaign = CampaignTarget(
            company_name_japanese="株式会社サンリオ",
            company_name_english="Sanrio Co Ltd",
            tse_ticker="8136.T",
            bloomberg_ticker="8136 JP Equity",
            campaign_start=date(2021, 6, 14),
            campaign_end=None,
            max_ownership_pct=9.84,
            min_ownership_pct=5.01,
            total_filings=12,
        )

        self.assertEqual(campaign.company_name_japanese, "株式会社サンリオ")
        self.assertEqual(campaign.bloomberg_ticker, "8136 JP Equity")
        self.assertIsNone(campaign.campaign_end)

    def test_invalid_ownership_percentages(self):
        """Test validation of ownership percentages."""
        # Max ownership > 100
        with self.assertRaises(ValueError):
            CampaignTarget(
                company_name_japanese="Test",
                company_name_english=None,
                tse_ticker="1234.T",
                bloomberg_ticker="1234 JP Equity",
                campaign_start=date(2021, 1, 1),
                campaign_end=None,
                max_ownership_pct=150.0,
                min_ownership_pct=5.0,
                total_filings=1,
            )

        # Min ownership < 0
        with self.assertRaises(ValueError):
            CampaignTarget(
                company_name_japanese="Test",
                company_name_english=None,
                tse_ticker="1234.T",
                bloomberg_ticker="1234 JP Equity",
                campaign_start=date(2021, 1, 1),
                campaign_end=None,
                max_ownership_pct=10.0,
                min_ownership_pct=-5.0,
                total_filings=1,
            )

        # Min > Max
        with self.assertRaises(ValueError):
            CampaignTarget(
                company_name_japanese="Test",
                company_name_english=None,
                tse_ticker="1234.T",
                bloomberg_ticker="1234 JP Equity",
                campaign_start=date(2021, 1, 1),
                campaign_end=None,
                max_ownership_pct=5.0,
                min_ownership_pct=10.0,
                total_filings=1,
            )

    def test_invalid_campaign_dates(self):
        """Test validation of campaign date sequence."""
        # Campaign end before start
        with self.assertRaises(ValueError):
            CampaignTarget(
                company_name_japanese="Test",
                company_name_english=None,
                tse_ticker="1234.T",
                bloomberg_ticker="1234 JP Equity",
                campaign_start=date(2021, 6, 1),
                campaign_end=date(2021, 1, 1),
                max_ownership_pct=10.0,
                min_ownership_pct=5.0,
                total_filings=1,
            )

    def test_point_in_time_violation_in_dataclass(self):
        """Test that snapshot_date >= campaign_start raises error."""
        # Snapshot date after campaign start
        with self.assertRaises(ValueError) as context:
            CampaignTarget(
                company_name_japanese="Test",
                company_name_english=None,
                tse_ticker="1234.T",
                bloomberg_ticker="1234 JP Equity",
                campaign_start=date(2021, 6, 1),
                campaign_end=None,
                max_ownership_pct=10.0,
                min_ownership_pct=5.0,
                total_filings=1,
                snapshot_date=date(2021, 6, 15),  # After campaign start!
            )

        self.assertIn("Point-in-time violation", str(context.exception))

    def test_valid_snapshot_date(self):
        """Test that snapshot_date before campaign_start is valid."""
        campaign = CampaignTarget(
            company_name_japanese="Test",
            company_name_english=None,
            tse_ticker="1234.T",
            bloomberg_ticker="1234 JP Equity",
            campaign_start=date(2021, 6, 1),
            campaign_end=None,
            max_ownership_pct=10.0,
            min_ownership_pct=5.0,
            total_filings=1,
            snapshot_date=date(2021, 3, 31),  # Before campaign start
        )

        self.assertEqual(campaign.snapshot_date, date(2021, 3, 31))


class TestFieldGapEntry(unittest.TestCase):
    """Test FieldGapEntry dataclass."""

    def test_field_gap_entry_creation(self):
        """Test creation of field gap entry."""
        gap = FieldGapEntry(
            ticker="8136 JP Equity",
            field_name="BEST_PE_RATIO",
            error_message="Field not available",
            bloomberg_error_code="N/A",
        )

        self.assertEqual(gap.ticker, "8136 JP Equity")
        self.assertEqual(gap.field_name, "BEST_PE_RATIO")
        self.assertIsNotNone(gap.timestamp)

    def test_timestamp_auto_generation(self):
        """Test that timestamp is auto-generated if not provided."""
        gap = FieldGapEntry(
            ticker="8136 JP Equity",
            field_name="BEST_PE_RATIO",
            error_message="Field not available",
        )

        # Timestamp should be ISO format string
        self.assertIsInstance(gap.timestamp, str)
        # Should be parseable as datetime
        datetime.fromisoformat(gap.timestamp)


class TestSnapshotExtractor(unittest.TestCase):
    """Test SnapshotExtractor class."""

    def setUp(self):
        """Set up test fixtures."""
        # Mock Bloomberg session
        self.mock_session = MagicMock()

        # Mock batching engine
        self.mock_batching_engine = MagicMock()

        # Create temporary logs directory
        self.test_logs_dir = Path("/tmp/bloomberg_test_logs")
        self.test_logs_dir.mkdir(exist_ok=True)

        # Initialize extractor
        self.extractor = SnapshotExtractor(
            session=self.mock_session,
            batching_engine=self.mock_batching_engine,
            logs_dir=self.test_logs_dir,
        )

    def tearDown(self):
        """Clean up test artifacts."""
        # Remove test logs
        if self.test_logs_dir.exists():
            for file in self.test_logs_dir.glob("*.json"):
                file.unlink()
            self.test_logs_dir.rmdir()

    def test_extractor_initialization(self):
        """Test SnapshotExtractor initialization."""
        self.assertIsNotNone(self.extractor.session)
        self.assertIsNotNone(self.extractor.batching_engine)
        self.assertTrue(self.extractor.logs_dir.exists())

    def test_enrich_fiscal_metadata(self):
        """Test fiscal metadata enrichment."""
        # Create sample campaigns
        campaigns = [
            CampaignTarget(
                company_name_japanese="サンリオ",
                company_name_english="Sanrio",
                tse_ticker="8136.T",
                bloomberg_ticker="8136 JP Equity",
                campaign_start=date(2021, 6, 14),
                campaign_end=None,
                max_ownership_pct=9.84,
                min_ownership_pct=5.01,
                total_filings=12,
            )
        ]

        # Mock fiscal year-end response
        fye_df = pd.DataFrame(
            {
                "security": ["8136 JP Equity"],
                "FISCAL_YEAR_END_MONTH_DE": [3],  # March FYE
            }
        )
        self.mock_session.send_request.return_value = fye_df

        # Enrich fiscal metadata
        self.extractor._enrich_fiscal_metadata(campaigns)

        # Verify fiscal metadata was computed
        campaign = campaigns[0]
        self.assertEqual(campaign.fye_month, 3)
        self.assertIsNotNone(campaign.snapshot_date)
        self.assertIsNotNone(campaign.fund_per_override)

        # Verify point-in-time safety
        self.assertLess(campaign.snapshot_date, campaign.campaign_start)

        # Verify FUND_PER override format
        self.assertTrue(campaign.fund_per_override.startswith("FY"))

    def test_compute_derived_fields(self):
        """Test derived field calculations."""
        # Create sample DataFrame
        df = pd.DataFrame(
            {
                "security": ["8136 JP Equity", "9107 JP Equity"],
                "BS_CASH_NEAR_CASH_ITEM": [100_000, 50_000],
                "BS_MKT_SEC_OTHER_ST_INVEST": [20_000, 10_000],
                "SHORT_AND_LONG_TERM_DEBT": [30_000, 40_000],
                "CUR_MKT_CAP": [200_000, 100_000],
            }
        )

        # Compute derived fields
        result_df = self.extractor.compute_derived_fields(df)

        # Verify net_cash calculation
        # 8136: 100,000 + 20,000 - 30,000 = 90,000
        # 9107: 50,000 + 10,000 - 40,000 = 20,000
        self.assertEqual(result_df.loc[0, "net_cash"], 90_000)
        self.assertEqual(result_df.loc[1, "net_cash"], 20_000)

        # Verify net_cash_to_market_cap calculation
        # 8136: 90,000 / 200,000 = 0.45
        # 9107: 20,000 / 100,000 = 0.20
        self.assertAlmostEqual(
            result_df.loc[0, "net_cash_to_market_cap"], 0.45, places=5
        )
        self.assertAlmostEqual(
            result_df.loc[1, "net_cash_to_market_cap"], 0.20, places=5
        )

    def test_compute_derived_fields_with_nulls(self):
        """Test derived field calculations with missing data."""
        # Create DataFrame with null values
        df = pd.DataFrame(
            {
                "security": ["8136 JP Equity"],
                "BS_CASH_NEAR_CASH_ITEM": [np.nan],
                "BS_MKT_SEC_OTHER_ST_INVEST": [20_000],
                "SHORT_AND_LONG_TERM_DEBT": [30_000],
                "CUR_MKT_CAP": [200_000],
            }
        )

        # Compute derived fields
        result_df = self.extractor.compute_derived_fields(df)

        # With NaN in cash, net_cash should be computed using 0 for NaN
        # 0 + 20,000 - 30,000 = -10,000
        self.assertEqual(result_df.loc[0, "net_cash"], -10_000)

    def test_compute_derived_fields_division_by_zero(self):
        """Test derived field calculations with zero market cap."""
        # Create DataFrame with zero market cap
        df = pd.DataFrame(
            {
                "security": ["8136 JP Equity"],
                "BS_CASH_NEAR_CASH_ITEM": [100_000],
                "BS_MKT_SEC_OTHER_ST_INVEST": [20_000],
                "SHORT_AND_LONG_TERM_DEBT": [30_000],
                "CUR_MKT_CAP": [0],  # Zero market cap
            }
        )

        # Compute derived fields
        result_df = self.extractor.compute_derived_fields(df)

        # With zero market cap, net_cash_to_market_cap should be NaN
        self.assertTrue(pd.isna(result_df.loc[0, "net_cash_to_market_cap"]))

    def test_compute_data_quality_scores(self):
        """Test data quality score computation."""
        # Create sample DataFrame with varying data quality
        df = pd.DataFrame(
            {
                "security": ["8136 JP Equity", "9107 JP Equity", "1234 JP Equity"],
                # Critical fields
                "PX_TO_BOOK_RATIO": [0.8, 1.2, np.nan],
                "RETURN_COM_EQY": [12.5, np.nan, np.nan],
                "CUR_MKT_CAP": [200_000, 100_000, 50_000],
                "NET_DEBT": [-50_000, 20_000, np.nan],
                "TRAIL_12M_SALES": [150_000, np.nan, np.nan],
            }
        )

        # Compute quality scores
        result_df = self.extractor._compute_data_quality_scores(df)

        # 8136: 5/5 critical fields = 100%
        self.assertEqual(result_df.loc[0, "data_quality_score"], 100.0)
        self.assertFalse(result_df.loc[0, "manual_review_flag"])

        # 9107: 3/5 critical fields = 60% (should be flagged)
        self.assertEqual(result_df.loc[1, "data_quality_score"], 60.0)
        self.assertTrue(result_df.loc[1, "manual_review_flag"])

        # 1234: 1/5 critical fields = 20% (should be flagged)
        self.assertEqual(result_df.loc[2, "data_quality_score"], 20.0)
        self.assertTrue(result_df.loc[2, "manual_review_flag"])

    def test_log_field_gaps(self):
        """Test field gap reporting."""
        # Create sample DataFrame with missing data
        df = pd.DataFrame(
            {
                "security": ["8136 JP Equity", "9107 JP Equity"],
                "company_name_japanese": ["サンリオ", "川崎汽船"],
                "PX_TO_BOOK_RATIO": [0.8, np.nan],
                "RETURN_COM_EQY": [12.5, 8.3],
                "CUR_MKT_CAP": [200_000, 100_000],
                "BEST_PE_RATIO": [np.nan, np.nan],
                "data_quality_score": [100.0, 80.0],
                "manual_review_flag": [False, False],
            }
        )

        # Generate gap report
        gap_report = self.extractor.log_field_gaps(df)

        # Verify gap report structure
        self.assertIn("timestamp", gap_report)
        self.assertIn("total_securities", gap_report)
        self.assertIn("total_fields", gap_report)
        self.assertIn("field_coverage", gap_report)
        self.assertIn("security_coverage", gap_report)
        self.assertIn("missing_data", gap_report)

        # Verify statistics
        self.assertEqual(gap_report["total_securities"], 2)
        self.assertEqual(gap_report["total_fields"], 4)  # Excludes metadata

        # Verify field coverage
        self.assertEqual(
            gap_report["field_coverage"]["PX_TO_BOOK_RATIO"]["count"], 1
        )
        self.assertEqual(
            gap_report["field_coverage"]["BEST_PE_RATIO"]["count"], 0
        )

        # Verify missing data entries
        missing_entries = gap_report["missing_data"]
        self.assertEqual(len(missing_entries), 3)  # 1 + 2 missing values

    def test_save_gap_report(self):
        """Test gap report JSON file creation."""
        # Create sample gap report
        gap_report = {
            "timestamp": datetime.now().isoformat(),
            "total_securities": 2,
            "total_fields": 10,
            "field_coverage": {},
            "security_coverage": {},
            "missing_data": [],
        }

        # Save gap report
        filepath = self.extractor._save_gap_report(gap_report)

        # Verify file exists
        self.assertTrue(filepath.exists())

        # Verify file name format
        self.assertTrue(filepath.name.startswith("snapshot_gaps_"))
        self.assertTrue(filepath.name.endswith(".json"))

        # Verify file contents
        import json

        with open(filepath, "r") as f:
            loaded_report = json.load(f)

        self.assertEqual(loaded_report["total_securities"], 2)


class TestPointInTimeSafety(unittest.TestCase):
    """Test point-in-time safety validation."""

    def test_validate_point_in_time_safety_valid(self):
        """Test validation of valid campaigns."""
        campaigns = [
            CampaignTarget(
                company_name_japanese="サンリオ",
                company_name_english="Sanrio",
                tse_ticker="8136.T",
                bloomberg_ticker="8136 JP Equity",
                campaign_start=date(2021, 6, 14),
                campaign_end=None,
                max_ownership_pct=9.84,
                min_ownership_pct=5.01,
                total_filings=12,
                snapshot_date=date(2021, 3, 31),  # Before campaign start
                fund_per_override="FY2021",
            )
        ]

        # Should not raise exception
        result = validate_point_in_time_safety(campaigns)
        self.assertTrue(result)

    def test_validate_point_in_time_safety_violation(self):
        """Test validation catches temporal violations."""
        # Note: CampaignTarget.__post_init__ will catch this in dataclass creation,
        # so we need to create a campaign that bypasses validation initially,
        # then test the validator function

        # Create a valid campaign first
        campaign = CampaignTarget(
            company_name_japanese="サンリオ",
            company_name_english="Sanrio",
            tse_ticker="8136.T",
            bloomberg_ticker="8136 JP Equity",
            campaign_start=date(2021, 6, 14),
            campaign_end=None,
            max_ownership_pct=9.84,
            min_ownership_pct=5.01,
            total_filings=12,
            snapshot_date=date(2021, 3, 31),  # Initially valid
            fund_per_override="FY2021",
        )

        # Manually modify snapshot_date to create violation
        # (simulates a bug in fiscal alignment logic)
        campaign.snapshot_date = date(2021, 6, 30)  # After campaign start!

        campaigns = [campaign]

        # Should raise ValueError
        with self.assertRaises(ValueError) as context:
            validate_point_in_time_safety(campaigns)

        self.assertIn("Point-in-time violations", str(context.exception))

    def test_validate_point_in_time_safety_missing_snapshot(self):
        """Test validation catches missing snapshot dates."""
        campaigns = [
            CampaignTarget(
                company_name_japanese="サンリオ",
                company_name_english="Sanrio",
                tse_ticker="8136.T",
                bloomberg_ticker="8136 JP Equity",
                campaign_start=date(2021, 6, 14),
                campaign_end=None,
                max_ownership_pct=9.84,
                min_ownership_pct=5.01,
                total_filings=12,
                snapshot_date=None,  # Missing!
            )
        ]

        # Should raise ValueError
        with self.assertRaises(ValueError) as context:
            validate_point_in_time_safety(campaigns)

        self.assertIn("snapshot_date is None", str(context.exception))


class TestDerivedFieldEdgeCases(unittest.TestCase):
    """Test edge cases in derived field calculations."""

    def setUp(self):
        """Set up test extractor."""
        mock_session = MagicMock()
        mock_batching_engine = MagicMock()
        self.extractor = SnapshotExtractor(
            session=mock_session,
            batching_engine=mock_batching_engine,
        )

    def test_extreme_net_cash_ratios(self):
        """Test handling of extreme net cash to market cap ratios."""
        # Create DataFrame with extreme ratio (net cash > market cap)
        df = pd.DataFrame(
            {
                "security": ["8136 JP Equity"],
                "BS_CASH_NEAR_CASH_ITEM": [200_000],
                "BS_MKT_SEC_OTHER_ST_INVEST": [50_000],
                "SHORT_AND_LONG_TERM_DEBT": [10_000],
                "CUR_MKT_CAP": [100_000],  # Market cap < net cash
            }
        )

        # Should not crash, should log warning
        result_df = self.extractor.compute_derived_fields(df)

        # Net cash = 200,000 + 50,000 - 10,000 = 240,000
        # Ratio = 240,000 / 100,000 = 2.4 (240%)
        self.assertEqual(result_df.loc[0, "net_cash"], 240_000)
        self.assertAlmostEqual(
            result_df.loc[0, "net_cash_to_market_cap"], 2.4, places=5
        )

    def test_negative_net_cash(self):
        """Test handling of negative net cash (net debt position)."""
        # Create DataFrame with high debt
        df = pd.DataFrame(
            {
                "security": ["8136 JP Equity"],
                "BS_CASH_NEAR_CASH_ITEM": [10_000],
                "BS_MKT_SEC_OTHER_ST_INVEST": [5_000],
                "SHORT_AND_LONG_TERM_DEBT": [100_000],
                "CUR_MKT_CAP": [200_000],
            }
        )

        result_df = self.extractor.compute_derived_fields(df)

        # Net cash = 10,000 + 5,000 - 100,000 = -85,000
        self.assertEqual(result_df.loc[0, "net_cash"], -85_000)

        # Ratio = -85,000 / 200,000 = -0.425 (-42.5%)
        self.assertAlmostEqual(
            result_df.loc[0, "net_cash_to_market_cap"], -0.425, places=5
        )


if __name__ == "__main__":
    unittest.main()
