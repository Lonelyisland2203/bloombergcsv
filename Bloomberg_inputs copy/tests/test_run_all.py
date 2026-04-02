"""
Integration Tests for Pipeline Orchestration Layer (run_all.py)

This test suite validates the end-to-end orchestration of all 10 pipeline modules.

Test Coverage:
    1. ExecutionConfig validation
    2. CSV loading and target creation
    3. Fiscal period alignment
    4. Sequential data extraction workflow
    5. Parallel data extraction workflow (if enabled)
    6. Data quality validation integration
    7. Excel output generation
    8. Execution summary reporting
    9. Error handling and recovery
    10. Dry-run mode
    11. CLI argument parsing
    12. Full pipeline integration (mock Bloomberg)

Author: Bloomberg Activist Pipeline
"""

import pytest
import sys
import json
from datetime import date, datetime
from pathlib import Path
from unittest.mock import Mock, MagicMock, patch, call
from io import StringIO

import pandas as pd
import numpy as np

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from run_all import (
    ExecutionConfig,
    ExecutionSummary,
    PipelineOrchestrator,
    parse_arguments,
    main,
)
from extract_snapshot import CampaignTarget
from data_validator import DataQualityReport


# =============================================================================
# FIXTURES
# =============================================================================


@pytest.fixture
def sample_input_csv(tmp_path):
    """Create sample input CSV file."""
    csv_content = """target_company,target_ticker,total_filings,first_filing,last_filing,max_ownership_pct,min_ownership_pct
川崎汽船株式会社,9107.T,115,2021-06-14,2026-03-06,0.3899,0.3386
ライフネット生命保険株式会社,7157.T,76,2021-04-06,2026-02-26,0.2113,0.0614
サンケン電気株式会社,6707.T,68,2021-04-07,2025-03-25,0.2865,0.1916"""

    csv_path = tmp_path / "test_input.csv"
    csv_path.write_text(csv_content)
    return csv_path


@pytest.fixture
def execution_config(sample_input_csv, tmp_path):
    """Create ExecutionConfig for testing."""
    return ExecutionConfig(
        input_csv=sample_input_csv,
        activist_name="Effissimo Capital Management",
        output_path=tmp_path / "output.xlsx",
        log_level="WARNING",
        dry_run=False,
    )


@pytest.fixture
def sample_targets():
    """Create sample CampaignTarget objects."""
    return [
        CampaignTarget(
            company_name_japanese="川崎汽船株式会社",
            company_name_english="Kawasaki Kisen Kaisha",
            tse_ticker="9107.T",
            bloomberg_ticker="9107 JP Equity",
            campaign_start=date(2021, 6, 14),
            campaign_end=date(2026, 3, 6),
            max_ownership_pct=0.3899,
            min_ownership_pct=0.3386,
            total_filings=115,
            snapshot_date=date(2021, 3, 31),
            fund_per_override="FY2020",
            fye_month=3,
        ),
        CampaignTarget(
            company_name_japanese="ライフネット生命保険株式会社",
            company_name_english="Lifenet Insurance",
            tse_ticker="7157.T",
            bloomberg_ticker="7157 JP Equity",
            campaign_start=date(2021, 4, 6),
            campaign_end=date(2026, 2, 26),
            max_ownership_pct=0.2113,
            min_ownership_pct=0.0614,
            total_filings=76,
            snapshot_date=date(2020, 12, 31),
            fund_per_override="FY2020",
            fye_month=12,
        ),
    ]


@pytest.fixture
def sample_snapshot_df():
    """Create sample snapshot DataFrame."""
    return pd.DataFrame(
        {
            "ticker": ["9107 JP Equity", "7157 JP Equity"],
            "company_name": ["Kawasaki Kisen", "Lifenet Insurance"],
            "PX_TO_BOOK_RATIO": [0.65, 1.23],
            "RETURN_COM_EQY": [8.5, 12.3],
            "CUR_MKT_CAP": [150000, 45000],
            "data_quality_score": [85.0, 92.0],
        }
    )


