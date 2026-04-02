# Coding Standards

## File Naming
- Modules: snake_case (e.g., bloomberg_session.py, extract_snapshot.py)
- Classes: PascalCase (e.g., BloombergSession, TickerConverter)
- Functions: snake_case (e.g., convert_ticker, compute_snapshot_date)
- Constants: UPPER_SNAKE_CASE (e.g., MAX_BATCH_SIZE, RATE_LIMIT_DELAY)

## Type Hints
All functions must have type hints for parameters and return values.
Use from __future__ import annotations for forward references.

## Docstrings
Google-style docstrings required for all public functions and classes.
Include Args, Returns, Raises sections.

## Error Messages
- Actionable: Include what failed and what user should do
- Contextual: Include ticker/field name when available
- Logged: All errors logged to logs/ with timestamps

## DataFrame Conventions
- Ticker column: Always named "ticker" (lowercase)
- Date columns: datetime64[ns] dtype, named with _date suffix
- Percentage fields: Stored as float (0.38 = 38%), formatted in Excel as percentage
- Currency fields: Float in JPY, formatted in Excel with ¥ symbol

## Logging
- INFO: Pipeline milestones (phase start/end, extraction counts)
- WARNING: Missing fields, skipped securities
- ERROR: Bloomberg API errors, session failures
- DEBUG: Request details, response parsing

## Testing
- Unit tests: Mock Bloomberg responses, test business logic only
- Integration tests: Require live Bloomberg Terminal, test 3-5 real securities
- Edge case tests: Invalid tickers, missing fields, fiscal period off-by-one

## Git Commit Messages
- Format: "<module>: <verb> <description>"
- Examples: "bloomberg_session: Add auto-reconnect on timeout", "extract_snapshot: Fix FUND_PER override construction"
