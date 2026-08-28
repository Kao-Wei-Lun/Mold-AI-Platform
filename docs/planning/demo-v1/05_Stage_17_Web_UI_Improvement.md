# Stage 17 — Engineering Web UI/UX Improvement Plan

Implementation note: Phase A multi-route navigation and Phase B English/Traditional Chinese UI
switching are complete. Governed API source records intentionally remain in their authored language
until approved localized fields are part of the data contract.

- 狀態：Phase A implemented; workflow refinement in progress
- 優先級：P1
- 前置：Stage 13–16 contracts與UAT穩定
- 出口：一致、清楚、可擴充的Engineering Workspace，不改變domain evidence與安全邊界

## 1. 改良原則

現有Web UI已能完成各Stage工作，但畫面是依能力逐步加入，下一階段需要從「功能集合」改良為
「工程工作流程」。UI改版必須遵守：

1. 先讓使用者知道目前Project/Mold/Artifact/Job context，再顯示操作。
2. 主要工程工作使用專用UI；Assistant是協助入口，不遮蔽3D/evidence。
3. 每個AI/Rule/Search結果同時呈現來源、版本、限制與下一步。
4. 不用顏色單獨表示PASS/FAIL、風險或狀態。
5. 長任務可離開頁面，Job仍可追蹤；refresh不重複建立job。
6. Demo default、user input、system computed、model generated必須視覺上可區分。
7. UI不得自行做授權判定或工程計算；server仍是truth。
8. 先完成Desktop Engineering Workspace，再針對外部檢視提供responsive模式；不追求手機完成複雜3D工作。

## 2. UX goals and measurable outcomes

### 2.1 Goals

- 新使用者在沒有口頭教學時能完成Guided Demo。
- 工程師在任何頁面能回答「我看的是哪個版本、資料從哪裡來、結果是否完成」。
- Similarity/Review/CAE evidence可在同一視線範圍比較，不需來回捲動尋找ID。
- Error、abstention、not-ready與permission denied有不同、可操作的處理方式。
- ChatGPT deep link進入後，使用者理解來源是MCP並可返回原工作context。

### 2.2 Initial UX metrics

| Metric | Baseline method | Target direction |
|---|---|---|
| Guided Demo completion rate | 5–8位測試者 | 提升，且無阻斷錯誤 |
| Time to first Similarity result | 從登入至開啟Top 1 | 降低 |
| Wrong-context action | 錯Artifact/Review/Search操作次數 | 0 critical |
| Evidence discovery | 找到rule/source/citation所需時間 | 降低 |
| Job duplicate creation | refresh/back導致重複job | 0 |
| Error recovery | 遇到typed error後成功完成比例 | 提升 |
| Accessibility checks | keyboard/contrast/name/role | agreed gate全數通過 |
| Frontend performance | route load、bundle、3D interaction | 不低於v1.0 baseline |

數值門檻在Stage 17 discovery完成後，以實測baseline設定，不在規格階段虛構百分比。

## 3. Target information architecture

```text
Mold AI Platform
├─ Home / Demo Guide
├─ Engineering
│  ├─ CAD & Artifact
│  ├─ Similarity
│  ├─ Design Review
│  ├─ Process / Trial
│  ├─ CAE
│  └─ Machine HMI / Excel
├─ Knowledge
├─ Jobs
├─ Evidence & Audit
└─ Settings / Demo Status
```

全域App Shell：

```text
┌──────────────────────────────────────────────────────────────────────┐
│ Product / environment / Demo badge | context breadcrumb | user/status│
├──────────────┬──────────────────────────────────────┬────────────────┤
│ Navigation   │ Main engineering workspace           │ Assistant /    │
│              │                                      │ Evidence drawer│
│              │                                      │                │
├──────────────┴──────────────────────────────────────┴────────────────┤
│ Job center / notifications / provider and connection status          │
└──────────────────────────────────────────────────────────────────────┘
```

右側panel依工作切換`Assistant`與`Evidence`，不永久占用小螢幕。3D工作時可收合；deep link開啟citation
時自動切至Evidence但不遮住選定幾何。

## 4. Design system foundation

### 4.1 Tokens

建立集中tokens，不在components散落hex/spacing：

- Color：surface、text、border、accent、info、success、warning、danger、disabled、focus。
- Typography：display、heading、body、label、mono/data；中英文字型fallback。
- Spacing：4/8-based scale。
- Radius、shadow、z-index、motion duration/easing。
- Data visualization colors，包含color-blind可辨識組合。
- 3D selection/highlight/evidence colors與對應legend。

