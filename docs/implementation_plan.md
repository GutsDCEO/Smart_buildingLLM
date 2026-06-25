# Implementation Plan — Template-Based RAG Document Filling

This document outlines the final implementation plan and architecture for the **Template Document Filling** feature (Phase 6) of the Smart Building AI Assistant.

---

## 1. Goal

Allow users to upload a building or IoT PDF template, automatically extract programmatically fillable fields or text placeholders, use the RAG pipeline to answer/fill each field, and return a completed PDF for download. Real-time feedback is provided to the user via a Server-Sent Events (SSE) progress stream.

---

## 2. Architecture & Design Decisions

### 2.1 Multi-Format Placeholder Extraction (Strategy Pattern)
Since users upload unknown templates at runtime, we cannot predict the placeholder format. The `PlaceholderExtractor` uses a prioritised strategy chain to locate fields:
1. **Interactive form widgets (AcroForm)**: programmatically fillable PDF form fields (the cleanest, layout-safe fill path).
2. **Bracket placeholders**: text matching `\[([^\]]{3,150})\]` (e.g. `[Building Name]`).
3. **Underscore placeholders**: text matching `([\w][^\n:]{2,60}):\s*_{4,}` (e.g. `Inspector: __________`).
4. **Mustache tags**: text matching `\{\{([^}]{1,100})\}\}` (e.g. `{{building_name}}`).

If interactive widgets are detected, the parser skips the text scans to prevent redundant matches. This strategy follows the **Open-Closed Principle (OCP)**; new extraction strategies can be added simply by appending to the `PLACEHOLDER_PATTERNS` regex list.

### 2.2 Reuse QAAgent (Dependency Inversion Principle)
`TemplateService` does not replicate the RAG workflow. Instead, it delegates individual question answering to the existing `QAAgent` using an injected dependency:
```python
question = f"What is the value for: {field_name}"
request = AskRequest(question=question)
response = await self._qa.answer(request)
```
This guarantees that all re-ranking, query routing, citation sourcing, and LLM optimizations immediately benefit template filling.

### 2.3 SSE Progress Streaming
The `/templates/fill` endpoint streams SSE events back to the client, replicating the streaming architecture of the `/chat` endpoint:
* `status`: pipeline phase updates (opening, analyzing, filling, saving).
* `field`: per-field results as they finish (status: `filled`/`failed`, generated value preview, confidence).
* `complete`: the final summary DTO.
* `done`: stream termination event.

### 2.4 Error Handling Resilience
If a specific field fails (e.g. empty LLM response, error from Qdrant, length exceeds `MAX_ANSWER_CHARS = 300`), the service logs the error, leaves the placeholder text untouched in the output PDF, and continues to the remaining fields. A status of `completed_with_errors` is returned in the final summary.

---

## 3. Endpoints

All endpoints mount under `/templates` and require valid JWT authentication:
* `POST /templates/analyze`: Uploads a PDF template and returns detected fields + a unique `file_id`.
* `POST /templates/fill`: Accepts a `file_id` and an optional subset list of `fields` to fill, streaming SSE progress.
* `GET /templates/download/{file_id}`: Serves the completed PDF file after enforcing ownership (validating that the file starts with the logged-in user's ID).

---

## 4. Modified & Added Files

### Backend (`services/agents/`)
* **[Modify]** [models.py](file:///Users/mac/Smart_buildingLLM/services/agents/models.py): Added template DTOs (`TemplateField`, `TemplateAnalyzeResponse`, `TemplateFillRequest`, `TemplateFillResponse`, `TemplateFillError`).
* **[New]** [template_service.py](file:///Users/mac/Smart_buildingLLM/services/agents/template_service.py): Core logic including `PlaceholderExtractor` and `TemplateService`.
* **[New]** [template_router.py](file:///Users/mac/Smart_buildingLLM/services/agents/template_router.py): Thin endpoint controllers.
* **[Modify]** [main.py](file:///Users/mac/Smart_buildingLLM/services/agents/main.py): Lifespan configuration, dependency injection, and router mounting.
* **[Modify]** [config.py](file:///Users/mac/Smart_buildingLLM/services/agents/config.py): Configured output directory and max file size properties.
* **[Modify]** [requirements.txt](file:///Users/mac/Smart_buildingLLM/services/agents/requirements.txt): Declared `PyMuPDF>=1.24.0`.

### Infrastructure
* **[Modify]** [docker-compose.yml](file:///Users/mac/Smart_buildingLLM/docker-compose.yml): Added output folder bind mount for persistence.

### Frontend (`services/chat-ui/`)
* **[Modify]** [api.ts](file:///Users/mac/Smart_buildingLLM/services/chat-ui/src/lib/api.ts): Expanded the API client to support template endpoints.
* **[Modify]** [Sidebar.tsx](file:///Users/mac/Smart_buildingLLM/services/chat-ui/src/components/Sidebar.tsx): Added templates view to `SidebarTab` state and added it to the profile menu.
* **[Modify]** [page.tsx](file:///Users/mac/Smart_buildingLLM/services/chat-ui/src/app/page.tsx): Handled layout switching when the templates tab is active.
* **[New]** [TemplateCenter.tsx](file:///Users/mac/Smart_buildingLLM/services/chat-ui/src/components/TemplateCenter.tsx): Built the frontend drag-drop, field list, progress bar, and download interface.

---

## 5. Verification Plan

### 5.1 Automated Tests
Verify python backend code functionality:
```bash
docker exec -it sb_agents python -m pytest /app/tests/test_template_service.py /app/tests/test_template_router.py -v --tb=short
```

Verify frontend TypeScript builds:
```bash
cd services/chat-ui
npx tsc --noEmit
```

### 5.2 Manual Verification
1. Boot the stack (`docker-compose up -d --build`).
2. Log in, select **Templates Center** from the user profile menu.
3. Drop a template PDF and verify that extracted placeholders appear in the preview table.
4. Select all fields and click **Auto-Fill**.
5. Ensure progress bar and field rows animate synchronously during SSE filling.
6. Download the generated file and verify text coordinates align correctly on pages.
