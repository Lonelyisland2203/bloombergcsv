# Technology Stack

## Core Dependencies
- Python: 3.9+ (type hints, dataclasses required)
- blpapi: Bloomberg Desktop API Python binding (official package)
- pandas: 1.5+ (DataFrame operations, Excel I/O)
- openpyxl: Excel workbook formatting engine
- pyyaml: YAML config parsing

## Data Infrastructure
- Bloomberg Terminal: Desktop application (DAPI enabled required)
- Input Format: CSV (UTF-8, Tokyo Stock Exchange ticker format)
- Output Format: Excel .xlsx (multi-sheet workbooks)

## Development Tools
- pytest: Unit and integration testing
- mypy: Static type checking
- flake8: PEP8 linting
- pylint: Code quality analysis

## Environment
- OS: macOS/Windows (Bloomberg Terminal compatibility)
- Bloomberg Service: //blp/refdata (Reference Data Service)
- API Protocol: blpapi.Session (persistent connection)

## Performance Targets
- Throughput: <10 minutes for 50 securities
- Memory: <500MB peak usage
- Rate Limit: <1 request/second (conservative)
