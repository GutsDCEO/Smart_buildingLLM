# Smart Building AI — Quick Context

> This file provides quick context to Antigravity. For full details, see `.agents/AGENTS.md`.

## What Is This Project?
A privacy-first, multi-agent RAG system for Smart Building document intelligence.
Runs locally on Mac Mini (Apple Silicon) with Docker Compose (7 services).

## Don't Re-Scan These Files
The AI should NOT waste tokens re-reading these unless explicitly asked:
- `docs/Smartbuilding Full Documentation.md` (92 KB) — use `.agents/AGENTS.md` summary instead
- `docs/NOTION_UNIFIED_WIKI.txt` (77 KB) — historical, mostly superseded
- `docker-compose.yml` — only read if debugging container issues

## Current Task
**Phase 5: Secure Authentication** — JWT, RBAC, session management, OWASP compliance.

## Model Usage Guide
- **Opus 4.6:** Architecture, security logic, code review, SOLID refactoring
- **Gemini 3.1 Pro (High):** Cross-service debugging, Docker issues, large log scanning
- **Gemini 3 Flash:** Quick edits, boilerplate, formatting, config changes
- **Sonnet 4.6:** Mid-complexity coding when Opus quota is low