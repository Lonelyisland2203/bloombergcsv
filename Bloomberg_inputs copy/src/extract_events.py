"""
Events Extractor for Bloomberg Activist Data Pipeline

This module extracts corporate actions (dividends, buybacks, splits, M&A) during
activist campaign periods ONLY.

Core Responsibilities:
    1. Extract dividend history (DVD_HIST_ALL)
    2. Extract share buyback programs (SHARE_REPURCHASE_SUMMARY)
    3. Extract stock splits (STOCK_SPLIT_HIST)
    4. Extract M&A activity (MERGERS_AND_ACQUISITIONS)
    5. Filter events to campaign period ONLY (first_filing to last_filing)
    6. Classify events (increase/decrease, initiation/suspension)
    7. Compute months_after_activist_entry for each event
    8. Deduplicate events (same announcement, multiple filings)

CRITICAL: Date Filtering
    - User requirement: Extract ONLY events during campaign period
    - campaign_start = first_filing date (activist initial disclosure)
    - campaign_end = last_filing date (or today if campaign ongoing)
    - Filter: campaign_start <= event_date <= campaign_end
    - NO historical events before campaign
    - NO forward-looking events after campaign end

Point-in-Time Considerations:
    - event_date = announcement date (when market learned of event)
    - effective_date = when event takes effect (e.g., dividend payment date)
    - Use announcement date for timeline analysis
    - Document both dates for full context
    - filing_date may differ from announcement_date (Bloomberg data lag)

Event Classification:
    1. Dividend Increase: New dividend > previous dividend
    2. Dividend Decrease: New dividend < previous dividend
    3. Dividend Initiation: First dividend from previously non-paying company
    4. Dividend Suspension: Dividend stopped
    5. Buyback Announcement: Share repurchase program announced
    6. Stock Split: Forward or reverse split
    7. M&A - Acquisition: Company acquiring another
    8. M&A - Divestiture: Company selling assets/division
    9. M&A - Merger: Company merging with another

Deduplication Logic:
    - Bloomberg sometimes returns same event multiple times
    - Group by (ticker, event_type, event_date, key_detail)
    - Keep first occurrence
    - Log duplicates to gap report

Author: Bloomberg Activist Pipeline
"""

import logging
from dataclasses import dataclass
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from bloomberg_session import BloombergSession

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class CampaignPeriod:
    """
    Represents the time period of an activist campaign.

    Attributes:
        ticker: Bloomberg ticker
        company_name: Company name
        campaign_start: First filing date (activist entry)
        campaign_end: Last filing date (or None if ongoing)
    """

    ticker: str
    company_name: str
    campaign_start: date
    campaign_end: Optional[date]

    def is_within_campaign(self, event_date: date) -> bool:
        """
        Check if an event date falls within campaign period.

        Args:
            event_date: Date of corporate event

        Returns:
            True if event is within campaign period
        """
        if event_date < self.campaign_start:
            return False

        if self.campaign_end is not None and event_date > self.campaign_end:
            return False

        return True

    def months_after_entry(self, event_date: date) -> float:
        """
        Compute months between campaign start and event date.

        Args:
            event_date: Date of corporate event

        Returns:
            Number of months after activist entry (can be negative if before)
        """
        delta = (event_date - self.campaign_start).days
        return delta / 30.44  # Average days per month


