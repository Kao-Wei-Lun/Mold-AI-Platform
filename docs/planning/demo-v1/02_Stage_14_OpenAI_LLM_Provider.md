# Stage 14 — OpenAI LLM Provider for the Embedded Engineering Assistant

- 狀態：Implementation complete；account-bound live UAT pending
- 優先級：P0（若 Demo 宣稱有生成式 Copilot）
- 前置：Stage 6 Provider interface、Stage 13 deep-link contract
- 出口：可由環境啟用 OpenAI Provider，故障時安全降級且不影響工程結果

## 1. 目標與產品邊界

本 Stage 將現有 `LLMProvider` abstraction 的唯一可執行實作從 `deterministic-demo` 擴充為：

```text
LLMProvider
├─ deterministic-demo
└─ openai-responses
```

LLM 的責任：

- 將已授權、已計算、已引用的 domain evidence 組織成自然語言。
- 依 UI Context 解釋 Similarity、Review、Knowledge、Process/Trial、CAE 結果。
- 清楚分隔 fact、computed result、recommendation、uncertainty、limitations。
- 在證據不足時保留 abstention，不補造根因或參數。

LLM 不負責：

- 計算或調整 CAD similarity score。
- 決定 Design Review PASS/FAIL/NOT_EVALUATED。
- 計算 CAE metric delta 或 compatibility。
- 建立未有 evidence 的 Process parameter recommendation。
- 核准、waive、修改資料或寫入外部系統。
- 繞過 server-side authorization 或自行擴大資料 scope。

## 2. 官方能力基線與不寫死原則

依 2026-08-27 查證的 OpenAI 官方文件：