Theme至少支援light/dark一致性；若Demo只先交付一種theme，另一種不得保留半完成狀態。

### 4.2 Component inventory

必備共用components：

- AppShell、Sidebar、TopContextBar、Breadcrumb。
- PageHeader、Section、SplitPane、ResizableDrawer。
- Button、IconButton、Menu、Tabs、Dialog、Popover、Tooltip。
- TextField、NumberField、Select、FileDropzone、FormError。
- DataTable、VirtualList、Pagination、FilterBar。
- StatusBadge、SourceBadge、ConfidenceBadge、ProviderBadge。
- EmptyState、LoadingSkeleton、ErrorState、AbstentionState。
- JobProgress、JobDrawer、NotificationCenter。
- EvidenceCard、CitationLink、LineagePanel、VersionChip。
- CompareTable、MetricDelta、ScoreBreakdown、Legend。
- ConfirmAction、ReviewerDecisionForm。

所有component定義keyboard、focus、disabled、loading、error、empty與responsive states。

## 5. Global context and navigation

- **UIX-001**：Top bar永遠顯示environment與Public/Synthetic Demo badge。
- **UIX-002**：Breadcrumb顯示Artifact→Version→Search/Review，不只顯示頁名。
- **UIX-003**：切換module前若有未儲存review/input，需明確提示。
- **UIX-004**：Deep link進入顯示「Opened from ChatGPT MCP」與來源tool；可關閉提示。
- **UIX-005**：Global Job Center列出queued/running/failed/recent succeeded，點擊回到正確context。
- **UIX-006**：Connection status區分Web API、Queue/Qdrant、LLM Provider、MCP，不用單一綠點掩蓋降級。
- **UIX-007**：URL保存非敏感read context，支援refresh/back/forward；write form state不放URL。

### Phase A implementation（2026-08-28）

- `/` 改為 Guided Demo Home，不再同時 mount 所有能力。
- CAD、Similarity、Design Review、Process/Trial、CAE、HMI、Knowledge、Mold Rules 與 Status
  各自具有 canonical route，支援 browser back/forward 與 Nginx SPA fallback。
- ChatGPT deep link 會從 legacy root query 自動定位到對應 route，並保留原本 contract 與安全驗證。
- App Shell 顯示 breadcrumb、Demo scope、目前 CAD context、Assistant toggle 與 responsive navigation。
- 新增 `/governance/rules`，從 API 顯示已核准 profile、owner、approver、version、checksum、13 條
  RuleVersion、condition、severity、risk 與 reference；因尚無 draft/approval workflow，維持 read-only。
- UI 新增集中 design tokens 與 keyboard focus ring；既有 domain component 計算與 API contract 不變。

## 6. Home and Guided Demo

Home提供兩種模式：

### Guided Demo

- 顯示固定七步主流程與完成狀態。
- 每一步說明輸入、預期結果、資料性質、安全限制。
- 使用Stage 15 curated fixtures，但需明確點選「使用Demo案例」。
- 可重置Guided progress，不刪除domain data。
- 每一步提供「開啟功能」與「查看證據」。

### Engineering Workspace

- 顯示最近Artifacts、Jobs、Searches、Reviews。
- Dataset/Provider/Service readiness摘要。
- 不以大型行銷卡片取代工程資料。
- Empty state提供明確第一步，而非自動建立資料。

## 7. CAD and 3D Viewer improvement

- Upload採stepper：選檔→metadata/dataset→validation→job→preview。
- File validation在提交前與server response後分開呈現。
- Viewer toolbar：rotate、pan、zoom、fit、standard views、projection、opacity、reset。
- 顯示model unit、bbox、volume、area、faces/edges、quality flags與parser/version。
- 選取Face時顯示stable reference能力；若目前不支援stable face ID，UI明確標示whole-model evidence。
- Large model loading顯示progress與fallback，不凍結整頁。
- 3D canvas具有keyboard可達替代資訊與geometry summary；不可只依滑鼠hover。
- Download/preview使用authenticated fetch，維持現有安全邊界。

## 8. Similarity workspace

建議三區：

```text
Query context | Ranked candidates | Comparison / evidence
```