class EventsExtractor:
    """
    Extracts corporate actions during activist campaign periods.

    This class provides methods to:
    - Query Bloomberg bulk fields for corporate events
    - Filter events to campaign period ONLY
    - Classify event types
    - Deduplicate events
    - Compute timeline metrics (months after activist entry)

    Attributes:
        session: Active Bloomberg session
        logs_dir: Directory for event gap reports
    """

    # Event type classifications
    EVENT_TYPES = {
        "dividend_increase": "Dividend Increase",
        "dividend_decrease": "Dividend Decrease",
        "dividend_initiation": "Dividend Initiation",
        "dividend_suspension": "Dividend Suspension",
        "buyback": "Share Buyback",
        "stock_split": "Stock Split",
        "reverse_split": "Reverse Stock Split",
        "acquisition": "M&A - Acquisition",
        "divestiture": "M&A - Divestiture",
        "merger": "M&A - Merger",
    }

    def __init__(
        self,
        session: BloombergSession,
        logs_dir: Optional[Path] = None,
    ):
        """
        Initialize events extractor.

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

        logger.info("EventsExtractor initialized")

    def extract_dividend_history(
        self,
        securities: List[str],
        campaign_periods: Dict[str, CampaignPeriod],
    ) -> pd.DataFrame:
        """
        Extract dividend history during campaign periods ONLY.

        Queries DVD_HIST_ALL bulk field and filters to campaign dates.

        Args:
            securities: List of Bloomberg tickers
            campaign_periods: Dict mapping ticker -> CampaignPeriod

        Returns:
            DataFrame with columns:
            - security: Bloomberg ticker
            - event_date: Dividend declaration/announcement date
            - event_type: Classified type (Increase, Decrease, Initiation, Suspension)
            - dividend_amount: Dividend per share
            - currency: Currency code
            - frequency: Dividend frequency (Annual, Semi-Annual, Quarterly)
            - months_after_activist_entry: Months since campaign_start

        Notes:
            - DVD_HIST_ALL returns full history, we filter to campaign period
            - Dividend increases/decreases determined by comparing to previous
            - Initiation = first dividend in history
        """
        if not securities:
            raise ValueError("No securities provided for dividend extraction")

        logger.info(
            f"Extracting dividend history for {len(securities)} securities (campaign period only)"
        )

        # Query Bloomberg bulk field
        try:
            dividends_df = self.session.send_bulk_request(
                securities=securities,
                field="DVD_HIST_ALL",
            )
        except Exception as e:
            logger.error(f"Failed to extract dividend data: {e}")
            raise ValueError(
                f"Dividend extraction failed: {e}\n"
                "Ensure Bloomberg Terminal is running and securities are valid."
            ) from e

        if dividends_df.empty:
            logger.warning("No dividend data returned from Bloomberg")
            return pd.DataFrame()

        logger.info(f"Retrieved {len(dividends_df)} dividend records (pre-filter)")

        # Standardize column names
        dividends_df = self._standardize_dividend_columns(dividends_df)

        # Filter to campaign period ONLY
        dividends_df = self._filter_to_campaign_period(
            dividends_df, campaign_periods
        )

        if dividends_df.empty:
            logger.info("No dividend events during campaign periods")
            return pd.DataFrame()

        # Classify dividend events
        dividends_df = self._classify_dividend_events(dividends_df)

        # Compute months after activist entry
        dividends_df = self._compute_months_after_entry(
            dividends_df, campaign_periods
        )

        logger.info(
            f"Dividend extraction complete: {len(dividends_df)} events during campaign periods"
        )

        return dividends_df

    def extract_buyback_history(
        self,
        securities: List[str],
        campaign_periods: Dict[str, CampaignPeriod],
    ) -> pd.DataFrame:
        """
        Extract share buyback programs during campaign periods ONLY.

        Queries SHARE_REPURCHASE_SUMMARY bulk field.

        Args:
            securities: List of Bloomberg tickers
            campaign_periods: Dict mapping ticker -> CampaignPeriod

        Returns:
            DataFrame with columns:
            - security: Bloomberg ticker
            - event_date: Buyback announcement date
            - event_type: "Share Buyback"
            - program_amount: Total program size (shares or currency)
            - currency: Currency code
            - months_after_activist_entry: Months since campaign_start

        Notes:
            - Buyback announcements often signal undervaluation belief
            - Activists frequently push for buybacks to return cash to shareholders
        """
        if not securities:
            raise ValueError("No securities provided for buyback extraction")

        logger.info(
            f"Extracting buyback history for {len(securities)} securities (campaign period only)"
        )

        # Query Bloomberg bulk field
        try:
            buybacks_df = self.session.send_bulk_request(
                securities=securities,
                field="SHARE_REPURCHASE_SUMMARY",
            )
        except Exception as e:
            logger.error(f"Failed to extract buyback data: {e}")
            raise ValueError(
                f"Buyback extraction failed: {e}\n"
                "Ensure Bloomberg Terminal is running and securities are valid."
            ) from e

        if buybacks_df.empty:
            logger.warning("No buyback data returned from Bloomberg")
            return pd.DataFrame()

        logger.info(f"Retrieved {len(buybacks_df)} buyback records (pre-filter)")

        # Standardize column names
        buybacks_df = self._standardize_buyback_columns(buybacks_df)

        # Filter to campaign period ONLY
        buybacks_df = self._filter_to_campaign_period(
            buybacks_df, campaign_periods
        )

        if buybacks_df.empty:
            logger.info("No buyback events during campaign periods")
            return pd.DataFrame()

        # Add event type
        buybacks_df["event_type"] = "Share Buyback"

        # Compute months after activist entry
        buybacks_df = self._compute_months_after_entry(
            buybacks_df, campaign_periods
        )

        logger.info(
            f"Buyback extraction complete: {len(buybacks_df)} events during campaign periods"
        )

        return buybacks_df

    def extract_split_history(
        self,
        securities: List[str],
        campaign_periods: Dict[str, CampaignPeriod],
    ) -> pd.DataFrame:
        """
        Extract stock split history during campaign periods ONLY.

        Queries STOCK_SPLIT_HIST bulk field.

        Args:
            securities: List of Bloomberg tickers
            campaign_periods: Dict mapping ticker -> CampaignPeriod

        Returns:
            DataFrame with columns:
            - security: Bloomberg ticker
            - event_date: Split announcement date
            - event_type: "Stock Split" or "Reverse Stock Split"
            - split_ratio: Split ratio (e.g., "2-for-1")
            - effective_date: When split takes effect
            - months_after_activist_entry: Months since campaign_start

        Notes:
            - Forward splits (2-for-1, 3-for-1) increase shares, reduce price
            - Reverse splits (1-for-2, 1-for-10) reduce shares, increase price
            - Reverse splits often signal financial distress (rare in Japan)
        """
        if not securities:
            raise ValueError("No securities provided for split extraction")

        logger.info(
            f"Extracting split history for {len(securities)} securities (campaign period only)"
        )

        # Query Bloomberg bulk field
        try:
            splits_df = self.session.send_bulk_request(
                securities=securities,
                field="STOCK_SPLIT_HIST",
            )
        except Exception as e:
            logger.error(f"Failed to extract split data: {e}")
            raise ValueError(
                f"Split extraction failed: {e}\n"
                "Ensure Bloomberg Terminal is running and securities are valid."
            ) from e

        if splits_df.empty:
            logger.warning("No split data returned from Bloomberg")
            return pd.DataFrame()

        logger.info(f"Retrieved {len(splits_df)} split records (pre-filter)")

        # Standardize column names
        splits_df = self._standardize_split_columns(splits_df)

        # Filter to campaign period ONLY
        splits_df = self._filter_to_campaign_period(
            splits_df, campaign_periods
        )

        if splits_df.empty:
            logger.info("No split events during campaign periods")
            return pd.DataFrame()

        # Classify split type (forward vs reverse)
        splits_df = self._classify_split_events(splits_df)

        # Compute months after activist entry
        splits_df = self._compute_months_after_entry(
            splits_df, campaign_periods
        )

        logger.info(
            f"Split extraction complete: {len(splits_df)} events during campaign periods"
        )

        return splits_df

    def extract_ma_history(
        self,
        securities: List[str],
        campaign_periods: Dict[str, CampaignPeriod],
    ) -> pd.DataFrame:
        """
        Extract M&A activity during campaign periods ONLY.

        Queries MERGERS_AND_ACQUISITIONS bulk field.

        Args:
            securities: List of Bloomberg tickers
            campaign_periods: Dict mapping ticker -> CampaignPeriod

        Returns:
            DataFrame with columns:
            - security: Bloomberg ticker
            - event_date: M&A announcement date
            - event_type: "M&A - Acquisition", "M&A - Divestiture", or "M&A - Merger"
            - counterparty: Target company (for acquisitions) or acquirer (for divestitures)
            - deal_value: Transaction value
            - currency: Currency code
            - status: Deal status (Announced, Completed, Terminated)
            - months_after_activist_entry: Months since campaign_start

        Notes:
            - Activists often push for strategic M&A to unlock value
            - Divestitures of non-core assets common in activist campaigns
            - Deal completion may take months/years after announcement
        """
        if not securities:
            raise ValueError("No securities provided for M&A extraction")

        logger.info(
            f"Extracting M&A history for {len(securities)} securities (campaign period only)"
        )

        # Query Bloomberg bulk field
        try:
            ma_df = self.session.send_bulk_request(
                securities=securities,
                field="MERGERS_AND_ACQUISITIONS",
            )
        except Exception as e:
            logger.error(f"Failed to extract M&A data: {e}")
            raise ValueError(
                f"M&A extraction failed: {e}\n"
                "Ensure Bloomberg Terminal is running and securities are valid."
            ) from e

        if ma_df.empty:
            logger.warning("No M&A data returned from Bloomberg")
            return pd.DataFrame()

        logger.info(f"Retrieved {len(ma_df)} M&A records (pre-filter)")

        # Standardize column names
        ma_df = self._standardize_ma_columns(ma_df)

        # Filter to campaign period ONLY
        ma_df = self._filter_to_campaign_period(ma_df, campaign_periods)

        if ma_df.empty:
            logger.info("No M&A events during campaign periods")
            return pd.DataFrame()

        # Classify M&A type
        ma_df = self._classify_ma_events(ma_df)

        # Compute months after activist entry
        ma_df = self._compute_months_after_entry(ma_df, campaign_periods)

        logger.info(
            f"M&A extraction complete: {len(ma_df)} events during campaign periods"
        )

        return ma_df

    def _standardize_dividend_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize Bloomberg DVD_HIST_ALL column names."""
        column_mappings = {
            "Declared Date": "event_date",
            "DECLARED_DATE": "event_date",
            "Ex-Date": "ex_date",
            "EX_DATE": "ex_date",
            "Dividend Amount": "dividend_amount",
            "DVD_AMT": "dividend_amount",
            "Amount": "dividend_amount",
            "Currency": "currency",
            "CURRENCY": "currency",
            "Frequency": "frequency",
            "FREQUENCY": "frequency",
            "Dividend Type": "dividend_type",
            "TYPE": "dividend_type",
        }

        df_renamed = df.rename(columns=column_mappings)

        # Ensure event_date column exists
        if "event_date" not in df_renamed.columns:
            if "ex_date" in df_renamed.columns:
                logger.warning("Using ex_date as event_date (declared_date not available)")
                df_renamed["event_date"] = df_renamed["ex_date"]
            else:
                raise ValueError("No date column found in dividend data")

        return df_renamed

    def _standardize_buyback_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize Bloomberg SHARE_REPURCHASE_SUMMARY column names."""
        column_mappings = {
            "Announcement Date": "event_date",
            "ANNOUNCEMENT_DATE": "event_date",
            "Program Size": "program_amount",
            "PROGRAM_SIZE": "program_amount",
            "Amount": "program_amount",
            "Currency": "currency",
            "CURRENCY": "currency",
            "Shares Authorized": "shares_authorized",
            "SHARES_AUTHORIZED": "shares_authorized",
        }

        df_renamed = df.rename(columns=column_mappings)

        if "event_date" not in df_renamed.columns:
            raise ValueError("No announcement date found in buyback data")

        return df_renamed

    def _standardize_split_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize Bloomberg STOCK_SPLIT_HIST column names."""
        column_mappings = {
            "Announcement Date": "event_date",
            "ANNOUNCEMENT_DATE": "event_date",
            "Effective Date": "effective_date",
            "EFFECTIVE_DATE": "effective_date",
            "Split Ratio": "split_ratio",
            "SPLIT_RATIO": "split_ratio",
            "Ratio": "split_ratio",
        }

        df_renamed = df.rename(columns=column_mappings)

        if "event_date" not in df_renamed.columns:
            if "effective_date" in df_renamed.columns:
                logger.warning("Using effective_date as event_date (announcement not available)")
                df_renamed["event_date"] = df_renamed["effective_date"]
            else:
                raise ValueError("No date column found in split data")

        return df_renamed

    def _standardize_ma_columns(self, df: pd.DataFrame) -> pd.DataFrame:
        """Standardize Bloomberg MERGERS_AND_ACQUISITIONS column names."""
        column_mappings = {
            "Announcement Date": "event_date",
            "ANNOUNCEMENT_DATE": "event_date",
            "Target Name": "counterparty",
            "TARGET_NAME": "counterparty",
            "Acquirer Name": "counterparty",
            "ACQUIRER_NAME": "counterparty",
            "Deal Value": "deal_value",
            "DEAL_VALUE": "deal_value",
            "Value": "deal_value",
            "Currency": "currency",
            "CURRENCY": "currency",
            "Status": "status",
            "STATUS": "status",
            "Deal Type": "deal_type",
            "DEAL_TYPE": "deal_type",
        }

        df_renamed = df.rename(columns=column_mappings)

        if "event_date" not in df_renamed.columns:
            raise ValueError("No announcement date found in M&A data")

        return df_renamed

    def _filter_to_campaign_period(
        self,
        df: pd.DataFrame,
        campaign_periods: Dict[str, CampaignPeriod],
    ) -> pd.DataFrame:
        """
        Filter events to campaign period ONLY.

        CRITICAL: This is the core filtering logic per user requirement.

        Args:
            df: Events DataFrame with 'security' and 'event_date' columns
            campaign_periods: Dict mapping ticker -> CampaignPeriod

        Returns:
            Filtered DataFrame with events during campaign only
        """
        if df.empty:
            return df

        # Convert event_date to datetime
        df["event_date"] = pd.to_datetime(df["event_date"], errors="coerce")

        # Remove rows with missing event_date
        initial_count = len(df)
        df = df[df["event_date"].notna()].copy()
        removed_count = initial_count - len(df)
        if removed_count > 0:
            logger.warning(f"Removed {removed_count} events with missing event_date")

        # Filter by campaign period
        filtered_rows = []

        for _, row in df.iterrows():
            ticker = row["security"]
            event_date = row["event_date"].date()

            if ticker not in campaign_periods:
                logger.warning(f"No campaign period defined for {ticker}, skipping event")
                continue

            campaign = campaign_periods[ticker]

            if campaign.is_within_campaign(event_date):
                filtered_rows.append(row)

        filtered_df = pd.DataFrame(filtered_rows)

        logger.info(
            f"Campaign period filter: {len(df)} total events -> {len(filtered_df)} during campaigns"
        )

        return filtered_df

    def _classify_dividend_events(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Classify dividend events (increase, decrease, initiation, suspension).

        Args:
            df: Dividend DataFrame with 'dividend_amount' column

        Returns:
            DataFrame with 'event_type' column added
        """
        df = df.copy()

        # Sort by security and date
        df = df.sort_values(["security", "event_date"]).reset_index(drop=True)

        # Compute previous dividend for each security
        df["prev_dividend"] = df.groupby("security")["dividend_amount"].shift(1)

        # Classify events
        def classify_dividend(row):
            if pd.isna(row["prev_dividend"]):
                # First dividend in data = initiation (or unknown)
                return "Dividend Initiation"
            elif row["dividend_amount"] > row["prev_dividend"]:
                return "Dividend Increase"
            elif row["dividend_amount"] < row["prev_dividend"]:
                return "Dividend Decrease"
            else:
                # Same amount = regular dividend (no change)
                return "Dividend (No Change)"

        df["event_type"] = df.apply(classify_dividend, axis=1)

        # Drop temporary column
        df = df.drop(columns=["prev_dividend"])

        return df

    def _classify_split_events(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Classify split events (forward vs reverse).

        Args:
            df: Split DataFrame with 'split_ratio' column

        Returns:
            DataFrame with 'event_type' column added
        """
        df = df.copy()

        # Parse split ratio (e.g., "2-for-1", "1-for-2")
        # Forward split: ratio > 1 (e.g., 2-for-1)
        # Reverse split: ratio < 1 (e.g., 1-for-2)

        def classify_split(row):
            split_ratio = row.get("split_ratio", "")

            if pd.isna(split_ratio) or split_ratio == "":
                return "Stock Split"

            # Try to parse ratio string
            split_str = str(split_ratio).upper()

            if "FOR" in split_str:
                # Format: "2-FOR-1" or "1-FOR-2"
                parts = split_str.split("FOR")
                if len(parts) == 2:
                    try:
                        numerator = float(parts[0].strip().replace("-", ""))
                        denominator = float(parts[1].strip().replace("-", ""))
                        ratio = numerator / denominator

                        if ratio > 1:
                            return "Stock Split"
                        elif ratio < 1:
                            return "Reverse Stock Split"
                    except (ValueError, ZeroDivisionError):
                        pass

            # Default: assume forward split
            return "Stock Split"

        df["event_type"] = df.apply(classify_split, axis=1)

        return df

    def _classify_ma_events(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Classify M&A events (acquisition, divestiture, merger).

        Args:
            df: M&A DataFrame with 'deal_type' or other classification fields

        Returns:
            DataFrame with 'event_type' column added
        """
        df = df.copy()

        # Classify based on deal_type field (if available)
        def classify_ma(row):
            deal_type = str(row.get("deal_type", "")).upper()

            if "ACQUISITION" in deal_type or "BUYOUT" in deal_type:
                return "M&A - Acquisition"
            elif "DIVESTITURE" in deal_type or "SALE" in deal_type or "SPINOFF" in deal_type:
                return "M&A - Divestiture"
            elif "MERGER" in deal_type:
                return "M&A - Merger"
            else:
                # Default to acquisition (most common)
                return "M&A - Acquisition"

        df["event_type"] = df.apply(classify_ma, axis=1)

        return df

    def _compute_months_after_entry(
        self,
        df: pd.DataFrame,
        campaign_periods: Dict[str, CampaignPeriod],
    ) -> pd.DataFrame:
        """
        Compute months after activist entry for each event.

        Args:
            df: Events DataFrame with 'security' and 'event_date' columns
            campaign_periods: Dict mapping ticker -> CampaignPeriod

        Returns:
            DataFrame with 'months_after_activist_entry' column added
        """
        df = df.copy()

        months_list = []

        for _, row in df.iterrows():
            ticker = row["security"]
            event_date = row["event_date"]

            if pd.isna(event_date):
                months_list.append(None)
                continue

            if ticker not in campaign_periods:
                months_list.append(None)
                continue

            campaign = campaign_periods[ticker]
            months = campaign.months_after_entry(event_date.date())
            months_list.append(round(months, 2))

        df["months_after_activist_entry"] = months_list

        return df

    def deduplicate_events(self, events_df: pd.DataFrame) -> pd.DataFrame:
        """
        Remove duplicate event announcements.

        Bloomberg sometimes returns the same event multiple times due to:
        - Multiple filings for the same announcement
        - Amended filings
        - Data feed duplicates

        Deduplication strategy:
        - Group by (security, event_type, event_date, key_detail)
        - Keep first occurrence
        - Log duplicates to gap report

        Args:
            events_df: Events DataFrame

        Returns:
            Deduplicated DataFrame
        """
        if events_df.empty:
            return events_df

        initial_count = len(events_df)

        # Define deduplication key based on event type
        dedup_columns = ["security", "event_type", "event_date"]

        # Add type-specific key columns
        if "dividend_amount" in events_df.columns:
            dedup_columns.append("dividend_amount")
        if "program_amount" in events_df.columns:
            dedup_columns.append("program_amount")
        if "split_ratio" in events_df.columns:
            dedup_columns.append("split_ratio")
        if "counterparty" in events_df.columns:
            dedup_columns.append("counterparty")

        # Deduplicate
        events_df = events_df.drop_duplicates(
            subset=dedup_columns, keep="first"
        ).reset_index(drop=True)

        removed_count = initial_count - len(events_df)

        if removed_count > 0:
            logger.info(f"Removed {removed_count} duplicate events")

        return events_df

    def extract_all_events(
        self,
        securities: List[str],
        campaign_periods: Dict[str, CampaignPeriod],
    ) -> pd.DataFrame:
        """
        Extract all corporate events (dividends, buybacks, splits, M&A) during campaigns.

        This is the main entry point for event extraction.

        Args:
            securities: List of Bloomberg tickers
            campaign_periods: Dict mapping ticker -> CampaignPeriod

        Returns:
            Combined DataFrame with all events, columns:
            - security: Bloomberg ticker
            - company_name: Company name (from campaign_periods)
            - event_type: Classified event type
            - event_date: Event announcement date
            - months_after_activist_entry: Months since campaign start
            - campaign_status_at_event: "During Campaign" (all events in range)
            - details: Event-specific details (JSON or dict)

        Raises:
            ValueError: If extraction fails
        """
        logger.info(
            f"Extracting all corporate events for {len(securities)} securities"
        )

        all_events = []

        # Extract dividends
        try:
            dividends = self.extract_dividend_history(securities, campaign_periods)
            if not dividends.empty:
                dividends["event_category"] = "Dividend"
                all_events.append(dividends)
        except Exception as e:
            logger.warning(f"Dividend extraction failed: {e}")

        # Extract buybacks
        try:
            buybacks = self.extract_buyback_history(securities, campaign_periods)
            if not buybacks.empty:
                buybacks["event_category"] = "Buyback"
                all_events.append(buybacks)
        except Exception as e:
            logger.warning(f"Buyback extraction failed: {e}")

        # Extract splits
        try:
            splits = self.extract_split_history(securities, campaign_periods)
            if not splits.empty:
                splits["event_category"] = "Split"
                all_events.append(splits)
        except Exception as e:
            logger.warning(f"Split extraction failed: {e}")

        # Extract M&A
        try:
            ma_events = self.extract_ma_history(securities, campaign_periods)
            if not ma_events.empty:
                ma_events["event_category"] = "M&A"
                all_events.append(ma_events)
        except Exception as e:
            logger.warning(f"M&A extraction failed: {e}")

        # Combine all events
        if not all_events:
            logger.warning("No events extracted for any category")
            return pd.DataFrame()

        combined_df = pd.concat(all_events, ignore_index=True)

        # Deduplicate
        combined_df = self.deduplicate_events(combined_df)

        # Add company names
        combined_df["company_name"] = combined_df["security"].map(
            {cp.ticker: cp.company_name for cp in campaign_periods.values()}
        )

        # Add campaign status (all events are during campaign by construction)
        combined_df["campaign_status_at_event"] = "During Campaign"

        # Sort by event date
        combined_df = combined_df.sort_values(
            ["security", "event_date"]
        ).reset_index(drop=True)

        logger.info(
            f"Event extraction complete: {len(combined_df)} total events across "
            f"{combined_df['security'].nunique()} securities"
        )

        return combined_df

    def save_events_to_csv(
        self,
        events_df: pd.DataFrame,
        output_path: Path,
    ) -> None:
        """
        Save events data to CSV.

        Args:
            events_df: Events DataFrame
            output_path: Path to save CSV file
        """
        output_path = Path(output_path)
        output_path.parent.mkdir(parents=True, exist_ok=True)

        events_df.to_csv(output_path, index=False, encoding="utf-8-sig")

        logger.info(f"Events data saved to: {output_path}")
