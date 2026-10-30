import React, {useCallback, useEffect, useState} from "react";
import {createRoot} from "react-dom/client";
import HoldingDecisionPanel from "../src/components/HoldingDecisionPanel";
import HoldingRecoveryPanel from "../src/components/HoldingRecoveryPanel";
import {
  getHoldingDecisionSupport,
  getHoldingManagement,
  getHoldingRecovery,
} from "../src/services/holdingsApi";
import "../src/holdings.css";

// True production React UI components against real GET Holdings FastAPI handlers;
// local only, ephemeral private snapshot, no write routes exposed.
function Fixture() {
  const [seed, setSeed] = useState(null);
  const [decision, setDecision] = useState(null);
  const [management, setManagement] = useState(null);
  const [recovery, setRecovery] = useState(null);
  const [error, setError] = useState(false);
  const refresh = useCallback(async (keys) => {
    const [decisionResult, managementResult, recoveryResult] = await Promise.all([
      getHoldingDecisionSupport(keys.stock_id),
      getHoldingManagement(keys.stock_id),
      getHoldingRecovery(keys.position_id),
    ]);
    setDecision(decisionResult);
    setManagement(managementResult);
    setRecovery(recoveryResult);
  }, []);

  useEffect(() => {
    let active = true;
    fetch("/__p004/seed", {cache: "no-store"})
      .then((r) => {if (!r.ok) throw new Error("seed unavailable"); return r.json();})
      .then(async (keys) => {
        if (!active) return;
        setSeed(keys);
        await refresh(keys);
      })
      .catch(() => { if (active) setError(true); });
    return () => {active = false;};
  }, [refresh]);

  const managementItem = management?.positions.find(
    (entry) => entry.position_id === seed?.position_id,
  );
  const positions = seed
    ? [{
      position_id: seed.position_id,
      account_name: managementItem?.account_name ?? "보유 계좌",
      provider: managementItem?.provider ?? "MANUAL",
      status: "OPEN",
    }]
    : [];

  return (
    <main>
      <h1>P0-04 실제 저장 데이터 조회 전용 화면 검증</h1>
      <p>운영 DB 사본에서만 읽습니다. 판단 갱신, 평가 저장, 계획 적용, 거래는 이 서버에서 차단됩니다.</p>
      {error && <p role="alert">테스트용 데이터를 불러오지 못했습니다.</p>}
      {decision && management && recovery && seed && (
        <>
          <HoldingDecisionPanel
            positions={positions}
            data={decision}
            management={management}
            status={{status: "AVAILABLE", reason_code: null}}
            onContextChanged={() => refresh(seed)}
            onPlanChanged={() => refresh(seed)}
          />
          <HoldingRecoveryPanel
            positions={positions}
            contexts={{[seed.position_id]: recovery}}
            status={{status: "AVAILABLE", reason_code: null}}
            onContextChanged={() => refresh(seed)}
          />
        </>
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<Fixture />);
