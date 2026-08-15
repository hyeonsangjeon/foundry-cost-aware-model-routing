# 실험 아틀라스 — 각 실험은 어떻게 구성되는가

> **시각 매뉴얼.** 대시보드의 **Experiments — click for the metrics** 스트립에는 여섯 개의 탭 —
> `adaptive`, `curated`, `ensemble`, `hero`, `limits`, `single-call` — 이 있습니다. 각 탭은 *같은*
> 라우터를 워크로드에 다시 돌려, 재현성 계약 아래에서 비용 · 커버리지 · 팬아웃 세금을 찍어 냅니다.
> 이 페이지는 그 내부를 엽니다: 각 실험이 **어떤 모델**을 쓰고, **무엇을 처리하며**, **어떤 선택
> 메커니즘**(순차 에스컬레이션, 팬아웃, 싱글콜)을 쓰는지, 그리고 **정직한 헤드라인**은 무엇인지.
> 끝은 **실측 트랙**(라이브 Foundry 브리지, 실험 09–12)으로 맺으며, 실제 환경을 직접 세울 수
> 있도록 전체 Azure 셋업 가이드로 링크를 겁니다.

!!! tip "다이어그램은 움직입니다"
    아래 메커니즘·아키텍처 SVG는 애니메이션입니다(브라우저에서 GIF처럼 반복됩니다) — 라우터가
    사다리를 걷고, 팬아웃하고, 백엔드를 고르는 과정을 지켜보세요. 마지막 섹션의 라이브 Foundry
    브리지(`measured=true`)를 *제외한* 모든 숫자는 **오프라인 결정론적 투영**(`labels.measured=false`)입니다.

## 한눈에 보기

![여섯 실험 한눈에: hero와 curated는 순차 에스컬레이션, ensemble은 팬아웃, adaptive는 팬아웃을 끄고, limits는 정직한 바닥을 보이며, single-call은 하나의 선제 선택을 믹스와 대비한다](/foundry-cost-aware-model-routing/assets/experiments-overview.svg)

어디서나 같은 모델, 같은 가격, 같은 정책. 각 실험은 정확히 **다이얼 하나** — 워크로드, 팬아웃
게이트, 비교 arm — 만 바꿔, 한 번에 한 아이디어씩 읽게 합니다.

---

## 공통 기계 장치

### 1 · 모델 사다리

모든 실험은 하나의 후보 모델 우주에서 뽑아 씁니다. 라우팅 **정책**
([`src/policy/seed_policy.yaml`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/src/policy/seed_policy.yaml))은
각 **태스크 클래스**를 싼 것부터 순서대로 나열한 후보 목록에 매핑하며, 각 후보는 두 개의 사전값 —
**통과율(pass-rate)**과 **`$/resolved`**(해결 태스크당 총 달러) — 을 담습니다.

![모델 사다리: 해결 태스크당 달러 기준으로 가장 싼 것부터 가장 비싼 것까지 정렬된 다섯 후보 모델](/foundry-cost-aware-model-routing/assets/models-ladder.svg)

| 태스크 클래스 | 정렬된 후보 (싼 것 → 비싼 것, `$/resolved`) |
| --- | --- |
| `plan` | swift-coder `0.40` · balanced-pro `1.10` · deep-reasoner `2.80` |
| `generate` | mini-fast `0.12` · swift-coder `0.35` · balanced-pro `1.05` |
| `test` | mini-fast `0.15` · swift-coder `0.38` · balanced-pro `1.00` |
| `validate` | mini-fast `0.14` · balanced-pro `0.95` · deep-reasoner `2.50` |
| `repo_patch` | swift-coder `0.55` · balanced-pro `1.40` · deep-reasoner `3.10` · premium-max `5.20` |

