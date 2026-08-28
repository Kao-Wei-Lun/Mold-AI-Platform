# 12 — Identity, Access and Account Management Software Requirements Specification

版本：0.1 Draft  
日期：2026-08-28  
適用範圍：Mold AI Platform Demo 擴充版與 Enterprise 正式版

## 1. 文件目的

本文件定義 Mold AI Platform 的帳號、登入、角色、資料範圍、權限、工作階段、服務帳號、
核准職責分離及身分稽核需求。它是
[資料管理中心 SRS](11_Data_Management_SRS.md) 的必要相依規格。

本文件中的「帳號管理」不只是登入畫面。它必須回答：

- 誰正在操作，以及身分由誰證明。
- 使用者可以對哪個組織、客戶、專案、模具與資料分類執行哪些動作。
- 誰建立、審查、核准、匯出、封存或拒絕某項工程資料。
- Web UI、MCP、Connector、Worker 與排程工作如何延續同一 Actor 或 Service Identity。
- 人員離職、轉調或權限到期後，如何立即停止存取但保留歷史歸屬。

## 2. 是否需要帳號管理：決策與理由

**需要，且應在完整資料管理功能之前或同一階段完成基礎版本。**

若沒有帳號管理，系統無法可靠實現：

1. 新增、修改、核准、封存與匯出的 Actor 追溯。
2. 模具設計規定的 Author／Reviewer／Approver 職責分離。
3. 客戶、供應商、Business Unit、Project 與資料分類隔離。
4. 個人待辦、儲存的查詢條件、語言及通知偏好。
5. MCP 與 Web UI 的一致授權及寫入確認。
6. 帳號停用、權限到期、Session 撤銷及安全事件調查。
7. Enterprise SSO、公司目錄與離職停權流程。

Demo 可先使用受控的本機帳號與固定角色；Enterprise 應整合公司 IdP。正式版不得自行建立
另一套公司密碼目錄來取代既有 SSO／AD。

## 3. 現況與目標差距

### 3.1 目前 Demo 現況

- Django 已包含基礎 authentication 元件，但尚未形成平台帳號管理功能。
- 對外 Demo 可設定共用 Bearer Token；Token 代表入口憑證，不代表每一位人員。
- 多數 API View 目前未套用個別使用者 permission class。
- MCP 支援 `none` 或 Demo Bearer 模式；OAuth 使用者身分映射尚未完成。
- UI 可顯示 Access 狀態，但沒有使用者、角色、群組與授權範圍管理頁。

以上機制可供私人連線 Demo 使用，但不符合多人資料管理與 Enterprise 驗收條件。

### 3.2 目標狀態

```text
Human / MCP Client / Connector / Worker
                │
        Authentication Layer
                │
     Canonical Identity + Session
                │
   RBAC Permission + ABAC Data Scope
                │
         Domain Capability API
                │
       Audit / Lineage / Decision
```

任何入口只要執行相同 Capability，就必須得到相同的授權結果；不得因從 MCP、管理 UI 或
內部 API 呼叫而繞過資料範圍。

## 4. 目標與非目標

### 4.1 目標

- 提供安全登入、登出、Session 與帳號生命週期。
- 以 RBAC 表達工作職責，以 ABAC／Scope 表達可接觸的資料範圍。
- 提供可管理的使用者、群組、角色、權限指派與有效期間。
- 讓工程核准、稽核與 Lineage 指向不可混淆的 Actor ID。
- 對 Web、MCP、API、Worker、Connector 與排程套用一致政策。
- Demo 與 Enterprise 共用授權模型，只替換身分來源及部署整合。

### 4.2 非目標

- 不取代 Enterprise IdP、Active Directory、人資系統或 PAM。
- 不在應用程式保存第三方 LLM、MCP Tunnel 或 Connector 的明文 Secret。
- 不允許 Platform Admin 修改或刪除既有 Audit 來改寫歷史。
- 不以電子郵件地址作為永久 Canonical Identity。
- 不允許 LLM 自行授予角色、建立高權限帳號或核准自己的動作。

## 5. 身分與帳號類型

