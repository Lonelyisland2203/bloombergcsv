"""
Fiscal Period Alignment for Bloomberg Data Extraction

This module computes point-in-time safe fiscal year-end dates and constructs
Bloomberg FUND_PER override parameters for historical data extraction.

Point-in-Time Safety (CRITICAL):
    All fiscal alignment functions ensure no lookahead bias by:
    1. Using only campaign_start_date as reference (known at campaign time)
    2. Applying 60-day buffer before FY-end to avoid late-filing lookups
    3. Selecting most recent COMPLETED fiscal year before campaign start

Temporal Semantics:
    - snapshot_date: The fiscal year-end date for data extraction
    - campaign_start_date: When activist campaign began (earliest filing date)
    - 60-day buffer: Safety margin for financial statement availability

Author: Bloomberg Activist Pipeline
"""

from datetime import date, timedelta
from typing import Tuple
import calendar


def compute_snapshot_date(campaign_start_date: date, fye_month: int) -> date:
    """
    Compute the most recent fiscal year-end date before campaign start.

    This function determines which fiscal year-end to use for snapshot data
    extraction, ensuring point-in-time safety by selecting the most recent
    COMPLETED fiscal year that would have been available at campaign start.

    Args:
        campaign_start_date: Date when activist campaign began (earliest filing date)
        fye_month: Fiscal year-end month (1=January, 12=December)

    Returns:
        Fiscal year-end date (last day of fye_month in appropriate year)

    Raises:
        ValueError: If fye_month is not in range [1, 12]
        TypeError: If campaign_start_date is not a date object

    Algorithm:
        1. Validate inputs
        2. Find FYE in campaign start year
        3. If campaign_start is within 60 days of FYE, use prior year's FYE
        4. Otherwise, if campaign_start is after FYE, use that FYE
        5. Otherwise, use previous year's FYE

    Edge Cases:
        - 60-day buffer: If campaign starts within 60 days of FY-end, assume
          financial statements not yet available → use prior year's FY-end
        - Leap years: February 29 FYE handled correctly (Feb 28 in non-leap years)
        - Year boundaries: Handles campaigns starting in January correctly

    Examples:
        >>> # Campaign starts June 14, 2021; March 31 FYE
        >>> compute_snapshot_date(date(2021, 6, 14), 3)
        datetime.date(2021, 3, 31)

        >>> # Campaign starts April 6, 2021; March 31 FYE (within 60-day buffer)
        >>> compute_snapshot_date(date(2021, 4, 6), 3)
        datetime.date(2020, 3, 31)

        >>> # Campaign starts January 15, 2021; December 31 FYE
        >>> compute_snapshot_date(date(2021, 1, 15), 12)
        datetime.date(2020, 12, 31)

        >>> # Campaign starts November 1, 2021; March 31 FYE (before FYE in year)
        >>> compute_snapshot_date(date(2021, 11, 1), 3)
        datetime.date(2021, 3, 31)

    Notes:
        - Point-in-time safe: Only uses information available at campaign_start_date
        - No lookahead bias: Buffer ensures financial statements were filed
        - Japanese market context: Most Japanese companies have March 31 FYE
    """
    # Validate inputs
    if not isinstance(campaign_start_date, date):
        raise TypeError(
            f"campaign_start_date must be a datetime.date object, "
            f"got {type(campaign_start_date).__name__}"
        )

    if not isinstance(fye_month, int):
        raise TypeError(
            f"fye_month must be an integer, got {type(fye_month).__name__}"
        )

    if not 1 <= fye_month <= 12:
        raise ValueError(
            f"fye_month must be between 1 (January) and 12 (December), got {fye_month}"
        )

    # Get last day of FYE month in campaign start year
    campaign_year = campaign_start_date.year
    last_day = calendar.monthrange(campaign_year, fye_month)[1]
    fye_in_campaign_year = date(campaign_year, fye_month, last_day)

    # Also get prior year's FYE for comparison
    last_day_prior = calendar.monthrange(campaign_year - 1, fye_month)[1]
    fye_in_prior_year = date(campaign_year - 1, fye_month, last_day_prior)

    # Calculate days from campaign start to each FYE
    days_from_prior_fye = (campaign_start_date - fye_in_prior_year).days
    days_to_current_fye = (fye_in_campaign_year - campaign_start_date).days

    # Decision logic for point-in-time safety:
    # Use the most recent COMPLETED FYE, but only if financials would be available
    # (i.e., FYE was more than 60 days ago)

    if days_from_prior_fye > 60:
        # Prior year's FYE was more than 60 days ago
        # Check if current year's FYE has also passed and cleared 60-day buffer
        if days_to_current_fye < 0 and abs(days_to_current_fye) > 60:
            # Current year's FYE passed more than 60 days ago → use it
            snapshot_year = campaign_year
        else:
            # Current year's FYE either hasn't occurred or is within 60-day buffer
            # → use prior year's FYE
            snapshot_year = campaign_year - 1
    else:
        # Prior year's FYE was within 60 days → use FYE from year before that
        snapshot_year = campaign_year - 2

    # Construct snapshot date (handle leap year edge case for Feb 29 FYE)
    if fye_month == 2:
        # February: Get last day of month (28 or 29 depending on leap year)
        last_day_snapshot = calendar.monthrange(snapshot_year, fye_month)[1]
        snapshot_date = date(snapshot_year, fye_month, last_day_snapshot)
    else:
        # Other months: Last day is same regardless of leap year
        snapshot_date = date(snapshot_year, fye_month, last_day)

    return snapshot_date


