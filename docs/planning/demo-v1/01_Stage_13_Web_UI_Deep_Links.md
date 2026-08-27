# Stage 13 — Valid Web UI Deep Links

- 狀態：Implemented；production deployment 與 ChatGPT external UAT 待本階段 release gate 完成
- 優先級：P0
- 前置：Stage 12、私人 Sites、HTTPS Quick Tunnel、Secure MCP Tunnel 已可運作
- 出口：ChatGPT MCP 回覆可安全開啟正確 Engineering Web context

## 1. 問題定義

MCP Gateway 目前以 `PUBLIC_WEB_BASE_URL=https://dynamic-quick-tunnel.invalid` 建立 links。
Domain result 正確，但 link 無法開啟。Quick Tunnel URL 在容器啟動後才產生，且重新建立後可能改變；
因此不能在 image build 時寫死，也不能要求每次 MCP metadata 變更後重建 ChatGPT connection。

Deep link 不是一般首頁連結。它必須把使用者帶到特定工程 context，例如：

- 某一個 Similarity Search 與 selected candidate。
- 某一個 Design Review 與 finding。
- 某一個 Job 的狀態。
- 某一次 Knowledge Search 與 citation。
- 某一次 Process/Trial Search 與 selected case。

Deep link 只傳遞 identifier，不傳遞 domain object、permission claim 或 secret。完整資料由 Web API
重新讀取並執行 server-side authorization。

## 2. 建議架構決策

採用「穩定 Sites Entry + 動態 Workspace Origin」兩層設計：

```text
ChatGPT MCP result
  -> stable owner-only Sites URL /open?...context refs...
  -> Sites validates target allowlist
  -> Sites reads current Quick Tunnel URL and Demo token from sessionStorage
  -> opens dynamic Engineering Web URL with context refs
  -> Web consumes token through the existing fragment handoff
  -> Web removes token fragment immediately
  -> Web reloads domain records from API
```

不直接讓 MCP Gateway 回傳 Quick Tunnel URL，理由如下：

- Quick Tunnel URL 會變動，但 Sites URL 穩定。
- MCP 不應取得或回傳 Demo bearer token。
- 使用者已在 Sites 中建立私人 session，可重用既有 connection information。
- ChatGPT connector metadata 不必因 Web origin 變動而重新整理。

若 Sites session 尚未設定目前 Tunnel URL／token，`/open` 應顯示設定畫面與待開啟目標，使用者完成
連線檢查後再繼續，不得丟失 context。

## 3. Requirements

### 3.1 Link generation

- **DL-001**：所有 MCP `links.ui` 必須使用設定的穩定 HTTPS Sites entry base URL。
- **DL-002**：未設定、非 HTTPS、`.invalid`、localhost 或包含 credential 的 entry URL，release preflight 必須失敗。
- **DL-003**：MCP links 僅包含 allowlisted target 與最小 identifier；不得包含 API token、Tunnel key、模型 prompt、完整 evidence 或使用者 permission。
- **DL-004**：所有 link 使用 versioned contract，例如 `deep_link_version=1.0`。
- **DL-005**：Domain ID 必須使用 canonical UUID；錯誤格式不得生成可執行 redirect。
- **DL-006**：Link summary 與 target 必須一致；Knowledge 結果不得連到 Process，Similarity candidate 不得連到不同 search。

### 3.2 Stable Sites entry

- **DL-010**：Sites 提供 `/open` route 或等價 dispatcher，解析 allowlisted query parameters。
- **DL-011**：只允許內建 Engineering Web target；不得接受任意 `return_url`、scheme、hostname 或 JavaScript URL。
- **DL-012**：Sites session 無有效 Workspace URL 時，顯示 connection setup，不自動前往未知 origin。
- **DL-013**：Workspace URL 必須是 HTTPS，且通過現有 reachability／system identity check。
- **DL-014**：Demo token 只存在 `sessionStorage`；不得放入 query string、server log、analytics 或 MCP response。
- **DL-015**：Sites 開啟 Workspace 時沿用既有 fragment token handoff，Workspace 取得後立即清除 fragment。
- **DL-016**：使用者取消或 connection test 失敗時保留待開啟 target，並提供安全重試。

### 3.3 Engineering Web resolution

