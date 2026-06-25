# Smart Building AI — Step-by-Step Run Guide

This guide describes how to run the **Smart Building AI Assistant** codebase from scratch on your macOS system using an optimized hybrid approach:
- **Local Host**: Next.js UI (run manually for instant updates and faster development with optimized RAM).
- **Docker**: Postgres, Qdrant, Ingestion, Embedding, Agents, and n8n orchestration.

---

## 📋 Prerequisites

Ensure you have the following installed on your host Mac:
1. **Docker Desktop**: Running and active.
2. **Node.js** (v18+ or v20+) & **npm**: For running the frontend.

---

## 🚀 Step-by-Step Startup Sequence

Follow these steps in order to start the entire system.

### Step 1: Validate Environment Configurations

Check the main `.env` file in the root directory:
- Set `LLM_PROVIDER` based on your desired backend:
  ```env
  LLM_PROVIDER=groq  # Configured to use cloud models via Groq
  ```
- Ensure your `GROQ_API_KEY` is properly configured.

---

### Step 2: Launch Dockerized Backend Infrastructure

Run the core database, pipeline, and agent services. Since the `chat-ui` service has been removed from `docker-compose.yml`, this will only spin up the backend dependencies.

1. Navigate to the project root directory.
2. Build and start the backend containers in the background:
   ```bash
   docker-compose up -d --build
   ```
3. Verify all services are healthy and running:
   ```bash
   docker-compose ps
   ```
   *Expected active containers:* `sb_qdrant`, `sb_postgres`, `sb_ingestion`, `sb_embedding`, `sb_agents`, `sb_n8n`.
4. (Optional) Stream logs of the main agent backend:
   ```bash
   docker-compose logs -f agents
   ```

---

### Step 3: Run the Chat UI Manually

Running the UI on your host system bypasses Docker container overhead. The development server has been configured with optimized heap limits (`NODE_OPTIONS='--max-old-space-size=256'`) and disabled default in-memory caches to minimize RAM usage.

1. Navigate to the UI service folder:
   ```bash
   cd services/chat-ui
   ```
2. Install the frontend dependencies (only required on the first run or if `package.json` changes):
   ```bash
   npm install
   ```
3. Start the Next.js server:
   ```bash
   # Option A: Start in development mode (hot-reloads, ~250MB RAM)
   npm run dev

   # Option B: Start in production mode (pre-compiled, uses only ~50MB RAM)
   npm run build && npm run start
   ```
4. Access the web interface in your browser at:
   👉 **[http://localhost:3001](http://localhost:3001)**

---

## 🛠️ Diagnostics & Useful Commands

### Service Port Mapping Cheat Sheet

| Service | Host URL / Port | Run Environment |
| :--- | :--- | :--- |
| **Chat UI** | `http://localhost:3001` | Local (Host) |
| **Agents (FastAPI)** | `http://localhost:8003` | Docker |
| **Embedding Service** | `http://localhost:8002` | Docker |
| **Ingestion Service** | `http://localhost:8001` | Docker |
| **n8n Orchestrator** | `http://localhost:5678` | Docker |
| **Qdrant (Vector DB)** | `http://localhost:6333` | Docker |
| **PostgreSQL** | `http://localhost:5432` | Docker |

### Troubleshooting Container Issues

* **Rebuild a Single Service**: If you modify the codebase of a Docker service (e.g., `agents`), rebuild it without restarting others:
  ```bash
  docker-compose up -d --build agents
  ```
* **View Service Logs**: Check a specific service's output:
  ```bash
  docker-compose logs -f <service-name>
  ```
* **Full Shutdown**: Stop all running backend containers:
  ```bash
  docker-compose down
  ```
* **Hard Reset (Clear Data/Caches)**: To wipe all database volumes and start with a clean slate:
  ```bash
  docker-compose down -v
  ```

---

> [!NOTE]
> When executing commands locally, keep a terminal window open for the Docker backend logs and a separate terminal window running the Next.js development server (`npm run dev`) for active UI logging.
