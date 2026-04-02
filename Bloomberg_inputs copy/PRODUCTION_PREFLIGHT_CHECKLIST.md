# Production Pre-Flight Checklist
## Bloomberg Activist Data Pipeline - Effissimo Extraction

**Last Updated:** April 1, 2026
**Target Dataset:** 30 Effissimo Capital Management campaigns
**Status:** Ready for first production run

---

## 1. Environment Setup

### 1.1 Bloomberg Terminal
- [ ] Bloomberg Terminal installed and running
- [ ] Active Bloomberg Professional subscription
- [ ] Terminal logged in with valid credentials
- [ ] Terminal has been running for at least 5 minutes (API initialization)

**Verification:**
```bash
# On Bloomberg Terminal keyboard, press:
# <HELP> <HELP> to verify session is active
```

### 1.2 Python Environment
- [ ] Python 3.8+ installed (detected: Python 3.13.7) ✅
- [ ] Virtual environment activated (recommended)
- [ ] Core dependencies installed (pandas, openpyxl, pyyaml) ✅

**Verification:**
```bash
python3 -c "import pandas; import openpyxl; import yaml; print('Core deps OK')"
```

### 1.3 Bloomberg Python API
- [ ] **BLOCKER:** `blpapi` module NOT INSTALLED

**Installation Required:**
```bash
# Option 1: From Bloomberg Terminal
# WAPI<GO> → Downloads → Python API → Download wheel file
pip install /path/to/blpapi-3.24.10-cp313-cp313-macosx_14_0_arm64.whl

# Option 2: Via conda (if using conda environment)
conda install -c conda-forge blpapi

# Option 3: Via pip (if wheel is in PyPI - check compatibility)
pip install blpapi
```

**Verification:**
```bash
python3 -c "import blpapi; print(f'Bloomberg API v{blpapi.__version__} installed')"
```

---

## 2. Input Data Validation

### 2.1 CSV File Location
- [ ] File exists: `effissimo_summary_by_company.csv`
- [x] File located in working directory ✅
- [ ] File has 30 data rows (31 total including header)

**Current Location:**
```
/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs/effissimo_summary_by_company.csv
```

### 2.2 CSV Schema Validation
- [x] Column `target_company` present ✅
- [x] Column `target_ticker` present ✅
- [x] Column `total_filings` present ✅
- [x] Column `first_filing` present (YYYY-MM-DD format) ✅
- [x] Column `last_filing` present (YYYY-MM-DD format) ✅
- [x] Column `max_ownership_pct` present (decimal format) ✅
- [x] Column `min_ownership_pct` present (decimal format) ✅

### 2.3 Data Quality Issues

**CRITICAL ISSUE DETECTED:**
- [ ] **DUPLICATE TICKER:** 6676.T appears twice (rows 23 and 27)
  - Row 23: 株式会社メルコホールディングス (Melco Holdings)
  - Row 27: 株式会社バッファロー (Buffalo Inc.)

**Action Required:**
User must verify which company is correct or if one ticker is a typo.

**Possible resolutions:**
1. Verify correct ticker for 株式会社バッファロー (Buffalo Inc.) - may be subsidiary/parent relationship
2. Check if Melco Holdings and Buffalo are the same entity (Buffalo was acquired by Melco)
3. Confirm if one entry should be removed

**Other Observations:**
- 3 companies have very recent last_filing dates (2026-03): campaigns may still be active
- 1 company has only 1 filing (8013.T): minimal data, may result in incomplete extraction
- Campaign durations range from 1 day to 5 years

---

## 3. Output Directory Setup

### 3.1 Directory Structure
- [ ] Create output directory: `output/`
- [ ] Create logs directory: `logs/`
- [ ] Verify write permissions

**Setup Commands:**
```bash
cd "/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs"
mkdir -p output logs
touch output/.gitkeep logs/.gitkeep
```

### 3.2 Disk Space
- [ ] Verify at least 500 MB free disk space
  - Expected Excel file size: ~3 MB per company
  - 30 companies × 3 MB = ~90 MB
  - Logs and temp files: ~50 MB
  - Safety margin: 360 MB

**Verification:**
```bash
df -h "/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs"
```

---

## 4. Test Extraction (Single Company)

**Recommendation:** Before running full 30-company extraction, test with one company.

### 4.1 Create Test CSV
```bash
head -n 2 effissimo_summary_by_company.csv > input/test_single.csv
# This creates a CSV with header + first company (9107.T - Kawasaki Kisen)
```

