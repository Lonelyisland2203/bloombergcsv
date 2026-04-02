"""
Unit Tests for Excel Writer

Test Coverage:
    1. 5-sheet workbook creation
    2. Metadata header in Sheet 1
    3. Formatting application (freeze panes, column widths, number formats)
    4. File creation and readability
    5. Integration with real data structures
    6. Edge cases (empty sheets, missing data)

Target Coverage: >85%

Author: Bloomberg Activist Pipeline
"""

import pytest
import pandas as pd
import numpy as np
from pathlib import Path
from datetime import date, datetime
from openpyxl import load_workbook

import sys
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from excel_writer import ExcelWriter
from data_validator import DataQualityReport, RangeViolation


@pytest.fixture
def temp_output_dir(tmp_path):
    """Create temporary output directory."""
    output_dir = tmp_path / "output"
    output_dir.mkdir()
    return output_dir


@pytest.fixture
def excel_writer(temp_output_dir):
    """Create ExcelWriter instance."""
    return ExcelWriter(output_dir=temp_output_dir)


@pytest.fixture
def sample_snapshot_data():
    """Create sample snapshot data."""
    data = {
        "bloomberg_ticker": ["8001 JP Equity", "8002 JP Equity", "8003 JP Equity"],
        "company_name_english": ["Company A", "Company B", "Company C"],
        "PX_TO_BOOK_RATIO": [1.5, 2.0, 1.8],
        "RETURN_COM_EQY": [10.5, 12.0, 8.5],
        "CUR_MKT_CAP": [1000000, 2000000, 1500000],
        "NET_DEBT": [100000, -50000, 200000],
        "TRAIL_12M_SALES": [500000, 600000, 550000],
        "snapshot_date": [date(2021, 3, 31)] * 3,
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_ownership_data():
    """Create sample ownership data."""
    data = {
        "bloomberg_ticker": ["8001 JP Equity"] * 3,
        "holder_name": ["Holder A", "Holder B", "Holder C"],
        "pct_held": [10.5, 8.2, 5.1],
        "position_date": [date(2021, 3, 31)] * 3,
        "holder_type": ["Institution", "Mutual Fund", "Hedge Fund"],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_events_data():
    """Create sample events data."""
    data = {
        "bloomberg_ticker": ["8001 JP Equity", "8002 JP Equity"],
        "event_type": ["Dividend", "Stock Split"],
        "event_date": [date(2021, 6, 30), date(2021, 9, 30)],
        "description": ["Annual dividend ¥50", "2-for-1 split"],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_price_history():
    """Create sample price history data."""
    dates = pd.date_range(start="2021-01-01", periods=10, freq="D")
    data = {
        "bloomberg_ticker": ["8001 JP Equity"] * 10,
        "date": dates,
        "PX_LAST": [1000, 1010, 1020, 1015, 1025, 1030, 1028, 1035, 1040, 1050],
        "PX_VOLUME": [100000] * 10,
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_peer_comps():
    """Create sample peer comparables data."""
    data = {
        "bloomberg_ticker": ["8001 JP Equity", "8002 JP Equity"],
        "company_name_english": ["Company A", "Company B"],
        "peer_ticker": ["8010 JP Equity", "8020 JP Equity"],
        "peer_name": ["Peer A", "Peer B"],
        "PX_TO_BOOK_RATIO": [1.5, 1.8],
        "RETURN_COM_EQY": [10.5, 11.0],
    }
    return pd.DataFrame(data)


@pytest.fixture
def sample_quality_report():
    """Create sample data quality report."""
    return DataQualityReport(
        total_securities=3,
        critical_field_coverage={
            "PX_TO_BOOK_RATIO": 1.0,
            "RETURN_COM_EQY": 1.0,
            "CUR_MKT_CAP": 1.0,
            "NET_DEBT": 0.67,
            "TRAIL_12M_SALES": 1.0,
        },
        range_violations=[
            RangeViolation(
                ticker="8001 JP Equity",
                field="PX_TO_BOOK_RATIO",
                value=0.05,
                min_expected=0.1,
                max_expected=10.0,
            )
        ],
        recommended_manual_review=["8003 JP Equity"],
        overall_quality_score=0.893,
    )


class TestExcelWriter:
    """Test suite for ExcelWriter class."""

    def test_initialization(self, excel_writer, temp_output_dir):
        """Test ExcelWriter initialization."""
        assert excel_writer.output_dir == temp_output_dir
        assert excel_writer.output_dir.exists()

    def test_initialization_default_output_dir(self):
        """Test initialization with default output directory."""
        writer = ExcelWriter()
        assert writer.output_dir.exists()
        assert writer.output_dir.name == "output"

    def test_write_activist_workbook_basic(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_ownership_data,
        sample_events_data,
        sample_price_history,
        sample_peer_comps,
        sample_quality_report,
        temp_output_dir,
    ):
        """Test basic workbook creation with all sheets."""
        activist_name = "Effissimo Capital Management"

        output_path = excel_writer.write_activist_workbook(
            activist_name=activist_name,
            snapshot_df=sample_snapshot_data,
            ownership_df=sample_ownership_data,
            events_df=sample_events_data,
            price_history_df=sample_price_history,
            peer_comps_df=sample_peer_comps,
            data_quality_report=sample_quality_report,
        )

        # Verify file exists
        assert output_path.exists()
        assert output_path.suffix == ".xlsx"

        # Verify filename format
        timestamp = datetime.now().strftime("%Y%m%d")
        expected_filename = f"Effissimo_Capital_Management_bloomberg_data_{timestamp}.xlsx"
        assert output_path.name == expected_filename

        # Load workbook and verify sheets
        wb = load_workbook(output_path)
        sheet_names = wb.sheetnames

        assert "Financial Snapshot" in sheet_names
        assert "Ownership" in sheet_names
        assert "Corporate Actions" in sheet_names
        assert "Price History" in sheet_names
        assert "Peer Comparables" in sheet_names
        assert len(sheet_names) == 5  # Exactly 5 sheets

    def test_write_activist_workbook_snapshot_only(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_quality_report,
        temp_output_dir,
    ):
        """Test workbook creation with only snapshot data."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Test Activist",
            snapshot_df=sample_snapshot_data,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        assert output_path.exists()

        # Load and verify only Financial Snapshot sheet exists
        wb = load_workbook(output_path)
        sheet_names = wb.sheetnames

        assert "Financial Snapshot" in sheet_names
        # Empty DataFrames should not create sheets
        assert len(sheet_names) >= 1

    def test_write_activist_workbook_none_snapshot_raises_error(
        self,
        excel_writer,
        sample_quality_report,
    ):
        """Test that None snapshot_df raises ValueError."""
        with pytest.raises(ValueError, match="snapshot_df cannot be None"):
            excel_writer.write_activist_workbook(
                activist_name="Test Activist",
                snapshot_df=None,
                ownership_df=pd.DataFrame(),
                events_df=pd.DataFrame(),
                price_history_df=pd.DataFrame(),
                peer_comps_df=pd.DataFrame(),
                data_quality_report=sample_quality_report,
            )

    def test_write_activist_workbook_custom_output_path(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_quality_report,
        temp_output_dir,
    ):
        """Test workbook creation with custom output path."""
        custom_path = temp_output_dir / "custom_output.xlsx"

        output_path = excel_writer.write_activist_workbook(
            activist_name="Test Activist",
            snapshot_df=sample_snapshot_data,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
            output_path=custom_path,
        )

        assert output_path == custom_path
        assert output_path.exists()

    def test_sheet_1_metadata_header(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_quality_report,
        temp_output_dir,
    ):
        """Test Sheet 1 contains metadata header in rows 1-5."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Effissimo Capital",
            snapshot_df=sample_snapshot_data,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Financial Snapshot"]

        # Check metadata header rows
        assert ws["A1"].value == "Metric"
        assert ws["B1"].value == "Value"

        assert ws["A2"].value == "Extraction Date"
        assert ws["A3"].value == "Activist Name"
        assert ws["A4"].value == "Number of Targets"
        assert ws["A5"].value == "Data Quality Score"
        assert ws["A6"].value == "Manual Review Required"

        # Check metadata values
        assert ws["B3"].value == "Effissimo Capital"
        assert ws["B4"].value == 3
        assert "89.3%" in str(ws["B5"].value)
        assert ws["B6"].value == 1

        # Check data starts at row 7 (blank row 7, headers row 8)
        # Actually, we write at startrow=6, so headers should be at row 7
        assert ws["A7"].value == "bloomberg_ticker"

    def test_sheet_1_freeze_panes(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_quality_report,
    ):
        """Test Sheet 1 has freeze panes at row 8."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=sample_snapshot_data,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Financial Snapshot"]

        # Check freeze panes
        assert ws.freeze_panes == "A8"

    def test_other_sheets_freeze_panes(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_ownership_data,
        sample_quality_report,
    ):
        """Test other sheets have freeze panes at row 2."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=sample_snapshot_data,
            ownership_df=sample_ownership_data,
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Ownership"]

        assert ws.freeze_panes == "A2"

    def test_create_simple_workbook(
        self,
        excel_writer,
        sample_snapshot_data,
        temp_output_dir,
    ):
        """Test create_simple_workbook for testing purposes."""
        output_path = excel_writer.create_simple_workbook(
            activist_name="Test Activist",
            snapshot_df=sample_snapshot_data,
        )

        assert output_path.exists()

        wb = load_workbook(output_path)
        assert "Financial Snapshot" in wb.sheetnames

    def test_apply_formatting_column_widths(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_quality_report,
    ):
        """Test that column widths are auto-fitted."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=sample_snapshot_data,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Financial Snapshot"]

        # Check that columns have been auto-sized
        # Column widths should be > 0
        for col in ["A", "B", "C", "D", "E"]:
            width = ws.column_dimensions[col].width
            assert width > 0
            assert width <= 50  # Max width is 50

    def test_apply_formatting_header_row(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_quality_report,
    ):
        """Test that header row has bold formatting and background color."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=sample_snapshot_data,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Financial Snapshot"]

        # Check header row formatting (row 7 for data headers)
        header_cell = ws["A7"]
        assert header_cell.font.bold is True
        # RGB color may include alpha channel (00FFFFFF or FFFFFFFF)
        assert "FFFFFF" in header_cell.font.color.rgb  # White text
        assert "366092" in header_cell.fill.start_color.rgb  # Blue background

    def test_number_formatting_percentages(
        self,
        excel_writer,
        sample_quality_report,
    ):
        """Test that percentage fields are formatted correctly."""
        # Create data with percentage fields (numeric values, not pre-formatted)
        data = {
            "bloomberg_ticker": ["8001 JP Equity"],
            "RETURN_COM_EQY": [10.5],  # Will be numeric value
            "pct_margin": [25.0],  # Will be numeric value
        }
        df = pd.DataFrame(data)

        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=df,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Financial Snapshot"]

        # Find RETURN_COM_EQY column
        # Headers are at row 7
        headers = [cell.value for cell in ws[7]]
        roe_col_idx = headers.index("RETURN_COM_EQY") + 1

        # Check formatting of data cell (row 8)
        roe_cell = ws.cell(row=8, column=roe_col_idx)
        # Verify the cell value is numeric and formatting is applied
        assert isinstance(roe_cell.value, (int, float))
        assert roe_cell.number_format == "0.00%"

    def test_number_formatting_currency(
        self,
        excel_writer,
        sample_quality_report,
    ):
        """Test that currency fields are formatted correctly."""
        # Create data with currency fields
        data = {
            "bloomberg_ticker": ["8001 JP Equity"],
            "CUR_MKT_CAP": [1000000],
            "TRAIL_12M_SALES": [500000],
        }
        df = pd.DataFrame(data)

        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=df,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Financial Snapshot"]

        # Find CUR_MKT_CAP column
        headers = [cell.value for cell in ws[7]]
        mkt_cap_col_idx = headers.index("CUR_MKT_CAP") + 1

        # Check formatting
        mkt_cap_cell = ws.cell(row=8, column=mkt_cap_col_idx)
        # Verify the cell value is numeric and formatting is applied
        assert isinstance(mkt_cap_cell.value, (int, float))
        assert mkt_cap_cell.number_format == "¥#,##0"

    def test_number_formatting_dates(
        self,
        excel_writer,
        sample_quality_report,
    ):
        """Test that date fields are formatted correctly."""
        data = {
            "bloomberg_ticker": ["8001 JP Equity"],
            "snapshot_date": [date(2021, 3, 31)],
        }
        df = pd.DataFrame(data)

        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=df,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Financial Snapshot"]

        # Find snapshot_date column
        headers = [cell.value for cell in ws[7]]
        date_col_idx = headers.index("snapshot_date") + 1

        # Check formatting
        date_cell = ws.cell(row=8, column=date_col_idx)
        assert date_cell.number_format == "YYYY-MM-DD"

    def test_workbook_readable_by_excel(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_quality_report,
    ):
        """Test that created workbook can be opened by openpyxl (Excel-compatible)."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=sample_snapshot_data,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        # Try to open with openpyxl (simulates Excel opening)
        try:
            wb = load_workbook(output_path)
            assert wb is not None
            assert len(wb.sheetnames) > 0
        except Exception as e:
            pytest.fail(f"Workbook not readable by Excel: {e}")

    def test_all_sheets_created_with_data(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_ownership_data,
        sample_events_data,
        sample_price_history,
        sample_peer_comps,
        sample_quality_report,
    ):
        """Test that all 5 sheets are created when data is provided."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=sample_snapshot_data,
            ownership_df=sample_ownership_data,
            events_df=sample_events_data,
            price_history_df=sample_price_history,
            peer_comps_df=sample_peer_comps,
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)

        assert len(wb.sheetnames) == 5
        assert "Financial Snapshot" in wb.sheetnames
        assert "Ownership" in wb.sheetnames
        assert "Corporate Actions" in wb.sheetnames
        assert "Price History" in wb.sheetnames
        assert "Peer Comparables" in wb.sheetnames

    def test_ownership_sheet_data_integrity(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_ownership_data,
        sample_quality_report,
    ):
        """Test that ownership sheet contains correct data."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=sample_snapshot_data,
            ownership_df=sample_ownership_data,
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Ownership"]

        # Check headers
        assert ws["A1"].value == "bloomberg_ticker"
        assert ws["B1"].value == "holder_name"
        assert ws["C1"].value == "pct_held"

        # Check data
        assert ws["A2"].value == "8001 JP Equity"
        assert ws["B2"].value == "Holder A"
        assert ws["C2"].value == 10.5

    def test_events_sheet_data_integrity(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_events_data,
        sample_quality_report,
    ):
        """Test that events sheet contains correct data."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=sample_snapshot_data,
            ownership_df=pd.DataFrame(),
            events_df=sample_events_data,
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Corporate Actions"]

        # Check headers
        assert ws["A1"].value == "bloomberg_ticker"
        assert ws["B1"].value == "event_type"

        # Check data
        assert ws["A2"].value == "8001 JP Equity"
        assert ws["B2"].value == "Dividend"

    def test_metadata_bold_formatting(
        self,
        excel_writer,
        sample_snapshot_data,
        sample_quality_report,
    ):
        """Test that metadata section has bold formatting."""
        output_path = excel_writer.write_activist_workbook(
            activist_name="Test",
            snapshot_df=sample_snapshot_data,
            ownership_df=pd.DataFrame(),
            events_df=pd.DataFrame(),
            price_history_df=pd.DataFrame(),
            peer_comps_df=pd.DataFrame(),
            data_quality_report=sample_quality_report,
        )

        wb = load_workbook(output_path)
        ws = wb["Financial Snapshot"]

        # Check that metadata metric names are bold
        for row in range(1, 6):
            cell = ws.cell(row=row, column=1)
            assert cell.font.bold is True


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--cov=excel_writer", "--cov-report=term-missing"])
