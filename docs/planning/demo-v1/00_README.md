# Mold AI Platform Demo v1.0 Completion Plan

- 版本：1.0 Planning Baseline
- 日期：2026-08-27
- 狀態：Approved for implementation planning
- 適用範圍：單台 Windows 11 + NVIDIA GPU + Docker Desktop + OpenAI API + 私人 Sites + Secure MCP Tunnel

## 1. 文件目的

本文件包定義 Stage 12 之後，將目前「可操作的功能型 Demo」完成為
`Mold AI Platform Demo v1.0` 所需的剩餘工作。它是實作與驗收計畫，不取代既有 SRS、
Canonical Data Contract 或 Enterprise Roadmap。

Demo v1.0 的產品承諾是：

> 使用公開或合成資料，從 Engineering Web 與 ChatGPT MCP 兩個入口，穩定重現 CAD
> ingestion、Similarity、Design Review、Knowledge、Process/Trial、CAE、HMI→Excel 與
> Assistant 的治理流程；所有結果都能追溯資料、版本、限制與證據。

Demo v1.0 不宣稱公司資料準確率、因果推論、正式 Moldflow 整合、泛用 OCR、企業身分治理或
自動機台控制。

## 2. 現況基線

Stage 1–12 已提供：

- STEP/STL 上傳、非同步解析、版本與 lineage、Three.js preview。
- Deterministic CAD feature、Qdrant candidate search、explainable reranking。
- 13 條 checksum-protected Demo rules、Review findings、Reviewer decisions、audit events。
- TXT/Markdown Knowledge ingestion、prompt-injection quarantine、extractive citation、abstention。
- Synthetic Process/Trial 與 CAE connectors、canonical records、比較與 guardrails。
- 固定 synthetic HMI profile、人工確認、versioned XLSX export。
- Deterministic Embedded Assistant fallback、UI Action allowlist。
- 9 個 MCP tools、ChatGPT Developer Mode 與 Secure MCP Tunnel 實測成功。
- 私人 Sites portal、HTTPS Quick Tunnel、Demo bearer access。
- Backend、Web、Sites 與 running-container smoke tests。

已確認的剩餘缺口：

1. MCP 回傳的 Web deep link 使用 `dynamic-quick-tunnel.invalid`。
2. Assistant Provider adapter 已完成；仍需以核准 Project key/model 做 account-bound live UAT。
3. CAD Demo 尚未有獨立、治理、可重置的 curated corpus 與 golden scenarios。
4. Demo 啟停、狀態、reset、backup、外部 UAT 與 release evidence 尚未整合成單一流程。
5. Web UI 可用但仍偏向逐 Stage 累積的工程畫面；Demo v1.0 完成後需要一致的 UI/UX 改良。

## 3. 文件索引

| 文件 | 階段 | 主要結果 |
|---|---|---|
| [01 — Web UI Deep Links](01_Stage_13_Web_UI_Deep_Links.md) | Stage 13 | ChatGPT 結果可安全跳轉至指定 Web context |
| [02 — OpenAI LLM Provider](02_Stage_14_OpenAI_LLM_Provider.md) | Stage 14 | 真實 LLM adapter、fallback、usage、eval 與安全邊界 |
| [03 — Curated CAD Demo Corpus](03_Stage_15_Curated_CAD_Demo_Corpus.md) | Stage 15 | 可重複 seed、ground truth、Demo scenarios 與 smoke isolation |
| [04 — Operations, UAT and Release](04_Stage_16_Operations_UAT_Release.md) | Stage 16 | 一鍵操作、reset/backup、安全檢查、UAT 與 v1.0 release gate |
| [05 — Web UI Improvement](05_Stage_17_Web_UI_Improvement.md) | Stage 17 | Demo v1.0 後的 UI/UX、design system 與 workflow 改良 |
| [06 — Traceability and Decisions](06_Traceability_Risks_Decisions.md) | 全階段 | 需求追溯、依賴、風險、決策與變更控制 |

## 4. 執行順序與依賴

```text
Stage 12 baseline
       |
       v
Stage 13 Deep Link
       |
       +-------------------+
       |                   |
       v                   v
Stage 14 LLM         Stage 15 CAD Corpus
       |                   |
       +---------+---------+
                 |
                 v
Stage 16 Operations + UAT + Release
                 |
                 v
          Demo v1.0 feature complete
                 |
                 v
Stage 17 Web UI Improvement
```

Stage 14 與 Stage 15 在 Stage 13 contract 固定後可平行開發，但 Stage 16 UAT 必須使用兩者的完成版。
Stage 17 不得在 Stage 13–16 尚未通過時大幅重寫功能流程，避免同時改變產品行為與 UI。

## 5. Demo v1.0 強制範圍

### 5.1 MUST

