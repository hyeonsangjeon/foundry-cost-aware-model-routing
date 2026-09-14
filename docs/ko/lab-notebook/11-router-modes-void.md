# 실험 11 · 라우터 세 모드 비교 · 1차 (측정 실패)

!!! abstract "한 줄 요약"
    저장소 최초의 **유료 4-arm 실측 비교**에서 라우터의 Cost · Balanced · Quality 모드와
    `gpt-5.6-sol` 직접 호출을 같은 24개 코딩 과제에 적용했습니다(24과제 × 4arm × n=3 =
    288 계획 셀). 결과를 보기 **전에** 커밋한 사전등록은 두 게이트를 걸어 뒀고, 이 실행은
    **둘 다** 넘지 못해 **무효(VOID)**입니다 — ① quality arm의 채점 커버리지가
    **79.2% < 90%**였고, ② cost·balanced arm의 **unpriced 43.4%**로 두 arm이
    cost-incomplete가 됐습니다. 두 게이트는 서로 독립이며 어느 하나만으로도 무효입니다.
    그래서 이 실행은 절감 비교의 근거로 쓸 수 없습니다. 그래도 quality arm이 `direct-premium`
    보다 비쌌고, Cost 모드는 Grok을 썼으며, reasoning이 output 예산을 소진했다는 사실을
    기록했습니다. [실험 09](09-live-routing-proof.md)는 라우터 선택을,
    [실험 10](10-measured-ledger.md)은 실측 usage를 봉인하는 방법을 기록합니다.

!!! warning "이 페이지는 실제 유료 실행을 기록합니다 — 승인된 지출"
    실험 01–10이 오프라인 투영 또는 이미 캡처된 usage의 재봉인이었던 것과 달리, 이 실험은
    **명시적 승인 게이트 두 단계 — 운영자 승인, 그다음 해시된 실행 계획 승인 — 을 통과한 뒤
    실행된 실제 Azure 추론 실행**입니다.
    **가격화된 셀의 합계 $3.467533 / 예산 $20.00**(Azure 청구서 총액이 아닙니다 — 금액이
    보류된 cost·balanced arm의 Grok 셀은 이 합계에 들어 있지 않습니다), 키리스 Entra,
    디스패치 순서가 고정된 순차 실행입니다 —
    과제 단위로 돌면서 그 안에서 반복, 그 안에서 비교 전략(arm) 순입니다. 계획에서 받아 요청에
    싣는 값은
    `max_output_tokens` 하나뿐이고, 샘플링 온도는 서비스 기본값이라 이 저장소가 정하지도
    기록하지도 않습니다. 프롬프트·응답
    **원문은 공개되지 않습니다** — 봉인 스냅샷은 로컬(gitignored)에 남고, 공개 흔적에는
    `output_sha256`(채점 증거)만 실립니다([실험 10](10-measured-ledger.md)의 원문 보존 계약과 동일).

## 무엇을 물었나 — "세 모드는 정말 비용·품질을 가르나?"

- **상황(왜):** 라우터에는 `Cost` / `Balanced` / `Quality` 세 라우팅 모드가 있습니다. 오프라인
  투영은 "Cost가 싸고 Quality가 정확하다"를 **가정**했을 뿐, 같은 워크로드에서 **실측으로**
  비용과 통과율이 정말 그 순서로 갈리는지는 검증된 적이 없었습니다.
- **작업(무엇을):** 4개 arm — `router-cost`(Model Router의 Cost 모드; mode=Cost) ·
  `router-balanced`(Model Router의 Balanced 모드; routing 블록 부재=Balanced 기본값) ·
  `router-quality`(Model Router의 Quality 모드; mode=Quality) · `direct-premium`(프리미엄 모델
  직접 호출 · `gpt-5.6-sol`) — 을
  [`benchmarks/original-coding`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/tree/main/benchmarks/original-coding)
  의 24개 큐레이션 코딩 태스크에 물립니다. `24 태스크 × 4 arm × n=3 = 288 셀`, 결정론적
  실행 신호 채점, v2 합성 요율표로 비용 산정.
- **규율(먼저 고정):** 결과를 보기 전에 품질 게이트·추정 대상(estimand)·예상 방향·무효 판정 기준을
  [`prereg-03d-router-modes.md`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/prereg-03d-router-modes.md)
  에 커밋했습니다. **타임스탬프가 증빙**입니다 — 결과에 맞춰 나중에 고칠 수 없습니다.

<figure markdown="span">
  ![비용 대 통과율 산점도(실험 12 · 발행 가능한 재실행): direct-premium은 router-quality보다 비용이 낮고 통과율이 높다. router-cost는 같은 통과율에서 비용이 가장 낮다](/foundry-cost-aware-model-routing/assets/03d/cost-vs-quality-scatter.svg)
  <figcaption>대조 — 이 산점도는 <strong>실험 12(발행 가능한 재실행)</strong>의 비용 대 통과율이다. 실험 11은 사전등록 게이트를 넘지 못해 발행 가능한 자기 차트가 없어, 두 원인을 고친 뒤 나온 실험 12의 결과를 대조로 싣는다. 바로 아래는 실험 11의 무효 처리된 실측 표다.</figcaption>