- **DL-020**：Web 啟動時解析 query/hash，驗證 version、target 與 ID，再載入對應 workspace。
- **DL-021**：Web 必須透過 API 重新取得 record；不得信任 link 中的名稱、分數、狀態或 ACL。
- **DL-022**：Record 不存在、未完成、過期或無權限時顯示 typed UI state，不得透露其他 scope 是否存在。
- **DL-023**：已成功定位後，URL 可保留非敏感 context refs，支援 refresh/back/forward。
- **DL-024**：Context 與頁面不相容時拒絕；不得讓 `candidate_id` 在另一個 `search_id` 中被選取。
- **DL-025**：Deep link loading 不得自動執行新的 write/job action。

### 3.4 Observability and compatibility

- **DL-030**：記錄 `deep_link.opened`、`resolved`、`failed` 的安全 metadata；不記 token。
- **DL-031**：事件至少包含 contract version、target type、correlation ID、result status 與 latency。
- **DL-032**：未知 future version 顯示 upgrade-required，不以 best effort 執行。
- **DL-033**：MCP link contract change 必須有 backward compatibility test。
- **DL-034**：Demo Status 顯示 `deep_link_ready`、entry origin 類型及最後一次 Sites connection check；不得回傳 token。

## 4. Deep Link Contract 1.0

建議穩定 entry：

```text
https://<owner-sites-domain>/open?deep_link_version=1.0&target=similarity&search_id=<uuid>&candidate_id=<uuid>
```

允許的 target：

| Target | Required refs | Optional refs | Web destination |
|---|---|---|---|
| `home` | 無 | 無 | Dashboard |
| `job` | `job_id` | 無 | Job drawer／workspace status |
| `similarity` | `search_id` | `candidate_id` | Similarity result and comparison |
| `design_review` | `review_id` | `finding_id` | Review findings/evidence |
| `knowledge` | `knowledge_search_id` | `citation_id` | Knowledge results/source evidence |
| `process_trial` | `process_search_id` | `case_id` | Process results/case evidence |
| `cae` | `cae_comparison_id` | `metric_code` | CAE comparison/evidence |
| `hmi` | `hmi_extraction_id` | 無 | Extraction/review/export |

雖然目前 MCP 只對其中部分 target 產生 link，contract 先保留所有已實作 Web module，避免 Stage 17
再建立第二種路由格式。

禁止欄位：

```text
token
api_key
tunnel_id
workspace_url
return_url
javascript
permission
classification override
serialized domain result
```

## 5. Component changes

### 5.1 MCP Gateway

- 將 `PUBLIC_WEB_BASE_URL` 拆分為明確的 `PUBLIC_WEB_ENTRY_BASE_URL`。
- 建立單一 `DeepLinkBuilder`，禁止各 tool 自行拼接 URL。
- Builder 驗證 target/ref schema、HTTPS origin 與禁止資訊。
- 更新 9 tools 的 link contract tests。
- Preflight 報告 entry URL readiness，不報動態 Workspace URL。

### 5.2 Sites

- 新增 `/open` dispatcher page。
- 抽出 versioned deep-link parser 與 target allowlist。
- 將 pending target 存於 sessionStorage，通過 connection test 後繼續。
- 使用現有 Workspace launch fragment handoff，不建立第二份 token storage。
- 顯示 target 摘要，例如「開啟 Similarity Search」，但不偽造尚未載入的 domain metadata。

### 5.3 Engineering Web

- 建立 `DeepLinkContext` parser，不讓每個 component 分別解析 location。
- App shell 根據 target 切換 module，再把 validated refs 傳給 workspace。
- 各 workspace 支援 `load by ID`、loading、not found、forbidden、not ready。
- 避免 mount 時重複建立 Search/Review；deep link 永遠是 read/resume。
- 完成後用 replaceState 清除一次性 token fragment，但保留非敏感 refs。

### 5.4 Operations

- `.env.sites-demo.example` 增加穩定 Sites entry 設定，不存真實 token。
- `sites-demo-start.ps1` 驗證 Sites entry 與 Workspace tunnel 是兩條不同 URL。
- `demo-status.ps1` 顯示 entry readiness、Workspace reachability、MCP tool count。
- 文件說明 Quick Tunnel 改變不需要 refresh MCP metadata。

## 6. Error model