!!! note "모델 이름은 일반적인 대역입니다"
    `mini-fast … premium-max`는 벤더 제품이 아니라 예시용 자리표시자이며, 사전값도 (측정이 아니라)
    시드된 값입니다. 여러분은 자신의 라우팅 텔레메트리에서 유도한 값으로 이들을 대체합니다. 맨 아래
    **라이브** 섹션은 Azure Model Router가 실제로 고른 진짜 모델(`gpt-5.4`,
    `grok-4-1-fast-reasoning`)을 보여 줍니다.

### 2 · 네 개의 결정 레이어

내부에서 하나의 태스크는 네 레이어를 흐릅니다([핵심 개념](concept.md)에 상세):

```text
1. CLASSIFY  task → {plan, generate, test, validate, repo_patch}
2. POLICY    task class → ordered candidate models (pass-rate, $/resolved priors)
3. SELECT    cost-aware single route (cheapest-clean-first); escalate/fan-out on failure
4. GOVERN    a cost governor decides — before spending — whether a task is worth fanning out
```

실험마다 모양이 바뀌는 것은 **레이어 3(SELECT)**뿐입니다. 모양은 정확히 **세 가지**입니다.

### 3 · 세 가지 선택 메커니즘

=== "순차 에스컬레이션"

    후보를 싼 것 → 비싼 것 순으로 걷습니다. **첫 번째 깨끗한 결과**(자기 검증 가능한 신호:
    *적용됨 · 컴파일됨 · 테스트 통과 · 린트/타입 통과*)를 받아들입니다. 실패한 검사에서 **만**
    에스컬레이션합니다. 청구는 **받아들인** 모델 기준 — 실패한 싼 시도는 관찰될 뿐 승자로 청구되지
    않습니다. 절감의 대부분이 여기서 나옵니다.

    ![비용 인지 단일 경로: 가장 싼 후보를 먼저 시도하고, 실패한 검사에서만 에스컬레이션하며, 받아들인 모델만 청구](/foundry-cost-aware-model-routing/assets/mechanism-ordered.svg)

    *사용 · `hero` · `curated` · `limits` · `adaptive`*  ·  코드: `ordered_select()`

=== "팬아웃 (앙상블)"

    **모든** 후보를 병렬로 돌리고(`compare` 모드), 실행 신호로 각각 채점한 뒤 최고를 남깁니다.
    동점은 **가장 싼 통과** 모델로 가릅니다. 선택하지 않은 후보의 호출에도 비용이 듭니다.

    ![앙상블 팬아웃: 모든 후보를 병렬로 돌리고, 가장 싼 통과 결과를 남기며, 선택하지 않은 호출 비용도 낸다](/foundry-cost-aware-model-routing/assets/mechanism-fanout.svg)

    *사용 · `ensemble`*  ·  코드: `compare_select()`

=== "싱글콜"

    각 프롬프트를 예측 난이도로 버킷팅하고 **하나의** 모델에 선제적으로 커밋합니다 — 팬아웃도,
    에스컬레이션도 없습니다. 잘못된 선제 선택을 교정할 수 없어 커버리지가 떨어집니다. 이것은
    제품화된 라우터의 *모양*입니다; 진짜 라우터의 선택 실력은 독점이며 **측정**됩니다(마지막 섹션
    참조).

    ![싱글콜 라우팅: 난이도 티어로 프롬프트마다 하나의 모델을 선제 선택하고, 에스컬레이션 없음](/foundry-cost-aware-model-routing/assets/mechanism-single-call.svg)

    *사용 · `single-call`*  ·  코드: `single_call_pick()`

---

## 여섯 실험

각 카드는 **무엇을 처리하는지**, **어떤 모델**인지, **어떤 메커니즘**인지, 돌리는 **다이얼**,
(아래 명령으로 라이브 재유도되는) **헤드라인**, 그리고 전체 lab-notebook 항목 링크를 담습니다.

