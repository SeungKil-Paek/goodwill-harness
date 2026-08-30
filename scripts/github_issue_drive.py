#!/usr/bin/env python3
"""github_issue_drive.py — Artificial Will motivation gate for Hermes cron.

Responsibility (implementation.md §8, nothing more):
  1. observe GitHub world state via `gh` CLI
  2. filter actionable issues
  3. compute M(t)
  4. compute D(t) = M(t) - M*
  5. decide wakeAgent
  6. print context

Never calls an LLM. Never reasons. Deterministic.

Contract with Hermes (verified against v0.20.6 cron/scheduler.py):
  - _parse_wake_gate() reads ONLY the last non-empty stdout line as JSON.
  - Only literal `"wakeAgent": false` skips the agent run.
  - Non-zero exit injects a Script Error report and wakes the agent anyway,
    so every failure path must still print a final JSON line and exit 0.
"""

import json
import os
import subprocess
import sys
from pathlib import Path

# Hermes copies installed gates into ~/.hermes/scripts/; config ships next to
# the script. Env override exists for dev runs from the source repo.
_DEFAULT_CONFIG = Path(__file__).resolve().parent / "github_issue_drive.config.yaml"
CONFIG_PATH = Path(os.getenv("GOODWILL_CONFIG", _DEFAULT_CONFIG))


# --- config -------------------------------------------------------------------
# Tiny flat YAML reader (2 levels of indent, scalars and simple lists).
# A full YAML dependency is not justified for a PoC gate (spec §19: keep it
# simple). Falls back to defaults if the file is missing.

def load_config(path: Path) -> dict:
    cfg = {
        "repository": "SeungKil-Paek/goodwill-harness-target",
        "required_labels": ["agent"],
        "excluded_labels": ["human", "do-not-automate"],
        "desired": 0,
        "threshold": 0,
        "selection": "lowest_number",
    }
    try:
        text = path.read_text()
    except OSError:
        return cfg
    section = None
    key = None
    for raw in text.splitlines():
        if not raw.strip() or raw.strip().startswith("#"):
            continue
        indent = len(raw) - len(raw.lstrip(" "))
        line = raw.strip()
        if indent == 0:
            section = line.rstrip(":")
            key = None
            continue
        if line.startswith("- "):
            if key is not None:
                cfg[key].append(line[2:].strip().strip('"').strip("'"))
            continue
        if ":" in line:
            k, _, v = line.partition(":")
            k, v = k.strip(), v.strip().strip('"').strip("'")
            if section == "github" and k == "repository":
                cfg["repository"] = v
            elif section == "issue_filter" and k == "required_labels":
                key = "required_labels"
                cfg[key] = []
            elif section == "issue_filter" and k == "excluded_labels":
                key = "excluded_labels"
                cfg[key] = []
            elif section == "desired_state" and k == "actionable_open_issues":
                cfg["desired"] = int(v)
            elif section == "drive" and k == "threshold":
                cfg["threshold"] = int(v)
            elif section == "drive" and k == "selection":
                cfg["selection"] = v
            else:
                key = None
    return cfg


# --- world state ------------------------------------------------------------

def gh_json(args: list, timeout: int = 30):
    """Run gh, parse stdout JSON. Raises RuntimeError on failure."""
    env = dict(os.environ)
    env.setdefault("GH_PAGER", "")
    try:
        proc = subprocess.run(
            ["gh"] + args,
            capture_output=True, text=True, timeout=timeout, env=env,
        )
    except FileNotFoundError:
        raise RuntimeError("gh CLI not found on PATH")
    except subprocess.TimeoutExpired:
        raise RuntimeError(f"gh {' '.join(args[:2])} timed out")
    if proc.returncode != 0:
        raise RuntimeError(f"gh failed ({proc.returncode}): {proc.stderr.strip()[:300]}")
    try:
        return json.loads(proc.stdout or "[]")
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"gh output not JSON: {exc}")


def is_actionable(issue: dict, cfg: dict) -> bool:
    labels = {l["name"].lower() for l in issue.get("labels", [])}
    if issue.get("state") != "open":
        return False
    if not all(r.lower() in labels for r in cfg["required_labels"]):
        return False
    if labels & {e.lower() for e in cfg["excluded_labels"]}:
        return False
    return True


def select_issue(candidates: list, mode: str) -> dict:
    if mode == "oldest":
        return min(candidates, key=lambda i: i.get("createdAt", "") or "")
    return min(candidates, key=lambda i: i["number"])  # lowest_number


# --- motivation function ------------------------------------------------------

def compute_drive(cfg: dict) -> dict:
    """M(t) -> D(t) -> gate payload. Pure w.r.t. the fetched issue list."""
    issues = gh_json([
        "issue", "list", "-R", cfg["repository"],
        "--state", "open", "--limit", "200",
        "--json", "number,title,labels,createdAt",
    ])
    actionable = [i for i in issues if is_actionable(i, cfg)]
    m_t = len(actionable)
    d_t = m_t - cfg["desired"]

    if d_t > cfg["threshold"]:
        chosen = select_issue(actionable, cfg["selection"])
        return {
            "wakeAgent": True,
            "context": {
                "measure": m_t,
                "desired_state": cfg["desired"],
                "drive": d_t,
                "selected_issue": {"number": chosen["number"], "title": chosen["title"]},
                "repository": cfg["repository"],
            },
        }
    return {"wakeAgent": False}


def main() -> int:
    cfg = load_config(CONFIG_PATH)
    # Human-readable lines before the JSON gate: Hermes injects full stdout
    # into the prompt under `## Script Output`; only the LAST line is parsed.
    print(f"[github_issue_drive] repo={cfg['repository']}")
    try:
        payload = compute_drive(cfg)
    except Exception as exc:  # gate must never crash the tick or wake by accident
        print(f"[github_issue_drive] ERROR: {exc}", file=sys.stderr)
        payload = {"wakeAgent": False, "reason": f"gate_error: {exc}"}
    print(json.dumps(payload, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())
