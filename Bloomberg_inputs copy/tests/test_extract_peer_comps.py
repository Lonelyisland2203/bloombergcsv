"""
Unit Tests for Peer Comparisons Extractor

Test Coverage:
    1. PeerCompTarget dataclass validation
    2. GICS sector identification
    3. Sector peer retrieval (placeholder)
    4. Sector median computation
    5. Discount/premium calculation
    6. ROE difference calculation
    7. Edge case: sector with <5 companies
    8. Edge case: missing GICS sector
    9. Full peer comp extraction workflow
    10. Integration test with multiple sectors

Edge Cases:
    - Company with missing GICS sector
    - Sector with insufficient peers (<5)
    - Missing valuation metrics
    - Division by zero in discount calculation
    - All peers missing a metric

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

from extract_peer_comps import (
    PeerCompTarget,
    SectorMedians,
    PeerCompsExtractor,
)


class TestPeerCompTarget(unittest.TestCase):
    """Test PeerCompTarget dataclass."""

    def test_valid_target(self):
        """Test creation of valid peer comp target."""
        target = PeerCompTarget(
            ticker="9107 JP Equity",
            company_name="Kawasaki Kisen Kaisha Ltd",
        )

        self.assertEqual(target.ticker, "9107 JP Equity")
        self.assertEqual(target.company_name, "Kawasaki Kisen Kaisha Ltd")
        self.assertIsNone(target.sector)
        self.assertIsNone(target.industry_group)

    def test_target_with_sector(self):
        """Test target with sector populated."""
        target = PeerCompTarget(
            ticker="9107 JP Equity",
            company_name="Kawasaki Kisen Kaisha Ltd",
            sector="Industrials",
            industry_group="Transportation",
        )

        self.assertEqual(target.sector, "Industrials")
        self.assertEqual(target.industry_group, "Transportation")


class TestSectorMedians(unittest.TestCase):
    """Test SectorMedians dataclass."""

    def test_valid_medians(self):
        """Test creation of sector medians."""
        medians = SectorMedians(
            sector_name="Industrials",
            median_pbr=1.2,
            median_roe=8.5,
            median_ev_ebitda=10.2,
            peer_count=15,
            metric_availability={"pbr": 14, "roe": 15, "ev_ebitda": 12},
        )

        self.assertEqual(medians.sector_name, "Industrials")
        self.assertEqual(medians.median_pbr, 1.2)
        self.assertEqual(medians.peer_count, 15)

    def test_medians_with_missing_data(self):
        """Test medians with some missing metrics."""
        medians = SectorMedians(
            sector_name="Materials",
            median_pbr=None,  # Missing
            median_roe=7.5,
            median_ev_ebitda=None,  # Missing
            peer_count=3,
        )

        self.assertIsNone(medians.median_pbr)
        self.assertEqual(medians.median_roe, 7.5)
        self.assertIsNone(medians.median_ev_ebitda)


class TestPeerCompsExtractor(unittest.TestCase):
    """Test PeerCompsExtractor methods."""

    def setUp(self):
        """Set up mock Bloomberg session for testing."""
        self.mock_session = Mock()
        self.mock_session.session = Mock()  # Active session
        self.extractor = PeerCompsExtractor(self.mock_session, min_peer_count=5)

    def test_initialization(self):
        """Test extractor initialization."""
        self.assertEqual(self.extractor.session, self.mock_session)
        self.assertEqual(self.extractor.min_peer_count, 5)

    def test_initialization_without_active_session(self):
        """Test initialization fails if session not started."""
        mock_session = Mock()
        mock_session.session = None  # Not started

        with self.assertRaises(ValueError):
            PeerCompsExtractor(mock_session)

    def test_identify_sector_success(self):
        """Test successful sector identification."""
        # Mock Bloomberg response
        mock_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"],
                "GICS_SECTOR_NAME": ["Industrials"],
                "GICS_INDUSTRY_GROUP_NAME": ["Transportation"],
            }
        )

        self.mock_session.send_request.return_value = mock_df

        sector, industry = self.extractor.identify_sector("9107 JP Equity")

        self.assertEqual(sector, "Industrials")
        self.assertEqual(industry, "Transportation")

    def test_identify_sector_missing_data(self):
        """Test sector identification with missing data."""
        # Mock Bloomberg response with NaN
        mock_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"],
                "GICS_SECTOR_NAME": [np.nan],
                "GICS_INDUSTRY_GROUP_NAME": [np.nan],
            }
        )

        self.mock_session.send_request.return_value = mock_df

        sector, industry = self.extractor.identify_sector("9107 JP Equity")

        self.assertIsNone(sector)
        self.assertIsNone(industry)

    def test_identify_sector_no_data(self):
        """Test sector identification with no data returned."""
        self.mock_session.send_request.return_value = pd.DataFrame()

        sector, industry = self.extractor.identify_sector("9107 JP Equity")

        self.assertIsNone(sector)
        self.assertIsNone(industry)

    def test_get_sector_peers_placeholder(self):
        """Test sector peer retrieval (placeholder implementation)."""
        # This is a placeholder - should return empty list
        peers = self.extractor.get_sector_peers("Industrials")

        self.assertEqual(peers, [])

    def test_compute_sector_medians_success(self):
        """Test sector median computation."""
        # Mock Bloomberg response with peer data
        mock_df = pd.DataFrame(
            {
                "security": ["PEER1 JP Equity", "PEER2 JP Equity", "PEER3 JP Equity"],
                "PX_TO_BOOK_RATIO": [1.0, 1.2, 1.5],
                "RETURN_COM_EQY": [8.0, 10.0, 12.0],
                "CUR_MKT_CAP": [100000, 150000, 200000],
                "NET_DEBT": [50000, 60000, 70000],
                "EBITDA": [10000, 12000, 15000],
            }
        )

        self.mock_session.send_request.return_value = mock_df

        peers = ["PEER1 JP Equity", "PEER2 JP Equity", "PEER3 JP Equity"]
        medians = self.extractor.compute_sector_medians(peers, "Industrials")

        # Verify medians
        self.assertEqual(medians.sector_name, "Industrials")
        self.assertEqual(medians.median_pbr, 1.2)  # Median of [1.0, 1.2, 1.5]
        self.assertEqual(medians.median_roe, 10.0)  # Median of [8.0, 10.0, 12.0]
        self.assertIsNotNone(medians.median_ev_ebitda)
        self.assertEqual(medians.peer_count, 3)

    def test_compute_sector_medians_with_missing_values(self):
        """Test sector median computation with missing values."""
        # Mock Bloomberg response with some NaN values
        mock_df = pd.DataFrame(
            {
                "security": ["PEER1 JP Equity", "PEER2 JP Equity", "PEER3 JP Equity"],
                "PX_TO_BOOK_RATIO": [1.0, np.nan, 1.5],
                "RETURN_COM_EQY": [8.0, 10.0, np.nan],
                "CUR_MKT_CAP": [100000, 150000, 200000],
                "NET_DEBT": [50000, np.nan, 70000],
                "EBITDA": [10000, 12000, 15000],
            }
        )

        self.mock_session.send_request.return_value = mock_df

        peers = ["PEER1 JP Equity", "PEER2 JP Equity", "PEER3 JP Equity"]
        medians = self.extractor.compute_sector_medians(peers, "Industrials")

        # Verify medians (should ignore NaN)
        self.assertEqual(medians.median_pbr, 1.25)  # Median of [1.0, 1.5]
        self.assertEqual(medians.median_roe, 9.0)  # Median of [8.0, 10.0]

        # Verify metric availability
        self.assertEqual(medians.metric_availability["pbr"], 2)
        self.assertEqual(medians.metric_availability["roe"], 2)

    def test_compute_sector_medians_no_peers(self):
        """Test sector median computation with no peers."""
        medians = self.extractor.compute_sector_medians([], "Industrials")

        self.assertEqual(medians.sector_name, "Industrials")
        self.assertEqual(medians.peer_count, 0)
        self.assertIsNone(medians.median_pbr)

    def test_compute_sector_medians_no_data_returned(self):
        """Test sector median computation with no data from Bloomberg."""
        self.mock_session.send_request.return_value = pd.DataFrame()

        peers = ["PEER1 JP Equity", "PEER2 JP Equity"]
        medians = self.extractor.compute_sector_medians(peers, "Industrials")

        self.assertEqual(medians.peer_count, 2)
        self.assertIsNone(medians.median_pbr)

    def test_compute_discount_premium_success(self):
        """Test discount/premium calculation."""
        # Company trading at discount
        discount = self.extractor.compute_discount_premium(0.8, 1.2)
        self.assertAlmostEqual(discount, -0.3333333, places=6)

        # Company trading at premium
        premium = self.extractor.compute_discount_premium(1.5, 1.2)
        self.assertAlmostEqual(premium, 0.25, places=6)

        # Company at sector median
        neutral = self.extractor.compute_discount_premium(1.2, 1.2)
        self.assertAlmostEqual(neutral, 0.0, places=6)

    def test_compute_discount_premium_missing_values(self):
        """Test discount/premium with missing values."""
        # Company value missing
        result = self.extractor.compute_discount_premium(np.nan, 1.2)
        self.assertTrue(np.isnan(result))

        # Sector median missing
        result = self.extractor.compute_discount_premium(1.0, np.nan)
        self.assertTrue(np.isnan(result))

    def test_compute_discount_premium_zero_median(self):
        """Test discount/premium with zero sector median."""
        result = self.extractor.compute_discount_premium(1.0, 0.0)
        self.assertTrue(np.isnan(result))

    def test_compute_roe_difference_success(self):
        """Test ROE difference calculation."""
        # Underperforming sector
        diff = self.extractor.compute_roe_difference(8.5, 12.0)
        self.assertEqual(diff, -3.5)

        # Outperforming sector
        diff = self.extractor.compute_roe_difference(15.0, 12.0)
        self.assertEqual(diff, 3.0)

        # At sector median
        diff = self.extractor.compute_roe_difference(12.0, 12.0)
        self.assertEqual(diff, 0.0)

    def test_compute_roe_difference_missing_values(self):
        """Test ROE difference with missing values."""
        result = self.extractor.compute_roe_difference(np.nan, 12.0)
        self.assertTrue(np.isnan(result))

        result = self.extractor.compute_roe_difference(8.5, np.nan)
        self.assertTrue(np.isnan(result))

    def test_extract_peer_comps_success(self):
        """Test full peer comp extraction."""
        # Create targets
        targets = [
            PeerCompTarget(
                ticker="9107 JP Equity",
                company_name="Kawasaki Kisen",
            ),
            PeerCompTarget(
                ticker="8136 JP Equity",
                company_name="Sanrio",
            ),
        ]

        # Create snapshot DataFrame
        snapshot_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity", "8136 JP Equity"],
                "PX_TO_BOOK_RATIO": [0.8, 2.5],
                "RETURN_COM_EQY": [8.5, 15.0],
                "CUR_MKT_CAP": [100000, 200000],
                "NET_DEBT": [50000, -30000],
                "EBITDA": [10000, 25000],
            }
        )

        # Mock sector identification
        def mock_identify_sector(ticker):
            if ticker == "9107 JP Equity":
                return "Industrials", "Transportation"
            else:
                return "Consumer Discretionary", "Consumer Services"

        # Mock sector peers (empty - placeholder)
        def mock_get_sector_peers(sector, **kwargs):
            return []

        # Mock sector medians computation
        def mock_compute_sector_medians(peers, sector_name):
            if "Industrials" in sector_name:
                return SectorMedians(
                    sector_name=sector_name,
                    median_pbr=1.2,
                    median_roe=10.0,
                    median_ev_ebitda=12.0,
                    peer_count=10,
                )
            else:
                return SectorMedians(
                    sector_name=sector_name,
                    median_pbr=3.0,
                    median_roe=18.0,
                    median_ev_ebitda=15.0,
                    peer_count=8,
                )

        with patch.object(
            self.extractor, "identify_sector", side_effect=mock_identify_sector
        ):
            with patch.object(
                self.extractor, "get_sector_peers", side_effect=mock_get_sector_peers
            ):
                with patch.object(
                    self.extractor,
                    "compute_sector_medians",
                    side_effect=mock_compute_sector_medians,
                ):
                    result = self.extractor.extract_peer_comps(targets, snapshot_df)

        # Verify result structure
        self.assertEqual(len(result), 2)
        self.assertIn("ticker", result.columns)
        self.assertIn("sector", result.columns)
        self.assertIn("pbr_vs_sector", result.columns)
        self.assertIn("roe_vs_sector", result.columns)
        self.assertIn("ev_ebitda_vs_sector", result.columns)

        # Verify 9107 JP Equity (Industrials)
        row_9107 = result[result["ticker"] == "9107 JP Equity"].iloc[0]
        self.assertEqual(row_9107["sector"], "Industrials")
        self.assertEqual(row_9107["company_pbr"], 0.8)
        self.assertEqual(row_9107["sector_median_pbr"], 1.2)
        self.assertAlmostEqual(
            row_9107["pbr_vs_sector"], -0.3333333, places=6
        )  # (0.8/1.2) - 1

        # Verify 8136 JP Equity (Consumer Discretionary)
        row_8136 = result[result["ticker"] == "8136 JP Equity"].iloc[0]
        self.assertEqual(row_8136["sector"], "Consumer Discretionary")
        self.assertEqual(row_8136["company_pbr"], 2.5)
        self.assertAlmostEqual(
            row_8136["pbr_vs_sector"], -0.1666667, places=6
        )  # (2.5/3.0) - 1

    def test_extract_peer_comps_no_targets(self):
        """Test extraction with no targets."""
        with self.assertRaises(ValueError):
            self.extractor.extract_peer_comps([], pd.DataFrame())

    def test_extract_peer_comps_empty_snapshot(self):
        """Test extraction with empty snapshot."""
        targets = [
            PeerCompTarget(
                ticker="9107 JP Equity",
                company_name="Kawasaki Kisen",
            )
        ]

        with self.assertRaises(ValueError):
            self.extractor.extract_peer_comps(targets, pd.DataFrame())

    def test_extract_peer_comps_target_not_in_snapshot(self):
        """Test extraction when target not found in snapshot."""
        targets = [
            PeerCompTarget(
                ticker="9107 JP Equity",
                company_name="Kawasaki Kisen",
            )
        ]

        snapshot_df = pd.DataFrame(
            {
                "security": ["8136 JP Equity"],  # Different ticker
                "PX_TO_BOOK_RATIO": [2.5],
                "RETURN_COM_EQY": [15.0],
                "CUR_MKT_CAP": [200000],
                "NET_DEBT": [-30000],
                "EBITDA": [25000],
            }
        )

        # Mock sector identification
        with patch.object(
            self.extractor, "identify_sector", return_value=("Industrials", "Transportation")
        ):
            result = self.extractor.extract_peer_comps(targets, snapshot_df)

        # Should return empty result (target skipped)
        self.assertEqual(len(result), 0)

    def test_extract_peer_comps_missing_sector(self):
        """Test extraction when sector is missing."""
        targets = [
            PeerCompTarget(
                ticker="9107 JP Equity",
                company_name="Kawasaki Kisen",
            )
        ]

        snapshot_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity"],
                "PX_TO_BOOK_RATIO": [0.8],
                "RETURN_COM_EQY": [8.5],
                "CUR_MKT_CAP": [100000],
                "NET_DEBT": [50000],
                "EBITDA": [10000],
            }
        )

        # Mock sector identification returning None
        with patch.object(
            self.extractor, "identify_sector", return_value=(None, None)
        ):
            result = self.extractor.extract_peer_comps(targets, snapshot_df)

        # Should return result with sector = "N/A" and no peer data
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]["sector"], "N/A")
        self.assertTrue(np.isnan(result.iloc[0]["pbr_vs_sector"]))

    def test_compute_ev_ebitda_single(self):
        """Test EV/EBITDA computation for single row."""
        row = pd.Series(
            {
                "CUR_MKT_CAP": 100000,
                "NET_DEBT": 50000,
                "EBITDA": 10000,
            }
        )

        ev_ebitda = self.extractor._compute_ev_ebitda_single(row)

        # EV = 100000 + 50000 = 150000
        # EV/EBITDA = 150000 / 10000 = 15.0
        self.assertEqual(ev_ebitda, 15.0)

    def test_compute_ev_ebitda_single_missing_data(self):
        """Test EV/EBITDA with missing data."""
        row = pd.Series(
            {
                "CUR_MKT_CAP": 100000,
                "NET_DEBT": 50000,
                "EBITDA": np.nan,  # Missing
            }
        )

        ev_ebitda = self.extractor._compute_ev_ebitda_single(row)

        self.assertTrue(np.isnan(ev_ebitda))

    def test_compute_ev_ebitda_single_zero_ebitda(self):
        """Test EV/EBITDA with zero EBITDA."""
        row = pd.Series(
            {
                "CUR_MKT_CAP": 100000,
                "NET_DEBT": 50000,
                "EBITDA": 0,  # Zero
            }
        )

        ev_ebitda = self.extractor._compute_ev_ebitda_single(row)

        self.assertTrue(np.isnan(ev_ebitda))


class TestIntegrationPeerComps(unittest.TestCase):
    """Integration tests with realistic scenarios."""

    def test_full_peer_comp_workflow_multiple_sectors(self):
        """Test complete workflow with multiple sectors."""
        # Create mock session
        mock_session = Mock()
        mock_session.session = Mock()

        extractor = PeerCompsExtractor(mock_session, min_peer_count=5)

        # Create targets from different sectors
        targets = [
            PeerCompTarget(ticker="9107 JP Equity", company_name="Kawasaki Kisen"),
            PeerCompTarget(ticker="8136 JP Equity", company_name="Sanrio"),
            PeerCompTarget(ticker="4063 JP Equity", company_name="Shin-Etsu Chemical"),
        ]

        # Create snapshot data
        snapshot_df = pd.DataFrame(
            {
                "security": ["9107 JP Equity", "8136 JP Equity", "4063 JP Equity"],
                "PX_TO_BOOK_RATIO": [0.8, 2.5, 1.5],
                "RETURN_COM_EQY": [8.5, 15.0, 12.0],
                "CUR_MKT_CAP": [100000, 200000, 500000],
                "NET_DEBT": [50000, -30000, 100000],
                "EBITDA": [10000, 25000, 50000],
            }
        )

        # Mock sector identification
        sector_map = {
            "9107 JP Equity": ("Industrials", "Transportation"),
            "8136 JP Equity": ("Consumer Discretionary", "Consumer Services"),
            "4063 JP Equity": ("Materials", "Chemicals"),
        }

        def mock_identify_sector(ticker):
            return sector_map.get(ticker, (None, None))

        # Mock sector medians
        sector_medians_map = {
            "Industrials": SectorMedians(
                "Industrials",
                median_pbr=1.2,
                median_roe=10.0,
                median_ev_ebitda=12.0,
                peer_count=15,
            ),
            "Consumer Discretionary": SectorMedians(
                "Consumer Discretionary",
                median_pbr=3.0,
                median_roe=18.0,
                median_ev_ebitda=15.0,
                peer_count=12,
            ),
            "Materials": SectorMedians(
                "Materials",
                median_pbr=1.8,
                median_roe=14.0,
                median_ev_ebitda=10.0,
                peer_count=10,
            ),
        }

        def mock_compute_sector_medians(peers, sector_name):
            return sector_medians_map.get(sector_name, SectorMedians(sector_name))

        with patch.object(
            extractor, "identify_sector", side_effect=mock_identify_sector
        ):
            with patch.object(
                extractor, "get_sector_peers", return_value=[]
            ):
                with patch.object(
                    extractor,
                    "compute_sector_medians",
                    side_effect=mock_compute_sector_medians,
                ):
                    result = extractor.extract_peer_comps(targets, snapshot_df)

        # Verify all targets processed
        self.assertEqual(len(result), 3)

        # Verify sector assignments
        sectors = result["sector"].tolist()
        self.assertIn("Industrials", sectors)
        self.assertIn("Consumer Discretionary", sectors)
        self.assertIn("Materials", sectors)

        # Verify discount/premium calculations exist
        self.assertFalse(result["pbr_vs_sector"].isna().all())
        self.assertFalse(result["roe_vs_sector"].isna().all())


if __name__ == "__main__":
    unittest.main()
