"""
eval/run_evals.py — Rx-AI evaluation runner.

Evaluates all four AI features against JSONL logs:
  • STT  — Word Error Rate (WER) via jiwer (falls back to built-in DP) against
            eval/datasets/stt_golden.json
  • TTS  — latency + error-rate summary
  • Image analysis — keyword-recall vs. golden labels; optional GEval (--deepeval)
  • Question generation — structural validity + clinical keyword relevance

Usage:
    python eval/run_evals.py                              # all features, week2 report
    python eval/run_evals.py --deepeval                   # add LLM-judged image metrics
    python eval/run_evals.py --generate-samples           # seed synthetic logs then run
    python eval/run_evals.py --feature image_analysis     # one feature only
    python eval/run_evals.py --log eval/logs/2026-04-27.jsonl   # specific log file
    python eval/run_evals.py --output eval/reports/week1.json   # custom report path

Output: eval/reports/week2.json (or --output path).
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
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

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
        with open(fpath) as fh:
            for line in fh:
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
# STT helpers
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

    Empty-reference semantics:
      - ref empty, hyp empty  → 0.0  (both silent, no error)
      - ref empty, hyp non-empty → 1.0  (maximal error; avoids false perfect
        scores when a golden transcript is accidentally blank)
    Both jiwer and the fallback DP share this guard, applied before either
    path is reached.
    """
    ref_words = _normalise_text(reference).split()
    hyp_words = _normalise_text(hypothesis).split()

    # Guard must precede jiwer: jiwer.wer("", "words") returns 0.0, which
    # would silently report a perfect score for a blank golden transcript.
    if not ref_words:
        return 0.0 if not hyp_words else 1.0

    try:
        import jiwer  # noqa: PLC0415
        return float(jiwer.wer(reference, hypothesis))
    except ImportError:
        pass

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
    Find the best-matching golden entry for a given transcript.
    Returns the golden entry if ≥60% of its words appear in the transcript.
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
    return best if best_score >= 0.6 else None


# ─────────────────────────────────────────────────────────────────────────────
# STT evaluation
# ─────────────────────────────────────────────────────────────────────────────

