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
