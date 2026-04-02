"""
Unit Tests for Bloomberg Session Manager

Tests Bloomberg DAPI session lifecycle, request handling, response parsing,
and error recovery using mocked blpapi responses.

These tests do NOT require a live Bloomberg Terminal connection.
For integration testing with real Bloomberg API, see test_integration_bloomberg.py.

Author: Bloomberg Activist Pipeline
"""

import unittest
from datetime import date
from unittest.mock import MagicMock, Mock, patch, call

import pandas as pd
import pytest

# Import the module (will work even if blpapi not installed due to graceful fallback)
from src.bloomberg_session import (
    BloombergSession,
    BloombergConnectionError,
    BloombergRateLimitError,
    CircuitBreaker,
    BLPAPI_AVAILABLE
)


class TestCircuitBreaker(unittest.TestCase):
    """Test circuit breaker pattern for rate limit protection."""

    def test_circuit_breaker_initial_state(self):
        """Circuit breaker starts closed."""
        cb = CircuitBreaker(failure_threshold=3)
        self.assertFalse(cb.is_open)
        self.assertEqual(cb.failure_count, 0)

    def test_circuit_breaker_opens_after_threshold(self):
        """Circuit breaker opens after threshold failures."""
        cb = CircuitBreaker(failure_threshold=3)

        # Record failures
        cb.record_failure()
        self.assertFalse(cb.is_open)
        self.assertEqual(cb.failure_count, 1)

        cb.record_failure()
        self.assertFalse(cb.is_open)
        self.assertEqual(cb.failure_count, 2)

        cb.record_failure()
        self.assertTrue(cb.is_open)
        self.assertEqual(cb.failure_count, 3)

    def test_circuit_breaker_blocks_when_open(self):
        """Circuit breaker raises error when open."""
        cb = CircuitBreaker(failure_threshold=2)
        cb.record_failure()
        cb.record_failure()

        self.assertTrue(cb.is_open)

        with pytest.raises(BloombergRateLimitError, match="Circuit breaker is OPEN"):
            cb.check()

    def test_circuit_breaker_resets_on_success(self):
        """Circuit breaker resets after successful request."""
        cb = CircuitBreaker(failure_threshold=3)

        # Record some failures
        cb.record_failure()
        cb.record_failure()
        self.assertEqual(cb.failure_count, 2)

        # Success resets
        cb.record_success()
        self.assertFalse(cb.is_open)
        self.assertEqual(cb.failure_count, 0)


class TestBloombergSessionInitialization(unittest.TestCase):
    """Test Bloomberg session initialization and connection."""

    @patch('src.bloomberg_session.BLPAPI_AVAILABLE', False)
    def test_init_without_blpapi_installed(self):
        """Session initialization fails gracefully if blpapi not installed."""
        with pytest.raises(ImportError, match="Bloomberg API.*is not installed"):
            BloombergSession()

    @patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
    @patch('src.bloomberg_session.blpapi')
    def test_init_with_default_parameters(self, mock_blpapi):
        """Session initializes with default host/port."""
        session = BloombergSession()

        self.assertEqual(session.host, 'localhost')
        self.assertEqual(session.port, 8194)
        self.assertIsNone(session.session)
        self.assertIsNone(session.refdata_service)

    @patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
    @patch('src.bloomberg_session.blpapi')
    def test_init_with_custom_parameters(self, mock_blpapi):
        """Session initializes with custom host/port."""
        session = BloombergSession(host='192.168.1.100', port=9000)

        self.assertEqual(session.host, '192.168.1.100')
        self.assertEqual(session.port, 9000)

    @patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
    @patch('src.bloomberg_session.blpapi')
    def test_start_success(self, mock_blpapi):
        """Session starts successfully with mock Bloomberg API."""
        # Mock SessionOptions
        mock_session_options = MagicMock()
        mock_blpapi.SessionOptions.return_value = mock_session_options

        # Mock Session
        mock_session_instance = MagicMock()
        mock_session_instance.start.return_value = True
        mock_session_instance.openService.return_value = True
        mock_blpapi.Session.return_value = mock_session_instance

        # Mock Service
        mock_service = MagicMock()
        mock_session_instance.getService.return_value = mock_service

        # Start session
        session = BloombergSession()
        result = session.start()

        self.assertTrue(result)
        self.assertIsNotNone(session.session)
        self.assertIsNotNone(session.refdata_service)

        # Verify session configuration
        mock_session_options.setServerHost.assert_called_once_with('localhost')
        mock_session_options.setServerPort.assert_called_once_with(8194)

    @patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
    @patch('src.bloomberg_session.blpapi')
    def test_start_failure_terminal_not_running(self, mock_blpapi):
        """Session start fails when Bloomberg Terminal not running."""
        # Mock Session that fails to start
        mock_session_instance = MagicMock()
        mock_session_instance.start.return_value = False
        mock_blpapi.Session.return_value = mock_session_instance

        session = BloombergSession()

        with pytest.raises(BloombergConnectionError, match="Failed to start Bloomberg session"):
            session.start()

    @patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
    @patch('src.bloomberg_session.blpapi')
    def test_start_already_started(self, mock_blpapi):
        """Starting an already-started session is idempotent."""
        # Mock successful session
        mock_session_instance = MagicMock()
        mock_session_instance.start.return_value = True
        mock_session_instance.openService.return_value = True
        mock_blpapi.Session.return_value = mock_session_instance

        session = BloombergSession()
        session.start()

        # Try to start again
        result = session.start()
        self.assertTrue(result)

        # Session.start should only be called once
        self.assertEqual(mock_session_instance.start.call_count, 1)


