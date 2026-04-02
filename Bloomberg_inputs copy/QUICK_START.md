# Bloomberg Pipeline - Quick Start Guide

## Prerequisites Checklist

- [ ] Bloomberg Terminal running and logged in
- [ ] Python 3.8+ installed
- [ ] Virtual environment activated
- [ ] Bloomberg Python API (blpapi) installed
- [ ] Input CSV ready with 30 companies

---

## Installation (One-Time Setup)

```bash
# 1. Navigate to project
cd "/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs"

# 2. Create virtual environment
python -m venv venv
source venv/bin/activate  # macOS/Linux
# venv\Scripts\activate   # Windows

# 3. Install dependencies
pip install -r requirements.txt

# 4. Install Bloomberg API
# Option A: From Terminal (WAPI<GO> → Downloads → Python API)
# Option B: Via pip (if available)
pip install blpapi

# 5. Verify installation
python -c "import blpapi; print('Bloomberg API ready')"
pytest  # Should show 367 tests passing
```

---

## Usage Commands

### Test Run (Single Company)
```bash
python src/run_all.py \
    --input input/test_single.csv \
    --activist "Effissimo Capital Management" \
    --output output/test_single.xlsx
```

### Production Run (All 30 Companies)
```bash
python src/run_all.py \
    --input input/effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --output output/effissimo_full_data.xlsx \
    --log-level INFO
```

### With Debug Logging
```bash
python src/run_all.py \
    --input input/effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --output output/effissimo_full_data.xlsx \
    --log-level DEBUG
```

---

## Input CSV Format

**File:** `input/effissimo_summary_by_company.csv`

**Required Columns:**
```csv
ticker,activist_stake_percent,first_filing,last_filing,campaign_outcome
7267.T,13.5,2018-04-15,2019-03-31,Ongoing
6503.T,8.2,2019-07-01,2020-06-30,Board Seats
```

**Ticker Format:** Tokyo Stock Exchange with .T extension (e.g., "7267.T")
**Date Format:** YYYY-MM-DD
**Stake:** Numeric percentage (e.g., 13.5 for 13.5%)

---

## Output Structure

### Excel Workbook (5 Sheets)

1. **Snapshot** - 60+ financial/valuation/governance fields
2. **Ownership** - Top 20 institutional holders per company
3. **Events** - Corporate actions during campaign period
4. **Price History** - Daily OHLCV data
5. **Peer Comps** - GICS sector benchmarks

### Log Files

- `logs/execution_YYYYMMDD_HHMMSS.log` - Runtime log
- `logs/quality_report_YYYYMMDD_HHMMSS.txt` - Data quality analysis
- `logs/gap_report_YYYYMMDD_HHMMSS.csv` - Missing field details

---

## Expected Runtime

- **Single Company:** 5-10 minutes
- **30 Companies:** 2.5-5 hours
- **Memory Usage:** < 500 MB
- **Output File Size:** 2-5 MB per company

---

## Data Quality Checks

After pipeline completion, verify:

1. **Snapshot Sheet:**
   - All 30 tickers present
   - Key fields populated (Revenue, EBITDA, Market Cap)
   - Quality score > 70% for each security

2. **Ownership Sheet:**
   - 20 rows per ticker
   - Ownership percentages sum correctly
   - No duplicate holders

3. **Events Sheet:**
   - Events within campaign period
   - Reasonable dividend amounts
   - Logical split ratios

4. **Price History Sheet:**
   - Daily data without gaps (except holidays)
   - No extreme price jumps
   - Volume data present

5. **Peer Comps Sheet:**
   - Sector assignment correct
   - Median values reasonable
   - Target excluded from peers

---

## Troubleshooting

### "Bloomberg Terminal not running"
**Fix:** Start Bloomberg Terminal and wait for full login

### "Ticker not found"
**Fix:** Verify ticker has .T extension and is active on Bloomberg

### "Session timeout"
**Fix:** Reduce batch size or process companies one at a time

### "High missing data (>30%)"
**Fix:** Check fiscal period alignment - some fields may be unavailable for specified period

### "Excel file locked"
**Fix:** Close any open Excel files in output directory

---

## Running Tests

```bash
# All tests (367)
pytest

# Specific module
pytest tests/test_extract_snapshot.py

# With coverage
pytest --cov=src --cov-report=html

# Integration tests only (requires Bloomberg Terminal)
pytest tests/test_integration_*.py

# Verbose output
pytest -v -s
```

---

## File Locations

**Input:** `/input/effissimo_summary_by_company.csv`
**Output:** `/output/*.xlsx`
**Logs:** `/logs/*.log`
**Code:** `/src/*.py`
**Tests:** `/tests/test_*.py`
**Docs:** `/docs/*.md`
**Examples:** `/examples/*.py`

---

## Getting Help

1. **Quick Reference:** This file
2. **Comprehensive Guide:** PROJECT_README.md
3. **Executive Summary:** EXECUTIVE_SUMMARY.md
4. **Phase Details:** docs/phase{1-11}_*.md
5. **Code Examples:** examples/*.py
6. **Bloomberg API:** WAPI<GO> on Terminal

---

## Command Reference Card

```bash
# Activate environment
source venv/bin/activate

# Run pipeline (test)
python src/run_all.py --input input/test.csv --activist "Effissimo Capital Management" --output output/test.xlsx

# Run pipeline (production)
python src/run_all.py --input input/effissimo_summary_by_company.csv --activist "Effissimo Capital Management" --output output/effissimo_data.xlsx --log-level INFO

# Run all tests
pytest

# Check Bloomberg API
python -c "import blpapi; print('OK')"

# View logs
tail -f logs/execution_*.log

# Deactivate environment
deactivate
```

---

## Success Criteria

- [ ] Pipeline completes without errors
- [ ] Excel file generated with 5 sheets
- [ ] All 30 companies present in output
- [ ] Data quality score > 70% for each security
- [ ] No critical errors in execution log
- [ ] Gap report shows acceptable missing data levels
- [ ] Key financial metrics populated for known companies

---

**Last Updated:** April 1, 2026
**Status:** Production Ready (367 tests passing)
