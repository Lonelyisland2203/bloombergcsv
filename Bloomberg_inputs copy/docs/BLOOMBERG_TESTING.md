# Bloomberg Session Manager - Testing Guide

This guide explains how to test the Bloomberg Session Manager both with and without access to a live Bloomberg Terminal.

## Overview

The Bloomberg Session Manager has two testing strategies:

1. **Unit Tests** (Automated): Use mocked Bloomberg API responses, no Terminal required
2. **Integration Tests** (Manual): Require live Bloomberg Terminal connection

## Unit Tests (No Bloomberg Terminal Required)

### Running Unit Tests

```bash
# Run all Bloomberg session tests
pytest tests/test_bloomberg_session.py -v

# Run with coverage report
pytest tests/test_bloomberg_session.py --cov=src.bloomberg_session --cov-report=html

# Run specific test class
pytest tests/test_bloomberg_session.py::TestBloombergSessionRequests -v
```

### What Unit Tests Cover

Unit tests use mocked `blpapi` responses to verify:

- ✅ Session initialization and connection logic
- ✅ Request construction (reference, bulk, historical)
- ✅ Response parsing to pandas DataFrames
- ✅ Error handling (invalid securities, missing fields)
- ✅ Retry logic and circuit breaker pattern
- ✅ Context manager lifecycle
- ✅ Field error tracking

### Mock Architecture

Unit tests mock the Bloomberg API at the `blpapi` package level:

```python
# Example mock setup
@patch('src.bloomberg_session.blpapi')
def test_send_request(mock_blpapi):
    # Mock session, service, request, response
    mock_session = MagicMock()
    mock_blpapi.Session.return_value = mock_session

    # Test proceeds with mocked responses
    with BloombergSession() as session:
        df = session.send_request(...)
```

**Limitations**: Mocks verify logic but can't catch:
- Bloomberg API version changes
- Field availability for specific securities
- Actual response format variations
- Network/timeout issues

## Integration Tests (Bloomberg Terminal Required)

### Prerequisites

