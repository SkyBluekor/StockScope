import { useState } from "react";
import RecommendationTracking from "./RecommendationTracking";
import SimulationWorkspace from "./SimulationWorkspace";
import "../tracking.css";

export default function TrackingWorkspace() {
  const [mode, setMode] = useState<"tracking" | "historical">("tracking");
  return (
    <div className="tracking-shell">
      <div className="tracking-mode-switch" role="tablist" aria-label="종목 성과 추적과 과거 전략 검증">
        <button role="tab" aria-selected={mode === "tracking"} className={mode === "tracking" ? "active" : ""} onClick={() => setMode("tracking")}>종목 성과 추적</button>
        <button role="tab" aria-selected={mode === "historical"} className={mode === "historical" ? "active" : ""} onClick={() => setMode("historical")}>과거 전략 검증</button>
      </div>
      <p className="tracking-mode-guide">{mode === "tracking"
        ? "선택한 종목의 이후 움직임과 성과를 기록해 Scanner 개선 자료로 쌓습니다."
        : "Scanner 전략 전체를 과거 시장에 적용해 성능을 검증하는 연구 화면입니다."}</p>
      {mode === "tracking" ? <RecommendationTracking /> : <SimulationWorkspace />}
    </div>
  );
}
