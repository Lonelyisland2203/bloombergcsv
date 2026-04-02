# Issues Backlog

This file tracks resolved issues, postmortems, and workarounds from the Bloomberg pipeline project.

## Active Issues

### BLOCKER-001: Bloomberg Python API Not Installed
**Status:** OPEN - User Action Required
**Severity:** Critical (blocks production execution)
**Detected:** April 1, 2026 (Phase 12 integration testing)
**Type:** Environmental dependency

**Description:**
The Bloomberg Python API (blpapi) package is not installed in the Python environment. This prevents the pipeline from connecting to Bloomberg Terminal and executing real data extractions.

**Evidence:**
```
$ python3 -c "import blpapi"
ModuleNotFoundError: No module named 'blpapi'
```

**Impact:**
- Pipeline cannot execute real data extraction
- All tests run with mocked Bloomberg API responses
- Production deployment blocked

**Resolution Path:**
USER ACTION REQUIRED:
1. Install Bloomberg Python API: `pip install blpapi`
2. Verify Bloomberg Terminal is running
3. Confirm DAPI (Desktop API) is enabled in Terminal settings
4. Test connection: `python src/bloomberg_session.py`

**Notes:**
- This is documented in .claude/rules/stack.md as a core dependency
- All 367 tests pass with mocked API, indicating code readiness
- Only environmental setup remains

---

### BLOCKER-002: Duplicate Ticker 6676.T in Input CSV
**Status:** OPEN - User Clarification Required
**Severity:** High (data quality issue)
**Detected:** April 1, 2026 (Phase 12 CSV validation)
**Type:** Data quality - duplicate ticker

**Description:**
The ticker 6676.T appears twice in effissimo_summary_by_company.csv, mapped to two different companies with non-overlapping campaign periods.

**Evidence:**
```csv
Line 23: 株式会社メルコホールディングス,6676.T,6,2021-11-08,2024-09-20,0.1052,0.0801
Line 27: 株式会社バッファロー,6676.T,3,2025-05-14,2026-03-04,0.1025,0.079
```

**Analysis:**
- Melco Holdings (メルコホールディングス): 6 filings, campaign 2021-2024
- Buffalo (バッファロー): 3 filings, campaign 2025-2026
- No temporal overlap (suggests sequential campaigns or corporate restructuring)

**Possible Explanations:**
1. Corporate restructuring: Buffalo spun off from Melco Holdings
2. Ticker reassignment: TSE reassigned ticker after Melco campaign ended
3. Name variation: Same company with different name representations
4. Data error: One company name or ticker is incorrect

**Impact:**
- Pipeline will extract Bloomberg data for 6676.T twice
- Output Excel files may contain duplicate/conflicting data
- Data analysis may be compromised without clarification

**Resolution Path:**
USER CLARIFICATION REQUIRED:
1. Verify corporate relationship between Melco Holdings and Buffalo
2. Confirm ticker assignments with Bloomberg/TSE records
3. Decide on handling:
   - Option A: Keep both if legitimate separate campaigns
   - Option B: Merge if same campaign with name change
   - Option C: Remove incorrect entry if data error

**Notes:**
- CSV validation report (csv_validation_report.json) did not flag this as duplicate
- Both entries have valid data structure and date ranges
- Requires domain knowledge to resolve correctly

---

## Resolved Issues

(No resolved issues yet - project is in first production deployment phase)
