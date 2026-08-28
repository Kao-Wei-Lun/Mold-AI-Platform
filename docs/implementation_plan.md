# Mold AI Platform — UI/UX 全面改良規劃

## 問題摘要

經過完整的原始碼分析，系統目前存在 **三大類** UI/UX 問題：

1. **表單輸入欄位設計不當** — 多處應使用下拉選單（`<select>`）或受控元件的欄位，卻使用了自由文字輸入（`<input type="text">`），導致使用者輸入錯誤率高
2. **表單驗證與引導不足** — 缺乏即時驗證、提示文字不清、必填欄位標示不明顯
3. **整體 UX 體驗可提升** — 包含版面配置、空狀態引導、操作回饋、錯誤恢復等

---

## 一、表單欄位類型錯誤（高優先級）

以下欄位目前使用 `<input type="text">` 自由輸入，應改為受控輸入元件（`<select>` 或 datalist 等）以防止輸入錯誤。

### 1.1 CadWorkspace — CAD 上傳表單

> [!CAUTION]
> 此處有 3 個自由文字欄位，使用者完全無法知道有效值為何。

| 欄位 | 目前 | 問題 | 建議改良 |
|------|------|------|----------|
| **Dataset** (`datasetId`) | `<input type="text">` | 使用者不知道有效的 dataset ID，預設值 `manual-cad-upload-v1` 也不明顯 | 改為 `<select>`，預設選項含 `manual-cad-upload-v1` 和 `curated-cad-demo-v1` |
| **Product type** (`productType`) | `<input type="text">` placeholder `housing` | 使用者只能猜測有效值 | 改為 `<select>`，選項含 `housing`、`connector_housing`、`electronics_cover`、`thin_wall_tray` 等（與 ProcessTrial 一致） |
| **Material** (`materialCode`) | `<input type="text">` placeholder `PC_ABS` | 使用者需要知道精確的材料編碼格式 | 改為 `<select>`，選項含 `PA6-GF30`、`ABS-GENERAL`、`PP-HOMO`、`PC_ABS` 等 |

#### [MODIFY] [CadWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/CadWorkspace.vue)
- L174-184: 將 `datasetId`、`productType`、`materialCode` 的 `<input type="text">` 改為 `<select>` 下拉選單
- 新增「其他（手動輸入）」選項，切換成 text input（保持彈性但預設受控）

---

### 1.2 SimilarityWorkspace — 相似度搜尋表單

> [!WARNING]
> 3 個篩選條件全是自由文字輸入，使用者根本不知道系統中有哪些合法值。

| 欄位 | 目前 | 問題 | 建議改良 |
|------|------|------|----------|
| **Dataset filter** (`datasetId`) | `<input type="text">` | 使用者不知道可用的 dataset ID | 改為 `<select>`，選項含 `public-demo-v1`、`curated-cad-demo-v1` 等 |
| **Product type** (`productType`) | `<input type="text">` placeholder `Any` | 同 CadWorkspace 問題 | 改為 `<select>`，含「Any」+ 所有 product type 選項 |
| **Material** (`materialCode`) | `<input type="text">` placeholder `Any` | 同上 | 改為 `<select>`，含「Any」+ 所有 material code 選項 |

#### [MODIFY] [SimilarityWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/SimilarityWorkspace.vue)
- L201-212: 將三個 `<input type="text">` 改為 `<select>` 下拉選單
- 每個都保留「Any」作為空值選項

---

### 1.3 ProcessTrialWorkspace — Process / Trial 查詢表單

> [!IMPORTANT]
> 此表單混合了良好設計（`<select>` for defect/material/machine/productType）和不良設計（`<input type="text">` for location）。

| 欄位 | 目前 | 問題 | 建議改良 |
|------|------|------|----------|
| **Location** (`location`) | `<input type="text">` | 使用者不知道有效的 location 值（如 `far_flow_end`） | 改為 `<select>`，選項含 `far_flow_end`、`gate_area`、`core_side`、`cavity_side` 等從既有 fixture 數據取得的選項 |

#### [MODIFY] [ProcessTrialWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/ProcessTrialWorkspace.vue)
- L238-241: 將 `location` 改為 `<select>`，含「Any location」+ 預設位置選項

---

### 1.4 DesignReviewWorkspace — 設計審查表單

| 欄位 | 目前 | 問題 | 建議改良 |
|------|------|------|----------|
| **Nominal wall (mm)** | `<input type="number">` | 缺乏合理範圍提示 | 新增 placeholder 顯示建議範圍（如 `1.0 – 5.0`），加入 tooltip 說明 |
| **Max rib (mm)** | `<input type="number">` | 同上 | 同上，建議範圍 `0.5 – 4.0` |
| **Min draft (deg)** | `<input type="number">` | 同上 | 同上，建議範圍 `0.5 – 5.0` |
| **Approver** (`decisionApprover`) | `<input type="text">` | 審批者名稱完全自由輸入，無驗證 | 改為 `<select>` 含預設審批者清單，或加入 autocomplete 提示 |