- Query card固定顯示artifact/version/dataset/product/material。
- Filter與profile可展開，active filters以chips顯示。
- Candidate list顯示Overall與lane mini-bars、data flags、rank change（若有profile comparison）。
- 選取candidate不改變query；比較context固定在top bar。
- Side-by-side viewer與score/difference table同步。
- Lane unavailable不顯示0分，顯示`Not available`及weight renormalized提示。
- Limitations與lineage收進Evidence drawer但有明顯入口。
- 未來Relevant/Not Relevant feedback加入時，需要reason與dataset/version，不直接訓練。

## 9. Design Review workspace

- Summary先顯示PASS/FAIL/NOT_EVALUATED counts與profile/version。
- Finding列表支援severity/result/rule filter。
- 每個finding顯示actual、limit、unit、evidence scope、rule reference、measurement provenance。
- 選取finding同步3D evidence；whole-model scope不偽裝為face highlight。
- Reviewer decision使用dialog，Reject/Waive required fields與後果清楚。
- 歷史decision immutable timeline可檢視actor/time/reason。
- LLM explanation放在finding旁的Assistant入口，不混入deterministic result欄位。

## 10. Knowledge workspace

- 左側document catalog顯示authority/effective/ingestion/dataset。
- 中央search結果以claim/excerpt呈現；每個claim附近放citation，不集中到頁尾。
- 右側source viewer定位section/paragraph；未來PDF支援才顯示page coordinate。
- Abstention使用專用state，列出已搜尋scope與缺少資料，不推薦切到無關lane。
- Prompt-injection quarantine只對有權操作者顯示安全摘要，不回傳惡意全文。
- Search filters與dataset scope可見，使用者不能自稱permission。

## 11. Process/Trial workspace

- 必要欄位先顯示，optional machine/location/parameters放進Advanced section。
- 預設全空；`Use explicit Demo inputs`保留清楚badge與可一鍵清除。
- Results把`Historical evidence`與`Controlled trial candidate`視覺分區。
- 每個parameter顯示before/after/unit/source case、applicability、stop condition。
- `requires_engineer_approval`與`do_not_auto_apply`固定在建議附近，不只在頁尾。
- Missing material/machine的abstention與range withholding原因可理解。
- 不提供`Apply to machine`按鈕或暗示自動寫入。

## 12. CAE workspace

- Baseline與candidate selection並排，顯示solver/material/mesh/mold revision/unit compatibility。
- Compatibility gate先於metric table；blocked時不顯示空delta表格。
- Metric table顯示baseline/candidate/delta/%/finding/quality。
- Temperature等無單調好壞規則的metric使用neutral change state。
- Evidence drawer顯示study/run/result IDs與lineage。
- Contour placeholder不得看似真實field visualization；未實作時只顯示structured metrics。

## 13. HMI → Excel workspace

- Upload區明確標示支援的fixed Demo profile與non-goals。
- 原圖與field table並排；source region可在圖上highlight。
- Confidence、raw/normalized value、unit、range error分欄。
- Low-confidence fields建立review queue，完成前Export disabled並說明原因。
- Correction需保留original value與reviewer action。
- Export完成顯示artifact version、hash與安全download action。
- 不提供任意Excel template designer，除非另立Stage。

## 14. Assistant panel

- 顯示目前context chips，例如Similarity search/candidate，而非把ID埋在prompt。
- Provider badge區分OpenAI、safe fallback、unavailable。
- 回覆固定sections：Summary、Facts、Interpretation、Recommendations、Uncertainty、Evidence。
- Model-generated內容有清楚標示，citation由server提供。
- Suggested prompts依目前page/selection生成，不顯示unsupported intent。
- UI Actions只透過allowlist；執行前顯示目標，失效時安全拒絕。
- Panel可resize/collapse；3D/Evidence工作不被遮蔽。

## 15. Error, loading and empty states

建立統一state matrix：

| State | Meaning | Required UI |
|---|---|---|
| Loading | 正在讀取既有資料 | skeleton/progress，不可重複submit |
| Queued/Running | Server job存在 | job ID、stage、progress、離開提示 |
| Empty | 尚未建立或沒有項目 | 合法下一步，不是假錯誤 |
| Abstained | 系統刻意不下結論 | 缺少evidence/field與安全理由 |
| Validation error | 輸入可修正 | field-level error與保留輸入 |
| Dependency degraded | 部分服務失效 | 可用/不可用能力與retry |
| Unauthorized | 未授權 | 不透露resource existence |
| Failed job | Terminal failure | typed error、correlation ID、safe retry條件 |
| Stale context | Deep link/result不再適用 | 回到parent，不自動建立新工作 |