@pytest.fixture
def sample_ownership_df():
    """Create sample ownership DataFrame."""
    return pd.DataFrame(
        {
            "ticker": ["9107 JP Equity", "9107 JP Equity", "7157 JP Equity"],
            "holder_name": ["BlackRock", "Vanguard", "T. Rowe Price"],
            "holder_type": ["Investment Advisor", "Investment Advisor", "Fund"],
            "shares_held": [5000000, 3000000, 1500000],
            "pct_of_shares_out": [5.5, 3.2, 7.8],
        }
    )


@pytest.fixture
def sample_events_df():
    """Create sample events DataFrame."""
    return pd.DataFrame(
        {
            "ticker": ["9107 JP Equity", "7157 JP Equity"],
            "event_type": ["Dividend Increase", "Buyback Announcement"],
            "event_date": [date(2022, 5, 15), date(2023, 3, 20)],
            "months_after_activist_entry": [11, 23],
        }
    )


@pytest.fixture
def sample_price_df():
    """Create sample price history DataFrame."""
    dates = pd.date_range("2021-01-01", "2021-12-31", freq="D")
    return pd.DataFrame(
        {
            "ticker": ["9107 JP Equity"] * len(dates),
            "date": dates,
            "adjusted_close": np.random.uniform(100, 120, len(dates)),
            "volume": np.random.randint(1000000, 5000000, len(dates)),
            "days_since_activist_entry": range(-165, len(dates) - 165),
            "cumulative_return": np.random.uniform(-0.1, 0.2, len(dates)),
        }
    )


@pytest.fixture
def sample_peer_comps_df():
    """Create sample peer comparables DataFrame."""
    return pd.DataFrame(
        {
            "ticker": ["9107 JP Equity", "7157 JP Equity"],
            "sector": ["Transportation", "Insurance"],
            "sector_median_pbr": [0.85, 1.45],
            "sector_median_roe": [9.2, 11.5],
            "pbr_discount_to_sector": [-0.24, -0.15],
        }
    )


@pytest.fixture
def sample_quality_report():
    """Create sample DataQualityReport."""
    return DataQualityReport(
        total_securities=2,
        critical_field_coverage={
            "PX_TO_BOOK_RATIO": 1.0,
            "RETURN_COM_EQY": 1.0,
            "CUR_MKT_CAP": 1.0,
        },
        range_violations=[],
        recommended_manual_review=[],
        overall_quality_score=0.885,  # 88.5% as decimal
        notes=[],
    )


# =============================================================================
# TEST: ExecutionConfig
# =============================================================================


def test_execution_config_validation(sample_input_csv, tmp_path):
    """Test ExecutionConfig validation."""
    # Valid config
    config = ExecutionConfig(
        input_csv=sample_input_csv,
        activist_name="Test Activist",
    )
    assert config.input_csv.exists()
    assert config.activist_name == "Test Activist"
    assert config.output_path is not None  # Auto-generated
    assert config.log_level == "INFO"
    assert config.enable_parallel is False
    assert config.dry_run is False


def test_execution_config_missing_csv(tmp_path):
    """Test ExecutionConfig with missing CSV."""
    missing_csv = tmp_path / "missing.csv"

    with pytest.raises(FileNotFoundError, match="Input CSV not found"):
        ExecutionConfig(
            input_csv=missing_csv,
            activist_name="Test Activist",
        )


def test_execution_config_auto_output_path(sample_input_csv):
    """Test automatic output path generation."""
    config = ExecutionConfig(
        input_csv=sample_input_csv,
        activist_name="Effissimo Capital Management",
    )

    # Should auto-generate output path
    assert config.output_path is not None
    assert "effissimo_capital_management" in str(config.output_path).lower()
    assert config.output_path.suffix == ".xlsx"


# =============================================================================
# TEST: CSV Loading
# =============================================================================


def test_load_input_csv(execution_config):
    """Test CSV loading and target creation."""
    orchestrator = PipelineOrchestrator(execution_config)

    targets = orchestrator._load_input_csv()

    # Should create 3 targets
    assert len(targets) == 3

    # Check first target
    target = targets[0]
    assert target.company_name_japanese == "川崎汽船株式会社"
    assert target.tse_ticker == "9107.T"
    assert target.bloomberg_ticker == "9107 JP Equity"
    assert target.campaign_start == date(2021, 6, 14)
    assert target.campaign_end == date(2026, 3, 6)
    assert target.max_ownership_pct == 0.3899
    assert target.total_filings == 115


