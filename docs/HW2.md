# CoursePilot 作業 2 技術說明

## 專案延續與架構

學生輸入查詢、排程或重新排程目標，Agent 讀取已確認的課程任務與時段，依當前狀態選擇工具，再用驗證結果決定回傳完整計畫、部分計畫或要求補件。本階段對應作業 1 的 FR-04（可用時段輸入部分）、FR-07、FR-08（以更新後的資料重新規劃）、FR-09（期限缺漏及時段不足）及 FR-10（追蹤部分）。輸入以 JSON 模擬作業 1 的已確認任務，source 欄位保留原始人工標註。

```mermaid
flowchart TD
  U["使用者：目標＋任務與時段"] --> D["Agent：讀取資料工具"]
  D --> G{"依目標與資料狀態決策"}
  G -->|查詢| L["回傳任務及來源"]
  G -->|資料缺漏| A["請補期限或時段"]
  G -->|可規劃| P["排程工具"]
  P --> V["獨立限制驗證工具"]
  V -->|驗證不通過| E["拒絕候選排程"]
  V -->|驗證通過| R["完整計畫或部分計畫＋不足工時"]
```

除使用者操作的終端外，Agent、工具與測試都由一個 Podman 容器執行。一次請求的狀態包含目標、資料、候選排程、檢查結果與事件追蹤。這是 goal-based、state-based Agent：依工具觀察走不同分支。未採用 LLM ReAct，因為這一階段只有三個明確目標與有限的工具順序，程式化分支即可驗證。工具追蹤採用 Decision → Tool Call → Observation 格式，並非模型思考紀錄。LLM、RAG、相依任務、自動擷取、長期記憶及網頁版留待後續。

## 工具定義

| 名稱 | 目的 | 輸入 | 輸出 | 錯誤處理 |
|---|---|---|---|---|
| `load_case` | 實際讀取並驗證檔案 | JSON 路徑 | 任務與時段 | 檔案或格式錯誤記錄 observation，回傳 `data_error` |
| `build_schedule` | 依較早期限優先配置，每塊 30 分鐘 | 已確定期限的待辦、已驗證時段 | 包含 ID、開始及結束的區塊 | 無合法區塊時保留部分或空計畫，交由驗證器計算未排工時 |
| `validate_schedule` | 獨立檢查候選計畫 | 待辦、時段、候選區塊 | `valid`、`errors`、`remaining_minutes` | 拒絕未知任務、重疊、過期、超額或非法時段；Agent 不輸出錯誤候選 |

排程工具將重疊可用時段轉成不重複的半小時區塊，再將可分割任務依期限排序。驗證不依賴排程的結果標記，會重新計算每項工作配置量；沒有錯誤但尚有未安排工時時，狀態為 `insufficient`。

## 實際完整追蹤

對應 [原始 JSON](../evidence/success.json)；由 CLI 實際執行產生。

| 步驟 | 事件 | 觀察到的內容 |
|---|---|---|
| 1 | User Input | `plan --case success` |
| 2–4 | Decision → Tool Call → Observation | 呼叫 `load_case`；讀到 DB01（90 分鐘）、AI01（60 分鐘）及兩段可用時段 |
| 5–7 | Decision → Tool Call → Observation | 期限與時段均已提供，呼叫 `build_schedule`；取得五個 30 分鐘區塊 |
| 8–10 | Decision → Tool Call → Observation | 呼叫 `validate_schedule`；取得 `valid: true`，無錯誤、無未排工時 |
| 11–12 | Decision → Result | 採用完整計畫，`status: ok`；DB01 三塊、AI01 兩塊，保留任務來源 |

## 失敗情境與測試證據

| 情境 | 原因 | 處理及實際結果 |
|---|---|---|
| [期限不明](../evidence/unknown.json) | 公告只有「下週五」，沒有參考日期 | 讀取後停止排程，回傳 `needs_deadline`；請確認 DB01 日期後重跑 |
| [期限前容量不足](../evidence/short.json) | 雖有 90 分鐘可用時間，但期限前只有 30 分鐘 | 回傳 `insufficient`，僅列合法的 30 分鐘區塊，DB01 尚缺 60 分鐘；建議增加期限前的可用時段 |
| 候選計畫錯誤 | 測試注入未知任務的區塊 | Agent 回傳 `invalid_schedule`，不提供錯誤候選；驗證器也另測重疊與超期 |
| [重新規劃](../evidence/changed.json)（對照成功） | DB01 已完成且時段改成週四 | `ok`；只排 AI01，使用新時段 |

[本機測試紀錄](../evidence/tests.txt)：10 項通過，涵蓋成功追蹤、重新規劃、資料錯誤、未確認期限、容量不足與驗證分支。容器驗證尚待具備 Podman 的環境或 GitHub Actions 執行。

## 評分對照

| 項目 | 檢查位置 |
|---|---|
| Working Agent 6% | `coursepilot.py`、`Containerfile`、README 執行指令 |
| Tool / Workflow / Planning 5% | 工具定義、架構圖、完整追蹤 |
| 功能完整性 3% | 任務查詢、首次排程、重新規劃測試 |
| Error Handling 2% | 失敗情境表與錯誤觀察 |
| Testing / Failure Evidence 2% | `data/`、`tests/`、`evidence/` |
| README / 執行環境 2% | `README.md`、Podman CI |
