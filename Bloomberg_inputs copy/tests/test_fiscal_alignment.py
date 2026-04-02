"""
Unit Tests for Fiscal Period Alignment Module

Tests cover:
1. March 31 FYE alignment (most common in Japan)
2. Non-standard FYEs (December, September, etc.)
3. 60-day buffer edge case (critical for point-in-time safety)
4. Leap year handling (February 29 FYE)
5. Year boundary transitions
6. FUND_PER override construction
7. Fiscal year range computation
8. Integration tests with all combinations

Test Coverage Target: 100%
Point-in-Time Safety: All tests verify no lookahead bias
"""

import pytest
from datetime import date
import sys
from pathlib import Path

# Add src directory to path for imports
src_path = Path(__file__).parent.parent / "src"
sys.path.insert(0, str(src_path))

from fiscal_period_aligner import (
    compute_snapshot_date,
    construct_fund_per_override,
    get_fiscal_year_range,
    validate_fye_month,
    compute_campaign_fiscal_alignment,
)


class TestComputeSnapshotDate:
    """Test snapshot date computation (core fiscal alignment logic)."""

    def test_campaign_after_fye_march(self):
        """Test campaign starting well after March FYE (typical case)."""
        # Campaign starts June 14, 2021; March 31 FYE
        # → Should use March 31, 2021 (most recent completed FY)
        snapshot = compute_snapshot_date(date(2021, 6, 14), 3)
        assert snapshot == date(2021, 3, 31)

    def test_campaign_within_60day_buffer_march(self):
        """Test campaign within 60 days of March FYE (critical edge case)."""
        # Campaign starts April 6, 2021; March 31 FYE (6 days after FYE)
        # → Should use prior year March 31, 2020 (assume financials not filed yet)
        snapshot = compute_snapshot_date(date(2021, 4, 6), 3)
        assert snapshot == date(2020, 3, 31)

        # Campaign starts May 15, 2021; March 31 FYE (45 days after FYE)
        # → Should use prior year (still within 60-day buffer)
        snapshot = compute_snapshot_date(date(2021, 5, 15), 3)
        assert snapshot == date(2020, 3, 31)

        # Campaign starts May 30, 2021; March 31 FYE (60 days exactly)
        # → Should use prior year (at buffer boundary)
        snapshot = compute_snapshot_date(date(2021, 5, 30), 3)
        assert snapshot == date(2020, 3, 31)

    def test_campaign_after_60day_buffer_march(self):
        """Test campaign after 60-day buffer expires."""
        # Campaign starts June 1, 2021; March 31 FYE (62 days after FYE)
        # → Should use current year March 31, 2021 (buffer expired)
        snapshot = compute_snapshot_date(date(2021, 6, 1), 3)
        assert snapshot == date(2021, 3, 31)

    def test_campaign_before_fye_march(self):
        """Test campaign before FYE in same calendar year."""
        # Campaign starts Feb 1, 2021; March 31 FYE (FYE hasn't occurred yet)
        # → Should use prior year March 31, 2020
        snapshot = compute_snapshot_date(date(2021, 2, 1), 3)
        assert snapshot == date(2020, 3, 31)

        # Campaign starts March 15, 2021; March 31 FYE (16 days before FYE)
        # → Should use prior year (within 60-day buffer)
        snapshot = compute_snapshot_date(date(2021, 3, 15), 3)
        assert snapshot == date(2020, 3, 31)

    def test_december_fye(self):
        """Test December 31 FYE alignment."""
        # Campaign starts June 1, 2021; December 31 FYE
        # → Should use December 31, 2020 (most recent completed FY)
        snapshot = compute_snapshot_date(date(2021, 6, 1), 12)
        assert snapshot == date(2020, 12, 31)

        # Campaign starts January 15, 2021; December 31 FYE (15 days after FYE)
        # → Should use prior year December 31, 2019 (within 60-day buffer)
        snapshot = compute_snapshot_date(date(2021, 1, 15), 12)
        assert snapshot == date(2019, 12, 31)

        # Campaign starts March 15, 2021; December 31 FYE (74 days after FYE)
        # → Should use current year December 31, 2020 (buffer expired)
        snapshot = compute_snapshot_date(date(2021, 3, 15), 12)
        assert snapshot == date(2020, 12, 31)

    def test_september_fye(self):
        """Test September 30 FYE alignment."""
        # Campaign starts November 1, 2021; September 30 FYE (32 days after)
        # → Should use prior year September 30, 2020 (within 60-day buffer)
        snapshot = compute_snapshot_date(date(2021, 11, 1), 9)
        assert snapshot == date(2020, 9, 30)

        # Campaign starts December 15, 2021; September 30 FYE (76 days after)
        # → Should use current year September 30, 2021 (buffer expired)
        snapshot = compute_snapshot_date(date(2021, 12, 15), 9)
        assert snapshot == date(2021, 9, 30)

    def test_february_fye_leap_year(self):
        """Test February 29 FYE in leap year."""
        # Campaign starts June 1, 2020; February 29 FYE (leap year)
        # → Should use February 29, 2020
        snapshot = compute_snapshot_date(date(2020, 6, 1), 2)
        assert snapshot == date(2020, 2, 29)

    def test_february_fye_non_leap_year(self):
        """Test February FYE in non-leap year (Feb 28)."""
        # Campaign starts June 1, 2021; February FYE (non-leap year)
        # → Should use February 28, 2021
        snapshot = compute_snapshot_date(date(2021, 6, 1), 2)
        assert snapshot == date(2021, 2, 28)

        # Campaign starts June 1, 2019; February FYE (non-leap year)
        # → Should use February 28, 2019
        snapshot = compute_snapshot_date(date(2019, 6, 1), 2)
        assert snapshot == date(2019, 2, 28)

    def test_all_month_fyes(self):
        """Test snapshot date computation for all 12 months."""
        campaign_date = date(2021, 7, 1)  # Mid-year campaign start

        expected_snapshots = {
            1: date(2021, 1, 31),   # January (61 days after FYE → use current year)
            2: date(2021, 2, 28),   # February (61 days after FYE → use current year)
            3: date(2021, 3, 31),   # March (62 days after FYE → use current year)
            4: date(2021, 4, 30),   # April (61 days after FYE → use current year)
            5: date(2020, 5, 31),   # May (31 days after FYE → within buffer, use prior year)
            6: date(2020, 6, 30),   # June (1 day after FYE → within buffer, use prior year)
            7: date(2020, 7, 31),   # July (FYE not yet occurred)
            8: date(2020, 8, 31),   # August (FYE not yet occurred)
            9: date(2020, 9, 30),   # September (FYE not yet occurred)
            10: date(2020, 10, 31), # October (FYE not yet occurred)
            11: date(2020, 11, 30), # November (FYE not yet occurred)
            12: date(2020, 12, 31), # December (FYE not yet occurred)
        }

        for fye_month, expected_snapshot in expected_snapshots.items():
            actual = compute_snapshot_date(campaign_date, fye_month)
            assert actual == expected_snapshot, (
                f"Failed for FYE month {fye_month}: "
                f"expected {expected_snapshot}, got {actual}"
            )