| 類型 | 用途 | 認證來源 | 是否可互動登入 |
|---|---|---|---:|
| Demo Human Account | 私人 Demo 與開發測試 | 平台本機帳號 | 是 |
| Federated Human Account | Enterprise 員工／核准供應商 | OIDC／SAML IdP | 是 |
| Service Account | Connector、整合服務、排程 | Workload credential | 否 |
| Worker Identity | Job Worker 執行受派工作 | Workload identity／短效 credential | 否 |
| MCP Client Identity | ChatGPT／支援 MCP 的 Client | OAuth subject + delegated user | 是，透過 Client |
| Break-glass Account | IdP 故障時的緊急維運 | 離線受控高強度認證 | 僅緊急 |

- 共用人員帳號禁止使用。
- 共用 Demo 入口 Token 不得被記錄成實際核准者。
- Service Account 必須有 Owner、用途、Scope、到期日與輪替政策。
- Worker 應保存 `requested_by` 與 `executed_by`，避免把背景工作歸屬錯記為人員直接執行。

## 6. Canonical Identity Data Model

### 6.1 UserAccount

至少包含：

- `user_id`：平台 UUID，永久且不重用。
- `username`：Demo 唯一登入名；Enterprise 可為顯示或別名。
- `display_name`, `preferred_name`, `email`。
- `account_type`, `status`, `locale`, `timezone`。
- `business_unit_id`, `manager_user_id`（如適用）。
- `source_system`, `external_subject_refs`。
- `created_at`, `activated_at`, `last_login_at`, `disabled_at`。
- `created_by`, `disabled_by`, `disable_reason`。
- `row_version`。

電子郵件可變更，不得作為外鍵、Audit Actor ID 或 OIDC 唯一比對依據。

### 6.2 其他核心實體

- `ExternalIdentity`：issuer、subject、provider、claims snapshot hash、last_seen_at。
- `Group`：組織群組或 IdP group mapping。
- `Role`：穩定的工作角色與版本。
- `Permission`：`resource.action` 格式的最小授權單位。
- `RoleAssignment`：subject、role、scope、valid_from/to、granted_by、reason。
- `AccessPolicy`：條件、效果、優先序、版本及生效日。
- `DataScope`：Tenant、Business Unit、Customer、Supplier、Project、Dataset、Classification。
- `Session`：session_id、subject、issued/last_seen/expires、client、IP/UA hash、revocation。
- `ServiceAccount`：owner、purpose、allowed capabilities、scope、status、expiry。
- `CredentialMetadata`：credential ID、type、created/rotated/expires/revoked；不保存可回讀 Secret。
- `Delegation`：delegator、delegate、permission/scope、有效期間與原因。
- `AccessReview`：Reviewer、範圍、決定、證據與完成時間。

## 7. 帳號生命週期

```text
Invited / Provisioned → Active → Suspended → Active
                              └→ Disabled → Archived Identity
```

- `Invited`：僅 Demo 本機帳號適用，邀請應為一次性且短效。
- `Provisioned`：Enterprise 已從 IdP/SCIM 建立但尚未完成首次登入或授權。
- `Active`：可登入，實際能力仍由 Role、Scope 與 Policy 決定。
- `Suspended`：暫停登入，保留角色與歷史，可受控恢復。
- `Disabled`：不可登入，Session、Refresh Token 及活躍 Credential 必須撤銷。
- `Archived Identity`：保存歷史 Actor 參照，不可重新指派相同 `user_id`。

### 7.1 共通需求

- **IAM-COM-001**：建立、啟用、停用、恢復與權限變更必須產生 Audit。
- **IAM-COM-002**：帳號停用後，現有 Session 應在可配置的撤銷 SLA 內失效。
- **IAM-COM-003**：刪除個資時應保留 pseudonymous Actor ID 與必要 Audit，不改寫工程歷史。
- **IAM-COM-004**：所有 RoleAssignment 必須有授予者、理由、Scope 與有效期間。
- **IAM-COM-005**：不得因使用者重新啟用而自動恢復已過期或已撤銷的高權限。
- **IAM-COM-006**：登入名、Email 或顯示名稱變更不得改變歷史 Actor 關聯。

## 8. 認證需求

### 8.1 Demo 本機認證

