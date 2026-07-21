# Foundry 실전 구성 매뉴얼 · 실험별 세팅 A–Z

이 페이지는 **목업 시뮬레이션이 아니라 실제 Azure AI Foundry 실행**으로 각 실험을 돌리는
방법을 처음부터 끝까지 따라 할 수 있게 정리합니다. 리소스 프로비저닝(`az`), 모델 선정,
KB(그라운딩) 설정, system prompt, 팬아웃·앙상블 메커니즘, 그리고 실험별 세팅을 한 곳에
모았습니다.

!!! success "이건 전부 실측입니다 (`measured = true`)"
    아래 숫자는 키리스 **Microsoft Entra ID**로 실제 배포를 호출해 얻은 것입니다. Foundry의
    단일 `model-router` 배포가 하나의 문제집(큐레이션 5건)을 실제로 이렇게 분기했습니다:

    | 라우터가 고른 실제 모델 | 벤더 | 건수 |
    | --- | --- | --- |
    | `gpt-5.4` | OpenAI | 3 |
    | `grok-4-1-fast-reasoning` | xAI | 2 |

    포착 스냅샷: [`samples/responses/foundry-arena-measured.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/responses/foundry-arena-measured.json).
    재현: `cost-router foundry arena --live --max-output-tokens 3000`.

---

## 0. 두 개의 플레인 — 라우팅 vs 그라운딩

이 데모의 Azure 자원은 역할이 뚜렷한 **두 플레인**으로 나뉩니다. 섞지 않는 게 이해의 핵심입니다.

| 플레인 | 리소스 | 배포/자원 | 하는 일 |
| --- | --- | --- | --- |
| **라우팅 플레인** | `aoai-router5-ext-faf57f` (`rg-foundry-router-5series`, eastus2) | `model-router` + `gpt-5.4` · `gpt-5.4-mini` · `gpt-5.4-nano` | 프롬프트별 모델 선정·추론(아레나·라이브 실험) |
| **그라운딩 플레인** | `aoai-foundry-iq-demo-ext` (`rg-foundry-iq-demo-ext`, eastus) + `srch-foundry-iq-demo-ext` (Azure AI Search) | `text-embedding-3-large` + 벡터 인덱스 | KB 임베딩·검색(RAG 그라운딩) |

- **아레나/헤드투헤드 실험은 라우팅 플레인만** 씁니다(추론 전용, KB 불필요).
- **KB 그라운딩은 선택**입니다. 실험에 근거 문서를 붙이고 싶을 때만 그라운딩 플레인을 씁니다
  ([§2](#2-kb)).

---

## 1. 라우팅 플레인 프로비저닝 (`az`)

한 번만 실행하면 되는, 실제로 이 데모를 만든 명령입니다. 값은 셸 변수로 빼서 그대로 붙여넣기
좋게 했습니다.

```bash
# 0) 컨텍스트 — 테넌트/구독 고정
az login --tenant <TENANT_ID> --use-device-code   # 헤드리스/샌드박스는 device-code
az account set --subscription <SUBSCRIPTION_ID>

RG=rg-foundry-router-5series
LOC=eastus2
ACCT=aoai-router5-ext-faf57f     # 전역 유일해야 함(접미사로 충돌 회피)

# 1) 리소스 그룹
az group create -n "$RG" -l "$LOC"

# 2) AI Services(=Foundry) 계정 — 키리스만 쓰도록 로컬 인증 비활성화
az cognitiveservices account create \
  -n "$ACCT" -g "$RG" -l "$LOC" \
  --kind AIServices --sku S0 \
  --custom-domain "$ACCT" \
  --assign-identity \
  --api-properties disableLocalAuth=true       # 키 인증 OFF → Entra ID 전용
```

### 1-1. 배포 만들기 — Model Router + 5시리즈

Model Router는 **단일 배포**지만, 내부적으로 여러 벤더 모델(OpenAI GPT-5 계열, xAI Grok,
gpt-oss 등)로 프롬프트를 분기합니다. 5시리즈 3종은 아레나의 단일/팬아웃 arm이 **직접**
호출합니다.

```bash
# 라우터(하나로 다 되는 선정 레이어)
az cognitiveservices account deployment create \
  -g "$RG" -n "$ACCT" \
  --deployment-name model-router \
  --model-name model-router --model-version 2025-11-18 \
  --model-format OpenAI \
  --sku-name GlobalStandard --sku-capacity 10

# 5시리즈 3-티어 (nano=저렴, mini=중간, full=프론티어)
for M in "gpt-5.4-nano:2026-03-17" "gpt-5.4-mini:2026-03-17" "gpt-5.4:2026-03-05"; do
  NAME="${M%%:*}"; VER="${M##*:}"
  az cognitiveservices account deployment create \
    -g "$RG" -n "$ACCT" \
    --deployment-name "$NAME" \
    --model-name "$NAME" --model-version "$VER" \
    --model-format OpenAI \
    --sku-name GlobalStandard --sku-capacity 10
done

# 확인
az cognitiveservices account deployment list -g "$RG" -n "$ACCT" \
  --query "[].{name:name, model:properties.model.name, version:properties.model.version}" -o table
```

### 1-2. 키리스 역할 부여 (Entra ID)

데이터플레인 추론 호출에는 **`Cognitive Services OpenAI User`** 역할이 필요합니다(관리용
*Contributor* 로는 추론이 안 됩니다).

```bash
SCOPE=$(az cognitiveservices account show -g "$RG" -n "$ACCT" --query id -o tsv)
az role assignment create \
  --assignee "$(az ad signed-in-user show --query id -o tsv)" \
  --role "Cognitive Services OpenAI User" \
  --scope "$SCOPE"
```

### 1-3. `.env` 배선 (시크릿 없음)

`.env.sample`을 `.env`로 복사하고 **엔드포인트+배포만** 채웁니다. 키 칸은 비워 두세요 — 비어
있으면 브릿지가 자동으로 Entra ID로 전환합니다.

```bash
AZURE_AI_FOUNDRY_ENDPOINT=https://aoai-router5-ext-faf57f.cognitiveservices.azure.com/
AZURE_AI_FOUNDRY_MODEL_ROUTER=model-router
AZURE_AI_FOUNDRY_AUTH=entra        # 선택 — 비워도 키가 없으면 자동 entra
# AZURE_AI_FOUNDRY_API_KEY=        # 비워 둠 (키리스)
```

```bash
cost-router foundry status          # credentialed: yes / auth method: Microsoft Entra ID (keyless)
```

!!! tip "값은 하나도 커밋되지 않습니다"
    `.env`는 gitignored이고, `status`는 엔드포인트를 호스트까지만·키를 마스킹해서 보여줍니다.
    키리스 경로에는 애초에 저장할 키가 없습니다.

---

## 2. KB(그라운딩) 설정 — 선택 {#2-kb}

실험에 **근거 문서**(사내 위키, 리포 문서 등)를 붙이려면 벡터 인덱스를 만들어 그라운딩합니다.
라우팅 플레인엔 임베딩이 없으므로 **그라운딩 플레인**(`text-embedding-3-large` +
Azure AI Search)을 씁니다.

```bash
GRG=rg-foundry-iq-demo-ext
GACCT=aoai-foundry-iq-demo-ext          # text-embedding-3-large 보유
SEARCH=srch-foundry-iq-demo-ext         # Azure AI Search

# 1) 임베딩 배포 확인 (없으면 생성)
az cognitiveservices account deployment create \
  -g "$GRG" -n "$GACCT" \
  --deployment-name text-embedding-3-large \
  --model-name text-embedding-3-large --model-version 1 \
  --model-format OpenAI --sku-name GlobalStandard --sku-capacity 150

# 2) Search 서비스(이미 있으면 스킵)
az search service create -g "$GRG" -n "$SEARCH" -l centralus --sku Standard

# 3) Search가 임베딩 계정을 키리스로 읽도록 역할 부여
SID=$(az search service show -g "$GRG" -n "$SEARCH" --query id -o tsv)
az role assignment create \
  --assignee "$(az search service show -g "$GRG" -n "$SEARCH" --query identity.principalId -o tsv)" \
  --role "Cognitive Services OpenAI User" \
  --scope "$(az cognitiveservices account show -g "$GRG" -n "$GACCT" --query id -o tsv)"
```

그다음 **벡터 인덱스**를 만들고(필드: `id`, `content`, `contentVector`(dim 3072,
`text-embedding-3-large`)), 문서를 청크→임베딩→업서트합니다. 질의 시에는 질문을 임베딩해
kNN 검색으로 top-k 청크를 뽑아 **system prompt의 컨텍스트 블록**으로 주입합니다([§3](#3-system-prompt)).

!!! note "KB는 정직하게 '선택'"
    현재 번들 실험(아레나·큐레이션)은 **추론 전용**이라 KB를 쓰지 않습니다. 위 절차는 근거가
    필요한 실험(예: repo 그라운딩 리뷰)을 붙일 때의 표준 레시피입니다. KB를 붙여도 비용은
    임베딩+검색+추론 usage로 실측됩니다.

---

## 3. system prompt 생성 {#3-system-prompt}

system prompt는 실험의 **역할·출력계약**을 고정합니다. 코드에서는 `ArenaTask.system`(선택)로
태스크마다 주입하며, 없으면 순수 user 프롬프트만 보냅니다. 실험별 권장 system prompt:

| 실험 | system prompt (요지) |
| --- | --- |
| hero | "너는 시니어 엔지니어다. 정확하고 최소한의 코드/답을 제시하고, 불확실하면 가정을 명시하라." |
| curated | "각 문제의 acceptance 기준을 먼저 읽고, 그 기준을 충족하는 답만 제시하라." |
| ensemble | (arm별 동일 프롬프트로 공정 비교 — 팬아웃 슬레이트 전원에 같은 system) |
| adaptive | "고가치 태스크면 근거를 단계적으로 제시하고, 저가치면 간결히." |
| limits | "간결하게. 재시도/레이트리밋 상황을 가정하고 idempotent하게 답하라." |
| model-router | (system 없이 — 라우터가 난이도로 모델을 고르게 순수 프롬프트만) |

KB를 쓰는 경우 system prompt 끝에 컨텍스트 블록을 덧붙입니다:

```text
<context>
{{top_k 청크들 — 출처 표기}}
</context>
위 컨텍스트에 근거해서만 답하고, 없으면 "모름"이라고 말하라.
```

코드에서 주입:

```python
from router.foundry_arena import ArenaTask
task = ArenaTask(
    task_id="t-0006",
    title="Unit tests for merge_intervals",
    prompt="merge_intervals 유닛테스트를 작성하라 …",
    system="너는 꼼꼼한 테스트 엔지니어다. 경계/빈입력/정렬안됨 케이스를 반드시 포함하라.",
)
```

---

## 4. 팬아웃 & 앙상블 메커니즘 {#4-fanout}

네 가지 전략(arm)을 **하나의 문제**에 동시에 태워 비용·지연을 실측합니다. 각 arm은 실제 배포
호출입니다.

| arm | 배포 | 청구 방식 | 무엇을 보여주나 |
| --- | --- | --- | --- |
| `cheapest` | `gpt-5.4-nano` | single-call | 가장 싼 바닥 |
| `premium` | `gpt-5.4` | single-call | 나이브한 프론티어 상한 |
| `ensemble` | `gpt-5.4-nano + gpt-5.4-mini + gpt-5.4` (병렬 팬아웃) | **sum-all-fanout** | 전부 호출→최고만 채택 = **팬아웃 세금** |
| `router` | `model-router` | winner-only | Foundry가 프롬프트별 1개 모델 선정 |

- **팬아웃**은 슬레이트 전원을 **병렬**(`ThreadPoolExecutor`)로 호출하므로 지연은 *가장 느린*
  호출입니다(합이 아니라 max). 비용은 **전원 합산**(세금)입니다.
- **라우터**는 단 한 번 호출해 승자 모델 비용만 청구합니다.

### 실측 결과 (큐레이션 5건, `max_completion_tokens=3000`)

| arm | 실비용(5건 합) | 평균 지연 | 메모 |
| --- | --- | --- | --- |
| `cheapest` | **$0.001191** | 9,079 ms | 프론티어 대비 ~13× 저렴 |
| `premium` | $0.015368 | 4,112 ms | 추론 OFF 기본 배포 |
| `ensemble` | $0.022046 | 8,325 ms | 최고가 = 팬아웃 세금 |
| `router` | $0.020806 | 12,182 ms | grok×2 + gpt-5.4×3, 추론 ON |

!!! quote "정직한 관찰 — 투영과 실측은 다르다"
    오프라인 실험(합성 신호)의 라우터는 **비용 최적화**형이라 '가장 싸다'로 나옵니다. 그러나
    **실제 Foundry model-router는 품질 최적화**형입니다 — 어지간한 코딩 문제는 추론 모델
    (grok·gpt-5.4)로 보냅니다. 그래서 *추론을 끈* 단일 `gpt-5.4` 호출보다 라우터가 더 비쌀 수
    있습니다. 대신 라우터는 **팬아웃 앙상블보다 싸고**(1콜/1청구), 프롬프트마다 **벤더를
    적정 배치**합니다:

    - `t-0006`(유닛테스트): 라우터→`grok` **$0.00052** vs premium `gpt-5.4` $0.00376 → **7× 저렴**
    - `t-0004`(설계 플랜): 라우터→`gpt-5.4`(추론) $0.01450 vs premium(추론 OFF) $0.00801 → 라우터가 추론에 투자

    비용·지연은 **실측**, 정답 여부(정확도)는 **미채점**입니다(그래더를 주입하면 측정 가능).

---

## 5. 모델 선정 방법 — 라우터는 어떻게 고르나 {#5-selection}

`model-router` 배포에 프롬프트를 보내면, Foundry가 **난이도·요구역량**을 보고 하위 모델을
고릅니다. 응답의 `model` 필드에 **실제로 고른 모델**이 담겨 옵니다. 서로 다른 난이도의
프롬프트를 실제로 보내 관찰한 분기(실측):

| 프롬프트 성격 | 라우터가 고른 실제 모델 | 벤더 |
| --- | --- | --- |
| 사소한 질문(2+2, 번역) | `gpt-oss-120b` | 오픈소스 GPT |
| 짧은 변환/쉬운 코드 | `gpt-5.4-mini` | OpenAI |
| 코드·추론(리팩터, 리뷰, 증명) | `grok-4-1-fast-reasoning` | xAI |
| 무거운 설계/아키텍처 | `gpt-5.4` | OpenAI |

- **아무 것도 설정할 필요 없음** — 라우터가 자동 선정합니다. 여러분은 `model=model-router`로
  한 번만 호출하면 됩니다.
- **코드에서 선정 결과 읽기**: `RouterOutcome.model`(정규화 후 `gpt-5.4-2026-03-05` →
  `gpt-5.4`). 아레나는 이 값으로 요율을 매기고 `router_model_mix`에 집계합니다.

```bash
# 라우터가 프롬프트별로 무엇을 고르는지 직접 관찰 (measured)
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl --synth --json \
  | jq '.model_counts'          # 예: {"gpt-5.4-2026-03-05": 3, "grok-4-1-fast-reasoning": 2}
```

---

## 6. 실험별 세팅 {#6-per-experiment}

여섯 실험 각각을 **어떤 모델로, 어떤 프롬프트로, 어떻게 실행**하는지입니다. `실측 상태`는
지금 이 저장소에서 실제로 측정 가능한지를 뜻합니다.

### 6-1. hero — 히어로(before/after)
- **모델**: 라우팅 후(`model-router`) vs 나이브 상한(`gpt-5.4`).
- **KB**: 없음. **system**: 시니어 엔지니어 역할(§3).
- **실행(실측)**: `cost-router foundry arena --live` 의 `router` vs `premium` arm이 그대로
  before/after입니다.
- **실측 상태**: ✅ 비용·지연 실측 / 정확도 미채점.
- 관련: [실험 01 · 히어로](../lab-notebook/01-hero.md)

### 6-2. curated — 큐레이션 헤드투헤드
- **모델**: 네 arm 전부(`gpt-5.4-nano`/`gpt-5.4`/팬아웃/`model-router`).
- **입력**: `samples/telemetry/curated-arena-live.sample.jsonl` (프롬프트+acceptance 포함).
- **KB**: 없음. **system**: acceptance 우선 준수(§3).
- **실행(실측)**: `cost-router foundry arena --live --max-output-tokens 3000`.
- **실측 상태**: ✅ 비용·지연 실측 / 정확도 미채점.
- 관련: [실험 02 · 큐레이션 샘플](../lab-notebook/02-curated.md)

### 6-3. ensemble — 앙상블 팬아웃 세금
- **모델**: 팬아웃 슬레이트 `gpt-5.4-nano + gpt-5.4-mini + gpt-5.4` (병렬).
- **KB**: 없음. **system**: 슬레이트 전원 동일(공정 비교).
- **메커니즘**: [§4](#4-fanout) — 전원 호출·합산 청구가 세금, 지연은 max.
- **실측 상태**: ✅ 세금(합산 비용)·지연 실측. 실측치 $0.022046(최고가)로 세금이 실제로 보임.
- 관련: [실험 05 · 앙상블 팬아웃 세금](../lab-notebook/05-ensemble-fanout.md)

### 6-4. adaptive — 적응형 팬아웃 다이얼
- **모델**: 저가치 태스크는 라우터 단일콜, 고가치 태스크만 팬아웃으로 승격.
- **다이얼**: `compare_min_value`(오프라인 `budget.py`). 라이브에서는 태스크 가치가 임계 이상일
  때만 `ensemble_arm`을, 아니면 `router_arm`을 호출하도록 슬레이트를 조건 분기하면 됩니다.
- **KB**: 없음. **system**: 가치 기반 상세도 조절(§3).
- **실측 상태**: ⚙️ 라우터/팬아웃 arm은 실측 가능. 다이얼 임계 정책은 입력 변수로 노출
  (아래 [§7](#7-code) `FleetSlate`/가치 임계).
- 관련: [실험 06 · 적응형 팬아웃 다이얼](../lab-notebook/06-fanout-dial.md)

### 6-5. limits — 레이트리밋/실패 벽
- **모델**: 단일 티어에 동시 부하를 주어 429/스로틀을 관찰.
- **KB**: 없음. **system**: 간결·idempotent(§3).
- **주의**: 실제 429를 강제하면 비용·쿼터에 영향. 데모에서는 **동시성·재시도 백오프**를 코드로
  시연하고, 벽(fail-wall)은 낮은 `--sku-capacity` 배포에서 관찰하는 걸 권장합니다.
- **실측 상태**: ⚙️ 지연/성공률은 실측 가능(부하 주입식). 기본은 안전하게 투영 유지.
- 관련: [실험 07 · 라우팅 레이어](../lab-notebook/07-model-router.md)

### 6-6. model-router — 라우팅 레이어(단일콜)
- **모델**: `model-router` 단일 배포. 프롬프트별로 grok/gpt-5.4/gpt-oss 등 자동 선정([§5](#5-selection)).
- **KB**: 없음. **system**: 없음(라우터가 난이도로 고르게).
- **실행(실측)**: `cost-router foundry live --live …` → `model_counts`에 실제 분기.
- **실측 상태**: ✅ **저장소 최초 `measured = true`** — grok×2 + gpt-5.4×3.
- 관련: [실험 09 · 실측 라우팅](../lab-notebook/09-live-routing-proof.md)

---

## 7. 깔끔한 실행 코드 투어 {#7-code}

실험 실행부는 **읽기 쉬움**을 최우선으로 설계했습니다(`src/router/foundry_arena.py`).

### 7-1. 환경 — 트랜스포트 하나, 배포는 이름으로

```python
from router.foundry_arena import FoundryFleet, FleetSlate, ArenaTask

fleet = FoundryFleet.from_env()          # 키리스 클라이언트 1개 (Entra ID)
slate = FleetSlate()                     # cheapest/premium/ensemble/router 배포명
call  = fleet.call("gpt-5.4-nano", ArenaTask("t-1", "…"))   # 아무 배포나 이름으로
# call.model / call.usage / call.latency_ms / call.provenance == "live"
```

- **하나의 트랜스포트**(`FoundryFleet`)가 키리스 SDK 클라이언트를 한 번만 만들고, 어떤 배포든
  이름으로 호출하며 usage·지연을 함께 잽니다.
- **전략은 순수 함수**입니다: `cheapest_arm/premium_arm/ensemble_arm/router_arm(fleet, task,
  slate, pricing) -> ArmResult`. 전역 상태·숨은 부작용이 없어 가짜 클라이언트만 주입하면
  네트워크 없이 테스트됩니다.

### 7-2. 입력 변수 — 타입으로 명확하게

```python
@dataclass(frozen=True)
class ArenaTask:      # 실험 입력 1건
    task_id: str; prompt: str; title: str = ""; system: str | None = None

@dataclass(frozen=True)
class FleetSlate:     # 어떤 배포가 어떤 arm을 받치나
    router:   str = "model-router"
    cheapest: str = "gpt-5.4-nano"
    premium:  str = "gpt-5.4"
    ensemble: tuple[str, ...] = ("gpt-5.4-nano", "gpt-5.4-mini", "gpt-5.4")
```

`--workload`(프롬프트 JSONL)·`--pricing`(요율 YAML)·`--max-output-tokens`(추론 헤드룸)만
바꾸면 실험 입력이 전부 제어됩니다.

### 7-3. 원장 관리 — 해시 체인 + 비용 재생으로 검증

```python
from router.foundry_arena import MeasuredArenaLedger
ledger = MeasuredArenaLedger(path=Path("runs/arena.jsonl"), pricing=pricing)
for outcome in outcomes:
    ledger.record(outcome)       # 태스크 1건 = 원장 1줄(해시 체인 봉인)
ledger.flush()                   # append-only JSONL
```

- **오프라인 감사 원장**(`src/router/ledger/record.py`, [감사 원장](ledger.md))은 계약상 항상
  `measured = false`입니다.
- **측정 원장**(`MeasuredArenaLedger`)은 **실 라이브 호출 전용**이라 `measured = true`
  provenance가 사는 유일한 곳입니다. 둘을 분리해 정직함 경계를 코드로 강제합니다.
- 이제 측정 원장도 오프라인 원장과 **같은 두 가지 무결성 보장**을 가집니다
  (`src/router/ledger/measured.py`):
    - **변조 감지** — 각 줄은 정규 페이로드에 대한 `record_hash`로 봉인되고 `previous_hash`로
      앞줄과 연결됩니다. 한 바이트만 바뀌어도 체인이 깨집니다.
    - **결정론적 비용 재생** — 각 줄은 채점에 쓴 `pricing_snapshot`(요율표)을 품고 있어,
      검증이 **기록된 토큰 usage × 그 요율표**로 모든 호출 비용을 다시 계산해 일치를 확인합니다.
      측정된 usage는 고정된 증거이고, 비용은 그 순수 함수입니다.

```bash
# 측정 원장 검증: 해시 체인 + 비용 재생
cost-router ledger measured-replay --ledger runs/arena.jsonl
```

```text
records: 5
replayed: 5
  → each recorded call cost re-derived from its usage × the pinned rate card
status: PASS
```

`foundry arena --ledger`는 flush 직후 이 검증을 자동으로 돌려
`ledger: +N measured row(s) → … (hash-chain + cost-replay: OK)`를 출력합니다.

### 7-4. 한 번에 재현

```bash
# 라이브 4-way 아레나 (비용·지연 실측) + 리포트/원장 저장
cost-router foundry arena --live --max-output-tokens 3000 \
  --out runs/arena-measured.json --ledger runs/arena.jsonl

# 라우터 단일콜 실측 (프롬프트별 모델 분기 확인)
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl --synth --json
```

!!! danger "정직함 경계 요약"
    - **비용·지연 = 실측**(실제 usage×요율, 실제 wall-clock). 요율은 공개 리스트가 기본이며,
      정확한 테넌트 지출은 `--pricing`으로 테넌트 요율을 주입하세요.
    - **정확도 = 미채점**(`accuracy: ungraded`). 답의 정오는 그래더를 주입해야 측정됩니다.
    - **`measured = true`는 방금 일어난 라이브 호출에만** 부여됩니다.
