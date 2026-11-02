# Smart Building AI

An on-premise RAG assistant for smart-building technical documentation. Facility teams ask questions in plain language and get answers grounded in their own manuals and maintenance logs, with the source file and page number for every claim.

Built as my final-year engineering project (EMSI, 2026) at TWINSIP Technologies.

▶ **Demo video:** [Watch the demo on LinkedIn](https://www.linkedin.com/posts/ahmedamineeloumami_what-if-building-technicians-could-ask-their-ugcPost-7523093181681315840-AK28/)

---

## What it does

- **Cited answers.** Each answer lists its sources with file name, page number and relevance score.
- **Diagrams on request.** Ask for a system diagram and it generates a Mermaid diagram, exportable as SVG or PNG.
- **Optional thinking mode** for harder questions.
- **Knowledge base.** Upload PDF, Word or text files, or sync a whole folder; new documents are indexed automatically.
- **Accounts and roles.** JWT authentication with revocable refresh tokens, Admin and User roles.

## How a query flows

```
Question → Guardrail → Router → Qdrant search (top-15) → Cross-encoder re-rank (top-5) → LLM → Streamed answer + citations
                                      ↑
PDF / DOCX → Ingestion (PyMuPDF → Docling → Tesseract OCR) → Chunking → Embedding → Qdrant
```

- **Guardrail:** regex rules aligned with OWASP LLM01 block prompt-injection attempts before any LLM call.
- **Router:** sends the question to the right agent. The orchestration is plain Python, no LangChain or LangGraph.
- **Retrieval in two steps:** Qdrant over-retrieves 15 chunks by cosine similarity, then `cross-encoder/ms-marco-MiniLM-L-6-v2` keeps the 5 that best answer the question.
- **Ingestion in three passes:** fast text extraction with PyMuPDF, Docling for tables and layout, Tesseract OCR for scanned pages.
- **LLM provider is swappable:** Qwen3-32B through Ollama for fully local inference, or Groq in the cloud, chosen with `LLM_PROVIDER` in `.env`.

## Stack

| Layer | Tools |
|---|---|
| Backend | Python, FastAPI (async), PostgreSQL |
| Retrieval | Qdrant, `BAAI/bge-base-en-v1.5` embeddings (768-d), cross-encoder re-ranker |
| Ingestion | PyMuPDF, Docling, Tesseract OCR |
| Frontend | Next.js, React, TypeScript, SSE streaming |
| Ops | Docker Compose, Caddy reverse proxy, n8n |

## Services

| Service | Role |
|---|---|
| `qdrant` | Vector database |
| `postgres` | Users, sessions, document metadata |
| `ingestion` | Text extraction and chunking |
| `embedding` | Vector generation and storage |
| `agents` | FastAPI backend: guardrail, router, Q&A, auth |
| `n8n` | Workflow automation and pipeline monitoring |
| `chat-ui` | Next.js frontend (production compose) |
| `caddy` | Reverse proxy and security headers (production compose) |

## Run it locally

Requirements: Docker Desktop, Node.js 20+, and either a Groq API key or Ollama on the host.

```bash
git clone https://github.com/GutsDCEO/Smart_buildingLLM.git
cd Smart_buildingLLM
cp .env.example .env   # set POSTGRES_PASSWORD, N8N_* secrets, LLM_PROVIDER and GROQ_API_KEY if using Groq
docker compose up -d --build
```

To run fully local with Qwen3-32B, install Ollama on the host and set in `.env`:

```bash
ollama pull qwen3:32b
# .env
LLM_PROVIDER=ollama
OLLAMA_MODEL=qwen3:32b
OLLAMA_HOST=http://host.docker.internal:11434
```

Then start the UI:

```bash
cd services/chat-ui
npm install
npm run dev            # http://localhost:3001
```

Production (all services behind Caddy on port 80):

```bash
docker compose -f docker-compose.yml -f docker-compose.prod.yml up -d --build
```

More detail: [`docs/RUN_GUIDE.md`](docs/RUN_GUIDE.md).

## Measured results

From the evaluation in my project report:

- 100% of tested prompt-injection attempts blocked
- Vector search under 100 ms
- About 400 ms to first token, about 2.3 s end to end

---

Private project. © 2026 Ahmed Amine El Oumami.