</figure>

## 결과 — arm별 채점 커버리지 · 통과율 · 비용

| arm | 라우팅 모드 | 채점 커버리지(셀) | 과제 통과율(과제) | unpriced 비율(셀) | 실측 비용 |
| --- | --- | --- | --- | --- | --- |
| `router-cost` | Cost | 95.8% (69/72) | 95.8% (23/24) | **95.8%** (전부 Grok) | — · *cost-incomplete* |
| `router-balanced` | Balanced | 94.4% (68/72) | 95.8% (23/24) | **77.8%** (56/72 Grok) | $0.259 · *cost-incomplete* |
| `router-quality` | Quality | **79.2% (57/72)** ❌ | 79.2% (19/24) | 0% | $1.791 |
| `direct-premium` | — (`gpt-5.6-sol`) | 93.1% (67/72) | 91.7% (22/24) | 0% | $1.417 |

- **가격화된 셀의 합계 $3.467533 / 예산 $20** · 288/288 셀 완주(partial=false) · 429 스로틀
  **0** · 타임아웃 7(HTTP408, 재시도 정책대로 처리) · 재생 **바이트 단위 동일**
  (`cost_mismatches: []`). 이 합계에는 fail-closed로 금액이 보류된 셀이 들어 있지 않으므로
  Azure 청구서 총액과 같지 않습니다.
- **집계 채점 커버리지는 90.6%(261/288)로 90%를 넘지만**, 게이트는 *arm별*입니다.
  `router-quality`가 **79.2%**에 그쳐 비교 전체가 무효가 됩니다.
- 두 번째 게이트도 함께 걸렸습니다 — **unpriced 43.4%**(288셀 중 125셀)로 cost·balanced arm이
  `cost_complete = false`가 됐습니다. 채점 커버리지를 통과했더라도 이 arm들의 절감 주장은
  막혔을 것입니다.

## 사전등록 예상이 틀렸다 — **고치지 않고 그대로 적는다**

사전등록은 지출 순서를 `cost ≤ balanced ≤ quality ≤ premium`으로, 통과율은 quality가 가장
높을 것으로 예상했습니다. 실측은 두 곳에서 달랐습니다.

- **비용:** `quality($1.791) > premium($1.417)`. Quality 모드의 프리미엄 서브모델 선택이
  direct 프리미엄보다 **더 비쌌고** 측정된 품질 우위도 없었습니다.
- **통과율:** quality가 **가장 낮았습니다**(0.792). 아래 발견 (2)가 그 이유를 설명하므로 이
  수치를 직접적인 품질 순위로 읽으면 안 됩니다.

!!! quote "예상을 사후 수정하지 않는 이유"
    틀린 예상을 지우고 결과에 맞춰 다시 쓰면 어떤 실행이든 "성공"처럼 보이게 만들 수 있습니다.
    사전등록의 존재 이유가 바로 그 유혹을 **구조적으로 차단**하는 것입니다. 그래서 여기엔
    "예상과 달랐다"라고 적습니다 — 그게 이 실험에서 가장 정직한 문장입니다.

## 예상 못 한 세 가지 발견

### (1) Claude가 아니라 **Grok**이었다

사전등록은 unpriced 위험을 **Claude 5종 부재**(Azure Retail에 실제 없음)로 예상했습니다. 실측에서
라우터가 실제로 간 곳은 **`grok-4-1-fast-reasoning`** 이었습니다 — 288셀 중 **125셀(43.4%)**,
특히 **Cost 모드는 100% Grok**. Claude로 간 셀은 **0건**. 예상한 위험은 나타나지 않았고
예상 못 한 백엔드가 unpriced의 원인이 됐습니다.

### (2) reasoning이 output 예산을 먼저 소진했다

`max_output_tokens = 2048`이었는데, OpenAI 계열 reasoning 모델(`gpt-5` · `gpt-5.5` · `gpt-5.6-sol`)
**20개 셀**이 그 예산을 **추론 토큰에 전부 쓰고 최종 코드를 한 글자도 내놓지 못했습니다**
(reasoning=2048에서 잘림 → output=0 → 채점 불가). 이 20개 중 15개가 quality arm에 몰리면서
quality 채점 커버리지를 79.2%로 끌어내렸습니다 — **실행을 무효로 만든 직접 원인**입니다. (반대로 Grok은
추론을 5,400 토큰까지 쓰고도 채점 가능한 본문을 냈습니다 — output 회계 방식이 provider마다 달랐습니다.)

### (3) 누락 요율 규칙이 설계대로 작동해 Grok 비용을 보류했다

