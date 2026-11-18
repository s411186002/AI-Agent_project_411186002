# CoursePilot 個人專案｜作業 2

CoursePilot 將已確認的課程任務與可用時段轉成可檢查的學習計畫。這一版是在作業 1 基礎上完成的可執行原型：可查任務、產生排程，或依新的時段與完成狀態重新安排。使用 CLI 及 JSON，無需模型、API 金鑰或外部 Python 套件。

## 1. 用 Podman 執行

系統需求：Podman；首次建置需能拉取 Python 3.12 slim 映像。Windows 或 macOS 若尚未建立 Podman VM，執行 `podman machine init --now`；已有但停止的 VM 執行 `podman machine start`。Linux 可直接使用 Podman。見 [Podman 官方說明](https://docs.podman.io/en/stable/markdown/podman-machine-init.1.html)。

在含有 Containerfile 的目錄執行：

```text
podman build -t coursepilot:hw2 .
podman run --rm --network none coursepilot:hw2 tasks --case success
podman run --rm --network none coursepilot:hw2 plan --case success
podman run --rm --network none coursepilot:hw2 replan --case changed
podman run --rm --network none coursepilot:hw2 plan --case unknown
podman run --rm --network none coursepilot:hw2 plan --case short
podman run --rm --network none --entrypoint python coursepilot:hw2 -m unittest discover -s tests -v
```

預期狀態依序為 `ok`、`ok`、`ok`、`needs_deadline`、`insufficient`。執行時網路可關閉。查詢 VM 狀態用 `podman machine list`；若卡在拉取映像，先檢查 registry 連線。出現 `data_error` 時，查看 trace 中的 observation。輸入待確認與部分排程屬正常業務結果，退出碼為 0；資料錯誤或排程驗證失敗退出碼為 2。

## 2. 調整資料再重新排程

複製 `data/changed.json` 為 `my-case.json`，將已完成工作標為 `done`，再修改可用時段。以本機 Python 3.12 快速開發或查錯：

```text
python -X utf8 coursepilot.py replan --file my-case.json
python -X utf8 -m unittest discover -s tests -v
```

正式容器演示可直接使用內建案例。若要將自備資料放入容器，可在映像後用唯讀掛載（Linux Bash 範例，Podman VM 上需使用 VM 可讀取的路徑）：

```bash
podman run --rm --network none -v "$(pwd)/my-case.json:/tmp/my-case.json:ro,Z" coursepilot:hw2 replan --file /tmp/my-case.json
```

- `tasks`：每筆包含唯一 `id`、`title`、`source`、`status`（`pending`／`done`）、`minutes`（正的 30 倍數）及 `due`（期限不明可用 `null`）。
- `windows`：每筆包含 `start`、`end`；使用 ISO 8601、`+08:00`，對齊整點或半點。時段總範圍最多七天，重疊時段會去重。請事先扣除打工等固定活動。
- 輸出為 JSON，含 `status`、`message`、適用時的 `schedule`／`remaining_minutes`，以及按順序排列的 `trace`。此版讀取最新輸入快照，不會修改輸入或儲存計畫。

## 3. 檢閱與提交

- [作業 2 技術說明](docs/HW2.md)：架構、工具輸入輸出、完整追蹤摘要、失敗情境及評分對照。
- [測試結果](evidence/tests.txt)與原始追蹤：[正常排程](evidence/success.json)、[重新排程](evidence/changed.json)、[期限不明](evidence/unknown.json)、[期限前時段不足](evidence/short.json)。
- 本機證據使用 Windows 上的 Python 3.12.14。此工作環境未安裝可用的 Podman，尚未實測容器。上傳後的 [Podman workflow](.github/workflows/podman.yml) 會建置映像、在容器內跑測試、檢查三個流程狀態並上傳 JSON 追蹤；請確認成功後再提交連結。
- 課程要求於 **11/22** 繳交，將本目錄內容（含隱藏的 `.github`）作為 GitHub repository 根目錄。如果已經有同一學期專案的 repository，沿用該 repository 並讓作業 2 的 README／CI 路徑與擺放位置一致。確認老師與助教可讀，再依課程管道分享 repository link。