#### [MODIFY] [DesignReviewWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/DesignReviewWorkspace.vue)
- L207-218: 為 number input 新增 placeholder 提示合理範圍
- L343-346: 將 approver 改為含預設選項的 `<select>`（因為是 Demo 環境，approver 清單有限）

---

### 1.5 KnowledgeWorkspace — 知識文件上傳表單

> [!NOTE]
> 此表單的 `<select>` 使用良好，但 Title 欄位缺乏引導。

| 欄位 | 目前 | 問題 | 建議改良 |
|------|------|------|----------|
| **Title** (`title`) | `<input type="text">` placeholder `Demo molding SOP` | 使用者可能輸入不規範的標題 | 保持 text input，但新增即時格式驗證（如最小長度、不允許特殊字元提示） |

#### [MODIFY] [KnowledgeWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/KnowledgeWorkspace.vue)
- L214-215: 新增 `required` 屬性和 `minlength` 約束

---

## 二、表單驗證與使用者引導（中優先級）

### 2.1 缺乏即時驗證回饋

**問題**：所有表單僅在提交時才報錯，使用者無法在填寫過程中得知是否正確。

**改良方案**：

- 為必填欄位新增 `required` 屬性和紅色星號（`*`）視覺標示
- 為 number input 新增 `min`/`max` 的 CSS 範圍提示（如 `helper-text` 顯示合理範圍）
- 新增表單級 validation summary，在 submit 按鈕旁顯示「尚有 N 個欄位需要填寫」

### 2.2 新增共用元件

#### [NEW] FormField 包裝元件概念

建立一個統一的表單欄位包裝，處理：
- Label + required 星號
- Helper text / description
- Error message 區域
- 統一的樣式與間距

```
<FormField label="Material" required helper="Select the injection material code">
  <select v-model="materialCode">...</select>
</FormField>
```

> [!IMPORTANT]
> 由於所有 workspace 目前都直接使用原生 `<label>` + `<input/select>`，引入 FormField 元件可以一次性解決所有表單的一致性問題。

---

## 三、整體 UX 改良項目（中低優先級）

### 3.1 空狀態引導不足

| 位置 | 問題 | 改良 |
|------|------|------|
| SimilarityWorkspace 無 query 時 | 僅顯示一行灰字 | 加入引導卡片，顯示步驟：「先到 CAD 頁面上傳模型 → 回到此頁搜尋」 |
| DesignReviewWorkspace 無 query 時 | 同上 | 同上，加入前往 CAD 的快速連結按鈕 |
| ProcessTrialWorkspace 無 fixture 時 | 只有 Load fixtures 按鈕 | 加入說明卡片解釋為何需要先載入 fixture |

### 3.2 導航與資訊架構

| 問題 | 改良建議 |
|------|----------|
| 側邊欄的 `navigation-marker` 只顯示前兩字母（如 `CA`、`SI`），辨識度低 | 改用 SVG icon 或 emoji icon 增強辨識 |
| 頁面切換時無 transition 動畫 | 加入淡入淡出 transition |
| 手機版導航按鈕僅顯示「Menu」文字 | 改用漢堡圖示（☰）+ 文字 |

### 3.3 操作回饋改善

| 問題 | 改良建議 |
|------|----------|
| 表單提交後只有 loading 文字（如 `Submitting...`） | 加入 spinner 動畫或 progress indicator |
| 成功操作無正面回饋 | 加入 toast / snackbar 通知（如「CAD 上傳成功」） |
| 錯誤訊息 (`error-message`) 在頁面最底部，容易被忽略 | 將錯誤訊息移至表單附近，或使用 toast 通知 |

### 3.4 表格可讀性優化

| 位置 | 問題 | 改良 |
|------|------|------|
| HMI table | Source region 顯示原始座標 (`x 120 · y 45 · 200×80`)，對一般使用者無意義 | 預設隱藏技術細節，改用「區域 A/B/C/D」等友善標籤，技術細節放在展開區 |
| CAE metric table | Evidence 欄位使用 `<details>` 很好，但 metric code 顯示原始代碼 | 優先顯示 `metric_label`，code 縮小顯示 |
| Rule table | 資訊密度過高，四欄擠在一起 | 考慮改用卡片式 (card) 佈局或可展開的列 |

### 3.5 一致性問題

