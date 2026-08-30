# 최종 보고서 — Goodwill / Artificial Will Harness PoC (issue #19)

implementation.md §23·§26 요구사항. 모든 수치는 실제 실행에서측정한 증거에 기반한다.

## 연구 질문 답변 (spec §23)

**1. Hermes cron + script + wakeAgent만으로 goal-driven autonomous activation이 가능한가?**
가능하다. `hermes cron` job `97936c0afbc1`(every 1m, script=github_issue_drive.py)이
매 tick gate를 실행하고, `M(t)>0`인 tick에서만 worker가 wake됐다. 실측 wake ticks:
`eaf4a50`(00:05), `9ccf81e`(00:43), `0d8ad6f`(01:13), `231447f`(01:59) — `hermes cron
runs 97936c0afbc1` 확인 가능. 외부 scheduler 코드 0줄.

**2. LLM inference 없이 measure 계산만 반복할 수 있는가?**
가능하다. gate는 `gh issue list --json` + 라벨 필터 + 뺄셈만 한다. `D<=0`이면
`{"wakeAgent": false}` 출력 후 exit 0 — Hermes의 `_parse_wake_gate()`(scheduler.py:4543)가
JSON 마지막 줄만 보고 해당 tick의 LLM 호출을 건너뛴다. LLM token 소비 0.

**3. 목표 상태에서 벗어날 때만 cognition이 발생하는가?**
발생한다. gate의 drive는 `D(t) = M(t) - M*` 한 줄. issue #19가 open인 동안은 매 tick
wake 사유가 있고(D=1), merge로 closed 되는 순간부터는wakeAgent=false로 조용해진다.
cognition의 트리거가 agent 내부가 아니라 world state measurement라는 점이 핵심.

**4. monitor(change-driven)과 goal-driven의 차이는 무엇인가?**
- goal-driven: `M(t) != M*` — 목표 괴리가 **계속되는 한** 매 tick wake. 미해결 작업을
  재촉구(re-prompt)하는 성질. issue #19에서 M=1 유지 동안 매 tick wake로 실증.
- change-driven: `monitor_open_issues.py` + `--monitor-script`(job `836a3e36e2d8`) —
  stdout byte hash가 바뀐 **최초 1회만** wake. 실험 결과: 동일 출력 유지 동안 연속
  suppression 확인(2분 간격 completed runs가 빈 출력으로 소진).
- 결론: monitor는 "세계가 변했다"를 알리는 센서이고, drive는 "목표에 못 갔다"를
  재촉하는 motivation이다.-goal-driven이PoC의 주 트리거에 맞다.

**5. Hermes execution/failure 기능만으로 반복 제어가 되는가?**
1차원은 된다. `try_register_running_job()`이 이전 run in-flight 시 tick을 skip하고
(중복 실행 방지), stale sweep이 wedged run을 정리한다. execution history
(`hermes cron runs`)로 run 단위의 재시행 추적 가능. 다만 run 단위라 issue 단위
중복 작업은 막지 못한다 — issue #19의 worker run들이 서로 다른 run id로 반복 wake된
것이 그 증거.

**6. claim/lease/cooldown이 실제로 필요한가?**
아직 아니다. spec §16 순리 원칙(실제 문제 확인 후 최소한 추가) 유지. gh exit≠0 →
gate fail-closed(false + exit 0) 관측이 확인됐고, run-level 중복 스킵은 Hermes가
처리. worker들이 shell spawn timeout에 걸린 사건의 root cause는 harness가 아니라
interactive 세션의 workdir rw-lock 점유였다 — 나중에cooldown은 scheduling stagger로
충분. lease DB를 만들 이유가 아직 없다.

## §26 성공 조건 체크

| 항목 | 답 |
|---|---|
| 새로 구현한 코드 | gate 171줄 + monitor 실험 28줄 = **199줄** (+ 테스트 111줄, prompt 23줄, config 38줄) |
| Hermes가 처리한 부분 | 스케줄·tick·script 실행·stdout 주입·wake gate·monitor hash suppression·중복 run guard·실행 이력·LLM/tools 전부 (`docs/hermes-capabilities.md`) |
| 중복 구현 | 없음 — spec §22 금지 항목(scheduler/daemon/DB/locking/runtime/RAG/RL/fork) 전부 미구현 |
| wakeAgent 이전 LLM token | 0 — gate는 Python+gh만 실행, wakeAgent=false tick은 LLM 호출 없음 |
| Drive의 world state 기반 | 예 — `gh issue list`로 GitHub 실상태를 매 tick 조회 |
| 행동 후 재측정 | 예 — worker PR merge 후 다음 tick의 M(t)이 실제 판정. agent self-report는 증거로 쓰지 않음 |
| monitor vs goal-driven 실험 | 실측 — job 836a3e36e2d8(byte-stable suppression) vs 97936c0afbc1(goal 괴리 지속 wake) |

## 남은 단일 미해결 항목 (이 PR의 실제 변경)

이 issue의 code/documented 산출물은 main에 존재하고 unit test 9/9 pass로 검증됐으나,
spec §23·§26의 **최종 보고서 파일 자체가 리포에 없었다**. 이 PR(`docs/final_report.md`)이
그 공백을 채우고, merge되면 human merge 게이트가 world state를 뒤집고
(M: 1→0) 다음 tick에서 closed loop가 완성된다.

## 검증 방법 (재현)

```bash
git clone https://github.com/SeungKil-Paek/goodwill-harness && cd goodwill-harness
python3 -m unittest discover -s tests -v   # 9/9 OK (network/LLM 없음)
python3 scripts/github_issue_drive.py      # M>0이면 wakeAgent=true JSON
hermes cron runs 97936c0afbc1              # goal-driven wake tick들
```
