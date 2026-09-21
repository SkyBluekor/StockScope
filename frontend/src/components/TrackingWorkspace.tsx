import { useState } from "react";
import RecommendationTracking from "./RecommendationTracking";
import SimulationWorkspace from "./SimulationWorkspace";
import "../tracking.css";

export default function TrackingWorkspace() {
  const [mode, setMode] = useState<"tracking" | "historical">("tracking");
  return (
    <div className="tracking-shell">
      <div className="tracking-mode-switch" role="tablist" aria-label="종목 성과 추적과 전략 성과 검증">
        <button role="tab" aria-selected={mode === "tracking"} className={mode === "tracking" ? "active" : ""} onClick={() => setMode("tracking")}>종목 성과 추적</button>
        <button role="tab" aria-selected={mode === "historical"} className={mode === "historical" ? "active" : ""} onClick={() => setMode("historical")}>전략 성과 검증</button>
      </div>
      {mode === "tracking" ? <RecommendationTracking /> : <SimulationWorkspace />}
    </div>
  );
}
