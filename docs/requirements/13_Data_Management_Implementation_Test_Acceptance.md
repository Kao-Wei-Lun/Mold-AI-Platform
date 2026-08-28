# 13 — Data Management and IAM Implementation, Test and Acceptance Plan

版本：0.1 Draft  
日期：2026-08-28  
適用範圍：Mold AI Platform 資料管理中心與帳號／存取管理

## 1. 文件目的

本文件將
[資料管理中心 SRS](11_Data_Management_SRS.md) 與
[帳號／存取管理 SRS](12_Identity_Access_Account_Management_SRS.md)
轉為可分階段開發、獨立測試、Git 提交與驗收的工作計畫。

它不代表所有 Enterprise 功能都應立即在單機 Demo 完成；每一階段明確區分：

- **Demo Deliverable**：可在目前 Windows + Docker 環境完成並展示。
- **Enterprise Contract**：Demo 現在就必須保留的資料契約與擴充邊界。
- **Deferred Enterprise Integration**：待公司 IdP、PDM/PLM、MES/QMS 與正式政策確認後實作。

## 2. 實作原則與前置決策

### 2.1 必須遵守的原則

1. 先建立身分與授權基礎，再開放資料修改與核准。
2. UI、MCP、Connector 與 Worker 只呼叫 Domain API，不直接操作 DB。
3. 已生效工程內容以新版本修改，不做 in-place overwrite。
4. 一般刪除以 Deactivate／Archive 為主；Hard Delete 是獨立高風險流程。
5. 每一階段測試通過後建立獨立 Git commit，不混入無關變更。
6. Migration、seed、API schema 與 UI 需可重複部署，不依賴人工直接改 DB。
7. Public/Synthetic Demo 與 Company Connector 共用 Canonical Entity 與 Validation。
8. 權限過濾發生在搜尋候選產生之前，而非取得結果後才遮蔽。
9. 新功能預設 fail closed；缺少 Policy、Scope 或 Actor 時不執行受控寫入。

### 2.2 開發前須核准的最小決策

- Demo 首批角色及每個角色的允許動作。
- 首批主檔：Dataset、Product Type、Material、Machine、Defect、Location、Unit。
- Project → Product/Part → Mold → MoldRevision 的最小欄位與唯一碼。
- Rule 審查是否要求 Reviewer 與 Approver 兩層，或 Demo 合併成單一核准層。
- Demo 保存、封存與重設政策。
- Enterprise IdP 類型先保留 OIDC contract；實際 issuer/claim mapping 延後配置。

## 3. 目標架構增量

```text
Vue Engineering Web
  ├─ /data/* 管理中心
  └─ /admin/identity/* 帳號與權限
             │
      AuthN / Session / CSRF
             │
    Permission + Scope Policy
             │
      Versioned Domain APIs
             │
 Postgres + Object Store + Outbox
             │
 Celery/Redis Workers + Qdrant
             │
 Audit / Lineage / Import Report
```

現有 Web 工程頁繼續使用 Capability API；受控下拉選項改讀 Master Data API。新增管理中心不應
複製 CAD、Rule、Trial、CAE、Knowledge 或 HMI 的核心商業邏輯。

## 4. 分階段開發計畫

### Phase 0 — Baseline、決策與 Schema Guardrail

#### Demo Deliverable

- 建立本文件、需求 ID、資料字典與初始權限矩陣。
- 盤點現有 Model/API/fixture/hard-coded option 與資料所有權。
- 定義 migration 命名、API version、error envelope、pagination、ETag 與 domain event 慣例。
- 建立 feature flags：`DATA_ADMIN_ENABLED`、`LOCAL_ACCOUNTS_ENABLED`、`ENTERPRISE_SSO_ENABLED`。
- 建立安全預設：未完成 IAM 時，管理路由不對外開放。

#### 測試與 Gate

- 文件連結、需求 ID、schema 範例與名稱一致性檢查。
- 現有完整測試須保持通過。
- `git diff --check` 無空白或 patch 錯誤。

#### Git Gate

`docs: specify governed data and account management`

### Phase 1 — Identity Foundation 與管理外殼

#### Demo Deliverable

