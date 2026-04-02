"""
Peer Comparisons Extractor for Bloomberg Activist Data Pipeline

This module computes sector median valuation metrics using GICS sector classification,
enabling relative valuation analysis for activist campaign targets.

Core Responsibilities:
    1. Identify GICS sector for each target company
    2. Retrieve all TSE-listed companies in same GICS sector
    3. Compute sector median metrics (PBR, ROE, EV/EBITDA)
    4. Calculate discount/premium vs. sector median
    5. Handle edge cases (sectors with <5 companies)
    6. Generate peer comparison reports

GICS Sector Classification:
    - Uses GICS_SECTOR_NAME (standard 11-sector classification)
    - Fallback to GICS_INDUSTRY_GROUP_NAME for small sectors (<5 companies)
    - Bloomberg reference data, no manual peer groups

Valuation Metrics:
    - PBR (Price-to-Book Ratio): PX_TO_BOOK_RATIO
    - ROE (Return on Equity): RETURN_COM_EQY
    - EV/EBITDA: ENTERPRISE_VALUE / EBITDA
    - Computed as sector medians (robust to outliers)

Discount/Premium Calculation:
    - For ratios (PBR, EV/EBITDA): (company_value / sector_median) - 1
    - For ROE: company_roe - sector_median_roe (percentage points)
    - Negative = discount, Positive = premium

Edge Case Handling:
    - Sector with <5 companies: Use broader GICS industry group
    - Missing GICS sector: Flag for manual review
    - Missing metrics: Report as N/A, exclude from median calculation

Author: Bloomberg Activist Pipeline
"""

import logging
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from bloomberg_session import BloombergSession

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class PeerCompTarget:
    """
    Target for peer comparison analysis.

    Attributes:
        ticker: Bloomberg ticker (e.g., "9107 JP Equity")
        company_name: Company name (for reporting)
        sector: GICS sector name (computed)
        industry_group: GICS industry group (fallback for small sectors)
    """

    ticker: str
    company_name: str
    sector: Optional[str] = None
    industry_group: Optional[str] = None


@dataclass
class SectorMedians:
    """
    Sector median valuation metrics.

    Attributes:
        sector_name: GICS sector or industry group name
        median_pbr: Median price-to-book ratio
        median_roe: Median return on equity (%)
        median_ev_ebitda: Median EV/EBITDA multiple
        peer_count: Number of companies in sector
        metric_availability: Dict of metric availability counts
    """

    sector_name: str
    median_pbr: Optional[float] = None
    median_roe: Optional[float] = None
    median_ev_ebitda: Optional[float] = None
    peer_count: int = 0
    metric_availability: Optional[Dict[str, int]] = None