class TestBloombergSessionRequests(unittest.TestCase):
    """Test request dispatching and response parsing."""

    def setUp(self):
        """Set up mock Bloomberg session for each test."""
        self.patcher_available = patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
        self.patcher_blpapi = patch('src.bloomberg_session.blpapi')

        self.patcher_available.start()
        self.mock_blpapi = self.patcher_blpapi.start()

        # Mock session setup
        self.mock_session_instance = MagicMock()
        self.mock_session_instance.start.return_value = True
        self.mock_session_instance.openService.return_value = True
        self.mock_blpapi.Session.return_value = self.mock_session_instance

        # Mock service
        self.mock_service = MagicMock()
        self.mock_session_instance.getService.return_value = self.mock_service

        # Mock event types
        self.mock_blpapi.Event.RESPONSE = 5  # Bloomberg constant

    def tearDown(self):
        """Clean up patches."""
        self.patcher_available.stop()
        self.patcher_blpapi.stop()

    def test_send_request_without_session(self):
        """Sending request before starting session raises error."""
        session = BloombergSession()

        with pytest.raises(BloombergConnectionError, match="Session not started"):
            session.send_request(
                securities=["9107 JP Equity"],
                fields=["PX_TO_BOOK_RATIO"]
            )

    def test_send_request_success(self):
        """Reference data request returns DataFrame."""
        session = BloombergSession()
        session.start()

        # Mock request
        mock_request = MagicMock()
        self.mock_service.createRequest.return_value = mock_request

        # Mock response message
        mock_msg = self._create_mock_reference_response(
            security="9107 JP Equity",
            fields_data={"PX_TO_BOOK_RATIO": 1.23, "RETURN_COM_EQY": 8.5}
        )

        # Mock event
        mock_event = MagicMock()
        mock_event.eventType.return_value = self.mock_blpapi.Event.RESPONSE
        mock_event.__iter__.return_value = [mock_msg]

        self.mock_session_instance.nextEvent.return_value = mock_event

        # Send request
        df = session.send_request(
            securities=["9107 JP Equity"],
            fields=["PX_TO_BOOK_RATIO", "RETURN_COM_EQY"]
        )

        # Verify DataFrame
        self.assertEqual(len(df), 1)
        self.assertEqual(df.iloc[0]["security"], "9107 JP Equity")
        self.assertEqual(df.iloc[0]["PX_TO_BOOK_RATIO"], 1.23)
        self.assertEqual(df.iloc[0]["RETURN_COM_EQY"], 8.5)

    def test_send_request_with_overrides(self):
        """Request with field overrides is properly constructed."""
        session = BloombergSession()
        session.start()

        # Mock request
        mock_request = MagicMock()
        self.mock_service.createRequest.return_value = mock_request

        # Mock response
        mock_msg = self._create_mock_reference_response(
            security="9107 JP Equity",
            fields_data={"PX_TO_BOOK_RATIO": 1.23}
        )
        mock_event = MagicMock()
        mock_event.eventType.return_value = self.mock_blpapi.Event.RESPONSE
        mock_event.__iter__.return_value = [mock_msg]
        self.mock_session_instance.nextEvent.return_value = mock_event

        # Send request with overrides
        df = session.send_request(
            securities=["9107 JP Equity"],
            fields=["PX_TO_BOOK_RATIO"],
            overrides={"END_DT_OVERRIDE": "20230331"}
        )

        # Verify override was set
        mock_request.getElement.assert_called_with("overrides")

    def test_send_request_missing_field(self):
        """Missing field returns NaN in DataFrame."""
        session = BloombergSession()
        session.start()

        # Mock request
        mock_request = MagicMock()
        self.mock_service.createRequest.return_value = mock_request

        # Mock response with missing field
        mock_msg = self._create_mock_reference_response(
            security="9107 JP Equity",
            fields_data={"PX_TO_BOOK_RATIO": 1.23}  # RETURN_COM_EQY missing
        )
        mock_event = MagicMock()
        mock_event.eventType.return_value = self.mock_blpapi.Event.RESPONSE
        mock_event.__iter__.return_value = [mock_msg]
        self.mock_session_instance.nextEvent.return_value = mock_event

        # Send request
        df = session.send_request(
            securities=["9107 JP Equity"],
            fields=["PX_TO_BOOK_RATIO", "RETURN_COM_EQY"]
        )

        # Verify missing field is None
        self.assertEqual(df.iloc[0]["PX_TO_BOOK_RATIO"], 1.23)
        self.assertIsNone(df.iloc[0]["RETURN_COM_EQY"])

        # Verify field error was tracked
        errors = session.get_field_errors()
        self.assertIn("9107 JP Equity", errors)
        self.assertIn("RETURN_COM_EQY", errors["9107 JP Equity"])

    def test_send_request_invalid_security(self):
        """Invalid security is skipped, logged, but doesn't fail."""
        session = BloombergSession()
        session.start()

        # Mock request
        mock_request = MagicMock()
        self.mock_service.createRequest.return_value = mock_request

        # Mock response with security error
        mock_msg = self._create_mock_reference_response_with_error(
            security="INVALID JP Equity",
            error_message="Unknown security"
        )
        mock_event = MagicMock()
        mock_event.eventType.return_value = self.mock_blpapi.Event.RESPONSE
        mock_event.__iter__.return_value = [mock_msg]
        self.mock_session_instance.nextEvent.return_value = mock_event

        # Send request (should not raise)
        df = session.send_request(
            securities=["INVALID JP Equity"],
            fields=["PX_TO_BOOK_RATIO"]
        )

        # Verify empty DataFrame
        self.assertEqual(len(df), 0)

    def test_send_bulk_request(self):
        """Bulk reference data request returns long-format DataFrame."""
        session = BloombergSession()
        session.start()

        # Mock request
        mock_request = MagicMock()
        self.mock_service.createRequest.return_value = mock_request

        # Mock bulk response
        mock_msg = self._create_mock_bulk_response(
            security="9107 JP Equity",
            bulk_data=[
                {"Holder Name": "Nomura Asset Mgmt", "Portfolio % Market Value Held": 5.2},
                {"Holder Name": "BlackRock Japan", "Portfolio % Market Value Held": 3.8}
            ]
        )
        mock_event = MagicMock()
        mock_event.eventType.return_value = self.mock_blpapi.Event.RESPONSE
        mock_event.__iter__.return_value = [mock_msg]
        self.mock_session_instance.nextEvent.return_value = mock_event

        # Send bulk request
        df = session.send_bulk_request(
            securities=["9107 JP Equity"],
            field="TOP_20_HOLDERS_PUBLIC_FILINGS"
        )

        # Verify long-format DataFrame
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["security"], "9107 JP Equity")
        self.assertEqual(df.iloc[0]["Holder Name"], "Nomura Asset Mgmt")
        self.assertEqual(df.iloc[1]["Holder Name"], "BlackRock Japan")

    def test_send_historical_request(self):
        """Historical data request returns time-series DataFrame."""
        session = BloombergSession()
        session.start()

        # Mock request
        mock_request = MagicMock()
        self.mock_service.createRequest.return_value = mock_request

        # Mock historical response
        mock_msg = self._create_mock_historical_response(
            security="9107 JP Equity",
            data_points=[
                {"date": date(2023, 1, 4), "PX_LAST": 1234.0, "PX_VOLUME": 500000},
                {"date": date(2023, 1, 5), "PX_LAST": 1238.0, "PX_VOLUME": 520000}
            ]
        )
        mock_event = MagicMock()
        mock_event.eventType.return_value = self.mock_blpapi.Event.RESPONSE
        mock_event.__iter__.return_value = [mock_msg]
        self.mock_session_instance.nextEvent.return_value = mock_event

        # Send historical request
        df = session.send_historical_request(
            security="9107 JP Equity",
            fields=["PX_LAST", "PX_VOLUME"],
            start_date=date(2023, 1, 1),
            end_date=date(2023, 1, 31)
        )

        # Verify time-series DataFrame
        self.assertEqual(len(df), 2)
        self.assertEqual(df.iloc[0]["date"], date(2023, 1, 4))
        self.assertEqual(df.iloc[0]["PX_LAST"], 1234.0)
        self.assertEqual(df.iloc[1]["date"], date(2023, 1, 5))

    def test_send_historical_request_invalid_date_range(self):
        """Historical request with invalid date range raises ValueError."""
        session = BloombergSession()
        session.start()

        with pytest.raises(ValueError, match="Invalid date range"):
            session.send_historical_request(
                security="9107 JP Equity",
                fields=["PX_LAST"],
                start_date=date(2023, 12, 31),
                end_date=date(2023, 1, 1)  # End before start
            )

    # Helper methods to create mock Bloomberg responses

    def _create_mock_reference_response(self, security: str, fields_data: dict):
        """Create mock ReferenceDataResponse message."""
        mock_msg = MagicMock()
        mock_msg.messageType.return_value = "ReferenceDataResponse"

        # Mock security data array
        mock_security_data_array = MagicMock()
        mock_security_data_array.numValues.return_value = 1

        # Mock security data element
        mock_security_data = MagicMock()
        mock_security_data.getElementAsString.return_value = security
        mock_security_data.hasElement.side_effect = lambda x: x != "securityError"

        # Mock field data
        mock_field_data = MagicMock()

        def has_field(field):
            return field in fields_data

        def get_field_element(field):
            mock_element = MagicMock()
            mock_element.isNull.return_value = False
            mock_element.datatype.return_value = self.mock_blpapi.DataType.FLOAT64
            mock_element.getValueAsFloat.return_value = fields_data[field]
            return mock_element

        mock_field_data.hasElement.side_effect = has_field
        mock_field_data.getElement.side_effect = get_field_element

        mock_security_data.getElement.return_value = mock_field_data
        mock_security_data_array.getValueAsElement.return_value = mock_security_data

        mock_msg.getElement.return_value = mock_security_data_array

        # Mock DataType enum
        self.mock_blpapi.DataType = MagicMock()
        self.mock_blpapi.DataType.FLOAT64 = 13

        return mock_msg

    def _create_mock_reference_response_with_error(self, security: str, error_message: str):
        """Create mock ReferenceDataResponse with security error."""
        mock_msg = MagicMock()
        mock_msg.messageType.return_value = "ReferenceDataResponse"

        mock_security_data_array = MagicMock()
        mock_security_data_array.numValues.return_value = 1

        mock_security_data = MagicMock()
        mock_security_data.getElementAsString.return_value = security
        mock_security_data.hasElement.side_effect = lambda x: x == "securityError"

        # Mock error element
        mock_error = MagicMock()
        mock_error.getElementAsString.return_value = error_message
        mock_security_data.getElement.return_value = mock_error

        mock_security_data_array.getValueAsElement.return_value = mock_security_data
        mock_msg.getElement.return_value = mock_security_data_array

        return mock_msg

    def _create_mock_bulk_response(self, security: str, bulk_data: list):
        """Create mock bulk ReferenceDataResponse."""
        mock_msg = MagicMock()
        mock_msg.messageType.return_value = "ReferenceDataResponse"

        mock_security_data_array = MagicMock()
        mock_security_data_array.numValues.return_value = 1

        mock_security_data = MagicMock()
        mock_security_data.getElementAsString.return_value = security
        mock_security_data.hasElement.side_effect = lambda x: x != "securityError"

        # Mock bulk field data
        mock_field_data = MagicMock()
        mock_field_data.hasElement.return_value = True

        mock_bulk_array = MagicMock()
        mock_bulk_array.numValues.return_value = len(bulk_data)

        def get_bulk_row(index):
            row = bulk_data[index]
            mock_row = MagicMock()
            mock_row.numElements.return_value = len(row)

            elements = []
            for i, (key, value) in enumerate(row.items()):
                mock_element = MagicMock()
                mock_element.name.return_value = key
                mock_element.isNull.return_value = False
                mock_element.datatype.return_value = (
                    self.mock_blpapi.DataType.FLOAT64
                    if isinstance(value, float)
                    else self.mock_blpapi.DataType.STRING
                )
                if isinstance(value, float):
                    mock_element.getValueAsFloat.return_value = value
                else:
                    mock_element.getValueAsString.return_value = value
                elements.append(mock_element)

            mock_row.getElement.side_effect = lambda idx: elements[idx]
            return mock_row

        mock_bulk_array.getValueAsElement.side_effect = get_bulk_row
        mock_field_data.getElement.return_value = mock_bulk_array
        mock_security_data.getElement.return_value = mock_field_data

        mock_security_data_array.getValueAsElement.return_value = mock_security_data
        mock_msg.getElement.return_value = mock_security_data_array

        return mock_msg

    def _create_mock_historical_response(self, security: str, data_points: list):
        """Create mock HistoricalDataResponse."""
        mock_msg = MagicMock()
        mock_msg.messageType.return_value = "HistoricalDataResponse"

        mock_security_data = MagicMock()
        mock_security_data.hasElement.side_effect = lambda x: x != "securityError"

        # Mock field data array
        mock_field_data_array = MagicMock()
        mock_field_data_array.numValues.return_value = len(data_points)

        def get_data_point(index):
            point = data_points[index]
            mock_point = MagicMock()

            # Mock date element
            mock_date_element = MagicMock()
            mock_date_element.date.return_value = point["date"]
            mock_point.getElementAsDatetime.return_value = mock_date_element

            # Mock field elements
            def has_field(field):
                return field in point

            def get_field(field):
                mock_element = MagicMock()
                mock_element.isNull.return_value = False
                value = point[field]
                if isinstance(value, float):
                    mock_element.datatype.return_value = self.mock_blpapi.DataType.FLOAT64
                    mock_element.getValueAsFloat.return_value = value
                else:
                    mock_element.datatype.return_value = self.mock_blpapi.DataType.INT64
                    mock_element.getValueAsInteger.return_value = value
                return mock_element

            mock_point.hasElement.side_effect = has_field
            mock_point.getElement.side_effect = get_field
            return mock_point

        mock_field_data_array.getValueAsElement.side_effect = get_data_point
        mock_security_data.getElement.return_value = mock_field_data_array

        mock_msg.getElement.return_value = mock_security_data

        return mock_msg


