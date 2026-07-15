# 실험 03 · 커버리지 절벽 (정직한 반례)

!!! abstract "한 줄 요약"
    "비싼 모델을 아예 지우면 더 아끼지 않을까?" — 그렇게 만든 정책은 장부상 더 싸 보이지만,
    커버리지가 **100% → 67% (−33%p)**로 무너집니다. **비용은 커버리지를 고정했을 때만
    비교할 수 있습니다.** 모든 수치는 `measured = false`.

## 이 실험은 무엇인가

- **상황(언제):** "비싼 fallback 모델을 지우면 더 아끼지 않을까?"라는 최적화 제안이 들어온 순간.
- **작업(무엇을):** 비싼 fallback을 삭제한 후보 정책(`experiments/policies/cost-cut.yaml`)과
  번들 시드 정책을 **동일한 공유 신호**로 회귀 비교합니다.
- **실험(무엇을 검증):** 순진한 비용 절감이 커버리지를 얼마나 무너뜨리는지(100% → 67%), 즉
  커버리지를 고정하지 않은 비용 비교가 왜 무의미한지 검증합니다.

이 실험은 앞의 두 실험과 방향이 반대입니다. 실험 01·02가 *"라우팅이 이득"*을 보여줬다면,
여기서는 라우팅을 **잘못 튜닝했을 때 무엇을 잃는지**를 정직하게 드러냅니다.

## 유혹적인 "최적화"

시드 정책에는 클래스마다 비싼 fallback 모델(`deep-reasoner`, `premium-max`)이 있습니다.
가장 쉬운 절감 아이디어는 그것들을 **그냥 지우는 것**입니다. 그러면 라우터는 절대 비싼
모델로 에스컬레이션할 수 없으니 비용이 내려갈 것 같습니다.

이 발상을 그대로 담은 후보 정책이 [`experiments/policies/cost-cut.yaml`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/experiments/policies/cost-cut.yaml)
입니다 — `plan`·`validate`·`repo_patch`에서 비싼 fallback을 삭제했습니다.

- **base(기준):** 번들 시드 정책 (`src/policy/seed_policy.yaml`)
- **candidate(후보):** `experiments/policies/cost-cut.yaml` (비싼 fallback 삭제)
- **평가:** 합성 100건, 두 정책을 **동일한 공유 신호**로 채점 (`--synth`)

## 실행

```bash
cost-router policy regression --candidate experiments/policies/cost-cut.yaml --synth
```

## 결과 — 커버리지 절벽

```text
regression (candidate vs base):
  tasks: 100 (base 100)
  coverage: 67.0% (base 100.0%, delta -0.3300)
  routed_total_usd: 0.727969 (base 1.659167, delta -0.931198)
  baseline_total_usd: 1.191187
  delta_pct vs baseline: 38.9% (base 25.5%)
```

| 지표 | base(시드) | candidate(cost-cut) |
| --- | --- | --- |
| 태스크 수 | 100 | 100 |
| **커버리지** | **100.0%** | **67.0%** (−33%p) |
| 라우팅 비용 | $1.659167 | $0.727969 |

## 이 숫자를 정직하게 읽기

후보 정책의 라우팅 비용($0.727969)이 기준($1.659167)보다 **낮은 건 사실입니다.** 하지만
그건 절감이 아니라 **일을 안 한 결과**입니다 — 태스크의 33%가 자기 검사를 통과하는 모델을
아예 잃었습니다. 비싼 fallback이 사라지면서 "보장된 깨끗한 마지막 후보"가 없어졌기 때문입니다.

!!! danger "delta_pct를 곧이곧대로 비교하지 마세요"
    리포트의 `delta_pct vs baseline`은 **각 정책을 자기 자신의 나이브 baseline과** 비교한
    값입니다. cost-cut은 비싼 모델을 지웠으므로 그 baseline마저 낮아집니다
    (`$1.191187` vs 시드의 `$2.226910`). 그래서 "38.9% > 25.5%"는 **더 나은 절감이 아니라**
    약해진 기준에 대한 착시입니다. **커버리지를 고정하지 않은 비용 비교는 무의미합니다.**

이것이 시드 정책이 비싼 fallback을 남겨두는 이유입니다. 그 모델은 대부분의 태스크에서
선택되지 않지만(그래서 평소 비용에 거의 영향이 없지만), 소수의 어려운 태스크에서
**커버리지를 100%로 지키는 안전망**입니다. 비용 인지 라우팅의 핵심 주장은 *"같은 커버리지,
더 낮은 비용"*이며, 커버리지를 깨뜨리는 절감은 그 주장에 해당하지 않습니다.

## 이 실험을 언제 쓰나

- 정책을 손보기 전에 **커버리지 회귀**를 먼저 확인하고 싶을 때.
- "비싼 모델을 지우자"는 제안이 들어왔을 때, 그 대가를 **숫자로** 보여주고 싶을 때.
- 라우팅이 만능이 아니라 **트레이드오프의 조율**임을 팀에 설명할 때.

!!! note "회귀 가드로 쓰기"
    `cost-router policy regression`은 CI에서 정책 변경을 지키는 가드로도 쓸 수 있습니다 —
    후보 정책이 커버리지를 떨어뜨리면 리뷰에서 바로 드러납니다. 자세한 필드 설명은
    [실험 설정(YAML)](../manual/experiments.md)과 `cost-router policy regression --help`를
    참고하세요.

## 이 실험 재현하기

```bash
pip install -e .
cost-router policy validate --policy experiments/policies/cost-cut.yaml   # OK
cost-router policy regression --candidate experiments/policies/cost-cut.yaml --synth
```
