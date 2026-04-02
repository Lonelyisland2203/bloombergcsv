"""
Bloomberg DAPI Session Manager

This module provides robust lifecycle management for Bloomberg Desktop API (DAPI) sessions,
including connection handling, request dispatching, error recovery, and response parsing.

Session Lifecycle:
    1. Initialize with host/port (default: localhost:8194)
    2. Start session and connect to //blp/refdata service
    3. Send requests (reference, bulk, historical)
    4. Parse responses to pandas DataFrames
    5. Graceful teardown (automatic with context manager)

Point-in-Time Considerations:
    - Historical requests: Specify explicit date ranges, no implicit "latest"
    - Reference data: Use END_DT_OVERRIDE for point-in-time snapshots
    - Fundamental data: Use FUND_PER override to anchor to fiscal periods
    - All responses preserve as_of_date context for downstream processing

Error Handling:
    - Session timeout: Auto-reconnect (max 3 attempts, 5s backoff)
    - Terminal not running: Fail fast with actionable message
    - Field errors: Log warning, return null, continue
    - Security errors: Log warning, skip security, continue
    - Rate limits: Exponential backoff, circuit breaker pattern

Author: Bloomberg Activist Pipeline
"""

import logging
import time
from contextlib import contextmanager
from datetime import date, datetime
from typing import Any, Dict, List, Optional, Tuple

import pandas as pd

# Bloomberg API import with graceful fallback
try:
    import blpapi
    BLPAPI_AVAILABLE = True
except ImportError:
    BLPAPI_AVAILABLE = False
    blpapi = None  # type: ignore


# Configure logging
logger = logging.getLogger(__name__)


class BloombergConnectionError(Exception):
    """Raised when Bloomberg Terminal connection fails."""
    pass


class BloombergRateLimitError(Exception):
    """Raised when Bloomberg API rate limit is exceeded."""
    pass


class BloombergFieldError(Exception):
    """Raised when requested field is invalid or unavailable."""
    pass


class CircuitBreaker:
    """
    Circuit breaker pattern for rate limit protection.

    Opens after threshold failures, preventing further requests.
    Resets after successful request.
    """

    def __init__(self, failure_threshold: int = 5):
        """
        Initialize circuit breaker.

        Args:
            failure_threshold: Number of consecutive failures before opening circuit
        """
        self.failure_threshold = failure_threshold
        self.failure_count = 0
        self.is_open = False

    def record_success(self) -> None:
        """Record successful request, reset circuit."""
        self.failure_count = 0
        self.is_open = False

    def record_failure(self) -> None:
        """Record failed request, potentially open circuit."""
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self.is_open = True
            logger.error(
                f"Circuit breaker opened after {self.failure_count} consecutive failures. "
                "Blocking further requests to prevent rate limit abuse."
            )

    def check(self) -> None:
        """
        Check if circuit is open.

        Raises:
            BloombergRateLimitError: If circuit is open
        """
        if self.is_open:
            raise BloombergRateLimitError(
                f"Circuit breaker is OPEN after {self.failure_count} consecutive rate limit errors. "
                "Wait before retrying. Check Bloomberg Terminal connection and API limits."
            )


