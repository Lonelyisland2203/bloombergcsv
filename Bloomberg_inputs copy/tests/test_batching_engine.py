"""
Unit Tests for Batching Engine Module

Tests cover:
1. FieldGroupManager: Field loading, grouping, validation
2. RateLimitTracker: Wait enforcement, timestamp recording
3. BatchingEngine: Batch creation, field grouping, size limits
4. Batch execution: Retry logic, exponential backoff, error handling
5. Parallel execution: ThreadPoolExecutor usage, result merging
6. Integration: Complete workflow with mock Bloomberg session

Test Coverage Target: >85%
"""

import pytest
import sys
import time
from datetime import date
from pathlib import Path
from unittest.mock import MagicMock, Mock, patch, call
import pandas as pd

# Add src directory to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from batching_engine import (
    BatchingEngine,
    FieldGroupManager,
    RateLimitTracker,
    RequestBatch,
    BatchExecutionResult,
)


class TestFieldGroupManager:
    """Test FieldGroupManager functionality."""

    def test_initialization_success(self):
        """Test successful initialization with config file."""
        manager = FieldGroupManager()
        assert manager.field_groups is not None
        assert manager.override_map is not None
        assert len(manager.field_groups) > 0

    def test_initialization_with_explicit_path(self):
        """Test initialization with explicit config path."""
        config_path = Path(__file__).parent.parent / "config" / "bloomberg_fields.yaml"
        manager = FieldGroupManager(config_path=config_path)
        assert manager.config_path == config_path
        assert len(manager.field_groups) > 0

    def test_initialization_missing_config(self):
        """Test initialization fails with missing config."""
        with pytest.raises(FileNotFoundError, match="Bloomberg fields config not found"):
            FieldGroupManager(config_path=Path("/nonexistent/path.yaml"))

    def test_get_override_type(self):
        """Test retrieving override type for known fields."""
        manager = FieldGroupManager()

        # Valuation metrics: END_DT_OVERRIDE
        assert manager.get_override_type("PX_TO_BOOK_RATIO") == "END_DT_OVERRIDE"
        assert manager.get_override_type("PE_RATIO") == "END_DT_OVERRIDE"

        # Profitability metrics: FUND_PER
        assert manager.get_override_type("RETURN_COM_EQY") == "FUND_PER"
        assert manager.get_override_type("RETURN_ON_ASSET") == "FUND_PER"

        # Governance metrics: none
        assert manager.get_override_type("FISCAL_YEAR_END_MONTH_DE") == "none"

        # Bulk fields: bulk
        assert manager.get_override_type("TOP_20_HOLDERS_PUBLIC_FILINGS") == "bulk"

    def test_get_override_type_unknown_field(self):
        """Test retrieving override type for unknown field."""
        manager = FieldGroupManager()
        assert manager.get_override_type("UNKNOWN_FIELD_XYZ") is None

    def test_get_fields_by_group(self):
        """Test retrieving all fields in a group."""
        manager = FieldGroupManager()

        # Get valuation metrics
        valuation_fields = manager.get_fields_by_group("valuation_metrics")
        assert "PX_TO_BOOK_RATIO" in valuation_fields
        assert "PE_RATIO" in valuation_fields
        assert isinstance(valuation_fields, list)

        # Get profitability metrics
        profitability_fields = manager.get_fields_by_group("profitability_metrics")
        assert "RETURN_COM_EQY" in profitability_fields
        assert "RETURN_ON_ASSET" in profitability_fields

    def test_get_fields_by_group_invalid(self):
        """Test error when requesting invalid group."""
        manager = FieldGroupManager()
        with pytest.raises(KeyError, match="Field group .* not found"):
            manager.get_fields_by_group("nonexistent_group")

    def test_get_fields_by_override_type(self):
        """Test retrieving all fields with specific override type."""
        manager = FieldGroupManager()

        # Get all FUND_PER fields
        fund_per_fields = manager.get_fields_by_override_type("FUND_PER")
        assert "RETURN_COM_EQY" in fund_per_fields
        assert "BS_CASH_NEAR_CASH_ITEM" in fund_per_fields
        assert len(fund_per_fields) > 0

        # Get all END_DT_OVERRIDE fields
        end_dt_fields = manager.get_fields_by_override_type("END_DT_OVERRIDE")
        assert "PX_TO_BOOK_RATIO" in end_dt_fields
        assert "CUR_MKT_CAP" in end_dt_fields

    def test_validate_fields(self):
        """Test field validation."""
        manager = FieldGroupManager()

        # All valid fields
        valid, invalid = manager.validate_fields([
            "PX_TO_BOOK_RATIO",
            "RETURN_COM_EQY",
            "FISCAL_YEAR_END_MONTH_DE",
        ])
        assert len(valid) == 3
        assert len(invalid) == 0

        # Mixed valid and invalid
        valid, invalid = manager.validate_fields([
            "PX_TO_BOOK_RATIO",
            "INVALID_FIELD_1",
            "RETURN_COM_EQY",
            "INVALID_FIELD_2",
        ])
        assert len(valid) == 2
        assert len(invalid) == 2
        assert "INVALID_FIELD_1" in invalid
        assert "INVALID_FIELD_2" in invalid

        # All invalid
        valid, invalid = manager.validate_fields([
            "UNKNOWN_1",
            "UNKNOWN_2",
        ])
        assert len(valid) == 0
        assert len(invalid) == 2

    def test_group_fields_by_override(self):
        """Test grouping fields by override type."""
        manager = FieldGroupManager()

        fields = [
            "PX_TO_BOOK_RATIO",  # END_DT_OVERRIDE
            "RETURN_COM_EQY",  # FUND_PER
            "FISCAL_YEAR_END_MONTH_DE",  # none
            "TOP_20_HOLDERS_PUBLIC_FILINGS",  # bulk
            "UNKNOWN_FIELD",  # unknown
        ]

        grouped = manager.group_fields_by_override(fields)

        assert "END_DT_OVERRIDE" in grouped
        assert "PX_TO_BOOK_RATIO" in grouped["END_DT_OVERRIDE"]

        assert "FUND_PER" in grouped
        assert "RETURN_COM_EQY" in grouped["FUND_PER"]

        assert "none" in grouped
        assert "FISCAL_YEAR_END_MONTH_DE" in grouped["none"]

        assert "bulk" in grouped
        assert "TOP_20_HOLDERS_PUBLIC_FILINGS" in grouped["bulk"]

        assert "unknown" in grouped
        assert "UNKNOWN_FIELD" in grouped["unknown"]

    def test_group_fields_by_override_homogeneous(self):
        """Test grouping when all fields have same override type."""
        manager = FieldGroupManager()

        # All FUND_PER fields
        fields = ["RETURN_COM_EQY", "RETURN_ON_ASSET", "OPER_MARGIN"]
        grouped = manager.group_fields_by_override(fields)

        assert len(grouped) == 1
        assert "FUND_PER" in grouped
        assert len(grouped["FUND_PER"]) == 3


