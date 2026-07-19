# 라이브 실측 브릿지 · Azure Model Router

저장소의 나머지 전부는 **합성 텔레메트리에 대한 오프라인 투영**(`measured = false`)입니다.
이 페이지가 설명하는 `src/router/foundry_live.py`는 그 투영을 **실측**으로 바꾸는 **단
하나의 격리된 이음새**입니다 — 실제 Azure AI Foundry **Model Router** 배포에 진짜 프롬프트를
보내고, 라우터가 고른 실제 모델과 **실제로 청구된 토큰 usage**를 읽어 그 usage로 비용을
계산합니다.

!!! danger "정직함 경계 — 일부러 엄격하게"
    - **지출은 측정할 수 있지만, 품질은 (이 저장소로는) 측정할 수 없습니다.** 라이브 호출은
      실제 토큰을 돌려주므로 `total_cost_usd`는 진짜 측정된 지출입니다. 각 답이 *좋았는지*는
      여러분이 주입하는 **grader**가 있어야만 측정되며, 없으면 커버리지는 오프라인 신호
      투영으로 떨어지고 `coverage_measured = false`로 라벨됩니다.
    - **`measured = true`는 방금 일어난 라이브 호출에만 부여됩니다.** 녹화된 usage 스냅샷을
      재생하면 동일한 스코어링 경로를 타지만 `provenance = recorded` · `measured = false`로
      라벨됩니다 — 포착된 측정치이지, 새 측정이 아닙니다.
    - **기본 경로는 절대 송신하지 않습니다.** Azure SDK는 **선택적 의존성**이며
      `AzureModelRouterClient`를 만들 때만 지연 임포트됩니다. 그 외에는 (메트릭 이미터처럼)
      주입식 이음새라 CLI·CI·테스트는 순수 표준 라이브러리·결정론으로 남습니다.

## 1. Foundry 설정 처리

라이브 브릿지가 읽는 환경 변수입니다. 각 항목은 Foundry 전용 이름과 일반 Azure OpenAI
이름을 모두 받으며, 하나라도 없으면 전부 오프라인으로 남습니다.

| 변수 | 역할 | 대체 이름 |
| --- | --- | --- |
| `AZURE_AI_FOUNDRY_ENDPOINT` | 리소스 엔드포인트 | `AZURE_OPENAI_ENDPOINT` |
| `AZURE_AI_FOUNDRY_MODEL_ROUTER` | Model Router 배포 이름 | `AZURE_MODEL_ROUTER_DEPLOYMENT` |
| `AZURE_AI_FOUNDRY_API_KEY` | API 키 | `AZURE_OPENAI_API_KEY` |
| `AZURE_AI_FOUNDRY_API_VERSION` | 데이터플레인 API 버전(선택) | `AZURE_OPENAI_API_VERSION` |
| `AZURE_AI_FOUNDRY_CONNECTION_STRING` | 관측성 전송(선택) | `APPLICATIONINSIGHTS_CONNECTION_STRING` |
| `FOUNDRY_PRICING_PATH` | 여러분 테넌트 요율 YAML(선택) | `COST_ROUTER_PRICING` |

`.env.sample`을 `.env`로 복사해 로컬에서 채우세요(`.env`는 gitignored). 무엇이 배선됐는지는
**시크릿을 노출하지 않고** 확인할 수 있습니다:

```bash
cost-router foundry status
```

```text
Azure AI Foundry — live measured Model Router bridge
  router configured : yes
  credentialed      : yes
  endpoint          : https://your-resource.example   # 호스트만 (경로·쿼리 제거)
  deployment        : model-router
  api key           : set (****WXYZ)                            # 마지막 4자만
  connection string : missing
  pricing           : (bundled illustrative — measured=false)
  ready: `cost-router foundry live --live` (needs a workload with prompts).
```

!!! warning "시크릿은 절대 평문으로 나오지 않습니다"
    `status()`는 엔드포인트를 **스킴+호스트**로 줄이고, API 키와 연결 문자열을 **마지막 4자**로
    마스킹합니다. 배포 이름·API 버전(시크릿 아님)만 그대로 보여, 로그·화면에 붙여도
    안전합니다. `--json`으로 기계가 읽을 수도 있습니다.

## 2. 실측 스코어링 경로

핵심은 `pricing.cost_usd(model, tokens)`에 **합성 `task.tokens` 대신 응답의 실제 usage**를
넣는 것입니다. 오프라인 arm과 라이브 브릿지의 유일한 차이가 바로 이 한 곳입니다.