- **IAM-D-001**：Demo 應提供每人獨立本機帳號，不使用共用 Admin 帳密。
- **IAM-D-002**：首次啟動採一次性 bootstrap 建立首位管理者；完成後自動關閉 bootstrap。
- **IAM-D-003**：密碼使用框架核准的強雜湊、唯一 salt 與可升級參數，不自行實作加密。
- **IAM-D-004**：應提供登入、登出、變更密碼、忘記密碼／管理員重設及強制登出。
- **IAM-D-005**：不得在 Repository、Image、`.env.example`、log 或前端 bundle 放置預設密碼。
- **IAM-D-006**：連續失敗應受 rate limit、遞增延遲與暫時鎖定保護。
- **IAM-D-007**：管理者與 Approver 宜啟用 MFA；若 Demo 階段未啟用，需標示限制且不得宣稱正式安全。
- **IAM-D-008**：安全 Cookie 應設定 `HttpOnly`、`Secure`、適當 `SameSite`，並使用 CSRF 防護。
- **IAM-D-009**：目前共用 Bearer Token 僅作過渡式入口保護，不得成為完整帳號功能的驗收替代品。

### 8.2 Enterprise 聯合認證

- **IAM-E-001**：Enterprise 應支援企業核准的 OIDC；若公司僅提供 SAML，透過核准的 Broker 或 SAML 整合。
- **IAM-E-002**：帳號映射以驗證過的 `issuer + subject` 為主，不以 Email 單獨綁定。
- **IAM-E-003**：MFA、裝置、地點與 Conditional Access 由企業 IdP 政策強制執行。
- **IAM-E-004**：應支援 JIT 或 SCIM Provisioning；啟用方式由企業 IAM 核准。
- **IAM-E-005**：來源帳號停用或群組移除應在約定 SLA 內同步停權／撤權。
- **IAM-E-006**：IdP claim/group 到平台 Role 的 Mapping 必須版本化、可預覽且可 Audit。
- **IAM-E-007**：未知 issuer、subject、audience、nonce、state 或過期 token 必須 fail closed。
- **IAM-E-008**：正式環境不得以 Developer Mode、Debug Header 或靜態共用 Token 旁路 SSO。

### 8.3 MCP／ChatGPT 認證

- **IAM-MCP-001**：公開或多人使用的私人資料 MCP 應使用當時官方支援且經查證的 OAuth 流程。
- **IAM-MCP-002**：MCP OAuth subject 應映射為平台 Canonical User；Tunnel Runtime API Key 只用於建立通道，不是最終使用者身分。
- **IAM-MCP-003**：MCP token 的 audience、scope、expiry、issuer 與 signature 必須驗證。
- **IAM-MCP-004**：MCP 執行寫入時應記錄 `actor_id`、`client_id`、`conversation/request correlation` 與 confirmation evidence。
- **IAM-MCP-005**：若 Client 無法提供可驗證個人身分，僅開放最小唯讀 Demo Scope，不得執行核准或高風險寫入。
- **IAM-MCP-006**：OpenAI／ChatGPT 實際支援方式應在開發與上線前依官方文件重新查證，不將變動中的 UI 流程寫死於 Domain Contract。

## 9. 授權模型

### 9.1 RBAC + ABAC

授權結果由以下條件共同決定：

```text
Allow = Authenticated
    AND Role grants Resource.Action
    AND Data Scope matches Entity attributes
    AND Classification policy allows access
    AND Workflow state allows action
    AND Separation-of-Duties passes
    AND No explicit deny / legal hold restriction
```

- RBAC 用於 `rule.approve`、`cad.upload`、`knowledge.publish` 等動作。
- ABAC 用於 Tenant、Business Unit、Customer、Supplier、Project、Dataset、Classification、Owner。
- Explicit Deny 優先於 Allow。
- 前端隱藏按鈕不是授權；API 與背景工作必須重做 Server-side Authorization。

### 9.2 代表性權限

- `master_data.read/create/update/deactivate`
- `mold.read/create/update/archive`
- `artifact.upload/download/reprocess/archive`
- `rule.read/create_version/submit/review/approve/publish/retire`
- `trial.read/create/correct/close/reopen`
- `cae.read/import/compare/archive`
- `knowledge.read/import/publish/retire`
- `hmi.read/extract/review/export`
- `job.read/cancel/retry`
- `audit.read/export`
- `identity.read/invite/update/disable`
- `role.read/assign/revoke`
- `service_account.create/rotate/revoke`

### 9.3 預設角色矩陣

