# TRACK.1.10.4 v1.0.1 precheck hotfix

The first TRACK.1.10.4 apply script incorrectly required the literal text `TRACK.1.10.3`
inside `RecommendationTracking.tsx`. TRACK.1.10.3 never wrote that literal marker, so the
apply stopped before changing any project files.

v1.0.1 changes only the baseline precheck. It now verifies real TRACK.1.10.3 feature markers:
`previewManualTrackedItem`, `EmbeddedScanner`, `원하는 종목 직접 찾기`, `최신 반영`, and `추적 종료`.

The TRACK.1.10.4 payload and implementation are otherwise unchanged.
