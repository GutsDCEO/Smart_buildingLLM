# 🔄 n8n Data Pipeline — Setup & Testing Guide

> **Phase 1.5** | Document Ingestion Pipeline
> This guide walks you through starting all services with Docker and testing the full
> Ingestion → Embedding pipeline through the n8n UI.

---

## A. Technical Architecture Explanation

### What is n8n doing here?
n8n is the **"Glue" layer** of our system. It doesn't do any AI work itself — it orchestrates:
1. Calls our **Ingestion Service** to extract and chunk text from a document.
2. Passes those chunks to our **Embedding Service** to generate vectors.
3. The Embedding Service stores them in **Qdrant** and logs to **PostgreSQL**.

### How does Docker Networking work?
All services run on a shared Docker network called `sb_network`. Inside this network,
each service can be called by its **container name** instead of `localhost`.

```
n8n container  →  calls  →  http://ingestion:8001/ingest
n8n container  →  calls  →  http://embedding:8002/embed
embedding      →  calls  →  http://qdrant:6333  (internal)
```

### Startup Dependency Chain
```
qdrant (starts first)
postgres (starts first)
     │
     ├──▶ ingestion (waits for qdrant + postgres to be healthy)
     ├──▶ embedding (waits for qdrant + postgres to be healthy)
          │
          └──▶ n8n (waits for ingestion + embedding to be healthy)
```

---

## B. Critical Code Snippet — Reshape Node

The most important node in the workflow is the **"Reshape Chunks"** Code Node.
It bridges the output contract of the Ingestion Service with the input contract
of the Embedding Service.

```javascript
// Why is this needed?
// Ingestion returns: { source_file, total_chunks, chunks: [...] }
// Embedding expects: { chunks: [...] }
// Without this node, the Embedding Service returns a 422 Unprocessable Entity.

const ingestResponse = $input.first().json;

if (!ingestResponse.chunks || ingestResponse.chunks.length === 0) {
  throw new Error(`No chunks were produced from ${ingestResponse.source_file}`);
}

return [{ json: { chunks: ingestResponse.chunks } }];
```

---

## C. Step-by-Step Testing Guide

### Step 1: Build and Start All Services
```powershell
# From the project root (s:\Documents\Projects\Smart_buildingLLM)
docker-compose up -d --build
```
> ⏳ First run takes 5–10 minutes. The Embedding Service downloads the AI model (~90MB).

### Step 2: Verify All Services Are Healthy
```powershell
docker-compose ps
```
**Expected output** — all 5 services should show `Up (healthy)`:
```
NAME              STATUS
sb_qdrant         Up (healthy)
sb_postgres       Up (healthy)
sb_ingestion      Up (healthy)
sb_embedding      Up (healthy)
sb_n8n            Up (healthy)
```

### Step 3: Open n8n Dashboard
Go to: `http://localhost:5678`

Login with:
- **User:** `admin` (or your `N8N_BASIC_AUTH_USER` value)
- **Password:** your `N8N_BASIC_AUTH_PASSWORD` from `.env`

### Step 4: Import the Workflow
1. In the n8n sidebar, click **Workflows**.
2. Click **Import** (top right).
3. Select `n8n/workflows/ingestion_pipeline.json`.
4. The workflow opens with 5 connected nodes.

### Step 5: Run the Workflow
1. Open the **"Set File Path"** node.
2. Change the `file_path` value to the path of a test PDF inside the `data/ingest/` 
   folder (which is accessible from the ingestion container).
3. Click **Execute Workflow**.

### Step 6: What to Verify

| Node | Expected Output |
|:-----|:----------------|
| **POST /ingest** | `total_chunks > 0`, each chunk has `text`, `page_number` |
| **Reshape Chunks** | Output body is `{ "chunks": [...] }` — not the full ingestion response |
| **POST /embed** | `chunks_stored` matches `total_chunks` from ingest |
| **Build Summary** | `status: "SUCCESS"`, sample `vector_ids` are valid UUIDs |

### Step 7: Verify in Qdrant Dashboard
```
http://localhost:6333/dashboard
```
- Select collection `smart_building_docs`.
- Point count should increase by `chunks_stored`.
- Click any point → inspect `payload` for `text`, `source_file`, `page_number`.

---

## D. Testing Failure Paths

| Failure | How to Test | Expected Behaviour |
|:--------|:-----------|:-------------------|
| Unsupported file type | Change file to a `.txt` | `POST /ingest` returns `400 Bad Request` |
| Embedding service down | Stop `sb_embedding` container | `POST /embed` returns connection error in n8n |
| Empty document | Upload a blank PDF | `Reshape Chunks` throws error and halts workflow safely |
