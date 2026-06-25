# 🎥 Smart Building AI — Director & Advisor Demo Guide

This guide provides a step-by-step walkthrough to run, navigate, and showcase every visual aspect of the **Smart Building AI Assistant** for a screen recording or live demonstration.

---

## 🛠️ Step 1: Startup Commands (Clean Slate)

Ensure all backend containers and the Next.js dev server are running:

### 1. Verify Groq Configuration (.env)
Since you are using Groq for cloud LLM services (instead of local Ollama), ensure your `.env` contains:
```env
LLM_PROVIDER=groq
GROQ_API_KEY=your_actual_api_key_here
GROQ_MODEL=qwen/qwen3-32b
```

### 2. Start Docker Containers
Navigate to the repository root and bring up the database, vector storage, ingestion, embedding, agents, and orchestration services:
```bash
# In project root: /Users/mac/Smart_buildingLLM
docker-compose up -d --build
```
*Verify they are all healthy:*
```bash
docker-compose ps
```

### 3. Launch the Next.js Frontend
```bash
cd services/chat-ui
npm run dev
```
👉 The Chat UI is now running at: **[http://localhost:3001](http://localhost:3001)**


---

## 🔑 Step 2: Access Credentials

Use these credentials to log in during the demo:

| Service / Interface | URL | Username / Email | Password |
| :--- | :--- | :--- | :--- |
| **Chat UI** | `http://localhost:3001` | `youness` | `StrongPassword123!` |
| **n8n Canvas** | `http://localhost:5678` | *Create your owner account on startup* | *Choose your own* |
| **Qdrant DB** | `http://localhost:6333/dashboard` | *None (Public dashboard)* | *None* |

> 💡 **n8n Account Reset:** The user account database for n8n has been cleared. When you visit `http://localhost:5678`, n8n will ask you to register a brand new owner account. After creating the account, import the workflows in the n8n UI:
> 1. Click **Workflows** in the sidebar.
> 2. Click **Import** (top-right).
> 3. Select `n8n/workflows/ingestion_pipeline.json` and `query_orchestration.json`.

---

## 🎬 Step 3: Step-by-Step Demo Script (5-Minute Walkthrough)

Here is a recommended timeline and script structure for your video presentation:

### Part 1: Login & Intro (0:00 - 0:45)
1. **What to show:** Open browser to `http://localhost:3001`. Show the login screen with its dark glassmorphism layout and floating animated background orbs.
2. **What to say:** *"Hello, today I will demonstrate the Smart Building AI Assistant, a privacy-first, local RAG system running entirely on our network. First, let's log in to the admin account."*
3. **Action:** Type `youness` and `StrongPassword123!`, then click **Sign In**.

### Part 2: RAG Chat & Pipeline Status (0:45 - 2:00)
1. **What to show:** The main chat view. Highlight the starter prompt chips and the sidebar navigation.
2. **Action:** Click one of the starter chips (e.g., *"What maintenance tasks are due this month?"*) or type a custom building query.
3. **What to highlight in video:**
   - **4-Step Pipeline Bar:** Draw attention to the bottom status bar displaying the active RAG step in real-time: `Guard 🛡️ → Route 🚦 → Search 🔍 → Generate ✨`. Explain that the guardrail prevents prompt injection, the router determines domain applicability, retrieval fetches Qdrant segments, and the generator streams local tokens.
   - **Token Streaming:** Show how the text prints out smoothly.
   - **Citations:** Click a source card at the bottom of the answer. Show that it highlights the specific source file (e.g., `ahu-air-handler-units-pm-checklist.pdf`) and page number.
   - **CoT toggle:** Hover over the "Think" button (`🧠`) and mention that deep-thinking chain-of-thought reasoning can be toggled on demand.

### Part 3: Inline Interactive Diagrams (2:00 - 2:45)
1. **Action:** Type: *"Draw a network diagram of a typical BACnet MSTP configuration with a router, primary controller, and three smart thermostats."*
2. **What to show:** Watch the AI generate a Mermaid codeblock which instantly renders into an elegant, high-contrast, interactive architectural diagram inside the chat window.
3. **What to say:** *"The assistant is equipped with an inline rendering engine that translates text architectures into interactive visual diagrams on the fly, aiding facilities engineers during maintenance."*

### Part 4: Knowledge Base & Ingestion Gateway (2:45 - 3:45)
1. **Action:** Click **Knowledge Base** in the sidebar.
2. **What to show:** The list of currently indexed documents, metadata cards (chunk counts, file sizes, creation timestamps), and filters.
3. **Action:** Click **Upload Document**, pick a building document from the `data/documents/` folder, and wait for ingestion. Alternatively, click **Sync Folder** to run an automated sweep of the ingest folder.
4. **What to say:** *"Administrators can manage the knowledge base. Here, we can upload raw PDFs or Word documents. The system parses them locally using our three-pass ingestion pipeline (Docling and Tesseract OCR) and auto-splits them into vector chunks."*

### Part 5: RAG-Powered Document Template Center (3:45 - 4:45)
1. **Action:** Click **Document Templates** in the sidebar.
2. **Action:** Drag and drop a form template PDF (or browse to upload).
3. **What to show:** The extracted placeholders table showing placeholder names, type (Acroform, bracket, mustache), page number, and confidence.
4. **Action:** Select a few placeholders and click **Auto-Fill Selected**. Watch the real-time SSE progress bar cycle through stages as it uses RAG to answer form details.
5. **Action:** Once complete, click **Download Filled PDF** to show the filled document.
6. **What to say:** *"In the Template Center, users can upload empty checklists or inspection forms. The AI extracts the placeholders, automatically queries our vector storage for the answers, fills the form fields programmatically, and outputs a downloadable, complete PDF."*

### Part 6: n8n & Qdrant Behind-the-Scenes (4:45 - end)
1. **Action:** Switch tabs to `http://localhost:5678` (n8n) and open the `query_orchestration` workflow.
2. **What to say:** *"Behind the scenes, we use n8n to choreograph the API queries between agents, routing logic, and guardrails in a visual canvas."*
3. **Action:** Switch to `http://localhost:6333/dashboard` (Qdrant) and show the points/payloads.
4. **What to say:** *"All vector embeddings are indexed locally in Qdrant, securing our building documents locally without relying on external cloud endpoints. Thank you!"*

---

## 💡 Pro-Tips for a Great Screen Recording

- **Clean Browser Profile:** Use a dedicated browser window without personal bookmarks or open tabs.
- **Font Size:** Zoom in slightly (110% or 120%) so the code snippets, titles, and diagrams are easily readable on mobile or presentation screens.
- **Use Real Files:** Upload a small file (1-2 pages) for the video demo so the ingestion and sync steps take under 5 seconds to complete.
- **Smooth Cursor Movement:** Avoid shaking the mouse or clicking rapidly. Move the cursor directly to the button you want to click.