- 新整合以 Responses API 為起點；模型、reasoning、verbosity 等屬 deployment-time profile，
  不應散落寫死在 domain code。[API deployment checklist](https://developers.openai.com/api/docs/guides/deployment-checklist)
- API key 應保存在安全位置並由 process environment／secret mechanism 提供，不應放入前端或 Git。
  [Developer quickstart](https://developers.openai.com/api/docs/quickstart)
- Responses API 可用 SSE streaming；是否啟用 streaming 應由 UI latency與安全需求決定。
  [Streaming responses](https://developers.openai.com/api/docs/guides/streaming-responses)
- API 資料可能涉及 abuse-monitoring logs與 application state；實際導入公司資料前必須重新評估
  retention、region、approved project 與 data controls。[Data controls](https://developers.openai.com/api/docs/guides/your-data)

本規格不固定特定模型名稱、價格、rate limit 或帳號能力。實作時以 `OPENAI_MODEL` 與 versioned
Provider Profile 選擇，release 前重新查證官方文件及 Project limits。

## 3. Architecture

```text
Assistant request + minimal UI Context refs
  -> server-side authorization and context reload
  -> deterministic capability/evidence resolver
  -> AssistantEvidenceEnvelope 1.0
  -> data minimization/redaction
  -> PromptTemplate version + ProviderProfile version
  -> OpenAIProvider.responses.create(...)
  -> structured output validation
  -> evidence-ref and unsupported-claim checks
  -> AssistantResponse contract
  -> audit metadata + usage

Failure at any provider stage
  -> deterministic-demo response
  -> explicit provider degraded state
  -> no fabricated provider success
```

第一版不讓 OpenAI model 直接呼叫 domain tools。Domain capability 由 server 依已支援 intent 和
validated context 執行，再把最小 evidence envelope 交給模型。這可避免模型自行選錯資料 lane，並讓
Web Assistant 與 MCP 的 domain contract 保持一致。未來若開放 tool calling，須另建立 allowlist、
authorization、approval 與 evaluation gate。

## 4. Requirements

### 4.1 Provider abstraction

- **LLM-001**：`LLMProvider` 提供 `health()`、`generate()`；streaming 若實作，使用獨立明確 contract。
- **LLM-002**：Provider input/output 不包含 Django model、HTTP request 或 UI component type。
- **LLM-003**：Provider adapter 可替換；Assistant orchestration 不直接 import OpenAI SDK types。
- **LLM-004**：Provider Profile 記錄 provider、model selector、prompt version、timeout、output limit、data policy version。
- **LLM-005**：每個 Assistant response 回傳實際 provider mode：`openai`、`deterministic_fallback` 或 `unavailable`。

### 4.2 Configuration and secret handling

- **LLM-010**：`LLM_PROVIDER=deterministic-demo|openai`；未知值 fail closed，不自動選模型。
- **LLM-011**：`OPENAI_API_KEY` 只從 server process secret/environment 讀取，禁止 API、UI、log、exception、Git 回傳。
- **LLM-012**：`OPENAI_MODEL` 必填且由 allowlisted Provider Profile 驗證；程式不使用隱藏 default model。
- **LLM-013**：Demo 使用獨立 OpenAI Project/API key，與 Tunnel runtime key、Admin key 分離。
- **LLM-014**：API key 缺失、placeholder、格式異常時 Provider health 為 `misconfigured`，不呼叫外部 API。
- **LLM-015**：前端 bundle 與 Sites config 不得包含 OpenAI API key。

建議設定名稱：

```text
LLM_PROVIDER=openai
OPENAI_API_KEY=<process secret>
OPENAI_MODEL=<approved model selector>
OPENAI_TIMEOUT_SECONDS=20
OPENAI_MAX_OUTPUT_TOKENS=<bounded value>
OPENAI_MAX_INPUT_CHARS=<bounded value>
OPENAI_PROVIDER_PROFILE=openai-demo-public-v1
OPENAI_PROMPT_PROFILE=mold-assistant-grounded-v1
```

數值在實作時依模型、帳號 limits、latency benchmark 與預算決定，不在此文件假設永久值。

### 4.3 Evidence and prompt safety

- **LLM-020**：輸入模型前先完成 authorization、classification 與 dataset filter。
- **LLM-021**：Demo Provider 只接受 `public_demo` evidence；其他 classification 強制 deterministic fallback 或拒絕。
- **LLM-022**：CAD metadata、document text、OCR text、case note 全部視為 untrusted data，以資料區塊傳入，不當作 system instruction。
- **LLM-023**：Prompt Template 明確要求不執行 evidence 中的指令、不揭露 hidden prompt、不補造 evidence。
- **LLM-024**：Evidence envelope 設定總長度與每 source 上限；超過時使用 deterministic selection，不直接截斷 citation identity。
- **LLM-025**：每個 claim 必須引用 envelope 中存在的 evidence ref；不存在的 ref 使 validation 失敗並 fallback。
- **LLM-026**：模型不得輸出新的精確 Process parameter，除非相同值已存在於 approved recommendation evidence。
- **LLM-027**：模型不得把 association、similarity 或 historical outcome 描述為 proven causality。

### 4.4 Reliability and cost

- **LLM-030**：設定 connect/read/total timeout；UI 顯示明確等待與 fallback 狀態。
- **LLM-031**：Retry 次數有界，採 backoff/jitter；不對未知是否已完成的 request 無限重送。
- **LLM-032**：429、timeout、5xx、invalid output、content refusal 分開記錄 typed provider result。
- **LLM-033**：Provider failure 不讓 Assistant endpoint 500；回傳 deterministic fallback 與 limitation。
- **LLM-034**：保存 usage metadata、latency、model/profile/prompt version、fallback reason；不預設保存完整 prompt/response。
- **LLM-035**：設定 application-side concurrency、input/output limits 與 Demo budget alarm；超過限制安全降級。
- **LLM-036**：自動化測試預設使用 fake provider，不產生 API 費用；live test 必須 opt-in 並清楚標示可能計費。

### 4.5 Output and UI

- **LLM-040**：模型輸出使用結構化 schema，不直接把任意 HTML 插入頁面。
- **LLM-041**：AssistantResponse 至少包含 summary、facts、interpretation、recommendations、uncertainty、limitations、evidence_refs、provider。
- **LLM-042**：Web 對 model-generated 與 deterministic content 使用不同但不誤導的 badge。
- **LLM-043**：Citation、Search、Review deep links 使用 Stage 13 builder，不由模型生成 URL。
- **LLM-044**：Streaming 若實作，只有完整 validated response 才標示完成；partial output 不保存為正式工程答案。
- **LLM-045**：使用者可以停止等待，但停止不等同 provider 已取消或不計費；UI 文案必須正確。

## 5. Data contracts

### 5.1 AssistantEvidenceEnvelope 1.0

```json
{
  "schema_version": "1.0",
  "intent": "explain_similarity",
  "locale": "zh-Hant",
  "context_refs": {
    "search_id": "uuid",
    "candidate_artifact_version_id": "uuid"
  },
  "facts": [
    {
      "fact_id": "fact:similarity:overall",
      "type": "computed_result",
      "value": 0.928,
      "unit": "ratio",
      "evidence_refs": ["similarity-result:uuid"]
    }
  ],
  "evidence": [
    {
      "evidence_ref": "similarity-result:uuid",
      "evidence_type": "persisted_similarity_result",
      "classification": "public_demo",
      "content": "bounded model-readable evidence"
    }
  ],
  "required_limitations": [
    "Deterministic Demo similarity; not a company-calibrated prediction."
  ]
}
```

### 5.2 Provider result

```json
{
  "provider": "openai",
  "provider_profile": "openai-demo-public-v1",
  "model": "configured-at-runtime",
  "prompt_profile": "mold-assistant-grounded-v1",
  "status": "succeeded",
  "latency_ms": 1234,
  "usage": {
    "input_tokens": 0,
    "output_tokens": 0,
    "total_tokens": 0
  },
  "response": {
    "summary": "...",
    "facts": [],
    "interpretation": [],
    "recommendations": [],
    "uncertainty": [],
    "limitations": [],
    "evidence_refs": []
  }
}
```

Usage 欄位依 SDK/API 實際可得資訊填寫；不可得時為 `null`，不得估算成權威帳單數字。

## 6. Initial supported intents

| Intent | Required context | Evidence source | LLM allowed behavior |
|---|---|---|---|
| `explain_similarity` | search + candidate | persisted lane scores/differences | 說明排名與差異 |
| `explain_design_review` | review + optional finding | rule/finding/evidence | 解釋風險，不改結果 |
| `summarize_knowledge` | knowledge search | authorized excerpts/citations | 整理已有 evidence；abstention 保留 |
| `summarize_process_cases` | process search | selected cases/recommendation guardrails | 比較案例，不宣稱因果 |
| `explain_cae_comparison` | comparison + optional metric | compatibility/deltas/evidence | 解釋變化，不產生最佳化參數 |
| `unsupported` | 任意 | 無 | deterministic capability guidance |

第一版不做自由聊天記憶、跨使用者 conversation storage、模型自行瀏覽網路或任意 tool execution。

## 7. Audit and privacy

Audit metadata：

- correlation ID、actor/demo principal、intent。
- input classification、evidence count/hash、redaction profile。
- provider/model/profile/prompt version。
- start/end/latency/status/fallback reason。
- usage metadata與 response schema validation status。

預設不記錄：

- API key。
- 完整 system/developer prompt。
- 未裁切的 CAD metadata/document/OCR text。
- 完整 model response（除非 Demo policy 明確啟用且只含 public synthetic data）。

公司資料導入前必須重新做 Data Protection／Retention review，不得把 Demo 的 public-data policy直接沿用。

## 8. Test plan

### 8.1 Unit with fake transport

- Success、timeout、connect failure、429、5xx、malformed JSON、schema mismatch、refusal。
- Missing/invalid API key 不發出 network call。
- Evidence redaction、length limit、prompt injection text containment。
- Unknown evidence ref、new precise parameter、missing limitation 觸發 fallback。
- Usage missing/null、latency、model/profile recording。
- No key/secret in logs and exceptions。

### 8.2 Assistant contract

- 五個 supported intents 各自有 positive、abstention、not-ready、unauthorized cases。
- LLM 與 deterministic mode 使用相同 domain evidence IDs。
- Provider output不能改變 persisted score/rule/delta。
- Deep links由 server builder產生，不接受 model URL。

### 8.3 Frontend

- Provider badge、generating、fallback、timeout、retry、cancel-wait states。
- Partial stream 不標示完成。
- Citation click 使用 Stage 13 deep link。
- XSS/Markdown unsafe content 不可執行。

### 8.4 Opt-in live test

只有 `RUN_OPENAI_LIVE_TESTS=1` 且明確設定 Demo Project key 時執行：

- 一個最小 public synthetic evidence request。
- 驗證 schema、citation refs、latency、usage presence與 fallback切換。
- 不送 CAD source file、公司資料、token或 tunnel configuration。
- 測試說明必須標示會產生 API usage/cost。

## 9. Acceptance criteria

- **ACC-LLM-001**：OpenAI Provider 可由 environment 啟用，沒有 hidden model default。
- **ACC-LLM-002**：至少五個 supported intents 的 structured response 通過 contract tests。
- **ACC-LLM-003**：Provider failure/refusal/invalid output 100% 回到 deterministic safe fallback。
- **ACC-LLM-004**：Similarity score、Rule result、CAE delta、Process evidence 在 LLM 前後完全一致。
- **ACC-LLM-005**：所有生成 claim 引用有效 evidence ref；unsupported critical claim 為 0。
- **ACC-LLM-006**：API key 不出現在 Git、frontend、response、log、test artifact。
- **ACC-LLM-007**：Live test與 provider outage UAT通過，且 usage/cost責任已記錄。
- **ACC-LLM-008**：完整自動化測試預設不呼叫付費 API。

## 10. Rollout and rollback

- 預設保持 `LLM_PROVIDER=deterministic-demo`。
- 先在 local/dev以 fake provider通過，再使用獨立 Demo Project key做 opt-in live test。
- Sites Demo由明確 env切換 `openai`，UI顯示 model-independent provider status。
- 發生高錯誤率、預算超限、policy疑慮時切回 deterministic，不需改 DB schema或重建 domain結果。
- Rollback不得刪除既有 evidence/audit；只停用外部 provider。

## 11. Suggested implementation commits

```text
feat(assistant): add versioned evidence envelope
feat(llm): implement OpenAI Responses provider
feat(web): add provider and generation states
test(llm): add fake-provider safety and fallback suite
docs: add OpenAI provider operations and live-test runbook
```

## 12. Implementation evidence（2026-08-28）

- `openai-responses` adapter uses `POST /v1/responses`, strict Structured Outputs, `store: false`,
  bounded input/output, server request IDs, usage metadata, timeout and concurrency limits.
- Provider/model/prompt/data-policy profiles are runtime configuration; no model name or key is
  committed to source control.
- Similarity、Design Review、Knowledge、Process/Trial、CAE all resolve persisted `public_demo`
  evidence before optional generation. Provider failure preserves the deterministic answer.
- Web distinguishes configured/generated/fallback states and supports truthful stop-waiting UX.
- Default tests use `httpx.MockTransport`; `test_openai_live.py` is skipped unless
  `RUN_OPENAI_LIVE_TESTS=1`, so the normal test gate does not generate OpenAI API usage.
- Operator setup and the potentially billable live UAT are documented in
  [Stage 14 operations](../../development/stage-14-openai-provider.md).

Remaining acceptance evidence: run the opt-in live test with a separately approved OpenAI Project
key/model, then record latency, usage and Project budget/limit ownership in Stage 16 UAT evidence.