def test_load_input_csv_missing_columns(tmp_path):
    """Test CSV loading with missing columns."""
    # Create CSV with missing columns
    csv_content = """target_company,target_ticker
Company A,9107.T"""

    csv_path = tmp_path / "invalid.csv"
    csv_path.write_text(csv_content)

    config = ExecutionConfig(
        input_csv=csv_path,
        activist_name="Test",
        log_level="WARNING",
    )
    orchestrator = PipelineOrchestrator(config)

    with pytest.raises(ValueError, match="Missing required columns"):
        orchestrator._load_input_csv()


def test_load_input_csv_invalid_ticker(tmp_path):
    """Test CSV loading with invalid ticker format."""
    csv_content = """target_company,target_ticker,total_filings,first_filing,last_filing,max_ownership_pct
Company A,INVALID,10,2021-01-01,2021-12-31,0.1"""

    csv_path = tmp_path / "invalid_ticker.csv"
    csv_path.write_text(csv_content)

    config = ExecutionConfig(
        input_csv=csv_path,
        activist_name="Test",
        log_level="WARNING",
    )
    orchestrator = PipelineOrchestrator(config)

    # Should log warning but continue
    targets = orchestrator._load_input_csv()
    assert len(targets) == 0  # Ticker conversion failed


# =============================================================================
# TEST: Fiscal Period Alignment
# =============================================================================


@patch("run_all.BloombergSession")
def test_align_fiscal_periods(mock_session_class, execution_config, sample_targets):
    """Test fiscal period alignment."""
    # Mock Bloomberg session
    mock_session = Mock()
    mock_fye_df = pd.DataFrame(
        {
            "ticker": ["9107 JP Equity", "7157 JP Equity"],
            "FISCAL_YEAR_END_MONTH_DE": [3, 12],
        }
    )
    mock_session.reference_data.return_value = mock_fye_df
    mock_session_class.return_value = mock_session

    orchestrator = PipelineOrchestrator(execution_config)
    orchestrator.session = mock_session

    # Remove pre-computed fiscal data from targets
    for target in sample_targets:
        target.fye_month = None
        target.snapshot_date = None
        target.fund_per_override = None

    aligned_targets = orchestrator._align_fiscal_periods(sample_targets)

    # Check alignment
    assert len(aligned_targets) == 2

    # First target (9107, March FYE)
    assert aligned_targets[0].fye_month == 3
    assert aligned_targets[0].snapshot_date is not None
    assert aligned_targets[0].fund_per_override is not None

    # Second target (7157, December FYE)
    assert aligned_targets[1].fye_month == 12
    assert aligned_targets[1].snapshot_date is not None
    assert aligned_targets[1].fund_per_override is not None

    # Alignment report should be saved
    report_files = list(orchestrator.logs_dir.glob("fiscal_alignment_report_*.csv"))
    assert len(report_files) > 0


@patch("run_all.BloombergSession")
def test_align_fiscal_periods_missing_fye(
    mock_session_class, execution_config, sample_targets
):
    """Test fiscal alignment with missing FYE data."""
    # Mock Bloomberg session with missing FYE
    mock_session = Mock()
    mock_fye_df = pd.DataFrame(
        {
            "ticker": ["9107 JP Equity", "7157 JP Equity"],
            "FISCAL_YEAR_END_MONTH_DE": [3, np.nan],  # Missing for second
        }
    )
    mock_session.reference_data.return_value = mock_fye_df
    mock_session_class.return_value = mock_session

    orchestrator = PipelineOrchestrator(execution_config)
    orchestrator.session = mock_session

    # Remove pre-computed fiscal data
    for target in sample_targets:
        target.fye_month = None
        target.snapshot_date = None
        target.fund_per_override = None

    aligned_targets = orchestrator._align_fiscal_periods(sample_targets)

    # Second target should default to March (3)
    assert aligned_targets[1].fye_month == 3


