"""
Unit Tests for Data Validator

Test Coverage:
    1. Critical field coverage calculation
    2. Range validation (PBR, ROE, Market Cap, etc.)
    3. Manual review flagging (>30% missing fields)
    4. Quality report generation
    5. Edge cases (empty data, all missing, all valid)

Target Coverage: >85%

Author: Bloomberg Activist Pipeline
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from data_validator import (
    DataValidator,
    DataQualityReport,
    RangeViolation,
)


@pytest.fixture
def temp_logs_dir(tmp_path):
    """Create temporary logs directory."""
    logs_dir = tmp_path / "logs"
    logs_dir.mkdir()
    return logs_dir


@pytest.fixture
def validator(temp_logs_dir):
    """Create DataValidator instance."""
    return DataValidator(logs_dir=temp_logs_dir)


@pytest.fixture
def sample_snapshot_data():
    """Create sample snapshot data with various quality levels."""
    data = {
        "bloomberg_ticker": ["8001 JP Equity", "8002 JP Equity", "8003 JP Equity", "8004 JP Equity"],
        "company_name_english": ["Company A", "Company B", "Company C", "Company D"],
        "PX_TO_BOOK_RATIO": [1.5, 2.0, np.nan, 0.05],  # Last one is out of range
        "RETURN_COM_EQY": [10.5, -5.2, 25.0, 60.0],  # Last one is out of range
        "CUR_MKT_CAP": [1000000, 2000000, 500000, -100],  # Last one is invalid
        "NET_DEBT": [100000, -50000, np.nan, 200000],
        "TRAIL_12M_SALES": [500000, 600000, np.nan, 700000],
        "net_cash": [-100000, 50000, np.nan, -200000],
        "net_cash_to_market_cap": [-0.1, 0.025, np.nan, 1.5],  # Last one is out of range
        "snapshot_date": [date(2021, 3, 31)] * 4,
    }
    return pd.DataFrame(data)


@pytest.fixture
def high_quality_data():
    """Create high-quality data with all fields populated."""
    data = {
        "bloomberg_ticker": ["8001 JP Equity", "8002 JP Equity"],
        "PX_TO_BOOK_RATIO": [1.5, 2.0],
        "RETURN_COM_EQY": [10.5, 12.0],
        "CUR_MKT_CAP": [1000000, 2000000],
        "NET_DEBT": [100000, 200000],
        "TRAIL_12M_SALES": [500000, 600000],
        "net_cash": [-100000, -200000],
        "net_cash_to_market_cap": [-0.1, -0.1],
        "snapshot_date": [date(2021, 3, 31), date(2021, 3, 31)],
        "data_quality_score": [1.0, 1.0],
    }
    return pd.DataFrame(data)


@pytest.fixture
def poor_quality_data():
    """Create poor-quality data with many missing fields."""
    data = {
        "bloomberg_ticker": ["8001 JP Equity", "8002 JP Equity"],
        "PX_TO_BOOK_RATIO": [np.nan, np.nan],
        "RETURN_COM_EQY": [np.nan, 10.0],
        "CUR_MKT_CAP": [np.nan, 1000000],
        "NET_DEBT": [np.nan, np.nan],
        "TRAIL_12M_SALES": [np.nan, np.nan],
    }
    return pd.DataFrame(data)


class TestDataValidator:
    """Test suite for DataValidator class."""

    def test_initialization(self, validator, temp_logs_dir):
        """Test DataValidator initialization."""
        assert validator.logs_dir == temp_logs_dir
        assert len(validator.critical_fields) == 5
        assert "PX_TO_BOOK_RATIO" in validator.critical_fields
        assert validator.logs_dir.exists()

    def test_initialization_default_logs_dir(self):
        """Test initialization with default logs directory."""
        validator = DataValidator()
        assert validator.logs_dir.exists()
        assert validator.logs_dir.name == "logs"

    def test_validate_snapshot_data_basic(self, validator, sample_snapshot_data):
        """Test basic snapshot data validation."""
        report = validator.validate_snapshot_data(sample_snapshot_data)

        assert isinstance(report, DataQualityReport)
        assert report.total_securities == 4
        assert len(report.critical_field_coverage) == 5
        assert len(report.range_violations) > 0  # Should detect violations
        assert report.overall_quality_score > 0.0

    def test_validate_empty_dataframe(self, validator):
        """Test validation of empty DataFrame raises error."""
        empty_df = pd.DataFrame()

        with pytest.raises(ValueError, match="Cannot validate empty DataFrame"):
            validator.validate_snapshot_data(empty_df)

    def test_validate_missing_ticker_column(self, validator):
        """Test validation fails if bloomberg_ticker column missing."""
        df = pd.DataFrame({"company_name": ["Test"]})

        with pytest.raises(ValueError, match="must contain 'bloomberg_ticker' column"):
            validator.validate_snapshot_data(df)

    def test_calculate_field_coverage(self, validator, sample_snapshot_data):
        """Test critical field coverage calculation."""
        report = validator.validate_snapshot_data(sample_snapshot_data)

        # Check PX_TO_BOOK_RATIO coverage (3 out of 4 populated)
        assert report.critical_field_coverage["PX_TO_BOOK_RATIO"] == 0.75

        # Check RETURN_COM_EQY coverage (4 out of 4 populated)
        assert report.critical_field_coverage["RETURN_COM_EQY"] == 1.0

        # Check TRAIL_12M_SALES coverage (3 out of 4 populated)
        assert report.critical_field_coverage["TRAIL_12M_SALES"] == 0.75

    def test_detect_range_violations(self, validator, sample_snapshot_data):
        """Test range violation detection."""
        report = validator.validate_snapshot_data(sample_snapshot_data)

        # Should detect violations:
        # - PX_TO_BOOK_RATIO: 0.05 < 0.1
        # - RETURN_COM_EQY: 60.0 > 50.0
        # - CUR_MKT_CAP: -100 < 0
        # - net_cash_to_market_cap: 1.5 > 1.0

        assert len(report.range_violations) >= 4

        # Check specific violations
        pbr_violations = [v for v in report.range_violations if v.field == "PX_TO_BOOK_RATIO"]
        assert len(pbr_violations) == 1
        assert pbr_violations[0].value == 0.05
        assert pbr_violations[0].ticker == "8004 JP Equity"

        roe_violations = [v for v in report.range_violations if v.field == "RETURN_COM_EQY"]
        assert len(roe_violations) == 1
        assert roe_violations[0].value == 60.0

    def test_flag_manual_review_securities(self, validator, sample_snapshot_data):
        """Test manual review flagging for securities with >30% missing fields."""
        report = validator.validate_snapshot_data(sample_snapshot_data)

        # 8003 JP Equity has missing PX_TO_BOOK_RATIO, NET_DEBT, TRAIL_12M_SALES
        # That's 3 out of 5 = 60% missing (>30% threshold)
        assert "8003 JP Equity" in report.recommended_manual_review

    def test_manual_review_threshold(self, validator):
        """Test manual review with custom threshold."""
        # Create data where 2 out of 5 fields missing (40% missing)
        data = {
            "bloomberg_ticker": ["8001 JP Equity"],
            "PX_TO_BOOK_RATIO": [np.nan],
            "RETURN_COM_EQY": [np.nan],
            "CUR_MKT_CAP": [1000000],
            "NET_DEBT": [100000],
            "TRAIL_12M_SALES": [500000],
        }
        df = pd.DataFrame(data)

        # With 30% threshold, should be flagged
        manual_review_30 = validator.flag_manual_review_securities(df, threshold=0.3)
        assert "8001 JP Equity" in manual_review_30

        # With 50% threshold, should NOT be flagged
        manual_review_50 = validator.flag_manual_review_securities(df, threshold=0.5)
        assert "8001 JP Equity" not in manual_review_50

    def test_validate_range_single_value(self, validator):
        """Test validate_range method for single values."""
        # Valid value
        assert validator.validate_range(1.5, "PX_TO_BOOK_RATIO", 0.1, 10.0) is True

        # Out of range (too low)
        assert validator.validate_range(0.05, "PX_TO_BOOK_RATIO", 0.1, 10.0) is False

        # Out of range (too high)
        assert validator.validate_range(15.0, "PX_TO_BOOK_RATIO", 0.1, 10.0) is False

        # NaN value (should return True - handled separately)
        assert validator.validate_range(np.nan, "PX_TO_BOOK_RATIO", 0.1, 10.0) is True

    def test_overall_quality_score_high(self, validator, high_quality_data):
        """Test quality score for high-quality data."""
        report = validator.validate_snapshot_data(high_quality_data)

        # High-quality data should have >90% score
        assert report.overall_quality_score >= 0.9

    def test_overall_quality_score_poor(self, validator, poor_quality_data):
        """Test quality score for poor-quality data."""
        report = validator.validate_snapshot_data(poor_quality_data)

        # Poor-quality data should have <50% score
        assert report.overall_quality_score < 0.5

    def test_generate_quality_report(self, validator, sample_snapshot_data):
        """Test generate_quality_report method (alias)."""
        report = validator.generate_quality_report(sample_snapshot_data)

        assert isinstance(report, DataQualityReport)
        assert report.total_securities == 4

    def test_validate_ownership_data(self, validator):
        """Test ownership data validation."""
        ownership_data = {
            "bloomberg_ticker": ["8001 JP Equity"] * 3,
            "holder_name": ["Holder A", "Holder B", "Holder C"],
            "pct_held": [10.5, 5.2, 120.0],  # Last one out of range
            "position_date": [date(2021, 3, 31)] * 3,
        }
        df = pd.DataFrame(ownership_data)

        report = validator.validate_ownership_data(df)

        assert report.total_securities == 1
        assert len(report.range_violations) == 1  # 120% is invalid
        assert report.range_violations[0].field == "pct_held"
        assert report.range_violations[0].value == 120.0

    def test_validate_ownership_data_empty(self, validator):
        """Test ownership validation with empty DataFrame."""
        empty_df = pd.DataFrame()

        report = validator.validate_ownership_data(empty_df)

        assert report.total_securities == 0
        assert report.overall_quality_score == 0.0
        assert len(report.notes) > 0

    def test_save_report(self, validator, sample_snapshot_data, temp_logs_dir):
        """Test saving quality report to JSON."""
        report = validator.validate_snapshot_data(sample_snapshot_data)

        output_file = "test_quality_report.json"
        validator.save_report(report, filename=output_file)

        output_path = temp_logs_dir / output_file
        assert output_path.exists()

        # Read back and verify
        import json

        with open(output_path, "r") as f:
            data = json.load(f)

        assert data["total_securities"] == 4
        assert "critical_field_coverage" in data
        assert "range_violations" in data

    def test_range_violation_to_dict(self):
        """Test RangeViolation to_dict method."""
        violation = RangeViolation(
            ticker="8001 JP Equity",
            field="PX_TO_BOOK_RATIO",
            value=0.05,
            min_expected=0.1,
            max_expected=10.0,
            severity="warning",
        )

        result = violation.to_dict()

        assert result["ticker"] == "8001 JP Equity"
        assert result["field"] == "PX_TO_BOOK_RATIO"
        assert result["value"] == 0.05
        assert result["severity"] == "warning"

    def test_data_quality_report_to_dict(self, validator, sample_snapshot_data):
        """Test DataQualityReport to_dict method."""
        report = validator.validate_snapshot_data(sample_snapshot_data)
        result = report.to_dict()

        assert "total_securities" in result
        assert "critical_field_coverage" in result
        assert "range_violations" in result
        assert "overall_quality_score" in result
        assert "extraction_timestamp" in result

    def test_data_quality_report_summary(self, validator, sample_snapshot_data):
        """Test DataQualityReport summary method."""
        report = validator.validate_snapshot_data(sample_snapshot_data)
        summary = report.summary()

        assert "Data Quality Report" in summary
        assert "Total Securities: 4" in summary
        assert "Critical Field Coverage:" in summary
        assert "Overall Quality Score:" in summary

    def test_validation_notes_generation(self, validator, sample_snapshot_data):
        """Test validation notes are generated correctly."""
        report = validator.validate_snapshot_data(sample_snapshot_data)

        assert len(report.notes) > 0

        # Should have note about range violations
        violation_note = any("violation" in note.lower() for note in report.notes)
        assert violation_note

        # Should have note about snapshot dates
        date_note = any("snapshot" in note.lower() for note in report.notes)
        assert date_note

    def test_custom_critical_fields(self, temp_logs_dir):
        """Test validator with custom critical fields."""
        custom_fields = ["EBITDA", "FREE_CASH_FLOW"]
        validator = DataValidator(
            logs_dir=temp_logs_dir, critical_fields=custom_fields
        )

        assert validator.critical_fields == custom_fields

        # Create data with custom fields
        data = {
            "bloomberg_ticker": ["8001 JP Equity"],
            "EBITDA": [1000000],
            "FREE_CASH_FLOW": [np.nan],
        }
        df = pd.DataFrame(data)

        report = validator.validate_snapshot_data(df)

        assert "EBITDA" in report.critical_field_coverage
        assert "FREE_CASH_FLOW" in report.critical_field_coverage
        assert report.critical_field_coverage["EBITDA"] == 1.0
        assert report.critical_field_coverage["FREE_CASH_FLOW"] == 0.0

    def test_custom_range_rules(self, temp_logs_dir):
        """Test validator with custom range rules."""
        custom_rules = {
            "EBITDA": (0.0, 1000000.0, "error"),
        }
        validator = DataValidator(logs_dir=temp_logs_dir, range_rules=custom_rules)

        assert validator.range_rules == custom_rules

        # Create data that violates custom rule
        data = {
            "bloomberg_ticker": ["8001 JP Equity"],
            "EBITDA": [2000000],  # Exceeds max
        }
        df = pd.DataFrame(data)

        report = validator.validate_snapshot_data(df)

        assert len(report.range_violations) == 1
        assert report.range_violations[0].field == "EBITDA"
        assert report.range_violations[0].severity == "error"

    def test_net_cash_field_coverage(self, validator):
        """Test that NET_DEBT critical field can be satisfied by net_cash derived field."""
        data = {
            "bloomberg_ticker": ["8001 JP Equity"],
            "PX_TO_BOOK_RATIO": [1.5],
            "RETURN_COM_EQY": [10.0],
            "CUR_MKT_CAP": [1000000],
            "net_cash": [-100000],  # Derived field instead of NET_DEBT
            "TRAIL_12M_SALES": [500000],
        }
        df = pd.DataFrame(data)

        report = validator.validate_snapshot_data(df)

        # NET_DEBT coverage should be calculated from net_cash
        assert report.critical_field_coverage["NET_DEBT"] == 1.0

    def test_multiple_range_violations_same_security(self, validator):
        """Test detection of multiple range violations in same security."""
        data = {
            "bloomberg_ticker": ["8001 JP Equity"],
            "PX_TO_BOOK_RATIO": [0.05],  # Out of range
            "RETURN_COM_EQY": [60.0],  # Out of range
            "CUR_MKT_CAP": [1000000],
            "NET_DEBT": [100000],
            "TRAIL_12M_SALES": [500000],
            "net_cash_to_market_cap": [-1.5],  # Out of range
        }
        df = pd.DataFrame(data)

        report = validator.validate_snapshot_data(df)

        # Should detect 3 violations for same ticker
        violations_8001 = [
            v for v in report.range_violations if v.ticker == "8001 JP Equity"
        ]
        assert len(violations_8001) == 3


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=data_validator", "--cov-report=term-missing"])
