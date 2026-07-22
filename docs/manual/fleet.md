# 플릿 등록 & 모델 선택 · Fleet

실측 아레나(`cost-router foundry arena`)와 대시보드는 **네 개의 전략 아암**을 굴립니다 —
**router(메인)**, **cheapest(하한)**, **premium(상한)**, **ensemble(팬아웃)**. 각 아암을
어떤 **실제 배포 모델**이 맡을지는 지금까지 코드에 하드코딩돼 있었습니다. `src/router/fleet.py`는
그 매핑을 여러분이 소유하는 작은 **환경 파일(플릿 설정)**로 승격합니다 — "사용할 모델을
환경파일에 등록한다"는 바로 그 단계입니다.

!!! note "플릿 = 카탈로그 + 역할 배정"
    - **카탈로그**: 실제로 배포해 둔 모델 목록. 각 항목은 가격표·리포트에 쓰는 논리
      `name`, 라이브 클라이언트가 호출하는 Azure `deployment` 이름, 그리고 자유 형식 `tier`.
    - **역할 배정(slate)**: 어느 카탈로그 모델이 어느 아암을 맡는지. `name`과 `deployment`는
      보통 같지만, 하나의 논리 모델이 다르게 명명된 배포를 가리킬 수 있도록 **의도적으로
      분리**돼 있습니다.

## 1. 플릿 설정 파일

```yaml
# samples/fleet/foundry-5series.fleet.yaml
version: 1
models:
  - { name: gpt-5.4-nano, deployment: gpt-5.4-nano, tier: small,    label: "GPT-5.4 nano — cheap floor" }
  - { name: gpt-5.4-mini, deployment: gpt-5.4-mini, tier: mid,      label: "GPT-5.4 mini — mid tier" }
  - { name: gpt-5.4,      deployment: gpt-5.4,      tier: frontier, label: "GPT-5.4 — frontier ceiling" }
  - { name: model-router, deployment: model-router, tier: router,   label: "Foundry Model Router" }
roles:
  router: model-router
  cheapest: gpt-5.4-nano
  premium: gpt-5.4
  ensemble: [gpt-5.4-nano, gpt-5.4-mini, gpt-5.4]
```

실행을 이 파일로 향하게 하는 방법(우선순위 높은 순):

1. `--fleet PATH` 플래그
2. `FOUNDRY_FLEET_PATH`(또는 `COST_ROUTER_FLEET`) 환경 변수 — `.env`에 두면 자동 로드
3. 번들 샘플 `samples/fleet/foundry-5series.fleet.yaml`
4. 코드 내 기본값(파일이 전혀 없어도 항상 동작 — 오프라인 결정론 보존)

`deployment`를 여러분 리소스가 실제로 가진 이름으로 바꾸고, `name`을 가격표 YAML의 행과
맞추면 됩니다.

### 1-1. `provider` — 어느 호출 표면으로 부를지 (멀티프로바이더)

Foundry(`kind=AIServices`) 리소스 **하나**는 Azure OpenAI 모델과 파트너/OSS 모델을 **같은
엔드포인트**에 함께 호스팅합니다. 다만 실제 호출이 나가는 **와이어 경로(표면)**는 둘로 나뉩니다.
카탈로그 항목의 `provider` 필드가 이를 고릅니다:

| `provider` | 호출 표면 | 대상 모델 |
|---|---|---|
| `openai` (기본) | Azure OpenAI chat-completions (`*.openai.azure.com`) | Model Router, GPT-5.x / GPT-4o 계열 |
| `foundry` | Azure AI Model Inference (`*.services.ai.azure.com/models`) | DeepSeek·Mistral·xAI·Moonshot·Meta(Llama)·Cohere·MS(Phi) 등 파트너/OSS |

```yaml
models:
  - { name: gpt-5.6-sol,      deployment: gpt-5.6-sol,      tier: frontier }              # provider 생략 = openai
  - { name: deepseek-v4-pro,  deployment: deepseek-v4-pro,  tier: frontier, provider: foundry }
```

- OpenAI 계열은 `provider`를 **생략**하면 됩니다(기본 `openai`, YAML에도 안 써집니다).
- 파트너 표면 엔드포인트는 `AZURE_AI_FOUNDRY_ENDPOINT`의 리소스 이름에서 자동 유도됩니다
  (`https://<리소스>.services.ai.azure.com/models`). 다르면 `AZURE_AI_FOUNDRY_INFERENCE_ENDPOINT`로
  덮어씁니다. 인증은 OpenAI 표면과 **동일한 Entra ID(키리스)** 자격을 그대로 씁니다.