!!! info "여섯 실험이 네 차별점에 어떻게 매핑되는가 (내장 라우터의 선택 위에서)"
    Azure AI Foundry의 **내장 Model Router**는 이미 *선택*을 처리합니다 — 한 번 배포로, 크로스
    프로바이더(Grok · DeepSeek · Llama · gpt-oss는 별도 배포 없이; Claude는 예외). 아래 실험은
    선택 뒤에 일어나는 네 동작을 검사합니다. **① 검증 기반 채택**(`hero`, `curated`,
    `limits`) · **② 모든 후보 호출 비용 계산**(`ensemble`) · **③ 팬아웃 전 지출 검사**(`adaptive`) ·
    **④ 감사 추적**(측정 브리지 + 아래 원장). **single-call** 카드는 한 번 미리 고르고 멈추는
    방식과 결과를 확인한 뒤 실패하면 올리는 방식을 비교합니다. 합성 커버리지 숫자가 차이를
    보여 줍니다.

각 카드는 **반복 애니메이션으로 시작**해 자신의 실제 메커니즘 — 흐름 점, 에스컬레이션 사다리,
팬아웃 — 을 그리며, 그동안 오프라인(`measured=false`) 숫자가 라이브로 세어 올라갑니다. 이들은 위
숫자에서
[`scripts/build_experiment_gifs.py`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/scripts/build_experiment_gifs.py)
(Pillow + ffmpeg)로 결정론적으로 생성됩니다.

### `hero` — 같은 커버리지, 더 낮은 비용

![hero 루프 애니메이션: 나이브 레인은 모든 태스크를 premium-max($2.23)로 보내는 반면, 비용 인지 레인은 mini-fast를 먼저 시도하고 실패한 검사에서 한 번 에스컬레이션해 swift-coder를 남긴다 — 같은 100% 커버리지에서 25.5% 더 싸게 안착](/foundry-cost-aware-model-routing/assets/gif/hero.gif)

| | |
| --- | --- |
| **처리 대상** | 100개 합성 태스크 (결정론적 오프라인 신호, `synth: true`) |
| **모델** | 클래스별 전체 사다리 (mini-fast … premium-max) |
| **메커니즘** | **순차 에스컬레이션** |
| **다이얼** | 없음 — 플래그십 기본값 |
| **헤드라인** | **100% 커버리지 · −25.5%** vs 모든-태스크-프리미엄 ($2.23 → $1.66) |
| **계약** | `min_coverage 1.0`, `min_delta_pct 0.20`, `min_tasks 100` |

```bash
cost-router experiment run hero
```

나이브 arm은 *가장 비싼* 후보를 모든 태스크에 올립니다(100% 커버리지, $2.23). 순차 에스컬레이션은
그 100% 커버리지를 유지하되 싼-것-깨끗이-먼저로 시도해 25.5% 더 싸게 안착합니다.
→ [Lab-notebook 01](../lab-notebook/01-hero.md) · 정본 수치: [오프라인 실험 결과](projection-results.md)

### `curated` — 읽을 수 있는 다섯 태스크

![curated 루프 애니메이션: 손수 라벨링한 다섯 태스크 위에서 같은 에스컬레이션 사다리를 싼-것-깨끗이-먼저로 걸어, 모든-태스크-프리미엄보다 56.7% 아래로 안착](/foundry-cost-aware-model-routing/assets/gif/curated.gif)

| | |
| --- | --- |
| **처리 대상** | 손으로 쓴 오프라인 신호 5개 (`samples/responses/routing-signals.sample.json`) |
| **모델** | 클래스별 전체 사다리 |
| **메커니즘** | **순차 에스컬레이션** |
| **다이얼** | 없음 — 가장 작은 "되긴 되나?" 확인 |
| **헤드라인** | **100% 커버리지 · −56.7%** ($0.13 → $0.06) |
| **계약** | `min_coverage 1.0`, `min_delta_pct 0.30`, `min_tasks 3` |

```bash
cost-router experiment run curated
```

모든 라우팅 결정을 눈으로 끝까지 따라갈 만큼 작습니다.
→ [Lab-notebook 02](../lab-notebook/02-curated.md)

### `ensemble` — best-of-N, 진짜 비용을 치르고

