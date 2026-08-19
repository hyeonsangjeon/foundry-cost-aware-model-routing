# 실험 12 · 라우터 세 모드 비교 · 2차 (측정 성공)

!!! abstract "한 줄 요약"
    [실험 11](11-router-modes-void.md)은 quality 채점 커버리지가 79.2% < 90%라
    **무효(VOID)**였습니다. 이번 런은 거기서 확인한 원인 두 가지(Fix A · Fix B)만 바꾸고 같은
    4-arm 비교를 같은 게이트와 estimand로 다시 돌렸습니다. 채점 커버리지가 79.2%에서
    **96.18%**로 올라 **네 arm 전부 게이트를 통과 — publishable**했습니다. 실측 비용 순서는
    사전등록의 예상(`cost < balanced < premium
    ≤ quality`)과 같았습니다. 지출은 **$3.27 / $20**, replay는
    바이트 단위 동일, unpriced는 **0%**였습니다. 실험 11의 "규율이 무효를 강제했다"와 이 실험의
    "규율 아래 유효 결과가 나왔다"는 **같은 게이트를 두 번, 완화 없이** 적용한 기록입니다.

!!! warning "이 페이지도 실제 유료 런을 기록한다 — operator가 승인한 지출"
    실험 11과 동일하게, 이 재런은 **명시적 승인 게이트를 통과한 뒤 실행된 실제 Azure 추론 런**
    입니다. 총지출 **$3.269553 / 예산 $20.00**, 키리스 Entra, 디스패치 순서가 고정된 순차
    실행입니다 — 과제 단위로 돌면서 그 안에서 반복, 그 안에서 arm 순이고, arm을 훑는 순서는
    어느 과제에서나 어느 반복에서나 같습니다. 계획에서 받아 요청에 싣는 값은
    `max_output_tokens` 하나뿐이고, 샘플링 온도는 서비스 기본값이라 이 저장소가 정하지도
    기록하지도 않습니다.
    프롬프트·응답 **원문은 공개되지 않습니다** — 봉인 스냅샷은 로컬(gitignored)에
    남고, 공개 흔적에는 `output_sha256`(채점 증거)만 실립니다.

## 무엇을 고쳤나 — 음성 결과가 지목한 두 원인만

실험 11은 세 가지를 발견했고 그중 **런을 무효로 만든 두 원인**을 이 재런에서 고쳤습니다.
게이트·estimand·워크로드·디스패치 순서는 **하나도 바꾸지 않았습니다.**

| 고친 것 | 실험 11에서 왜 문제였나 | 이 재런의 효과 |
| --- | --- | --- |
| **Fix A — `grok-4-1-fast.cached: 0.2`** (요율표) | Grok이 cached input을 돌려줬는데 Azure Retail에 cached meter가 없어 fail-closed로 비용 withhold → unpriced 43.4% | **unpriced 0%.** cost·balanced arm이 cost-complete로 가격화됨 |
| **Fix B — `max_output_tokens` 2048 → 8192** (config) | reasoning 모델이 예산을 추론에 다 써 코드 미출력 → quality 채점 커버리지 79.2% | **채점 커버리지 96.18% 복구.** 전 arm 90% 게이트 통과 |

두 수정 모두 config/요율표를 바꿔 **`plan_hash`가 바뀌므로**, [새 사전등록
(`prereg-03d2-router-modes.md`)](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/prereg-03d2-router-modes.md)
을 **결과를 보기 전에** 다시 커밋하고 재승인했습니다 — 실패 기준(커버리지 90%, min_pass 0.60,
max_drop 10pp, 예산 $20)은 **완화 없이 그대로**입니다.

## 결과 — arm별 커버리지 · 통과율 · 비용 · cost-per-pass

**실험 arm 라벨:** `router-cost`(Model Router의 Cost 모드) · `router-balanced`(Model
Router의 Balanced 모드) · `router-quality`(Model Router의 Quality 모드) ·
`direct-premium`(프리미엄 모델 직접 호출 · `gpt-5.6-sol`).

<figure markdown="span">
  ![arm별 총비용 가로 막대: router-cost $0.06, router-balanced $0.31, direct-premium $1.34, router-quality $1.56. 각 막대에 통과율과 cost-per-pass 주석](/foundry-cost-aware-model-routing/assets/03d/arm-cost-comparison.svg)
  <figcaption>arm별 총비용 — router-cost가 가장 싸고 router-quality가 가장 비싸다. 각 막대에 통과율과 통과당 비용(cost-per-pass)을 함께 표기했다. 아래 표와 같은 실측 값이다.</figcaption>
</figure>

