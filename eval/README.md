## Rx-AI Evaluation

This repo logs every AI feature call (question generation, TTS, STT, image analysis) and provides scripts to evaluate individual features and **workflow combinations**.

### What gets logged

- **Where**: JSONL files under `eval/logs/<YYYY-MM-DD>.jsonl`
- **Optional**: Stream the same entries to **BigQuery** (for workflow queries)
- **Schema**: produced by `eval/eval_logger.py` (one entry per AI call)

### Workflow correlation (required for workflow evals)

Workflow-combination evaluation groups multiple feature calls that belong to the same patient check-in session using a client-supplied workflow id.

- **Header**: `X-RxAI-Workflow-Id: <uuid>`
- The backend injects it into logs as `input.workflow_id`.

If you don’t send this header, `eval/run_workflow_evals.py` will not be able to group calls into workflows.

### Local setup

Create env + install deps (recommended):

```bash
./setup_conda.sh
cp .env.example .env
```

Ensure your `.env` includes:

```bash
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/service-account.json
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GEMINI_MODEL=gemini-2.5-flash
```

### Run the product locally (API)

```bash
./start_api.sh
# or: python api.py
```

Server: `http://localhost:8000`

### Generate logs quickly (without frontend)

#### 1) Question generation (CrewAI pipeline)

```bash
curl -X POST http://localhost:8000/generate-questionnaire \
  -H "Content-Type: application/json" \
  -H "X-RxAI-Workflow-Id: 11111111-1111-1111-1111-111111111111" \
  -d '{
    "patient_id":"P001",
    "visit_id":"P001_V3",
    "conditions":["Diabetes Type 2","Hypertension"],
    "medications":["Metformin 1000mg BID","Lisinopril 10mg QD"],
    "allergies":["Penicillin"],
    "issues_detected":["Elevated blood pressure","Foot numbness"],
    "clinical_provider_note":"Patient reports occasional dizziness..."
  }'
```

#### 2) Question generation baseline (single-pass Gemini)

```bash
curl -X POST http://localhost:8000/generate-questionnaire-singlepass \
  -H "Content-Type: application/json" \
  -H "X-RxAI-Workflow-Id: 11111111-1111-1111-1111-111111111111" \
  -d '{
    "patient_id":"P001",
    "visit_id":"P001_V3",
    "conditions":["Diabetes Type 2","Hypertension"],
    "medications":["Metformin 1000mg BID","Lisinopril 10mg QD"],
    "allergies":["Penicillin"],
    "issues_detected":["Elevated blood pressure","Foot numbness"],
    "clinical_provider_note":"Patient reports occasional dizziness..."
  }'
```

#### 3) TTS

```bash
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -H "X-RxAI-Workflow-Id: 11111111-1111-1111-1111-111111111111" \
  -d '{"text":"Hello, how are you feeling today?"}' \
  --output test.mp3
open test.mp3
```

#### 4) STT

STT requires a real audio file. If you have one (e.g. `test.webm` from a browser MediaRecorder):

```bash
curl -X POST http://localhost:8000/stt \
  -H "X-RxAI-Workflow-Id: 11111111-1111-1111-1111-111111111111" \
  -F "audio=@test.webm"
```

The hardened backend returns:
- `needs_rerecord: true` when `confidence < 0.7`

### Run evaluations locally (JSONL source)

#### Week 2-style per-feature evals

```bash
python eval/run_evals.py --generate-samples
python eval/run_evals.py
```

Reports are written to `eval/reports/` (default: `week2.json`).

#### TTS — LLM-judge scripts (DeepEval GEval)

These judge **the text** sent to `/tts` (audio is not replayed in the eval).

```bash
# Naturalness / intelligibility of generic check-in questions
python eval/tts_naturalness_eval.py --dry-run
python eval/tts_naturalness_eval.py --log-file eval/logs/2026-05-05.jsonl

# Polypharmacy: multi-drug strings and TTS-friendly spelling (pass rate = headline “pronunciation accuracy”)
python eval/tts_polypharmacy_eval.py --dry-run
python eval/tts_polypharmacy_eval.py --log-file eval/logs/2026-05-05.jsonl --max-from-logs 10
```

Reports default to `eval/reports/tts_naturalness_week2.json` and `eval/reports/tts_polypharmacy.json`.

#### Workflow-combination evals

This requires logs with `input.workflow_id` present (send `X-RxAI-Workflow-Id`).

```bash
python eval/run_workflow_evals.py --source jsonl
```

Output: `eval/reports/workflows.json` (default)

### BigQuery setup (optional)

Provision dataset + table:

```bash
python -m eval.setup_bigquery --dataset rxai_eval --table feature_logs
```

Enable streaming by adding to `.env`:

```bash
BIGQUERY_DATASET=rxai_eval
BIGQUERY_TABLE=feature_logs
```

Then re-run the API and make requests; logs will stream to BigQuery in the background.

To run workflow evals from BigQuery:

```bash
python eval/run_workflow_evals.py --source bigquery --bq-limit 5000
```

### Backend hardening checks you can verify locally

- **STT hardening**:
  - Upload an extremely small audio file → `400 audio too short`
  - A low-confidence transcription → response includes `needs_rerecord=true`
- **TTS hardening**:
  - Empty text → `400 text must not be empty`
  - Very long text → `400 text too long`
- **Vision hardening**:
  - Invalid base64 → `400 image_base64 is not valid base64`
  - Model failure → `502 Vision model failed: ...`

