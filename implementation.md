# handoff.md  
## Hermes Agent 내장 기능을 활용한 Goodwill / Artificial Will Harness PoC

## 1. 작업 목적

Hermes Agent에 이미 탑재된 cron, pre-run script, `wakeAgent`, `monitor`, workdir, execution history 등의 기능을 적극 활용하여, 별도의 scheduler나 agent runtime을 새로 만들지 않고 다음 구조를 구현하라.

```text id="3sp45w"
Value
  ↓
Desired State
  ↓
Measure
  ↓
Drive / Motivation Function
  ↓
Hermes wakeAgent
  ↓
Hermes Agent cognition
  ↓
Action
  ↓
Verification
  ↓
World State 변화
```

첫 번째 PoC의 대상은 GitHub Project이다.

목표는 사람이 매번 prompt를 입력하지 않아도 외부 상태를 주기적으로 측정하고, 현재 상태가 바람직한 상태에서 벗어나 있을 때만 Hermes Agent가 깨어나 reasoning/token generation을 시작하도록 만드는 것이다.

---

# 2. 가장 중요한 설계 원칙

이 프로젝트에서 **Hermes가 이미 제공하는 기능을 재구현하지 않는다.**

다음 기능은 Hermes에 맡긴다.

```text id="ogmmte"
- Gateway daemon
- Cron scheduling
- scheduler tick
- tick.lock
- cron execution lifecycle
- pre-run script 실행
- script timeout
- stdout → prompt context injection
- wakeAgent JSON parsing
- monitor change detection
- execution history
- workdir
- reasoning_effort
- cron failure handling
- LLM invocation
```

따라서 이 프로젝트는 scheduler framework도 아니고 새로운 agent runtime도 아니다.

우리가 구현할 핵심은 오직 다음이다.

```text id="levamc"
1. 무엇을 측정할 것인가?        Measure
2. 어떤 상태가 좋은 상태인가?    Desired State
3. 언제 AI를 깨울 것인가?        Drive / Motivation Function
4. 깨어난 AI가 무엇을 할 것인가? Prompt / Skill
```

---

# 3. Hermes 기능을 먼저 조사하라

구현 전에 현재 설치된 Hermes Agent 버전과 GitHub source를 기준으로 다음 항목을 확인하라.

```text id="8vhgun"
- cron job schema
- script 필드
- monitor 필드
- wakeAgent JSON 처리
- script stdout의 prompt 주입 방식
- monitor output 비교 방식
- scheduler tick 주기
- tick.lock
- execution history
- workdir
- reasoning_effort
- cron failure/retry 동작
- 동일 job의 overlapping 실행 가능 여부
```

문서만 보지 말고 실제 source implementation을 확인하라.

확인 결과는 다음 문서에 짧게 기록한다.

```text id="10fqwc"
docs/hermes-capabilities.md
```

목적은 Hermes가 이미 제공하는 기능과 우리가 구현해야 하는 기능의 경계를 명확히 하는 것이다.

---

# 4. Hermes `script`를 Artificial Will의 핵심 primitive로 사용

Hermes cron의 `script`는 매 tick마다 먼저 실행된다.

이 script가 deterministic하게 세계 상태를 측정하고 motivation function을 계산한다.

그 결과로 다음 중 하나를 출력한다.

문제가 없을 때:

```json id="sfuxh5"
{"wakeAgent": false}
```

AI가 행동해야 할 때:

```json id="s17ng8"
{
  "wakeAgent": true,
  "context": {
    "measure": 1,
    "target": 0,
    "drive": 1
  }
}
```

따라서 기본 구조는 다음과 같다.

```text id="glyz24"
Hermes Cron Tick
      ↓
pre-run script
      ↓
GitHub 상태 측정
      ↓
M(t)
      ↓
D(t) = M(t) - M*
      ↓
D(t) > threshold ?
     / \
   NO   YES
   ↓     ↓
sleep   wakeAgent=true
          ↓
      Hermes Agent
```

---

# 5. `monitor`와 `wakeAgent`를 구분해서 사용하라

Hermes의 `monitor`는 매우 유용하지만 이번 PoC의 핵심 Drive와는 의미가 다르다.

`monitor`는 본질적으로 다음 조건이다.

```text id="qjqski"
현재 출력 != 직전 출력
→ agent wake
```

즉:

```text id="zdr9bf"
M(t) != M(t-1)
```

반면 Artificial Will의 핵심은:

```text id="qsuckc"
현재 상태 != Desired State
→ agent wake
```

즉:

```text id="8rch5b"
D(t) = M(t) - M*
D(t) > threshold
```

이다.

