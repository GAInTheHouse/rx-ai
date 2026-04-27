"""
setup_bigquery.py — One-time provisioning script for the rxai_eval BigQuery dataset.

Creates:
  • Dataset  : <project>.<BIGQUERY_DATASET>          (default: rxai_eval)
  • Table    : <project>.<BIGQUERY_DATASET>.<BIGQUERY_TABLE>  (default: feature_logs)

The table schema mirrors the JSONL log schema produced by eval_logger.py.
input / output columns are STRING (JSON) to keep the schema flat and avoid
BigQuery nested RECORD limitations in streaming inserts.

Usage:
    python -m eval.setup_bigquery
    python -m eval.setup_bigquery --dataset rxai_eval --table feature_logs
"""

import argparse
import os
import sys

from dotenv import load_dotenv

load_dotenv()


def main() -> None:
    parser = argparse.ArgumentParser(description="Provision rxai_eval BigQuery resources")
    parser.add_argument(
        "--dataset",
        default=os.getenv("BIGQUERY_DATASET", "rxai_eval"),
        help="BigQuery dataset name (default: rxai_eval)",
    )
    parser.add_argument(
        "--table",
        default=os.getenv("BIGQUERY_TABLE", "feature_logs"),
        help="BigQuery table name (default: feature_logs)",
    )
    parser.add_argument(
        "--location",
        default=os.getenv("GOOGLE_CLOUD_LOCATION", "US"),
        help="Dataset location (default: US)",
    )
    parser.add_argument(
        "--project",
        default=os.getenv("GOOGLE_CLOUD_PROJECT"),
        help="GCP project ID (default: GOOGLE_CLOUD_PROJECT env var)",
    )
    args = parser.parse_args()

    if not args.project:
        print(
            "ERROR: GCP project ID is required. "
            "Set GOOGLE_CLOUD_PROJECT in .env or pass --project."
        )
        sys.exit(1)

    try:
        from google.cloud import bigquery
        from google.api_core.exceptions import Conflict
    except ImportError:
        print("ERROR: google-cloud-bigquery is not installed. Run: pip install google-cloud-bigquery")
        sys.exit(1)

    client = bigquery.Client(project=args.project)
    dataset_id = f"{args.project}.{args.dataset}"
    table_id = f"{dataset_id}.{args.table}"

    # ── Dataset ──────────────────────────────────────────────────────────────
    dataset = bigquery.Dataset(dataset_id)
    dataset.location = args.location
    dataset.description = (
        "Rx-AI evaluation logs — streamed from eval_logger.py during API calls."
    )
    try:
        client.create_dataset(dataset, timeout=30)
        print(f"✓ Created dataset  {dataset_id}  (location={args.location})")
    except Conflict:
        print(f"  Dataset already exists: {dataset_id}")

    # ── Table ─────────────────────────────────────────────────────────────────
    schema = [
        bigquery.SchemaField("session_id",  "STRING",    mode="REQUIRED", description="UUID per AI call"),
        bigquery.SchemaField("feature",     "STRING",    mode="REQUIRED", description="stt | tts | image_analysis | question_generation"),
        bigquery.SchemaField("model",       "STRING",    mode="REQUIRED", description="Model or voice identifier"),
        bigquery.SchemaField("input",       "STRING",    mode="NULLABLE", description="JSON-serialised input summary"),
        bigquery.SchemaField("output",      "STRING",    mode="NULLABLE", description="JSON-serialised output summary"),
        bigquery.SchemaField("latency_ms",  "INTEGER",   mode="NULLABLE", description="Wall-clock latency in milliseconds"),
        bigquery.SchemaField("timestamp",   "TIMESTAMP", mode="NULLABLE", description="UTC timestamp of the call"),
        bigquery.SchemaField("patient_id",  "STRING",    mode="NULLABLE", description="Patient identifier"),
        bigquery.SchemaField("question_id", "STRING",    mode="NULLABLE", description="Question identifier"),
        bigquery.SchemaField("error",       "STRING",    mode="NULLABLE", description="Exception type:message on failure"),
    ]

    table = bigquery.Table(table_id, schema=schema)
    table.description = "Feature-level evaluation logs for Rx-AI API calls."

    # Partition by day on the timestamp column so queries can prune efficiently.
    table.time_partitioning = bigquery.TimePartitioning(
        type_=bigquery.TimePartitioningType.DAY,
        field="timestamp",
    )

    try:
        client.create_table(table, timeout=30)
        print(f"✓ Created table    {table_id}")
    except Conflict:
        print(f"  Table already exists: {table_id}")

    print(
        "\nSetup complete. Add these to your .env:\n"
        f"  BIGQUERY_DATASET={args.dataset}\n"
        f"  BIGQUERY_TABLE={args.table}\n"
        f"  GOOGLE_CLOUD_PROJECT={args.project}\n"
    )


if __name__ == "__main__":
    main()
