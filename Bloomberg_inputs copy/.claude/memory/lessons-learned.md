# Lessons Learned

## Pattern Template
```
### [CATEGORY] [PATTERN-ID]: [Title]
**Context**: When this pattern applies
**Pattern**: What worked (or didn't work)
**Evidence**: Specific example or outcome
**Recommendation**: How to apply in future
```

---

## Bloomberg API Patterns

(To be populated as implementation progresses)

This section will capture:
- Successful override construction patterns
- Bulk request parsing techniques
- Error handling strategies that worked
- Rate limit management approaches
- Session reconnection patterns

---

## Data Quality Patterns

(To be populated during extraction)

This section will capture:
- Field availability patterns by market segment
- Fiscal period edge cases encountered
- Corporate action deduplication heuristics
- Cross-shareholding identification rules
- Foreign ownership computation fallbacks

---

## Testing Patterns

(To be populated during Phase 12)

This section will capture:
- Effective Bloomberg response mocking strategies
- Integration test setup (Terminal state management)
- Edge case coverage approaches
- Spot-check validation workflows

---

## Anti-Patterns (Things to Avoid)

(To be populated when issues discovered)

This section will capture:
- Mixed override types in single request (known issue)
- Fiscal period hardcoding (breaks for non-March FYE)
- Assuming field availability without validation
- Ignoring Bloomberg error codes
- Over-batching (exceeding rate limits)

---

## Performance Patterns

(To be populated during Phase 14)

This section will capture:
- Optimal batch sizes for different field groups
- Parallel extraction strategies
- Memory optimization techniques
- DataFrame dtype optimization

---

(Lessons will be added throughout implementation as patterns emerge)
