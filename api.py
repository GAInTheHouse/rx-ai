import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, Any, List
from crewai import Agent, Task, Crew, Process
from dotenv import load_dotenv
import os
import uvicorn

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

app = FastAPI(title="Rx-AI Questionnaire API", version="1.0.0")

# Enable CORS for React frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://localhost:3000"],  # Vite default port + common React port
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Load full patient data once at startup
# Use dynamic path resolution
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
input_file = os.path.join(BASE_DIR, "data", "final_merged_patient_data.json")

try:
    with open(input_file, "r") as f:
        ALL_PATIENT_DATA = json.load(f)
    print(f"🚀 Loaded {len(ALL_PATIENT_DATA)} patients into memory")
except FileNotFoundError:
    print(f"⚠️  Warning: Patient data file not found at {input_file}")
    ALL_PATIENT_DATA = []

# Your 3 agents (unchanged)
def create_agents():
    return [
        Agent(role="Medical Data Deduplicator", goal="Deduplicate notes", backstory="EHR expert", verbose=False),
        Agent(role="Healthcare Data Summarizer", goal="Extract problems", backstory="Clinical grouping expert", verbose=False),
        Agent(role="Patient Questionnaire Generator", goal="Generate questions", backstory="Questionnaire expert", verbose=False)
    ]

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

# HTML UI Page - Simple test interface
@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    patient_count = len(ALL_PATIENT_DATA)
    
    html_content = """
    <!DOCTYPE html>
    <html>
    <head>
        <title>Rx-AI Questionnaire API</title>
        <style>
            body { font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; background: #f5f5f5; }
            .card { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 4px rgba(0,0,0,0.1); }
            h1 { color: #333; }
            .status { padding: 15px; background: #e7f3ff; border-left: 4px solid #007bff; margin: 20px 0; }
            .endpoint { background: #f8f9fa; padding: 15px; margin: 10px 0; border-radius: 5px; }
            code { background: #f4f4f4; padding: 2px 6px; border-radius: 3px; }
        </style>
    </head>
    <body>
        <div class="card">
            <h1>Rx-AI Questionnaire API</h1>
            <div class="status">
                <strong>Status:</strong> API is running ✓<br>
                <strong>Patients loaded:</strong> """ + str(patient_count) + """
            </div>
            
            <h2>Available Endpoints</h2>
            
            <div class="endpoint">
                <strong>GET /patients</strong><br>
                List all patients in the system
            </div>
            
            <div class="endpoint">
                <strong>POST /generate-questionnaire</strong><br>
                Generate dynamic questionnaire for a visit<br>
                <small>Used by React frontend</small>
            </div>
            
            <div class="endpoint">
                <strong>POST /questionnaire</strong><br>
                Generate questionnaire from stored patient data
            </div>
            
            <h3>Quick Test</h3>
            <p>Test the API using curl:</p>
            <code style="display: block; padding: 10px; overflow-x: auto;">
curl -X GET http://localhost:8000/patients
            </code>
            
            <p style="margin-top: 30px;">
                <strong>Documentation:</strong> See README_API.md for full details<br>
                <strong>React Frontend:</strong> http://localhost:5173 (when running)
            </p>
        </div>
    </body>
    </html>
    """
    return HTMLResponse(content=html_content)

# Keep your existing API endpoints
@app.get("/patients")
async def list_patients():
    return [{"patient_id": p["patient_id"], "age": p["history"]["age"], "sex": p["history"]["sex"]} 
            for p in ALL_PATIENT_DATA]