class TestComputeSnapshotDateValidation:
    """Test input validation for compute_snapshot_date."""

    def test_invalid_fye_month_zero(self):
        """Test that FYE month 0 raises ValueError."""
        with pytest.raises(ValueError, match="must be between 1.*and 12"):
            compute_snapshot_date(date(2021, 6, 1), 0)

    def test_invalid_fye_month_13(self):
        """Test that FYE month 13 raises ValueError."""
        with pytest.raises(ValueError, match="must be between 1.*and 12"):
            compute_snapshot_date(date(2021, 6, 1), 13)

    def test_invalid_fye_month_negative(self):
        """Test that negative FYE month raises ValueError."""
        with pytest.raises(ValueError, match="must be between 1.*and 12"):
            compute_snapshot_date(date(2021, 6, 1), -1)

    def test_invalid_campaign_date_type(self):
        """Test that non-date campaign_start_date raises TypeError."""
        with pytest.raises(TypeError, match="must be a datetime.date object"):
            compute_snapshot_date("2021-06-01", 3)

        with pytest.raises(TypeError, match="must be a datetime.date object"):
            compute_snapshot_date(20210601, 3)

        with pytest.raises(TypeError, match="must be a datetime.date object"):
            compute_snapshot_date(None, 3)

    def test_invalid_fye_month_type(self):
        """Test that non-integer fye_month raises TypeError."""
        with pytest.raises(TypeError, match="must be an integer"):
            compute_snapshot_date(date(2021, 6, 1), "3")

        with pytest.raises(TypeError, match="must be an integer"):
            compute_snapshot_date(date(2021, 6, 1), 3.0)


