"""
CSV Input Validation Script

This script validates input CSV files to detect data quality issues before
running the Bloomberg pipeline.

Checks performed:
1. Required columns present
2. No duplicate tickers
3. Valid date formats
4. Valid ticker formats (TSE format: NNNN.T)
5. Valid ownership percentages (0-100%)
6. No missing critical values

Usage:
    python scripts/validate_input_csv.py --input effissimo_summary_by_company_corrected.csv

Author: Bloomberg Activist Pipeline
"""

import argparse
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Tuple

import pandas as pd


class CSVValidator:
    """Validates input CSV files for the Bloomberg pipeline."""

    REQUIRED_COLUMNS = [
        "target_company",
        "target_ticker",
        "total_filings",
        "first_filing",
        "last_filing",
        "max_ownership_pct",
        "min_ownership_pct",
    ]

    def __init__(self, csv_path: Path):
        """
        Initialize validator.

        Args:
            csv_path: Path to CSV file to validate
        """
        self.csv_path = csv_path
        self.df: pd.DataFrame = None
        self.errors: List[str] = []
        self.warnings: List[str] = []

    def validate(self) -> bool:
        """
        Run all validation checks.

        Returns:
            True if validation passes, False otherwise
        """
        print("=" * 80)
        print("CSV Validation Report")
        print("=" * 80)
        print(f"File: {self.csv_path}")
        print(f"Validation Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("=" * 80)

        # Load CSV
        if not self._load_csv():
            return False

        # Run validation checks
        self._check_required_columns()
        self._check_duplicate_tickers()
        self._check_date_formats()
        self._check_ticker_formats()
        self._check_ownership_percentages()
        self._check_filing_counts()
        self._check_date_logic()

        # Print results
        self._print_results()

        return len(self.errors) == 0

    def _load_csv(self) -> bool:
        """Load CSV file."""
        try:
            self.df = pd.read_csv(self.csv_path)
            print(f"\n✓ CSV loaded successfully: {len(self.df)} rows, {len(self.df.columns)} columns")
            return True
        except FileNotFoundError:
            self.errors.append(f"CSV file not found: {self.csv_path}")
            return False
        except Exception as e:
            self.errors.append(f"Error loading CSV: {e}")
            return False

    def _check_required_columns(self) -> None:
        """Check that all required columns are present."""
        missing_cols = [col for col in self.REQUIRED_COLUMNS if col not in self.df.columns]
        if missing_cols:
            self.errors.append(f"Missing required columns: {missing_cols}")
        else:
            print(f"✓ All required columns present: {self.REQUIRED_COLUMNS}")

    def _check_duplicate_tickers(self) -> None:
        """Check for duplicate tickers."""
        duplicate_tickers = self.df[self.df.duplicated(subset=["target_ticker"], keep=False)]

        if not duplicate_tickers.empty:
            duplicates = duplicate_tickers["target_ticker"].value_counts()
            self.errors.append(
                f"Duplicate tickers found: {duplicates.to_dict()}"
            )
            print(f"\n✗ DUPLICATE TICKERS DETECTED:")
            for ticker, count in duplicates.items():
                rows = duplicate_tickers[duplicate_tickers["target_ticker"] == ticker]
                print(f"  Ticker: {ticker} (appears {count} times)")
                for idx, row in rows.iterrows():
                    print(f"    Row {idx + 2}: {row['target_company']}")
        else:
            print(f"✓ No duplicate tickers: {len(self.df)} unique tickers")

    def _check_date_formats(self) -> None:
        """Check that date columns are valid."""
        date_cols = ["first_filing", "last_filing"]

        for col in date_cols:
            if col not in self.df.columns:
                continue

            invalid_dates = []
            for idx, value in enumerate(self.df[col]):
                if pd.isna(value):
                    continue
                try:
                    pd.to_datetime(value)
                except Exception:
                    invalid_dates.append((idx + 2, value))  # +2 for header and 0-index

            if invalid_dates:
                self.errors.append(
                    f"Invalid date format in {col}: {invalid_dates[:5]}"  # Show first 5
                )
            else:
                print(f"✓ Valid date format in {col}")

    def _check_ticker_formats(self) -> None:
        """Check that tickers follow TSE format (NNNN.T)."""
        invalid_tickers = []

        for idx, ticker in enumerate(self.df["target_ticker"]):
            if pd.isna(ticker):
                invalid_tickers.append((idx + 2, ticker, "Missing ticker"))
                continue

            ticker_str = str(ticker)

            # Check format: NNNN.T (4 digits followed by .T)
            if not ticker_str.endswith(".T"):
                invalid_tickers.append((idx + 2, ticker_str, "Missing .T suffix"))
            else:
                ticker_code = ticker_str[:-2]  # Remove .T
                if not ticker_code.isdigit():
                    invalid_tickers.append((idx + 2, ticker_str, "Non-numeric ticker code"))
                elif len(ticker_code) != 4:
                    # Some tickers may be 1-4 digits, so this is a warning not error
                    self.warnings.append(f"Row {idx + 2}: Unusual ticker length: {ticker_str}")

        if invalid_tickers:
            self.errors.append(
                f"Invalid ticker formats: {invalid_tickers[:5]}"  # Show first 5
            )
        else:
            print(f"✓ All tickers follow TSE format (NNNN.T)")

    def _check_ownership_percentages(self) -> None:
        """Check that ownership percentages are valid (0-100%)."""
        pct_cols = ["max_ownership_pct", "min_ownership_pct"]

        for col in pct_cols:
            if col not in self.df.columns:
                continue

            invalid_pcts = []
            for idx, value in enumerate(self.df[col]):
                if pd.isna(value):
                    invalid_pcts.append((idx + 2, value, "Missing value"))
                elif value < 0 or value > 1:
                    # Assuming percentages are stored as decimals (0.10 = 10%)
                    invalid_pcts.append((idx + 2, value, "Out of range (0-1)"))

            if invalid_pcts:
                self.errors.append(
                    f"Invalid ownership percentages in {col}: {invalid_pcts[:5]}"
                )
            else:
                print(f"✓ Valid ownership percentages in {col} (0-100%)")

    def _check_filing_counts(self) -> None:
        """Check that total_filings is positive integer."""
        invalid_counts = []

        for idx, value in enumerate(self.df["total_filings"]):
            if pd.isna(value):
                invalid_counts.append((idx + 2, value, "Missing value"))
            elif not isinstance(value, (int, float)) or value <= 0:
                invalid_counts.append((idx + 2, value, "Must be positive integer"))

        if invalid_counts:
            self.errors.append(
                f"Invalid filing counts: {invalid_counts[:5]}"
            )
        else:
            print(f"✓ All filing counts are positive integers")

    def _check_date_logic(self) -> None:
        """Check that last_filing >= first_filing."""
        # Parse dates
        try:
            self.df["first_filing_dt"] = pd.to_datetime(self.df["first_filing"])
            self.df["last_filing_dt"] = pd.to_datetime(self.df["last_filing"])
        except Exception as e:
            self.errors.append(f"Error parsing dates for logic check: {e}")
            return

        invalid_ranges = []
        for idx, row in self.df.iterrows():
            if pd.notna(row["first_filing_dt"]) and pd.notna(row["last_filing_dt"]):
                if row["last_filing_dt"] < row["first_filing_dt"]:
                    invalid_ranges.append(
                        (
                            idx + 2,
                            row["target_ticker"],
                            row["first_filing"],
                            row["last_filing"],
                        )
                    )

        if invalid_ranges:
            self.errors.append(
                f"Invalid date ranges (last_filing < first_filing): {invalid_ranges}"
            )
        else:
            print(f"✓ All date ranges valid (last_filing >= first_filing)")

    def _print_results(self) -> None:
        """Print validation results."""
        print("\n" + "=" * 80)
        print("Validation Results")
        print("=" * 80)

        if self.warnings:
            print(f"\nWarnings: {len(self.warnings)}")
            for warning in self.warnings:
                print(f"  ⚠ {warning}")

        if self.errors:
            print(f"\nErrors: {len(self.errors)}")
            for error in self.errors:
                print(f"  ✗ {error}")
            print("\n" + "=" * 80)
            print("VALIDATION FAILED ✗")
            print("=" * 80)
        else:
            print(f"\n✓ All validation checks passed!")
            print("=" * 80)
            print("VALIDATION PASSED ✓")
            print("=" * 80)
            print(f"\nThis CSV is ready for Bloomberg pipeline execution.")


def parse_arguments() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        description="Validate input CSV for Bloomberg Activist Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Validate corrected CSV
  python scripts/validate_input_csv.py --input effissimo_summary_by_company_corrected.csv

  # Validate original CSV (will detect duplicate ticker)
  python scripts/validate_input_csv.py --input effissimo_summary_by_company.csv
        """,
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to input CSV file to validate",
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point.

    Returns:
        Exit code (0 = validation passed, 1 = validation failed)
    """
    args = parse_arguments()

    validator = CSVValidator(args.input)
    passed = validator.validate()

    return 0 if passed else 1


if __name__ == "__main__":
    sys.exit(main())