class TestRateLimitTracker:
    """Test RateLimitTracker functionality."""

    def test_initialization(self):
        """Test tracker initialization."""
        tracker = RateLimitTracker(min_interval_seconds=2.0)
        assert tracker.min_interval_seconds == 2.0
        assert tracker.request_timestamps == []
        assert tracker.max_history == 100

    def test_record_request(self):
        """Test recording request timestamps."""
        tracker = RateLimitTracker()
        tracker.record_request()
        assert len(tracker.request_timestamps) == 1

        tracker.record_request()
        assert len(tracker.request_timestamps) == 2

    def test_wait_if_needed_no_wait(self):
        """Test no wait when no previous requests."""
        tracker = RateLimitTracker(min_interval_seconds=2.0)
        wait_time = tracker.wait_if_needed()
        assert wait_time == 0.0

    @patch("time.sleep")
    @patch("time.time")
    def test_wait_if_needed_enforces_delay(self, mock_time, mock_sleep):
        """Test wait enforcement when interval too short."""
        tracker = RateLimitTracker(min_interval_seconds=2.0)

        # Simulate first request at t=0
        mock_time.return_value = 0.0
        tracker.record_request()

        # Second request at t=1.0 (within 2s window)
        mock_time.return_value = 1.0
        wait_time = tracker.wait_if_needed()

        # Should wait 1s (2.0 - 1.0)
        assert wait_time == 1.0
        mock_sleep.assert_called_once_with(1.0)

    @patch("time.time")
    def test_wait_if_needed_no_enforcement(self, mock_time):
        """Test no wait when interval sufficient."""
        tracker = RateLimitTracker(min_interval_seconds=2.0)

        # First request at t=0
        mock_time.return_value = 0.0
        tracker.record_request()

        # Second request at t=3.0 (after 2s window)
        mock_time.return_value = 3.0
        wait_time = tracker.wait_if_needed()

        # Should not wait
        assert wait_time == 0.0

    def test_history_trimming(self):
        """Test that history is trimmed to max_history size."""
        tracker = RateLimitTracker(max_history=10)

        # Add 20 requests
        for _ in range(20):
            tracker.record_request()

        # Should only keep last 10
        assert len(tracker.request_timestamps) == 10


