# UX.1.2 v1.0.2 — Historical sibling-layout hotfix

Fixes the v1.0.1 failure:
`Historical strategy block: no common JSX container found`.

Cause: current `BacktestPanel.tsx` keeps the explanatory intro and the 10-strategy card/list in separate sibling JSX containers. v1.0.1 incorrectly required both markers to share one wrapper.

v1.0.2 changes:
- discovers the 10-strategy list from strategy labels only (first/last visible labels)
- handles the explanatory intro as a separate optional block
- expands safe JSX container parsing tags
- refuses to move an implausibly broad/page-level wrapper
- validates every frontend source transformation in memory before writing any file
- keeps the existing project-.venv / npm / runtime-DB portability checks

No backend, DB, Scanner algorithm, Ranking, Risk, Entry/Stop/Target, or TRACK behavior is changed.