## 16. Localization and terminology

- UI至少提供`zh-Hant`一致翻譯；是否保留English切換在discovery決定。
- Domain code/IDs/units不翻譯；顯示label可本地化。
- 建立術語表：Mold、Part、Artifact、Revision、Trial、Process Run、Finding、Waiver、Evidence。
- 同一詞不得在不同module使用不同翻譯。
- 日期、timezone、number與unit格式使用明確locale，但canonical API值不變。

## 17. Accessibility and responsive behavior

- 全鍵盤完成navigation、forms、tables、dialogs、drawer；3D另提供資料替代路徑。
- 清楚focus indicator、semantic labels、error association、live region（僅必要status）。
- Color contrast與status icon/text共同表示。
- `prefers-reduced-motion`時停用非必要動畫。
- Tables在窄畫面改為可控scroll/card，不截斷evidence IDs與units。
- Mobile主要支援status、Knowledge、Job、evidence檢視；複雜3D操作顯示建議使用desktop。

## 18. Frontend architecture

- 保留Vue/TypeScript，建立feature modules與shared design system。
- API types由versioned contract集中管理，避免component內複製interface。
- 使用route/context store管理read context；不建立包含secret的global persistent store。
- 大型3D/viewer module維持lazy loading並監控bundle。
- Error boundary、request cancellation、deduplication與stale response protection標準化。
- Components不直接讀取`window.location`拼接domain behavior；由router/deep-link service處理。
- Visual state與server state分離；禁止前端把Job改成succeeded。

## 19. Delivery phases

### UI-1 — Discovery and audit

- 現有畫面inventory、task flow、responsive/accessibility/performance baseline。
- 5–8位目標使用者完成Guided tasks並記錄問題。
- 確認資訊架構、術語、priority與不改contract原則。

### UI-2 — Design system and App Shell

- Tokens、base components、Storybook或等價component catalog。
- AppShell、navigation、context bar、Job Center、global states。
- Visual regression baseline。

### UI-3 — Core CAD workflows

- Home/Guided Demo、CAD upload/viewer、Similarity、Design Review。
- Deep link與Assistant/Evidence drawer整合。
- 完成第一輪usability test。

### UI-4 — Evidence workflows

- Knowledge、Process/Trial、CAE、HMI。
- 統一tables、filters、citations、lineage與review states。

### UI-5 — Responsive, accessibility and polish

- Keyboard/contrast/screen reader checks。
- Narrow-width檢視、empty/error/loading/failure states。
- Bundle/performance优化與跨browser測試。

## 20. Test and acceptance

### Automated

- Component unit與interaction tests。
- API request mapping與no-duplicate-action tests。
- Deep-link route matrix。
- Accessibility automated checks。
- Visual regression在固定fixtures/browser/viewport執行。
- Typecheck、lint、production build與bundle budget。

### Manual

- Guided Demo全流程。
- Keyboard-only。
- 125%/200% zoom與常見desktop viewport。
- Slow network、API error、provider fallback、job running。
- 中英文長字串、units、IDs、empty datasets。
- 3D interaction與evidence同步。

### Acceptance

- **ACC-UIX-001**：七步Guided Demo無需URL/ID手動複製。
- **ACC-UIX-002**：所有module顯示正確context、dataset、version、status與limitations。
- **ACC-UIX-003**：Refresh/back/forward不建立重複job或decision。
- **ACC-UIX-004**：Keyboard與agreed accessibility gate通過，critical issue為0。
- **ACC-UIX-005**：Error/empty/abstention/degraded states均有可操作且truthful UI。
- **ACC-UIX-006**：Stage 13–16既有domain/UAT contract全數保持通過。
- **ACC-UIX-007**：Frontend performance不低於v1.0 baseline，超出budget需書面決策。

## 21. Non-goals

- 不在UI改版期間重寫CAD/Similarity/Rule算法。
- 不用動畫或dashboard數量取代evidence與工程context。
- 不建立假3D contour、假face highlight或假LLM streaming。
- 不加入machine apply/write action。
- 不因美觀把Demo/Synthetic、safe fallback、NOT_EVALUATED或limitations隱藏。

## 22. Suggested implementation commits

```text
docs(ui): record UX audit and design decisions
feat(ui): add design tokens and application shell
feat(ui): redesign CAD similarity and review workspaces
feat(ui): unify evidence workflows and assistant panel
test(ui): add accessibility and visual regression gates
perf(ui): enforce route and viewer bundle budgets
```
