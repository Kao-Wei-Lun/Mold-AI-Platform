# Stage 16 — Demo Operations, Security, UAT and v1.0 Release

- 狀態：Phase A implemented；Phase B readiness/stale-job/performance baseline implemented；manual external release gates pending
- 優先級：P0
- 前置：Stage 13–15 完成
- 出口：可在全新 Windows host 重建、操作、重置、驗收並交付 Demo v1.0

## 1. 目標

Stage 16不增加新的工程演算法，而是把已完成能力組合成可重複、可診斷、可恢復的Demo產品。
目前已有`dev.ps1`、`sites-demo-start.ps1`、`mcp-secure-tunnel.ps1`、`test.ps1`與`smoke.ps1`，
但操作者仍需理解多套Compose、port、runtime key與Tunnel狀態。v1.0需要單一、明確的操作面。

## 2. Operator commands

新增或整理為：

```powershell
.\scripts\demo-start.ps1
.\scripts\demo-status.ps1
.\scripts\demo-reset.ps1
.\scripts\demo-backup.ps1
.\scripts\demo-stop.ps1
.\scripts\demo-acceptance.ps1
```

### 2.1 `demo-start.ps1`

責任：

1. 驗證Windows、Docker Desktop、可用disk/RAM與必要工具。
2. 驗證`.env.sites-demo`存在或以安全方式初始化。
3. 不顯示完整secret；不得將secret寫入transcript。
4. Build並啟動唯一指定的Sites Demo Compose project。
5. 等待DB、Redis、Qdrant、API、Workers、Web、MCP健康。
6. 執行migration與`seed_demo_data`，包含Stage 15 CAD reconciliation。
7. 啟動／確認Web Quick Tunnel並驗證system identity。
8. 驗證Stage 13 Sites entry與dynamic Workspace connection。
9. 檢查 MCP preflight `tool_count=10` 且 Plugin UI resource ready。
10. 輸出下一步啟動Secure MCP Tunnel的明確指令。

Start不得自動讀取或顯示`CONTROL_PLANE_API_KEY`，也不得在沒有使用者啟動terminal時偷偷建立長期
background tunnel-client process。

### 2.2 `demo-status.ps1`

以read-only方式輸出：

- Compose project與service/image/version。
- API liveness/readiness與dependency狀態。
- Worker heartbeat／queue reachability。
- Dataset expected/indexed/reconciliation counts。
- Assistant provider mode／health，不顯示key。
- Web Quick Tunnel reachability與system identity。
- Stable Sites entry設定狀態。
- MCP local endpoint、tool count、tunnel-client process/health（可取得時）。
- Git commit與working tree是否乾淨。
- Overall：`ready|degraded|not_ready`及下一步。

支援`-Json`輸出，供acceptance與support evidence使用；JSON不得包含token、key、完整URL fragment。

### 2.3 `demo-reset.ps1`

Reset是破壞性操作，必須：

- 預設建立metadata backup或要求明確`-SkipBackup`。
- 顯示將刪除的record categories與保留項目。
- 要求輸入明確確認字串或`-Confirm`；CI只能使用專用test environment flag。
- 只操作指定Compose project與資料庫schema，不以廣泛filesystem recursive delete實作。
- 保留`.env.sites-demo`、Tunnel profile、API keys、curated fixtures與Git repository。
- 清除manual uploads、analysis jobs/results、review decisions、HMI exports、automated smoke artifacts。
- 依policy保留或重建audit events；不能讓文件與實作矛盾。
- 重新seed curated Demo datasets並reconcile Qdrant。
- Reset完成後自動執行status/smoke子集。

Reset modes：

| Mode | 用途 | 清除 |
|---|---|---|
| `operations` | 兩場Demo之間 | searches/reviews/jobs/manual HMI/manual uploads |
| `datasets` | Fixture升版驗證 | operation data + seeded canonical/index records |
| `full-demo-volume` | 開發者重建 | 明確Demo volumes；需要二次確認與backup |

不得提供刪除任意path、Docker所有volumes或使用者home的參數。

### 2.4 `demo-backup.ps1`

Demo backup最低包含：

- PostgreSQL logical dump。
- Artifact/media manifest與hash；依需要封裝public/synthetic user-generated Demo files。
- Dataset manifests與versions。
- Rule profiles與checksums。
- Qdrant collection metadata；vector可選擇snapshot或由canonical data重建。
- App/version/commit/Compose image metadata。

預設不包含：

- `.env`、API key、Tunnel key、Demo token。
- Browser/sessionStorage資料。
- 不必要的prompt/response內容。

每個backup有manifest、created_at、source commit、checksums與restore instructions。

### 2.5 `demo-stop.ps1`

