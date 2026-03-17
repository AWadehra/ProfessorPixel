# Contract Negotiator — Upgrade Tracker

## Goal: 14 GCP Services, Premium UX, Hackathon-Winning Demo

| # | Feature | GCP Service | Status |
|---|---------|-------------|--------|
| 1 | Contract Heatmap View | — | DONE |
| 2 | Cloud DLP PII Detection | Cloud DLP | DONE |
| 3 | Redline Mode Agent | — | DONE |
| 4 | Google Sheets Export | Sheets API | DONE |
| 5 | Cloud Translation | Translation API | DONE |
| 6 | Animated Score Reveal | — | DONE |
| 7 | Firestore Persistence | Firestore | DONE |
| 8 | Cloud Logging Dashboard | Cloud Logging | DONE |

## GCP Services Used (14)
1. Vertex AI (aiplatform.googleapis.com)
2. Gemini 2.5 Flash (model)
3. ADK (framework)
4. Document AI (documentai.googleapis.com)
5. Cloud TTS (texttospeech.googleapis.com)
6. Google Search (grounding on lawyers)
7. Cloud Storage (storage.googleapis.com)
8. Cloud Run (run.googleapis.com) — deployment target
9. Firebase Hosting — frontend deployment target
10. Cloud DLP (dlp.googleapis.com) — PII detection
11. Cloud Translation (translate.googleapis.com) — multi-language
12. Google Sheets (sheets.googleapis.com) — risk matrix export
13. Firestore (firestore.googleapis.com) — analysis persistence
14. Cloud Logging (logging.googleapis.com) — observability

## Agent Pipeline (6 agents, 5 ADK patterns)
1. ClauseExtractor (LlmAgent, output_schema=ContractClauses)
2. DualAnalysis (ParallelAgent)
   - BuyerLawyer (LlmAgent, google_search, output_schema=LawyerAnalysis)
   - SellerLawyer (LlmAgent, google_search, output_schema=LawyerAnalysis)
3. DebateRounds (LoopAgent, max 3 rounds)
   - BuyerRebuttal (LlmAgent, output_schema=Rebuttal)
   - SellerRebuttal (LlmAgent, output_schema=Rebuttal)
   - DebateTracker (Custom BaseAgent)
4. Mediator (LlmAgent, output_schema=FinalReport)
5. Redliner (LlmAgent, output_schema=RedlinedContract)

## Frontend Features
- Contract heatmap with clause-level risk coloring
- PII detection banner (Cloud DLP)
- Language auto-detection with translation offer
- Split-screen lawyer debate
- Progressive disclosure (expandable sections)
- Redlined contract with side-by-side diff
- Animated score reveal with counting animation
- Text-to-speech with distinct agent voices
- Export to Google Sheets
- Export to PDF (print)
- Dark/light theme toggle
- Auto-save to Firestore
- Analysis history
