# Decisions Log

## Decision Template
```
### [DATE] [DECISION-ID]: [Title]
**Context**: Why this decision was needed
**Options Considered**:
1. Option A: Description, pros/cons
2. Option B: Description, pros/cons
**Decision**: Chosen option with rationale
**Impact**: What this affects (modules, timeline, dependencies)
**Reversibility**: Can this be changed later? Cost?
```

---

## 2026-04-01-D001: Three-Tiered Memory Architecture

**Context**: Need to track project state across 14 implementation phases and multiple specialized agents while keeping CLAUDE.md under 200 lines for optimal context budget.

**Options Considered**:
1. Single CLAUDE.md with all information: Simple but would exceed 200 lines quickly
2. Two-tier (CLAUDE.md + archive): Loses stable knowledge structure
3. Three-tier (hot/stable/cold): Optimal context budget usage

**Decision**: Implement three-tiered memory architecture:
- Tier 1 (CLAUDE.md): Current state, active issues, latest session (hot, <200 lines)
- Tier 2 (.claude/rules/): Stable knowledge (stack, architecture, standards, field specs)
- Tier 3 (.claude/memory/): Detailed history (decisions, sessions, issues, lessons)

**Impact**:
- CLAUDE.md stays lean and focused on current work
- Stable knowledge in rules files loaded at startup, not repeated in every prompt
- Full audit trail preserved in memory files for reference
- Agent handoffs simplified (read CLAUDE.md + relevant rules file)

**Reversibility**: Low cost to restructure, but benefits clear from start.

---

## 2026-04-01-D002: Modular Extraction Architecture

**Context**: 58 Bloomberg fields span multiple categories (financials, ownership, events, prices, peer comps). Need clear module boundaries for parallel development and testing.

**Options Considered**:
1. Monolithic extractor: Single module handles all fields (simpler but harder to test/maintain)
2. Field-type separation: 5 specialized extractors (snapshot, ownership, events, prices, peer comps)
3. Request-type separation: Group by Bloomberg API request type only

**Decision**: Modular extraction with 5 specialized extractors, each responsible for logically related fields and output to specific Excel sheet.

