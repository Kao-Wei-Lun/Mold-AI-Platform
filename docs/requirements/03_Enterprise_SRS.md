# 03 — Enterprise Software Requirements Specification

## 1. 企業版目標

Enterprise 版本將 Demo 的可替換資料與單機元件正式化，支援公司資料、多人協作、組織權限、可稽核決策、模型治理及水平擴充。它不是把 Demo 容器直接搬上 Server，而是保留 Contract、Capability 與操作流程，替換 Connector、Identity、Storage、Deployment、Model 與營運控制。

## 2. 企業使用者與責任

- **Mold Designer/RD**：搜尋案例、設計審查、比較、提出 waiver。
- **Process/Trial Engineer**：缺陷分析、參數比較、試模結案與回饋。
- **CAE Engineer**：管理 study、比較結果、審核風險解讀。
- **Quality/Reviewer**：簽核 review、驗證 evidence、管理 false positive/negative。
- **Knowledge Curator**：管理文件、分類、有效期限與權威來源。
- **Data Steward**：資料 mapping、品質、主檔、Lineage 與保留政策。
- **Capability/Model Owner**：版本、評估、核准、監控與退役。
- **Tenant/Platform/Security Admin**：組織、權限、基礎設施、事件回應。
- **Auditor**：唯讀檢視操作、版本、核准與資料流向。

## 3. 企業共通功能需求

### 3.1 Identity and access

- **E-IAM-001**：應整合公司 OIDC/SAML SSO；使用穩定 subject ID，不以 email 作唯一外鍵。
- **E-IAM-002**：應支援使用者、群組、角色與 attribute-based policy；至少可依 customer、supplier、business unit、project、confidentiality、data purpose 限制。
- **E-IAM-003**：Service account、worker、connector 與人員帳號應分離，使用最小權限及可輪替 credential。
- **E-IAM-004**：離職、群組變更及專案關閉應在定義 SLA 內反映；緊急停權立即生效。
- **E-IAM-005**：向量、全文與關聯查詢均應在候選產生前套用 security filter，不得只在結果頁後置遮蔽。

### 3.2 Project/Mold lifecycle

- **E-DOM-001**：應管理 Project、Product、Part、Mold、Mold Revision、Drawing/CAD、CAE Study、Trial、Process Run、Defect、Corrective Action、Quotation、Maintenance 的關聯。
- **E-DOM-002**：所有工程 artifact 需 immutable version；新版本以 supersedes/derived_from 關聯，不覆寫歷史內容。
- **E-DOM-003**：應支援 draft、reviewed、approved、obsolete、quarantined 等 lifecycle，並限制未核准資料用於 production decision。
- **E-DOM-004**：應保留公司原始系統 ID、source record version、extract time 與 mapping version。

### 3.3 Capability lifecycle

- **E-CAP-001**：每個 Capability 應在 Registry 記錄 owner、version、schema、permissions、resource class、SLO、model/rule dependencies、validation suite 與 status。
- **E-CAP-002**：Draft/Shadow/Approved/Deprecated/Retired 階段應有明確 promote gate。
- **E-CAP-003**：相同輸入 snapshot、相同 deterministic component version 應可重現；非決定性輸出須保存 request parameters 與 evidence。
- **E-CAP-004**：重大版本可平行執行 shadow/canary；使用者結果應標示使用版本。

## 4. 企業功能需求

### 4.1 CAD Similarity

- **E-SIM-001**：支援公司核准的 STEP/IGES/STL/DWG/DXF/PDF/image 與選定 native CAD connector；每種格式有明確 support level。
- **E-SIM-002**：應支援 1M Mold Case 級別的離線索引設計；資料量定義以唯一 Mold/Part 為主，不以檔案數混用。
- **E-SIM-003**：搜尋採 coarse candidate → rerank → detailed compare；可按產品線套用 Similarity Profile。
- **E-SIM-004**：支援整體與選定局部結構搜尋；局部結果須保存 selection geometry reference。
- **E-SIM-005**：工程師 feedback 應進入 review queue，經標註治理後才可成為 training/evaluation label。
- **E-SIM-006**：應提供 index rebuild、incremental update、rollback、staleness 與 coverage dashboard。

