# 실험 01 · 히어로

!!! abstract "한 줄 요약"
    합성 워크로드 100건을 비용 인지로 라우팅하면, **커버리지 100%를 유지**하면서 나이브(모든
    태스크에 프리미엄) 대비 **25.5% 낮은 비용**을 냅니다. 모든 수치는 `measured = false`.

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
  BEFORE  naive: premium model on every task   $2.226910
  AFTER   cost-aware routing                   $1.659167
  SAVED   $0.567743  (25.5% lower)  at 100.0% coverage
```

| 지표 | 값 |
| --- | --- |
| 태스크 수 | 100 |
| 커버리지 | 100.0% |
| 나이브 비용 | $2.226910 |
| 라우팅 비용 | $1.659167 |
| 절감액 | $0.567743 |
| 절감률 | 25.5% |

## 스포트라이트 — 대표 태스크

`spotlight: auto`가 고른, 나이브/라우팅 비율이 가장 큰 수용 태스크입니다.

```text
spotlight  t-0078 · validate · clean-first
  routed  mini-fast      $0.000293
  naive   deep-reasoner  $0.007059   (24.1x more)
```

`validate` 태스크는 가장 싼 후보(`mini-fast`)가 첫 시도에 깨끗하게 통과했습니다. 나이브
방식은 같은 태스크에 `deep-reasoner`를 써서 **24.1배** 더 지출했을 것입니다.

## 왜 '가장 싼 청구서'가 아닌가 — arm 비교

| arm | 커버리지 | 비용 | 메모 |
| --- | --- | --- | --- |
| cost | **22%** | $0.187913 | 가장 싸지만 커버리지 붕괴 |
| balanced | 38% | $1.323157 | 중간 |
| quality (naive) | 100% | $2.226910 | 커버리지 100%지만 최대 비용 |
| **비용 인지 라우팅** | **100%** | **$1.659167** | 커버리지 유지 + 절감 |

핵심은 커버리지를 지키면서 비용을 낮추는 것입니다. 가장 싼 arm은 값은 싸지만 커버리지가 22%로
무너집니다.

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
| high | 32 | $1.228623 |
| moderate | 42 | $0.367087 |
| low | 26 | $0.063457 |

| 난이도 | 태스크 | 비용 |
| --- | --- | --- |
| hard | 22 | $0.630214 |
| medium | 41 | $0.856523 |
| easy | 37 | $0.172430 |

비용은 소수의 high-risk 태스크에 집중됩니다. 라우팅이 가치를 내는 지점도 바로 여기입니다.

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
