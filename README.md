# 🏗️ Smart Building AI Assistant

> A **local, privacy-first AI assistant** for Smart Building management.  
> Ask questions about your building documents and get accurate, cited answers — all running on your own hardware.

---

## 📋 Quick Start

### Prerequisites

| Tool | Minimum Version | Purpose |
|------|----------------|---------|
| **Docker Desktop** | 24.x+ | Container runtime |
| **Docker Compose** | v2.x+ | Multi-service orchestration |
| **Git** | 2.x+ | Version control |

### 1. Clone & Configure

```bash
git clone https://github.com/GutsDCEO/Smart_buildingLLM.git
cd Smart_buildingLLM

# Create your local environment file
cp .env.example .env
# Edit .env and set real passwords for POSTGRES_PASSWORD, N8N_BASIC_AUTH_PASSWORD, N8N_ENCRYPTION_KEY
```

### 2. Launch Infrastructure

```bash
docker-compose up -d
```

This starts:
- **Qdrant** (vector database) → `http://localhost:6333`
- **PostgreSQL** (metadata store) → `localhost:5432`
- **n8n** (workflow engine) → `http://localhost:5678`
- **Ollama** (local LLM) → `http://localhost:11434`

### 3. Pull an LLM Model (on Mac)

```bash
docker exec -it sb_ollama ollama pull llama3.1
```

### 4. Drop Documents

Place PDF and DOCX files into `data/documents/` to be ingested by the pipeline.

---

## 🏛️ Architecture Overview

```
User → Chat UI → Guardrail → Router → Q&A Agent → [Qdrant + LLM] → Cited Answer
                                          ↑
                  Ingestion Pipeline → Chunk → Embed → Store
```

For the full architecture, see [NOTION_PROJECT_WIKI.md](./NOTION_PROJECT_WIKI.md).

---

## 📁 Project Structure

```
smart-building-ai/
├── docker-compose.yml          # Infrastructure services
├── .env.example                # Environment variable template
├── services/
│   ├── ingestion/              # PDF/DOCX parsing + chunking
│   ├── embedding/              # Vector embedding service
│   ├── agents/                 # Router, Q&A, Guardrail agents
│   └── chat-ui/                # Chat interface (Chainlit)
├── n8n/workflows/              # Exported n8n workflow JSONs
├── data/documents/             # Drop building documents here
├── tests/                      # Unit & integration tests
└── docs/                       # Technical documentation
```

---

## 🛡️ Security

- All data stays **local** — nothing leaves your network.
- Secrets are managed via `.env` (never committed to Git).
- Input validation via the Guardrail Agent (OWASP-compliant).

---

## 📝 License

Private project — © 2026 GutsDCEO
