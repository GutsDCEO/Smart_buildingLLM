# 🧪 Manual Verification Guide — Ingestion Service

Follow these steps to verify that the Ingestion Service correctly extracts and chunks documents.

## 1. Prepare Environment
Open a terminal in the project root and install the dependencies (locally for testing):

```bash
cd services/ingestion
pip install -r requirements.txt
```

## 2. Start the Service
Run the FastAPI app using uvicorn:

```bash
uvicorn main:app --host 0.0.0.0 --port 8001 --reload
```
> [!NOTE]
> The service is now listening at `http://localhost:8001`.

---

## 3. Test Endpoints

### ✅ Check Health & Formats
Verify the service is up and knows its parsers:

```powershell
# PowerShell
Invoke-RestMethod -Uri "http://localhost:8001/health"
Invoke-RestMethod -Uri "http://localhost:8001/formats"
```

### 📄 Ingest a PDF
Pick any PDF file (e.g., `test.pdf`) and send it to the ingestion endpoint:

```powershell
# PowerShell
$filePath = "C:\path\to\your\document.pdf"
Invoke-RestMethod -Method Post -Uri "http://localhost:8001/ingest" -InFile $filePath -ContentType "multipart/form-data"
```

### 📝 Ingest a DOCX
Repeat with a Word document:

```powershell
# PowerShell
$filePath = "C:\path\to\your\document.docx"
Invoke-RestMethod -Method Post -Uri "http://localhost:8001/ingest" -InFile $filePath -ContentType "multipart/form-data"
```

---

## 4. What to Look For in the Response
A successful response (`200 OK`) should look like this:

```json
{
  "source_file": "document.pdf",
  "total_pages": 4,
  "total_chunks": 12,
  "chunks": [
    {
      "text": "The HVAC system in Building A consists of...",
      "chunk_index": 0,
      "token_count": 482,
      "source_file": "document.pdf",
      "page_number": 1,
      "start_char": 0,
      "end_char": 1024
    },
    ...
  ],
  "ingested_at": "2026-03-06T17:15:00Z"
}
```

- **Check `token_count`**: It should be $\le 500$ (default limit).
- **Check `chunks`**: The end of chunk 0 should overlap slightly with the start of chunk 1.
- **Check `page_number`**: Ensure it correctly tracks the source page.
