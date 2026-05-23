/**
 * Unit Tests — MermaidDiagram component
 *
 * Tests rendering, error fallback, expand modal, and export functions.
 * Mermaid library is mocked to avoid actual SVG rendering in test env.
 */

import React from "react";
import { render, screen, fireEvent, act, waitFor } from "@testing-library/react";
import "@testing-library/jest-dom";

// ── Mock mermaid library ──────────────────────────────────────────
const mockRender = jest.fn();
jest.mock("mermaid", () => ({
  __esModule: true,
  default: {
    initialize: jest.fn(),
    render: mockRender,
  },
}));

// ── Mock html-to-image ────────────────────────────────────────────
const mockToPng = jest.fn();
jest.mock("html-to-image", () => ({
  toPng: mockToPng,
}));

// ── Import component AFTER mocks ──────────────────────────────────
import MermaidDiagram, { MermaidSkeleton } from "../MermaidDiagram";

// ── Helpers ───────────────────────────────────────────────────────
const SAMPLE_CODE = "graph TD\n  A[Chiller]-->B[AHU]";
const SAMPLE_SVG = '<svg xmlns="http://www.w3.org/2000/svg"><rect/></svg>';

beforeEach(() => {
  jest.clearAllMocks();
  mockRender.mockResolvedValue({ svg: SAMPLE_SVG });
  mockToPng.mockResolvedValue("data:image/png;base64,abc123");

  // Mock clipboard
  Object.assign(navigator, {
    clipboard: { writeText: jest.fn().mockResolvedValue(undefined) },
  });
});

describe("MermaidDiagram — rendering", () => {
  it("renders SVG when mermaid.render succeeds", async () => {
    render(<MermaidDiagram code={SAMPLE_CODE} />);

    await waitFor(() => {
      const body = document.querySelector(".mermaid-body");
      expect(body).toBeTruthy();
      expect(body?.innerHTML).toContain("<svg");
    });
  });

  it("injects HVAC classDefs into the code", async () => {
    render(<MermaidDiagram code={SAMPLE_CODE} />);

    await waitFor(() => {
      expect(mockRender).toHaveBeenCalled();
      const renderedCode = mockRender.mock.calls[0][1];
      expect(renderedCode).toContain("classDef hot");
      expect(renderedCode).toContain("classDef cold");
      expect(renderedCode).toContain("classDef sensor");
      expect(renderedCode).toContain("classDef alarm");
      expect(renderedCode).toContain("classDef controller");
    });
  });

  it("cleans invalid C/JS style comments from code before rendering", async () => {
    const dirtyCode = "graph TD\n  A-->B /* comment 1 */\n  C-->D // comment 2\n  E-->F http://example.com";
    render(<MermaidDiagram code={dirtyCode} />);

    await waitFor(() => {
      expect(mockRender).toHaveBeenCalled();
      const renderedCode = mockRender.mock.calls[mockRender.mock.calls.length - 1][1];
      expect(renderedCode).not.toContain("/* comment 1 */");
      expect(renderedCode).not.toContain("// comment 2");
      expect(renderedCode).toContain("http://example.com"); // URL preserved
    });
  });

  it("shows error fallback when mermaid.render fails", async () => {
    mockRender.mockRejectedValueOnce(new Error("Parse error at line 2"));

    render(<MermaidDiagram code="invalid syntax |||" />);

    await waitFor(() => {
      const errorEl = document.querySelector(".mermaid-error");
      expect(errorEl).toBeTruthy();
      expect(errorEl?.textContent).toContain("invalid syntax");
      expect(errorEl?.textContent).toContain("Parse error");
    });
  });

  it("renders card header with title", async () => {
    render(<MermaidDiagram code={SAMPLE_CODE} />);

    await waitFor(() => {
      const title = document.querySelector(".mermaid-title");
      expect(title?.textContent).toContain("System Diagram");
    });
  });
});

