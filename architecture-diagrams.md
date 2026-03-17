# Contract Negotiator — Architecture Diagrams

## 1. High-Level Pipeline

```mermaid
graph TD
    A[User uploads contract] --> B[Document AI OCR]
    B --> C[Cloud DLP PII Scan]
    C --> D[Cloud Translation auto-detect]
    D --> E[ClauseExtractor Agent]
    E --> F[Parallel Analysis]
    F --> G[3-Round Adversarial Debate]
    G --> H[Mediator Verdict]
    H --> I[Redliner Agent]
    I --> J[Results Dashboard]
    J --> K[Google Sheets Export]
    J --> L[Firestore Save]
    J --> M[Cloud TTS Playback]

    style A fill:#818cf8,color:#fff
    style E fill:#a78bfa,color:#fff
    style F fill:#a78bfa,color:#fff
    style G fill:#a78bfa,color:#fff
    style H fill:#a78bfa,color:#fff
    style I fill:#a78bfa,color:#fff
    style J fill:#34d399,color:#fff
```

## 2. Detailed Agent Architecture

```mermaid
graph TD
    USER[User Input] --> UPLOAD{Upload Method}
    UPLOAD -->|Photo or PDF| DOCAI[Document AI OCR Processor]
    UPLOAD -->|Paste text| LANG[Cloud Translation Language Detection]
    DOCAI --> GCS[Cloud Storage Bucket]
    DOCAI --> LANG
    LANG -->|Non-English| TRANSLATE[Cloud Translation API]
    LANG -->|English| DLP[Cloud DLP PII Scanner]
    TRANSLATE --> DLP

    DLP --> CE[ClauseExtractor - LlmAgent]
    CE -->|ContractClauses JSON| DUAL[DualAnalysis - ParallelAgent]

    DUAL --> BL[BuyerLawyer - LlmAgent]
    DUAL --> SL[SellerLawyer - LlmAgent]

    BL -->|LawyerAnalysis JSON| LOOP[DebateRounds - LoopAgent x3]
    SL -->|LawyerAnalysis JSON| LOOP

    LOOP --> BR[BuyerRebuttal - LlmAgent]
    LOOP --> SR[SellerRebuttal - LlmAgent]
    LOOP --> DT[DebateTracker - Custom BaseAgent]
    BR --> DT
    SR --> DT
    DT -->|round < 3| BR
    DT -->|round = 3 or escalate| MED[Mediator - LlmAgent]

    MED -->|FinalReport JSON| RED[Redliner - LlmAgent]
    RED -->|RedlinedContract JSON| OUTPUT[Frontend Dashboard]

    OUTPUT --> HEATMAP[Contract Heatmap View]
    OUTPUT --> SCORE[Animated Score Reveal]
    OUTPUT --> REDVIEW[Side-by-Side Redline Diff]
    OUTPUT --> TTS[Cloud TTS Agent Voices]
    OUTPUT --> SHEETS[Google Sheets Risk Matrix]
    OUTPUT --> FIRE[Firestore Analysis History]
    OUTPUT --> PDF[PDF Export]

    CE -.->|Gemini 2.5 Flash| VERTEX[Vertex AI]
    BL -.->|Gemini 2.5 Flash| VERTEX
    SL -.->|Gemini 2.5 Flash| VERTEX
    BR -.->|Gemini 2.5 Flash| VERTEX
    SR -.->|Gemini 2.5 Flash| VERTEX
    MED -.->|Gemini 2.5 Flash| VERTEX
    RED -.->|Gemini 2.5 Flash| VERTEX

    style USER fill:#818cf8,color:#fff
    style DOCAI fill:#4285f4,color:#fff
    style GCS fill:#4285f4,color:#fff
    style TRANSLATE fill:#4285f4,color:#fff
    style DLP fill:#4285f4,color:#fff
    style VERTEX fill:#4285f4,color:#fff
    style TTS fill:#4285f4,color:#fff
    style SHEETS fill:#4285f4,color:#fff
    style FIRE fill:#4285f4,color:#fff
    style CE fill:#a78bfa,color:#fff
    style BL fill:#818cf8,color:#fff
    style SL fill:#fb923c,color:#fff
    style BR fill:#818cf8,color:#fff
    style SR fill:#fb923c,color:#fff
    style DT fill:#a78bfa,color:#fff
    style MED fill:#a78bfa,color:#fff
    style RED fill:#a78bfa,color:#fff
    style DUAL fill:#a78bfa,color:#fff
    style LOOP fill:#a78bfa,color:#fff
    style OUTPUT fill:#34d399,color:#fff
```

## 3. Google Cloud Services Map