### 4.2 Run Test Extraction
```bash
python3 src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --output output/test_9107T.xlsx \
    --log-level DEBUG
```

### 4.3 Validate Test Output
- [ ] Excel file created: `output/test_9107T.xlsx`
- [ ] File size: 2-5 MB (reasonable range)
- [ ] Excel opens without errors
- [ ] All 5 sheets present:
  - [ ] Snapshot (60+ fields)
  - [ ] Ownership (Top 20 holders)
  - [ ] Events (corporate actions)
  - [ ] Price History (daily OHLCV)
  - [ ] Peer Comps (sector benchmarks)
- [ ] Snapshot sheet has data in key fields:
  - [ ] Market Cap (CUR_MKT_CAP)
  - [ ] Total Revenue (SALES_REV_TURN)
  - [ ] P/E Ratio (PE_RATIO)
- [ ] Log file created: `logs/run_all_YYYYMMDD_HHMMSS.log`
- [ ] Data quality report generated: `logs/gap_report_YYYYMMDD_HHMMSS.csv`

### 4.4 Expected Test Runtime
- Single company extraction: **5-10 minutes**
- Bloomberg API calls dominate runtime (network latency + Terminal processing)
- Most time spent in:
  - Snapshot extraction (60+ fields)
  - Price history (daily data, potentially 5 years)
  - Ownership extraction (Top 20 holders)

---

## 5. Production Run Configuration

### 5.1 Execution Parameters

**Full Dataset Extraction:**
```bash
python3 src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --output output/effissimo_full_extraction.xlsx \
    --log-level INFO
```

**Key Configuration Decisions:**
- `--log-level INFO`: Balance between verbosity and readability (DEBUG for troubleshooting)
- Output file: Single consolidated workbook vs. 30 individual files
  - Current default: **Single workbook** (all companies in one Excel file)
  - Alternative: Process companies one-by-one and generate 30 separate files

### 5.2 Runtime Estimates

**Per-Company Breakdown:**
- Ticker conversion: < 1 second
- Fiscal alignment (Bloomberg query): 5-10 seconds
- Snapshot extraction (60 fields): 60-120 seconds
- Ownership extraction (Top 20): 15-30 seconds
- Events extraction: 10-20 seconds
- Price history extraction: 30-90 seconds (depends on campaign duration)
- Peer comps extraction: 20-40 seconds
- Data validation: 5 seconds
- Excel writing: 10 seconds

**Total per company:** 5-10 minutes
**30 companies:** 2.5-5 hours

**Variability Factors:**
- Bloomberg Terminal load (time of day, concurrent users)
- Network latency to Bloomberg servers
- Campaign duration (longer campaigns = more price history data)
- Number of corporate events (more events = longer extraction)

### 5.3 Resource Usage

**Memory:**
- Peak usage: ~300-500 MB
- Scales linearly with company count
- pandas DataFrames are primary memory consumer

**CPU:**
- Low CPU usage (I/O bound, not compute bound)
- Bloomberg API calls are network-limited
- Excel writing is single-threaded

**Network:**
- All data transferred via Bloomberg Terminal (localhost connection)
- No direct internet access required
- Bloomberg Terminal handles all external communication

---

## 6. Monitoring & Validation

### 6.1 Real-Time Monitoring

**During Execution:**
- Monitor log output for errors
- Watch for Bloomberg API timeout errors (retry logic built-in)
- Check disk space periodically (should not be an issue for 30 companies)

**Log Locations:**
```bash
# Main execution log
tail -f logs/run_all_YYYYMMDD_HHMMSS.log

# Data quality report (generated at end)
cat logs/gap_report_YYYYMMDD_HHMMSS.csv
```

### 6.2 Success Criteria

**Execution Success:**
- [ ] Script completes without fatal errors
- [ ] Excel file created in output/ directory
- [ ] File size reasonable (50-150 MB for 30 companies)
- [ ] Log file shows "SUCCESS" for all companies
- [ ] No "CRITICAL" or "ERROR" messages in final log

**Data Quality Thresholds:**
- [ ] At least 70% field completeness per company (on average)
- [ ] All companies have non-null Market Cap
- [ ] All companies have at least 1 ownership record
- [ ] Price history data present for campaign period
- [ ] No more than 5 companies flagged for manual review (>30% missing data)

### 6.3 Known Expected Warnings

