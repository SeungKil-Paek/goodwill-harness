"""Unit tests for github_issue_drive.py (implementation.md §20).

No network, no LLM: gh output is faked by monkeypatching gh_json.
Run: python3 -m unittest tests/test_github_issue_drive.py
"""

import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

import github_issue_drive as drv  # noqa: E402

BASE_CFG = {
    "repository": "o/r",
    "required_labels": ["agent"],
    "excluded_labels": ["human", "do-not-automate"],
    "desired": 0,
    "threshold": 0,
    "selection": "lowest_number",
}


def issue(n, labels, state="open", created="2026-08-01T00:00:00Z"):
    return {
        "number": n,
        "title": f"issue {n}",
        "state": state,
        "labels": [{"name": l} for l in labels],
        "createdAt": created,
    }


def fake_gh(issues):
    def _fake(args, timeout=30):
        return issues
    return _fake


class WakeGateTests(unittest.TestCase):
    def setUp(self):
        self.cfg = dict(BASE_CFG)

    def _drive(self, issues):
        drv.gh_json = fake_gh(issues)
        return drv.compute_drive(self.cfg)

    def test_no_issue_outputs_wake_false(self):
        out = self._drive([])
        self.assertIs(out["wakeAgent"], False)

    def test_actionable_issue_outputs_wake_true(self):
        out = self._drive([issue(7, ["agent"])])
        self.assertIs(out["wakeAgent"], True)
        self.assertEqual(out["context"]["measure"], 1)
        self.assertEqual(out["context"]["selected_issue"]["number"], 7)

    def test_excluded_issue_does_not_trigger(self):
        out = self._drive([
            issue(1, ["agent", "human"]),
            issue(2, ["agent", "do-not-automate"]),
            issue(3, ["needs-work"]),
            issue(4, ["agent"], state="closed"),
        ])
        self.assertIs(out["wakeAgent"], False)

    def test_measure_is_correct(self):
        out = self._drive([
            issue(1, ["agent"]),
            issue(2, ["agent", "human"]),
            issue(3, ["agent"]),
        ])
        self.assertEqual(out["context"]["measure"], 2)

    def test_drive_is_correct(self):
        out = self._drive([issue(1, ["agent"]), issue(2, ["agent"])])
        self.assertEqual(out["context"]["drive"], out["context"]["measure"] - out["context"]["desired_state"])
        self.assertEqual(out["context"]["drive"], 2)

    def test_output_is_valid_wakeAgent_json(self):
        """Hermes parses ONLY the last non-empty stdout line as JSON."""
        drv.gh_json = fake_gh([issue(5, ["agent"])])
        code = drv.main()
        self.assertEqual(code, 0)  # gate failures must exit 0, never wake by error

    def test_selection_lowest_number(self):
        out = self._drive([issue(9, ["agent"]), issue(3, ["agent"])])
        self.assertEqual(out["context"]["selected_issue"]["number"], 3)

    def test_selection_oldest(self):
        self.cfg["selection"] = "oldest"
        out = self._drive([
            issue(9, ["agent"], created="2026-08-10T00:00:00Z"),
            issue(3, ["agent"], created="2026-08-20T00:00:00Z"),
        ])
        self.assertEqual(out["context"]["selected_issue"]["number"], 9)

    def test_gate_error_fails_closed(self):
        def boom(args, timeout=30):
            raise RuntimeError("network down")
        drv.gh_json = boom
        with self.assertRaises(RuntimeError):  # compute_drive raises...
            drv.compute_drive(self.cfg)
        code = drv.main()  # ...but main() catches, prints gate-false, exits 0
        self.assertEqual(code, 0)


if __name__ == "__main__":
    unittest.main(verbosity=2)
