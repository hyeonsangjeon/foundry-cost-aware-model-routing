# 실험 07 · 한 번 고르기 vs 결과 보고 올리기

!!! quote "⭐ 이 저장소의 센터피스 — 내장 라우터 옆에 왜 이 자산이 존재하나"
    Azure AI Foundry **내장 Model Router**는 프롬프트당 모델을 고르는 **'선택'** 을 이미 잘 합니다
    (배포 하나·크로스 프로바이더). 이 실험은 그 위에 얹히는 층의 **존재 이유**를 한 화면에 담습니다
    — 미리 한 번 고르고 끝내기 vs 관찰-후-에스컬레이션, *비슷한 비용에*. *선택은 내장이,
    검증·거버넌스·감사는 이 저장소가.* 그리고 *"실제 라우터를 이 arm에 그대로 꽂으면?"* 의
    **측정된** 답이 [실험 09](09-live-routing-proof.md) — 키리스 Entra로 라이브 배포를 불러
    `gpt-5.4`×3·`grok-4-1-fast-reasoning`×2로 실제 갈린 이 저장소의 첫 `measured=true` 실행입니다.

!!! info "용어 — 이 페이지의 '커버리지'는 통과율입니다"
    이 실험에서 **커버리지**는 **통과율(pass rate)**, 곧 통과(해결)한 태스크의 비율을 뜻합니다
    (오프라인 CLI의 `coverage` 필드). 측정 결과(실험 11·12·03D)에서 별도로 쓰는 **채점
    커버리지**(채점된 셀 비율)와는 다른 지표입니다 → [용어집](../manual/glossary.md).

!!! abstract "한 줄 요약"
    **`single-call`**은 프롬프트마다 모델을 **한 번** 고르고 멈춥니다. **에스컬레이션이 없어**
    합성 100건에서 커버리지가 **52%**입니다. `cost-aware mix`는 결과를 확인하고 실패하면 다른
    모델로 옮겨 비슷한 비용(**$1.66 vs $1.59**)으로 커버리지 **100%**를 냅니다. 재현성 계약
    `min_escalation_gain`이 **+48%p** 차이를 고정합니다. 모든 수치는 합성 데이터에 대한 오프라인
    투영이며 `measured = false`입니다. 어떤 상용 제품의 점수가 아닙니다.

<figure markdown="span">
  ![단일 호출 레인과 관찰-후-에스컬레이션 레인의 커버리지를 나란히 비교하는 애니메이션](/foundry-cost-aware-model-routing/assets/gif/model-router.gif)
  <figcaption>한 번 고르기 vs 결과 보고 올리기 — 앞서 한 티어를 정해두는 레인과, 값싼 실패를 관찰해 필요할 때만 올리는 레인의 커버리지 대비.</figcaption>
</figure>

실제 Foundry **Model Router**의 선택 실력은 **측정된 값**이라, 자격 증명 뒤의 게이트된
어댑터(측정 브리지)로 그 결정을 이 arm에 그대로 끼워 넣을 수 있게 열어 두었습니다.

!!! tip "운영 관점 — Model Router는 '배포 하나면 알아서 된다'"
    실제 운영에서 Model Router는 **배포 하나**로 끝납니다. 지원 모델(OpenAI GPT-4/5 계열, xAI
    Grok, DeepSeek, Meta Llama, gpt-oss)은 **따로 배포하지 않아도** 라우터가 프롬프트마다 알아서
    고릅니다 — 유일한 예외는 직접 배포가 필요한 Anthropic Claude입니다. 즉 내장 라우터는 이미
    **크로스 프로바이더**입니다. 그래서 *"여러 회사 모델을 라우팅한다"* 는 사실은 차별점이 아니라
    이미 처리합니다. 이 저장소는 결과 검사, 실패 후 에스컬레이션, 모든 후보 호출 비용 계산,
    지출 제한, 감사 원장을 더합니다([핵심 개념](../manual/concept.md)). 내장 라우터를
    **대체하지 않고** **일급 후보 arm**으로 사용합니다. 아래 실험은 "한 번 고르기(라우터) vs
    관찰하고 올리기(mix)"의 커버리지 차이를 계산합니다.

## 이 실험은 무엇인가

- **상황(언제):** "Azure AI Foundry Model Router로 앙상블을 하자"는 요청에서 출발했지만,
  Model Router는 프롬프트마다 모델 하나를 고르는 **단일 호출 라우터**입니다. 이 저장소의
  `route_task`와 같은 비교에 놓습니다.
- **작업(무엇을):** `single_call`을 다섯 번째 전략으로 추가합니다. 태스크 가치로 모델 하나를
  고르고 실패해도 다른 모델로 옮기지 않습니다. 같은 오프라인 신호로 비용·커버리지를 계산하고
  "단일 호출은 에스컬레이션이 버는 커버리지를 잃는다"를 `min_escalation_gain`으로 고정합니다.
