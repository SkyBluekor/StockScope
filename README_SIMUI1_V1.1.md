# SIM.UI.1 v1.1 Router Hotfix

The original SIM.UI.1 apply was rolled back after the combined regression suite showed that the aggregate API router exposed only `position-marks`.

v1.1 keeps the same UI and Simulation behavior but changes `backend/app/api/simulation.py` to explicitly register the stable SIM.1/SIM.2/SIM.3 endpoint functions with `APIRouter.add_api_route()` instead of nesting the three module-level routers. This makes the aggregate route contract independent of pytest/import/reload ordering.

Run from the StockScope repository root with the venv active:

```powershell
python .\apply_sim_ui1_workspace_v11.py
```

The apply script rolls back its own changes on failure and verifies the Simulation regression suite, frontend build, and Scanner production baseline.
