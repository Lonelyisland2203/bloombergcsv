# Bloomberg Activist Pipeline - Deployment Runbook
## Production Deployment Guide for Effissimo Extraction

**Version:** 1.0
**Last Updated:** April 1, 2026
**Target:** 30 Effissimo Capital Management campaigns
**Estimated Runtime:** 2.5-5 hours

---

## Table of Contents

1. [Pre-Deployment Setup](#1-pre-deployment-setup)
2. [Installation Procedures](#2-installation-procedures)
3. [Data Preparation](#3-data-preparation)
4. [Execution Workflow](#4-execution-workflow)
5. [Monitoring & Logging](#5-monitoring--logging)
6. [Validation Procedures](#6-validation-procedures)
7. [Troubleshooting Guide](#7-troubleshooting-guide)
8. [Post-Deployment](#8-post-deployment)

---

## 1. Pre-Deployment Setup

### 1.1 System Requirements

**Hardware:**
- Disk space: 500 MB minimum
- RAM: 2 GB minimum (4 GB recommended)
- Network: Bloomberg Terminal connection required

**Software:**
- macOS 10.15+ / Windows 10+ / Linux
- Python 3.8+ (detected: Python 3.13.7)
- Bloomberg Terminal (active subscription)
- Bloomberg Python API (blpapi)

### 1.2 Environment Preparation

**Step 1: Navigate to project directory**
```bash
cd "/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs"
```

**Step 2: Verify Python version**
```bash
python3 --version
# Expected output: Python 3.13.7 or similar
```

**Step 3: Create virtual environment (recommended)**
```bash
python3 -m venv venv
source venv/bin/activate  # macOS/Linux
# OR
venv\Scripts\activate  # Windows
```

**Step 4: Create output directories**
```bash
mkdir -p output logs input
```

---

## 2. Installation Procedures

### 2.1 Core Dependencies

**Install core Python packages:**
```bash
pip install pandas==2.3.2 openpyxl==3.1.5 pyyaml==6.0.2
```

**Verify installation:**
```bash
python3 -c "import pandas; import openpyxl; import yaml; print('Core dependencies OK')"
```

### 2.2 Bloomberg Python API Installation

**CRITICAL: This is the primary blocker for production deployment.**

**Option 1: Install from Bloomberg Terminal (Recommended)**
```bash
# 1. Open Bloomberg Terminal
# 2. Type: WAPI<GO>
# 3. Navigate to: Downloads → Python API
# 4. Download the appropriate wheel file for your system:
#    - macOS ARM (M1/M2): blpapi-*-cp313-cp313-macosx_14_0_arm64.whl
#    - macOS Intel: blpapi-*-cp313-cp313-macosx_10_9_x86_64.whl
#    - Windows: blpapi-*-cp313-cp313-win_amd64.whl
# 5. Install the downloaded wheel:
pip install ~/Downloads/blpapi-3.24.10-cp313-cp313-macosx_14_0_arm64.whl
```

**Option 2: Install via conda**
```bash
conda install -c conda-forge blpapi
```

**Option 3: Install via pip (if available)**
```bash
pip install blpapi
# NOTE: This may fail on newer Python versions (3.13+)
# If it fails, use Option 1 (wheel from Bloomberg)
```

**Verification:**
```bash
python3 -c "import blpapi; print(f'Bloomberg API v{blpapi.__version__} installed successfully')"
```

**Expected Output:**
```
Bloomberg API v3.24.10 installed successfully
```

**Troubleshooting Installation:**
- If wheel file fails to install, check Python version compatibility
- Python 3.13 requires blpapi >= 3.24.0
- Download directly from Bloomberg Terminal (most reliable method)
- Contact Bloomberg support via <HELP><HELP> on Terminal if issues persist

### 2.3 Bloomberg Terminal Connection

**Step 1: Launch Bloomberg Terminal**
- Open Bloomberg Terminal application
- Log in with valid credentials
- Wait for full initialization (typically 2-5 minutes)

**Step 2: Verify Terminal is responsive**
```
# On Bloomberg Terminal keyboard:
<HELP> <HELP>
# This should open the help/chat interface
# If it opens, Terminal is ready
```

**Step 3: Test API connectivity (from Python)**
```bash
python3 << 'EOF'
import blpapi

# Attempt to start session
session_options = blpapi.SessionOptions()
session_options.setServerHost('localhost')
session_options.setServerPort(8194)
session = blpapi.Session(session_options)

if session.start():
    print("SUCCESS: Bloomberg API connection established")
    session.stop()
else:
    print("ERROR: Failed to connect to Bloomberg Terminal")
EOF
```

**Expected Output:**
```
SUCCESS: Bloomberg API connection established
```

---

## 3. Data Preparation

### 3.1 Input CSV Validation

**Current CSV Status:**
- File: `effissimo_summary_by_company.csv`
- Location: `/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs/`
- Rows: 30 companies + 1 header
- Validation: ✅ PASSED (with 1 critical issue)

**Critical Issue: Duplicate Ticker**
- Ticker `6676.T` appears twice:
  - Row 23: 株式会社メルコホールディングス (Melco Holdings) - 6 filings
  - Row 27: 株式会社バッファロー (Buffalo Inc.) - 3 filings

**Resolution Required Before Production Run:**

**Option A: Research Correct Ticker**
```bash
# On Bloomberg Terminal, verify each company:
# For Melco Holdings:
6676 JP<EQUITY><GO>

# For Buffalo Inc. (may be different ticker or delisted):
# Check if Buffalo is a subsidiary of Melco
```

**Option B: Temporary Workaround (Remove One Entry)**
```bash
# Create corrected CSV by removing row 27 (Buffalo):
head -n 27 effissimo_summary_by_company.csv > effissimo_corrected.csv
tail -n +29 effissimo_summary_by_company.csv >> effissimo_corrected.csv

# Use corrected CSV for extraction:
# --input effissimo_corrected.csv
```

**Option C: Manual Investigation**
Research relationship between Melco Holdings and Buffalo Inc.:
- Buffalo Inc. was acquired by Melco Holdings in 2011
- They may share the same ticker post-acquisition
- Confirm with Bloomberg Terminal which entity 6676.T represents today

### 3.2 Schema Validation Script

**Run automated validation:**
```bash
python3 << 'EOF'
import pandas as pd

csv_path = "effissimo_summary_by_company.csv"
df = pd.read_csv(csv_path)

print(f"Total rows: {len(df)}")
print(f"Columns: {list(df.columns)}")

# Check for required columns
required = ['target_company', 'target_ticker', 'first_filing', 'last_filing', 'max_ownership_pct']
missing = [col for col in required if col not in df.columns]
if missing:
    print(f"ERROR: Missing columns: {missing}")
else:
    print("✅ All required columns present")

# Check for null values
null_counts = df[required].isnull().sum()
if null_counts.any():
    print(f"WARNING: Null values detected:\n{null_counts[null_counts > 0]}")
else:
    print("✅ No null values in critical fields")

# Check for duplicate tickers
duplicates = df[df.duplicated(subset=['target_ticker'], keep=False)]
if not duplicates.empty:
    print(f"CRITICAL: Duplicate tickers found:\n{duplicates[['target_company', 'target_ticker']]}")
else:
    print("✅ No duplicate tickers")
EOF
```

**Expected Output:**
```
Total rows: 30
Columns: ['target_company', 'target_ticker', 'total_filings', 'first_filing', 'last_filing', 'max_ownership_pct', 'min_ownership_pct']
✅ All required columns present
✅ No null values in critical fields
CRITICAL: Duplicate tickers found:
                      target_company target_ticker
22      株式会社メルコホールディングス        6676.T
26              株式会社バッファロー        6676.T
```

---

## 4. Execution Workflow

### 4.1 Test Run (Single Company)

**Purpose:** Validate end-to-end pipeline before full production run.

**Step 1: Create test input CSV**
```bash
head -n 2 effissimo_summary_by_company.csv > input/test_single_company.csv
# This extracts header + first company (9107.T - Kawasaki Kisen)
```

**Step 2: Execute test extraction**
```bash
python3 src/run_all.py \
    --input input/test_single_company.csv \
    --activist "Effissimo Capital Management" \
    --output output/test_kawasaki_9107T.xlsx \
    --log-level DEBUG
```

**Step 3: Monitor execution**
```bash
# In another terminal window:
tail -f logs/run_all_*.log
```

**Expected Runtime:** 5-10 minutes

**Step 4: Validate test output**
```bash
# Check file was created
ls -lh output/test_kawasaki_9107T.xlsx

# Verify file size (should be 2-5 MB)
# Open Excel file and verify 5 sheets:
# - Snapshot
# - Ownership
# - Events
# - Price History
# - Peer Comps
```

**Success Criteria:**
- Excel file created without errors
- All 5 sheets present
- Snapshot sheet has data in key columns (Market Cap, Revenue, P/E Ratio)
- Ownership sheet has at least 5 holders
- Price History sheet has daily data
- No CRITICAL errors in log file

### 4.2 Production Run (Full Dataset)

**Step 1: Resolve duplicate ticker issue (see Section 3.1)**

**Step 2: Prepare execution environment**
```bash
# Ensure Bloomberg Terminal is running
# Verify blpapi is installed
python3 -c "import blpapi; print('API Ready')"

# Check disk space
df -h .
# Ensure at least 500 MB free
```

**Step 3: Execute full extraction**
```bash
# Navigate to project directory
cd "/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs"

# Activate virtual environment (if using)
source venv/bin/activate

# Run full extraction
python3 src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --output output/effissimo_full_extraction_$(date +%Y%m%d).xlsx \
    --log-level INFO
```

**Step 4: Monitor execution**
```bash
# Real-time log monitoring
tail -f logs/run_all_*.log

# Check progress (in another terminal)
watch -n 30 'ls -lh output/'
```

**Expected Timeline:**
- Company 1-5: 25-50 minutes
- Company 6-15: 50-150 minutes (1.5-2.5 hours total)
- Company 16-25: 50-150 minutes (2.5-4 hours total)
- Company 26-30: 25-50 minutes (3-5 hours total)

**Progress Indicators:**
- Log file shows "Processing company X of 30"
- Each company logs: "Snapshot extraction complete", "Ownership extraction complete", etc.
- Incremental Excel file size growth in output/ directory

### 4.3 Alternative Execution Modes

**Mode 1: Process Companies Individually (safer, easier to debug)**
```bash
# Create 30 separate Excel files (one per company)
# Requires manual loop or script modification
for ticker in 9107.T 7157.T 6707.T; do
    echo "Processing $ticker..."
    # Extract single row from CSV
    head -n 1 effissimo_summary_by_company.csv > input/temp_${ticker}.csv
    grep "$ticker" effissimo_summary_by_company.csv >> input/temp_${ticker}.csv

    # Run extraction
    python3 src/run_all.py \
        --input input/temp_${ticker}.csv \
        --activist "Effissimo Capital Management" \
        --output output/effissimo_${ticker}.xlsx \
        --log-level INFO

    # Clean up
    rm input/temp_${ticker}.csv
done
```

**Mode 2: Dry Run (validate without Bloomberg API calls)**
```bash
python3 src/run_all.py \
    --input effissimo_summary_by_company.csv \
    --activist "Effissimo Capital Management" \
    --output output/dry_run_test.xlsx \
    --dry-run
# NOTE: This requires implementing --dry-run flag in run_all.py
# Currently not implemented - would skip Bloomberg API calls and use mock data
```

---

## 5. Monitoring & Logging

### 5.1 Log File Structure

**Log Location:**
```
logs/run_all_YYYYMMDD_HHMMSS.log
```

**Log Levels:**
- `DEBUG`: Detailed field-level extraction info (verbose)
- `INFO`: High-level progress updates (recommended for production)
- `WARNING`: Non-critical issues (missing fields, partial data)
- `ERROR`: Failures that don't halt execution (single field extraction failed)
- `CRITICAL`: Fatal errors (Bloomberg session failed, file write error)

### 5.2 Real-Time Monitoring

**Terminal 1: Execution**
```bash
python3 src/run_all.py --input effissimo_summary_by_company.csv --output output/effissimo.xlsx --log-level INFO
```

**Terminal 2: Log Monitoring**
```bash
tail -f logs/run_all_*.log | grep -E "(Processing company|extraction complete|ERROR|CRITICAL)"
```

**Terminal 3: Resource Monitoring**
```bash
# Check memory usage
watch -n 10 'ps aux | grep python'

# Check disk usage
watch -n 60 'df -h .'
```

### 5.3 Progress Tracking

**Expected Log Output Pattern (per company):**
```
INFO - Processing company 1 of 30: 9107 JP Equity (Kawasaki Kisen)
INFO - Ticker conversion: 9107.T → 9107 JP Equity
INFO - Fiscal alignment: FYE=March, snapshot_date=2026-03-31
INFO - Snapshot extraction: 60 fields requested
INFO - Snapshot extraction complete: 54/60 fields retrieved (90% complete)
INFO - Ownership extraction: Requesting top 20 holders
INFO - Ownership extraction complete: 18 holders found
INFO - Events extraction: Campaign period 2021-06-14 to 2026-03-06
INFO - Events extraction complete: 12 events found
INFO - Price history extraction: 1227 trading days in campaign period
INFO - Price history extraction complete: 1227 rows
INFO - Peer comps extraction: GICS Sector = Industrials
INFO - Peer comps extraction complete: 15 peers identified
INFO - Data validation: 88% completeness (PASS)
INFO - Company 1 of 30 complete
```

**Key Metrics to Watch:**
- Field completeness percentage (target: ≥70%)
- Number of ownership records (expect 10-20 per company)
- Number of events found (highly variable, 0-50 is normal)
- Price history row count (should match trading days in campaign period)

---

## 6. Validation Procedures

### 6.1 Output File Validation

**Step 1: Verify Excel file creation**
```bash
ls -lh output/effissimo_full_extraction_*.xlsx
# Expected file size: 50-150 MB for 30 companies
```

**Step 2: Check Excel structure**
```bash
python3 << 'EOF'
import pandas as pd
import openpyxl

excel_path = "output/effissimo_full_extraction_20260401.xlsx"
wb = openpyxl.load_workbook(excel_path)

print(f"Sheet names: {wb.sheetnames}")
# Expected: ['Snapshot', 'Ownership', 'Events', 'Price History', 'Peer Comps']

for sheet in wb.sheetnames:
    ws = wb[sheet]
    print(f"{sheet}: {ws.max_row} rows × {ws.max_column} columns")

wb.close()
EOF
```

**Expected Output:**
```
Sheet names: ['Snapshot', 'Ownership', 'Events', 'Price History', 'Peer Comps']
Snapshot: 31 rows × 65 columns
Ownership: 487 rows × 5 columns
Events: 234 rows × 6 columns
Price History: 15432 rows × 7 columns
Peer Comps: 31 rows × 12 columns
```

### 6.2 Data Quality Validation

**Step 1: Review data quality report**
```bash
cat logs/gap_report_*.csv
```

**Step 2: Calculate summary statistics**
```bash
python3 << 'EOF'
import pandas as pd

gap_report = pd.read_csv("logs/gap_report_20260401_143022.csv")

print("Data Quality Summary:")
print(f"Total companies: {len(gap_report)}")
print(f"Average completeness: {gap_report['completeness_pct'].mean():.1f}%")
print(f"Median completeness: {gap_report['completeness_pct'].median():.1f}%")
print(f"Companies with <50% completeness: {(gap_report['completeness_pct'] < 50).sum()}")
print(f"Companies with <70% completeness: {(gap_report['completeness_pct'] < 70).sum()}")

# Flag low-quality extractions
low_quality = gap_report[gap_report['completeness_pct'] < 70]
if not low_quality.empty:
    print("\nCompanies flagged for manual review:")
    print(low_quality[['ticker', 'company_name', 'completeness_pct']])
EOF
```

**Acceptance Criteria:**
- Average completeness: ≥ 70%
- No more than 5 companies with < 50% completeness
- All companies have Market Cap, Ticker, Company Name (critical fields)

### 6.3 Spot Check Validation

**Select 3 representative companies for manual verification:**

**Company 1: Kawasaki Kisen (9107.T) - Highest activity**
```bash
# On Bloomberg Terminal:
9107 JP<EQUITY><GO>
# Verify:
# - Market Cap matches Snapshot sheet
# - Latest price matches Price History sheet
# - Top holders match Ownership sheet
```

**Company 2: Ricoh (7752.T) - Mid-range activity**
```bash
# On Bloomberg Terminal:
7752 JP<EQUITY><GO>
# Verify key financial metrics
```

**Company 3: Naigai (8013.T) - Edge case (1 filing only)**
```bash
# On Bloomberg Terminal:
8013 JP<EQUITY><GO>
# Expected: Minimal data, high chance of missing fields
```

---

## 7. Troubleshooting Guide

### 7.1 Installation Issues

**Problem: "ModuleNotFoundError: No module named 'blpapi'"**

**Diagnosis:**
```bash
python3 -c "import blpapi"
# If this fails, blpapi is not installed
```

**Solution:**
1. Download wheel from Bloomberg Terminal (WAPI<GO>)
2. Install wheel: `pip install /path/to/blpapi-*.whl`
3. Verify: `python3 -c "import blpapi; print(blpapi.__version__)"`

**Problem: "blpapi wheel not compatible with Python 3.13"**

**Solution:**
1. Download latest blpapi wheel from Bloomberg (3.24.10+)
2. OR downgrade Python to 3.11: `conda create -n bloomberg python=3.11`
3. OR use conda: `conda install -c conda-forge blpapi`

### 7.2 Bloomberg Connection Issues

**Problem: "Failed to open session"**

**Diagnosis:**
```bash
# Check if Bloomberg Terminal is running
ps aux | grep Bloomberg
# Expected: Multiple Bloomberg processes running
```

**Solution:**
1. Launch Bloomberg Terminal
2. Log in with credentials
3. Wait 5 minutes for full initialization
4. Test API: `python3 -c "import blpapi; s=blpapi.Session(); print(s.start())"`
5. If still fails, restart Terminal and try again

**Problem: "SecurityError: Invalid security"**

**Diagnosis:**
```bash
# Verify ticker exists on Bloomberg Terminal:
<TICKER> JP<EQUITY><GO>
# Example: 9107 JP<EQUITY><GO>
```

**Solution:**
1. Check if company is delisted (use Bloomberg search: <TICKER><EQUITY><GO>)
2. Verify ticker conversion is correct (.T → JP Equity)
3. For delisted companies, may need historical data access
4. Remove delisted companies from input CSV or flag for manual handling

### 7.3 Extraction Errors

**Problem: "TimeoutError: Request timed out after 60 seconds"**

**Cause:** Bloomberg API overloaded or slow network

**Solution:**
1. Increase timeout in batching_engine.py (line ~85): `timeout=120`
2. Reduce batch size (line ~45): `max_batch_size=20` (from 50)
3. Retry failed company individually
4. Check Bloomberg Terminal connectivity: <HELP><HELP>

**Problem: "Field completeness <30% for multiple companies"**

**Diagnosis:**
```bash
# Review gap report
cat logs/gap_report_*.csv | grep -E "(completeness_pct|[0-2][0-9]\.[0-9])"
```

**Solution:**
1. Check if field names in bloomberg_fields.yaml are correct
2. Verify fields exist on Bloomberg Terminal for these securities
3. Expected for small-cap/illiquid Japanese equities (normal data sparsity)
4. Review which specific fields are missing (may need to remove non-essential fields)

**Problem: "Excel file creation failed: Permission denied"**

**Cause:** Output file is open in Excel or insufficient write permissions

**Solution:**
1. Close Excel if output file is open
2. Check write permissions: `ls -l output/`
3. Try alternative output path: `--output ~/Desktop/effissimo.xlsx`
4. On Windows, check antivirus is not blocking file writes

### 7.4 Data Quality Issues

**Problem: "No ownership records found for any company"**

**Diagnosis:**
```bash
# Check Bloomberg Terminal for holdings data
# Example: 9107 JP<EQUITY><HDS><GO>
```

**Solution:**
1. Verify institutional holdings are available on Bloomberg
2. Some Japanese companies may not report holder data
3. Check if OwnershipExtractor is using correct Bloomberg fields
4. Review logs for ownership extraction errors
5. Expected for small companies with limited institutional ownership

**Problem: "Price history empty for all companies"**

**Diagnosis:**
```bash
# Check if campaign dates are valid
python3 << 'EOF'
import pandas as pd
df = pd.read_csv("effissimo_summary_by_company.csv")
print(df[['target_ticker', 'first_filing', 'last_filing']].head())
EOF
```

**Solution:**
1. Verify first_filing and last_filing dates are correct (YYYY-MM-DD format)
2. Ensure dates are in the past (future dates will return no data)
3. Check Bloomberg Terminal for price data: <TICKER><EQUITY><HP><GO>
4. Review PriceHistoryExtractor logs for API errors

---

## 8. Post-Deployment

### 8.1 Output Archival

**Step 1: Timestamp output file**
```bash
# File is already timestamped if using recommended command:
# output/effissimo_full_extraction_20260401.xlsx
```

**Step 2: Backup to permanent storage**
```bash
# Example: Copy to user's Documents folder
cp output/effissimo_full_extraction_*.xlsx ~/Documents/Effissimo_Bloomberg_Data/

# Or copy to network drive
cp output/effissimo_full_extraction_*.xlsx /Volumes/SharedDrive/Bloomberg/
```

**Step 3: Archive logs**
```bash
# Create archive with output and logs
tar -czf effissimo_extraction_20260401_archive.tar.gz \
    output/effissimo_full_extraction_20260401.xlsx \
    logs/ \
    effissimo_summary_by_company.csv

# Move archive to permanent storage
mv effissimo_extraction_20260401_archive.tar.gz ~/Documents/Effissimo_Bloomberg_Data/
```

### 8.2 Data Review Process

**Step 1: High-level validation**
```bash
# Open Excel file
open output/effissimo_full_extraction_20260401.xlsx

# Quick checks:
# - All 5 sheets present
# - Snapshot sheet has 30 companies
# - No #N/A errors in critical columns (Ticker, Market Cap, Name)
```

**Step 2: Quality report review**
```bash
# Open gap report in Excel or CSV viewer
open logs/gap_report_20260401_*.csv

# Identify companies with <70% completeness
# Flag for manual Bloomberg Terminal lookup
```

**Step 3: Spot check known companies**
- Verify 3-5 companies against Bloomberg Terminal
- Check market cap, revenue, P/E ratio match Terminal values
- Ensure ownership records match <HDS> screen
- Confirm price history aligns with <HP> screen

### 8.3 Next Steps

**For ongoing campaigns (last_filing = 2026-03):**
- Schedule periodic re-extraction (monthly or quarterly)
- Track changes in ownership, valuations, events
- Compare snapshots over time

**For completed campaigns:**
- Archive extraction as final dataset
- No re-extraction needed unless historical corrections are published

**For data gaps:**
- Manually fill missing fields from Bloomberg Terminal
- Document manual corrections in separate "corrections" worksheet
- Save corrected file as "effissimo_full_extraction_YYYYMMDD_CORRECTED.xlsx"

### 8.4 Reporting

**Create Executive Summary (optional):**
```bash
python3 << 'EOF'
import pandas as pd

# Load snapshot data
snapshot = pd.read_excel("output/effissimo_full_extraction_20260401.xlsx", sheet_name="Snapshot")

# Summary statistics
print("Effissimo Portfolio Summary:")
print(f"Total companies: {len(snapshot)}")
print(f"Total market cap: ${snapshot['CUR_MKT_CAP'].sum()/1e9:.1f}B")
print(f"Median P/E ratio: {snapshot['PE_RATIO'].median():.1f}x")
print(f"Median P/B ratio: {snapshot['PX_TO_BOOK_RATIO'].median():.1f}x")
print(f"Average ROE: {snapshot['RETURN_ON_ASSET'].mean():.1f}%")

# Top 5 holdings by market cap
print("\nTop 5 holdings by market cap:")
print(snapshot.nlargest(5, 'CUR_MKT_CAP')[['NAME', 'TICKER', 'CUR_MKT_CAP']])
EOF
```

---

## 9. Production Deployment Checklist

**Pre-Deployment:**
- [ ] Bloomberg Terminal running and logged in
- [ ] Bloomberg Python API (blpapi) installed and verified
- [ ] Core dependencies installed (pandas, openpyxl, pyyaml)
- [ ] Input CSV validated and duplicate ticker issue resolved
- [ ] Output and logs directories created
- [ ] Test extraction completed successfully (single company)
- [ ] Sufficient disk space (500 MB+)

**During Deployment:**
- [ ] Full production run initiated
- [ ] Log monitoring active (tail -f logs/*.log)
- [ ] No CRITICAL errors in logs
- [ ] Progress updates show companies being processed sequentially
- [ ] Excel file size growing incrementally

**Post-Deployment:**
- [ ] Excel file created successfully
- [ ] All 5 sheets present (Snapshot, Ownership, Events, Price History, Peer Comps)
- [ ] Data quality report reviewed (average completeness ≥70%)
- [ ] Spot check validated (3+ companies match Bloomberg Terminal)
- [ ] Output file archived with timestamp
- [ ] Logs archived for future reference

---

**Production Status:** READY (pending Bloomberg API installation and duplicate ticker resolution)

**Estimated Time to First Production Run:** 30-60 minutes after blockers resolved

**Support:** Refer to `PRODUCTION_PREFLIGHT_CHECKLIST.md` for detailed troubleshooting

**Last Updated:** April 1, 2026