### 4.2 Design Review

- **E-REV-001**：Rule Profile 依 product/customer/material/effective date 選擇；選擇邏輯可稽核。
- **E-REV-002**：Rule authoring、technical review、approval、publish、exception、retire 採職責分離。
- **E-REV-003**：Violation 可連結幾何位置、量測方法、tolerance、rule reference 與可視化證據。
- **E-REV-004**：不同 CAD revision 的 review 應提供 added/resolved/unchanged violation diff。
- **E-REV-005**：Waiver 需 scope、reason、approver、expiry；新 revision 不得自動繼承，除非 policy 明確允許。

### 4.3 Process and Trial

- **E-TRI-001**：應接入 MES/QMS/Trial log 的 batch、machine、mold、material lot、parameter、defect、image、action、outcome。
- **E-TRI-002**：單位與欄位需正規化但保存原始值；時間需明確 timezone、event time 與 ingestion time。
- **E-TRI-003**：Root-cause ranking 應顯示 evidence lane：similar cases、rule、CAE、geometry、ML；不得將機率解讀為因果證明。
- **E-TRI-004**：Parameter recommendation 需上下限、machine/mold applicability、safety policy、expected impact 與 approval；預設只讀建議。
- **E-TRI-005**：任何回寫 MES 或下發設備屬獨立重大 Capability，需雙重確認、change ticket、rollback 及安全評估。

### 4.4 CAE/Moldflow

- **E-CAE-001**：優先使用授權允許的 API／原始 Result connector；PDF、報告與 screenshot 僅作降級入口。
- **E-CAE-002**：應保存 solver/version/material model/mesh/process settings/unit system，無法對齊時禁止直接比較。
- **E-CAE-003**：支援 fill、pack、cool、warp 及公司核准結果類型；各 metric 有 schema、valid range、location 與 quality flag。
- **E-CAE-004**：Result interpretation 必須分離 parsed fact、rule finding、model inference 與 LLM narrative。
- **E-CAE-005**：參數最佳化需定義 objective、constraints、simulation budget、feasible domain 與工程師批准。

### 4.5 Machine UI to Excel

- **E-XLS-001**：應以 HMI Profile 管理廠牌、機型、語言、畫面、欄位座標、單位與 validation rules。
- **E-XLS-002**：輸出值需保留 OCR raw text、normalized value、confidence、bounding region、image hash 與 reviewer correction。
- **E-XLS-003**：Excel template 應版本化；資料擷取與 1:1 layout reconstruction 為不同 Capability/SLA。
- **E-XLS-004**：敏感照片依資料分級與保留政策處理，不得未經核准送往 Cloud vision provider。

### 4.6 Knowledge/RAG

- **E-KNW-001**：Connector 支援文件管理系統、PDM/PLM、SharePoint/File Server 等核准來源，繼承原始 ACL 或映射為平台 policy。
- **E-KNW-002**：Chunk 保存 source artifact/version/page/section/effective date/classification；obsolete source 預設不作權威答案。
- **E-KNW-003**：回答至少提供 citation、來源有效性、retrieval time；無足夠證據時拒絕下結論。
- **E-KNW-004**：結構化 Case 與文件 RAG 可融合，但每個 claim 的 evidence type 應可區分。
- **E-KNW-005**：建立 prompt injection、malicious document、hidden text、ACL leakage 的 ingestion 與 runtime 防護。

### 4.7 Quotation and maintenance

- **E-QUO-001**：報價模型使用歷史相似案、mold size/weight/material/cavity/complexity/slider/lifter/cooling/cost；輸出區間、driver、reference case 與資料日期。
- **E-QUO-002**：不得將預估自動視為正式報價；需商務核准及匯率／成本版本。
- **E-MNT-001**：維修預測需 shot count、repair history、failure mode、component、material、operating condition 與 censoring 定義。
- **E-MNT-002**：資料不足時只提供履歷與 rule-based due list，不強行輸出故障機率。