- 顯示即將停止的Compose project。
- 停止Web Quick Tunnel與containers。
- 提醒操作者在Tunnel terminal按Ctrl+C；可安全偵測但不強殺未知process。
- 預設保留volumes；`-RemoveDemoVolumes`需明確確認與backup。
- 停止後驗證public Workspace URL不可再存取API。

## 3. Security release requirements

- **OPS-SEC-001**：外部Web只能HTTPS；MCP只綁loopback並由Secure MCP Tunnel outbound連接。
- **OPS-SEC-002**：DB、Redis、Qdrant、Docker daemon不發布至LAN/Internet。
- **OPS-SEC-003**：Demo token至少256-bit random，API read/write scope fail closed。
- **OPS-SEC-004**：Token不出現在query string、Git、frontend bundle、一般log、UAT evidence。
- **OPS-SEC-005**：OpenAI API key、Tunnel runtime key、Admin key用途分離，不共用。
- **OPS-SEC-006**：所有upload維持type/signature/size/hash/basic screening與server-generated path。
- **OPS-SEC-007**：Rate-limit/WAF若v1.0未實作，Sites必須owner-only且Demo不得公開分享；此限制寫入release notes。
- **OPS-SEC-008**：每次外部Demo後可立即stop tunnel並rotate Demo token。
- **OPS-SEC-009**：Secret scan、dependency scan與container/image inventory保存結果。
- **OPS-SEC-010**：任何P0/P1安全問題阻止release，不以Demo名義waive資料外洩或任意執行。

OAuth/SSO不列為私人v1.0 blocker；只有要公開MCP或使用公司/私人資料時才升級為MUST。

## 4. Reliability requirements

- **OPS-REL-001**：Start可安全重跑，不建立重複fixtures或多套同名containers。
- **OPS-REL-002**：Seed partial failure使overall not_ready，並提供失敗dataset/job ID。
- **OPS-REL-003**：Worker restart後queued job可處理；running stale job有明確recover/fail policy。
- **OPS-REL-004**：Qdrant failure不破壞canonical records；恢復後可re-index。
- **OPS-REL-005**：Provider failure只降級Assistant，不影響CAD/Review/Knowledge/Process/CAE/HMI。
- **OPS-REL-006**：Backup至少完成一次restore drill至隔離Demo project。
- **OPS-REL-007**：Quick Tunnel重建後Stage 13 links仍從stable Sites entry運作。
- **OPS-REL-008**：Stop/start不需要重新建立OpenAI Tunnel或ChatGPT connection；只有metadata contract變更才refresh。

## 5. UAT environments and evidence

### 5.1 Environments

| Environment | 用途 | External network | Paid API |
|---|---|---:|---:|
| Local dev | Unit/integration與快速迭代 | 否 | 預設否 |
| Sites Demo | 完整production-like Web與MCP | 是 | 可選 |
| Clean-room | 全新volumes與重建驗證 | 可選 | 最小live test |

### 5.2 Evidence bundle

建議位置（只放非敏感結果）：

```text
docs/evidence/demo-v1/<YYYY-MM-DD>/
├─ README.md
├─ environment.json
├─ automated-tests.json
├─ smoke-summary.json
├─ uat-results.md
├─ security-checks.md
├─ dataset-reconciliation.json
└─ known-limitations.md
```

Screenshot若包含個人email、token、tunnel ID、private URL或browser資料，必須redact；不需要commit的完整
證據放在ignored release artifact目錄，Git只保存sanitized summary。

## 6. Master UAT script

### UAT-00 — Clean start

1. Docker Desktop已啟動。
2. 從clean Demo volumes執行`demo-start.ps1`。
3. Status為ready，curated datasets reconciliation passed。
4. 第二次start不建立duplicate data。

### UAT-01 — Private external Web

1. 從不同網路登入owner-only Sites。
2. 填入目前Workspace URL與Demo token。
3. Connection identity check通過。
4. 開啟完整Engineering Web，各module可讀取status。

### UAT-02 — CAD ingestion and Similarity

1. 選取Stage 15 curated query或上傳指定STEP。
2. Job顯示queued→running→succeeded。
3. Preview可rotate/zoom/fit。
4. Similarity Top K符合Golden group，分項與limitations完整。
5. 選取candidate顯示side-by-side evidence。

### UAT-03 — Design Review

1. 對指定fixture執行review。
2. PASS/FAIL/NOT_EVALUATED符合expected contract。
3. Rib/draft user-supplied measurement明確標示。
4. Reviewer decision需理由/approver條件，audit event產生。

### UAT-04 — Knowledge and Process

1. 查詢`射出成型短射`取得governed citation。
2. 無證據查詢明確abstain。
3. Process搜尋缺material時不給精確建議。
4. 提供`PA6-GF30`後取得synthetic cases與input provenance。

