"use client";

export type Stage = "guardrail" | "router" | "retrieval" | "generating" | "done" | "idle";

const STAGES: { id: Stage; label: string; icon: string }[] = [
  { id: "guardrail",  label: "Guard",    icon: "🛡️" },
  { id: "router",     label: "Route",    icon: "🚦" },
  { id: "retrieval",  label: "Search",   icon: "🔍" },
  { id: "generating", label: "Generate", icon: "✨" },
];

interface PipelineStatusProps {
  activeStage: Stage;
}

export default function PipelineStatus({ activeStage }: PipelineStatusProps) {
  if (activeStage === "idle" || activeStage === "done") return null;

  const activeIndex = STAGES.findIndex((s) => s.id === activeStage);

  return (
    <div className="pipeline-bar">
      {STAGES.map((stage, i) => {
        const state =
          i < activeIndex ? "past" : i === activeIndex ? "active" : "future";
        return (
          <div key={stage.id} className={`pipeline-step pipeline-step--${state}`}>
            <span className="pipeline-icon">{stage.icon}</span>
            <span className="pipeline-label">{stage.label}</span>
            {i < STAGES.length - 1 && <span className="pipeline-arrow">›</span>}
          </div>
        );
      })}
    </div>
  );
}