## 5. Assistant、MCP 與 LLM 企業需求

- **E-AST-001**：Assistant 應遵守 UI Context 最小化、permission re-check、tool allowlist 與 tenant-bound session。
- **E-AST-002**：Prompt/response log 是否保存依資料分級；預設稽核保存 metadata 與 tool evidence，不保存完整敏感 prompt。
- **E-AST-003**：LLM routing policy 可依 confidentiality、capability、cost、latency、region、modality 選擇 provider。
- **E-AST-004**：Confidential/Restricted data 不得傳送到未核准 provider；敏感欄位先 redaction/tokenization。
- **E-MCP-001**：MCP Gateway 對 tool name/schema/version 建立 backward compatibility 與 deprecation policy。
- **E-MCP-002**：Read/write/destructive tools 有不同 approval 與 scope；write action 須 server-side authorization，不信任 client annotation。
- **E-MCP-003**：MCP result 只包含完成目前任務所需資料，避免把大型 CAD metadata 或其他客戶資訊交給模型。
- **E-MCP-004**：支援 enterprise OAuth/OIDC、token audience、scope、expiry、revocation 與 per-tool policy。

## 6. Job、可用性與營運需求

- **E-JOB-001**：Queue 按 tenant/project/resource/priority 進行公平排程與 quota，防止單一大型工作耗盡資源。
- **E-JOB-002**：Job state 至少為 queued/running/succeeded/failed/cancel_requested/cancelled/expired；所有轉移可稽核。
- **E-JOB-003**：At-least-once delivery 下 handler 需 idempotent；相同 idempotency key 不重複建立業務結果。
- **E-REL-001**：依企業風險訂定 Web/API、Search、Queue、Connector 的 SLO、RTO、RPO；不得將單機 Demo 指標當 SLA。
- **E-REL-002**：備份須定期 restore test；Object、DB、Vector index 與 Model/Rule artifacts 有一致恢復點策略。
- **E-OBS-001**：Metrics、logs、traces、audit 分離；支援 SIEM/APM、alert、runbook 與 incident ticket。
- **E-OPS-001**：支援 blue/green 或 canary、schema migration、rollback、feature flag 與 emergency kill switch。

## 7. 安全與治理需求

- **E-SEC-001**：完成 threat model，涵蓋檔案解析、prompt injection、SSRF、MCP tool abuse、supply chain、GPU/worker isolation 與 data exfiltration。
- **E-SEC-002**：所有傳輸 TLS、敏感儲存加密、secret 由集中式管理；禁止 hard-coded keys。
- **E-SEC-003**：Upload 採 content sniffing、size/page/entity limit、malware scan、quarantine、sandboxed parser 與 timeout。
- **E-SEC-004**：不可逆、高風險或外部系統 write 操作要求人類確認；確認內容列明目標、影響與參數。
- **E-GOV-001**：每個 model/rule/dataset/capability 有 owner、用途、限制、評估、核准、監控、變更與退役紀錄。
- **E-GOV-002**：訓練與評估資料應有使用權、同意、保留與跨境處理記錄。

## 8. Enterprise 非功能基線

以下需在 sizing 後填值：

- Availability：`[TBD by service tier]`。
- Search p95/p99：按 1M case、filter selectivity、warm/cold index 定義。
- Concurrent users/jobs：按 Site/BU/shift 定義。
- RTO/RPO：按 metadata、artifact、audit、vector index 分開定義。
- Data residency：按客戶與法規定義。
- Retention：raw prompt、artifact、job log、audit event、feedback 各自定義。

## 9. Enterprise 驗收出口條件

- 兩個以上公司 Connector 完成 reconciliation、ACL mapping 與增量同步。
- Golden Dataset 指標達業務核准門檻，並完成 shadow/pilot。
- 具備 SSO、最小權限、Audit/Lineage、備份還原、DR 演練與安全測試證據。
- 至少一個 Capability 通過完整 lifecycle：draft → shadow → approved → monitored。
- 生產 Runbook、Owner、On-call、SLO、incident 與 rollback 流程完成簽核。