- 每人本機帳號、登入、登出、變更／重設密碼、Session、CSRF。
- 一次性首位管理者 bootstrap，完成後關閉。
- User、Role、Permission、RoleAssignment、DataScope、Session、Audit model/migration。
- 固定角色 seed：Viewer、Data Editor、Data Steward、Mold Engineer、Rule Owner、Reviewer、Approver、Platform Admin、Auditor。
- `/api/v1/auth/me` 與 permission summary。
- `/admin/identity/users`、帳號詳細、角色指派、停用與 Session 撤銷基本 UI。
- 共通 route guard 只改善 UX；所有 API 另做 server-side check。
- Background Job 保存 `requested_by` 與 `executed_by`。

#### Enterprise Contract

- `ExternalIdentity(issuer, subject)`、Group Mapping 及 federated account type。
- Auth Provider interface，不讓 Domain model 依賴 Django username 或特定 IdP claim。
- OIDC/SAML/SCIM 僅建立 adapter contract，不在沒有公司設定時宣稱完成。

#### 測試與 Gate

- 密碼雜湊、登入／登出、Cookie、CSRF、rate limit、Session expiry。
- 每種角色至少一個 allow 與 deny API 測試。
- 改 URL、直接 API、deep link 仍不可繞過權限。
- 帳號停用後 Session 撤銷；歷史 Audit Actor 仍存在。
- Log 與 response 不包含密碼、Token 或 Secret。
- 無預設帳密、無 bootstrap 重入。

#### Git Gate

測試全通過後提交：`feat: add local identity and access foundation`

### Phase 2 — Master Data 管理與動態工程選項

#### Demo Deliverable

- Dataset、Product Type、Material、Machine、Defect、Location、Unit 的 canonical model/API/UI。
- 清單搜尋、排序、分頁；建立、修改、停用、封存與引用摘要。
- 多語顯示名稱與不變 canonical code。
- 初始 fixture 以 idempotent seed migration/command 匯入。
- CadWorkspace、SimilarityWorkspace、ProcessTrialWorkspace 等受控欄位改讀 API。
- API 故障時顯示可恢復錯誤，不靜默退回未治理的任意正式值。
- Master Data 變更 Audit、ETag／`row_version`、cache invalidation。

#### Enterprise Contract

- `source_system`、`source_refs`、`scope`、`classification`、`effective_from/to`。
- Company master source 為唯讀時，平台欄位與本機 override 的界線。

#### 測試與 Gate

- 每種主檔 CRUD（實際 Delete 驗證為 Deactivate/Archive）。
- 重複 code、停用後新表單不可選、歷史仍正確顯示。
- 被引用資料不可硬刪除並回傳引用摘要。
- ETag 衝突回傳 409，不覆蓋另一使用者資料。
- 中英文名稱、鍵盤與表單錯誤可用性。
- UI 不再把正式選項寫死；允許的 emergency fallback 必須標為 Demo fixture。

#### Git Gate

`feat: add governed master data management`

### Phase 3 — Mold Registry、Revision 與 CAD Artifact 管理

#### Demo Deliverable

- Project、Product/Part、Mold、MoldRevision 最小 registry。
- Mold/CAD 清單、詳細、關聯、版本、品質、Job、Lineage 與 Audit 頁。
- STEP/STL 上傳掛入 MoldRevision；原始 ArtifactVersion immutable。
- 重複 hash 偵測、檔案驗證、Quarantine、Preview、parse/index 狀態。
- 重新解析、特徵重建、重新索引由 Job 啟動且保留舊版本。
- Archive impact preview；有工程引用時禁止 Hard Delete。
- 現有 curated CAD fixture 映射至明確 Demo Project/MoldRevision。

#### Enterprise Contract

- PDM/PLM IDs、native CAD metadata、revision mapping 與 connector ownership。
- Customer/Project scope 與 Artifact classification。

#### 測試與 Gate

- Mold hierarchy 的唯一碼、關聯完整性及版本不可變性。
- 檔案副檔名、MIME、magic bytes、大小、hash 與 malware adapter 測試。
- Retry/idempotency；舊 FeatureSet/Result 不被新 Job 覆寫。
- Viewer download deny、Engineer upload allow、跨 Scope 全面 deny。
- Archive/restore、引用保護、Lineage 鏈與 Audit。
- 現有 CAD similarity/design review regression 與 Golden Dataset 保持通過。

#### Git Gate

`feat: add mold registry and governed CAD artifacts`

### Phase 4 — Rule 與 Knowledge 發布生命週期

#### Demo Deliverable