class TestBatchingEngine:
    """Test BatchingEngine core functionality."""

    def test_initialization(self):
        """Test engine initialization."""
        engine = BatchingEngine(
            max_batch_size=20,
            min_delay_seconds=2.0,
            max_retries=3,
        )
        assert engine.max_batch_size == 20
        assert engine.min_delay_seconds == 2.0
        assert engine.max_retries == 3
        assert engine.field_manager is not None
        assert engine.rate_tracker is not None

    def test_create_batches_single_batch(self):
        """Test batch creation when all securities fit in one batch."""
        engine = BatchingEngine(max_batch_size=20)

        securities = ["9107 JP Equity", "7157 JP Equity", "6707 JP Equity"]
        fields = ["PX_TO_BOOK_RATIO", "PE_RATIO"]

        batches = engine.create_batches(securities, fields)

        assert len(batches) == 1
        assert batches[0].securities == securities
        assert batches[0].fields == fields
        assert batches[0].override_type == "END_DT_OVERRIDE"

    def test_create_batches_multiple_batches(self):
        """Test batch creation splits large security list."""
        engine = BatchingEngine(max_batch_size=5)

        # 12 securities -> should create 3 batches (5 + 5 + 2)
        securities = [f"TICKER{i:02d} JP Equity" for i in range(12)]
        fields = ["PX_TO_BOOK_RATIO"]

        batches = engine.create_batches(securities, fields)

        assert len(batches) == 3
        assert len(batches[0].securities) == 5
        assert len(batches[1].securities) == 5
        assert len(batches[2].securities) == 2

        # All batches should have same fields
        for batch in batches:
            assert batch.fields == fields

    def test_create_batches_preserves_order(self):
        """Test that batch creation preserves security order."""
        engine = BatchingEngine(max_batch_size=3)

        securities = ["A JP Equity", "B JP Equity", "C JP Equity", "D JP Equity"]
        fields = ["PX_TO_BOOK_RATIO"]

        batches = engine.create_batches(securities, fields)

        # Reconstruct order from batches
        reconstructed = []
        for batch in batches:
            reconstructed.extend(batch.securities)

        assert reconstructed == securities

    def test_create_batches_empty_securities(self):
        """Test batch creation with empty security list."""
        engine = BatchingEngine()
        batches = engine.create_batches([], ["PX_TO_BOOK_RATIO"])
        assert batches == []

    def test_create_batches_empty_fields(self):
        """Test batch creation with empty field list."""
        engine = BatchingEngine()
        batches = engine.create_batches(["9107 JP Equity"], [])
        assert batches == []

    def test_create_batches_batch_ids(self):
        """Test that batch IDs are sequential and informative."""
        engine = BatchingEngine(max_batch_size=2)

        securities = ["A JP Equity", "B JP Equity", "C JP Equity"]
        fields = ["RETURN_COM_EQY"]  # FUND_PER field

        batches = engine.create_batches(securities, fields)

        assert len(batches) == 2
        assert "FUND_PER" in batches[0].batch_id
        assert "001_of_002" in batches[0].batch_id
        assert "002_of_002" in batches[1].batch_id

    def test_group_fields_by_override(self):
        """Test field grouping delegates to FieldGroupManager."""
        engine = BatchingEngine()

        fields = [
            "PX_TO_BOOK_RATIO",  # END_DT_OVERRIDE
            "RETURN_COM_EQY",  # FUND_PER
        ]

        grouped = engine.group_fields_by_override(fields)

        assert "END_DT_OVERRIDE" in grouped
        assert "FUND_PER" in grouped
        assert len(grouped["END_DT_OVERRIDE"]) == 1
        assert len(grouped["FUND_PER"]) == 1

    def test_track_rate_limits(self):
        """Test rate limit statistics tracking."""
        engine = BatchingEngine()

        stats = engine.track_rate_limits()

        assert "total_batches_executed" in stats
        assert "total_retries" in stats
        assert "total_failures" in stats
        assert "requests_last_minute" in stats
        assert stats["total_batches_executed"] == 0  # Initial state

    def test_get_statistics(self):
        """Test comprehensive statistics."""
        engine = BatchingEngine()

        stats = engine.get_statistics()

        assert "success_rate" in stats
        assert "retry_rate" in stats
        assert stats["success_rate"] == 0.0  # Initial state