class TestConstructFundPerOverride:
    """Test FUND_PER override string construction."""

    def test_march_fye_2021(self):
        """Test FUND_PER construction for March 31, 2021."""
        fund_per = construct_fund_per_override(date(2021, 3, 31))
        assert fund_per == "FY2021"

    def test_december_fye_2020(self):
        """Test FUND_PER construction for December 31, 2020."""
        fund_per = construct_fund_per_override(date(2020, 12, 31))
        assert fund_per == "FY2020"

    def test_february_fye_2022(self):
        """Test FUND_PER construction for February 28, 2022."""
        fund_per = construct_fund_per_override(date(2022, 2, 28))
        assert fund_per == "FY2022"

    def test_various_years(self):
        """Test FUND_PER construction for various years."""
        test_cases = [
            (date(2015, 3, 31), "FY2015"),
            (date(2018, 12, 31), "FY2018"),
            (date(2020, 9, 30), "FY2020"),
            (date(2023, 6, 30), "FY2023"),
            (date(2026, 3, 31), "FY2026"),
        ]

        for snapshot_date, expected_fund_per in test_cases:
            actual = construct_fund_per_override(snapshot_date)
            assert actual == expected_fund_per

    def test_invalid_snapshot_date_type(self):
        """Test that non-date snapshot_date raises TypeError."""
        with pytest.raises(TypeError, match="must be a datetime.date object"):
            construct_fund_per_override("2021-03-31")

        with pytest.raises(TypeError, match="must be a datetime.date object"):
            construct_fund_per_override(20210331)

    def test_unreasonable_past_date(self):
        """Test that very old dates raise ValueError."""
        with pytest.raises(ValueError, match="outside reasonable range"):
            construct_fund_per_override(date(1970, 3, 31))

    def test_unreasonable_future_date(self):
        """Test that far future dates raise ValueError."""
        with pytest.raises(ValueError, match="outside reasonable range"):
            construct_fund_per_override(date(2050, 3, 31))


class TestGetFiscalYearRange:
    """Test fiscal year range computation."""

    def test_march_fye_range(self):
        """Test fiscal year range for March 31 FYE."""
        start, end = get_fiscal_year_range(date(2021, 3, 31))
        assert start == date(2020, 4, 1)
        assert end == date(2021, 3, 31)

    def test_december_fye_range(self):
        """Test fiscal year range for December 31 FYE."""
        start, end = get_fiscal_year_range(date(2020, 12, 31))
        assert start == date(2020, 1, 1)
        assert end == date(2020, 12, 31)

    def test_september_fye_range(self):
        """Test fiscal year range for September 30 FYE."""
        start, end = get_fiscal_year_range(date(2021, 9, 30))
        assert start == date(2020, 10, 1)
        assert end == date(2021, 9, 30)

    def test_june_fye_range(self):
        """Test fiscal year range for June 30 FYE."""
        start, end = get_fiscal_year_range(date(2021, 6, 30))
        assert start == date(2020, 7, 1)
        assert end == date(2021, 6, 30)

    def test_february_leap_year_range(self):
        """Test fiscal year range for February 29 FYE (leap year)."""
        start, end = get_fiscal_year_range(date(2020, 2, 29))
        assert start == date(2019, 3, 1)
        assert end == date(2020, 2, 29)

    def test_invalid_fye_date_type(self):
        """Test that non-date fye_date raises TypeError."""
        with pytest.raises(TypeError, match="must be a datetime.date object"):
            get_fiscal_year_range("2021-03-31")


