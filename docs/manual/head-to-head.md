# 문제 하나, 네 가지 방법 (5분 wow)

대시보드의 다른 패널이 **워크로드 전체**를 집계로 비교한다면, 이 아레나는 신규 사용자가 가장
먼저 던지는 질문에 답합니다: **"이 문제 하나를 두고, 각 방법은 얼마를 쓰고, 얼마나 느리고,
정답을 맞히긴 하나?"** 태스크를 하나 고르고, 네 개의 열이 채워지는 걸 지켜보는 — HuggingFace
Spaces 같은 "누르면 바로 보이는" 화면입니다.

!!! success "설치 없이 바로 보기"
    아레나 패널은 라이브 대시보드에 포함되어 있습니다.

    [:material-open-in-new: 라이브 데모](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/){ .md-button target=_blank }

## 네 가지 방법

같은 태스크 하나에 대해 네 접근을 점수화합니다. 집계 패널과 **완전히 같은 오프라인 기계**를
재사용하므로 숫자는 구성상 일치합니다.

| 접근 | 무엇을 하나 | 비용 청구 |
| --- | --- | --- |
| **가장 싼 모델** | 클래스의 가장 싼 후보 하나만 호출 | 그 한 번 |
| **프리미엄 모델** | 가장 비싼 후보 하나만 호출 (나이브 천장) | 그 한 번 |
| **앙상블(팬아웃)** | 후보 **전부**에 팬아웃해 최선을 채택 | **후보 전부의 합** (팬아웃 세금) |
| **비용 인지 라우터** | 값싼 것부터, 실패하면 위로 에스컬레이션 | **승자 한 번만** |

## 세 개의 축

- **비용** — 태스크 토큰 수에 예시 가격을 적용. 라우터는 **승자만**, 앙상블은 **전부** 청구.
- **정확도** — 라우터의 `is_clean` 판정(모든 오프라인 체크 통과 시 "pass"). 합성 신호 투영이지
  채점된 라이브 답이 아닙니다.
- **지연** — **예시적 투영**이며 측정값이 아닙니다. 번들 텔레메트리에는 타이밍이 없어, 티어별
  처리량 모델이 토큰 수를 밀리초로 바꿔 세 번째 축에 모양만 줍니다. 앙상블은 병렬 팬아웃이므로
  **가장 느린 하나**(max), 라우터는 순차 에스컬레이션이므로 **시도한 호출들의 합**(sum)입니다.

## 정직한 트레이드오프

기본 태스크 `t-0003`(repo_patch)에서 결과는:

| 접근 | 비용 | 지연* | 정확도 |
| --- | --- | --- | --- |
| 가장 싼 모델 | `$0.006680` | 빠름 | ✗ 실패 |
| 프리미엄 모델 | `$0.081981` | 중간 | ✓ 통과 |
| 앙상블(팬아웃) | `$0.179844` | 중간 | ✓ 통과 |
| **비용 인지 라우터** | **`$0.032793`** | **가장 느림** | ✓ 통과 |

라우터는 **가장 싸면서 정답도 맞히지만**(프리미엄보다 약 2.5× 저렴 — 프리미엄·앙상블도 똑같이
정답), 순차 에스컬레이션 때문에 **지연은 가장 느립니다**. 프리미엄이 지연을 이깁니다. **공짜
점심은 없습니다** — 여기서는 비용을 아끼는 대가로 지연을 냅니다. 정확도는 이진값이라 통과한
세 접근(프리미엄·앙상블·라우터)이 **동등하게** 정답이고, 가장 싼 모델만 실패합니다. 쉬운
태스크(`t-0001`)를 고르면 가장 싼 모델이 세 축을 모두 이기고 라우터도 그걸 그대로 고릅니다 —
라우팅은 어려운 태스크에서 가치를 냅니다.

`*` 지연은 예시적 투영입니다(`measured = false`). 실제 wall-clock이 아니며, 실제 타이밍은
[라이브 실측 브릿지](foundry-live.md)에서 나옵니다.

## 입력 데이터 — 읽을 수 있는 문제

각 태스크에는 **사람이 읽는 문제 진술**이 붙어 있습니다 — 제목, 실제로 던질 프롬프트, 합격
기준(`expect`). CLI는 표 위에 `problem` 블록으로, 웹앱은 태스크 카드로 띄웁니다. 덕분에 "이게
무슨 문제인지" 곧바로 보이고, 네 방법이 **같은 구체적 문제**를 푼다는 게 분명해집니다.

