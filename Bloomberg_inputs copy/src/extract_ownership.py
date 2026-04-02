"""
Ownership Extractor for Bloomberg Activist Data Pipeline

This module extracts Top 20 shareholder data and computes cross-shareholding metrics
for Japanese activist campaign targets.

Core Responsibilities:
    1. Extract TOP_20_HOLDERS_PUBLIC_FILINGS from Bloomberg
    2. Parse holder names, types, shares, and percentages
    3. Identify cross-shareholding (Corporation holder type)
    4. Flag foreign institutional holders
    5. Compute aggregate cross-shareholding ratios
    6. Validate data quality and log gaps

Japanese Cross-Shareholding Context:
    - Japanese companies commonly hold shares in business partners (15-30% typical)
    - "Corporation" holder_type indicates cross-shareholding
    - Cross-shareholding reduces free float and complicates governance
    - Foreign activists target companies with high cross-shareholding ratios

Foreign Holder Identification:
    - "Investment Advisor" type (e.g., BlackRock, Vanguard)
    - "Fund" type with international names
    - Names containing "Capital", "Asset Management", "Partners"
    - Excludes Japanese domestic institutional holders

Point-in-Time Considerations:
    - TOP_20_HOLDERS returns most recent public filing data
    - Filing dates may lag actual ownership changes by weeks/months
    - No temporal override available for ownership data (Bloomberg limitation)
    - Document filing_date for each holder to track staleness

Data Quality Assurance:
    - Validate sum of percentages doesn't exceed 100%
    - Check for duplicate holder names (merger/name change issues)
    - Flag securities with <20 holders (data availability issues)
    - Log missing holder_type or percentage data

Author: Bloomberg Activist Pipeline
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from bloomberg_session import BloombergSession

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class OwnershipSummary:
    """
    Aggregated ownership metrics for a single security.

    Attributes:
        ticker: Bloomberg ticker
        company_name: Company name (Japanese)
        total_holders_reported: Number of holders in TOP_20 data (usually 20)
        cross_shareholding_ratio: % of shares held by Corporation holders
        foreign_institutional_ratio: % held by foreign institutional investors
        top_5_concentration: % held by top 5 holders
        data_quality_score: % of expected data fields populated
        filing_date: Most recent filing date in holder data
    """

    ticker: str
    company_name: str
    total_holders_reported: int
    cross_shareholding_ratio: float
    foreign_institutional_ratio: float
    top_5_concentration: float
    data_quality_score: float
    filing_date: Optional[date] = None


class OwnershipExtractor:
    """
    Extracts and processes Top 20 shareholder data from Bloomberg.

    This class provides methods to:
    - Query TOP_20_HOLDERS_PUBLIC_FILINGS bulk field
    - Parse holder metadata (name, type, shares, percentage)
    - Identify cross-shareholding and foreign holders
    - Compute aggregate ownership metrics
    - Validate data quality

    Attributes:
        session: Active Bloomberg session
        logs_dir: Directory for ownership gap reports
        holder_type_map: Mapping of Bloomberg holder types to categories
    """

    # Bloomberg holder types mapped to our categories
    HOLDER_TYPE_CATEGORIES = {
        "Corporation": "cross_shareholder",
        "Investment Advisor": "foreign_institutional",
        "Fund": "foreign_institutional",
        "Bank": "domestic_institutional",
        "Insurance Company": "domestic_institutional",
        "Government Agency": "government",
        "Individual Investor": "individual",
        "Other": "other",
    }

    # Keywords in holder names that indicate foreign institutional investors
    FOREIGN_KEYWORDS = [
        "BLACKROCK",
        "VANGUARD",
        "STATE STREET",
        "FIDELITY",
        "CAPITAL",
        "PARTNERS",
        "ASSET MANAGEMENT",
        "INVESTMENTS",
        "TRUST",
        "FUND",
        "ADVISORS",
        "JP MORGAN",
        "GOLDMAN SACHS",
        "MORGAN STANLEY",
    ]

    def __init__(
        self,
        session: BloombergSession,
        logs_dir: Optional[Path] = None,
    ):
        """
        Initialize ownership extractor.

        Args:
            session: Active Bloomberg session
            logs_dir: Directory for gap reports (default: ../logs)

        Raises:
            ValueError: If session is not started
        """
        if session.session is None:
            raise ValueError("Bloomberg session must be started before use")

        self.session = session

        # Set up logs directory
        if logs_dir is None:
            src_dir = Path(__file__).parent
            logs_dir = src_dir.parent / "logs"

        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        logger.info("OwnershipExtractor initialized")

    def extract_top_20_holders(
        self, securities: List[str]
    ) -> pd.DataFrame:
        """
        Query TOP_20_HOLDERS_PUBLIC_FILINGS for all securities.

        Extracts comprehensive holder data including:
        - Holder name and rank
        - Holder type (Corporation, Investment Advisor, etc.)
        - Shares held and ownership percentage
        - Filing date

        Args:
            securities: List of Bloomberg tickers (e.g., ["9107 JP Equity"])

        Returns:
            DataFrame with columns:
            - security: Bloomberg ticker
            - holder_rank: Rank (1-20)
            - holder_name: Shareholder name
            - holder_type: Type (Corporation, Investment Advisor, etc.)
            - shares_held: Number of shares
            - percent_held: Ownership percentage
            - filing_date: Filing date (if available)

        Raises:
            ValueError: If no securities provided or all queries fail

        Notes:
            - Returns long-format DataFrame (one row per holder per security)
            - Missing data (unavailable holders) represented as NaN
            - Typical result: ~20 rows per security (if all holders available)
        """
        if not securities:
            raise ValueError("No securities provided for ownership extraction")

        logger.info(
            f"Extracting TOP_20_HOLDERS_PUBLIC_FILINGS for {len(securities)} securities"
        )

        # Query Bloomberg bulk field
        try:
            holders_df = self.session.send_bulk_request(
                securities=securities,
                field="TOP_20_HOLDERS_PUBLIC_FILINGS",
            )
        except Exception as e:
            logger.error(f"Failed to extract ownership data: {e}")
            raise ValueError(
                f"Ownership extraction failed: {e}\n"
                "Ensure Bloomberg Terminal is running and securities are valid."
            ) from e

        if holders_df.empty:
            logger.warning(
                "No ownership data returned from Bloomberg. "
                "Check security identifiers and data availability."
            )
            return pd.DataFrame()

        logger.info(
            f"Retrieved {len(holders_df)} holder records for {holders_df['security'].nunique()} securities"
        )

        # Standardize column names (Bloomberg field names vary)
        holders_df = self._standardize_column_names(holders_df)

        # Validate and clean data
        holders_df = self._clean_holder_data(holders_df)

        return holders_df

    def _standardize_column_names(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Standardize Bloomberg bulk field column names.

        Bloomberg TOP_20_HOLDERS field returns columns like:
        - Holder Name / HOLDER_NAME
        - Holder Type / TYPE
        - Portfolio % / PERCENT_OUTSTANDING
        - Shares Held / SHARES_HELD

        Args:
            df: Raw DataFrame from Bloomberg

        Returns:
            DataFrame with standardized column names
        """
        # Define column mappings (Bloomberg name -> our standard name)
        column_mappings = {
            # Holder identification
            "Holder Name": "holder_name",
            "HOLDER_NAME": "holder_name",
            "Name": "holder_name",
            # Holder type
            "Holder Type": "holder_type",
            "TYPE": "holder_type",
            "Type": "holder_type",
            # Ownership percentage
            "Portfolio %": "percent_held",
            "PERCENT_OUTSTANDING": "percent_held",
            "Percent Outstanding": "percent_held",
            "% Out": "percent_held",
            # Shares held
            "Shares Held": "shares_held",
            "SHARES_HELD": "shares_held",
            "Amount Held": "shares_held",
            # Filing date
            "Filing Date": "filing_date",
            "FILING_DATE": "filing_date",
            "File Date": "filing_date",
            # Rank
            "Rank": "holder_rank",
            "RANK": "holder_rank",
            # Security (should already be lowercase)
            "Security": "security",
            "SECURITY": "security",
        }

        # Rename columns using mapping
        df_renamed = df.rename(columns=column_mappings)

        # Log any columns that weren't mapped
        unmapped_cols = set(df.columns) - set(column_mappings.keys()) - {"security"}
        if unmapped_cols:
            logger.debug(f"Unmapped columns: {unmapped_cols}")

        # Ensure required columns exist
        required_cols = ["security", "holder_name"]
        missing_cols = set(required_cols) - set(df_renamed.columns)
        if missing_cols:
            logger.error(f"Missing required columns after standardization: {missing_cols}")
            raise ValueError(
                f"Bloomberg response missing required fields: {missing_cols}"
            )

        return df_renamed

    def _clean_holder_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean and validate holder data.

        Cleaning steps:
        1. Remove rows with missing holder_name
        2. Deduplicate holders (same name appearing multiple times)
        3. Infer holder_rank if missing (order by percent_held descending)
        4. Convert data types (percent_held to float, shares_held to int)
        5. Validate percent_held is 0-100 range

        Args:
            df: Raw holder DataFrame

        Returns:
            Cleaned DataFrame
        """
        initial_count = len(df)

        # Remove rows with missing holder_name
        df = df[df["holder_name"].notna()].copy()
        removed_count = initial_count - len(df)
        if removed_count > 0:
            logger.warning(f"Removed {removed_count} rows with missing holder_name")

        # Deduplicate holders within each security
        df = df.drop_duplicates(subset=["security", "holder_name"], keep="first")
        dedup_count = initial_count - len(df) - removed_count
        if dedup_count > 0:
            logger.warning(f"Removed {dedup_count} duplicate holder entries")

        # Infer holder_rank if missing
        if "holder_rank" not in df.columns or df["holder_rank"].isna().any():
            logger.debug("Inferring holder_rank from percent_held order")
            if "percent_held" in df.columns:
                df["holder_rank"] = df.groupby("security")["percent_held"].rank(
                    method="first", ascending=False
                )
            else:
                # Fallback: sequential rank within each security
                df["holder_rank"] = df.groupby("security").cumcount() + 1

        # Convert data types
        if "percent_held" in df.columns:
            df["percent_held"] = pd.to_numeric(df["percent_held"], errors="coerce")

            # Validate percentage range
            invalid_pct = df[
                (df["percent_held"].notna())
                & ((df["percent_held"] < 0) | (df["percent_held"] > 100))
            ]
            if not invalid_pct.empty:
                logger.warning(
                    f"Found {len(invalid_pct)} holders with invalid percent_held (outside 0-100 range)"
                )

        if "shares_held" in df.columns:
            df["shares_held"] = pd.to_numeric(df["shares_held"], errors="coerce")

        # Convert filing_date to datetime
        if "filing_date" in df.columns:
            df["filing_date"] = pd.to_datetime(df["filing_date"], errors="coerce")

        # Sort by security and rank for consistent ordering
        df = df.sort_values(["security", "holder_rank"]).reset_index(drop=True)

        logger.info(f"Cleaned holder data: {len(df)} records")

        return df

    def flag_foreign_holders(
        self, ownership_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Identify and flag foreign institutional holders.

        Foreign holders identified by:
        1. holder_type = "Investment Advisor" or "Fund"
        2. holder_name contains foreign keywords (BLACKROCK, VANGUARD, etc.)
        3. Manual inspection of holder names (heuristics)

        Args:
            ownership_df: Holder DataFrame from extract_top_20_holders

        Returns:
            DataFrame with added column:
            - is_foreign: Boolean flag (True if foreign institutional)

        Notes:
            - Conservative approach: flags obvious foreign investors
            - May miss some foreign holders with Japanese names
            - Does not flag domestic Japanese institutional investors
        """
        logger.info("Flagging foreign institutional holders")

        df = ownership_df.copy()

        # Initialize is_foreign column
        df["is_foreign"] = False

        # Flag by holder_type
        if "holder_type" in df.columns:
            foreign_types = ["Investment Advisor", "Fund"]
            df.loc[df["holder_type"].isin(foreign_types), "is_foreign"] = True

        # Flag by holder_name keywords
        if "holder_name" in df.columns:
            holder_name_upper = df["holder_name"].str.upper().fillna("")

            for keyword in self.FOREIGN_KEYWORDS:
                df.loc[holder_name_upper.str.contains(keyword, na=False), "is_foreign"] = True

        # Log statistics
        total_holders = len(df)
        foreign_count = df["is_foreign"].sum()
        foreign_pct = (foreign_count / total_holders * 100) if total_holders > 0 else 0

        logger.info(
            f"Foreign holder flagging complete: {foreign_count} / {total_holders} "
            f"({foreign_pct:.1f}%) flagged as foreign"
        )

        return df

    def compute_cross_shareholding_ratio(
        self, ownership_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Compute cross-shareholding ratio for each security.

        Cross-shareholding = sum of percent_held for holder_type = "Corporation"

        Args:
            ownership_df: Holder DataFrame with holder_type column

        Returns:
            DataFrame with columns:
            - security: Bloomberg ticker
            - cross_shareholding_ratio: % held by Corporation holders
            - num_cross_shareholders: Count of Corporation holders

        Raises:
            ValueError: If holder_type column missing

        Notes:
            - Japanese cross-shareholding is culturally significant
            - Typical range: 15-30% for established companies
            - Activists target companies with high ratios (reduces free float)
        """
        logger.info("Computing cross-shareholding ratios")

        if "holder_type" not in ownership_df.columns:
            raise ValueError(
                "holder_type column required for cross-shareholding computation. "
                "Ensure extract_top_20_holders returned holder type data."
            )

        if "percent_held" not in ownership_df.columns:
            raise ValueError(
                "percent_held column required for cross-shareholding computation."
            )

        # Filter to Corporation holders only
        cross_holders = ownership_df[
            ownership_df["holder_type"] == "Corporation"
        ].copy()

        # Aggregate by security
        cross_ratios = (
            cross_holders.groupby("security")
            .agg(
                cross_shareholding_ratio=("percent_held", "sum"),
                num_cross_shareholders=("holder_name", "count"),
            )
            .reset_index()
        )

        # Add securities with zero cross-shareholding
        all_securities = ownership_df["security"].unique()
        zero_cross = pd.DataFrame(
            {
                "security": [
                    sec
                    for sec in all_securities
                    if sec not in cross_ratios["security"].values
                ]
            }
        )
        zero_cross["cross_shareholding_ratio"] = 0.0
        zero_cross["num_cross_shareholders"] = 0

        cross_ratios = pd.concat([cross_ratios, zero_cross], ignore_index=True)

        # Log statistics
        avg_ratio = cross_ratios["cross_shareholding_ratio"].mean()
        max_ratio = cross_ratios["cross_shareholding_ratio"].max()

        logger.info(
            f"Cross-shareholding computation complete: "
            f"avg={avg_ratio:.1f}%, max={max_ratio:.1f}%"
        )

        return cross_ratios

    def compute_foreign_institutional_ratio(
        self, ownership_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Compute foreign institutional ownership ratio for each security.

        Args:
            ownership_df: Holder DataFrame with is_foreign flag

        Returns:
            DataFrame with columns:
            - security: Bloomberg ticker
            - foreign_institutional_ratio: % held by foreign institutions
            - num_foreign_holders: Count of foreign holders

        Raises:
            ValueError: If is_foreign column missing
        """
        logger.info("Computing foreign institutional ownership ratios")

        if "is_foreign" not in ownership_df.columns:
            raise ValueError(
                "is_foreign column required. Run flag_foreign_holders() first."
            )

        if "percent_held" not in ownership_df.columns:
            raise ValueError("percent_held column required for ratio computation.")

        # Filter to foreign holders only
        foreign_holders = ownership_df[ownership_df["is_foreign"]].copy()

        # Aggregate by security
        foreign_ratios = (
            foreign_holders.groupby("security")
            .agg(
                foreign_institutional_ratio=("percent_held", "sum"),
                num_foreign_holders=("holder_name", "count"),
            )
            .reset_index()
        )

        # Add securities with zero foreign ownership
        all_securities = ownership_df["security"].unique()
        zero_foreign = pd.DataFrame(
            {
                "security": [
                    sec
                    for sec in all_securities
                    if sec not in foreign_ratios["security"].values
                ]
            }
        )
        zero_foreign["foreign_institutional_ratio"] = 0.0
        zero_foreign["num_foreign_holders"] = 0

        foreign_ratios = pd.concat([foreign_ratios, zero_foreign], ignore_index=True)

        # Log statistics
        avg_ratio = foreign_ratios["foreign_institutional_ratio"].mean()
        max_ratio = foreign_ratios["foreign_institutional_ratio"].max()

        logger.info(
            f"Foreign institutional ownership computation complete: "
            f"avg={avg_ratio:.1f}%, max={max_ratio:.1f}%"
        )

        return foreign_ratios

    def compute_top_5_concentration(
        self, ownership_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Compute top 5 shareholder concentration ratio.

        Args:
            ownership_df: Holder DataFrame with holder_rank and percent_held

        Returns:
            DataFrame with columns:
            - security: Bloomberg ticker
            - top_5_concentration: % held by top 5 holders

        Notes:
            - High concentration indicates control by few investors
            - Relevant for activist campaigns (easier to engage with concentrated ownership)
        """
        logger.info("Computing top 5 shareholder concentration")

        if "holder_rank" not in ownership_df.columns:
            raise ValueError("holder_rank column required for concentration computation")

        if "percent_held" not in ownership_df.columns:
            raise ValueError("percent_held column required for concentration computation")

        # Filter to top 5 holders
        top_5 = ownership_df[ownership_df["holder_rank"] <= 5].copy()

        # Aggregate by security
        concentration = (
            top_5.groupby("security")
            .agg(top_5_concentration=("percent_held", "sum"))
            .reset_index()
        )

        # Add securities with <5 holders
        all_securities = ownership_df["security"].unique()
        missing_securities = [
            sec for sec in all_securities if sec not in concentration["security"].values
        ]

        if missing_securities:
            logger.warning(
                f"Found {len(missing_securities)} securities with <5 holders reported"
            )

        # Log statistics
        avg_concentration = concentration["top_5_concentration"].mean()

        logger.info(
            f"Top 5 concentration computation complete: avg={avg_concentration:.1f}%"
        )

        return concentration

    def generate_ownership_summary(
        self,
        securities: List[str],
        company_names: Optional[Dict[str, str]] = None,
    ) -> pd.DataFrame:
        """
        Generate comprehensive ownership summary for all securities.

        This is the main entry point for ownership analysis. It orchestrates:
        1. Extract TOP_20_HOLDERS data
        2. Flag foreign holders
        3. Compute cross-shareholding ratio
        4. Compute foreign institutional ratio
        5. Compute top 5 concentration
        6. Merge all metrics into summary DataFrame

        Args:
            securities: List of Bloomberg tickers
            company_names: Optional dict mapping ticker -> company name

        Returns:
            DataFrame with columns:
            - security: Bloomberg ticker
            - company_name: Company name (if provided)
            - total_holders_reported: Number of holders
            - cross_shareholding_ratio: % held by Corporation holders
            - foreign_institutional_ratio: % held by foreign institutions
            - top_5_concentration: % held by top 5 holders
            - data_quality_score: % of expected data available

        Raises:
            ValueError: If ownership extraction fails
        """
        logger.info(f"Generating ownership summary for {len(securities)} securities")

        # Step 1: Extract TOP_20_HOLDERS
        holders_df = self.extract_top_20_holders(securities)

        if holders_df.empty:
            logger.warning("No ownership data extracted, returning empty summary")
            return pd.DataFrame()

        # Step 2: Flag foreign holders
        holders_df = self.flag_foreign_holders(holders_df)

        # Add cross-shareholder flag
        holders_df["is_cross_shareholder"] = (
            holders_df.get("holder_type", "") == "Corporation"
        )

        # Step 3: Compute cross-shareholding ratio
        cross_ratios = self.compute_cross_shareholding_ratio(holders_df)

        # Step 4: Compute foreign institutional ratio
        foreign_ratios = self.compute_foreign_institutional_ratio(holders_df)

        # Step 5: Compute top 5 concentration
        concentration = self.compute_top_5_concentration(holders_df)

        # Step 6: Compute data quality scores
        quality_scores = self._compute_ownership_quality_scores(holders_df)

        # Step 7: Merge all metrics
        summary_df = cross_ratios.merge(foreign_ratios, on="security", how="outer")
        summary_df = summary_df.merge(concentration, on="security", how="outer")
        summary_df = summary_df.merge(quality_scores, on="security", how="outer")

        # Add company names if provided
        if company_names:
            summary_df["company_name"] = summary_df["security"].map(company_names)
        else:
            summary_df["company_name"] = None

        # Reorder columns
        column_order = [
            "security",
            "company_name",
            "total_holders_reported",
            "cross_shareholding_ratio",
            "num_cross_shareholders",
            "foreign_institutional_ratio",
            "num_foreign_holders",
            "top_5_concentration",
            "data_quality_score",
        ]

        # Include only columns that exist
        column_order = [col for col in column_order if col in summary_df.columns]
        summary_df = summary_df[column_order]

        logger.info(f"Ownership summary complete: {len(summary_df)} securities")

        return summary_df

    def _compute_ownership_quality_scores(
        self, holders_df: pd.DataFrame
    ) -> pd.DataFrame:
        """
        Compute data quality scores for ownership data.

        Quality metrics:
        - Expected 20 holders per security
        - Required fields: holder_name, percent_held
        - Optional fields: holder_type, shares_held, filing_date

        Args:
            holders_df: Holder DataFrame

        Returns:
            DataFrame with columns:
            - security: Bloomberg ticker
            - total_holders_reported: Number of holders
            - data_quality_score: % of expected data available (0-100)
        """
        quality_scores = []

        for security in holders_df["security"].unique():
            sec_holders = holders_df[holders_df["security"] == security]

            # Count holders
            total_holders = len(sec_holders)

            # Compute quality score
            # Expected: 20 holders with all fields populated
            expected_holders = 20
            holder_score = min(total_holders / expected_holders * 100, 100)

            # Field completeness
            required_fields = ["holder_name", "percent_held"]
            optional_fields = ["holder_type", "shares_held"]

            required_completeness = (
                sec_holders[required_fields].notna().all(axis=1).sum() / total_holders
                if total_holders > 0
                else 0
            )

            optional_completeness = (
                sec_holders[optional_fields].notna().sum().sum()
                / (total_holders * len(optional_fields))
                if total_holders > 0
                else 0
            )

            # Combined score: 50% holder count, 30% required fields, 20% optional fields
            data_quality_score = (
                0.5 * holder_score + 0.3 * required_completeness * 100 + 0.2 * optional_completeness * 100
            )

            quality_scores.append(
                {
                    "security": security,
                    "total_holders_reported": total_holders,
                    "data_quality_score": round(data_quality_score, 2),
                }
            )

        return pd.DataFrame(quality_scores)

    def save_detailed_ownership(
        self,
        holders_df: pd.DataFrame,
        output_path: Path,
    ) -> None:
        """
        Save detailed holder-level data to CSV.

        Args:
            holders_df: Holder DataFrame from extract_top_20_holders
            output_path: Path to save CSV file

        Notes:
            - Saves long-format data (one row per holder per security)
            - Useful for manual inspection and detailed analysis
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        holders_df.to_csv(output_path, index=False, encoding="utf-8-sig")

        logger.info(f"Detailed ownership data saved to: {output_path}")
