"""
Example: Using BatchingEngine for Bloomberg Data Extraction

This script demonstrates the complete workflow for using the batching engine
to efficiently extract data from Bloomberg Terminal for multiple securities.

Workflow:
    1. Initialize Bloomberg session and batching engine
    2. Group fields by override type (prevent mixed override requests)
    3. Create batches respecting size limits
    4. Execute batches with rate limiting and retry logic
    5. Combine results into final DataFrame

Usage:
    python examples/example_batching_engine.py

Requirements:
    - Bloomberg Terminal running and logged in
    - blpapi package installed
    - config/bloomberg_fields.yaml present
"""

import sys
from datetime import date
from pathlib import Path

# Add src to path
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

from batching_engine import BatchingEngine
from bloomberg_session import BloombergSession


def example_basic_batching():
    """Example 1: Basic batching with single field group."""
    print("=" * 80)
    print("Example 1: Basic Batching with Single Field Group")
    print("=" * 80)

    # Initialize batching engine
    engine = BatchingEngine(
        max_batch_size=10,  # Conservative batch size
        min_delay_seconds=2.0,  # Bloomberg recommendation
        max_retries=3,
    )

    # Securities to query (subset of Effissimo companies)
    securities = [
        "9107 JP Equity",  # Kawasaki Kisen
        "7157 JP Equity",  # Lifenet Insurance
        "6707 JP Equity",  # Sanken Electric
        "7752 JP Equity",  # Ricoh
        "6502 JP Equity",  # Toshiba
    ]

    # Fields to retrieve (all END_DT_OVERRIDE type)
    fields = [
        "PX_TO_BOOK_RATIO",
        "PE_RATIO",
        "CUR_MKT_CAP",
        "EQY_DVD_YLD_IND",
    ]

    # Create batches
    batches = engine.create_batches(securities, fields)

    print(f"\nCreated {len(batches)} batch(es):")
    for batch in batches:
        print(f"  - {batch.batch_id}: {len(batch.securities)} securities, "
              f"{len(batch.fields)} fields, override_type={batch.override_type}")

    # Execute with Bloomberg session (commented out - requires Terminal)
    # with BloombergSession() as session:
    #     result_df = engine.execute_batches_sequential(
    #         session,
    #         batches,
    #         overrides={"END_DT_OVERRIDE": "20210331"}  # March 31, 2021 snapshot
    #     )
    #     print(f"\nRetrieved {len(result_df)} records")
    #     print(result_df.head())

    print("\n✓ Batch creation successful")


def example_field_grouping():
    """Example 2: Automatic field grouping by override type."""
    print("\n" + "=" * 80)
    print("Example 2: Field Grouping by Override Type")
    print("=" * 80)

    engine = BatchingEngine()

    # Mixed fields from different override groups
    all_fields = [
        # END_DT_OVERRIDE fields
        "PX_TO_BOOK_RATIO",
        "PE_RATIO",
        "CUR_MKT_CAP",
        # FUND_PER fields
        "RETURN_COM_EQY",
        "RETURN_ON_ASSET",
        "OPER_MARGIN",
        # 'none' type fields
        "FISCAL_YEAR_END_MONTH_DE",
    ]

    # Group fields by override type
    grouped_fields = engine.group_fields_by_override(all_fields)

    print(f"\nGrouped {len(all_fields)} fields into {len(grouped_fields)} groups:")
    for override_type, fields in grouped_fields.items():
        print(f"\n  {override_type}:")
        for field in fields:
            print(f"    - {field}")

    print("\n✓ Field grouping successful")


def example_multi_group_workflow():
    """Example 3: Complete workflow with multiple field groups."""
    print("\n" + "=" * 80)
    print("Example 3: Complete Multi-Group Workflow")
    print("=" * 80)

    engine = BatchingEngine(max_batch_size=10)

    securities = [
        "9107 JP Equity",
        "7157 JP Equity",
        "6707 JP Equity",
    ]

    # Mixed fields requiring different overrides
    all_fields = [
        "PX_TO_BOOK_RATIO",  # END_DT_OVERRIDE
        "RETURN_COM_EQY",  # FUND_PER
        "FISCAL_YEAR_END_MONTH_DE",  # none
    ]

    # Step 1: Group fields by override type
    grouped_fields = engine.group_fields_by_override(all_fields)

    print(f"\nProcessing {len(securities)} securities with {len(all_fields)} fields")
    print(f"Grouped into {len(grouped_fields)} field groups\n")

    # Step 2: Create batches for each field group
    all_batches = []
    for override_type, fields in grouped_fields.items():
        batches = engine.create_batches(securities, fields)
        all_batches.extend(batches)
        print(f"{override_type}: {len(batches)} batch(es)")

    # Step 3: Define override values
    overrides = {
        "END_DT_OVERRIDE": "20210331",  # March 31, 2021 snapshot
        "FUND_PER": "FY2021",  # Fiscal year 2021
        # 'none' type doesn't need override
    }

    print(f"\nTotal batches to execute: {len(all_batches)}")

    # Step 4: Execute batches (commented out - requires Terminal)
    # with BloombergSession() as session:
    #     # Can use parallel or sequential execution
    #     result_df = engine.execute_batches_parallel(
    #         session,
    #         all_batches,
    #         overrides,
    #         max_workers=3
    #     )
    #     print(f"\nRetrieved {len(result_df)} total records")

    print("\n✓ Multi-group workflow setup successful")