- Rule Profile、Rule Version 的建立、測試、送審、核准、發布、退役 UI/API。
- 受限 DSL／registered evaluator；禁止任意程式碼。
- Author/Reviewer/Approver SoD 與版本差異。
- Knowledge 文件 metadata、版本、Authority、ACL、Quarantine、publish/retire。
- Parser/Chunk/Index 狀態與 Citation 對 ArtifactVersion 定位。
- 已發布內容修改時建立新版本；舊 Review/Citation 可重現。

#### Enterprise Contract

- Rule scope：Product、Material、Customer、effective date。
- Knowledge classification、Legal Hold、企業文件類型與 approval mapping。

#### 測試與 Gate

- Rule state machine 所有合法／非法轉移。
- positive、negative、boundary、not-applicable、not-evaluable fixture。
- 自己核准被拒；合法第二人核准成功且 Audit 完整。
- Retired Rule/Document 不用於新工作，歷史結果仍可閱讀。
- Quarantined/unauthorized 文件不進入 keyword/vector candidate。
- Prompt injection 文件掃描與不受信任內容邊界。
- 既有 design review、knowledge/RAG、MCP regression。

#### Git Gate

`feat: add governed rule and knowledge lifecycle`

### Phase 5 — Trial、CAE 與 HMI 資料管理

#### Demo Deliverable

- Trial/Process 的建立、編輯 Draft、結案、重開與 Correction Record。
- Defect/Material/Machine/Location/Unit 引用主檔，未知值進 Mapping Backlog。
- CAE Study/Run/Result 匯入、metadata、compatibility 與 archive 管理。
- HMI Profile 版本、Extraction、人工 review、Export Artifact 與 correction decision。
- 三模組詳細頁皆提供關聯、版本、品質、Lineage、Audit。

#### Enterprise Contract

- MES/QMS/CAE Connector mapping、source authority、solver license 與 unit policy。
- Machine write 永遠不在資料管理 CRUD 範圍內；未來另行安全設計。

#### 測試與 Gate

- Trial 結案後不得覆寫，Correction 保留 before/after。
- CAE incompatibility 必須拒絕比較且提供 typed reason。
- HMI 低信心或 invalid field 不可匯出；人工修正不覆寫 raw OCR。
- Connector 重跑 idempotent、unit conversion、unknown mapping。
- Process/Trial、CAE、HMI 現有 regression 與 Golden scenarios。

#### Git Gate

可依風險拆成三筆通過測試的 commit，或在共同驗收通過後提交：
`feat: add governed trial CAE and HMI data management`

### Phase 6 — Bulk Import、治理、封存與營運

#### Demo Deliverable

- CSV/XLSX/ZIP + Manifest 的 upload、mapping、Dry Run、確認、非同步 commit、報告。
- Added/Updated/Skipped/Warning/Error 與 canonical ID reconciliation。
- Job/Queue 管理、受控 cancel/retry、Audit/Lineage UI。
- Archive、restore、derived purge 模擬／受控流程；Demo 不開放一般 Hard Delete。
- Export 權限、欄位遮罩、非同步檔案及短效下載。
- 管理 Dashboard：coverage、quarantine、failed import、stale job、待審核。

#### Enterprise Contract

- Retention、Legal Hold、DLP、SIEM、Object Lock、正式 purge 與雙人核准。
- PDM/PLM/MES/QMS/CAE Connector 排程、checkpoint、dead-letter、reconciliation。

#### 測試與 Gate

- Dry Run 零正式寫入；相同 source version 重跑 idempotent。
- all-or-nothing 與逐筆 commit 策略不可混淆。
- 權限、遮罩與 Scope 在匯出前套用。
- 大量操作具配額、rate limit、timeout、cancel 與清楚進度。
- Archive 引用摘要、Legal Hold deny、restore state machine。
- Audit export 也產生 Audit；一般 Admin 無法修改 Audit/Lineage。
- Backup/restore 後 revoked identity 與 archived state 不被錯誤恢復。

#### Git Gate

`feat: complete governed data operations and bulk workflows`

### Phase 7 — Enterprise Identity 與 Company Connector（公司環境）

#### 前置條件

- 公司核准 IdP 測試租戶、OIDC/SAML metadata、claim/group 規則。
- 公司 Data Classification、RBAC/ABAC、Retention、DLP 與供應商政策。
- PDM/PLM/MES/QMS/CAE Sandbox、service identity 與 sample schema。

#### Deliverable