class TestBatchExecution:
    """Test batch execution with retry logic."""

    def test_execute_batch_success_first_attempt(self):
        """Test successful batch execution on first attempt."""
        engine = BatchingEngine(max_retries=3)

        # Mock Bloomberg session
        mock_session = MagicMock()
        mock_df = pd.DataFrame({
            "security": ["9107 JP Equity"],
            "PX_TO_BOOK_RATIO": [1.23],
        })
        mock_session.send_request.return_value = mock_df

        # Create batch
        batch = RequestBatch(
            securities=["9107 JP Equity"],
            fields=["PX_TO_BOOK_RATIO"],
            override_type="END_DT_OVERRIDE",
            batch_id="test_001",
        )

        # Execute
        result = engine.execute_batch_with_backoff(
            mock_session, batch, override_value="20210331"
        )

        assert result.success is True
        assert result.data is not None
        assert len(result.data) == 1
        assert result.retry_count == 0
        assert result.error_message is None

        # Verify session called correctly
        mock_session.send_request.assert_called_once()
        call_args = mock_session.send_request.call_args
        assert call_args[1]["overrides"] == {"END_DT_OVERRIDE": "20210331"}

    @patch("time.sleep")
    def test_execute_batch_retry_on_error(self, mock_sleep):
        """Test retry logic with exponential backoff."""
        engine = BatchingEngine(max_retries=2)

        # Mock session that fails twice then succeeds
        mock_session = MagicMock()
        mock_df = pd.DataFrame({
            "security": ["9107 JP Equity"],
            "PX_TO_BOOK_RATIO": [1.23],
        })

        # First two calls fail, third succeeds
        mock_session.send_request.side_effect = [
            Exception("Network error"),
            Exception("Network error"),
            mock_df,
        ]

        batch = RequestBatch(
            securities=["9107 JP Equity"],
            fields=["PX_TO_BOOK_RATIO"],
            override_type="END_DT_OVERRIDE",
            batch_id="test_001",
        )

        result = engine.execute_batch_with_backoff(mock_session, batch)

        assert result.success is True
        assert result.retry_count == 2
        assert mock_session.send_request.call_count == 3

        # Verify backoff delays: First retry has 0s (backoff_schedule[0]),
        # second retry has 2s (backoff_schedule[1])
        # Only sleep when wait_time > 0
        assert mock_sleep.call_count == 1
        mock_sleep.assert_called_with(2)

    @patch("time.sleep")
    def test_execute_batch_max_retries_exceeded(self, mock_sleep):
        """Test failure after max retries exceeded."""
        engine = BatchingEngine(max_retries=2)

        # Mock session that always fails
        mock_session = MagicMock()
        mock_session.send_request.side_effect = Exception("Persistent error")

        batch = RequestBatch(
            securities=["9107 JP Equity"],
            fields=["PX_TO_BOOK_RATIO"],
            override_type="END_DT_OVERRIDE",
            batch_id="test_001",
        )

        result = engine.execute_batch_with_backoff(mock_session, batch)

        assert result.success is False
        assert result.data is None
        assert "Persistent error" in result.error_message
        assert mock_session.send_request.call_count == 3  # Initial + 2 retries

    def test_execute_batch_bulk_field(self):
        """Test execution of bulk field request."""
        engine = BatchingEngine()

        # Mock session
        mock_session = MagicMock()
        mock_df = pd.DataFrame({
            "security": ["9107 JP Equity"],
            "holder_name": ["Nomura Asset Management"],
            "shares_held": [1000000],
        })
        mock_session.send_bulk_request.return_value = mock_df

        batch = RequestBatch(
            securities=["9107 JP Equity"],
            fields=["TOP_20_HOLDERS_PUBLIC_FILINGS"],
            override_type="bulk",
            batch_id="bulk_001",
        )

        result = engine.execute_batch_with_backoff(mock_session, batch)

        assert result.success is True
        assert result.data is not None
        mock_session.send_bulk_request.assert_called_once_with(
            securities=["9107 JP Equity"],
            field="TOP_20_HOLDERS_PUBLIC_FILINGS",
        )

    def test_execute_batch_bulk_multiple_fields_error(self):
        """Test that bulk batch with multiple fields raises error."""
        engine = BatchingEngine()

        mock_session = MagicMock()

        batch = RequestBatch(
            securities=["9107 JP Equity"],
            fields=["TOP_20_HOLDERS_PUBLIC_FILINGS", "DVD_HIST_ALL"],  # Multiple fields
            override_type="bulk",
            batch_id="bulk_001",
        )

        result = engine.execute_batch_with_backoff(mock_session, batch)

        assert result.success is False
        assert "exactly 1 field" in result.error_message

    def test_execute_batch_with_fund_per_override(self):
        """Test batch execution with FUND_PER override."""
        engine = BatchingEngine()

        mock_session = MagicMock()
        mock_df = pd.DataFrame({
            "security": ["9107 JP Equity"],
            "RETURN_COM_EQY": [8.5],
        })
        mock_session.send_request.return_value = mock_df

        batch = RequestBatch(
            securities=["9107 JP Equity"],
            fields=["RETURN_COM_EQY"],
            override_type="FUND_PER",
            batch_id="fund_001",
        )

        result = engine.execute_batch_with_backoff(
            mock_session, batch, override_value="FY2021"
        )

        assert result.success is True

        # Verify override passed correctly
        call_args = mock_session.send_request.call_args
        assert call_args[1]["overrides"] == {"FUND_PER": "FY2021"}

    def test_execute_batch_no_override_for_none_type(self):
        """Test that no overrides used for 'none' type fields."""
        engine = BatchingEngine()

        mock_session = MagicMock()
        mock_df = pd.DataFrame({
            "security": ["9107 JP Equity"],
            "FISCAL_YEAR_END_MONTH_DE": [3],
        })
        mock_session.send_request.return_value = mock_df

        batch = RequestBatch(
            securities=["9107 JP Equity"],
            fields=["FISCAL_YEAR_END_MONTH_DE"],
            override_type="none",
            batch_id="none_001",
        )

        result = engine.execute_batch_with_backoff(
            mock_session, batch, override_value="IGNORED"
        )

        assert result.success is True

        # Verify no overrides passed
        call_args = mock_session.send_request.call_args
        overrides = call_args[1].get("overrides")
        assert overrides is None


