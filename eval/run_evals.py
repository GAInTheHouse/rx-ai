"""
eval/run_evals.py — Rx-AI evaluation runner for Week 2 sprint.

Runs:
  1. Image analysis GEval metric against /eval/logs/*.jsonl
  2. STT WER check against stt_golden.json
  3. (optional) TTS naturalness check via --deepeval flag

Usage:
    python eval/run_evals.py                        # lightweight, no DeepEval
    python eval/run_evals.py --deepeval             # full LLM-judged metrics
    python eval/run_evals.py --log eval/logs/2026-04-27.jsonl  # specific log file
    python eval/run_evals.py --feature image_analysis  # run only one feature

Output: eval/reports/week2.json
"""

import argparse
import json
import os
import re
import sys
from datetime import datetime, timezone
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Paths
# ─────────────────────────────────────────────────────────────────────────────

_REPO_ROOT = Path(__file__).resolve().parent.parent
_LOG_DIR = _REPO_ROOT / "eval" / "logs"
_DATASETS_DIR = _REPO_ROOT / "eval" / "datasets"
_REPORTS_DIR = _REPO_ROOT / "eval" / "reports"
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)


# ─────────────────────────────────────────────────────────────────────────────
# Log loading helpers
# ─────────────────────────────────────────────────────────────────────────────

def load_logs(log_paths: list[Path]) -> list[dict]:
    entries = []
    for path in log_paths:
        if not path.exists():
            print(f"[warn] Log file not found: {path}", file=sys.stderr)
            continue
        with open(path) as f:
            for line in f:
                line = line.strip()
                if line:
                    try:
                        entries.append(json.loads(line))
                    except json.JSONDecodeError:
                        pass
    return entries


def filter_feature(entries: list[dict], feature: str) -> list[dict]:
    return [e for e in entries if e.get("feature") == feature]


# ─────────────────────────────────────────────────────────────────────────────
# WER helper (word error rate — no external deps)
# ─────────────────────────────────────────────────────────────────────────────

def _wer(reference: str, hypothesis: str) -> float:
    """Compute Word Error Rate using dynamic programming."""
    ref = reference.lower().split()
    hyp = hypothesis.lower().split()
    if not ref:
        return 0.0
    n, m = len(ref), len(hyp)
    dp = [[0] * (m + 1) for _ in range(n + 1)]
    for i in range(n + 1):
        dp[i][0] = i
    for j in range(m + 1):
        dp[0][j] = j
    for i in range(1, n + 1):
        for j in range(1, m + 1):
            if ref[i - 1] == hyp[j - 1]:
                dp[i][j] = dp[i - 1][j - 1]
            else:
                dp[i][j] = 1 + min(dp[i - 1][j], dp[i][j - 1], dp[i - 1][j - 1])
    return dp[n][m] / len(ref)


# ─────────────────────────────────────────────────────────────────────────────
# STT evaluation
# ─────────────────────────────────────────────────────────────────────────────

def eval_stt(entries: list[dict]) -> dict:
    golden_path = _DATASETS_DIR / "stt_golden.json"
    golden = {}
    if golden_path.exists():
        with open(golden_path) as f:
            data = json.load(f)
        for clip in data.get("clips", []):
            golden[clip["id"]] = clip["transcript"]

    stt_entries = filter_feature(entries, "stt")
    wer_scores = []
    low_confidence = []
    error_count = 0

    for e in stt_entries:
        if e.get("error"):
            error_count += 1
            continue
        transcript = e.get("output", {}).get("transcript", "")
        confidence = e.get("output", {}).get("confidence", 0.0)

        # WER against closest golden (simple heuristic: try each, keep best match)
        if golden and transcript:
            best_wer = min(_wer(ref, transcript) for ref in golden.values())
            wer_scores.append(best_wer)

        if confidence and float(confidence) < 0.70:
            low_confidence.append(
                {
                    "session_id": e["session_id"],
                    "confidence": confidence,
                    "transcript": transcript,
                }
            )

    result = {
        "count": len(stt_entries),
        "error_count": error_count,
        "error_rate": round(error_count / max(len(stt_entries), 1), 3),
        "wer": {
            "avg": round(sum(wer_scores) / len(wer_scores), 4) if wer_scores else None,
            "scored_count": len(wer_scores),
            "pass": (sum(wer_scores) / len(wer_scores) <= 0.10) if wer_scores else None,
        },
        "confidence": {
            "avg": round(
                sum(
                    e["output"]["confidence"]
                    for e in stt_entries
                    if not e.get("error") and e["output"].get("confidence")
                )
                / max(
                    sum(
                        1
                        for e in stt_entries
                        if not e.get("error") and e["output"].get("confidence")
                    ),
                    1,
                ),
                3,
            ),
            "low_confidence_count": len(low_confidence),
            "low_confidence_entries": low_confidence,
        },
    }
    return result