@patch("run_all.BloombergSession")
def test_align_fiscal_periods_with_override(
    mock_session_class, execution_config, sample_targets
):
    """Test fiscal alignment with snapshot date override."""
    # Set snapshot date override
    execution_config.snapshot_date_override = date(2020, 12, 31)

    mock_session = Mock()
    mock_fye_df = pd.DataFrame(
        {
            "ticker": ["9107 JP Equity", "7157 JP Equity"],
            "FISCAL_YEAR_END_MONTH_DE": [3, 12],
        }
    )
    mock_session.reference_data.return_value = mock_fye_df
    mock_session_class.return_value = mock_session

    orchestrator = PipelineOrchestrator(execution_config)
    orchestrator.session = mock_session

    for target in sample_targets:
        target.fye_month = None
        target.snapshot_date = None
        target.fund_per_override = None

    aligned_targets = orchestrator._align_fiscal_periods(sample_targets)

    # All targets should use override date
    for target in aligned_targets:
        assert target.snapshot_date == date(2020, 12, 31)


# =============================================================================
# TEST: Data Extraction
# =============================================================================


@patch("run_all.PeerCompsExtractor")
@patch("run_all.PriceHistoryExtractor")
@patch("run_all.EventsExtractor")
@patch("run_all.OwnershipExtractor")
@patch("run_all.SnapshotExtractor")
def test_extract_all_data_sequential(
    mock_snapshot,
    mock_ownership,
    mock_events,
    mock_price,
    mock_peer,
    execution_config,
    sample_targets,
    sample_snapshot_df,
    sample_ownership_df,
    sample_events_df,
    sample_price_df,
    sample_peer_comps_df,
):
    """Test sequential data extraction."""
    # Mock extractors
    mock_snapshot.return_value.extract_for_targets.return_value = sample_snapshot_df
    mock_ownership.return_value.extract_top_20_holders.return_value = sample_ownership_df
    mock_events.return_value.extract_for_campaigns.return_value = sample_events_df
    mock_price.return_value.extract_for_targets.return_value = sample_price_df
    mock_peer.return_value.extract_peer_comparisons.return_value = sample_peer_comps_df

    orchestrator = PipelineOrchestrator(execution_config)
    orchestrator.session = Mock()  # Mock Bloomberg session

    (
        snapshot_df,
        ownership_df,
        events_df,
        price_df,
        peer_comps_df,
    ) = orchestrator._extract_all_data_sequential(sample_targets)

    # Check all DataFrames returned
    assert len(snapshot_df) == 2
    assert len(ownership_df) == 3
    assert len(events_df) == 2
    assert len(price_df) > 0
    assert len(peer_comps_df) == 2

    # Verify extractors called
    mock_snapshot.return_value.extract_for_targets.assert_called_once()
    mock_ownership.return_value.extract_top_20_holders.assert_called_once()
    mock_events.return_value.extract_for_campaigns.assert_called_once()
    mock_price.return_value.extract_for_targets.assert_called_once()
    mock_peer.return_value.extract_peer_comparisons.assert_called_once()


@patch("run_all.ThreadPoolExecutor")
@patch("run_all.PeerCompsExtractor")
@patch("run_all.PriceHistoryExtractor")
@patch("run_all.EventsExtractor")
@patch("run_all.OwnershipExtractor")
@patch("run_all.SnapshotExtractor")
def test_extract_all_data_parallel(
    mock_snapshot,
    mock_ownership,
    mock_events,
    mock_price,
    mock_peer,
    mock_executor,
    execution_config,
    sample_targets,
    sample_snapshot_df,
    sample_ownership_df,
    sample_events_df,
    sample_price_df,
    sample_peer_comps_df,
):
    """Test parallel data extraction."""
    # Enable parallel execution
    execution_config.enable_parallel = True

    # Mock extractors
    mock_snapshot.return_value.extract_for_targets.return_value = sample_snapshot_df
    mock_ownership.return_value.extract_top_20_holders.return_value = sample_ownership_df
    mock_events.return_value.extract_for_campaigns.return_value = sample_events_df
    mock_price.return_value.extract_for_targets.return_value = sample_price_df
    mock_peer.return_value.extract_peer_comparisons.return_value = sample_peer_comps_df

    # Mock ThreadPoolExecutor
    mock_future = Mock()
    mock_future.result.side_effect = [
        sample_snapshot_df,
        sample_ownership_df,
        sample_events_df,
        sample_price_df,
        sample_peer_comps_df,
    ]

    mock_executor_instance = MagicMock()
    mock_executor_instance.__enter__.return_value = mock_executor_instance
    mock_executor_instance.submit.return_value = mock_future
    mock_executor.return_value = mock_executor_instance

    orchestrator = PipelineOrchestrator(execution_config)
    orchestrator.session = Mock()

    (
        snapshot_df,
        ownership_df,
        events_df,
        price_df,
        peer_comps_df,
    ) = orchestrator._extract_all_data_parallel(sample_targets)

    # Check all DataFrames returned
    assert len(snapshot_df) == 2
    assert len(ownership_df) == 3
    assert len(events_df) == 2

    # ThreadPoolExecutor should be called with 5 workers
    mock_executor.assert_called_once_with(max_workers=5)