라우터가 Grok으로 갔는데 비용이 보류된 것을 보고 처음엔 "카드에 Grok
요율이 빠졌다"고 의심했지만 조사 결과 **틀린 진단**이었습니다:

- Grok 기본 요율(`input $0.2 / output $0.5 /1M`)은 **이미 카드에 있고** Azure Retail과 정확히 일치합니다.
- 실측에서 Grok 셀은 **100% cached input 토큰을 돌려줬는데**, Azure Retail에는 **Grok의 cached
  meter가 존재하지 않습니다**(전 리전·전 서비스 0행 — 권위 있게 확인). 그래서 카드의 `cached: null`은 **옳습니다**.
- `composite_cost`의 **cached-token 누락 요율 가드**가 "cached 토큰이 있는데 cached 요율이 없다"를
  감지했습니다. 그래서 fail-closed 규칙이 비용을 **추측하는 대신 보류**했습니다. 이건 버그가
  아니라 [정직 계약](10-measured-ledger.md)이 설계대로 작동한 것입니다.

## 무효(VOID) 결과가 여전히 쓸모 있는 이유

이 실행은 사전등록 게이트 둘을 통과하지 못했지만 다음 증거를 남겼습니다.

- **사전등록이 자기 자신을 무효화했습니다.** 커밋해 둔 게이트(어느 arm이든 채점 커버리지
  < 90%면 무효)가 하필 겉보기로 가장 "비싸 보이는" quality arm 위에서 발동했습니다. 결과를
  본 뒤였다면 이 규칙을 느슨하게 하고 싶은 유혹이 있었겠지만, 타임스탬프가 그걸 막았습니다.
- **무결성은 온전합니다.** 288/288 완주, 예산 내(가격화된 셀 합계 $3.47 / 예산 $20), 재생
  바이트 단위 동일, 변조 불일치 0. 데이터는 신뢰할 수 있고 — 다만 이 **구성으로는** 절감을
  주장할 수 없을 뿐입니다.
- **음성 결과와 세 발견이 다음 수정을 정합니다.** 유효한 비교 전에 무엇을 고쳐야 하는지
  확인했습니다.

!!! danger "이 실행으로 주장하지 않는 것"
    - **절감률**: 두 게이트가 모두 걸려 **비교 자체가 무효**입니다 — `router-quality`의 채점
      커버리지가 90% 하한을 못 넘었고, cost·balanced arm은 unpriced 43.4%로 cost-incomplete
      입니다. `savings_claim_allowed = false`.
    - **모드 순위**: 비용·통과율 순서는 발견 (2)의 채점 손실에 오염돼 있어 결론이 아닙니다.
    - **Grok 비용**: cost·balanced arm의 Grok 셀은 fail-closed로 금액이 보류됐습니다 — 액수
      없음(0이 아니라 **미상**). 그래서 위 표의 `router-cost` 비용 칸은 `0`이 아니라 `—`입니다.
    - **Azure 청구액**: $3.467533은 **가격화된 셀의 합계**이지 이 실행의 청구서 총액이 아닙니다.

## 다음 — [실험 12](12-router-modes-measured.md)가 고쳐야 할 두 가지

| 고칠 것 | 왜 | 효과 |
| --- | --- | --- |
| **`max_output_tokens` 상향** (2048 → 제안 8192) | reasoning 모델이 예산을 추론에 다 써 코드 미출력 | quality 채점 커버리지를 90% 위로 복구 → 비교 유효화 |
| **Grok cached-input 처리 결정** | Retail에 Grok cached meter 부재 → fail-closed로 금액 보류 | cost·balanced arm의 Grok 셀 가격화 → 절감 비교 가능 |

두 수정 모두 config/요율표를 바꾸므로 **`plan_hash`가 바뀌고, 새 사전등록 + 재승인이 필요**합니다 —
이전 결과에 맞춰 게이트를 손대는 게 아니라, **결과를 보기 전에 다시 고정**하는 같은 규율을 반복합니다.

---

!!! note "재현 · 증거"
    - **사전등록(공개·커밋됨):**
      [`benchmarks/original-coding/prereg-03d-router-modes.md`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/prereg-03d-router-modes.md)
      — 게이트·추정 대상·예상·무효 기준이 결과 **이전** 타임스탬프로 고정돼 있습니다.
    - **봉인 스냅샷(로컬·gitignored):** 매니페스트·요약·트레이스·원문이 `plan_hash`에 묶여 봉인됐고,
      `measure replay`가 **바이트 단위 동일**을 재확인합니다. 원문은 계약상 공개되지 않습니다.
    - **불변식:** 이 유료 실행은 오프라인 원장(`measured = false`)과 [실험 10](10-measured-ledger.md)의
      측정 원장 바이트를 **건드리지 않습니다** — 세 감사는 서로의 정직 라벨을 흐리지 않게 분리돼 있습니다.
