# Lovable Super Prompt — Smart Building AI Documentation Site

Copy everything below the line and paste it into Lovable:

---

Build a **stunning, single-page documentation website** for an enterprise AI project called **"Smart Building AI"**. This is a **client-facing presentation** — it must look premium, polished, and impressive. The design should communicate "enterprise-grade engineering" at first glance.

## Design Requirements

### Overall Aesthetic
- **Dark mode** with a deep navy/slate background (`#0f172a` → `#1e293b` gradient)
- **Accent color**: Electric blue (`#3b82f6`) with subtle purple highlights (`#8b5cf6`)
- **Typography**: Use `Inter` from Google Fonts. Clean, modern, no serif.
- **Glassmorphism**: Card components should have frosted glass effect (`backdrop-filter: blur(16px)`, semi-transparent backgrounds `rgba(255,255,255,0.05)`, subtle white borders `rgba(255,255,255,0.1)`)
- **Smooth animations**: Sections should fade-in on scroll using Intersection Observer. Cards should have subtle hover lift effects.
- **Responsive**: Must look great on desktop AND tablet.

### Layout Structure
1. **Hero Section** — Full-width with animated gradient background
   - Title: "Smart Building AI"
   - Subtitle: "Privacy-First Document Intelligence for Facilities Management"
   - Three animated stat counters: "7 Microservices" | "20+ Modules" | "12 Test Suites"
   - A subtle pulsing dot next to "Status: Active — Phase 4"

2. **Executive Summary** — Glassmorphism card
   - "A local, privacy-first, multi-agent AI system for Smart Building document intelligence. Uses RAG (Retrieval-Augmented Generation) with a three-pass ingestion pipeline (PyMuPDF → IBM Docling TableFormer → Tesseract OCR) and a cross-encoder re-ranker to deliver cited, high-fidelity answers from HVAC checklists, maintenance manuals, and building specifications."

3. **Architecture Diagram** — Interactive visual
   - Show the 5-stage SSE pipeline as a horizontal flow:
     `User → Guardrail (shield icon) → Router (compass icon) → Qdrant Search + Re-Rank (magnifying glass) → LLM Generation (brain icon) → Streaming Response`
   - Each node should glow when hovered
   - Use connecting lines with animated gradient flow (like data flowing through a pipe)

4. **Tech Stack** — Grid of technology badges/cards (3 columns)
   Each card has an icon, name, and one-line description:
   - Qwen3-32B (Local LLM) — "Chain-of-Thought reasoning on Apple Silicon"
   - DeepSeek R1 via Groq (Cloud LLM) — "Fast cloud inference, hot-swappable"
   - IBM Docling (Document AI) — "TableFormer ACCURATE for scanned HVAC tables"
   - Qdrant (Vector DB) — "Production-grade semantic search"
   - PostgreSQL — "Chat history, documents, audit logs"
   - Next.js 14 (Chat UI) — "SSE streaming with glassmorphism design"
   - FastAPI (Backend) — "Async Python orchestrator"
   - Docker Compose — "7 services, one command"
   - Cross-Encoder Re-Ranker — "ms-marco-MiniLM precision filtering"

5. **Three-Pass Ingestion Pipeline** — Vertical stepper/timeline
   - Step 1: "PyMuPDF — Fast native text extraction (handles 80% of pages)"
   - Step 2: "IBM Docling — Deep-learning layout analysis for tables & scanned documents"
   - Step 3: "Tesseract OCR — Safety net for edge cases"
   - Show green checkmarks and a progress bar visual

6. **Key Features** — 2x3 grid of feature cards with icons
   - 🔍 "Cross-Encoder Re-Ranking" — "Over-retrieve top-15, re-rank to top-5 with neural precision"
   - 🏭 "Multi-Provider LLM" — "Swap between local Ollama and cloud Groq with one env variable"
   - 🎯 "Domain-Agnostic Config" — "Swap a single YAML file to repurpose for any industry"
   - 💬 "Multi-Session Chat" — "PostgreSQL-backed conversation history with sidebar navigation"
   - 📚 "Knowledge Base CRUD" — "Upload, manage, and delete documents with cascading vector cleanup"
   - 🔄 "Smart Folder Sync" — "Auto-detect new, modified, and deleted files"

7. **Engineering Principles** — Three horizontal cards
   - Card 1: "SOLID" with icons for S, O, L, I, D and one-line examples
   - Card 2: "FIRST Testing" — "12 test suites, all mocked, zero network calls"
   - Card 3: "OWASP Top 10" — "Parameterized queries, no hardcoded secrets, non-root containers"

8. **Key Decisions Log** — Styled table with 11 rows
   Show these decisions:
   | # | Decision | Choice | Status |
   |---|---|---|---|
   | 1 | LLM Hosting | Hybrid (Ollama + Groq) | ✅ |
   | 2 | Vector DB | Qdrant | ✅ |
   | 3 | Chat UI | Next.js 14 | ✅ |
   | 4 | Embedding Model | all-MiniLM-L6-v2 (local) | ✅ |
   | 5 | Orchestration | n8n + FastAPI hybrid | ✅ |
   | 6 | LLM Model | Qwen3-32B + DeepSeek R1 | ✅ |
   | 7 | Document Parsing | Three-pass cascade | ✅ |
   | 8 | Guardrails | Regex-based (~1ms) | ✅ |
   | 9 | Re-ranking | Cross-encoder ms-marco | ✅ |
   | 10 | Domain Config | YAML-based | ✅ |
   | 11 | Conversation Memory | PostgreSQL multi-session | ✅ |

9. **Phase Progress Timeline** — Vertical timeline with 4 phases
   - Phase 1: Foundation ✅ — "Infrastructure, parsing, embedding, Qdrant"
   - Phase 2: Core RAG ✅ — "Guardrail, Router, QA Agent, n8n orchestration"
   - Phase 3: Ship MVP ✅ — "Next.js Chat UI, Docker Compose, end-to-end integration"
   - Phase 4: Post-MVP 🟡 — "Docling, Re-Ranker, LLM Factory, Domain Config, Multi-Session, Knowledge Base, Folder Sync, Qwen3 CoT"
   
   Phase 4 should have a glowing border to indicate it's the current phase.

10. **Verification Metrics** — Horizontal progress bars or gauge cards
    - Docling Table Extraction: 95% (target: 90%)
    - Re-Ranker Precision: 92% (target: 85%)
    - Multi-Session Isolation: 100%
    - Folder Sync (100 files): 15s (target: 30s)

11. **Footer** — Simple dark footer
    - "Smart Building AI — Privacy-First Document Intelligence"
    - "Built with ❤️ on Mac Mini (Apple Silicon)"
    - GitHub link placeholder

## Technical Requirements
- Use React with TypeScript
- Use Tailwind CSS for styling
- Use Framer Motion for animations
- Use Lucide React for icons
- Make it a single-page app with smooth scroll navigation
- Add a sticky top navigation bar with section links
- All sections should animate in on scroll

## Color Palette
- Background: `#0f172a` (slate-900)
- Card BG: `rgba(30, 41, 59, 0.8)` with blur
- Primary: `#3b82f6` (blue-500)
- Accent: `#8b5cf6` (violet-500)
- Success: `#22c55e` (green-500)
- Text: `#f8fafc` (slate-50)
- Muted: `#94a3b8` (slate-400)
- Borders: `rgba(255, 255, 255, 0.1)`
