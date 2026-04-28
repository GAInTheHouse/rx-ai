"""
eval/run_workflow_evals.py — Workflow-combination evaluation runner.

This script produces eval/reports/workflows.json by default.

It supports two data sources:
  1) JSONL logs under eval/logs/ (default)
  2) BigQuery table streaming sink (when --source bigquery)

Workflow correlation:
  - The API supports a client-supplied workflow id header:
      X-RxAI-Workflow-Id: <uuid>
  - The API injects this into each log entry under entry["input"]["workflow_id"].
  - This runner groups calls by workflow_id and evaluates "mixed feature usage"
    by checking which features appear within the same workflow.

Important limitation:
  - Older logs without workflow_id cannot be grouped into workflows reliably.
"""

from __future__ import annotations

import argparse
import json
import os
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_REPO_ROOT = Path(__file__).resolve().parent.parent
_REPORTS_DIR = Path(__file__).resolve().parent / "reports"
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


def _default_log_dir() -> Path:
    env_log_dir = os.getenv("EVAL_LOG_DIR", "").strip()
    if env_log_dir:
        raw = Path(env_log_dir)
        return raw if raw.is_absolute() else _REPO_ROOT / raw
    return _REPO_ROOT / "eval" / "logs"


def load_jsonl(path: Path) -> list[dict]:
    entries: list[dict] = []
    if path.is_file():
        files = [path]
    else:
        files = sorted(path.glob("*.jsonl")) if path.is_dir() else []
    for f in files:
        try:
            with open(f) as fh:
                for line in fh:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
        except FileNotFoundError:
            pass
    return entries


def load_bigquery_entries(limit: int = 5000) -> list[dict]:
    """
    Pull recent entries from BigQuery.

    Requires:
      - GOOGLE_APPLICATION_CREDENTIALS
      - GOOGLE_CLOUD_PROJECT
      - BIGQUERY_DATASET
      - BIGQUERY_TABLE (optional)
    """
    dataset = os.getenv("BIGQUERY_DATASET", "").strip()
    table = os.getenv("BIGQUERY_TABLE", "feature_logs").strip()
    project = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip()

    if not (dataset and project):
        raise RuntimeError("BIGQUERY_DATASET and GOOGLE_CLOUD_PROJECT must be set for BigQuery source.")

    from google.cloud import bigquery  # noqa: PLC0415

    client = bigquery.Client(project=project)
    table_ref = f"{client.project}.{dataset}.{table}"

    query = f"""
    SELECT
      session_id,
      feature,
      model,
      input,
      output,
      latency_ms,
      CAST(timestamp AS STRING) AS timestamp,
      patient_id,
      question_id,
      error
    FROM `{table_ref}`
    ORDER BY timestamp DESC
    LIMIT @lim
    """

    job_config = bigquery.QueryJobConfig(
        query_parameters=[bigquery.ScalarQueryParameter("lim", "INT64", int(limit))]
    )
    results = client.query(query, job_config=job_config).result()

    entries: list[dict] = []
    for row in results:
        try:
            input_obj = json.loads(row["input"]) if row["input"] else {}
        except Exception:
            input_obj = {"_raw": row["input"]}
        try:
            output_obj = json.loads(row["output"]) if row["output"] else {}
        except Exception:
            output_obj = {"_raw": row["output"]}

        entries.append(
            {
                "session_id": row["session_id"],
                "feature": row["feature"],
                "model": row["model"],
                "input": input_obj,
                "output": output_obj,
                "latency_ms": row["latency_ms"],
                "timestamp": row["timestamp"],
                "patient_id": row["patient_id"],
                "question_id": row["question_id"],
                "error": row["error"],
            }
        )
    return entries


def group_by_workflow(entries: list[dict]) -> dict[str, list[dict]]:
    grouped: dict[str, list[dict]] = defaultdict(list)
    for e in entries:
        wf = (e.get("input") or {}).get("workflow_id")
        if not wf:
            continue
        grouped[str(wf)].append(e)
    return grouped


