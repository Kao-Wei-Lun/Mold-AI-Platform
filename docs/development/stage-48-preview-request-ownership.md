# Stage 48：CAD 預覽與相似搜尋非同步回應歸屬修復

日期：2026-09-07。

## 使用者問題與重現

在相似搜尋中切換候選，預覽先顯示正確模型，稍後突然變成其他模型；重選後恢復。
`CadPreview.loadModel` 原本沒有取消或識別舊請求。A 下載中切至 B，B 先載入而 A 後到，
A 仍會加入同一 scene 並改寫 mesh/camera；測試實際觀察到 scene 同時含 B 與 A。
舊回應的錯誤亦會覆寫 B 的成功狀態；元件卸載後仍可能加入 mesh。

相似搜尋父元件也有相關風險：舊 job/deep link 回應可覆寫新查詢結果，
`acceptJob` 每次接收成功工作都重選第一筆，而舊 comparison 可以顯示在新候選下。

## 修復範圍

- 每個預覽實例持有獨立 request generation 與 AbortController。
- 每次來源改變/重試取消前次下載；在 response 與 arrayBuffer 兩個 await 後檢查
  generation、目前 source 及元件存活狀態。即使底層不理會 abort，舊回應仍不能更新畫面。
- 來源 watcher 同步失效舊請求，支援 A→B→A，不以 URL 相等誤認為同一次載入。
- 舊回應不能改寫 loading/error/camera，也不能重新加入 scene。
- 移除模型立即釋放 geometry/material 並清空 mesh reference，scene 最多一個 CAD mesh。
- 卸載時失效 generation、abort、停止渲染迴圈、釋放 controls/mesh/renderer。
- accent 變更只更新材質，不再次下載模型；透明設定套用到新模型。
- 相似查詢/深連結/輪詢使用 search generation，過期結果與錯誤被忽略；輪詢最多一個 timer。
- 同一工作結果刷新保留使用者選取的候選；明確指定 deep-link candidate 仍優先。
- 候選或搜尋改變時失效 comparison generation，避免舊偏差結果成為新模型的解釋。

不改資料、特徵、排序分數、API 契約或登入權限。

## 回歸測試

新增故意延遲的請求測試，修復前四個案例確實失敗，而不是只測正常順序：

1. B 先到、A 後到，scene 只能存在 B，且 A 已發出 abort。
2. A 的 body 讀取失敗晚於 B 成功，不能污染 B 的畫面。
3. A→B→A，第一個 A 的 body 晚到不能取代最後一次 A。
4. 切換來源時釋放舊 mesh；改 accent 不重下載並保留透明設定。
5. 元件卸載後回應到達，不得加入 mesh。
6. 切換查詢後舊搜尋完成，不得覆寫新結果與左右預覽來源。
7. 舊 deep link 晚到，不得覆寫新的 search/candidate。
8. 同一搜尋刷新不跳回第一筆候選。
9. 舊候選的 3D comparison 晚到，新候選不得出現舊 heatmap。

目標驗證：CadPreview、SimilarityWorkspace、SimilarityWorkspace.race 共 14 項通過，
包含原有控制項、錯誤重試及搜尋正常流程。

完整 `scripts/test.ps1` 通過：後端 330 passed、9 subtests passed、1 skipped（未啟用可能
付費的 OpenAI live check）；Web 172 tests；Sites 15 tests。TypeScript、前端 production
build、Django system/migration checks、各 Compose 驗證均通過。

## 發布驗證

待完整測試及外網部署確認後補記；沿用既有共用 app image 與 Demo 專案，
不重建資料庫、不刪 volume、不重新發布內容未變更的 Sites 私人入口。
