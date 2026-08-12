# 실험 01 · 싼 모델로 먼저, 실패할 때만 올리기

!!! abstract "한 줄 요약 — 이 저장소의 '히어로' 실험"
    합성 워크로드 100건을 두 방식으로 실행합니다. 비용 인지 라우팅은 **커버리지 100%를
    유지**하면서 모든 태스크에 프리미엄 모델을 쓰는 나이브 방식보다 비용이 **25.5%
    낮습니다**. 모든 수치는 `measured = false`.

<figure markdown="span">
  ![히어로 루프 애니메이션 — 순진한 레인과 비용 인지 레인이 나란히 도는 모습](/foundry-cost-aware-model-routing/assets/gif/hero.gif)
  <figcaption>히어로 루프 — 순진한 레인은 모든 태스크를 프리미엄으로, 비용 인지 레인은 값싼 후보부터 시도해 실패한 검사에서만 한 단계 올린다.</figcaption>
</figure>

## 이 실험은 무엇인가

- **상황(언제):** 저장소를 처음 열어 30초 안에 "정말 동작하는지" 확인하고 싶은 순간. 난이도가
  섞인 실제형 코딩 에이전트 워크로드를 가정합니다.
- **작업(무엇을):** `plan`·`generate`·`test`·`validate`·`repo_patch` 다섯 클래스가 섞인 합성
  태스크 **100건**을 라우팅합니다.
- **실험(무엇을 검증):** 비용 인지 라우팅이 나이브(항상 프리미엄) 대비 **커버리지 100%를
  지키면서** 비용을 낮추는지, 그리고 그 결과가 재현성 계약(`expect`)의 하한을 통과하는지.

- **설정 파일:** `experiments/hero.yaml`
- **데이터:** 합성 워크로드 100건 (`--synth`, 결정론적 신호)
- **정책/가격:** 번들 시드 정책 / 번들 예시 가격
- **재현성 계약:** 커버리지 ≥ 100%, 절감 ≥ 20%, 태스크 ≥ 100

## 실행

```bash
cost-router hero
```

## 결과 — before / after

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $2.23
  AFTER   cost-aware routing                   $1.66
  SAVED   $0.57  (25.5% lower)  at 100.0% coverage
```

| 지표 | 값 |
| --- | --- |
| 태스크 수 | 100 |
| 커버리지 | 100.0% |
| 나이브 비용 | $2.23 |
| 라우팅 비용 | $1.66 |
| 절감액 | $0.57 |
| 절감률 | 25.5% |

> 정본: 이 실험의 대표 수치는 [오프라인 실험 결과](../manual/projection-results.md)에 모여 있습니다 — 재런하면 그 페이지가 기준입니다.

## 스포트라이트 — 대표 태스크

`spotlight: auto`가 고른, 나이브/라우팅 비율이 가장 큰 수용 태스크입니다.

```text
spotlight  t-0078 · validate · clean-first
  routed  mini-fast      $0.0003
  naive   deep-reasoner  $0.0071   (24.1x more)
```

`validate` 태스크는 가장 싼 후보(`mini-fast`)가 첫 시도에 깨끗하게 통과했습니다. 나이브
방식은 같은 태스크에 `deep-reasoner`를 써서 **24.1배** 더 지출했을 것입니다.

## 왜 '가장 싼 청구서'가 아닌가 — arm 비교

| arm | 커버리지 | 비용 | 메모 |
| --- | --- | --- | --- |
| cost | **22%** | $0.19 | 가장 싸지만 커버리지 붕괴 |
| balanced | 38% | $1.32 | 중간 |
| quality (naive) | 100% | $2.23 | 커버리지 100%지만 최대 비용 |
| **비용 인지 라우팅** | **100%** | **$1.66** | 커버리지 유지 + 절감 |

가장 싼 arm은 태스크의 22%만 풉니다. 비용 인지 라우팅은 검사에 실패하면 다른 모델로 옮겨
완전한 커버리지를 유지하면서 나이브보다 비용을 낮춥니다.

## 라우팅 전략 분해

```text
strategy  single-route=74 ensemble=26  |  clean-first=19 compared=18 escalated=55 tie-broken=8
```

- **single-route 74 / ensemble 26** — 4분의 3은 단일 경로로 해결, 나머지는 거버너가 앙상블로
  승격.
- **clean-first 19** — 가장 싼 후보가 첫 시도에 통과.
- **escalated 55** — 값싼 경로가 검사에 실패해 상위 후보로 이동.
- **compared 18 / tie-broken 8** — 앙상블 비교와 심판 타이브레이크.

## 계층(strata) — 위험/난이도별 비용

| 위험(risk) | 태스크 | 비용 |
| --- | --- | --- |
| high | 32 | $1.23 |
| moderate | 42 | $0.37 |
| low | 26 | $0.06 |

| 난이도 | 태스크 | 비용 |
| --- | --- | --- |
| hard | 22 | $0.63 |
| medium | 41 | $0.86 |
| easy | 37 | $0.17 |

high-risk 태스크가 비용 대부분을 씁니다. 라우팅은 이 태스크에 더 쓰고 나머지에는 덜 씁니다.

## 재현성 자체 점검

```text
reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 25.5% ≥ 20.0%
  PASS  tasks: 100 ≥ 100
```

계약을 통과하지 못하면 `cost-router hero`는 0이 아닌 코드로 종료합니다.

## 감사 원장과 함께 재현

```bash
cost-router hero --ledger reports/hero.jsonl
cost-router ledger replay --ledger reports/hero.jsonl   # status: PASS
```

## 이 실험 재현하기

```bash
pip install -e .
cost-router hero
# 기계가 읽는 전체 요약:
cost-router hero --json
```