class TestValidateFyeMonth:
    """Test FYE month validation helper."""

    def test_valid_months(self):
        """Test that months 1-12 are valid."""
        for month in range(1, 13):
            assert validate_fye_month(month) is True

    def test_invalid_month_zero(self):
        """Test that month 0 is invalid."""
        assert validate_fye_month(0) is False

    def test_invalid_month_13(self):
        """Test that month 13 is invalid."""
        assert validate_fye_month(13) is False

    def test_invalid_negative_month(self):
        """Test that negative months are invalid."""
        assert validate_fye_month(-1) is False
        assert validate_fye_month(-12) is False

    def test_invalid_non_integer(self):
        """Test that non-integer values are invalid."""
        assert validate_fye_month("3") is False
        assert validate_fye_month(3.0) is False
        assert validate_fye_month(None) is False


class TestCampaignFiscalAlignment:
    """Test comprehensive campaign fiscal alignment (integration)."""

    def test_kawasaki_kisen_alignment(self):
        """Test alignment for Kawasaki Kisen (9107.T) campaign."""
        # First filing: 2021-06-14; March 31 FYE
        # Expected: FY2021 (March 31, 2021), FY range: 2020-04-01 to 2021-03-31
        snapshot, fund_per, (fy_start, fy_end) = compute_campaign_fiscal_alignment(
            date(2021, 6, 14), 3
        )

        assert snapshot == date(2021, 3, 31)
        assert fund_per == "FY2021"
        assert fy_start == date(2020, 4, 1)
        assert fy_end == date(2021, 3, 31)

    def test_lifenet_insurance_alignment(self):
        """Test alignment for Lifenet Insurance (7157.T) campaign."""
        # First filing: 2021-04-06; March 31 FYE
        # 6 days after FYE → within 60-day buffer → use FY2020
        snapshot, fund_per, (fy_start, fy_end) = compute_campaign_fiscal_alignment(
            date(2021, 4, 6), 3
        )

        assert snapshot == date(2020, 3, 31)
        assert fund_per == "FY2020"
        assert fy_start == date(2019, 4, 1)
        assert fy_end == date(2020, 3, 31)

    def test_december_fye_integration(self):
        """Test full alignment for December FYE company."""
        # Campaign: 2021-06-01; December 31 FYE
        snapshot, fund_per, (fy_start, fy_end) = compute_campaign_fiscal_alignment(
            date(2021, 6, 1), 12
        )

        assert snapshot == date(2020, 12, 31)
        assert fund_per == "FY2020"
        assert fy_start == date(2020, 1, 1)
        assert fy_end == date(2020, 12, 31)

    def test_multiple_campaigns_same_company(self):
        """Test that different campaign dates yield different snapshots."""
        # Same company (March FYE), but campaigns in different years
        snapshot_2021, fund_per_2021, _ = compute_campaign_fiscal_alignment(
            date(2021, 6, 14), 3
        )
        snapshot_2022, fund_per_2022, _ = compute_campaign_fiscal_alignment(
            date(2022, 6, 14), 3
        )
        snapshot_2023, fund_per_2023, _ = compute_campaign_fiscal_alignment(
            date(2023, 6, 14), 3
        )

        assert snapshot_2021 == date(2021, 3, 31)
        assert snapshot_2022 == date(2022, 3, 31)
        assert snapshot_2023 == date(2023, 3, 31)

        assert fund_per_2021 == "FY2021"
        assert fund_per_2022 == "FY2022"
        assert fund_per_2023 == "FY2023"


