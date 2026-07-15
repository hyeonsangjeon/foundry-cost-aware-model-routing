# 실험 02 · 큐레이션 샘플

!!! abstract "한 줄 요약"
    손으로 작성한 오프라인 신호가 붙은 **5개 태스크**를 라우팅하면, 데이터를 처음부터 끝까지
    읽으며 라우팅 결정을 눈으로 확인할 수 있습니다. 나이브 대비 **56.7% 낮은 비용**.
    모든 수치는 `measured = false`.

- **설정 파일:** `experiments/curated.yaml`
- **데이터:** 큐레이션 픽스처 (`samples/responses/routing-signals.sample.json`)
- **재현성 계약:** 커버리지 ≥ 100%, 절감 ≥ 30%, 태스크 ≥ 3

## 실행

```bash
cost-router experiment run curated
```

## 결과 — before / after

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $0.127136
  AFTER   cost-aware routing                   $0.055038
  SAVED   $0.072098  (56.7% lower)  at 100.0% coverage
```

| 지표 | 값 |
| --- | --- |
| 태스크 수 | 5 |
| 커버리지 | 100.0% |
| 나이브 비용 | $0.127136 |
| 라우팅 비용 | $0.055038 |
| 절감률 | 56.7% |

## 스포트라이트

```text
spotlight  t-0005 · validate · clean-first
  routed  mini-fast      $0.000215
  naive   deep-reasoner  $0.005121   (23.8x more)
```

## 이 실험을 언제 쓰나

- 저장소가 **정말 동작하는지** 가장 빠르게 확인하고 싶을 때(소수 태스크, 즉시 실행).
- 합성 100건이 아니라 **읽을 수 있는 소량 데이터**로 라우팅 로직을 눈으로 따라가고 싶을 때.

!!! note "큐레이션 vs 히어로"
    큐레이션 샘플의 절감률(56.7%)이 히어로(25.5%)보다 큰 것은 태스크가 적고 구성이 다르기
    때문입니다. **절감률은 워크로드 구성에 따라 달라진다**는 점을 그대로 보여주는 예입니다 —
    그래서 진짜 숫자는 여러분의 워크로드에서 측정해야 합니다.

## 이 실험 재현하기

```bash
pip install -e .
cost-router experiment run curated
cost-router experiment run curated --json
```
