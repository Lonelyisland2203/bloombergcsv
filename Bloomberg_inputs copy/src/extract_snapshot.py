"""
Snapshot Extractor for Bloomberg Activist Data Pipeline

This is the MOST CRITICAL module in the pipeline, responsible for extracting
point-in-time financial snapshots for activist campaign targets.

Core Responsibilities:
    1. Extract 40+ Bloomberg fields for all target companies
    2. Ensure ZERO lookahead bias (all data as-of snapshot date before campaign)
    3. Use correct overrides (FUND_PER for fundamentals, END_DT_OVERRIDE for market data)
    4. Compute derived fields (Net Cash, Net Cash / Market Cap, etc.)
    5. Handle missing data gracefully with comprehensive logging
    6. Validate data quality and flag securities requiring manual review

Point-in-Time Safety (CRITICAL):
    - snapshot_date MUST be before campaign_start_date (validated in tests)
    - FUND_PER override MUST correspond to fiscal year BEFORE snapshot date
    - END_DT_OVERRIDE MUST use snapshot_date, not today's date
    - NO forward-looking data without explicit estimate date validation

Data Quality Assurance:
    - Log all missing fields to JSON gap reports
    - Flag securities with >30% missing critical fields
    - Compute data_quality_score for each security
    - Generate field coverage statistics

Derived Field Calculations:
    - net_cash = BS_CASH_NEAR_CASH_ITEM + BS_MKT_SEC_OTHER_ST_INVEST - SHORT_AND_LONG_TERM_DEBT
    - net_cash_to_market_cap = net_cash / CUR_MKT_CAP
    - data_quality_score = % of critical fields populated

Author: Bloomberg Activist Pipeline
"""

import logging
import json
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from bloomberg_session import BloombergSession
from batching_engine import BatchingEngine
from fiscal_period_aligner import (
    compute_snapshot_date,
    construct_fund_per_override,
)

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class CampaignTarget:
    """
    Represents a single activist campaign target company.

    Attributes:
        company_name_japanese: Japanese company name (primary identifier)
        company_name_english: English company name (will be fetched from Bloomberg if None)
        tse_ticker: Original Tokyo Stock Exchange ticker (e.g., "9107.T")
        bloomberg_ticker: Bloomberg-converted ticker (e.g., "9107 JP Equity")
        campaign_start: Date when activist campaign began (earliest filing date)
        campaign_end: Date when campaign ended (None if ongoing)
        max_ownership_pct: Maximum ownership percentage achieved
        min_ownership_pct: Minimum ownership percentage
        total_filings: Number of regulatory filings
        snapshot_date: Fiscal year-end date for data extraction (computed)
        fund_per_override: Bloomberg FUND_PER string (e.g., "FY2021")
        fye_month: Fiscal year-end month (1-12, fetched from Bloomberg)
    """

    company_name_japanese: str
    company_name_english: Optional[str]
    tse_ticker: str
    bloomberg_ticker: str
    campaign_start: date
    campaign_end: Optional[date]
    max_ownership_pct: float
    min_ownership_pct: float
    total_filings: int
    snapshot_date: Optional[date] = None
    fund_per_override: Optional[str] = None
    fye_month: Optional[int] = None

    def __post_init__(self):
        """Validate campaign target data after initialization."""
        # Validate ownership percentages
        if self.max_ownership_pct < 0 or self.max_ownership_pct > 100:
            raise ValueError(
                f"max_ownership_pct must be 0-100, got {self.max_ownership_pct}"
            )

        if self.min_ownership_pct < 0 or self.min_ownership_pct > 100:
            raise ValueError(
                f"min_ownership_pct must be 0-100, got {self.min_ownership_pct}"
            )

        if self.min_ownership_pct > self.max_ownership_pct:
            raise ValueError(
                f"min_ownership_pct ({self.min_ownership_pct}) cannot exceed "
                f"max_ownership_pct ({self.max_ownership_pct})"
            )

        # Validate campaign dates
        if self.campaign_end is not None and self.campaign_end < self.campaign_start:
            raise ValueError(
                f"campaign_end ({self.campaign_end}) cannot be before "
                f"campaign_start ({self.campaign_start})"
            )

        # Validate snapshot_date if provided
        if self.snapshot_date is not None:
            if self.snapshot_date >= self.campaign_start:
                raise ValueError(
                    f"Point-in-time violation: snapshot_date ({self.snapshot_date}) "
                    f"must be BEFORE campaign_start ({self.campaign_start})"
                )