1. **Bloomberg Terminal** must be running and logged in
2. **DAPI enabled**: Check `DAPI<GO>` in Terminal
3. **blpapi installed**: See [installation instructions](#installing-blpapi)
4. **Test securities available**: Tests use Japanese equities (9107, 9104, 9101 JP Equity)

### Running Integration Tests

```bash
# Run all integration tests
python tests/test_integration_bloomberg.py

# Expected output:
# ********************************************************************************
# BLOOMBERG SESSION MANAGER - MANUAL INTEGRATION TESTS
# ********************************************************************************
#
# TEST 1: Bloomberg Terminal Connection
# ✓ Successfully connected to Bloomberg API
#
# TEST 2: Reference Data - Single Security
# ✓ Retrieved data for 1 security
# ...
#
# Results: 8/8 tests passed
```

### What Integration Tests Cover

Integration tests verify real Bloomberg API behavior:

- ✅ Terminal connection and authentication
- ✅ Reference data retrieval for Japanese equities
- ✅ Point-in-time data with `END_DT_OVERRIDE`
- ✅ Bulk data retrieval (`TOP_20_HOLDERS_PUBLIC_FILINGS`)
- ✅ Historical price data
- ✅ Error handling with invalid securities/fields
- ✅ Field error tracking and reporting

### Manual Testing Checklist

If integration tests fail, check:

1. **Terminal Status**
   - Bloomberg Terminal is open and logged in
   - Run `DAPI<GO>` → Diagnostics → Test Connection
   - Verify DAPI service is running (should show green status)

2. **Network Configuration**
   - Default: `localhost:8194`
   - Corporate networks may use different host/port
   - Check with your Bloomberg support team

3. **Security Availability**
   - Tests use: `9107 JP Equity`, `9104 JP Equity`, `9101 JP Equity`
   - Verify these tickers exist: `9107 JP Equity <EQUITY><GO>`
   - Substitute with different securities if needed

4. **Field Permissions**
   - Some fields require specific data licenses
   - Check field availability: `FLDS<GO>` → Search field name
   - Common issues: `TOP_20_HOLDERS_PUBLIC_FILINGS` requires ownership data license

## Installing blpapi

The Bloomberg Python API (`blpapi`) is not included in standard PyPI due to licensing.

### Option 1: Download from Bloomberg Terminal

```bash
# In Bloomberg Terminal
WAPI<GO>

# Navigate to: Downloads → Python API
# Download the appropriate wheel for your platform
# Example: blpapi-3.23.4-py3-cp313-cp313-macosx_14_0_arm64.whl

# Install the wheel
pip install /path/to/blpapi-3.23.4-*.whl
```

### Option 2: Use conda-forge

```bash
conda install -c conda-forge blpapi
```

### Option 3: Download from Bloomberg Website

1. Visit: https://www.bloomberg.com/professional/support/api-library/
2. Download Python API for your platform
3. Install: `pip install /path/to/blpapi-*.whl`

### Verifying Installation

```python
# Test blpapi import
python -c "import blpapi; print(f'blpapi {blpapi.__version__} installed')"

# Expected output:
# blpapi 3.23.4 installed
```

## CI/CD Considerations

### GitHub Actions / CI Pipelines

Bloomberg API cannot run in standard CI environments because:
- Requires authenticated Bloomberg Terminal connection
- Terminal must be logged in with valid credentials
- DAPI service runs on local machine, not cloud

**Recommended CI Strategy**:

```yaml
# .github/workflows/test.yml
jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - name: Run unit tests (no Bloomberg required)
        run: |
          pytest tests/test_bloomberg_session.py -v
          pytest tests/test_ticker_converter.py -v
          pytest tests/test_fiscal_alignment.py -v

      - name: Skip integration tests
        run: |
          echo "Integration tests require Bloomberg Terminal"
          echo "Run manually: python tests/test_integration_bloomberg.py"
```

### Local Development Workflow

1. **Pre-commit**: Run unit tests (fast, no Terminal needed)
   ```bash
   pytest tests/test_bloomberg_session.py -v
   ```

2. **Pre-push**: Run integration tests (slower, requires Terminal)
   ```bash
   python tests/test_integration_bloomberg.py
   ```

3. **Release**: Full test suite + manual validation with production securities

## Troubleshooting

### "blpapi is not installed" Error

**Symptom**: `ImportError: Bloomberg API (blpapi) is not installed`

**Solution**:
1. Follow [installation instructions](#installing-blpapi)
2. Verify: `python -c "import blpapi"`
3. Check Python environment matches where blpapi is installed

### "Failed to start Bloomberg session" Error

**Symptom**: `BloombergConnectionError: Failed to start Bloomberg session`

**Possible Causes**:
1. **Terminal not running**: Open Bloomberg Terminal and log in
2. **DAPI disabled**: Run `DAPI<GO>` → Enable API
3. **Wrong host/port**: Corporate networks may use non-standard configuration
4. **Firewall blocking**: Check firewall allows `localhost:8194`

**Debug Steps**:
```python
# Test basic connection
from src.bloomberg_session import BloombergSession

session = BloombergSession()
try:
    session.start()
    print("✓ Connection successful")
except Exception as e:
    print(f"✗ Connection failed: {e}")
finally:
    session.close()
```

### "Field not available" Warnings

**Symptom**: Field returns `None`, logged in `session.field_errors`

**Possible Causes**:
1. **Field doesn't exist**: Check `FLDS<GO>` in Terminal
2. **No data for security**: Field exists but no data available
3. **Data license required**: Field requires specific subscription
4. **Incorrect override**: Wrong `FUND_PER` or `END_DT_OVERRIDE` value

**Debug Steps**:
```python
# Check field errors
df = session.send_request(["9107 JP Equity"], ["PX_TO_BOOK_RATIO", "INVALID_FIELD"])
errors = session.get_field_errors()
print(errors)
# Output: {'9107 JP Equity': ['INVALID_FIELD']}

# Verify in Terminal
# DES<GO> for the security → Check field availability
```

### Rate Limit Errors

**Symptom**: `BloombergRateLimitError: Circuit breaker is OPEN`

**Cause**: Too many requests in short time period

**Solution**:
1. Reduce request frequency
2. Batch multiple securities/fields per request
3. Wait 60+ seconds for circuit breaker to reset
4. Check Bloomberg API rate limits: `DAPI<GO>` → Settings

## Test Data Reference

### Test Securities (Effissimo Target Companies)

| Bloomberg Ticker | Company Name | Sector |
|-----------------|--------------|--------|
| 9107 JP Equity | Kawasaki Kisen Kaisha | Shipping |
| 9104 JP Equity | Mitsui OSK Lines | Shipping |
| 9101 JP Equity | Nippon Yusen | Shipping |

### Test Fields (Critical Fields)

| Field Name | Data Type | Override Type |
|-----------|-----------|---------------|
| PX_TO_BOOK_RATIO | float | END_DT_OVERRIDE |
| RETURN_COM_EQY | float | FUND_PER |
| CUR_MKT_CAP | float | END_DT_OVERRIDE |
| FISCAL_YEAR_END_MONTH_DE | int | None (static) |
| TOP_20_HOLDERS_PUBLIC_FILINGS | table | None (bulk) |

### Test Overrides

```python
# Point-in-time market data (as of 2023-03-31)
overrides = {"END_DT_OVERRIDE": "20230331"}

# Fundamental data (fiscal year 2022)
overrides = {"FUND_PER": "FY2022"}
```

## Coverage Goals

- **Unit Test Coverage**: >80% (verified with pytest-cov)
- **Integration Test Coverage**: All core request types (reference, bulk, historical)
- **Error Handling Coverage**: All known Bloomberg error codes

## Next Steps

After validating Bloomberg Session Manager:

1. Run unit tests: `pytest tests/test_bloomberg_session.py -v`
2. Run integration tests: `python tests/test_integration_bloomberg.py`
3. Proceed to **Phase 3: Batching Engine** if all tests pass
4. File issues for any failing tests (include full error output)

## References

- Bloomberg DAPI Documentation: `DAPI<GO>` in Terminal
- Field Search: `FLDS<GO>` in Terminal
- API Library: https://www.bloomberg.com/professional/support/api-library/
- Python API Examples: `WAPI<GO>` → Examples → Python