def example_large_batch():
    """Example 4: Batching large security list (all 30 Effissimo companies)."""
    print("\n" + "=" * 80)
    print("Example 4: Large Batch (30 Effissimo Companies)")
    print("=" * 80)

    engine = BatchingEngine(max_batch_size=10)

    # All 30 Effissimo target companies
    effissimo_securities = [
        "9107 JP Equity", "7157 JP Equity", "6707 JP Equity", "5741 JP Equity",
        "1813 JP Equity", "1786 JP Equity", "3104 JP Equity", "5449 JP Equity",
        "4047 JP Equity", "7740 JP Equity", "7222 JP Equity", "6246 JP Equity",
        "7752 JP Equity", "4551 JP Equity", "4980 JP Equity", "7122 JP Equity",
        "7250 JP Equity", "8750 JP Equity", "3401 JP Equity", "5541 JP Equity",
        "9742 JP Equity", "6676 JP Equity", "6502 JP Equity", "4902 JP Equity",
        "1737 JP Equity", "7545 JP Equity", "9640 JP Equity", "4464 JP Equity",
        "8013 JP Equity", "6676 JP Equity",
    ]

    fields = ["PX_TO_BOOK_RATIO", "RETURN_COM_EQY", "CUR_MKT_CAP"]

    # Group fields first
    grouped_fields = engine.group_fields_by_override(fields)

    print(f"\nProcessing {len(effissimo_securities)} Effissimo companies")
    print(f"Fields grouped into: {list(grouped_fields.keys())}\n")

    total_batches = 0
    for override_type, field_list in grouped_fields.items():
        batches = engine.create_batches(effissimo_securities, field_list)
        total_batches += len(batches)
        print(f"{override_type}: {len(field_list)} field(s), {len(batches)} batch(es)")

    print(f"\nTotal batches: {total_batches}")
    print("Estimated execution time (with 2s rate limit): "
          f"{total_batches * 2:.0f} seconds")

    print("\n✓ Large batch setup successful")


def example_rate_limiting():
    """Example 5: Rate limiting and statistics tracking."""
    print("\n" + "=" * 80)
    print("Example 5: Rate Limiting and Statistics")
    print("=" * 80)

    engine = BatchingEngine(
        max_batch_size=20,
        min_delay_seconds=2.0,
        max_retries=3,
    )

    # Check initial statistics
    stats = engine.get_statistics()
    print("\nInitial statistics:")
    print(f"  Max batch size: {stats['max_batch_size']}")
    print(f"  Min interval: {stats['min_interval_seconds']}s")
    print(f"  Batches executed: {stats['total_batches_executed']}")
    print(f"  Total retries: {stats['total_retries']}")
    print(f"  Total failures: {stats['total_failures']}")
    print(f"  Success rate: {stats['success_rate']:.1%}")

    # After execution, you can check updated statistics:
    # stats = engine.get_statistics()
    # print(f"\nPost-execution statistics:")
    # print(f"  Batches executed: {stats['total_batches_executed']}")
    # print(f"  Success rate: {stats['success_rate']:.1%}")
    # print(f"  Retry rate: {stats['retry_rate']:.2f}")

    print("\n✓ Rate limiting configuration verified")


def example_field_validation():
    """Example 6: Field validation before batching."""
    print("\n" + "=" * 80)
    print("Example 6: Field Validation")
    print("=" * 80)

    engine = BatchingEngine()

    # Mix of valid and invalid field names
    fields_to_validate = [
        "PX_TO_BOOK_RATIO",  # Valid
        "RETURN_COM_EQY",  # Valid
        "INVALID_FIELD_1",  # Invalid
        "CUR_MKT_CAP",  # Valid
        "UNKNOWN_FIELD_XYZ",  # Invalid
    ]

    valid, invalid = engine.field_manager.validate_fields(fields_to_validate)

    print(f"\nValidated {len(fields_to_validate)} fields:")
    print(f"\n  Valid ({len(valid)}):")
    for field in valid:
        override_type = engine.field_manager.get_override_type(field)
        print(f"    - {field} (override: {override_type})")

    if invalid:
        print(f"\n  Invalid ({len(invalid)}):")
        for field in invalid:
            print(f"    - {field}")
        print("\n  ⚠ Warning: Invalid fields will return null values from Bloomberg")
    else:
        print("\n  ✓ All fields valid")


if __name__ == "__main__":
    print("\n" + "=" * 80)
    print("Bloomberg Batching Engine - Usage Examples")
    print("=" * 80)
    print("\nThese examples demonstrate batching engine features.")
    print("Bloomberg Terminal connection is mocked for demonstration.\n")

    # Run all examples
    example_basic_batching()
    example_field_grouping()
    example_multi_group_workflow()
    example_large_batch()
    example_rate_limiting()
    example_field_validation()

    print("\n" + "=" * 80)
    print("All examples completed successfully!")
    print("=" * 80)
    print("\nTo execute with live Bloomberg Terminal:")
    print("  1. Ensure Terminal is running and logged in")
    print("  2. Uncomment the session execution blocks in examples")
    print("  3. Run: python examples/example_batching_engine.py")
    print("=" * 80 + "\n")