| Code | Condition | User behavior |
|---|---|---|
| `DEEP_LINK_VERSION_UNSUPPORTED` | 未知 contract version | 更新 client／重新取得 link |
| `DEEP_LINK_TARGET_INVALID` | 非 allowlisted target | 停止，不 redirect |
| `DEEP_LINK_REF_INVALID` | UUID／required ref 錯誤 | 顯示安全錯誤 |
| `WORKSPACE_CONNECTION_REQUIRED` | Sites 尚未設定目前 Workspace | 顯示 setup 並保留 target |
| `WORKSPACE_IDENTITY_MISMATCH` | Tunnel 非 Mold AI Platform | 阻止開啟 |
| `DEEP_LINK_RECORD_NOT_FOUND` | API 找不到或不允許揭露 | 回到 module 並顯示泛化訊息 |
| `DEEP_LINK_RECORD_NOT_READY` | Job/result 尚未完成 | 顯示狀態，可人工 refresh |
| `DEEP_LINK_CONTEXT_MISMATCH` | candidate/finding 不屬於 parent | 不選取 target，記錄安全事件 |

## 7. Test plan

### 7.1 Unit

- 每種 target 的 valid/invalid parser cases。
- URL encoding、duplicate params、unknown params、overlong values。
- `javascript:`、protocol-relative URL、foreign host、CRLF、Unicode confusable rejection。
- Builder 不包含 token/key/secret。
- candidate→search、finding→review parent relationship validation。

### 7.2 Component

- Sites session 已設定／未設定／失效三種流程。
- Connection test 成功後恢復 pending target。
- Web App 切到正確 module 並只執行 GET。
- 401、403、404、409/not-ready、network error 的 UI state。
- Browser back/forward/refresh 不重複建立 job。

### 7.3 Integration

- MCP tool response link 使用穩定 Sites origin。
- Sites 轉送至目前 Quick Tunnel。
- Web 使用 token 取得 domain result，然後清除 fragment。
- Quick Tunnel 重建後，不更新 MCP Gateway也能使用新 Workspace URL。

### 7.4 External UAT

從 ChatGPT App 逐項點擊：

1. `get_platform_status` → Dashboard。
2. `get_job_status` → 指定 Job。
3. `get_similarity_explanation` → 指定 search/candidate。
4. `search_knowledge` → 指定 Knowledge result/citation。
5. `search_process_trial_cases` → 指定 Process result/case。

每次記錄：MCP tool、link、Sites target、Workspace origin、API status、最終 module、selected record、耗時。
Evidence 必須遮蔽 token 與個人敏感資料。

## 8. Acceptance criteria

- **ACC-DL-001**：所有 MCP UI links 使用穩定 HTTPS Sites origin，沒有 `.invalid`。
- **ACC-DL-002**：Quick Tunnel URL 改變後，不修改 ChatGPT connection 即可再次開啟新 Workspace。
- **ACC-DL-003**：五個外部 UAT deep links 全數抵達正確 context。
- **ACC-DL-004**：URL、browser history、server log、MCP result 均無 Demo token。
- **ACC-DL-005**：任意 redirect、malformed ID、cross-parent ID、unknown version 全數拒絕。
- **ACC-DL-006**：Deep link 只讀取既有結果，不建立新分析或 reviewer decision。
- **ACC-DL-007**：Web 與 Sites unit/build tests、backend/MCP tests、running-stack smoke 全數通過。

## 9. Rollout and rollback

Rollout：

1. 先部署 Sites `/open`，保持舊首頁入口。
2. 部署 Web parser，直接 URL 手動測試。
3. 切換 MCP `DeepLinkBuilder` 至穩定 entry。
4. Refresh ChatGPT metadata，執行 external UAT。

Rollback：

- MCP link generation 可回到 Sites 首頁，但不得回到 `.invalid` 或帶 token 的 URL。
- Sites dispatcher failure 時保留手動 Workspace launch，不影響 MCP domain result。
- Deep link 永遠是附加導航能力；失敗不得讓核心 tool call 失敗。

## 10. Suggested implementation commits

```text
feat(sites): add versioned deep-link dispatcher
feat(web): resolve validated deep-link contexts
feat(mcp): generate stable Sites entry links
test: add external deep-link acceptance coverage
docs: complete Stage 13 operator runbook
```