class TestParallelExecution:
    """Test parallel batch execution."""

    def test_execute_batches_parallel_success(self):
        """Test successful parallel execution of multiple batches."""
        engine = BatchingEngine()

        # Mock session
        mock_session = MagicMock()

        # Create different responses for each batch
        def mock_send_request(securities, fields, overrides=None):
            return pd.DataFrame({
                "security": securities,
                fields[0]: [1.0] * len(securities),
            })

        mock_session.send_request.side_effect = mock_send_request

        # Create batches
        batches = [
            RequestBatch(
                securities=["A JP Equity"],
                fields=["PX_TO_BOOK_RATIO"],
                override_type="END_DT_OVERRIDE",
                batch_id="batch_001",
            ),
            RequestBatch(
                securities=["B JP Equity"],
                fields=["PX_TO_BOOK_RATIO"],
                override_type="END_DT_OVERRIDE",
                batch_id="batch_002",
            ),
            RequestBatch(
                securities=["C JP Equity"],
                fields=["PX_TO_BOOK_RATIO"],
                override_type="END_DT_OVERRIDE",
                batch_id="batch_003",
            ),
        ]

        overrides = {"END_DT_OVERRIDE": "20210331"}

        result_df = engine.execute_batches_parallel(
            mock_session, batches, overrides, max_workers=2
        )

        assert len(result_df) == 3
        assert set(result_df["security"]) == {"A JP Equity", "B JP Equity", "C JP Equity"}

    def test_execute_batches_parallel_partial_failure(self):
        """Test parallel execution with some batch failures."""
        engine = BatchingEngine(max_retries=1)

        mock_session = MagicMock()

        # First batch succeeds, second fails, third succeeds
        def mock_send_request(securities, fields, overrides=None):
            if securities[0] == "B JP Equity":
                raise Exception("Batch 2 error")
            return pd.DataFrame({
                "security": securities,
                fields[0]: [1.0] * len(securities),
            })

        mock_session.send_request.side_effect = mock_send_request

        batches = [
            RequestBatch(
                securities=["A JP Equity"],
                fields=["PX_TO_BOOK_RATIO"],
                override_type="END_DT_OVERRIDE",
                batch_id="batch_001",
            ),
            RequestBatch(
                securities=["B JP Equity"],
                fields=["PX_TO_BOOK_RATIO"],
                override_type="END_DT_OVERRIDE",
                batch_id="batch_002",
            ),
            RequestBatch(
                securities=["C JP Equity"],
                fields=["PX_TO_BOOK_RATIO"],
                override_type="END_DT_OVERRIDE",
                batch_id="batch_003",
            ),
        ]

        overrides = {"END_DT_OVERRIDE": "20210331"}

        result_df = engine.execute_batches_parallel(
            mock_session, batches, overrides, max_workers=2
        )

        # Should still succeed with 2 out of 3 batches
        assert len(result_df) == 2
        assert "B JP Equity" not in result_df["security"].values

    def test_execute_batches_parallel_all_fail(self):
        """Test parallel execution when all batches fail."""
        engine = BatchingEngine(max_retries=1)

        mock_session = MagicMock()
        mock_session.send_request.side_effect = Exception("All batches fail")

        batches = [
            RequestBatch(
                securities=["A JP Equity"],
                fields=["PX_TO_BOOK_RATIO"],
                override_type="END_DT_OVERRIDE",
                batch_id="batch_001",
            ),
        ]

        overrides = {"END_DT_OVERRIDE": "20210331"}

        with pytest.raises(ValueError, match="All .* batches failed"):
            engine.execute_batches_parallel(
                mock_session, batches, overrides, max_workers=2
            )

    def test_execute_batches_sequential_success(self):
        """Test successful sequential execution."""
        engine = BatchingEngine()

        mock_session = MagicMock()

        def mock_send_request(securities, fields, overrides=None):
            return pd.DataFrame({
                "security": securities,
                fields[0]: [1.0] * len(securities),
            })

        mock_session.send_request.side_effect = mock_send_request

        batches = [
            RequestBatch(
                securities=["A JP Equity"],
                fields=["PX_TO_BOOK_RATIO"],
                override_type="END_DT_OVERRIDE",
                batch_id="batch_001",
            ),
            RequestBatch(
                securities=["B JP Equity"],
                fields=["PX_TO_BOOK_RATIO"],
                override_type="END_DT_OVERRIDE",
                batch_id="batch_002",
            ),
        ]

        overrides = {"END_DT_OVERRIDE": "20210331"}

        result_df = engine.execute_batches_sequential(
            mock_session, batches, overrides
        )

        assert len(result_df) == 2
        assert mock_session.send_request.call_count == 2

    def test_execute_batches_empty_list(self):
        """Test execution with empty batch list."""
        engine = BatchingEngine()
        mock_session = MagicMock()

        result_df = engine.execute_batches_parallel(
            mock_session, [], {}, max_workers=2
        )

        assert len(result_df) == 0
        assert isinstance(result_df, pd.DataFrame)


