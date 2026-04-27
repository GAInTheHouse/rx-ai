import asyncio
import base64
import json
import os
import re
from typing import Any, Dict, List, Optional

import uvicorn
import vertexai
from crewai import Agent, Crew, LLM, Process, Task
from dotenv import load_dotenv
from eval.eval_logger import log_ai_call
from fastapi import FastAPI, File, HTTPException, Request, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, StreamingResponse
from google.cloud import texttospeech
from google.cloud.speech_v2 import SpeechClient
from google.cloud.speech_v2.types import cloud_speech
from pydantic import BaseModel
from vertexai.generative_models import GenerativeModel, Part

load_dotenv()

# ─────────────────────────────────────────────
# Vertex AI initialisation
# ─────────────────────────────────────────────
vertexai.init(
    project=os.getenv("GOOGLE_CLOUD_PROJECT"),
    location=os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1"),
)

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
_GCP_PROJECT = os.getenv("GOOGLE_CLOUD_PROJECT")
_GCP_LOCATION = os.getenv("GOOGLE_CLOUD_LOCATION", "us-central1")

if not _GCP_PROJECT:
    raise RuntimeError(
        "GOOGLE_CLOUD_PROJECT environment variable is not set. "
        "Copy .env.example to .env and fill in your GCP project ID."
    )

# LiteLLM (used by CrewAI 1.x internally) reads these env vars for Vertex AI.
# Map from the Google-standard names we already have in .env.
os.environ.setdefault("VERTEXAI_PROJECT", _GCP_PROJECT)
os.environ.setdefault("VERTEXAI_LOCATION", _GCP_LOCATION)

# ─────────────────────────────────────────────
# Google Cloud service clients (initialised once at startup)
# ─────────────────────────────────────────────
_tts_client = texttospeech.TextToSpeechClient()
_stt_client = SpeechClient()