```python
from router.foundry_live import RouterOutcome, measured_router_summary

# 한 태스크의 실제 결과: 라우터가 고른 모델 + 청구된 토큰
outcome = RouterOutcome(
    model="gpt-4o",
    usage={"input": 1000, "cached": 200, "output": 180, "reasoning": 120},
    provenance="live",
)

summary = measured_router_summary(
    workload, signals, policy, pricing,
    client=my_client,                     # 각 태스크 -> RouterOutcome
    grader=my_grader,                     # 선택: 있으면 coverage_measured=true
    model_aliases={"gpt-4o": "balanced-pro"},  # 실제 이름 -> 요율/신호 키
)
# summary["labels"] = {measured, spend_source: "provider-usage", provenance, coverage_measured}
```

- **비용**은 `outcome.usage`를 `pricing`으로 계산 — 실측 지출.
- **커버리지**는 `grader`가 있으면 측정, 없으면 그 모델의 오프라인 신호 투영(라벨 명시).
- **`measured`**는 모든 outcome의 provenance가 `live`일 때만 `true`.
- **`model_aliases`**는 `gpt-4o` 같은 벤더 이름을 요율/신호 키로 매핑합니다.

## 3. 라이브 실행

크리덴셜 없이도 **녹화된 usage 스냅샷**을 재생해 스코어링 경로를 확인할 수 있습니다(기본):

```bash
cost-router foundry live
```

```text
Azure Model Router — measured spend  (recorded snapshot (…/model-router-usage.sample.json))
  routed cost (real): $0.156730          # 실제 usage로 계산 (합성 투영 $0.087030과 다름)
  coverage (projected): 100.0%
  provenance        : recorded
  measured          : no                 # 재생이므로 measured=false
  → this is a replay/projection; run with --live + credentials for measured=true.
```

크리덴셜이 있고 워크로드에 **프롬프트가 있으면** 실제 호출로 `measured = true`를 얻습니다:

```bash
cost-router foundry live --live --workload my-prompts.jsonl --pricing samples/pricing/your-tenant.yaml
```

!!! note "번들 워크로드는 라이브로 못 보냅니다"
    번들 텔레메트리(`samples/telemetry/…`)는 `task_id`·`tokens`만 있고 **프롬프트 텍스트가
    없어** 실제 엔드포인트로 보낼 수 없습니다. 라이브 실측에는 태스크마다 `prompt`(또는
    `messages`)가 있는 워크로드가 필요합니다. CI는 그래서 녹화 픽스처로 경로를 검증합니다.

## 4. 히스토리컬 대시보드로 연결

`--store`를 주면 실측 실행이 기존 메트릭 히스토리에 한 줄로 기록되어, 웹앱의 **Historical
dashboard** 패널과 `metrics history`가 그대로 읽습니다:

```bash
cost-router foundry live --store runs.jsonl
cost-router metrics history --store runs.jsonl
# 2026-…Z  foundry-live  cov=100.0% routed=$0.156730 …
```

행에는 `measured` 플래그와 `provenance`·`spend_source` 차원이 실려, 라이브 실측 실행과
오프라인 투영이 같은 대시보드에서 정직하게 구분됩니다.

## 5. 실제 Azure 클라이언트

`AzureModelRouterClient`는 표준 chat-completions 표면으로 배포를 호출하고, 응답의 `model`(라우터가
고른 하위 모델)과 `usage`(청구된 토큰)를 읽습니다. SDK는 `_sdk_client()`에서 지연 임포트되므로
이 모듈을 임포트해도 SDK가 필요하지 않습니다. 라이브 엑스트라를 설치하려면:

```bash
pip install "foundry-cost-router[foundry]"   # openai SDK
```

테스트·오프라인에서는 `sdk_client`(또는 `RecordedRouterClient`)를 주입해 네트워크 없이
전체 경로를 돌립니다.

!!! tip "정직함 규약과의 관계"
    이 브릿지는 [정직함 규약](../honesty.md)의 *"여러분 테넌트의 라이브 eval → `measured =
    true`"* 행을 실제로 채우는 코드입니다. 요율은 `samples/pricing/your-tenant.yaml`(gitignored)에
    **여러분의 실제 요율**을 넣어야 측정 지출이 여러분 범위로 정확해집니다.
