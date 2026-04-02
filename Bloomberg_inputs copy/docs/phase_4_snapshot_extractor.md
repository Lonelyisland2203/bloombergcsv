# Phase 4: Snapshot Extractor

## Overview

The **Snapshot Extractor** is the most critical module in the Bloomberg Activist Data Pipeline. It orchestrates the extraction of comprehensive point-in-time financial snapshots for activist campaign targets, ensuring zero lookahead bias and high data quality.

## Architecture

### Core Components

```
SnapshotExtractor
├── CampaignTarget         # Dataclass representing campaign metadata
├── FieldGapEntry          # Dataclass for missing data tracking
├── _enrich_fiscal_metadata()     # Compute snapshot dates and FUND_PER overrides
├── _extract_fundamental_fields() # Extract FUND_PER fields (balance sheet, income statement)
├── _extract_market_fields()      # Extract END_DT_OVERRIDE fields (valuation, market data)
├── _extract_static_fields()      # Extract static fields (governance)
├── compute_derived_fields()      # Calculate net cash, ratios
├── log_field_gaps()              # Generate gap report
└── validate_point_in_time_safety() # Ensure no temporal violations
```

### Data Flow

```
Input: List[CampaignTarget]
   │
   ├─> Step 1: Fetch fiscal year-end months from Bloomberg
   │           (FISCAL_YEAR_END_MONTH_DE for all securities)
   │
   ├─> Step 2: Compute snapshot dates and FUND_PER overrides
   │           (using fiscal_period_aligner)
   │
   ├─> Step 3: Extract field groups in parallel
   │    ├─> FUND_PER fields (profitability, balance sheet, income statement)
   │    ├─> END_DT_OVERRIDE fields (valuation, market data, ownership)
   │    └─> Static fields (governance, company info)
   │
   ├─> Step 4: Merge all field groups into unified DataFrame
   │
   ├─> Step 5: Add campaign metadata columns
   │
   ├─> Step 6: Compute derived fields
   │           (net_cash, net_cash_to_market_cap)
   │
   ├─> Step 7: Compute data quality scores
   │           (% critical fields populated, manual review flags)
   │
   └─> Step 8: Generate and save field gap report
               (logs/snapshot_gaps_YYYYMMDD_HHMMSS.json)

Output: pd.DataFrame (N securities × ~50 fields)
```

## Point-in-Time Safety

### Critical Constraints

The Snapshot Extractor enforces **ZERO lookahead bias** through multiple validation layers:

1. **Snapshot Date Validation (Dataclass Level)**:
   ```python
   if snapshot_date >= campaign_start:
       raise ValueError("Point-in-time violation")
   ```

2. **Fiscal Alignment Validation**:
   - Snapshot date must be BEFORE campaign start
   - 60-day buffer ensures financial statements were filed
   - FUND_PER override corresponds to correct fiscal year

3. **Override Validation**:
   - FUND_PER: Uses fiscal year BEFORE snapshot date
   - END_DT_OVERRIDE: Uses snapshot date, not today's date
   - No forward-looking data without explicit validation

### Validation Function

```python
validate_point_in_time_safety(campaigns: List[CampaignTarget]) -> bool
```

Raises `ValueError` if ANY campaign violates temporal constraints.

## Field Groups

### 1. FUND_PER Fields (Fundamental Data)

**Override**: `FUND_PER = "FY2021"` (fiscal year ending in 2021)

**Fields**:
- Profitability: `RETURN_COM_EQY`, `RETURN_ON_ASSET`, `RETURN_ON_INV_CAPITAL`
- Margins: `OPER_MARGIN`, `PROF_MARGIN`
- Balance Sheet: `BS_CASH_NEAR_CASH_ITEM`, `SHORT_AND_LONG_TERM_DEBT`, `NET_DEBT`
- Income Statement: `TRAIL_12M_SALES`, `TRAIL_12M_NET_INC`, `TRAIL_12M_EPS`

**Extraction Strategy**:
- Group campaigns by FUND_PER override value
- Extract in parallel for each FUND_PER group
- Typical groups: FY2020, FY2021, FY2022 (depends on campaign dates)

### 2. END_DT_OVERRIDE Fields (Market Data)

**Override**: `END_DT_OVERRIDE = "20210331"` (snapshot as of March 31, 2021)

**Fields**:
- Valuation: `PX_TO_BOOK_RATIO`, `PE_RATIO`, `BEST_CUR_EV_TO_EBITDA`
- Market Data: `CUR_MKT_CAP`, `EQY_SH_OUT`, `EQY_FREE_FLOAT_PCT`
- Ownership: `EQY_INST_PCT_SH_OUT`, `EQY_FOREIGN_OWNERSHIP_PCT`

