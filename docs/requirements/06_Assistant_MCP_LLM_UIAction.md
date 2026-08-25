# 06 — Embedded Assistant、MCP、LLM Provider 與 UI Action Protocol

## 1. 產品原則

`Embedded Engineering Assistant`／`Mold AI Assistant` 是 UI 功能與 Agent 角色，不是特定模型品牌。專用 UI、ChatGPT Web 及未來其他 MCP Client 共用 Capability API；差異只在 Context 注入、呈現與互動協議。

Assistant 應能理解目前工程上下文並操作受控工具，但不能繞過 Domain validation、權限、人工核准或把 LLM 回覆當成工程事實。

## 2. Embedded Assistant 體驗

### 2.1 UI 功能

- Chat：自然語言提問與追問。
- Suggested Actions：依頁面、選取物與結果提供有限建議。
- Explain：解釋排名、規則、CAE finding、trial recommendation。
- Analyze：建立非同步 Capability job。
- Execute：呼叫工具；write/high-risk action 先顯示確認卡。
- Evidence：展開來源、量測、版本、citation 與 Lineage。
- Open in context：以 UI Action 導航、選取 Face、開啟 Compare 或 Job。

### 2.2 Context Envelope

前端不直接把整個頁面資料或 CAD 塞進 prompt，而傳送 references：

```json
{
  "context_version": "1.0",
  "page": "similarity_search",
  "project_id": "...",
  "query_mold_id": "NEW-001",
  "query_revision_id": "...",
  "selected_mold_id": "A123",
  "search_job_id": "...",
  "selected_geometry_refs": [],
  "visible_result_refs": ["..."],
  "ui_locale": "zh-TW"
}
```

- **AST-CTX-001**：Context 只包含必要 ID、UI state 與使用者明確選取內容。
- **AST-CTX-002**：Backend 需重新查詢資料與驗證權限；不得信任前端傳來的 tenant、permission 或 object metadata。
- **AST-CTX-003**：Context 有 TTL、session/user binding；切換專案或登出立即失效。
- **AST-CTX-004**：使用者可查看「Assistant 目前知道什麼」並清除 Context。

### 2.3 Answer Contract

回覆應分層：

- `summary`：簡短工程結論。
- `facts`：來源資料與計算結果。
- `interpretation`：規則／模型支持的解讀。
- `recommendations`：建議、條件與核准需求。
- `uncertainties`：資料缺口、不可比或低信心。
- `evidence_refs`：可點擊來源。
- `ui_actions`：安全的頁面互動提案。

不得隱藏 evidence 不足；不得在 citation 不存在時偽造引用。

## 3. Assistant Orchestration

### 3.1 執行流程

1. Normalize input，套用 user/tenant policy。
2. Resolve UI Context refs，僅取得授權且必要的資料。
3. 列出當前可用 tools；依 capability、role、classification allowlist。
4. LLM 產生 tool plan 或直接回答一般問題。
5. Policy Engine 驗證 tool、schema、resource、approval、rate limit。
6. 執行 read tool 或建立 async job。
7. 驗證 tool result schema，裁切／redact 後才送回 LLM。
8. 產生 evidence-backed answer；前端驗證 UI Action allowlist。
9. 記錄 metadata、tool calls、versions、approval、result/lineage。

### 3.2 Tool risk levels

- R0：公開／無敏感資料之 read。
- R1：受權限保護 read、建立純分析 Job。
- R2：建立／修改平台記錄、匯出敏感檔案、送審。
- R3：刪除、覆寫核准狀態、外部系統 write、機台/MES 動作。

R2 必須顯示明確確認；R3 預設不開放 Demo，Enterprise 需獨立安全評審、雙重核准與 rollback。

### 3.3 Prompt injection boundary

- CAD metadata、OCR text、文件、MCP result 皆視為 untrusted data。
- 文件內如「忽略規則」「呼叫刪除」不得改變 system/tool policy。
- Tool description 不包含 secrets；tool arguments 由 server schema 驗證。
- Assistant 不可任意讀 URL、內網位址或檔案路徑；僅接受已註冊 artifact references。

## 4. MCP Gateway

### 4.1 定位

MCP Gateway 將內部 Capability 映射為適合 AI Client 的 focused tools。它不是另一套 Domain Backend，也不直接連 DB。所有工具經相同 AuthZ、Job、Audit、Lineage 與 schema validation。

### 4.2 Tool design

- 一個 tool 對應一個明確 user goal，例如 `search_similar_molds`、`get_similarity_explanation`、`run_design_review`、`get_job_status`。
- 名稱與 schema 版本穩定；破壞性變更建立新 major tool/schema。
- 結果同時提供精簡 `content` 與 `structuredContent`；無 UI 時仍可完成任務。
- 長任務只回 `job_id`、初始狀態與 deep link。
- 正確填寫 read-only／destructive 等 annotation，但 server 不以 client annotation 取代授權。

### 4.3 Demo tool catalog

| Tool | Risk | 同步 | 說明 |
|---|---:|---:|---|
| `list_demo_molds` | R0/R1 | 是 | 依可見 scope 列出案例 |
| `get_mold_summary` | R1 | 是 | 取得最小摘要與 artifact refs |
| `search_similar_molds` | R1 | 建 Job | 啟動相似搜尋 |
| `get_similarity_results` | R1 | 是 | 讀取已完成結果 |
| `get_similarity_explanation` | R1 | 是 | 取得分數與差異證據 |
| `run_design_review` | R1 | 建 Job | 啟動 review |
| `get_review_results` | R1 | 是 | 讀取 violations |
| `search_knowledge` | R1 | 是 | 有 citation 的檢索 |
| `get_job_status` | R1 | 是 | 查詢進度與錯誤 |