| 角色 | 主要能力 | 明確限制 |
|---|---|---|
| Viewer | 授權資料唯讀 | 不可下載受限原檔、不可寫入 |
| Data Editor | 建立與修改 Draft | 不可發布、核准、硬刪除 |
| Data Steward | 主檔、Mapping、品質、封存 | 不可修改 Audit；敏感匯出另授權 |
| Mold Engineer | Mold/CAD/Trial 工程操作 | 不可核准自己的 Rule/Waiver |
| Rule Owner | 建立版本、測試、送審 | 不可核准自己的版本 |
| Technical Reviewer | 技術審查與退回 | 不因審查角色自動取得發布權 |
| Approver | 核准／拒絕指定 Scope | 不得核准自己建立或被委託禁止的項目 |
| Knowledge Curator | 文件與 Authority 管理 | 不可自行提升至最高權威級別而無核准 |
| Platform Admin | 帳號、設定與營運 | 不可改寫工程決定或 Audit |
| Auditor | Audit、Lineage、Access Review 唯讀 | 不可變更營運資料 |

### 9.4 資料範圍與檢索

- **IAM-AUTHZ-001**：授權過濾必須在關鍵字、向量或相似度候選產生前執行。
- **IAM-AUTHZ-002**：回應中的 count、facet、建議值、錯誤與 timing 不得洩漏無權資料存在。
- **IAM-AUTHZ-003**：下載、Preview、Citation、deep link 與 Export 均應重新驗證權限。
- **IAM-AUTHZ-004**：Cache key 必須包含有效 Scope/Policy version，避免跨使用者資料污染。
- **IAM-AUTHZ-005**：Job 建立時與結果領取時皆需驗證；長時間 Job 執行前宜重新檢查關鍵權限。
- **IAM-AUTHZ-006**：Connector 只可寫入指定 Source/Scope，不因是內部服務而擁有全域權限。
- **IAM-AUTHZ-007**：權限拒絕使用一致錯誤，不回傳敏感資源細節。

## 10. 職責分離與委派

- Rule 作者不得核准自己建立的 Rule Version。
- Waiver 申請者不得成為唯一核准者。
- 高權限 Role 指派、Hard Delete、Audit Export 與 Break-glass 可要求雙人核准。
- 委派必須指定起訖時間、能力、Scope、原因，並在到期後自動失效。
- 委派不應允許把權限再委派，除非 Policy 明確允許。
- Emergency override 應帶有事件編號、短效時限與事後審查。

- **IAM-SOD-001**：API 應根據實際 Actor 與資料作者關係驗證 SoD，不信任前端傳入 Approver 名稱。
- **IAM-SOD-002**：核准紀錄保存 Actor ID、當時角色、Policy version、決定、理由與時間。
- **IAM-SOD-003**：系統不得以刪除或修改帳號來改變既有核准紀錄的顯示與有效性。

## 11. 帳號管理 UI

```text
/admin/identity                 帳號與存取總覽
/admin/identity/users           使用者
/admin/identity/users/:id       帳號、群組、角色、Scope、Session、Audit
/admin/identity/groups          群組及 IdP Mapping
/admin/identity/roles           角色與權限矩陣
/admin/identity/assignments     Role Assignment 與到期項目
/admin/identity/service-accounts 服務帳號
/admin/identity/sessions        Session 與撤銷
/admin/identity/access-reviews  定期存取審查
/admin/identity/audit           身分與權限 Audit
```

### 11.1 管理功能

- **IAM-ADM-001**：管理者可依名稱、狀態、類型、角色、群組、Scope 與最後登入時間查詢帳號。
- **IAM-ADM-002**：建立／邀請帳號時應先檢查重複 External Identity，不以相似 Email 自動合併。
- **IAM-ADM-003**：角色指派前顯示新增權限、資料範圍、有效期間與高風險警告。
- **IAM-ADM-004**：停用帳號前顯示待核准項目、Owned Service Account 與未完成工作移交。
- **IAM-ADM-005**：可撤銷指定 Session 或全部 Session，並立即寫入 Audit。
- **IAM-ADM-006**：角色與 Policy 版本差異應可閱讀，禁止在無預覽下大量授權。
- **IAM-ADM-007**：批次指派需 Dry Run、影響人數、錯誤報告、第二次確認及可追蹤 Job。
- **IAM-ADM-008**：UI 須支援中英文、鍵盤操作、焦點管理與不只依顏色表達狀態。
- **IAM-ADM-009**：一般 Platform Admin 不得查看密碼、Token 或 Secret 明文。
- **IAM-ADM-010**：使用者應可查看自己的基本資料、有效角色、Scope、Session 與安全事件。

## 12. Session、Token 與瀏覽器安全

