# 🧠 Deep Tech Briefing: Ingestion & Embedding Pipeline

## 🏗️ Architectural Decisions

### 1. Token-Based Chunking (tiktoken)
Normal text splitting by "character count" often cuts sentences in half, destroying the AI's understanding. 
*   **Our Solution:** We use `cl100k_base` (the same tokenizer used by GPT-4). 
*   **Benefit:** Every chunk is exactly the size the Embedding model expects, maximizing "semantic density."

### 2. The Singleton Embedder
Loading an AI model from disk into RAM takes 2–5 seconds. 
*   **Our Solution:** We load the model during the FastAPI `lifespan` event.
*   **Benefit:** The model stays in memory. The actual "Math" conversion happens in milliseconds.

### 3. Graceful Storage Degradation
We have two databases: Qdrant (Critical) and Postgres (Optional Audit).
*   **Our Solution:** The `db.py` module uses a `try/except` block at the connection level.
*   **Benefit:** If Postgres is down for maintenance, your Building AI **does not stop working**. It continues to store vectors in Qdrant and simply logs a warning about the missing audit trail.

---

## 🛰️ The Communication Contract (DTOs)
We use **Pydantic Models** to ensure "Strict Typing."
*   If the Ingestion Service changes its output format, the Embedding Service will immediately throw a `422 Unprocessable Entity` error. 
*   **Why?** This prevents "Silent Failures" and "Dirty Data" from entering your Vector Database.

---

## 🧪 Detailed Testing Protocol (End-to-End)

| Phase | Action | Expected Result |
|:---|:---|:---|
| **Discovery** | `GET /formats` (8001) | Returns `[".pdf", ".docx"]` |
| **Extraction** | `POST /ingest` (8001) | Returns JSON with `text` + `token_count` |
| **Translation** | `POST /embed` (8002) | Returns `vector_ids` (UUIDs) |
| **Persistence** | Qdrant Dashboard | Collection count increases by N chunks |
| **Audit** | `SELECT * FROM ingestion_log` | New row appears with filename and count |

---

## 🛡️ Security Check (Quality Rule ③)
*   **Sanitization:** The `PdfParser` strips control characters and excessive whitespace to prevent "Prompt Injection" via hidden text in PDFs.
*   **Non-Root:** Both services run as `appuser` inside Docker. Even if someone "hacks" the FastAPI app, they don't have root access to your Mini Mac.
