# Bloomberg Field Specification

## Critical Fields (Must Have 100% Coverage)
- PX_TO_BOOK_RATIO (Price-to-Book Ratio)
- RETURN_COM_EQY (Return on Equity)
- CUR_MKT_CAP (Market Capitalization)
- NET_DEBT (Net Debt, negative = net cash)
- BS_CASH_NEAR_CASH_ITEM (Cash & Equivalents)
- SHORT_AND_LONG_TERM_DEBT (Total Debt)
- TOT_EQUITY (Total Shareholders' Equity)
- EQY_SH_OUT (Shares Outstanding)
- FISCAL_YEAR_END_MONTH_DE (FYE Month, required for fiscal alignment)

## Field Groups by Override Type

### Group 1: Fundamental (FUND_PER Override)
Profitability: RETURN_COM_EQY, RETURN_ON_ASSET, RETURN_ON_INV_CAPITAL, OPER_MARGIN, PROF_MARGIN
Balance Sheet: BS_CASH_NEAR_CASH_ITEM, BS_MKT_SEC_OTHER_ST_INVEST, BS_LONG_TERM_INVESTMENTS, SHORT_AND_LONG_TERM_DEBT, NET_DEBT, TOT_EQUITY
Income Statement: TRAIL_12M_SALES, TRAIL_12M_OPER_INC, TRAIL_12M_NET_INC, TRAIL_12M_EPS

### Group 2: Market Data (END_DT_OVERRIDE)
Valuation: PX_TO_BOOK_RATIO, PE_RATIO, BEST_PE_RATIO, BEST_CUR_EV_TO_EBITDA, CUR_EV_TO_T12M_SALES, EQY_DVD_YLD_IND
Market Metrics: CUR_MKT_CAP, HIGH_52WEEK, LOW_52WEEK, EQY_SH_OUT, EQY_FREE_FLOAT_PCT, VOLUME_AVG_30D
Ownership: EQY_INST_PCT_SH_OUT, EQY_FOREIGN_OWNERSHIP_PCT, INSIDER_OWNERSHIP_PCT

### Group 3: Static (No Override)
Governance: BOARD_SIZE, PCT_INDEPENDENT_DIRECTORS, FISCAL_YEAR_END_MONTH_DE

### Group 4: Bulk (BulkReferenceDataRequest)
Ownership: TOP_20_HOLDERS_PUBLIC_FILINGS (table: holder name, type, shares, %)
Corporate Actions: DVD_HIST_ALL, SHARE_REPURCHASE_SUMMARY, STOCK_SPLIT_HIST, MERGERS_AND_ACQUISITIONS
  NOTE: Extract only events during campaign period (first_filing to last_filing dates)

## Japanese Market Data Quirks
- EQY_FOREIGN_OWNERSHIP_PCT: May be unavailable for Standard/Growth segments. Fallback: compute from TOP_20_HOLDERS.
- PCT_INDEPENDENT_DIRECTORS: Limited coverage outside Prime Market. Mark as optional.
- Cross-shareholding: Common in Japan. Use TOP_20_HOLDERS to identify corporate holders.
- Fiscal Year-End: 70% use March 31, but ~10% use December 31 or September 30. Always query FISCAL_YEAR_END_MONTH_DE.

## Derived Fields (Computed Post-Extraction)
- net_cash: BS_CASH_NEAR_CASH_ITEM + BS_MKT_SEC_OTHER_ST_INVEST - SHORT_AND_LONG_TERM_DEBT
- net_cash_to_market_cap: net_cash / CUR_MKT_CAP
- cross_shareholding_ratio: Sum of % held by holders with type = "Corporation" from TOP_20_HOLDERS
- campaign_status: "Active" if last_filing within 60 days, else "Exited"

## Data Quality Thresholds
- Critical field coverage: 100% (PBR, ROE, Market Cap, Net Debt)
- Optional field coverage: 70% acceptable (analyst estimates, governance)
- Overall quality score: >90% required for production
- Manual review flag: Securities with >30% missing fields