- Deep link 使用穩定、可到達的 HTTPS entry URL，且不在 URL 放入 token。
- Deep link 可定位 Similarity、Review、Job、Knowledge、Process/Trial context。
- 至少一個 OpenAI Responses API adapter 可由環境設定啟用。
- Provider timeout、error、rate-limit 或停用時自動回到 deterministic safe fallback。
- LLM 不計算或覆寫 CAD score、Rule PASS/FAIL、CAE delta 或 Process evidence。
- Curated CAD corpus 與 automated smoke corpus 使用不同 dataset ID。
- Curated corpus 有 manifest、license/provenance、generator/version、預期 ranking 與 rule outcome。
- 全新環境可用單一命令建置並 seed 所有 Demo data。
- Reset 只清除明確列出的 Demo operation records；不得刪除 repo、runtime secrets 或未驗證路徑。
- Web 與 ChatGPT 完成主展示腳本，保留 UAT evidence。
- 外部 Demo 只經 HTTPS／Secure MCP Tunnel；DB、Redis、Qdrant 不對外發布。
- Release 前所有自動化測試與 running-stack smoke 通過，Git working tree 乾淨。

### 5.2 SHOULD

- LLM Web 回覆支援 streaming；若延後，須有 loading、timeout 與 cancel UX。
- Demo Status 同時顯示 deep-link readiness、LLM provider、curated dataset 與 external path。
- Demo reset 前建立 metadata backup，並在 reset 後執行 readiness 和 seed reconciliation。
- UAT evidence 使用機器可讀 JSON 加人工 Markdown summary。
- Demo 啟動輸出只顯示必要資訊，token 預設不寫入持久化 log。

### 5.3 不列入 v1.0 Gate

- 公司 PDM/PLM/MES/QMS/Moldflow connectors。
- Enterprise SSO、SAML、RBAC/ABAC、多 tenant。
- 公開 Plugin Marketplace、公開 OAuth MCP server。
- Learned 3D embedding、local geometry correspondence、root-cause ML。
- 真正 solver submission、CAE optimization、泛用 HMI OCR。
- MES／PLC／機台 write-back。
- 1M case、HA、autoscaling、Kubernetes、正式 SLA。
- Quotation 與 Maintenance prediction。

## 6. Demo v1.0 Definition of Done

只有全部條件同時成立才可標記 `Demo v1.0 feature complete`：

1. Stage 13–16 的 MUST requirements 全數 Pass；沒有未核准的 Waiver。
2. `scripts/test.ps1`、release preflight 與 running-container smoke 全數成功。
3. 從不同網路完成私人 Sites Web 與 ChatGPT Secure MCP Tunnel UAT。
4. ChatGPT 能發現 9 個 tools，並能從 MCP 結果開啟正確 Web context。
5. OpenAI Provider 正常與故障兩種 UAT 均通過；故障時無 fabricated success。
6. 全新資料 volume 可 seed curated corpus；連續執行兩次結果 idempotent。
7. Reset 後資料筆數、dataset scope、Qdrant index 與檔案 manifest 一致。
8. 所有畫面與回答標示 Public/Synthetic Demo、版本、限制及 evidence。
9. API key、Tunnel key、Demo token 不存在於 Git、前端 bundle、UAT artifact 或一般 log。
10. 已產生版本、commit、測試摘要、已知限制、操作 runbook 與 rollback 說明。

## 7. 開發與 Git 規則

每一 Stage 採以下節奏：

1. 先固定 contract、schema、error code 與 acceptance test。
2. 分小批實作 backend、frontend、scripts、fixtures、documentation。
3. 執行 targeted tests；修正後再執行完整 `scripts/test.ps1`。
4. 需要容器或外部路徑的 Stage 再執行 rebuild、smoke 與人工 UAT。
5. `git diff --check`、secret pattern scan、文件 link check 通過。
6. 每一 Stage 至少一筆獨立 commit；不得把未通過的下一 Stage 混入。

建議 commit 邊界：

```text
feat: add stable demo deep links
feat: add OpenAI assistant provider
feat: seed curated CAD demo corpus
feat: complete demo v1 operations and UAT
feat: redesign engineering web workspace
```

## 8. 文件維護規則

- 需求變更必須先更新本文件包及 [Demo SRS](../../requirements/02_Demo_SRS.md)。
- 實作完成後，對應 planning 文件保留原需求，並將狀態更新為 `Implemented`，不得刪除歷史。
- 官方 OpenAI 能力、模型與 UI 名稱不得永久寫死；實作前再次查證官方文件。
- 實測結果、帳號狀態與外部 URL 不直接寫入需求基線，應存入日期化 release evidence。
- 真實 API key、token、tunnel ID、公司資料與個人敏感資訊不得進入文件或測試 fixture。