describe("MermaidDiagram — expand modal", () => {
  it("opens modal when expand button is clicked", async () => {
    render(<MermaidDiagram code={SAMPLE_CODE} />);

    await waitFor(() => {
      expect(document.querySelector(".mermaid-body")).toBeTruthy();
    });

    // Find and click expand button
    const expandBtn = document.querySelector("[title='Expand diagram']");
    expect(expandBtn).toBeTruthy();
    fireEvent.click(expandBtn!);

    expect(document.querySelector(".mermaid-modal-backdrop")).toBeTruthy();
    expect(document.querySelector(".mermaid-modal")).toBeTruthy();
  });

  it("closes modal on Escape key", async () => {
    render(<MermaidDiagram code={SAMPLE_CODE} />);

    await waitFor(() => {
      expect(document.querySelector(".mermaid-body")).toBeTruthy();
    });

    const expandBtn = document.querySelector("[title='Expand diagram']");
    fireEvent.click(expandBtn!);
    expect(document.querySelector(".mermaid-modal-backdrop")).toBeTruthy();

    fireEvent.keyDown(window, { key: "Escape" });
    expect(document.querySelector(".mermaid-modal-backdrop")).toBeFalsy();
  });

  it("closes modal on backdrop click", async () => {
    render(<MermaidDiagram code={SAMPLE_CODE} />);

    await waitFor(() => {
      expect(document.querySelector(".mermaid-body")).toBeTruthy();
    });

    const expandBtn = document.querySelector("[title='Expand diagram']");
    fireEvent.click(expandBtn!);

    const backdrop = document.querySelector(".mermaid-modal-backdrop");
    expect(backdrop).toBeTruthy();
    fireEvent.click(backdrop!);
    expect(document.querySelector(".mermaid-modal-backdrop")).toBeFalsy();
  });
});

describe("MermaidDiagram — export functions", () => {
  it("copies raw mermaid code to clipboard", async () => {
    render(<MermaidDiagram code={SAMPLE_CODE} />);

    await waitFor(() => {
      expect(document.querySelector(".mermaid-body")).toBeTruthy();
    });

    const copyBtn = document.querySelector("[title='Copy mermaid code']");
    expect(copyBtn).toBeTruthy();
    fireEvent.click(copyBtn!);

    expect(navigator.clipboard.writeText).toHaveBeenCalledWith(SAMPLE_CODE);
  });

  it("triggers SVG download", async () => {
    // Mock URL.createObjectURL and revokeObjectURL
    const mockUrl = "blob:http://localhost/test-svg";
    global.URL.createObjectURL = jest.fn().mockReturnValue(mockUrl);
    global.URL.revokeObjectURL = jest.fn();

    const clickSpy = jest.fn();
    jest.spyOn(document, "createElement").mockImplementation((tag: string) => {
      if (tag === "a") {
        const el = { href: "", download: "", click: clickSpy } as unknown as HTMLElement;
        return el;
      }
      return document.createElement(tag);
    });

    render(<MermaidDiagram code={SAMPLE_CODE} />);

    await waitFor(() => {
      expect(document.querySelector(".mermaid-body")).toBeTruthy();
    });

    const svgBtn = document.querySelector("[title='Download SVG']");
    expect(svgBtn).toBeTruthy();
    fireEvent.click(svgBtn!);

    expect(global.URL.createObjectURL).toHaveBeenCalled();
    expect(clickSpy).toHaveBeenCalled();

    jest.restoreAllMocks();
  });
});

describe("MermaidSkeleton", () => {
  it("renders skeleton with spinner and text", () => {
    render(<MermaidSkeleton />);

    const skeleton = document.querySelector(".mermaid-card--skeleton");
    expect(skeleton).toBeTruthy();

    const spinner = document.querySelector(".mermaid-skeleton-spinner");
    expect(spinner).toBeTruthy();

    expect(skeleton?.textContent).toContain("Generating diagram");
  });
});
