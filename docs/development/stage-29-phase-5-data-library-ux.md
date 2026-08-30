# Stage 29 — Phase 5 Data Library UX Integration

## Outcome

The governed history area is now presented as the user-facing **Data Library** (`工程資料庫`) while preserving all stable `/data/*` routes. The name distinguishes complete engineering records from the smaller governed choice lists in **Engineering Reference Data**.

## Integrated behavior

- Domain navigation and overview cards only expose areas granted to the current account.
- Direct deep links to an unauthorized domain render an explicit permission state; child workspaces are not mounted and no data request is made.
- Import history rows navigate to stable `/data/imports/{batch_id}` URLs.
- Refresh, browser Back, and Forward reload the selected batch from the URL instead of depending on component memory.
- Import detail links to its background Job, filtered Audit view, source ArtifactVersion lineage, and imported domain records.
- Row-level commit results are part of the detail API contract and show created/skipped outcomes with destination links.
- Data Library, CAD versioning, ingestion domains, permissions, states, and evidence actions have English and Traditional Chinese UI text.
- Import result and evidence layouts collapse to one column on mobile and retain keyboard-operable table rows and native controls.

## Verification

- API adapter and HMI regression: 28 tests passed.
- Web: 32 test files, 105 tests passed.
- Vue typecheck and production Vite build passed.
- Deep-link selection, path prop refresh, and Job evidence navigation are covered by component tests.

External Sites and MCP validation remains the Phase 6 release gate so the published Demo is checked only after security and recovery work is complete.
