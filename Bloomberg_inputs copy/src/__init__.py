"""
Bloomberg Activist Data Pipeline - Core Utilities

This package contains core utilities for:
    - Converting Japanese ticker formats (TSE .T → Bloomberg JP Equity)
    - Aligning fiscal periods for point-in-time data extraction
    - Managing Bloomberg DAPI session lifecycle with robust error handling
"""

__version__ = "0.1.0"

# Import Bloomberg session manager (graceful fallback if blpapi not installed)
try:
    from src.bloomberg_session import (
        BloombergSession,
        BloombergConnectionError,
        BloombergRateLimitError,
        BloombergFieldError
    )
    BLOOMBERG_SESSION_AVAILABLE = True
except ImportError:
    BLOOMBERG_SESSION_AVAILABLE = False
    BloombergSession = None
    BloombergConnectionError = None
    BloombergRateLimitError = None
    BloombergFieldError = None

__all__ = [
    # Bloomberg session (may be None if blpapi not installed)
    "BloombergSession",
    "BloombergConnectionError",
    "BloombergRateLimitError",
    "BloombergFieldError",
    "BLOOMBERG_SESSION_AVAILABLE"
]
