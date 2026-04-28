## rx-ai

Rx-AI is a multimodal patient check-in prototype:
- **Question generation** (Gemini 2.5 Flash) → personalized questionnaires
- **TTS**: read questions aloud
- **STT**: capture spoken answers
- **Vision**: describe patient-submitted photos for clinically relevant context

See `README_API.md` and `README_EVAL.md` for setup and evaluation.

## CrewAI (3-agent) vs single-pass Gemini

The system currently supports two questionnaire generation modes:

- **Default (used by the React frontend)**: `POST /generate-questionnaire`  
  This runs the **CrewAI 3-agent sequential pipeline** (dedup → summarize → generate).
- **Baseline (comparison)**: `POST /generate-questionnaire-singlepass`  
  This runs a **single Gemini call** that returns the same response shape.

### Latency

- **Single-pass is faster** in practice because it makes **1 model call** vs **3 sequential model calls** for CrewAI.

### Quality trade-offs (based on observed outputs)

- **CrewAI strengths**:
  - Tends to ask **broader, safer intake questions** when visit context is sparse.
  - More likely to include “catch-all” questions (sleep, activity, mental health) and explicit **photo requests** when appropriate.
- **Single-pass strengths**:
  - Tends to be **more direct and condition-focused**, producing fewer “generic intake” questions.
- **Single-pass risk**:
  - Higher risk of **implicit assumptions** when structured context is missing. For example, single-pass can mention specific medications even when `medications: []` was provided (plausible inference from conditions, but still an assumption).

### Recommendation (current default)

Keep **CrewAI** as the default for now (frontend uses `/generate-questionnaire`) until we add stricter grounding rules / JSON validation for the single-pass path. Use the single-pass endpoint when you need lower latency and can tolerate more assumption risk.