# =============================================================================
# TEST: Data Validation
# =============================================================================


@patch("run_all.DataValidator")
def test_validate_data_quality(
    mock_validator, execution_config, sample_snapshot_df, sample_quality_report
):
    """Test data quality validation."""
    # Mock validator
    mock_validator_instance = Mock()
    mock_validator_instance.validate_snapshot_data.return_value = sample_quality_report
    mock_validator.return_value = mock_validator_instance

    orchestrator = PipelineOrchestrator(execution_config)

    quality_report = orchestrator._validate_data_quality(sample_snapshot_df)

    # Check report
    assert quality_report.overall_quality_score == 0.885  # Decimal format
    assert quality_report.total_securities == 2
    assert len(quality_report.recommended_manual_review) == 0

    # Validator should be called
    mock_validator_instance.validate_snapshot_data.assert_called_once()
    mock_validator_instance.save_quality_report.assert_called_once()


# =============================================================================
# TEST: Excel Output
# =============================================================================


@patch("run_all.ExcelWriter")
def test_write_excel_output(
    mock_writer,
    execution_config,
    sample_snapshot_df,
    sample_ownership_df,
    sample_events_df,
    sample_price_df,
    sample_peer_comps_df,
    sample_quality_report,
    tmp_path,
):
    """Test Excel output generation."""
    # Mock writer
    output_path = tmp_path / "test_output.xlsx"
    mock_writer_instance = Mock()
    mock_writer_instance.write_activist_workbook.return_value = output_path
    mock_writer.return_value = mock_writer_instance

    orchestrator = PipelineOrchestrator(execution_config)

    result_path = orchestrator._write_excel_output(
        sample_snapshot_df,
        sample_ownership_df,
        sample_events_df,
        sample_price_df,
        sample_peer_comps_df,
        sample_quality_report,
    )

    assert result_path == output_path

    # Writer should be called with correct arguments
    mock_writer_instance.write_activist_workbook.assert_called_once_with(
        activist_name=execution_config.activist_name,
        snapshot_df=sample_snapshot_df,
        ownership_df=sample_ownership_df,
        events_df=sample_events_df,
        price_df=sample_price_df,
        peer_comps_df=sample_peer_comps_df,
        quality_report=sample_quality_report,
        output_path=execution_config.output_path,
    )


# =============================================================================
# TEST: Execution Summary
# =============================================================================


def test_execution_summary_creation():
    """Test ExecutionSummary creation."""
    summary = ExecutionSummary(
        total_companies=30,
        successful_extractions=28,
        failed_extractions=2,
        data_quality_score=85.5,
        manual_review_flags=["9107 JP Equity", "7157 JP Equity"],
        execution_time_seconds=123.45,
    )

    assert summary.total_companies == 30
    assert summary.successful_extractions == 28
    assert summary.failed_extractions == 2
    assert summary.data_quality_score == 85.5
    assert len(summary.manual_review_flags) == 2

    # Test to_dict
    summary_dict = summary.to_dict()
    assert summary_dict["total_companies"] == 30
    assert summary_dict["data_quality_score"] == 85.5


def test_print_execution_summary(capsys, sample_input_csv):
    """Test execution summary printing."""
    summary = ExecutionSummary(
        total_companies=30,
        successful_extractions=28,
        failed_extractions=2,
        data_quality_score=85.5,
        manual_review_flags=["9107 JP Equity"],
        execution_time_seconds=123.45,
        output_file=Path("/tmp/output.xlsx"),
    )

    config = ExecutionConfig(
        input_csv=sample_input_csv,  # Use valid CSV path
        activist_name="Test",
        log_level="WARNING",
    )
    orchestrator = PipelineOrchestrator(config)
    orchestrator._print_execution_summary(summary)

    captured = capsys.readouterr()
    assert "EXECUTION SUMMARY" in captured.out
    assert "Total Companies:           30" in captured.out
    assert "Successful Extractions:    28" in captured.out
    assert "Data Quality Score:        85.5%" in captured.out
    assert "9107 JP Equity" in captured.out