- OIDC/SAML、JIT/SCIM、Group Mapping、MFA/Conditional Access 整合。
- Data Scope 與 Classification policy enforcement。
- Service Account/Vault/Workload Identity、SIEM 與 Access Review。
- Public/Synthetic Connector 切換為 Company Connector，但不改 Domain API。
- 企業容量、HA/DR、安全與滲透驗收。

#### Git Gate

依 Connector/Identity adapter 分別提交；正式 Secret 與環境值永不進 Git。

## 5. 現有資料遷移策略

### 5.1 Hard-coded 選項轉主檔

1. 列出前端、後端 constant、fixture 與測試中的所有值。
2. 建立 canonical code、英文／繁中名稱、Alias 與來源。
3. 使用 idempotent command 建立主檔並輸出 reconciliation。
4. 對既有資料 backfill foreign key；未知值標記 `mapping_required`，不可默默丟棄。
5. UI 改讀 Master Data API，同一 release 暫時保留可觀測 fallback。
6. 使用率與錯誤穩定後移除 hard-coded production fallback。

### 5.2 Fixture 與正式資料隔離

- Synthetic/Public 資料保留固定 Dataset ID、classification 與 source label。
- 測試 fixture 只允許在明確 Demo/Test 模式載入。
- Production startup 不自動重灌或覆寫公司資料。
- Seed command 必須 idempotent 並提供 `--dry-run`；破壞式 reset 維持 backup-first、雙確認。

### 5.3 身分遷移

- Demo 本機使用者切換 Enterprise SSO 時，以管理員核准流程連結 ExternalIdentity。
- 不可只因 Email 相同自動合併帳號。
- 合併保留舊 Actor ID Alias 與 Audit provenance。
- 共用 Bearer Token 產生的歷史事件標為 `demo_shared_gateway`，不得偽造成人員事件。

## 6. API、Migration 與相容性要求

- 每個 DB migration 必須可由乾淨資料庫與既有 Demo backup 升級測試。
- Schema 變更採 expand → migrate/backfill → switch → contract，不同版本服務可安全短暫共存。
- API response 新增欄位應向後相容；移除／改義需新 API 或 schema version。
- Domain Event 使用 outbox，consumer 支援 idempotency 與未知欄位忽略策略。
- DB transaction 不包含長時間 CAD/LLM/Connector 呼叫。
- Audit 事件與業務寫入必須在可證明一致的 transaction/outbox 邊界內。
- 索引可由 DB + Artifact + manifest 重建；Qdrant 不是唯一事實來源。

## 7. 測試策略

### 7.1 Unit Test

- Entity validation、code uniqueness、state machine、versioning、ETag。
- Permission resolution、Scope intersection、explicit deny、SoD。
- Password/token/session helper 與 Secret redaction。
- Mapping、unit conversion、import diff、archive impact。

### 7.2 API／Integration Test

- 每個 endpoint 的 happy path、validation、401、403、404、409、429。
- UI、MCP、Connector 對同一 Capability 得到一致 AuthZ。
- DB/Object/Qdrant/Redis/Worker 中斷、retry 與 reconciliation。
- File upload、malware adapter、download authorization 與 short-lived URL。
- Outbox delivery、duplicate event、dead-letter 與 index rebuild。

### 7.3 UI／Accessibility Test

- 清單 filter/sort/page、detail tabs、version diff、empty/error/loading/success state。
- Create/Edit/Review/Archive/Import 表單的 required、helper、server error 與 validation summary。
- Viewer 不顯示不適用 action；直接呼叫仍被 API 拒絕。
- 中英文、鍵盤、focus、screen reader label、contrast 與 responsive layout。
- 破壞性操作確認內容包含實體、影響、原因與是否可回復。

### 7.4 Security Test

- Broken access control、IDOR、跨 Scope search/count/facet/cache leak。
- CSRF、CORS、XSS、SQL/command/template injection、open redirect、clickjacking。
- Login brute force、session fixation、token replay/expiry/audience/issuer。
- Malicious archive、path traversal、MIME spoof、oversized upload、formula injection。
- Prompt injection 文件不得改變授權或執行未核准 Tool。
- Secret scan、dependency/container scan 與 log redaction。

### 7.5 Reliability／Recovery Test

- Worker crash、duplicate delivery、timeout、retry exhaustion、stale job recovery。
- Backup/restore、Qdrant rebuild、Artifact checksum 與 audit continuity。
- 權限撤銷後 cache invalidation；還原舊 backup 不復活已撤銷 credential。
- Import 中斷後 resume/reconcile，不產生不可識別的半套資料。