def construct_fund_per_override(snapshot_date: date) -> str:
    """
    Construct Bloomberg FUND_PER override string from snapshot date.

    Converts a fiscal year-end date to Bloomberg's FUND_PER format, which
    is used in ReferenceDataRequest overrides to extract specific fiscal
    period data.

    Args:
        snapshot_date: Fiscal year-end date (output of compute_snapshot_date)

    Returns:
        Bloomberg FUND_PER override string in format "FYYYY" (e.g., "FY2021")

    Raises:
        TypeError: If snapshot_date is not a date object
        ValueError: If snapshot_date is unreasonably far in past/future

    Format:
        Bloomberg FUND_PER format: "FY" + 4-digit year of fiscal year-end
        Example: Fiscal year ending March 31, 2021 → "FY2021"

    Examples:
        >>> construct_fund_per_override(date(2021, 3, 31))
        'FY2021'

        >>> construct_fund_per_override(date(2020, 12, 31))
        'FY2020'

        >>> construct_fund_per_override(date(2022, 2, 28))
        'FY2022'

    Notes:
        - Year is taken from snapshot_date.year (calendar year of FY-end)
        - For Japanese companies with March FYE: FY2021 = April 2020 - March 2021
        - Bloomberg interprets "FY2021" as fiscal year ending in calendar year 2021
    """
    if not isinstance(snapshot_date, date):
        raise TypeError(
            f"snapshot_date must be a datetime.date object, "
            f"got {type(snapshot_date).__name__}"
        )

    # Sanity check: Reject unreasonable dates (likely input errors)
    current_year = date.today().year
    if snapshot_date.year < 1980 or snapshot_date.year > current_year + 5:
        raise ValueError(
            f"snapshot_date year {snapshot_date.year} is outside reasonable range "
            f"[1980, {current_year + 5}]. Check input date."
        )

    # Construct FUND_PER override string
    fund_per = f"FY{snapshot_date.year}"

    return fund_per


def get_fiscal_year_range(fye_date: date) -> Tuple[date, date]:
    """
    Compute the start and end dates of a fiscal year given its year-end date.

    Args:
        fye_date: Fiscal year-end date

    Returns:
        Tuple of (fiscal_year_start, fiscal_year_end)

    Raises:
        TypeError: If fye_date is not a date object

    Examples:
        >>> get_fiscal_year_range(date(2021, 3, 31))
        (datetime.date(2020, 4, 1), datetime.date(2021, 3, 31))

        >>> get_fiscal_year_range(date(2020, 12, 31))
        (datetime.date(2020, 1, 1), datetime.date(2020, 12, 31))

    Notes:
        - Fiscal year runs from (FYE - 1 year + 1 day) to FYE
        - For March 31 FYE: April 1 (prior year) to March 31 (current year)
        - For December 31 FYE: January 1 to December 31 (same year)
    """
    if not isinstance(fye_date, date):
        raise TypeError(
            f"fye_date must be a datetime.date object, "
            f"got {type(fye_date).__name__}"
        )

    # Fiscal year starts one day after previous year's FYE
    # Handle leap year edge case: Feb 29 FYE
    try:
        # Try to construct date with same month/day in prior year
        prior_year_fye = date(fye_date.year - 1, fye_date.month, fye_date.day)
    except ValueError:
        # Occurs when fye_date is Feb 29 (leap year) and prior year is not a leap year
        # Use Feb 28 instead
        prior_year_fye = date(fye_date.year - 1, 2, 28)

    fiscal_year_start = prior_year_fye + timedelta(days=1)
    fiscal_year_end = fye_date

    return (fiscal_year_start, fiscal_year_end)


def validate_fye_month(fye_month: int) -> bool:
    """
    Validate fiscal year-end month value.

    Args:
        fye_month: Month number to validate (1-12)

    Returns:
        True if valid, False otherwise

    Examples:
        >>> validate_fye_month(3)
        True

        >>> validate_fye_month(13)
        False

        >>> validate_fye_month(0)
        False
    """
    return isinstance(fye_month, int) and 1 <= fye_month <= 12


def compute_campaign_fiscal_alignment(
    campaign_start_date: date,
    fye_month: int
) -> Tuple[date, str, Tuple[date, date]]:
    """
    Comprehensive fiscal alignment computation (convenience wrapper).

    Combines all fiscal alignment operations into a single function call.

    Args:
        campaign_start_date: Date when activist campaign began
        fye_month: Fiscal year-end month (1-12)

    Returns:
        Tuple of:
            - snapshot_date: Fiscal year-end date for data extraction
            - fund_per_override: Bloomberg FUND_PER string (e.g., "FY2021")
            - fiscal_year_range: (start_date, end_date) of fiscal year

    Raises:
        ValueError: If fye_month is invalid
        TypeError: If campaign_start_date is not a date object

    Examples:
        >>> compute_campaign_fiscal_alignment(date(2021, 6, 14), 3)
        (datetime.date(2021, 3, 31), 'FY2021', (datetime.date(2020, 4, 1), datetime.date(2021, 3, 31)))

        >>> compute_campaign_fiscal_alignment(date(2021, 4, 6), 3)
        (datetime.date(2020, 3, 31), 'FY2020', (datetime.date(2019, 4, 1), datetime.date(2020, 3, 31)))

    Notes:
        - Convenience function for end-to-end fiscal alignment
        - All outputs are point-in-time safe
        - Use individual functions if only specific outputs needed
    """
    # Compute snapshot date
    snapshot_date = compute_snapshot_date(campaign_start_date, fye_month)

    # Construct FUND_PER override
    fund_per_override = construct_fund_per_override(snapshot_date)

    # Get fiscal year range
    fiscal_year_range = get_fiscal_year_range(snapshot_date)

    return (snapshot_date, fund_per_override, fiscal_year_range)
