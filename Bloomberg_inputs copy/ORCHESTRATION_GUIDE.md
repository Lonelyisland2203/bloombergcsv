# Orchestration Layer Guide - run_all.py

## Overview

`run_all.py` is the main CLI entry point for the Bloomberg Activist Data Pipeline. It orchestrates all 10 modules to produce a comprehensive Excel workbook with activist campaign data.

## Quick Start

### Basic Usage

```bash
python src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management"
```

This will:
1. Load all companies from the CSV
2. Query Bloomberg for fiscal year-end data
3. Extract snapshot, ownership, events, price history, and peer comp data
4. Validate data quality
5. Generate formatted Excel workbook in `output/`

### Common Options

```bash
# Custom output path
python src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --output custom_output.xlsx

# Debug logging
python src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --log-level DEBUG

# Dry run (validate inputs without querying Bloomberg)
python src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --dry-run

# Parallel execution (EXPERIMENTAL - use with caution)
python src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --parallel
```

## Pipeline Workflow

### Step 1: Load Input CSV

**What happens:**
- Reads input CSV file
- Validates required columns: `target_company`, `target_ticker`, `first_filing`, `last_filing`, `max_ownership_pct`, `total_filings`
- Converts TSE tickers (`.T` format) to Bloomberg format (`JP Equity`)
- Creates `CampaignTarget` objects for each company

**Required CSV columns:**
```
target_company          - Japanese company name
target_ticker           - TSE ticker (e.g., "9107.T")
total_filings           - Number of regulatory filings
first_filing            - Campaign start date (YYYY-MM-DD)
last_filing             - Campaign end date (YYYY-MM-DD)
max_ownership_pct       - Maximum ownership percentage (decimal, e.g., 0.3899)
min_ownership_pct       - Minimum ownership percentage (optional)
```

**Output:**
- List of `CampaignTarget` objects
- Ticker conversion log

### Step 2: Align Fiscal Periods

**What happens:**
- Queries `FISCAL_YEAR_END_MONTH_DE` from Bloomberg (single batch request)
- Computes `snapshot_date` for each company using fiscal alignment logic
- Constructs `FUND_PER` overrides for fundamental data extraction
- Saves fiscal alignment report to `logs/`

**Point-in-Time Safety:**
- Uses 60-day buffer before fiscal year-end
- Selects most recent COMPLETED fiscal year before campaign start
- Ensures no lookahead bias in fundamental data

**Output:**
- Updated `CampaignTarget` objects with `snapshot_date`, `fye_month`, `fund_per_override`
- Fiscal alignment report CSV in `logs/fiscal_alignment_report_YYYYMMDD_HHMMSS.csv`

### Step 3: Extract Data

**What happens:**
- Executes 5 extractors (sequential or parallel based on `--parallel` flag)
- Each extractor produces a DataFrame

**Extractors:**

1. **Snapshot Extractor**
   - Extracts 40+ financial, valuation, and governance fields
   - Uses `FUND_PER` override for point-in-time data
   - Computes derived fields (net cash, net cash/market cap)
   - Output: `snapshot_df` (1 row per company)

2. **Ownership Extractor**
   - Extracts Top 20 shareholders
   - Identifies cross-shareholding and foreign institutional holders
   - Computes aggregate ownership metrics
   - Output: `ownership_df` (up to 20 rows per company)

3. **Events Extractor**
   - Extracts corporate actions during campaign period ONLY
   - Dividends, buybacks, splits, M&A
   - Computes `months_after_activist_entry`
   - Output: `events_df` (variable rows per company)

4. **Price History Extractor**
   - Extracts daily adjusted prices from 6 months pre-entry to exit/present
   - Computes cumulative returns and `days_since_activist_entry`
   - Output: `price_df` (hundreds of rows per company)

5. **Peer Comps Extractor**
   - Identifies GICS sector peers
   - Computes sector median valuation metrics (PBR, ROE, EV/EBITDA)
   - Calculates discount/premium to sector
   - Output: `peer_comps_df` (1 row per company)

**Parallel Execution:**
- When `--parallel` is enabled, all 5 extractors run concurrently
- Uses `ThreadPoolExecutor` with max 5 workers
- CAUTION: Bloomberg API may have concurrency limits
- Use for faster execution on large datasets

### Step 4: Validate Data Quality

