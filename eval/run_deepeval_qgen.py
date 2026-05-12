"""
eval/run_deepeval_qgen.py — DeepEval metrics for dynamic question generation.

Runs AnswerRelevancyMetric and HallucinationMetric (as described in the project report)
over generated questions vs. a synthetic clinical summary built from eval profiles.

Modes
-----
  --source live     Call the running API for each profile (requires server + credentials).
  --source logs     Read question_generation entries from JSONL logs (offline).

Usage
-----
  # Live (API must be up; uses P001 as anchor patient_id with profile fields in body):
  python eval/run_deepeval_qgen.py --source live --pipeline both

  # From captured logs only:
  python eval/run_deepeval_qgen.py --source logs --log-dir eval/logs

Output: eval/reports/qgen_deepeval.json by default.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from dotenv import load_dotenv

load_dotenv()

_REPO_ROOT = Path(__file__).resolve().parent.parent
_DATASETS_DIR = Path(__file__).resolve().parent / "datasets"
_REPORTS_DIR = Path(__file__).resolve().parent / "reports"
_REPORTS_DIR.mkdir(parents=True, exist_ok=True)

_DEFAULT_PATIENT_ID = os.getenv("EVAL_QGEN_PATIENT_ID", "P001")
_RELEVANCY_THRESHOLD = float(os.getenv("EVAL_QGEN_RELEVANCY_THRESHOLD", "0.75"))
_HALLUCINATION_THRESHOLD = float(os.getenv("EVAL_QGEN_HALLUCINATION_THRESHOLD", "0.25"))
_JUDGE_MODEL = os.getenv(
    "DEEPEVAL_JUDGE_MODEL",
    f"vertex_ai/{os.getenv('GEMINI_MODEL', 'gemini-2.5-flash')}",
)


def load_logs(log_path: Path) -> list[dict]:
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
                if not line:
                    continue
                try:
                    entries.append(json.loads(line))
                except json.JSONDecodeError:
                    pass
    return entries


def profile_to_clinical_summary(p: dict) -> str:
    """Flatten eval profile JSON into a single context string for judges."""
    lines = [
        f"Patient profile: {p.get('description', '')}",
        f"Conditions: {', '.join(p.get('conditions') or [])}",
        f"Medications: {', '.join(p.get('medications') or [])}",
        f"Allergies: {', '.join(p.get('allergies') or [])}",
        f"Issues / vitals / labs: {', '.join(p.get('issues_detected') or [])}",
    ]
    return "\n".join(lines).strip()


def _post_json(url: str, payload: dict, timeout_s: int = 300) -> dict:
    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=timeout_s) as resp:
        return json.loads(resp.read().decode("utf-8"))


def fetch_questions_live(api_base: str, pipeline: str, profile: dict) -> tuple[list[str], str]:
    """Return (question_texts, pipeline_label)."""
    visit_id = f"eval_{profile.get('profile_id', 'unknown')}"
    body = {
        "patient_id": profile.get("api_patient_id") or _DEFAULT_PATIENT_ID,
        "visit_id": visit_id,
        "conditions": profile.get("conditions") or [],
        "medications": profile.get("medications") or [],
        "allergies": profile.get("allergies") or [],
        "issues_detected": profile.get("issues_detected") or [],
        "clinical_provider_note": profile.get("clinical_provider_note") or "",
        "request_patient_images": bool(profile.get("request_patient_images", False)),
    }
    if pipeline == "crewai":
        path = "/generate-questionnaire"
    else:
        path = "/generate-questionnaire-singlepass"
    url = api_base.rstrip("/") + path
    data = _post_json(url, body)
    qs = data.get("questions") or []
    texts = [str(q.get("question", "")).strip() for q in qs if isinstance(q, dict) and q.get("question")]
    label = "crewai" if pipeline == "crewai" else "singlepass"
    return texts, label


def questions_from_logs(
    entries: list[dict], pipeline: str | None
) -> list[tuple[str, list[str], str]]:
    """
    Build (clinical_summary, questions, pipeline_label) from question_generation logs.
    Summary is reconstructed from input fields; questions from output.questions_preview.

    ``pipeline`` is None (both), ``crewai``, or ``singlepass`` — matched against
    ``input.endpoint`` values ``generate-questionnaire`` / ``generate-questionnaire-singlepass``.
    """
    out: list[tuple[str, list[str], str]] = []
    for e in entries:
        if e.get("feature") != "question_generation" or e.get("error"):
            continue
        inp = e.get("input") or {}
        ep = inp.get("endpoint") or ""
        if pipeline == "crewai" and ep != "generate-questionnaire":
            continue
        if pipeline == "singlepass" and ep != "generate-questionnaire-singlepass":
            continue
        summary_lines = [
            f"Patient ID: {inp.get('patient_id', '')}",
            f"Visit: {inp.get('visit_id', '')}",
            f"Conditions: {', '.join(inp.get('conditions') or [])}",
        ]
        clinical_summary = "\n".join(summary_lines)
        prev = (e.get("output") or {}).get("questions_preview") or []
        questions = [str(q).strip() for q in prev if str(q).strip()]
        if not questions:
            continue
        label = "crewai" if ep == "generate-questionnaire" else "singlepass"
        out.append((clinical_summary, questions, label))
    return out


def run_deepeval_on_pairs(
    pairs: list[tuple[str, str, str]],
    judge_model: str,
) -> dict[str, Any]:
    """pairs: (clinical_summary, question_text, pipeline_label)."""
    try:
        from deepeval import evaluate
        from deepeval.evaluate.configs import AsyncConfig
        from deepeval.metrics import AnswerRelevancyMetric, HallucinationMetric
        from deepeval.test_case import LLMTestCase
    except ImportError as exc:
        return {"error": f"deepeval not installed: {exc}"}

    if not pairs:
        return {"error": "No (context, question) pairs to evaluate."}

    relevancy = AnswerRelevancyMetric(
        threshold=_RELEVANCY_THRESHOLD,
        model=judge_model,
        async_mode=False,
    )
    hallucination = HallucinationMetric(
        threshold=_HALLUCINATION_THRESHOLD,
        model=judge_model,
        async_mode=False,
    )

    test_cases = [
        LLMTestCase(
            input=summary,
            actual_output=qtext,
            context=[summary],
        )
        for summary, qtext, _ in pairs
    ]

    try:
        result = evaluate(
            test_cases,
            [relevancy, hallucination],
            async_config=AsyncConfig(run_async=False),
        )
    except Exception as exc:
        return {"error": f"DeepEval evaluate() failed: {exc}"}

    rel_pass = 0
    hall_non_flag_pass = 0
    rel_scores: list[float] = []
    hall_scores: list[float] = []
    details: list[dict[str, Any]] = []

    for i, tr in enumerate(result.test_results):
        summary, qtext, plabel = pairs[i]
        row: dict[str, Any] = {
            "pipeline": plabel,
            "question_preview": qtext[:160],
            "context_preview": summary[:200],
        }
        for md in tr.metrics_data or []:
            name = (getattr(md, "name", "") or "").lower()
            score = float(md.score) if md.score is not None else None
            success = bool(md.success)
            if "relevancy" in name:
                row["answer_relevancy_score"] = score
                row["answer_relevancy_pass"] = success
                if score is not None:
                    rel_scores.append(score)
            if "hallucination" in name:
                row["hallucination_score"] = score
                row["hallucination_pass"] = success
                if score is not None:
                    hall_scores.append(score)
        if row.get("answer_relevancy_pass"):
            rel_pass += 1
        if row.get("hallucination_pass"):
            hall_non_flag_pass += 1
        details.append(row)

    n = len(pairs)
    return {
        "judge_model": judge_model,
        "relevancy_threshold": _RELEVANCY_THRESHOLD,
        "hallucination_threshold": _HALLUCINATION_THRESHOLD,
        "pair_count": n,
        "clinical_relevance_rate": round(rel_pass / n, 4) if n else None,
        "hallucination_flag_rate": round((n - hall_non_flag_pass) / n, 4) if n else None,
        "avg_answer_relevancy_score": round(sum(rel_scores) / len(rel_scores), 4) if rel_scores else None,
        "avg_hallucination_score": round(sum(hall_scores) / len(hall_scores), 4) if hall_scores else None,
        "details": details,
    }


def main() -> None:
    parser = argparse.ArgumentParser(description="DeepEval question-generation metrics")
    parser.add_argument(
        "--source",
        choices=["live", "logs"],
        default="logs",
        help="live = call API; logs = read JSONL",
    )
    parser.add_argument("--api-base", default="http://localhost:8000", help="API root (live mode)")
    parser.add_argument(
        "--pipeline",
        choices=["crewai", "singlepass", "both"],
        default="both",
        help="Which generator to run or filter",
    )
    parser.add_argument(
        "--profiles",
        type=Path,
        default=_DATASETS_DIR / "qgen_profiles.json",
        help="Synthetic eval profiles (live mode)",
    )
    parser.add_argument("--log-dir", type=Path, default=_REPO_ROOT / "eval" / "logs")
    parser.add_argument("--log", type=Path, default=None, help="Single JSONL file")
    parser.add_argument(
        "--output",
        type=Path,
        default=_REPORTS_DIR / "qgen_deepeval.json",
    )
    args = parser.parse_args()

    pairs: list[tuple[str, str, str]] = []

    if args.source == "live":
        if not args.profiles.exists():
            print(f"[run_deepeval_qgen] Profiles not found: {args.profiles}", file=sys.stderr)
            sys.exit(1)
        with open(args.profiles) as f:
            profiles = json.load(f)
        pipelines: list[str]
        if args.pipeline == "both":
            pipelines = ["crewai", "singlepass"]
        else:
            pipelines = [args.pipeline]

        for p in profiles:
            summary = profile_to_clinical_summary(p)
            for pl in pipelines:
                try:
                    qs, label = fetch_questions_live(args.api_base, pl, p)
                except urllib.error.URLError as exc:
                    print(f"[run_deepeval_qgen] API error for {p.get('profile_id')} ({pl}): {exc}", file=sys.stderr)
                    continue
                for q in qs:
                    pairs.append((summary, q, label))
        print(f"[run_deepeval_qgen] Live mode: collected {len(pairs)} questions.")
    else:
        log_path = args.log if args.log else args.log_dir
        entries = load_logs(log_path)
        pipeline_filter = None if args.pipeline == "both" else args.pipeline
        bundles = questions_from_logs(entries, pipeline_filter)
        for summary, qs, label in bundles:
            for q in qs:
                pairs.append((summary, q, label))
        print(f"[run_deepeval_qgen] Logs mode: collected {len(pairs)} question rows.")

    report = run_deepeval_on_pairs(pairs, _JUDGE_MODEL)
    report["generated_at"] = datetime.now(timezone.utc).isoformat()
    report["source"] = args.source
    report["pipeline_filter"] = args.pipeline

    args.output.parent.mkdir(parents=True, exist_ok=True)
    with open(args.output, "w") as f:
        json.dump(report, f, indent=2)

    print(f"[run_deepeval_qgen] Wrote {args.output}")
    if report.get("error"):
        print(f"[run_deepeval_qgen] Warning: {report['error']}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