class TestIntegration:
    """Integration tests with complete workflows."""

    def test_complete_workflow_single_field_group(self):
        """Test complete workflow: grouping -> batching -> execution."""
        engine = BatchingEngine(max_batch_size=5)

        # Mock session
        mock_session = MagicMock()
        mock_session.send_request.return_value = pd.DataFrame({
            "security": ["9107 JP Equity"],
            "PX_TO_BOOK_RATIO": [1.23],
            "PE_RATIO": [12.5],
        })

        # 12 securities
        securities = [f"TICKER{i:02d} JP Equity" for i in range(12)]
        fields = ["PX_TO_BOOK_RATIO", "PE_RATIO"]  # Both END_DT_OVERRIDE

        # Create batches
        batches = engine.create_batches(securities, fields)

        # Should create 3 batches (5 + 5 + 2 securities)
        assert len(batches) == 3

        # Execute sequentially
        result_df = engine.execute_batches_sequential(
            mock_session,
            batches,
            overrides={"END_DT_OVERRIDE": "20210331"},
        )

        # Verify execution
        assert mock_session.send_request.call_count == 3
        assert len(result_df) == 3  # Mock returns 1 row per call

    def test_complete_workflow_multiple_field_groups(self):
        """Test workflow with fields from different override groups."""
        engine = BatchingEngine()

        # Fields from different groups
        all_fields = [
            "PX_TO_BOOK_RATIO",  # END_DT_OVERRIDE
            "RETURN_COM_EQY",  # FUND_PER
            "FISCAL_YEAR_END_MONTH_DE",  # none
        ]

        # Group fields by override type
        grouped = engine.group_fields_by_override(all_fields)

        assert len(grouped) == 3
        assert "END_DT_OVERRIDE" in grouped
        assert "FUND_PER" in grouped
        assert "none" in grouped

        # Each group should be processed separately
        securities = ["9107 JP Equity", "7157 JP Equity"]

        for override_type, fields in grouped.items():
            batches = engine.create_batches(securities, fields)
            assert len(batches) == 1
            assert batches[0].override_type == override_type

    def test_statistics_tracking(self):
        """Test that statistics are correctly tracked across executions."""
        engine = BatchingEngine()

        mock_session = MagicMock()
        mock_session.send_request.return_value = pd.DataFrame({
            "security": ["9107 JP Equity"],
            "PX_TO_BOOK_RATIO": [1.23],
        })

        batches = [
            RequestBatch(
                securities=["9107 JP Equity"],
                fields=["PX_TO_BOOK_RATIO"],
                override_type="END_DT_OVERRIDE",
                batch_id="test_001",
            ),
        ]

        # Execute
        engine.execute_batches_sequential(mock_session, batches, {})

        # Check statistics
        stats = engine.get_statistics()
        assert stats["total_batches_executed"] == 1
        assert stats["total_retries"] == 0
        assert stats["total_failures"] == 0
        assert stats["success_rate"] == 1.0


