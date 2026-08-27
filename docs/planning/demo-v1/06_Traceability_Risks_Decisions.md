# Demo v1.0 Traceability, Risks and Decision Register

- 狀態：Planning baseline
- 更新規則：每個Stage開始、scope變更、Gate評審與release候選時更新

## 1. Cross-stage traceability

| Existing requirement | Gap | Planned requirement | Stage | Primary evidence | Initial status |
|---|---|---|---|---|---|
| D-MCP-002 | MCP UI URL為`.invalid` | DL-001–034 | 13 | link contract/unit/external UAT | Planned |
| D-AST-003/004 | 只有deterministic provider | LLM-001–045 | 14 | provider/fallback/evidence tests | Planned |
| D-SIM-001–007 | 無獨立curated CAD corpus | CAD-DATA-001–014 | 15 | manifest/seed/Golden scenarios | Planned |
| D-REV-001–005 | Rule有fixtures但主Demo corpus未治理 | CAD review scenarios | 15 | expected review contract | Planned |
| ACC-D-002 | 未有統一clean-room重建證據 | OPS-REL/ACC-OPS | 16 | demo-start/status/acceptance | Planned |
| ACC-D-005 | 外部安全操作分散於多份runbook | OPS-SEC-001–010 | 16 | security/release evidence | Planned |
| Demo DoD | Reset/backup/restore/UAT未整合 | ACC-OPS-001–007 | 16 | UAT-00–09 | Planned |
| Web usability | Stage累積UI缺乏一致workflow | UIX-001–007 | 17 | UX/accessibility/visual tests | Planned |

## 2. Stage deliverable matrix

| Deliverable | 13 | 14 | 15 | 16 | 17 |
|---|---:|---:|---:|---:|---:|
| Stable Sites entry contract | Primary | Consume | Consume | UAT | Preserve |
| MCP link builder | Primary | Consume | UAT | UAT | Preserve |
| OpenAI provider adapter |  | Primary |  | UAT/operate | UI refine |
| Deterministic fallback | Preserve | Primary |  | Outage UAT | UI refine |
| Curated CAD manifest/seed |  |  | Primary | Operate/reset | Guided flow |
| Golden Similarity/Review |  | Evidence | Primary | UAT | Preserve |
| Start/status/reset/backup/stop | Support | Config | Seed hooks | Primary | Preserve |
| External Web + MCP UAT | Link subset | Provider subset | CAD subset | Master | Regression |
| Design system/App Shell |  | Minimal states | Minimal guided hook | No redesign | Primary |

## 3. Dependency rules

- Stage 13的link contract必須在Stage 14 provider回傳links前固定。
- Stage 14不能依賴Stage 17 UI；先以現有AssistantPanel提供完整truthful states。
- Stage 15 seed contract必須在Stage 16 reset/backup scripts前固定。
- Stage 16 release候選不得包含未完成Stage 17的大規模UI rewrite。
- Stage 17可調整layout與interaction，但不得未經versioning改變Stage 13–16 API/domain contracts。
- 任何Stage發現P0/P1安全問題，可阻止後續Stage並優先修正。

## 4. Risk register

| ID | Risk | Probability | Impact | Mitigation | Owner role | Gate |
|---|---|---:|---:|---|---|---|
| R-DL-01 | Quick Tunnel URL變動造成MCP links失效 | High | High | Stable Sites dispatcher，不把dynamic origin寫入MCP | Platform | Stage 13 |
| R-DL-02 | Token進入URL/history/log | Medium | Critical | Session storage + fragment handoff + secret scan | Security | Stage 13 |
| R-DL-03 | Open redirect或cross-context ID | Medium | High | Target allowlist + parent relationship validation | Platform | Stage 13 |
| R-LLM-01 | Model補造工程事實/參數 | Medium | Critical | Deterministic evidence first、structured validation、fallback | AI/Domain | Stage 14 |
| R-LLM-02 | API費用或rate limit失控 | Medium | Medium | Separate project、limits、usage、concurrency、budget alarm | Platform | Stage 14 |
| R-LLM-03 | Public Demo policy被誤用於公司資料 | Medium | Critical | classification gate；Company rollout需新data review | Security/Data | R3 |
| R-CAD-01 | Synthetic ranking過度適配單一query | Medium | High | 至少兩個queries、negative controls、versionedprofile | Search | Stage 15 |
| R-CAD-02 | Fixture/license/provenance不完整 | Low | High | Synthetic-first；manifest required fields/checksums | Data | Stage 15 |
| R-CAD-03 | Seed partial成功卻宣稱ready | Medium | High | Non-zero failure + reconciliation gate | Platform | Stage 15/16 |
| R-OPS-01 | Reset誤刪repo或其他Docker data | Low | Critical | Fixed project/scope、explicit confirmation、backup | Platform | Stage 16 |
| R-OPS-02 | Evidence bundle洩漏secret/PII | Medium | High | Sanitization、ignored raw artifacts、secret scan | Security | Stage 16 |
| R-OPS-03 | 只在開發者機器可重現 | Medium | High | Clean-room Windows rebuild與runbook UAT | QA/Platform | Stage 16 |
| R-UI-01 | UI rewrite造成domain regression | Medium | High | Contract freeze、visual/interaction + full UAT regression | Frontend | Stage 17 |
| R-UI-02 | 3D/large tables使前端效能惡化 | Medium | Medium | Lazy load、virtualization、bundle/perf budgets | Frontend | Stage 17 |
| R-UI-03 | 美化後隱藏limitations/source | Medium | High | Evidence/limitation為acceptance requirement | Product/Domain | Stage 17 |

