# 🏗️ Smart Building AI Assistant — Visual Conception Guide

> **Project Goal:** A fully local, multi-agent AI system that ingests Smart Building documents and provides intelligent Q&A, summaries, and anomaly detection — all orchestrated via n8n.

---

## 1. 🗺️ System Overview (The Big Picture)

```
┌──────────────────────────────────────────────────────────────────────────┐
│                        SMART BUILDING AI SYSTEM                         │
│                                                                         │
│   ┌─────────────┐     ┌──────────────┐     ┌───────────────────────┐   │
│   │  DATA INPUT  │────▶│  PROCESSING  │────▶│   INTELLIGENT LAYER   │   │
│   │             │     │              │     │                       │   │
│   │ • PDFs      │     │ • Extract    │     │ • Route Questions     │   │
│   │ • DOCX      │     │ • Chunk      │     │ • Answer with Sources │   │
│   │ • URLs      │     │ • Embed      │     │ • Summarize Docs      │   │
│   │ • HTML DOMs │     │ • Store      │     │ • Detect Anomalies    │   │
│   └─────────────┘     └──────────────┘     └───────────┬───────────┘   │
│                                                         │               │
│                                              ┌──────────▼──────────┐   │
│                                              │     CHAT UI         │   │
│                                              │  (User Interface)   │   │
│                                              └─────────────────────┘   │
└──────────────────────────────────────────────────────────────────────────┘
```

---

## 2. 🧩 How RAG Works (The Core Idea)

RAG = **Retrieval-Augmented Generation** — you **don't train** the AI on your data. Instead:

```
  YOUR DOCUMENTS                         USER ASKS A QUESTION
  ──────────────                         ────────────────────
       │                                          │
       ▼                                          ▼
  ┌─────────┐                              ┌─────────────┐
  │  CHUNK  │  Split into small pieces     │  EMBED the  │
  │  text   │  (~500 tokens each)          │  question   │
  └────┬────┘                              └──────┬──────┘
       ▼                                          ▼
  ┌─────────┐                              ┌─────────────┐
  │  EMBED  │  Convert to numbers          │  SEARCH for │
  │  chunks │  (vector fingerprints)       │  similar    │
  └────┬────┘                              │  chunks     │
       ▼                                   └──────┬──────┘
  ┌─────────────────┐                            │
  │   VECTOR DB     │◀───── match ──────────────┘
  │   (Qdrant)      │
  │   stores all    │────── top 5 matching chunks
  │   embeddings    │              │
  └─────────────────┘              ▼
                             ┌───────────┐
                             │   LLM     │  "Given these chunks,
                             │ (Ollama)  │   answer the question"
                             └─────┬─────┘
                                   ▼
                            ✅ ANSWER WITH
                               CITATIONS
```

---

## 3. 🤖 The 7 Agents (Who Does What)