### 4.4 Transport and auth

- Production-style MCP endpoint 使用 HTTPS + Streamable HTTP，路徑建議 `/mcp`。
- Demo 可使用官方 Secure MCP Tunnel（若帳號／Workspace 支援）或受控 HTTPS forwarding；現場前須預檢。
- Private data/write tools 使用 OAuth 2.1/OIDC compatible flow、短效 token、audience/scope validation。
- 無認證的 public demo tool 只能回傳已核准公開資料，並設 Rate limit、captcha/abuse 防護（若公開）。

### 4.5 Current OpenAI capability boundary

依 2026-08-25 官方文件：Plugin 可包含 Skills、MCP Server 與選用 UI；MCP 可提供 tools/resources/prompts/instructions，且結果應在沒有自訂 UI 時也可用。ChatGPT Developer Mode 能否使用取決於帳號與 Workspace Policy；連線需公開 HTTPS endpoint 或官方 Secure MCP Tunnel。故系統規格以「capability detection + preflight」取代永久假設。

官方來源：

- [Plugin architecture](https://developers.openai.com/plugins/concepts/plugins)
- [MCP server](https://developers.openai.com/plugins/concepts/mcp-server)
- [Build an MCP server](https://developers.openai.com/plugins/build/mcp-server)
- [Connect and test your plugin](https://developers.openai.com/plugins/deploy/connect-chatgpt)

## 5. LLM Provider Abstraction

### 5.1 Provider interface

```text
LLMProvider
├─ generate(messages, response_schema, policy)
├─ plan_tools(messages, tool_schemas, policy)
├─ summarize(evidence, response_schema)
├─ embed(inputs, embedding_profile)          [optional]
├─ vision(inputs, response_schema)           [optional]
├─ health()
└─ usage()
```

Provider adapter 負責 API shape、streaming、tool-call、structured output、error、retry、usage mapping；Domain service 不應使用 provider-specific response objects。

### 5.2 Model capability profile

Registry 不以品牌名稱推測能力，實際記錄：text、vision、structured output、tool calling、context limit、data policy、region、latency class、cost class、approved classifications、snapshot/version。

### 5.3 Routing policy

輸入：capability、classification、modality、latency target、cost budget、required features、tenant policy。輸出：provider/model/fallback chain。

範例：

- Public Demo complex assistant → approved cloud model。
- Confidential document summary → company internal model only。
- Simple classification → local small model 或 deterministic logic。
- Geometry/Rule judgement → no LLM。

### 5.4 Failure and fallback

- Timeout/429/5xx 使用 bounded exponential backoff；避免放大重試。
- Provider circuit breaker；降級到 alternative provider/local 或回傳「Assistant 暫不可用」。
- Fallback 不得降低資料 policy，例如 Restricted 不可落到未核准 cloud。
- Provider change 需重新跑 regression/eval；不可只因 API 相容就視為行為相同。

### 5.5 Cost and retention

保存 token/latency/cost metadata、cache hit、provider/model version；敏感 prompt/response 是否保存依 policy。預設不將公司資料用於 provider training，實際條款由採購／法務確認。

## 6. UI Action Protocol

### 6.1 目的

Assistant 可建議 UI 操作，但前端只執行版本化 allowlist action，不執行任意 JavaScript、URL 或 DOM selector。

### 6.2 Action envelope

```json
{
  "protocol_version": "1.0",
  "action_id": "uuid",
  "type": "viewer.highlight_geometry",
  "target": {
    "artifact_version_id": "uuid",
    "geometry_refs": ["face:235"]
  },
  "parameters": {"color": "warning"},
  "preconditions": [{"type": "page", "equals": "design_review"}],
  "requires_confirmation": false,
  "expires_at": "RFC3339",
  "evidence_refs": ["violation:uuid"]
}
```

### 6.3 Allowlist

- `navigation.open_entity`
- `navigation.open_job`
- `viewer.highlight_geometry`
- `viewer.set_standard_view`
- `viewer.compare_side_by_side`
- `viewer.toggle_overlay`
- `results.apply_filter`
- `results.select_item`
- `review.open_violation`
- `assistant.show_evidence`
- `export.prepare`（只準備，不自動下載敏感檔）

禁止：任意 URL、shell、script、clipboard、secret read、直接 approve/waive/delete、任意外部 write。

### 6.4 Validation

- Frontend 驗證 protocol version、action type、target existence、page precondition、expiry。
- Backend 簽發 action 前驗證權限；前端執行時可再次向 backend resolve secure target。
- Action 失敗回傳 typed error，不讓 LLM 猜測已成功。
- 所有需要確認的 action 顯示人類可讀 target、effect、evidence 與取消選項。

## 7. Assistant/MCP 驗證指標

- Tool selection accuracy、argument schema validity、completion rate。
- Grounded answer/citation precision、unsupported claim rate。
- Context resolution accuracy、cross-project leakage = 0。
- Unsafe tool execution = 0；approval bypass = 0。
- P95 first-token、end-to-end latency、provider error/fallback rate。
- User correction、abstention quality、deep-link success。
- 每次 prompt/tool/model/schema 更新皆跑固定 adversarial + domain eval set。