예를 들어 open issue 수가 계속 1이면 `monitor`는 최초 변화 때만 agent를 깨울 수 있다.

하지만 Artificial Will에서는 issue가 해결되지 않은 한 계속 “행동할 이유”가 존재한다.

따라서 첫 번째 구현에서는 다음 원칙을 적용한다.

```text id="g3altr"
Primary trigger:
    script + wakeAgent

Optional change detector:
    monitor
```

`monitor`를 Drive 대신 사용하지 않는다.

다만 새로운 사건만 감지하면 되는 use case에서는 `monitor`를 적극 활용한다.

---

# 6. 첫 번째 PoC Measure

첫 번째 PoC는 GitHub issue를 대상으로 한다.

목표 상태:

```text id="6bsol8"
Actionable Open Issue Count = 0
```

기본 measure:

```text id="nbc1zz"
M(t) = actionable open issue count
```

초기 PoC의 actionable 조건은 단순하게 유지한다.

예:

```text id="f07xas"
state == open
AND label contains "agent"
AND label does NOT contain "human"
AND label does NOT contain "do-not-automate"
```

필요 이상으로 복잡한 issue classification 시스템을 만들지 않는다.

---

# 7. Motivation Function

기본 target:

```text id="jmt2c6"
M* = 0
```

Drive:

```text id="bnx86g"
D(t) = M(t) - M*
```

Trigger:

```text id="jxdd81"
if D(t) > 0:
    wakeAgent = true
else:
    wakeAgent = false
```

첫 PoC에서는 이것으로 충분하다.

향후 확장 가능성은 유지한다.

예:

```text id="d6uvuw"
D(t) =
    10 * critical
  + 5  * bug
  + 3  * regression
  + 1  * normal
```

하지만 이번 단계에서 weighted scoring을 미리 구현하지 않는다.

---

# 8. 구현할 script

최소한 다음 파일을 만든다.

```text id="42opsj"
scripts/github_issue_drive.py
```

이 script의 책임은 다음뿐이다.

```text id="786ikf"
1. GitHub 상태 조회
2. actionable issue 필터링
3. M(t) 계산
4. D(t) 계산
5. wakeAgent 판단
6. 필요한 context 출력
```

LLM을 호출하지 않는다.

복잡한 reasoning을 하지 않는다.

가능하면 `gh` CLI를 먼저 사용한다.

예:

```text id="oohko7"
gh issue list
```

필요하면 GitHub API를 사용한다.

---

# 9. Script 출력

actionable issue가 없을 때:

```json id="xizihn"
{
  "wakeAgent": false
}
```

actionable issue가 있을 때:

```json id="5enb4h"
{
  "wakeAgent": true,
  "context": {
    "measure": 2,
    "desired_state": 0,
    "drive": 2,
    "selected_issue": {
      "number": 123,
      "title": "..."
    }
  }
}
```

실제 Hermes가 `context`를 어떤 형식으로 prompt에 주입하는지는 현재 source 동작을 확인하여 정확히 맞춘다.

새 인터페이스를 임의로 만들지 않는다.

---

# 10. Issue 선택

PoC에서는 한 번에 issue 하나만 선택한다.

선택 기준은 단순하게 한다.

예:

```text id="3nl39l"
1. priority label
2. oldest actionable issue
```

또는

```text id="1gejkw"
lowest issue number
```

중 하나를 택한다.

복잡한 scheduler, queue, multi-worker system을 구현하지 않는다.

---

# 11. Hermes Cron을 그대로 사용

별도 polling loop를 만들지 않는다.

다음을 사용한다.

```text id="uw8dku"
Hermes Gateway
    ↓
Hermes Cron
    ↓
pre-run script
    ↓
wakeAgent
```

목표 cron job의 개념은 다음과 같다.

```text id="40r88n"
schedule:
    every 1 minute

script:
    github_issue_drive.py

workdir:
    target repository

prompt:
    issue_worker.md

reasoning_effort:
    high
```

정확한 CLI syntax는 현재 Hermes source와 `hermes cron --help` 결과를 기준으로 작성한다.

추측하지 않는다.

---

# 12. Hermes `workdir` 적극 활용

GitHub repository를 대상으로 작업할 때 Hermes cron의 `workdir`을 사용한다.

이렇게 하면 Hermes가 해당 repository 안에서 작업하도록 한다.

가능하면 기존:

```text id="ko8pxp"
AGENTS.md
CLAUDE.md
.cursorrules
```

등의 project instruction도 Hermes가 원래 지원하는 방식으로 그대로 활용한다.

별도로 동일한 project context loading 기능을 만들지 않는다.