**Non-Critical Warnings (Expected):**
- "Field not available for this security" - Some Bloomberg fields may not exist for all companies
- "No events found for period" - Some companies may have no corporate actions during campaign
- "Peer comparison data incomplete" - Small/illiquid companies may lack robust peer set
- "Ownership data may be delayed" - Bloomberg institutional holdings can lag

**Do NOT treat as failures:**
- Missing values in non-critical fields (e.g., analyst estimates, foreign ownership)
- Empty Events sheet for companies with no corporate actions
- Peer comps with < 10 comparables (acceptable for niche sectors)

---

## 7. Output Validation

### 7.1 Excel Workbook Structure

**Expected Output:**
- File: `output/effissimo_full_extraction.xlsx`
- Sheets: 5 (Snapshot, Ownership, Events, Price History, Peer Comps)
- Format: .xlsx (OpenPyXL-compatible)

**Sheet-Specific Checks:**

**Snapshot Sheet:**
- [ ] 30 rows (one per company) + header
- [ ] 60+ columns (Bloomberg fields)
- [ ] Key fields populated:
  - [ ] TICKER (Bloomberg format: "9107 JP Equity")
  - [ ] NAME (company name)
  - [ ] CUR_MKT_CAP (market cap)
  - [ ] SALES_REV_TURN (revenue)
  - [ ] TOT_DEBT_TO_TOT_EQY (debt-to-equity)

**Ownership Sheet:**
- [ ] Up to 600 rows (30 companies × 20 holders max)
- [ ] Columns: TICKER, HOLDER_NAME, PCT_HELD, POSITION
- [ ] At least 10 rows per major company

**Events Sheet:**
- [ ] Variable row count (depends on corporate actions)
- [ ] Columns: TICKER, EVENT_TYPE, ANNOUNCE_DT, EX_DT, AMOUNT
- [ ] Events only within campaign periods (first_filing to last_filing)

**Price History Sheet:**
- [ ] Variable row count (daily data × campaign duration)
- [ ] Columns: TICKER, DATE, OPEN, HIGH, LOW, CLOSE, VOLUME
- [ ] No gaps in trading days (weekends/holidays expected)

**Peer Comps Sheet:**
- [ ] 30 rows (one per company) + header
- [ ] Columns: TICKER, GICS_SECTOR, MEDIAN_PE, MEDIAN_PB, MEDIAN_EV_EBITDA, etc.
- [ ] Peer statistics exclude target company itself

### 7.2 Data Quality Report

**Gap Report Location:**
```
logs/gap_report_YYYYMMDD_HHMMSS.csv
```

**Report Contents:**
- Securities with >30% missing data (flagged for manual review)
- Field-level completeness percentages
- Summary statistics (mean, median completeness)

**Acceptance Criteria:**
- [ ] Average completeness across all companies: ≥ 70%
- [ ] No more than 5 companies with completeness < 50%
- [ ] All companies have Market Cap (100% for this field)

### 7.3 Spot Check (Manual Validation)

**Select 3 Known Companies:**
1. 9107.T (Kawasaki Kisen) - Most filings (115), longest campaign
2. 7752.T (Ricoh) - Well-known, liquid stock
3. 8013.T (Naigai) - Smallest campaign (1 filing), edge case

**Validation Steps:**
1. Open Excel workbook
2. Filter Snapshot sheet for each ticker
3. Verify key metrics match Bloomberg Terminal (if accessible):
   - Market cap (CURRENT_MKT_CAP on Terminal)
   - P/E ratio (PE_RATIO on Terminal)
   - Revenue (SALES_REV_TURN on Terminal)
4. Check Ownership sheet for reasonable holder names (not just error codes)
5. Verify Price History dates align with campaign periods

---

## 8. Troubleshooting

### 8.1 Common Errors

**Error: "ModuleNotFoundError: No module named 'blpapi'"**
- **Cause:** Bloomberg Python API not installed
- **Fix:** See Section 1.3 - Install blpapi

**Error: "Failed to open session"**
- **Cause:** Bloomberg Terminal not running or not fully initialized
- **Fix:**
  1. Launch Bloomberg Terminal
  2. Log in with credentials
  3. Wait 5 minutes for full startup
  4. Retry extraction

**Error: "SecurityError: Invalid ticker"**
- **Cause:** Ticker conversion failed or ticker not in Bloomberg database
- **Fix:**
  1. Verify ticker exists on Bloomberg (check Terminal: <ticker> <EQUITY> <GO>)
  2. Check for delisted companies (may require historical data access)
  3. Review CSV for typos in ticker column