**Extraction Strategy**:
- Group campaigns by snapshot date (YYYYMMDD format)
- Extract in parallel for each date group
- Typical groups: 20210331, 20201231 (varies by FYE)

### 3. Static Fields (No Override)

**Override**: None (current/most recent data)

**Fields**:
- Governance: `BOARD_SIZE`, `PCT_INDEPENDENT_DIRECTORS`
- Company Info: `FISCAL_YEAR_END_MONTH_DE`

**Extraction Strategy**:
- Single batch for all securities
- No override needed

## Derived Fields

### Net Cash

```python
net_cash = BS_CASH_NEAR_CASH_ITEM + BS_MKT_SEC_OTHER_ST_INVEST - SHORT_AND_LONG_TERM_DEBT
```

**Interpretation**:
- Positive: Company has net cash position (excess liquidity)
- Negative: Company has net debt position (leveraged)

**Activist Relevance**: Companies with high net cash often targeted for capital return (dividends, buybacks).

### Net Cash to Market Cap Ratio

```python
net_cash_to_market_cap = net_cash / CUR_MKT_CAP
```

**Interpretation**:
- >50%: Exceptional cash position (strong activist target)
- 20-50%: Significant cash position
- <0%: Net debt position

**Edge Cases**:
- Division by zero: Returns `NaN` if market cap = 0
- Extreme ratios (>100%): Logged as warning for manual review

## Data Quality Management

### Quality Scoring

Each security receives a **data quality score** based on critical field coverage:

```python
data_quality_score = (populated_critical_fields / total_critical_fields) × 100
```

**Critical Fields**:
1. `PX_TO_BOOK_RATIO` (valuation)
2. `RETURN_COM_EQY` (profitability)
3. `CUR_MKT_CAP` (market data)
4. `NET_DEBT` (balance sheet)
5. `TRAIL_12M_SALES` (income statement)

### Manual Review Flagging

Securities with `data_quality_score < 70%` are flagged:

```python
manual_review_flag = True if data_quality_score < 70.0 else False
```

**Action**: Review flagged securities manually to determine if data gaps are:
- Unavailable from Bloomberg (acceptable)
- Data entry errors (fix at source)
- Bloomberg API errors (retry extraction)

### Gap Reporting

Field gaps are logged to JSON:

```json
{
  "timestamp": "2024-01-15T10:30:00",
  "total_securities": 30,
  "total_fields": 46,
  "field_coverage": {
    "PX_TO_BOOK_RATIO": {"count": 29, "pct": 96.7},
    "BEST_PE_RATIO": {"count": 15, "pct": 50.0}
  },
  "security_coverage": {
    "8136 JP Equity": {"count": 44, "pct": 95.7}
  },
  "missing_data": [
    {
      "security": "8136 JP Equity",
      "field": "BEST_PE_RATIO",
      "reason": "N/A"
    }
  ]
}
```

## Usage

### Basic Usage

```python
from bloomberg_session import BloombergSession
from batching_engine import BatchingEngine
from extract_snapshot import CampaignTarget, SnapshotExtractor

# Define campaigns
campaigns = [
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
    )
]

# Initialize components
with BloombergSession() as session:
    batching_engine = BatchingEngine()
    extractor = SnapshotExtractor(session, batching_engine)

    # Extract snapshot
    snapshot_df = extractor.extract_snapshot(campaigns)

    # Save results
    snapshot_df.to_csv("effissimo_snapshot.csv", index=False)
```

### Output DataFrame Schema

| Column | Type | Description |
|--------|------|-------------|
| `security` | str | Bloomberg ticker (e.g., "8136 JP Equity") |
| `company_name_japanese` | str | Japanese company name |
| `company_name_english` | str | English company name |
| `tse_ticker` | str | Original TSE ticker (e.g., "8136.T") |
| `campaign_start` | date | Campaign start date |
| `snapshot_date` | date | Fiscal year-end date used for extraction |
| `fund_per_override` | str | Bloomberg FUND_PER override (e.g., "FY2021") |
| `fye_month` | int | Fiscal year-end month (1-12) |
| `PX_TO_BOOK_RATIO` | float | Price-to-Book ratio |
| `RETURN_COM_EQY` | float | Return on Equity (%) |
| `CUR_MKT_CAP` | float | Market capitalization (JPY) |
| `net_cash` | float | Net cash position (JPY) |
| `net_cash_to_market_cap` | float | Net cash / Market cap ratio |
| `data_quality_score` | float | % of critical fields populated (0-100) |
| `manual_review_flag` | bool | True if >30% critical fields missing |
| ... | ... | (40+ additional Bloomberg fields) |

## Error Handling

### Missing Fiscal Year-End

```python
# Default to March (most common in Japan)
if pd.isna(fye_month):
    logger.warning(f"FYE not available for {ticker}, defaulting to March (3)")
    fye_month = 3
```

