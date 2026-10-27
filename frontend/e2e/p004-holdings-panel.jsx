import React, {useCallback, useEffect, useState} from "react";
import {createRoot} from "react-dom/client";
import HoldingDecisionPanel from "../src/components/HoldingDecisionPanel";
import {getHoldingDecisionSupport, getHoldingManagement} from "../src/services/holdingsApi";

// A test-only React mount of the genuine production component.
// The browser suite intercepts ALL /api requests. No provider is reachable.
function Fixture() {
  const [data, setData] = useState(null);
  const [management, setManagement] = useState(null);
  const [error, setError] = useState(null);
  const refresh = useCallback(async () => {
    const [decision, plan] = await Promise.all([
      getHoldingDecisionSupport("stock-p004"),
      getHoldingManagement("stock-p004"),
    ]);
    setData(decision);
    setManagement(plan);
  }, []);

  useEffect(() => {
    refresh().catch((e) => setError(String(e)));
  }, [refresh]);

  return (
    <main>
      <h1>P0-04 Synthetic Holdings UAT</h1>
      {error && <p role="alert">{error}</p>}
      {data && management && (
        <HoldingDecisionPanel
          positions={[{
            position_id: "position-p004",
            account_name: "합성 수동 계좌",
            provider: "MANUAL",
          }]}
          data={data}
          management={management}
          status={{status: "AVAILABLE", reason_code: null}}
          onContextChanged={refresh}
          onPlanChanged={refresh}
        />
      )}
    </main>
  );
}

createRoot(document.getElementById("root")).render(<Fixture />);
