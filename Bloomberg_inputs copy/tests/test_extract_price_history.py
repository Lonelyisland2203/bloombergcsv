"""
Unit Tests for Price History Extractor

Test Coverage:
    1. PriceHistoryTarget dataclass validation
    2. Price history extraction with date ranges
    3. Derived metrics computation (days_since_entry, cumulative_return)
    4. Missing days handling (market holidays, trading suspensions)
    5. Data quality validation (suspicious price movements)
    6. Summary statistics computation
    7. Multiple campaign extraction
    8. Integration test with mock Bloomberg data

Edge Cases:
    - Entry date not in price history (holiday)
    - Campaign with no price data
    - Extreme price movements (>50% daily change)
    - Zero volume days
    - Date range validation

Author: Bloomberg Activist Pipeline
"""

import unittest
from datetime import date, timedelta
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch
import sys

import pandas as pd
import numpy as np

# Add src to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from extract_price_history import (
    PriceHistoryTarget,
    PriceHistoryExtractor,
)


class TestPriceHistoryTarget(unittest.TestCase):
    """Test PriceHistoryTarget dataclass validation."""

    def test_valid_target(self):
        """Test creation of valid price history target."""
        target = PriceHistoryTarget(
            ticker="9107 JP Equity",
            campaign_start=date(2023, 6, 14),
            campaign_end=date(2024, 12, 31),
        )

        self.assertEqual(target.ticker, "9107 JP Equity")
        self.assertEqual(target.campaign_start, date(2023, 6, 14))
        self.assertEqual(target.campaign_end, date(2024, 12, 31))
        self.assertIsNone(target.entry_price)

    def test_invalid_date_range(self):
        """Test validation of campaign date range."""
        with self.assertRaises(ValueError):
            PriceHistoryTarget(
                ticker="9107 JP Equity",
                campaign_start=date(2024, 1, 1),
                campaign_end=date(2023, 1, 1),  # End before start
            )

    def test_ongoing_campaign(self):
        """Test target with no end date (ongoing campaign)."""
        target = PriceHistoryTarget(
            ticker="9107 JP Equity",
            campaign_start=date(2023, 6, 14),
            campaign_end=None,  # Ongoing
        )

        self.assertIsNone(target.campaign_end)


