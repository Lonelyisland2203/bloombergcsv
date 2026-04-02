"""
Ticker Format Converter for Japanese Securities

This module converts Tokyo Stock Exchange (TSE) ticker formats to Bloomberg format.

Input Format:  TSE .T format (e.g., "9107.T", "8952J.T")
Output Format: Bloomberg format (e.g., "9107 JP Equity", "8952J JP Equity")

Point-in-Time Considerations:
    Ticker conversions are static mappings and have no temporal dependencies.
    No lookahead bias concerns for this utility.

Author: Bloomberg Activist Pipeline
"""

import re
from typing import Optional


def convert_ticker(tse_ticker: str) -> str:
    """
    Convert TSE .T format ticker to Bloomberg JP Equity format.

    This function validates and converts Tokyo Stock Exchange ticker formats
    from the standard .T suffix format to Bloomberg's "JP Equity" format.

    Args:
        tse_ticker: TSE ticker in .T format (e.g., "9107.T", "8952J.T")

    Returns:
        Bloomberg-formatted ticker (e.g., "9107 JP Equity", "8952J JP Equity")

    Raises:
        ValueError: If ticker format is invalid or cannot be parsed

    Examples:
        >>> convert_ticker("9107.T")
        '9107 JP Equity'

        >>> convert_ticker("8952J.T")  # REIT with J suffix
        '8952J JP Equity'

        >>> convert_ticker("invalid")
        Traceback (most recent call last):
            ...
        ValueError: Invalid TSE ticker format: 'invalid'. Expected format: NNNN.T or NNNNJ.T

    Notes:
        - Standard equity tickers: 4-digit code + .T suffix (e.g., "9107.T")
        - REIT tickers: 4-digit code + J + .T suffix (e.g., "8952J.T")
        - Validation ensures code is exactly 4 digits
        - Case-sensitive: ".T" suffix must be uppercase
    """
    if not isinstance(tse_ticker, str):
        raise ValueError(
            f"Ticker must be a string, got {type(tse_ticker).__name__}: {tse_ticker}"
        )

    # Strip whitespace
    tse_ticker = tse_ticker.strip()

    if not tse_ticker:
        raise ValueError("Ticker cannot be empty or whitespace")

    # Validate .T suffix
    if not tse_ticker.endswith(".T"):
        raise ValueError(
            f"Invalid TSE ticker format: '{tse_ticker}'. "
            "Expected format: NNNN.T or NNNNJ.T (must end with '.T')"
        )

    # Extract base code (everything before .T)
    base_code = tse_ticker[:-2]  # Remove ".T" suffix

    if not base_code:
        raise ValueError(
            f"Invalid TSE ticker format: '{tse_ticker}'. "
            "Ticker code cannot be empty before .T suffix"
        )

    # Validate format: Either NNNN or NNNNJ (4 digits, optional J for REITs)
    # Pattern: Exactly 4 digits, optionally followed by 'J'
    pattern = r'^(\d{4})(J)?$'
    match = re.match(pattern, base_code)

    if not match:
        # Provide specific error guidance
        if re.match(r'^\d+J?$', base_code):
            # Contains only digits and optional J, but wrong length
            digit_count = len(re.sub(r'J$', '', base_code))
            raise ValueError(
                f"Invalid TSE ticker format: '{tse_ticker}'. "
                f"TSE code must be exactly 4 digits, got {digit_count} digits. "
                f"Expected format: NNNN.T or NNNNJ.T"
            )
        else:
            # Contains invalid characters
            raise ValueError(
                f"Invalid TSE ticker format: '{tse_ticker}'. "
                "TSE code must contain only 4 digits (optionally followed by 'J' for REITs). "
                "Expected format: NNNN.T or NNNNJ.T"
            )

    # Convert to Bloomberg format
    bloomberg_ticker = f"{base_code} JP Equity"

    return bloomberg_ticker


def validate_tse_ticker(tse_ticker: str) -> bool:
    """
    Validate TSE ticker format without converting.

    Checks if a string is a valid TSE ticker in .T format.

    Args:
        tse_ticker: String to validate

    Returns:
        True if valid TSE ticker format, False otherwise

    Examples:
        >>> validate_tse_ticker("9107.T")
        True

        >>> validate_tse_ticker("8952J.T")
        True

        >>> validate_tse_ticker("invalid")
        False

        >>> validate_tse_ticker("107.T")  # Only 3 digits
        False
    """
    try:
        convert_ticker(tse_ticker)
        return True
    except ValueError:
        return False


def extract_tse_code(tse_ticker: str) -> str:
    """
    Extract the numeric TSE code from a .T format ticker.

    Args:
        tse_ticker: TSE ticker in .T format (e.g., "9107.T")

    Returns:
        TSE code without .T suffix (e.g., "9107")

    Raises:
        ValueError: If ticker format is invalid

    Examples:
        >>> extract_tse_code("9107.T")
        '9107'

        >>> extract_tse_code("8952J.T")
        '8952J'
    """
    # Reuse conversion logic for validation, then extract base code
    if not validate_tse_ticker(tse_ticker):
        raise ValueError(f"Invalid TSE ticker format: '{tse_ticker}'")

    # Strip .T suffix
    return tse_ticker[:-2]


def convert_bloomberg_to_tse(bloomberg_ticker: str) -> str:
    """
    Convert Bloomberg JP Equity format to TSE .T format (reverse conversion).

    Args:
        bloomberg_ticker: Bloomberg ticker in "JP Equity" format (e.g., "9107 JP Equity")

    Returns:
        TSE ticker in .T format (e.g., "9107.T")

    Raises:
        ValueError: If Bloomberg ticker format is invalid

    Examples:
        >>> convert_bloomberg_to_tse("9107 JP Equity")
        '9107.T'

        >>> convert_bloomberg_to_tse("8952J JP Equity")
        '8952J.T'
    """
    if not isinstance(bloomberg_ticker, str):
        raise ValueError(
            f"Ticker must be a string, got {type(bloomberg_ticker).__name__}"
        )

    bloomberg_ticker = bloomberg_ticker.strip()

    if not bloomberg_ticker.endswith(" JP Equity"):
        raise ValueError(
            f"Invalid Bloomberg ticker format: '{bloomberg_ticker}'. "
            "Expected format: 'NNNN JP Equity' or 'NNNNJ JP Equity'"
        )

    # Extract base code
    base_code = bloomberg_ticker[:-10].strip()  # Remove " JP Equity"

    # Validate base code format (4 digits, optional J)
    pattern = r'^(\d{4})(J)?$'
    if not re.match(pattern, base_code):
        raise ValueError(
            f"Invalid Bloomberg ticker format: '{bloomberg_ticker}'. "
            f"Code '{base_code}' must be exactly 4 digits (optionally followed by 'J'). "
            "Expected format: 'NNNN JP Equity' or 'NNNNJ JP Equity'"
        )

    return f"{base_code}.T"
