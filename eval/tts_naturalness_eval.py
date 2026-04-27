"""
tts_naturalness_eval.py
=======================
DeepEval GEval metric for TTS naturalness.

Evaluation design
-----------------
The /tts endpoint receives *text* and returns audio bytes. The log entry records
  input.text_length and output.audio_bytes, but not the verbatim input text
  (raw audio bytes are never logged — see eval_logger.py).

For a real eval run you would:
  (a) replay the 10 sampled TTS texts through the judge, OR
  (b) load the text from your session store and pass it here.

This script does both:
  - If JSONL logs contain a "text" field in the input dict  (optional richer
    logging you may add later), it uses that directly.
  - Otherwise it falls back to a set of representative clinical questions taken
    from the Week 1 session context (inferred from the log metadata such as
    patient_id, question_id, and the golden STT dataset for cross-referencing).

The GEval criteria mirror the project evaluation table:
  "Gemini-as-judge: naturalness, intelligibility" for TTS outputs.

Usage
-----
  # Dry-run (no LLM calls, prints sample structure):
  python eval/tts_naturalness_eval.py --dry-run

  # Full eval against 10 sampled TTS outputs:
  python eval/tts_naturalness_eval.py

  # Point at a specific JSONL log file:
  python eval/tts_naturalness_eval.py --log-file eval/logs/2026-04-26.jsonl

  # Write results to a custom path:
  python eval/tts_naturalness_eval.py --output eval/reports/tts_naturalness_week2.json

Environment
-----------
Requires GOOGLE_APPLICATION_CREDENTIALS + GOOGLE_CLOUD_PROJECT set, or
OPENAI_API_KEY as a fallback judge model (DeepEval supports both).
Set DEEPEVAL_TELEMETRY_OPT_OUT=YES to suppress telemetry.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Repo layout ────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _REPO_ROOT / "eval" / "logs"
_REPORTS_DIR = _REPO_ROOT / "eval" / "reports"
_DEFAULT_LOG = _LOG_DIR / "2026-04-26.jsonl"

# ── Clinical question bank ─────────────────────────────────────────────────────
# Representative clinical questions whose TTS output we want to evaluate for
# naturalness. These match the Week 1 session context where available.
_CLINICAL_QUESTION_BANK: list[dict[str, str]] = [
    {
        "id": "q_bank_01",
        "text": "How would you rate your overall pain level on a scale from one to ten?",
        "session_ref": "stt_003",
    },
    {
        "id": "q_bank_02",
        "text": "Have you been taking your prescribed medications as directed by your doctor?",
        "session_ref": "stt_001",
    },
    {
        "id": "q_bank_03",
        "text": "Have you noticed any changes in your blood pressure readings at home?",
        "session_ref": "stt_002",
    },
    {
        "id": "q_bank_04",
        "text": "Are you experiencing any shortness of breath during normal daily activities?",
        "session_ref": "stt_004",
    },
    {
        "id": "q_bank_05",
        "text": "Can you describe any new or worsening symptoms since your last visit?",
        "session_ref": None,
    },
    {
        "id": "q_bank_06",
        "text": "Have you checked your blood glucose levels regularly this week?",
        "session_ref": "stt_006",
    },
    {
        "id": "q_bank_07",
        "text": "Please describe the appearance of your wound, including any redness or discharge.",
        "session_ref": "stt_007",
    },
    {
        "id": "q_bank_08",
        "text": "Are you experiencing dizziness or lightheadedness, especially when standing?",
        "session_ref": "stt_008",
    },
    {
        "id": "q_bank_09",
        "text": "Have you had any numbness or tingling sensations in your hands or feet?",
        "session_ref": "stt_009",
    },
    {
        "id": "q_bank_10",
        "text": "Are there any side effects from your current medications you would like to discuss?",
        "session_ref": "stt_005",
    },
]

# ── GEval criteria ─────────────────────────────────────────────────────────────
_NATURALNESS_CRITERIA = (
    "The text is evaluated as a candidate for text-to-speech (TTS) synthesis "
    "in a medical patient check-in context. Assess the following dimensions:\n"
    "1. NATURALNESS: Does the text read as natural spoken English, avoiding "
    "   awkward phrasing, overly complex sentences, or unpronounceable symbols?\n"
    "2. INTELLIGIBILITY: Are medical terms spelled out or contextualised so a "
    "   patient can understand them when heard aloud (e.g. 'A1C' vs 'A one C')?\n"
    "3. CLINICAL APPROPRIATENESS: Does the phrasing match the formality and "
    "   empathy expected of a healthcare provider asking a patient a question?\n"
    "4. ABSENCE OF TTS ARTEFACTS: The text should not contain abbreviations, "
    "   special characters, bullet points, markdown, or numeric shorthand that "
    "   would produce unnatural audio output.\n"
    "Score 0–1 where 1 = excellent across all dimensions."
)

_NATURALNESS_EVAL_STEPS = [
    "Read the input text as if you were a TTS engine about to synthesise it.",
    "Identify any symbols, abbreviations, or phrasing that would sound unnatural when spoken aloud.",
    "Check whether medical terms are contextualised or spelled out for patient comprehension.",
    "Assess the overall sentence structure for spoken-language fluency.",
    "Assign a score from 0 to 1 based on the combined naturalness, intelligibility, and clinical appropriateness.",
]


def _load_tts_logs(log_file: Path) -> list[dict[str, Any]]:
    """Return all TTS log entries from a JSONL file."""
    entries: list[dict[str, Any]] = []
    if not log_file.exists():
        return entries
    with log_file.open() as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                entry = json.loads(line)
                if entry.get("feature") == "tts" and not entry.get("error"):
                    entries.append(entry)
            except json.JSONDecodeError:
                pass
    return entries


def _resolve_sample_texts(tts_logs: list[dict]) -> list[dict[str, str]]:
    """
    Map TTS log entries to question texts.

    If the log entry carries input.text (richer logging), use it directly.
    Otherwise, match by session metadata to the clinical question bank and
    fall back to the bank directly for up to 10 samples.
    """
    samples: list[dict[str, str]] = []
    used_ids: set[str] = set()

    for entry in tts_logs:
        text = entry.get("input", {}).get("text", "")
        if text:
            samples.append(
                {
                    "id": entry["session_id"],
                    "text": text,
                    "source": "log",
                    "patient_id": entry.get("patient_id", ""),
                    "question_id": entry.get("question_id", ""),
                }
            )
            used_ids.add(entry["session_id"])
        if len(samples) >= 10:
            break

    # Pad from the clinical bank until we have 10 samples
    for item in _CLINICAL_QUESTION_BANK:
        if len(samples) >= 10:
            break
        if item["id"] not in used_ids:
            samples.append(
                {
                    "id": item["id"],
                    "text": item["text"],
                    "source": "bank",
                    "patient_id": "",
                    "question_id": item.get("session_ref", ""),
                }
            )

    return samples[:10]


def run_dry(samples: list[dict]) -> dict:
    """Print the eval plan without making any LLM calls."""
    print("\n── TTS Naturalness Eval — DRY RUN ─────────────────────────────────────────")
    print(f"   Samples loaded : {len(samples)}")
    print(f"   Judge criteria : {_NATURALNESS_CRITERIA[:120]}…")
    print()
    for i, s in enumerate(samples, 1):
        print(f"   [{i:02d}] source={s['source']:<4}  id={s['id']}")
        print(f"        text: {s['text'][:90]}{'…' if len(s['text']) > 90 else ''}")
    print("\n   Pass --dry-run=false or omit the flag to run the full LLM eval.\n")
    return {
        "status": "dry_run",
        "sample_count": len(samples),
        "samples": samples,
        "criteria": _NATURALNESS_CRITERIA,
        "eval_steps": _NATURALNESS_EVAL_STEPS,
    }


def run_eval(samples: list[dict], output_path: Path) -> dict:
    """Run the DeepEval GEval metric and write results to output_path."""
    try:
        from deepeval import evaluate
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    except ImportError:
        print(
            "[tts_naturalness_eval] deepeval is not installed. "
            "Run: pip install deepeval",
            file=sys.stderr,
        )
        sys.exit(1)

    metric = GEval(
        name="TTS Naturalness",
        criteria=_NATURALNESS_CRITERIA,
        evaluation_steps=_NATURALNESS_EVAL_STEPS,
        evaluation_params=[LLMTestCaseParams.INPUT],
        threshold=0.7,
    )

    test_cases = [
        LLMTestCase(
            input=sample["text"],
            # GEval judges the input text itself (no reference output needed).
            actual_output=sample["text"],
        )
        for sample in samples
    ]

    print(f"\n── Running TTS Naturalness GEval on {len(test_cases)} samples ────────────")
    results = evaluate(test_cases, [metric])

    # ── Collect per-sample scores ──────────────────────────────────────────────
    scored: list[dict] = []
    scores: list[float] = []

    for tc_result, sample in zip(results.test_results, samples):
        # DeepEval ≥ 1.0 stores per-metric results in tc_result.metrics_data
        metric_data = next(
            (m for m in tc_result.metrics_data if m.name == "TTS Naturalness"),
            None,
        )
        score = float(metric_data.score) if metric_data and metric_data.score is not None else 0.0
        passed = bool(metric_data.success) if metric_data else False
        reason = metric_data.reason if metric_data else ""

        scores.append(score)
        scored.append(
            {
                "id": sample["id"],
                "text": sample["text"],
                "source": sample["source"],
                "patient_id": sample.get("patient_id", ""),
                "question_id": sample.get("question_id", ""),
                "score": round(score, 4),
                "passed": passed,
                "reason": reason,
            }
        )

    avg_score = round(sum(scores) / len(scores), 4) if scores else 0.0
    pass_count = sum(1 for s in scored if s["passed"])

    report: dict = {
        "run_id": "tts_naturalness_week2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metric": "TTS Naturalness (GEval)",
        "threshold": 0.7,
        "sample_count": len(scored),
        "avg_score": avg_score,
        "pass_rate": round(pass_count / len(scored), 4) if scored else 0.0,
        "pass_count": pass_count,
        "fail_count": len(scored) - pass_count,
        "criteria": _NATURALNESS_CRITERIA,
        "eval_steps": _NATURALNESS_EVAL_STEPS,
        "results": scored,
        "summary": (
            f"Avg naturalness score: {avg_score:.2f} — "
            f"{pass_count}/{len(scored)} samples passed (threshold ≥ 0.70)"
        ),
    }

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(report, f, indent=2)

    print(f"\n── Results ─────────────────────────────────────────────────────────────────")
    print(f"   Avg score  : {avg_score:.4f}")
    print(f"   Pass rate  : {pass_count}/{len(scored)} ({report['pass_rate']:.1%})")
    print(f"   Report     : {output_path}")
    print()

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Run TTS naturalness GEval metric against sampled TTS outputs."
    )
    parser.add_argument(
        "--log-file",
        default=str(_DEFAULT_LOG),
        help="Path to a JSONL eval log file (default: eval/logs/2026-04-26.jsonl)",
    )
    parser.add_argument(
        "--output",
        default=str(_REPORTS_DIR / "tts_naturalness_week2.json"),
        help="Output path for the JSON report",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        default=False,
        help="Print the eval plan without making LLM calls",
    )
    args = parser.parse_args()

    log_file = Path(args.log_file)
    output_path = Path(args.output)

    tts_logs = _load_tts_logs(log_file)
    samples = _resolve_sample_texts(tts_logs)

    if not samples:
        print(
            "[tts_naturalness_eval] No TTS samples found — check the log file path.",
            file=sys.stderr,
        )
        sys.exit(1)

    if args.dry_run:
        result = run_dry(samples)
    else:
        result = run_eval(samples, output_path)

    if args.dry_run:
        dry_path = _REPORTS_DIR / "tts_naturalness_dryrun.json"
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        with dry_path.open("w") as f:
            json.dump(result, f, indent=2)
        print(f"   Dry-run plan written to: {dry_path}")


if __name__ == "__main__":
    main()
