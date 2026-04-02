# Phase 9-10: Data Validator & Excel Writer

**Status**: ✅ Complete
**Test Coverage**: >85%
**Integration**: Ready for Phase 11 orchestration

---

## Overview

Phase 9-10 implements the final data pipeline components:
- **Phase 9**: Data quality validation and audit reporting
- **Phase 10**: Formatted Excel workbook generation (5-sheet layout)

These modules ensure data integrity before export and generate publication-ready Excel workbooks for analyst consumption.

---

## Phase 9: Data Validator (`src/data_validator.py`)

### Purpose
Validates extracted data quality, detects range violations, and flags securities requiring manual review.

### Key Classes

#### `DataValidator`
Main validation engine with configurable rules.

```python
from data_validator import DataValidator

# Initialize with default rules
validator = DataValidator()

# Or with custom critical fields and range rules
validator = DataValidator(
    critical_fields=["PX_TO_BOOK_RATIO", "RETURN_COM_EQY", "CUR_MKT_CAP"],
    range_rules={
        "PX_TO_BOOK_RATIO": (0.1, 10.0, "warning"),
        "RETURN_COM_EQY": (-50.0, 50.0, "warning"),
    }
)
```

#### `DataQualityReport`
Comprehensive validation report with quality metrics.

```python
report = validator.validate_snapshot_data(snapshot_df)

print(f"Quality Score: {report.overall_quality_score:.1%}")
print(f"Range Violations: {len(report.range_violations)}")
print(f"Manual Review Required: {len(report.recommended_manual_review)}")

# Save to JSON
validator.save_report(report, filename="quality_report.json")

# Print human-readable summary
print(report.summary())
```

### Critical Fields (Default)

| Field | Description | Required |
|-------|-------------|----------|
| `PX_TO_BOOK_RATIO` | Price-to-book ratio | Yes |
| `RETURN_COM_EQY` | Return on equity | Yes |
| `CUR_MKT_CAP` | Market capitalization | Yes |
| `NET_DEBT` | Net debt (or `net_cash`) | Yes |
| `TRAIL_12M_SALES` | Trailing 12-month sales | Yes |

### Range Validation Rules (Japanese Equities)

| Field | Min | Max | Severity | Rationale |
|-------|-----|-----|----------|-----------|
| `PX_TO_BOOK_RATIO` | 0.1 | 10.0 | warning | Typical Japanese equity range |
| `RETURN_COM_EQY` | -50% | +50% | warning | Extreme profitability bounds |
| `CUR_MKT_CAP` | 0.0 | ∞ | error | Market cap must be positive |
| `net_cash_to_market_cap` | -1.0 | +1.0 | warning | Net cash ratio bounds |
| `BS_LEVERAGE` | 0.0 | 10.0 | warning | Leverage ratio bounds |

### Quality Scoring

Quality score (0.0 to 1.0) is computed as:

```
Quality Score = 0.6 × Avg(Critical Field Coverage)
              + 0.2 × Derived Fields Present
              + 0.2 × Data Recency
```

**Thresholds**:
- **100%**: All critical fields present
- **70%+**: Acceptable quality
- **30-70%**: Marginal quality (flag for review)
- **<30%**: Poor quality (manual review required)

### Manual Review Flagging

Securities are flagged for manual review if >30% of critical fields are missing.

```python
# Check which securities need manual review
flagged = validator.flag_manual_review_securities(df, threshold=0.3)
print(f"Manual review required for: {flagged}")
```

### Usage Example

```python
from data_validator import DataValidator

# Initialize validator
validator = DataValidator(logs_dir=Path("logs"))

# Validate snapshot data
snapshot_report = validator.validate_snapshot_data(snapshot_df)

# Validate ownership data
ownership_report = validator.validate_ownership_data(ownership_df)

# Print summary
print(snapshot_report.summary())

# Save report
validator.save_report(snapshot_report, "snapshot_quality_report.json")
```

---

## Phase 10: Excel Writer (`src/excel_writer.py`)

### Purpose
Generates formatted 5-sheet Excel workbooks with professional styling, number formatting, and conditional highlighting.

### Key Classes

#### `ExcelWriter`
Main Excel generation engine.

```python
from excel_writer import ExcelWriter
from data_validator import DataQualityReport

# Initialize writer
writer = ExcelWriter(output_dir=Path("output"))

# Generate workbook
output_path = writer.write_activist_workbook(
    activist_name="Effissimo Capital Management",
    snapshot_df=snapshot_df,
    ownership_df=ownership_df,
    events_df=events_df,
    price_history_df=price_history_df,
    peer_comps_df=peer_comps_df,
    data_quality_report=quality_report,
)

print(f"Workbook created: {output_path}")
```

