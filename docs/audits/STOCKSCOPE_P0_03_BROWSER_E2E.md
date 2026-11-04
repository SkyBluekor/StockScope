# P0-03 Chromium E2E in an isolated browser (fixture-based)

Starts the real React /scanner page on loopback 127.0.0.1:5279 with a
test-only Vite config that has NO /api proxy. Playwright mocks all API
endpoints, fails unexpected writes, and blocks external requests. The
fixtures reproduce the observed status LOW_LIQUIDITY for KOSPI 145720
without using the user's actual database or their temporary Job IDs.

The E2E verifies button click, plan, Job POST/GET, filter text, Job/capture
labels, no unrelated auto-selection, reload, explicit manual selection,
and the matched-candidate flow.

These are mocked-provider Chromium UI tests, not live Windows PC browser
verification, official KRX market freshness, or production capture proof.

CI installs pinned @playwright/test@1.56.1 without writing a lockfile,
installs Chromium, and runs:

    npx playwright test -c playwright.p003.config.mjs