- 閒置逾時、絕對 Session 壽命及敏感操作重新驗證應可配置。
- 權限升級、密碼重設、MFA 變更與帳號停用後應撤銷相關 Session。
- Refresh Token 需 rotation；偵測 reuse 時撤銷 token family。
- Access Token 短效，僅含最小 claim；敏感授權以 Server-side 最新政策為準。
- 登出應同時終止應用 Session；Enterprise 是否觸發 IdP logout 依整合政策。
- Web UI 不得將 Access Token 放入 URL、localStorage 或可被一般 script 讀取的長期儲存。
- CORS、CSRF、CSP、clickjacking、open redirect 與 login CSRF 必須測試。

## 13. Service Account 與 Secret 管理

- **IAM-SVC-001**：Service Account 必須與人員帳號分離，禁止互動登入。
- **IAM-SVC-002**：每個帳號只能存取明確 Capability、Connector 與 Data Scope。
- **IAM-SVC-003**：Credential 建立時僅顯示一次；系統只保存不可回讀表示或外部 Secret reference。
- **IAM-SVC-004**：Credential 應有到期日、輪替、雙 Key overlap 與緊急撤銷流程。
- **IAM-SVC-005**：Secret 不得出現在 Git、Container image、前端、Job payload、Audit detail 或一般 log。
- **IAM-SVC-006**：Owner 離職或轉調時，Owned Service Account 必須進入移交／停用工作流。
- **IAM-SVC-007**：Enterprise 宜使用 Vault/KMS/Workload Identity，避免長效靜態 API Key。
- **IAM-SVC-008**：OpenAI LLM API Key、Tunnel Runtime Key 與平台使用者認證應分離管理，不可互相替代。

## 14. Audit、事件與可觀測性

### 14.1 必記錄事件

- 登入成功／失敗、登出、鎖定、Session 撤銷。
- 帳號建立、邀請、啟用、停用、恢復、刪除個資。
- Role、Group、Scope、Policy、Delegation 的新增、修改與撤銷。
- Service Account/Credential 建立、輪替、到期及撤銷；不得記錄 Secret。
- 高風險操作重新驗證、拒絕、Break-glass 使用與 Access Review。
- MCP、Web、API、Connector 的 Actor、Client 與結果。

### 14.2 需求

- **IAM-AUD-001**：事件至少含 timestamp、actor、subject、action、scope、result、reason、request/correlation ID、source client。
- **IAM-AUD-002**：一般管理者不得修改或刪除 IAM Audit。
- **IAM-AUD-003**：登入失敗不得記錄輸入密碼、完整 Token 或不必要個資。
- **IAM-AUD-004**：異常登入、暴力嘗試、權限暴增、Break-glass 與大量匯出應觸發告警。
- **IAM-AUD-005**：Enterprise 應可輸出至 SIEM，並維持事件 schema/version。
- **IAM-AUD-006**：時間來源須同步；Audit 顯示使用者時區但保存 UTC。

## 15. 帳號復原與 Break-glass

- Demo 密碼重設使用一次性短效 Token 或受控管理流程，不可回傳舊密碼。
- Enterprise 帳號復原原則上由 IdP 完成；應用程式不得旁路企業 MFA。
- Break-glass 帳號數量最小化，Credential 離線保管、定期驗證及每次使用告警。
- 啟用 Break-glass 必須填寫事件編號，權限短效且使用後輪替 Credential。
- IdP 故障不代表所有使用者自動降級成匿名或全權限。

## 16. API 與錯誤契約

### 16.1 代表性端點

```text
POST            /api/v1/auth/login
POST            /api/v1/auth/logout
GET              /api/v1/auth/me
GET              /api/v1/auth/me/permissions
GET/POST         /api/v1/admin/users
GET/PATCH        /api/v1/admin/users/{id}
POST             /api/v1/admin/users/{id}/suspend
POST             /api/v1/admin/users/{id}/disable
POST             /api/v1/admin/users/{id}/revoke-sessions
GET/POST         /api/v1/admin/roles
POST             /api/v1/admin/role-assignments/dry-run
POST             /api/v1/admin/role-assignments
DELETE           /api/v1/admin/role-assignments/{id}
GET/POST         /api/v1/admin/service-accounts
POST             /api/v1/admin/service-accounts/{id}/rotate
POST             /api/v1/admin/service-accounts/{id}/revoke
GET              /api/v1/admin/access-reviews
```

### 16.2 錯誤與資訊揭露