- 전체 13배포(OpenAI 5 + 파트너 7 + 임베딩)를 등록한 실제 예시는
  `samples/fleet/foundry-ext-full.fleet.yaml`(가격표는 `samples/pricing/foundry-ext-full.yaml`)입니다.
  `cost-router models list`의 **surface** 열에서 각 모델이 어느 표면을 쓰는지 바로 확인할 수 있습니다.

!!! note "`provider` 태그가 의미 있는 곳"
    Model Router arm은 이 파트너 모델 상당수를 **이미 내부에서 크로스 프로바이더로** 라우팅합니다
    (별도 배포 불필요 — [실험 07](../lab-notebook/07-model-router.md)). 따라서 이 `provider` 태그는
    라우터를 거치지 않고 **직접 호출**하는 arm — cheapest·premium·ensemble 팬아웃 — 이 파트너 표면을
    부를 때 의미가 있습니다. 멀티프로바이더 라우팅 자체는 내장 기능(table-stakes)이고, 이 저장소의
    가치는 그 위의 검증·앙상블·거버너·감사 축에 있습니다.

## 2. 터미널에서 선택 (`/model` 피커)

카탈로그를 보고, 각 아암에 어떤 모델을 넣을지 고릅니다. 선택은 gitignore된
`.foundry-fleet.local.yaml`에 저장돼 실제 배포 이름이 커밋되지 않습니다.

```bash
cost-router models list            # 카탈로그 + 현재 slate + 라이브 준비 상태
cost-router models show            # 역할 -> 배포 해석 결과만
cost-router models select          # 대화형: 아암마다 번호나 이름 입력 (/model 스타일)
```

비대화형(스크립트·CI)으로는 플래그로 직접 지정합니다:

```bash
cost-router models select \
  --router model-router --cheapest gpt-5.4-nano \
  --premium gpt-5.4 --ensemble gpt-5.4-nano,gpt-5.4-mini,gpt-5.4
```

저장한 뒤 **여러분이 고른 slate**를 실측으로 돌립니다:

```bash
cost-router foundry arena --fleet .foundry-fleet.local.yaml --live
```

## 3. 대시보드에서 선택

`cost-router serve`(또는 `cost-router hero --serve`)로 대시보드를 띄우면 **"Fleet & live
routing"** 패널이 같은 카탈로그를 보여줍니다 — router/cheapest/premium 드롭다운과 ensemble
체크박스. **Run selection**을 누르면 커밋된 **실측 스냅샷**을 재생하고, 여러분 선택을 라이브로
측정할 정확한 터미널 명령을 출력합니다.

!!! danger "정직함 경계 — 웹 경로는 절대 유료 호출을 하지 않습니다"
    대시보드의 `Run selection`은 새 Azure 호출을 하지 않습니다. 커밋된 measured 스냅샷을
    **정직하게 `measured = false` · `provenance = recorded`로 재라벨**해 재생합니다 (포착된
    측정치이지 새 측정이 아님). 따라서 웹에서 다른 slate를 골라도 오프라인 숫자는 바뀌지
    않습니다 — 이는 포착된 **레퍼런스 플릿**을 반영하기 때문이며, 응답의 `note`와
    `recorded_fleet`에 명시됩니다. **여러분의 선택을 실제로 측정**하려면 패널이 출력한 터미널
    명령(`... --live`)을 쓰세요.

## 4. 배포가 하나뿐이라면

헤드투헤드는 보통 여러 배포에 걸쳐 있지만, 배포가 하나뿐이어도 **라이브 경로 전체**(키리스
Microsoft Entra ID → 실제 호출 → 실제 토큰 usage → 가격 계산 → 해시체인 원장)를 끝까지
증명할 수 있습니다. 모든 아암을 그 하나로 향하게 하면 아암들이 동점이 되는데, 그게 바로
요점입니다 — 스프레드가 아니라 진짜 *measured* 스모크 테스트입니다.

```bash
cp samples/fleet/single-deployment.example.yaml my-fleet.local.yaml
# my-fleet.local.yaml 에서 deployment 를 여러분 리소스 이름으로 수정
cost-router foundry arena --fleet my-fleet.local.yaml --live --max-output-tokens 512
```

## 5. 라이브러리로 쓰기

```python
from router.fleet import FleetRegistry

reg = FleetRegistry.resolve()                       # --fleet/env/번들/기본 우선순위
reg = reg.with_roles(premium="gpt-5.4-mini")        # 역할 교체 (검증 포함, 불변)
slate = reg.slate()                                 # 라이브 아레나가 소비하는 FleetSlate
print(reg.validation_errors())                      # [] 이면 유효
```

`FleetRegistry`는 불변(immutable)이라 `with_roles(...)`가 검증된 새 레지스트리를 돌려줍니다 —
CLI·대시보드 선택 흐름이 공유 상태를 건드리지 않습니다.
