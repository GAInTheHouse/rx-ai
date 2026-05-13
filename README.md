# rx-ai

Rx-AI is a **multimodal patient check-in prototype**: a FastAPI backend plus a React provider/patient UI. It generates personalised questionnaires with **CrewAI** (three sequential agents) and **Google Vertex AI (Gemini 2.5 Flash)**, reads questions aloud (**TTS**), transcribes spoken answers (**STT**), and describes patient-submitted photos (**vision**).

## Repository layout

| Path | Purpose |
|------|---------|
| [api.py](api.py) | FastAPI server: patients, questionnaire generation, TTS, STT, image analysis |
| [react-frontend/](react-frontend/) | Vite + React provider dashboard and patient portal |
| [eval/](eval/) | JSONL logging, evaluation scripts, reports (see [eval/README.md](eval/README.md)) |
| [data/](data/) | Demo patient / visit JSON consumed by the API |
| [submissions/](submissions/) | Architecture diagram, report, demo video, presentation (links below) |

## Prerequisites

- **Python 3.11** (conda recommended via [setup_conda.sh](setup_conda.sh))
- **Google Cloud** project with a service account. Required IAM roles (details in [docs/API.md](docs/API.md)): Vertex AI User, Cloud Speech-to-Text ServiceAgent, Cloud Text-to-Speech Editor; enable Vertex AI, Speech-to-Text, and Text-to-Speech APIs.
- **Node.js 16+** and npm for the frontend

## Setup

From the repository root:

1. **Backend environment**

   ```bash
   ./setup_conda.sh
   cp .env.example .env
   ```

   Edit `.env` with your GCP project, credentials path, and model settings. See the **Create `.env`** section in [docs/API.md](docs/API.md) for the full variable list.

2. **Frontend patient data**

   ```bash
   cp data/final_merged_patient_data.json react-frontend/public/data/final_merged_patient_data.json
   ```

3. **Frontend dependencies**

   ```bash
   cd react-frontend && npm install && cd ..
   ```

## Usage (full stack)

1. Start the API (from repo root, with the conda env activated if you use it):

   ```bash
   ./start_api.sh
   ```

   API base URL: `http://localhost:8000`

2. Start the React app:

   ```bash
   cd react-frontend && npm run dev
   ```

   The dev server is configured for **port 3000** ([react-frontend/vite.config.js](react-frontend/vite.config.js)). The API allows CORS from `http://localhost:3000` and `http://localhost:5173`; if you change the port, update `allow_origins` in [api.py](api.py) (see [docs/API.md](docs/API.md)).

## CrewAI (default) vs single-pass Gemini

- **Default (React app)**: `POST /generate-questionnaire` — **CrewAI** three-agent pipeline (deduplicate → summarise → generate).
- **Baseline**: `POST /generate-questionnaire-singlepass` — one Gemini call, same response shape.

**Latency:** single-pass is usually faster (one model round-trip vs three sequential calls).

**Quality (observed):** CrewAI tends toward broader, safer intake questions when context is thin and often includes photo requests when appropriate. Single-pass is more direct and condition-focused but can **infer** details (for example medications) when structured fields are empty. Full discussion: [docs/API.md](docs/API.md#crewai-vs-single-pass).

## Reproduce core functionality

### End-to-end UI demo

With API and frontend running:

1. Open `http://localhost:3000/patient/P001` (provider).
2. Create a new visit if needed, then use **Release Questionnaire to Patient**.
3. In another tab, open `http://localhost:3000/patient-portal/P001` (patient), complete the form, and submit.
4. Confirm responses appear back on the provider view.

More UI detail: [react-frontend/README.md](react-frontend/README.md).

### API-only smoke tests

Example: generate a questionnaire (expect on the order of **8–15 seconds** for the CrewAI path):

```bash
curl -X POST http://localhost:8000/generate-questionnaire \
  -H "Content-Type: application/json" \
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

TTS example:

```bash
curl -X POST http://localhost:8000/tts \
  -H "Content-Type: application/json" \
  -d '{"text":"Hello, how are you feeling today?"}' \
  --output test.mp3
```

Additional endpoints (`/stt`, `/analyze-image`, baseline generator): [docs/API.md](docs/API.md).

### Evaluation and logged results

AI calls append JSONL under `eval/logs/<date>.jsonl`. To regenerate sample logs and run packaged evals, and to interpret reports under `eval/reports/`, follow [eval/README.md](eval/README.md).

## Artifacts and deliverables

- [Architecture diagram](submissions/architecture_diagram.png)
- [Written report](submissions/report.pdf)
- [Demo video](submissions/Rx_AI_Demo.mp4)
- [Rx.AI Multimodal Final Presentation](submissions/Rx.AI%20Multimodal%20Final%20Presentation.pdf) (PDF)

## Further reading

- [docs/API.md](docs/API.md) — endpoints, env vars, troubleshooting, production notes  
- [eval/README.md](eval/README.md) — logging schema, workflow header, eval and BigQuery commands  
- [react-frontend/README.md](react-frontend/README.md) — frontend features and structure  