---

# 13. Hermes Prompt

다음 파일을 만든다.

```text id="g2q3ub"
prompts/issue_worker.md
```

내용은 다음 역할에 집중한다.

```text id="9lesbv"
You were awakened because the current project state
does not match the desired project state.

Inspect the supplied GitHub issue.

Your objective is to reduce the measured problem state safely.

1. Understand the issue.
2. Inspect the relevant repository code and documentation.
3. Determine whether the issue is actionable.
4. Make the smallest safe change that addresses the issue.
5. Run appropriate tests.
6. Verify the result.
7. Record clearly what changed.
8. Do not claim success without evidence.
9. Stop if the action requires unsafe, destructive, or ambiguous operations.
```

불필요하게 긴 autonomous-agent framework prompt를 만들지 않는다.

---

# 14. Verification

Hermes Agent가 “해결했다”고 말한 것만으로 성공으로 판단하지 않는다.

다음 cron tick에서 `github_issue_drive.py`가 다시 실제 GitHub 상태를 측정한다.

즉:

```text id="ou4l5s"
Before:
M(t) = 1

Agent 작업

After:
M(t+1) = 0
```

이 되어야 실제로 목표 상태에 도달한 것이다.

이 closed-loop가 PoC의 핵심이다.

```text id="m8k05r"
Measure
→ Wake
→ Think
→ Act
→ World changes
→ Measure again
```

---

# 15. Hermes execution history를 그대로 사용

별도의 execution history DB를 만들지 않는다.

Hermes가 이미 제공하는 cron execution history를 먼저 사용한다.

필요한 경우 다음을 조사한다.

```text id="yujt3x"
- job run status
- failure count
- previous output
- timestamps
- active run 여부
```

기존 history 정보로 충분하면 새로운 state database를 만들지 않는다.

---

# 16. Claim / Lease / Cooldown은 필요할 때만 추가

이전 설계처럼 처음부터 다음을 전부 구현하지 않는다.

```text id="58i5kh"
claim
lease
cooldown
retry database
custom execution ledger
custom locking
```

먼저 Hermes 자체 기능으로 다음 문제가 실제로 발생하는지 확인한다.

```text id="v6gvs6"
- 동일 issue가 중복 실행되는가?
- 이전 job이 아직 실행 중인데 다음 tick이 실행되는가?
- 실패한 issue가 매 tick마다 무한 inference를 발생시키는가?
```

문제가 실제로 확인된 경우에만 최소한의 state logic을 추가한다.

예:

```text id="hf64ok"
state/issue_state.json
```

또는 GitHub label을 활용할 수 있다.

예:

```text id="56lqer"
agent-working
agent-blocked
needs-human
```

Hermes가 이미 해결하는 문제를 다시 구현하지 않는다.

---

# 17. `monitor`를 사용할 수 있는 별도 실험

두 번째 작은 실험으로 Hermes `monitor` 기능도 검증한다.

예:

```text id="3c7jq2"
GitHub open issue 목록을 deterministic output으로 반환
```

출력이 바뀌었을 때만 Hermes가 깨어나는지 확인한다.

이 실험의 목적은 다음 두 동기 모델의 차이를 검증하는 것이다.

```text id="tniumo"
Change-driven:
    M(t) != M(t-1)

Goal-driven:
    M(t) != M*
```

둘은 별개의 activation policy로 기록한다.

---

# 18. 디렉터리 구조

프로젝트를 최소화한다.

```text id="78wf3f"
goodwill-harness/
├── README.md
├── config.yaml
│
├── scripts/
│   └── github_issue_drive.py
│
├── prompts/
│   └── issue_worker.md
│
├── tests/
│   └── test_github_issue_drive.py
│
└── docs/
    ├── architecture.md
    └── hermes-capabilities.md
```

초기 PoC에 Python package 구조가 필요하지 않으면 만들지 않는다.

---

# 19. Configuration

예:

```yaml id="6nesi9"
github:
  repository: OWNER/REPO

issue_filter:
  required_labels:
    - agent

  excluded_labels:
    - human
    - do-not-automate

desired_state:
  actionable_open_issues: 0

drive:
  threshold: 0

hermes:
  schedule: "every 1m"
  reasoning_effort: high
```

configuration은 단순하게 유지한다.

---

# 20. 테스트

최소 다음을 검증한다.

```text id="k7p6h8"
test_no_issue_outputs_wake_false

test_actionable_issue_outputs_wake_true

test_excluded_issue_does_not_trigger

test_measure_is_correct

test_drive_is_correct

test_output_is_valid_wakeAgent_json
```