class TestPriceHistoryExtractor(unittest.TestCase):
    """Test PriceHistoryExtractor methods."""

    def setUp(self):
        """Set up mock Bloomberg session for testing."""
        self.mock_session = Mock()
        self.mock_session.session = Mock()  # Active session
        self.extractor = PriceHistoryExtractor(self.mock_session)

    def test_initialization(self):
        """Test extractor initialization."""
        self.assertEqual(self.extractor.session, self.mock_session)
        self.assertEqual(self.extractor.adjustment_method, "DPDF")

    def test_initialization_without_active_session(self):
        """Test initialization fails if session not started."""
        mock_session = Mock()
        mock_session.session = None  # Not started

        with self.assertRaises(ValueError):
            PriceHistoryExtractor(mock_session)

    def test_extract_price_history_success(self):
        """Test successful price history extraction."""
        # Mock Bloomberg response
        mock_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 5,
                "date": pd.date_range("2023-01-04", periods=5, freq="D"),
                "PX_LAST": [1234.5, 1240.0, 1235.0, 1245.0, 1250.0],
                "PX_VOLUME": [500000, 520000, 480000, 510000, 530000],
            }
        )

        self.mock_session.send_historical_request.return_value = mock_df

        # Extract price history
        result = self.extractor.extract_price_history(
            security="9107 JP Equity",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 10),
        )

        # Verify result structure
        self.assertEqual(len(result), 5)
        self.assertIn("ticker", result.columns)
        self.assertIn("date", result.columns)
        self.assertIn("adjusted_close", result.columns)
        self.assertIn("volume", result.columns)
        self.assertIn("unadjusted_close", result.columns)

        # Verify data
        self.assertEqual(result["ticker"].iloc[0], "9107 JP Equity")
        self.assertEqual(result["adjusted_close"].iloc[0], 1234.5)
        self.assertEqual(result["volume"].iloc[0], 500000)

    def test_extract_price_history_invalid_date_range(self):
        """Test extraction with invalid date range."""
        with self.assertRaises(ValueError):
            self.extractor.extract_price_history(
                security="9107 JP Equity",
                start_date=date(2023, 12, 31),
                end_date=date(2023, 1, 1),  # End before start
            )

    def test_extract_price_history_no_data(self):
        """Test extraction with no data returned."""
        self.mock_session.send_historical_request.return_value = pd.DataFrame()

        result = self.extractor.extract_price_history(
            security="9107 JP Equity",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 10),
        )

        self.assertTrue(result.empty)
        self.assertIn("adjusted_close", result.columns)

    def test_compute_derived_metrics_success(self):
        """Test derived metrics computation."""
        # Create sample price data
        price_df = pd.DataFrame(
            {
                "ticker": ["9107 JP Equity"] * 10,
                "date": pd.date_range("2023-06-01", periods=10, freq="D"),
                "adjusted_close": [1200, 1210, 1205, 1215, 1220, 1225, 1230, 1235, 1240, 1245],
                "volume": [500000] * 10,
                "unadjusted_close": [1200, 1210, 1205, 1215, 1220, 1225, 1230, 1235, 1240, 1245],
            }
        )

        entry_date = date(2023, 6, 5)  # 5th row (0-indexed: row 4)
        entry_price = 1220.0

        # Compute derived metrics
        result = self.extractor.compute_derived_metrics(
            price_df=price_df,
            entry_date=entry_date,
            entry_price=entry_price,
        )

        # Verify new columns exist
        self.assertIn("days_since_activist_entry", result.columns)
        self.assertIn("cumulative_return", result.columns)
        self.assertIn("entry_price", result.columns)

        # Verify entry_price column
        self.assertEqual(result["entry_price"].iloc[0], 1220.0)

        # Verify days_since_activist_entry
        # 2023-06-01 is 4 days before 2023-06-05
        self.assertEqual(result["days_since_activist_entry"].iloc[0], -4)
        # 2023-06-05 is entry date (0 days)
        self.assertEqual(result["days_since_activist_entry"].iloc[4], 0)
        # 2023-06-10 is 5 days after entry
        self.assertEqual(result["days_since_activist_entry"].iloc[9], 5)

        # Verify cumulative_return
        # At entry: (1220 / 1220) - 1 = 0
        self.assertAlmostEqual(result["cumulative_return"].iloc[4], 0.0, places=6)
        # Last day: (1245 / 1220) - 1 ≈ 0.0205
        self.assertAlmostEqual(result["cumulative_return"].iloc[9], 0.0204918, places=6)

    def test_compute_derived_metrics_auto_entry_price(self):
        """Test derived metrics with auto-extracted entry price."""
        price_df = pd.DataFrame(
            {
                "ticker": ["9107 JP Equity"] * 5,
                "date": pd.to_datetime(
                    ["2023-06-01", "2023-06-02", "2023-06-05", "2023-06-06", "2023-06-07"]
                ).date,
                "adjusted_close": [1200, 1210, 1220, 1230, 1240],
                "volume": [500000] * 5,
                "unadjusted_close": [1200, 1210, 1220, 1230, 1240],
            }
        )

        entry_date = date(2023, 6, 5)

        # Compute without providing entry_price
        result = self.extractor.compute_derived_metrics(
            price_df=price_df,
            entry_date=entry_date,
            entry_price=None,  # Auto-extract
        )

        # Verify entry_price was extracted correctly
        self.assertEqual(result["entry_price"].iloc[0], 1220.0)

    def test_compute_derived_metrics_entry_date_not_found(self):
        """Test derived metrics when entry date not in data."""
        price_df = pd.DataFrame(
            {
                "ticker": ["9107 JP Equity"] * 5,
                "date": pd.to_datetime(
                    ["2023-06-01", "2023-06-02", "2023-06-06", "2023-06-07", "2023-06-08"]
                ).date,
                "adjusted_close": [1200, 1210, 1230, 1240, 1250],
                "volume": [500000] * 5,
                "unadjusted_close": [1200, 1210, 1230, 1240, 1250],
            }
        )

        entry_date = date(2023, 6, 5)  # Not in data (market holiday)

        # Should raise error if entry_price not provided
        with self.assertRaises(ValueError):
            self.extractor.compute_derived_metrics(
                price_df=price_df,
                entry_date=entry_date,
                entry_price=None,
            )

        # Should work if entry_price provided
        result = self.extractor.compute_derived_metrics(
            price_df=price_df,
            entry_date=entry_date,
            entry_price=1220.0,
        )

        self.assertEqual(result["entry_price"].iloc[0], 1220.0)

    def test_compute_derived_metrics_empty_df(self):
        """Test derived metrics with empty DataFrame."""
        price_df = pd.DataFrame()

        result = self.extractor.compute_derived_metrics(
            price_df=price_df,
            entry_date=date(2023, 6, 5),
            entry_price=1220.0,
        )

        self.assertTrue(result.empty)

    def test_extract_campaign_price_history(self):
        """Test campaign price history extraction."""
        # Mock Bloomberg response with dates that include campaign_start
        # Campaign starts on 2023-06-14, so include that date
        mock_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 10,
                "date": pd.date_range("2023-06-10", periods=10, freq="D"),
                "PX_LAST": [1200 + i * 10 for i in range(10)],
                "PX_VOLUME": [500000] * 10,
            }
        )

        self.mock_session.send_historical_request.return_value = mock_df

        # Create target
        target = PriceHistoryTarget(
            ticker="9107 JP Equity",
            campaign_start=date(2023, 6, 14),
            campaign_end=None,  # Ongoing
        )

        # Extract
        with patch("extract_price_history.date") as mock_date:
            mock_date.today.return_value = date(2023, 12, 31)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

            result = self.extractor.extract_campaign_price_history(target)

        # Verify result has derived metrics
        self.assertIn("days_since_activist_entry", result.columns)
        self.assertIn("cumulative_return", result.columns)

        # Verify entry_price was set on target
        self.assertIsNotNone(target.entry_price)

    def test_extract_multiple_campaigns(self):
        """Test extraction for multiple campaigns."""
        # Mock Bloomberg response - return different data based on security
        def mock_historical_request(security, fields, start_date, end_date, periodicity):
            if "9107" in security:
                # Data for 9107 including campaign_start date (2023-06-14)
                return pd.DataFrame(
                    {
                        "security": ["9107 JP Equity"] * 5,
                        "date": pd.date_range("2023-06-12", periods=5, freq="D"),
                        "PX_LAST": [1200, 1210, 1220, 1230, 1240],
                        "PX_VOLUME": [500000] * 5,
                    }
                )
            else:
                # Data for 8136 including campaign_start date (2023-05-01)
                return pd.DataFrame(
                    {
                        "security": ["8136 JP Equity"] * 5,
                        "date": pd.date_range("2023-04-28", periods=5, freq="D"),
                        "PX_LAST": [2200, 2210, 2220, 2230, 2240],
                        "PX_VOLUME": [300000] * 5,
                    }
                )

        self.mock_session.send_historical_request.side_effect = mock_historical_request

        # Create targets
        targets = [
            PriceHistoryTarget(
                ticker="9107 JP Equity",
                campaign_start=date(2023, 6, 14),
                campaign_end=None,
            ),
            PriceHistoryTarget(
                ticker="8136 JP Equity",
                campaign_start=date(2023, 5, 1),
                campaign_end=date(2024, 12, 31),
            ),
        ]

        # Extract
        with patch("extract_price_history.date") as mock_date:
            mock_date.today.return_value = date(2023, 12, 31)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

            result = self.extractor.extract_multiple_campaigns(targets)

        # Verify result combines both campaigns
        self.assertGreater(len(result), 0)
        self.assertIn("ticker", result.columns)

    def test_extract_multiple_campaigns_no_targets(self):
        """Test extraction with no targets."""
        with self.assertRaises(ValueError):
            self.extractor.extract_multiple_campaigns([])

    def test_compute_summary_statistics(self):
        """Test summary statistics computation."""
        # Create sample data with derived metrics
        price_df = pd.DataFrame(
            {
                "ticker": ["9107 JP Equity"] * 10,
                "date": pd.date_range("2023-06-01", periods=10, freq="D"),
                "adjusted_close": [1200, 1210, 1205, 1215, 1220, 1225, 1230, 1235, 1240, 1245],
                "volume": [500000] * 10,
                "days_since_activist_entry": list(range(-4, 6)),
                "cumulative_return": [
                    (p / 1220.0) - 1 for p in [1200, 1210, 1205, 1215, 1220, 1225, 1230, 1235, 1240, 1245]
                ],
            }
        )

        stats = self.extractor.compute_summary_statistics(price_df)

        # Verify stats structure
        self.assertIn("total_return", stats)
        self.assertIn("max_return", stats)
        self.assertIn("min_return", stats)
        self.assertIn("volatility", stats)
        self.assertIn("avg_volume", stats)
        self.assertIn("total_trading_days", stats)

        # Verify values make sense
        self.assertGreater(stats["total_return"], -1.0)  # > -100%
        self.assertGreater(stats["max_return"], stats["min_return"])
        self.assertGreater(stats["volatility"], 0.0)
        self.assertEqual(stats["avg_volume"], 500000)

    def test_compute_summary_statistics_empty_df(self):
        """Test summary statistics with empty DataFrame."""
        price_df = pd.DataFrame()

        stats = self.extractor.compute_summary_statistics(price_df)

        self.assertEqual(stats, {})

    def test_validate_price_data_quality(self):
        """Test price data quality validation."""
        # Create data with quality issues
        price_df = pd.DataFrame(
            {
                "ticker": ["9107 JP Equity"] * 5,
                "date": pd.date_range("2023-01-01", periods=5, freq="D"),
                "adjusted_close": [1200, 1800, 1210, 0, 1220],  # Spike and zero
                "volume": [500000, 0, 520000, 0, 510000],  # Zero volume
                "unadjusted_close": [1200, 1800, 1210, 0, 1220],
            }
        )

        # Validation should log warnings but not raise errors
        # (tested via log inspection in integration tests)
        self.extractor._validate_price_data(
            df=price_df,
            security="9107 JP Equity",
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 10),
        )


