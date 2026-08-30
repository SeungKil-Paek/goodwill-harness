# Architecture — Goodwill / Artificial Will Harness PoC

## Loop

```
            Hermes Gateway
                  │
                  ▼
             Hermes Cron  (every 1m tick)
                  │
                  ▼
        Motivation Script (scripts/github_issue_drive.py)
                  │
            sense world (gh issue list)
                  │
                  ▼
                M(t) = actionable open issue count
                  │
                  ▼
            D(t) = M(t) - M*   (M* = 0)
                  │
           ┌──────┴──────┐
         D<=0           D>0
           │             │
           ▼             ▼
  wakeAgent=false   wakeAgent=true + context
  (exit 0, silent)        │
                          ▼
                    Hermes Agent
                  reason / act
      (smallest safe change → test → branch → PR)
                          │
                          ▼
                      GitHub
        human merge closes issue → world state changes
                          │
                          └──── feedback: next tick re-measures
```

## Components (everything we wrote)

| File | Role |
|---|---|
| `scripts/github_issue_drive.py` | gate: measure → drive → wakeAgent JSON |
| `scripts/github_issue_drive.config.yaml` | installed config (copied next to script) |
| `config.yaml` | source-of-truth repo config |
| `prompts/issue_worker.md` | wake-time worker prompt |
| `tests/test_github_issue_drive.py` | unit tests (no network, no LLM) |

## Contracts

- Actionable: `state==open AND label~"agent" AND NOT "human" AND NOT "do-not-automate"`
- Selection: one issue per tick, lowest number (or oldest).
- Gate output: human lines first, JSON gate last line (Hermes parses last
  line only). Errors print `{"wakeAgent": false, "reason": ...}` and exit 0 —
  a crashed gate must not wake the LLM nor inject a Script Error.
- Verification is NOT the agent's word: the next tick re-measures real GitHub
  state. `M(t+1)=0` is the only proof of closure.

## world-state actor contract (spec §16 open question, resolved)

The agent never closes issues directly — it opens PRs with `Closes #N`.
A human merge flips world state; the harness observes. This keeps
M(t)=0 honest: measurement is external, closure is human-gated.

## Deliberately absent (spec §22)

No custom scheduler, daemon, tick loop, execution DB, locking, monitor
reimplementation, agent runtime, multi-agent scheduler, RAG, vector DB, RL,
or Hermes fork. If duplicate wakes or unbounded retries show up in real
runs, add the minimum lease/cooldown state then — not before.
