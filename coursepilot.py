"""CoursePilot HW2: goal-directed planning with observable tool calls."""
import argparse
import json
import sys
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path

STEP = timedelta(minutes=30)
FIXTURES = Path(__file__).with_name("data")


def require(test, message):
    if not test:
        raise ValueError(message)


def timestamp(value):
    require(isinstance(value, str), "時間須為 ISO 8601 字串")
    t = datetime.fromisoformat(value)
    require(t.utcoffset() == timedelta(hours=8) and t.minute in (0, 30)
            and not (t.second or t.microsecond), "時間須含 +08:00，並對齊 30 分鐘")
    return t


def load_case(path):
    data = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    require(isinstance(data, dict), "資料須為 JSON 物件")
    tasks, windows = data.get("tasks"), data.get("windows")
    require(isinstance(tasks, list) and len(tasks) <= 100, "tasks 須為最多 100 項的陣列")
    require(isinstance(windows, list) and len(windows) <= 100, "windows 須為最多 100 項的陣列")
    ids = set()
    for task in tasks:
        require(isinstance(task, dict), "任務須為物件")
        for key in ("id", "title", "source"):
            require(isinstance(task.get(key), str) and task[key].strip(), f"{key} 不可為空")
        require(task["id"] not in ids, "任務 ID 不得重複")
        ids.add(task["id"])
        require(task.get("status") in ("pending", "done"), "status 須為 pending 或 done")
        minutes = task.get("minutes")
        require(type(minutes) is int and 30 <= minutes <= 10080 and minutes % 30 == 0,
                "minutes 須為 30 至 10080 的 30 倍數")
        if task.get("due") is not None:
            timestamp(task["due"])
    bounds = []
    for w in windows:
        require(isinstance(w, dict), "時段須為物件")
        start, end = timestamp(w.get("start")), timestamp(w.get("end"))
        require(start < end <= start + timedelta(days=7), "時段須為正長度且不超過七天")
        bounds.append((start, end))
    require(not bounds or max(e for _, e in bounds) - min(s for s, _ in bounds)
            <= timedelta(days=7), "本版只接受七天內的可用時段")
    return {"tasks": tasks, "windows": windows}


def dayslot_set(windows):
    slots = set()
    for w in windows:
        start, end = timestamp(w["start"]), timestamp(w["end"])
        while start < end:
            slots.add(start)
            start += STEP
    return slots