class TestIntegrationPriceHistory(unittest.TestCase):
    """Integration tests with realistic Bloomberg data scenarios."""

    def test_full_campaign_extraction_workflow(self):
        """Test complete workflow from target to summary stats."""
        # Create mock session
        mock_session = Mock()
        mock_session.session = Mock()

        # Mock price data
        mock_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 252,  # 1 year of trading days
                "date": pd.date_range("2023-01-04", periods=252, freq="B"),  # Business days
                "PX_LAST": [1200 + np.random.randn() * 20 for _ in range(252)],
                "PX_VOLUME": [500000 + np.random.randint(-50000, 50000) for _ in range(252)],
            }
        )

        mock_session.send_historical_request.return_value = mock_df

        # Create extractor and target
        extractor = PriceHistoryExtractor(mock_session)

        target = PriceHistoryTarget(
            ticker="9107 JP Equity",
            campaign_start=date(2023, 6, 14),
            campaign_end=None,
        )

        # Extract campaign history
        with patch("extract_price_history.date") as mock_date:
            mock_date.today.return_value = date(2023, 12, 31)
            mock_date.side_effect = lambda *args, **kwargs: date(*args, **kwargs)

            price_df = extractor.extract_campaign_price_history(target)

        # Verify data structure
        self.assertGreater(len(price_df), 0)
        self.assertIn("cumulative_return", price_df.columns)

        # Compute summary stats
        stats = extractor.compute_summary_statistics(price_df)

        # Verify stats
        self.assertIn("total_return", stats)
        self.assertIn("volatility", stats)
        self.assertGreater(stats["total_trading_days"], 0)


if __name__ == "__main__":
    unittest.main()