class TestBloombergSessionErrorHandling(unittest.TestCase):
    """Test error handling and retry logic."""

    def setUp(self):
        """Set up mock Bloomberg session for each test."""
        self.patcher_available = patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
        self.patcher_blpapi = patch('src.bloomberg_session.blpapi')

        self.patcher_available.start()
        self.mock_blpapi = self.patcher_blpapi.start()

        # Mock session setup
        self.mock_session_instance = MagicMock()
        self.mock_session_instance.start.return_value = True
        self.mock_session_instance.openService.return_value = True
        self.mock_blpapi.Session.return_value = self.mock_session_instance

        # Mock service
        self.mock_service = MagicMock()
        self.mock_session_instance.getService.return_value = self.mock_service

        # Mock event types
        self.mock_blpapi.Event.RESPONSE = 5

    def tearDown(self):
        """Clean up patches."""
        self.patcher_available.stop()
        self.patcher_blpapi.stop()

    @patch('src.bloomberg_session.time.sleep')
    def test_rate_limit_retry_success(self, mock_sleep):
        """Rate limit error retries with exponential backoff."""
        session = BloombergSession()
        session.start()

        mock_request = MagicMock()
        self.mock_service.createRequest.return_value = mock_request

        # First two attempts fail with rate limit, third succeeds
        call_count = [0]

        def mock_send_request(req):
            call_count[0] += 1
            if call_count[0] < 3:
                raise Exception("Rate limit exceeded")
            # Success on third attempt - do nothing, nextEvent will return success

        self.mock_session_instance.sendRequest.side_effect = mock_send_request

        # Mock successful response
        mock_msg = MagicMock()
        mock_msg.messageType.return_value = "ReferenceDataResponse"
        mock_security_data_array = MagicMock()
        mock_security_data_array.numValues.return_value = 0
        mock_msg.getElement.return_value = mock_security_data_array

        mock_event = MagicMock()
        mock_event.eventType.return_value = self.mock_blpapi.Event.RESPONSE
        mock_event.__iter__.return_value = [mock_msg]
        self.mock_session_instance.nextEvent.return_value = mock_event

        # Send request (should succeed after retries)
        df = session.send_request(
            securities=["9107 JP Equity"],
            fields=["PX_TO_BOOK_RATIO"]
        )

        # Verify retries occurred
        self.assertEqual(call_count[0], 3)
        # Verify backoff delays: 2s, 4s
        self.assertEqual(mock_sleep.call_count, 2)
        mock_sleep.assert_any_call(2)
        mock_sleep.assert_any_call(4)

    @patch('src.bloomberg_session.time.sleep')
    def test_rate_limit_circuit_breaker(self, mock_sleep):
        """Circuit breaker opens after repeated rate limit errors."""
        session = BloombergSession()
        session.start()

        mock_request = MagicMock()
        self.mock_service.createRequest.return_value = mock_request

        # Always fail with rate limit
        self.mock_session_instance.sendRequest.side_effect = Exception("Rate limit exceeded")

        # First request: exhausts retries
        with pytest.raises(BloombergRateLimitError, match="Rate limit exceeded after all retry attempts"):
            session.send_request(
                securities=["9107 JP Equity"],
                fields=["PX_TO_BOOK_RATIO"]
            )

        # Circuit breaker should block further requests
        # Need to trigger more failures to open circuit (5 total)
        for _ in range(4):
            try:
                session.send_request(
                    securities=["9107 JP Equity"],
                    fields=["PX_TO_BOOK_RATIO"]
                )
            except BloombergRateLimitError:
                pass

        # Now circuit should be open
        self.assertTrue(session.circuit_breaker.is_open)

        # Next request should fail immediately
        with pytest.raises(BloombergRateLimitError, match="Circuit breaker is OPEN"):
            session.send_request(
                securities=["9107 JP Equity"],
                fields=["PX_TO_BOOK_RATIO"]
            )


