# 01 — 總體架構與系統範圍

## 1. 目標與產品定位

Mold AI Platform 是一個可擴充的模具工程工作平台，統一管理 2D/3D CAD、CAE、試模、製程、缺陷、報價、維修及知識文件，並透過可插拔 AI Capability 提供搜尋、審查、分析、預測、最佳化與自然語言操作。

平台不是單一 Chatbot，也不是單一模型。它將工程判定與生成式 AI 分離：

- Geometry Engine 負責幾何與拓撲量測。
- Rule Engine 負責可重現的設計規範判定。
- Search/Ranking Engine 負責相似案例檢索與重排。
- ML/Optimization Engine 負責風險預測、參數建議與校準。
- LLM/Assistant 負責意圖理解、工具協調、摘要、解釋與互動。

## 2. 系統邊界

### 2.1 In scope

- CAD/圖面匯入、標準化、預覽、特徵萃取、索引與版本管理。
- 相似模具整體／局部搜尋及可解釋比較。
- 版本化 Design Rule Profile 與規則審查。
- Process/Trial Case 檢索、風險分析與受控建議。
- CAE/Moldflow 結果匯入、結構化、規則／ML 分析與摘要。
- Machine HMI 影像之 OCR、欄位辨識、單位正規化與 Excel 匯出。
- 文件與結構化資料的 Knowledge/RAG。
- Embedded Engineering Assistant、MCP Gateway、LLM Gateway、UI Action Protocol。
- 權限、稽核、Lineage、Job/Worker/Queue、部署與可觀測性。

### 2.2 Out of scope for Demo

- 直接控制實體射出機、CNC、機械手臂或修改生產參數。
- 將 AI 建議自動下發到 MES／機台而不經人工核准。
- 原生 NX/CATIA/Creo/SolidWorks 全格式保證；Demo 優先 STEP/STL，2D 以 PDF/影像及選定 DXF 為主。
- 大型 LLM 訓練、百萬 CAD 全量建索引與 50+ 同時使用者的正式 SLA。
- 將 LLM 回覆視為工程簽核、法規符合性或安全保證。

## 3. 雙入口、單一能力核心

```text
                    ┌─────────────────────────┐
                    │ Dedicated Engineering UI│
                    │ 3D / Compare / Review   │
                    └────────────┬────────────┘
                                 │ REST/WebSocket
┌─────────────────────┐          │
│ ChatGPT Web / Client│──MCP──┐  │
│ Optional Plugin UI  │       │  │
└─────────────────────┘       ▼  ▼
                         API / MCP Gateway
                               │
                         Capability Registry
                               │
     ┌──────────────┬──────────┼──────────┬─────────────┐
     ▼              ▼          ▼          ▼             ▼
 CAD/Similarity  Rule Review  CAE      Process/Trial  Knowledge/Vision
     └──────────────┴──────────┼──────────┴─────────────┘
                               ▼
                    Job / Queue / Worker Pools
                               │
       ┌───────────────┬───────┼───────────┬─────────────┐
       ▼               ▼       ▼           ▼             ▼
   PostgreSQL      Object    Vector      Cache/Queue   Audit/Telemetry
                   Storage    Store
```

專用 UI 提供 3D rotate/zoom、Face highlight、Overlay、Section、CAE contour、批次工作、Review/Approve 與歷史比較。MCP 入口提供查詢、啟動工作、取得狀態、解釋結果及開啟對應 Web UI deep link；MCP-only 不承擔完整工程工作台。

## 4. 邏輯元件

### 4.1 Experience Layer

- **Engineering Web UI**：Vue 3 + TypeScript + Three.js 為建議基線；實作頁面 Context Store 與 Action Handler。
- **Embedded Assistant Panel**：讀取已授權 UI Context，支援 Chat、Suggested Actions、Explain、Analyze、Execute。
- **ChatGPT Adapter**：以 Plugin/MCP 工具呈現相同 Capability；可選小型 UI resource，不依賴其承載完整 3D 工作台。

### 4.2 Gateway and orchestration

- API Gateway：認證、授權、輸入大小限制、Rate limit、Correlation ID、API 版本。
- MCP Gateway：Tool discovery、Schema 映射、OAuth／Token 驗證、Approval policy、結果裁切與 Deep link。
- Assistant Orchestrator：Intent → Plan → Tool selection → Approval → Execute → Evidence-backed answer。
- Capability Registry：記錄 capability_id、version、input/output schema、permission、resource class、timeout、validation、metrics 與 lifecycle。

### 4.3 Engineering engines

- CAD Ingestion/Geometry/Topology/Meshing/Rendering。
- Vector retrieval、metadata filter、candidate generation、re-ranking、detailed comparison。
- Rule evaluation、measurement evidence、exception workflow。
- CAE parser、field mapper、engineering checks、result comparison。
- OCR/layout/field recognition、unit normalization、Excel renderer。
- Text/structured retrieval、citation builder、case fusion。
- ML inference、optimization、calibration、model registry。

### 4.4 Data platform

