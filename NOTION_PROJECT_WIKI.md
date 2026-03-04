# 🏗️ Smart Building AI Assistant — Project Wiki

> **Status:** 🟡 Architecture & Conception Phase
> **Started:** March 2026
> **Target Platform:** Mini Mac (Apple Silicon)
> **Development Machine:** Windows PC (pre-deployment work)

---

# 📌 Table of Contents

1. [Project Overview](#-1-project-overview)
2. [What is RAG?](#-2-what-is-rag)
3. [MVP Scope Definition](#-3-mvp-scope-definition)
4. [System Architecture (MVP)](#-4-system-architecture-mvp)
5. [The Agents — MVP vs Secondary](#-5-the-agents--mvp-vs-secondary)
6. [n8n Workflows](#-6-n8n-workflows)
7. [Tech Stack](#-7-tech-stack)
8. [Project Folder Structure](#-8-project-folder-structure)
9. [Implementation Roadmap (MVP-First)](#-9-implementation-roadmap-mvp-first)
10. [PC vs Mac Task Split](#-10-pc-vs-mac-task-split)
11. [Kanban Board Setup](#-11-kanban-board-setup)
12. [Key Decisions Log](#-12-key-decisions-log)

---

# 📋 1. Project Overview

## What Are We Building?

A **local, privacy-first AI assistant** for Smart Building management. The system ingests building documents (PDFs, DOCX files) and allows users to **ask questions and get accurate, cited answers** through a chat interface.

## Why Local?

Smart Building data often contains sensitive information (blueprints, access codes, certifications). By keeping everything local on a Mini Mac, **no data ever leaves the network**.

## Core Value Proposition

| Without This System | With This System |
|---------------------|------------------|
| Manually search through hundreds of PDFs | Ask a question in natural language |
| Miss expired certifications | Get automated alerts |
| No centralized knowledge | Single source of truth with citations |

---

# 🧠 2. What is RAG?

**RAG = Retrieval-Augmented Generation** — the industry standard for "AI over local data."

> **Key Insight:** We do NOT train/fine-tune an LLM on our data. Instead, we search for relevant document pieces and pass them to the LLM as context.

### How It Works (Step by Step)

```
STEP 1 — INGESTION (One-time per document)
   Document → Extract Text → Split into Chunks → Convert to Vectors → Store

STEP 2 — QUERY (Every time a user asks a question)
   Question → Convert to Vector → Find Similar Chunks → Send to LLM → Answer with Citations
```

### Why RAG Over Fine-Tuning?

| Criteria | RAG ✅ | Fine-Tuning ❌ |
|----------|--------|----------------|
| Cost | Free (local models) | Expensive (GPU hours) |
| Update data | Add new docs anytime | Must re-train |
| Citations | Can cite exact sources | Cannot cite |
| Hallucination | Lower (grounded in docs) | Higher |
| Time to deploy | Days | Weeks |

---

# 🎯 3. MVP Scope Definition

> **Rule: Ship the MVP first. Everything else is Phase 2+.**

## ✅ MVP — What We Ship First

The MVP answers one question: **"Can a user ask a question about their Smart Building documents and get a correct, cited answer?"**

| Feature | Why It's MVP |
|---------|-------------|
| PDF ingestion | Primary document format in building management |
| DOCX ingestion | Second most common format |
| Text chunking + embedding | Core RAG pipeline — nothing works without this |
| Q&A Agent with citations | **The core product** — answer questions with sources |
| Router Agent (basic) | Directs queries to the right handler |
| Guardrail Agent (input only) | Security — prevents prompt injection (OWASP compliance) |
| Vector DB (Qdrant) | Stores document embeddings |
| Metadata DB (PostgreSQL) | Tracks sources, chunks, ingestion logs |
| n8n ingestion workflow | Automates document processing |
| n8n query workflow | Handles the question-answer pipeline |
| Basic Chat UI | Users need an interface to interact with the AI |
| Docker Compose | All services must run with one command |

## ❌ NOT MVP — Secondary / Nice-to-Have (Phase 2+)

| Feature | Why It's Deferred | Phase |
|---------|-------------------|-------|
| Summary Agent | Useful but not core — users can ask specific questions first | Phase 2 |
| Anomaly/Insight Agent | Advanced feature, needs more structured data | Phase 2 |
| URL/HTML scraping | PDFs and DOCX cover the initial use case | Phase 2 |
| Scheduled alert workflows | Proactive alerts are a luxury until Q&A works | Phase 2 |
| Document auto-sync workflow | Manual re-ingestion is fine for MVP | Phase 2 |
| Guardrail output validation | Input guardrails are enough for MVP | Phase 2 |
| Conversation history | Stateless chat is acceptable for MVP | Phase 3 |
| Feedback mechanism (👍/👎) | Quality improvement feature, not launch-critical | Phase 3 |
| Performance tuning | Optimize after it works | Phase 3 |

---

# 🏛️ 4. System Architecture (MVP)

## High-Level Flow

```
┌──────────────┐     ┌───────────────────────────────────────┐
│  DATA INPUT  │     │         INGESTION PIPELINE            │
│              │     │                                       │
│  📄 PDFs     │────▶│  Extract → Chunk → Embed → Store     │
│  📝 DOCX     │     │         (n8n orchestrated)            │
└──────────────┘     └──────────────────┬────────────────────┘
                                        │
                                        ▼
                     ┌──────────────────────────────────────┐
                     │            STORAGE LAYER             │
                     │                                      │
                     │  🗄️ Qdrant (vectors)                 │
                     │  📋 PostgreSQL (metadata)            │
                     └──────────────────┬───────────────────┘
                                        │
                                        ▼
┌──────────────┐     ┌───────────────────────────────────────┐
│     USER     │     │          QUERY PIPELINE               │
│              │     │                                       │
│  💻 Chat UI  │────▶│  Guard → Route → Q&A Agent → Answer  │
│              │◀────│         (n8n orchestrated)            │
└──────────────┘     └───────────────────────────────────────┘
```

## Agent Interaction Flow (MVP)

```
User sends question via Chat UI
        │
        ▼
  🛡️ GUARDRAIL AGENT
  • Block prompt injection
  • Reject off-topic queries
  • Sanitize input
        │
        ▼
  🚦 ROUTER AGENT
  • Classify intent
  • MVP categories: factual_qa | out_of_scope
        │
        ▼
  💬 Q&A AGENT
  • Embed the question
  • Search Qdrant for top-5 relevant chunks
  • Send chunks + question to LLM
  • Generate answer WITH citations
        │
        ▼
  Chat UI displays:
  "According to [MaintenanceManual.pdf, p.34], the HVAC schedule is..."
```

---

# 🤖 5. The Agents — MVP vs Secondary

## MVP Agents (Build These First)

### 🔍 Agent 1: Ingestion Agent

| Aspect | Detail |
|--------|--------|
| **Job** | Extract text from PDFs and DOCX files |
| **Tools** | `PyMuPDF` (PDFs), `python-docx` (DOCX) |
| **Output** | Clean text chunks with metadata `{source_file, page, chunk_index, date}` |
| **Runs in** | n8n workflow (triggered when files are dropped in `/data/documents/`) |
| **MVP Scope** | PDF + DOCX only |

### 🔢 Agent 2: Embedding Agent

| Aspect | Detail |
|--------|--------|
| **Job** | Convert text chunks into vector embeddings |
| **Model** | `sentence-transformers/all-MiniLM-L6-v2` (local, free, CPU-friendly) |
| **Output** | Vectors stored in Qdrant + metadata logged in PostgreSQL |
| **Runs in** | n8n workflow (chained after Ingestion Agent) |

### 🚦 Agent 3: Router Agent

| Aspect | Detail |
|--------|--------|
| **Job** | Classify user query intent and route to correct agent |
| **MVP Logic** | Two categories only: `factual_qa` → Q&A Agent, `out_of_scope` → reject |
| **Implementation** | LLM-based classification with a system prompt |

### 💬 Agent 4: Q&A Agent (⭐ The Core Product)

| Aspect | Detail |
|--------|--------|
| **Job** | Answer questions using retrieved document chunks |
| **Flow** | Query → embed → vector search (top-5) → LLM generates answer |
| **Key Feature** | Always cites sources: *"According to [file.pdf, page X]..."* |
| **LLM** | Ollama (Llama 3.1 or Mistral 7B) locally |

### 🛡️ Agent 5: Guardrail Agent

| Aspect | Detail |
|--------|--------|
| **Job** | Validate and sanitize user input before processing |
| **MVP Scope** | Input validation only (block injections, off-topic, abusive content) |
| **Deferred** | Output hallucination checking → Phase 2 |

---

## Secondary Agents (Phase 2+)

| Agent | Job | Phase |
|-------|-----|-------|
| 📊 **Summary Agent** | Summarize entire documents or topics using map-reduce | Phase 2 |
| 🚨 **Anomaly Agent** | Cross-reference data to find expired certs, unusual patterns | Phase 2 |
| 🛡️ **Guardrail Output Check** | Validate LLM responses against retrieved chunks | Phase 2 |

---

# 🔄 6. n8n Workflows

## MVP Workflows

### Workflow 1: Data Ingestion Pipeline

```
Trigger (File dropped in /data/documents/)
  │
  ├──▶ Detect file type (PDF or DOCX)
  │
  ├──▶ Extract text (HTTP call to Python ingestion service)
  │
  ├──▶ Chunk text (Code Node — 500 tokens, 50-token overlap)
  │
  ├──▶ Generate embeddings (HTTP call to embedding service)
  │
  ├──▶ Store vectors in Qdrant (HTTP call to Qdrant API)
  │
  └──▶ Log metadata to PostgreSQL (chunk count, source, timestamp)
```

### Workflow 2: Query Orchestration

```
Webhook (receives question from Chat UI)
  │
  ├──▶ Guardrail check (Code Node — validate input)
  │
  ├──▶ Router Agent (LLM call — classify intent)
  │
  ├──▶ Switch Node:
  │      ├── factual_qa → Q&A Agent sub-workflow
  │      └── out_of_scope → return "I can only help with Smart Building topics"
  │
  ├──▶ Q&A Agent: embed query → search Qdrant → LLM generates answer
  │
  └──▶ Return cited answer to Chat UI
```

## Phase 2 Workflows (Deferred)

| Workflow | Purpose | Priority |
|----------|---------|----------|
| Scheduled Alerts | Daily Cron → check for expired items → notify | Phase 2 |
| Document Auto-Sync | 6h Cron → detect changed files → re-ingest | Phase 2 |

---

# 🛠️ 7. Tech Stack

| Layer | Technology | Why This Choice |
|-------|-----------|-----------------|
| **LLM** | Ollama + Llama 3.1 / Mistral 7B | Free, local, private, runs on Apple Silicon GPU |
| **Embeddings** | `all-MiniLM-L6-v2` | Free, local, CPU-friendly, industry standard |
| **Vector DB** | Qdrant (Docker) | Production-ready, REST API, excellent filtering |
| **Metadata DB** | PostgreSQL | Relational, tracks sources/chunks/queries |
| **Orchestration** | n8n (self-hosted via Docker) | Visual workflows, webhooks, scheduling, free |
| **Backend** | Python + FastAPI | Async, lightweight, dominant in LLM ecosystem |
| **Doc Parsing** | `PyMuPDF` + `python-docx` | Cross-platform, reliable, well-maintained |
| **Chat UI** | Chainlit (MVP) or Next.js (later) | Chainlit = fastest path to a working LLM chat UI |
| **Infrastructure** | Docker Compose | One command to start all services |

---

# 📁 8. Project Folder Structure

```
smart-building-ai/
│
├── docker-compose.yml              # One command to launch everything
├── .env.example                    # Template for secrets (never commit .env)
├── .gitignore                      # Excludes .env, data/, node_modules, etc.
├── README.md                       # Setup guide
│
├── services/
│   ├── ingestion/                  # 🔍 Ingestion Agent
│   │   ├── main.py                    FastAPI app for ingestion endpoints
│   │   ├── parsers/
│   │   │   ├── pdf_parser.py          PyMuPDF-based PDF extraction
│   │   │   └── docx_parser.py         python-docx-based DOCX extraction
│   │   ├── chunker.py                 Text splitting logic
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   ├── embedding/                  # 🔢 Embedding Agent
│   │   ├── main.py                    FastAPI app for embedding endpoints
│   │   ├── embedder.py                Vector generation with sentence-transformers
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   ├── agents/                     # 🧠 Router + Q&A + Guardrail Agents
│   │   ├── main.py                    FastAPI app — main entry point
│   │   ├── router_agent.py            Intent classification
│   │   ├── qa_agent.py                RAG Q&A with citations
│   │   ├── guardrail_agent.py         Input validation & security
│   │   ├── requirements.txt
│   │   └── Dockerfile
│   │
│   └── chat-ui/                    # 💻 Chat Interface
│       ├── app.py                     Chainlit app (or Next.js scaffold)
│       └── Dockerfile
│
├── n8n/
│   ├── workflows/                  # Exported n8n workflow JSONs
│   │   ├── ingestion_pipeline.json
│   │   └── query_orchestration.json
│   └── docker-compose.override.yml
│
├── data/
│   └── documents/                  # Drop Smart Building PDFs/DOCX here
│
├── tests/
│   ├── test_parsers.py
│   ├── test_chunker.py
│   ├── test_embedder.py
│   ├── test_qa_agent.py
│   ├── test_router_agent.py
│   └── test_guardrail_agent.py
│
└── docs/
    └── architecture.md             # Technical documentation
```

---

# 🗓️ 9. Implementation Blueprint (The Action Checklist)

> **Instructions for Notion:** Copy these into a **"To-Do List"** block or use Notion's native **Checklist** feature.

## 🏗️ Phase 1: Foundation & Pipeline (80% PC Ready)
*Goal: Ingest a document and see it appear in the database.*

- [ ] **1.1 Project & Repo Setup [💻 PC]**
    - [ ] Initialize Git repository.
    - [ ] Create folder structure (services, data, n8n, etc.).
    - [ ] Set up `.env.example` and `.gitignore`.
- [ ] **1.2 Infrastructure Configuration [💻 PC]**
    - [ ] Write `docker-compose.yml` (Qdrant, PostgreSQL, n8n, Ollama).
    - [ ] Test `docker-compose config` on Windows to ensure syntax is correct.
- [ ] **1.3 Ingestion Service [💻 PC]**
    - [ ] Implement PDF extractor (`PyMuPDF`).
    - [ ] Implement DOCX extractor (`python-docx`).
    - [ ] Write the `chunker.py` (500-token splitting + overlap).
- [ ] **1.4 Embedding Service [💻 PC]**
    - [ ] Set up `sentence-transformers` endpoint.
    - [ ] Verify local CPU execution (Windows).
- [ ] **1.5 Data Pipeline (n8n) [💻 PC]**
    - [ ] Build workflow: `Trigger → Parse → Chunk → Embed → Store`.
    - [ ] Export workflow as `ingestion_pipeline.json`.
- [ ] **1.6 [🍎 Mac Task] Deploy Foundation Layer**
    - [ ] Pull latest code on Mini Mac.
    - [ ] Run `docker-compose up`.
    - [ ] Verify Qdrant and Postgres are reachable.

---

## 🔵 Phase 2: Core RAG Intelligence (PC Developed)
*Goal: Ask a question and get a cited answer via terminal/API.*

- [ ] **2.1 Guardrail Agent [� PC]**
    - [ ] Write input validation logic (OWASP security).
    - [ ] Test against prompt injection strings.
- [ ] **2.2 Router Agent [� PC]**
    - [ ] Design the "Intent Classification" prompt.
    - [ ] Test logic: `Question → Intent (QA vs Out of Scope)`.
- [ ] **2.3 Q&A Agent (The Heart) [� PC]**
    - [ ] Implement Vector Search logic (Top-K chunks).
    - [ ] Design the "Answering with Citations" prompt.
    - [ ] Write logic to format sources: `[File.pdf, p. 12]`.
- [ ] **2.4 Query Orchestration (n8n) [� PC]**
    - [ ] Link `Webhook → Guard → Route → Q&A Agent`.
    - [ ] Export as `query_orchestration.json`.
- [ ] **2.5 [🍎 Mac Task] LLM Optimization**
    - [ ] Pull `Llama 3.1` or `Mistral` on Mini Mac via Ollama.
    - [ ] Test inference speed on Apple Silicon GPU.
    - [ ] Benchmark answer quality with real building docs.

---

## 🟢 Phase 3: UI & MVP Launch (Mac Integration)
*Goal: A beautiful chat interface for the user.*

- [ ] **3.1 Chat UI Scaffold [💻 PC]**
    - [ ] Build Chainlit or Next.js app.
    - [ ] Implement streaming responses (typing effect).
    - [ ] Design "Citation Popups" or "Sources Footer."
- [ ] **3.2 Dockerization [💻 PC]**
    - [ ] Write Dockerfiles for Agents and Chat-UI.
    - [ ] Confirm image builds successfully.
- [ ] **3.3 [🍎 Mac Task] Final Integration**
    - [ ] Import n8n JSONs into the Mac n8n instance.
    - [ ] Connect Chat-UI to n8n Webhook.
    - [ ] Final end-to-end bug hunt.
- [ ] **3.4 Documentation & Handover [💻 PC]**
    - [ ] Complete `README.md` with Mac setup commands.
    - [ ] Record a demo video of the local assistant.

---

## 🟣 Phase 4: Advanced Agents (Post-MVP)
*Goal: Intelligence beyond simple Q&A.*

- [ ] **4.1 Summary Agent [💻 PC]**
    - [ ] Implement "Map-Reduce" summarization for long docs.
- [ ] **4.2 Anomaly Agent [💻 PC]**
    - [ ] Write "Scan for Expired Items" logic.
- [ ] **4.3 Scheduled Alerts [💻 PC]**
    - [ ] n8n Cron Workflow setup.
- [ ] **4.4 Performance Tuning [🍎 Mac]**
    - [ ] Benchmark different chunk sizes vs embedding models.

---

# 📊 11. Kanban Board Setup

## Column Structure (GitHub Projects)

| Column | Purpose | WIP Limit |
|--------|---------|-----------|
| **New Issues** | Created but not triaged | — |
| **IceBox** | Frozen / blocked (Mac-only tasks go here initially) | — |
| **Product Backlog** | Prioritized, ready to pull | ~20 |
| **Sprint Backlog** | Committed for the current week | ~8 |
| **In Progress** | Actively being worked on | 2–3 |
| **Review/QA** | Code review, testing, validation | ~4 |
| **Done** | Completed and verified | — |

## Labels

| Label | Color | Usage |
|-------|-------|-------|
| `P0-critical` | 🔴 | Blocks everything — must be done first |
| `P1-high` | 🟠 | Important for MVP |
| `P2-medium` | 🟡 | Post-MVP enhancements |
| `P3-low` | 🟢 | Nice-to-have |
| `mvp` | 🔵 | Part of MVP scope |
| `post-mvp` | ⚪ | Deferred to after MVP |
| `pc-ready` | ⬜ | Can be done on Windows PC now |
| `mac-only` | ⬛ | Must wait for Mini Mac |
| `backend` | — | Python / FastAPI |
| `infra` | — | Docker / n8n / DevOps |
| `frontend` | — | Chat UI |
| `testing` | — | Unit / integration tests |

## Issue Dependency Chain

```
Phase 1 (Foundation):
#1.1 Repo Init
 └──▶ #1.2 docker-compose + #1.3 .env
       └──▶ #1.4 PDF Parser + #1.5 DOCX Parser
             └──▶ #1.6 Chunker
                   └──▶ #1.7 Embedding Service
                         └──▶ #1.9 n8n Ingestion Workflow

Phase 2 (Core RAG):
#1.7 Embedding ──▶ #2.1 Q&A Agent
#1.6 Chunker   ──▶ #2.2 Router Agent + #2.3 Guardrail Agent
                         └──▶ #2.4 FastAPI Main App
                               └──▶ #2.6 n8n Query Workflow

Phase 3 (Ship MVP):
#2.4 FastAPI ──▶ #3.1 Chat UI
#2.6 n8n     ──▶ #3.3 Deploy on Mac
                   └──▶ #3.6 E2E Integration Test
                         └──▶ 🎉 MVP SHIPPED
```

## Initial Board State (Day 1)

```
NEW ISSUES       → Phase 4 tasks (#4.1–#4.9)
ICEBOX           → Mac-only tasks (#3.3–#3.6)
PRODUCT BACKLOG  → Phase 2 tasks (#2.1–#2.7)
SPRINT BACKLOG   → Phase 1 tasks (#1.1–#1.10) ← START HERE
IN PROGRESS      → Empty
REVIEW/QA        → Empty
DONE             → Empty
```

---

# �️ 13. SOLID Architecture Compliance

> [!IMPORTANT]
> To ensure the project is **Open for Extension but Closed for Modification (OCP)**, we implement the following patterns:

### 1. **Component Decoupling (S & D)**
*   Each agent (Router, Q&A, Summary) lives as a separate **Module/Service**.
*   The **Router Agent** acts as an interface. Adding a "Summary Agent" in Phase 2 only requires adding a new `intent` to the Router's classification prompt and adding a new branch in n8n. **0 changes to the Q&A Agent's code.**

### 2. **Pluggable Orchestration (O)**
*   **n8n** is our primary OCP tool. The "Switch" node in the Query Workflow allows us to add infinite "Agent Sub-workflows" without modifying the primary Webhook or Guardrail logic.

### 3. **Stable Data Contracts**
*   **Qdrant** and **PostgreSQL** serve as our shared "Blackboard." New agents (like the Anomaly Agent) can read existing vector metadata without requiring changes to the Ingestion pipeline's schema.

### 4. **Dependency Inversion**
*   FastAPI endpoints depend on **Abstractions** (e.g., a generic `BaseAgent` class). This means the Orchestrator doesn't care if it's talking to a local Llama model or a remote API; the response format remains identical.

Track important architectural and technical decisions here.

| # | Decision | Options Considered | Choice | Reason | Status |
|---|----------|--------------------|--------|--------|--------|
| 1 | **LLM hosting** | Local (Ollama) vs Cloud (OpenAI) | Local (Ollama) | Data privacy — building data must stay local | ✅ Decided |
| 2 | **Vector DB** | Qdrant vs ChromaDB | Qdrant | Production-grade, REST API, good filtering | ✅ Decided |
| 3 | **Chat UI** | Chainlit vs Next.js | TBD | Chainlit = faster MVP, Next.js = more flexible | ⏳ Discuss with supervisor |
| 4 | **Embedding model** | `all-MiniLM-L6-v2` vs OpenAI | Local (`all-MiniLM`) | Free, private, CPU-friendly | ✅ Decided |
| 5 | **Orchestration** | n8n vs LangChain agents | n8n | Visual workflows, self-hosted, free | ✅ Decided |
| 6 | **LLM model** | Llama 3.1 vs Mistral 7B | TBD | Need to benchmark on Mini Mac hardware | ⏳ Test on Mac |
| 7 | **Document volume** | < 1000 docs vs > 10K | TBD | Determines indexing strategy | ⏳ Assess data |

---

> **This document is the single source of truth for the project's architecture and planning. Update it as decisions are made and phases are completed.**