class TestBloombergSessionContextManager(unittest.TestCase):
    """Test context manager functionality."""

    @patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
    @patch('src.bloomberg_session.blpapi')
    def test_context_manager_success(self, mock_blpapi):
        """Context manager starts and closes session automatically."""
        # Mock successful session
        mock_session_instance = MagicMock()
        mock_session_instance.start.return_value = True
        mock_session_instance.openService.return_value = True
        mock_blpapi.Session.return_value = mock_session_instance

        # Use context manager
        with BloombergSession() as session:
            self.assertIsNotNone(session.session)

        # Verify session was closed
        mock_session_instance.stop.assert_called_once()

    @patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
    @patch('src.bloomberg_session.blpapi')
    def test_context_manager_exception_cleanup(self, mock_blpapi):
        """Context manager closes session even on exception."""
        # Mock successful session
        mock_session_instance = MagicMock()
        mock_session_instance.start.return_value = True
        mock_session_instance.openService.return_value = True
        mock_blpapi.Session.return_value = mock_session_instance

        # Use context manager with exception
        try:
            with BloombergSession() as session:
                raise RuntimeError("Test exception")
        except RuntimeError:
            pass

        # Verify session was still closed
        mock_session_instance.stop.assert_called_once()


class TestBloombergSessionUtilities(unittest.TestCase):
    """Test utility methods."""

    @patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
    @patch('src.bloomberg_session.blpapi')
    def test_get_field_errors(self, mock_blpapi):
        """get_field_errors returns tracked field errors."""
        session = BloombergSession()

        # Manually add field errors
        session.field_errors = {
            "9107 JP Equity": ["INVALID_FIELD_1"],
            "8952J JP Equity": ["INVALID_FIELD_2", "INVALID_FIELD_3"]
        }

        errors = session.get_field_errors()

        self.assertEqual(len(errors), 2)
        self.assertIn("INVALID_FIELD_1", errors["9107 JP Equity"])
        self.assertEqual(len(errors["8952J JP Equity"]), 2)

    @patch('src.bloomberg_session.BLPAPI_AVAILABLE', True)
    @patch('src.bloomberg_session.blpapi')
    def test_clear_field_errors(self, mock_blpapi):
        """clear_field_errors resets error tracking."""
        session = BloombergSession()

        session.field_errors = {"9107 JP Equity": ["INVALID_FIELD"]}
        session.clear_field_errors()

        self.assertEqual(len(session.field_errors), 0)


if __name__ == '__main__':
    unittest.main()
