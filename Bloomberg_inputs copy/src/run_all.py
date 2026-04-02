"""
Orchestration Layer for Bloomberg Activist Data Pipeline

This is the main CLI entry point that coordinates all 10 modules to produce
a comprehensive Excel workbook with activist campaign data.

Execution Workflow:
    Step 1: Load Input CSV
        - Read effissimo_summary_by_company.csv
        - Validate columns (ticker, first_filing, last_filing, etc.)
        - Convert tickers (.T → JP Equity) using ticker_converter
        - Create CampaignTarget objects

    Step 2: Align Fiscal Periods
        - Query FISCAL_YEAR_END_MONTH_DE for all tickers (single batch)
        - Compute snapshot_date for each campaign (using fiscal_period_aligner)
        - Construct FUND_PER overrides
        - Log fiscal alignment report

    Step 3: Extract Data (Parallel Execution Optional)
        - Snapshot Extractor → financial/valuation/governance fields
        - Ownership Extractor → Top 20 holders
        - Events Extractor → corporate actions (campaign period only)
        - Price History Extractor → daily prices
        - Peer Comps Extractor → sector medians

    Step 4: Validate Data Quality
        - Run DataValidator on snapshot_df
        - Generate quality report
        - Flag securities with >30% missing data
        - Save gap report to logs/

    Step 5: Write Excel Output
        - ExcelWriter creates 5-sheet workbook
        - Apply formatting
        - Save to output directory
        - Return file path

    Step 6: Execution Summary
        - Print summary statistics
        - Show data quality score
        - List manual review flags
        - Save execution log

CLI Usage:
    python src/run_all.py \
        --input effissimo_summary_by_company.csv \
        --activist "Effissimo Capital Management" \
        --output output/effissimo_bloomberg_data.xlsx

    Optional Arguments:
        --snapshot-date: Override snapshot date (for testing)
        --log-level: Set logging verbosity (DEBUG, INFO, WARNING, ERROR)
        --parallel: Enable parallel execution of field groups
        --dry-run: Validate inputs without querying Bloomberg

Author: Bloomberg Activist Pipeline
"""

import argparse
import logging
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import date, datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple

import pandas as pd
import numpy as np

# Import all pipeline modules
from ticker_converter import convert_ticker
from fiscal_period_aligner import compute_snapshot_date, construct_fund_per_override
from bloomberg_session import BloombergSession
from batching_engine import BatchingEngine
from extract_snapshot import SnapshotExtractor, CampaignTarget
from extract_ownership import OwnershipExtractor
from extract_events import EventsExtractor, CampaignPeriod
from extract_price_history import PriceHistoryExtractor, PriceHistoryTarget
from extract_peer_comps import PeerCompsExtractor, PeerCompTarget
from data_validator import DataValidator
from excel_writer import ExcelWriter


# Configure logging
logger = logging.getLogger(__name__)


@dataclass
class ExecutionConfig:
    """
    Configuration for pipeline execution.

    Attributes:
        input_csv: Path to input CSV file
        activist_name: Name of activist investor (for output filename)
        output_path: Path for Excel output file
        snapshot_date_override: Override snapshot date (for testing)
        log_level: Logging verbosity level
        enable_parallel: Enable parallel execution of extractors
        dry_run: Validate inputs without querying Bloomberg
    """

    input_csv: Path
    activist_name: str
    output_path: Optional[Path] = None
    snapshot_date_override: Optional[date] = None
    log_level: str = "INFO"
    enable_parallel: bool = False
    dry_run: bool = False

    def __post_init__(self):
        """Validate configuration."""
        if not self.input_csv.exists():
            raise FileNotFoundError(f"Input CSV not found: {self.input_csv}")

        if self.output_path is None:
            # Auto-generate output path
            src_dir = Path(__file__).parent
            output_dir = src_dir.parent / "output"
            timestamp = datetime.now().strftime("%Y%m%d")
            filename = f"{self.activist_name.replace(' ', '_').lower()}_bloomberg_data_{timestamp}.xlsx"
            self.output_path = output_dir / filename