**Impact**:
- Parallel development possible (different agents can work on different extractors)
- Testing simplified (mock Bloomberg responses per extractor)
- Clearer error handling (failure in ownership doesn't crash snapshot)
- Agent specialization matches data domains

**Reversibility**: Medium cost (would require refactoring), but modularity benefits are substantial.

---

## 2026-04-01-D003: Field-Group-Aware Batching

**Context**: Bloomberg API silently fails or returns incorrect data when mixing override types (FUND_PER, END_DT_OVERRIDE) in single request.

**Options Considered**:
1. Single batch per security: Inefficient, 3x request volume
2. Mixed overrides: Risk silent failures and incorrect data
3. Separate batches by override type: Correct data, moderate request volume

**Decision**: Implement batching_engine.py that separates fields by override type before creating batches. Never mix FUND_PER and END_DT_OVERRIDE in same request.

**Impact**:
- Guarantees data correctness (no silent override conflicts)
- Moderate request volume (3 batches instead of 1, but 20 securities per batch)
- Slightly more complex batching logic, but critical for reliability

**Reversibility**: Low cost to change batching strategy, but override separation is non-negotiable for correctness.

---

## 2026-04-01-D004: Output Format — 5 Sheets (Not 6)

**Context**: Initial plan included Sheet 6 for metadata and data quality metrics. User requested consolidation.

**Options Considered**:
1. 6-sheet workbook: Separate metadata sheet (more organized but adds sheet)
2. 5-sheet workbook: Merge metadata into existing sheet (simpler navigation)
3. 5-sheet + separate report file: Metadata in JSON/CSV (fragmented output)

**Decision**: Use 5-sheet Excel layout. Merge metadata summary into Sheet 5 (Peer Comps) footer or Sheet 1 (Snapshot) header section.

**Impact**:
- Simplified output structure (easier for end users to navigate)
- Metadata section becomes header/footer in existing sheets
- Update architecture.md and excel_writer.py specification
- No impact on extraction logic (only affects Excel formatting)

**Reversibility**: Low cost. Easy to split metadata to separate sheet if user requests.

---

## 2026-04-01-D005: Peer Comp Definition — GICS Sectors

**Context**: Need clear peer group definition for sector median calculations. Custom peer lists add complexity.

**Options Considered**:
1. Custom peer lists: User defines peers per company (flexible but requires input data)
2. GICS sectors: Standard classification (consistent, no additional input needed)
3. TSE industry codes: Japan-specific (might miss cross-listed comps)

**Decision**: Use GICS_SECTOR_NAME from Bloomberg for peer grouping. Query sector for each target company, then pull sector medians for same fields.

**Impact**:
- Standardized peer definition (no custom peer list input required)
- Peer comps extractor queries GICS_SECTOR_NAME, groups by sector
- All companies in same GICS sector treated as peers
- Simpler implementation (no peer list validation logic)

**Reversibility**: Medium cost. Could add custom peer list support later if needed.

---

## 2026-04-01-D006: Corporate Actions Historical Depth — Campaign Period Only

**Context**: Bloomberg corporate action history can span decades. Need to define extraction scope.

**Options Considered**:
1. Full history: All events in Bloomberg (comprehensive but noisy)
2. Campaign period: first_filing to last_filing dates (focused on activist impact)
3. Fixed window: Last 5 years (arbitrary, might miss early campaign events)

**Decision**: Extract corporate actions only during campaign period (first_filing to last_filing dates from CSV).

**Impact**:
- Focused dataset showing activist-catalyzed events
- Reduced data volume (no pre-campaign history)
- Events extractor filters by date range
- Clearer cause-effect analysis for activist impact

**Reversibility**: Easy. Date filtering is parameter-based.

---

## 2026-04-01-D007: Execution Frequency — One-Time Extraction

**Context**: Need to determine if pipeline supports incremental updates or one-time batch extraction.

**Options Considered**:
1. One-time extraction: Run once, generate report (simpler)
2. Recurring extraction: Monthly refreshes with incremental updates (complex checkpoint logic)
3. Hybrid: One-time with optional refresh mode (adds flexibility but complexity)

**Decision**: One-time extraction. No incremental update logic needed.

**Impact**:
- Simpler orchestration layer (no checkpoint/resume system required)
- Full re-extraction on each run (acceptable for 30 companies)
- Can add incremental mode later if recurring need emerges
- Checkpoint system becomes nice-to-have, not critical

**Reversibility**: Medium cost. Adding incremental logic later requires checkpoint architecture.

---

## 2026-04-01-D008: Multi-Activist Workflow — Single Activist Processing

**Context**: Need to define CLI interface for processing one vs. multiple activists.

**Options Considered**:
1. Single activist mode: CLI accepts one CSV path (simple)
2. Batch mode: Process multiple activist CSVs in one run (complex orchestration)
3. Config-driven: YAML with list of activists (adds configuration layer)

**Decision**: Process each activist individually. CLI accepts single CSV path. Target: Effissimo Capital Management only.

**Impact**:
- run_all.py CLI: Single CSV input, single Excel output
- No batch orchestration logic needed
- User runs pipeline separately for each activist (if expanding scope)
- Simpler error handling and logging

**Reversibility**: Low cost. Batch mode can wrap single-activist runs later.

---

## 2026-04-01-D009: Target Company Count Correction — 30 Companies

**Context**: Initial documentation stated 31 companies based on preliminary count. CSV validation confirmed 30 valid rows.

**Options Considered**:
N/A (data correction, not decision)

**Decision**: Correct target count to 30 companies across all documentation.

**Impact**:
- Update CLAUDE.md, success metrics, timeline estimates
- Affects batch sizing calculations (30 companies = 2 batches of 20+10)
- No impact on extraction logic (count is dynamic from CSV)

**Reversibility**: N/A (factual correction)

---

## 2026-04-01-D010: Phase Transition to Final Validation and Production Deployment

**Context**: All 11 development phases complete (367 tests passing, 100% pass rate). User opened effissimo_summary_by_company.csv in IDE, signaling readiness to proceed to final testing. Need to transition from development/testing to real-world validation and production deployment.

**Options Considered**:
1. Immediate full production run: Skip validation, process all 30 companies (risky, no real-data validation)
2. Single-company test first: Validate one company with real Bloomberg API before full run (safer)
3. Phased rollout: Test 1 company, then 5, then all 30 (most conservative, time-consuming)

**Decision**: Enter Phase 12 (Final End-to-End Integration Testing) with single-company validation before full production run. Structure remaining work as Phases 12-14:
- Phase 12: Final integration testing with real Effissimo data (validate CSV, test single company)
- Phase 13: Production deployment preparation (full 30-company run, quality review)
- Phase 14: User handoff and support setup (documentation review, ongoing support protocol)

**Impact**:
- CLAUDE.md status updated from "PRODUCTION READY" to "FINAL VALIDATION PHASE"
- Pre-production validation checklist created (CSV validation, blpapi check, real data testing)
- Reduces risk of batch failures due to real-world data edge cases
- User can identify and address issues before committing to 2.5-5 hour full run

**Reversibility**: Low cost. Can skip single-company test if user prefers immediate full run, but validation step is best practice.

---

(Future decisions will be appended here chronologically)
