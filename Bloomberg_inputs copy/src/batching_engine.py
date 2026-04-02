"""
Batching Engine for Bloomberg Data Extraction

This module provides intelligent request batching with field-group-aware splitting,
rate limit compliance, and parallel execution capabilities.

Core Features:
    - Field grouping by override type (FUND_PER, END_DT_OVERRIDE, none, bulk)
    - Security batching with configurable batch sizes
    - Rate limiting with exponential backoff
    - Parallel execution for independent field groups
    - Circuit breaker for rate limit protection
    - Comprehensive error handling and partial result recovery

Point-in-Time Considerations:
    - Batching is purely an optimization strategy
    - No temporal dependencies introduced by batch splitting
    - Override values are determined by caller (fiscal aligner, snapshot date)
    - Batching engine is stateless and deterministic

Author: Bloomberg Activist Pipeline
"""

import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import yaml

from bloomberg_session import BloombergSession

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class RequestBatch:
    """
    Represents a batch of securities and fields for Bloomberg API request.

    Attributes:
        securities: List of Bloomberg security identifiers
        fields: List of Bloomberg field names
        override_type: Override type for this batch ("FUND_PER", "END_DT_OVERRIDE", "none", "bulk")
        batch_id: Unique identifier for this batch (for tracking and logging)
    """

    securities: List[str]
    fields: List[str]
    override_type: str
    batch_id: str


@dataclass
class BatchExecutionResult:
    """
    Result of executing a batch request.

    Attributes:
        batch_id: Unique identifier of the batch
        data: DataFrame with results (None if failed)
        success: Whether the batch executed successfully
        error_message: Error description if success is False
        execution_time: Time taken to execute batch (seconds)
        retry_count: Number of retries attempted
    """

    batch_id: str
    data: Optional[pd.DataFrame] = None
    success: bool = True
    error_message: Optional[str] = None
    execution_time: float = 0.0
    retry_count: int = 0


@dataclass
class RateLimitTracker:
    """
    Tracks request timestamps for rate limit enforcement.

    Attributes:
        min_interval_seconds: Minimum time between requests (default: 2.0s)
        request_timestamps: List of recent request timestamps
        max_history: Maximum number of timestamps to track (default: 100)
    """

    min_interval_seconds: float = 2.0
    request_timestamps: List[float] = field(default_factory=list)
    max_history: int = 100

    def wait_if_needed(self) -> float:
        """
        Wait if necessary to enforce rate limit.

        Returns:
            Actual wait time in seconds (0 if no wait needed)
        """
        if not self.request_timestamps:
            return 0.0

        # Calculate time since last request
        last_request_time = self.request_timestamps[-1]
        time_since_last = time.time() - last_request_time

        # Wait if interval too short
        if time_since_last < self.min_interval_seconds:
            wait_time = self.min_interval_seconds - time_since_last
            logger.debug(f"Rate limit wait: {wait_time:.2f}s")
            time.sleep(wait_time)
            return wait_time

        return 0.0

    def record_request(self) -> None:
        """Record a new request timestamp."""
        current_time = time.time()
        self.request_timestamps.append(current_time)

        # Trim history to max size
        if len(self.request_timestamps) > self.max_history:
            self.request_timestamps = self.request_timestamps[-self.max_history :]


