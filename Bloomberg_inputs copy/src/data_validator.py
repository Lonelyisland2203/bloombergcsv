"""
Data Validator for Bloomberg Activist Data Pipeline

This module validates data quality, detects range violations, and flags
securities requiring manual review before final Excel export.

Core Responsibilities:
    1. Audit field availability across all securities
    2. Validate critical fields are within acceptable ranges
    3. Flag securities with >30% missing critical fields
    4. Generate comprehensive data quality reports

Validation Rules (Japanese Equities):
    - PBR (Price-to-Book Ratio): 0.1 to 10.0
    - ROE (Return on Equity): -50% to +50%
    - Market Cap: Must be > 0
    - Net Cash / Market Cap: -1.0 to +1.0
    - Leverage Ratio: 0 to 10.0

Critical Fields (must be present for high-quality analysis):
    - PX_TO_BOOK_RATIO (PBR)
    - RETURN_COM_EQY (ROE)
    - CUR_MKT_CAP (Market Cap)
    - NET_DEBT or derived net_cash
    - TRAIL_12M_SALES (Revenue)

Quality Scoring:
    - 100%: All critical fields present
    - 70%+: Acceptable quality
    - 30-70%: Marginal quality (flag for review)
    - <30%: Poor quality (manual review required)

Author: Bloomberg Activist Pipeline
"""

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class RangeViolation:
    """
    Represents a field value that falls outside acceptable bounds.

    Attributes:
        ticker: Bloomberg ticker
        field: Field name
        value: Actual value
        min_expected: Minimum acceptable value
        max_expected: Maximum acceptable value
        severity: 'warning' or 'error'
    """

    ticker: str
    field: str
    value: float
    min_expected: float
    max_expected: float
    severity: str = "warning"

    def to_dict(self) -> Dict:
        """Convert to dictionary for reporting."""
        return {
            "ticker": self.ticker,
            "field": self.field,
            "value": self.value,
            "min_expected": self.min_expected,
            "max_expected": self.max_expected,
            "severity": self.severity,
        }


@dataclass
class DataQualityReport:
    """
    Comprehensive data quality report for all extracted data.

    Attributes:
        total_securities: Number of securities analyzed
        critical_field_coverage: Field name -> % populated (0.0 to 1.0)
        range_violations: List of RangeViolation objects
        recommended_manual_review: List of tickers requiring review
        overall_quality_score: Weighted average quality (0.0 to 1.0)
        extraction_timestamp: When validation was performed
        notes: Additional observations or warnings
    """

    total_securities: int
    critical_field_coverage: Dict[str, float]
    range_violations: List[RangeViolation]
    recommended_manual_review: List[str]
    overall_quality_score: float
    extraction_timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    notes: List[str] = field(default_factory=list)

    def to_dict(self) -> Dict:
        """Convert to dictionary for JSON export."""
        return {
            "total_securities": self.total_securities,
            "critical_field_coverage": self.critical_field_coverage,
            "range_violations": [v.to_dict() for v in self.range_violations],
            "recommended_manual_review": self.recommended_manual_review,
            "overall_quality_score": self.overall_quality_score,
            "extraction_timestamp": self.extraction_timestamp,
            "notes": self.notes,
        }

    def summary(self) -> str:
        """Generate human-readable summary."""
        lines = [
            f"Data Quality Report - {self.extraction_timestamp}",
            f"Total Securities: {self.total_securities}",
            f"Overall Quality Score: {self.overall_quality_score:.1%}",
            f"Range Violations: {len(self.range_violations)}",
            f"Manual Review Required: {len(self.recommended_manual_review)}",
            "",
            "Critical Field Coverage:",
        ]

        for field_name, coverage in sorted(
            self.critical_field_coverage.items(), key=lambda x: x[1]
        ):
            lines.append(f"  {field_name}: {coverage:.1%}")

        if self.recommended_manual_review:
            lines.append("")
            lines.append("Securities Requiring Manual Review:")
            for ticker in self.recommended_manual_review:
                lines.append(f"  - {ticker}")

        if self.notes:
            lines.append("")
            lines.append("Notes:")
            for note in self.notes:
                lines.append(f"  - {note}")

        return "\n".join(lines)


