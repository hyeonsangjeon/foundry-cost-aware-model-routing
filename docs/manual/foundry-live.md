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

!!! tip "실제로 돌린 실측 결과 — [실험 09](../lab-notebook/09-live-routing-proof.md)"
    이 브릿지로 진짜 Foundry Model Router에 큐레이션 프롬프트를 보냈더니, 단일 `model-router`
    배포가 **`gpt-5.4`(3건)와 `grok-4-1-fast-reasoning`(2건)**으로 실제 분기했습니다 —
    저장소 최초의 `measured = true` 실측 스냅샷(키리스 Entra). 태스크별 증거·정직함 경계는
    [실험 09 · 실측 라우팅](../lab-notebook/09-live-routing-proof.md)을 보세요.

## 1. Foundry 설정 처리

라이브 브릿지가 읽는 환경 변수입니다. 각 항목은 Foundry 전용 이름과 일반 Azure OpenAI
이름을 모두 받으며, 하나라도 없으면 전부 오프라인으로 남습니다.

| 변수 | 역할 | 대체 이름 |
| --- | --- | --- |
| `AZURE_AI_FOUNDRY_ENDPOINT` | 리소스 엔드포인트 | `AZURE_OPENAI_ENDPOINT` |
| `AZURE_AI_FOUNDRY_MODEL_ROUTER` | Model Router 배포 이름 | `AZURE_MODEL_ROUTER_DEPLOYMENT` |
| `AZURE_AI_FOUNDRY_AUTH` | 인증 방식(선택): `entra` \| `key`, 비우면 자동 | — |
| `AZURE_AI_FOUNDRY_API_KEY` | API 키 — **Entra ID 사용 시 불필요** | `AZURE_OPENAI_API_KEY` |
| `AZURE_AI_FOUNDRY_TOKEN_SCOPE` | Entra 토큰 스코프(선택, 기본 Cognitive Services) | — |
| `AZURE_AI_FOUNDRY_API_VERSION` | 데이터플레인 API 버전(선택) | `AZURE_OPENAI_API_VERSION` |
| `AZURE_AI_FOUNDRY_CONNECTION_STRING` | 관측성 전송(선택) | `APPLICATIONINSIGHTS_CONNECTION_STRING` |
| `FOUNDRY_PRICING_PATH` | 여러분 테넌트 요율 YAML(선택) | `COST_ROUTER_PRICING` |