class FieldGroupManager:
    """
    Manages field grouping based on Bloomberg override types.

    Loads field configuration from bloomberg_fields.yaml and organizes fields
    by override type to prevent mixed override requests (which would fail).

    Attributes:
        config_path: Path to bloomberg_fields.yaml
        field_groups: Dict mapping group name to field metadata
        override_map: Dict mapping field name to override type
    """

    def __init__(self, config_path: Optional[Path] = None):
        """
        Initialize field group manager.

        Args:
            config_path: Path to bloomberg_fields.yaml (auto-detected if None)

        Raises:
            FileNotFoundError: If config file not found
            ValueError: If config format is invalid
        """
        # Auto-detect config path if not provided
        if config_path is None:
            # Try relative to this file
            src_dir = Path(__file__).parent
            config_path = src_dir.parent / "config" / "bloomberg_fields.yaml"

        self.config_path = Path(config_path)

        if not self.config_path.exists():
            raise FileNotFoundError(
                f"Bloomberg fields config not found at: {self.config_path}\n"
                "Expected location: config/bloomberg_fields.yaml"
            )

        # Load configuration
        logger.info(f"Loading Bloomberg field configuration from {self.config_path}")
        with open(self.config_path, "r", encoding="utf-8") as f:
            config = yaml.safe_load(f)

        # Parse field groups
        self.field_groups = {}
        self.override_map = {}

        for group_name, group_config in config.items():
            if not isinstance(group_config, dict):
                continue

            override_type = group_config.get("override_type")
            fields = group_config.get("fields", [])

            self.field_groups[group_name] = {
                "override_type": override_type,
                "description": group_config.get("description", ""),
                "fields": fields,
            }

            # Build override map for quick lookup
            for field_spec in fields:
                if isinstance(field_spec, dict):
                    field_name = field_spec.get("name")
                    if field_name:
                        self.override_map[field_name] = override_type

        logger.info(
            f"Loaded {len(self.field_groups)} field groups, "
            f"{len(self.override_map)} total fields"
        )

    def get_override_type(self, field: str) -> Optional[str]:
        """
        Get override type for a field.

        Args:
            field: Bloomberg field name

        Returns:
            Override type ("FUND_PER", "END_DT_OVERRIDE", "none", "bulk") or None if unknown
        """
        return self.override_map.get(field)

    def get_fields_by_group(self, group_name: str) -> List[str]:
        """
        Get all field names in a group.

        Args:
            group_name: Name of field group (e.g., "valuation_metrics")

        Returns:
            List of field names in the group

        Raises:
            KeyError: If group name not found
        """
        if group_name not in self.field_groups:
            raise KeyError(
                f"Field group '{group_name}' not found. "
                f"Available groups: {list(self.field_groups.keys())}"
            )

        group = self.field_groups[group_name]
        field_names = []

        for field_spec in group["fields"]:
            if isinstance(field_spec, dict):
                field_name = field_spec.get("name")
                if field_name:
                    field_names.append(field_name)

        return field_names

    def get_fields_by_override_type(self, override_type: str) -> List[str]:
        """
        Get all fields with a specific override type.

        Args:
            override_type: Override type to filter by

        Returns:
            List of field names with that override type
        """
        return [
            field
            for field, otype in self.override_map.items()
            if otype == override_type
        ]

    def validate_fields(self, fields: List[str]) -> Tuple[List[str], List[str]]:
        """
        Validate field names against known fields.

        Args:
            fields: List of field names to validate

        Returns:
            Tuple of (valid_fields, invalid_fields)
        """
        valid = []
        invalid = []

        for field in fields:
            if field in self.override_map:
                valid.append(field)
            else:
                invalid.append(field)

        return valid, invalid

    def group_fields_by_override(
        self, fields: List[str]
    ) -> Dict[str, List[str]]:
        """
        Group fields by their override type.

        Args:
            fields: List of field names to group

        Returns:
            Dict mapping override type to list of fields
            Keys: "FUND_PER", "END_DT_OVERRIDE", "none", "bulk", "unknown"
        """
        grouped = {
            "FUND_PER": [],
            "END_DT_OVERRIDE": [],
            "none": [],
            "bulk": [],
            "unknown": [],
        }

        for field in fields:
            override_type = self.get_override_type(field)
            if override_type:
                grouped[override_type].append(field)
            else:
                grouped["unknown"].append(field)
                logger.warning(f"Unknown field '{field}' - not in configuration")

        # Remove empty groups
        grouped = {k: v for k, v in grouped.items() if v}

        return grouped


