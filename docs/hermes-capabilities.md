# Hermes capabilities vs harness responsibilities

Hermes Agent v0.20.6 (upstream 2a598aad), verified against the actual
source at ~/.hermes/hermes-agent — not just docs.

## Provided by Hermes (we do NOT reimplement)

| Capability | Source evidence |
|---|---|
| Cron scheduling / gateway daemon | `hermes cron status`, gateway tick loop |
| tick.lock (cross-process tick serialization) | `~/.hermes/cron/.tick.lock` |
| Pre-run script execution | `--script`, `_run_job_script()` (cron/scheduler.py:4272) |
| Script path validation | `path.relative_to(scripts_dir.resolve())` — scripts must live inside `~/.hermes/scripts/`; **symlinks fail** (resolve escapes), install with `cp` |
| Script timeout | `HERMES_CRON_SCRIPT_TIMEOUT`, default 3600s |
| Interpreter choice | `.sh/.bash` → bash, everything else → `sys.executable` (shebang ignored) |
| stdout → prompt injection | full stdout injected as `## Script Output` fenced block |
| wakeAgent gate | `_parse_wake_gate()` (:4543) — parses ONLY the last non-empty stdout line as JSON; only literal `false` skips; non-JSON/missing key wakes |
| Error semantics | non-zero script exit → `## Script Error` injected, agent wakes anyway → gate must catch everything and exit 0 |
| monitor (change detection) | `--monitor-script/--monitor-url`, exact-bytes hash suppression (:5596+) |
| Duplicate-run guard | `try_register_running_job()` skips a job whose previous run is in flight; stale sweep ages out wedged runs |
| Execution history | `hermes cron runs` / `cron/executions.db` — job-level only, no per-issue granularity |
| workdir + project context | `--workdir` injects AGENTS.md/CLAUDE.md/.cursorrules, sets tool cwd |
| reasoning_effort pin | `--reasoning-effort`, per-job override beats config |
| Cron failure handling / incidents | `hermes cron incidents` |
| LLM invocation, agent tools | core runtime |

## Boundary: what the harness owns

Only the motivation function:

```
Measure   M(t) = actionable open issue count (gh issue list + label filter)
Desired   M* = 0
Drive     D(t) = M(t) - M*
Gate      D > threshold → {"wakeAgent": true, "context": {...}}
```

Plus the worker prompt, and (later, only if observed broken) per-issue
attempt/lease state — Hermes' ledger is job-level so per-issue memory
cannot come from Hermes.

## Known constraints (empirically confirmed)

- `GH_TOKEN`/`GITHUB_TOKEN` are stripped unconditionally from cron
  subprocesses (`_ALWAYS_STRIP_KEYS` in tools/environments/local.py).
  gh CLI still authenticates via the macOS keyring — verified with
  `env -i HOME=$HOME PATH=/opt/homebrew/bin:/usr/bin:/bin gh api user`.
- Gate config travels by being copied next to the installed script
  (`~/.hermes/scripts/github_issue_drive.config.yaml`), read via
  `Path(__file__).parent`.
- Agent run timeout is inactivity-based (600s default) — a busy worker can
  run hours.
