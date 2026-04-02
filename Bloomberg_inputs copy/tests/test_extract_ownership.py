"""
Unit Tests for Ownership Extractor

Test Coverage:
    1. TOP_20_HOLDERS extraction with mocked Bloomberg
    2. Column name standardization
    3. Holder data cleaning and deduplication
    4. Foreign holder flagging (by type and keywords)
    5. Cross-shareholding ratio computation
    6. Foreign institutional ratio computation
    7. Top 5 concentration computation
    8. Data quality score computation
    9. Integration test with 5 Effissimo companies

Author: Bloomberg Activist Pipeline
"""

import unittest
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
import sys

import pandas as pd
import numpy as np

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from extract_ownership import (
    OwnershipExtractor,
    OwnershipSummary,
)


class TestOwnershipExtractor(unittest.TestCase):
    """Test OwnershipExtractor class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock Bloomberg session
        self.mock_session = MagicMock()
        self.mock_session.session = MagicMock()  # Indicate session is started

        # Create temporary logs directory
        self.temp_logs = Path(__file__).parent / "temp_logs"
        self.temp_logs.mkdir(exist_ok=True)

        # Create extractor
        self.extractor = OwnershipExtractor(
            session=self.mock_session,
            logs_dir=self.temp_logs,
        )

    def tearDown(self):
        """Clean up test fixtures."""
        # Remove temp logs directory
        if self.temp_logs.exists():
            for file in self.temp_logs.glob("*"):
                file.unlink()
            self.temp_logs.rmdir()

    def test_initialization(self):
        """Test extractor initialization."""
        self.assertIsNotNone(self.extractor.session)
        self.assertEqual(self.extractor.logs_dir, self.temp_logs)

    def test_initialization_without_started_session(self):
        """Test that extractor raises error if session not started."""
        mock_session = MagicMock()
        mock_session.session = None  # Session not started

        with self.assertRaises(ValueError) as context:
            OwnershipExtractor(session=mock_session)

        self.assertIn("must be started", str(context.exception))

    def test_extract_top_20_holders_basic(self):
        """Test basic TOP_20_HOLDERS extraction."""
        # Mock Bloomberg response
        mock_response = pd.DataFrame(
            {
                "security": ["9107 JP Equity", "9107 JP Equity", "9107 JP Equity"],
                "Holder Name": ["Nomura Asset Management", "BlackRock Japan", "MUFG Bank"],
                "Holder Type": ["Investment Advisor", "Investment Advisor", "Bank"],
                "Portfolio %": [5.2, 3.8, 2.1],
                "Shares Held": [1234567, 900000, 500000],
                "Rank": [1, 2, 3],
            }
        )

        self.mock_session.send_bulk_request.return_value = mock_response

        # Extract ownership
        result = self.extractor.extract_top_20_holders(["9107 JP Equity"])

        # Verify Bloomberg was called correctly
        self.mock_session.send_bulk_request.assert_called_once_with(
            securities=["9107 JP Equity"],
            field="TOP_20_HOLDERS_PUBLIC_FILINGS",
        )

        # Verify result structure
        self.assertEqual(len(result), 3)
        self.assertIn("holder_name", result.columns)
        self.assertIn("holder_type", result.columns)
        self.assertIn("percent_held", result.columns)

    def test_standardize_column_names(self):
        """Test column name standardization."""
        # Test various Bloomberg column naming conventions
        raw_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"],
                "Holder Name": ["BlackRock"],
                "TYPE": ["Investment Advisor"],
                "PERCENT_OUTSTANDING": [5.0],
                "SHARES_HELD": [1000000],
            }
        )

        standardized = self.extractor._standardize_column_names(raw_df)

        # Verify standardized names
        self.assertIn("holder_name", standardized.columns)
        self.assertIn("holder_type", standardized.columns)
        self.assertIn("percent_held", standardized.columns)
        self.assertIn("shares_held", standardized.columns)

    def test_clean_holder_data(self):
        """Test holder data cleaning."""
        # Create data with issues: missing names, duplicates, invalid percentages
        raw_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 5,
                "holder_name": ["BlackRock", None, "Vanguard", "BlackRock", "MUFG"],
                "holder_type": ["Investment Advisor", "Bank", "Fund", "Investment Advisor", "Bank"],
                "percent_held": [5.0, 3.0, 2.0, 5.0, 150.0],  # Duplicate and invalid
                "shares_held": [1000000, 500000, 300000, 1000000, 2000000],
            }
        )

        cleaned = self.extractor._clean_holder_data(raw_df)

        # Verify missing names removed AND duplicates removed
        # Initial: 5 rows -> Remove 1 None -> 4 rows -> Remove 1 duplicate BlackRock -> 3 rows
        self.assertEqual(len(cleaned), 3)

        # Verify duplicates removed (only 1 BlackRock remains)
        self.assertEqual(len(cleaned[cleaned["holder_name"] == "BlackRock"]), 1)

        # Verify holder_rank inferred
        self.assertIn("holder_rank", cleaned.columns)

    def test_flag_foreign_holders_by_type(self):
        """Test foreign holder flagging by holder_type."""
        holders_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 3,
                "holder_name": ["Nomura", "BlackRock", "MUFG"],
                "holder_type": ["Investment Advisor", "Investment Advisor", "Bank"],
                "percent_held": [5.0, 3.0, 2.0],
            }
        )

        flagged = self.extractor.flag_foreign_holders(holders_df)

        # Verify is_foreign column added
        self.assertIn("is_foreign", flagged.columns)

        # Verify Investment Advisor types flagged
        self.assertTrue(flagged.loc[flagged["holder_name"] == "BlackRock", "is_foreign"].values[0])
        self.assertTrue(flagged.loc[flagged["holder_name"] == "Nomura", "is_foreign"].values[0])

        # Verify Bank not flagged
        self.assertFalse(flagged.loc[flagged["holder_name"] == "MUFG", "is_foreign"].values[0])

    def test_flag_foreign_holders_by_keyword(self):
        """Test foreign holder flagging by name keywords."""
        holders_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 4,
                "holder_name": [
                    "BlackRock Japan Co Ltd",
                    "Vanguard Investments",
                    "JP Morgan Securities",
                    "Dai-ichi Life Insurance",  # Japanese insurance company, no foreign keywords
                ],
                "holder_type": ["Other", "Other", "Other", "Other"],
                "percent_held": [5.0, 3.0, 2.0, 1.5],
            }
        )

        flagged = self.extractor.flag_foreign_holders(holders_df)

        # Verify keyword-based flagging
        self.assertTrue(flagged.loc[flagged["holder_name"].str.contains("BlackRock"), "is_foreign"].values[0])
        self.assertTrue(flagged.loc[flagged["holder_name"].str.contains("Vanguard"), "is_foreign"].values[0])
        self.assertTrue(flagged.loc[flagged["holder_name"].str.contains("JP Morgan"), "is_foreign"].values[0])

        # Verify Japanese institutional investor NOT flagged (no foreign keywords)
        self.assertFalse(
            flagged.loc[flagged["holder_name"].str.contains("Dai-ichi"), "is_foreign"].values[0]
        )

    def test_compute_cross_shareholding_ratio(self):
        """Test cross-shareholding ratio computation."""
        holders_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 5,
                "holder_name": ["Corp A", "Corp B", "Fund X", "Corp C", "Bank Y"],
                "holder_type": ["Corporation", "Corporation", "Fund", "Corporation", "Bank"],
                "percent_held": [10.0, 8.0, 5.0, 3.0, 2.0],
            }
        )

        cross_ratios = self.extractor.compute_cross_shareholding_ratio(holders_df)

        # Verify result
        self.assertEqual(len(cross_ratios), 1)
        self.assertEqual(cross_ratios.loc[0, "security"], "9107 JP Equity")

        # Expected: 10 + 8 + 3 = 21% (Corp A + Corp B + Corp C)
        self.assertEqual(cross_ratios.loc[0, "cross_shareholding_ratio"], 21.0)
        self.assertEqual(cross_ratios.loc[0, "num_cross_shareholders"], 3)

    def test_compute_cross_shareholding_ratio_zero(self):
        """Test cross-shareholding ratio with no Corporation holders."""
        holders_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 3,
                "holder_name": ["Fund X", "Bank Y", "Individual Z"],
                "holder_type": ["Fund", "Bank", "Individual Investor"],
                "percent_held": [10.0, 5.0, 2.0],
            }
        )

        cross_ratios = self.extractor.compute_cross_shareholding_ratio(holders_df)

        # Verify zero cross-shareholding
        self.assertEqual(cross_ratios.loc[0, "cross_shareholding_ratio"], 0.0)
        self.assertEqual(cross_ratios.loc[0, "num_cross_shareholders"], 0)

    def test_compute_foreign_institutional_ratio(self):
        """Test foreign institutional ownership ratio computation."""
        holders_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 4,
                "holder_name": ["BlackRock", "Vanguard", "MUFG", "Nomura"],
                "holder_type": ["Investment Advisor", "Fund", "Bank", "Investment Advisor"],
                "percent_held": [5.0, 3.0, 2.0, 1.5],
                "is_foreign": [True, True, False, False],
            }
        )

        foreign_ratios = self.extractor.compute_foreign_institutional_ratio(holders_df)

        # Verify result
        self.assertEqual(len(foreign_ratios), 1)

        # Expected: 5 + 3 = 8% (BlackRock + Vanguard)
        self.assertEqual(foreign_ratios.loc[0, "foreign_institutional_ratio"], 8.0)
        self.assertEqual(foreign_ratios.loc[0, "num_foreign_holders"], 2)

    def test_compute_top_5_concentration(self):
        """Test top 5 shareholder concentration computation."""
        holders_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 10,
                "holder_rank": range(1, 11),
                "holder_name": [f"Holder {i}" for i in range(1, 11)],
                "percent_held": [10.0, 8.0, 6.0, 5.0, 4.0, 3.0, 2.0, 1.5, 1.0, 0.5],
            }
        )

        concentration = self.extractor.compute_top_5_concentration(holders_df)

        # Verify result
        self.assertEqual(len(concentration), 1)

        # Expected: 10 + 8 + 6 + 5 + 4 = 33%
        self.assertEqual(concentration.loc[0, "top_5_concentration"], 33.0)

    def test_generate_ownership_summary(self):
        """Test comprehensive ownership summary generation."""
        # Mock Bloomberg response with diverse holders
        mock_response = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 10,
                "Holder Name": [
                    "Corp A", "Corp B", "BlackRock Japan", "Vanguard",
                    "MUFG Bank", "Corp C", "Nomura Asset", "Individual X",
                    "Fund Y", "Bank Z"
                ],
                "Holder Type": [
                    "Corporation", "Corporation", "Investment Advisor", "Fund",
                    "Bank", "Corporation", "Investment Advisor", "Individual Investor",
                    "Fund", "Bank"
                ],
                "Portfolio %": [12.0, 10.0, 8.0, 6.0, 5.0, 4.0, 3.5, 3.0, 2.5, 2.0],
                "Shares Held": [1200000, 1000000, 800000, 600000, 500000, 400000, 350000, 300000, 250000, 200000],
                "Rank": range(1, 11),
            }
        )

        self.mock_session.send_bulk_request.return_value = mock_response

        # Generate summary
        summary = self.extractor.generate_ownership_summary(
            securities=["9107 JP Equity"],
            company_names={"9107 JP Equity": "Sanrio Co Ltd"},
        )

        # Verify summary structure
        self.assertEqual(len(summary), 1)
        self.assertEqual(summary.loc[0, "security"], "9107 JP Equity")
        self.assertEqual(summary.loc[0, "company_name"], "Sanrio Co Ltd")

        # Verify cross-shareholding (Corp A + Corp B + Corp C = 12 + 10 + 4 = 26%)
        self.assertEqual(summary.loc[0, "cross_shareholding_ratio"], 26.0)

        # Verify top 5 concentration (12 + 10 + 8 + 6 + 5 = 41%)
        self.assertEqual(summary.loc[0, "top_5_concentration"], 41.0)

        # Verify data quality score exists
        self.assertIn("data_quality_score", summary.columns)
        self.assertGreater(summary.loc[0, "data_quality_score"], 0)

    def test_extract_ownership_empty_securities(self):
        """Test extraction with empty securities list."""
        with self.assertRaises(ValueError) as context:
            self.extractor.extract_top_20_holders([])

        self.assertIn("No securities provided", str(context.exception))

    def test_extract_ownership_bloomberg_error(self):
        """Test handling of Bloomberg API errors."""
        # Mock Bloomberg error
        self.mock_session.send_bulk_request.side_effect = Exception("Bloomberg connection failed")

        with self.assertRaises(ValueError) as context:
            self.extractor.extract_top_20_holders(["9107 JP Equity"])

        self.assertIn("Ownership extraction failed", str(context.exception))


class TestOwnershipIntegration(unittest.TestCase):
    """Integration tests with multiple securities."""

    def setUp(self):
        """Set up integration test fixtures."""
        self.mock_session = MagicMock()
        self.mock_session.session = MagicMock()

        self.extractor = OwnershipExtractor(session=self.mock_session)

    def test_multiple_securities_ownership(self):
        """Test ownership extraction for multiple securities."""
        # Mock Bloomberg response for 3 securities
        mock_response = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 5 + ["8136 JP Equity"] * 5 + ["6502 JP Equity"] * 5,
                "Holder Name": [
                    # 9107
                    "Corp A", "BlackRock", "Vanguard", "MUFG", "Corp B",
                    # 8136
                    "Corp X", "Corp Y", "Fund A", "Bank B", "Individual C",
                    # 6502
                    "Fund M", "Fund N", "Corp Z", "Bank P", "Individual Q",
                ],
                "Holder Type": [
                    # 9107
                    "Corporation", "Investment Advisor", "Fund", "Bank", "Corporation",
                    # 8136
                    "Corporation", "Corporation", "Fund", "Bank", "Individual Investor",
                    # 6502
                    "Fund", "Fund", "Corporation", "Bank", "Individual Investor",
                ],
                "Portfolio %": [
                    # 9107
                    15.0, 10.0, 8.0, 5.0, 3.0,
                    # 8136
                    20.0, 15.0, 10.0, 5.0, 3.0,
                    # 6502
                    12.0, 10.0, 8.0, 6.0, 4.0,
                ],
                "Shares Held": [1000000] * 15,
                "Rank": [1, 2, 3, 4, 5] * 3,
            }
        )

        self.mock_session.send_bulk_request.return_value = mock_response

        # Generate summary
        summary = self.extractor.generate_ownership_summary(
            securities=["9107 JP Equity", "8136 JP Equity", "6502 JP Equity"],
            company_names={
                "9107 JP Equity": "Sanrio",
                "8136 JP Equity": "Toshiba",
                "6502 JP Equity": "Sony",
            },
        )

        # Verify 3 securities in summary
        self.assertEqual(len(summary), 3)

        # Verify cross-shareholding ratios
        sanrio_cross = summary.loc[summary["security"] == "9107 JP Equity", "cross_shareholding_ratio"].values[0]
        toshiba_cross = summary.loc[summary["security"] == "8136 JP Equity", "cross_shareholding_ratio"].values[0]
        sony_cross = summary.loc[summary["security"] == "6502 JP Equity", "cross_shareholding_ratio"].values[0]

        self.assertEqual(sanrio_cross, 18.0)  # Corp A + Corp B
        self.assertEqual(toshiba_cross, 35.0)  # Corp X + Corp Y
        self.assertEqual(sony_cross, 8.0)  # Corp Z only


if __name__ == "__main__":
    unittest.main()