### Bloomberg API Errors

- Field errors: Log warning, return null, continue extraction
- Security errors: Log warning, skip security, continue
- Rate limit errors: Exponential backoff via `BatchingEngine`

### Data Validation Errors

- Division by zero: Return `NaN` (handled gracefully)
- Extreme values: Log warning, include in output (manual review)
- Missing data: Track in gap report, flag if >30% critical fields missing

## Testing

### Unit Tests

```bash
python -m pytest tests/test_extract_snapshot.py -v
```

**Coverage**: 85%+

**Test Cases**:
- CampaignTarget validation
- Fiscal metadata enrichment
- Derived field calculations
- Data quality scoring
- Point-in-time safety validation
- Gap report generation

### Integration Tests

```bash
python -m pytest tests/test_extract_snapshot_integration.py -v
```

**Test Scenarios**:
- Full extraction for 5 Effissimo campaigns
- Mixed fiscal year-ends (March, December)
- Point-in-time validation across all campaigns
- Data quality flagging
- Gap report generation

### Demo Script

```bash
python examples/snapshot_extraction_demo.py
```

**Note**: Requires Bloomberg Terminal running and logged in.

## Performance

### Extraction Time

| Companies | Fields | Time (Sequential) | Time (Parallel) |
|-----------|--------|-------------------|-----------------|
| 5         | 46     | ~30 seconds       | ~15 seconds     |
| 10        | 46     | ~60 seconds       | ~25 seconds     |
| 30        | 46     | ~180 seconds      | ~60 seconds     |

**Bottleneck**: Bloomberg API rate limits (2-second minimum between requests)

**Optimization**: Parallel extraction by field group reduces total time by ~50%

### Memory Usage

- Peak memory: ~200 MB for 30 companies × 46 fields
- DataFrame size: ~150 KB (uncompressed CSV)
- Gap report: ~50 KB (JSON)

## Best Practices

### 1. Always Validate Point-in-Time Safety

```python
# Before using snapshot data
validate_point_in_time_safety(campaigns)
```

### 2. Review Flagged Securities

```python
flagged = snapshot_df[snapshot_df["manual_review_flag"] == True]
print(f"Manual review required for {len(flagged)} securities")
```

### 3. Check Gap Report

```python
# Review field coverage
gap_report = extractor.log_field_gaps(snapshot_df)
print(f"Average field coverage: {gap_report['avg_field_coverage']:.1f}%")
```

### 4. Handle Missing Data

```python
# Check for critical missing fields
critical_missing = snapshot_df[
    snapshot_df[["PX_TO_BOOK_RATIO", "RETURN_COM_EQY"]].isna().any(axis=1)
]
```

## Common Issues

### Issue: Point-in-Time Violation

**Error**: `ValueError: snapshot_date >= campaign_start`

**Cause**: Fiscal alignment computed incorrectly

**Fix**: Verify campaign_start date is correct; check fiscal year-end month

### Issue: Low Field Coverage

**Error**: Many fields returning `NaN`

**Cause**: Security not in Bloomberg database, or data not available for snapshot date

**Fix**: Verify Bloomberg ticker is correct; check if company was public at snapshot date

### Issue: Extreme Net Cash Ratios

**Warning**: `net_cash_to_market_cap > 100%`

**Cause**: Market cap very low, or cash position exceptionally high

**Fix**: Review raw data for accuracy; common for distressed or cash-rich companies

## Future Enhancements

1. **Parallel Extraction by Security**: Currently parallelizes by field group; could further parallelize by security within each group

2. **Incremental Updates**: Cache previously extracted data; only fetch new campaigns

3. **Data Version Control**: Track snapshot version; allow rollback to previous extractions

4. **Enhanced Validation**: Cross-check derived fields against Bloomberg's calculated fields (e.g., compare computed net_cash with Bloomberg's NET_DEBT)

5. **Bulk Data Integration**: Add support for bulk fields (TOP_20_HOLDERS, DVD_HIST_ALL) in snapshot extraction

## Dependencies

- `bloomberg_session`: Bloomberg DAPI session manager
- `batching_engine`: Request batching and rate limiting
- `fiscal_period_aligner`: Snapshot date computation
- `pandas`: DataFrame operations
- `numpy`: Numerical computations

## Related Documentation

- [Phase 1: Fiscal Period Aligner](phase_1_fiscal_aligner.md)
- [Phase 2: Bloomberg Session Manager](phase_2_bloomberg_session.md)
- [Phase 3: Batching Engine](phase_3_batching_engine.md)
- [Bloomberg Fields Configuration](../config/bloomberg_fields.yaml)

## Contact

For questions or issues related to the Snapshot Extractor, please refer to the project documentation or contact the maintainers.