!!! warning "저작(합성) 프롬프트 — 공개 벤치마크가 아님"
    이 문제 진술은 저장소가 **직접 저작한 합성 예시**입니다(`problem_basis =
    authored-synthetic`, `samples/prompts/curated-arena.sample.json`). HumanEval·MBPP 같은
    **공개 벤치마크를 갖다 붙이지 않았습니다** — 합성 pass/fail 신호를 실명 벤치마크에 붙이면
    실측 평가인 양 오해를 낳아 정직하지 않기 때문입니다. 진짜 공개 데이터 + 실제 채점은
    [라이브 실측 브릿지](foundry-live.md)에서만 가능합니다. 프롬프트는 **표시 전용**이라
    분류·비용에 영향을 주지 않으며, 위 수치는 프롬프트가 없어도 동일합니다.

## CLI로 보기

```bash
cost-router compare                    # 기본 태스크(t-0003)
cost-router compare --task t-0001      # 특정 태스크
cost-router compare --json             # 그 태스크의 아레나를 JSON으로
```

출력 예:

```text
one problem, four ways   (measured = false)
task  t-0003   class=repo_patch   difficulty=medium
problem   Patch parse_duration to accept combined units
          The repo's parse_duration(text: str) -> int helper returns None for
          combined values like "1h30m" or "2m30s". Patch it to sum consecutive
          <number><unit> segments (h/m/s) into total seconds, reject empty or
          malformed input, and keep the existing single-unit tests green.
          expect: "1h30m" -> 5400, "45s" -> 45, "" and "10x" are rejected, and the
                  existing single-unit tests still pass.

approach            model(s)                            cost    latency*  result
------------------- ---------------------------- ----------- -----------  ------
Cheapest model      swift-coder                  $  0.006680     15485ms  ✗ fail
Premium model       premium-max                  $  0.081981     26860ms  ✓ pass @
Ensemble (fan-out)  4 models (swift-coder +3)    $  0.179844     26860ms  ✓ pass
Cost-aware router   swift-coder → balanced-pro   $  0.032793     33556ms  ✓ pass $

winners   cost: Cost-aware router   latency: Premium model   accuracy: 3 of 4 pass
note      latency is an illustrative projection (measured = false), not wall-clock.
          $ = cheapest   @ = fastest   (accuracy is pass/fail per approach)
```

## 엔드포인트

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/compare` | 태스크 메뉴 + 모든 큐레이션 태스크의 아레나 |
| GET | `/compare?task=<id>` | 기본 태스크를 지정 태스크로 |

페이로드는 작아서(큐레이션 5건) 전체 `{tasks, default, arenas}` 맵을 한 번에 반환합니다. 그래서
정적 export와 라이브가 동일하고, 웹앱은 왕복 없이 태스크를 전환합니다.

!!! note "모든 숫자는 오프라인 투영"
    비용·정확도는 다른 패널과 **구성상 동일한** 오프라인 기계에서 나오며(`measured = false`),
    지연은 새로 도입한 **예시적 투영**입니다. 모델 이름은 일반 자리표시자입니다.

## 실측으로 보기 (`measured = true`)

위 숫자는 전부 오프라인 투영(`measured = false`)입니다. **같은 큐레이션 태스크(t-0001~t-0006)를
실제 Azure Model Router로 측정**하려면, 프롬프트가 담긴 준비된 워크로드로 라이브 브릿지를
돌리세요 — 크리덴셜만 채우면 한 명령입니다:

```bash
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl \
  --pricing  samples/pricing/your-tenant.yaml --store runs.jsonl
```

실제로 청구된 토큰 usage로 비용이 계산되어 `measured = true`가 되고, `--store`로 히스토리컬
대시보드에 한 줄로 남습니다. 자세한 설정·정직함 경계는 [라이브 실측 브릿지](foundry-live.md)를
참고하세요. (정확도까지 측정하려면 `grader` 주입이 필요하며, 없으면 커버리지는 오프라인 신호
투영으로 라벨됩니다.)

## 실험 기록

이 프로토타입 실행 기능의 방법·수치·정직 라벨은 [실험 08 · 아레나](../lab-notebook/08-arena.md)에
정리돼 있습니다 — 왜 한 태스크로 좁혔는지, 지연 축이 왜 예시적 투영인지, 라우터가 왜 가장
느린지(순차 에스컬레이션)를 다룹니다.