**What happens:**
- Runs `DataValidator` on snapshot data
- Checks field coverage, range violations, missing critical fields
- Flags securities requiring manual review (>30% missing data)
- Generates comprehensive quality report

**Quality Metrics:**
- Overall quality score (0-100%)
- Field coverage percentages
- Range violations (values outside acceptable bounds)
- Manual review flags

**Output:**
- `DataQualityReport` object
- Quality report JSON in `logs/data_quality_report_YYYYMMDD_HHMMSS.json`

### Step 5: Write Excel Output

**What happens:**
- Creates 5-sheet Excel workbook
- Applies professional formatting (freeze panes, column widths, number formats)
- Adds metadata header to Sheet 1
- Implements conditional formatting for data quality issues

**Excel Sheets:**
1. **Financial Snapshot** - Metadata header (rows 1-5) + snapshot data
2. **Ownership** - Top 20 shareholders
3. **Corporate Actions** - Events during campaign
4. **Price History** - Daily adjusted prices
5. **Peer Comparables** - Sector median metrics

**Filename Convention:**
```
{activist_name}_bloomberg_data_{YYYYMMDD}.xlsx
```

**Output:**
- Excel workbook in `output/` directory

### Step 6: Execution Summary

**What happens:**
- Prints summary statistics to console
- Shows data quality score
- Lists securities requiring manual review
- Reports execution time

**Summary Metrics:**
- Total companies processed
- Successful/failed extractions
- Overall data quality score
- Manual review flags
- Execution time (seconds)
- Output file path

## Output Files

### Excel Workbook
**Location:** `output/{activist_name}_bloomberg_data_{YYYYMMDD}.xlsx`

**Sheets:**
1. Financial Snapshot (with metadata header)
2. Ownership (Top 20 holders)
3. Corporate Actions (events)
4. Price History (daily prices)
5. Peer Comparables (sector medians)

### Log Files
**Location:** `logs/`

**Files:**
- `pipeline_execution_{YYYYMMDD_HHMMSS}.log` - Detailed execution log
- `fiscal_alignment_report_{YYYYMMDD_HHMMSS}.csv` - Fiscal period alignment
- `data_quality_report_{YYYYMMDD_HHMMSS}.json` - Data quality metrics

**Additional extractor logs:**
- `snapshot_gap_report_{YYYYMMDD_HHMMSS}.json` - Missing snapshot fields
- `ownership_gap_report_{YYYYMMDD_HHMMSS}.json` - Ownership data issues
- `events_gap_report_{YYYYMMDD_HHMMSS}.json` - Event extraction issues
- `price_gap_report_{YYYYMMDD_HHMMSS}.json` - Price data gaps

## Error Handling

### Bloomberg Session Failures
```
ERROR: Bloomberg Terminal not running
```
**Solution:** Start Bloomberg Terminal and wait for full initialization

### Missing Fiscal Year-End Data
```
WARNING: Missing FYE month for {ticker}, defaulting to March (3)
```
**Solution:** Manual review of company fiscal calendar

### Data Quality Issues
```
WARNING: Securities requiring manual review:
  - 9107 JP Equity
```
**Solution:** Review `data_quality_report.json` for specific issues

### Extractor Failures
```
ERROR: Snapshot extraction failed: {error_message}
```
**Solution:** Check `logs/pipeline_execution_*.log` for details

## Advanced Usage

### Override Snapshot Date (Testing)

```bash
python src/run_all.py \
    --input test_input.csv \
    --activist "Test Activist" \
    --snapshot-date 2021-03-31
```

Forces all companies to use the same snapshot date instead of computing from fiscal year-end.

### Dry Run Mode

```bash
python src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --dry-run
```

**What it does:**
- Loads and validates CSV
- Converts tickers
- Creates `CampaignTarget` objects
- STOPS before Bloomberg queries

**Use cases:**
- Validate CSV format
- Test ticker conversion
- Check for data issues without querying Bloomberg

### Parallel Execution (EXPERIMENTAL)

```bash
python src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --parallel
```

**CAUTION:**
- Bloomberg API may have rate limits
- Potential for session conflicts
- Use only after testing with small datasets
- Monitor Bloomberg connection status

**Benefits:**
- Faster execution for large datasets
- Reduces total runtime by ~40% (5 extractors → 1x runtime)

## Performance Benchmarks