### UAT-05 — CAE and HMI

1. 比較compatible CAE runs並看到metric evidence。
2. 比較incompatible runs時不計算不當delta。
3. 上傳low-confidence HMI fixture，未review前禁止export。
4. 修正/確認後下載XLSX並驗證hash/values/lineage。

### UAT-06 — Embedded Assistant and LLM

1. OpenAI Provider啟用，詢問Similarity排名原因。
2. 回覆分隔facts/recommendation/uncertainty並引用evidence。
3. 停用或故意讓provider timeout。
4. UI顯示safe fallback，核心結果不變。

### UAT-07 — ChatGPT MCP and deep links

1. 新對話明確選取Mold AI Platform。
2. 能力/狀態回報 8 capabilities/10 tools 及正確 counts。
3. Knowledge與Process tools取得grounded result。
4. Similarity/Review create-job後以`get_job_status`poll完成。
5. 點deep link抵達相同persisted Web result。

### UAT-08 — Failure and recovery

1. Restart worker並確認job policy。
2. 暫停Qdrant，確認typed degradation；恢復後re-index/ready。
3. Provider outage維持核心能力。
4. Stop Quick Tunnel後外部Web不可達；本機資料仍保留。

### UAT-09 — Reset and restore

1. 建立backup。
2. 執行operations reset並確認manual operation data清除。
3. Curated datasets可用且counts一致。
4. 在隔離project執行restore drill並驗證manifest。

## 7. Automated test gates

Release前至少執行：

```powershell
.\scripts\test.ps1
docker compose up -d --build
.\scripts\smoke.ps1
.\scripts\demo-acceptance.ps1
```

Coverage categories：

- Backend contract/unit/integration。
- Web typecheck/unit/build。
- Sites lint/unit/build。
- Compose config與release preflight。
- Running API/Worker/Qdrant/MCP protocol。
- Stage 13 deep links。
- Stage 14 fake provider與opt-in live provider。
- Stage 15 manifest/seed/Golden scenarios。
- Reset/backup/restore safety。
- Secret pattern scan與Git diff check。

## 8. Performance baseline

v1.0不以1M case為gate，但必須記錄可重現基線：

- Curated corpus warm/cold Similarity latency。
- STEP/STL processing duration與resource peak。
- Knowledge與一般metadata API p50/p95。
- 三個並行互動session與五個queued jobs。
- Provider latency與usage（只在opt-in live test）。
- Web初次load與主要workspace bundle size。

報告包含hardware、OS、Docker、GPU/driver、commit、dataset/profile/index版本、sample size與error rate。

## 9. Release gate and artifacts

Release版本建議：`1.0.0-demo`。

必備artifacts：

- Git tag候選commit。
- Container image digests／dependency lockfiles。
- Sanitized test/UAT/security summary。
- Dataset/rule/provider/prompt/profile versions。
- Start/stop/reset/backup/restore runbook。
- Known limitations與non-goals。
- Rollback instructions。

禁止release情況：

- 自動測試或主UAT任一步失敗。
- Deep link仍為`.invalid`或含token。
- Curated seed/reconciliation不一致。
- Provider會改變工程deterministic results或在錯誤時假成功。
- 外部endpoint暴露DB/Queue/Vector Store。
- Git或bundle含secret。
- 工作樹有未審查變更。

## 10. Acceptance criteria

- **ACC-OPS-001**：全新Windows/clean volume依文件完成start與seed。
- **ACC-OPS-002**：status JSON正確反映services、datasets、provider、deep link與MCP。
- **ACC-OPS-003**：reset三種mode只影響明確scope，且至少一次restore drill成功。
- **ACC-OPS-004**：UAT-00至UAT-09全數Pass或有非安全、書面核准的waiver。
- **ACC-OPS-005**：不同網路的Sites與ChatGPT流程均可重現。
- **ACC-OPS-006**：Stop後外部path不可用，restart不需重建ChatGPT connection。
- **ACC-OPS-007**：Release evidence不含secret/PII，所有結果可追溯commit與version。

## 11. Suggested implementation commits

```text
feat(ops): add unified demo start and status commands
feat(ops): add scoped reset and backup manifests
test(uat): automate demo v1 acceptance checks
docs(ops): add release, restore, and incident runbooks
chore(release): prepare Mold AI Platform 1.0.0-demo
```

## 12. Phase A implementation evidence（2026-08-28）

本階段先完成不依賴外部帳號的 local/prod-like operations 基礎，版本為 `0.13.0-demo`：

- 統一 `demo-start.ps1`、`demo-status.ps1`、`demo-stop.ps1` 操作入口。
- `demo-status.ps1 -Json` 回傳 services、dependencies、dataset reconciliation、Assistant、MCP、
  Git 與明確 next actions；輸出不含 token、URL、tunnel ID。