```mermaid
graph TD
    PROJECT[GCP Project] --> AI[AI and ML]
    PROJECT --> STORAGE[Storage and Data]
    PROJECT --> INFRA[Infrastructure]
    PROJECT --> INTEGRATION[Integration]

    AI --> VERTEX[Vertex AI - Model hosting]
    AI --> GEMINI[Gemini 2.5 Flash - 7 agents]
    AI --> ADK[Agent Development Kit - Pipeline orchestration]
    AI --> DOCAI2[Document AI - Contract OCR]
    AI --> TRANS[Cloud Translation - Multi-language]
    AI --> DLPAPI[Cloud DLP - PII detection]
    AI --> TTSAPI[Cloud TTS - Agent voices]

    STORAGE --> GCS2[Cloud Storage - File uploads]
    STORAGE --> FIREDB[Firestore - Analysis history]

    INFRA --> RUN[Cloud Run - Backend hosting]
    INFRA --> FIREBASE[Firebase Hosting - Frontend]
    INFRA --> LOGGING[Cloud Logging - Observability]

    INTEGRATION --> SHEETSAPI[Google Sheets API - Risk matrix export]

    style PROJECT fill:#202124,color:#fff
    style AI fill:#a78bfa,color:#fff
    style STORAGE fill:#818cf8,color:#fff
    style INFRA fill:#34d399,color:#fff
    style INTEGRATION fill:#fb923c,color:#fff
    style VERTEX fill:#7c3aed,color:#fff
    style GEMINI fill:#7c3aed,color:#fff
    style ADK fill:#7c3aed,color:#fff
    style DOCAI2 fill:#7c3aed,color:#fff
    style TRANS fill:#7c3aed,color:#fff
    style DLPAPI fill:#7c3aed,color:#fff
    style TTSAPI fill:#7c3aed,color:#fff
    style GCS2 fill:#6366f1,color:#fff
    style FIREDB fill:#6366f1,color:#fff
    style RUN fill:#059669,color:#fff
    style FIREBASE fill:#059669,color:#fff
    style LOGGING fill:#059669,color:#fff
    style SHEETSAPI fill:#ea580c,color:#fff
```

## 4. ADK Agent Patterns Used

```mermaid
graph LR
    SEQ[SequentialAgent - ContractNegotiator] --> S1[LlmAgent - ClauseExtractor]
    SEQ --> S2[ParallelAgent - DualAnalysis]
    SEQ --> S3[LoopAgent - DebateRounds]
    SEQ --> S4[LlmAgent - Mediator]
    SEQ --> S5[LlmAgent - Redliner]

    S2 --> P1[LlmAgent - BuyerLawyer]
    S2 --> P2[LlmAgent - SellerLawyer]

    S3 --> L1[LlmAgent - BuyerRebuttal]
    S3 --> L2[LlmAgent - SellerRebuttal]
    S3 --> L3[Custom BaseAgent - DebateTracker]

    style SEQ fill:#a78bfa,color:#fff
    style S2 fill:#34d399,color:#fff
    style S3 fill:#fb923c,color:#fff
    style L3 fill:#f87171,color:#fff
    style S1 fill:#818cf8,color:#fff
    style S4 fill:#818cf8,color:#fff
    style S5 fill:#818cf8,color:#fff
    style P1 fill:#818cf8,color:#fff
    style P2 fill:#818cf8,color:#fff
    style L1 fill:#818cf8,color:#fff
    style L2 fill:#818cf8,color:#fff
```

## 5. Data Flow and State Passing

```mermaid
graph TD
    INPUT[User Contract Text] -->|user message| CE2[ClauseExtractor]
    CE2 -->|state: clauses| BL2[BuyerLawyer]
    CE2 -->|state: clauses| SL2[SellerLawyer]

    BL2 -->|state: buyer_analysis| BR2[BuyerRebuttal Round 1]
    SL2 -->|state: seller_analysis| SR2[SellerRebuttal Round 1]

    BR2 -->|state: buyer_rebuttal| DT2[DebateTracker]
    SR2 -->|state: seller_rebuttal| DT2
    DT2 -->|state: debate_history| BR3[BuyerRebuttal Round 2]
    DT2 -->|state: debate_round| SR3[SellerRebuttal Round 2]

    BR3 --> DT3[DebateTracker]
    SR3 --> DT3
    DT3 --> BR4[BuyerRebuttal Round 3]
    DT3 --> SR4[SellerRebuttal Round 3]
    BR4 --> DT4[DebateTracker]
    SR4 --> DT4
    DT4 -->|escalate = true| MED2[Mediator]

    MED2 -->|state: final_report| RED2[Redliner]
    RED2 -->|state: redlined_contract| DONE[Analysis Complete]

    style INPUT fill:#818cf8,color:#fff
    style CE2 fill:#a78bfa,color:#fff
    style BL2 fill:#818cf8,color:#fff
    style SL2 fill:#fb923c,color:#fff
    style MED2 fill:#a78bfa,color:#fff
    style RED2 fill:#a78bfa,color:#fff
    style DONE fill:#34d399,color:#fff
```
