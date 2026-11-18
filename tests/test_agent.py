import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from coursepilot import Agent, FIXTURES, load_case, build_schedule, validate_schedule


class AgentTests(unittest.TestCase):
    def run_case(self, goal, name):
        return Agent().run(goal, FIXTURES / f"{name}.json")

    def test_plan_and_full_trace(self):
        out = self.run_case("plan", "success")
        self.assertEqual(out["status"], "ok")
        self.assertEqual([b["id"] for b in out["schedule"]], ["DB01"] * 3 + ["AI01"] * 2)
        self.assertEqual(out["remaining_minutes"], {})
        self.assertEqual([e["tool"] for e in out["trace"] if e["event"] == "tool_call"],
                         ["load_case", "build_schedule", "validate_schedule"])
        self.assertEqual(out["trace"][-2]["action"], "show_complete")

    def test_replan_uses_new_window_and_skips_completed_task(self):
        out = self.run_case("replan", "changed")
        self.assertEqual(out["status"], "ok")
        self.assertEqual({b["id"] for b in out["schedule"]}, {"AI01"})
        self.assertEqual(out["schedule"][0]["start"], "2026-11-26T19:00:00+08:00")

    def test_list_preserves_sources_and_does_not_schedule(self):
        out = self.run_case("tasks", "success")
        self.assertIn("§2", out["tasks"][0]["source"])
        self.assertEqual([e["tool"] for e in out["trace"] if e["event"] == "tool_call"], ["load_case"])

    def test_unknown_due_stops_before_scheduler(self):
        out = self.run_case("plan", "unknown")
        self.assertEqual(out["status"], "needs_deadline")
        self.assertEqual(out["task_ids"], ["DB01"])
        self.assertNotIn("schedule", out)

    def test_insufficient_reports_only_capacity_before_deadline(self):
        out = self.run_case("plan", "short")
        self.assertEqual(out["status"], "insufficient")
        self.assertEqual(out["remaining_minutes"], {"DB01": 60})
        self.assertEqual(out["schedule"][0]["end"], "2026-11-25T21:00:00+08:00")
        self.assertEqual(len(out["schedule"]), 1)

    def test_missing_file_records_observation(self):
        out = self.run_case("plan", "not-present")
        self.assertEqual(out["status"], "data_error")
        self.assertTrue(any("error" in e for e in out["trace"] if e["event"] == "observation"))

    def test_bad_json_or_schema_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "bad.json"
            for content in ("{", '{"tasks":[null],"windows":[]}'):
                with self.subTest(content=content):
                    path.write_text(content, encoding="utf-8")
                    self.assertEqual(Agent().run("plan", path)["status"], "data_error")

    def test_no_windows_and_no_pending_are_distinct(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "case.json"
            data = load_case(FIXTURES / "success.json")
            data["windows"] = []
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(Agent().run("plan", path)["status"], "needs_windows")
            data["tasks"] = []
            path.write_text(json.dumps(data), encoding="utf-8")
            self.assertEqual(Agent().run("plan", path)["status"], "no_pending")

    def test_validator_rejects_overlap_and_late_block(self):
        data = load_case(FIXTURES / "short.json")
        block = {"id": "DB01", "start": "2026-11-25T21:00:00+08:00",
                 "end": "2026-11-25T21:30:00+08:00"}
        errors = validate_schedule(**data, blocks=[block, block])["errors"]
        self.assertIn("重複占用時段", errors)
        self.assertIn("超過截止日期", errors)

    def test_agent_rejects_invalid_candidate_instead_of_showing_it(self):
        with patch("coursepilot.build_schedule", new=build_invalid_schedule):
            out = self.run_case("plan", "success")
        self.assertEqual(out["status"], "invalid_schedule")
        self.assertNotIn("schedule", out)


def build_invalid_schedule(**_):
    return [{"id": "unknown", "start": "2026-11-23T19:00:00+08:00",
             "end": "2026-11-23T19:30:00+08:00"}]


if __name__ == "__main__":
    unittest.main()