- `demo-backup.ps1` 建立 PostgreSQL custom dump、artifact files/checksums、canonical release
  snapshot、image inventory 與 restore instruction；排除所有 env/key/token。
- `demo-restore.ps1` 只允許名稱結尾為 `-restore-drill` 的隔離 Compose project，驗證所有
  checksum，還原 DB/artifacts，重建 Knowledge/CAD Qdrant index，再執行 strict snapshot。
- `demo-reset.ps1` Phase A 只支援 `operations` mode；預設 dry-run，正式執行前預設建立
  backup，且要求精確字串 `RESET OPERATIONS`。既有 audit events 保留並新增 reset event。
- `demo-acceptance.ps1` 建立 ignored、sanitized evidence bundle 與各檔 SHA-256；local mode
  不會把尚未做的 external/OpenAI UAT 宣稱為通過。
- `seed_cad_demo --reindex` 可從 canonical FeatureSet 強制重建 Qdrant，供 restore/recovery。

實際 restore/reset drill 使用獨立 project 完成：還原 PostgreSQL 與 178 個 artifact files；
reset 移除 143 個 operations artifacts、44 個 Qdrant points 與 143 個 storage files，保留
curated fixtures、canonical Process/CAE、rule profiles 與既有 113 個 Audit Events；重新 seed
後 curated CAD 仍為 16/16。

尚未完成並保留為後續 Phase B：

- `datasets` 與 `full-demo-volume` reset modes。
- automated Qdrant/Quick Tunnel fault-injection 與 CAD/Similarity hardware microbenchmark。
- owner-only Sites 的不同網路 UAT、ChatGPT account/workspace MCP UAT。
- opt-in paid OpenAI live UAT、正式 sanitized evidence review 與 `1.0.0-demo` tag。

操作細節見
[Stage 16 Phase A operations](../../development/stage-16-operations-uat-phase-a.md)。

## 13. Phase B implementation evidence（2026-08-28）

- `demo-status.ps1` 現在顯示 dependency、兩個 Celery worker、全部 canonical dataset counts、
  core/external/optional readiness、Sites/Quick Tunnel、MCP deep link、Secure MCP Tunnel 與 client process。
- 新增 `recover_stale_jobs` dry-run/confirmed apply 命令；queued job 可重派、running job 依 attempt policy
  重派或以 typed error fail，且 applied run 會新增 Audit Event。
- Release snapshot 與 Demo status API 包含不含 Job ID 的 stale-job counts/policy。
- 新增 `demo-performance.ps1`，記錄五組 API p50/p95、三個 concurrent sessions 與五個 queued jobs，
  且不保存 URL、token 或 key。
- `demo-acceptance.ps1` 預設執行 performance gate 並將結果納入 checksummed evidence manifest；
  performance skipped/failed 不得成為 release candidate。

本次外部 Sites Demo 實測：五組 API 各 10 samples 零錯誤，p95 約 110–366 ms；三個 concurrent
sessions 全數成功，五個 queued jobs 全數完成。數值僅為此 Windows/Docker host 的 Demo baseline，
不是企業容量承諾。

Phase C 已完成 datasets/full-volume clean-room reset 與 Qdrant/Worker automated fault injection。
仍未完成：Quick Tunnel interruption UAT、CAD parse/similarity hardware microbenchmark、不同網路與
ChatGPT workspace manual UAT、optional live provider UAT 與 `1.0.0-demo` tag。Phase B 操作細節見
[Stage 16 Phase B operations](../../development/stage-16-operations-uat-phase-b.md)。

## 14. Phase C implementation evidence（2026-08-28）

- `datasets` reset 已具備 exact preview、backup-first execution、明確 PostgreSQL/Qdrant/artifact
  scope、Audit retention 與 deterministic reseed/re-index。
- `full-demo-volume` 是 double-confirmed clean-room rebuild，只允許名稱結尾為
  `-rebuild-drill` 的隔離 Compose project，不刪除 active Sites Demo 或 unrelated volumes。
- `demo-recovery-drill.ps1` 已自動驗證 Qdrant typed degradation、canonical record preservation、
  re-index recovery、`worker-cad` 停止期間 queue persistence 與 restart 後完成工作。
- 實際隔離測試從 fresh volumes 重建 16/16 curated CAD；dataset reset 清除 35 Artifacts、35
  ArtifactVersions 與 22 個明確 vector points，保留 profiles/Audit，再 seed 後 strict snapshot ready。
- Sanitized recovery evidence 只寫入 ignored `.runtime/evidence`，不含 URL、secret、Tunnel/task/container ID。

操作與安全邊界詳見
[Stage 16 Phase C operations](../../development/stage-16-operations-uat-phase-c.md)。