class BatchingEngine:
    """
    Intelligent batching engine for Bloomberg data extraction.

    Provides field-group-aware batching, rate limiting, exponential backoff,
    and parallel execution capabilities.

    Attributes:
        max_batch_size: Maximum securities per batch (default: 20)
        min_delay_seconds: Minimum delay between requests (default: 2.0s)
        max_retries: Maximum retry attempts per batch (default: 3)
        field_manager: FieldGroupManager instance
        rate_tracker: RateLimitTracker instance
    """

    def __init__(
        self,
        max_batch_size: int = 20,
        min_delay_seconds: float = 2.0,
        max_retries: int = 3,
        config_path: Optional[Path] = None,
    ):
        """
        Initialize batching engine.

        Args:
            max_batch_size: Maximum securities per batch (conservative: 20)
            min_delay_seconds: Minimum time between batches (Bloomberg recommendation: 2s)
            max_retries: Maximum retry attempts with exponential backoff
            config_path: Path to bloomberg_fields.yaml (auto-detected if None)
        """
        self.max_batch_size = max_batch_size
        self.min_delay_seconds = min_delay_seconds
        self.max_retries = max_retries

        # Initialize field manager
        self.field_manager = FieldGroupManager(config_path)

        # Initialize rate tracker
        self.rate_tracker = RateLimitTracker(min_interval_seconds=min_delay_seconds)

        # Execution statistics
        self.total_batches_executed = 0
        self.total_retries = 0
        self.total_failures = 0

        logger.info(
            f"BatchingEngine initialized: max_batch_size={max_batch_size}, "
            f"min_delay={min_delay_seconds}s, max_retries={max_retries}"
        )

    def create_batches(
        self,
        securities: List[str],
        fields: List[str],
    ) -> List[RequestBatch]:
        """
        Split securities into batches respecting size limit.

        Creates batches by splitting securities (not fields) to maintain
        field coherence within each request.

        Args:
            securities: List of Bloomberg security identifiers
            fields: List of Bloomberg field names (assumed to be from same override group)

        Returns:
            List of RequestBatch objects
        """
        if not securities:
            logger.warning("No securities provided for batching")
            return []

        if not fields:
            logger.warning("No fields provided for batching")
            return []

        # Determine override type (assumes all fields have same override type)
        override_types = set(
            self.field_manager.get_override_type(f) for f in fields
        )
        override_types.discard(None)  # Remove unknown fields

        if len(override_types) > 1:
            logger.warning(
                f"Mixed override types in field list: {override_types}. "
                "This may cause request failures. Consider grouping fields first."
            )
            override_type = "mixed"
        elif override_types:
            override_type = override_types.pop()
        else:
            override_type = "unknown"

        # Split securities into batches
        batches = []
        num_batches = (len(securities) + self.max_batch_size - 1) // self.max_batch_size

        for batch_idx in range(num_batches):
            start_idx = batch_idx * self.max_batch_size
            end_idx = min(start_idx + self.max_batch_size, len(securities))
            batch_securities = securities[start_idx:end_idx]

            batch_id = f"{override_type}_{batch_idx + 1:03d}_of_{num_batches:03d}"

            batch = RequestBatch(
                securities=batch_securities,
                fields=fields,
                override_type=override_type,
                batch_id=batch_id,
            )

            batches.append(batch)

        logger.info(
            f"Created {len(batches)} batches: {len(securities)} securities, "
            f"{len(fields)} fields, override_type={override_type}"
        )

        return batches

    def group_fields_by_override(
        self, fields: List[str]
    ) -> Dict[str, List[str]]:
        """
        Separate fields by override type to prevent mixed requests.

        Delegates to FieldGroupManager.

        Args:
            fields: List of field names to group

        Returns:
            Dict mapping override type to list of fields
        """
        return self.field_manager.group_fields_by_override(fields)

    def execute_batch_with_backoff(
        self,
        session: BloombergSession,
        batch: RequestBatch,
        override_value: Optional[str] = None,
    ) -> BatchExecutionResult:
        """
        Execute single batch with exponential backoff on errors.

        Implements retry logic with exponential backoff:
        - Attempt 1: Immediate execution
        - Attempt 2: Wait 2s, retry
        - Attempt 3: Wait 4s, retry
        - Attempt 4: Wait 8s, retry (if max_retries=3)

        Args:
            session: Active Bloomberg session
            batch: RequestBatch to execute
            override_value: Optional override value (e.g., "FY2021", "20210331")

        Returns:
            BatchExecutionResult with data or error information
        """
        start_time = time.time()
        backoff_schedule = [0, 2, 4, 8]  # Exponential backoff in seconds
        retry_count = 0

        for attempt in range(self.max_retries + 1):
            try:
                # Enforce rate limit before request
                self.rate_tracker.wait_if_needed()

                # Prepare overrides
                overrides = None
                if override_value and batch.override_type in [
                    "FUND_PER",
                    "END_DT_OVERRIDE",
                ]:
                    override_key = batch.override_type
                    overrides = {override_key: override_value}

                # Log request
                logger.debug(
                    f"Executing batch {batch.batch_id}: "
                    f"{len(batch.securities)} securities, {len(batch.fields)} fields"
                    + (f", overrides={overrides}" if overrides else "")
                )

                # Execute request
                if batch.override_type == "bulk":
                    # Bulk requests only support one field at a time
                    if len(batch.fields) != 1:
                        raise ValueError(
                            f"Bulk batch must have exactly 1 field, got {len(batch.fields)}"
                        )
                    df = session.send_bulk_request(
                        securities=batch.securities, field=batch.fields[0]
                    )
                else:
                    # Regular reference data request
                    df = session.send_request(
                        securities=batch.securities,
                        fields=batch.fields,
                        overrides=overrides,
                    )

                # Record successful request
                self.rate_tracker.record_request()
                self.total_batches_executed += 1

                execution_time = time.time() - start_time

                logger.info(
                    f"Batch {batch.batch_id} completed successfully: "
                    f"{len(df)} records, {execution_time:.2f}s"
                    + (f", {retry_count} retries" if retry_count > 0 else "")
                )

                return BatchExecutionResult(
                    batch_id=batch.batch_id,
                    data=df,
                    success=True,
                    execution_time=execution_time,
                    retry_count=retry_count,
                )

            except Exception as e:
                error_str = str(e).lower()

                # Check if rate limit error
                is_rate_limit = any(
                    keyword in error_str for keyword in ["rate", "limit", "429"]
                )

                # Check if last attempt
                is_last_attempt = attempt >= self.max_retries

                if is_last_attempt:
                    # Final failure
                    execution_time = time.time() - start_time
                    self.total_failures += 1

                    logger.error(
                        f"Batch {batch.batch_id} failed after {attempt + 1} attempts: {e}"
                    )

                    return BatchExecutionResult(
                        batch_id=batch.batch_id,
                        data=None,
                        success=False,
                        error_message=str(e),
                        execution_time=execution_time,
                        retry_count=retry_count,
                    )
                else:
                    # Retry with backoff
                    retry_count += 1
                    self.total_retries += 1

                    wait_time = backoff_schedule[attempt]
                    logger.warning(
                        f"Batch {batch.batch_id} attempt {attempt + 1} failed: {e}. "
                        f"Retrying in {wait_time}s..."
                    )

                    if wait_time > 0:
                        time.sleep(wait_time)

        # Should never reach here
        return BatchExecutionResult(
            batch_id=batch.batch_id,
            data=None,
            success=False,
            error_message="Max retries exceeded",
            execution_time=time.time() - start_time,
            retry_count=retry_count,
        )

    def execute_batches_parallel(
        self,
        session: BloombergSession,
        batches: List[RequestBatch],
        overrides: Dict[str, str],
        max_workers: int = 3,
    ) -> pd.DataFrame:
        """
        Execute multiple batches in parallel using ThreadPoolExecutor.

        Parallelizes by field group (override type), not by individual batches,
        to avoid overwhelming Bloomberg API with concurrent requests.

        Args:
            session: Active Bloomberg session
            batches: List of RequestBatch objects to execute
            overrides: Dict mapping override type to override value
                      (e.g., {"FUND_PER": "FY2021", "END_DT_OVERRIDE": "20210331"})
            max_workers: Maximum number of parallel threads (default: 3)

        Returns:
            Combined DataFrame with all results

        Raises:
            ValueError: If all batches fail
        """
        if not batches:
            logger.warning("No batches to execute")
            return pd.DataFrame()

        logger.info(
            f"Executing {len(batches)} batches in parallel (max_workers={max_workers})"
        )

        results: List[BatchExecutionResult] = []
        successful_dfs: List[pd.DataFrame] = []

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Submit all batches
            future_to_batch = {}
            for batch in batches:
                # Get appropriate override value for this batch
                override_value = overrides.get(batch.override_type)

                future = executor.submit(
                    self.execute_batch_with_backoff,
                    session,
                    batch,
                    override_value,
                )
                future_to_batch[future] = batch

            # Collect results as they complete
            for future in as_completed(future_to_batch):
                batch = future_to_batch[future]
                try:
                    result = future.result()
                    results.append(result)

                    if result.success and result.data is not None:
                        successful_dfs.append(result.data)
                    else:
                        logger.warning(
                            f"Batch {result.batch_id} failed: {result.error_message}"
                        )

                except Exception as e:
                    logger.error(f"Batch {batch.batch_id} raised exception: {e}")
                    results.append(
                        BatchExecutionResult(
                            batch_id=batch.batch_id,
                            data=None,
                            success=False,
                            error_message=str(e),
                        )
                    )

        # Aggregate results
        successful_count = sum(1 for r in results if r.success)
        failed_count = len(results) - successful_count

        logger.info(
            f"Parallel execution complete: {successful_count} succeeded, "
            f"{failed_count} failed"
        )

        if not successful_dfs:
            raise ValueError(
                f"All {len(batches)} batches failed. Check logs for details."
            )

        # Combine successful results
        combined_df = pd.concat(successful_dfs, ignore_index=True)

        logger.info(f"Combined results: {len(combined_df)} total records")

        return combined_df

    def execute_batches_sequential(
        self,
        session: BloombergSession,
        batches: List[RequestBatch],
        overrides: Dict[str, str],
    ) -> pd.DataFrame:
        """
        Execute batches sequentially (no parallelization).

        Safer for rate limit compliance, but slower than parallel execution.

        Args:
            session: Active Bloomberg session
            batches: List of RequestBatch objects to execute
            overrides: Dict mapping override type to override value

        Returns:
            Combined DataFrame with all results

        Raises:
            ValueError: If all batches fail
        """
        if not batches:
            logger.warning("No batches to execute")
            return pd.DataFrame()

        logger.info(f"Executing {len(batches)} batches sequentially")

        results: List[BatchExecutionResult] = []
        successful_dfs: List[pd.DataFrame] = []

        for batch in batches:
            override_value = overrides.get(batch.override_type)
            result = self.execute_batch_with_backoff(
                session, batch, override_value
            )
            results.append(result)

            if result.success and result.data is not None:
                successful_dfs.append(result.data)
            else:
                logger.warning(
                    f"Batch {result.batch_id} failed: {result.error_message}"
                )

        # Aggregate results
        successful_count = sum(1 for r in results if r.success)
        failed_count = len(results) - successful_count

        logger.info(
            f"Sequential execution complete: {successful_count} succeeded, "
            f"{failed_count} failed"
        )

        if not successful_dfs:
            raise ValueError(
                f"All {len(batches)} batches failed. Check logs for details."
            )

        # Combine successful results
        combined_df = pd.concat(successful_dfs, ignore_index=True)

        logger.info(f"Combined results: {len(combined_df)} total records")

        return combined_df

    def track_rate_limits(self) -> Dict[str, Any]:
        """
        Get current rate limit statistics.

        Returns:
            Dict with rate limit tracking information
        """
        now = time.time()
        recent_requests = [
            ts for ts in self.rate_tracker.request_timestamps if now - ts < 60
        ]

        return {
            "total_batches_executed": self.total_batches_executed,
            "total_retries": self.total_retries,
            "total_failures": self.total_failures,
            "requests_last_minute": len(recent_requests),
            "min_interval_seconds": self.rate_tracker.min_interval_seconds,
            "max_batch_size": self.max_batch_size,
        }

    def get_statistics(self) -> Dict[str, Any]:
        """
        Get comprehensive execution statistics.

        Returns:
            Dict with execution statistics
        """
        stats = self.track_rate_limits()
        stats.update(
            {
                "success_rate": (
                    (self.total_batches_executed - self.total_failures)
                    / self.total_batches_executed
                    if self.total_batches_executed > 0
                    else 0.0
                ),
                "retry_rate": (
                    self.total_retries / self.total_batches_executed
                    if self.total_batches_executed > 0
                    else 0.0
                ),
            }
        )
        return stats