![ensemble 루프 애니메이션: 워크로드가 다섯 후보를 병렬 호출하고, 가장 싼 통과 승자(swift-coder)를 남기며, 모든 호출 비용 ~3.7배를 기록한다](/foundry-cost-aware-model-routing/assets/gif/ensemble.gif)

| | |
| --- | --- |
| **처리 대상** | 고가치 태스크 6개 (`samples/responses/ensemble-fanout-signals.sample.json`) |
| **모델** | 클래스별 전체 사다리, 태스크마다 **전부** 실행 |
| **메커니즘** | **팬아웃 (compare)** |
| **다이얼** | 모든 태스크에 팬아웃 **켜짐** |
| **헤드라인** | **−47%** vs 나이브 ($0.25 → $0.13) · 모든 후보 호출은 승자의 **≈3.7×** (승자 ≈ $0.13, 전체 호출 ≈ $0.50) |
| **계약** | `min_coverage 1.0`, `min_delta_pct 0.40`, `min_tasks 6` |

```bash
cost-router experiment run ensemble
```

여러 모델이 각 고가치 태스크를 통과하므로 best-of-N은 **가장 싼 통과** 모델로 안착합니다 — 여전히
나이브보다 47% 아래 — 하지만 팬아웃은 진 호출의 값도 치른다는 뜻입니다.
→ [Lab-notebook 05](../lab-notebook/05-ensemble-fanout.md)

### `adaptive` — 팬아웃 다이얼, 꺼 버리기

![adaptive 루프 애니메이션: compare_min_value를 모든 태스크 가치 위로 올려 병렬 호출 다섯 줄을 하나로 줄이고, 추가 호출 비율을 3.7배에서 0.00배로 낮추며 47% 절감은 유지한다](/foundry-cost-aware-model-routing/assets/gif/adaptive.gif)

| | |
| --- | --- |
| **처리 대상** | `ensemble`과 **같은** 고가치 태스크 6개 |
| **모델** | 클래스별 전체 사다리 |
| **메커니즘** | **순차 에스컬레이션** (팬아웃 게이트로 차단) |
| **다이얼** | `budget.compare_min_value: 1.1` — 모든 태스크 가치(최대 1.0) 위 → **절대 팬아웃 안 함** |
| **헤드라인** | **100% 커버리지에서 동일한 −47%**, 추가 호출 비율은 **0.00×** |
| **계약** | `min_coverage 1.0`, `min_delta_pct 0.40`, `max_tax_ratio 0.01`, `min_tasks 6` |

```bash
cost-router experiment run adaptive
```

`ensemble`과 워크로드·절감·커버리지가 같지만 후보 추가 호출 비용은 ~$0으로 낮아집니다.
이 결정론적 투영에서는 단일 경로 에스컬레이션과 팬아웃이 같은 가장 싼 통과 모델을 고릅니다.
실제 best-of-N은 *품질*을 높일 수 있으므로 추가 호출 비용을 내기 전에 그 효과를 측정해야 합니다.
→ [Lab-notebook 06](../lab-notebook/06-fanout-dial.md)

### `limits` — 공짜 점심은 없다

![limits 루프 애니메이션: 싼 티어가 차례로 모두 실패해(mini-fast, swift-coder, balanced-pro, deep-reasoner 전부 빨강) 에스컬레이션이 모든 태스크에서 premium-max까지 끝까지 오른다 — 0.0% 절감, 정직한 지출](/foundry-cost-aware-model-routing/assets/gif/limits.gif)

| | |
| --- | --- |
| **처리 대상** | **가장 비싼 후보만 통과하는** 진짜 어려운 태스크 6개 (`hard-tasks-signals.sample.json`) |
| **모델** | 클래스별 전체 사다리 |
| **메커니즘** | **순차 에스컬레이션** (매번 꼭대기까지 오름) |
| **다이얼** | 없음 |
| **헤드라인** | **100% 커버리지에서 0.0% 절감** — 여기서는 라우팅 == 나이브 |
| **계약** | 양쪽: `min_coverage 1.0`, `min_delta_pct 0.0`, **`max_delta_pct 0.0`** |

