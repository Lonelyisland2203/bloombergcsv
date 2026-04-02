# Ticker Duplicate Analysis
## Bloomberg API Data Extraction Pipeline - Blocker #2 Investigation

**Analysis Date:** April 1, 2026
**Analyst:** quant-data-engineer (Claude Code)

---

## Issue Summary

The input CSV `effissimo_summary_by_company.csv` contains a duplicate ticker `6676.T` appearing in two different rows:

- **Row 23**: 株式会社メルコホールディングス (Melco Holdings Inc.) - Ticker 6676.T
- **Row 27**: 株式会社バッファロー (Buffalo Inc.) - Ticker 6676.T

This creates a data integrity risk, as the Bloomberg API will interpret both as the same security.

---

## Company Research

### Company 1: 株式会社メルコホールディングス (Melco Holdings Inc.)
- **Japanese Name**: 株式会社メルコホールディングス
- **English Name**: Melco Holdings Inc.
- **Ticker (Claimed)**: 6676.T
- **First Filing**: 2021-11-08
- **Last Filing**: 2024-09-20
- **Total Filings**: 6
- **Max Ownership**: 10.52%
- **Min Ownership**: 8.01%

**Research Notes:**
- Melco Holdings is a Japanese electronics manufacturer
- Known for computer peripherals, storage devices, networking equipment
- Publicly traded on Tokyo Stock Exchange
- Bloomberg ticker: 6676 JP Equity (6676.T in TSE format)

### Company 2: 株式会社バッファロー (Buffalo Inc.)
- **Japanese Name**: 株式会社バッファロー
- **English Name**: Buffalo Inc.
- **Ticker (Claimed)**: 6676.T
- **First Filing**: 2025-05-14
- **Last Filing**: 2026-03-04
- **Total Filings**: 3
- **Max Ownership**: 10.25%
- **Min Ownership**: 7.90%

**Research Notes:**
- Buffalo Inc. is a BRAND NAME owned by Melco Holdings Inc.
- Buffalo is NOT a separate publicly traded company
- Buffalo products are sold under the Melco Holdings corporate umbrella
- This appears to be a data entry error in the original CSV

---

## Root Cause Analysis

**Finding:** Buffalo Inc. (株式会社バッファロー) is NOT a separate publicly traded entity. It is a subsidiary/brand of Melco Holdings Inc. (株式会社メルコホールディングス).

**Implication:** Both rows actually refer to the SAME company (Melco Holdings, ticker 6676.T), but with different filing periods:
- **Period 1 (Row 23)**: 2021-11-08 to 2024-09-20 (6 filings, max 10.52%)
- **Period 2 (Row 27)**: 2025-05-14 to 2026-03-04 (3 filings, max 10.25%)

**Hypothesis:** Effissimo's regulatory filings may have referenced the company using different names in different periods:
- Early filings: "Melco Holdings Inc." (parent company name)
- Later filings: "Buffalo Inc." (brand/subsidiary name)

---

## Recommended Resolution

### Option A: Merge Rows (Preferred)
Combine both rows into a single entry representing the full campaign period:
- **Company Name**: 株式会社メルコホールディングス (Melco Holdings Inc.)
- **Ticker**: 6676.T
- **First Filing**: 2021-11-08 (earliest across both rows)
- **Last Filing**: 2026-03-04 (latest across both rows)
- **Total Filings**: 9 (6 + 3)
- **Max Ownership**: 10.52% (max across both periods)
- **Min Ownership**: 7.90% (min across both periods)

**Rationale:** This represents the complete activist campaign timeline for a single company.

### Option B: Delete Row 27 (Conservative)
Remove the "Buffalo Inc." entry (Row 27) and keep only "Melco Holdings Inc." (Row 23):
- **Reasoning**: The earlier filing period is more complete (6 filings vs 3)
- **Trade-off**: Loses recent filing data from 2025-2026

### Option C: Keep Both, Update Row 27 Ticker (Not Recommended)
Research if Buffalo Inc. was ever separately traded (unlikely):
- If Buffalo had a separate ticker historically, update Row 27
- If not, this is equivalent to deleting Row 27

---

## Decision

**Chosen Resolution:** **Option A - Merge Rows**

This preserves all data and accurately represents Effissimo's full engagement with the company (Melco Holdings / Buffalo brand) from 2021 to 2026.

---

## Implementation Plan

1. Create `effissimo_summary_by_company_corrected.csv` with:
   - Row 23 updated with merged data (earliest to latest filing dates)
   - Row 27 deleted
   - All other rows unchanged

2. Document the correction in `TICKER_CORRECTION_LOG.md`

3. Update all project documentation to reference the corrected CSV

4. Create validation script to check for future duplicate ticker issues

---

## Validation Checklist

- [ ] Corrected CSV has 30 rows (down from 31 due to merge)
- [ ] No duplicate tickers remain
- [ ] Merged row has correct date range (2021-11-08 to 2026-03-04)
- [ ] Total filings sum correctly (6 + 3 = 9)
- [ ] Max/min ownership percentages are accurate
- [ ] All other 29 companies unchanged
