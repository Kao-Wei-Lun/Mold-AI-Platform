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

## Development

Stages 1–5 establish the runnable foundation, the STEP/STL Artifact/Job vertical slice,
deterministic explainable CAD similarity through Qdrant, and an auditable deterministic Design
Review workflow, plus governed extractive Knowledge/RAG retrieval. See
[`docs/development/README.md`](docs/development/README.md) for environment setup, test commands,
service endpoints, and implementation boundaries.