- PostgreSQL：主檔、關聯、版本、工作、權限、稽核索引及狀態。
- Object Storage：原始檔、轉檔、Mesh、Thumbnail、CAE、Excel、報告；Demo 可用 local volume，預留 MinIO/S3 adapter。
- Vector Store：CAD/Image/Text/Case embedding；Demo 預設 Qdrant，Contract 不綁供應商。
- Redis：Queue broker、短期 cache、distributed lock；Demo 可搭配 Celery。
- 可選 Search Engine／Knowledge Graph：Enterprise 依資料量與查詢需求導入。

## 5. 關鍵資料與控制流程

### 5.1 長任務

1. Client 提交檔案與 Capability request。
2. API 驗證權限、格式、惡意檔案、Idempotency key。
3. 建立 immutable input snapshot 與 Job。
4. Queue 依 `resource_class` 分流至 CAD/CPU/GPU/CAE/Excel worker。
5. Worker 產生 artifact、metrics、logs、model/rule version 與 lineage。
6. Job 狀態透過 polling 或 WebSocket/SSE 更新。
7. Client 顯示結果；所有 write/approve action 再經授權與稽核。

### 5.2 Assistant tool call

1. UI 送出使用者訊息與最小必要 Context reference，不直接塞入所有 CAD/文件內容。
2. Assistant 取得使用者權限與可用 Capability。
3. LLM 只提出 tool plan；後端驗證 schema、權限與 policy。
4. Read-only 工具可直接執行；會改變資料、發佈、覆寫或刪除者要求明確確認。
5. 回覆須列出 evidence references、資料時間、rule/model version 及不確定性。

## 6. Demo 實體拓撲

單台 Windows 11 + NVIDIA GPU：

```text
Windows Host
├─ Browser / ChatGPT Web
├─ Docker Desktop + WSL2 backend
│  ├─ reverse-proxy
│  ├─ web-ui
│  ├─ api / assistant / mcp
│  ├─ worker-cad / worker-ai
│  ├─ postgres
│  ├─ qdrant
│  ├─ redis
│  └─ optional minio
├─ Local NVMe demo-data volume
├─ NVIDIA container runtime
└─ Outbound: LLM API
```

外部使用有兩條路：

- 專用 Web UI：經受保護的 HTTPS reverse tunnel／gateway，必須有登入、TLS、Rate limit 與停用開關。
- ChatGPT Web：以 Plugin/MCP 連接公開 HTTPS `/mcp` 或官方允許的 Secure MCP Tunnel；Demo 前驗證帳號與 Workspace Policy。

不得直接將資料庫、Redis、Qdrant、Docker daemon 或 Windows 遠端桌面暴露到 Internet。

## 7. Enterprise 目標拓撲

- Stateless Web/API/MCP replicas behind load balancer。
- 分離 CPU、CAD、GPU、CAE、Excel worker pools，支援獨立擴充與資源 quota。
- HA PostgreSQL、企業 Object Storage、備份／還原與跨區策略。
- SSO/OIDC、SCIM/group mapping、KMS/Secrets Manager、SIEM、APM。
- Private network connectors 連接 PDM/PLM/MES/QMS/File/CAE；預設 deny egress。
- 可依資料分級路由至 Local、Company Internal 或核准的 Cloud LLM。

## 8. 架構原則與決策紀錄

| ADR | 決策 | 理由 |
|---|---|---|
| ADR-001 | Capability-first，而非功能各自成系統 | 共用資料、權限、Job、版本與評估 |
| ADR-002 | Dedicated UI + MCP 雙入口 | 工程互動與自然語言入口各自適配 |
| ADR-003 | LLM Provider abstraction | 避免 UI/Domain logic 綁特定模型 |
| ADR-004 | 非同步長任務 | 支援取消、重試、排隊、擴充與追蹤 |
| ADR-005 | Canonical Model + Connector mapping | Demo Data 可替換，核心 Contract 不變 |
| ADR-006 | Rule/Geometry 決定性優先 | 可重現、可稽核，LLM 不當裁判 |
| ADR-007 | Security filter before retrieval | 防止跨客戶向量與關鍵字資料洩漏 |

## 9. 主要風險

- 公開 CAD 與公司 Mold Case 的語意差異造成 Demo 指標無法直接外推。
- Native CAD、Moldflow API 與授權限制導致 Connector 成本高於預期。
- 相似度 Ground Truth 不清，使模型指標看似良好但工程上無用。
- HMI 拍攝條件、語言、單位與廠牌差異造成 OCR domain shift。
- LLM prompt injection 或 Context over-sharing 導致資料外洩／錯誤工具呼叫。
- 單機資源競爭造成展示不穩；須在 Demo 前建立資料量與並行上限。

## 10. 架構驗收摘要

- 同一 Capability 可由 Web UI 與 MCP 呼叫，結果 schema 與 Job ID 一致。
- 更換 Public Connector 為 Mock Company Connector 不需修改 Domain UI 與 Capability contract。
- 任一結果可追溯到 input artifact、parser、feature/model、rule profile 與執行時間。
- 未授權資料在候選產生前即被排除；LLM 不得接收未授權內容。
- 長任務可查詢、取消、重試且不重複產生不一致的業務結果。
