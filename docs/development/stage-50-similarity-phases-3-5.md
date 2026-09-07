# Stage 50：幾何搜尋第 3–5 階段

依據：[CPU 幾何比對開發規劃](../planning/cpu-geometric-verification-plan.md)。

## Phase 3：局部結構與實際尺寸

- 新搜尋採 `cpu-surface-verification@2.0`；`@1.0` snapshot 仍可執行原先的全域比較。
- `comparison_mode`：`normalized_shape`（預設，允許等比縮放）、
  `engineering_size`（只旋轉／平移，先換算 mm；候選不能独立正規化大小）。
- `tolerance_mm`：0.001–10 mm，預設 0.5；不是 CAD 精密量測承諾。
  未知單位 query 在提交前回 400，未知單位候選在精比對時列 reference-only。
- 多容差曲線：0.5×、1×、2×；局部 2³／4³ 空間區域比較，至少 12 點才報局部覆蓋。
  較差四分之一區域覆蓋作保守折減；只用面積加權點，不以三角面數當設計特徵。
- STEP subprocess 新增 B-Rep 曲面相鄰類型、各曲面面積、正規化圓柱半徑及圓柱中心間距。
  這是結構證據，不是完整孔洞／肋骨／滑塊語意分類器；曲面分割方式仍可能影響統計。
- 新增 CADModel.brep_structure JSON（migration 0024）；不變更舊向量 checksum。
  舊 STEP 必須用既有重新處理流程才能補結構；不自动重算／覆盖历史搜尋。
- API 回傳 local_evidence、tolerance_curve、brep_structure，UI 中英顯示模式、容差與局部證據。
- cache key 增加模式、單位、容差與結構內容，避免跨模式或補資料後誤用舊結果。
- 自動驗證 transform 仍為內部正規化座標；不直接套入原始幾何 heatmap。

## Phase 4：評估與人工品質門檻

人工標註是獨立驗收條件，開發者不能把自動分数轉成「人工已確認」標籤。
會提供樣本準備、標註模板、標註合併驗證、開發集閾值擬合與 holdout 報告工具。
公開生成加工塊不等同公司歷史模具；未驗收資料不能啟用正式的無匹配判定。

## Phase 5：共享快取與效能／外網

保留授權與 checksum 檢查；將數值結果共用快取、候選召回診斷、cold/warm 時間與
驗證完成率納入報告；最後重建既有 Demo 的共用 image、保留資料與私人入口。

## 驗證紀錄

各階段完成後補記實際測試與部署結果；不以計畫值宣稱驗收通過。

Phase 3：完整 `scripts/test.ps1` exit 0，後端 347 passed、1 skipped、9 subtests；
Web 173 tests、Sites 15 tests。另驗證新模式在前端送出 comparison_mode/tolerance_mm。
Ruff、TypeScript、migration drift、build 與 Compose 檢查通過。
