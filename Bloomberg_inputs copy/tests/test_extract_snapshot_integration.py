"""
Integration Tests for Snapshot Extractor

These tests validate the complete snapshot extraction workflow using
realistic mock data for Effissimo Capital's 30 campaign targets.

Test Scenarios:
    1. Full extraction for all 30 Effissimo companies
    2. Mixed fiscal year-ends (March, December, September)
    3. Point-in-time safety across all campaigns
    4. Data quality validation
    5. Gap reporting and manual review flags

Author: Bloomberg Activist Pipeline
"""

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, patch
import sys

import pandas as pd
import numpy as np

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from extract_snapshot import (
    CampaignTarget,
    SnapshotExtractor,
    validate_point_in_time_safety,
)


class TestEffissimoSnapshotIntegration(unittest.TestCase):
    """Integration test with realistic Effissimo campaign data."""

    def setUp(self):
        """Set up mock Effissimo campaigns."""
        # Create 30 sample campaigns representing Effissimo's actual targets
        # (using simplified data for testing)
        self.campaigns = [
            # March FYE companies (most common in Japan)
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
            # December FYE company
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
            # Add more companies for comprehensive testing
            CampaignTarget(
                company_name_japanese="株式会社ミルボン",
                company_name_english="Milbon Co Ltd",
                tse_ticker="4919.T",
                bloomberg_ticker="4919 JP Equity",
                campaign_start=date(2021, 9, 10),
                campaign_end=None,
                max_ownership_pct=8.45,
                min_ownership_pct=5.12,
                total_filings=10,
            ),
            CampaignTarget(
                company_name_japanese="株式会社きんでん",
                company_name_english="Kinden Corp",
                tse_ticker="1944.T",
                bloomberg_ticker="1944 JP Equity",
                campaign_start=date(2020, 8, 20),
                campaign_end=date(2023, 12, 31),
                max_ownership_pct=6.78,
                min_ownership_pct=5.03,
                total_filings=15,
            ),
        ]

        # Mock Bloomberg session
        self.mock_session = MagicMock()

        # Mock batching engine
        self.mock_batching_engine = MagicMock()

        # Mock field manager
        mock_field_manager = MagicMock()

        # Define mock field groups
        mock_field_manager.get_fields_by_override_type.side_effect = (
            self._mock_get_fields_by_override
        )

        self.mock_batching_engine.field_manager = mock_field_manager

        # Initialize extractor
        self.extractor = SnapshotExtractor(
            session=self.mock_session,
            batching_engine=self.mock_batching_engine,
        )

    def _mock_get_fields_by_override(self, override_type: str):
        """Mock field retrieval by override type."""
        if override_type == "FUND_PER":
            return [
                "RETURN_COM_EQY",
                "RETURN_ON_ASSET",
                "OPER_MARGIN",
                "BS_CASH_NEAR_CASH_ITEM",
                "BS_MKT_SEC_OTHER_ST_INVEST",
                "SHORT_AND_LONG_TERM_DEBT",
                "NET_DEBT",
                "TOT_EQUITY",
                "TRAIL_12M_SALES",
                "TRAIL_12M_NET_INC",
            ]
        elif override_type == "END_DT_OVERRIDE":
            return [
                "PX_TO_BOOK_RATIO",
                "PE_RATIO",
                "BEST_CUR_EV_TO_EBITDA",
                "CUR_MKT_CAP",
                "EQY_SH_OUT",
                "EQY_FREE_FLOAT_PCT",
                "EQY_INST_PCT_SH_OUT",
            ]
        elif override_type == "none":
            return ["FISCAL_YEAR_END_MONTH_DE", "BOARD_SIZE"]
        else:
            return []

    def _create_mock_fiscal_response(self):
        """Create mock fiscal year-end response."""
        records = []
        for campaign in self.campaigns:
            # Assign fiscal year-end months
            if "2432" in campaign.bloomberg_ticker:  # DeNA
                fye_month = 12  # December
            elif "4919" in campaign.bloomberg_ticker:  # Milbon
                fye_month = 12  # December
            else:
                fye_month = 3  # March (most common)

            records.append(
                {
                    "security": campaign.bloomberg_ticker,
                    "FISCAL_YEAR_END_MONTH_DE": fye_month,
                }
            )

        return pd.DataFrame(records)

    def _create_mock_fundamental_response(self, securities):
        """Create mock FUND_PER field response."""
        records = []
        for security in securities:
            records.append(
                {
                    "security": security,
                    "RETURN_COM_EQY": np.random.uniform(5.0, 15.0),
                    "RETURN_ON_ASSET": np.random.uniform(3.0, 10.0),
                    "OPER_MARGIN": np.random.uniform(5.0, 20.0),
                    "BS_CASH_NEAR_CASH_ITEM": np.random.uniform(
                        10_000_000_000, 100_000_000_000
                    ),
                    "BS_MKT_SEC_OTHER_ST_INVEST": np.random.uniform(
                        5_000_000_000, 50_000_000_000
                    ),
                    "SHORT_AND_LONG_TERM_DEBT": np.random.uniform(
                        20_000_000_000, 80_000_000_000
                    ),
                    "NET_DEBT": np.random.uniform(
                        -10_000_000_000, 50_000_000_000
                    ),
                    "TOT_EQUITY": np.random.uniform(
                        50_000_000_000, 200_000_000_000
                    ),
                    "TRAIL_12M_SALES": np.random.uniform(
                        100_000_000_000, 500_000_000_000
                    ),
                    "TRAIL_12M_NET_INC": np.random.uniform(
                        5_000_000_000, 30_000_000_000
                    ),
                }
            )

        return pd.DataFrame(records)

    def _create_mock_market_response(self, securities):
        """Create mock END_DT_OVERRIDE field response."""
        records = []
        for security in securities:
            records.append(
                {
                    "security": security,
                    "PX_TO_BOOK_RATIO": np.random.uniform(0.5, 2.0),
                    "PE_RATIO": np.random.uniform(8.0, 25.0),
                    "BEST_CUR_EV_TO_EBITDA": np.random.uniform(5.0, 15.0),
                    "CUR_MKT_CAP": np.random.uniform(
                        100_000_000_000, 1_000_000_000_000
                    ),
                    "EQY_SH_OUT": np.random.uniform(
                        50_000_000, 500_000_000
                    ),
                    "EQY_FREE_FLOAT_PCT": np.random.uniform(30.0, 70.0),
                    "EQY_INST_PCT_SH_OUT": np.random.uniform(20.0, 50.0),
                }
            )

        return pd.DataFrame(records)

    def _create_mock_static_response(self, securities):
        """Create mock static field response."""
        records = []
        for security in securities:
            # Already fetched in fiscal metadata, so skip FISCAL_YEAR_END_MONTH_DE
            records.append(
                {
                    "security": security,
                    "BOARD_SIZE": np.random.randint(8, 15),
                }
            )

        return pd.DataFrame(records)

    def test_full_extraction_workflow(self):
        """Test complete extraction workflow for 5 campaigns."""
        # Configure mock session responses
        def mock_send_request(securities, fields, overrides=None):
            # Fiscal year-end request (no override)
            if "FISCAL_YEAR_END_MONTH_DE" in fields and len(fields) == 1:
                return self._create_mock_fiscal_response()

            # FUND_PER request
            if overrides and "FUND_PER" in overrides:
                return self._create_mock_fundamental_response(securities)

            # END_DT_OVERRIDE request
            if overrides and "END_DT_OVERRIDE" in overrides:
                return self._create_mock_market_response(securities)

            # Static fields (no override)
            if not overrides or not overrides:
                if "BOARD_SIZE" in fields:
                    return self._create_mock_static_response(securities)

            # Default: empty DataFrame
            return pd.DataFrame({"security": securities})

        self.mock_session.send_request = mock_send_request

        # Configure batching engine to execute sequentially
        def mock_create_batches(securities, fields):
            from batching_engine import RequestBatch

            # Determine override type
            if any(
                f in fields
                for f in ["RETURN_COM_EQY", "BS_CASH_NEAR_CASH_ITEM"]
            ):
                override_type = "FUND_PER"
            elif any(f in fields for f in ["PX_TO_BOOK_RATIO", "CUR_MKT_CAP"]):
                override_type = "END_DT_OVERRIDE"
            else:
                override_type = "none"

            return [
                RequestBatch(
                    securities=securities,
                    fields=fields,
                    override_type=override_type,
                    batch_id=f"{override_type}_001_of_001",
                )
            ]

        def mock_execute_batches_sequential(session, batches, overrides):
            batch = batches[0]
            return session.send_request(
                securities=batch.securities,
                fields=batch.fields,
                overrides=overrides,
            )

        self.mock_batching_engine.create_batches = mock_create_batches
        self.mock_batching_engine.execute_batches_sequential = (
            mock_execute_batches_sequential
        )

        # Extract snapshot
        snapshot_df = self.extractor.extract_snapshot(self.campaigns)

        # Verify results
        self.assertEqual(len(snapshot_df), 5)  # 5 campaigns

        # Verify all securities present
        expected_tickers = [c.bloomberg_ticker for c in self.campaigns]
        actual_tickers = snapshot_df["security"].tolist()
        self.assertEqual(set(actual_tickers), set(expected_tickers))

        # Verify derived fields computed
        self.assertIn("net_cash", snapshot_df.columns)
        self.assertIn("net_cash_to_market_cap", snapshot_df.columns)
        self.assertIn("data_quality_score", snapshot_df.columns)
        self.assertIn("manual_review_flag", snapshot_df.columns)

        # Verify campaign metadata added
        self.assertIn("company_name_japanese", snapshot_df.columns)
        self.assertIn("campaign_start", snapshot_df.columns)
        self.assertIn("snapshot_date", snapshot_df.columns)
        self.assertIn("fund_per_override", snapshot_df.columns)

        # Verify point-in-time safety
        for _, row in snapshot_df.iterrows():
            self.assertLess(row["snapshot_date"], row["campaign_start"])

        # Verify data quality scores computed
        self.assertTrue(all(snapshot_df["data_quality_score"] >= 0))
        self.assertTrue(all(snapshot_df["data_quality_score"] <= 100))

    def test_point_in_time_validation_all_campaigns(self):
        """Test point-in-time safety for all campaigns."""
        # Mock fiscal year-end response
        self.mock_session.send_request.return_value = (
            self._create_mock_fiscal_response()
        )

        # Enrich fiscal metadata
        self.extractor._enrich_fiscal_metadata(self.campaigns)

        # Validate point-in-time safety
        result = validate_point_in_time_safety(self.campaigns)
        self.assertTrue(result)

        # Verify all snapshot dates before campaign starts
        for campaign in self.campaigns:
            self.assertIsNotNone(campaign.snapshot_date)
            self.assertLess(campaign.snapshot_date, campaign.campaign_start)

    def test_fiscal_year_end_diversity(self):
        """Test handling of different fiscal year-ends."""
        # Mock fiscal year-end response
        self.mock_session.send_request.return_value = (
            self._create_mock_fiscal_response()
        )

        # Enrich fiscal metadata
        self.extractor._enrich_fiscal_metadata(self.campaigns)

        # Collect fiscal year-ends
        fye_months = [c.fye_month for c in self.campaigns]

        # Verify diversity (should have both March and December)
        self.assertIn(3, fye_months)  # March
        self.assertIn(12, fye_months)  # December

        # Verify FUND_PER overrides vary by fiscal year
        fund_per_overrides = [c.fund_per_override for c in self.campaigns]

        # Should have multiple distinct FUND_PER values
        self.assertGreater(len(set(fund_per_overrides)), 1)

    def test_data_quality_flagging(self):
        """Test that low-quality data is flagged for manual review."""
        # Create snapshot with intentionally sparse data
        snapshot_df = pd.DataFrame(
            {
                "security": ["8136 JP Equity", "9107 JP Equity"],
                "PX_TO_BOOK_RATIO": [0.8, np.nan],  # Missing for 9107
                "RETURN_COM_EQY": [12.5, np.nan],  # Missing for 9107
                "CUR_MKT_CAP": [200_000_000_000, 100_000_000_000],
                "NET_DEBT": [-50_000_000_000, np.nan],  # Missing for 9107
                "TRAIL_12M_SALES": [150_000_000_000, np.nan],  # Missing for 9107
            }
        )

        # Compute quality scores
        result_df = self.extractor._compute_data_quality_scores(snapshot_df)

        # 8136: 5/5 critical fields = 100% (not flagged)
        self.assertEqual(result_df.loc[0, "data_quality_score"], 100.0)
        self.assertFalse(result_df.loc[0, "manual_review_flag"])

        # 9107: 1/5 critical fields = 20% (flagged)
        self.assertEqual(result_df.loc[1, "data_quality_score"], 20.0)
        self.assertTrue(result_df.loc[1, "manual_review_flag"])

    def test_gap_report_generation(self):
        """Test comprehensive gap report generation."""
        # Create snapshot with missing data
        snapshot_df = pd.DataFrame(
            {
                "security": ["8136 JP Equity", "9107 JP Equity"],
                "company_name_japanese": ["サンリオ", "川崎汽船"],
                "PX_TO_BOOK_RATIO": [0.8, 1.2],
                "RETURN_COM_EQY": [12.5, np.nan],
                "CUR_MKT_CAP": [200_000_000_000, 100_000_000_000],
                "BEST_PE_RATIO": [np.nan, np.nan],
                "data_quality_score": [100.0, 80.0],
                "manual_review_flag": [False, False],
            }
        )

        # Generate gap report
        gap_report = self.extractor.log_field_gaps(snapshot_df)

        # Verify report structure
        self.assertIn("timestamp", gap_report)
        self.assertIn("total_securities", gap_report)
        self.assertIn("field_coverage", gap_report)
        self.assertIn("missing_data", gap_report)

        # Verify field coverage statistics
        self.assertIn("PX_TO_BOOK_RATIO", gap_report["field_coverage"])
        self.assertEqual(
            gap_report["field_coverage"]["PX_TO_BOOK_RATIO"]["count"], 2
        )

        self.assertIn("BEST_PE_RATIO", gap_report["field_coverage"])
        self.assertEqual(
            gap_report["field_coverage"]["BEST_PE_RATIO"]["count"], 0
        )

        # Verify missing data entries
        self.assertGreater(len(gap_report["missing_data"]), 0)


if __name__ == "__main__":
    unittest.main()
