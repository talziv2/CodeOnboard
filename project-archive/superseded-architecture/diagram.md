# CodeOnboard — End-to-End System Diagram

```mermaid
graph TB
    Dev(["Developer"])

    subgraph L1["Layer 1 — UI  (Node.js · Next.js + Tailwind)"]
        NextUI["Goal dialogue<br/>Learning path display<br/>Audio + video players<br/>VS Code extension sidebar"]
    end

    subgraph L2["Layer 2 — Backend API  (FastAPI)"]
        FAPI["POST /goal/start<br/>POST /goal/answer<br/>POST /onboard<br/>POST /ask"]
    end

    subgraph L3["Layer 3 — Orchestrator"]
        Orch["runner.py → LangGraph<br/>sequential chain → stateful graph"]
    end

    subgraph L4["Layer 4 — Agents"]
        GA["Goal Agent<br/>Haiku"]
        CSA["Code Structure Agent<br/>Haiku"]
        PRA["Prioritization Agent<br/>Haiku"]
        DA["Documentation Agent<br/>Haiku"]
        PA["Mentor Agent<br/>Sonnet"]
        MA["Multimedia Agent<br/>ElevenLabs · ffmpeg"]
    end

    subgraph L5["Layer 5 — RAG Pipeline"]
        Cln["Cloner<br/>git clone --depth 1"]
        Parse["Parser + Chunker<br/>tree-sitter AST units"]
        Embed["Embedder + Store<br/>nomic-embed-text-v1.5 (local) → ChromaDB"]
        Ret["Retriever<br/>top-k by goal"]
    end

    subgraph Ext["External Services"]
        Anth["Anthropic API"]
        GH["GitHub API"]
    end

    Dev -->|"GitHub URL + goal"| NextUI
    NextUI --> FAPI
    FAPI --> Orch

    Orch --> GA
    GA --> Anth
    Orch --> CSA
    CSA --> Cln
    Cln --> GH
    Cln --> Parse
    Parse --> Embed

    Orch --> PRA
    PRA --> Anth
    Orch --> DA
    DA --> GH
    DA --> Anth

    Orch --> PA
    PA --> Ret
    Ret --> Embed
    PA --> Anth

    Orch --> MA

    FAPI -->|"learning path JSON"| NextUI
    NextUI -->|"display steps"| Dev
```

## Component summary

| Layer | Component | Notes |
|---|---|---|
| UI | Next.js + Tailwind | Node.js runtime; goal dialogue, learning path, audio/video, VS Code extension |
| API | FastAPI | `/ask` endpoint for VS Code inline Q&A |
| Orchestrator | runner.py → LangGraph | Plain chain in Phase 1; migrated to LangGraph for conditional routing + retries |
| Agent | Goal Agent | Multi-turn dialogue → goal JSON; Haiku |
| Agent | Code Structure Agent | Clone + parse → module map + embed repo; Haiku |
| Agent | Prioritization Agent | Filter irrelevant modules before Mentor Agent; Haiku |
| Agent | Documentation Agent | Extract README/docstrings, enrich steps with real quotes; Haiku |
| Agent | Mentor Agent | Goal + filtered map + RAG → learning path; Sonnet (one call) |
| Agent | Multimedia Agent | Learning path text → TTS audio + code walkthrough video |
| RAG | Cloner | `git clone --depth 1` |
| RAG | Parser + Chunker | tree-sitter AST; chunks by function/class, never by line window |
| RAG | Embedder + Store | `nomic-embed-text-v1.5` via sentence-transformers (local) → ChromaDB; skip if collection exists |
| RAG | Retriever | Query by `goal.primary_goal`; return top-k to Mentor Agent |
