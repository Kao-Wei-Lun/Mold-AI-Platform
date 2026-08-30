# Mold AI Platform — 上傳資料功能分析報告

## 一、現有上傳入口一覽

系統目前有 **三個** 獨立的資料上傳入口：

| 上傳入口 | 所在 Workspace | 支援格式 | 最大檔案 | 後端驗證 |
|---------|---------------|---------|---------|---------|
| **CAD 上傳** | [CadWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/CadWorkspace.vue) | `.step` `.stp` `.stl` | 200 MB | ✅ 檔案簽章 + malware + 大小 |
| **Knowledge 文件上傳** | [KnowledgeWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/KnowledgeWorkspace.vue) | `.txt` `.md` | 5 MB (前端只接受 txt/md) | ✅ UTF-8 + injection scan + malware |
| **HMI 圖片上傳** | [HMIWorkspace.vue](file:///c:/project/Mold-AI-Platform/apps/web/src/components/HMIWorkspace.vue) | `.png` `.jpg` | 10 MB | ✅ 格式檢查 |

> [!NOTE]
> 後端其實還支援 Knowledge 的 `.pdf` 和 `.docx` 格式（含 PDF 加密偵測、DOCX macro 偵測、外部連結偵測等安全檢查），但前端 `accept` 屬性只開放了 `.txt` 和 `.md`。

---

## 二、逐一分析

### 2.1 CAD 上傳 ✅ 已做得不錯

**優點：**
- ✅ 有 `accept=".step,.stp,.stl"` 限制選檔
- ✅ 自動從檔名產生 Artifact name（`chooseFile` 裡去除副檔名）
- ✅ 有 idempotency key 防重複提交
- ✅ 有 Job 進度條顯示（state + stage + progress%）
- ✅ 有 `missingUploadFields` 計數器即時反饋未填必要欄位
- ✅ Upload 模式選擇清楚（Quick Analysis vs Governed Archive 的 radio card）
- ✅ 版本管理：New artifact vs New version 的分流邏輯
- ✅ 有 toast 通知成功/失敗
- ✅ 有 warning 顯示（如 "unassigned" / "duplicate content" / "malware screener"）

**需要優化的項目：**

| # | 問題 | 嚴重度 | 現狀 | 影響 |
|---|------|-------|------|------|
| **1** | **沒有前端檔案大小檢查** | 🔴 高 | 後端有 200 MB 限制 ([settings.py](file:///c:/project/Mold-AI-Platform/services/platform-api/mold_platform/settings.py#L95))，但前端 `chooseFile` 只做 `selectedFile = input.files[0]`，完全不檢查 size | 使用者選了 300 MB 的檔案會等很久上傳才收到 HTTP 413 錯誤 |
| **2** | **沒有前端檔案大小顯示** | 🟡 中 | 選了檔案後沒有任何 UI 顯示「已選擇 xxx.step (12.5 MB)」 | 使用者不確定是否選對了檔案 |
| **3** | **沒有拖放上傳（Drag & Drop）** | 🟡 中 | 只有原生 `<input type="file">`，沒有 drop zone | 工程師習慣從檔案總管拖放 |
| **4** | **上傳中沒有進度條** | 🔴 高 | `uploading.value = true` 期間只有按鈕文字變 "Submitting..."，大檔案（~200 MB）可能上傳很久，沒有 upload progress | 使用者以為卡住了 |
| **5** | **成功後不會清空表單** | 🟡 中 | 上傳成功後 `selectedFile`、`artifactName` 等欄位不會重置，可能導致誤重複提交 | UX 不符預期 |

---

### 2.2 Knowledge 文件上傳 ⚠️ 有明顯缺口

**優點：**
- ✅ 有 `missingUploadFields` 計數器
- ✅ 有 `fileError` / `titleError` 即時驗證錯誤訊息
- ✅ `uploadAttempted` flag 控制何時顯示驗證錯誤（避免一載入就滿地紅）
- ✅ 有 toast 通知
- ✅ 有 Job 進度追蹤

**需要優化的項目：**

| # | 問題 | 嚴重度 | 現狀 | 影響 |
|---|------|-------|------|------|
| **6** | **前端只接受 txt/md，但後端支援 PDF 和 DOCX** | 🔴 高 | 前端 `accept=".txt,.md,text/plain,text/markdown"`，但後端 [knowledge.py L42-49](file:///c:/project/Mold-AI-Platform/services/platform-api/platform_core/knowledge.py#L42-L49) 支援 `.pdf` 和 `.docx` 含完整安全掃描 | 使用者需要上傳 PDF/DOCX 但被前端擋住 |
| **7** | **沒有前端檔案大小檢查** | 🟡 中 | 後端限制 5 MB ([settings.py L96](file:///c:/project/Mold-AI-Platform/services/platform-api/mold_platform/settings.py#L96))，前端不檢查 | 文字文件通常很小，但 PDF 容易超過 |
| **8** | **沒有檔案大小/格式限制提示** | 🟡 中 | 只顯示 "Accepted formats: UTF-8 TXT or Markdown." 的 helper text | 使用者不知道大小限制 |
| **9** | **成功後不清空表單** | 🟡 中 | 上傳成功後 `uploadAttempted` 設為 false，但 `file`、`title` 不重置 | 可能再次提交相同內容 |

---

### 2.3 HMI 圖片上傳 ⚠️ 缺乏防護

**優點：**
- ✅ 有 `accept="image/png,image/jpeg"` 限制
- ✅ 選檔後立即顯示圖片預覽（`URL.createObjectURL`）
- ✅ 有 toast 通知
- ✅ Demo 模式可載入內建圖片

**需要優化的項目：**

| # | 問題 | 嚴重度 | 現狀 | 影響 |
|---|------|-------|------|------|
| **10** | **沒有前端大小檢查** | 🟡 中 | 後端限制 10 MB ([settings.py L98](file:///c:/project/Mold-AI-Platform/services/platform-api/mold_platform/settings.py#L98))，helper 文字寫了 "maximum 10 MB" 但前端不攔截 | 使用者上傳高解析度照片可能超過限制 |
| **11** | **沒有圖片尺寸（解析度）提示** | 🟡 低 | 後端會記錄 image_width / image_height，但前端沒有建議的解析度範圍 | 使用者可能上傳過小或過大的圖片影響擷取精度 |
| **12** | **沒有上傳確認步驟** | 🟡 中 | 選圖 → 按 "Extract four parameters" 直接發送，沒有「確認上傳？」的保護 | 誤觸風險較高 |

---

## 三、跨入口共通問題

以下問題在所有三個上傳入口都存在：

### 3.1 🔴 前端完全不做檔案大小前置檢查

**現狀**：三個入口的 `onFile` / `chooseFile` 函式都只做：
```ts
selectedFile.value = input.files?.[0] || null;  // CAD
file.value = (event.target as HTMLInputElement).files?.[0] || null;  // Knowledge
```
完全不檢查 `file.size`。

**後果**：超大檔案會上傳到 server 才被拒絕（HTTP 413），浪費使用者等待時間和網路頻寬。

**建議**：在 `chooseFile` / `onFile` 中加入：
```ts
if (file.size > MAX_SIZE) {
  error.value = t("File size exceeds {limit} MB limit.", { limit: MAX_MB });
  selectedFile.value = null;
  return;
}
```

---

### 3.2 🟡 缺乏「選檔摘要」回饋

**現狀**：除了 HMI（有圖片預覽）外，CAD 和 Knowledge 選了檔案後沒有任何視覺確認。

**建議**：選檔後顯示：
```
📄 housing-revision-B.step
12.4 MB · STEP format · last modified 2026-08-28
```

---

### 3.3 🟡 沒有 Drag & Drop 上傳區域

**現狀**：全部使用原生 `<input type="file">`。

**建議**：新增一個共用的 `FileDropZone.vue` 元件，支援：
- 拖放檔案到虛線框區域
- 點擊也可觸發檔案選擇器
- 拖放中有視覺反饋（框線變色、顯示 "放開以上傳" 文字）

---

### 3.4 🟡 上傳中沒有實際進度

**現狀**：上傳期間只有按鈕變 "Submitting..." / "Uploading..."，沒有 upload 進度百分比。

**原因**：使用 `fetch()` API，不支援 upload progress。需用 `XMLHttpRequest` 的 `upload.onprogress` 事件。

**影響**：CAD 檔案可達 200 MB，在網路較慢的情況下，使用者會以為系統卡住。

---

### 3.5 🟡 上傳成功後不自動清空表單

**現狀**：上傳成功後表單欄位保留原值，使用者需手動清空才能上傳新檔案。

**建議**：成功後自動重置 `file` / `selectedFile`、`title` / `artifactName` 等欄位，或至少提供一個 "上傳新檔案" 按鈕。

---

## 四、優先改良建議

| 優先級 | 項目 | 影響範圍 | 預估工作量 |
|--------|------|---------|----------|
| 🔴 最高 | **前端檔案大小前置檢查** | CAD / Knowledge / HMI 三個入口 | 小（每個 ~5 行） |
| 🔴 高 | **Knowledge 開放 PDF/DOCX 格式** | Knowledge 上傳表單 | 小（改 `accept` 屬性 + helper 文字） |
| 🟠 中高 | **選檔後顯示檔案摘要** | CAD / Knowledge | 小（新增 ~10 行 template） |
| 🟡 中 | **CAD 上傳進度條**（用 XMLHttpRequest） | CAD 上傳 | 中（需改 `api/cad.ts` 的 uploadCAD） |
| 🟡 中 | **新增 `FileDropZone.vue` 元件** | 全域共用 | 中（新元件 + 樣式） |
| 🟡 中 | **上傳成功後清空表單** | CAD / Knowledge | 小（新增 reset 函式） |
| 🟢 低 | **HMI 上傳確認步驟** | HMI 上傳 | 小 |
| 🟢 低 | **圖片解析度建議** | HMI 上傳 | 小 |

---

## Open Questions

1. **Knowledge 格式擴充**：後端已支援 PDF 和 DOCX 的安全解析（含加密偵測、macro 偵測、外部連結偵測），是否現在就開放前端接受 PDF/DOCX？

2. **拖放上傳**：是否需要新增 `FileDropZone.vue` 共用元件？如果是的話，要同時更新 CAD、Knowledge、HMI 三個入口嗎？

3. **上傳進度條**：CAD 檔案可達 200 MB，是否需要從 `fetch()` 改為 `XMLHttpRequest` 來顯示上傳進度？這會影響 `api/cad.ts` 的 `uploadCAD` 函式。

4. **表單重置策略**：上傳成功後是要自動清空所有欄位，還是保留 Dataset/Product Type 等常用設定只清空檔案相關欄位？

## 已確認決策（2026-08-30）

1. Knowledge 前端開放 `.pdf` 與 `.docx`，沿用後端既有安全解析與 5 MB 上限。
2. 建立共用 `FileDropZone.vue`，同時套用 CAD、Knowledge、HMI 三個入口。
3. CAD 改用可回報 upload progress 的傳輸實作，顯示 200 MB 大檔實際上傳進度。
4. 成功後只清除檔案、由檔名衍生的名稱與檔案選擇狀態；保留 Dataset、Product Type、Material、文件分類與語言等常用設定。
