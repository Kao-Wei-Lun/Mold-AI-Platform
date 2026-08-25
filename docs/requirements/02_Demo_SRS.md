# 02 — Demo Software Requirements Specification

## 1. Demo 目的

Demo 用於證明平台骨架與跨入口流程可行，不用公開資料宣稱已達公司正式準確率。展示重點為：

1. 上傳 3D CAD 並搜尋相似案例，顯示可解釋分數與 3D 比較。
2. 以 10–30 條可量化規則執行 Design Review，定位違規、列出量測與依據。
3. 以公開／合成 Process/Trial 資料查找相似異常案例並產生受控建議。
4. 展示 Knowledge/RAG、CAE 範例與 Machine UI→Excel 的次要流程。
5. 同一 Capability 可從專用 Web UI 及 ChatGPT Web 的 MCP/Plugin 入口操作。

## 2. 環境與限制

- 一台 Windows 11 開發／展示機、NVIDIA GPU、32–64 GB RAM 建議、1–2 TB NVMe 建議。
- Docker Desktop + WSL2；容器化 API、UI、Worker、PostgreSQL、Qdrant、Redis。
- LLM API 為 Demo Assistant 預設；核心 CAD/Rule/Search 在 LLM 不可用時仍可操作。
- 公開／合成資料：CAD 開發集 1K–10K，效能集可擴至 100K metadata/vector；不要求 Demo 首版處理 1M 原始 CAD。
- 外部連線僅限 HTTPS；Demo 可使用受保護 tunnel。禁止公開 DB、Queue、Vector Store。

## 3. Demo 角色

- **Demo Engineer**：上傳、搜尋、審查、查詢與匯出。
- **Reviewer**：檢視證據、接受／退回 Design Review 結果。
- **Demo Admin**：管理資料集、Rule Profile、使用者、Provider 與展示模式。
- **ChatGPT User**：透過已安裝／連接的 Plugin/MCP 呼叫 read-only 及受控 create-job tools。

單人可同時擁有多角色，但權限檢查不可省略。

## 4. 功能需求

### 4.1 身分、首頁與資料集

- **D-AUTH-001**：系統應提供本機 Demo 帳號或 OIDC 測試登入，不得以匿名管理員對外展示。
- **D-AUTH-002**：所有 API、MCP tool 及 artifact download 應驗證 token 與 dataset scope。
- **D-DATA-001**：Admin 應可啟用／停用公開資料集，顯示來源、授權、匯入版本與資料量。
- **D-DATA-002**：所有 Demo 畫面應標示「Public/Synthetic Demo Data」，避免被誤認為公司資料。

### 4.2 CAD ingestion 與 viewer

- **D-CAD-001**：應支援 STEP 與 STL；DXF、PDF/image 2D 支援可依 Sprint 選配。
- **D-CAD-002**：上傳後應執行 malware/type/size 檢查、hash、artifact version 建立與非同步解析。
- **D-CAD-003**：解析結果至少包含 bounding box、volume、surface area、face/edge count、基本 surface type 統計及 mesh preview。
- **D-CAD-004**：Viewer 應支援 rotate、zoom、fit、standard views、透明度與選取 Face；若模型無法解析，應提供可操作錯誤與保留原檔。

### 4.3 Similarity Search

- **D-SIM-001**：使用者可從既有 CAD 或新上傳 CAD 建立 search job。
- **D-SIM-002**：Candidate search 應結合 geometry/topology/visual/metadata 中至少三類訊號；分數權重由 versioned Similarity Profile 管理。
- **D-SIM-003**：結果應顯示 Overall、各分項分數、主要相似點、主要差異與來源 dataset。
- **D-SIM-004**：應支援 metadata filter，例如 product type、material、size range、dataset。
- **D-SIM-005**：Top result 可開啟 side-by-side 3D、基本 overlay 或對應量測比較。
- **D-SIM-006**：工程師可標記 Relevant/Not relevant 並輸入原因，形成評估資料但不得自動改模型。
- **D-SIM-007**：搜尋結果需記錄 profile/model/index version 與 query artifact lineage。

### 4.4 Design Review

- **D-REV-001**：Admin 可匯入或建立 10–30 條 Demo Rule，包含 ID、version、適用條件、公式、severity、reference 與 owner。
- **D-REV-002**：Review job 應產生 PASS/FAIL/NOT_EVALUATED，不得將無法量測視為 PASS。
- **D-REV-003**：每個 violation 應包含 actual、limit、unit、location reference、risk、evidence geometry 與 rule version。
- **D-REV-004**：LLM 可解釋風險與改善方向，但 PASS/FAIL 必須來自 Geometry + Rule Engine。
- **D-REV-005**：Reviewer 可 Accept、Reject、Waive；Waive 必須填原因並產生 audit event。

### 4.5 Process / Trial

- **D-TRI-001**：使用者可輸入 material、defect、location、mold temperature、pressure、speed、holding、cooling time 等可用欄位。
- **D-TRI-002**：系統應檢索相似歷史／合成 Case，列出來源、相似因素、corrective action 與 outcome。
- **D-TRI-003**：建議值須由 rule、案例或模型輸出產生，並標示來源與信心；LLM 不得憑空生成未受限參數。
- **D-TRI-004**：Demo 不得提供直接下發機台動作；所有建議標記為需工程師確認。

### 4.6 CAE / Moldflow