```bash
cost-router experiment run limits
```

`hero`에 대한 의도적 counter-weight입니다. 라우팅은 싼 모델을 시도하고, 실패를 지켜보며, 모든
태스크에서 꼭대기 모델로 올바르게 에스컬레이션합니다. 절감을 지어내지 않습니다 — 그리고
**`max_delta_pct 0.0`** 상한은 훗날 어떤 변경이 어려운 작업에서 "더 싸다"는 숫자를 위조하면 CI가
요란하게 실패하게 합니다.
→ [Lab-notebook 04](../lab-notebook/04-no-free-lunch.md)

### `single-call` — 하나의 선택 대 관찰-후-에스컬레이션 { #model-router-one-pick-vs-observe-and-escalate }

![single-call 루프 애니메이션: 싱글콜 레인이 하나의 티어를 선제 선택하고 52% 커버리지에서 멈추는 반면, 에스컬레이션 레인은 싼 실패를 관찰하고 필요할 때만 올려 같은 비용 대역에서 100% 커버리지(+48퍼센트포인트)에 도달한다](/foundry-cost-aware-model-routing/assets/gif/model-router.gif)

| | |
| --- | --- |
| **역할** | ⭐ **핵심** — 내장 라우터 위 레이어를 정당화하는 직접 대비 |
| **처리 대상** | 100개 합성 태스크 |
| **모델** | 클래스별 전체 사다리 |
| **메커니즘** | **싱글콜** arm을 에스컬레이팅 **믹스**와 비교 |
| **다이얼** | `single_call` 전략 arm을 믹스와 나란히 노출 |
| **헤드라인** | 싱글콜 **52%** 커버리지 vs 믹스 **100%** — 비슷한 비용에서 **+48%p 에스컬레이션 이득** |
| **계약** | `min_coverage 1.0`, `min_delta_pct 0.20`, `min_tasks 100`, **`min_escalation_gain 0.30`** |

```bash
cost-router experiment run single-call
```

싱글콜 라우터는 어떤 검사도 보기 전에 커밋하므로 잘못된 선택을 교정할 수 없고, 이 합성 arm의
커버리지는 52%로 떨어집니다. 관찰-후-에스컬레이션 믹스는 거의 같은 비용으로 전체 커버리지를
되찾습니다.

그 수치는 일반적인 *모양*의 투영이지, 출시된 어떤 제품의 점수가 아닙니다. 진짜 Foundry Model
Router의 선택 실력은 독점이며 — 그 간극이야말로 다음 **측정** 라이브 브리지가 포착하는 것입니다.
→ [Lab-notebook 07](../lab-notebook/07-model-router.md) · 정본 수치: [오프라인 실험 결과](projection-results.md)

---

## 다섯 전략을 비용과 커버리지로 비교

대시보드는 싱글콜 arm과 라우팅 전략을 비용·커버리지 산점도 하나에 놓습니다:

![다섯 전략의 비용 대 커버리지 산점도](/foundry-cost-aware-model-routing/assets/frontier.svg)

| 전략 | 선택 | 비용 | 커버리지 |
| --- | --- | ---: | ---: |
| `all-mini` | 모든 태스크에 가장 싼 후보 | **$0.19** | 22.0% |
| `single-call` | 난이도 티어 단일 선택 | $1.59 | 52.0% |
| **`cost-aware mix`** | **싼-것-깨끗이-먼저, 실패 시 에스컬레이션** | **$1.66** | **100.0%** |
| `all-premium` (naive) | 모든 태스크에 가장 비싼 후보 | $2.23 | 100.0% |
| `ensemble-all` | 모든 모델을 모든 태스크에 팬아웃 | $4.23 | 100.0% |

**cost-aware mix**는 *둘 다 이기는 구간*에 있습니다: 100% 커버리지를, 전체 커버리지를 사는 가장 싼
비용쯤에서 — `all-premium`보다 한참 아래, `ensemble-all`의 몇 분의 일로.

