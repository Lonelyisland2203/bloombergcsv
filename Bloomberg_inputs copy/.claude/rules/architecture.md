# System Architecture

## Design Principles
1. Modular Extraction: Separate extractors for snapshot, ownership, events, prices, peer comps
2. Field-Group Awareness: Never mix Bloomberg override types in single request
3. Fiscal Period Correctness: Query FYE upfront, compute snapshot dates dynamically
4. Graceful Degradation: Missing fields log warnings, don't crash pipeline
5. Idempotency: Same input produces identical output across runs

## Data Flow
```
CSV Input → Ticker Conversion → Fiscal Alignment → Batching Engine
  ↓
Parallel Extraction Streams (Snapshot, Ownership, Events, Prices, Peer Comps)
  ↓
Data Validation → Excel Writer → 5-Sheet Workbook Output
```

## Output Structure (5-Sheet Excel)
- Sheet 1: Snapshot (Financial/Valuation/Governance) + Metadata header
- Sheet 2: Ownership (Top 20 Holders)
- Sheet 3: Corporate Actions (Dividends, Buybacks, M&A during campaign period)
- Sheet 4: Price History (Daily adjusted prices)
- Sheet 5: Peer Comps (GICS sector medians)

## Module Boundaries
- bloomberg_session.py: DAPI lifecycle, reconnection, error handling (NO business logic)
- ticker_converter.py: Format validation, conversion (NO Bloomberg calls)
- fiscal_period_aligner.py: FYE query, snapshot date computation (ONE Bloomberg call per run)
- batching_engine.py: Request grouping, rate limiting (NO data transformation)
- extract_*.py: Field-specific extraction logic (SINGLE responsibility per extractor)
- excel_writer.py: Formatting only (NO computation or validation)
- data_validator.py: Quality checks only (NO data modification)
- run_all.py: Orchestration only (NO extraction logic)

## Override Type Mapping
- FUND_PER: Profitability, Balance Sheet, Income Statement (fiscal period based)
- END_DT_OVERRIDE: Valuation, Market Data, Ownership % (market date sensitive)
- None: Governance, Static fields (current data only)
- Bulk: TOP_20_HOLDERS, DVD_HIST_ALL, SHARE_REPURCHASE_SUMMARY, etc.

## Error Handling Strategy
- Session timeout: Auto-reconnect (max 3 attempts, 5s backoff)
- Terminal offline: Fail immediately with actionable message
- Field unavailable: Log warning, set null, continue
- Security invalid: Log warning, skip security, continue
- Rate limit: Exponential backoff (2s, 4s, 8s), circuit breaker at 5 failures

## Checkpoint System
After each extraction stream completes, save intermediate results to data/checkpoints/.
On failure, resume from last successful checkpoint.