# ─────────────────────────────────────────────────────────────────────────────
# TTS evaluation (lightweight — latency + error rate only)
# ─────────────────────────────────────────────────────────────────────────────

def eval_tts(entries: list[dict]) -> dict:
    tts_entries = filter_feature(entries, "tts")
    error_count = sum(1 for e in tts_entries if e.get("error"))
    latencies = [e["latency_ms"] for e in tts_entries if not e.get("error")]
    return {
        "count": len(tts_entries),
        "error_count": error_count,
        "error_rate": round(error_count / max(len(tts_entries), 1), 3),
        "latency_ms": {
            "avg": round(sum(latencies) / len(latencies)) if latencies else None,
            "min": min(latencies) if latencies else None,
            "max": max(latencies) if latencies else None,
        },
    }


# ─────────────────────────────────────────────────────────────────────────────
# Image analysis evaluation — keyword-based accuracy vs. golden labels
# ─────────────────────────────────────────────────────────────────────────────

def _keyword_recall(description: str, key_features: list[str]) -> float:
    """Fraction of golden key_features that appear in the model description."""
    if not key_features or not description:
        return 0.0
    desc_lower = description.lower()
    matched = sum(1 for kf in key_features if kf.lower() in desc_lower)
    return matched / len(key_features)


def eval_image_analysis_keyword(entries: list[dict]) -> dict:
    """
    Lightweight keyword-based image analysis evaluation.
    Matches image_analysis log entries against golden dataset by category
    and question similarity, then measures key-feature recall.
    """
    golden_path = _DATASETS_DIR / "image_golden.json"
    if not golden_path.exists():
        return {"error": "image_golden.json not found"}

    with open(golden_path) as f:
        golden_data = json.load(f)
    golden_samples = golden_data.get("samples", [])
    pass_threshold = golden_data.get("evaluation_config", {}).get(
        "geval_pass_threshold", 0.70
    )

    img_entries = filter_feature(entries, "image_analysis")
    if not img_entries:
        return {
            "count": 0,
            "note": "No image_analysis entries found in logs. Run the app with camera questions to generate data.",
            "golden_samples": len(golden_samples),
        }

    scored = []
    for e in img_entries:
        if e.get("error"):
            continue
        description = e.get("output", {}).get("description", "")
        question = e.get("input", {}).get("question", "")

        # Find the closest golden sample by question overlap
        best_sample = None
        best_overlap = -1
        for gs in golden_samples:
            q_lower = question.lower()
            ref_lower = gs["question"].lower()
            overlap = sum(1 for w in ref_lower.split() if w in q_lower)
            if overlap > best_overlap:
                best_overlap = overlap
                best_sample = gs

        if best_sample:
            recall = _keyword_recall(description, best_sample["key_features"])
            scored.append(
                {
                    "session_id": e["session_id"],
                    "matched_golden_id": best_sample["id"],
                    "category": best_sample["category"],
                    "question": question[:80],
                    "description_preview": description[:120],
                    "key_feature_recall": round(recall, 3),
                    "pass": recall >= pass_threshold,
                }
            )

    pass_count = sum(1 for s in scored if s["pass"])
    avg_recall = sum(s["key_feature_recall"] for s in scored) / max(len(scored), 1)

    return {
        "count": len(img_entries),
        "scored_count": len(scored),
        "avg_key_feature_recall": round(avg_recall, 3),
        "pass_count": pass_count,
        "pass_rate": round(pass_count / max(len(scored), 1), 3),
        "pass_threshold": pass_threshold,
        "overall_pass": avg_recall >= pass_threshold,
        "details": scored,
    }


