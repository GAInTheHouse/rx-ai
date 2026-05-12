"""
eval/tts_polypharmacy_eval.py
=============================
DeepEval GEval metric for **polypharmacy TTS pronunciation** — whether
check-in question text that names multiple medications is written so a
clinical TTS engine would pronounce each drug name acceptably.

This mirrors the project report row “Polypharmacy Pronunciation” (LLM-as-judge
on text, analogous to naturalness eval — we do not replay audio in this script).

Usage
-----
  python eval/tts_polypharmacy_eval.py --dry-run
  python eval/tts_polypharmacy_eval.py
  python eval/tts_polypharmacy_eval.py --log-file eval/logs/2026-05-05.jsonl
  python eval/tts_polypharmacy_eval.py --output eval/reports/tts_polypharmacy.json

Environment
-----------
Same as other DeepEval scripts: GOOGLE_APPLICATION_CREDENTIALS,
GOOGLE_CLOUD_PROJECT, GEMINI_MODEL / DEEPEVAL_JUDGE_MODEL optional.
Set DEEPEVAL_TELEMETRY_OPT_OUT=YES to suppress telemetry.

Optional: POLYPHARMACY_GEVal_THRESHOLD (default 0.85) — samples scoring at or
above this are counted as “pronunciation correct” for the headline pass rate.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

# ── Repo layout ────────────────────────────────────────────────────────────────
_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _REPO_ROOT / "eval" / "logs"
_REPORTS_DIR = _REPO_ROOT / "eval" / "reports"
_DEFAULT_LOG = _LOG_DIR / "2026-05-05.jsonl"

_GEVal_THRESHOLD = float(os.getenv("POLYPHARMACY_GEVal_THRESHOLD", "0.85"))
_METRIC_NAME = "Polypharmacy Pronunciation"

# Lowercase tokens; if ≥2 appear in a TTS log line, treat as polypharmacy sample.
_DRUG_HINTS = frozenset(
    {
        "metformin",
        "lisinopril",
        "atorvastatin",
        "warfarin",
        "furosemide",
        "methotrexate",
        "insulin",
        "aspirin",
        "sertraline",
        "lorazepam",
        "omeprazole",
        "gabapentin",
        "amlodipine",
        "metoprolol",
        "levothyroxine",
        "prednisone",
        "acetaminophen",
        "hydrochlorothiazide",
        "rosuvastatin",
        "tiotropium",
        "cephalexin",
        "glargine",
        "albuterol",
    }
)

# Fixed bank: each string names multiple medications (report-style polypharmacy).
_POLYPHARMACY_BANK: list[dict[str, str]] = [
    {
        "id": "poly_01",
        "text": (
            "Please confirm you are still taking metformin, lisinopril, and atorvastatin "
            "exactly as prescribed."
        ),
    },
    {
        "id": "poly_02",
        "text": (
            "Have you had any side effects from warfarin, furosemide, or metoprolol "
            "since your last visit?"
        ),
    },
    {
        "id": "poly_03",
        "text": (
            "Are you taking aspirin and omeprazole together, and if so, has your "
            "doctor reviewed stomach bleeding risk with you?"
        ),
    },
    {
        "id": "poly_04",
        "text": (
            "List the times you take insulin glargine and your meal-time insulin "
            "each day."
        ),
    },
    {
        "id": "poly_05",
        "text": (
            "Do you still use tiotropium daily along with your albuterol inhaler for COPD?"
        ),
    },
    {
        "id": "poly_06",
        "text": (
            "Have you missed any doses of methotrexate or folic acid this week?"
        ),
    },
    {
        "id": "poly_07",
        "text": (
            "Are gabapentin, sertraline, and lorazepam helping your nerve pain and mood?"
        ),
    },
    {
        "id": "poly_08",
        "text": (
            "Please verify you are on amlodipine five milligrams and rosuvastatin "
            "twenty milligrams once daily."
        ),
    },
    {
        "id": "poly_09",
        "text": (
            "When you take cephalexin, do you also continue metformin and insulin as usual?"
        ),
    },
    {
        "id": "poly_10",
        "text": (
            "Any new symptoms after starting levothyroxine while still on metoprolol?"
        ),
    },
    {
        "id": "poly_11",
        "text": (
            "For your blood pressure, are hydrochlorothiazide and lisinopril both taken "
            "in the morning?"
        ),
    },
    {
        "id": "poly_12",
        "text": (
            "Have you used acetaminophen while on warfarin without your clinician’s guidance?"
        ),
    },
    {
        "id": "poly_13",
        "text": (
            "Confirm prednisone taper schedule with your current dose of omeprazole."
        ),
    },
    {
        "id": "poly_14",
        "text": (
            "Do you take insulin, metformin, and cephalexin together after meals as directed?"
        ),
    },
]

_CRITERIA = (
    "Evaluate TEXT that will be read aloud by clinical text-to-speech and that "
    "mentions multiple medications (polypharmacy).\n"
    "Score how likely it is that a standard U.S. English neural TTS (e.g. Google Cloud "
    "Chirp) will pronounce every medication name and dose phrase acceptably for a patient.\n"
    "Rules:\n"
    "1. Prefer standard generic international nonproprietary names (e.g. metformin, "
    "   lisinopril) spelled conventionally.\n"
    "2. Penalize Latin abbreviations a patient-facing prompt should spell out "
    "   (e.g. BID, QD, PRN) if they would sound wrong or confuse TTS.\n"
    "3. 'mg', 'mcg', and spelled-out numbers ('five milligrams') are fine.\n"
    "4. Penalize dense symbols, slash-dosing without words, or brand names spelled "
    "   unusually unless they are standard.\n"
    "5. Multiple drugs in one sentence or list must each remain intelligible when spoken.\n"
    "Output a single score from 0 to 1, where 1 means all drug-related tokens are "
    "TTS-friendly and 0 means major mispronunciation or ambiguity risk."
)

_EVAL_STEPS = [
    "List every medication or drug-class token in the input.",
    "For each token, decide if typical TTS would read it correctly without clinician correction.",
    "Flag Latin pharmacy abbreviations or symbols that should be words for spoken prompts.",
    "Aggregate into one 0–1 score: weakest link dominates (one bad token lowers the score).",
]


def _drug_token_hits(text: str) -> int:
    t = re.sub(r"[^\w\s]", " ", text.lower())
    words = set(t.split())
    return sum(1 for d in _DRUG_HINTS if d in words or d in t)


def _load_tts_logs(log_file: Path) -> list[dict[str, Any]]:
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


def _resolve_samples(log_file: Path, max_from_logs: int) -> list[dict[str, str]]:
    """Bank first, then augment with log lines that mention ≥2 drug hints."""
    samples: list[dict[str, str]] = []
    seen_text: set[str] = set()

    for item in _POLYPHARMACY_BANK:
        samples.append(
            {
                "id": item["id"],
                "text": item["text"],
                "source": "bank",
            }
        )
        seen_text.add(item["text"].strip())

    if max_from_logs <= 0:
        return samples

    for entry in _load_tts_logs(log_file):
        text = (entry.get("input") or {}).get("text", "").strip()
        if not text or text in seen_text:
            continue
        if _drug_token_hits(text) < 2:
            continue
        samples.append(
            {
                "id": f"log_{entry.get('session_id', 'unknown')[:8]}",
                "text": text,
                "source": "log",
            }
        )
        seen_text.add(text)
        if sum(1 for s in samples if s["source"] == "log") >= max_from_logs:
            break

    return samples


def run_dry(samples: list[dict]) -> dict:
    print("\n── TTS Polypharmacy Pronunciation — DRY RUN ────────────────────────────────")
    print(f"   GEval threshold : {_GEVal_THRESHOLD}")
    print(f"   Samples         : {len(samples)}")
    print()
    for i, s in enumerate(samples, 1):
        print(f"   [{i:02d}] source={s['source']:<4}  id={s['id']}")
        print(f"        text: {s['text'][:100]}{'…' if len(s['text']) > 100 else ''}")
    print()
    return {
        "status": "dry_run",
        "threshold": _GEVal_THRESHOLD,
        "sample_count": len(samples),
        "samples": samples,
        "criteria": _CRITERIA,
        "eval_steps": _EVAL_STEPS,
    }


def run_eval(samples: list[dict], output_path: Path) -> dict:
    try:
        from deepeval import evaluate
        from deepeval.evaluate.configs import AsyncConfig
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    except ImportError:
        print(
            "[tts_polypharmacy_eval] deepeval is not installed. Run: pip install deepeval",
            file=sys.stderr,
        )
        sys.exit(1)

    metric = GEval(
        name=_METRIC_NAME,
        criteria=_CRITERIA,
        evaluation_steps=_EVAL_STEPS,
        evaluation_params=[LLMTestCaseParams.INPUT],
        threshold=_GEVal_THRESHOLD,
    )

    test_cases = [
        LLMTestCase(input=s["text"], actual_output=s["text"]) for s in samples
    ]

    print(f"\n── Running {_METRIC_NAME} GEval on {len(test_cases)} samples ─────────")
    results = evaluate(
        test_cases,
        [metric],
        async_config=AsyncConfig(run_async=False),
    )

    scored: list[dict] = []
    scores: list[float] = []

    for tc_result, sample in zip(results.test_results, samples):
        md_list = tc_result.metrics_data or []
        metric_data = None
        if len(md_list) == 1:
            metric_data = md_list[0]
        else:
            metric_data = next(
                (
                    m
                    for m in md_list
                    if "polypharmacy" in (getattr(m, "name", "") or "").lower()
                    or "pronunciation" in (getattr(m, "name", "") or "").lower()
                ),
                md_list[0] if md_list else None,
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
                "score": round(score, 4),
                "passed": passed,
                "reason": reason,
            }
        )

    avg_score = round(sum(scores) / len(scores), 4) if scores else 0.0
    pass_count = sum(1 for s in scored if s["passed"])
    n = len(scored)
    pronunciation_accuracy_rate = round(pass_count / n, 4) if n else 0.0

    report: dict[str, Any] = {
        "run_id": "tts_polypharmacy_geval",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "metric": f"{_METRIC_NAME} (GEval)",
        "threshold": _GEVal_THRESHOLD,
        "sample_count": n,
        "avg_score": avg_score,
        "pronunciation_accuracy_rate": pronunciation_accuracy_rate,
        "pass_count": pass_count,
        "fail_count": n - pass_count,
        "criteria": _CRITERIA,
        "eval_steps": _EVAL_STEPS,
        "results": scored,
        "summary": (
            f"Pronunciation accuracy (pass rate ≥ {_GEVal_THRESHOLD}): "
            f"{pronunciation_accuracy_rate:.1%} ({pass_count}/{n}); "
            f"mean GEval score: {avg_score:.3f}"
        ),
    }

    _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w") as f:
        json.dump(report, f, indent=2)

    print(f"\n── Results ─────────────────────────────────────────────────────────────────")
    print(f"   Pronunciation accuracy (pass rate): {pronunciation_accuracy_rate:.1%}")
    print(f"   Mean GEval score                    : {avg_score:.4f}")
    print(f"   Report                              : {output_path}")
    print()

    return report


def main() -> None:
    parser = argparse.ArgumentParser(
        description="GEval polypharmacy TTS pronunciation (text-in, LLM-as-judge)."
    )
    parser.add_argument(
        "--log-file",
        default=str(_DEFAULT_LOG),
        help="JSONL log file to mine for multi-drug TTS lines (optional)",
    )
    parser.add_argument(
        "--max-from-logs",
        type=int,
        default=10,
        help="Max extra samples from logs (0 = bank only)",
    )
    parser.add_argument(
        "--output",
        default=str(_REPORTS_DIR / "tts_polypharmacy.json"),
        help="Output JSON report path",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print sample list without calling the judge LLM",
    )
    args = parser.parse_args()

    log_file = Path(args.log_file)
    output_path = Path(args.output)

    samples = _resolve_samples(log_file, args.max_from_logs)
    if not samples:
        print("[tts_polypharmacy_eval] No samples — bank is empty.", file=sys.stderr)
        sys.exit(1)

    if args.dry_run:
        result = run_dry(samples)
        dry_path = _REPORTS_DIR / "tts_polypharmacy_dryrun.json"
        _REPORTS_DIR.mkdir(parents=True, exist_ok=True)
        with dry_path.open("w") as f:
            json.dump(result, f, indent=2)
        print(f"   Dry-run plan written to: {dry_path}")
    else:
        run_eval(samples, output_path)


if __name__ == "__main__":
    main()
