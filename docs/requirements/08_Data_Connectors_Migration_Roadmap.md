# 08 — 資料來源、Public→Company Connector 切換與 Roadmap

## 1. 目標

Demo 不做一次性資料管線。Public、Synthetic 與 Company source 均實作相同 Connector interface，輸出 Canonical entities/artifacts/events；Capability、UI、MCP tools、Job 與評估框架不因來源切換而重寫。

## 2. Connector Contract

```text
SourceConnector
├─ discover(scope, cursor)
├─ extract(source_ref)
├─ fetch_artifact(source_ref)
├─ map_to_canonical(raw, mapping_version)
├─ validate(canonical)
├─ emit_change(event)
├─ checkpoint()
├─ reconcile(window)
└─ health()
```

- **CON-001**：Connector 必須保存 source system/id/version、extract time、raw hash、mapping version、quality issues。
- **CON-002**：支援 initial load、incremental sync、delete/tombstone、retry、checkpoint 與 reconciliation。
- **CON-003**：相同 source version 重跑必須 idempotent；不同版本產生新 ArtifactVersion/entity revision。
- **CON-004**：ACL、classification、customer/project scope 與資料一起 mapping，不得在之後人工補上才允許索引。
- **CON-005**：Raw landing zone 與 normalized zone 分離；mapping error 進 quarantine，不污染 production index。
- **CON-006**：Connector credential 僅能讀必要來源；write-back 使用獨立 Connector/permission。

## 3. Demo Connector

### 3.1 Public CAD

輸入：公開 CAD 檔及 metadata manifest。輸出：Project/Product/Part/MoldCase/CADModel/ArtifactVersion。需保存 dataset name、source URL、license、download date、原始 split 與轉換。

ABC 等公開 shape dataset 與公司模具資料可能語意不同，因此 Demo UI 必須標示資料性質；評估只代表 Demo dataset，不外推公司準確率。

### 3.2 Synthetic Mold Fixtures

以受控參數生成壁厚、Rib、Hole、Boss 等幾何，並保存 generator/version/parameters。此來源主要驗證 Geometry/Rule 的 measurement truth，不用來證明真實案例搜尋品質。

### 3.3 Public Process/CAE/Knowledge/HMI

- Process：保存原始欄位、資料字典、缺值、split、license；mapping 成 canonical parameter/defect/action。
- CAE：公開 tutorial/export 或自製 fixture，清楚標記非公司 solver integration。
- Knowledge：公開規範與 Demo SOP，記權威等級與有效性。
- HMI：合成影像連同 ground-truth fields/regions/profile。

## 4. Company Connector 類型

### 4.1 PDM/PLM/CAD Vault

取得 project/part/mold/revision、CAD/drawing、lifecycle、owner、ACL。需處理 native CAD reference、assembly、external reference、check-in/check-out 與 revision semantics。

### 4.2 File Server

檔名與 folder 不作唯一 truth；使用 manifest、hash、metadata extraction 與 owner mapping。偵測 duplicate、latest-only folder、無 revision、access inheritance 等問題。

### 4.3 MES/Trial/QMS

將 machine/tag、recipe/parameter、lot、timestamp、defect、inspection、corrective action、outcome 對齊 Mold/Part revision。首要風險為時間對齊、單位、機台欄位別名與缺少 outcome。

### 4.4 CAE/Moldflow

先做版本與授權盤點；確認可用 API、Result export、資料字典、批次存取、automation 授權。若只可讀 PDF，建立 fallback Connector 並標示 quality limitation。

### 4.5 ERP/Quotation/Maintenance

Quotation 需區分 estimate/approved quote/order/actual cost、currency/date；Maintenance 需 mold/component、shot count、repair reason、replacement、downtime、failure outcome。

### 4.6 Identity and authorization

取得 user/group/project/customer scope；避免以姓名/email fuzzy mapping。ACL mapping 未完成的資料預設 quarantine 或只限 Data Steward。

## 5. Public→Company 切換流程

### Phase A — Source inventory

建立 source catalog：owner、system、format、volume、update frequency、ACL、classification、quality、retention、API/license、sample。

### Phase B — Mapping workshop

由 Domain Expert + Data Steward 對照 Canonical field，產出：mapping rule、code/unit dictionary、null semantics、master data、quality threshold、unmapped backlog。

### Phase C — Read-only landing

只讀抽取小範圍資料到隔離 landing；計算 hash/manifest，不建立全域 index。執行 malware、schema、ACL、classification 檢查。

### Phase D — Canonical shadow

將 company data 轉成同一 contract；與 source record 對帳。UI 以 feature flag/tenant scope 只給試點使用者。

