# 라우팅 모드 실측 결과 · 03D Results

> **`measured=true` 유료 실측.** 실제 Azure AI Foundry로 네 개 arm(라우팅 세 모드 + direct-premium
> 기준선)을 같은 24개 코딩 과제에 n=3으로 돌린 결과다. 288셀, 봉인 스냅샷, replay로 byte-identical
> 재생 검증됨. 이 페이지의 모든 숫자는 오프라인 투영이 아니라 **한 번의 실제 측정**에서 나왔다 —
> 그래서 강력하지만 좁다. 아래 한계를 먼저 읽어라.

!!! warning "먼저 읽을 한계 — 일반화 금지"
    - **24 과제 = evidence_tier `directional`.** 방향성 신호이지 통계적 신뢰가 아니다. 통계적
      결론에는 ~100문제가 필요하다.
    - **단일 테넌트 · 단일 리전 · 1회 측정.** replay로 *재현*은 보장되지만 모집단 추정은 아니다.
    - **타임아웃이 라우터 arm에만 불리하게 작용한다.** 라우터 백엔드는 지연이 길어(p50 12–16s)
      고정 타임아웃에 걸리고, direct-premium(4.2s)은 걸리지 않는다. 아래 **4.17%p** 통과율 격차는
      코드 품질이 아니라 이 지연 특성 차이에서 나온다.
    - **다른 워크로드로 일반화하지 마라.** 이 결과는 이 워크로드·이 테넌트·이 1회 측정에 한한다.

!!! info "정직 라벨"
    - `measured=true` — 실제 Foundry 호출과 usage(토큰·지연). 합성/투영 아님.
    - `unpriced 0%` — 모든 셀이 pinned 요율로 가격화됨(`cost_complete=true`).
    - `coverage 96.18%` (277/288) — content-graded 셀 비율(**채점 커버리지**). arm 최저 94.4% (모두 게이트 90% 통과).
    - `evidence_tier=directional` — 24 과제, 방향성.
    - `replay verified` — 봉인 스냅샷 byte-identical 재생, `plan_hash sha256:d640dc07…`,
      prereg 커밋이 실행보다 앞섬.

실지출 **$3.27 / $20.00** 예산 · 288/288 셀 · 429 스로틀 **0건** · 타임아웃 11셀(HTTP 408).

---

## 1 · Arm 비교 — 비용 · 통과율 · cost-per-pass

![arm별 총비용 가로 막대: router-cost $0.06, router-balanced $0.31, direct-premium $1.34, router-quality $1.56. 각 막대에 통과율과 cost-per-pass 주석](/foundry-cost-aware-model-routing/assets/03d/arm-cost-comparison.svg)

핵심 대비는 **가장 싼 라우터 모드 대 direct-premium 기준선**이다: `router-cost`는 과제 통과율을
95.8%로 유지하면서 direct-premium 대비 **95.2% 저렴**하다(풀정밀도 계산). 통과율 격차는 **4.17%p**
이내이고 그 격차마저 아래에서 보듯 전부 타임아웃 때문이다.

| Arm | 모드 | 총비용 | 통과율 | $/pass | 채점 커버리지 |
| --- | --- | ---: | ---: | ---: | ---: |
| `router-cost` | Cost | $0.06 | 95.8% (23/24) | $0.0028 | 94.4% |
| `router-balanced` | Balanced | $0.31 | 95.8% (23/24) | $0.0133 | 95.8% |
| `direct-premium` | — | $1.34 | 100.0% (24/24) | $0.0559 | 100.0% |
| `router-quality` | Quality | $1.56 | 95.8% (23/24) | $0.0678 | 94.4% |

*배포 매핑 — `router-cost`→`model-router-cost` · `router-balanced`→`model-router` ·
`direct-premium`→`gpt-5.6-sol` · `router-quality`→`model-router-quality`. 모든 arm은
`cost_complete=true`(unpriced 0%)로, 모든 셀이 pinned 요율로 가격화됐다.*

