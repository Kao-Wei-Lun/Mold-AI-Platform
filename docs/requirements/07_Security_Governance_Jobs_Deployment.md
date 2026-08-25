# 07 — 安全、權限、稽核、Lineage、Job/Worker 與部署

## 1. 安全目標

保護公司與客戶工程資料、避免跨範圍搜尋洩漏、阻止惡意檔案與 prompt injection 濫用工具，並讓每個結果與人類決策可稽核、可還原、可撤銷。

## 2. 資料分類與信任邊界

建議分類：Public、Internal、Confidential、Restricted。每筆 Artifact/Entity/Chunk/Feature/Result 繼承或提高分類，不得自行降低。

主要邊界：Internet→Gateway、Browser→API、ChatGPT/MCP Client→MCP Gateway、Gateway→Domain service、Worker→Storage、Connector→Company system、Platform→LLM provider。

- **SEC-001**：每一邊界採明確 authentication、authorization、TLS、input validation、rate limit 與 audit。
- **SEC-002**：Server-side policy 是權威；UI 隱藏按鈕或 MCP annotation 不等同權限控制。
- **SEC-003**：LLM、外部文件、CAD metadata、OCR 與 Tool result 全部視為不受信任輸入。

## 3. 權限模型

### 3.1 RBAC + ABAC

角色提供操作集合；Attributes 決定資料範圍。Policy evaluation 至少考慮 actor/group、tenant、business unit、customer、supplier、project、classification、purpose、action、resource lifecycle。

### 3.2 Retrieval enforcement

1. Resolve actor policy scope。
2. 將 scope 轉為 DB/vector/search native filter。
3. 候選生成前套用 filter。
4. Domain service 對取得的 entity 再驗權。
5. 傳往 LLM/MCP 前做 data minimization/redaction。

禁止在全域向量 Top K 後才刪除未授權結果，因為 ranking、timing 或摘要仍可能洩漏存在性。

### 3.3 Action permission

`read`, `create_job`, `export`, `annotate`, `review`, `approve`, `waive`, `admin`, `external_write`, `delete` 分離。Review requestor 與 approver 宜職責分離。

## 4. 稽核

### 4.1 Audit event

記錄 actor/service、action、target、tenant/scope、timestamp、request/correlation ID、client type、decision、policy version、before/after reference、approval、reason、result/error。

- **AUD-001**：登入、權限拒絕、搜尋、敏感 artifact 讀取／下載、MCP tool、LLM provider call、rule/model publish、waiver、export、刪除都須稽核。
- **AUD-002**：Audit append-only、restricted write、可送 SIEM；一般 app admin 不得修改。
- **AUD-003**：不在 audit 保存 secrets；raw prompt/response 依分類與保留政策，預設只保存 hash/metadata/tool evidence。
- **AUD-004**：Audit clock 使用同步時間，跨服務具 correlation/trace ID。

## 5. Lineage

每個結果顯示「由何資料、何版本、何規則／模型、何次執行、何人核准」產生。Lineage 詳細 contract 見 04。

- 原始檔 hash、parser/extractor、feature/model/index/rule profile、prompt template（若影響結果）、provider/model snapshot、job execution。
- Human feedback、waiver、review、export 作為追加 node/edge，不覆寫模型結果。
- UI 與報告提供可讀 lineage summary；Auditor 可檢視完整 graph。

## 6. File and parser security

- 副檔名、MIME/content sniffing、magic bytes 一致性。
- 每類檔案 size/entity/page/decompression limits，防 zip bomb 與極端 CAD。
- Malware scan、quarantine、sandboxed parser、read-only volume、non-root container、CPU/RAM/time limit。
- Parser 禁止任意外連；暫存檔使用專用 task directory 並清理。
- 原始檔與衍生物分 bucket/prefix；download 使用短效 signed URL 或授權 streaming。
- 解析失敗不自動嘗試不受控外部服務。

## 7. LLM/MCP 安全