# =============================================================================
# TEST: Dry Run Mode
# =============================================================================


@patch("run_all.BloombergSession")
def test_dry_run_mode(mock_session_class, sample_input_csv, tmp_path):
    """Test dry-run mode (no Bloomberg queries)."""
    config = ExecutionConfig(
        input_csv=sample_input_csv,
        activist_name="Test Activist",
        dry_run=True,
        log_level="WARNING",
    )

    orchestrator = PipelineOrchestrator(config)
    summary = orchestrator.run()

    # Bloomberg session should NOT be initialized
    mock_session_class.assert_not_called()

    # Summary should have zero extractions
    assert summary.total_companies == 3
    assert summary.successful_extractions == 0
    assert summary.failed_extractions == 0


# =============================================================================
# TEST: CLI Argument Parsing
# =============================================================================


def test_parse_arguments_basic(monkeypatch):
    """Test basic CLI argument parsing."""
    test_args = [
        "run_all.py",
        "--input",
        "test_input.csv",
        "--activist",
        "Effissimo Capital Management",
    ]

    with monkeypatch.context() as m:
        m.setattr(sys, "argv", test_args)
        args = parse_arguments()

    assert args.input == Path("test_input.csv")
    assert args.activist == "Effissimo Capital Management"
    assert args.output is None
    assert args.log_level == "INFO"
    assert args.parallel is False
    assert args.dry_run is False


def test_parse_arguments_full(monkeypatch):
    """Test CLI argument parsing with all options."""
    test_args = [
        "run_all.py",
        "--input",
        "test_input.csv",
        "--activist",
        "Test Activist",
        "--output",
        "custom_output.xlsx",
        "--snapshot-date",
        "2021-03-31",
        "--log-level",
        "DEBUG",
        "--parallel",
        "--dry-run",
    ]

    with monkeypatch.context() as m:
        m.setattr(sys, "argv", test_args)
        args = parse_arguments()

    assert args.input == Path("test_input.csv")
    assert args.activist == "Test Activist"
    assert args.output == Path("custom_output.xlsx")
    assert args.snapshot_date == date(2021, 3, 31)
    assert args.log_level == "DEBUG"
    assert args.parallel is True
    assert args.dry_run is True


def test_parse_arguments_missing_required(monkeypatch, capsys):
    """Test CLI argument parsing with missing required args."""
    test_args = ["run_all.py", "--input", "test_input.csv"]
    # Missing --activist

    with monkeypatch.context() as m:
        m.setattr(sys, "argv", test_args)
        with pytest.raises(SystemExit):
            parse_arguments()


# =============================================================================
# TEST: Full Pipeline Integration (Mocked Bloomberg)
# =============================================================================