def build_schedule(tasks, windows):
    free = sorted(dayslot_set(windows))
    queue = sorted(tasks, key=lambda t: (timestamp(t["due"]), t["id"]))
    blocks = []
    for task in queue:
        for _ in range(task["minutes"] // 30):
            if not free or free[0] + STEP > timestamp(task["due"]):
                break
            start = free.pop(0)
            blocks.append({"id": task["id"], "start": start.isoformat(),
                           "end": (start + STEP).isoformat()})
    return blocks


def validate_schedule(tasks, windows, blocks):
    by_id = {t["id"]: t for t in tasks}
    slots = dayslot_set(windows)
    occupied, minutes, errors = set(), Counter(), []
    for block in blocks:
        if not isinstance(block, dict) or not isinstance(block.get("id"), str):
            errors.append("區塊格式不正確")
            continue
        task = by_id.get(block["id"])
        try:
            start, end = timestamp(block.get("start")), timestamp(block.get("end"))
        except ValueError as exc:
            errors.append(str(exc))
            continue
        if not task or start not in slots or end - start != STEP:
            errors.append("未知任務或區塊不在可用時段內")
            continue
        if start in occupied:
            errors.append("重複占用時段")
        if end > timestamp(task["due"]):
            errors.append("超過截止日期")
        occupied.add(start)
        minutes[task["id"]] += 30
    remaining = {}
    for t in tasks:
        gap = t["minutes"] - minutes[t["id"]]
        if gap < 0:
            errors.append("配置超出所需工時")
        if gap > 0:
            remaining[t["id"]] = gap
    return {"valid": not errors, "errors": errors, "remaining_minutes": remaining}


@dataclass
class Agent:
    trace: list = field(default_factory=list, init=False)

    def record(self, event, **fields):
        self.trace.append({"event": event, **fields})

    def call(self, tool, **args):
        self.record("tool_call", tool=tool.__name__, input=args)
        try:
            result = tool(**args)
        except (OSError, ValueError, TypeError) as exc:
            self.record("observation", tool=tool.__name__, error=str(exc))
            raise
        self.record("observation", tool=tool.__name__, output=result)
        return result

    def run(self, goal, path):
        self.trace.clear()
        self.record("user_input", goal=goal, case=path.name)
        self.record("decision", action="load_case", reason="先取得任務狀態及可用時段")
        # JSON-safe path in the trace; load_case accepts a Path-compatible string.
        try:
            data = self.call(load_case, path=str(path))
        except (OSError, ValueError, TypeError):
            code = "data_error"
            self.record("decision", action="stop", reason="無法讀取或驗證資料")
            return self.finish(code, "請檢查檔案存在且符合資料格式。")
        pending = [t for t in data["tasks"] if t["status"] == "pending"]
        if goal == "tasks":
            self.record("decision", action="show_tasks", reason="使用者要求查詢任務")
            return self.finish("ok", "已列出任務與來源。", tasks=data["tasks"])
        if not pending:
            self.record("decision", action="stop", reason="沒有待排任務")
            return self.finish("no_pending", "目前沒有待排任務。")
        unknown = [t["id"] for t in pending if t.get("due") is None]
        if unknown:
            self.record("decision", action="ask_deadline", reason="有任務缺少已確認期限")
            return self.finish("needs_deadline", "請確認期限後再排程。", task_ids=unknown)
        if not data["windows"]:
            self.record("decision", action="ask_windows", reason="未提供可用時段")
            return self.finish("needs_windows", "請先提供可用時段。")
        args = {"tasks": pending, "windows": data["windows"]}
        self.record("decision", action="build_schedule", reason="期限與可用時段均已提供，只安排未完成任務")
        blocks = self.call(build_schedule, **args)
        self.record("decision", action="validate_schedule", reason="檢查候選計畫，不直接採用工具輸出")
        check = self.call(validate_schedule, **args, blocks=blocks)
        if not check["valid"]:
            self.record("decision", action="reject_schedule", reason="候選計畫違反硬限制")
            return self.finish("invalid_schedule", "驗證未通過，已拒絕候選計畫。", errors=check["errors"])
        payload = {"schedule": blocks, "remaining_minutes": check["remaining_minutes"],
                   "tasks": pending}
        if check["remaining_minutes"]:
            self.record("decision", action="show_partial", reason="計畫符合硬限制，但仍有工作未安排")
            return self.finish("insufficient", "只完成部分排程；請增加期限前的可用時段或調整工時。", **payload)
        self.record("decision", action="show_complete", reason="全部待辦已配置且通過驗證")
        return self.finish("ok", "排程完成；請檢視時間區塊與任務來源。", **payload)

    def finish(self, status, message, **details):
        self.record("result", status=status, message=message)
        return {"status": status, "message": message, **details, "trace": self.trace.copy()}


def main():
    parser = argparse.ArgumentParser(description="CoursePilot 作業 2：課程任務排程 Agent")
    parser.add_argument("goal", choices=["tasks", "plan", "replan"])
    cases = parser.add_mutually_exclusive_group()
    cases.add_argument("--case", choices=["success", "changed", "unknown", "short"], default="success")
    cases.add_argument("--file", type=Path, help="自備 JSON 任務與時段資料")
    args = parser.parse_args()
    output = Agent().run(args.goal, args.file or FIXTURES / f"{args.case}.json")
    print(json.dumps(output, ensure_ascii=False, indent=2))
    return 2 if output["status"] in {"data_error", "invalid_schedule"} else 0


if __name__ == "__main__":
    sys.exit(main())