# ─────────────────────────────────────────────
# FastAPI app
# ─────────────────────────────────────────────
app = FastAPI(title="Rx-AI Questionnaire API", version="2.0.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ─────────────────────────────────────────────
# Patient data — loaded once at startup
# ─────────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
_input_file = os.path.join(BASE_DIR, "data", "final_merged_patient_data.json")

try:
    with open(_input_file, "r") as f:
        ALL_PATIENT_DATA = json.load(f)
    print(f"Loaded {len(ALL_PATIENT_DATA)} patients into memory")
except FileNotFoundError:
    print(f"Warning: Patient data file not found at {_input_file}")
    ALL_PATIENT_DATA = []

# ─────────────────────────────────────────────
# CrewAI agent factory
# ─────────────────────────────────────────────

def create_agents():
    # CrewAI 1.x uses LiteLLM internally — pass a crewai.LLM instance.
    # The vertex_ai/ prefix tells LiteLLM to route via Vertex AI using
    # VERTEXAI_PROJECT / VERTEXAI_LOCATION env vars set above.
    llm = LLM(
        model=f"vertex_ai/{GEMINI_MODEL}",
        temperature=0.2,
    )
    return [
        Agent(
            role="Medical Data Deduplicator",
            goal="Deduplicate notes",
            backstory="EHR expert",
            llm=llm,
            verbose=False,
        ),
        Agent(
            role="Healthcare Data Summarizer",
            goal="Extract problems",
            backstory="Clinical grouping expert",
            llm=llm,
            verbose=False,
        ),
        Agent(
            role="Patient Questionnaire Generator",
            goal="Generate questions",
            backstory="Questionnaire expert",
            llm=llm,
            verbose=False,
        ),
    ]

# ─────────────────────────────────────────────
# Pydantic models
# ─────────────────────────────────────────────

class PatientRequest(BaseModel):
    patient_id: str


class QuestionnaireGenerationRequest(BaseModel):
    patient_id: str
    visit_id: str
    conditions: List[str] = []
    medications: List[str] = []
    allergies: List[str] = []
    issues_detected: List[str] = []
    clinical_provider_note: str = ""


class TTSRequest(BaseModel):
    text: str
    voice: Optional[str] = None  # overrides GEMINI_TTS_VOICE env var


class QuestionItem(BaseModel):
    id: str
    question: str
    type: str = "text"
    source: Optional[str] = None
    rationale: Optional[str] = None
    required: bool = True
    options: List[str] = []
    requires_image: bool = False
    image_prompt: str = ""


class ImageAnalysisRequest(BaseModel):
    image_base64: str           # standard base64 — no data-URI prefix
    question: str               # the check-in question that prompted the photo
    patient_id: Optional[str] = None
    question_id: Optional[str] = None


# ─────────────────────────────────────────────
# Utilities: parse + normalise CrewAI question output
# ─────────────────────────────────────────────

def _strip_markdown_fences(text: str) -> str:
    """Remove ```json / ``` wrappers that LLMs often add around JSON output."""
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\s*", "", text)
    text = re.sub(r"\s*```$", "", text)
    return text.strip()


def _try_parse_json(raw: str):
    """Try to parse raw string as JSON, stripping markdown fences first."""
    try:
        return json.loads(raw)
    except Exception:
        pass
    try:
        return json.loads(_strip_markdown_fences(raw))
    except Exception:
        pass
    return raw


_IMAGE_KEYWORDS = [
    "photo", "picture", "image", "skin", "wound", "rash", "redness",
    "swelling", "bruise", "sore", "lesion", "medication", "pill",
    "bottle", "prescription", "insurance card", "id card",
]

_IMAGE_PROMPT_MAP = {
    "wound":          "Please take a photo of the wound or injury.",
    "rash":           "Please take a close-up photo of the rash.",
    "redness":        "Please take a photo showing the area of redness.",
    "swelling":       "Please photograph the swollen area.",
    "bruise":         "Please photograph the bruise.",
    "sore":           "Please photograph the sore.",
    "lesion":         "Please photograph the lesion.",
    "skin":           "Please take a clear photo of the affected skin area.",
    "medication":     "Please take a photo of your medication bottle or pill.",
    "pill":           "Please take a photo of the pill.",
    "bottle":         "Please take a photo of the medication bottle label.",
    "prescription":   "Please photograph your prescription label.",
    "insurance card": "Please take a clear photo of your insurance card.",
    "id card":        "Please take a photo of your ID card.",
    "photo":          "Please take a photo as requested.",
    "picture":        "Please take a photo as requested.",
    "image":          "Please take a photo as requested.",
}


def _normalize_question(q: dict) -> dict:
    """Back-fill missing fields so the frontend always receives a complete object."""
    q.setdefault("id", f"q{id(q)}")
    q.setdefault("type", "text")
    q.setdefault("required", True)
    q.setdefault("options", [])
    q.setdefault("source", "")
    q.setdefault("rationale", "")

    question_lower = str(q.get("question", "")).lower()

    if "requires_image" not in q:
        q["requires_image"] = any(kw in question_lower for kw in _IMAGE_KEYWORDS)

    if "image_prompt" not in q or not q.get("image_prompt"):
        match = next((kw for kw in _IMAGE_PROMPT_MAP if kw in question_lower), None)
        q["image_prompt"] = _IMAGE_PROMPT_MAP[match] if match else (
            "Please take a photo related to this question." if q["requires_image"] else ""
        )

    return q


def _extract_questions(result) -> list:
    if hasattr(result, "raw") and result.raw:
        parsed = _try_parse_json(result.raw)
    elif hasattr(result, "output") and result.output:
        parsed = result.output
    else:
        parsed = result

    while isinstance(parsed, list) and len(parsed) == 1:
        parsed = parsed[0]

    if isinstance(parsed, dict):
        questions = parsed.get("questions", [])
        if not questions and "questionnaire" in parsed:
            questionnaire = parsed["questionnaire"]
            if isinstance(questionnaire, dict):
                questions = questionnaire.get("questions", [])
            elif isinstance(questionnaire, list):
                questions = questionnaire
    elif isinstance(parsed, list):
        questions = parsed
    else:
        questions = []

    return [_normalize_question(q) for q in questions if isinstance(q, dict)]


# Image-trigger keywords used by both endpoints to auto-set requires_image when
# the LLM omits the field.
_IMAGE_KEYWORDS = frozenset([
    "photo", "photograph", "picture", "image", "skin", "wound", "rash",
    "lesion", "sore", "bruise", "swelling", "medication", "pill", "bottle",
    "prescription", "insurance", "card", "scan", "show", "upload",
])


def _normalize_question(q: dict) -> dict:
    """
    Back-fill requires_image / image_prompt with safe defaults if the LLM
    omitted them, and ensure every field defined in QuestionItem is present.
    Also auto-detects image-relevant questions from keyword heuristics.
    """
    q.setdefault("id", "")
    q.setdefault("question", "")
    q.setdefault("type", "text")
    q.setdefault("source", None)
    q.setdefault("rationale", None)
    q.setdefault("required", True)
    q.setdefault("options", [])

    text_lower = q["question"].lower()
    auto_image = any(kw in text_lower for kw in _IMAGE_KEYWORDS)

    if "requires_image" not in q:
        q["requires_image"] = auto_image
    if "image_prompt" not in q:
        q["image_prompt"] = (
            "Please take a clear photo and upload it." if q["requires_image"] else ""
        )
    return q


# ─────────────────────────────────────────────
# Routes — informational
# ─────────────────────────────────────────────

@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    patient_count = len(ALL_PATIENT_DATA)
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Rx-AI Questionnaire API</title>
        <style>
            body {{ font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; background: #f5f5f5; }}
            .card {{ background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }}
            h1 {{ color: #333; }}
            .status {{ padding: 15px; background: #e7f3ff; border-left: 4px solid #007bff; margin: 20px 0; }}
            .endpoint {{ background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; }}
            code {{ background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }}
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Rx-AI Questionnaire API v2</h1>
            <div class="status">
                <strong>Status:</strong> API is running ✓<br>
                <strong>Patients loaded:</strong> {patient_count}<br>
                <strong>LLM:</strong> {GEMINI_MODEL} (Vertex AI)
            </div>

            <h2>Endpoints</h2>

            <div class="endpoint"><strong>GET /patients</strong> — List all patients</div>
            <div class="endpoint"><strong>POST /generate-questionnaire</strong> — Generate dynamic questionnaire (React frontend)</div>
            <div class="endpoint"><strong>POST /questionnaire</strong> — Generate questionnaire from stored data (legacy)</div>
            <div class="endpoint"><strong>POST /tts</strong> — Text-to-speech (returns mp3)</div>
            <div class="endpoint"><strong>POST /stt</strong> — Speech-to-text (multipart audio upload)</div>
            <div class="endpoint"><strong>POST /analyze-image</strong> — Describe a patient-submitted photo</div>

            <p style="margin-top: 30px;">
                <strong>Documentation:</strong> See README_API.md for full details<br>
                <strong>React Frontend:</strong> http://localhost:5173 (when running)
            </p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)


@app.get("/patients")
async def list_patients():
    return [
        {"patient_id": p["patient_id"], "age": p["history"]["age"], "sex": p["history"]["sex"]}
        for p in ALL_PATIENT_DATA
    ]


# ─────────────────────────────────────────────
# Routes — questionnaire generation (CrewAI)
# ─────────────────────────────────────────────

@app.post("/questionnaire")
async def get_questionnaire(request: PatientRequest):
    """Legacy endpoint — generates questionnaire from stored patient data only."""
    patient_data = next(
        (p for p in ALL_PATIENT_DATA if p["patient_id"] == request.patient_id), None
    )
    if not patient_data:
        raise HTTPException(status_code=404, detail=f"Patient {request.patient_id} not found")

    dedup_agent, summarize_agent, question_agent = create_agents()

    dedup_task = Task(
        description=f"""
        Process this patient data: {json.dumps(patient_data)}

        Remove duplicate sentences from clinical notes.
        Output JSON with deduplicated_notes field.
        """,
        agent=dedup_agent,
        expected_output="JSON with deduplicated_notes",
    )

    summarize_task = Task(
        description="""
        Use the previous task output.
        Extract problems from conditions and issues_detected.
        Group by medical problem with history, status, treatments, labs.
        Output JSON with problems and Ungrouped_data fields.
        """,
        agent=summarize_agent,
        expected_output="JSON with problems and Ungrouped_data",
        context=[dedup_task],
    )

    question_task = Task(
        description="""
        Use the previous outputs.
        Generate 1-3 questions per problem.
        Output JSON with questionnaire containing questions array.
        Each question MUST have these exact fields:
          id, question, type, source, rationale, required, options,
          requires_image (bool — true if a photo would aid assessment),
          image_prompt (str — concise instruction for the photo if requires_image is true, else "").
        Set requires_image=true and image_prompt for wound/rash/medication/insurance questions.
        """,
        agent=question_agent,
        expected_output="JSON with questionnaire",
        context=[dedup_task, summarize_task],
    )

    crew = Crew(
        agents=[dedup_agent, summarize_agent, question_agent],
        tasks=[dedup_task, summarize_task, question_task],
        process=Process.sequential,
        verbose=False,
    )

    async with log_ai_call(
        feature="question_generation",
        input_data={"patient_id": request.patient_id, "endpoint": "legacy"},
        model=GEMINI_MODEL,
        patient_id=request.patient_id,
    ) as log_output:
        result = crew.kickoff(inputs={"patient_data": [patient_data]})
        try:
            questions = [_normalize_question(q) for q in _extract_questions(result)]
        except Exception as e:
            print(f"Error processing questionnaire: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
        log_output["question_count"] = len(questions)
        log_output["requires_image_count"] = sum(1 for q in questions if q.get("requires_image"))

    return {"questions": questions, "patient_id": request.patient_id}


@app.post("/generate-questionnaire")
async def generate_dynamic_questionnaire(request: QuestionnaireGenerationRequest):
    """
    Generate a dynamic questionnaire based on current visit context.
    Called from the React frontend when creating a new visit.
    """
    print(f"Generating questionnaire for {request.patient_id} — Visit: {request.visit_id}")

    patient_data = next(
        (p for p in ALL_PATIENT_DATA if p["patient_id"] == request.patient_id), None
    )
    if not patient_data:
        raise HTTPException(status_code=404, detail=f"Patient {request.patient_id} not found")

    merged_data = {
        "patient_id": request.patient_id,
        "history": patient_data.get("history", {}),
        "visits": patient_data.get("visits", []),
        "current_visit": {
            "visit_id": request.visit_id,
            "conditions": request.conditions,
            "medications": request.medications,
            "allergies": request.allergies,
            "issues_detected": request.issues_detected,
            "clinical_provider_note": request.clinical_provider_note,
        },
    }

    dedup_agent, summarize_agent, question_agent = create_agents()

    dedup_task = Task(
        description=f"""
        Analyze this patient data including their history and current visit:
        {json.dumps(merged_data)}

        Focus on the current_visit data and recent visit history.
        Remove duplicate information across visits.
        Output JSON with deduplicated information focusing on changes and new developments.
        """,
        agent=dedup_agent,
        expected_output="JSON with deduplicated current visit information",
    )

    summarize_task = Task(
        description="""
        Use the deduplicated data from the previous task.

        Identify:
        1. Key problems and conditions that need follow-up
        2. Changes in patient status since last visit
        3. Medication adherence concerns
        4. New symptoms or issues
        5. Risk factors requiring monitoring

        Output JSON with categorized problems and areas needing patient input.
        """,
        agent=summarize_agent,
        expected_output="JSON with problems requiring patient questionnaire",
        context=[dedup_task],
    )

    question_task = Task(
        description=f"""
        Use the previous outputs to generate a personalized patient questionnaire.

        Patient demographics:
        - Age: {merged_data['history'].get('age', 'Unknown')}
        - Sex: {merged_data['history'].get('sex', 'Unknown')}

        Generate 3-8 targeted questions that:
        1. Assess current symptoms and their severity
        2. Monitor medication adherence and side effects
        3. Screen for complications related to their conditions
        4. Gather lifestyle/behavioral information relevant to their care

        Use validated question formats when appropriate (e.g., PHQ-9 for depression, pain scales).

        For questions where a photo would substantially aid clinical assessment (e.g., wounds,
        skin conditions, medication bottles, insurance cards), set requires_image to true and
        provide a concise image_prompt instructing the patient what photo to take.

        Output JSON with this EXACT structure:
        {{
            "questions": [
                {{
                    "id": "q1",
                    "question": "Question text here?",
                    "type": "text|scale|radio|checkbox|multiline",
                    "source": "Clinical reasoning or standard scale name",
                    "rationale": "Why this question is relevant",
                    "required": true,
                    "options": ["option1", "option2"],
                    "requires_image": false,
                    "image_prompt": ""
                }}
            ]
        }}

        Set requires_image to true and provide a short image_prompt for any question
        where a photo of a wound, rash, medication bottle, or insurance card would
        meaningfully improve the clinical answer. Otherwise set both to false/empty.
        """,
        agent=question_agent,
        expected_output="JSON with questions array including requires_image and image_prompt per question",
        context=[dedup_task, summarize_task],
    )

    crew = Crew(
        agents=[dedup_agent, summarize_agent, question_agent],
        tasks=[dedup_task, summarize_task, question_task],
        process=Process.sequential,
        verbose=True,
    )

    print("Running CrewAI pipeline...")
    async with log_ai_call(
        feature="question_generation",
        input_data={
            "patient_id": request.patient_id,
            "visit_id": request.visit_id,
            "conditions": request.conditions,
            "endpoint": "generate-questionnaire",
        },
        model=GEMINI_MODEL,
        patient_id=request.patient_id,
    ) as log_output:
        result = crew.kickoff(inputs={"patient_data": merged_data})
        print("CrewAI pipeline completed")
        try:
            questions = [_normalize_question(q) for q in _extract_questions(result)]
        except Exception as e:
            print(f"Error processing questionnaire: {str(e)}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")
        log_output["question_count"] = len(questions)
        log_output["requires_image_count"] = sum(1 for q in questions if q.get("requires_image"))
        log_output["questions_preview"] = [q.get("question", "")[:120] for q in questions]

    print(f"Generated {len(questions)} questions")
    return {
        "questions": questions,
        "patient_id": request.patient_id,
        "visit_id": request.visit_id,
    }


# ─────────────────────────────────────────────
# Routes — multimodal (TTS / STT / Vision)
# ─────────────────────────────────────────────

@app.post("/tts")
async def text_to_speech(request: TTSRequest):
    """
    Convert question text to speech.
    Returns an mp3 audio stream using Google Cloud TTS (Chirp3 HD voice).
    """
    voice_name = request.voice or os.getenv("GEMINI_TTS_VOICE", "en-US-Chirp3-HD-Aoede")

    async with log_ai_call(
        feature="tts",
        input_data={"text_length": len(request.text), "voice": voice_name},
        model=voice_name,
    ) as log_output:
        synthesis_input = texttospeech.SynthesisInput(text=request.text)
        voice_params = texttospeech.VoiceSelectionParams(
            language_code="en-US",
            name=voice_name,
        )
        audio_config = texttospeech.AudioConfig(
            audio_encoding=texttospeech.AudioEncoding.MP3,
        )
        tts_response = await asyncio.to_thread(
            _tts_client.synthesize_speech,
            input=synthesis_input,
            voice=voice_params,
            audio_config=audio_config,
        )
        audio_bytes = tts_response.audio_content
        log_output["audio_bytes"] = len(audio_bytes)

    return StreamingResponse(
        iter([audio_bytes]),
        media_type="audio/mpeg",
        headers={"Content-Disposition": "inline; filename=speech.mp3"},
    )


@app.post("/stt")
async def speech_to_text(audio: UploadFile = File(...)):
    """
    Transcribe patient speech to text.
    Accepts audio/webm;codecs=opus (from browser MediaRecorder) or audio/mp4.
    Returns { transcript, confidence }.
    """
    audio_bytes = await audio.read()

    async with log_ai_call(
        feature="stt",
        input_data={
            "audio_bytes": len(audio_bytes),
            "content_type": audio.content_type,
        },
        model="chirp_2",
    ) as log_output:
        config = cloud_speech.RecognitionConfig(
            auto_decoding_config=cloud_speech.AutoDetectDecodingConfig(),
            language_codes=["en-US"],
            model="chirp_2",
            features=cloud_speech.RecognitionFeatures(
                enable_word_confidence=True,
                enable_automatic_punctuation=True,
            ),
        )
        stt_request = cloud_speech.RecognizeRequest(
            recognizer=(
                f"projects/{_GCP_PROJECT}/locations/{_GCP_LOCATION}/recognizers/_"
            ),
            config=config,
            content=audio_bytes,
        )
        stt_response = await asyncio.to_thread(_stt_client.recognize, request=stt_request)

        transcript = ""
        confidence = 0.0
        if stt_response.results:
            best_alternative = stt_response.results[0].alternatives[0]
            transcript = best_alternative.transcript
            confidence = round(best_alternative.confidence, 3)

        log_output.update({"transcript": transcript, "confidence": confidence})

    return {"transcript": transcript, "confidence": confidence}


@app.post("/analyze-image")
async def analyze_image(request: ImageAnalysisRequest):
    """
    Describe a patient-submitted photo in clinical terms.
    Accepts a base64-encoded image (JPEG) and the question that prompted the photo.
    Returns { description }.
    """
    _MAX_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB decoded limit
    try:
        image_bytes = base64.b64decode(request.image_base64, validate=True)
    except Exception:
        raise HTTPException(status_code=400, detail="image_base64 is not valid base64")
    if len(image_bytes) > _MAX_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Image too large (max 10 MB)")

    async with log_ai_call(
        feature="image_analysis",
        input_data={
            "image_bytes": len(image_bytes),
            "question": request.question,
        },
        model=GEMINI_MODEL,
        patient_id=request.patient_id,
        question_id=request.question_id,
    ) as log_output:
        vision_model = GenerativeModel(GEMINI_MODEL)
        image_part = Part.from_data(data=image_bytes, mime_type="image/jpeg")
        prompt = (
            f'A patient submitted this photo in response to the check-in question: '
            f'"{request.question}"\n\n'
            "Describe only what is clinically relevant in the image. "
            "Be concise (2–4 sentences). Do not speculate beyond what is visible. "
            "Output plain text only — no markdown, no bullet points."
        )
        vision_response = await asyncio.to_thread(
            vision_model.generate_content, [image_part, prompt]
        )
        description = vision_response.text.strip()
        log_output["description"] = description

    return {"description": description}


# ─────────────────────────────────────────────
# Entry point
# ─────────────────────────────────────────────

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
