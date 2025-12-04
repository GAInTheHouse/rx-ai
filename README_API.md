# Rx-AI Dynamic Questionnaire API

This API uses CrewAI with multiple AI agents to generate personalized patient questionnaires based on their medical history and current visit context.

## Setup

### Quick Start (Recommended)

**One-time setup:**
```bash
./setup_conda.sh
```

This will:
- Create a conda environment named `rx-ai` with Python 3.11
- Install all dependencies from `requirements.txt`
- Create a `.env` template file

**Then edit `.env` and add your OpenAI API key:**
```bash
OPENAI_API_KEY=your_openai_api_key_here
```

**Start the server:**
```bash
./start_api.sh
```

### Manual Setup

If you prefer to set up manually:

#### 1. Create Conda Environment

```bash
conda create -n rx-ai python=3.11
conda activate rx-ai
```

#### 2. Install Dependencies

```bash
pip install -r requirements.txt
```

#### 3. Configure Environment

Create a `.env` file in the project root:

```bash
OPENAI_API_KEY=your_openai_api_key_here
```

#### 4. Start the API Server

```bash
python api.py
```

The server will start on `http://localhost:8000`

## API Endpoints

### 1. **Generate Dynamic Questionnaire** (NEW)

**Endpoint:** `POST /generate-questionnaire`

**Purpose:** Generate a personalized questionnaire based on current visit context

**Request Body:**
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
      "question": "On a scale of 1-10, how would you rate the numbness in your feet?",
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

### 2. **Get Questionnaire** (Legacy)

**Endpoint:** `POST /questionnaire`

**Purpose:** Generate questionnaire from stored patient data only

**Request Body:**
```json
{
  "patient_id": "P001"
}
```

### 3. **List Patients**

**Endpoint:** `GET /patients`

Returns list of all patients in the system.

### 4. **Web Interface**

**Endpoint:** `GET /`

Simple web interface for testing the API directly in your browser.

## How It Works

The API uses **3 AI Agents** in a sequential pipeline:

1. **Medical Data Deduplicator**
   - Removes duplicate information across visits
   - Identifies new developments and changes

2. **Healthcare Data Summarizer**
   - Extracts key problems requiring follow-up
   - Categorizes issues by medical concern
   - Identifies risk factors

3. **Patient Questionnaire Generator**
   - Creates personalized questions based on patient context
   - Uses validated scales (PHQ-9, GAD-7, pain scales, etc.)
   - Generates 3-8 targeted questions per visit

## Frontend Integration

The React frontend automatically calls this API when the "Release Questionnaire to Patient" button is clicked in the Visit Form.

**File:** `react-frontend/src/utils/questionnaireManager.js`

```javascript
const generatedQuestionnaire = await DynamicQuestionnaireGenerator.generateQuestionnaire(
  patientData,
  visitContext
)
```

## Troubleshooting

### API Not Connecting

If you see "Cannot connect to AI server" in the frontend:

1. Make sure the API is running: `python api.py`
2. Check that it's on port 8000: `http://localhost:8000`
3. Verify your `.env` file has a valid OpenAI API key

### CORS Errors

The API is configured to allow requests from:
- `http://localhost:5173` (Vite dev server)
- `http://localhost:3000` (Create React App)

If using a different port, update the `allow_origins` in `api.py`.

### Slow Response Times

The AI generation process typically takes **10-15 seconds** because:
- CrewAI runs 3 agents sequentially
- Each agent makes LLM calls to OpenAI
- Complex reasoning is performed

This is normal behavior for production-quality questionnaire generation.

## Development Notes

- The API uses in-memory patient data loaded at startup
- Patient data is loaded from `data/final_merged_patient_data.json`
- All AI processing happens synchronously (can be optimized with async tasks for production)
- Questionnaires are generated fresh for each request (no caching)

## Production Considerations

For production deployment:

1. **Database:** Replace in-memory data with proper database
2. **Caching:** Cache generated questionnaires to reduce API costs
3. **Async Processing:** Move AI generation to background tasks
4. **Rate Limiting:** Add rate limits to prevent abuse
5. **Authentication:** Add proper auth/authorization
6. **Monitoring:** Add logging and error tracking
7. **Scaling:** Deploy with multiple workers (Gunicorn + Uvicorn)