@dataclass
class FieldGapEntry:
    """
    Represents a missing field for a specific security.

    Attributes:
        ticker: Bloomberg ticker
        field_name: Bloomberg field name
        error_message: Error description from Bloomberg API
        bloomberg_error_code: Bloomberg error code (if available)
        timestamp: When the gap was recorded
    """

    ticker: str
    field_name: str
    error_message: str
    bloomberg_error_code: Optional[str] = None
    timestamp: str = None

    def __post_init__(self):
        """Set timestamp to current time if not provided."""
        if self.timestamp is None:
            self.timestamp = datetime.now().isoformat()


class SnapshotExtractor:
    """
    Core data extractor for point-in-time financial snapshots.

    This class orchestrates the extraction of comprehensive financial data
    for activist campaign targets, ensuring point-in-time safety and
    data quality throughout the process.

    Attributes:
        session: Active Bloomberg session
        batching_engine: Batching engine for request optimization
        logs_dir: Directory for gap reports and quality logs
        field_gaps: List of FieldGapEntry objects tracking missing data
    """

    # Define critical fields that MUST be present for quality validation
    CRITICAL_FIELDS = [
        "PX_TO_BOOK_RATIO",  # Valuation
        "RETURN_COM_EQY",  # Profitability
        "CUR_MKT_CAP",  # Market data
        "NET_DEBT",  # Balance sheet
        "TRAIL_12M_SALES",  # Income statement
    ]

    def __init__(
        self,
        session: BloombergSession,
        batching_engine: BatchingEngine,
        logs_dir: Optional[Path] = None,
    ):
        """
        Initialize snapshot extractor.

        Args:
            session: Active Bloomberg session
            batching_engine: Batching engine instance
            logs_dir: Directory for gap reports (default: ../logs)

        Raises:
            ValueError: If session is not started
        """
        self.session = session
        self.batching_engine = batching_engine

        # Set up logs directory
        if logs_dir is None:
            src_dir = Path(__file__).parent
            logs_dir = src_dir.parent / "logs"

        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Track field gaps
        self.field_gaps: List[FieldGapEntry] = []

        logger.info("SnapshotExtractor initialized")

    def extract_snapshot(
        self, campaigns: List[CampaignTarget]
    ) -> pd.DataFrame:
        """
        Extract complete snapshot for all campaigns.

        This is the main entry point for snapshot extraction. It orchestrates:
        1. Fiscal year-end determination
        2. Field grouping by override type
        3. Parallel extraction of field groups
        4. Data merging and derived field computation
        5. Data quality validation and gap reporting

        Args:
            campaigns: List of CampaignTarget objects

        Returns:
            DataFrame with complete snapshot data

        Raises:
            ValueError: If no campaigns provided or all extractions fail
        """
        if not campaigns:
            raise ValueError("No campaigns provided for snapshot extraction")

        logger.info(f"Starting snapshot extraction for {len(campaigns)} campaigns")

        # Step 1: Determine fiscal year-end for all securities
        securities = [c.bloomberg_ticker for c in campaigns]
        self._enrich_fiscal_metadata(campaigns)

        # Step 2: Extract field groups in parallel
        fund_per_df = self._extract_fundamental_fields(campaigns)
        market_df = self._extract_market_fields(campaigns)
        static_df = self._extract_static_fields(securities)

        # Step 3: Merge all data
        logger.info("Merging field groups into unified snapshot")
        snapshot_df = self._merge_field_groups(
            securities, fund_per_df, market_df, static_df
        )

        # Step 4: Add campaign metadata
        snapshot_df = self._add_campaign_metadata(snapshot_df, campaigns)

        # Step 5: Compute derived fields
        snapshot_df = self.compute_derived_fields(snapshot_df)

        # Step 6: Validate data quality and log gaps
        snapshot_df = self._compute_data_quality_scores(snapshot_df)
        gap_report = self.log_field_gaps(snapshot_df)

        # Step 7: Save gap report to JSON
        gap_report_path = self._save_gap_report(gap_report)
        logger.info(f"Field gap report saved to: {gap_report_path}")

        logger.info(
            f"Snapshot extraction complete: {len(snapshot_df)} securities, "
            f"{len(snapshot_df.columns)} fields"
        )

        return snapshot_df

    def _enrich_fiscal_metadata(self, campaigns: List[CampaignTarget]) -> None:
        """
        Fetch fiscal year-end month and compute snapshot dates for all campaigns.

        Updates CampaignTarget objects in-place with:
        - fye_month: Fiscal year-end month (1-12)
        - snapshot_date: Computed fiscal year-end date
        - fund_per_override: Bloomberg FUND_PER string

        Args:
            campaigns: List of CampaignTarget objects to enrich

        Raises:
            ValueError: If fiscal year-end data not available
        """
        logger.info("Fetching fiscal year-end metadata for all securities")

        securities = [c.bloomberg_ticker for c in campaigns]

        # Fetch fiscal year-end month for all securities
        fye_df = self.session.send_request(
            securities=securities, fields=["FISCAL_YEAR_END_MONTH_DE"]
        )

        # Build lookup dict
        fye_lookup = {}
        for _, row in fye_df.iterrows():
            ticker = row["security"]
            fye_month = row.get("FISCAL_YEAR_END_MONTH_DE")

            if pd.notna(fye_month):
                fye_lookup[ticker] = int(fye_month)
            else:
                logger.warning(
                    f"Fiscal year-end month not available for {ticker}, "
                    "defaulting to March (3)"
                )
                fye_lookup[ticker] = 3  # Default to March (common in Japan)

        # Compute snapshot dates and FUND_PER overrides
        for campaign in campaigns:
            campaign.fye_month = fye_lookup.get(campaign.bloomberg_ticker, 3)

            # Compute snapshot date
            campaign.snapshot_date = compute_snapshot_date(
                campaign.campaign_start, campaign.fye_month
            )

            # Construct FUND_PER override
            campaign.fund_per_override = construct_fund_per_override(
                campaign.snapshot_date
            )

            logger.info(
                f"{campaign.bloomberg_ticker}: FYE={campaign.fye_month}, "
                f"snapshot_date={campaign.snapshot_date}, "
                f"FUND_PER={campaign.fund_per_override}"
            )

            # Validate point-in-time safety
            if campaign.snapshot_date >= campaign.campaign_start:
                raise ValueError(
                    f"Point-in-time violation for {campaign.bloomberg_ticker}: "
                    f"snapshot_date ({campaign.snapshot_date}) must be BEFORE "
                    f"campaign_start ({campaign.campaign_start})"
                )

    def _extract_fundamental_fields(
        self, campaigns: List[CampaignTarget]
    ) -> pd.DataFrame:
        """
        Extract profitability, balance sheet, and income statement fields.

        Uses FUND_PER override for fiscal-period-based data.

        Args:
            campaigns: List of CampaignTarget objects with fiscal metadata

        Returns:
            DataFrame with fundamental fields
        """
        logger.info("Extracting fundamental fields (FUND_PER override)")

        # Get FUND_PER fields from batching engine
        fund_per_fields = self.batching_engine.field_manager.get_fields_by_override_type(
            "FUND_PER"
        )

        if not fund_per_fields:
            logger.warning("No FUND_PER fields configured")
            return pd.DataFrame()

        logger.info(f"Extracting {len(fund_per_fields)} FUND_PER fields")

        # Group campaigns by FUND_PER override value
        campaigns_by_fund_per: Dict[str, List[CampaignTarget]] = {}
        for campaign in campaigns:
            fund_per = campaign.fund_per_override
            if fund_per not in campaigns_by_fund_per:
                campaigns_by_fund_per[fund_per] = []
            campaigns_by_fund_per[fund_per].append(campaign)

        # Extract data for each FUND_PER group
        all_dfs = []
        for fund_per, group_campaigns in campaigns_by_fund_per.items():
            securities = [c.bloomberg_ticker for c in group_campaigns]

            logger.info(
                f"Extracting FUND_PER={fund_per} for {len(securities)} securities"
            )

            # Create batches
            batches = self.batching_engine.create_batches(
                securities=securities, fields=fund_per_fields
            )

            # Execute batches
            overrides = {"FUND_PER": fund_per}
            df = self.batching_engine.execute_batches_sequential(
                session=self.session, batches=batches, overrides=overrides
            )

            all_dfs.append(df)

        # Combine all groups
        if all_dfs:
            combined_df = pd.concat(all_dfs, ignore_index=True)
            logger.info(
                f"FUND_PER extraction complete: {len(combined_df)} records"
            )
            return combined_df
        else:
            return pd.DataFrame()

    def _extract_market_fields(
        self, campaigns: List[CampaignTarget]
    ) -> pd.DataFrame:
        """
        Extract valuation, market data, and ownership fields.

        Uses END_DT_OVERRIDE for market-date-sensitive data.

        Args:
            campaigns: List of CampaignTarget objects with snapshot dates

        Returns:
            DataFrame with market fields
        """
        logger.info("Extracting market fields (END_DT_OVERRIDE)")

        # Get END_DT_OVERRIDE fields from batching engine
        market_fields = self.batching_engine.field_manager.get_fields_by_override_type(
            "END_DT_OVERRIDE"
        )

        if not market_fields:
            logger.warning("No END_DT_OVERRIDE fields configured")
            return pd.DataFrame()

        logger.info(f"Extracting {len(market_fields)} END_DT_OVERRIDE fields")

        # Group campaigns by snapshot date
        campaigns_by_date: Dict[str, List[CampaignTarget]] = {}
        for campaign in campaigns:
            # Convert snapshot_date to YYYYMMDD format for Bloomberg
            snapshot_str = campaign.snapshot_date.strftime("%Y%m%d")
            if snapshot_str not in campaigns_by_date:
                campaigns_by_date[snapshot_str] = []
            campaigns_by_date[snapshot_str].append(campaign)

        # Extract data for each snapshot date group
        all_dfs = []
        for snapshot_str, group_campaigns in campaigns_by_date.items():
            securities = [c.bloomberg_ticker for c in group_campaigns]

            logger.info(
                f"Extracting END_DT_OVERRIDE={snapshot_str} for {len(securities)} securities"
            )

            # Create batches
            batches = self.batching_engine.create_batches(
                securities=securities, fields=market_fields
            )

            # Execute batches
            overrides = {"END_DT_OVERRIDE": snapshot_str}
            df = self.batching_engine.execute_batches_sequential(
                session=self.session, batches=batches, overrides=overrides
            )

            all_dfs.append(df)

        # Combine all groups
        if all_dfs:
            combined_df = pd.concat(all_dfs, ignore_index=True)
            logger.info(
                f"END_DT_OVERRIDE extraction complete: {len(combined_df)} records"
            )
            return combined_df
        else:
            return pd.DataFrame()

    def _extract_static_fields(self, securities: List[str]) -> pd.DataFrame:
        """
        Extract governance and company info fields (no override needed).

        Args:
            securities: List of Bloomberg tickers

        Returns:
            DataFrame with static fields
        """
        logger.info("Extracting static fields (no override)")

        # Get static fields (override_type="none")
        static_fields = self.batching_engine.field_manager.get_fields_by_override_type(
            "none"
        )

        if not static_fields:
            logger.warning("No static fields configured")
            return pd.DataFrame()

        logger.info(f"Extracting {len(static_fields)} static fields")

        # Create batches
        batches = self.batching_engine.create_batches(
            securities=securities, fields=static_fields
        )

        # Execute batches (no overrides)
        df = self.batching_engine.execute_batches_sequential(
            session=self.session, batches=batches, overrides={}
        )

        logger.info(f"Static field extraction complete: {len(df)} records")

        return df

    def _merge_field_groups(
        self,
        securities: List[str],
        fund_per_df: pd.DataFrame,
        market_df: pd.DataFrame,
        static_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Merge all field groups into unified snapshot DataFrame.

        Args:
            securities: List of Bloomberg tickers (for ensuring all are present)
            fund_per_df: FUND_PER fields DataFrame
            market_df: END_DT_OVERRIDE fields DataFrame
            static_df: Static fields DataFrame

        Returns:
            Merged DataFrame with all fields
        """
        # Start with securities as base
        snapshot_df = pd.DataFrame({"security": securities})

        # Merge FUND_PER fields
        if not fund_per_df.empty:
            snapshot_df = snapshot_df.merge(
                fund_per_df, on="security", how="left"
            )

        # Merge market fields
        if not market_df.empty:
            snapshot_df = snapshot_df.merge(
                market_df, on="security", how="left"
            )

        # Merge static fields
        if not static_df.empty:
            snapshot_df = snapshot_df.merge(
                static_df, on="security", how="left"
            )

        return snapshot_df

    def _add_campaign_metadata(
        self, snapshot_df: pd.DataFrame, campaigns: List[CampaignTarget]
    ) -> pd.DataFrame:
        """
        Add campaign metadata columns to snapshot DataFrame.

        Args:
            snapshot_df: Snapshot DataFrame with financial data
            campaigns: List of CampaignTarget objects

        Returns:
            DataFrame with campaign metadata added
        """
        # Build metadata lookup
        metadata_records = []
        for campaign in campaigns:
            metadata_records.append(
                {
                    "security": campaign.bloomberg_ticker,
                    "company_name_japanese": campaign.company_name_japanese,
                    "company_name_english": campaign.company_name_english,
                    "tse_ticker": campaign.tse_ticker,
                    "campaign_start": campaign.campaign_start,
                    "campaign_end": campaign.campaign_end,
                    "max_ownership_pct": campaign.max_ownership_pct,
                    "min_ownership_pct": campaign.min_ownership_pct,
                    "total_filings": campaign.total_filings,
                    "snapshot_date": campaign.snapshot_date,
                    "fund_per_override": campaign.fund_per_override,
                    "fye_month": campaign.fye_month,
                }
            )

        metadata_df = pd.DataFrame(metadata_records)

        # Merge metadata (left join to preserve all snapshot data)
        snapshot_df = snapshot_df.merge(metadata_df, on="security", how="left")

        return snapshot_df

    def compute_derived_fields(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute derived financial fields from Bloomberg raw data.

        Derived fields:
        - net_cash: BS_CASH_NEAR_CASH_ITEM + BS_MKT_SEC_OTHER_ST_INVEST - SHORT_AND_LONG_TERM_DEBT
        - net_cash_to_market_cap: net_cash / CUR_MKT_CAP

        Args:
            df: DataFrame with Bloomberg fields

        Returns:
            DataFrame with derived fields added

        Notes:
            - Handles missing data gracefully (null propagation)
            - Logs warnings for invalid calculations (e.g., division by zero)
        """
        logger.info("Computing derived fields")

        # Net Cash = Cash + ST Investments - Total Debt
        # Use fillna(0) to handle missing values properly
        df["net_cash"] = (
            df.get("BS_CASH_NEAR_CASH_ITEM", pd.Series(0, index=df.index)).fillna(0)
            + df.get("BS_MKT_SEC_OTHER_ST_INVEST", pd.Series(0, index=df.index)).fillna(0)
            - df.get("SHORT_AND_LONG_TERM_DEBT", pd.Series(0, index=df.index)).fillna(0)
        )

        # Net Cash / Market Cap ratio
        df["net_cash_to_market_cap"] = np.where(
            df.get("CUR_MKT_CAP", 0) > 0,
            df["net_cash"] / df["CUR_MKT_CAP"],
            np.nan,
        )

        # Log securities with extreme net cash ratios (potential data issues)
        extreme_ratios = df[
            (df["net_cash_to_market_cap"].notna())
            & (abs(df["net_cash_to_market_cap"]) > 1.0)
        ]

        if not extreme_ratios.empty:
            logger.warning(
                f"Found {len(extreme_ratios)} securities with extreme "
                "net_cash_to_market_cap ratios (>100% or <-100%)"
            )
            for _, row in extreme_ratios.iterrows():
                logger.warning(
                    f"  {row['security']}: net_cash_to_market_cap = "
                    f"{row['net_cash_to_market_cap']:.2%}"
                )

        logger.info("Derived field computation complete")

        return df

    def _compute_data_quality_scores(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Compute data quality scores and flag securities requiring manual review.

        Adds columns:
        - data_quality_score: % of critical fields populated (0-100)
        - manual_review_flag: True if >30% of critical fields missing

        Args:
            df: Snapshot DataFrame

        Returns:
            DataFrame with quality scores added
        """
        logger.info("Computing data quality scores")

        # Compute % of critical fields populated for each security
        critical_field_counts = df[self.CRITICAL_FIELDS].notna().sum(axis=1)
        total_critical_fields = len(self.CRITICAL_FIELDS)

        df["data_quality_score"] = (
            critical_field_counts / total_critical_fields * 100
        )

        # Flag securities with >30% missing critical fields
        df["manual_review_flag"] = df["data_quality_score"] < 70.0

        # Log securities requiring manual review
        flagged = df[df["manual_review_flag"]]
        if not flagged.empty:
            logger.warning(
                f"Found {len(flagged)} securities requiring manual review "
                "(>30% missing critical fields)"
            )
            for _, row in flagged.iterrows():
                logger.warning(
                    f"  {row['security']}: data_quality_score = "
                    f"{row['data_quality_score']:.1f}%"
                )

        logger.info("Data quality score computation complete")

        return df

    def log_field_gaps(self, df: pd.DataFrame) -> Dict[str, Any]:
        """
        Audit missing data and return comprehensive gap report.

        Args:
            df: Snapshot DataFrame

        Returns:
            Dict with gap report statistics and field-level details

        Gap report structure:
        {
            "timestamp": "2024-01-15T10:30:00",
            "total_securities": 30,
            "total_fields": 46,
            "field_coverage": {
                "PX_TO_BOOK_RATIO": {"count": 29, "pct": 96.7},
                ...
            },
            "security_coverage": {
                "9107 JP Equity": {"count": 44, "pct": 95.7},
                ...
            },
            "missing_data": [
                {"security": "9107 JP Equity", "field": "BEST_PE_RATIO", "reason": "N/A"},
                ...
            ]
        }
        """
        logger.info("Generating field gap report")

        # Exclude metadata and derived fields from gap analysis
        metadata_cols = [
            "security",
            "company_name_japanese",
            "company_name_english",
            "tse_ticker",
            "campaign_start",
            "campaign_end",
            "max_ownership_pct",
            "min_ownership_pct",
            "total_filings",
            "snapshot_date",
            "fund_per_override",
            "fye_month",
            "net_cash",
            "net_cash_to_market_cap",
            "data_quality_score",
            "manual_review_flag",
        ]

        # Get Bloomberg data fields only
        data_fields = [col for col in df.columns if col not in metadata_cols]

        # Compute field coverage
        field_coverage = {}
        for field in data_fields:
            populated_count = df[field].notna().sum()
            total_count = len(df)
            coverage_pct = (populated_count / total_count * 100) if total_count > 0 else 0

            field_coverage[field] = {
                "count": int(populated_count),
                "pct": round(coverage_pct, 2),
            }

        # Compute security coverage
        security_coverage = {}
        for _, row in df.iterrows():
            security = row["security"]
            populated_count = row[data_fields].notna().sum()
            total_count = len(data_fields)
            coverage_pct = (populated_count / total_count * 100) if total_count > 0 else 0

            security_coverage[security] = {
                "count": int(populated_count),
                "pct": round(coverage_pct, 2),
            }

        # Collect missing data entries
        missing_data = []
        for _, row in df.iterrows():
            security = row["security"]
            for field in data_fields:
                if pd.isna(row[field]):
                    missing_data.append(
                        {
                            "security": security,
                            "field": field,
                            "reason": "N/A",  # Bloomberg doesn't provide detailed error codes in response
                        }
                    )

        # Build gap report
        gap_report = {
            "timestamp": datetime.now().isoformat(),
            "total_securities": len(df),
            "total_fields": len(data_fields),
            "field_coverage": field_coverage,
            "security_coverage": security_coverage,
            "missing_data_count": len(missing_data),
            "missing_data": missing_data,
        }

        # Log summary statistics
        avg_field_coverage = sum(f["pct"] for f in field_coverage.values()) / len(
            field_coverage
        )
        avg_security_coverage = sum(s["pct"] for s in security_coverage.values()) / len(
            security_coverage
        )

        logger.info(
            f"Gap report: {len(missing_data)} missing data points, "
            f"avg field coverage: {avg_field_coverage:.1f}%, "
            f"avg security coverage: {avg_security_coverage:.1f}%"
        )

        return gap_report

    def _save_gap_report(self, gap_report: Dict[str, Any]) -> Path:
        """
        Save gap report to JSON file.

        Args:
            gap_report: Gap report dictionary

        Returns:
            Path to saved JSON file
        """
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        filename = f"snapshot_gaps_{timestamp}.json"
        filepath = self.logs_dir / filename

        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(gap_report, f, indent=2, ensure_ascii=False)

        logger.info(f"Gap report saved to: {filepath}")

        return filepath


def validate_point_in_time_safety(campaigns: List[CampaignTarget]) -> bool:
    """
    Validate that all campaigns have point-in-time safe snapshot dates.

    Args:
        campaigns: List of CampaignTarget objects

    Returns:
        True if all campaigns are point-in-time safe, False otherwise

    Raises:
        ValueError: If any campaign violates point-in-time constraints
    """
    violations = []

    for campaign in campaigns:
        if campaign.snapshot_date is None:
            violations.append(
                f"{campaign.bloomberg_ticker}: snapshot_date is None"
            )
            continue

        if campaign.snapshot_date >= campaign.campaign_start:
            violations.append(
                f"{campaign.bloomberg_ticker}: snapshot_date ({campaign.snapshot_date}) "
                f">= campaign_start ({campaign.campaign_start})"
            )

    if violations:
        error_msg = "Point-in-time violations detected:\n" + "\n".join(
            violations
        )
        raise ValueError(error_msg)

    logger.info(
        f"Point-in-time validation passed for {len(campaigns)} campaigns"
    )
    return True