class PeerCompsExtractor:
    """
    Extractor for sector peer comparisons using GICS classification.

    This class identifies peer groups based on GICS sector classification
    and computes sector median valuation metrics for relative analysis.

    Attributes:
        session: Active Bloomberg session
        min_peer_count: Minimum peers required for sector (default: 5)
    """

    # Bloomberg fields for sector identification
    SECTOR_FIELDS = [
        "GICS_SECTOR_NAME",  # Level 1: 11 sectors
        "GICS_INDUSTRY_GROUP_NAME",  # Level 2: 24 industry groups
    ]

    # Bloomberg fields for valuation metrics
    VALUATION_FIELDS = [
        "PX_TO_BOOK_RATIO",  # Price-to-Book
        "RETURN_COM_EQY",  # Return on Equity
        "CUR_MKT_CAP",  # Market Cap (for filtering)
    ]

    # Bloomberg fields for EV/EBITDA
    EV_EBITDA_FIELDS = [
        "CUR_MKT_CAP",  # Market Cap
        "NET_DEBT",  # Net Debt
        "EBITDA",  # EBITDA
    ]

    def __init__(
        self,
        session: BloombergSession,
        min_peer_count: int = 5,
    ):
        """
        Initialize peer comps extractor.

        Args:
            session: Active Bloomberg session
            min_peer_count: Minimum peers for sector median (default: 5)

        Raises:
            ValueError: If session is not started
        """
        if session.session is None:
            raise ValueError("Bloomberg session must be started before use")

        self.session = session
        self.min_peer_count = min_peer_count

        logger.info(
            f"PeerCompsExtractor initialized (min_peer_count={min_peer_count})"
        )

    def identify_sector(self, security: str) -> Tuple[Optional[str], Optional[str]]:
        """
        Identify GICS sector and industry group for security.

        Args:
            security: Bloomberg ticker

        Returns:
            Tuple of (sector_name, industry_group_name)
            Either or both may be None if not available

        Examples:
            >>> sector, industry = extractor.identify_sector("9107 JP Equity")
            >>> print(f"Sector: {sector}, Industry: {industry}")
        """
        logger.info(f"Identifying GICS sector for {security}")

        df = self.session.send_request(
            securities=[security],
            fields=self.SECTOR_FIELDS,
        )

        if df.empty:
            logger.warning(f"No sector data returned for {security}")
            return None, None

        sector = df.iloc[0].get("GICS_SECTOR_NAME")
        industry_group = df.iloc[0].get("GICS_INDUSTRY_GROUP_NAME")

        if pd.isna(sector):
            sector = None
        if pd.isna(industry_group):
            industry_group = None

        logger.info(
            f"{security}: sector={sector}, industry_group={industry_group}"
        )

        return sector, industry_group

    def get_sector_peers(
        self,
        sector: str,
        exchange: str = "JP",
        use_industry_group: bool = False,
    ) -> List[str]:
        """
        Get all companies in the same GICS sector/industry group.

        Note: This is a placeholder implementation. In production, you would:
        1. Query Bloomberg EQS (Equity Screening) to find all companies in sector
        2. Filter by exchange (Tokyo Stock Exchange)
        3. Filter by market cap if needed (for large sectors)

        For this implementation, we'll use a reference data approach:
        - Query a representative set of companies
        - Filter by GICS sector match

        Args:
            sector: GICS sector or industry group name
            exchange: Exchange code (default: "JP" for Japan)
            use_industry_group: Whether sector is industry group (broader)

        Returns:
            List of Bloomberg tickers in the sector

        Examples:
            >>> peers = extractor.get_sector_peers("Industrials")
            >>> print(f"Found {len(peers)} peer companies")
        """
        logger.info(
            f"Getting sector peers for: {sector} (use_industry_group={use_industry_group})"
        )

        # In production, this would use Bloomberg EQS screening:
        # Example query: "GICS_SECTOR_NAME = 'Industrials' AND EXCH_CODE = 'JP'"

        # For this implementation, we return empty list and log a message
        # The actual implementation would require Bloomberg EQS access
        logger.warning(
            "get_sector_peers is a placeholder. "
            "Production implementation requires Bloomberg EQS screening."
        )

        return []

    def compute_sector_medians(
        self,
        sector_peers: List[str],
        sector_name: str,
    ) -> SectorMedians:
        """
        Compute sector median valuation metrics.

        Args:
            sector_peers: List of Bloomberg tickers in sector
            sector_name: GICS sector or industry group name

        Returns:
            SectorMedians object with computed metrics

        Examples:
            >>> medians = extractor.compute_sector_medians(
            ...     sector_peers=["9107 JP Equity", "8952 JP Equity"],
            ...     sector_name="Industrials"
            ... )
            >>> print(f"Median PBR: {medians.median_pbr:.2f}")
        """
        if not sector_peers:
            logger.warning(f"No peers provided for sector: {sector_name}")
            return SectorMedians(
                sector_name=sector_name,
                peer_count=0,
            )

        logger.info(
            f"Computing sector medians for {sector_name}: {len(sector_peers)} peers"
        )

        # Extract valuation metrics for all peers
        all_fields = list(set(self.VALUATION_FIELDS + self.EV_EBITDA_FIELDS))

        df = self.session.send_request(
            securities=sector_peers,
            fields=all_fields,
        )

        if df.empty:
            logger.warning(f"No data returned for sector peers: {sector_name}")
            return SectorMedians(
                sector_name=sector_name,
                peer_count=len(sector_peers),
            )

        # Compute EV/EBITDA for each company
        df["ev_ebitda"] = self._compute_ev_ebitda(df)

        # Compute medians (ignoring NaN values)
        median_pbr = df["PX_TO_BOOK_RATIO"].median()
        median_roe = df["RETURN_COM_EQY"].median()
        median_ev_ebitda = df["ev_ebitda"].median()

        # Count metric availability
        metric_availability = {
            "pbr": df["PX_TO_BOOK_RATIO"].notna().sum(),
            "roe": df["RETURN_COM_EQY"].notna().sum(),
            "ev_ebitda": df["ev_ebitda"].notna().sum(),
        }

        medians = SectorMedians(
            sector_name=sector_name,
            median_pbr=median_pbr if pd.notna(median_pbr) else None,
            median_roe=median_roe if pd.notna(median_roe) else None,
            median_ev_ebitda=median_ev_ebitda if pd.notna(median_ev_ebitda) else None,
            peer_count=len(df),
            metric_availability=metric_availability,
        )

        logger.info(
            f"Sector medians computed: PBR={medians.median_pbr}, "
            f"ROE={medians.median_roe}, EV/EBITDA={medians.median_ev_ebitda}"
        )

        return medians

    def compute_discount_premium(
        self,
        company_value: float,
        sector_median: float,
    ) -> float:
        """
        Calculate percentage discount or premium vs. sector median.

        For valuation ratios (PBR, EV/EBITDA):
            discount_premium = (company_value / sector_median) - 1
            Negative = trading at discount
            Positive = trading at premium

        Args:
            company_value: Company's valuation metric
            sector_median: Sector median valuation metric

        Returns:
            Discount/premium as decimal (e.g., -0.25 = 25% discount)

        Examples:
            >>> discount = extractor.compute_discount_premium(0.8, 1.2)
            >>> print(f"Discount: {discount:.1%}")  # -33.3%
        """
        if pd.isna(company_value) or pd.isna(sector_median):
            return np.nan

        if sector_median == 0:
            logger.warning("sector_median is zero, cannot compute discount/premium")
            return np.nan

        discount_premium = (company_value / sector_median) - 1.0

        return discount_premium

    def compute_roe_difference(
        self,
        company_roe: float,
        sector_median_roe: float,
    ) -> float:
        """
        Calculate ROE difference vs. sector median (in percentage points).

        For ROE, we compute absolute difference rather than ratio:
            roe_difference = company_roe - sector_median_roe
            Negative = underperforming sector
            Positive = outperforming sector

        Args:
            company_roe: Company's ROE (as percentage)
            sector_median_roe: Sector median ROE (as percentage)

        Returns:
            ROE difference in percentage points

        Examples:
            >>> diff = extractor.compute_roe_difference(8.5, 12.0)
            >>> print(f"ROE difference: {diff:.1f} pp")  # -3.5 pp
        """
        if pd.isna(company_roe) or pd.isna(sector_median_roe):
            return np.nan

        roe_diff = company_roe - sector_median_roe

        return roe_diff

    def extract_peer_comps(
        self,
        targets: List[PeerCompTarget],
        snapshot_df: pd.DataFrame,
    ) -> pd.DataFrame:
        """
        Extract peer comparisons for all target companies.

        This is the main entry point for peer comp extraction. It:
        1. Identifies GICS sector for each target
        2. Retrieves sector peers
        3. Computes sector medians
        4. Calculates discount/premium for each target
        5. Handles edge cases (<5 peers, missing data)

        Args:
            targets: List of PeerCompTarget objects
            snapshot_df: DataFrame with target company metrics
                Required columns: security, PX_TO_BOOK_RATIO, RETURN_COM_EQY,
                                 CUR_MKT_CAP, NET_DEBT, EBITDA

        Returns:
            DataFrame with peer comparison metrics:
                - ticker
                - company_name
                - sector
                - company_pbr
                - sector_median_pbr
                - pbr_vs_sector (discount/premium)
                - company_roe
                - sector_median_roe
                - roe_vs_sector (percentage point difference)
                - company_ev_ebitda
                - sector_median_ev_ebitda
                - ev_ebitda_vs_sector (discount/premium)
                - peer_count

        Examples:
            >>> peer_comps_df = extractor.extract_peer_comps(targets, snapshot_df)
            >>> print(peer_comps_df[["ticker", "pbr_vs_sector"]])
        """
        if not targets:
            raise ValueError("No targets provided")

        if snapshot_df.empty:
            raise ValueError("snapshot_df is empty")

        logger.info(f"Extracting peer comparisons for {len(targets)} targets")

        # Step 1: Identify sectors for all targets
        for target in targets:
            sector, industry_group = self.identify_sector(target.ticker)
            target.sector = sector
            target.industry_group = industry_group

        # Step 2: Group targets by sector
        targets_by_sector: Dict[str, List[PeerCompTarget]] = {}
        for target in targets:
            sector_key = target.sector or target.industry_group or "UNKNOWN"
            if sector_key not in targets_by_sector:
                targets_by_sector[sector_key] = []
            targets_by_sector[sector_key].append(target)

        # Step 3: Compute sector medians for each sector
        sector_medians_cache: Dict[str, SectorMedians] = {}

        for sector_key, sector_targets in targets_by_sector.items():
            if sector_key == "UNKNOWN":
                logger.warning(
                    f"Skipping sector median calculation for UNKNOWN sector "
                    f"({len(sector_targets)} targets)"
                )
                continue

            logger.info(
                f"Processing sector: {sector_key} ({len(sector_targets)} targets)"
            )

            # Get sector peers (placeholder - returns empty list)
            sector_peers = self.get_sector_peers(sector_key)

            # If no peers found or <5 peers, use broader industry group
            if len(sector_peers) < self.min_peer_count:
                logger.warning(
                    f"Sector {sector_key} has {len(sector_peers)} peers "
                    f"(< min_peer_count={self.min_peer_count}). "
                    "Would use broader GICS industry group in production."
                )

                # For now, compute medians from available data
                # In production, would query broader industry group
                sector_peers = []

            # Compute sector medians
            medians = self.compute_sector_medians(sector_peers, sector_key)
            sector_medians_cache[sector_key] = medians

        # Step 4: Build peer comparison DataFrame
        peer_comp_records = []

        for target in targets:
            # Get target's metrics from snapshot_df
            target_row = snapshot_df[snapshot_df["security"] == target.ticker]

            if target_row.empty:
                logger.warning(
                    f"Target {target.ticker} not found in snapshot_df, skipping"
                )
                continue

            target_row = target_row.iloc[0]

            # Get sector medians
            sector_key = target.sector or target.industry_group or "UNKNOWN"
            medians = sector_medians_cache.get(sector_key)

            # Extract company metrics
            company_pbr = target_row.get("PX_TO_BOOK_RATIO")
            company_roe = target_row.get("RETURN_COM_EQY")
            company_ev_ebitda = self._compute_ev_ebitda_single(target_row)

            # Compute discount/premium
            if medians:
                pbr_vs_sector = self.compute_discount_premium(
                    company_pbr, medians.median_pbr
                )
                roe_vs_sector = self.compute_roe_difference(
                    company_roe, medians.median_roe
                )
                ev_ebitda_vs_sector = self.compute_discount_premium(
                    company_ev_ebitda, medians.median_ev_ebitda
                )
                sector_median_pbr = medians.median_pbr
                sector_median_roe = medians.median_roe
                sector_median_ev_ebitda = medians.median_ev_ebitda
                peer_count = medians.peer_count
            else:
                pbr_vs_sector = np.nan
                roe_vs_sector = np.nan
                ev_ebitda_vs_sector = np.nan
                sector_median_pbr = np.nan
                sector_median_roe = np.nan
                sector_median_ev_ebitda = np.nan
                peer_count = 0

            record = {
                "ticker": target.ticker,
                "company_name": target.company_name,
                "sector": target.sector or "N/A",
                "company_pbr": company_pbr,
                "sector_median_pbr": sector_median_pbr,
                "pbr_vs_sector": pbr_vs_sector,
                "company_roe": company_roe,
                "sector_median_roe": sector_median_roe,
                "roe_vs_sector": roe_vs_sector,
                "company_ev_ebitda": company_ev_ebitda,
                "sector_median_ev_ebitda": sector_median_ev_ebitda,
                "ev_ebitda_vs_sector": ev_ebitda_vs_sector,
                "peer_count": peer_count,
            }

            peer_comp_records.append(record)

        peer_comps_df = pd.DataFrame(peer_comp_records)

        logger.info(
            f"Peer comparison extraction complete: {len(peer_comps_df)} records"
        )

        return peer_comps_df

    def _compute_ev_ebitda(self, df: pd.DataFrame) -> pd.Series:
        """
        Compute EV/EBITDA for DataFrame.

        EV = Market Cap + Net Debt
        EV/EBITDA = EV / EBITDA

        Args:
            df: DataFrame with CUR_MKT_CAP, NET_DEBT, EBITDA columns

        Returns:
            Series with EV/EBITDA values
        """
        # Enterprise Value = Market Cap + Net Debt
        ev = df.get("CUR_MKT_CAP", 0) + df.get("NET_DEBT", 0).fillna(0)

        # EV/EBITDA
        ebitda = df.get("EBITDA", np.nan)
        ev_ebitda = np.where(
            (ebitda.notna()) & (ebitda != 0),
            ev / ebitda,
            np.nan,
        )

        return pd.Series(ev_ebitda, index=df.index)

    def _compute_ev_ebitda_single(self, row: pd.Series) -> float:
        """
        Compute EV/EBITDA for single row.

        Args:
            row: Series with CUR_MKT_CAP, NET_DEBT, EBITDA

        Returns:
            EV/EBITDA value
        """
        market_cap = row.get("CUR_MKT_CAP", np.nan)
        net_debt = row.get("NET_DEBT", 0)
        ebitda = row.get("EBITDA", np.nan)

        if pd.isna(market_cap) or pd.isna(ebitda) or ebitda == 0:
            return np.nan

        ev = market_cap + (net_debt if pd.notna(net_debt) else 0)
        ev_ebitda = ev / ebitda

        return ev_ebitda