@patch("run_all.ExcelWriter")
@patch("run_all.DataValidator")
@patch("run_all.PeerCompsExtractor")
@patch("run_all.PriceHistoryExtractor")
@patch("run_all.EventsExtractor")
@patch("run_all.OwnershipExtractor")
@patch("run_all.SnapshotExtractor")
@patch("run_all.BloombergSession")
def test_full_pipeline_integration(
    mock_session_class,
    mock_snapshot,
    mock_ownership,
    mock_events,
    mock_price,
    mock_peer,
    mock_validator,
    mock_writer,
    sample_input_csv,
    sample_snapshot_df,
    sample_ownership_df,
    sample_events_df,
    sample_price_df,
    sample_peer_comps_df,
    sample_quality_report,
    tmp_path,
):
    """Test complete pipeline execution with mocked Bloomberg."""
    # Mock Bloomberg session
    mock_session = Mock()
    mock_fye_df = pd.DataFrame(
        {
            "ticker": ["9107 JP Equity", "7157 JP Equity", "6707 JP Equity"],
            "FISCAL_YEAR_END_MONTH_DE": [3, 12, 3],
        }
    )
    mock_session.reference_data.return_value = mock_fye_df
    mock_session_class.return_value = mock_session

    # Mock extractors
    mock_snapshot.return_value.extract_for_targets.return_value = sample_snapshot_df
    mock_ownership.return_value.extract_top_20_holders.return_value = sample_ownership_df
    mock_events.return_value.extract_for_campaigns.return_value = sample_events_df
    mock_price.return_value.extract_for_targets.return_value = sample_price_df
    mock_peer.return_value.extract_peer_comparisons.return_value = sample_peer_comps_df

    # Mock validator
    mock_validator_instance = Mock()
    mock_validator_instance.validate_snapshot_data.return_value = sample_quality_report
    mock_validator.return_value = mock_validator_instance

    # Mock writer
    output_path = tmp_path / "output.xlsx"
    mock_writer_instance = Mock()
    mock_writer_instance.write_activist_workbook.return_value = output_path
    mock_writer.return_value = mock_writer_instance

    # Create config and run pipeline
    config = ExecutionConfig(
        input_csv=sample_input_csv,
        activist_name="Effissimo Capital Management",
        output_path=output_path,
        log_level="WARNING",
    )

    orchestrator = PipelineOrchestrator(config)
    summary = orchestrator.run()

    # Check summary
    assert summary.total_companies == 3
    assert summary.successful_extractions == 2  # From sample_snapshot_df
    assert summary.failed_extractions == 1
    assert summary.data_quality_score == 88.5  # Converted to percentage in ExecutionSummary
    assert summary.output_file == output_path

    # Verify all extractors called
    mock_snapshot.return_value.extract_for_targets.assert_called_once()
    mock_ownership.return_value.extract_top_20_holders.assert_called_once()
    mock_events.return_value.extract_for_campaigns.assert_called_once()
    mock_price.return_value.extract_for_targets.assert_called_once()
    mock_peer.return_value.extract_peer_comparisons.assert_called_once()

    # Verify validator called
    mock_validator_instance.validate_snapshot_data.assert_called_once()

    # Verify writer called
    mock_writer_instance.write_activist_workbook.assert_called_once()

    # Verify Bloomberg session lifecycle
    mock_session.start.assert_called_once()
    mock_session.stop.assert_called_once()


# =============================================================================
# TEST: Error Handling
# =============================================================================


@patch("run_all.BloombergSession")
def test_pipeline_error_handling_session_failure(
    mock_session_class, sample_input_csv
):
    """Test error handling when Bloomberg session fails."""
    # Mock session to raise exception on start
    mock_session = Mock()
    mock_session.start.side_effect = Exception("Bloomberg Terminal not running")
    mock_session_class.return_value = mock_session

    config = ExecutionConfig(
        input_csv=sample_input_csv,
        activist_name="Test",
        log_level="WARNING",
    )

    orchestrator = PipelineOrchestrator(config)

    with pytest.raises(Exception, match="Bloomberg Terminal not running"):
        orchestrator.run()

    # Session stop should still be called (cleanup)
    mock_session.stop.assert_called_once()


@patch("run_all.SnapshotExtractor")
@patch("run_all.BloombergSession")
def test_pipeline_error_handling_extractor_failure(
    mock_session_class, mock_snapshot, sample_input_csv
):
    """Test error handling when extractor fails."""
    # Mock Bloomberg session
    mock_session = Mock()
    mock_fye_df = pd.DataFrame(
        {
            "ticker": ["9107 JP Equity", "7157 JP Equity", "6707 JP Equity"],
            "FISCAL_YEAR_END_MONTH_DE": [3, 12, 3],
        }
    )
    mock_session.reference_data.return_value = mock_fye_df
    mock_session_class.return_value = mock_session

    # Mock snapshot extractor to raise exception
    mock_snapshot.return_value.extract_for_targets.side_effect = Exception(
        "Data extraction failed"
    )

    config = ExecutionConfig(
        input_csv=sample_input_csv,
        activist_name="Test",
        log_level="WARNING",
    )

    orchestrator = PipelineOrchestrator(config)

    with pytest.raises(Exception, match="Data extraction failed"):
        orchestrator.run()

    # Session cleanup should still occur
    mock_session.stop.assert_called_once()


# =============================================================================
# TEST: Main Entry Point
# =============================================================================