Probability/Impact在各Stage kickoff重新評估；不得因本表標示Low就省略Critical impact的control。

## 5. Decision register

### ADR-DV1-001 — Stable Sites entry for deep links

- **Decision**：MCP links指向stable owner-only Sites dispatcher，不直接使用dynamic Quick Tunnel origin。
- **Reason**：避免Workspace URL變動要求refresh MCP metadata，並防止MCP接觸Demo token。
- **Consequence**：Sites成為navigation control point；session未設定時需setup/resume UX。
- **Status**：Proposed，Stage 13 kickoff確認實際Sites routing能力。

### ADR-DV1-002 — Server-resolved evidence before LLM

- **Decision**：Stage 14由server先執行domain resolver，再把bounded evidence交給OpenAI；模型不直接任意call tools。
- **Reason**：保持authorization、lane selection、evidence與工程計算可測。
- **Consequence**：第一版intent數量有限，但安全且可重現。
- **Status**：Proposed。

### ADR-DV1-003 — Model selection is runtime configuration

- **Decision**：文件與domain code不寫死OpenAI模型；使用allowlistedProvider Profile與`OPENAI_MODEL`。
- **Reason**：模型、availability、cost、limits會變動，且需依Demo Project驗證。
- **Consequence**：Release evidence必須記錄實際model/profile，而requirements只定義能力。
- **Status**：Accepted planning principle。

### ADR-DV1-004 — Synthetic-first CAD corpus

- **Decision**：v1.0 curated corpus以project-generated synthetic CAD為主。
- **Reason**：可控truth、可重現、無公司資料與授權爭議。
- **Consequence**：不能宣稱真實公司relevance；R3需重新建立Golden Dataset。
- **Status**：Proposed。

### ADR-DV1-005 — UI redesign after v1.0 contract gate

- **Decision**：Stage 17在Stage 13–16 feature completion後執行。
- **Reason**：避免navigation、provider、dataset與operations contracts仍變動時同時重寫UI。
- **Consequence**：Stage 13–16只做必要UI，不追求全面視覺改版。
- **Status**：Accepted by requested sequence。

## 6. Open decisions

以下項目在對應Stage開始前確認，不阻止文件建立：

| Decision | Needed by | Options | Recommended default |
|---|---|---|---|
| Stable Sites path是否可直接提供`/open` route | Stage 13 | route/query dispatcher、single-page dispatcher | 先驗證route；不行則用首頁query dispatcher |
| Demo Sites production URL | Stage 13 | 現有owner-only Site、新Site | 保留現有，避免重新授權 |
| Initial OpenAI model/profile | Stage 14 | 依當時官方models與Project limits | 以eval/latency/cost選，不在規格寫死 |
| Streaming是否列為Stage 14 MUST | Stage 14 | synchronous、SSE | 先完成安全structured response；再以UX benchmark決定 |
| CAD fixture generator | Stage 15 | OpenCascade Python、checked-in files、hybrid | Generator+checked checksum hybrid |
| Curated corpus exact size | Stage 15 | 14、18、22+ | 以兩個Golden scenarios完整性決定 |
| Reset audit retention | Stage 16 | retain、archive、reseed | 預設retain安全metadata；操作資料按policy清除 |
| UI語言 | Stage 17 | zh-Hant only、zh-Hant+English | Domain IDs保留英文；UI優先zh-Hant並預留i18n |
| UI component catalog | Stage 17 | Storybook、custom route、other | 依Vue toolchain最小維護成本決定 |

## 7. Requirement status values

統一使用：

- `Planned`：已寫入範圍，尚未開始。
- `In Progress`：已有active branch/worktree implementation。
- `Implemented`：code完成但尚未全Gate。
- `Verified`：automated + required UAT通過。
- `Waived`：非安全requirement經owner書面核准並有expiry。
- `Blocked`：外部authority/data/license/technical dependency阻止。
- `Deferred`：移出v1.0且已寫入後續Roadmap。

禁止把`Implemented`等同`Verified`，也禁止將「測試環境未執行」標成Pass。

## 8. Gate review template

每個Stage結束建立以下summary：

```markdown
# Stage <N> Gate Review

- Commit:
- Environment:
- Date/operator:
- Requirements implemented:
- Automated tests:
- Running-stack tests:
- External UAT:
- Security/secret scan:
- Dataset/provider/profile versions:
- Known limitations:
- Waivers:
- Rollback tested:
- Decision: Pass / Fail / Conditional
```

## 9. Change control

- 新需求先判斷屬v1.0 MUST、Stage 17 UI、或Enterprise/R3+。
- 改變schema/URL/tool/prompt/dataset ID時更新traceability與compatibility test。
- Scope增加不得默默延後security、evidence、reset或UAT工作。
- 外部OpenAI/Sites/Tunnel能力變動時，更新adapter/runbook；核心Capability contract保持穩定。
- 每次Gate後保留文件歷史，使用Git review而非覆寫成看不出原決策。

## 10. Overall completion dashboard

| Stage | Feature scope | Automated | Running stack | External UAT | Gate |
|---|---|---|---|---|---|
| 13 Deep Links | Planned | Planned | Planned | Planned | Not started |
| 14 OpenAI Provider | Planned | Planned | Planned | Planned | Not started |
| 15 CAD Corpus | Planned | Planned | Planned | Planned | Not started |
| 16 Operations/Release | Planned | Planned | Planned | Planned | Not started |
| Demo v1.0 | Depends on 13–16 | — | — | — | Not ready |
| 17 Web UI Improvement | Planned after v1.0 | Planned | Planned | Planned | Not started |