### 5-Sheet Layout

#### Sheet 1: Financial Snapshot + Metadata

**Metadata Header** (Rows 1-6):
| Metric | Value |
|--------|-------|
| Extraction Date | 2026-04-01 14:35:22 |
| Activist Name | Effissimo Capital Management |
| Number of Targets | 30 |
| Data Quality Score | 89.3% |
| Manual Review Required | 3 |

**Data Section** (Row 7+): One row per company with ~50 financial fields

#### Sheet 2: Ownership
Top 20 holders for each target company

#### Sheet 3: Corporate Actions
Corporate events (dividends, splits, buybacks)

#### Sheet 4: Price History
Daily price data for each target

#### Sheet 5: Peer Comparables
Peer comparison data (no metadata section)

### Formatting Features

#### Freeze Panes
- **Sheet 1**: Freeze at row 8 (below metadata and headers)
- **Sheets 2-5**: Freeze at row 2 (below headers)

#### Column Widths
- Auto-fit based on content
- Maximum width: 50 characters

#### Number Formatting

| Field Type | Format | Example |
|------------|--------|---------|
| Percentages | `0.00%` | 10.52% |
| Currency (Yen) | `¥#,##0` | ¥1,000,000 |
| Dates | `YYYY-MM-DD` | 2021-03-31 |

**Auto-detected by keywords**:
- **Percentages**: `PCT`, `PERCENT`, `RATIO`, `ROE`, `ROA`, `MARGIN`, `RETURN_COM_EQY`
- **Currency**: `MKT_CAP`, `MARKET_CAP`, `SALES`, `REVENUE`, `NET_CASH`, `DEBT`, `PRICE`, `PX_LAST`
- **Dates**: `DATE`, `DT`, `SNAPSHOT`, `CAMPAIGN_START`

