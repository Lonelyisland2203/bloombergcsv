"""
Unit Tests for Events Extractor

Test Coverage:
    1. Campaign period date filtering (CRITICAL)
    2. Dividend extraction and classification
    3. Buyback extraction
    4. Stock split extraction and classification
    5. M&A extraction and classification
    6. Event deduplication
    7. Months-after-entry computation
    8. Integration test with multiple companies and event types

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

from extract_events import (
    EventsExtractor,
    CampaignPeriod,
)


class TestCampaignPeriod(unittest.TestCase):
    """Test CampaignPeriod dataclass."""

    def test_is_within_campaign_ongoing(self):
        """Test date checking for ongoing campaign."""
        campaign = CampaignPeriod(
            ticker="9107 JP Equity",
            company_name="Sanrio",
            campaign_start=date(2021, 6, 14),
            campaign_end=None,  # Ongoing
        )

        # Event before campaign
        self.assertFalse(campaign.is_within_campaign(date(2021, 6, 1)))

        # Event on campaign start
        self.assertTrue(campaign.is_within_campaign(date(2021, 6, 14)))

        # Event during campaign
        self.assertTrue(campaign.is_within_campaign(date(2021, 12, 1)))

        # Event far in future (ongoing campaign)
        self.assertTrue(campaign.is_within_campaign(date(2025, 1, 1)))

    def test_is_within_campaign_ended(self):
        """Test date checking for ended campaign."""
        campaign = CampaignPeriod(
            ticker="9107 JP Equity",
            company_name="Sanrio",
            campaign_start=date(2021, 6, 14),
            campaign_end=date(2023, 12, 31),
        )

        # Event before campaign
        self.assertFalse(campaign.is_within_campaign(date(2021, 6, 1)))

        # Event during campaign
        self.assertTrue(campaign.is_within_campaign(date(2022, 6, 1)))

        # Event on campaign end
        self.assertTrue(campaign.is_within_campaign(date(2023, 12, 31)))

        # Event after campaign end
        self.assertFalse(campaign.is_within_campaign(date(2024, 1, 1)))

    def test_months_after_entry(self):
        """Test months-after-entry computation."""
        campaign = CampaignPeriod(
            ticker="9107 JP Equity",
            company_name="Sanrio",
            campaign_start=date(2021, 6, 14),
            campaign_end=None,
        )

        # Same day
        self.assertAlmostEqual(campaign.months_after_entry(date(2021, 6, 14)), 0.0, places=1)

        # ~1 month later
        self.assertAlmostEqual(campaign.months_after_entry(date(2021, 7, 14)), 1.0, places=0)

        # ~6 months later
        self.assertAlmostEqual(campaign.months_after_entry(date(2021, 12, 14)), 6.0, places=0)

        # ~1 year later
        self.assertAlmostEqual(campaign.months_after_entry(date(2022, 6, 14)), 12.0, places=0)

        # Before campaign start (negative)
        self.assertLess(campaign.months_after_entry(date(2021, 5, 14)), 0)


class TestEventsExtractor(unittest.TestCase):
    """Test EventsExtractor class."""

    def setUp(self):
        """Set up test fixtures."""
        # Create mock Bloomberg session
        self.mock_session = MagicMock()
        self.mock_session.session = MagicMock()

        # Create temporary logs directory
        self.temp_logs = Path(__file__).parent / "temp_logs"
        self.temp_logs.mkdir(exist_ok=True)

        # Create extractor
        self.extractor = EventsExtractor(
            session=self.mock_session,
            logs_dir=self.temp_logs,
        )

        # Create test campaign periods
        self.campaign_periods = {
            "9107 JP Equity": CampaignPeriod(
                ticker="9107 JP Equity",
                company_name="Sanrio",
                campaign_start=date(2021, 6, 14),
                campaign_end=date(2023, 12, 31),
            ),
            "8136 JP Equity": CampaignPeriod(
                ticker="8136 JP Equity",
                company_name="Toshiba",
                campaign_start=date(2020, 3, 1),
                campaign_end=None,  # Ongoing
            ),
        }

    def tearDown(self):
        """Clean up test fixtures."""
        if self.temp_logs.exists():
            for file in self.temp_logs.glob("*"):
                file.unlink()
            self.temp_logs.rmdir()

    def test_initialization(self):
        """Test extractor initialization."""
        self.assertIsNotNone(self.extractor.session)
        self.assertEqual(self.extractor.logs_dir, self.temp_logs)

    def test_filter_to_campaign_period(self):
        """Test CRITICAL date filtering to campaign period."""
        # Create events spanning before, during, and after campaign
        events_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 5,
                "event_date": [
                    "2021-05-01",  # Before campaign
                    "2021-06-14",  # Campaign start (should be included)
                    "2022-06-01",  # During campaign
                    "2023-12-31",  # Campaign end (should be included)
                    "2024-01-15",  # After campaign
                ],
                "event_type": ["Dividend"] * 5,
            }
        )

        # Filter
        filtered = self.extractor._filter_to_campaign_period(
            events_df, self.campaign_periods
        )

        # Verify only 3 events during campaign
        self.assertEqual(len(filtered), 3)

        # Verify dates
        filtered_dates = pd.to_datetime(filtered["event_date"]).dt.date.tolist()
        self.assertIn(date(2021, 6, 14), filtered_dates)
        self.assertIn(date(2022, 6, 1), filtered_dates)
        self.assertIn(date(2023, 12, 31), filtered_dates)
        self.assertNotIn(date(2021, 5, 1), filtered_dates)
        self.assertNotIn(date(2024, 1, 15), filtered_dates)

    def test_filter_ongoing_campaign(self):
        """Test filtering for ongoing campaign (no end date)."""
        # Events for Toshiba (ongoing campaign starting 2020-03-01)
        events_df = pd.DataFrame(
            {
                "security": ["8136 JP Equity"] * 4,
                "event_date": [
                    "2020-02-15",  # Before campaign
                    "2020-03-01",  # Campaign start
                    "2022-06-01",  # During campaign
                    "2025-01-01",  # Far future (ongoing, should be included)
                ],
                "event_type": ["Buyback"] * 4,
            }
        )

        # Filter
        filtered = self.extractor._filter_to_campaign_period(
            events_df, self.campaign_periods
        )

        # Verify 3 events (all except before campaign start)
        self.assertEqual(len(filtered), 3)

        filtered_dates = pd.to_datetime(filtered["event_date"]).dt.date.tolist()
        self.assertNotIn(date(2020, 2, 15), filtered_dates)
        self.assertIn(date(2020, 3, 1), filtered_dates)
        self.assertIn(date(2025, 1, 1), filtered_dates)

    def test_extract_dividend_history(self):
        """Test dividend extraction with campaign filtering."""
        # Mock Bloomberg response (full history, before filtering)
        mock_response = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 5,
                "Declared Date": [
                    "2021-05-01",  # Before campaign
                    "2021-09-01",  # During campaign
                    "2022-03-01",  # During campaign
                    "2022-09-01",  # During campaign
                    "2024-01-01",  # After campaign
                ],
                "Dividend Amount": [50, 55, 60, 65, 70],
                "Currency": ["JPY"] * 5,
                "Frequency": ["Semi-Annual"] * 5,
            }
        )

        self.mock_session.send_bulk_request.return_value = mock_response

        # Extract dividends
        result = self.extractor.extract_dividend_history(
            securities=["9107 JP Equity"],
            campaign_periods=self.campaign_periods,
        )

        # Verify only events during campaign (3 events)
        self.assertEqual(len(result), 3)

        # Verify dates
        result_dates = pd.to_datetime(result["event_date"]).dt.date.tolist()
        self.assertNotIn(date(2021, 5, 1), result_dates)  # Before campaign
        self.assertNotIn(date(2024, 1, 1), result_dates)  # After campaign

    def test_classify_dividend_events(self):
        """Test dividend event classification."""
        # Create dividend data with various patterns
        dividends_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 5,
                "event_date": pd.to_datetime(
                    ["2021-09-01", "2022-03-01", "2022-09-01", "2023-03-01", "2023-09-01"]
                ),
                "dividend_amount": [50, 55, 60, 60, 55],  # Increase, increase, no change, decrease
            }
        )

        # Classify
        classified = self.extractor._classify_dividend_events(dividends_df)

        # Verify classifications
        self.assertEqual(classified.loc[0, "event_type"], "Dividend Initiation")  # First dividend
        self.assertEqual(classified.loc[1, "event_type"], "Dividend Increase")  # 50 -> 55
        self.assertEqual(classified.loc[2, "event_type"], "Dividend Increase")  # 55 -> 60
        self.assertEqual(classified.loc[3, "event_type"], "Dividend (No Change)")  # 60 -> 60
        self.assertEqual(classified.loc[4, "event_type"], "Dividend Decrease")  # 60 -> 55

    def test_extract_buyback_history(self):
        """Test buyback extraction with campaign filtering."""
        # Mock Bloomberg response
        mock_response = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 3,
                "Announcement Date": [
                    "2021-05-01",  # Before campaign
                    "2022-06-01",  # During campaign
                    "2023-09-01",  # During campaign
                ],
                "Program Size": [10000000000, 15000000000, 20000000000],  # JPY
                "Currency": ["JPY"] * 3,
            }
        )

        self.mock_session.send_bulk_request.return_value = mock_response

        # Extract buybacks
        result = self.extractor.extract_buyback_history(
            securities=["9107 JP Equity"],
            campaign_periods=self.campaign_periods,
        )

        # Verify only 2 events during campaign
        self.assertEqual(len(result), 2)

        # Verify event type
        self.assertTrue((result["event_type"] == "Share Buyback").all())

    def test_extract_split_history(self):
        """Test stock split extraction with campaign filtering."""
        # Mock Bloomberg response
        mock_response = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 3,
                "Announcement Date": [
                    "2021-05-01",  # Before campaign
                    "2022-04-01",  # During campaign
                    "2023-10-01",  # During campaign
                ],
                "Split Ratio": ["2-FOR-1", "3-FOR-1", "1-FOR-2"],  # Forward, forward, reverse
                "Effective Date": ["2021-06-01", "2022-05-01", "2023-11-01"],
            }
        )

        self.mock_session.send_bulk_request.return_value = mock_response

        # Extract splits
        result = self.extractor.extract_split_history(
            securities=["9107 JP Equity"],
            campaign_periods=self.campaign_periods,
        )

        # Verify only 2 events during campaign
        self.assertEqual(len(result), 2)

    def test_classify_split_events(self):
        """Test split classification (forward vs reverse)."""
        splits_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 3,
                "event_date": pd.to_datetime(["2022-04-01", "2022-10-01", "2023-03-01"]),
                "split_ratio": ["2-FOR-1", "3-FOR-1", "1-FOR-2"],
            }
        )

        # Classify
        classified = self.extractor._classify_split_events(splits_df)

        # Verify classifications
        self.assertEqual(classified.loc[0, "event_type"], "Stock Split")  # 2-for-1
        self.assertEqual(classified.loc[1, "event_type"], "Stock Split")  # 3-for-1
        self.assertEqual(classified.loc[2, "event_type"], "Reverse Stock Split")  # 1-for-2

    def test_extract_ma_history(self):
        """Test M&A extraction with campaign filtering."""
        # Mock Bloomberg response
        mock_response = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 3,
                "Announcement Date": [
                    "2021-05-01",  # Before campaign
                    "2022-08-01",  # During campaign
                    "2023-11-01",  # During campaign
                ],
                "Deal Type": ["ACQUISITION", "DIVESTITURE", "MERGER"],
                "Target Name": ["Company A", "Division B", "Company C"],
                "Deal Value": [5000000000, 2000000000, 10000000000],
                "Currency": ["JPY"] * 3,
                "Status": ["Completed", "Announced", "Completed"],
            }
        )

        self.mock_session.send_bulk_request.return_value = mock_response

        # Extract M&A
        result = self.extractor.extract_ma_history(
            securities=["9107 JP Equity"],
            campaign_periods=self.campaign_periods,
        )

        # Verify only 2 events during campaign
        self.assertEqual(len(result), 2)

    def test_classify_ma_events(self):
        """Test M&A event classification."""
        ma_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 3,
                "event_date": pd.to_datetime(["2022-08-01", "2022-11-01", "2023-03-01"]),
                "deal_type": ["ACQUISITION", "DIVESTITURE", "MERGER"],
            }
        )

        # Classify
        classified = self.extractor._classify_ma_events(ma_df)

        # Verify classifications
        self.assertEqual(classified.loc[0, "event_type"], "M&A - Acquisition")
        self.assertEqual(classified.loc[1, "event_type"], "M&A - Divestiture")
        self.assertEqual(classified.loc[2, "event_type"], "M&A - Merger")

    def test_compute_months_after_entry(self):
        """Test months-after-entry computation."""
        events_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 3,
                "event_date": pd.to_datetime([
                    "2021-06-14",  # Campaign start (0 months)
                    "2021-12-14",  # ~6 months
                    "2022-06-14",  # ~12 months
                ]),
                "event_type": ["Dividend"] * 3,
            }
        )

        # Compute months
        result = self.extractor._compute_months_after_entry(
            events_df, self.campaign_periods
        )

        # Verify months
        self.assertAlmostEqual(result.loc[0, "months_after_activist_entry"], 0.0, places=1)
        self.assertAlmostEqual(result.loc[1, "months_after_activist_entry"], 6.0, places=0)
        self.assertAlmostEqual(result.loc[2, "months_after_activist_entry"], 12.0, places=0)

    def test_deduplicate_events(self):
        """Test event deduplication."""
        # Create events with duplicates
        events_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"] * 5,
                "event_type": ["Dividend", "Dividend", "Buyback", "Buyback", "Split"],
                "event_date": pd.to_datetime([
                    "2022-06-01",
                    "2022-06-01",  # Duplicate
                    "2022-09-01",
                    "2022-09-01",  # Duplicate
                    "2023-03-01",
                ]),
                "dividend_amount": [50, 50, None, None, None],  # Same dividend
                "program_amount": [None, None, 10000000000, 10000000000, None],  # Same buyback
            }
        )

        # Deduplicate
        deduped = self.extractor.deduplicate_events(events_df)

        # Verify duplicates removed (should have 3 events instead of 5)
        self.assertEqual(len(deduped), 3)

    def test_extract_all_events_integration(self):
        """Integration test: Extract all event types for multiple securities."""
        # Mock dividend response
        mock_dividends = pd.DataFrame(
            {
                "security": ["9107 JP Equity", "9107 JP Equity"],
                "Declared Date": ["2022-03-01", "2022-09-01"],
                "Dividend Amount": [50, 55],
                "Currency": ["JPY", "JPY"],
            }
        )

        # Mock buyback response
        mock_buybacks = pd.DataFrame(
            {
                "security": ["9107 JP Equity"],
                "Announcement Date": ["2023-06-01"],
                "Program Size": [15000000000],
                "Currency": ["JPY"],
            }
        )

        # Mock split response (empty)
        mock_splits = pd.DataFrame()

        # Mock M&A response (empty)
        mock_ma = pd.DataFrame()

        # Configure mock to return different responses based on field
        def side_effect_bulk(securities, field):
            if field == "DVD_HIST_ALL":
                return mock_dividends
            elif field == "SHARE_REPURCHASE_SUMMARY":
                return mock_buybacks
            elif field == "STOCK_SPLIT_HIST":
                return mock_splits
            elif field == "MERGERS_AND_ACQUISITIONS":
                return mock_ma
            else:
                return pd.DataFrame()

        self.mock_session.send_bulk_request.side_effect = side_effect_bulk

        # Extract all events
        all_events = self.extractor.extract_all_events(
            securities=["9107 JP Equity"],
            campaign_periods=self.campaign_periods,
        )

        # Verify we got dividends and buyback (3 total events)
        self.assertGreater(len(all_events), 0)

        # Verify event categories
        self.assertIn("event_category", all_events.columns)
        self.assertIn("months_after_activist_entry", all_events.columns)
        self.assertIn("campaign_status_at_event", all_events.columns)

        # All events should be "During Campaign"
        self.assertTrue((all_events["campaign_status_at_event"] == "During Campaign").all())


class TestEventsEdgeCases(unittest.TestCase):
    """Test edge cases and error handling."""

    def setUp(self):
        """Set up test fixtures."""
        self.mock_session = MagicMock()
        self.mock_session.session = MagicMock()
        self.extractor = EventsExtractor(session=self.mock_session)

    def test_empty_securities_list(self):
        """Test extraction with empty securities list."""
        campaign_periods = {}

        with self.assertRaises(ValueError) as context:
            self.extractor.extract_dividend_history([], campaign_periods)

        self.assertIn("No securities provided", str(context.exception))

    def test_bloomberg_api_error(self):
        """Test handling of Bloomberg API errors."""
        self.mock_session.send_bulk_request.side_effect = Exception("Connection failed")

        campaign_periods = {
            "9107 JP Equity": CampaignPeriod(
                ticker="9107 JP Equity",
                company_name="Sanrio",
                campaign_start=date(2021, 6, 14),
                campaign_end=None,
            )
        }

        with self.assertRaises(ValueError) as context:
            self.extractor.extract_dividend_history(
                securities=["9107 JP Equity"],
                campaign_periods=campaign_periods,
            )

        self.assertIn("Dividend extraction failed", str(context.exception))

    def test_no_events_during_campaign(self):
        """Test case where no events occur during campaign period."""
        # Mock response with events only outside campaign
        mock_response = pd.DataFrame(
            {
                "security": ["9107 JP Equity", "9107 JP Equity"],
                "Declared Date": ["2021-05-01", "2024-01-01"],  # Both outside campaign
                "Dividend Amount": [50, 55],
                "Currency": ["JPY", "JPY"],
            }
        )

        self.mock_session.send_bulk_request.return_value = mock_response

        campaign_periods = {
            "9107 JP Equity": CampaignPeriod(
                ticker="9107 JP Equity",
                company_name="Sanrio",
                campaign_start=date(2021, 6, 14),
                campaign_end=date(2023, 12, 31),
            )
        }

        # Extract dividends
        result = self.extractor.extract_dividend_history(
            securities=["9107 JP Equity"],
            campaign_periods=campaign_periods,
        )

        # Should return empty DataFrame
        self.assertEqual(len(result), 0)


if __name__ == "__main__":
    unittest.main()
