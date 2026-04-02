# Decisions Log

This file contains full decision records with context, alternatives considered, and rationale.

## Decision: Blocker Resolution Process (April 1, 2026)

**Context:**
Phase 12 integration testing revealed two blockers preventing production deployment:
1. Bloomberg Python API (blpapi) not installed
2. Duplicate ticker 6676.T in input CSV

**Decision:**
Document blockers as user-action-required issues rather than attempting automated fixes or workarounds.

**Alternatives Considered:**

1. **Auto-install blpapi**
   - Rejected: Bloomberg API requires specific licensing and Bloomberg Terminal installation
   - Not appropriate for automated dependency resolution
   - User must have Bloomberg Terminal subscription and access

2. **Auto-deduplicate CSV entries**
   - Rejected: Requires domain knowledge to determine correct resolution
   - Could delete legitimate campaign data
   - Risk of data loss without user confirmation

3. **Create duplicate ticker workaround**
   - Rejected: Would mask underlying data quality issue
   - Could produce incorrect analysis results
   - Better to resolve data issue at source

**Rationale:**
Both blockers require user domain knowledge or environmental access:
- blpapi installation requires Bloomberg Terminal access and subscription
- Duplicate ticker resolution requires understanding of corporate restructuring or data provenance

Documenting as user-action-required ensures:
- User maintains control over critical dependencies
- Data quality issues are resolved correctly
- No automated changes to user data without explicit approval

**Implementation:**
1. Created issues-backlog.md with detailed blocker documentation
2. Updated CLAUDE.md Active Issues section with blocker status
3. Project status remains "BLOCKERS IDENTIFIED" until user resolves both issues
4. Clear resolution paths provided for each blocker

**Success Criteria:**
- User installs blpapi and confirms Bloomberg Terminal connection
- User clarifies/resolves duplicate ticker 6676.T
- Pipeline successfully executes single-company test extraction
- Project status updates to "BLOCKERS RESOLVED" → "READY FOR DEPLOYMENT"

---

## Decision: Phase 12 Integration Testing Approach (April 1, 2026)

**Context:**
All 367 tests passing with mocked Bloomberg API. Ready to test with real Bloomberg Terminal.

**Decision:**
Conduct systematic pre-production validation before full 30-company run:
1. Validate input CSV structure and data quality
2. Verify environmental dependencies (blpapi, Terminal)
3. Execute single-company test extraction
4. Compare real vs. mocked API responses
5. Address any discrepancies before full production run

**Alternatives Considered:**

1. **Skip validation, run full production immediately**
   - Rejected: High risk of failures mid-execution
   - Could waste hours of Bloomberg API quota
   - Difficult to debug issues across 30 companies

2. **Manual spot-checking without systematic validation**
   - Rejected: May miss systematic issues
   - Inconsistent validation approach
   - No documented validation process

**Rationale:**
Systematic validation reduces risk:
- Catches environmental issues before large-scale execution
- Validates data quality assumptions
- Documents any discrepancies between mocked and real API behavior
- Single-company test limits API quota usage during validation

**Implementation:**
Phases 12-14 roadmap:
- Phase 12: Final integration testing (current)
- Phase 13: Production deployment preparation
- Phase 14: User handoff and support setup

**Success Criteria:**
- CSV validation passes all checks
- Bloomberg API connection successful
- Single-company extraction produces valid Excel output
- Data quality meets 70% completeness threshold
- No major discrepancies vs. test expectations
