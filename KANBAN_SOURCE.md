# 🏗️ Smart Building AI Assistant - Implementation Source

> This file is structured for the **Project Maker Kanban Automation** system.
> Focus: MVP First, followed by Secondary Features, following SOLID (OCP) principles.

## 📅 Week 1: Foundation & Pipeline [Phase 1]
*Goal: System infrastructure setup and functional document ingestion.*

- [ ] **1.1 Project & Repo Setup [💻 PC]** — 🔵 MVP [P0]
    - [ ] Initialize Git repository (Completed).
    - [ ] Create folder structure (services, data, n8n, etc.).
    - [ ] Set up `.env.example` and `.gitignore` (Completed).
- [ ] **1.2 Infrastructure Configuration [💻 PC]** — 🔵 MVP [P0]
    - [ ] Write `docker-compose.yml` (Qdrant, PostgreSQL, n8n, Ollama).
    - [ ] Test `docker-compose config` on Windows to ensure syntax is correct.
- [ ] **1.3 Ingestion Service [💻 PC]** — 🔵 MVP [P0]
    - [ ] Implement PDF extractor (`PyMuPDF`).
    - [ ] Implement DOCX extractor (`python-docx`).
    - [ ] Write the `chunker.py` (500-token splitting + 50 tokens overlap).
- [ ] **1.4 Embedding Service [💻 PC]** — 🔵 MVP [P0]
    - [ ] Set up `sentence-transformers` endpoint (`all-MiniLM-L6-v2`).
    - [ ] Verify local CPU execution for vector generation.
- [ ] **1.5 Data Pipeline n8n [💻 PC]** — 🔵 MVP [P0]
    - [ ] Build workflow: `Trigger → Parse → Chunk → Embed → Store`.
    - [ ] Export workflow as `ingestion_pipeline.json`.
- [ ] **1.6 Deploy Foundation Layer [🍎 Mac]** — 🔵 MVP [P0]
    - [ ] Pull latest code on Mini Mac.
    - [ ] Run `docker-compose up` on target hardware.
    - [ ] Verify Qdrant and Postgres are reachable via Mac network.
- [ ] **1.0 Week 1 Demo & Retro [💻 PC]** — 🔵 MVP
    - [ ] Show successful PDF ingestion into Qdrant.
    - [ ] Document retrospective notes.

## 📅 Week 2: Core RAG Intelligence [Phase 2]
*Goal: Intent routing and factual Q&A with document citations.*

- [ ] **2.1 Guardrail Agent [💻 PC]** — 🔵 MVP [P1]
    - [ ] Write input validation logic (OWASP Top 10 compliance).
    - [ ] Test against prompt injection and off-topic strings.
- [ ] **2.2 Router Agent [💻 PC]** — 🔵 MVP [P1]
    - [ ] Design "Intent Classification" prompt (OCP compliant).
    - [ ] Test logic: `Question → Intent (QA vs Out of Scope)`.
- [ ] **2.3 QA Agent [💻 PC]** — 🔵 MVP [P1]
    - [ ] Implement Vector Search logic (Top-K chunks retrieval).
    - [ ] Design "Answering with Citations" prompt.
    - [ ] Write logic to format sources: `[File.pdf, p. 12]`.
- [ ] **2.4 Query Orchestration n8n [💻 PC]** — 🔵 MVP [P1]
    - [ ] Link `Webhook → Guard → Route → Q&A Agent`.
    - [ ] Export as `query_orchestration.json`.
- [ ] **2.0 Week 2 Demo & Retro [💻 PC]** — 🔵 MVP
    - [ ] Demo successful cited answer to building specific query.
    - [ ] Update Kanban board status.

## 📅 Week 3: Integration & Optimization [Phase 2 Cont.]
*Goal: Refining AI performance and API orchestration.*

- [ ] **2.5 LLM Optimization [🍎 Mac]** — 🔵 MVP [P1]
    - [ ] Pull `Llama 3.1` on Mini Mac via Ollama.
    - [ ] Test inference speed on Apple Silicon GPU.
    - [ ] Benchmark answer quality with complex building blueprints/manuals.