---

## 오프라인 투영에서 실측 라우팅으로

위의 모든 것은 **오프라인 투영**입니다. *모델 선택*을 진짜 **실측** 결과로 바꾸려면, Azure AI
Foundry **Model Router**를 배포하고 실제 프롬프트를 라우팅하게 하세요. **하나의**
배포(`model="model-router"`)를 호출하면, 라우터가 **자기 관리 로스터에서** 백엔드를 골라
`response.model`로 어느 것인지 돌려줍니다.

![키리스 Entra 인증을 쓴 Azure AI Foundry Model Router 아키텍처](/foundry-cost-aware-model-routing/assets/azure-architecture.svg)

!!! success "이것이 바로 실험 09가 증명된 방식입니다"
    이 하나의 `model-router` 배포를 통해, 큐레이션된 프롬프트가 라이브로 **`gpt-5.4` (×3)**와
    **`grok-4-1-fast-reasoning` (×2)**로 갈렸습니다 — 서로 다른 response-id 지문(`gpt-5.4` →
    `chatcmpl-…`, grok → 순수 UUID)이 백엔드 출처를 증명합니다. 특히 **grok은 우리가 배포한 적이
    없습니다** — 계정에는 `model-router` + `gpt-5.4 / -mini / -nano`만 있어, 라우터가 *자기*
    로스터로 라우팅함을 증명합니다. 전체 증거: [Lab-notebook 09 · 라이브 라우팅 증명](../lab-notebook/09-live-routing-proof.md).

키리스 Entra 전 과정 워크스루 — 하나의 `model-router` 배포, API 키 없음, 저장소 배선, 그리고 단일
실측 패스 — 는 [Foundry 셋업](foundry-setup.md)의 복붙 가이드에 있습니다. 저장소가 배선되면
`cost-router foundry live --live`가 모든 큐레이션 태스크를 진짜 `measured=true` 호출로 바꿉니다.
거기서부터 **실측 트랙**이 네 개의 lab-notebook 항목으로 이어집니다; 아틀라스는 이를 한눈에
나열하고 상세는 링크로 뺍니다.

### `09` · 라이브 라우팅 증명 — `measured=true`

위 아키텍처가 곧 실험 09입니다: 키리스로 호출된 하나의 `model-router` 배포가 큐레이션 프롬프트를
실제로 `gpt-5.4` (×3)와 `grok-4-1-fast-reasoning` (×2)로 가릅니다. `grok`은 계정에 배포된 적이
없으므로, 이는 라우터가 **자기** 로스터에서 고른다는 직접 증거입니다.
→ [Lab-notebook 09](../lab-notebook/09-live-routing-proof.md)

### `10` · 감사 원장

그 실측 런을 나중에 몰래 편집할 수 없도록 봉인합니다: 정본이며 해시 체인으로 엮인 원장으로,
**변조 감지 가능**하고 봉인된 요율표에 대해 **비용 재현 가능**하며, 한 줄로 `PASS` 재검증됩니다 —
한 바이트만 뒤집어도 실패합니다. 이것이 위 차별점이 약속한 **④ 감사 추적**입니다.
→ [Lab-notebook 10](../lab-notebook/10-measured-ledger.md)

### `11` · 유료 라우터-모드 런 (VOID)

첫 유료 4-arm 비교(**$3.47 / $20**)는 사전에 커밋한 사전등록에 따라 **VOID**입니다 — 채점
커버리지가 **79.2%**로 **90%** arm별 바닥 아래로 떨어졌습니다. 규율로 자산으로 남긴 음성 결과:
예상이 뒤집혔습니다(Claude가 아니라 Grok이 100%; 추론 토큰이 출력을 삼킴).

**실험 arm 라벨:** `router-cost`(Model Router의 Cost 모드) · `router-balanced`(Model
Router의 Balanced 모드) · `router-quality`(Model Router의 Quality 모드) ·
`direct-premium`(프리미엄 모델 직접 호출 · `gpt-5.6-sol`).

