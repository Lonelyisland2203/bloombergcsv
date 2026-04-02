# Issues Backlog

## Active Issues
(Issues currently blocking or requiring attention - duplicated in CLAUDE.md)

None currently.

---

## Resolved Issues
(Issues that have been resolved, with resolution notes)

None yet.

---

## Known Limitations
(Documented constraints that won't be fixed, with workarounds)

### L001: Bloomberg Terminal Required
**Description**: Pipeline cannot run without active Bloomberg subscription and Desktop Terminal.
**Impact**: No offline testing, deployment limited to Bloomberg-enabled environments.
**Workaround**: Document clearly in README. Integration tests require Terminal. Unit tests mock Bloomberg responses.
**Future Enhancement**: Consider Bloomberg Cloud API support for non-Terminal environments (separate project).

### L002: Japanese Market Data Gaps
**Description**: Some fields have limited coverage for Standard/Growth market segments:
- EQY_FOREIGN_OWNERSHIP_PCT: Often unavailable outside Prime Market
- PCT_INDEPENDENT_DIRECTORS: Limited governance data for smaller companies
**Impact**: <100% field coverage even with correct Bloomberg queries.
**Workaround**:
- Fallback: Compute foreign ownership from TOP_20_HOLDERS by identifying foreign institutions
- Mark governance fields as optional
- Log gaps in data quality report
**Acceptance Criteria**: >90% overall coverage, 100% for critical fields (PBR, ROE, Market Cap, Net Debt)

### L003: Fiscal Period Alignment Complexity
**Description**: Japanese companies use varied fiscal year-ends (70% March 31, ~10% December 31, others scattered). Off-by-one errors in fiscal period construction can silently return wrong year's data.
**Impact**: Risk of incorrect financial data if fiscal period override is wrong.
**Mitigation**:
- Two-stage validation: Query FISCAL_YEAR_END_MONTH_DE upfront, compute snapshot dates dynamically
- Comprehensive unit tests for edge cases (non-March FYE, entry date near FYE)
- Spot-check validation against Bloomberg Terminal for 10 random securities
**Acceptance Criteria**: 100% fiscal period accuracy on spot-check

### L004: Corporate Actions Deduplication
**Description**: Bloomberg sometimes returns duplicate announcements (same event, multiple filings).
**Impact**: Over-counting of dividends, buybacks in corporate actions sheet.
**Mitigation**: Deduplication logic in extract_events.py (group by event date + type, keep first occurrence). Log duplicates for audit trail.
**Acceptance Criteria**: No duplicate events in final Excel output.

---

## Resolved Questions
(Questions that have been answered with user decisions)

### Q001: Output Format Preference — RESOLVED 2026-04-01
**Question**: 6-sheet vs 5-sheet Excel workbook?
**Decision**: 5-sheet layout (remove "Sheet 6: Metadata & Data Quality")
**Action Taken**: Metadata merged into Sheet 5 or Sheet 1 header. Updated architecture.md.
**Decision ID**: D004

### Q002: Peer Comp Definition — RESOLVED 2026-04-01
**Question**: Should peer comps use GICS sectors or custom peer groups?
**Decision**: Use standard GICS_SECTOR_NAME classification from Bloomberg
**Action Taken**: Peer group = all companies in same GICS sector. Updated bloomberg-field-spec.md.
**Decision ID**: D005

### Q003: Corporate Actions Historical Depth — RESOLVED 2026-04-01
**Question**: Pull entire Bloomberg history or only campaign period?
**Decision**: Campaign period only (first_filing to last_filing)
**Action Taken**: Events extractor filters by date range. Updated bloomberg-field-spec.md.
**Decision ID**: D006

### Q004: Execution Frequency — RESOLVED 2026-04-01
**Question**: One-time extraction or recurring with incremental updates?
**Decision**: One-time extraction (no incremental update logic needed)
**Action Taken**: Checkpoint system optional, not critical. Simplified orchestration scope.
**Decision ID**: D007

### Q005: Multi-Activist Workflow — RESOLVED 2026-04-01
**Question**: Support batch processing of multiple activists in one run?
**Decision**: Process each activist individually (CLI accepts single CSV path)
**Action Taken**: Target = Effissimo only. No batch mode in run_all.py.
**Decision ID**: D008

### DATA CORRECTION: Target Company Count — RESOLVED 2026-04-01
**Issue**: Documentation stated 31 companies, CSV validation confirmed 30
**Decision**: Correct to 30 companies across all documentation
**Action Taken**: Updated CLAUDE.md, all metrics, timeline estimates.
**Decision ID**: D009

---

(Future resolved questions will be moved here from Active Issues in CLAUDE.md)
