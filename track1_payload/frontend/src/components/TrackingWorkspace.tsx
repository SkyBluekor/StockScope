import { useState } from "react";
import RecommendationTracking from "./RecommendationTracking";
import SimulationWorkspace from "./SimulationWorkspace";
import "../tracking.css";

export default function TrackingWorkspace() {
  const [mode, setMode] = useState<"tracking" | "historical">("tracking");
  return (
    <div className="tracking-shell">
      <div className="tracking-mode-switch" role="tablist" aria-label="추천 추적 기능">
        <button role="tab" aria-selected={mode === "tracking"} className={mode === "tracking" ? "active" : ""} onClick={() => setMode("tracking")}>추천 추적</button>
        <button role="tab" aria-selected={mode === "historical"} className={mode === "historical" ? "active" : ""} onClick={() => setMode("historical")}>과거 전략 검증</button>
      </div>
      {mode === "tracking" ? <RecommendationTracking /> : <SimulationWorkspace />}
    </div>
  );
}