!!! note "통과율과 채점 커버리지는 다른 지표 — 분모가 다르다"
    표의 **통과율**(예: 23/24)은 *태스크* 기준 — 통과(해결)한 태스크 비율이다. **채점
    커버리지**(예: 68/72)는 *셀* 기준 — 실제로 채점된 셀 비율(측정 완전성)이다. 타임아웃 셀은
    채점 커버리지에서 빠지고 **동시에** 통과율에서 실패로 계상되므로, 오프라인과 달리 두 값이
    갈린다 — 그래서 `router-cost`는 통과율 95.8%(23/24)와 채점 커버리지 94.4%(68/72)가 서로
    다르다. 오타가 아니라 정의가 다른 별개의 값이다. 정의는 [용어집](glossary.md) 참고.

!!! note "두 개의 절감 기준선 — 섞지 말 것"
    - **헤드라인 95.2%** = `router-cost`($0.06) 대 **`direct-premium`**($1.34). 실무에서 흔한
      "그냥 제일 좋은 모델 직접 호출" 대비 절감이다.
    - 공개 번들(`published.json`)의 **`savings_pct=95.8%`** 는 다른 기준선이다 — best-arm 대
      **naive/worst-arm**(`router-quality` $1.56). 최선 대 최악 arm 대비다.
    - 두 숫자는 서로 다른 질문에 답한다. 이 페이지는 실무에 더 가까운 **direct-premium 기준선**을
      헤드라인으로 쓰고, 번들 값도 그대로 공개한다. 절감률은 표시 반올림이 아니라 풀정밀도 금액으로
      계산한다(표시 금액은 2자리, 서브센트·단가 평균은 4자리).

---

## 2 · 비용 × 품질 — quality 모드는 direct-premium에 지배당한다

![비용 대 통과율 산점도: direct-premium이 router-quality보다 왼쪽 위(더 싸고 통과율 높음)에 있어 router-quality가 지배당함을 보인다. router-cost는 같은 통과율에서 가장 왼쪽](/foundry-cost-aware-model-routing/assets/03d/cost-vs-quality-scatter.svg)

가장 반직관적인 발견: **`router-quality`($1.56) 모드는 `direct-premium`($1.34)에 완전히
지배당한다** — 더 비싼데 통과율은 오히려 낮다(95.8% < 100.0%). 라우터의 "품질" 모드가 프리미엄
백엔드로 올라가면서 붙는 마크업이 직접 프리미엄 호출을 이기지 못한다. 품질을 원하면 라우터의
quality 모드보다 **direct-premium을 직접 부르는 편이 싸고 정확하다** — 이 워크로드에서는.

반대로 `router-cost`는 다른 라우터 arm과 같은 통과율(95.8%)을 **1/20 이하 비용**으로 낸다. 이
워크로드에서 라우터의 가치는 "품질 상향"이 아니라 "품질 유지 + 비용 급감"에 있다.

---

## 3 · 백엔드 분포 — Cost 모드 100% Grok, 두 런 연속 재현

![arm별 실제 라우팅된 백엔드 스택 막대: router-cost는 100% grok-4-1-fast-reasoning, router-quality는 gpt-5과 gpt-5.5로 분할되고 grok 없음, direct-premium은 100% gpt-5.6-sol](/foundry-cost-aware-model-routing/assets/03d/backend-distribution.svg)

`router-cost`는 graded 셀 전부(100%)를 `grok-4-1-fast-reasoning`으로 보냈다. 이 **Cost 모드
100% Grok** 쏠림은 직전 void 런과 이번 publishable 런 **두 번 연속 재현**됐다 — 라우터 정책이
비용 모드에서 일관되게 같은 저비용 백엔드를 고른다는 방향성 증거다. `router-quality`는 정반대로
`gpt-5`(57%)와 `gpt-5.5`(43%)로 나뉘고 Grok은 전혀 쓰지 않는다. (분포는 graded 셀 기준 —
타임아웃으로 백엔드가 확정되지 않은 셀은 제외.)

---

## 4 · 타임아웃 11셀 — 숨기지 않는다

11셀이 HTTP 408로 타임아웃했다(전체의 3.8%). **전부 라우터 arm에서만** 발생했다 —
`direct-premium`은 0건이다.