**Error: "TimeoutError: Request timed out"**
- **Cause:** Bloomberg API overloaded or network issue
- **Fix:**
  1. Wait 5 minutes and retry
  2. Reduce batch size (modify batching_engine.py: max_batch_size)
  3. Check Terminal connection: <HELP> <HELP>

**Warning: "Field not available: <FIELD_NAME>"**
- **Cause:** Field does not exist for this security (expected for some companies)
- **Fix:** This is normal - not all fields apply to all companies. Pipeline handles gracefully.

### 8.2 Data Quality Issues

**Issue: Completeness < 50% for many companies**
- **Possible Causes:**
  1. Bloomberg data coverage gaps for small-cap Japanese equities
  2. Delisted companies (historical data may be limited)
  3. Field names in bloomberg_fields.yaml incorrect
- **Fix:**
  1. Review gap_report.csv to identify specific missing fields
  2. Cross-check field names on Bloomberg Terminal
  3. Consider removing non-essential fields from bloomberg_fields.yaml

**Issue: Empty Ownership sheet**
- **Possible Cause:** Bloomberg institutional holdings not available for these companies
- **Fix:**
  1. Verify on Terminal: <ticker> <HDS> <GO> (Holders screen)
  2. Some Japanese companies may not report institutional ownership
  3. Expected for small/illiquid stocks

**Issue: No Events found for any company**
- **Possible Cause:** Date range filtering too restrictive or events API call failing
- **Fix:**
  1. Check log for EventsExtractor errors
  2. Verify first_filing and last_filing dates are correct
  3. Test single company with known corporate actions (e.g., 9107.T)

---

## 9. Post-Extraction Actions

### 9.1 Immediate Validation
- [ ] Open Excel workbook and verify structure (5 sheets)
- [ ] Review data quality report in logs/
- [ ] Spot-check 3 known companies for data accuracy
- [ ] Flag anomalies for manual review

### 9.2 Data Storage
- [ ] Save Excel file to permanent location (currently in `output/`)
- [ ] Backup logs directory (contains quality reports)
- [ ] Archive input CSV with timestamp (for reproducibility)

### 9.3 Next Steps
- [ ] Share output with stakeholders (if applicable)
- [ ] Identify companies requiring manual data correction
- [ ] Plan for periodic re-extraction (if campaigns are ongoing)
- [ ] Document any customizations or edge cases discovered

---

## 10. Support & Escalation

### 10.1 Documentation References
- **Comprehensive Guide:** `PROJECT_README.md`
- **Executive Summary:** `EXECUTIVE_SUMMARY.md`
- **Phase-Specific Docs:** `docs/` directory
- **Code Examples:** `examples/` directory
- **Test Cases:** `tests/` directory (367 passing tests)

### 10.2 Bloomberg Support
- **API Documentation:** WAPI<GO> on Bloomberg Terminal
- **Help Desk:** <HELP> <HELP> on Terminal (chat with Bloomberg support)
- **Phone Support:** Check Terminal for regional help desk numbers

### 10.3 Code Issues
- **Architecture:** See `.claude/rules/architecture.md`
- **Bloomberg Fields:** See `.claude/rules/bloomberg-field-spec.md`
- **Test Suite:** Run `pytest -v` to verify all 367 tests still pass

---

## 11. Final Pre-Flight Checklist

**Before executing production run:**

- [ ] 1. Bloomberg Terminal running and logged in
- [ ] 2. Bloomberg Python API (blpapi) installed
- [ ] 3. Core Python dependencies installed (pandas, openpyxl, pyyaml)
- [ ] 4. Input CSV located and validated
- [ ] 5. **CRITICAL:** Duplicate ticker issue (6676.T) resolved
- [ ] 6. Output and logs directories created
- [ ] 7. Sufficient disk space available (500 MB+)
- [ ] 8. Test extraction completed successfully (single company)
- [ ] 9. Test output validated (5 sheets, reasonable data)
- [ ] 10. Execution command prepared (see Section 5.1)

**Once all checks pass, proceed with production run.**

---

**Production Status:** PENDING BLOCKERS
- **Primary Blocker:** Bloomberg Python API not installed
- **Secondary Issue:** Duplicate ticker (6676.T) requires user verification
- **Estimated Time to Production Ready:** 30-60 minutes (API install + ticker fix)

**Last Review:** April 1, 2026
