# Quick Start: Price History & Peer Comps

## 5-Minute Setup

### 1. Import Modules

```python
from datetime import date
from bloomberg_session import BloombergSession
from extract_price_history import PriceHistoryExtractor, PriceHistoryTarget
from extract_peer_comps import PeerCompsExtractor, PeerCompTarget
```

### 2. Price History - Basic Example

```python
# Define campaign
target = PriceHistoryTarget(
    ticker="9107 JP Equity",
    campaign_start=date(2023, 6, 14),
    campaign_end=None  # Ongoing
)

# Extract price history
with BloombergSession() as session:
    extractor = PriceHistoryExtractor(session)
    df = extractor.extract_campaign_price_history(target)

    # View results
    print(f"Entry price: {target.entry_price:.2f}")
    print(f"Trading days: {len(df)}")

    # Compute stats
    stats = extractor.compute_summary_statistics(df)
    print(f"Total return: {stats['total_return']:.2%}")
```

### 3. Peer Comps - Basic Example

```python
import pandas as pd

# Define targets
targets = [
    PeerCompTarget("9107 JP Equity", "Kawasaki Kisen"),
    PeerCompTarget("8136 JP Equity", "Sanrio"),
]

# Snapshot data (from extract_snapshot.py in production)
snapshot_df = pd.DataFrame({
    "security": ["9107 JP Equity", "8136 JP Equity"],
    "PX_TO_BOOK_RATIO": [0.8, 2.5],
    "RETURN_COM_EQY": [8.5, 15.0],
    "CUR_MKT_CAP": [100000, 200000],
    "NET_DEBT": [50000, -30000],
    "EBITDA": [10000, 25000],
})

# Extract peer comparisons
with BloombergSession() as session:
    extractor = PeerCompsExtractor(session)
    peer_comps = extractor.extract_peer_comps(targets, snapshot_df)

    # View results
    for _, row in peer_comps.iterrows():
        print(f"{row['company_name']}:")
        print(f"  Sector: {row['sector']}")
        print(f"  PBR Discount: {row['pbr_vs_sector']:.2%}")
        print(f"  ROE vs Sector: {row['roe_vs_sector']:.1f} pp")
```

## Common Operations

### Extract Multiple Campaigns (Price History)

```python
targets = [
    PriceHistoryTarget("8136 JP Equity", date(2021, 6, 14), None),
    PriceHistoryTarget("9107 JP Equity", date(2020, 11, 13), date(2023, 4, 7)),
]

with BloombergSession() as session:
    extractor = PriceHistoryExtractor(session)
    all_prices = extractor.extract_multiple_campaigns(targets)

    # Group by ticker
    for ticker, group in all_prices.groupby("ticker"):
        print(f"{ticker}: {len(group)} trading days")
```

### Identify Sector Only (Peer Comps)

```python
with BloombergSession() as session:
    extractor = PeerCompsExtractor(session)

    sector, industry = extractor.identify_sector("9107 JP Equity")
    print(f"Sector: {sector}")
    print(f"Industry: {industry}")
```

## Output Columns

### Price History DataFrame

| Column | Description |
|--------|-------------|
| ticker | Bloomberg ticker |
| date | Trading date |
| adjusted_close | Adjusted close price |
| volume | Daily volume |
| days_since_activist_entry | Days since entry |
| cumulative_return | Return from entry |
| entry_price | Entry price reference |

### Peer Comps DataFrame

| Column | Description |
|--------|-------------|
| ticker | Bloomberg ticker |
| company_name | Company name |
| sector | GICS sector |
| company_pbr | Company PBR |
| pbr_vs_sector | % discount/premium |
| company_roe | Company ROE |
| roe_vs_sector | ROE difference (pp) |
| company_ev_ebitda | Company EV/EBITDA |
| ev_ebitda_vs_sector | % discount/premium |

## Running Demo Scripts

```bash
# Price history demo
python examples/price_history_demo.py

# Peer comps demo
python examples/peer_comps_demo.py
```

## Running Tests

```bash
# All tests
pytest tests/test_extract_price_history.py tests/test_extract_peer_comps.py -v

# Just price history
pytest tests/test_extract_price_history.py -v

# Just peer comps
pytest tests/test_extract_peer_comps.py -v
```

## Troubleshooting

**Entry date not found:**
```python
# Provide entry_price if entry_date is market holiday
df = extractor.compute_derived_metrics(
    price_df=df,
    entry_date=date(2023, 6, 14),
    entry_price=1234.5  # Manually specify
)
```

**No sector data:**
```python
# Check if ticker is valid
sector, industry = extractor.identify_sector("INVALID JP Equity")
# Returns: (None, None)
```

**Missing metrics in snapshot:**
```python
# Ensure snapshot_df has required columns:
required = ["PX_TO_BOOK_RATIO", "RETURN_COM_EQY",
            "CUR_MKT_CAP", "NET_DEBT", "EBITDA"]
missing = [col for col in required if col not in snapshot_df.columns]
print(f"Missing columns: {missing}")
```

## Full Documentation

- Price History: `docs/phase7_price_history.md`
- Peer Comps: `docs/phase8_peer_comps.md`
- Implementation Summary: `PHASE7_8_IMPLEMENTATION_SUMMARY.md`