依 OpenAI 官方 Plugin 安全原則落實最小權限、明確同意、深度防禦、Server-side validation、不可逆操作人類確認、PII log redaction。[Security & Privacy](https://developers.openai.com/plugins/guides/security-privacy)

- Tool schema 使用 strict validation；未知欄位拒絕或明確處理。
- OAuth token 不放入模型上下文、component props、URL query 或 log。
- UI resource/widget 視為低信任 client；CSP、allowed domains、no privileged browser API。
- MCP server 僅回目前任務需要的 structured content；大檔以 secure reference/deep link。
- 對 prompt injection、tool injection、cross-tenant IDOR、SSRF、over-broad OAuth scope 建立測試。

## 8. Job/Worker/Queue

### 8.1 Worker pools

- `cpu-general`：metadata、報告、一般轉換。
- `cad`：CAD parse、geometry、mesh。
- `gpu`：embedding、vision、local inference。
- `cae`：solver/result parsing 或受控 simulation。
- `excel`：OCR 後處理與 workbook export。
- `connector`：來源同步與 reconciliation。

Demo 可在一台 host 以不同 queue/container 表示；Enterprise 可獨立擴展。

### 8.2 Job state machine

```text
queued → running → succeeded
   │        ├────→ failed → retry_wait → queued
   │        └────→ cancel_requested → cancelled
   └─────────────→ cancelled / expired
```

- **JOB-001**：狀態轉移原子化並記 audit；worker heartbeat 與 stale detection。
- **JOB-002**：Handler 使用 immutable input snapshot、idempotency key、deterministic output key。
- **JOB-003**：只對 transient error 重試；validation/permission/data error 不重試。
- **JOB-004**：Poison job 進 dead-letter queue，附分類錯誤與人工處理流程。
- **JOB-005**：取消為 cooperative；已完成不可假裝取消，僅可刪除／隱藏依 policy。
- **JOB-006**：Progress 以 stage + bounded percentage；不得回退或偽造精確值。

### 8.3 Scheduling

Priority、resource class、tenant quota、project quota、GPU memory requirement、deadline。Enterprise 採 fair scheduling 與 backpressure；API 在容量不足時明確拒絕／排隊，不無限接受。

### 8.4 Retry and timeout

- CAD/CAE/LLM/OCR 各有不同 timeout 與 max attempts。
- External provider 429/5xx bounded exponential backoff + jitter。
- Job deadline 超時後中止下游，釋放 GPU/temporary storage。
- Side effect 必須以 outbox/transaction pattern 或 idempotent external key 防重複。

## 9. 可觀測性

### 9.1 Metrics

- Request rate/error/latency、queue depth/wait time、worker utilization、GPU VRAM/temperature、DB/vector latency。
- Parse/feature/index success、model/rule distribution、LLM usage/cost/fallback。
- AI quality telemetry：feedback、abstention、drift、slice performance。

### 9.2 Logs and traces

Structured logs 含 trace/correlation/job ID、service/version、event、duration、error code，不含 secrets/raw sensitive payload。Distributed trace 串接 Web→API→Queue→Worker→Provider。

### 9.3 Alerts

Queue backlog、stale job、provider failure、error budget burn、ACL denial anomaly、large export、unexpected egress、disk/VRAM pressure、backup failure、index staleness。

## 10. Demo 部署規格

### 10.1 Containers

建議服務：`reverse-proxy`, `web`, `api`, `assistant`, `mcp`, `worker-cad`, `worker-ai`, `postgres`, `qdrant`, `redis`, optional `minio`。同一 codebase 可共享 image，但 runtime role 與 permission 分開。

### 10.2 Windows host

- Docker Desktop 使用 WSL2 backend；NVIDIA 驅動與 container runtime 經 smoke test。
- 專案資料、DB、object volumes 放在明確的 NVMe 路徑並定期備份。
- Windows Firewall 僅開 reverse proxy 必要埠；DB/Redis/Qdrant 只在 private Docker network。
- API keys 使用 `.env` 的本機非版控檔或 Docker secrets 等機制；提供 `.env.example` 無真實值。
- Demo 外部 endpoint 具 TLS、登入、Rate limit、IP/geo policy（若可）、一鍵停用。

### 10.3 Demo resource controls

- Worker concurrency 預設 CAD=1、GPU=1–2、general=2，依 VRAM/RAM 基準調整。
- 設 upload/file/data size、job queue、LLM cost budget。
- 啟動前 health/preflight：disk、GPU、DB、vector、queue、provider、MCP endpoint、ChatGPT account capability。

### 10.4 Backup and reset

- Seed data、DB dump、object manifest、vector rebuild manifest 分開。
- 提供 documented reset：停止服務、還原 seed DB/objects、重建 index、清除 transient queue；不得刪除 repo 或任意 host folder。

## 11. Enterprise 部署規格

- Linux container platform/Kubernetes 或公司核准 orchestrator；Infrastructure as Code。
- Separate namespaces/accounts、network policy、private registry、image signing/SBOM/vulnerability scan。
- API/MCP stateless replicas；worker autoscaling 依 queue/resource；GPU node pool。
- Managed/HA PostgreSQL、object storage、cache/queue；vector store replication/backup 按產品能力。
- Private connectors、egress allowlist、KMS/secrets、WAF/API gateway、SIEM/APM。
- Dev/Test/UAT/Prod 分離；production data 禁止複製到非生產，除非去識別與核准。

## 12. CI/CD 與供應鏈

- Pull request review、unit/contract/security/eval tests、dependency/license scan。
- Container 固定 digest、產生 SBOM、簽章、部署前政策驗證。
- DB/event/schema/model/rule migration 均有 compatibility check 與 rollback。
- Secret scanning、禁止 LLM key/CAD/customer data commit。
- 發佈產生 release manifest：code、container、schema、model、rule、prompt、index compatibility。

## 13. Incident and recovery

事件類型：資料外洩、錯誤權限、惡意檔、模型失控、錯誤規則、Provider outage、資料損毀、Queue/GPU exhaustion。

每類建立 detect、contain、kill switch、evidence preservation、notify、recover、postmortem。重大錯誤規則／模型需能立即停用版本並將受影響結果標記需重評。