인증은 두 가지입니다. **API 키**가 있으면 키 인증, 없으면 **Microsoft Entra ID(Azure AD)**
토큰 인증으로 자동 전환됩니다. 키 인증이 비활성화된 리소스(`disableLocalAuth=true`,
엔터프라이즈 테넌트에서 흔함)에서는 후자가 유일한 경로입니다 — 자세한 절차는
[1-bis. Microsoft Entra ID(키리스) 인증](#1-bis-microsoft-entra-idkeyless)을 보세요.

`.env.sample`을 `.env`로 복사해 로컬에서 채우세요(`.env`는 gitignored). `cost-router foundry
status`·`live` 명령은 실행 시 **이 `.env`를 자동으로 로드**한 뒤 설정을 읽습니다 — 별도의
`source`나 `export` 없이 그대로 동작합니다. 규칙은 일부러 보수적입니다:

- `.env`가 **없으면 아무 일도 하지 않습니다**(무해). CI·기본 실행은 `.env`가 없으니 그대로
  오프라인·결정론입니다.
- 이미 셸에 **export된 실제 환경 변수가 항상 우선**합니다(`.env`가 덮어쓰지 않음). CI 설정과
  명시적 export가 조용히 교체되는 일은 없습니다.
- `KEY=VALUE` 줄만 읽습니다. 빈 줄·`#` 주석·앞의 `export`는 무시하고, 값의 양끝 따옴표는
  벗깁니다. 셸 확장·명령 실행은 전혀 없습니다(값은 문자 그대로).

다른 파일을 쓰려면 `--env-file <경로>`를 주세요(기본 `.env`). 무엇이 배선됐는지는 **시크릿을
노출하지 않고** 확인할 수 있습니다:

```bash
cost-router foundry status
```

```text
Azure AI Foundry — live measured Model Router bridge
  router configured : yes
  credentialed      : yes
  auth method       : API key                          # 또는 Microsoft Entra ID (keyless)
  endpoint          : https://your-resource.example   # 호스트만 (경로·쿼리 제거)
  deployment        : model-router
  api key           : set (****WXYZ)                            # 마지막 4자만
  connection string : missing
  pricing           : (bundled illustrative — measured=false)
  .env loaded       : 3 setting(s) from .env                    # 자동 로드된 개수(값은 숨김)
  ready: `cost-router foundry live --live` (needs a workload with prompts).
```

!!! warning "시크릿은 절대 평문으로 나오지 않습니다"
    `status()`는 엔드포인트를 **스킴+호스트**로 줄이고, API 키와 연결 문자열을 **마지막 4자**로
    마스킹합니다. 배포 이름·API 버전(시크릿 아님)만 그대로 보여, 로그·화면에 붙여도
    안전합니다. `--json`으로 기계가 읽을 수도 있습니다.

### 1-bis. Microsoft Entra ID(keyless) 인증 {#1-bis-microsoft-entra-idkeyless}

엔터프라이즈 테넌트는 API 키 인증을 꺼두는 경우가 많습니다(`disableLocalAuth=true`). 이때는
키 대신 **여러분의 Azure 신원**(`az login`, 매니지드 아이덴티티, 환경 자격증명 등)에서 발급한
베어러 토큰으로 호출합니다. 브릿지는 **API 키가 없으면 자동으로 Entra ID로 전환**하므로,
설정은 사실상 "키를 비워 두는 것"이 전부입니다.

```bash
# 1) 라이브 extra 설치 (openai + azure-identity)
pip install "foundry-cost-router[foundry]"

# 2) 여러분 신원에 데이터플레인 역할 부여 — 리소스에 한 번만
az role assignment create \
  --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --role "Cognitive Services OpenAI User" \
  --scope "<리소스 resourceId>"

# 3) 로그인 (샌드박스/헤드리스는 --use-device-code)
az login --use-device-code

# 4) .env: 키는 비우고 엔드포인트+배포만 (+ 원하면 방식 고정)
#    AZURE_AI_FOUNDRY_ENDPOINT=https://your-resource.example    # 실제 리소스 호스트
#    AZURE_AI_FOUNDRY_MODEL_ROUTER=model-router
#    AZURE_AI_FOUNDRY_AUTH=entra        # 선택 — 비워도 키가 없으면 자동 entra
cost-router foundry status              # auth method : Microsoft Entra ID (keyless)
```

- **역할**: 데이터플레인 호출에는 `Cognitive Services OpenAI User`가 필요합니다(관리자
  역할인 *Contributor*로는 추론 호출이 안 됩니다).
- **스코프**: 기본 토큰 스코프는 `https://cognitiveservices.azure.com/.default`이며,
  `AZURE_AI_FOUNDRY_TOKEN_SCOPE`로 재정의할 수 있습니다.
- **강제**: 키와 Entra가 모두 가능한 환경에서 키리스를 강제하려면 `AZURE_AI_FOUNDRY_AUTH=entra`.
- **결정론 유지**: `azure-identity`는 라이브 호출 시에만 지연 임포트됩니다 — 기본 오프라인
  경로·CI는 이 패키지 없이도 그대로 동작합니다.

!!! note "시크릿을 다루지 않습니다"
    Entra 경로에는 `.env`에 넣을 키 자체가 없습니다. 토큰은 라이브 호출 순간 여러분의
    신원에서 발급되고 메모리에만 존재하며, 이 저장소는 어떤 자격증명도 저장하지 않습니다.

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

### 큐레이션 태스크를 실측으로 — 한 명령 (t-0001~t-0006)

번들 텔레메트리에는 프롬프트가 없어 라이브로 못 보냅니다. 그래서 아레나의 큐레이션 5건을
**보낼 수 있는 프롬프트와 함께** 담은 워크로드를 준비했습니다:
`samples/telemetry/curated-arena-live.sample.jsonl`. 크리덴셜을 채운 뒤 이 한 명령이면
t-0001~t-0006 **전부**가 실제 Model Router 호출로 `measured = true`가 됩니다:

```bash
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl \
  --pricing  samples/pricing/your-tenant.yaml \
  --store    runs.jsonl
```

```text
Azure Model Router — measured spend  (LIVE Azure Model Router)
  tasks             : 5
  routed cost (real): $…                 # 여러분 배포가 실제로 청구한 usage
  coverage (projected): …                # grader 없으면 오프라인 신호 투영
  provenance        : live
  measured          : yes                # 방금 일어난 라이브 호출
```

크리덴셜이 아직 없으면, **같은 워크로드를 녹화 스냅샷으로** 돌려 경로를 그대로 확인할 수
있습니다(결정론·무송신, `measured = false`):

```bash
cost-router foundry live --workload samples/telemetry/curated-arena-live.sample.jsonl
```

!!! note "왜 이 워크로드만 라이브로 보낼 수 있나"
    번들 텔레메트리(`mixed-coding-workload…`)는 `task_id`·`tokens`만 있고 **프롬프트 텍스트가
    없어** 실제 엔드포인트로 보낼 수 없습니다. `curated-arena-live…`는 아레나 5건에 **저작한
    합성 프롬프트**(표시·전송용, `measured = false`인 입력)를 붙여 라이브 전송이 가능하게 한
    것입니다. 프롬프트는 저작-합성이지만, 그걸 **실제로 보내 받은 usage·비용은 measured=true**
    입니다 — 입력의 출처(저작)와 측정의 출처(라이브)는 별개입니다. 정확도(pass/fail)까지
    측정하려면 `grader`를 주입하세요(없으면 커버리지는 오프라인 신호 투영으로 라벨).

### 임의 워크로드로

여러분의 실제 프롬프트가 있는 워크로드를 직접 줘도 됩니다:

```bash
cost-router foundry live --live --workload my-prompts.jsonl --pricing samples/pricing/your-tenant.yaml
```

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
pip install "foundry-cost-router[foundry]"   # openai + azure-identity
```

인증은 `config.auth_method`를 따릅니다:

- **키 인증** — `AzureOpenAI(api_key=…)`. `AZURE_AI_FOUNDRY_API_KEY`가 있을 때 자동 선택.
- **Entra ID(키리스)** — 키가 없으면 `azure.identity.DefaultAzureCredential`로
  `azure_ad_token_provider`를 만들어 `AzureOpenAI(azure_ad_token_provider=…)`로 호출합니다.
  `azure-identity`는 이 순간에만 지연 임포트됩니다.

```python
from router.foundry_live import AzureModelRouterClient, FoundryConfig

# 키가 없으면 auth_method == "entra" — az login 신원으로 토큰 발급
client = AzureModelRouterClient(config=FoundryConfig.from_env())

# 테스트/오프라인: 네트워크·azure-identity 없이 Entra 분기를 검증하려면
# token_provider(또는 sdk_client / RecordedRouterClient)를 주입합니다.
client = AzureModelRouterClient(
    config=FoundryConfig.from_env(),
    token_provider=lambda: "fake-bearer-token",
)
```

테스트·오프라인에서는 `sdk_client`(또는 `RecordedRouterClient`)를 주입해 네트워크 없이
전체 경로를 돌립니다.

!!! tip "정직함 규약과의 관계"
    이 브릿지는 [정직함 규약](../honesty.md)의 *"여러분 테넌트의 라이브 eval → `measured =
    true`"* 행을 실제로 채우는 코드입니다. 요율은 `samples/pricing/your-tenant.yaml`(gitignored)에
    **여러분의 실제 요율**을 넣어야 측정 지출이 여러분 범위로 정확해집니다.