```
┌───────────────────────────────────────────────────────────────────────┐
│                         AGENT MAP                                     │
│                                                                       │
│  ╔═══════════════════════════════════════════════╗                    │
│  ║          DATA PIPELINE (Background)           ║                    │
│  ║                                               ║                    │
│  ║  🔍 Agent 1: INGESTION                        ║                    │
│  ║     Extracts text from PDFs, DOCX, URLs       ║                    │
│  ║     Tools: unstructured.io, PyMuPDF           ║                    │
│  ║              │                                ║                    │
│  ║              ▼                                ║                    │
│  ║  🔢 Agent 2: EMBEDDING                        ║                    │
│  ║     Converts text → vectors                   ║                    │
│  ║     Model: all-MiniLM-L6-v2 (local, free)    ║                    │
│  ╚═══════════════════════════════════════════════╝                    │
│                                                                       │
│  ╔═══════════════════════════════════════════════╗                    │
│  ║          QUERY PIPELINE (User-facing)         ║                    │
│  ║                                               ║                    │
│  ║  🛡️ Agent 7: GUARDRAIL ◀── user query         ║                    │
│  ║     Validates input, blocks injections        ║                    │
│  ║              │                                ║                    │
│  ║              ▼                                ║                    │
│  ║  🚦 Agent 3: ROUTER                           ║                    │
│  ║     Classifies intent, picks the right agent  ║                    │
│  ║          ┌───┼───────────┐                    ║                    │
│  ║          ▼   ▼           ▼                    ║                    │
│  ║  💬 QA  📊 Summary  🚨 Anomaly               ║                    │
│  ║  Agent4  Agent5      Agent6                   ║                    │
│  ║  Answer  Summarize   Find issues              ║                    │
│  ║  w/cite  documents   & expired items          ║                    │
│  ╚═══════════════════════════════════════════════╝                    │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 4. 🔄 n8n Workflow Map

```
┌──────────── n8n WORKFLOWS ────────────────────────────────────────────┐
│                                                                       │
│  WORKFLOW 1: INGEST DATA                                              │
│  ┌────────┐   ┌─────────┐   ┌───────┐   ┌───────┐   ┌────────────┐  │
│  │Trigger │──▶│ Extract │──▶│ Chunk │──▶│ Embed │──▶│ Store in   │  │
│  │(file   │   │ Text    │   │ Text  │   │       │   │ Qdrant +   │  │
│  │watcher)│   │         │   │       │   │       │   │ PostgreSQL │  │
│  └────────┘   └─────────┘   └───────┘   └───────┘   └────────────┘  │
│                                                                       │
│  WORKFLOW 2: ANSWER QUESTIONS                                         │
│  ┌────────┐   ┌─────────┐   ┌────────┐   ┌───────┐   ┌───────────┐  │
│  │Webhook │──▶│ Guard-  │──▶│ Route  │──▶│ Agent │──▶│ Return    │  │
│  │(Chat   │   │ rail    │   │ Query  │   │ + LLM │   │ Answer    │  │
│  │ UI)    │   │ Check   │   │        │   │       │   │ to User   │  │
│  └────────┘   └─────────┘   └────────┘   └───────┘   └───────────┘  │
│                                                                       │
│  WORKFLOW 3: DAILY ALERTS                                             │
│  ┌────────┐   ┌──────────────┐   ┌──────────────────┐                │
│  │ Cron   │──▶│ Check for    │──▶│ Send Slack/Email │                │
│  │ 8:00am │   │ expired certs│   │ notification     │                │
│  └────────┘   └──────────────┘   └──────────────────┘                │
│                                                                       │
│  WORKFLOW 4: AUTO-SYNC DOCS                                           │
│  ┌────────┐   ┌──────────────┐   ┌──────────────────┐                │
│  │ Cron   │──▶│ Check folder │──▶│ Re-ingest        │                │
│  │ 6 hrs  │   │ for changes  │   │ updated files    │                │
│  └────────┘   └──────────────┘   └──────────────────┘                │
└───────────────────────────────────────────────────────────────────────┘
```

---

## 5. 🖥️ Tech Stack at a Glance

```
┌─────────────────────────────────────────────────────────────┐
│                     TECH STACK                               │
│                                                              │
│  ┌─── AI & LLM ───────────────────────────────────────────┐ │
│  │  Ollama + Llama 3.1 / Mistral 7B  (local, free, GPU)  │ │
│  │  all-MiniLM-L6-v2                 (embeddings, CPU)    │ │
│  └────────────────────────────────────────────────────────┘ │
│                                                              │
│  ┌─── Storage ─────────────────────────────────────────────┐│
│  │  Qdrant (Docker)     → Vector database                  ││
│  │  PostgreSQL          → Metadata, logs, query history    ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─── Backend ─────────────────────────────────────────────┐│
│  │  Python + FastAPI    → Agent logic, REST API            ││
│  │  unstructured.io     → Document parsing                 ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─── Orchestration ───────────────────────────────────────┐│
│  │  n8n (self-hosted)   → Workflows, scheduling, webhooks  ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─── Frontend ────────────────────────────────────────────┐│
│  │  Chainlit or Next.js → Chat UI                          ││
│  └─────────────────────────────────────────────────────────┘│
│                                                              │
│  ┌─── Infrastructure ──────────────────────────────────────┐│
│  │  Docker Compose      → All services in one command      ││
│  └─────────────────────────────────────────────────────────┘│
└─────────────────────────────────────────────────────────────┘
```

---

## 6. 📁 Project Folder Structure

```
smart-building-ai/
│
├── docker-compose.yml              ← Launches everything
├── .env                            ← Secrets (NEVER in Git!)
│
├── services/
│   ├── ingestion/                  ← 🔍 Agent 1
│   │   ├── parsers/                   PDF, DOCX, HTML parsers
│   │   ├── chunker.py                 Text splitting logic
│   │   └── Dockerfile
│   │
│   ├── embedding/                  ← 🔢 Agent 2
│   │   ├── embedder.py               Vector generation
│   │   └── Dockerfile
│   │
│   ├── agents/                     ← 🧠 Agents 3-7
│   │   ├── router_agent.py           🚦 Query routing
│   │   ├── qa_agent.py               💬 Q&A with citations
│   │   ├── summary_agent.py          📊 Document summarization
│   │   ├── anomaly_agent.py          🚨 Anomaly detection
│   │   ├── guardrail_agent.py        🛡️ Input/output safety
│   │   └── Dockerfile
│   │
│   └── chat-ui/                    ← 💻 User Interface
│       └── Dockerfile
│
├── n8n/
│   ├── workflows/                  ← Exported workflow JSONs
│   └── docker-compose.override.yml
│
├── data/
│   └── documents/                  ← Drop your PDFs/DOCX here
│
└── docs/
    └── architecture.md             ← This document
```

---

## 7. 🗓️ Implementation Phases

```
PHASE 1: FOUNDATION (Week 1-2)                              🟡 FIRST
├── Docker Compose setup (Qdrant, PostgreSQL, Ollama, n8n)
├── Ingestion service (PDF + DOCX parser)
├── Embedding service
├── n8n ingestion workflow
└── ✅ Test: ingest a PDF → verify chunks in Qdrant

