/**
 * Unit Tests — ChatMessage renderContent parser
 *
 * Tests the mermaid fence detection logic that splits message text
 * into plain text spans and MermaidDiagram components.
 */

import React from "react";
import { renderContent } from "../ChatMessage";

// ── Mock MermaidDiagram so we don't need the full mermaid library ──
jest.mock("../MermaidDiagram", () => ({
  __esModule: true,
  default: ({ code }: { code: string }) => (
    <div data-testid="mermaid-diagram" data-code={code} />
  ),
  MermaidSkeleton: () => <div data-testid="mermaid-skeleton" />,
}));

describe("renderContent — mermaid fence parser", () => {
  it("returns a single span for plain text", () => {
    const result = renderContent("Hello world");
    expect(result).toHaveLength(1);
    // Should be a span with text content
    const el = result[0] as React.ReactElement;
    expect(el.type).toBe("span");
    expect(el.props.children).toBe("Hello world");
  });

  it("returns a MermaidDiagram for a complete mermaid block", () => {
    const input = "```mermaid\ngraph TD\n  A-->B\n```";
    const result = renderContent(input);

    // Should contain at least one MermaidDiagram
    const diagrams = result.filter(
      (el) => React.isValidElement(el) && (el as React.ReactElement).props["data-testid"] === "mermaid-diagram"
    );
    expect(diagrams.length).toBe(1);
  });

  it("returns mixed text and diagram for interleaved content", () => {
    const input = "Explanation text\n```mermaid\ngraph TD\n  A-->B\n```\nMore text";
    const result = renderContent(input);

    // Should have 3 elements: span, diagram, span
    expect(result.length).toBe(3);

    const first = result[0] as React.ReactElement;
    expect(first.type).toBe("span");
    expect(first.props.children).toContain("Explanation text");

    const diagram = result[1] as React.ReactElement;
    expect(diagram.props["data-code"]).toBe("graph TD\n  A-->B");

    const last = result[2] as React.ReactElement;
    expect(last.type).toBe("span");
    expect(last.props.children).toContain("More text");
  });

  it("handles multiple mermaid blocks", () => {
    const input =
      "First\n```mermaid\ngraph TD\n  A-->B\n```\nMiddle\n```mermaid\ngraph LR\n  C-->D\n```\nLast";
    const result = renderContent(input);

    const diagrams = result.filter(
      (el) => React.isValidElement(el) && (el as React.ReactElement).props["data-code"]
    );
    expect(diagrams.length).toBe(2);
  });

  it("shows skeleton for incomplete fence during streaming", () => {
    const input = "Some text\n```mermaid\ngraph TD\n  A-->B";
    const result = renderContent(input, true);

    const skeletons = result.filter(
      (el) =>
        React.isValidElement(el) &&
        (el as React.ReactElement).props["data-testid"] === "mermaid-skeleton"
    );
    expect(skeletons.length).toBe(1);
  });

  it("does NOT show skeleton for incomplete fence when NOT streaming", () => {
    const input = "Some text\n```mermaid\ngraph TD\n  A-->B";
    const result = renderContent(input, false);

    const skeletons = result.filter(
      (el) =>
        React.isValidElement(el) &&
        (el as React.ReactElement).props["data-testid"] === "mermaid-skeleton"
    );
    expect(skeletons.length).toBe(0);
  });
});