## 8. 效能初始門檻

以下為單機 Demo 初始工程目標，需在固定硬體、資料量與測試腳本下紀錄；Enterprise 另行容量核准。

| 操作 | Demo 初始目標 |
|---|---:|
| Master/Entity list P95 | ≤ 1.0 s |
| Entity detail P95 | ≤ 1.5 s |
| Authenticated `/auth/me` P95 | ≤ 300 ms |
| Server-side authorization 額外 P95 | ≤ 100 ms |
| 10k rows import dry-run | ≤ 60 s，非同步可回報進度 |
| 10k metadata export | ≤ 60 s，非同步產生 |
| 緊急帳號／credential 撤銷 | 新請求立即；既有 Session 依配置且可驗證 |
| Master Data cache 失效 | ≤ 60 s Demo 目標 |

測試報告必須記錄 CPU、RAM、GPU、Docker、資料量、並行數、冷／暖 cache 及成功率；只報平均值不算驗收。

## 9. UAT 驗收情境

### 9.1 帳號與權限

- **UAT-IAM-01**：Admin 建立 Alice（Editor）與 Bob（Approver），兩人個別登入且 Audit Actor 不同。
- **UAT-IAM-02**：Viewer 嘗試由 UI、API、deep link、MCP 修改 Material，全部被拒且不洩漏額外資料。
- **UAT-IAM-03**：Alice 建立 Rule Version 後不能自行核准；Bob 在相同 Scope 可核准。
- **UAT-IAM-04**：撤銷 Alice Project A Scope 後，她無法搜尋、計數、下載或匯出 Project A 資料。
- **UAT-IAM-05**：停用 Alice 後，既有 Session 失效；歷史 Rule/Audit 仍顯示同一 Actor。
- **UAT-IAM-06**：Service Account 只能執行指定 Connector，無法進入管理 UI 或擴大 Scope。
- **UAT-IAM-07**：Secret 掃描與 log 檢查找不到密碼、Token、LLM API Key、Tunnel Key。

### 9.2 主檔與 Mold/CAD

- **UAT-DM-01**：Steward 新增 Material 後工程表單可選取；停用後新表單不再列出，歷史紀錄仍顯示。
- **UAT-DM-02**：兩位 Editor 同時編輯相同主檔，第二筆過期 ETag 被 409 拒絕。
- **UAT-DM-03**：Engineer 建立 Mold/Revision、上傳 STEP、完成 parse/index，Lineage 可一路追溯原檔。
- **UAT-DM-04**：替換 CAD 產生新 ArtifactVersion；舊 Design Review 仍指向原版本。
- **UAT-DM-05**：有引用的 CAD/Master 無法 Hard Delete，Archive 前顯示影響摘要。

### 9.3 Rule、Knowledge、Trial、CAE、HMI

- **UAT-DM-06**：Rule 通過 fixtures、審查、核准與發布；任一非法 state transition 被拒。
- **UAT-DM-07**：Knowledge 新版本發布後用於新檢索；歷史 Citation 仍可定位舊版本。
- **UAT-DM-08**：Trial 結案後修正建立 Correction，不改寫原始參數與缺陷。
- **UAT-DM-09**：兩個不相容 CAE Run 無法比較；相容 Run 產生版本化 Comparison。
- **UAT-DM-10**：低信心 HMI 欄位未人工確認前不能匯出 Excel。

### 9.4 匯入、封存與治理

- **UAT-DM-11**：XLSX Dry Run 顯示新增／更新／錯誤且 DB 零變更；確認後由 Job commit。
- **UAT-DM-12**：相同 source version 重跑不重複建立資料，並產生 reconciliation report。
- **UAT-DM-13**：跨 Scope 匯出只含授權資料與遮罩欄位，下載過期後不可再用。
- **UAT-DM-14**：Audit 頁可追蹤 Actor、Entity、Request、Decision；Platform Admin 無法修改事件。
- **UAT-DM-15**：Backup/restore 後 Artifact checksum、版本、Lineage、Audit 與停權狀態一致。

## 10. 需求追溯矩陣