| arm | 라우팅 모드 | 채점 커버리지 | 태스크 통과율 | 실측 비용 | cost_complete | cost-per-pass |
| --- | --- | --- | --- | --- | --- | --- |
| `router-cost` | Cost | 94.4% (68/72) | 95.8% (23/24) | **$0.064867** | ✅ | **$0.00282** |
| `router-balanced` | Balanced | 95.8% (69/72) | 95.8% (23/24) | $0.305492 | ✅ | $0.01328 |
| `direct-premium` | — (`gpt-5.6-sol`) | 100% (72/72) | 100% (24/24) | $1.340535 | ✅ | $0.05586 |
| `router-quality` | Quality | 94.4% (68/72) | 95.8% (23/24) | $1.558659 | ✅ | $0.06777 |

- **총지출 $3.269553 / $20** · 288/288 완주(partial=false) · 429 스로틀 **0** · 타임아웃 11(HTTP408) ·
  집계 채점 커버리지 **96.18%(277/288)** · unpriced **0%** · replay **바이트 단위 동일**(`cost_mismatches: []`).
- **비용 순서: `cost($0.065) < balanced($0.305) < premium($1.341) < quality($1.559)`.**

## 품질 게이트 판정 — **네 arm 전부 PASS → publishable**

<figure markdown="span">
  ![비용 대 통과율 산점도: direct-premium은 router-quality보다 비용이 낮고 통과율이 높다. router-cost는 같은 통과율에서 비용이 가장 낮다](/foundry-cost-aware-model-routing/assets/03d/cost-vs-quality-scatter.svg)
  <figcaption>비용 대 통과율 산점도 — router-cost는 같은 통과율대에서 비용이 가장 낮다. router-quality는 direct-premium보다 비용이 높고 통과율이 낮다.</figcaption>
</figure>

| 게이트 | 기준 | 결과 |
| --- | --- | --- |
| 채점 커버리지 (arm별) | ≥ 90% | 최저 arm 94.4% → **PASS** |
| 최소 통과율 (arm별) | ≥ 0.60 | 최저 0.958 → **PASS** |
| premium 대비 통과율 하락 | ≤ 10 %p | 라우터 0.958 vs premium 1.000 = **4.17 %p** → **PASS** |
| 예산 | ≤ $20 | $3.27 → **PASS** |

실험 11에서 비교를 무효로 만든 **채점 커버리지 게이트가 이번엔 전 arm에서 통과**했고 나머지 게이트도
충족돼 이 런은 **savings 비교로 publishable**합니다.

## 사전등록 예상이 **맞았다** — 예상을 먼저 적고, 결과를 뒤에 적는다

재런 사전등록에 적어 둔 비용 방향 예상은 **`cost < balanced < direct-premium ≤ quality`** 였습니다
(실험 11에서 quality가 premium보다 비쌌던 실측을 반영해 갱신한 예상). 실측은 이를
**그대로 확인**했습니다: `cost($0.065) < balanced($0.305) < premium($1.341) < quality($1.559)`.

!!! quote "왜 이게 실험 11의 '뒤집힘'과 모순이 아닌가"
    실험 11의 예상은 **첫 실측 이전**의 가설(`cost ≤ balanced ≤ quality ≤ premium`)이었고 뒤집혔습니다.
    이 재런의 예상은 그 뒤집힘을 **학습해 갱신한** 새 가설(`premium ≤ quality`)이고, 이번엔 맞았습니다.
    두 문서는 각각 그때의 예상을 타임스탬프로 고정합니다 — 실험 11의 서술은 **고치지 않았습니다.**
    Quality 모드가 direct 프리미엄보다 비싼 이유는 동일합니다: **라우터 마크업이 프리미엄 서브모델
    선택 위에 얹혀** direct 호출을 넘어섭니다.

## 재현된 발견 — **Cost 모드 100% Grok, 두 런 연속**

<figure markdown="span">
  ![arm별 실제 라우팅된 백엔드 스택 막대: router-cost는 100% grok-4-1-fast-reasoning, router-quality는 gpt-5과 gpt-5.5로 분할되고 grok 없음, direct-premium은 100% gpt-5.6-sol](/foundry-cost-aware-model-routing/assets/03d/backend-distribution.svg)
  <figcaption>arm별 실제 라우팅된 백엔드 분포 — Cost 모드는 전 셀을 Grok으로, Quality 모드는 gpt 계열로 분할되고 Grok이 없다. 아래 표를 그림으로 옮긴 것이다.</figcaption>
</figure>

| arm | 실제 라우팅된 백엔드 (top) |
| --- | --- |
| `router-cost` | **`grok-4-1-fast-reasoning` 100%** (68/68) |
| `router-balanced` | `grok-4-1-fast-reasoning` 83% · `gpt-5.4` 13% · `gpt-5.5` 4% |
| `router-quality` | `gpt-5` 57% · `gpt-5.5` 43% (Grok 0건) |
| `direct-premium` | `gpt-5.6-sol` 100% |

