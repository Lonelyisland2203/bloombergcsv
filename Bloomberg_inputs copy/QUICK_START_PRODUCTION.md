# Quick Start - Production Deployment
## Get Your First Extraction Running in Under 1 Hour

**Last Updated:** April 1, 2026
**Target:** 30 Effissimo companies
**Estimated Time:** 30-60 min setup + 2.5-5 hours extraction

---

## Step 1: Install Bloomberg Python API (15-30 min)

**On Bloomberg Terminal:**
```
WAPI<GO>
→ Downloads
→ Python API
→ Download wheel file for macOS ARM Python 3.13
```

**In Terminal:**
```bash
cd "/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs"

# Install downloaded wheel
pip install ~/Downloads/blpapi-3.24.10-cp313-cp313-macosx_14_0_arm64.whl

# Verify
python3 -c "import blpapi; print(f'Bloomberg API v{blpapi.__version__} ready')"
```

**Expected Output:**
```
Bloomberg API v3.24.10 ready
```

**If you see this, proceed to Step 2.**

---

## Step 2: Fix Duplicate Ticker (5-15 min)

**Problem:** Ticker `6676.T` appears twice in CSV (rows 23 and 27)

**Quick Fix (Remove Row 27):**
```bash
head -n 27 effissimo_summary_by_company.csv > effissimo_corrected.csv
tail -n +29 effissimo_summary_by_company.csv >> effissimo_corrected.csv

# Verify (should show 30 lines: header + 29 companies)
wc -l effissimo_corrected.csv
```

**If you want to verify on Bloomberg first:**
```
6676 JP<EQUITY><GO>
# Check if this is Melco or Buffalo
```

---

## Step 3: Test Run - Single Company (5-10 min)

**Create test input:**
```bash
mkdir -p input output logs
head -n 2 effissimo_summary_by_company.csv > input/test_single.csv
```

**Ensure Bloomberg Terminal is running and logged in.**

**Run test:**
```bash
python3 src/run_all.py \
    --input input/test_single.csv \
    --activist "Effissimo Capital Management" \
    --output output/test_kawasaki_9107T.xlsx \
    --log-level INFO
```

**Wait 5-10 minutes.**

**Verify output:**
```bash
ls -lh output/test_kawasaki_9107T.xlsx
# Should be 2-5 MB

# Open in Excel and check 5 sheets are present:
open output/test_kawasaki_9107T.xlsx
```

**Expected sheets:**
1. Snapshot (60+ columns)
2. Ownership (Top 20 holders)
3. Events (corporate actions)
4. Price History (daily OHLCV)
5. Peer Comps (sector benchmarks)

**If test succeeds, proceed to Step 4.**

---

## Step 4: Production Run - 30 Companies (2.5-5 hours)

**Ensure:**
- [ ] Bloomberg Terminal is running
- [ ] Test extraction succeeded
- [ ] Have 2-5 hours available (or run overnight)

**Run production extraction:**
```bash
python3 src/run_all.py \
    --input effissimo_corrected.csv \
    --activist "Effissimo Capital Management" \
    --output output/effissimo_full_extraction_$(date +%Y%m%d).xlsx \
    --log-level INFO
```

**Monitor progress (in another terminal):**
```bash
tail -f logs/run_all_*.log
```

**Expected log output:**
```
INFO - Processing company 1 of 30: 9107 JP Equity
INFO - Snapshot extraction complete: 54/60 fields (90%)
INFO - Ownership extraction complete: 18 holders
INFO - Events extraction complete: 12 events
INFO - Price history extraction complete: 1227 rows
INFO - Peer comps extraction complete: 15 peers
INFO - Company 1 of 30 complete

INFO - Processing company 2 of 30: 7157 JP Equity
...
```

**Wait 2.5-5 hours for completion.**

---

## Step 5: Validate Output (10-20 min)

**Check file created:**
```bash
ls -lh output/effissimo_full_extraction_*.xlsx
# Should be 50-150 MB
```

**Open Excel:**
```bash
open output/effissimo_full_extraction_*.xlsx
```

**Quick checks:**
- [ ] All 5 sheets present
- [ ] Snapshot sheet has 29 rows (header + 29 companies, if one removed)
- [ ] No #N/A errors in critical columns (Ticker, Market Cap, Name)

**Review data quality:**
```bash
open logs/gap_report_*.csv
```

**Check:**
- [ ] Average completeness ≥70%
- [ ] No more than 5 companies with <50% completeness

**Spot-check 3 companies on Bloomberg Terminal:**
```
9107 JP<EQUITY><GO>  # Verify market cap, P/E match
7752 JP<EQUITY><GO>  # Check financials
8013 JP<EQUITY><GO>  # Review ownership
```

**If all checks pass, you're done!**

---

## Troubleshooting

### "ModuleNotFoundError: No module named 'blpapi'"
→ Go back to Step 1, install Bloomberg API

### "Failed to open session"
→ Bloomberg Terminal not running or not fully initialized
→ Launch Terminal, wait 5 minutes, retry

### "SecurityError: Invalid security"
→ Ticker may be delisted or incorrect
→ Verify on Terminal: `<TICKER> JP<EQUITY><GO>`

### "TimeoutError: Request timed out"
→ Bloomberg API overloaded
→ Wait 5 minutes and retry

### Excel file is small (<10 MB for 30 companies)
→ Check logs for errors
→ Review gap_report.csv for missing data
→ May indicate Bloomberg API issues

---

## Expected Results

**Runtime:**
- Test (1 company): 5-10 minutes
- Production (30 companies): 2.5-5 hours

**Output File:**
- Size: 50-150 MB
- Sheets: 5 (Snapshot, Ownership, Events, Price History, Peer Comps)

**Data Quality:**
- Average completeness: 70-85%
- Some companies may have gaps (expected for small-caps)
- Critical fields (Market Cap, Ticker, Name) should be 100%

---

## Need More Help?

**Comprehensive Guides:**
- `FINAL_HANDOFF.md` - Complete user handoff (600+ lines)
- `DEPLOYMENT_RUNBOOK.md` - Step-by-step deployment (700+ lines)
- `PRODUCTION_PREFLIGHT_CHECKLIST.md` - Pre-deployment validation (500+ lines)

**Troubleshooting:**
- `DEPLOYMENT_RUNBOOK.md` Section 7 - 30+ common issues with solutions

**Bloomberg Support:**
- Terminal: `<HELP><HELP>` (chat with support)
- API Docs: `WAPI<GO>` on Terminal

**Test Suite (Verify System):**
```bash
pytest -v  # Should show 367 tests passing
```

---

## Quick Command Reference

**Check Python:**
```bash
python3 --version  # Should be 3.8+
```

**Check Bloomberg API:**
```bash
python3 -c "import blpapi; print(blpapi.__version__)"
```

**Check Dependencies:**
```bash
python3 -c "import pandas; import openpyxl; import yaml; print('OK')"
```

**Create Directories:**
```bash
mkdir -p input output logs
```

**View Logs:**
```bash
tail -f logs/run_all_*.log
```

**Check Disk Space:**
```bash
df -h .
```

---

**You have everything you need. Good luck with your extraction!**

---

**Last Updated:** April 1, 2026
**Status:** Ready for production deployment
