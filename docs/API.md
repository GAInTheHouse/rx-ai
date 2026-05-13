# Rx-AI Dynamic Questionnaire API

This API uses **CrewAI** with three sequential AI agents and **Google Cloud Vertex AI (Gemini 2.5 Flash)** to generate personalised patient questionnaires, convert questions to speech, transcribe patient answers, and describe patient-submitted photos.

---

## Setup

### Quick start (recommended)

**One-time setup:**

```bash
./setup_conda.sh
```

Then copy the environment template and fill in your GCP details:

```bash
cp .env.example .env
# edit .env with your values
```

**Start the server:**

```bash
./start_api.sh
# or: python api.py
```

---

### Manual setup

#### 1. Create Conda environment

```bash
conda create -n rx-ai python=3.11
conda activate rx-ai
pip install -r requirements.txt
```

#### 2. Configure Google Cloud credentials

You need a GCP service account with the following roles:

| Role | Purpose |
|---|---|
| `Vertex AI User` | CrewAI LLM calls + `/analyze-image` |
| `Cloud Speech-to-Text ServiceAgent` | `/stt` endpoint |
| `Cloud Text-to-Speech Editor` | `/tts` endpoint |

Steps:
1. Open [GCP Console → IAM → Service Accounts](https://console.cloud.google.com/iam-admin/serviceaccounts)
2. Create (or select) the `rx-ai-backend` service account
3. Assign the three roles above
4. Click **Keys → Add Key → JSON** and save the file to a path **outside** the repo, e.g. `~/.gcp/rx-ai-sa.json`

Enable these APIs in your project:
- [Vertex AI API](https://console.cloud.google.com/apis/library/aiplatform.googleapis.com)
- [Cloud Text-to-Speech API](https://console.cloud.google.com/apis/library/texttospeech.googleapis.com)
- [Cloud Speech-to-Text API](https://console.cloud.google.com/apis/library/speech.googleapis.com)

#### 3. Create `.env`

```bash
cp .env.example .env
```

Edit `.env` — never commit it:

```bash
# Google Cloud — Vertex AI
GOOGLE_APPLICATION_CREDENTIALS=/absolute/path/to/rx-ai-sa.json
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# Speech-to-Text v2 location (used for both the regional endpoint and recognizer path).
# chirp_2 is available in specific regions (e.g., us-central1).
GOOGLE_CLOUD_STT_LOCATION=us-central1

# Gemini model identifiers
GEMINI_MODEL=gemini-2.5-flash
GEMINI_TTS_VOICE=en-US-Chirp3-HD-Aoede

# Evaluation log output directory (relative to project root)
EVAL_LOG_DIR=eval/logs
```

#### 4. Start the API server

```bash
python api.py
```

The server starts on `http://localhost:8000`.

---

## API Endpoints

### `GET /patients`

Returns all patients in the system.

```bash
curl http://localhost:8000/patients
```

---

### `POST /generate-questionnaire` *(primary — used by React frontend)*

Generates a personalised questionnaire based on current visit context.

**Request body:**

```json
{
  "patient_id": "P001",
  "visit_id": "P001_V3",
  "conditions": ["Diabetes Type 2", "Hypertension"],
  "medications": ["Metformin 1000mg BID", "Lisinopril 10mg QD"],
  "allergies": ["Penicillin"],
  "issues_detected": ["Elevated blood pressure", "Foot numbness"],
  "clinical_provider_note": "Patient reports occasional dizziness..."
}
```

**Response:**

```json
{
  "questions": [
    {
      "id": "q1",
      "question": "How often do you experience dizziness?",
      "type": "radio",
      "source": "Clinical notes follow-up",
      "rationale": "Monitor reported symptom severity",
      "required": true,
      "options": ["Never", "Rarely", "Sometimes", "Often", "Always"]
    },
    {
      "id": "q2",
      "question": "On a scale of 1–10, how would you rate the numbness in your feet?",
      "type": "scale",
      "source": "Diabetic neuropathy screening",
      "rationale": "Assess peripheral neuropathy progression",
      "required": true,
      "min": 1,
      "max": 10
    }
  ],
  "patient_id": "P001",
  "visit_id": "P001_V3"
}
```

---

### `POST /generate-questionnaire-singlepass` *(baseline)*

Single-pass Gemini baseline questionnaire generator used to compare against the 3-agent CrewAI pipeline.

Uses the same request body as `/generate-questionnaire` and returns the same response shape.

---

## CrewAI vs single-pass

Which is used by default?
- **Default (React frontend)**: `/generate-questionnaire` (CrewAI 3-agent sequential pipeline)
- **Baseline comparison endpoint**: `/generate-questionnaire-singlepass` (single Gemini call)

Observed trade-offs:
- **Latency**: single-pass is typically faster (1 LLM call vs 3 sequential calls).
- **Quality**:
  - CrewAI tends to be more **robust** when the visit context is sparse (asks safer intake questions, covers more domains).
  - Single-pass tends to be more **direct and condition-focused**, but can make **implicit assumptions** if key structured fields are empty.

Recommendation (current):
- Keep **CrewAI** as default for now, and use single-pass when you need lower latency and can tolerate a higher assumption risk.

### `POST /questionnaire` *(legacy)*

Generates a questionnaire from stored patient data only (no current visit context).

```json
{ "patient_id": "P001" }
```

---

### `POST /tts`

Converts question text to speech. Returns an **mp3 audio stream**.

**Request body:**

```json
{
  "text": "How are you feeling compared to your last visit?",
  "voice": "en-US-Chirp3-HD-Aoede"
}
```

`voice` is optional — defaults to `GEMINI_TTS_VOICE` env var.

**Verify:**

```bash
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello, how are you feeling today?"}' \
  --output test.mp3 && open test.mp3
```

---

### `POST /stt`

Transcribes patient speech to text. Accepts `multipart/form-data` with an audio file field named `audio`.

Supported codecs: `audio/webm;codecs=opus` (browser `MediaRecorder` default), `audio/mp4`.

**Response:**

```json
{
  "transcript": "I have been feeling some dizziness in the morning.",
  "confidence": 0.962
}
```

**Verify:**

```bash
curl -X POST http://localhost:8000/stt \
  -F "audio=@test.webm"
```

---

### `POST /analyze-image`

Describes a patient-submitted photo in clinical terms using Gemini 2.5 Flash multimodal.

**Request body:**

```json
{
  "image_base64": "<standard base64, no data-URI prefix>",
  "question": "Can you show us the affected area on your foot?",
  "patient_id": "P001",
  "question_id": "q3"
}
```

**Response:**

```json
{
  "description": "The image shows the lateral aspect of the left foot with a 2–3 cm area of reddened, slightly raised skin near the fifth metatarsal. No open wound or discharge is visible."
}
```

**Verify:**

```bash
IMAGE_B64=$(base64 -i your_photo.jpg | tr -d '\n')
curl -X POST http://localhost:8000/analyze-image \
  -H "Content-Type: application/json" \
  -d "{\"image_base64\":\"$IMAGE_B64\",\"question\":\"Show us the area of concern.\"}"
```

---

## Workflow correlation header

To evaluate workflow combinations (e.g., question generation + TTS + STT + image analysis within the same patient check-in), send a workflow id header on every request:

- `X-RxAI-Workflow-Id: <uuid>`

The backend logs this value under `input.workflow_id` in JSONL/BigQuery logs.

## How it works

### Question generation — 3-agent CrewAI pipeline (Gemini 2.5 Flash)

1. **Medical Data Deduplicator** — removes duplicate information across visits and clinical notes
2. **Healthcare Data Summarizer** — identifies key problems and risk factors requiring patient input
3. **Patient Questionnaire Generator** — creates 3–8 targeted, validated questions

Typical pipeline latency: **8–15 seconds** (3 sequential LLM calls).

### Voice endpoints (TTS / STT)

- **`/tts`** — Google Cloud Text-to-Speech with Chirp3 HD voices (highest quality, low latency)
- **`/stt`** — Cloud Speech-to-Text v2 with Chirp 2 model; `AutoDetectDecodingConfig` handles webm/opus natively; medical vocabulary hints are included

### Image analysis

- **`/analyze-image`** — same Gemini 2.5 Flash model as the LLM, called with an inline image part + clinical prompt; returns 2–4 sentences of plain text

---

## Evaluation logging

Every AI call (question generation, TTS, STT, image analysis) writes a JSONL entry to `eval/logs/<date>.jsonl` via the `log_ai_call` async context manager in `eval/eval_logger.py`.

Log schema:

```json
{
  "session_id": "uuid4",
  "feature": "stt | tts | image_analysis | question_generation",
  "model": "model-name-or-voice",
  "input": {},
  "output": {},
  "latency_ms": 1234,
  "timestamp": "2026-04-14T10:00:00Z",
  "patient_id": "P001",
  "question_id": "q2",
  "error": null
}
```

These logs feed the evaluation pipeline described in [eval/README.md](../eval/README.md).

---

## Troubleshooting

### API not connecting

1. Check the server is running: `python api.py`
2. Verify `http://localhost:8000` is reachable
3. Confirm `.env` has valid `GOOGLE_APPLICATION_CREDENTIALS` pointing to the service account JSON

### CORS errors

The API allows `http://localhost:5173` (Vite) and `http://localhost:3000`. Update `allow_origins` in `api.py` if using a different port.

### `403 Permission denied` from Google Cloud

The service account is missing a required role. Check the three roles listed in the setup section above.

### TTS voice not found

Chirp3 HD voices may need to be enabled in your GCP project. Verify availability at:
**GCP Console → Text-to-Speech → Voice list → filter by "Chirp3 HD"**

### Slow responses

- CrewAI pipeline: 8–15 seconds is normal (3 sequential LLM calls to Gemini)
- TTS/STT: 1–3 seconds round-trip to Google Cloud APIs
- If event loop blocking is observed under load, the sync SDK calls in `/tts` and `/stt` can be wrapped in `asyncio.get_event_loop().run_in_executor(None, ...)` — defer this to Week 2

---

## Production considerations

1. **Database** — replace in-memory patient JSON with a proper database
2. **Caching** — cache generated questionnaires to reduce LLM calls
3. **Async SDK calls** — move `synthesize_speech` and `recognize` to thread pool executor
4. **BigQuery eval sink** — update `eval_logger.py` to stream to BigQuery (see Week 2 plan)
5. **Rate limiting** — add per-patient request throttling
6. **Authentication** — add proper auth/authorization before patient data is accessible
7. **HTTPS** — `getUserMedia` (camera/mic) requires HTTPS in production; localhost is exempt
