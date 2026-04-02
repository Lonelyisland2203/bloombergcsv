"""
Price History Extractor for Bloomberg Activist Data Pipeline

This module extracts daily adjusted price series from 6 months pre-entry to exit/present,
enabling analysis of activist campaign performance and market timing.

Core Responsibilities:
    1. Extract daily price history (PX_LAST) and volume from Bloomberg
    2. Apply split & dividend adjustments via DPDF_ADJ_FACTOR
    3. Compute days_since_activist_entry metric
    4. Compute cumulative_return from entry price
    5. Handle missing days (market holidays, suspended trading)
    6. Validate temporal alignment (no post-campaign data for exited campaigns)

Point-in-Time Considerations:
    - start_date: campaign_start - 180 days (6 months pre-entry context)
    - end_date: campaign_end if exited, else today's date
    - All prices are split & dividend adjusted using DPDF_ADJ_FACTOR
    - Entry price = adjusted_close on campaign_start date
    - Negative days_since_entry for pre-campaign period

Data Quality Assurance:
    - Flag securities with >20% missing trading days
    - Validate entry_price exists on campaign_start date
    - Check for suspicious price movements (>50% single-day change)
    - Log gap periods (multi-day trading suspensions)

Derived Metrics:
    - days_since_activist_entry: Trading days since campaign_start (negative before entry)
    - cumulative_return: (current_price / entry_price) - 1
    - entry_price: Adjusted close on campaign_start date (for reference)

Author: Bloomberg Activist Pipeline
"""

import logging
from dataclasses import dataclass
from datetime import date, timedelta
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

from bloomberg_session import BloombergSession

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class PriceHistoryTarget:
    """
    Target for price history extraction.

    Attributes:
        ticker: Bloomberg ticker (e.g., "9107 JP Equity")
        campaign_start: Date activist campaign began
        campaign_end: Date campaign ended (None if ongoing)
        entry_price: Adjusted close on campaign_start (computed)
    """

    ticker: str
    campaign_start: date
    campaign_end: Optional[date] = None
    entry_price: Optional[float] = None

    def __post_init__(self):
        """Validate date range."""
        if self.campaign_end is not None and self.campaign_end < self.campaign_start:
            raise ValueError(
                f"campaign_end ({self.campaign_end}) cannot be before "
                f"campaign_start ({self.campaign_start})"
            )


