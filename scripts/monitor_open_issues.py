#!/usr/bin/env python3
"""monitor_open_issues.py — §17 change-driven experiment (NOT the Drive).

Prints a deterministic snapshot of open issue numbers. Hermes hashes the
output; the agent wakes ONLY when the bytes change:
    M(t) != M(t-1)   (change-driven)
vs the goal-driven gate in github_issue_drive.py:
    M(t) != M*       (goal-driven)

No timestamps — output must be byte-stable when nothing changed.
"""
import json
import subprocess
import sys

REPO = "SeungKil-Paek/goodwill-harness"
try:
    out = subprocess.run(
        ["gh", "issue", "list", "-R", REPO, "--state", "open",
         "--limit", "200", "--json", "number"],
        capture_output=True, text=True, timeout=30,
    )
    if out.returncode != 0:
        sys.exit(1)  # monitor failure: Hermes keeps old hash, retries next tick
    nums = sorted(i["number"] for i in json.loads(out.stdout or "[]"))
    print("open_issues:" + ",".join(str(n) for n in nums))
except Exception:
    sys.exit(1)