@patch("run_all.PipelineOrchestrator")
def test_main_success(mock_orchestrator, monkeypatch, tmp_path):
    """Test main() entry point with successful execution."""
    # Create temporary CSV
    csv_path = tmp_path / "test_input.csv"
    csv_path.write_text("target_company,target_ticker,total_filings,first_filing,last_filing,max_ownership_pct\nTest,9107.T,10,2021-01-01,2021-12-31,0.1")

    test_args = [
        "run_all.py",
        "--input",
        str(csv_path),
        "--activist",
        "Test",
        "--dry-run",
    ]

    with monkeypatch.context() as m:
        m.setattr(sys, "argv", test_args)

        # Mock orchestrator to return successful summary
        mock_summary = ExecutionSummary(
            total_companies=1,
            successful_extractions=1,
            failed_extractions=0,
            data_quality_score=100.0,
            manual_review_flags=[],
        )
        mock_orchestrator.return_value.run.return_value = mock_summary

        exit_code = main()

    assert exit_code == 0


@patch("run_all.PipelineOrchestrator")
def test_main_with_failures(mock_orchestrator, monkeypatch, tmp_path):
    """Test main() entry point with failed extractions."""
    csv_path = tmp_path / "test_input.csv"
    csv_path.write_text("target_company,target_ticker,total_filings,first_filing,last_filing,max_ownership_pct\nTest,9107.T,10,2021-01-01,2021-12-31,0.1")

    test_args = [
        "run_all.py",
        "--input",
        str(csv_path),
        "--activist",
        "Test",
        "--dry-run",
    ]

    with monkeypatch.context() as m:
        m.setattr(sys, "argv", test_args)

        # Mock orchestrator with failures
        mock_summary = ExecutionSummary(
            total_companies=3,
            successful_extractions=2,
            failed_extractions=1,
            data_quality_score=75.0,
            manual_review_flags=["9107 JP Equity"],
        )
        mock_orchestrator.return_value.run.return_value = mock_summary

        exit_code = main()

    # Should return 1 (failure) due to failed extractions
    assert exit_code == 1


@patch("run_all.PipelineOrchestrator")
def test_main_exception(mock_orchestrator, monkeypatch, tmp_path):
    """Test main() entry point with exception."""
    csv_path = tmp_path / "test_input.csv"
    csv_path.write_text("target_company,target_ticker,total_filings,first_filing,last_filing,max_ownership_pct\nTest,9107.T,10,2021-01-01,2021-12-31,0.1")

    test_args = [
        "run_all.py",
        "--input",
        str(csv_path),
        "--activist",
        "Test",
    ]

    with monkeypatch.context() as m:
        m.setattr(sys, "argv", test_args)

        # Mock orchestrator to raise exception
        mock_orchestrator.return_value.run.side_effect = Exception(
            "Pipeline failed"
        )

        exit_code = main()

    assert exit_code == 1


def test_main_keyboard_interrupt(monkeypatch, tmp_path):
    """Test main() entry point with keyboard interrupt."""
    csv_path = tmp_path / "test_input.csv"
    csv_path.write_text("target_company,target_ticker,total_filings,first_filing,last_filing,max_ownership_pct\nTest,9107.T,10,2021-01-01,2021-12-31,0.1")

    test_args = [
        "run_all.py",
        "--input",
        str(csv_path),
        "--activist",
        "Test",
    ]

    with monkeypatch.context() as m:
        m.setattr(sys, "argv", test_args)

        # Mock orchestrator to raise KeyboardInterrupt
        with patch("run_all.PipelineOrchestrator") as mock_orch:
            mock_orch.return_value.run.side_effect = KeyboardInterrupt()

            exit_code = main()

    assert exit_code == 1


# =============================================================================
# PERFORMANCE TESTS
# =============================================================================


def test_pipeline_execution_time_logging(execution_config, capsys):
    """Test that execution time is logged."""
    config = ExecutionConfig(
        input_csv=execution_config.input_csv,
        activist_name="Test",
        dry_run=True,
        log_level="INFO",
    )

    orchestrator = PipelineOrchestrator(config)
    summary = orchestrator.run()

    # Execution time should be recorded (even for dry run, it's >= 0)
    assert summary.execution_time_seconds >= 0
    # In dry-run mode, time will be minimal but non-negative
    assert isinstance(summary.execution_time_seconds, float)


# =============================================================================
# RUN TESTS
# =============================================================================


if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])