def workflow_summary(grouped: dict[str, list[dict]]) -> dict[str, Any]:
    feature_sets: list[frozenset[str]] = []
    per_workflow: list[dict[str, Any]] = []

    for wf_id, calls in grouped.items():
        features = sorted({c.get("feature") for c in calls if c.get("feature")})
        feature_sets.append(frozenset(features))
        per_workflow.append(
            {
                "workflow_id": wf_id,
                "feature_set": features,
                "call_count": len(calls),
                "error_count": sum(1 for c in calls if c.get("error")),
                "patients": sorted({c.get("patient_id") for c in calls if c.get("patient_id")}),
            }
        )

    set_counts = Counter(feature_sets)
    combos = [
        {"features": sorted(list(fs)), "count": cnt}
        for fs, cnt in sorted(set_counts.items(), key=lambda x: x[1], reverse=True)
    ]

    return {
        "workflow_count": len(grouped),
        "combination_counts": combos,
        "sample_workflows": per_workflow[:20],
    }


def endpoint_hardening_checks(entries: list[dict]) -> dict[str, Any]:
    """
    Endpoint hardening: check for common failure modes and quantify them.
    """
    stt = [e for e in entries if e.get("feature") == "stt"]
    tts = [e for e in entries if e.get("feature") == "tts"]
    img = [e for e in entries if e.get("feature") == "image_analysis"]

    stt_low_conf = 0
    stt_total_ok = 0
    for e in stt:
        if e.get("error"):
            continue
        out = e.get("output") or {}
        conf = out.get("confidence")
        transcript = out.get("transcript") or ""
        if transcript and conf is not None:
            stt_total_ok += 1
            try:
                if float(conf) < 0.7:
                    stt_low_conf += 1
            except Exception:
                pass

    return {
        "stt": {
            "count": len(stt),
            "error_count": sum(1 for e in stt if e.get("error")),
            "low_confidence_count": stt_low_conf,
            "low_confidence_rate": round(stt_low_conf / max(stt_total_ok, 1), 3),
            "note": "low_confidence_rate computed over successful STT calls with non-empty transcripts",
        },
        "tts": {
            "count": len(tts),
            "error_count": sum(1 for e in tts if e.get("error")),
        },
        "image_analysis": {
            "count": len(img),
            "error_count": sum(1 for e in img if e.get("error")),
        },
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="Workflow evaluation runner")
    parser.add_argument(
        "--source",
        choices=["jsonl", "bigquery"],
        default="jsonl",
        help="Log source (default: jsonl)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=_default_log_dir(),
        help="Directory containing JSONL logs (default: eval/logs/)",
    )
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Specific JSONL log file (overrides --log-dir)",
    )
    parser.add_argument(
        "--bq-limit",
        type=int,
        default=5000,
        help="Max rows to fetch from BigQuery (default: 5000)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_REPORTS_DIR / "workflows.json",
        help="Output report path (default: eval/reports/workflows.json)",
    )
    args = parser.parse_args()

    if args.source == "bigquery":
        entries = load_bigquery_entries(limit=args.bq_limit)
        source_meta = {"type": "bigquery", "limit": args.bq_limit}
    else:
        log_path = args.log if args.log else args.log_dir
        entries = load_jsonl(log_path)
        source_meta = {"type": "jsonl", "path": str(log_path)}

    grouped = group_by_workflow(entries)
    summary = workflow_summary(grouped)
    hardening = endpoint_hardening_checks(entries)

    report: dict[str, Any] = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "source": source_meta,
        "total_entries": len(entries),
        "workflows": summary,
        "hardening_checks": hardening,
        "notes": [
            "Workflows are grouped by input.workflow_id. Ensure the client sends X-RxAI-Workflow-Id.",
            "If you have no workflows, run the frontend and make calls that hit STT/TTS/image/question-generation within the same workflow.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as fh:
        json.dump(report, fh, indent=2)

    print(f"[run_workflow_evals] Wrote report → {args.output}")
    print(f"[run_workflow_evals] Total entries: {len(entries)} | Workflows: {summary['workflow_count']}")


if __name__ == "__main__":
    main()

