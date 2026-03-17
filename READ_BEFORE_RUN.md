# Contract Negotiator — Setup & Run Guide

## Prerequisites

- Python 3.11+
- A GCP project with the following APIs enabled:
  - Vertex AI
  - Document AI
  - Cloud Text-to-Speech
  - Cloud Storage
  - Cloud DLP
  - Cloud Firestore
  - Cloud Translation
- A service account key JSON with access to the above APIs
- `gcloud` CLI authenticated (`gcloud auth application-default login`)

## 1. Clone & Install

```bash
git clone <repo-url>
cd ProfessorPixel
git checkout daniel/idea

python -m venv .venv
source .venv/bin/activate   # or .venv\Scripts\activate on Windows
pip install -e .
```

## 2. Environment Variables

Create a `.env` file in the project root (it's gitignored):

```env
GOOGLE_CLOUD_PROJECT=your-gcp-project-id
GOOGLE_CLOUD_LOCATION=us-central1
GOOGLE_APPLICATION_CREDENTIALS=path/to/service-account-key.json
```

Check `server.py` lines 54-60 for the full list of env vars it reads.

## 3. Run the Server

```bash
python server.py
```

The app starts on `http://localhost:8080` by default.

Open it in a browser, paste a contract or upload a PDF, and click **Analyze Contract**.

## 4. Project Structure

```
server.py                    # FastAPI server (SSE streaming, file upload, TTS, exports)
contract_negotiator/
  __init__.py                # Wires all agents into the pipeline
  agent.py                   # Root SequentialAgent definition
  agents/                    # Individual AI agents (clause extractor, lawyers, debate, mediator, redliner)
  models/schemas.py          # Pydantic schemas (FinalReport, Rebuttal, RedlinedContract, etc.)
  tools/                     # Agent tools
static/
  index.html                 # Single-page frontend
  style.css                  # All styles (Material Design 3 inspired)
  app.js                     # Frontend logic (SSE handling, rendering, stepper, PDF export)
  print.css                  # Print/PDF-specific styles (curated report)
```

## 5. Git Workflow

We work on feature branches off `main`.

```bash
# Create a branch
git checkout -b your-name/feature-name

# Make changes, then commit
git add <files>
git commit -m "Description of changes"

# Push
git push -u origin your-name/feature-name

# Open a PR into main via GitHub
```

**Do not** commit `.env`, service account keys, or any credentials. These are in `.gitignore`.

## 6. Key Tech

| Layer     | Tech                                                    |
|-----------|---------------------------------------------------------|
| Backend   | FastAPI + Uvicorn, Google ADK (Agent Development Kit)   |
| AI        | Gemini 2.5 via Vertex AI, multi-agent pipeline          |
| Frontend  | Vanilla HTML/CSS/JS, Material Symbols icons, Marked.js  |
| GCP       | Document AI, Cloud TTS, Cloud DLP, Firestore, GCS       |