PHASE 2: CORE RAG (Week 3-4)                                🔵 SECOND
├── Q&A Agent (FastAPI endpoint)
├── Vector search + LLM prompting
├── Router Agent (intent classification)
├── Guardrail Agent (input validation)
├── n8n query orchestration workflow
└── ✅ Test: ask questions → get cited answers

PHASE 3: ADVANCED AGENTS (Week 5-6)                         🟣 THIRD
├── Summary Agent
├── Anomaly/Insight Agent
├── URL/HTML scraping in ingestion
├── n8n scheduled alert workflows
└── ✅ Test: summarize docs, detect expired items

PHASE 4: UI + POLISH (Week 7-8)                             🟢 FINAL
├── Chat UI (Chainlit / Next.js)
├── Conversation history
├── Feedback mechanism (thumbs up/down)
└── ✅ Performance tuning (chunk size, top-K, model)
```

---

## 8. 🖥️💻 Task Split: Personal PC vs Mini Mac

Since your Mini Mac is **not available yet**, here is exactly what you can do **right now on your personal PC** to avoid wasting any time:

### ✅ Tasks You CAN Do on Your Personal PC (Now)

| # | Task | Why It Works on PC |
|---|------|--------------------|
| 1 | **Write all Python agent code** (router, Q&A, summary, anomaly, guardrail) | Pure Python — runs anywhere, no Mac dependency |
| 2 | **Write the ingestion parsers** (PDF, DOCX, HTML) | Libraries like `PyMuPDF`, `python-docx`, `BeautifulSoup` are cross-platform |
| 3 | **Write the chunking logic** (`chunker.py`) | Pure algorithm, no hardware dependency |
| 4 | **Write the embedding service** (`embedder.py`) | `sentence-transformers` runs on any CPU |
| 5 | **Write all Dockerfiles** for each service | Dockerfiles are just text files |
| 6 | **Write the `docker-compose.yml`** | YAML config — portable to any machine |
| 7 | **Write the `.env.example`** template | Template with placeholder values |
| 8 | **Design & export n8n workflows** (as JSON) | n8n Desktop runs on Windows; export as JSON to import on Mac later |
| 9 | **Write FastAPI endpoints & route handlers** | Pure Python, fully testable on PC |
| 10 | **Write unit tests** for all agents | `pytest` runs on any platform |
| 11 | **Design the Chat UI** (HTML/CSS/JS or Next.js scaffold) | Frontend code is universal |
| 12 | **Write all documentation** (README, API docs, setup guides) | Markdown files |
| 13 | **Set up the Git repository** and push initial code | Git works everywhere |
| 14 | **Collect & organize sample documents** (PDFs, DOCX) into `data/documents/` | File organization |
| 15 | **Research & test LLM prompts** (via Ollama on PC or free API) | Prompt engineering needs no Mac |

### ⏳ Tasks That MUST Wait for the Mini Mac

| # | Task | Why It Needs the Mac |
|---|------|-----------------------|
| 1 | **Deploy the full Docker Compose stack** | Mac will be the production host |
| 2 | **Run Ollama with GPU acceleration** | Mac's Apple Silicon GPU is the target runtime |
| 3 | **Load-test with real document volume** | Need the actual hardware to benchmark |
| 4 | **Configure n8n production workflows** (webhooks, cron triggers) | Must run on the final host |
| 5 | **End-to-end integration testing** | Full stack must run on target hardware |
| 6 | **Network/firewall configuration** | Specific to the Mac's network setup |
| 7 | **Performance tuning** (chunk size, top-K, model selection) | Must benchmark on actual hardware |

### 💡 Recommended PC Work Order

```
On Your PC RIGHT NOW:
─────────────────────
1️⃣  Initialize Git repo + project folder structure
2️⃣  Write docker-compose.yml + all Dockerfiles
3️⃣  Build ingestion service (parsers + chunker)
4️⃣  Build embedding service
5️⃣  Build all agent logic (router, QA, summary, anomaly, guardrail)
6️⃣  Write FastAPI app tying agents together
7️⃣  Write unit tests for each component
8️⃣  Design n8n workflows (install n8n Desktop on Windows)
9️⃣  Scaffold the Chat UI
🔟  Collect sample Smart Building documents

When Mini Mac Arrives:
──────────────────────
1️⃣  Clone repo → docker-compose up
2️⃣  Install Ollama + pull Llama 3.1
3️⃣  Import n8n workflows
4️⃣  Run end-to-end tests
5️⃣  Tune performance
```

---

> [!TIP]
> **Bottom line:** ~80% of the work is pure code that runs on any machine. You can have the entire codebase ready and tested with mocks before the Mac arrives. When it does, it's mostly `git clone` → `docker-compose up` → import n8n → done.