- [ ] **2.6 FastAPI Agent Orchestrator [💻 PC]** — 🔵 MVP [P1]
    - [ ] Unify all agents under one REST API endpoint.
    - [ ] Implement async streaming for LLM responses.
- [ ] **2.7 Component Unit Tests [💻 PC]** — 🔵 MVP [P1]
    - [ ] Write `pytest` for each Agent (Router, QA, Guardrail).
    - [ ] Mock LLM responses for repeatable CI testing.
- [ ] **3.0 Week 3 Demo & Retro [💻 PC]** — 🔵 MVP
    - [ ] Show optimized inference speed on Mac.
    - [ ] Validate SOLID OCP by adding mock "New Agent" branch.

## 📅 Week 4: Chat UI & MVP Launch [Phase 3]
*Goal: Delivering a polished user experience on the local hardware.*

- [ ] **3.1 Chat UI Scaffold [💻 PC]** — 🔵 MVP [P1]
    - [ ] Build Chainlit or Next.js chat application.
    - [ ] Implement streaming UI and sources display.
- [ ] **3.2 Dockerization [💻 PC]** — 🔵 MVP [P1]
    - [ ] Write production Dockerfiles for Agents and Chat-UI.
    - [ ] Verify multi-stage builds and minimal image sizes.
- [ ] **3.3 Final Mac Integration [🍎 Mac]** — 🔵 MVP [P1]
    - [ ] Import finalized n8n JSONs into Mac instance.
    - [ ] Final end-to-end testing of the full RAG pipeline.
- [ ] **3.4 Documentation & Handover [💻 PC]** — 🔵 MVP [P1]
    - [ ] Complete `README.md` with Mac deployment steps.
    - [ ] Record high-quality demo of the Local AI Assistant.
- [ ] **4.0 Week 4 MVP Demo & Retro [🍎 Mac]** — 🔵 MVP
    - [ ] Final MVP presentation to supervisors.
    - [ ] Celebrate MVP Launch.

## 📅 Week 5: Advanced Agents [Phase 4]
*Goal: Expanding capabilities beyond simple Q&A (Secondary Features).*

- [ ] **4.1 Summary Agent [💻 PC]** — ⚪ Post-MVP [P2]
    - [ ] Implement "Map-Reduce" summarization for long building logs.
    - [ ] Add `summarize` intent to Router Agent.
- [ ] **4.2 Anomaly Agent [💻 PC]** — ⚪ Post-MVP [P2]
    - [ ] Write "Scan for Expired Items" logic.
    - [ ] Integrate structured data (CSV/BMS) check.
- [ ] **4.3 Scheduled Alerts n8n [💻 PC]** — ⚪ Post-MVP [P2]
    - [ ] Setup Cron Trigger (Daily/Weekly).
    - [ ] Connect Anomaly Agent to notification nodes (Email/Teams).
- [ ] **5.0 Week 5 Demo & Retro [💻 PC]** — ⚪ Post-MVP
    - [ ] Show automated alert for a generated "expired" document.

## 📅 Week 6: Polish & Scaling [Phase 4 Cont.]
*Goal: Performance, security audit, and persistent history.*

- [ ] **4.4 Performance Tuning [🍎 Mac]** — ⚪ Post-MVP [P3]
    - [ ] Benchmark chunk sizes vs accuracy.
    - [ ] Test quantization levels of Llama-3.1 on Mac Studio/Mini.
- [ ] **4.5 Conversation History [💻 PC]** — ⚪ Post-MVP [P3]
    - [ ] Implement Postgres session storage for chat history.
    - [ ] Add "Clear History" and "Session Management" to UI.
- [ ] **4.6 User Feedback Loop [💻 PC]** — ⚪ Post-MVP [P3]
    - [ ] Add Thumbs Up/Down and comment section to Chat-UI.
- [ ] **6.0 Final Project Retro & Handover** — ⚪ Post-MVP
    - [ ] Final clean up of the Kanban board.
    - [ ] Finalize internship documentation.
