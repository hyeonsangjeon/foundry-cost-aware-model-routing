# 실험 04 · 공짜 점심은 없다 (라우팅의 한계)

!!! abstract "한 줄 요약"
    모든 태스크가 진짜 어려워 **가장 비싼 모델만 통과**하는 워크로드에서는, 라우팅이 싼 모델을
    전부 시도하다 실패해 최상위 모델로 올라갑니다. 결과는 **커버리지 100% · 절감 0.0%** —
    라우팅 비용이 나이브(항상 프리미엄)와 **정확히 같습니다.** 라우팅은 없는 절감을
    지어내지 않습니다. 모든 수치는 `measured = false`.

## 이 실험은 무엇인가

- **상황(언제):** "라우팅을 켜면 항상 싸지는 거 아냐?"라는 기대가 들어온 순간. 그 기대의
  **경계**를 정직하게 그어야 할 때.
- **작업(무엇을):** 손으로 고른 어려운 태스크 6건에 대해, 각 태스크에서 **최상위 후보만
  통과**하는 오프라인 신호(`samples/responses/hard-tasks-signals.sample.json`)를 붙여
  라우팅을 실행합니다.
- **실험(무엇을 검증):** 이런 워크로드에서 라우팅이 (1) **커버리지를 100%로 유지**하면서
  (2) 절감은 **0%**임을 검증합니다 — 즉 어려운 일에는 정직하게 최상위 비용을 씁니다.

이 실험은 실험 01·02(라우팅이 이득)와 실험 03(잘못 튜닝하면 커버리지 붕괴)에 이은
**세 번째 정직함**입니다. 여기서는 라우팅을 *올바르게* 썼는데도 **이득이 0인 경계**를
드러냅니다.

## 설정 — 오직 최상위만 통과하는 워크로드

각 태스크의 신호는 클래스의 **모든 후보**에 대해 정의되며, 값싼 후보는 검사에 실패하고
(`compiles=false` 또는 `tests_pass=false`) **가장 비싼 후보만** 모든 검사를 통과합니다.
라우터는 값싼 후보를 먼저 평가하지만 통과하는 게 없어 최상위로 에스컬레이션합니다.

- **워크로드:** `samples/telemetry/mixed-coding-workload.sample.jsonl`의 hard 태스크 6건
- **신호:** [`samples/responses/hard-tasks-signals.sample.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/responses/hard-tasks-signals.sample.json) (최상위만 clean)
- **정책·가격:** 번들 시드 정책·가격 (`measured = false`)

## 실행

```bash
cost-router experiment run limits
```

## 결과 — 절감 0%, 커버리지 100%

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $0.236785
  AFTER   cost-aware routing                   $0.236785
  SAVED   $0.000000  (0.0% lower)  at 100.0% coverage

reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 0.0% ≥ 0.0%
  PASS  tasks: 6 ≥ 6
  PASS  savings_ceiling: 0.0% ≤ 0.0%
```

태스크마다 라우터는 값싼 후보를 평가하고 → 실패 → 다음 후보로 올라가, 결국 **통과하는
유일한 후보(최상위)**를 선택합니다.

| task | class | 시도 → 결과 | 선택 | 비용 |
| --- | --- | --- | --- | --- |
| t-0007 | plan | swift-coder ✗ · balanced-pro ✗ · **deep-reasoner ✓** | deep-reasoner | $0.052828 |
| t-0036 | generate | mini-fast ✗ · swift-coder ✗ · **balanced-pro ✓** | balanced-pro | $0.012747 |
| t-0032 | test | mini-fast ✗ · swift-coder ✗ · **balanced-pro ✓** | balanced-pro | $0.010589 |
| t-0015 | validate | mini-fast ✗ · balanced-pro ✗ · **deep-reasoner ✓** | deep-reasoner | $0.008658 |
| t-0024 | repo_patch | swift-coder ✗ · balanced-pro ✗ · deep-reasoner ✗ · **premium-max ✓** | premium-max | $0.083925 |
| t-0029 | repo_patch | swift-coder ✗ · balanced-pro ✗ · deep-reasoner ✗ · **premium-max ✓** | premium-max | $0.068038 |

합계 라우팅 비용 **$0.236785** = 나이브 비용 **$0.236785** → 절감 **$0.000000 (0.0%)**.

## 이 숫자를 정직하게 읽기

라우팅이 "실패"한 게 아닙니다. 라우팅의 약속은 *"같은 커버리지, 더 낮은 비용"*이지
*"언제나 더 낮은 비용"*이 아닙니다. **싼 모델이 실제로 통과할 때만** 절감이 생깁니다.
모든 태스크가 최상위 모델을 진짜로 필요로 하면, 올바른 선택은 그 비용을 **쓰는 것**이고,
라우팅은 정확히 그렇게 합니다 — 커버리지를 깎아 가짜 절감을 만드는 대신([실험 03](03-coverage-cliff.md)).

!!! success "양방향 재현성 계약 (`max_delta_pct`)"
    이 실험의 `expect` 블록은 **양쪽을 모두** 고정합니다:

    - `min_coverage: 1.0` — 라우팅은 (비용을 써서라도) 커버리지를 100%로 유지해야 하고,
    - `max_delta_pct: 0.0` — 이 워크로드에서 **절감이 0%를 넘으면 안 됩니다.**

    두 번째 상한은 새로 추가한 가드입니다. 만약 미래의 변경이 이 어려운 워크로드를 갑자기
    "더 싸" 보이게 만든다면(예: 신호 약화, 비용 계산 버그로 인한 **유령 절감**),
    `savings_ceiling` 체크가 실패하며 CI가 시끄럽게 깨집니다. 절감은 위로도 아래로도
    정직해야 합니다.

## 이 실험을 언제 쓰나

- 라우팅 도입 전, **"우리 워크로드에서도 이득이 날까?"**를 정직하게 가늠할 때.
  이득은 **싼 모델이 통과하는 태스크의 비율**에 달려 있습니다.
- "라우팅 켰는데 왜 안 싸지지?"라는 질문에, *"그건 실패가 아니라 어려운 워크로드의 정직한
  결과"*임을 숫자로 설명할 때.
- 벤치마크·데모가 **과장된 절감**을 보고하지 않도록 CI에 **상한 계약**을 걸 때.

## 이 실험 재현하기

```bash
pip install -e .
cost-router experiment run limits          # 사람이 읽는 요약
cost-router experiment run limits --json   # 기계가 읽는 전체 요약 + 계약 체크
```
