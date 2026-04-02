# Phase 1 Quick Reference Guide
**Core Utilities: Ticker Conversion & Fiscal Alignment**

---

## Module Imports

```python
# Ticker conversion
from src.ticker_converter import (
    convert_ticker,              # TSE → Bloomberg conversion
    validate_tse_ticker,         # Format validation
    extract_tse_code,            # Extract base code
    convert_bloomberg_to_tse,    # Reverse conversion
)

# Fiscal alignment
from src.fiscal_period_aligner import (
    compute_snapshot_date,        # Compute FY-end date
    construct_fund_per_override,  # Generate FUND_PER string
    get_fiscal_year_range,        # Get FY start/end dates
    compute_campaign_fiscal_alignment,  # All-in-one function
)
```

---

## Quick Examples

### Ticker Conversion

```python
# Convert TSE ticker to Bloomberg format
bloomberg = convert_ticker("9107.T")
# Returns: "9107 JP Equity"

# Validate ticker format
is_valid = validate_tse_ticker("9107.T")
# Returns: True

# Extract base code
code = extract_tse_code("9107.T")
# Returns: "9107"

# Reverse conversion
tse = convert_bloomberg_to_tse("9107 JP Equity")
# Returns: "9107.T"
```

### Fiscal Period Alignment

```python
from datetime import date

campaign_start = date(2021, 6, 14)  # Kawasaki Kisen campaign
fye_month = 3  # March 31 FYE

# Compute snapshot date (most recent FYE before campaign)
snapshot = compute_snapshot_date(campaign_start, fye_month)
# Returns: date(2021, 3, 31)

# Generate Bloomberg FUND_PER override
fund_per = construct_fund_per_override(snapshot)
# Returns: "FY2021"

# Get fiscal year range
fy_start, fy_end = get_fiscal_year_range(snapshot)
# Returns: (date(2020, 4, 1), date(2021, 3, 31))

# All-in-one function
snapshot, fund_per, (fy_start, fy_end) = compute_campaign_fiscal_alignment(
    campaign_start, fye_month
)
# Returns: (date(2021, 3, 31), "FY2021", (date(2020, 4, 1), date(2021, 3, 31)))
```

---

## 60-Day Buffer Examples

### Campaign Within 60-Day Buffer (Use Prior Year FYE)

```python
from datetime import date

# Campaign starts April 6, 2021 (6 days after March 31 FYE)
campaign_start = date(2021, 4, 6)
fye_month = 3

snapshot = compute_snapshot_date(campaign_start, fye_month)
# Returns: date(2020, 3, 31)  ← Prior year FYE (financials not yet filed)

fund_per = construct_fund_per_override(snapshot)
# Returns: "FY2020"
```

### Campaign After 60-Day Buffer (Use Current Year FYE)

```python
from datetime import date

# Campaign starts June 14, 2021 (75 days after March 31 FYE)
campaign_start = date(2021, 6, 14)
fye_month = 3

snapshot = compute_snapshot_date(campaign_start, fye_month)
# Returns: date(2021, 3, 31)  ← Current year FYE (buffer expired)

fund_per = construct_fund_per_override(snapshot)
# Returns: "FY2021"
```

---

## Error Handling

### Ticker Conversion Errors

```python
# Invalid format → ValueError with helpful message
try:
    convert_ticker("107.T")  # Only 3 digits
except ValueError as e:
    print(e)
# Output: Invalid TSE ticker format: '107.T'.
#         TSE code must be exactly 4 digits, got 3 digits.
#         Expected format: NNNN.T or NNNNJ.T

# Missing .T suffix
try:
    convert_ticker("9107")
except ValueError as e:
    print(e)
# Output: Invalid TSE ticker format: '9107'.
#         Expected format: NNNN.T or NNNNJ.T (must end with '.T')
```

### Fiscal Alignment Errors

```python
from datetime import date

# Invalid FYE month
try:
    compute_snapshot_date(date(2021, 6, 14), 13)  # Month 13 doesn't exist
except ValueError as e:
    print(e)
# Output: fye_month must be between 1 (January) and 12 (December), got 13

# Invalid date type
try:
    compute_snapshot_date("2021-06-14", 3)  # String instead of date
except TypeError as e:
    print(e)
# Output: campaign_start_date must be a datetime.date object, got str
```

---

## Batch Processing Example

```python
import pandas as pd
from datetime import date
from src.ticker_converter import convert_ticker
from src.fiscal_period_aligner import compute_campaign_fiscal_alignment

# Load campaign data
df = pd.read_csv("effissimo_summary_by_company.csv")
df['first_filing'] = pd.to_datetime(df['first_filing']).dt.date

# Process all campaigns
results = []
for idx, row in df.iterrows():
    tse_ticker = row['target_ticker']
    campaign_start = row['first_filing']
    fye_month = 3  # Assume March 31 FYE (fetch from Bloomberg in Phase 2)

    # Convert ticker
    bloomberg_ticker = convert_ticker(tse_ticker)

    # Compute fiscal alignment
    snapshot, fund_per, (fy_start, fy_end) = compute_campaign_fiscal_alignment(
        campaign_start, fye_month
    )

    results.append({
        'company': row['target_company'],
        'tse_ticker': tse_ticker,
        'bloomberg_ticker': bloomberg_ticker,
        'campaign_start': campaign_start,
        'snapshot_date': snapshot,
        'fund_per': fund_per,
        'fy_start': fy_start,
        'fy_end': fy_end,
    })

# Create results DataFrame
results_df = pd.DataFrame(results)
print(results_df.head())
```