추가로 Hermes integration test를 수행한다.

---

# 21. 실제 Hermes Integration Test

다음 순서로 검증한다.

### Case A

GitHub actionable issue 없음.

예상:

```text id="2m89j0"
script runs
wakeAgent=false
LLM inference 없음
```

### Case B

`agent` label이 있는 open issue 생성.

예상:

```text id="h9cglc"
M(t)=1
D(t)=1
wakeAgent=true
Hermes Agent session 실행
```

### Case C

Hermes가 issue 작업 수행.

예상:

```text id="q1a0c9"
repository inspect
code change
test
result
```

### Case D

issue가 실제 해결됨.

다음 tick:

```text id="43zjop"
M(t+1)=0
wakeAgent=false
```

### Case E

issue가 해결되지 않음.

다음 tick에서 다시:

```text id="2ei06o"
M(t+1)>0
```

이면 기본적으로 다시 wake된다.

이 시점에서 무한 반복 문제가 실제로 나타나는지 관찰한다.

그 후에만 cooldown 또는 retry policy의 필요성을 판단한다.

---

# 22. 구현하지 말아야 할 것

이번 PoC에서는 다음을 만들지 않는다.

```text id="a608ek"
custom scheduler
custom daemon
custom tick loop
custom cron
custom execution database
custom locking
custom stdout → prompt pipeline
custom monitor
custom agent runtime
multi-agent scheduler
RAG
vector DB
reinforcement learning
Hermes fork
```

Hermes 자체 기능으로 해결할 수 있는 문제는 Hermes에 맡긴다.

---

# 23. 연구적으로 확인할 질문

구현 완료 후 다음 질문에 답하라.

```text id="3ky3x9"
1. Hermes cron + script + wakeAgent만으로
   goal-driven autonomous activation이 가능한가?

2. LLM inference 없이 measure 계산만 반복할 수 있는가?

3. 현재 세계 상태가 목표 상태에서 벗어나 있을 때만
   cognition을 발생시킬 수 있는가?

4. monitor 기반 change-driven activation과
   script 기반 goal-driven activation의 차이는 무엇인가?

5. Hermes 기존 execution/failure 기능만으로
   어느 정도 반복 제어가 가능한가?

6. 추가적인 claim/lease/cooldown이 실제로 필요한가?
```

---

# 24. 최종 Architecture

최종적으로 다음 구조를 목표로 한다.

```text id="b6v3zh"
              Hermes Gateway
                    │
                    ▼
               Hermes Cron
                    │
                    ▼
            Motivation Script
                    │
              sense world
                    │
                    ▼
                  M(t)
                    │
                    ▼
              D(t)=M(t)-M*
                    │
             ┌──────┴──────┐
             │             │
           D<=0           D>0
             │             │
             ▼             ▼
      wakeAgent=false  wakeAgent=true
                           │
                           ▼
                     Hermes Agent
                           │
                     reason / act
                           │
                           ▼
                       GitHub
                           │
                           └──── feedback
```

---

# 25. 핵심 개념

이 시스템에서 Hermes는 이미 다음을 제공한다.

```text id="mppcse"
Sensing schedule
Wake mechanism
Cognition engine
Action tools
Execution infrastructure
```

우리가 추가하는 핵심은 다음이다.

```text id="1arwg2"
Motivation Function
```

즉:

```text id="x08wqr"
D = f(World State, Desired State)
```

그리고:

```text id="adgf5k"
if D > threshold:
    wakeAgent
```

이다.

---

# 26. 최종 성공 조건

이 PoC가 성공했다는 것은 새로운 agent framework를 많이 만들었다는 뜻이 아니다.

오히려 반대다.

다음이 최소한의 코드로 구현되어야 한다.

```text id="6dexrv"
Hermes built-in capability
        +
small deterministic motivation script
        +
agent prompt
        =
goal-driven autonomous agent
```

최종 보고서에는 반드시 다음을 답하라.

```text id="fmdvnx"
- 새로 구현한 코드가 몇 줄인가?
- Hermes 기존 기능으로 처리한 부분은 무엇인가?
- 중복 구현한 기능은 없는가?
- wakeAgent 이전에는 LLM token이 전혀 소비되지 않는가?
- Drive 계산이 실제 world state에 기반하는가?
- Agent 행동 후 world state가 다시 measure되는가?
- monitor와 goal-driven drive의 차이를 실제 실험으로 확인했는가?
```

가장 중요한 원칙:

> Hermes를 다시 만들지 말라.  
> Hermes가 이미 가진 실행 구조 위에  
> “무엇 때문에 AI가 깨어나야 하는가”만 구현하라.