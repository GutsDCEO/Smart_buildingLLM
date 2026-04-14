"use client";

import type { CitationData } from "@/lib/api";

interface CitationCardProps {
  citation: CitationData;
  index: number;
}

export default function CitationCard({ citation, index }: CitationCardProps) {
  const score = Math.round(citation.relevance_score * 100);
  const scoreColor =
    score >= 85 ? "#22c55e" : score >= 65 ? "#f59e0b" : "#ef4444";

  return (
    <div className="citation-card">
      <span className="citation-index">[{index + 1}]</span>
      <div className="citation-body">
        <span className="citation-file">📄 {citation.source_file}</span>
        {citation.page_number != null && (
          <span className="citation-page">p. {citation.page_number}</span>
        )}
      </div>
      <span className="citation-score" style={{ color: scoreColor }}>
        {score}%
      </span>
    </div>
  );
}
