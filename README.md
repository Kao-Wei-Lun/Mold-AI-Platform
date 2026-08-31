# Mold AI Platform

本 Repository 用於開發可擴充的模具 AI 平台。現階段已建立需求與架構基線，涵蓋單機 Demo 與未來企業正式版本。

## Requirements

請從 [`docs/requirements/00_README.md`](docs/requirements/00_README.md) 開始閱讀。規格套件包含：

- 總體架構與範圍
- Demo / Enterprise SRS
- Canonical Data Model / Data Contract
- CAD Similarity、Design Review、Process/Trial、CAE/Moldflow、Machine UI→Excel、Knowledge/RAG
- Embedded Engineering Assistant、MCP Gateway、LLM Provider abstraction、UI Action Protocol
- 權限、稽核、Lineage、安全、Job/Worker/Queue、部署
- Public→Company Connector 切換、Roadmap、測試與驗收
- 受控資料管理中心：主檔、模具／CAD、規則、Trial、CAE、Knowledge、HMI、匯入、版本與封存
- 帳號與存取管理：Demo 本機帳號、Enterprise SSO、RBAC + ABAC、職責分離、Session 與服務帳號

目前文件為 `0.9 Draft Baseline`；企業資料來源、實際 CAD/Moldflow 版本、相似度 Ground Truth、權限政策與正式效能門檻仍需在需求訪談與資料盤點後核准。

Demo v1.0 剩餘開發與完成後的 Web UI 改良，請從
[`docs/planning/demo-v1/00_README.md`](docs/planning/demo-v1/00_README.md) 開始閱讀。該文件包將
Stage 13–16 定義為 Demo v1.0 completion gates，Stage 17 定義為後續 Engineering Web UI/UX 改良。

## Development

Stages 1–12 establish the runnable foundation, the STEP/STL Artifact/Job vertical slice,
deterministic explainable CAD similarity through Qdrant, and an auditable deterministic Design
Review workflow, governed extractive Knowledge/RAG retrieval, and the context-aware Assistant plus
Streamable HTTP MCP Gateway. Stage 7 adds canonical Process/Trial cases, a replaceable synthetic
Connector, explainable case ranking, and engineer-gated parameter references. Stage 8 adds
canonical structured CAE results and a strict compatibility-gated Run comparison. Stage 9 adds a
bounded Machine UI extraction profile, human review gate, and versioned Excel export with source
lineage. Stage 10 adds controlled external Demo access, fail-closed security/MCP preflight,
authenticated artifact downloads, and a TLS release topology plus Secure MCP Tunnel runbook.
Stage 11 adds a private Sites portal, an outbound HTTPS Quick Tunnel for the complete Web, and a
separate Secure MCP Tunnel startup path for ChatGPT developer-mode testing. Stage 12 grounds
ChatGPT behavior with a canonical capability/status catalog, nine focused MCP tools, governed
Traditional Chinese Demo knowledge, isolated smoke-test data, and explicit Process/Trial input
provenance. See
[`docs/development/README.md`](docs/development/README.md) for environment setup, test commands,
service endpoints, and implementation boundaries.

Stage 13 implements stable, versioned ChatGPT-to-Web deep links through the owner-only Sites
portal. See [`docs/development/stage-13-web-deep-links.md`](docs/development/stage-13-web-deep-links.md).

Stage 14 adds the grounded OpenAI Responses provider with deterministic fallback. Stage 15 adds a
versioned 16-model synthetic CAD corpus, two isolated error controls, reproducible checksums,
idempotent reconciliation, Golden Similarity/Design Review scenarios, smoke dataset isolation and
an explicit curated-query Web flow. See
[`docs/development/stage-15-curated-cad-corpus.md`](docs/development/stage-15-curated-cad-corpus.md).

Stage 16 Phase A adds unified Demo operations, secret-free status/evidence, checksummed database and
artifact backup, an isolated restore drill, Qdrant recovery and a backup-first operations reset.
See
[`docs/development/stage-16-operations-uat-phase-a.md`](docs/development/stage-16-operations-uat-phase-a.md).

Stage 16 Phase B adds explicit core/external/optional readiness, live Celery worker checks, bounded
and audited stale-job recovery, and a sanitized HTTP/concurrency/queue performance baseline that is
included in acceptance evidence. See
[`docs/development/stage-16-operations-uat-phase-b.md`](docs/development/stage-16-operations-uat-phase-b.md).

Stage 16 Phase C adds the backup-first canonical dataset reset, a double-confirmed clean-room
full-volume rebuild, and automated isolated Qdrant/CAD-worker fault-recovery evidence. See
[`docs/development/stage-16-operations-uat-phase-c.md`](docs/development/stage-16-operations-uat-phase-c.md).

The context-driven Mold Planning workspace and its complete Phase 0–6 release contract are
documented in
[`docs/development/stage-31-mold-planning-release.md`](docs/development/stage-31-mold-planning-release.md).

Stage 17 Phase A replaces the single scrolling page with a route-based Engineering Workspace,
Guided Demo home, persistent CAD context, responsive navigation and a governed Mold Rule catalog.
See [`docs/development/stage-17-ui-phase-a.md`](docs/development/stage-17-ui-phase-a.md).

Stage 17 Phase B adds application-wide English/Traditional Chinese switching with a persisted
browser preference and explicit governed-source translation boundary. See
[`docs/development/stage-17-ui-phase-b-i18n.md`](docs/development/stage-17-ui-phase-b-i18n.md).

Stage 17 Phase C constrains engineering inputs and adds a shared accessible field contract,
required/range guidance and actionable empty states. See
[`docs/development/stage-17-ui-phase-c-form-guidance.md`](docs/development/stage-17-ui-phase-c-form-guidance.md).

Stage 17 Phase D adds bounded accessible action notifications, consistent busy indicators and
plain-language operation labels. See
[`docs/development/stage-17-ui-phase-d-feedback.md`](docs/development/stage-17-ui-phase-d-feedback.md).

Stage 17 Phase E applies the precision-manufacturing visual system, route icons, layered working
surfaces and clearer engineering tables. See
[`docs/development/stage-17-ui-phase-e-visual-system.md`](docs/development/stage-17-ui-phase-e-visual-system.md).