@app.post("/questionnaire")
async def get_questionnaire(request: PatientRequest):
    """Legacy endpoint - generates questionnaire from stored patient data only"""
    patient_data = next((p for p in ALL_PATIENT_DATA if p["patient_id"] == request.patient_id), None)
    if not patient_data:
        raise HTTPException(status_code=404, detail=f"Patient {request.patient_id} not found")
    
    dedup_agent, summarize_agent, question_agent = create_agents()
    
    # Create tasks with proper context linking
    dedup_task = Task(
        description=f"""
        Process this patient data: {json.dumps(patient_data)}
        
        Remove duplicate sentences from clinical notes.
        Output JSON with deduplicated_notes field.
        """,
        agent=dedup_agent,
        expected_output="JSON with deduplicated_notes"
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
        context=[dedup_task]
    )
    
    question_task = Task(
        description="""
        Use the previous outputs.
        Generate 1-3 questions per problem.
        Output JSON with questionnaire containing questions array.
        Each question should have: id, question, type, source, rationale
        """,
        agent=question_agent,
        expected_output="JSON with questionnaire",
        context=[dedup_task, summarize_task]
    )
    
    crew = Crew(
        agents=[dedup_agent, summarize_agent, question_agent],
        tasks=[dedup_task, summarize_task, question_task],
        process=Process.sequential,
        verbose=False
    )
    
    result = crew.kickoff(inputs={'patient_data': [patient_data]})
    
    try:
        # Parse CrewAI output
        if hasattr(result, "raw") and result.raw:
            try:
                parsed = json.loads(result.raw)
            except:
                parsed = result.raw
        elif hasattr(result, "output") and result.output:
            parsed = result.output
        else:
            parsed = result
        
        # Handle nested structures
        while isinstance(parsed, list) and len(parsed) == 1:
            parsed = parsed[0]
        
        if isinstance(parsed, dict):
            questionnaire = parsed.get("questionnaire", {})
        else:
            raise ValueError("Unexpected output format")
        
        # Ensure questionnaire has questions array
        if isinstance(questionnaire, dict):
            questions = questionnaire.get("questions", [])
        elif isinstance(questionnaire, list):
            questions = questionnaire
        else:
            questions = []
        
        return {
            "questions": questions,
            "patient_id": request.patient_id
        }
    except Exception as e:
        print(f"❌ Error processing questionnaire: {str(e)}")
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@app.post("/generate-questionnaire")
async def generate_dynamic_questionnaire(request: QuestionnaireGenerationRequest):
    """
    NEW ENDPOINT: Generate dynamic questionnaire based on current visit context
    This is called from the frontend when creating a new visit
    """
    print(f"🤖 Generating questionnaire for {request.patient_id} - Visit: {request.visit_id}")
    
    # Find patient in database
    patient_data = next((p for p in ALL_PATIENT_DATA if p["patient_id"] == request.patient_id), None)
    if not patient_data:
        raise HTTPException(status_code=404, detail=f"Patient {request.patient_id} not found")
    
    # Merge stored patient history with new visit data
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
            "clinical_provider_note": request.clinical_provider_note
        }
    }
    
    # Create agents
    dedup_agent, summarize_agent, question_agent = create_agents()
    
    # Create tasks
    dedup_task = Task(
        description=f"""
        Analyze this patient data including their history and current visit:
        {json.dumps(merged_data)}
        
        Focus on the current_visit data and recent visit history.
        Remove duplicate information across visits.
        Output JSON with deduplicated information focusing on changes and new developments.
        """,
        agent=dedup_agent,
        expected_output="JSON with deduplicated current visit information"
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
        context=[dedup_task]
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
                    "options": ["option1", "option2"] (only for radio/checkbox)
                }}
            ]
        }}
        """,
        agent=question_agent,
        expected_output="JSON with questions array",
        context=[dedup_task, summarize_task]
    )
    
    crew = Crew(
        agents=[dedup_agent, summarize_agent, question_agent],
        tasks=[dedup_task, summarize_task, question_task],
        process=Process.sequential,
        verbose=True  # Enable verbose for debugging
    )
    
    print("⏳ Running CrewAI pipeline...")
    result = crew.kickoff(inputs={'patient_data': merged_data})
    print("✅ CrewAI pipeline completed")
    
    try:
        # Parse CrewAI output
        if hasattr(result, "raw") and result.raw:
            try:
                parsed = json.loads(result.raw)
            except:
                parsed = result.raw
        elif hasattr(result, "output") and result.output:
            parsed = result.output
        else:
            parsed = result
        
        # Unwrap nested structures
        while isinstance(parsed, list) and len(parsed) == 1:
            parsed = parsed[0]
        
        # Extract questions
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
        
        print(f"📋 Generated {len(questions)} questions")
        
        return {
            "questions": questions,
            "patient_id": request.patient_id,
            "visit_id": request.visit_id
        }
        
    except Exception as e:
        print(f"❌ Error processing questionnaire: {str(e)}")
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
