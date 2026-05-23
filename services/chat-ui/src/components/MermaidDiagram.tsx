"use client";

import { useEffect, useRef, useState, useId, useCallback } from "react";

// ── HVAC class definitions injected into every diagram ──────────
const HVAC_CLASS_DEFS = `
classDef hot fill:#c53030,stroke:#fc8181,color:#fff
classDef cold fill:#2b6cb0,stroke:#63b3ed,color:#fff
classDef sensor fill:#2f855a,stroke:#68d391,color:#fff
classDef alarm fill:#c05621,stroke:#ed8936,color:#fff
classDef controller fill:#6b46c1,stroke:#9f7aea,color:#fff
`.trim();

// ── Clean LLM-generated code before rendering ──────────────────
// Removes invalid syntax that LLMs commonly add to Mermaid blocks:
//  1. C-style block comments:  /* ... */
//  2. Inline comments:         // ...  (preserves http:// URLs)
//  3. LLM-generated classDef lines (we inject our own HVAC_CLASS_DEFS,
//     so duplicates cause silent parse failures in Mermaid 11+)
//  4. LLM-generated class assignment lines that reference removed defs
//  5. Trailing semicolons on any line (Mermaid does not use semicolons)
function cleanMermaidCode(rawCode: string): string {
  return rawCode
    .replace(/\/\*[\s\S]*?\*\//g, "")                   // Strip /* ... */
    .replace(/(^|[^\s:])\s*\/\/(?![\w/]).*$/gm, "$1")   // Strip // comments, keep http://
    .replace(/^\s*classDef\s+\S+.*$/gm, "")             // Strip LLM classDef lines
    .replace(/^\s*class\s+[\w,]+\s+\w+\s*$/gm, "")      // Strip LLM class assignments
    .replace(/;(\s*)$/gm, "$1")                          // Strip trailing semicolons
    .replace(/\n{3,}/g, "\n\n")                          // Collapse excess blank lines
    .trim();
}

interface MermaidDiagramProps {
  code: string;
}

export default function MermaidDiagram({ code }: MermaidDiagramProps) {
  const uniqueId = useId().replace(/:/g, "m"); // mermaid IDs can't have colons
  const diagramId = `mermaid-${uniqueId}`;
  const containerRef = useRef<HTMLDivElement>(null);
  const modalContainerRef = useRef<HTMLDivElement>(null);

  const [svgHtml, setSvgHtml] = useState<string>("");
  const [error, setError] = useState<string>("");
  const [copied, setCopied] = useState(false);
  const [expanded, setExpanded] = useState(false);

  // ── Render mermaid to SVG ──────────────────────────────────────
  useEffect(() => {
    let cancelled = false;

    async function render() {
      try {
        // Dynamic import to avoid SSR issues with mermaid
        const mermaid = (await import("mermaid")).default;

        mermaid.initialize({
          startOnLoad: false,
          securityLevel: "strict",
          suppressErrorRendering: true,
          theme: "dark",
          themeVariables: {
            primaryColor: "#2d2d2d",
            primaryTextColor: "#ececec",
            primaryBorderColor: "rgba(255,255,255,0.15)",
            lineColor: "#9f7aea",
            secondaryColor: "#2a2a2a",
            tertiaryColor: "#1a1a1a",
            fontFamily: "Inter, system-ui, sans-serif",
            fontSize: "14px",
          },
          flowchart: {
            htmlLabels: true,
            curve: "basis",
            padding: 12,
            nodeSpacing: 50,
            rankSpacing: 60,
          },
        });

        // Clean any invalid JS/C style comments from the LLM output
        const cleanedCode = cleanMermaidCode(code);

        // Inject HVAC class definitions after the graph declaration
        const codeWithClasses = `${cleanedCode}\n${HVAC_CLASS_DEFS}`;

        // Use a highly unique ID per render call to completely bypass mermaid's internal cache
        const renderId = `${diagramId}-${Date.now()}-${Math.floor(Math.random() * 1000)}`;

        const { svg } = await mermaid.render(renderId, codeWithClasses);

        if (!cancelled) {
          setSvgHtml(svg);
          setError("");
        }
      } catch (err: unknown) {
        console.error("[Mermaid Render Error]", err);
        if (!cancelled) {
          const msg = err instanceof Error ? err.message : "Failed to render diagram";
          setError(msg);
          setSvgHtml("");
        }
      }
    }

    render();
    return () => { cancelled = true; };
  }, [code, diagramId]);

  // ── Close modal on Escape ──────────────────────────────────────
  useEffect(() => {
    if (!expanded) return;
    const handler = (e: KeyboardEvent) => {
      if (e.key === "Escape") setExpanded(false);
    };
    window.addEventListener("keydown", handler);
    return () => window.removeEventListener("keydown", handler);
  }, [expanded]);

  // ── Copy raw mermaid code ──────────────────────────────────────
  const handleCopy = useCallback(() => {
    navigator.clipboard.writeText(code).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    });
  }, [code]);

  // ── Download SVG ───────────────────────────────────────────────
  const handleDownloadSvg = useCallback(() => {
    if (!svgHtml) return;
    const blob = new Blob([svgHtml], { type: "image/svg+xml" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "diagram.svg";
    a.click();
    URL.revokeObjectURL(url);
  }, [svgHtml]);

  // ── Download PNG ───────────────────────────────────────────────
  const handleDownloadPng = useCallback(async () => {
    const target = expanded ? modalContainerRef.current : containerRef.current;
    const svgEl = target?.querySelector("svg");
    if (!svgEl) return;

    try {
      const { toPng } = await import("html-to-image");
      const dataUrl = await toPng(svgEl as unknown as HTMLElement, {
        backgroundColor: "#2a2a2a",
        pixelRatio: 2,
      });
      const a = document.createElement("a");
      a.href = dataUrl;
      a.download = "diagram.png";
      a.click();
    } catch {
      // Silently fail — PNG export is best-effort
    }
  }, [expanded]);

  // ── Action buttons (shared between card and modal) ─────────────
  const renderActions = () => (
    <div className="mermaid-actions">
      {!expanded && (
        <button
          className="action-btn"
          onClick={() => setExpanded(true)}
          title="Expand diagram"
          id={`${diagramId}-expand`}
        >
          ⛶
        </button>
      )}
      <button
        className="action-btn"
        onClick={handleCopy}
        title="Copy mermaid code"
        id={`${diagramId}-copy`}
      >
        {copied ? "✓" : "⎘"}
      </button>
      <button
        className="action-btn"
        onClick={handleDownloadSvg}
        title="Download SVG"
        disabled={!svgHtml}
        id={`${diagramId}-svg`}
      >
        SVG
      </button>
      <button
        className="action-btn"
        onClick={handleDownloadPng}
        title="Download PNG"
        disabled={!svgHtml}
        id={`${diagramId}-png`}
      >
        PNG
      </button>
    </div>
  );

  return (
    <>
      {/* Inline Card */}
      <div className="mermaid-card" id={diagramId}>
        <div className="mermaid-header">
          <span className="mermaid-title">📊 System Diagram</span>
          {renderActions()}
        </div>

        {error ? (
          <div className="mermaid-error">
            <pre>{code}</pre>
            <div style={{ marginTop: 8, fontSize: 11, opacity: 0.7 }}>
              ⚠ Diagram render error: {error}
            </div>
          </div>
        ) : svgHtml ? (
          <div
            ref={containerRef}
            className="mermaid-body"
            dangerouslySetInnerHTML={{ __html: svgHtml }}
          />
        ) : (
          <div className="mermaid-body">
            <div className="mermaid-loading">Rendering diagram…</div>
          </div>
        )}
      </div>

      {/* Fullscreen Modal */}
      {expanded && (
        <div
          className="mermaid-modal-backdrop"
          onClick={(e) => {
            if (e.target === e.currentTarget) setExpanded(false);
          }}
        >
          <div className="mermaid-modal">
            <div className="mermaid-modal-header">
              <span className="mermaid-title">📊 System Diagram</span>
              <div className="mermaid-modal-header-right">
                {renderActions()}
                <button
                  className="mermaid-modal-close"
                  onClick={() => setExpanded(false)}
                  title="Close (Esc)"
                  id={`${diagramId}-close`}
                >
                  ×
                </button>
              </div>
            </div>

            {svgHtml ? (
              <div
                ref={modalContainerRef}
                className="mermaid-modal-body"
                dangerouslySetInnerHTML={{ __html: svgHtml }}
              />
            ) : (
              <div className="mermaid-modal-body">
                <div className="mermaid-loading">Rendering diagram…</div>
              </div>
            )}
          </div>
        </div>
      )}
    </>
  );
}

// ── Skeleton placeholder shown during streaming ──────────────────
export function MermaidSkeleton() {
  return (
    <div className="mermaid-card mermaid-card--skeleton">
      <div className="mermaid-header">
        <span className="mermaid-title">📊 System Diagram</span>
      </div>
      <div className="mermaid-skeleton-body">
        <div className="mermaid-skeleton-spinner" />
        <span>Generating diagram…</span>
      </div>
    </div>
  );
}