Cost 모드는 실험 11(void)과 이 재런 모두에서 **모든 셀을 Grok으로** 보냈습니다. 사전등록은
"같은 라우팅 행동을 예상한다"고 적었고 두 번째 실측에서도 같은 동작이 나왔습니다.

## 타임아웃 11셀 — 커버리지와 통과율에 모두 반영

8192 cap(Fix B)이 켜지자 reasoning 셀의 생성이 길어져 **고정 타임아웃(read 90s / overall 120s)**을
넘긴 셀이 11개 나왔습니다 — **전부 라우터 arm**(cost 4 · balanced 3 · quality 4), direct-premium은
최장 33.5s로 0건. 태스크별로는 `toll-schedule` 7 · `dedupe-stable` 3 · `weekday-label` 1.

각 타임아웃은 두 지표에 반영됩니다:

- **커버리지에서 제외** — 본문이 없어 `output_sha256 = None` → 채점 커버리지 분자에서 빠짐.
- **동시에 통과율에서 fail** — `pass = False`로 계상되어 통과율도 깎임.

라우터 arm의 **4.17 %p 통과율 하락은 전부 타임아웃 때문이지 코드 품질이 아닙니다**. 이 감점을
없애도록 게이트를 바꾸지 않았고 타임아웃을 그대로 센 상태에서 publishable로 판정했습니다.

!!! danger "이 런으로 주장하지 않는 것 (한계 — 반드시 함께 읽을 것)"
    - **통계적 신뢰**: 24개 태스크 = `evidence_tier` **directional(방향성)**. 통계적으로 확정하려면
      태스크 **~100개**가 필요합니다. 이 결과는 방향을 가리킬 뿐 신뢰구간을 주지 않습니다.
    - **일반화 금지**: 단일 테넌트 · 단일 리전 · **1회 측정**입니다. 다른 워크로드·시점·리전으로
      이 숫자를 옮겨 쓰지 마십시오.
    - **타임아웃 비대칭**: 고정 타임아웃이 **라우터 arm에만** 불리하게 작용합니다(라우터가 느린
      reasoning 백엔드로 가고 라우팅 지연이 얹히는 구조적 특성). 통과율 격차를 "품질 차이"로
      읽으면 안 됩니다.
    - **절감률 서술은 이 구성 한정**: 게이트를 통과했다는 사실이 임의 워크로드의 절감을 보장하지 않습니다.

## 다음 — Fix C 후보 (이번 런이 새로 드러낸 것)

남은 문제는 위 **타임아웃 11셀**입니다. 성공 셀 최장 지연은 81.8s(Grok reasoning), p99
74.8s였고 **11셀 전부 `read_timeout` 90s에 도달했으며** overall 120s에는 도달하지 않았습니다.
[Fix C 제안서](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/fix-c-timeout-proposal.md)
는 read 90→180s / overall 120→240s를 제안합니다. config가 바뀌므로 **`plan_hash`가 바뀌고 새
사전등록 + 재승인이 필요**합니다. 적용 여부는 operator가 정하며 이 페이지는 제안만 기록합니다.

---

!!! note "재현 · 증거"
    - **사전등록(공개·커밋됨):**
      [`benchmarks/original-coding/prereg-03d2-router-modes.md`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/benchmarks/original-coding/prereg-03d2-router-modes.md)
      — 게이트·estimand·**갱신된 예상**·무효 기준이 결과 **이전** 타임스탬프로 고정돼 있습니다.
    - **봉인 스냅샷(로컬·gitignored):** 매니페스트·요약·트레이스·원문이 `plan_hash`
      (`sha256:d640dc07…91d2921e`)에 묶여 봉인됐고, `measure replay`가 **바이트 단위 동일**을
      재확인합니다(`cost_mismatches: []`). 원문은 계약상 공개되지 않습니다.
    - **불변식:** 이 유료 런은 오프라인 원장(`measured = false`)과 [실험 10](10-measured-ledger.md)의
      측정 원장 바이트를 **건드리지 않습니다**. 실험 11의 무효 판정 서술도 **그대로 보존**됩니다.

이 런의 봉인 traces에 남아 있던 캐시 토큰을 유료 호출 없이 사후 재집계한 기록은 별도
해설에 있습니다 — [봉인된 런에서 관측된 프롬프트 캐시](../manual/prompt-cache-observed.md).
사전등록 게이트 밖의 사후 관측이며, 이 페이지의 수치는 하나도 바뀌지 않았습니다.