class TestPointInTimeSafety:
    """Test critical point-in-time safety properties."""

    def test_no_lookahead_within_buffer(self):
        """Verify 60-day buffer prevents lookahead bias."""
        # Campaign on April 1 (1 day after March 31 FYE)
        # Should NOT use March 31 of that year (financials not filed)
        snapshot = compute_snapshot_date(date(2021, 4, 1), 3)
        assert snapshot == date(2020, 3, 31), (
            "LOOKAHEAD BIAS: Used current year FYE within 60-day buffer"
        )

        # Campaign on May 30 (60 days after March 31 FYE, boundary case)
        snapshot = compute_snapshot_date(date(2021, 5, 30), 3)
        assert snapshot == date(2020, 3, 31), (
            "LOOKAHEAD BIAS: Used current year FYE at 60-day boundary"
        )

    def test_buffer_expires_after_60_days(self):
        """Verify that buffer correctly expires after 60 days."""
        # Campaign on May 31 (61 days after March 31 FYE)
        # Should use current year FYE (buffer expired)
        snapshot = compute_snapshot_date(date(2021, 5, 31), 3)
        assert snapshot == date(2021, 3, 31), (
            "Buffer should expire after 60 days"
        )

    def test_only_past_data_used(self):
        """Verify snapshot is always before or equal to campaign start."""
        test_cases = [
            (date(2021, 6, 14), 3),   # After FYE
            (date(2021, 4, 6), 3),    # Within buffer
            (date(2021, 1, 15), 12),  # Different FYE
            (date(2022, 11, 1), 9),   # September FYE
        ]

        for campaign_date, fye_month in test_cases:
            snapshot = compute_snapshot_date(campaign_date, fye_month)
            assert snapshot < campaign_date, (
                f"TEMPORAL VIOLATION: Snapshot {snapshot} is not before "
                f"campaign start {campaign_date}"
            )

    def test_consistent_snapshot_for_same_inputs(self):
        """Verify deterministic behavior (no time-dependent logic)."""
        # Same inputs should always yield same snapshot
        campaign_date = date(2021, 6, 14)
        fye_month = 3

        snapshot1 = compute_snapshot_date(campaign_date, fye_month)
        snapshot2 = compute_snapshot_date(campaign_date, fye_month)
        snapshot3 = compute_snapshot_date(campaign_date, fye_month)

        assert snapshot1 == snapshot2 == snapshot3, (
            "Non-deterministic snapshot computation"
        )


class TestEdgeCases:
    """Test edge cases and boundary conditions."""

    def test_year_boundary_december_fye(self):
        """Test December FYE across year boundary."""
        # Campaign in January, just after December FYE
        snapshot = compute_snapshot_date(date(2021, 1, 5), 12)
        # 5 days after Dec 31 → within buffer → use prior year
        assert snapshot == date(2019, 12, 31)

    def test_year_boundary_january_fye(self):
        """Test January FYE transition."""
        # Campaign in February, after January FYE
        snapshot = compute_snapshot_date(date(2021, 2, 15), 1)
        # 15 days after Jan 31 → within buffer → use prior year
        assert snapshot == date(2020, 1, 31)

    def test_campaign_on_fye_day(self):
        """Test campaign starting exactly on FYE day."""
        # Campaign on March 31 (FYE day itself)
        # Should use prior year (financials for that day not available)
        snapshot = compute_snapshot_date(date(2021, 3, 31), 3)
        assert snapshot == date(2020, 3, 31)

    def test_very_early_campaign(self):
        """Test campaign very early in calendar year."""
        # Campaign on January 1, various FYEs
        snapshot_march = compute_snapshot_date(date(2021, 1, 1), 3)
        snapshot_dec = compute_snapshot_date(date(2021, 1, 1), 12)

        assert snapshot_march == date(2020, 3, 31)
        assert snapshot_dec == date(2019, 12, 31)  # Within buffer

    def test_very_late_campaign(self):
        """Test campaign very late in calendar year."""
        # Campaign on December 31, various FYEs
        snapshot_march = compute_snapshot_date(date(2021, 12, 31), 3)
        snapshot_dec = compute_snapshot_date(date(2021, 12, 31), 12)

        assert snapshot_march == date(2021, 3, 31)
        assert snapshot_dec == date(2020, 12, 31)  # Within buffer


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