- **실험(무엇을 검증):** 합성 100건에서 (1) `single_call`은 **커버리지 52%**, (2)
  `cost-aware mix`는 **비슷한 비용**으로 **커버리지 100%**를 내고, (3) **+48%p** 차이가
  30% 하한을 넘는지 확인합니다.

한 번 고르고 멈추는 방식과 결과를 검사한 뒤 실패하면 다른 모델을 부르는 방식은 다릅니다.
실험 01·02는 절감을, 03은 커버리지 하락을, 04는 절감 없음, 05는 모든 후보 호출 비용,
06은 팬아웃 임계값을 다뤘습니다.

## 라우팅 레이어란 무엇인가 (Model Router ≠ 앙상블)

| | 하는 일 | 커버리지 | 이 저장소의 대응 |
| --- | --- | --- | --- |
| **Model Router** (단일 호출) | 프롬프트마다 **한 모델**을 미리 고름 | 첫 선택이 실패하면 회복 불가 | `route_task`의 **ordered/단일 경로** |
| **앙상블/팬아웃** (compare) | 여러 모델을 **다 돌리고** 승자를 고름 | 높지만 [추가 호출 비용](05-ensemble-fanout.md) | `route_task`의 **compare 경로** |
| **cost-aware mix** (이 저장소) | 싼 것부터, **실패하면 에스컬레이션** | 100%를 낮은 비용으로 | `route_task` 전체 |

Azure AI Foundry Model Router는 이 저장소가 하는 일의 **제품화된 얇은 라우팅 레이어**입니다 —
프롬프트를 보고 모델을 한 번 고릅니다. 그래서 이 실험의 `single_call` arm은 그 **형태**를
투명하게 흉내 냅니다: 태스크 가치(난이도)로 클래스 사다리에서 인덱스를 고르는
`floor(value × N)` 규칙입니다(쉬우면 가장 싼 `mini-fast`, 어려우면 `premium-max`).