class TestEffissimoIntegration:
    """Integration test with all 30 Effissimo companies."""

    EFFISSIMO_TICKERS = [
        "9107 JP Equity", "7157 JP Equity", "6707 JP Equity", "5741 JP Equity",
        "1813 JP Equity", "1786 JP Equity", "3104 JP Equity", "5449 JP Equity",
        "4047 JP Equity", "7740 JP Equity", "7222 JP Equity", "6246 JP Equity",
        "7752 JP Equity", "4551 JP Equity", "4980 JP Equity", "7122 JP Equity",
        "7250 JP Equity", "8750 JP Equity", "3401 JP Equity", "5541 JP Equity",
        "9742 JP Equity", "6676 JP Equity", "6502 JP Equity", "4902 JP Equity",
        "1737 JP Equity", "7545 JP Equity", "9640 JP Equity", "4464 JP Equity",
        "8013 JP Equity", "6676 JP Equity",  # 30th ticker (duplicate 6676 from CSV)
    ]

    def test_batch_all_effissimo_companies(self):
        """Test batching all 30 Effissimo companies."""
        engine = BatchingEngine(max_batch_size=10)

        fields = ["PX_TO_BOOK_RATIO", "PE_RATIO"]

        batches = engine.create_batches(self.EFFISSIMO_TICKERS, fields)

        # 30 companies, batch size 10 -> 3 batches
        assert len(batches) == 3
        assert len(batches[0].securities) == 10
        assert len(batches[1].securities) == 10
        assert len(batches[2].securities) == 10  # Last batch

        # Verify all companies included (preserves order, including duplicates)
        all_securities = []
        for batch in batches:
            all_securities.extend(batch.securities)

        assert all_securities == self.EFFISSIMO_TICKERS

    def test_execute_effissimo_mock(self):
        """Test mock execution with all Effissimo companies."""
        engine = BatchingEngine(max_batch_size=10)

        mock_session = MagicMock()

        # Mock response returns data for each security
        def mock_send_request(securities, fields, overrides=None):
            return pd.DataFrame({
                "security": securities,
                "PX_TO_BOOK_RATIO": [1.0 + i * 0.1 for i in range(len(securities))],
                "PE_RATIO": [10.0 + i for i in range(len(securities))],
            })

        mock_session.send_request.side_effect = mock_send_request

        fields = ["PX_TO_BOOK_RATIO", "PE_RATIO"]
        batches = engine.create_batches(self.EFFISSIMO_TICKERS, fields)

        result_df = engine.execute_batches_sequential(
            mock_session,
            batches,
            overrides={"END_DT_OVERRIDE": "20210331"},
        )

        # Should get 30 rows (one per company)
        assert len(result_df) == 30
        assert set(result_df["security"]) == set(self.EFFISSIMO_TICKERS)
        assert mock_session.send_request.call_count == 3  # 3 batches


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "--cov=batching_engine", "--cov-report=term-missing"])