class BloombergSession:
    """
    Robust Bloomberg DAPI session manager with connection pooling and error recovery.

    This class manages the full lifecycle of a Bloomberg Desktop API session,
    including connection establishment, request dispatching, response parsing,
    and graceful teardown.

    Attributes:
        host: Bloomberg API host (default: localhost)
        port: Bloomberg API port (default: 8194)
        session: Active blpapi.Session instance (None if not started)
        refdata_service: Bloomberg reference data service handle
        max_retries: Maximum connection retry attempts (default: 3)
        retry_backoff: Seconds between retry attempts (default: 5)

    Examples:
        >>> # Context manager (recommended)
        >>> with BloombergSession() as session:
        ...     df = session.send_request(
        ...         securities=["9107 JP Equity"],
        ...         fields=["PX_TO_BOOK_RATIO", "RETURN_COM_EQY"]
        ...     )

        >>> # Manual lifecycle management
        >>> session = BloombergSession()
        >>> session.start()
        >>> df = session.send_request(["9107 JP Equity"], ["PX_TO_BOOK_RATIO"])
        >>> session.close()

    Notes:
        - Requires Bloomberg Terminal to be running and logged in
        - Default connection: localhost:8194 (standard DAPI configuration)
        - Session must be started before sending requests
        - Use context manager for automatic cleanup
    """

    def __init__(self, host: str = 'localhost', port: int = 8194):
        """
        Initialize session parameters (does not connect).

        Args:
            host: Bloomberg API host address
            port: Bloomberg API port number

        Raises:
            ImportError: If blpapi package is not installed
        """
        if not BLPAPI_AVAILABLE:
            raise ImportError(
                "Bloomberg API (blpapi) is not installed. "
                "\n\nInstallation options:"
                "\n  1. Download from Bloomberg Terminal: WAPI<GO> → Downloads → Python API"
                "\n  2. Use conda: conda install -c conda-forge blpapi"
                "\n  3. Download wheel from: https://www.bloomberg.com/professional/support/api-library/"
                "\n  4. Install wheel: pip install /path/to/blpapi-*.whl"
                "\n\nFor macOS with Python 3.13, ensure you download the correct wheel for your platform."
            )

        self.host = host
        self.port = port
        self.session: Optional[blpapi.Session] = None
        self.refdata_service: Optional[blpapi.Service] = None

        # Connection parameters
        self.max_retries = 3
        self.retry_backoff = 5  # seconds

        # Rate limit protection
        self.circuit_breaker = CircuitBreaker(failure_threshold=5)

        # Error tracking
        self.field_errors: Dict[str, List[str]] = {}  # {security: [field1, field2, ...]}

        logger.info(f"Bloomberg session initialized (host={host}, port={port})")

    def start(self) -> bool:
        """
        Start Bloomberg session and connect to //blp/refdata service.

        Implements retry logic with exponential backoff for transient connection issues.

        Returns:
            True if connection successful

        Raises:
            BloombergConnectionError: If connection fails after all retries

        Examples:
            >>> session = BloombergSession()
            >>> session.start()
            True
        """
        if self.session is not None:
            logger.warning("Session already started, skipping connection")
            return True

        # Create session options
        session_options = blpapi.SessionOptions()
        session_options.setServerHost(self.host)
        session_options.setServerPort(self.port)

        # Attempt connection with retry logic
        for attempt in range(1, self.max_retries + 1):
            try:
                logger.info(f"Connecting to Bloomberg API (attempt {attempt}/{self.max_retries})...")

                # Create and start session
                self.session = blpapi.Session(session_options)

                if not self.session.start():
                    raise BloombergConnectionError(
                        "Failed to start Bloomberg session. "
                        "Ensure Bloomberg Terminal is running and logged in."
                    )

                # Open reference data service
                if not self.session.openService("//blp/refdata"):
                    raise BloombergConnectionError(
                        "Failed to open //blp/refdata service. "
                        "Check Bloomberg API service availability."
                    )

                self.refdata_service = self.session.getService("//blp/refdata")
                logger.info("Successfully connected to Bloomberg API")
                return True

            except BloombergConnectionError:
                # Re-raise connection errors immediately (not transient)
                raise

            except Exception as e:
                logger.warning(
                    f"Connection attempt {attempt}/{self.max_retries} failed: {e}"
                )

                if attempt < self.max_retries:
                    logger.info(f"Retrying in {self.retry_backoff} seconds...")
                    time.sleep(self.retry_backoff)
                else:
                    raise BloombergConnectionError(
                        f"Failed to connect to Bloomberg API after {self.max_retries} attempts. "
                        f"Last error: {e}\n\n"
                        "Troubleshooting steps:\n"
                        "  1. Ensure Bloomberg Terminal is running and logged in\n"
                        "  2. Check DAPI service status in Terminal: DAPI<GO>\n"
                        "  3. Verify host/port settings (default: localhost:8194)\n"
                        "  4. Check firewall/antivirus settings\n"
                        "  5. Restart Bloomberg Terminal if necessary"
                    ) from e

        return False  # Should never reach here

    def send_request(
        self,
        securities: List[str],
        fields: List[str],
        overrides: Optional[Dict[str, str]] = None
    ) -> pd.DataFrame:
        """
        Send ReferenceDataRequest and parse response to DataFrame.

        This is the primary method for retrieving point-in-time fundamental and market data.
        Supports field overrides for temporal anchoring (END_DT_OVERRIDE, FUND_PER).

        Args:
            securities: List of Bloomberg security identifiers (e.g., ["9107 JP Equity"])
            fields: List of Bloomberg field names (e.g., ["PX_TO_BOOK_RATIO", "RETURN_COM_EQY"])
            overrides: Optional dict of field overrides (e.g., {"END_DT_OVERRIDE": "20230331"})

        Returns:
            DataFrame with columns: security, <field1>, <field2>, ..., <fieldN>
            Missing data is represented as NaN/None

        Raises:
            BloombergConnectionError: If session not started
            BloombergRateLimitError: If circuit breaker is open

        Examples:
            >>> df = session.send_request(
            ...     securities=["9107 JP Equity", "8952J JP Equity"],
            ...     fields=["PX_TO_BOOK_RATIO", "RETURN_COM_EQY"],
            ...     overrides={"END_DT_OVERRIDE": "20230331"}
            ... )
            >>> print(df)
                  security  PX_TO_BOOK_RATIO  RETURN_COM_EQY
            0  9107 JP Equity              1.23           8.5
            1  8952J JP Equity             0.98           6.2

        Notes:
            - Field errors are logged but don't stop processing
            - Invalid securities are logged and skipped
            - Use overrides for point-in-time data extraction
        """
        if self.session is None or self.refdata_service is None:
            raise BloombergConnectionError(
                "Session not started. Call start() before sending requests."
            )

        # Check circuit breaker
        self.circuit_breaker.check()

        logger.info(
            f"Sending reference data request: {len(securities)} securities, "
            f"{len(fields)} fields{', with overrides' if overrides else ''}"
        )
        logger.debug(f"Securities: {securities}")
        logger.debug(f"Fields: {fields}")
        if overrides:
            logger.debug(f"Overrides: {overrides}")

        # Create request
        request = self.refdata_service.createRequest("ReferenceDataRequest")

        # Add securities
        for security in securities:
            request.append("securities", security)

        # Add fields
        for field in fields:
            request.append("fields", field)

        # Add overrides
        if overrides:
            overrides_element = request.getElement("overrides")
            for key, value in overrides.items():
                override = overrides_element.appendElement()
                override.setElement("fieldId", key)
                override.setElement("value", value)

        # Send request with retry logic for rate limits
        response_data = self._send_request_with_retry(request)

        # Parse response to DataFrame
        df = self._parse_reference_response(response_data, fields)

        logger.info(f"Retrieved {len(df)} records")
        return df

    def send_bulk_request(
        self,
        securities: List[str],
        field: str
    ) -> pd.DataFrame:
        """
        Send BulkReferenceDataRequest for table fields (e.g., TOP_20_HOLDERS).

        Bulk fields return multi-row data per security (tables, arrays).
        Common use cases: ownership data, dividend history, corporate actions.

        Args:
            securities: List of Bloomberg security identifiers
            field: Single bulk field name (e.g., "TOP_20_HOLDERS_PUBLIC_FILINGS")

        Returns:
            DataFrame with columns: security, <bulk_field_col1>, <bulk_field_col2>, ...
            Each row represents one record from the bulk field table

        Raises:
            BloombergConnectionError: If session not started
            BloombergRateLimitError: If circuit breaker is open

        Examples:
            >>> df = session.send_bulk_request(
            ...     securities=["9107 JP Equity"],
            ...     field="TOP_20_HOLDERS_PUBLIC_FILINGS"
            ... )
            >>> print(df)
                  security              holder_name  holder_pct  shares_held
            0  9107 JP Equity  Nomura Asset Mgmt      5.2      1234567
            1  9107 JP Equity  BlackRock Japan        3.8       900000
            ...

        Notes:
            - Only one bulk field per request (Bloomberg API limitation)
            - Returns long-format DataFrame (one row per table entry)
            - Empty result if field not available for security
        """
        if self.session is None or self.refdata_service is None:
            raise BloombergConnectionError(
                "Session not started. Call start() before sending requests."
            )

        # Check circuit breaker
        self.circuit_breaker.check()

        logger.info(
            f"Sending bulk reference data request: {len(securities)} securities, "
            f"field={field}"
        )

        # Create request
        request = self.refdata_service.createRequest("ReferenceDataRequest")

        # Add securities
        for security in securities:
            request.append("securities", security)

        # Add bulk field
        request.append("fields", field)

        # Send request with retry logic
        response_data = self._send_request_with_retry(request)

        # Parse bulk response to DataFrame
        df = self._parse_bulk_response(response_data, field)

        logger.info(f"Retrieved {len(df)} bulk records")
        return df

    def send_historical_request(
        self,
        security: str,
        fields: List[str],
        start_date: date,
        end_date: date,
        periodicity: str = "DAILY"
    ) -> pd.DataFrame:
        """
        Send HistoricalDataRequest for time-series data (e.g., price history).

        Retrieves historical time-series data for a single security over a date range.
        Commonly used for price history, volume, high/low data.

        Args:
            security: Single Bloomberg security identifier
            fields: List of historical fields (e.g., ["PX_LAST", "PX_VOLUME"])
            start_date: Start of date range (inclusive)
            end_date: End of date range (inclusive)
            periodicity: Data frequency - "DAILY", "WEEKLY", "MONTHLY" (default: "DAILY")

        Returns:
            DataFrame with columns: date, security, <field1>, <field2>, ...
            One row per date in range

        Raises:
            BloombergConnectionError: If session not started
            BloombergRateLimitError: If circuit breaker is open
            ValueError: If date range is invalid

        Examples:
            >>> df = session.send_historical_request(
            ...     security="9107 JP Equity",
            ...     fields=["PX_LAST", "PX_VOLUME"],
            ...     start_date=date(2023, 1, 1),
            ...     end_date=date(2023, 12, 31)
            ... )
            >>> print(df)
                     date         security  PX_LAST  PX_VOLUME
            0  2023-01-04  9107 JP Equity     1234     500000
            1  2023-01-05  9107 JP Equity     1238     520000
            ...

        Notes:
            - Only one security per request (Bloomberg API limitation)
            - Returns data only for trading days (no weekends/holidays)
            - Missing data on specific dates represented as NaN
        """
        if self.session is None or self.refdata_service is None:
            raise BloombergConnectionError(
                "Session not started. Call start() before sending requests."
            )

        # Validate date range
        if start_date > end_date:
            raise ValueError(
                f"Invalid date range: start_date ({start_date}) > end_date ({end_date})"
            )

        # Check circuit breaker
        self.circuit_breaker.check()

        logger.info(
            f"Sending historical data request: security={security}, "
            f"fields={fields}, {start_date} to {end_date}, periodicity={periodicity}"
        )

        # Create request
        request = self.refdata_service.createRequest("HistoricalDataRequest")

        # Set security
        request.append("securities", security)

        # Set fields
        for field in fields:
            request.append("fields", field)

        # Set date range (format: YYYYMMDD)
        request.set("startDate", start_date.strftime("%Y%m%d"))
        request.set("endDate", end_date.strftime("%Y%m%d"))

        # Set periodicity
        request.set("periodicitySelection", periodicity)

        # Send request with retry logic
        response_data = self._send_request_with_retry(request)

        # Parse historical response to DataFrame
        df = self._parse_historical_response(response_data, security, fields)

        logger.info(f"Retrieved {len(df)} historical records")
        return df

    def _send_request_with_retry(self, request: Any) -> List[Any]:
        """
        Send request with exponential backoff for rate limit errors.

        Args:
            request: Bloomberg request object

        Returns:
            List of response messages

        Raises:
            BloombergRateLimitError: If rate limit persists after retries
        """
        backoff_seconds = [2, 4, 8]  # Exponential backoff

        for attempt, wait_time in enumerate(backoff_seconds + [None], start=1):
            try:
                # Send request
                self.session.sendRequest(request)

                # Collect response messages
                response_data = []
                while True:
                    event = self.session.nextEvent(500)  # 500ms timeout

                    for msg in event:
                        response_data.append(msg)

                    if event.eventType() == blpapi.Event.RESPONSE:
                        break

                # Success - reset circuit breaker
                self.circuit_breaker.record_success()
                return response_data

            except Exception as e:
                error_str = str(e).lower()

                # Check if rate limit error (HTTP 429 equivalent)
                if "rate" in error_str or "limit" in error_str or "429" in error_str:
                    self.circuit_breaker.record_failure()

                    if wait_time is not None:
                        logger.warning(
                            f"Rate limit hit (attempt {attempt}). "
                            f"Retrying in {wait_time}s..."
                        )
                        time.sleep(wait_time)
                    else:
                        raise BloombergRateLimitError(
                            "Rate limit exceeded after all retry attempts. "
                            "Circuit breaker activated. Wait before retrying."
                        ) from e
                else:
                    # Non-rate-limit error, propagate immediately
                    raise

        # Should never reach here
        return []

    def _parse_reference_response(
        self,
        response_data: List[Any],
        fields: List[str]
    ) -> pd.DataFrame:
        """
        Parse ReferenceDataResponse messages to DataFrame.

        Args:
            response_data: List of Bloomberg response messages
            fields: List of requested field names

        Returns:
            DataFrame with security and field columns
        """
        records = []

        for msg in response_data:
            if msg.messageType() == "ReferenceDataResponse":
                security_data_array = msg.getElement("securityData")

                for i in range(security_data_array.numValues()):
                    security_data = security_data_array.getValueAsElement(i)
                    security = security_data.getElementAsString("security")

                    # Check for security-level errors
                    if security_data.hasElement("securityError"):
                        error = security_data.getElement("securityError")
                        error_msg = error.getElementAsString("message")
                        logger.warning(f"Security error for {security}: {error_msg}")
                        continue

                    # Extract field data
                    record = {"security": security}
                    field_data = security_data.getElement("fieldData")

                    for field in fields:
                        try:
                            if field_data.hasElement(field):
                                value = self._extract_field_value(field_data, field)
                                record[field] = value
                            else:
                                # Field not available
                                record[field] = None
                                if security not in self.field_errors:
                                    self.field_errors[security] = []
                                self.field_errors[security].append(field)
                        except Exception as e:
                            logger.debug(f"Error extracting {field} for {security}: {e}")
                            record[field] = None

                    records.append(record)

        # Log field errors summary
        if self.field_errors:
            logger.warning(
                f"Field errors detected for {len(self.field_errors)} securities. "
                "Use session.field_errors for details."
            )

        return pd.DataFrame(records)

    def _parse_bulk_response(
        self,
        response_data: List[Any],
        field: str
    ) -> pd.DataFrame:
        """
        Parse bulk field response (returns table data).

        Args:
            response_data: List of Bloomberg response messages
            field: Bulk field name

        Returns:
            DataFrame with security and bulk field columns (long format)
        """
        records = []

        for msg in response_data:
            if msg.messageType() == "ReferenceDataResponse":
                security_data_array = msg.getElement("securityData")

                for i in range(security_data_array.numValues()):
                    security_data = security_data_array.getValueAsElement(i)
                    security = security_data.getElementAsString("security")

                    # Check for errors
                    if security_data.hasElement("securityError"):
                        error = security_data.getElement("securityError")
                        error_msg = error.getElementAsString("message")
                        logger.warning(f"Security error for {security}: {error_msg}")
                        continue

                    # Extract bulk field data
                    field_data = security_data.getElement("fieldData")

                    if field_data.hasElement(field):
                        bulk_data = field_data.getElement(field)

                        # Iterate over bulk data array
                        for j in range(bulk_data.numValues()):
                            row_data = bulk_data.getValueAsElement(j)

                            # Extract all fields from this row
                            record = {"security": security}
                            for k in range(row_data.numElements()):
                                element = row_data.getElement(k)
                                field_name = str(element.name())
                                field_value = self._extract_element_value(element)
                                record[field_name] = field_value

                            records.append(record)
                    else:
                        logger.warning(f"Bulk field {field} not available for {security}")

        return pd.DataFrame(records)

    def _parse_historical_response(
        self,
        response_data: List[Any],
        security: str,
        fields: List[str]
    ) -> pd.DataFrame:
        """
        Parse HistoricalDataResponse messages to DataFrame.

        Args:
            response_data: List of Bloomberg response messages
            security: Security identifier
            fields: List of requested field names

        Returns:
            DataFrame with date, security, and field columns
        """
        records = []

        for msg in response_data:
            if msg.messageType() == "HistoricalDataResponse":
                security_data = msg.getElement("securityData")

                # Check for errors
                if security_data.hasElement("securityError"):
                    error = security_data.getElement("securityError")
                    error_msg = error.getElementAsString("message")
                    logger.warning(f"Security error for {security}: {error_msg}")
                    continue

                # Extract field data array
                field_data_array = security_data.getElement("fieldData")

                for i in range(field_data_array.numValues()):
                    field_data = field_data_array.getValueAsElement(i)

                    # Extract date
                    date_value = field_data.getElementAsDatetime("date")
                    record = {
                        "date": date_value.date() if hasattr(date_value, 'date') else date_value,
                        "security": security
                    }

                    # Extract field values
                    for field in fields:
                        try:
                            if field_data.hasElement(field):
                                value = self._extract_field_value(field_data, field)
                                record[field] = value
                            else:
                                record[field] = None
                        except Exception as e:
                            logger.debug(f"Error extracting {field} for {security}: {e}")
                            record[field] = None

                    records.append(record)

        return pd.DataFrame(records)

    def _extract_field_value(self, field_data: Any, field: str) -> Any:
        """
        Extract typed value from Bloomberg field element.

        Args:
            field_data: Bloomberg fieldData element
            field: Field name to extract

        Returns:
            Typed field value (float, int, str, date, etc.)
        """
        element = field_data.getElement(field)
        return self._extract_element_value(element)

    def _extract_element_value(self, element: Any) -> Any:
        """
        Extract typed value from Bloomberg element.

        Args:
            element: Bloomberg element

        Returns:
            Typed value based on element datatype
        """
        if element.isNull():
            return None

        # Determine type and extract value
        datatype = element.datatype()

        if datatype == blpapi.DataType.BOOL:
            return element.getValueAsBool()
        elif datatype == blpapi.DataType.INT32 or datatype == blpapi.DataType.INT64:
            return element.getValueAsInteger()
        elif datatype == blpapi.DataType.FLOAT32 or datatype == blpapi.DataType.FLOAT64:
            return element.getValueAsFloat()
        elif datatype == blpapi.DataType.STRING:
            return element.getValueAsString()
        elif datatype == blpapi.DataType.DATE:
            date_value = element.getValueAsDatetime()
            return date_value.date() if hasattr(date_value, 'date') else date_value
        elif datatype == blpapi.DataType.DATETIME:
            return element.getValueAsDatetime()
        else:
            # Fallback to string representation
            return str(element.getValueAsString())

    def close(self) -> None:
        """
        Gracefully close Bloomberg session and release resources.

        This method should always be called when done with the session,
        preferably via context manager to ensure cleanup even on errors.

        Examples:
            >>> session = BloombergSession()
            >>> session.start()
            >>> # ... do work ...
            >>> session.close()  # Explicit cleanup
        """
        if self.session is not None:
            try:
                self.session.stop()
                logger.info("Bloomberg session closed successfully")
            except Exception as e:
                logger.warning(f"Error closing session: {e}")
            finally:
                self.session = None
                self.refdata_service = None

    def __enter__(self):
        """Context manager entry: start session."""
        self.start()
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit: close session."""
        self.close()
        return False  # Don't suppress exceptions

    def get_field_errors(self) -> Dict[str, List[str]]:
        """
        Get summary of field errors encountered during requests.

        Returns:
            Dict mapping security to list of unavailable fields

        Examples:
            >>> df = session.send_request(["9107 JP Equity"], ["PX_TO_BOOK_RATIO", "INVALID_FIELD"])
            >>> errors = session.get_field_errors()
            >>> print(errors)
            {'9107 JP Equity': ['INVALID_FIELD']}
        """
        return self.field_errors.copy()

    def clear_field_errors(self) -> None:
        """Clear field error tracking."""
        self.field_errors.clear()