def eval_stt(entries: list[dict], golden: list[dict] | None = None) -> dict:
    stt_entries = filter_feature(entries, "stt")
    if not stt_entries:
        return {"count": 0, "note": "No STT log entries found.", "wer": None, "confidence": None, "failure_modes": []}

    golden = golden or []
    confidences: list[float] = []
    wer_results: list[dict] = []
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
            confidences.append(float(confidence))
            if float(confidence) < 0.7:
                low_confidence.append({
                    "session_id": e["session_id"],
                    "confidence": confidence,
                    "transcript": transcript[:80],
                })

        match = _find_golden_match(transcript, golden) if golden else None
        if match:
            wer = _word_error_rate(match["reference_transcript"], transcript)
            wer_results.append({
                "session_id": e["session_id"],
                "golden_id": match["id"],
                "wer": wer,
                "reference": match["reference_transcript"],
                "hypothesis": transcript[:120],
            })

    failure_modes: list[dict] = []
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
        "error_count": len(error_entries),
        "error_rate": round(len(error_entries) / max(len(stt_entries), 1), 3),
        "wer": {
            "avg": avg_wer,
            "matched_golden_count": len(wer_results),
            "pass": (avg_wer <= 0.10) if avg_wer is not None else None,
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
# TTS evaluation
# ─────────────────────────────────────────────────────────────────────────────

def eval_tts(entries: list[dict]) -> dict:
    tts_entries = filter_feature(entries, "tts")
    if not tts_entries:
        return {"count": 0, "note": "No TTS log entries found.", "failure_modes": []}

    errors = [e for e in tts_entries if e.get("error")]
    latencies = [e["latency_ms"] for e in tts_entries if not e.get("error") and e.get("latency_ms")]
    return {
        "count": len(tts_entries),
        "error_count": len(errors),
        "error_rate": round(len(errors) / max(len(tts_entries), 1), 3),
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
# Image analysis evaluation — keyword recall vs. golden labels
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
    Matches image_analysis log entries against the golden dataset by question
    similarity, then measures key-feature recall.
    """
    golden_path = _DATASETS_DIR / "image_golden.json"
    if not golden_path.exists():
        return {"error": "image_golden.json not found"}

    with open(golden_path) as f:
        golden_data = json.load(f)
    golden_samples = golden_data.get("samples", [])
    pass_threshold = golden_data.get("evaluation_config", {}).get("geval_pass_threshold", 0.70)

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
            scored.append({
                "session_id": e["session_id"],
                "matched_golden_id": best_sample["id"],
                "category": best_sample["category"],
                "question": question[:80],
                "description_preview": description[:120],
                "key_feature_recall": round(recall, 3),
                "pass": recall >= pass_threshold,
            })

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
        "failure_modes": (
            [] if avg_recall >= pass_threshold else [{
                "type": "low_key_feature_recall",
                "severity": "MEDIUM",
                "avg_recall": round(avg_recall, 3),
                "recommendation": "Refine the /analyze-image prompt for more complete clinical feature coverage.",
            }]
        ),
        "details": scored,
    }


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
    pass_threshold = golden_data.get("evaluation_config", {}).get("geval_pass_threshold", 0.70)

    img_entries = [
        e
        for e in filter_feature(entries, "image_analysis")
        if not e.get("error") and e.get("output", {}).get("description")
    ]

    if not img_entries:
        return {"count": 0, "note": "No successful image_analysis entries to evaluate with GEval."}

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
    entry_map: dict[int, str] = {}
    for idx, e in enumerate(img_entries):
        description = e["output"]["description"]
        question = e["input"].get("question", "")

        best_sample = None
        best_overlap = -1
        for gs in golden_samples.values():
            overlap = sum(1 for w in gs["question"].lower().split() if w in question.lower())
            if overlap > best_overlap:
                best_overlap = overlap
                best_sample = gs

        expected = best_sample["reference_description"] if best_sample else ""
        tc = LLMTestCase(input=question, actual_output=description, expected_output=expected)
        test_cases.append(tc)
        entry_map[idx] = e["session_id"]

    results = evaluate(test_cases, [image_accuracy_metric], run_async=False)

    scores = []
    for idx, result in enumerate(results.test_results):
        metric_result = result.metrics_data[0] if result.metrics_data else None
        score = metric_result.score if metric_result else None
        passed = metric_result.success if metric_result else False
        scores.append({
            "session_id": entry_map.get(idx),
            "geval_score": round(score, 3) if score is not None else None,
            "pass": passed,
            "reason": metric_result.reason if metric_result else None,
        })

    pass_count = sum(1 for s in scores if s["pass"])
    valid_scores = [s["geval_score"] for s in scores if s["geval_score"] is not None]
    avg_score = round(sum(valid_scores) / len(valid_scores), 3) if valid_scores else None

    return {
        "count": len(img_entries),
        "avg_geval_score": avg_score,
        "pass_count": pass_count,
        "pass_rate": round(pass_count / max(len(scores), 1), 3),
        "pass_threshold": pass_threshold,
        "overall_pass": (avg_score >= pass_threshold) if avg_score is not None else False,
        "details": scores,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Question generation evaluation
# ─────────────────────────────────────────────────────────────────────────────

_CLINICAL_KEYWORDS = {
    "pain", "symptom", "medication", "dose", "adherence", "blood", "pressure",
    "glucose", "sugar", "weight", "breath", "chest", "nausea", "dizziness",
    "fatigue", "sleep", "mood", "anxiety", "swelling", "wound", "skin", "photo",
    "image", "exercise", "diet", "alcohol", "smoke", "insulin", "side effect",
}


def _keyword_relevance_score(question_text: str) -> float:
    """Simple keyword overlap score against clinical vocabulary (0.0 – 1.0)."""
    tokens = set(_normalise_text(question_text).split())
    matched = sum(1 for kw in _CLINICAL_KEYWORDS if kw in tokens or any(kw in t for t in tokens))
    return round(min(matched / 2, 1.0), 4)


def eval_question_generation(entries: list[dict]) -> dict:
    qgen_entries = filter_feature(entries, "question_generation")
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
    error_entries: list[dict] = []

    for e in qgen_entries:
        if e.get("error"):
            error_entries.append({"session_id": e["session_id"], "error": e["error"]})
            continue

        output = e.get("output", {})
        latency = e.get("latency_ms")
        if latency:
            latencies.append(latency)

        q_count = output.get("question_count", 0)
        ri_count = output.get("requires_image_count", 0)
        structure_ok = q_count > 0
        all_structure_results.append({
            "session_id": e["session_id"],
            "question_count": q_count,
            "requires_image_count": ri_count,
            "structure_ok": structure_ok,
        })

        questions_preview = output.get("questions_preview", [])
        if questions_preview:
            combined = " ".join(questions_preview)
            relevance_scores.append(_keyword_relevance_score(combined))

    failure_modes: list[dict] = []
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
        "error_count": len(error_entries),
        "error_rate": round(len(error_entries) / max(len(qgen_entries), 1), 3),
        "relevance": {
            "avg_keyword_score": avg_relevance,
            "note": (
                "Keyword relevance measures clinical vocabulary coverage of the "
                "generated question text (questions_preview). Entries logged "
                "before questions_preview was added are excluded from this metric. "
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
        {
            "session_id": str(uuid.uuid4()), "feature": "stt", "model": "chirp_2",
            "input": {"audio_bytes": 48000, "content_type": "audio/webm", "workflow_id": "WF_SYNTH_001"},
            "output": {"transcript": "I have been taking my metformin every morning with breakfast", "confidence": 0.94},
            "latency_ms": 820, "timestamp": f"{today}T10:01:00+00:00",
            "patient_id": "P001", "question_id": "q2", "error": None,
        },
        {
            "session_id": str(uuid.uuid4()), "feature": "stt", "model": "chirp_2",
            "input": {"audio_bytes": 12000, "content_type": "audio/webm", "workflow_id": "WF_SYNTH_001"},
            "output": {"transcript": "my pressure uh been high", "confidence": 0.52},
            "latency_ms": 610, "timestamp": f"{today}T10:03:15+00:00",
            "patient_id": "P001", "question_id": "q3", "error": None,
        },
        {
            "session_id": str(uuid.uuid4()), "feature": "stt", "model": "chirp_2",
            "input": {"audio_bytes": 22000, "content_type": "audio/webm", "workflow_id": "WF_SYNTH_002"},
            "output": {"transcript": "my pain level is about a seven out of ten", "confidence": 0.91},
            "latency_ms": 740, "timestamp": f"{today}T10:05:42+00:00",
            "patient_id": "P002", "question_id": "q1", "error": None,
        },
        {
            "session_id": str(uuid.uuid4()), "feature": "stt", "model": "chirp_2",
            "input": {"audio_bytes": 3200, "content_type": "audio/webm", "workflow_id": "WF_SYNTH_003"},
            "output": {"transcript": "", "confidence": 0.0},
            "latency_ms": 510, "timestamp": f"{today}T10:07:00+00:00",
            "patient_id": "P003", "question_id": "q1", "error": None,
        },
        {
            "session_id": str(uuid.uuid4()), "feature": "stt", "model": "chirp_2",
            "input": {"audio_bytes": 32000, "content_type": "audio/webm", "workflow_id": "WF_SYNTH_001"},
            "output": {"transcript": "I have been feeling numbness and tingling in my feet especially at night", "confidence": 0.88},
            "latency_ms": 790, "timestamp": f"{today}T10:09:20+00:00",
            "patient_id": "P001", "question_id": "q4", "error": None,
        },
        {
            "session_id": str(uuid.uuid4()), "feature": "question_generation",
            "model": "gemini-2.5-flash",
            "input": {"patient_id": "P001", "visit_id": "V003",
                      "conditions": ["Type 2 Diabetes Mellitus", "Hypertension"], "endpoint": "generate-questionnaire", "workflow_id": "WF_SYNTH_001"},
            "output": {
                "question_count": 6, "requires_image_count": 1,
                "questions_preview": [
                    "How would you rate your blood sugar control over the past week?",
                    "Have you been taking your insulin or diabetes medication as prescribed?",
                    "Have you experienced any dizziness or fatigue recently?",
                    "How has your blood pressure been? Have you checked it at home?",
                    "Have you noticed any swelling in your legs or feet?",
                    "Can you take a photo of any skin changes or wounds on your feet?",
                ],
            },
            "latency_ms": 11240, "timestamp": f"{today}T09:55:00+00:00",
            "patient_id": "P001", "question_id": None, "error": None,
        },
        {
            "session_id": str(uuid.uuid4()), "feature": "question_generation",
            "model": "gemini-2.5-flash",
            "input": {"patient_id": "P004", "visit_id": "V002",
                      "conditions": ["Post-operative wound", "Type 2 Diabetes Mellitus"], "endpoint": "generate-questionnaire", "workflow_id": "WF_SYNTH_004"},
            "output": {
                "question_count": 5, "requires_image_count": 2,
                "questions_preview": [
                    "How is your wound healing? Is there any pain, redness, or discharge?",
                    "Can you take a photo of the wound site so we can assess it visually?",
                    "Are you managing your blood glucose levels? What were your recent readings?",
                    "Have you noticed any signs of infection such as increased swelling or fever?",
                    "Can you photograph the wound dressing to confirm it is intact?",
                ],
            },
            "latency_ms": 13100, "timestamp": f"{today}T10:15:30+00:00",
            "patient_id": "P004", "question_id": None, "error": None,
        },
        {
            "session_id": str(uuid.uuid4()), "feature": "tts",
            "model": "en-US-Chirp3-HD-Aoede",
            "input": {"text_length": 72, "voice": "en-US-Chirp3-HD-Aoede", "workflow_id": "WF_SYNTH_001"},
            "output": {"audio_bytes": 42560},
            "latency_ms": 620, "timestamp": f"{today}T10:01:05+00:00",
            "patient_id": "P001", "question_id": "q1", "error": None,
        },
        {
            "session_id": str(uuid.uuid4()), "feature": "tts",
            "model": "en-US-Chirp3-HD-Aoede",
            "input": {"text_length": 0, "voice": "en-US-Chirp3-HD-Aoede", "workflow_id": "WF_SYNTH_002"},
            "output": {},
            "latency_ms": 210, "timestamp": f"{today}T10:02:00+00:00",
            "patient_id": "P002", "question_id": "q1",
            "error": "InvalidArgument: Text must not be empty",
        },
        {
            "session_id": str(uuid.uuid4()), "feature": "image_analysis",
            "model": "gemini-2.5-flash",
            "input": {"image_bytes": 204800, "question": "Can you take a photo of your wound?", "workflow_id": "WF_SYNTH_004"},
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
# Fixes applied — document what was addressed in Week 2
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
        "fix": "_extract_questions() already handled nested JSON; added _strip_markdown_fences() "
               "and _try_parse_json() to handle markdown-wrapped JSON; _normalize_question() now "
               "additionally fills missing id/type/options/required fields.",
        "files": ["api.py"],
    },
    {
        "issue": "Low-confidence STT transcripts silently passed to the patient",
        "fix": "Documented threshold (confidence < 0.7) in eval report. Full re-record "
               "prompt UX is future work; backend confidence is already logged so "
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
# Top failure modes aggregator
# ─────────────────────────────────────────────────────────────────────────────

def aggregate_top_failures(*feature_results: dict) -> list[dict]:
    feature_names = ["stt", "question_generation", "tts", "image_analysis"]
    all_modes: list[dict] = []
    for feature_name, result in zip(feature_names, feature_results):
        for mode in result.get("failure_modes", []):
            all_modes.append({"feature": feature_name, **mode})
    severity_rank = {"HIGH": 0, "MEDIUM": 1, "LOW": 2}
    return sorted(all_modes, key=lambda m: (severity_rank.get(m.get("severity", "LOW"), 2), -m.get("count", 0)))


# ─────────────────────────────────────────────────────────────────────────────
# Main
# ─────────────────────────────────────────────────────────────────────────────

def main() -> None:
    parser = argparse.ArgumentParser(description="Rx-AI evaluation runner")
    parser.add_argument(
        "--log",
        type=Path,
        default=None,
        help="Path to a specific JSONL log file (default: all files under --log-dir)",
    )
    parser.add_argument(
        "--log-dir",
        type=Path,
        default=_DEFAULT_LOG_DIR,
        help=f"Directory of JSONL log files (default: {_DEFAULT_LOG_DIR})",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=_REPORTS_DIR / "week2.json",
        help="Output report path (default: eval/reports/week2.json)",
    )
    parser.add_argument(
        "--deepeval",
        action="store_true",
        help="Run DeepEval GEval metrics for image analysis (requires credentials + internet)",
    )
    parser.add_argument(
        "--feature",
        choices=["stt", "tts", "image_analysis", "question_generation", "all"],
        default="all",
        help="Evaluate only this feature (default: all)",
    )
    parser.add_argument(
        "--generate-samples",
        action="store_true",
        help="Write synthetic sample log entries before running (useful with no real logs)",
    )
    args = parser.parse_args()

    log_path = args.log if args.log else args.log_dir

    if args.generate_samples:
        sample_dir = log_path.parent if (args.log and log_path.suffix == ".jsonl") else log_path
        generate_sample_logs(sample_dir)
        if args.log and log_path.suffix == ".jsonl":
            log_path = sample_dir

    # Load golden STT dataset
    golden_path = _DATASETS_DIR / "stt_golden.json"
    stt_golden: list[dict] = []
    if golden_path.exists():
        with open(golden_path) as fh:
            raw = json.load(fh)
            stt_golden = raw if isinstance(raw, list) else raw.get("clips", [])
    else:
        print(f"[run_evals] Warning: STT golden dataset not found at {golden_path}")

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

    feature = args.feature

    print("[run_evals] Evaluating STT …")
    stt_result = eval_stt(entries, stt_golden) if feature in ("stt", "all") else {}

    print("[run_evals] Evaluating TTS …")
    tts_result = eval_tts(entries) if feature in ("tts", "all") else {}

    print("[run_evals] Evaluating question generation …")
    qg_result = eval_question_generation(entries) if feature in ("question_generation", "all") else {}

    img_eval_method = "skipped"
    img_result: dict[str, Any] = {}
    if feature in ("image_analysis", "all"):
        if args.deepeval:
            print("[run_evals] Running DeepEval GEval for image analysis …")
            img_result = eval_image_analysis_geval(entries)
            img_eval_method = "geval"
        else:
            print("[run_evals] Running keyword-based image analysis evaluation …")
            img_result = eval_image_analysis_keyword(entries)
            img_eval_method = "keyword_recall"

    top_failures = aggregate_top_failures(stt_result, qg_result, tts_result, img_result)

    report: dict[str, Any] = {
        "run_id": args.output.stem,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "log_files": log_files,
        "total_entries": len(entries),
        "eval_method": {
            "image_analysis": img_eval_method,
            "stt": "wer_vs_golden",
            "tts": "latency_error_rate",
            "question_generation": "structure_and_keyword_relevance",
        },
        "features": {
            "stt": stt_result,
            "tts": tts_result,
            "image_analysis": img_result,
            "question_generation": qg_result,
        },
        "top_failure_modes": top_failures,
        "accuracy_vs_golden": {
            "image_analysis": {
                "method": img_eval_method,
                "avg_score": (
                    img_result.get("avg_key_feature_recall")
                    if img_eval_method == "keyword_recall"
                    else img_result.get("avg_geval_score")
                ),
                "pass_threshold": img_result.get("pass_threshold"),
                "overall_pass": img_result.get("overall_pass"),
                "note": (
                    "No image_analysis data in logs yet — integrate CameraCapture + "
                    "PatientView voice+camera mode then re-run."
                    if img_result.get("count", 0) == 0 else None
                ),
            },
            "stt": {
                "method": "wer_vs_stt_golden",
                "avg_wer": (stt_result.get("wer") or {}).get("avg"),
                "pass_threshold": 0.10,
                "overall_pass": (stt_result.get("wer") or {}).get("pass"),
            },
        },
        "fixes_applied": FIXES_APPLIED,
        "next_steps": [
            "Use the PatientView voice+camera mode to generate real image_analysis log entries.",
            "Re-run this script after generating image data: python eval/run_evals.py",
            "Use --deepeval for LLM-judged image accuracy (requires DeepEval + GCP credentials).",
            "Run workflow combination evals (STT+camera vs. text-only baseline).",
            "Add confidence < 0.7 re-record prompt to /stt endpoint.",
        ],
    }

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as fh:
        json.dump(report, fh, indent=2)

    print(f"\n{'='*60}")
    print(f"  Rx-AI Evaluation Report — {report['run_id']}")
    print(f"{'='*60}")
    print(f"  Total log entries   : {len(entries)}")
    if stt_result:
        print(f"  STT entries         : {stt_result.get('count', 0)}")
        wer = (stt_result.get("wer") or {}).get("avg")
        print(f"  STT avg WER         : {f'{wer:.1%}' if wer is not None else 'N/A (no golden matches)'}")
    if img_result:
        score = img_result.get("avg_key_feature_recall") or img_result.get("avg_geval_score")
        print(f"  Image analysis score: {score if score is not None else 'N/A (no data)'}")
    if top_failures:
        print(f"  Top failure modes   : {len(top_failures)}")
        for fm in top_failures[:3]:
            print(f"    [{fm.get('severity', '?')}] {fm['feature']}/{fm['type']} — {fm.get('count', '?')} occurrence(s)")
    print(f"\n  Report written to   : {args.output}")
    print(f"{'='*60}\n")


if __name__ == "__main__":
    main()
