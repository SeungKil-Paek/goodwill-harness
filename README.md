# Goodwill / Artificial Will Harness PoC

Hermes Agent 내장 기능(cron, script, wakeAgent, monitor, workdir, execution
history) 위에 motivation function 하나만 얹은 goal-driven 자율 활성화
PoC. scheduler도 runtime도 새로 만들지 않았다.

```
Hermes Cron tick (1m)
  → scripts/github_issue_drive.py   Measure M(t) = actionable open issue count
  → D(t) = M(t) - M* (=0)
  → D<=0: {"wakeAgent": false} → LLM token 소비 0
  → D>0:  {"wakeAgent": true, context:{selected_issue}} → worker 깨어남
  → worker: smallest safe change → test → branch → PR
  → human merge → world state change → 다음 tick 재측정 (closed loop)
```

## 구조

```
goodwill-harness-r1/
├── README.md
├── config.yaml                              # source-of-truth 설정
├── scripts/
│   ├── github_issue_drive.py               # motivation gate (primary)
│   ├── github_issue_drive.config.yaml     # installed copy용 설정
│   └── monitor_open_issues.py            # §17 change-driven 실험
├── prompts/
│   └── issue_worker.md                     # wake 시 worker prompt
├── tests/
│   └── test_github_issue_drive.py        # 9 unit tests (no network)
└── docs/
    ├── architecture.md
    └── hermes-capabilities.md            # v0.20.6 소스 검증 결과
```

## 설치/실행

```bash
cp scripts/github_issue_drive.py scripts/github_issue_drive.config.yaml ~/.hermes/scripts/   # symlink 금지 — resolve() 검증에 걸림
hermes cron create "every 1m" --name goodwill-issue-drive \
  --script github_issue_drive.py \
  --workdir "$(pwd)" --reasoning-effort high --deliver local "<worker prompt>"
```

실제 등록: job `97936c0afbc1` (every 1m, workdir=this repo).

## 활성화 정책 두 축 (spec §5, §17)

| | trigger | job |
|---|---|---|
| Goal-driven (primary) | `M(t) != M*` | goodwill-issue-drive (script+wakeAgent) |
| Change-driven (실험) | `M(t) != M(t-1)` | monitor job (--monitor-script) |

issue가 unresolved로 남아있는 한 goal-driven은 매 tick wake 사유가 있다.
change-driven은 최초 변화 때만 wake한다.

## 검증 원칙

agent의 "해결했다"는 증거가 아니다. 다음 tick의 실측 `M(t+1)=0`만 성공 판정.
worker는 issue를 직접 close하지 않고 `Closes #N` PR을 연다 — merge는 사람.

## 실행 노트 (live)

- `gh issue list --json`의 state는 대문자 `OPEN` → gate에서 normalize함 (발견된 실버그)
- cron sandbox에서 GH_TOKEN은 무조건 strip되지만 gh keyring 인증으로 동작 (env -i로 검증)
- gate crash 시에도 마지막 줄 JSON + exit 0. 비정상 exit은 Script Error로 agent를 깨움
- gate 시연: M=0→false / M=1→true+context / do-not-automate→false — 통과
- 첫 tick 실화: issue #19 감지, wakeAgent=true, run `eaf4a508c4c7…` 실행 중
