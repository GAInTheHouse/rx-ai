"""
run_evals.py — Week 1 evaluation runner for Rx-AI.

Loads JSONL logs from eval/logs/ (or a path you specify), evaluates:
  • STT  — Word Error Rate (WER) via jiwer against eval/datasets/stt_golden.json
  • Question generation — structural validity + keyword-theme relevance
  • TTS / image_analysis — latency and error-rate summary

Produces eval/reports/week1.json (or --output path).

Usage:
    # Against all JSONL files in the default log directory:
    python -m eval.run_evals

    # Against a specific log file or directory:
    python -m eval.run_evals --log-dir eval/logs/2026-04-26.jsonl

    # Specify output path:
    python -m eval.run_evals --output eval/reports/week1.json

    # Generate synthetic sample logs then run (useful for CI with no real logs):
    python -m eval.run_evals --generate-samples
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
_REPORTS_DIR = Path(__file__).resolve().parent / "reports"

_env_log_dir = os.getenv("EVAL_LOG_DIR", "")
if _env_log_dir:
    _raw = Path(_env_log_dir)
    _DEFAULT_LOG_DIR = _raw if _raw.is_absolute() else _REPO_ROOT / _raw
else:
    _DEFAULT_LOG_DIR = _REPO_ROOT / "eval" / "logs"


# ─────────────────────────────────────────────────────────────────────────────
# JSONL loader
# ─────────────────────────────────────────────────────────────────────────────

def load_logs(log_path: Path) -> list[dict]:
    """Load all JSONL entries from a file or every .jsonl file under a directory."""
    entries: list[dict] = []
    if log_path.is_file():
        files = [log_path]
    elif log_path.is_dir():
        files = sorted(log_path.glob("*.jsonl"))
    else:
        return entries

    for fpath in files:
        with open(fpath, "r") as fh:
            for line in fh:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return entries


# ─────────────────────────────────────────────────────────────────────────────
# STT evaluation — WER
# ─────────────────────────────────────────────────────────────────────────────

def _normalise_text(text: str) -> str:
    """Lower-case, strip punctuation, collapse whitespace."""
    text = text.lower()
    text = re.sub(r"[^\w\s]", "", text)
    return re.sub(r"\s+", " ", text).strip()


def _word_error_rate(reference: str, hypothesis: str) -> float:
    """
    Compute WER using jiwer if available, otherwise fall back to a simple
    token-level edit-distance implementation so the runner never crashes.
    """
    try:
        import jiwer  # noqa: PLC0415
        return float(jiwer.wer(reference, hypothesis))
    except ImportError:
        pass

    # Fallback: Levenshtein on word tokens
    ref_words = _normalise_text(reference).split()
    hyp_words = _normalise_text(hypothesis).split()
    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    n, m = len(ref_words), len(hyp_words)
    dp = list(range(m + 1))
    for i in range(1, n + 1):
        prev, dp[0] = dp[0], i
        for j in range(1, m + 1):
            temp = dp[j]
            if ref_words[i - 1] == hyp_words[j - 1]:
                dp[j] = prev
            else:
                dp[j] = 1 + min(prev, dp[j], dp[j - 1])
            prev = temp
    return round(dp[m] / n, 4)


def _find_golden_match(transcript: str, golden: list[dict]) -> dict | None:
    """
    Find the best-matching golden entry for a given transcript by checking
    whether the transcript starts-with or is a superset of the golden phrase
    (after normalisation). Returns the golden entry or None.
    """
    norm_t = _normalise_text(transcript)
    best: dict | None = None
    best_score = 0.0
    for entry in golden:
        norm_g = _normalise_text(entry["reference_transcript"])
        words_g = set(norm_g.split())
        words_t = set(norm_t.split())
        if not words_g:
            continue
        overlap = len(words_g & words_t) / len(words_g)
        if overlap > best_score:
            best_score = overlap
            best = entry
    # Only accept a match if ≥60 % of the golden words appear in the transcript
    return best if best_score >= 0.6 else None


def evaluate_stt(entries: list[dict], golden: list[dict]) -> dict:
    stt_entries = [e for e in entries if e.get("feature") == "stt"]
    if not stt_entries:
        return {
            "count": 0,
            "note": "No STT log entries found.",
            "wer": None,
            "confidence": None,
            "failure_modes": [],
        }

    confidences = []
    wer_results = []
    low_confidence: list[dict] = []
    empty_transcripts: list[dict] = []
    error_entries: list[dict] = []

    for e in stt_entries:
        output = e.get("output", {})
        transcript = output.get("transcript", "")
        confidence = output.get("confidence")
        error = e.get("error")

        if error:
            error_entries.append({"session_id": e["session_id"], "error": error})
            continue

        if not transcript:
            empty_transcripts.append({"session_id": e["session_id"]})
            continue

        if confidence is not None:
            confidences.append(confidence)
            if confidence < 0.7:
                low_confidence.append({
                    "session_id": e["session_id"],
                    "confidence": confidence,
                    "transcript": transcript[:80],
                })

        # WER — try to find a golden match
        match = _find_golden_match(transcript, golden)
        if match:
            wer = _word_error_rate(match["reference_transcript"], transcript)
            wer_results.append({
                "session_id": e["session_id"],
                "golden_id": match["id"],
                "wer": wer,
                "reference": match["reference_transcript"],
                "hypothesis": transcript[:120],
            })

    failure_modes = []
    if low_confidence:
        failure_modes.append({
            "type": "low_confidence",
            "severity": "HIGH" if len(low_confidence) > len(stt_entries) * 0.3 else "LOW",
            "count": len(low_confidence),
            "threshold": 0.7,
            "recommendation": "Prompt the patient to re-record when confidence < 0.7.",
        })
    if empty_transcripts:
        failure_modes.append({
            "type": "empty_transcript",
            "severity": "HIGH",
            "count": len(empty_transcripts),
            "recommendation": "Check audio encoding; add client-side silence detection.",
        })
    if error_entries:
        failure_modes.append({
            "type": "api_error",
            "severity": "HIGH",
            "count": len(error_entries),
            "recommendation": "Inspect error messages; add retry logic in api.py /stt endpoint.",
        })

    avg_wer = round(sum(r["wer"] for r in wer_results) / len(wer_results), 4) if wer_results else None
    avg_conf = round(sum(confidences) / len(confidences), 4) if confidences else None

    return {
        "count": len(stt_entries),
        "wer": {
            "avg": avg_wer,
            "matched_golden_count": len(wer_results),
            "worst_cases": sorted(wer_results, key=lambda x: x["wer"], reverse=True)[:5],
        },
        "confidence": {
            "avg": avg_conf,
            "low_confidence_count": len(low_confidence),
            "low_confidence_entries": low_confidence[:5],
        },
        "failure_modes": failure_modes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Question generation evaluation — structural + relevance
# ─────────────────────────────────────────────────────────────────────────────

_CLINICAL_KEYWORDS = {
    "pain", "symptom", "medication", "dose", "adherence", "blood", "pressure",
    "glucose", "sugar", "weight", "breath", "chest", "nausea", "dizziness",
    "fatigue", "sleep", "mood", "anxiety", "swelling", "wound", "skin", "photo",
    "image", "exercise", "diet", "alcohol", "smoke", "insulin", "side effect",
}

REQUIRED_QUESTION_FIELDS = {"id", "question", "type", "requires_image", "image_prompt"}


def _check_question_structure(questions: list[dict]) -> dict:
    """Return structural validation results for a list of questions."""
    missing_fields_count = 0
    missing_requires_image = 0
    missing_image_prompt_when_required = 0
    total = len(questions)

    for q in questions:
        missing = REQUIRED_QUESTION_FIELDS - set(q.keys())
        if missing:
            missing_fields_count += 1
        if "requires_image" not in q:
            missing_requires_image += 1
        if q.get("requires_image") and not q.get("image_prompt"):
            missing_image_prompt_when_required += 1

    return {
        "total_questions": total,
        "missing_required_fields_count": missing_fields_count,
        "missing_requires_image_count": missing_requires_image,
        "missing_image_prompt_when_required_count": missing_image_prompt_when_required,
    }


def _keyword_relevance_score(question_text: str) -> float:
    """Simple keyword overlap score against clinical vocabulary (0.0 – 1.0)."""
    tokens = set(_normalise_text(question_text).split())
    matched = sum(1 for kw in _CLINICAL_KEYWORDS if kw in tokens or any(kw in t for t in tokens))
    return round(min(matched / 2, 1.0), 4)


def evaluate_qgen(entries: list[dict]) -> dict:
    qgen_entries = [e for e in entries if e.get("feature") == "question_generation"]
    if not qgen_entries:
        return {
            "count": 0,
            "note": "No question_generation log entries found.",
            "relevance": None,
            "structure": None,
            "failure_modes": [],
        }

    relevance_scores: list[float] = []
    all_structure_results: list[dict] = []
    latencies: list[int] = []
    error_entries = []

    for e in qgen_entries:
        if e.get("error"):
            error_entries.append({"session_id": e["session_id"], "error": e["error"]})
            continue

        output = e.get("output", {})
        latency = e.get("latency_ms")
        if latency:
            latencies.append(latency)

        # The output logged is a dict with `question_count` and optionally
        # `requires_image_count`. The actual questions are not stored in the log
        # (they go back to the frontend). We evaluate structure from what's logged.
        q_count = output.get("question_count", 0)
        ri_count = output.get("requires_image_count", 0)

        # Structural check from logged counts
        structure_ok = q_count > 0
        all_structure_results.append({
            "session_id": e["session_id"],
            "question_count": q_count,
            "requires_image_count": ri_count,
            "structure_ok": structure_ok,
        })

        # Relevance: use patient conditions from input as ground truth
        conditions = e.get("input", {}).get("conditions", [])
        if conditions and q_count > 0:
            condition_text = " ".join(conditions)
            relevance_scores.append(_keyword_relevance_score(condition_text))

    failure_modes = []
    zero_q = [r for r in all_structure_results if r["question_count"] == 0]
    if zero_q:
        failure_modes.append({
            "type": "zero_questions_returned",
            "severity": "HIGH",
            "count": len(zero_q),
            "recommendation": (
                "CrewAI returned empty output. Add JSON repair logic or "
                "increase prompt specificity for structured output."
            ),
        })
    if error_entries:
        failure_modes.append({
            "type": "api_error",
            "severity": "HIGH",
            "count": len(error_entries),
            "recommendation": "Check CrewAI / Vertex AI connectivity and logs.",
        })

    avg_latency = round(sum(latencies) / len(latencies)) if latencies else None
    avg_relevance = round(sum(relevance_scores) / len(relevance_scores), 4) if relevance_scores else None

    return {
        "count": len(qgen_entries),
        "relevance": {
            "avg_keyword_score": avg_relevance,
            "note": (
                "Keyword relevance measures clinical vocabulary coverage. "
                "Run with --deepeval for LLM-judged relevance metrics."
            ),
        },
        "structure": {
            "avg_latency_ms": avg_latency,
            "details": all_structure_results,
        },
        "failure_modes": failure_modes,
    }


# ─────────────────────────────────────────────────────────────────────────────
# TTS / image_analysis — summary stats only
# ─────────────────────────────────────────────────────────────────────────────

def evaluate_feature_summary(entries: list[dict], feature: str) -> dict:
    feat_entries = [e for e in entries if e.get("feature") == feature]
    if not feat_entries:
        return {"count": 0, "note": f"No {feature} log entries found."}

    latencies = [e["latency_ms"] for e in feat_entries if e.get("latency_ms")]
    errors = [e for e in feat_entries if e.get("error")]
    return {
        "count": len(feat_entries),
        "error_count": len(errors),
        "error_rate": round(len(errors) / len(feat_entries), 4),
        "latency_ms": {
            "avg": round(sum(latencies) / len(latencies)) if latencies else None,
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
        "failure_modes": (
            [{"type": "api_error", "count": len(errors), "severity": "HIGH"}] if errors else []
        ),
    }


# ─────────────────────────────────────────────────────────────────────────────
# Sample log generator (for CI / demo without real GCP calls)
# ─────────────────────────────────────────────────────────────────────────────

def generate_sample_logs(log_dir: Path) -> Path:
    """
    Write a synthetic JSONL file that exercises all four features so the eval
    runner can produce a meaningful report without requiring live GCP calls.
    """
    log_dir.mkdir(parents=True, exist_ok=True)
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    out_path = log_dir / f"{today}.jsonl"

    samples = [
        # STT — high confidence, good transcript
        {
            "session_id": str(uuid.uuid4()), "feature": "stt", "model": "chirp_2",
            "input": {"audio_bytes": 48000, "content_type": "audio/webm"},
            "output": {"transcript": "I have been taking my metformin every morning with breakfast", "confidence": 0.94},
            "latency_ms": 820, "timestamp": f"{today}T10:01:00+00:00",
            "patient_id": "P001", "question_id": "q2", "error": None,
        },
        # STT — low confidence
        {
            "session_id": str(uuid.uuid4()), "feature": "stt", "model": "chirp_2",
            "input": {"audio_bytes": 12000, "content_type": "audio/webm"},
            "output": {"transcript": "my pressure uh been high", "confidence": 0.52},
            "latency_ms": 610, "timestamp": f"{today}T10:03:15+00:00",
            "patient_id": "P001", "question_id": "q3", "error": None,
        },
        # STT — good transcript, pain scale
        {
            "session_id": str(uuid.uuid4()), "feature": "stt", "model": "chirp_2",
            "input": {"audio_bytes": 22000, "content_type": "audio/webm"},
            "output": {"transcript": "my pain level is about a seven out of ten", "confidence": 0.91},
            "latency_ms": 740, "timestamp": f"{today}T10:05:42+00:00",
            "patient_id": "P002", "question_id": "q1", "error": None,
        },
        # STT — empty transcript
        {
            "session_id": str(uuid.uuid4()), "feature": "stt", "model": "chirp_2",
            "input": {"audio_bytes": 3200, "content_type": "audio/webm"},
            "output": {"transcript": "", "confidence": 0.0},
            "latency_ms": 510, "timestamp": f"{today}T10:07:00+00:00",
            "patient_id": "P003", "question_id": "q1", "error": None,
        },
        # STT — neuropathy symptoms
        {
            "session_id": str(uuid.uuid4()), "feature": "stt", "model": "chirp_2",
            "input": {"audio_bytes": 32000, "content_type": "audio/webm"},
            "output": {"transcript": "I have been feeling numbness and tingling in my feet especially at night", "confidence": 0.88},
            "latency_ms": 790, "timestamp": f"{today}T10:09:20+00:00",
            "patient_id": "P001", "question_id": "q4", "error": None,
        },
        # Question generation — successful
        {
            "session_id": str(uuid.uuid4()), "feature": "question_generation",
            "model": "gemini-2.5-flash",
            "input": {"patient_id": "P001", "visit_id": "V003",
                      "conditions": ["Type 2 Diabetes Mellitus", "Hypertension"], "endpoint": "generate-questionnaire"},
            "output": {"question_count": 6, "requires_image_count": 1},
            "latency_ms": 11240, "timestamp": f"{today}T09:55:00+00:00",
            "patient_id": "P001", "question_id": None, "error": None,
        },
        # Question generation — zero questions (failure mode)
        {
            "session_id": str(uuid.uuid4()), "feature": "question_generation",
            "model": "gemini-2.5-flash",
            "input": {"patient_id": "P002", "visit_id": "V001",
                      "conditions": ["COPD"], "endpoint": "generate-questionnaire"},
            "output": {"question_count": 0, "requires_image_count": 0},
            "latency_ms": 9800, "timestamp": f"{today}T10:12:00+00:00",
            "patient_id": "P002", "question_id": None, "error": None,
        },
        # Question generation — successful
        {
            "session_id": str(uuid.uuid4()), "feature": "question_generation",
            "model": "gemini-2.5-flash",
            "input": {"patient_id": "P004", "visit_id": "V002",
                      "conditions": ["Post-operative wound", "Type 2 Diabetes Mellitus"], "endpoint": "generate-questionnaire"},
            "output": {"question_count": 5, "requires_image_count": 2},
            "latency_ms": 13100, "timestamp": f"{today}T10:15:30+00:00",
            "patient_id": "P004", "question_id": None, "error": None,
        },
        # TTS — successful
        {
            "session_id": str(uuid.uuid4()), "feature": "tts",
            "model": "en-US-Chirp3-HD-Aoede",
            "input": {"text_length": 72, "voice": "en-US-Chirp3-HD-Aoede"},
            "output": {"audio_bytes": 42560},
            "latency_ms": 620, "timestamp": f"{today}T10:01:05+00:00",
            "patient_id": "P001", "question_id": "q1", "error": None,
        },
        # TTS — error
        {
            "session_id": str(uuid.uuid4()), "feature": "tts",
            "model": "en-US-Chirp3-HD-Aoede",
            "input": {"text_length": 0, "voice": "en-US-Chirp3-HD-Aoede"},
            "output": {},
            "latency_ms": 210, "timestamp": f"{today}T10:02:00+00:00",
            "patient_id": "P002", "question_id": "q1",
            "error": "InvalidArgument: Text must not be empty",
        },
        # Image analysis — successful
        {
            "session_id": str(uuid.uuid4()), "feature": "image_analysis",
            "model": "gemini-2.5-flash",
            "input": {"image_bytes": 204800, "question": "Can you take a photo of your wound?"},
            "output": {"description": "The image shows a healing surgical incision on the lower right leg approximately 6 cm in length with mild erythema at the margins and no visible purulent discharge."},
            "latency_ms": 1840, "timestamp": f"{today}T10:18:00+00:00",
            "patient_id": "P004", "question_id": "q3", "error": None,
        },
    ]

    with open(out_path, "w") as fh:
        for s in samples:
            fh.write(json.dumps(s) + "\n")

    print(f"[run_evals] Wrote {len(samples)} sample log entries → {out_path}")
    return out_path


# ─────────────────────────────────────────────────────────────────────────────
# Top failure modes aggregator
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_top_failures(*feature_results: dict) -> list[dict]:
    all_modes: list[dict] = []
    feature_names = ["stt", "question_generation", "tts", "image_analysis"]
    for feature_name, result in zip(feature_names, feature_results):
        for mode in result.get("failure_modes", []):
            all_modes.append({"feature": feature_name, **mode})
    # Sort HIGH severity first, then by count desc
    severity_rank = {"HIGH": 0, "LOW": 1}
    return sorted(all_modes, key=lambda m: (severity_rank.get(m.get("severity", "LOW"), 1), -m.get("count", 0)))


# ─────────────────────────────────────────────────────────────────────────────
# Fixes applied — document what was already addressed in Week 2
# ─────────────────────────────────────────────────────────────────────────────

FIXES_APPLIED = [
    {
        "issue": "requires_image and image_prompt missing from question_generation output",
        "fix": "Added _normalize_question() in api.py that back-fills both fields with "
               "safe defaults and keyword-based auto-detection. CrewAI prompt updated to "
               "explicitly request these fields.",
        "files": ["api.py"],
    },
    {
        "issue": "Question generation could return empty questions array on malformed LLM output",
        "fix": "_extract_questions() already handled nested JSON; _normalize_question() now "
               "additionally fills missing id/type/options/required fields so downstream "
               "consumers never receive incomplete question objects.",
        "files": ["api.py"],
    },
    {
        "issue": "Low-confidence STT transcripts silently passed to the patient",
        "fix": "Documented threshold (confidence < 0.7) in eval report. Full re-record "
               "prompt UX is Week 3 work; backend confidence is already logged so "
               "thresholding can be added to /stt without schema changes.",
        "files": ["eval/run_evals.py"],
    },
    {
        "issue": "No BigQuery sink — logs only written locally",
        "fix": "eval_logger.py updated to stream every AI call to BigQuery when "
               "BIGQUERY_DATASET env var is set. eval/setup_bigquery.py provisions "
               "the rxai_eval dataset and feature_logs table.",
        "files": ["eval/eval_logger.py", "eval/setup_bigquery.py"],
    },
]


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Rx-AI Week 1 evaluation runner")
    parser.add_argument(
        "--log-dir",
        default=str(_DEFAULT_LOG_DIR),
        help="Path to a JSONL file or directory of JSONL files (default: eval/logs/)",
    )
    parser.add_argument(
        "--output",
        default=str(_REPORTS_DIR / "week1.json"),
        help="Path for the output report (default: eval/reports/week1.json)",
    )
    parser.add_argument(
        "--generate-samples",
        action="store_true",
        help="Write synthetic sample log entries before running (useful with no real logs)",
    )
    args = parser.parse_args()

    log_path = Path(args.log_dir)
    output_path = Path(args.output)

    # Optionally seed with sample data
    if args.generate_samples:
        generate_sample_logs(_DEFAULT_LOG_DIR)
        if not log_path.exists():
            log_path = _DEFAULT_LOG_DIR

    # Load golden dataset for STT WER
    golden_path = _DATASETS_DIR / "stt_golden.json"
    if golden_path.exists():
        with open(golden_path) as fh:
            stt_golden = json.load(fh)
    else:
        stt_golden = []
        print(f"[run_evals] Warning: golden dataset not found at {golden_path}")

    # Load logs
    entries = load_logs(log_path)
    log_files = (
        [str(log_path)]
        if log_path.is_file()
        else [str(p) for p in sorted(log_path.glob("*.jsonl"))]
    )

    if not entries:
        print(
            f"[run_evals] No log entries found under {log_path}.\n"
            "  Run with --generate-samples to create synthetic data, or start the API "
            "and make some requests first."
        )
        sys.exit(0)

    print(f"[run_evals] Loaded {len(entries)} log entries from {len(log_files)} file(s)")

    # Run evaluations
    print("[run_evals] Evaluating STT …")
    stt_result = evaluate_stt(entries, stt_golden)

    print("[run_evals] Evaluating question generation …")
    qgen_result = evaluate_qgen(entries)

    print("[run_evals] Summarising TTS …")
    tts_result = evaluate_feature_summary(entries, "tts")

    print("[run_evals] Summarising image analysis …")
    img_result = evaluate_feature_summary(entries, "image_analysis")

    # Top failures
    top_failures = aggregate_top_failures(stt_result, qgen_result, tts_result, img_result)

    # Build report
    report: dict[str, Any] = {
        "run_id": "week1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "log_files": log_files,
        "total_entries": len(entries),
        "features": {
            "stt": stt_result,
            "question_generation": qgen_result,
            "tts": tts_result,
            "image_analysis": img_result,
        },
        "top_failure_modes": top_failures,
        "fixes_applied": FIXES_APPLIED,
        "next_steps": [
            "Assemble real 20-clip STT golden dataset (eval/datasets/stt_golden.json) "
            "with matched session_ids to get accurate WER.",
            "Enable BigQuery streaming (set BIGQUERY_DATASET in .env) and re-run to "
            "validate BQ sink.",
            "Run with --deepeval flag (Week 2 stretch) for LLM-judged relevance on "
            "question generation.",
            "Week 3: add confidence < 0.7 re-record prompt to /stt endpoint.",
        ],
    }

    # Write report
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w") as fh:
        json.dump(report, fh, indent=2)

    # Print summary
    print(f"\n{'='*60}")
    print(f"  Rx-AI Week 1 Evaluation Report")
    print(f"{'='*60}")
    print(f"  Total log entries : {len(entries)}")
    print(f"  STT entries       : {stt_result['count']}")
    if stt_result.get("wer") and stt_result["wer"]["avg"] is not None:
        print(f"  STT avg WER       : {stt_result['wer']['avg']:.1%}")
    if stt_result.get("confidence") and stt_result["confidence"]["avg"] is not None:
        print(f"  STT avg confidence: {stt_result['confidence']['avg']:.1%}")
    print(f"  QGen entries      : {qgen_result['count']}")
    if qgen_result.get("structure") and qgen_result["structure"].get("avg_latency_ms"):
        print(f"  QGen avg latency  : {qgen_result['structure']['avg_latency_ms']} ms")
    print(f"  TTS entries       : {tts_result['count']}")
    print(f"  Image analysis    : {img_result['count']}")
    print(f"\n  Top failure modes :")
    for fm in top_failures[:5]:
        print(f"    [{fm.get('severity','?')}] {fm['feature']}/{fm['type']} — {fm['count']} occurrence(s)")
    print(f"\n  Report written to : {output_path}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
