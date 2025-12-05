import json
from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import HTMLResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from typing import Dict, Any
from crewai import Agent, Task, Crew, Process
from dotenv import load_dotenv
import os
import uvicorn

load_dotenv()
os.environ["OPENAI_API_KEY"] = os.getenv("OPENAI_API_KEY")

app = FastAPI(title="Rx-AI Questionnaire API", version="1.0.0")

# Load full patient data once at startup
input_file = "/Users/rushin/Columbia/rx-ai/data/final_merged_patient_data.json"
with open(input_file, "r") as f:
    ALL_PATIENT_DATA = json.load(f)

print(f"🚀 Loaded {len(ALL_PATIENT_DATA)} patients into memory")

# Your 3 agents (unchanged)
def create_agents():
    return [
        Agent(role="Medical Data Deduplicator", goal="Deduplicate notes", backstory="EHR expert", verbose=False),
        Agent(role="Healthcare Data Summarizer", goal="Extract problems", backstory="Clinical grouping expert", verbose=False),
        Agent(role="Patient Questionnaire Generator", goal="Generate questions", backstory="Questionnaire expert", verbose=False)
    ]

class PatientRequest(BaseModel):
    patient_id: str

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
    patient_data = next((p for p in ALL_PATIENT_DATA if p["patient_id"] == request.patient_id), None)
    if not patient_data:
        raise HTTPException(status_code=404, detail=f"Patient {request.patient_id} not found")
    
    agents = create_agents()
    tasks = [
        Task(description=f"Process ONLY: {json.dumps(patient_data)} Output JSON with deduplicated_notes", 
             agent=agents[0], expected_output="JSON"),
        Task(description="Input: previous. Output JSON with problems/Ungrouped_data", 
             agent=agents[1], expected_output="JSON", context=[tasks[0]]),
        Task(description="Input: previous. Extract ONLY questionnaire JSON", 
             agent=agents[2], expected_output="JSON", context=[tasks[0], tasks[1]])
    ]
    
    crew = Crew(agents=agents, tasks=tasks, process=Process.sequential, verbose=False)
    result = crew.kickoff(inputs={'patient_data': [patient_data]})
    
    try:
        final_data = result.to_dict() if hasattr(result, 'to_dict') else json.loads(str(result))
        questionnaire = final_data[0]["questionnaire"]
        return questionnaire
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