### Phase E — Re-index and recalibration

使用公司資料重做 CAD feature/index、similarity profile、rules、RAG chunking、OCR profile、ML calibration；Public model 不直接宣告可用。

### Phase F — Parallel pilot

現行流程與平台並行，收集 relevance、review error、trial outcome、time saved、ACL denial。AI 不自動回寫。

### Phase G — Production cutover

完成 owner、SLO、backup/DR、security、support、training、change management、retention；按 Capability 而非一次性全平台切換。

## 6. Reconciliation

每次同步產生：

- Source discovered/extracted/mapped/valid/quarantined counts。
- Missing/duplicate/version conflict、hash mismatch、ACL mismatch。
- Source→Canonical→Index coverage。
- Last success/checkpoint、lag、delete/tombstone status。

Reconciliation 差異超過門檻時停止 promote/index publish，通知 Data Steward。

## 7. 資料成熟度 Gate

| Capability | 最低資料成熟度 | 不足時替代 |
|---|---|---|
| CAD Similarity | Revision、可解析 CAD、工程相似 label | 僅 metadata/shape demo |
| Design Review | 核准規則、量測定義、fixtures | 少量 deterministic rules |
| Process/Trial | Parameter + defect + action + outcome 對齊 | Case browser / rule hints |
| CAE | 原始 result/context/solver version | Report parsing demo |
| Quotation | Reference case + approved/actual cost | 規則區間，不稱 ML 預測 |
| Maintenance | Shot count + repair/failure history | 履歷與 due-rule |

## 8. Roadmap

時間為相對階段，實際週期在資料盤點後估算。

### R0 — Foundation and decision closure

- 建 repo、CI、container skeleton、canonical schema、Capability/Job contract。
- 確認 Similarity 定義、Demo datasets、10–30 Rule、HMI 目標、OpenAI/ChatGPT account preflight。
- 建 security baseline、source/license register、evaluation plan。

出口：Architecture/Data/Security review 通過；Demo backlog 可開發。

### R1 — Demo vertical slice

- STEP/STL ingestion、viewer、geometry features、Qdrant index。
- Similarity Top K + explanation、Design Review、Knowledge。
- Dedicated UI + Embedded Assistant + MCP tools + Job progress。
- Single Windows Docker deployment、external HTTPS demo access。

出口：02 的主展示腳本與驗收通過。

### R2 — Demo breadth and hardening

- Process/Trial case、CAE fixture comparison、Machine UI→Excel。
- Security/adversarial tests、provider fallback、backup/reset、100K vector scale test。
- Feedback/evaluation dashboard、UI Action Protocol。

出口：穩定外部展示、完整 test report、企業 gap list。

### R3 — Company data discovery and shadow pilot

- PDM/File + 選定 MES/QMS/CAE Connector。
- SSO/ACL mapping、read-only company scope、reconciliation。
- Golden Dataset、Similarity Profile/Rules/RAG recalibration。

出口：無 ACL leakage；Company shadow 指標經 Domain Owner 簽核。

### R4 — Enterprise pilot

- 多使用者、HA 非必要但 production-like；分離 worker/storage。
- Review/waiver workflow、model/rule registry、SIEM/APM、backup/restore。
- 一個 Site/產品線、限定 Capability 正式使用。

出口：Pilot business KPI、安全與營運 Readiness 通過。

### R5 — Production and scale

- HA/SLO/DR、autoscaling、1M case index、增量同步。
- CAE 原始結果、Process recommendation governance。
- Quotation/Maintenance 依資料成熟度啟動。

出口：正式 SLA、Runbook、Owner、Change/Incident process。

### R6 — Advanced optimization

- Local geometry search、cross-modal defect-to-geometry retrieval。
- CAE optimization loop、learning-to-rank、active learning。
- 受控 external write 僅在獨立安全與變更核准後考慮。

## 9. Roadmap 優先級

優先順序固定為：資料與權限 → CAD ingestion/Similarity → Design Review → Knowledge → Process/Trial → CAE/Machine UI → Quotation/Maintenance。不得為了展示生成式對話而跳過 Canonical、Evidence、Evaluation 與 Security。

## 10. 決策 Gate

每階段評審至少回答：

- 資料是否有使用權、ACL、版本與 Ground Truth？
- 結果是否能被工程師重現與查證？
- False positive/negative 的業務成本為何？
- 是否把 Demo 能力錯誤宣稱為正式能力？
- Connector/Model/Rule 改變是否能 rollback？
- 目前最安全的 abstain/fallback 是什麼？
