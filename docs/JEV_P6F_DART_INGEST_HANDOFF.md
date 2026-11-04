# P6-F — OpenDART observed metadata → EventEvidence (2026-10-30)

## Confirmed real baseline

- P6-E: On the user's Windows PC, Dongkook Pharmaceutical (KOSDAQ 086450) returned 2 actual OpenDART listings for 2026-10-01~30, receipts 20261012900154 / 20261012900140, both dated 2026-10-12. EventEvidence at that time had zero records. This is an actual read-only API/UI verification, NOT proof of successful EventEvidence storage.
- P6-F code: backend/app/event_evidence/dart_ingest_p6f.py validates minimal receipt/corp/ticker/receipt date/URL and observation time, then provides the contract to connect SourceRef → EventRevision → listed-company Entity → confirmed direct relevance → existing Quality service. Time quality remains DATE_ONLY for the receipt; first_seen/available/fetched remain observation instants, never an invented publication timestamp.
- Stable receipt identities and content hashes support reprocessing without duplicate rows or resetting first observation. Changed metadata content on an existing receipt fails closed, pending verified revision mapping. Distinct disclosures for the same company are distinct events, not automatically equated or deemed conflicting.
- API GET /api/dart/stocks/{stock_code}/disclosures?market=KOSDAQ stays user-initiated and display-only. A server-side non-persisting row-by-row validation preview returns eligible metadata count and invalid row reasons; market is supplied by Scanner and NOT independently verified by this OpenDART response. UI says EventEvidence validated candidates but REAL DB STORAGE 0.
- Current app/event_evidence/policy.py OpenDART derived_retention=false, raw_retention=false, ai_transform=false, historical_evaluation=false, prediction_input=false. No real-write route or collector is exposed. Isolated test-only persistence is guarded by fixed P6F-ISOLATED-TEST-OPENDART-V1 policy and a p6f-test-*.db file; it does NOT grant user source rights.

## Official source policy checked 2026-10-30

- https://opendart.fss.or.kr/intro/main.do — OpenDART describes broad use and extraction of public disclosures.
- https://opendart.fss.or.kr/intro/terms.do — OpenDART terms sections 5, 7 and 16 reference related law, declared use, copyright.
- https://opendart.fss.or.kr/disclosureinfo/mainMatter/main.do — direct processing for investment decisions/research, with caveats on user responsibility.

These texts do not establish the exact user's API account right to keep a persistent research derivative corpus or transmit content to third-party TypeSafe. Keep production rights blocked pending source/field/purpose/account authorization. No client-supplied approval flag.

## Regression and future scope

- backend/tests/test_jev_dart_ingest_p6f.py: synthetic DART-shaped dual receipts in isolated migrated SQLite; SourceRef/Revision/Entity/Relevance/Quality/as-of, retry first_seen stability, duplicate protection, changed content rejection, unapproved rights and malformed source ID/time. Chromium E2E verifies manual display, normalized count and zero persisted records.
- Freeze backend/app/market/providers/dart.py, scanner baseline manifest, historical SHORT capture a1e9c341-7542-4511-8740-e07f4ee250ff and P5 LOCAL_MATCH. Actual TypeSafe calls 0.
- Implementation complete only after final CI confirmation; actual OpenDART EventEvidence production storage remains NOT DONE. Activation requires verifiable source rights, independent stock market mapping, per-account policy review, capture-time provenance, safe backup/transaction strategy, explicit user decision, and a separate live DB UAT.
- For Windows read-only preview: pull current branch, run development servers, Scanner → AI 검토 → 실제 OpenDART 공시 조회 → 공시 새로 조회. Validate per-source normalized count independently from the text '실제 DB 저장 0건'.