**30 companies (Effissimo dataset):**
- Sequential execution: ~15-20 minutes
- Parallel execution: ~10-12 minutes
- Dry run: <5 seconds

**Bottlenecks:**
- Bloomberg API query time (dominant factor)
- Fiscal alignment query (batch request, minimal)
- Price history extraction (hundreds of daily prices per company)

**Optimization tips:**
- Use `--parallel` for datasets >10 companies
- Check Bloomberg connection before large runs
- Monitor logs for slow extractors

## Troubleshooting

### Issue: "Input CSV not found"
**Cause:** Invalid file path
**Solution:** Use absolute path or verify relative path from project root

### Issue: "Missing required columns"
**Cause:** CSV missing required fields
**Solution:** Ensure CSV has all required columns (see Step 1)

### Issue: Ticker conversion failed
**Cause:** Invalid ticker format
**Solution:** Verify TSE tickers match `.T` format (e.g., "9107.T", "7157.T")

### Issue: Low data quality score (<70%)
**Cause:** Missing Bloomberg fields or connectivity issues
**Solution:** Review `data_quality_report.json` for specific missing fields

### Issue: Pipeline timeout
**Cause:** Bloomberg Terminal disconnected or slow network
**Solution:** Check Bloomberg connection, restart if needed

## Integration with Existing Workflow

### Before Pipeline Execution
1. Ensure Bloomberg Terminal is running and logged in
2. Prepare input CSV with required columns
3. Verify disk space for logs and output (~100MB for 30 companies)

### After Pipeline Execution
1. Review execution summary for failures
2. Check `data_quality_report.json` for manual review flags
3. Open Excel workbook and verify data
4. Review logs for warnings or errors
5. Archive logs and output for audit trail

### Downstream Analysis
- Excel workbook ready for analyst consumption
- Price data suitable for performance attribution
- Events data for timeline analysis
- Ownership data for governance research

## API Reference

### ExecutionConfig

```python
@dataclass
class ExecutionConfig:
    input_csv: Path              # Path to input CSV
    activist_name: str           # Activist investor name
    output_path: Path            # Excel output path (optional)
    snapshot_date_override: date # Override snapshot date (optional)
    log_level: str              # DEBUG, INFO, WARNING, ERROR
    enable_parallel: bool        # Enable parallel execution
    dry_run: bool               # Validate without Bloomberg queries
```

### ExecutionSummary

```python
@dataclass
class ExecutionSummary:
    total_companies: int              # Total companies processed
    successful_extractions: int       # Successful extractions
    failed_extractions: int           # Failed extractions
    data_quality_score: float         # Overall quality (0-100)
    manual_review_flags: List[str]    # Tickers requiring review
    output_file: Path                 # Excel output path
    execution_time_seconds: float     # Total execution time
    log_file: Path                    # Execution log path
```

### PipelineOrchestrator

```python
class PipelineOrchestrator:
    def __init__(self, config: ExecutionConfig)
    def run(self) -> ExecutionSummary

    # Internal methods:
    def _load_input_csv(self) -> List[CampaignTarget]
    def _align_fiscal_periods(self, targets) -> List[CampaignTarget]
    def _extract_all_data(self, targets) -> Tuple[DataFrame, ...]
    def _validate_data_quality(self, snapshot_df) -> DataQualityReport
    def _write_excel_output(self, ...) -> Path
```

## Exit Codes

- `0` - Success (all extractions successful)
- `1` - Failure (one or more extractions failed OR exception occurred)

## Best Practices

1. **Always run dry-run first** on new CSV files
2. **Monitor logs** during execution for warnings
3. **Review data quality report** before using Excel output
4. **Archive logs** for audit trail and debugging
5. **Use parallel execution cautiously** - test with small datasets first
6. **Check Bloomberg connection** before large batch runs
7. **Validate CSV format** matches expected schema
8. **Set appropriate log level** (INFO for production, DEBUG for troubleshooting)

## Support

For issues or questions:
1. Check `logs/pipeline_execution_*.log` for detailed error messages
2. Review `data_quality_report.json` for data issues
3. Consult module-specific documentation in `src/` files
4. Contact Bloomberg Activist Pipeline team

---

**Version:** 1.0.0
**Last Updated:** 2026-04-01
**Author:** Bloomberg Activist Pipeline Team