#### Header Styling
- Bold white text
- Blue background (#366092)
- Centered alignment

#### Conditional Formatting
- **Missing data**: Red fill (#FFC7CE)
- **Outliers**: Yellow fill (#FFEB9C)
- **Manual review**: Orange fill (#FDE9D9)

### File Naming Convention

```
{activist_name}_bloomberg_data_{YYYYMMDD}.xlsx
```

Example: `Effissimo_Capital_Management_bloomberg_data_20260401.xlsx`

### Usage Example

```python
from excel_writer import ExcelWriter
from data_validator import DataValidator

# Validate data first
validator = DataValidator()
quality_report = validator.validate_snapshot_data(snapshot_df)

# Create Excel workbook
writer = ExcelWriter()
output_path = writer.write_activist_workbook(
    activist_name="Effissimo Capital Management",
    snapshot_df=snapshot_df,
    ownership_df=ownership_df,
    events_df=events_df,
    price_history_df=price_history_df,
    peer_comps_df=peer_comps_df,
    data_quality_report=quality_report,
)

# Verify workbook
from openpyxl import load_workbook
wb = load_workbook(output_path)
print(f"Created {len(wb.sheetnames)} sheets: {wb.sheetnames}")
```

---

## Testing

### Test Coverage

| Module | Tests | Coverage | Status |
|--------|-------|----------|--------|
| `data_validator.py` | 24 tests | >90% | ✅ Passing |
| `excel_writer.py` | 20 tests | >90% | ✅ Passing |

### Run Tests

```bash
# Test data validator
python -m pytest tests/test_data_validator.py -v

# Test Excel writer
python -m pytest tests/test_excel_writer.py -v

# Run all Phase 9-10 tests
python -m pytest tests/test_data_validator.py tests/test_excel_writer.py -v

# With coverage report
python -m pytest tests/test_data_validator.py tests/test_excel_writer.py \
    --cov=src/data_validator --cov=src/excel_writer --cov-report=term-missing
```

### Test Coverage Highlights

#### Data Validator Tests
- ✅ Critical field coverage calculation
- ✅ Range violation detection
- ✅ Manual review flagging (>30% missing)
- ✅ Quality score computation
- ✅ Custom validation rules
- ✅ Ownership data validation
- ✅ Report saving (JSON)

#### Excel Writer Tests
- ✅ 5-sheet workbook creation
- ✅ Metadata header in Sheet 1
- ✅ Freeze panes application
- ✅ Column width auto-fit
- ✅ Number formatting (%, currency, dates)
- ✅ Header row styling
- ✅ File creation and readability
- ✅ Data integrity verification

---

## Demo

Run the Phase 9-10 demonstration:

```bash
python examples/phase9_10_demo.py
```

**Demo Output**:
```
================================================================================
Phase 9-10 Demo: Data Validation & Excel Export
================================================================================

Created sample data:
  - Snapshot: 5 securities
  - Ownership: 3 holders
  - Events: 2 corporate actions
  - Price History: 10 daily prices
  - Peer Comps: 2 peer comparisons

--------------------------------------------------------------------------------
PHASE 9: Data Validation
--------------------------------------------------------------------------------

Validating snapshot data...

Validation Summary:
Data Quality Report - 2026-04-01T17:25:46
Total Securities: 5
Overall Quality Score: 86.1%
Range Violations: 4
Manual Review Required: 1

✓ Quality report saved to: logs/effissimo_quality_report.json

--------------------------------------------------------------------------------
PHASE 10: Excel Export
--------------------------------------------------------------------------------

Generating 5-sheet Excel workbook...

✓ Excel workbook created: output/Effissimo_Capital_Management_bloomberg_data_20260401.xlsx

Workbook contains 5 sheets:
  1. Financial Snapshot (12 rows × 11 cols)
  2. Ownership (4 rows × 5 cols)
  3. Corporate Actions (3 rows × 4 cols)
  4. Price History (11 rows × 4 cols)
  5. Peer Comparables (3 rows × 6 cols)
```

---

## Integration with Pipeline

Phase 9-10 integrates with the full pipeline:

```python
# Phase 4-8: Extract data
snapshot_df = snapshot_extractor.extract_all(targets)
ownership_df = ownership_extractor.extract_all(targets)
events_df = events_extractor.extract_all(targets)
price_df = price_extractor.extract_all(targets)
peer_comps_df = peer_comps_extractor.extract_all(targets)

# Phase 9: Validate
validator = DataValidator()
quality_report = validator.validate_snapshot_data(snapshot_df)

if quality_report.overall_quality_score < 0.7:
    logger.warning("Data quality below 70% threshold")

# Phase 10: Export to Excel
writer = ExcelWriter()
output_path = writer.write_activist_workbook(
    activist_name="Effissimo Capital Management",
    snapshot_df=snapshot_df,
    ownership_df=ownership_df,
    events_df=events_df,
    price_history_df=price_df,
    peer_comps_df=peer_comps_df,
    data_quality_report=quality_report,
)

logger.info(f"Pipeline complete: {output_path}")
```

---

## File Locations

| File | Path | Description |
|------|------|-------------|
| Data Validator | `src/data_validator.py` | Validation engine |
| Excel Writer | `src/excel_writer.py` | Excel generation |
| Validator Tests | `tests/test_data_validator.py` | 24 unit tests |
| Writer Tests | `tests/test_excel_writer.py` | 20 unit tests |
| Demo Script | `examples/phase9_10_demo.py` | Interactive demo |
| Quality Reports | `logs/` | JSON validation reports |
| Excel Outputs | `output/` | Generated workbooks |

---

## Dependencies

```python
# Core
pandas>=2.3.2
openpyxl>=3.1.5

# Testing
pytest>=8.0.0
pytest-cov>=5.0.0
```

---

## Next Steps

**Phase 11: Orchestration Layer**
- Create master pipeline orchestrator
- Implement end-to-end workflow
- Add progress tracking and logging
- Error handling and recovery

**Phase 12-14: Testing & Documentation**
- Integration tests for full pipeline
- Performance optimization
- User documentation
- Deployment guide

---

## Success Criteria

### Phase 9: Data Validator ✅
- [x] DataValidator validates all critical fields
- [x] Range violations detected (PBR, ROE, Market Cap, etc.)
- [x] Manual review flagging works (>30% missing)
- [x] Quality report comprehensive (coverage, violations, notes)
- [x] Unit test coverage >85%

### Phase 10: Excel Writer ✅
- [x] 5-sheet Excel workbook generated
- [x] Metadata in Sheet 1 header (not separate sheet)
- [x] All formatting applied correctly (freeze panes, widths, colors)
- [x] Number formatting works (%, currency, dates)
- [x] File opens without errors in Excel
- [x] Conditional formatting highlights issues
- [x] Unit test coverage >85%

---

## Troubleshooting

### Common Issues

**Issue**: "Module src/data_validator was never imported"
- **Solution**: Use `python -m pytest` instead of `pytest`

**Issue**: Number formatting not applied
- **Solution**: Ensure data values are numeric (int/float), not strings

**Issue**: Excel file corrupted
- **Solution**: Check pandas and openpyxl versions match requirements.txt

**Issue**: Coverage report not generated
- **Solution**: Run tests from project root directory

---

## Author

Bloomberg Activist Data Pipeline
Phase 9-10 Implementation
April 2026