# ─────────────────────────────────────────────────────────────────────────────
# DeepEval GEval image analysis (requires --deepeval flag + credentials)
# ─────────────────────────────────────────────────────────────────────────────

def eval_image_analysis_geval(entries: list[dict]) -> dict:
    """
    LLM-judged image analysis accuracy using DeepEval GEval.
    Requires: pip install deepeval, GOOGLE_APPLICATION_CREDENTIALS set.
    """
    try:
        from deepeval import evaluate
        from deepeval.metrics import GEval
        from deepeval.test_case import LLMTestCase, LLMTestCaseParams
    except ImportError:
        return {"error": "deepeval not installed. Run: pip install deepeval"}

    golden_path = _DATASETS_DIR / "image_golden.json"
    if not golden_path.exists():
        return {"error": "image_golden.json not found"}

    with open(golden_path) as f:
        golden_data = json.load(f)
    golden_samples = {s["id"]: s for s in golden_data.get("samples", [])}
    pass_threshold = golden_data.get("evaluation_config", {}).get(
        "geval_pass_threshold", 0.70
    )

    img_entries = [
        e
        for e in filter_feature(entries, "image_analysis")
        if not e.get("error") and e.get("output", {}).get("description")
    ]

    if not img_entries:
        return {
            "count": 0,
            "note": "No successful image_analysis entries to evaluate with GEval.",
        }

    image_accuracy_metric = GEval(
        name="ImageAnalysisAccuracy",
        criteria=(
            "Evaluate the actual output (model description of a patient photo) against the "
            "expected output (human-authored reference description). Score based on: "
            "(1) Clinical accuracy — does the model correctly identify the same findings? "
            "(2) Completeness — are all key clinical features from the reference mentioned? "
            "(3) No hallucination — does the model avoid stating things not in the reference? "
            "(4) Conciseness — is the output 2–4 sentences without fluff?"
        ),
        evaluation_params=[
            LLMTestCaseParams.ACTUAL_OUTPUT,
            LLMTestCaseParams.EXPECTED_OUTPUT,
        ],
        threshold=pass_threshold,
    )

    test_cases = []
    entry_map = {}  # test case index → log entry
    for idx, e in enumerate(img_entries):
        description = e["output"]["description"]
        question = e["input"].get("question", "")

        # Find closest golden
        best_sample = None
        best_overlap = -1
        for gs in golden_samples.values():
            overlap = sum(1 for w in gs["question"].lower().split() if w in question.lower())
            if overlap > best_overlap:
                best_overlap = overlap
                best_sample = gs

        expected = best_sample["reference_description"] if best_sample else ""

        tc = LLMTestCase(
            input=question,
            actual_output=description,
            expected_output=expected,
        )
        test_cases.append(tc)
        entry_map[idx] = e["session_id"]

    results = evaluate(test_cases, [image_accuracy_metric], run_async=False)

    scores = []
    for idx, result in enumerate(results.test_results):
        metric_result = result.metrics_data[0] if result.metrics_data else None
        score = metric_result.score if metric_result else None
        passed = metric_result.success if metric_result else False
        scores.append(
            {
                "session_id": entry_map.get(idx),
                "geval_score": round(score, 3) if score is not None else None,
                "pass": passed,
                "reason": metric_result.reason if metric_result else None,
            }
        )

    pass_count = sum(1 for s in scores if s["pass"])
    avg_score = sum(s["geval_score"] for s in scores if s["geval_score"] is not None) / max(
        sum(1 for s in scores if s["geval_score"] is not None), 1
    )

    return {
        "count": len(img_entries),
        "avg_geval_score": round(avg_score, 3),
        "pass_count": pass_count,
        "pass_rate": round(pass_count / max(len(scores), 1), 3),
        "pass_threshold": pass_threshold,
        "overall_pass": avg_score >= pass_threshold,
        "details": scores,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Question generation evaluation
# ─────────────────────────────────────────────────────────────────────────────

def eval_question_generation(entries: list[dict]) -> dict:
    qg_entries = filter_feature(entries, "question_generation")
    error_count = sum(1 for e in qg_entries if e.get("error"))
    valid = [e for e in qg_entries if not e.get("error")]
    latencies = [e["latency_ms"] for e in valid]

    question_counts = [e["output"].get("question_count", 0) for e in valid]
    requires_image_counts = [e["output"].get("requires_image_count", 0) for e in valid]

    return {
        "count": len(qg_entries),
        "error_count": error_count,
        "error_rate": round(error_count / max(len(qg_entries), 1), 3),
        "latency_ms": {
            "avg": round(sum(latencies) / len(latencies)) if latencies else None,
        },
        "question_counts": question_counts,
        "requires_image_counts": requires_image_counts,
        "avg_questions_per_call": round(
            sum(question_counts) / max(len(question_counts), 1), 1
        ),
        "structure": [
            {
                "session_id": e["session_id"],
                "question_count": e["output"].get("question_count", 0),
                "requires_image_count": e["output"].get("requires_image_count", 0),
                "structure_ok": e["output"].get("question_count", 0) > 0,
            }
            for e in valid
        ],
    }


# ─────────────────────────────────────────────────────────────────────────────
# Failure mode summary
# ─────────────────────────────────────────────────────────────────────────────

def _collect_failure_modes(
    stt: dict, tts: dict, img: dict, qg: dict
) -> list[dict]:
    modes = []

    if stt.get("error_count", 0):
        modes.append(
            {
                "feature": "stt",
                "type": "api_error",
                "severity": "HIGH",
                "count": stt["error_count"],
                "recommendation": (
                    "SpeechContext was removed (v2 incompatibility fix). "
                    "Verify STT is now error-free in today's logs."
                ),
            }
        )
    if stt.get("confidence", {}).get("low_confidence_count", 0):
        modes.append(
            {
                "feature": "stt",
                "type": "low_confidence",
                "severity": "LOW",
                "count": stt["confidence"]["low_confidence_count"],
                "threshold": 0.70,
                "recommendation": "Prompt the patient to re-record when confidence < 0.7.",
            }
        )
    if tts.get("error_count", 0):
        modes.append(
            {
                "feature": "tts",
                "type": "api_error",
                "severity": "HIGH",
                "count": tts["error_count"],
            }
        )
    if img.get("count", 0) == 0:
        modes.append(
            {
                "feature": "image_analysis",
                "type": "no_data",
                "severity": "INFO",
                "count": 0,
                "recommendation": "Trigger camera questions in the patient portal to generate image_analysis log entries.",
            }
        )
    elif not img.get("overall_pass", True):
        modes.append(
            {
                "feature": "image_analysis",
                "type": "low_key_feature_recall",
                "severity": "MEDIUM",
                "avg_recall": img.get("avg_key_feature_recall"),
                "recommendation": "Refine the /analyze-image prompt for more complete clinical feature coverage.",
            }
        )
    if qg.get("error_count", 0):
        modes.append(
            {
                "feature": "question_generation",
                "type": "api_error_or_empty",
                "severity": "HIGH",
                "count": qg["error_count"],
                "recommendation": (
                    "Enable Vertex AI API in GCP console. "
                    "_normalize_question() now back-fills requires_image on all returned questions."
                ),
            }
        )

    return modes


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def parse_args():
    parser = argparse.ArgumentParser(description="Rx-AI evaluation runner")
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Path to a specific JSONL log file (default: all files in eval/logs/)",
    )
    parser.add_argument(
        "--deepeval",
        action="store_true",
        help="Run DeepEval GEval metrics (requires credentials + internet)",
    )
    parser.add_argument(
        "--feature",
        choices=["stt", "tts", "image_analysis", "question_generation", "all"],
        default="all",
        help="Evaluate only this feature (default: all)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_REPORTS_DIR / "week2.json",
        help="Output report path",
    )
    return parser.parse_args()