| 분해 | 내역 |
| --- | --- |
| arm별 | `router-cost` 4 · `router-balanced` 3 · `router-quality` 4 · `direct-premium` **0** |
| 과제별 | `toll-schedule` 7 · `dedupe-stable` 3 · `weekday-label` 1 |
| 상태 | 11셀 모두 HTTP 408 (read timeout) |

타임아웃 셀은 **이중 보수 처리**된다: (1) content가 없으니 채점 커버리지에서 **제외**되고, 동시에
(2) pass=False로 **실패 계상**된다. 그래서 라우터 arm의 통과율이 direct-premium보다 정확히
이 타임아웃만큼 낮아진다. **위 4.17%p 격차는 코드 품질 차이가 아니라 지연(latency) 차이다** —
라우터 백엔드가 프리미엄보다 느려 고정 타임아웃(read 90s / overall 120s)에 먼저 걸렸다. 후속
타임아웃 상향 제안은 [Fix C 문서](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/fix-c-timeout-proposal.md)에 있다(적용 시 새 prereg + 재런 필요).

---

## 5 · 신호 분리 — 각 지표가 무엇을 증명하고, 무엇을 증명하지 않나

측정 결과를 과대해석하지 않기 위해, 지표별로 경계를 명시한다.

| 지표 (이 런의 값) | 무엇을 **증명하나** | 무엇을 **증명하지 않나** |
| --- | --- | --- |
| `measured=true` | 실제 provider 호출과 usage(토큰·지연)가 실제로 일어나 기록됨 | 코드 품질을 증명하지 않음 |
| `cost_complete=true` (unpriced 0%) | 모든 셀이 pinned 요율로 가격화됨 | 청구서와의 정합(invoice reconciliation)을 증명하지 않음 |
| pass rate 95.8–100% | 결정론적 exec-signals 채점기를 통과함 | 일반적 코드 품질 평가가 아님 |
| savings 95.2% | 이 워크로드·이 테넌트·1회 측정에서의 절감 | 다른 워크로드·테넌트로의 일반화가 아님 |

---

## 6 · 재현과 출처

- **데이터 소스**: 봉인 스냅샷을 `measure publish` 경로로 마스킹 추출한
  [`docs/assets/03d/published.json`](/foundry-cost-aware-model-routing/assets/03d/published.json). **집계·arm별 수치·백엔드
  분포만** 담는다 — 프롬프트·응답 원문, 엔드포인트, 테넌트 식별자는 포함하지 않는다(엔드포인트는
  `***.cognitiveservices.azure.com`로 마스킹, 원문은 `output_sha256`만).
- **차트**: 위 세 SVG는 `published.json`에서 `scripts/build_03d_dashboard.py`로 **정적 생성**된다.
  브라우저에서 데이터를 페치하지 않는다.
- **무결성**: `plan_hash sha256:d640dc07…91d2921e` · prereg 커밋이 실행보다 앞섬(D8 게이트) ·
  replay `summary_matches=true`, `cost_mismatches=[]`(byte-identical) · `partial=false`.
- **품질 게이트 판정**(prereg 고정 기준): 채점 커버리지 ≥ 90% **PASS** · min_pass ≥ 0.60 **PASS** ·
  premium 대비 drop ≤ 10%p (실측 4.17%p) **PASS** · 예산 **PASS** → **publishable**.
- **prereg 예상 적중**: 갱신 예상은 `cost < balanced < premium ≤ quality`(비용 순서)였고
  실측도 `$0.06 < $0.31 < $1.34 < $1.56`로 **맞았다**. 즉 quality 모드가 premium보다 비싸다는
  예상이 확인됐다.

같은 런의 서술형 기록은 실험노트에 있다 —
[실험 12 · 라우팅 모드 유료 실측 재런](../lab-notebook/12-router-modes-measured.md). 직전
[실험 11 · prereg VOID](../lab-notebook/11-router-modes-void.md)와 나란히 읽으면 무엇을
고쳤고(요율 커버리지·출력 상한) 무엇이 달라졌는지 보인다.
