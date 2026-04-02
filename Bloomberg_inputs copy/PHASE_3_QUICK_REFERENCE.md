# Phase 3 Quick Reference: Batching Engine

## Overview
Intelligent request batching for Bloomberg data extraction with field-group-aware splitting, rate limiting, and parallel execution.

## Files
- **Implementation**: `src/batching_engine.py` (685 lines)
- **Tests**: `tests/test_batching_engine.py` (928 lines, 44 tests, 95% coverage)
- **Examples**: `examples/example_batching_engine.py` (6 usage examples)

## Quick Start

### Basic Usage
```python
from batching_engine import BatchingEngine
from bloomberg_session import BloombergSession

# Initialize engine
engine = BatchingEngine(
    max_batch_size=20,       # Securities per batch
    min_delay_seconds=2.0,   # Rate limit interval
    max_retries=3            # Retry attempts
)

# Create batches
securities = ["9107 JP Equity", "7157 JP Equity", "6707 JP Equity"]
fields = ["PX_TO_BOOK_RATIO", "PE_RATIO", "CUR_MKT_CAP"]

batches = engine.create_batches(securities, fields)

# Execute with Bloomberg session
with BloombergSession() as session:
    result_df = engine.execute_batches_sequential(
        session,
        batches,
        overrides={"END_DT_OVERRIDE": "20210331"}
    )
```

### Field Grouping (CRITICAL)
```python
# ALWAYS group fields by override type BEFORE batching
all_fields = [
    "PX_TO_BOOK_RATIO",      # END_DT_OVERRIDE
    "RETURN_COM_EQY",        # FUND_PER
    "FISCAL_YEAR_END_MONTH_DE"  # none
]

grouped = engine.group_fields_by_override(all_fields)
# Returns: {
#   "END_DT_OVERRIDE": ["PX_TO_BOOK_RATIO"],
#   "FUND_PER": ["RETURN_COM_EQY"],
#   "none": ["FISCAL_YEAR_END_MONTH_DE"]
# }

# Create separate batches for each group
for override_type, field_list in grouped.items():
    batches = engine.create_batches(securities, field_list)
    # Execute with appropriate override value
```

### Parallel Execution
```python
# Execute multiple field groups in parallel
with BloombergSession() as session:
    result_df = engine.execute_batches_parallel(
        session,
        all_batches,
        overrides={
            "END_DT_OVERRIDE": "20210331",
            "FUND_PER": "FY2021"
        },
        max_workers=3  # Concurrent threads
    )
```

## Key Classes

### BatchingEngine
**Constructor**:
```python
BatchingEngine(
    max_batch_size=20,        # Max securities per batch
    min_delay_seconds=2.0,    # Min time between requests
    max_retries=3,            # Max retry attempts
    config_path=None          # Path to bloomberg_fields.yaml (auto-detected)
)
```

**Methods**:
- `create_batches(securities, fields)` → List[RequestBatch]
- `group_fields_by_override(fields)` → Dict[str, List[str]]
- `execute_batch_with_backoff(session, batch, override_value)` → BatchExecutionResult
- `execute_batches_parallel(session, batches, overrides, max_workers)` → DataFrame
- `execute_batches_sequential(session, batches, overrides)` → DataFrame
- `track_rate_limits()` → Dict[str, Any]
- `get_statistics()` → Dict[str, Any]

### FieldGroupManager
**Methods**:
- `get_override_type(field)` → Optional[str]
- `get_fields_by_group(group_name)` → List[str]
- `validate_fields(fields)` → Tuple[List[str], List[str]]
- `group_fields_by_override(fields)` → Dict[str, List[str]]

### RequestBatch (Dataclass)
```python
@dataclass
class RequestBatch:
    securities: List[str]      # Bloomberg identifiers
    fields: List[str]          # Field names
    override_type: str         # "FUND_PER" | "END_DT_OVERRIDE" | "none" | "bulk"
    batch_id: str              # Unique identifier
```

## Override Types