- `401 AUTHENTICATION_REQUIRED/INVALID/EXPIRED`
- `403 ACCESS_DENIED/SCOPE_DENIED/SOD_VIOLATION/STEP_UP_REQUIRED`
- `409 IDENTITY_CONFLICT/CONCURRENT_MODIFICATION`
- `423 ACCOUNT_SUSPENDED/LOCKED`
- `429 AUTH_RATE_LIMITED`

外部登入失敗不得揭露帳號是否存在；管理介面可在授權後顯示更詳細的 reconciliation 資訊。

## 17. Demo 與 Enterprise 實作邊界

| 項目 | Demo 必做 | Enterprise 必做 |
|---|---|---|
| Human identity | 個別本機帳號 | OIDC/SAML 聯合身分 |
| 登入 | Session Cookie + CSRF | IdP flow + 平台 Session |
| MFA | 管理者宜啟用／明示限制 | 由 IdP 強制 |
| Role | 固定平台角色 | 可治理角色、Group Mapping |
| Scope | 單一 Demo Dataset/Project scope | Tenant/BU/Customer/Project/Class |
| Provisioning | Admin invite/bootstrap | JIT 或 SCIM + HR/IdP lifecycle |
| Service identity | 少量受控 Secret | Vault/Workload Identity/rotation |
| MCP | 私人 Demo，最小 Scope | OAuth delegated identity |
| Audit | DB append-only 邏輯與匯出 | SIEM、Retention、偵測與 Access Review |
| Break-glass | 可延後但須記錄限制 | 必做且定期演練 |

## 18. 非功能需求

- **IAM-NFR-001**：授權檢查不應使一般 API P95 額外增加超過初始目標 100 ms；正式值經基準測試核准。
- **IAM-NFR-002**：登入、Token 驗證、Role 變更與撤銷需可水平擴充且 fail closed。
- **IAM-NFR-003**：IdP、Policy Store 或 Cache 故障時不得默認允許。
- **IAM-NFR-004**：權限撤銷與 Cache 失效 SLA 應可監測；Enterprise 初始目標 5 分鐘內，緊急撤銷立即生效。
- **IAM-NFR-005**：敏感設定、credential metadata 與 Audit 應加密傳輸與依資料分類加密保存。
- **IAM-NFR-006**：所有安全 UI 支援 WCAG 2.1 AA 目標、鍵盤操作與中英文。
- **IAM-NFR-007**：備份／還原不得使已停用帳號、撤銷 Token 或舊 Policy 意外恢復有效。
- **IAM-NFR-008**：系統時間偏差超過容許範圍時，Token 驗證與 Audit 應告警。

## 19. 驗收條件摘要

1. 兩位不同帳號的操作在 Audit 中可明確區分。
2. Viewer 無法透過 UI、直接 API、deep link 或 MCP 寫入資料。
3. Rule Author 無法核准自己的版本，且拒絕原因可 Audit。
4. 使用者只能搜尋、計數、下載與匯出其 Scope 內資料。
5. 停用帳號後無法建立新 Session，既有 Session 在 SLA 內失效。
6. 停用主檔或歷史核准資料仍顯示原 Actor，不因帳號改名而失真。
7. Secret 不出現在 Git、log、API response、前端 bundle 或測試證據。
8. MCP 若缺少可驗證 delegated identity，不得執行高風險寫入。
9. Enterprise IdP 故障時系統 fail closed，Break-glass 使用會立即告警。
10. 權限矩陣、資料範圍、SoD、Session 撤銷與 Audit 測試全部通過。

詳細分階段測試見
[13_Data_Management_Implementation_Test_Acceptance.md](13_Data_Management_Implementation_Test_Acceptance.md)。

## 20. 待確認事項

- 公司 IdP 採 OIDC、SAML 或既有 Identity Broker。
- 是否具 SCIM、群組命名規則與人資離職事件整合。
- Customer、Supplier、Project、Business Unit 的資料隔離與跨 Scope 授權規則。
- 哪些操作要求 MFA step-up、雙人核准或 PAM。
- Session timeout、存取撤銷、Audit 保存與 Access Review 頻率。
- 外部供應商帳號的 Sponsor、到期、裝置與下載限制。
- ChatGPT/MCP 正式使用者身分、Workspace Policy 與 OAuth 配置。
- 個資遮罩、跨境、DLP、Legal Hold 與刪除政策。