- **D-CAE-001**：應支援至少一種 Demo 結構化結果或公開 tutorial export；PDF/影像解析屬 fallback。
- **D-CAE-002**：至少映射 fill time、pressure、temperature、weld line、air trap、warpage 中可取得的欄位。
- **D-CAE-003**：應能比較兩次 study 的相同指標並標示不可比條件。
- **D-CAE-004**：摘要必須引用 study/result/metric ID，不可只輸出無來源自然語言。

### 4.7 Machine UI→Excel

- **D-XLS-001**：使用者可上傳 JPG/PNG；系統執行旋轉／透視校正、OCR、欄位辨識與單位正規化。
- **D-XLS-002**：首版以「資料正確」為目標，輸出 Parameter、Value、Unit、Confidence、Source Region；不承諾 1:1 畫面重建。
- **D-XLS-003**：低信心欄位應在預覽表中要求人工確認後才匯出。
- **D-XLS-004**：輸出 `.xlsx` 並附原圖 hash、擷取時間與欄位信心。

### 4.8 Knowledge / RAG

- **D-KNW-001**：可匯入 Demo SOP、Design Guideline、Trial Report 與 Case note，保存來源、版本與頁／段落定位。
- **D-KNW-002**：回答應提供可點擊 citation；找不到證據時明確回答不足，不得補造內容。
- **D-KNW-003**：複合查詢可同時使用 Knowledge、Mold Case、Trial 與 CAE retrieval，再以共同 Case ID 合併。

### 4.9 Embedded Assistant

- **D-AST-001**：Assistant 應取得 page、selected object、job、rule/result 等最小 Context reference。
- **D-AST-002**：使用者問「為什麼這個排第一」時，系統應呼叫 similarity explanation，而非要求使用者重述 query/selection。
- **D-AST-003**：Assistant 回覆應區分 fact、computed result、recommendation 與 uncertainty。
- **D-AST-004**：Provider 故障時 UI 應顯示降級狀態，非 LLM 功能仍可用。

### 4.10 MCP / ChatGPT demo

- **D-MCP-001**：應提供至少 `search_similar_molds`、`get_similarity_explanation`、`run_design_review`、`get_job_status`、`search_knowledge` 五個 MCP tools。
- **D-MCP-002**：MCP 結果應使用與 REST API 相同的 domain schema，另加精簡 model-readable text 與 Engineering UI deep link。
- **D-MCP-003**：Create-job tools 必須回傳 job_id，不應讓 MCP request 等待重型工作完成。
- **D-MCP-004**：Demo 前應完成 Developer Mode／Plugin 可用性、Workspace Policy、endpoint、auth 與 tool discovery 預檢。
- **D-MCP-005**：若官方 ChatGPT 能力或帳號限制不允許現場連線，應提供預錄證據與 MCP Inspector 備援，但不得宣稱為現場成功。

## 5. 非功能需求

- **D-PERF-001**：10K 已索引資料、單使用者 warm query 的候選搜尋 p95 目標 ≤ 3 秒；完整細部比較可非同步於 30 秒內完成。門檻須以實測硬體報告確認。
- **D-PERF-002**：一般 metadata/knowledge API p95 目標 ≤ 2 秒，不含外部 LLM latency。
- **D-PERF-003**：至少支援 3 個並行互動使用者與 5 個排隊長任務，不發生資料串流或權限混淆。
- **D-REL-001**：Worker restart 後 queued/running job 可被安全重試或標記失敗；不得無限卡住。
- **D-OBS-001**：每個 request/job/tool call 具 correlation_id、duration、result status、provider/model/rule/index version。
- **D-SEC-001**：Secret 不寫入 repo、log 或前端；外部 endpoint 全程 TLS；上傳檔隔離處理。
- **D-PORT-001**：核心容器可在 Linux host 重建，程式不得依賴 Windows-only path 或 COM，除非隔離在明確 Adapter。

## 6. Demo 資料與 Seed

- CAD：ABC 等合法公開資料之授權允許子集；另製作可驗證尺寸／Rib/Wall 的 synthetic CAD fixtures。
- Process：公開 Injection Molding dataset 或合成案例，保留來源與生成規則。
- CAE：公開 tutorial/export 或自製結構化結果，不假冒正式 Moldflow API 整合。
- HMI：自製多角度、反光、模糊、不同語言／單位的合成影像。
- Knowledge：公開文件、Demo SOP 與人工撰寫 Case，逐項標示 license/provenance。

## 7. 建議展示腳本

1. 登入並選擇 Demo Dataset。
2. 上傳 `NEW-001.step`；觀看 Job progress 與 3D preview。
3. 執行 Similarity，開啟第一名，查看分項分數與差異。
4. 在 Assistant 問「為什麼它排第一？」；驗證 Context-aware explanation。
5. 執行 Design Review；選取 violation Face、顯示 actual vs limit 與 rule version。
6. 切換 ChatGPT Web，透過 MCP 問相同案例並取得 Web deep link。
7. 上傳 HMI 圖，人工確認低信心欄位後輸出 Excel。
8. 模擬 LLM provider unavailable，證明 CAD Search/Review 仍可運作。

## 8. Demo Definition of Done

- 01–07 主腳本可在全新重建環境重複完成。
- 無 P0/P1 安全缺陷；無跨使用者 artifact 讀取。
- 需求 D-* 皆有測試案例與結果；未完成者清楚列為 Gap。
- 所有 AI 結果標示資料集、版本、信心／限制與證據。
- 具備一鍵或文件化啟停、備份 seed data、provider key 設定與 Demo reset 流程。