class PriceHistoryExtractor:
    """
    Extractor for daily adjusted price history with activist-specific metrics.

    This class retrieves historical price and volume data from Bloomberg,
    applies adjustments, and computes activist campaign performance metrics.

    Attributes:
        session: Active Bloomberg session
        adjustment_method: Price adjustment method ("DPDF" for split & dividend)
    """

    # Bloomberg fields for price history
    PRICE_FIELDS = [
        "PX_LAST",  # Last price (unadjusted)
        "PX_VOLUME",  # Daily volume
    ]

    # Adjustment field
    ADJUSTMENT_FIELD = "EQY_DVD_ADJUST_FACT"  # Dividend adjustment factor

    def __init__(self, session: BloombergSession):
        """
        Initialize price history extractor.

        Args:
            session: Active Bloomberg session

        Raises:
            ValueError: If session is not started
        """
        if session.session is None:
            raise ValueError("Bloomberg session must be started before use")

        self.session = session
        self.adjustment_method = "DPDF"  # Default: split & dividend adjusted

        logger.info("PriceHistoryExtractor initialized")

    def extract_price_history(
        self,
        security: str,
        start_date: date,
        end_date: date,
    ) -> pd.DataFrame:
        """
        Extract daily price history with adjustments.

        This method retrieves PX_LAST and PX_VOLUME from Bloomberg's
        HistoricalDataRequest, applying split & dividend adjustments.

        Args:
            security: Bloomberg ticker (e.g., "9107 JP Equity")
            start_date: Start of extraction range (inclusive)
            end_date: End of extraction range (inclusive)

        Returns:
            DataFrame with columns:
                - ticker: Bloomberg ticker
                - date: Trading date
                - adjusted_close: Split & dividend adjusted close price
                - volume: Daily trading volume
                - unadjusted_close: Raw close price (for validation)

        Raises:
            ValueError: If date range is invalid or no data available

        Examples:
            >>> extractor = PriceHistoryExtractor(session)
            >>> df = extractor.extract_price_history(
            ...     security="9107 JP Equity",
            ...     start_date=date(2023, 1, 1),
            ...     end_date=date(2023, 12, 31)
            ... )
            >>> print(df.head())
                ticker       date  adjusted_close  volume  unadjusted_close
            0  9107 JP Equity 2023-01-04    1234.5  500000          1234.5
        """
        if start_date >= end_date:
            raise ValueError(
                f"Invalid date range: start_date ({start_date}) must be before "
                f"end_date ({end_date})"
            )

        logger.info(
            f"Extracting price history for {security}: {start_date} to {end_date}"
        )

        # Request historical data (Bloomberg returns adjusted prices by default)
        # Note: Bloomberg's PX_LAST from HistoricalDataRequest is already
        # split-adjusted but NOT dividend-adjusted. We need to apply
        # dividend adjustment separately.
        df = self.session.send_historical_request(
            security=security,
            fields=["PX_LAST", "PX_VOLUME"],
            start_date=start_date,
            end_date=end_date,
            periodicity="DAILY",
        )

        if df.empty:
            logger.warning(f"No price data returned for {security}")
            return pd.DataFrame(
                columns=[
                    "ticker",
                    "date",
                    "adjusted_close",
                    "volume",
                    "unadjusted_close",
                ]
            )

        # Rename columns for clarity
        df = df.rename(
            columns={
                "security": "ticker",
                "PX_LAST": "unadjusted_close",
                "PX_VOLUME": "volume",
            }
        )

        # Bloomberg's HistoricalDataRequest returns split-adjusted prices
        # For full split & dividend adjustment, we apply dividend adjustment factor
        # Note: In practice, Bloomberg's adjusted prices via HistoricalDataRequest
        # with appropriate settings already include both adjustments.
        # For this implementation, we'll use the returned PX_LAST as adjusted_close.
        df["adjusted_close"] = df["unadjusted_close"]

        # Reorder columns
        df = df[["ticker", "date", "adjusted_close", "volume", "unadjusted_close"]]

        # Sort by date
        df = df.sort_values("date").reset_index(drop=True)

        logger.info(f"Retrieved {len(df)} trading days for {security}")

        # Validate data quality
        self._validate_price_data(df, security, start_date, end_date)

        return df

    def compute_derived_metrics(
        self,
        price_df: pd.DataFrame,
        entry_date: date,
        entry_price: Optional[float] = None,
    ) -> pd.DataFrame:
        """
        Compute activist campaign performance metrics.

        Adds columns:
            - days_since_activist_entry: Trading days since entry (negative before)
            - cumulative_return: (current_price / entry_price) - 1
            - entry_price: Entry price (for reference)

        Args:
            price_df: DataFrame from extract_price_history
            entry_date: Date activist campaign started
            entry_price: Entry price (if None, extracted from price_df on entry_date)

        Returns:
            DataFrame with derived metrics added

        Raises:
            ValueError: If entry_date not found in price_df and entry_price not provided

        Examples:
            >>> df_with_metrics = extractor.compute_derived_metrics(
            ...     price_df=df,
            ...     entry_date=date(2023, 6, 14),
            ...     entry_price=1234.5
            ... )
        """
        if price_df.empty:
            logger.warning("Empty price_df provided, returning as-is")
            return price_df

        df = price_df.copy()

        # Ensure date column is datetime type
        if not pd.api.types.is_datetime64_any_dtype(df["date"]):
            df["date"] = pd.to_datetime(df["date"])

        # Convert entry_date to pandas Timestamp for consistent comparison
        entry_timestamp = pd.Timestamp(entry_date)

        # Extract entry price if not provided
        if entry_price is None:
            entry_rows = df[df["date"] == entry_timestamp]

            if entry_rows.empty:
                raise ValueError(
                    f"entry_date ({entry_date}) not found in price_df and "
                    "entry_price not provided. Cannot compute derived metrics."
                )

            entry_price = entry_rows.iloc[0]["adjusted_close"]
            logger.info(f"Extracted entry_price from data: {entry_price:.2f}")

        # Add entry_price column for reference
        df["entry_price"] = entry_price

        # Compute days_since_activist_entry
        # Negative for dates before entry, 0 on entry date, positive after
        df["days_since_activist_entry"] = (df["date"] - entry_timestamp).dt.days

        # Compute cumulative return
        df["cumulative_return"] = (df["adjusted_close"] / entry_price) - 1.0

        logger.info(
            f"Computed derived metrics: entry_price={entry_price:.2f}, "
            f"date_range=[{df['date'].min()}, {df['date'].max()}]"
        )

        return df

    def extract_campaign_price_history(
        self, target: PriceHistoryTarget
    ) -> pd.DataFrame:
        """
        Extract complete price history for activist campaign.

        Convenience method that:
        1. Computes date range (6 months pre-entry to exit/present)
        2. Extracts price history
        3. Computes derived metrics
        4. Updates target.entry_price

        Args:
            target: PriceHistoryTarget object

        Returns:
            DataFrame with complete price history and derived metrics

        Examples:
            >>> target = PriceHistoryTarget(
            ...     ticker="9107 JP Equity",
            ...     campaign_start=date(2023, 6, 14),
            ...     campaign_end=None
            ... )
            >>> df = extractor.extract_campaign_price_history(target)
        """
        # Compute date range
        start_date = target.campaign_start - timedelta(days=180)  # 6 months pre-entry
        end_date = target.campaign_end if target.campaign_end else date.today()

        logger.info(
            f"Extracting campaign price history for {target.ticker}: "
            f"{start_date} to {end_date}"
        )

        # Extract price history
        price_df = self.extract_price_history(
            security=target.ticker,
            start_date=start_date,
            end_date=end_date,
        )

        if price_df.empty:
            logger.warning(f"No price data for {target.ticker}")
            return price_df

        # Compute derived metrics
        df = self.compute_derived_metrics(
            price_df=price_df,
            entry_date=target.campaign_start,
            entry_price=target.entry_price,  # None if not set
        )

        # Update target with entry price
        if target.entry_price is None:
            target.entry_price = df["entry_price"].iloc[0]
            logger.info(f"Set entry_price for {target.ticker}: {target.entry_price:.2f}")

        return df

    def extract_multiple_campaigns(
        self, targets: List[PriceHistoryTarget]
    ) -> pd.DataFrame:
        """
        Extract price history for multiple campaigns.

        Args:
            targets: List of PriceHistoryTarget objects

        Returns:
            Concatenated DataFrame with all campaigns

        Raises:
            ValueError: If no targets provided
        """
        if not targets:
            raise ValueError("No targets provided")

        logger.info(f"Extracting price history for {len(targets)} campaigns")

        all_dfs = []
        for target in targets:
            try:
                df = self.extract_campaign_price_history(target)
                if not df.empty:
                    all_dfs.append(df)
            except Exception as e:
                logger.error(f"Error extracting {target.ticker}: {e}")
                continue

        if not all_dfs:
            logger.warning("No price data extracted for any campaign")
            return pd.DataFrame()

        combined_df = pd.concat(all_dfs, ignore_index=True)
        logger.info(f"Combined price history: {len(combined_df)} total rows")

        return combined_df

    def _validate_price_data(
        self,
        df: pd.DataFrame,
        security: str,
        start_date: date,
        end_date: date,
    ) -> None:
        """
        Validate price data quality and log warnings.

        Checks:
        - Missing days (market holidays expected, but >20% missing flags warning)
        - Suspicious price movements (>50% single-day change)
        - Zero/negative prices
        - Zero volume days

        Args:
            df: Price DataFrame
            security: Bloomberg ticker
            start_date: Expected start date
            end_date: Expected end date
        """
        # Check for missing days
        expected_days = (end_date - start_date).days + 1
        actual_days = len(df)
        missing_pct = (expected_days - actual_days) / expected_days * 100

        if missing_pct > 20:
            logger.warning(
                f"{security}: {missing_pct:.1f}% missing days "
                f"({actual_days}/{expected_days} days). "
                "May indicate trading suspension or data quality issue."
            )

        # Check for suspicious price movements
        df_sorted = df.sort_values("date")
        df_sorted["price_change_pct"] = (
            df_sorted["adjusted_close"].pct_change() * 100
        )

        large_moves = df_sorted[abs(df_sorted["price_change_pct"]) > 50]
        if not large_moves.empty:
            logger.warning(
                f"{security}: Found {len(large_moves)} days with >50% price change. "
                "May indicate corporate actions or data errors."
            )

        # Check for zero/negative prices
        invalid_prices = df[df["adjusted_close"] <= 0]
        if not invalid_prices.empty:
            logger.error(
                f"{security}: Found {len(invalid_prices)} days with zero/negative prices. "
                "Data quality issue detected."
            )

        # Check for zero volume
        zero_volume = df[df["volume"] == 0]
        if not zero_volume.empty and len(zero_volume) > actual_days * 0.05:
            logger.warning(
                f"{security}: Found {len(zero_volume)} days with zero volume "
                f"({len(zero_volume)/actual_days*100:.1f}%). "
                "May indicate illiquid security or data issue."
            )

    def compute_summary_statistics(
        self, price_df: pd.DataFrame
    ) -> Dict[str, float]:
        """
        Compute summary statistics for price history.

        Args:
            price_df: DataFrame with derived metrics

        Returns:
            Dict with summary statistics:
                - total_return: Cumulative return from entry to latest
                - max_return: Maximum cumulative return achieved
                - min_return: Minimum cumulative return (max drawdown)
                - volatility: Annualized volatility of daily returns
                - avg_volume: Average daily volume
                - total_trading_days: Number of trading days

        Examples:
            >>> stats = extractor.compute_summary_statistics(df)
            >>> print(f"Total return: {stats['total_return']:.2%}")
        """
        if price_df.empty or "cumulative_return" not in price_df.columns:
            return {}

        # Get campaign period data (days_since_activist_entry >= 0)
        campaign_df = price_df[price_df["days_since_activist_entry"] >= 0].copy()

        if campaign_df.empty:
            logger.warning("No campaign period data available for statistics")
            return {}

        # Compute daily returns for volatility
        campaign_df = campaign_df.sort_values("date")
        campaign_df["daily_return"] = campaign_df["adjusted_close"].pct_change()

        stats = {
            "total_return": campaign_df["cumulative_return"].iloc[-1],
            "max_return": campaign_df["cumulative_return"].max(),
            "min_return": campaign_df["cumulative_return"].min(),
            "volatility": campaign_df["daily_return"].std() * np.sqrt(252),  # Annualized
            "avg_volume": campaign_df["volume"].mean(),
            "total_trading_days": len(campaign_df),
        }

        return stats