@dataclass
class ExecutionSummary:
    """
    Summary of pipeline execution results.

    Attributes:
        total_companies: Total number of companies processed
        successful_extractions: Number of successful extractions
        failed_extractions: Number of failed extractions
        data_quality_score: Overall data quality score (0-100)
        manual_review_flags: List of tickers requiring manual review
        output_file: Path to generated Excel file
        execution_time_seconds: Total execution time
        log_file: Path to execution log file
    """

    total_companies: int
    successful_extractions: int
    failed_extractions: int
    data_quality_score: float
    manual_review_flags: List[str]
    output_file: Optional[Path] = None
    execution_time_seconds: float = 0.0
    log_file: Optional[Path] = None

    def to_dict(self) -> Dict:
        """Convert to dictionary for logging."""
        return {
            "total_companies": self.total_companies,
            "successful_extractions": self.successful_extractions,
            "failed_extractions": self.failed_extractions,
            "data_quality_score": self.data_quality_score,
            "manual_review_flags": self.manual_review_flags,
            "output_file": str(self.output_file) if self.output_file else None,
            "execution_time_seconds": self.execution_time_seconds,
            "log_file": str(self.log_file) if self.log_file else None,
        }


class PipelineOrchestrator:
    """
    Orchestrates the end-to-end Bloomberg activist data extraction pipeline.

    This class coordinates all 10 modules to produce a comprehensive Excel workbook
    with activist campaign data.

    Attributes:
        config: Execution configuration
        session: Bloomberg session (initialized in run())
        logs_dir: Directory for execution logs
    """

    def __init__(self, config: ExecutionConfig):
        """
        Initialize pipeline orchestrator.

        Args:
            config: Execution configuration
        """
        self.config = config
        self.session: Optional[BloombergSession] = None

        # Create logs directory
        src_dir = Path(__file__).parent
        self.logs_dir = src_dir.parent / "logs"
        self.logs_dir.mkdir(parents=True, exist_ok=True)

        # Configure logging
        self._setup_logging()

        logger.info("=" * 80)
        logger.info("Bloomberg Activist Data Pipeline - Orchestration Layer")
        logger.info("=" * 80)
        logger.info(f"Input CSV: {self.config.input_csv}")
        logger.info(f"Activist: {self.config.activist_name}")
        logger.info(f"Output: {self.config.output_path}")
        logger.info(f"Parallel Execution: {self.config.enable_parallel}")
        logger.info(f"Dry Run: {self.config.dry_run}")
        logger.info("=" * 80)

    def _setup_logging(self) -> None:
        """Configure logging with file and console handlers."""
        # Create log file
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        log_file = self.logs_dir / f"pipeline_execution_{timestamp}.log"

        # Configure root logger
        root_logger = logging.getLogger()
        root_logger.setLevel(getattr(logging, self.config.log_level))

        # File handler (detailed)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        root_logger.addHandler(file_handler)

        # Console handler (summary)
        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setLevel(getattr(logging, self.config.log_level))
        console_formatter = logging.Formatter("%(levelname)s: %(message)s")
        console_handler.setFormatter(console_formatter)
        root_logger.addHandler(console_handler)

        logger.info(f"Logging initialized. Log file: {log_file}")

    def run(self) -> ExecutionSummary:
        """
        Execute the complete pipeline.

        Returns:
            Execution summary with results and statistics

        Raises:
            Exception: If pipeline execution fails at any stage
        """
        start_time = datetime.now()

        try:
            # Step 1: Load Input CSV
            logger.info("\n" + "=" * 80)
            logger.info("STEP 1: Load Input CSV and Create Campaign Targets")
            logger.info("=" * 80)
            targets = self._load_input_csv()
            logger.info(f"✓ Loaded {len(targets)} campaign targets")

            if self.config.dry_run:
                logger.info("\nDRY RUN MODE: Stopping before Bloomberg queries")
                return ExecutionSummary(
                    total_companies=len(targets),
                    successful_extractions=0,
                    failed_extractions=0,
                    data_quality_score=0.0,
                    manual_review_flags=[],
                )

            # Initialize Bloomberg session
            logger.info("\nInitializing Bloomberg session...")
            self.session = BloombergSession()
            self.session.start()
            logger.info("✓ Bloomberg session started")

            # Step 2: Align Fiscal Periods
            logger.info("\n" + "=" * 80)
            logger.info("STEP 2: Align Fiscal Periods")
            logger.info("=" * 80)
            targets = self._align_fiscal_periods(targets)
            logger.info(f"✓ Fiscal periods aligned for {len(targets)} targets")

            # Step 3: Extract Data
            logger.info("\n" + "=" * 80)
            logger.info("STEP 3: Extract Data from Bloomberg")
            logger.info("=" * 80)
            (
                snapshot_df,
                ownership_df,
                events_df,
                price_df,
                peer_comps_df,
            ) = self._extract_all_data(targets)

            logger.info(f"✓ Snapshot: {len(snapshot_df)} rows")
            logger.info(f"✓ Ownership: {len(ownership_df)} rows")
            logger.info(f"✓ Events: {len(events_df)} rows")
            logger.info(f"✓ Price History: {len(price_df)} rows")
            logger.info(f"✓ Peer Comps: {len(peer_comps_df)} rows")

            # Step 4: Validate Data Quality
            logger.info("\n" + "=" * 80)
            logger.info("STEP 4: Validate Data Quality")
            logger.info("=" * 80)
            quality_report = self._validate_data_quality(snapshot_df)
            logger.info(f"✓ Data Quality Score: {quality_report.overall_quality_score * 100:.1f}%")
            logger.info(
                f"✓ Manual Review Required: {len(quality_report.recommended_manual_review)} securities"
            )

            # Step 5: Write Excel Output
            logger.info("\n" + "=" * 80)
            logger.info("STEP 5: Write Excel Output")
            logger.info("=" * 80)
            output_path = self._write_excel_output(
                snapshot_df,
                ownership_df,
                events_df,
                price_df,
                peer_comps_df,
                quality_report,
            )
            logger.info(f"✓ Excel workbook written: {output_path}")

            # Step 6: Execution Summary
            logger.info("\n" + "=" * 80)
            logger.info("STEP 6: Execution Summary")
            logger.info("=" * 80)

            end_time = datetime.now()
            execution_time = (end_time - start_time).total_seconds()

            summary = ExecutionSummary(
                total_companies=len(targets),
                successful_extractions=len(snapshot_df),
                failed_extractions=len(targets) - len(snapshot_df),
                data_quality_score=quality_report.overall_quality_score * 100,  # Convert to percentage
                manual_review_flags=quality_report.recommended_manual_review,
                output_file=output_path,
                execution_time_seconds=execution_time,
            )

            self._print_execution_summary(summary)

            return summary

        except Exception as e:
            logger.error(f"Pipeline execution failed: {e}", exc_info=True)
            raise

        finally:
            # Cleanup Bloomberg session
            if self.session is not None:
                try:
                    self.session.stop()
                    logger.info("✓ Bloomberg session closed")
                except Exception as e:
                    logger.warning(f"Error closing Bloomberg session: {e}")

    def _load_input_csv(self) -> List[CampaignTarget]:
        """
        Load input CSV and create CampaignTarget objects.

        Returns:
            List of CampaignTarget objects

        Raises:
            ValueError: If CSV is missing required columns
        """
        logger.info(f"Reading input CSV: {self.config.input_csv}")

        # Read CSV
        df = pd.read_csv(self.config.input_csv)
        logger.info(f"CSV loaded: {len(df)} rows, {len(df.columns)} columns")

        # Validate required columns
        required_cols = [
            "target_company",
            "target_ticker",
            "first_filing",
            "last_filing",
            "max_ownership_pct",
            "total_filings",
        ]
        missing_cols = [col for col in required_cols if col not in df.columns]
        if missing_cols:
            raise ValueError(f"Missing required columns: {missing_cols}")

        logger.info("✓ All required columns present")

        # Parse dates
        df["first_filing"] = pd.to_datetime(df["first_filing"]).dt.date
        df["last_filing"] = pd.to_datetime(df["last_filing"]).dt.date

        # Convert tickers
        logger.info("Converting TSE tickers to Bloomberg format...")
        targets = []
        conversion_errors = []

        for idx, row in df.iterrows():
            try:
                bloomberg_ticker = convert_ticker(row["target_ticker"])

                target = CampaignTarget(
                    company_name_japanese=row["target_company"],
                    company_name_english=None,  # Will be fetched from Bloomberg
                    tse_ticker=row["target_ticker"],
                    bloomberg_ticker=bloomberg_ticker,
                    campaign_start=row["first_filing"],
                    campaign_end=row["last_filing"] if pd.notna(row["last_filing"]) else None,
                    max_ownership_pct=row["max_ownership_pct"],
                    min_ownership_pct=row.get("min_ownership_pct"),
                    total_filings=row["total_filings"],
                    snapshot_date=None,  # Will be computed in Step 2
                    fund_per_override=None,  # Will be computed in Step 2
                    fye_month=None,  # Will be fetched from Bloomberg
                )
                targets.append(target)

            except Exception as e:
                conversion_errors.append((row["target_ticker"], str(e)))
                logger.warning(f"Ticker conversion failed for {row['target_ticker']}: {e}")

        if conversion_errors:
            logger.warning(
                f"Ticker conversion failed for {len(conversion_errors)} securities"
            )
            for ticker, error in conversion_errors:
                logger.debug(f"  {ticker}: {error}")

        logger.info(f"✓ Created {len(targets)} CampaignTarget objects")

        return targets

    def _align_fiscal_periods(self, targets: List[CampaignTarget]) -> List[CampaignTarget]:
        """
        Query fiscal year-end months and compute snapshot dates.

        Args:
            targets: List of CampaignTarget objects

        Returns:
            Updated targets with snapshot_date and fund_per_override

        Raises:
            Exception: If fiscal alignment fails
        """
        logger.info("Querying FISCAL_YEAR_END_MONTH_DE from Bloomberg...")

        # Extract tickers
        tickers = [t.bloomberg_ticker for t in targets]

        # Batch query for fiscal year-end months
        fye_df = self.session.reference_data(
            tickers, ["FISCAL_YEAR_END_MONTH_DE"], overrides=None
        )

        logger.info(f"✓ Retrieved fiscal year-end data for {len(fye_df)} securities")

        # Map ticker → fye_month
        fye_map = {}
        for _, row in fye_df.iterrows():
            ticker = row["ticker"]
            fye_month = row.get("FISCAL_YEAR_END_MONTH_DE")
            if pd.notna(fye_month):
                fye_map[ticker] = int(fye_month)
            else:
                logger.warning(f"Missing FYE month for {ticker}, defaulting to March (3)")
                fye_map[ticker] = 3  # Default to March for Japanese companies

        # Compute snapshot dates
        logger.info("Computing snapshot dates using fiscal alignment logic...")
        alignment_report = []

        for target in targets:
            ticker = target.bloomberg_ticker
            fye_month = fye_map.get(ticker, 3)

            # Use snapshot_date_override if provided (for testing)
            if self.config.snapshot_date_override:
                snapshot_date = self.config.snapshot_date_override
                logger.debug(f"{ticker}: Using override snapshot_date={snapshot_date}")
            else:
                snapshot_date = compute_snapshot_date(target.campaign_start, fye_month)

            fund_per = construct_fund_per_override(snapshot_date)

            # Update target
            target.fye_month = fye_month
            target.snapshot_date = snapshot_date
            target.fund_per_override = fund_per

            alignment_report.append(
                {
                    "ticker": ticker,
                    "campaign_start": target.campaign_start,
                    "fye_month": fye_month,
                    "snapshot_date": snapshot_date,
                    "fund_per": fund_per,
                }
            )

            logger.debug(
                f"{ticker}: campaign_start={target.campaign_start}, "
                f"fye_month={fye_month}, snapshot_date={snapshot_date}, "
                f"fund_per={fund_per}"
            )

        # Save alignment report
        alignment_df = pd.DataFrame(alignment_report)
        report_path = self.logs_dir / f"fiscal_alignment_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        alignment_df.to_csv(report_path, index=False)
        logger.info(f"✓ Fiscal alignment report saved: {report_path}")

        return targets

    def _extract_all_data(
        self, targets: List[CampaignTarget]
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Extract data from all 5 extractors.

        Args:
            targets: List of CampaignTarget objects

        Returns:
            Tuple of (snapshot_df, ownership_df, events_df, price_df, peer_comps_df)
        """
        if self.config.enable_parallel:
            logger.info("Using parallel execution for extractors...")
            return self._extract_all_data_parallel(targets)
        else:
            logger.info("Using sequential execution for extractors...")
            return self._extract_all_data_sequential(targets)

    def _extract_all_data_sequential(
        self, targets: List[CampaignTarget]
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """Execute extractors sequentially."""
        # 1. Snapshot Extractor
        logger.info("\n[1/5] Snapshot Extractor: Extracting financial/valuation fields...")
        snapshot_extractor = SnapshotExtractor(self.session)
        snapshot_df = snapshot_extractor.extract_for_targets(targets)
        logger.info(f"✓ Snapshot extraction complete: {len(snapshot_df)} rows")

        # 2. Ownership Extractor
        logger.info("\n[2/5] Ownership Extractor: Extracting Top 20 holders...")
        ownership_extractor = OwnershipExtractor(self.session)
        tickers = [t.bloomberg_ticker for t in targets]
        ownership_df = ownership_extractor.extract_top_20_holders(tickers)
        logger.info(f"✓ Ownership extraction complete: {len(ownership_df)} rows")

        # 3. Events Extractor
        logger.info("\n[3/5] Events Extractor: Extracting corporate actions...")
        events_extractor = EventsExtractor(self.session)
        campaign_periods = [
            CampaignPeriod(
                ticker=t.bloomberg_ticker,
                company_name=t.company_name_japanese,
                campaign_start=t.campaign_start,
                campaign_end=t.campaign_end,
            )
            for t in targets
        ]
        events_df = events_extractor.extract_for_campaigns(campaign_periods)
        logger.info(f"✓ Events extraction complete: {len(events_df)} rows")

        # 4. Price History Extractor
        logger.info("\n[4/5] Price History Extractor: Extracting daily prices...")
        price_extractor = PriceHistoryExtractor(self.session)
        price_targets = [
            PriceHistoryTarget(
                ticker=t.bloomberg_ticker,
                campaign_start=t.campaign_start,
                campaign_end=t.campaign_end,
            )
            for t in targets
        ]
        price_df = price_extractor.extract_for_targets(price_targets)
        logger.info(f"✓ Price history extraction complete: {len(price_df)} rows")

        # 5. Peer Comps Extractor
        logger.info("\n[5/5] Peer Comps Extractor: Computing sector medians...")
        peer_extractor = PeerCompsExtractor(self.session)
        peer_targets = [
            PeerCompTarget(
                ticker=t.bloomberg_ticker, company_name=t.company_name_japanese
            )
            for t in targets
        ]
        peer_comps_df = peer_extractor.extract_peer_comparisons(peer_targets)
        logger.info(f"✓ Peer comps extraction complete: {len(peer_comps_df)} rows")

        return snapshot_df, ownership_df, events_df, price_df, peer_comps_df

    def _extract_all_data_parallel(
        self, targets: List[CampaignTarget]
    ) -> Tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame, pd.DataFrame]:
        """
        Execute extractors in parallel (EXPERIMENTAL).

        Note: Bloomberg API may have concurrency limits. Use with caution.
        """
        results = {}

        with ThreadPoolExecutor(max_workers=5) as executor:
            futures = {}

            # Submit all extractor jobs
            logger.info("Submitting extractor jobs to thread pool...")

            # Snapshot
            snapshot_extractor = SnapshotExtractor(self.session)
            futures["snapshot"] = executor.submit(
                snapshot_extractor.extract_for_targets, targets
            )

            # Ownership
            ownership_extractor = OwnershipExtractor(self.session)
            tickers = [t.bloomberg_ticker for t in targets]
            futures["ownership"] = executor.submit(
                ownership_extractor.extract_top_20_holders, tickers
            )

            # Events
            events_extractor = EventsExtractor(self.session)
            campaign_periods = [
                CampaignPeriod(
                    ticker=t.bloomberg_ticker,
                    company_name=t.company_name_japanese,
                    campaign_start=t.campaign_start,
                    campaign_end=t.campaign_end,
                )
                for t in targets
            ]
            futures["events"] = executor.submit(
                events_extractor.extract_for_campaigns, campaign_periods
            )

            # Price History
            price_extractor = PriceHistoryExtractor(self.session)
            price_targets = [
                PriceHistoryTarget(
                    ticker=t.bloomberg_ticker,
                    campaign_start=t.campaign_start,
                    campaign_end=t.campaign_end,
                )
                for t in targets
            ]
            futures["price"] = executor.submit(
                price_extractor.extract_for_targets, price_targets
            )

            # Peer Comps
            peer_extractor = PeerCompsExtractor(self.session)
            peer_targets = [
                PeerCompTarget(
                    ticker=t.bloomberg_ticker, company_name=t.company_name_japanese
                )
                for t in targets
            ]
            futures["peer_comps"] = executor.submit(
                peer_extractor.extract_peer_comparisons, peer_targets
            )

            # Wait for all to complete
            logger.info("Waiting for parallel extractors to complete...")
            for name, future in futures.items():
                try:
                    results[name] = future.result()
                    logger.info(f"✓ {name.capitalize()} extraction complete")
                except Exception as e:
                    logger.error(f"✗ {name.capitalize()} extraction failed: {e}")
                    results[name] = pd.DataFrame()  # Empty fallback

        return (
            results.get("snapshot", pd.DataFrame()),
            results.get("ownership", pd.DataFrame()),
            results.get("events", pd.DataFrame()),
            results.get("price", pd.DataFrame()),
            results.get("peer_comps", pd.DataFrame()),
        )

    def _validate_data_quality(self, snapshot_df: pd.DataFrame):
        """
        Validate data quality and generate report.

        Args:
            snapshot_df: Snapshot DataFrame

        Returns:
            DataQualityReport object
        """
        logger.info("Running data quality validation...")

        validator = DataValidator(logs_dir=self.logs_dir)
        quality_report = validator.validate_snapshot_data(snapshot_df)

        # Log summary
        logger.info(f"Overall Quality Score: {quality_report.overall_quality_score * 100:.1f}%")
        logger.info(
            f"Total Securities Analyzed: {quality_report.total_securities}"
        )
        logger.info(
            f"Range Violations: {len(quality_report.range_violations)}"
        )
        logger.info(
            f"Manual Review Required: {len(quality_report.recommended_manual_review)}"
        )

        if quality_report.recommended_manual_review:
            logger.warning("Securities requiring manual review:")
            for ticker in quality_report.recommended_manual_review:
                logger.warning(f"  - {ticker}")

        # Save quality report
        report_path = self.logs_dir / f"data_quality_report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
        validator.save_quality_report(quality_report, report_path)
        logger.info(f"✓ Data quality report saved: {report_path}")

        return quality_report

    def _write_excel_output(
        self,
        snapshot_df: pd.DataFrame,
        ownership_df: pd.DataFrame,
        events_df: pd.DataFrame,
        price_df: pd.DataFrame,
        peer_comps_df: pd.DataFrame,
        quality_report,
    ) -> Path:
        """
        Write Excel workbook with all data.

        Args:
            snapshot_df: Snapshot DataFrame
            ownership_df: Ownership DataFrame
            events_df: Events DataFrame
            price_df: Price history DataFrame
            peer_comps_df: Peer comparables DataFrame
            quality_report: Data quality report

        Returns:
            Path to output Excel file
        """
        logger.info("Writing Excel workbook...")

        writer = ExcelWriter()
        output_path = writer.write_activist_workbook(
            activist_name=self.config.activist_name,
            snapshot_df=snapshot_df,
            ownership_df=ownership_df,
            events_df=events_df,
            price_df=price_df,
            peer_comps_df=peer_comps_df,
            quality_report=quality_report,
            output_path=self.config.output_path,
        )

        logger.info(f"✓ Excel workbook written: {output_path}")

        return output_path

    def _print_execution_summary(self, summary: ExecutionSummary) -> None:
        """
        Print execution summary to console.

        Args:
            summary: Execution summary object
        """
        print("\n" + "=" * 80)
        print("EXECUTION SUMMARY")
        print("=" * 80)
        print(f"Total Companies:           {summary.total_companies}")
        print(f"Successful Extractions:    {summary.successful_extractions}")
        print(f"Failed Extractions:        {summary.failed_extractions}")
        print(f"Data Quality Score:        {summary.data_quality_score:.1f}%")
        print(f"Manual Review Required:    {len(summary.manual_review_flags)} securities")
        print(f"Execution Time:            {summary.execution_time_seconds:.2f} seconds")
        print(f"Output File:               {summary.output_file}")
        print("=" * 80)

        if summary.manual_review_flags:
            print("\nSecurities Requiring Manual Review:")
            for ticker in summary.manual_review_flags:
                print(f"  - {ticker}")
            print()

        logger.info("Pipeline execution complete!")


def parse_arguments() -> argparse.Namespace:
    """
    Parse command-line arguments.

    Returns:
        Parsed arguments
    """
    parser = argparse.ArgumentParser(
        description="Bloomberg Activist Data Pipeline - Orchestration Layer",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Basic usage
  python src/run_all.py \\
      --input effissimo_summary_by_company.csv \\
      --activist "Effissimo Capital Management"

  # With custom output path
  python src/run_all.py \\
      --input effissimo_summary_by_company.csv \\
      --activist "Effissimo Capital Management" \\
      --output output/effissimo_data.xlsx

  # Dry run (validate inputs only)
  python src/run_all.py \\
      --input effissimo_summary_by_company.csv \\
      --activist "Effissimo Capital Management" \\
      --dry-run

  # Enable parallel execution (EXPERIMENTAL)
  python src/run_all.py \\
      --input effissimo_summary_by_company.csv \\
      --activist "Effissimo Capital Management" \\
      --parallel

  # Debug logging
  python src/run_all.py \\
      --input effissimo_summary_by_company.csv \\
      --activist "Effissimo Capital Management" \\
      --log-level DEBUG
        """,
    )

    parser.add_argument(
        "--input",
        type=Path,
        required=True,
        help="Path to input CSV file (e.g., effissimo_summary_by_company.csv)",
    )

    parser.add_argument(
        "--activist",
        type=str,
        required=True,
        help='Name of activist investor (e.g., "Effissimo Capital Management")',
    )

    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="Path for Excel output file (default: auto-generated in output/)",
    )

    parser.add_argument(
        "--snapshot-date",
        type=lambda s: datetime.strptime(s, "%Y-%m-%d").date(),
        default=None,
        help="Override snapshot date for testing (format: YYYY-MM-DD)",
    )

    parser.add_argument(
        "--log-level",
        type=str,
        choices=["DEBUG", "INFO", "WARNING", "ERROR"],
        default="INFO",
        help="Logging verbosity level (default: INFO)",
    )

    parser.add_argument(
        "--parallel",
        action="store_true",
        help="Enable parallel execution of extractors (EXPERIMENTAL)",
    )

    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate inputs without querying Bloomberg",
    )

    return parser.parse_args()


def main() -> int:
    """
    Main entry point for CLI.

    Returns:
        Exit code (0 = success, 1 = failure)
    """
    try:
        # Parse arguments
        args = parse_arguments()

        # Create configuration
        config = ExecutionConfig(
            input_csv=args.input,
            activist_name=args.activist,
            output_path=args.output,
            snapshot_date_override=args.snapshot_date,
            log_level=args.log_level,
            enable_parallel=args.parallel,
            dry_run=args.dry_run,
        )

        # Create orchestrator and run pipeline
        orchestrator = PipelineOrchestrator(config)
        summary = orchestrator.run()

        # Check for failures
        if summary.failed_extractions > 0:
            logger.warning(
                f"Pipeline completed with {summary.failed_extractions} failed extractions"
            )
            return 1

        logger.info("Pipeline execution successful!")
        return 0

    except KeyboardInterrupt:
        logger.warning("\nPipeline execution interrupted by user")
        return 1

    except Exception as e:
        logger.error(f"Pipeline execution failed: {e}", exc_info=True)
        return 1


if __name__ == "__main__":
    sys.exit(main())