| 問題 | 位置 | 改良 |
|------|------|------|
| Demo 標籤文字風格不一致 | `Public / Synthetic Demo Data` vs `Synthetic evidence · No machine write` vs `Fixed synthetic profile · No cloud vision` | 統一格式為 `{type} · {constraint}` |
| 按鈕文字風格不一致 | `Load fixtures` vs `Reload idempotently` vs `Check compatibility and compare` | 統一使用動詞 + 名詞格式，避免技術術語（如 `idempotently`） |
| `Top K` 欄位標籤對一般使用者不友善 | ProcessTrial / Similarity / Knowledge 都有 | 改為「最多顯示 N 筆結果」或加入 tooltip 解釋 |

---

## 四、優先執行順序

### Phase 1 — 高優先：修正表單輸入類型 (3-4 天)

1. **CadWorkspace** — Dataset / Product type / Material 改為 `<select>`
2. **SimilarityWorkspace** — Dataset / Product type / Material 改為 `<select>`
3. **ProcessTrialWorkspace** — Location 改為 `<select>`
4. **DesignReviewWorkspace** — Approver 改為 `<select>` + number field 加 range hint

---

### Phase 2 — 中優先：增強驗證與引導 (2-3 天)

5. 新增 FormField 共用元件（label + required 星號 + helper text + error）
6. 所有必填欄位加上視覺標示
7. Number input 加上合理範圍提示
8. 空狀態引導卡片 (CTA)

---

### Phase 3 — 中低優先：UX 細節打磨 (2-3 天)

9. 操作回饋改善（toast 通知、spinner）
10. 按鈕 / 標籤文字統一
11. 導航圖示改善
12. 表格可讀性優化

---

## 五、影響範圍

### 前端修改檔案清單

| 檔案 | 修改內容 |
|------|----------|
| [CadWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/CadWorkspace.vue) | 3 個 input→select 轉換 |
| [SimilarityWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/SimilarityWorkspace.vue) | 3 個 input→select 轉換 |
| [ProcessTrialWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/ProcessTrialWorkspace.vue) | 1 個 input→select 轉換 |
| [DesignReviewWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/DesignReviewWorkspace.vue) | Approver select + number hints |
| [KnowledgeWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/KnowledgeWorkspace.vue) | Title 驗證增強 |
| [styles.css](file:///c:/project/Mold-AI-Platform/apps/web/src/styles.css) | FormField 樣式、required 星號、helper text |
| [i18n.ts](file:///c:/project/Mold-AI-Platform/apps/web/src/i18n.ts) | 新增翻譯字串 |
| **[NEW] FormField.vue** | 共用表單欄位元件 |
| **[NEW] Toast.vue** | 通知元件 |

### 後端無需修改

> [!NOTE]
> 所有改良都是前端 UI 層面的變更。後端 API 的驗證邏輯（如 `SUPPORTED_DEFECTS` 集合驗證）已經存在且正確，問題在於前端未向使用者暴露這些約束。

---

## Open Questions

1. **是否需要支援「自訂輸入」**？ 例如將 Material 改為 `<select>` 後，是否還需要一個「其他」選項讓使用者手動輸入自訂材料代碼？還是嚴格限制為下拉選項即可？

2. **Top K 參數是否需要向一般使用者暴露**？ 這是一個技術參數，可以考慮放入「進階設定」區域，預設隱藏。

3. **Phase 排程確認** — 是否同意先執行 Phase 1（修正表單輸入類型），再逐步進入 Phase 2、Phase 3？ 或者有其他優先順序偏好？

4. **Toast 通知元件** — 是否有偏好的 toast 位置（右上 / 右下 / 底部中央）？

---

## Implementation status (2026-08-28)

- Phase 1 is complete and independently verified in Git commit `4a6838b`.
- Phase 2 is complete in Stage 17 Phase C: shared accessible fields, required/range guidance,
  validation summaries and actionable empty states.
- Phase 3 is complete across Stage 17 Phases D and E: action feedback, progress states,
  plain-language copy, route icons and governed table/readability improvements.
- Detailed implementation and verification boundaries are recorded in
  [`development/stage-17-ui-phase-c-form-guidance.md`](development/stage-17-ui-phase-c-form-guidance.md).

## Verification Plan

### Automated Tests
```bash
cd apps/web && npx vitest run
```
- 確保所有既有的 `*.spec.ts` 測試仍通過
- 為新增的 FormField 元件撰寫單元測試

### Manual Verification
- 逐一操作每個 workspace 的表單，驗證下拉選單選項是否完整
- 嘗試用 Demo 資料完成完整的 7 步驟流程
- 確認中文（`zh-TW`）locale 下所有新增翻譯正確顯示