| 需求群組 | 實作階段 | 主要測試 | UAT |
|---|---|---|---|
| IAM-COM / IAM-D | Phase 1 | auth/session/lifecycle | IAM-01, 05 |
| IAM-AUTHZ / IAM-SOD | Phase 1–4 | matrix/scope/SoD/IDOR | IAM-02–04 |
| IAM-ADM / IAM-SVC / IAM-AUD | Phase 1, 6 | admin/service/audit/security | IAM-05–07, DM-14 |
| DM-MST | Phase 2 | CRUD/reference/cache/ETag | DM-01, 02 |
| DM-CAD | Phase 3 | artifact/version/job/lineage | DM-03–05 |
| DM-RUL / DM-KNW | Phase 4 | workflow/index/authorization | DM-06, 07 |
| DM-TRI / DM-CAE / DM-HMI | Phase 5 | correction/compatibility/review | DM-08–10 |
| DM-IMP / DM-DEL / DM-GOV | Phase 6 | dry-run/idempotency/archive/audit | DM-11–15 |
| IAM-E / IAM-MCP | Phase 7 / MCP release | OIDC/token/delegation/scope | Enterprise UAT |

每個 Pull Request 應在描述中列出受影響需求 ID、測試名稱與 migration；不能只寫「完成 CRUD」。

## 11. Release、Feature Flag 與回復

- 新管理路由在 schema 與權限完成前保持關閉。
- Migration 上線先 expand；資料 backfill/reconcile 通過後才切換讀取來源。
- Master Data API 切換期間可保留明示且可觀測的 Demo fallback，不允許 silent fallback。
- IAM 上線前保留受控本機復原路徑，但不得形成永久認證旁路。
- 每階段發布前建立資料庫與 Artifact 備份；測試 restore 而非只測 backup。
- 回復應關閉新寫入、回切相容 read path，不使用 `git reset --hard` 或直接刪除正式資料。
- 破壞性 migration 必須等至少一個穩定 release 且完成備份／還原證據後執行。

## 12. Definition of Done

每一階段只有在以下條件全部成立時才算完成：

1. 對應 MUST requirements 已實作，延後項目有決策紀錄。
2. Model、migration、API、UI、i18n、Audit、Lineage 與文件同步更新。
3. Unit、API、UI、security-relevant regression 與該階段 UAT 通過。
4. 無未授權旁路、無 Secret、無高風險 debug/default credential。
5. 全新安裝與既有 Demo 資料升級皆成功。
6. `git diff --check`、lint/typecheck/test 通過，Git 工作樹只含該階段變更。
7. 效能未超出門檻；若超出有量測、原因與核准例外。
8. 操作手冊、備份／回復、限制與下一階段相依已更新。
9. 建立有意義的 Git commit，包含需求／測試範圍；不把多個未驗證階段壓成不透明提交。

## 13. 風險與緩解

| 風險 | 影響 | 緩解 |
|---|---|---|
| 先做 CRUD、後補 IAM | 無法可信稽核與隔離 | Phase 1 先完成最小 IAM |
| 把 Email 當永久 ID | 改名／併購後身分錯接 | Canonical UUID + issuer/subject |
| Published 資料直接 Update | 歷史結果不可重現 | immutable content + new version |
| 前端寫死主檔與 DB 不一致 | 無效輸入、搜尋漏失 | Master API + idempotent seed |
| 全能 Platform Admin | 權限濫用、Audit 不可信 | SoD、explicit permissions、Audit immutable |
| 搜尋後才過濾 | 向量／facet 側通道洩漏 | candidate generation 前套 Scope |
| Connector 重跑重複資料 | 統計與 Lineage 污染 | source identity + idempotency + reconciliation |
| 直接 Hard Delete | 破壞關聯、法規與報告 | Archive first + impact + Legal Hold |
| 自建 Enterprise 密碼庫 | 高維運與安全風險 | 公司 IdP + federation adapter |
| MCP Tunnel Key 當使用者 | 無個人責任歸屬 | OAuth delegated identity + actor mapping |

## 14. 建議首個可交付版本

第一個可供私人 Demo 實際使用的「Data Admin v0.1」應包含：

- Phase 1 的本機帳號、固定角色、Session、Audit 與基本 Scope。
- Phase 2 的七類主檔 CRUD／停用及工程表單動態選項。
- Phase 3 的 Mold Registry、Revision 與 CAD Artifact 管理。
- Rule 管理至少完成 Draft → Review → Approve → Publish 與 SoD。
- 其餘 Trial/CAE/HMI 先提供唯讀詳細與既有資料關聯，再逐步開放受控寫入。

此範圍能先解決「資料只能靠檔案或程式碼維護」的核心問題，同時不犧牲未來 Enterprise
所需的身分、版本、權限與稽核基礎。
