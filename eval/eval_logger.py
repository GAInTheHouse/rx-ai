"""
eval_logger.py — Async context manager for logging every AI feature call.

Each call produces one JSONL line written to eval/logs/<date>.jsonl.
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

import json
import os
import time
import uuid
import aiofiles
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import AsyncGenerator, Optional

_LOG_DIR = Path(os.getenv("EVAL_LOG_DIR", "eval/logs"))


def _log_path() -> Path:
    _LOG_DIR.mkdir(parents=True, exist_ok=True)
    date_str = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return _LOG_DIR / f"{date_str}.jsonl"


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
    log entry to eval/logs/<today>.jsonl when the block exits (success or error).

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
        try:
            async with aiofiles.open(_log_path(), mode="a") as f:
                await f.write(json.dumps(entry) + "\n")
        except Exception as log_exc:
            # Never let logging failures propagate into the API response
            print(f"[eval_logger] Failed to write log entry: {log_exc}")