![비용 대 통과율 산점도: direct-premium은 router-quality보다 비용이 낮고 통과율이 높다. router-cost는 같은 통과율에서 비용이 가장 낮다](/foundry-cost-aware-model-routing/assets/03d/cost-vs-quality-scatter.svg)
*이 산점도는 실험 **12**의 publishable 결과입니다 — 실험 11 자신의 유료 런은 VOID라 자기 차트가 없습니다.*
→ [Lab-notebook 11](../lab-notebook/11-router-modes-void.md)

### `12` · 유료 라우터-모드 재런 (publishable)

실험 11이 짚은 두 원인만 고쳐 **같은** 사전등록 게이트에 다시 돌립니다: 채점 커버리지가
**79.2% → 96.18%**로 회복되고 **네 arm 모두 PASS → publishable**(**$3.27 / $20**, 바이트 동일
재현)입니다. 아래 세 개의 03D 차트가 이 런의 증거입니다.

![arm별 총비용 가로 막대: router-cost $0.06, router-balanced $0.31, direct-premium $1.34, router-quality $1.56. 각 막대에 통과율과 cost-per-pass 주석](/foundry-cost-aware-model-routing/assets/03d/arm-cost-comparison.svg)
![arm별 실제 라우팅된 백엔드 스택 막대: router-cost는 100% grok-4-1-fast-reasoning, router-quality는 gpt-5과 gpt-5.5로 분할되고 grok 없음, direct-premium은 100% gpt-5.6-sol](/foundry-cost-aware-model-routing/assets/03d/backend-distribution.svg)
→ [Lab-notebook 12](../lab-notebook/12-router-modes-measured.md) · 전체 차트: [03D 실측 결과](03d-results.md)

### `13` · 요율 카드를 감사하게 된 유료 라우터-모드 런

같은 네 arm을 타임아웃을 올려 세 번째로 돌립니다. 측정은 깨끗하게 나왔습니다: 채점 커버리지
**96.18% → 99.65%**, 네 arm 모두 통과율 1.0, `cost < balanced < premium ≤ quality`도 유지
(**$4.20 / $20**). 이 런이 드러낸 것은 라우터가 아니라 우리 쪽입니다 — Balanced arm의 72개 호출 중
12개를 `gpt-5.6-terra`가 처리했는데 요율 카드에 그 행이 없어 fail-closed로 금액이 보류됐고, 그
arm은 **cost-incomplete**가 됐습니다: 보고는 하되 절감 주장은 싣지 않습니다. 봉인된 사전등록 두
건이 기존 카드의 다이제스트를 못박고 있으므로, 정정은 파일을 고치는 대신 **새 날짜 파일**로
냈습니다.
→ [Lab-notebook 13](../lab-notebook/13-router-modes-rate-card-gap.md)

---

## 무엇이 측정되고, 무엇이 아닌가

| 주장 | 라이브 브리지 | 오프라인 실험 |
| --- | --- | --- |
| **모델 선택** (어느 백엔드) | ✅ 측정 — 실제 `response.model` | 투영 |
| **토큰 사용량** (청구된 입력/출력/추론) | ✅ 측정 — 프로바이더 사용량 | 합성 |
| **wall-clock 지연** | ✅ 측정 | 미모델링 |
| **키리스 인증** | ✅ 진짜 Entra 베어러 토큰 | 해당 없음 |
| **정확도 / 커버리지** | ⚠️ `grader`를 주입하지 않으면 투영 (`coverage_measured=false`) | 투영 |
| **비용 *요율*** (토큰당 USD) | ⚠️ 예시 요율 × 실제 토큰 — 여러분의 Azure 청구서가 **아님** | 예시 |

이 페이지의 모든 오프라인 숫자는 `labels.measured=false`입니다. 라이브 브리지의 *선택, 사용량,
지연, 인증*만 `measured=true`입니다. 전체 경계는 [정직함 규약](../honesty.md)을 보세요.
