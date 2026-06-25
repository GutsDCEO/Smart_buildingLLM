"use client";

import { useState, useRef, DragEvent, ChangeEvent } from "react";
import {
  analyzeTemplate,
  streamFillTemplate,
  downloadTemplate,
  type TemplateField,
  type TemplateAnalyzeResponse,
  type TemplateSSEEvent
} from "@/lib/api";

const TYPE_ICONS: Record<string, string> = {
  acroform: "⚙️",
  bracket: "🏷️",
  underscore: "✍️",
  mustache: "{{}}",
};

export default function TemplateCenter() {
  const [file, setFile] = useState<File | null>(null);
  const [isDragOver, setIsDragOver] = useState(false);
  const [isLoading, setIsLoading] = useState(false);
  const [analysis, setAnalysis] = useState<TemplateAnalyzeResponse | null>(null);
  const [selectedFields, setSelectedFields] = useState<string[]>([]);
  const [isFilling, setIsFilling] = useState(false);

  const [fillProgress, setFillProgress] = useState<{
    stage: string;
    message: string;
    progress?: number;
    total?: number;
  } | null>(null);

  const [fieldResults, setFieldResults] = useState<Record<string, {
    status: "pending" | "loading" | "filled" | "failed";
    value?: string;
    confidence?: number;
    error?: string;
  }>>({});

  const [downloadFileId, setDownloadFileId] = useState<string | null>(null);
  const [downloadSuccess, setDownloadSuccess] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const fileInputRef = useRef<HTMLInputElement>(null);
  const abortControllerRef = useRef<AbortController | null>(null);

  // ── Drag & Drop Handlers ──────────────────────────────────────────

  const handleDragOver = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(true);
  };

  const handleDragLeave = () => {
    setIsDragOver(false);
  };

  const handleDrop = (e: DragEvent) => {
    e.preventDefault();
    setIsDragOver(false);
    const droppedFile = e.dataTransfer.files?.[0];
    if (droppedFile && droppedFile.type === "application/pdf") {
      setFile(droppedFile);
      handleAnalyze(droppedFile);
    } else {
      setError("Only PDF files are supported as templates.");
    }
  };

  const handleFileChange = (e: ChangeEvent<HTMLInputElement>) => {
    const selectedFile = e.target.files?.[0];
    if (selectedFile) {
      setFile(selectedFile);
      handleAnalyze(selectedFile);
    }
  };

  // ── API Calls ─────────────────────────────────────────────────────

  const handleAnalyze = async (targetFile: File) => {
    setIsLoading(true);
    setError(null);
    setAnalysis(null);
    setDownloadFileId(null);
    setDownloadSuccess(false);
    setFillProgress(null);
    setFieldResults({});

    try {
      const res = await analyzeTemplate(targetFile);
      if (res) {
        setAnalysis(res);
        // Default to select all fields
        const allNames = res.fields.map(f => f.field_name);
        setSelectedFields(allNames);

        // Initialize fields as pending
        const initialResults: typeof fieldResults = {};
        res.fields.forEach(f => {
          initialResults[f.field_name] = {
            status: "pending",
            value: f.current_value || undefined
          };
        });
        setFieldResults(initialResults);
      } else {
        setError("Failed to analyze the template. Please check if it is a valid PDF.");
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "An error occurred during template analysis.");
    } finally {
      setIsLoading(false);
    }
  };

  const handleFieldToggle = (fieldName: string) => {
    if (isFilling) return;
    setSelectedFields(prev =>
      prev.includes(fieldName)
        ? prev.filter(name => name !== fieldName)
        : [...prev, fieldName]
    );
  };

  const handleToggleAll = () => {
    if (isFilling || !analysis) return;
    if (selectedFields.length === analysis.fields.length) {
      setSelectedFields([]);
    } else {
      setSelectedFields(analysis.fields.map(f => f.field_name));
    }
  };

  const handleFill = async () => {
    if (!analysis || selectedFields.length === 0 || isFilling) return;

    setIsFilling(true);
    setError(null);
    setDownloadFileId(null);
    setDownloadSuccess(false);

    // Reset status of selected fields to loading, others remain pending
    setFieldResults(prev => {
      const updated = { ...prev };
      analysis.fields.forEach(f => {
        if (selectedFields.includes(f.field_name)) {
          updated[f.field_name] = { status: "pending" };
        }
      });
      return updated;
    });

    const controller = new AbortController();
    abortControllerRef.current = controller;

    try {
      const stream = streamFillTemplate(analysis.file_id, selectedFields, controller.signal);

      for await (const event of stream) {
        switch (event.type) {
          case "status":
            setFillProgress(event.data);
            break;

          case "field":
            const fieldData = event.data;
            setFieldResults(prev => ({
              ...prev,
              [fieldData.field_name]: {
                status: fieldData.status === "filled" ? "filled" : "failed",
                value: fieldData.value,
                confidence: fieldData.confidence,
                error: fieldData.error,
              }
            }));
            break;

          case "complete":
            setDownloadFileId(event.data.file_id);
            break;

          case "error":
            setError(event.data.message);
            break;

          case "done":
            setIsFilling(false);
            setFillProgress(null);
            break;
        }
      }
    } catch (err) {
      if (err instanceof Error && err.name === "AbortError") {
        setError("Template filling process was cancelled.");
      } else {
        setError(err instanceof Error ? err.message : "An error occurred during filling.");
      }
      setIsFilling(false);
      setFillProgress(null);
    } finally {
      abortControllerRef.current = null;
    }
  };

  const handleCancel = () => {
    if (abortControllerRef.current) {
      abortControllerRef.current.abort();
    }
  };

  const handleDownload = async () => {
    if (!downloadFileId || !analysis) return;

    try {
      const blob = await downloadTemplate(downloadFileId);
      if (blob) {
        const url = window.URL.createObjectURL(blob);
        const a = document.createElement("a");
        a.href = url;
        a.download = `filled_${analysis.filename}`;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
        window.URL.revokeObjectURL(url);
        setDownloadSuccess(true);
      } else {
        setError("Could not download the filled PDF. Try again or check server logs.");
      }
    } catch (err) {
      setError("Failed to download PDF: " + (err instanceof Error ? err.message : String(err)));
    }
  };

  const handleReset = () => {
    setFile(null);
    setAnalysis(null);
    setSelectedFields([]);
    setFieldResults({});
    setDownloadFileId(null);
    setDownloadSuccess(false);
    setFillProgress(null);
    setError(null);
    if (fileInputRef.current) fileInputRef.current.value = "";
  };

  // ── Render ────────────────────────────────────────────────────────

  return (
    <div className="tmpl-container">
      {/* Header */}
      <div className="tmpl-header">
        <h2 className="tmpl-title">📑 Document Templates</h2>
        <p className="tmpl-subtitle">
          Upload an IoT or Building Form PDF, extract placeholders, and fill them via RAG
        </p>
      </div>

      <div className="tmpl-content">
        {/* Error Alert */}
        {error && (
          <div className="tmpl-error-box">
            ⚠️ {error}
          </div>
        )}

        {/* 1. Upload state */}
        {!analysis && !isLoading && (
          <div
            className={`tmpl-dropzone ${isDragOver ? "tmpl-dropzone--dragover" : ""}`}
            onDragOver={handleDragOver}
            onDragLeave={handleDragLeave}
            onDrop={handleDrop}
            onClick={() => fileInputRef.current?.click()}
          >
            <input
              ref={fileInputRef}
              type="file"
              accept=".pdf"
              onChange={handleFileChange}
              style={{ display: "none" }}
            />
            <span className="tmpl-dropzone-icon">📤</span>
            <p className="tmpl-dropzone-text">Drag & drop your PDF template here</p>
            <p className="tmpl-dropzone-subtext">or click to browse local files (max 25MB)</p>
          </div>
        )}

        {/* Loading Spinner */}
        {isLoading && (
          <div className="kb-loading" style={{ padding: "40px", textAlign: "center" }}>
            ⏳ Analyzing document structures and extracting placeholder patterns...
          </div>
        )}

        {/* 2. Analysis & Extraction Preview */}
        {analysis && (
          <>
            {/* Template Info Card */}
            <div className="kb-doc-card" style={{ padding: "16px 20px", display: "flex", gap: "16px" }}>
              <span style={{ fontSize: "28px" }}>📄</span>
              <div style={{ flex: 1 }}>
                <span className="kb-doc-name">{analysis.filename}</span>
                <div className="kb-doc-meta" style={{ marginTop: "4px" }}>
                  <span>{analysis.total_fields} fields detected</span>
                  <span className="kb-doc-sep">·</span>
                  <span>{selectedFields.length} selected</span>
                </div>
              </div>
              <button
                className="tmpl-btn-secondary"
                style={{ padding: "6px 12px", fontSize: "12px" }}
                onClick={handleReset}
                disabled={isFilling}
              >
                Reset Template
              </button>
            </div>

            {/* Progress Card during SSE filling */}
            {fillProgress && (
              <div className="tmpl-progress-card">
                <div className="tmpl-progress-header">
                  <span className="tmpl-progress-stage">
                    ⚡ Stage: {fillProgress.stage.toUpperCase()}
                  </span>
                  {fillProgress.progress !== undefined && fillProgress.total !== undefined && (
                    <span className="tmpl-progress-pct">
                      {Math.round((fillProgress.progress / fillProgress.total) * 100)}%
                    </span>
                  )}
                </div>
                {fillProgress.progress !== undefined && fillProgress.total !== undefined && (
                  <div className="tmpl-progress-bar-bg">
                    <div
                      className="tmpl-progress-bar-fg"
                      style={{ width: `${(fillProgress.progress / fillProgress.total) * 100}%` }}
                    />
                  </div>
                )}
                <div className="tmpl-progress-message">
                  {fillProgress.message}
                </div>
              </div>
            )}

            {/* Table of Fields */}
            <div className="tmpl-table-wrapper">
              <div className="tmpl-table-header">
                <span>Extracted Placeholders</span>
                <button
                  className="tmpl-btn-secondary"
                  style={{ padding: "4px 10px", fontSize: "11px" }}
                  onClick={handleToggleAll}
                  disabled={isFilling}
                >
                  {selectedFields.length === analysis.fields.length ? "Deselect All" : "Select All"}
                </button>
              </div>
              <div className="tmpl-table-scroll">
                <table className="tmpl-table">
                  <thead>
                    <tr>
                      <th style={{ width: "40px", textAlign: "center" }}>
                        <input
                          type="checkbox"
                          checked={analysis.fields.length > 0 && selectedFields.length === analysis.fields.length}
                          onChange={handleToggleAll}
                          disabled={isFilling}
                        />
                      </th>
                      <th>Placeholder Name</th>
                      <th>Type</th>
                      <th>Page</th>
                      <th>Filled Value Preview</th>
                      <th>Confidence</th>
                      <th>Status</th>
                    </tr>
                  </thead>
                  <tbody>
                    {analysis.fields.map((field) => {
                      const res = fieldResults[field.field_name] || { status: "pending" };
                      const isSelected = selectedFields.includes(field.field_name);

                      return (
                        <tr key={field.field_name} style={{ opacity: isSelected ? 1 : 0.45 }}>
                          <td style={{ textAlign: "center" }}>
                            <input
                              type="checkbox"
                              checked={isSelected}
                              onChange={() => handleFieldToggle(field.field_name)}
                              disabled={isFilling}
                            />
                          </td>
                          <td style={{ fontWeight: 600, color: "var(--text-primary)" }}>
                            {field.field_name}
                          </td>
                          <td>
                            <span className={`tmpl-badge tmpl-badge--${field.field_type}`}>
                              {TYPE_ICONS[field.field_type] || ""} {field.field_type}
                            </span>
                          </td>
                          <td>{field.page_number}</td>
                          <td>
                            {res.status === "filled" && (
                              <span style={{ color: "var(--text-primary)", fontStyle: "normal" }}>
                                {res.value}
                              </span>
                            )}
                            {res.status === "failed" && (
                              <span style={{ color: "var(--accent-red)", fontSize: "12px" }}>
                                {res.error}
                              </span>
                            )}
                            {res.status === "pending" && (
                              <span style={{ color: "var(--text-muted)", fontStyle: "italic" }}>
                                {field.current_value ? `Default: ${field.current_value}` : "Not filled yet"}
                              </span>
                            )}
                            {res.status === "loading" && (
                              <span style={{ color: "var(--accent-amber)", fontStyle: "italic" }}>
                                Generating answer...
                              </span>
                            )}
                          </td>
                          <td>
                            {res.confidence !== undefined ? (
                              <span style={{ fontWeight: 600 }}>
                                {Math.round(res.confidence * 100)}%
                              </span>
                            ) : (
                              <span style={{ color: "var(--text-muted)" }}>-</span>
                            )}
                          </td>
                          <td>
                            {res.status === "pending" && (
                              <span className="tmpl-status tmpl-status--pending">💤 Idle</span>
                            )}
                            {res.status === "loading" && (
                              <span className="tmpl-status tmpl-status--loading">⏳ Filling</span>
                            )}
                            {res.status === "filled" && (
                              <span className="tmpl-status tmpl-status--success">✅ Ready</span>
                            )}
                            {res.status === "failed" && (
                              <span className="tmpl-status tmpl-status--failed">❌ Failed</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            </div>

            {/* Action Bar */}
            <div className="tmpl-actions">
              {isFilling ? (
                <button className="tmpl-btn-primary" style={{ backgroundColor: "var(--accent-red)" }} onClick={handleCancel}>
                  ⏹ Cancel Process
                </button>
              ) : (
                <button
                  className="tmpl-btn-primary"
                  onClick={handleFill}
                  disabled={selectedFields.length === 0}
                >
                  🚀 Auto-Fill Selected ({selectedFields.length})
                </button>
              )}
            </div>

            {/* 3. Final Download Result Card */}
            {downloadFileId && !isFilling && (
              <div className="tmpl-download-card">
                <div className="tmpl-download-info">
                  <div className="tmpl-download-title">🎉 Document Auto-Fill Complete!</div>
                  <div className="tmpl-download-sub">
                    Successfully wrote RAG answers into the PDF layout placeholders.
                  </div>
                </div>
                <button className="tmpl-download-btn" onClick={handleDownload}>
                  {downloadSuccess ? "📥 Download Again" : "📥 Download Filled PDF"}
                </button>
              </div>
            )}
          </>
        )}
      </div>
    </div>
  );
}