---

## Testing

### Run All Tests

```bash
# Run all Phase 1 tests
pytest tests/ -v

# Run specific test module
pytest tests/test_ticker_converter.py -v
pytest tests/test_fiscal_alignment.py -v
pytest tests/test_integration_phase1.py -v

# Run with coverage report
pytest tests/ --cov=src --cov-report=term-missing
```

### Run Type Checking

```bash
# Check ticker converter
mypy src/ticker_converter.py --strict

# Check fiscal aligner
mypy src/fiscal_period_aligner.py --strict

# Check all source files
mypy src/ --strict
```

---

## Point-in-Time Safety Checklist

When using fiscal alignment functions, verify:

- [ ] `snapshot_date < campaign_start_date` (no future data)
- [ ] 60-day buffer applied correctly (check campaign dates in April-May for March FYE)
- [ ] FYE month is correct for target company
- [ ] Leap year handling (if Feb 29 FYE)
- [ ] Year boundary cases (campaigns in January with December FYE)

**Verification Example**:
```python
from datetime import date
from src.fiscal_period_aligner import compute_snapshot_date

campaign_start = date(2021, 4, 6)
snapshot = compute_snapshot_date(campaign_start, 3)

# Verify point-in-time safety
assert snapshot < campaign_start, "TEMPORAL VIOLATION: Snapshot is in the future"

# Verify 60-day buffer for April campaigns
days_after_fye = (campaign_start - date(2021, 3, 31)).days
if days_after_fye <= 60:
    assert snapshot.year < campaign_start.year, "Buffer not applied"
```

---

## Common Pitfalls to Avoid

### 1. Using Wrong Date Type

```python
# WRONG: Passing string instead of date
compute_snapshot_date("2021-06-14", 3)  # TypeError

# CORRECT: Use datetime.date object
from datetime import date
compute_snapshot_date(date(2021, 6, 14), 3)  # OK
```

### 2. Forgetting 60-Day Buffer

```python
# WRONG: Assuming FYE is always current year if campaign after FYE
# Campaign on April 6, 2021 (6 days after March 31)
snapshot = compute_snapshot_date(date(2021, 4, 6), 3)
# Returns: 2020-03-31 (NOT 2021-03-31 due to buffer)

# CORRECT: Always use compute_snapshot_date(), don't compute manually
```

### 3. Using Calendar Year Instead of Fiscal Year

```python
# WRONG: Assuming fiscal year = calendar year
campaign_year = date(2021, 6, 14).year  # 2021
fye = date(campaign_year, 3, 31)  # 2021-03-31 (may be wrong)

# CORRECT: Use compute_snapshot_date() which handles fiscal year logic
snapshot = compute_snapshot_date(date(2021, 6, 14), 3)
```

### 4. Not Validating Ticker Format Before Conversion

```python
# WRONG: Assuming all tickers are valid
bloomberg = convert_ticker(user_input)  # May raise ValueError

# CORRECT: Validate first
if validate_tse_ticker(user_input):
    bloomberg = convert_ticker(user_input)
else:
    print(f"Invalid ticker format: {user_input}")
```

---

## Integration with Phase 2

Phase 2 (Bloomberg Session Manager) will use these modules as follows:

```python
# Example Bloomberg request building (Phase 2 pseudocode)
from src.ticker_converter import convert_ticker
from src.fiscal_period_aligner import compute_campaign_fiscal_alignment

# User input
tse_ticker = "9107.T"
campaign_start = date(2021, 6, 14)
fye_month = 3  # Will be fetched from Bloomberg API in Phase 2

# Phase 1 utilities
bloomberg_ticker = convert_ticker(tse_ticker)
snapshot, fund_per, _ = compute_campaign_fiscal_alignment(campaign_start, fye_month)

# Bloomberg API request (Phase 2)
session.send_reference_request(
    securities=[bloomberg_ticker],  # "9107 JP Equity"
    fields=["CURR_MKT_CAP", "PX_TO_BOOK_RATIO", "ROE_1YR_AVG"],
    overrides={"FUND_PER": fund_per}  # "FY2021"
)
```

---

## File Locations

### Production Code
- `/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs/src/ticker_converter.py`
- `/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs/src/fiscal_period_aligner.py`

### Test Code
- `/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs/tests/test_ticker_converter.py`
- `/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs/tests/test_fiscal_alignment.py`
- `/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs/tests/test_integration_phase1.py`

### Documentation
- `/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs/PHASE_1_COMPLETION_REPORT.md`
- `/Users/javierlee/Activism Playbook Raw Inputs/raw_inputs/Bloomberg_inputs/PHASE_1_QUICK_REFERENCE.md` (this file)

---

## Support & Resources

**Test Execution**: `pytest tests/ -v`
**Type Checking**: `mypy src/ --strict`
**Code Coverage**: `pytest tests/ --cov=src --cov-report=html`

**Questions?** Refer to:
1. Function docstrings (Google-style, with examples)
2. Test files (comprehensive usage examples)
3. PHASE_1_COMPLETION_REPORT.md (detailed specification)

---