!!! warning "이 arm은 자리표시자다 (`measured = false`, `equivalent = illustrative`)"
    `single_call` arm은 단일 호출 라우터의 **모양**을 보여주는 투명한 프록시일 뿐,
    Azure의 내부 선택 로직이 아닙니다. 합성 100건에서 선택은 다섯 모델에 고루 퍼집니다
    (`mini-fast` 31 · `swift-coder` 23 · `balanced-pro` 20 · `deep-reasoner` 19 ·
    `premium-max` 7) — 스트로맨이 아니라 사다리 전체를 쓰는 공정한 난이도 라우터입니다.
    실제 라우터의 **선택 실력**은 측정된 값이며 아래 [측정 브리지](#측정-브리지)로
    끼워 넣습니다.

## 결과 — 한 번 고르기와 실패 후 올리기

합성 100건 워크로드의 다섯 전략입니다:

| 전략 | 비용 | 커버리지 | 위치 |
| --- | --- | --- | --- |
| all-mini | $0.19 | 22% | 싸지만 커버리지 낮음 |
| **single_call** (단일 호출) | **$1.59** | **52%** | 한 번 고르고 회복 불가 |
| cost-aware mix | $1.66 | **100%** | 실패하면 다른 모델 호출 |
| all-premium | $2.23 | 100% | 같은 커버리지, 최대 비용 |
| all-ensemble | $4.23 | 100% | 모든 후보 호출 ([팬아웃 추가 비용](05-ensemble-fanout.md)) |

핵심은 `single_call`와 `mix`의 대비입니다:

- **비용은 거의 같습니다** — 단일 호출 $1.59 vs 관찰-후-에스컬레이션 $1.66 (**+4.5%**).
- **커버리지는 두 배 차이입니다** — 52% vs 100%. **에스컬레이션 이득 = +48%p.**

즉 *"거의 같은 돈으로, 관찰하고 올리면 커버리지를 두 배로 채운다."* 단일 호출은 첫 모델이
실패하면 회복할 수 없습니다.

> 정본: single-call 통과율 격차(+48%p)는 [오프라인 실험 결과](../manual/projection-results.md)에 모여 있습니다.

## 한 번 고르면 실패한 태스크가 남는 이유

결정론적 오프라인 신호에서, 라우터가 **미리** 한 모델을 고르면 그 모델이 태스크를 통과하지
못해도 **회복 경로가 없습니다** — 그 태스크는 커버리지에서 빠집니다. 난이도 추정이 아무리
좋아도, 첫 선택이 빗나가는 태스크(여기선 48%)는 그대로 손실입니다.

`cost-aware mix`는 **가장 싼 후보부터 시도**하고 자체 체크가 실패하면 다음으로
**에스컬레이션**합니다. 거의 같은 비용으로 추가 시도가 커버리지를 100%까지 올립니다.

## 실험 07 — 에스컬레이션 이득을 계약으로 고정

```bash
cost-router experiment run single-call    # (구 이름 model-router 도 별칭으로 동작)
```

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $2.23
  AFTER   cost-aware routing                   $1.66
  SAVED   $0.57  (25.5% lower)  at 100.0% coverage

spotlight  t-0078 · validate · clean-first
  routed  mini-fast      $0.0003
  naive   deep-reasoner  $0.0071   (24.1x more)

reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 25.5% ≥ 20.0%
  PASS  tasks: 100 ≥ 100
  PASS  escalation_gain: mix 100.0% − single-call 52.0% = +48.0% ≥ 30.0%
```

새 계약 체크 `escalation_gain`은 *"관찰-후-에스컬레이션(mix)이 단일 호출(single_call)보다
커버리지를 최소 30%p 더 벌어야 한다"* 를 고정합니다. 만약 누군가 라우팅에서 에스컬레이션을
빼거나(mix가 단일 호출처럼 붕괴) arm을 부풀리면, 이득이 30%p 아래로 떨어져 **CI가
실패**합니다.

!!! note "새 역량 — 계약의 세 번째 축"
    실험 04는 `max_delta_pct`로 보고된 절감에 상한을 두고, 실험 06은 `max_tax_ratio`로 후보
    추가 호출 비용에 상한을 둡니다. 실험 07은 `min_escalation_gain`(**에스컬레이션 이득 하한**)을 더합니다 —
    "관찰이 실제로 커버리지를 벌고 있는가"를 CI가 지킵니다. 자세한 필드는
    [실험 설정(YAML)](../manual/experiments.md) 참고.

## <a name="측정-브리지"></a>측정 브리지 — 게이트된 라이브 어댑터

`single_call` arm의 선택은 자리표시자 프록시입니다. 실제 Azure AI Foundry Model Router의
**결정**을 끼워 넣고 싶다면, 의존성 없는 게이트 어댑터
`router.foundry_router.FoundryModelRouter`를 씁니다:

- **환경 변수로 게이트**됩니다 — `AZURE_AI_FOUNDRY_ENDPOINT`,
  `AZURE_AI_FOUNDRY_MODEL_ROUTER`(배포 이름), `AZURE_AI_FOUNDRY_API_KEY`. 이들이 없으면
  어댑터는 **비활성**이고 오프라인 프록시가 대신합니다.
- **네트워크를 직접 열지 않습니다** — HTTP 호출은 **주입된 `client` 콜러블**입니다(`metrics`의
  `FoundryMetricsEmitter`와 같은 방식). 이 모듈은 SDK를 임포트하지 않으므로 테스트·CI에서
  안전하고 완전히 결정론적입니다.
- **정직 경계(중요):** 라이브 **결정**을 끼워 넣어도 수치가 측정값이 되는 건 아닙니다 —
  비용·커버리지는 여전히 합성 신호에 대한 오프라인 투영(`measured = false`)이고 오직 모델
  **선택**만 라이브일 수 있습니다. `labels.decisions`가 출처(`live` / `recorded` /
  `illustrative`)를 기록해 이 구분이 사라지지 않게 합니다. 진짜 측정된 지출은 실제 토큰
  사용량과 실제 평가가 필요하며, 이 오프라인 저장소의 범위 밖입니다.

기록된 결정 스냅샷도 같은 비교에서 채점할 수 있습니다
(`samples/responses/model-router-choices.sample.json`):

```python
from router.foundry_router import load_recorded_choices, summary_from_choices
choices = load_recorded_choices("samples/responses/model-router-choices.sample.json")
arm = summary_from_choices(workload, signals, policy, pricing, choices)
# 강한 모델로 기운 기록 실행: 커버리지 100%, $0.13 — 에스컬레이션 mix($0.06)의 약 2.3배
```

이 기록 실행은 강한 모델로 기울어 커버리지 100%를 냅니다. 관찰-후-에스컬레이션 mix는 같은
커버리지를 **2.3배 싸게** 냅니다. 이번에는 기록된 라이브 결정을 **측정된 결정 경로**로
비교했습니다.

### 실제 Azure에 물리기 — `azure_router_choice_client` + `foundry router`

주입할 `client` 콜러블의 **실제 구현**은 `azure_router_choice_client`입니다. 이는 item 1이 실은
키리스 SDK 브릿지(`AzureModelRouterClient`)를 `(deployment, task) -> model` 선택 함수로
감싸, 배포가 실제로 고른 모델(정규화됨: `gpt-5.4-2026-03-05` → `gpt-5.4`)만 돌려줍니다:

```python
from router.foundry_live import AzureModelRouterClient, FoundryConfig
from router.foundry_router import FoundryModelRouter, azure_router_choice_client

client = AzureModelRouterClient(config=FoundryConfig.from_env())
router = FoundryModelRouter.from_env(client=azure_router_choice_client(client))
model = router.choose({"task_id": "t-0003", "prompt": "..."})  # 라이브 단일-호출 결정
```

CLI 한 줄로 exp-07 헤드투헤드(오프라인 프록시 pick vs 라우터의 실제 선택)를 돌릴 수 있습니다.
기본은 기록 스냅샷을 오프라인에서 재생(결정론·무송신)하고, `--live`는 실제 배포에
물어 **진짜 per-task 선택**을 보여주며, `--capture`는 그 선택을 파일로 남깁니다:

```bash
cost-router foundry router                        # 오프라인: 프록시 vs 기록된 선택
cost-router foundry router --live                 # 실제 배포가 고른 모델(측정된 결정)
cost-router foundry router --live --capture picks.json   # 진짜 선택을 스냅샷으로 포착
```

```text
Azure Model Router — single-call choice  (recorded snapshot (…/model-router-choices.sample.json))
  tasks                 : 5
  offline proxy pick    : $0.09   coverage 60.0%  (difficulty-tiered, illustrative)
  router choices        : $0.13   coverage 100.0%  (decisions: recorded)
  Δ cost vs proxy       : +$0.04
  chosen models         : balanced-pro×2, deep-reasoner×2, premium-max×1
  labels                : measured=no  decisions=recorded
```

`capture_recorded_choices`(=`load_recorded_choices`의 역함수)는 각 항목을 `decisions=recorded` /
`measured=false`로 정직하게 찍고, 최상위 `captured_from=live`가 "출처는 실제"임을 남깁니다.
`--live`로 실제 5-시리즈 이름(`gpt-5.4`·`grok-4-1-fast-reasoning`)이 나오면, 오프라인 후보
사다리(자리표시자 이름)에 대응 행이 없어 채점은 프록시로 **폴백**합니다 — 선택은 라이브지만
비용·커버리지는 여전히 오프라인 투영입니다(정직 경계 유지).

## 웹앱에서 보기 — 다섯 전략 비교

대시보드는 `single_call`을 `all-mini`·`all-premium`·`all-ensemble`·`cost-aware mix`와
함께 그립니다. `single_call`은 한 번 고르고 멈춰 커버리지가 낮고, mix는 실패 뒤 올려 완전한
커버리지를 냅니다.

[라이브 데모에서 보기 →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)

## 이 숫자를 정직하게 읽기

이 실험은 *"단일 호출 라우팅은 관찰-후-에스컬레이션보다 커버리지를 잃는다"* 를 보입니다.
하지만 두 가지 정직한 단서:

1. **`single_call` arm은 자리표시자입니다.** 실제 Foundry Model Router의 선택 실력은 이
   프록시보다 좋을 수 있습니다. 그 향상은 **측정된 값**이고 [측정 브리지](#측정-브리지)로
   끼워 넣습니다. 실제 배포 결과는 [실험 09](09-live-routing-proof.md)에 있습니다. 이 실험은
   실제 라우터의 실력을 대신 주장하지 않습니다.
2. **비용·커버리지는 오프라인 투영입니다.** 라이브 결정을 넣어도 `measured = false`입니다.
   진짜 측정된 우열은 실제 토큰·평가가 필요합니다.

따라서 정직한 규칙은: *단일 호출 라우터를 고르기 전에, 그것이 잃는 커버리지(+48%p)를
에스컬레이션이 얼마에 사는지 견줘라.* 이 실험은 그 비용·커버리지 축을 계량해 판단의 재료를
제공합니다.

## 이 실험을 언제 쓰나

- 관리형 **단일 호출 라우터**(Azure AI Foundry Model Router 등)를 도입할 때 "한 번 고르기"가
  남기는 실패 태스크 수를 확인할 때.
- 재현성 계약에 **에스컬레이션 이득 하한**(`min_escalation_gain`)을 걸어, 누군가 라우팅에서
  관찰-후-에스컬레이션을 조용히 빼면 CI가 막게 할 때.
- 실제 라우터의 결정을 **측정 브리지**로 끼워 넣어 자리표시자 프록시 대신 라이브 선택을
  채점할 때.

## 이 실험 재현하기

```bash
pip install -e .
cost-router experiment run single-call            # 사람이 읽는 요약 (에스컬레이션 이득 계약 포함)
cost-router experiment run single-call --json     # 계약 체크 + 전략 arm
cost-router replay --synth                         # 프런티어 다섯 전략을 직접 확인
```
