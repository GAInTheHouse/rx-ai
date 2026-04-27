"""
eval_logger.py — Async context manager for logging every AI feature call.

Each call produces one JSONL line written to eval/logs/<date>.jsonl.
When BIGQUERY_DATASET is set the same entry is also streamed to BigQuery via
the streaming insert API (table: <BIGQUERY_DATASET>.<BIGQUERY_TABLE>).

Schema:
    session_id    : str   — unique per call (UUID4)
    feature       : str   — "stt" | "tts" | "image_analysis" | "question_generation"
    model         : str   — model/voice identifier used
    input         : dict  — lightweight summary of inputs (never raw audio bytes)
    output        : dict  — lightweight summary of outputs
    latency_ms    : int   — wall-clock time from context entry to exit
    timestamp     : str   — ISO 8601 UTC
    patient_id    : str?  — if available from the request
    question_id   : str?  — if available from the request
    error         : str?  — exception type + message on failure

Usage:
    async with log_ai_call(
        feature="stt",
        input_data={"audio_bytes": len(raw), "content_type": "audio/webm"},
        model="chirp_2",
        patient_id="P001",
    ) as output:
        result = call_stt(raw)
        output.update({"transcript": result.transcript, "confidence": result.confidence})
    # log entry is written automatically on context exit, even on exception
"""

import asyncio
import json
import os
import time
import uuid
import aiofiles
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

# ─────────────────────────────────────────────
# JSONL log directory
# ─────────────────────────────────────────────

# Anchor the log directory to the repo root so it is stable regardless of the
# working directory used to launch the server (uvicorn, systemd, etc.).
_REPO_ROOT = Path(__file__).resolve().parent.parent
_env_log_dir = os.getenv("EVAL_LOG_DIR", "")
if _env_log_dir:
    _raw = Path(_env_log_dir)
    _LOG_DIR = _raw if _raw.is_absolute() else _REPO_ROOT / _raw
else:
    _LOG_DIR = _REPO_ROOT / "eval" / "logs"

_write_lock = asyncio.Lock()


def _log_path() -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _LOG_DIR / f"{date_str}.jsonl"


# ─────────────────────────────────────────────
# BigQuery streaming sink (optional)
# ─────────────────────────────────────────────

_BQ_DATASET: Optional[str] = os.getenv("BIGQUERY_DATASET", "").strip() or None
_BQ_TABLE: str = os.getenv("BIGQUERY_TABLE", "feature_logs").strip()
_BQ_PROJECT: Optional[str] = os.getenv("GOOGLE_CLOUD_PROJECT", "").strip() or None

# Lazily initialised BigQuery client — only created if BQ streaming is enabled.
_bq_client = None
_bq_table_ref: Optional[str] = None


def _get_bq_client():
    """Return a cached BigQuery client, creating it on first call."""
    global _bq_client, _bq_table_ref
    if _bq_client is None:
        try:
            from google.cloud import bigquery  # noqa: PLC0415
            _bq_client = bigquery.Client(project=_BQ_PROJECT)
            _bq_table_ref = f"{_BQ_PROJECT}.{_BQ_DATASET}.{_BQ_TABLE}"
            print(
                f"[eval_logger] BigQuery streaming enabled → {_bq_table_ref}"
            )
        except Exception as exc:
            print(f"[eval_logger] BigQuery client init failed: {exc}")
            _bq_client = False  # sentinel: don't retry
    return _bq_client if _bq_client is not False else None


def _entry_to_bq_row(entry: dict) -> dict:
    """
    Convert a log entry to a BigQuery-compatible row dict.
    input / output dicts are serialised to JSON strings because BigQuery
    streaming inserts do not support nested RECORD fields in this path.
    """
    return {
        "session_id": entry["session_id"],
        "feature": entry["feature"],
        "model": entry["model"],
        "input": json.dumps(entry.get("input") or {}),
        "output": json.dumps(entry.get("output") or {}),
        "latency_ms": entry["latency_ms"],
        "timestamp": entry["timestamp"],
        "patient_id": entry.get("patient_id"),
        "question_id": entry.get("question_id"),
        "error": entry.get("error"),
    }


async def _stream_to_bigquery(entry: dict) -> None:
    """Fire-and-forget BigQuery streaming insert (runs in thread pool)."""
    if not _BQ_DATASET:
        return
    client = _get_bq_client()
    if client is None:
        return

    row = _entry_to_bq_row(entry)

    def _insert():
        errors = client.insert_rows_json(_bq_table_ref, [row])
        if errors:
            print(f"[eval_logger] BigQuery insert errors: {errors}")

    try:
        await asyncio.to_thread(_insert)
    except Exception as exc:
        # Never let BQ errors propagate into the API response
        print(f"[eval_logger] BigQuery streaming failed: {exc}")


# ─────────────────────────────────────────────
# Public context manager
# ─────────────────────────────────────────────

@asynccontextmanager
async def log_ai_call(
    feature: str,
    input_data: dict,
    model: str,
    patient_id: Optional[str] = None,
    question_id: Optional[str] = None,
) -> AsyncGenerator[dict, None]:
    """
    Async context manager that times the enclosed block and appends a JSONL
    log entry to eval/logs/<today>.jsonl when the block exits (success or
    error).  If BIGQUERY_DATASET is configured the same entry is also streamed
    to BigQuery.

    Yields a mutable dict (`output`) — callers should populate it with the
    relevant output fields before the block exits so they appear in the log.
    """
    start = time.monotonic()
    output: dict = {}
    error: Optional[str] = None

    try:
        yield output
    except Exception as exc:
        error = type(exc).__name__ + ": " + str(exc)
        raise
    finally:
        elapsed_ms = int((time.monotonic() - start) * 1000)
        entry = {
            "session_id": str(uuid.uuid4()),
            "feature": feature,
            "model": model,
            "input": input_data,
            "output": output,
            "latency_ms": elapsed_ms,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "patient_id": patient_id,
            "question_id": question_id,
            "error": error,
        }

        # 1 — JSONL (always)
        try:
            async with _write_lock:
                async with aiofiles.open(_log_path(), mode="a") as f:
                    await f.write(json.dumps(entry) + "\n")
        except Exception as log_exc:
            print(f"[eval_logger] Failed to write JSONL log entry: {log_exc}")

        # 2 — BigQuery (when configured)
        if _BQ_DATASET:
            await _stream_to_bigquery(entry)
