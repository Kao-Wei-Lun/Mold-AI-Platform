# Stage 51：相似 CAD 搜尋欄位對齊

日期：2026-09-08。範圍：前端表單排版，不變更 API、搜尋演算法、索引或資料庫。

## 原因

- 比對模式／容差誤用全域 `score-grid`，該四欄網格又被塞入原本五欄 similarity-form 的一格。
- `form-wide` 並沒有在此表單定義跨整列規則，导致兩層 grid 擠壓、標籤／輸入框互相覆蓋。
- 外層 `align-items: end` 以包含 helper 的整個欄位底部對齊，使「最多顯示結果」輸入框偏高。

## 修正

1. 模式、條件式容差、資料集、產品類型、材料、最多結果，改為同一專用網格的直接子欄位。
2. component-scoped CSS 隔離分數卡片的排版與 span 樣式，避免其他頁面受影響。
3. 同列標籤保留相同高度、輸入／選單統一 3rem 高；提示文字只放在控制項下方。
4. 寬螢幕五／六個欄位同列，模式欄較寬；依表單容器可用寬度在 72／48／32rem 分為三／二／一欄。
   依容器而非整個視窗判斷，側欄／助理展開或縮放時仍可自適應。
5. 搜尋按鈕獨立一列靠右；窄螢幕全寬。容差的必填標記與既有 required 驗證一致。
6. 保留全部輸入綁定、預設值、搜尋請求、狀態及查詢結果，不清空既有資料。

## 測試

- Web 完整 39 files／174 tests 通過；typecheck、production build 通過。
- 相似搜尋與非同步切換專項 9 tests 通過，新增五／六欄同層級、模式切換、按鈕獨立與中文檢查。
- `node scripts/check-similarity-layout.mjs`：啟動獨立本機 Vite 及隔離 headless Chrome，
  用真實 Vue 元件與全域 CSS 測試；不登入、不呼叫生產 API、不修改 CAD。
- 4 種視窗尺寸 × 中英文 × 2 種模式共 16 組通過：
  檢查欄位數、同列輸入 y 座標、label/input 不重疊、控制項不越界、按鈕不蓋 helper、無橫向捲動。
  測試實際 viewport 寬度為 1572、1172、872、500px（Chrome 視窗外框會影響 viewport）。
- 量測 JSON 與 PNG 位於 `.runtime/similarity-layout/2026-09-08T00-22-07.925Z/`；
  已檢視桌面繁中尺寸模式截圖，六項同水平。可透過 `LAYOUT_CHROME_PATH` 指定其他 Chromium。
- `tests/layout/similarity.html` 是本機 Vite 測試 fixture，不是 production build 入口。

## 部署

測試通過後提交 Git，再更新既有外網 Demo 共用 app image；不另建 Sites、不變更私人存取權限。
發布後補記實際外網 JS/CSS 與已測 build 的 SHA 校驗結果。

### 實際發布驗證（2026-09-08）

- 程式提交：`817354e`。更新既有 `mold-ai-platform-sites-demo` 的 api、worker、worker-cad、web、mcp-gateway，五項服務共用單一 app image。
- 外網入口：`https://neck-rap-chocolate-extensive.trycloudflare.com`；既有私人 Sites 入口與存取權限不變。
- 已從外網下載發布資產，SHA-256 均與本機通過建置的檔案一致：
  - `/assets/index-Dr6r0FSz.js`：`9221E56A0A1B0FA9B437CA6E63E966404E944D630D42A6BD659208891E2AF2E1`
  - `/assets/index-DvioUC22.css`：`1251F73DF9FC3F8A109CBABFFE5DFC450D9BEDCA99879ACC7B84E111BF2F1098`
- 發布後狀態：Containers ready、API ok、兩個 Worker 回應、Core Demo ready、Sites entry ready、Web tunnel ready；資料與搜尋演算法未變更。
- 整體狀態仍顯示既有 optional Assistant fallback 的 degraded，不影響此次排版修正或核心 Demo。
- 使用者可按 `Ctrl+F5` 重新整理以載入最新前端。