| Type | Description | Example Fields | Override Value Format |
|------|-------------|----------------|----------------------|
| `END_DT_OVERRIDE` | Market-date snapshot | PX_TO_BOOK_RATIO, CUR_MKT_CAP | "20210331" (YYYYMMDD) |
| `FUND_PER` | Fiscal period data | RETURN_COM_EQY, BS_CASH_NEAR_CASH_ITEM | "FY2021" (FYYYY) |
| `none` | Current/static data | FISCAL_YEAR_END_MONTH_DE | (no override) |
| `bulk` | Table/multi-row data | TOP_20_HOLDERS_PUBLIC_FILINGS | (no override) |

## Rate Limiting

### Enforcement
- **Min Interval**: 2.0 seconds between requests (Bloomberg recommendation)
- **Tracking**: Last 100 request timestamps
- **Auto-Wait**: Engine automatically enforces delay before each request

### Exponential Backoff
- **Attempt 1**: Immediate execution
- **Attempt 2**: Wait 2s, retry
- **Attempt 3**: Wait 4s, retry
- **Attempt 4**: Wait 8s, retry (if max_retries=3)

### Circuit Breaker
- **Threshold**: 5 consecutive failures
- **Action**: Halt all further requests
- **Recovery**: Create new engine instance

## Statistics Tracking

```python
stats = engine.get_statistics()
# Returns:
# {
#     "total_batches_executed": 15,
#     "total_retries": 2,
#     "total_failures": 0,
#     "requests_last_minute": 8,
#     "min_interval_seconds": 2.0,
#     "max_batch_size": 20,
#     "success_rate": 1.0,      # 100%
#     "retry_rate": 0.133       # 2/15
# }
```

## Common Patterns

### Pattern 1: Single Field Group
```python
# All fields have same override type
fields = ["PX_TO_BOOK_RATIO", "PE_RATIO", "CUR_MKT_CAP"]
batches = engine.create_batches(securities, fields)

with BloombergSession() as session:
    df = engine.execute_batches_sequential(
        session, batches,
        overrides={"END_DT_OVERRIDE": snapshot_date.strftime("%Y%m%d")}
    )
```

### Pattern 2: Multiple Field Groups
```python
# Mix of override types
grouped = engine.group_fields_by_override(all_fields)

with BloombergSession() as session:
    results = []

    for override_type, field_list in grouped.items():
        batches = engine.create_batches(securities, field_list)
        override_value = get_override_value(override_type)  # Your logic

        df = engine.execute_batches_sequential(
            session, batches,
            overrides={override_type: override_value} if override_value else {}
        )
        results.append(df)

    # Merge by security
    final_df = merge_results(results)
```

### Pattern 3: Bulk Fields (Special)
```python
# Bulk fields require one field per request
bulk_field = "TOP_20_HOLDERS_PUBLIC_FILINGS"
batches = engine.create_batches(securities, [bulk_field])

with BloombergSession() as session:
    # Returns long-format DataFrame (multiple rows per security)
    df = engine.execute_batches_sequential(session, batches, {})
```

## Error Handling

### Partial Failures
```python
# Some batches may fail while others succeed
try:
    df = engine.execute_batches_sequential(session, batches, overrides)
except ValueError as e:
    # All batches failed
    print(f"Complete failure: {e}")
else:
    # At least some batches succeeded
    # Missing securities will have NaN values
    print(f"Retrieved {len(df)} records")
```

### Field Validation
```python
# Pre-validate fields before batching
valid, invalid = engine.field_manager.validate_fields(fields)

if invalid:
    print(f"Warning: Unknown fields will return null: {invalid}")

# Continue with valid fields only
batches = engine.create_batches(securities, valid)
```

## Testing

### Run Tests
```bash
# All batching engine tests
pytest tests/test_batching_engine.py -v

# With coverage
pytest tests/test_batching_engine.py --cov=batching_engine --cov-report=term

# Specific test class
pytest tests/test_batching_engine.py::TestFieldGroupManager -v
```

### Run Examples
```bash
python examples/example_batching_engine.py
```

## Performance Guidelines