class DataValidator:
    """
    Validates data quality and flags issues before Excel export.

    This validator ensures data integrity across all extracted datasets,
    applying domain-specific validation rules for Japanese equities.

    Attributes:
        logs_dir: Directory for validation reports
        critical_fields: List of field names that must be present
        range_rules: Dict mapping field names to (min, max) tuples
    """

    # Critical fields (must be present for quality analysis)
    DEFAULT_CRITICAL_FIELDS = [
        "PX_TO_BOOK_RATIO",  # Valuation
        "RETURN_COM_EQY",  # Profitability
        "CUR_MKT_CAP",  # Market data
        "NET_DEBT",  # Balance sheet (or net_cash derived field)
        "TRAIL_12M_SALES",  # Revenue
    ]

    # Range validation rules: field -> (min, max, severity)
    DEFAULT_RANGE_RULES = {
        "PX_TO_BOOK_RATIO": (0.1, 10.0, "warning"),
        "RETURN_COM_EQY": (-50.0, 50.0, "warning"),
        "CUR_MKT_CAP": (0.0, float("inf"), "error"),
        "net_cash_to_market_cap": (-1.0, 1.0, "warning"),
        "BS_LEVERAGE": (0.0, 10.0, "warning"),
    }

    def __init__(
        self,
        logs_dir: Optional[Path] = None,
        critical_fields: Optional[List[str]] = None,
        range_rules: Optional[Dict[str, Tuple[float, float, str]]] = None,
    ):
        """
        Initialize data validator.

        Args:
            logs_dir: Directory for validation reports (default: ../logs)
            critical_fields: List of critical field names (uses defaults if None)
            range_rules: Custom range validation rules (uses defaults if None)
        """
        # Set up logs directory
        if logs_dir is None:
            src_dir = Path(__file__).parent
            logs_dir = src_dir.parent / "logs"

        self.logs_dir = Path(logs_dir)
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Set critical fields and range rules
        self.critical_fields = critical_fields or self.DEFAULT_CRITICAL_FIELDS
        self.range_rules = range_rules or self.DEFAULT_RANGE_RULES

        logger.info(
            f"DataValidator initialized with {len(self.critical_fields)} critical fields"
        )

    def validate_snapshot_data(self, df: pd.DataFrame) -> DataQualityReport:
        """
        Validate financial snapshot data comprehensively.

        Args:
            df: DataFrame from extract_snapshot.py

        Returns:
            DataQualityReport with validation results

        Raises:
            ValueError: If DataFrame is empty or missing ticker column
        """
        if df.empty:
            raise ValueError("Cannot validate empty DataFrame")

        if "bloomberg_ticker" not in df.columns:
            raise ValueError("DataFrame must contain 'bloomberg_ticker' column")

        logger.info(f"Validating snapshot data for {len(df)} securities")

        # Calculate field coverage
        field_coverage = self._calculate_field_coverage(df)

        # Detect range violations
        range_violations = self._detect_range_violations(df)

        # Flag securities for manual review
        manual_review_tickers = self._flag_manual_review_securities(df)

        # Compute overall quality score
        quality_score = self._compute_overall_quality_score(df, field_coverage)

        # Generate notes
        notes = self._generate_validation_notes(df, field_coverage, range_violations)

        report = DataQualityReport(
            total_securities=len(df),
            critical_field_coverage=field_coverage,
            range_violations=range_violations,
            recommended_manual_review=manual_review_tickers,
            overall_quality_score=quality_score,
            notes=notes,
        )

        logger.info(f"Validation complete. Quality score: {quality_score:.1%}")

        return report

    def validate_ownership_data(self, df: pd.DataFrame) -> DataQualityReport:
        """
        Validate ownership data.

        Args:
            df: DataFrame from extract_ownership.py

        Returns:
            DataQualityReport focused on ownership data quality
        """
        if df.empty:
            logger.warning("Ownership DataFrame is empty")
            return DataQualityReport(
                total_securities=0,
                critical_field_coverage={},
                range_violations=[],
                recommended_manual_review=[],
                overall_quality_score=0.0,
                notes=["Ownership data is empty"],
            )

        logger.info(f"Validating ownership data for {len(df)} holders")

        # Check critical ownership fields
        ownership_fields = ["holder_name", "pct_held", "position_date"]
        field_coverage = {}

        for field in ownership_fields:
            if field in df.columns:
                coverage = df[field].notna().mean()
                field_coverage[field] = coverage
            else:
                field_coverage[field] = 0.0

        # Validate percentage held is in range 0-100
        range_violations = []
        if "pct_held" in df.columns:
            invalid_pct = df[
                (df["pct_held"] < 0) | (df["pct_held"] > 100)
            ].copy()
            for _, row in invalid_pct.iterrows():
                violation = RangeViolation(
                    ticker=row.get("bloomberg_ticker", "UNKNOWN"),
                    field="pct_held",
                    value=row["pct_held"],
                    min_expected=0.0,
                    max_expected=100.0,
                    severity="error",
                )
                range_violations.append(violation)

        quality_score = sum(field_coverage.values()) / len(field_coverage)

        return DataQualityReport(
            total_securities=len(df["bloomberg_ticker"].unique())
            if "bloomberg_ticker" in df.columns
            else 0,
            critical_field_coverage=field_coverage,
            range_violations=range_violations,
            recommended_manual_review=[],
            overall_quality_score=quality_score,
            notes=[f"Validated {len(df)} ownership records"],
        )

    def validate_range(
        self, value: float, field: str, min_val: float, max_val: float
    ) -> bool:
        """
        Validate a single field value is within acceptable range.

        Args:
            value: Field value to validate
            field: Field name (for logging)
            min_val: Minimum acceptable value
            max_val: Maximum acceptable value

        Returns:
            True if value is within range or is NaN, False otherwise
        """
        if pd.isna(value):
            return True  # Missing values handled separately

        if value < min_val or value > max_val:
            logger.warning(
                f"Range violation: {field}={value} outside [{min_val}, {max_val}]"
            )
            return False

        return True

    def flag_manual_review_securities(
        self, df: pd.DataFrame, threshold: float = 0.3
    ) -> List[str]:
        """
        Identify securities with >threshold missing critical fields.

        Args:
            df: DataFrame with financial data
            threshold: Maximum acceptable missing field rate (default: 0.3)

        Returns:
            List of bloomberg_ticker values requiring manual review
        """
        return self._flag_manual_review_securities(df, threshold)

    def generate_quality_report(self, df: pd.DataFrame) -> DataQualityReport:
        """
        Generate comprehensive data quality report.

        This is an alias for validate_snapshot_data() for backward compatibility.

        Args:
            df: DataFrame with financial data

        Returns:
            DataQualityReport
        """
        return self.validate_snapshot_data(df)

    def save_report(self, report: DataQualityReport, filename: str = "data_quality_report.json"):
        """
        Save quality report to JSON file.

        Args:
            report: DataQualityReport to save
            filename: Output filename (default: data_quality_report.json)
        """
        output_path = self.logs_dir / filename
        import json

        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(report.to_dict(), f, indent=2)

        logger.info(f"Quality report saved to {output_path}")

    # Private helper methods

    def _calculate_field_coverage(self, df: pd.DataFrame) -> Dict[str, float]:
        """Calculate percentage of non-null values for critical fields."""
        coverage = {}

        for field in self.critical_fields:
            if field in df.columns:
                coverage[field] = df[field].notna().mean()
            else:
                # Check for derived fields
                if field == "NET_DEBT" and "net_cash" in df.columns:
                    coverage[field] = df["net_cash"].notna().mean()
                else:
                    coverage[field] = 0.0

        return coverage

    def _detect_range_violations(self, df: pd.DataFrame) -> List[RangeViolation]:
        """Detect values outside acceptable ranges."""
        violations = []

        for field, (min_val, max_val, severity) in self.range_rules.items():
            if field not in df.columns:
                continue

            # Find rows with out-of-range values
            out_of_range = df[
                (df[field].notna())
                & ((df[field] < min_val) | (df[field] > max_val))
            ].copy()

            for _, row in out_of_range.iterrows():
                violation = RangeViolation(
                    ticker=row["bloomberg_ticker"],
                    field=field,
                    value=row[field],
                    min_expected=min_val,
                    max_expected=max_val,
                    severity=severity,
                )
                violations.append(violation)

        return violations

    def _flag_manual_review_securities(
        self, df: pd.DataFrame, threshold: float = 0.3
    ) -> List[str]:
        """Flag securities with excessive missing critical fields."""
        manual_review = []

        for _, row in df.iterrows():
            ticker = row["bloomberg_ticker"]
            missing_count = 0

            for field in self.critical_fields:
                if field in df.columns:
                    if pd.isna(row[field]):
                        missing_count += 1
                elif field == "NET_DEBT" and "net_cash" in df.columns:
                    if pd.isna(row["net_cash"]):
                        missing_count += 1
                else:
                    missing_count += 1

            missing_rate = missing_count / len(self.critical_fields)

            if missing_rate > threshold:
                manual_review.append(ticker)
                logger.warning(
                    f"{ticker}: {missing_rate:.1%} critical fields missing "
                    f"(threshold: {threshold:.1%})"
                )

        return manual_review

    def _compute_overall_quality_score(
        self, df: pd.DataFrame, field_coverage: Dict[str, float]
    ) -> float:
        """
        Compute weighted quality score.

        Score components:
            - 60%: Average critical field coverage
            - 20%: Presence of derived fields
            - 20%: Data recency (if snapshot_date available)
        """
        # Component 1: Critical field coverage (60% weight)
        avg_coverage = sum(field_coverage.values()) / len(field_coverage)
        coverage_score = avg_coverage * 0.6

        # Component 2: Derived fields (20% weight)
        derived_fields = ["net_cash", "net_cash_to_market_cap", "data_quality_score"]
        derived_count = sum(1 for field in derived_fields if field in df.columns)
        derived_score = (derived_count / len(derived_fields)) * 0.2

        # Component 3: Data recency (20% weight)
        # Full points if snapshot_date exists and is recent
        recency_score = 0.2 if "snapshot_date" in df.columns else 0.0

        overall_score = coverage_score + derived_score + recency_score
        return min(1.0, overall_score)  # Cap at 1.0

    def _generate_validation_notes(
        self,
        df: pd.DataFrame,
        field_coverage: Dict[str, float],
        range_violations: List[RangeViolation],
    ) -> List[str]:
        """Generate human-readable validation notes."""
        notes = []

        # Note on low coverage fields
        low_coverage_fields = [
            field for field, coverage in field_coverage.items() if coverage < 0.5
        ]

        if low_coverage_fields:
            notes.append(
                f"{len(low_coverage_fields)} fields have <50% coverage: "
                f"{', '.join(low_coverage_fields)}"
            )

        # Note on range violations by severity
        error_violations = [v for v in range_violations if v.severity == "error"]
        warning_violations = [v for v in range_violations if v.severity == "warning"]

        if error_violations:
            notes.append(
                f"{len(error_violations)} ERROR-level range violations detected"
            )

        if warning_violations:
            notes.append(
                f"{len(warning_violations)} WARNING-level range violations detected"
            )

        # Note on data freshness
        if "snapshot_date" in df.columns:
            dates = pd.to_datetime(df["snapshot_date"])
            date_range = f"{dates.min():%Y-%m-%d} to {dates.max():%Y-%m-%d}"
            notes.append(f"Snapshot dates range: {date_range}")

        return notes
