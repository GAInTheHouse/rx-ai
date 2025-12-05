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

# HTML UI Page (NEW)
@app.get("/", response_class=HTMLResponse)
async def home_page(request: Request):
    patients = [{"patient_id": p["patient_id"], "age": p["history"]["age"], "sex": p["history"]["sex"]} 
                for p in ALL_PATIENT_DATA[:10]]  # Show first 10
    
    html_content = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <title>Rx-AI Questionnaire Generator</title>
        <style>
            body {{ font-family: Arial; max-width: 800px; margin: 50px auto; padding: 20px; }}
            .card {{ background: #f8f9fa; padding: 20px; border-radius: 10px; margin: 20px 0; }}
            input[type="text"] {{ width: 300px; padding: 10px; font-size: 16px; }}
            button {{ padding: 10px 20px; background: #007bff; color: white; border: none; border-radius: 5px; font-size: 16px; }}
            .loading {{ display: none; color: #007bff; }}
            .questions {{ background: white; padding: 20px; border-radius: 10px; margin-top: 20px; }}
            .question {{ margin: 15px 0; padding: 15px; background: #e9ecef; border-radius: 8px; }}
        </style>
    </head>
    <body>
        <h1>🚀 Rx-AI Questionnaire Generator</h1>
        
        <div class="card">
            <h2>Enter Patient ID</h2>
            <input type="text" id="patient_id" placeholder="e.g. P001, P002" value="P001">
            <button onclick="generateQuestionnaire()">Generate Questionnaire</button>
            <div class="loading" id="loading">🔄 Processing with AI... (10-15s)</div>
        </div>
        
        <div id="result"></div>
        
        <div class="card">
            <h3>Available Patients (first 10):</h3>
            <ul>{''.join([f'<li>{p["patient_id"]} (Age {p["age"]}, {p["sex"]})</li>' for p in patients])}</ul>
        </div>

        <script>
        async function generateQuestionnaire() {{
            const patientId = document.getElementById('patient_id').value;
            const loading = document.getElementById('loading');
            const result = document.getElementById('result');
            
            loading.style.display = 'block';
            result.innerHTML = '';
            
            try {{
                const response = await fetch('/questionnaire', {{
                    method: 'POST',
                    headers: {{ 'Content-Type': 'application/json' }},
                    body: JSON.stringify({{ patient_id: patientId }})
                }});
                
                const data = await response.json();
                loading.style.display = 'none';
                
                if (response.ok) {{
                    result.innerHTML = `
                        <div class="card questions">
                            <h2>✅ Questionnaire for ${data.patient_id}</h2>
                            <p><strong>Age:</strong> ${data.patient_age} | <strong>Pronouns:</strong> ${data.pronouns}</p>
                            <p><strong>Total Questions:</strong> ${data.total_questions}</p>
                            ${data.questions.map(q => `
                                <div class="question">
                                    <h4>❓ ${q.question}</h4>
                                    <p><strong>Type:</strong> ${q.type} | <strong>Source:</strong> ${q.source}</p>
                                    <p><small>${q.rationale}</small></p>
                                </div>
                            `).join('')}
                        </div>
                    `;
                }} else {{
                    result.innerHTML = `<div class="card" style="color: red;">❌ Error: ${data.detail}</div>`;
                }}
            }} catch (error) {{
                loading.style.display = 'none';
                result.innerHTML = `<div class="card" style="color: red;">❌ Network error: ${error}</div>`;
            }}
        }}
        </script>
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