def main():
    args = parse_args()

    # Resolve log files
    if args.log:
        log_paths = [args.log]
    else:
        log_paths = sorted(_LOG_DIR.glob("*.jsonl"))

    if not log_paths:
        print("[error] No log files found. Run the API and make some requests first.")
        sys.exit(1)

    print(f"Loading logs from: {[str(p) for p in log_paths]}")
    entries = load_logs(log_paths)
    print(f"Total log entries: {len(entries)}")

    # Run evaluations
    feature = args.feature
    stt_result = eval_stt(entries) if feature in ("stt", "all") else {}
    tts_result = eval_tts(entries) if feature in ("tts", "all") else {}
    qg_result = eval_question_generation(entries) if feature in ("question_generation", "all") else {}

    if feature in ("image_analysis", "all"):
        if args.deepeval:
            print("Running DeepEval GEval for image analysis…")
            img_result = eval_image_analysis_geval(entries)
            img_eval_method = "geval"
        else:
            print("Running keyword-based image analysis evaluation…")
            img_result = eval_image_analysis_keyword(entries)
            img_eval_method = "keyword_recall"
    else:
        img_result = {}
        img_eval_method = "skipped"

    failure_modes = _collect_failure_modes(stt_result, tts_result, img_result, qg_result)

    # Assemble report
    report = {
        "run_id": "week2",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "log_files": [str(p) for p in log_paths],
        "total_entries": len(entries),
        "eval_method": {
            "image_analysis": img_eval_method,
            "stt": "wer_vs_golden",
            "tts": "latency_error_rate",
            "question_generation": "structure_check",
        },
        "features": {
            "stt": stt_result,
            "tts": tts_result,
            "image_analysis": img_result,
            "question_generation": qg_result,
        },
        "top_failure_modes": failure_modes,
        "accuracy_vs_golden": {
            "image_analysis": {
                "method": img_eval_method,
                "avg_score": (
                    img_result.get("avg_key_feature_recall")
                    if img_result.get("avg_key_feature_recall") is not None
                    else img_result.get("avg_geval_score")
                ),
                "pass_threshold": img_result.get("pass_threshold"),
                "overall_pass": img_result.get("overall_pass"),
                "note": (
                    "No image_analysis data in logs yet — integrate CameraCapture + PatientView "
                    "voice+camera mode then re-run this script."
                    if img_result.get("count", 0) == 0
                    else None
                ),
            },
            "stt": {
                "method": "wer_vs_stt_golden",
                "avg_wer": stt_result.get("wer", {}).get("avg"),
                "pass_threshold": 0.10,
                "overall_pass": stt_result.get("wer", {}).get("pass"),
            },
        },
        "next_steps": [
            "Use the PatientView voice+camera mode to generate real image_analysis log entries.",
            "Re-run this script after generating image data: python eval/run_evals.py",
            "Use --deepeval for LLM-judged image accuracy (requires DeepEval + GCP credentials).",
            "Week 3: run workflow combination evals (STT+camera vs. text-only baseline).",
        ],
    }

    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)

    print(f"\n{'='*60}")
    print(f"Report written to: {args.output}")
    print(f"Total entries evaluated: {len(entries)}")
    if stt_result:
        wer = stt_result.get("wer", {}).get("avg")
        print(f"STT avg WER: {wer if wer is not None else 'N/A (no golden matches)'}")
    if img_result:
        score = img_result.get("avg_key_feature_recall") or img_result.get("avg_geval_score")
        print(f"Image analysis avg score: {score if score is not None else 'N/A (no data)'}")
    if failure_modes:
        print(f"Top failure modes: {len(failure_modes)}")
        for fm in failure_modes[:3]:
            print(f"  [{fm.get('severity', '?')}] {fm['feature']}: {fm['type']}")
    print("="*60)


if __name__ == "__main__":
    main()