### Batch Size Selection
- **Small (10-20)**: Conservative, faster failure recovery, more progress tracking
- **Medium (50)**: Balanced, good for most use cases
- **Large (100+)**: Fewer requests, but slower failure recovery, higher memory

**Recommendation**: Start with 20, tune based on Bloomberg Terminal performance.

### Execution Mode Selection
- **Sequential**: Safer, easier to debug, predictable timing
- **Parallel**: Faster (2-3x speedup), good for independent field groups

**Recommendation**: Use sequential for initial development, parallel for production.

### Time Estimates (30 securities, 58 fields)
- **Field groups**: 8 (FUND_PER, END_DT_OVERRIDE, none, etc.)
- **Batches** (batch_size=10): ~24 batches (3 per field group)
- **Sequential**: 24 × 2s = 48 seconds
- **Parallel** (3 workers): ~18 seconds (3x faster)

## Best Practices

### ✅ DO
- Always group fields by override type BEFORE batching
- Use field validation to catch typos early
- Monitor statistics to detect rate limit issues
- Start with conservative batch sizes (20)
- Log batch IDs for debugging

### ❌ DON'T
- Mix override types in single batch (will fail)
- Batch multiple bulk fields together (not supported)
- Ignore partial failures (check result DataFrame for completeness)
- Set min_delay_seconds < 2.0 (risk rate limits)
- Retry manually (engine handles retries)

## Integration with Other Modules

### From fiscal_period_aligner
```python
from fiscal_period_aligner import compute_campaign_fiscal_alignment

snapshot_date, fund_per, _ = compute_campaign_fiscal_alignment(
    campaign_start_date=date(2021, 6, 14),
    fye_month=3
)
# Use snapshot_date for END_DT_OVERRIDE: snapshot_date.strftime("%Y%m%d")
# Use fund_per for FUND_PER: fund_per (already "FYYYY" format)
```

### From bloomberg_session
```python
from bloomberg_session import BloombergSession

# Engine uses session methods:
# - session.send_request(securities, fields, overrides)
# - session.send_bulk_request(securities, field)
```

## Troubleshooting

### Issue: Circuit breaker opened
**Cause**: 5 consecutive batch failures
**Solution**: Check Bloomberg Terminal connection, check field names, verify overrides

### Issue: "Bulk batch must have exactly 1 field"
**Cause**: Tried to batch multiple bulk fields together
**Solution**: Create separate batch for each bulk field

### Issue: Mixed override types warning
**Cause**: Fields with different override types in same batch
**Solution**: Use `group_fields_by_override()` first, batch each group separately

### Issue: All batches failed
**Cause**: Invalid overrides, Terminal not running, network issue
**Solution**: Check logs for specific error, verify Terminal connectivity

## Advanced Usage

### Custom Retry Logic
```python
# Override default backoff schedule
# (Requires modifying backoff_schedule in execute_batch_with_backoff)
```

### Progress Tracking
```python
for i, batch in enumerate(batches, 1):
    result = engine.execute_batch_with_backoff(session, batch, override_value)
    print(f"Progress: {i}/{len(batches)} batches, "
          f"Success: {result.success}, "
          f"Time: {result.execution_time:.1f}s")
```

### Merging Results from Multiple Field Groups
```python
import pandas as pd

def merge_field_group_results(results: Dict[str, pd.DataFrame]) -> pd.DataFrame:
    """Merge results from different field groups by security."""
    base_df = results[list(results.keys())[0]]

    for key, df in list(results.items())[1:]:
        base_df = base_df.merge(df, on="security", how="outer")

    return base_df
```

## References

- **Config**: `config/bloomberg_fields.yaml` (field definitions)
- **Tests**: `tests/test_batching_engine.py` (usage examples)
- **Examples**: `examples/example_batching_engine.py` (6 patterns)
- **Completion Report**: `PHASE3_COMPLETE.md` (full design rationale)

---

**Status**: ✅ Production Ready
**Coverage**: 95% (243 statements, 12 missed)
**Tests**: 44/44 passing
**Date**: April 1, 2026
