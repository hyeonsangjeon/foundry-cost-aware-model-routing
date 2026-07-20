# 실험 설정 (YAML)

**명명된 실험**은 워크로드, 오프라인 신호(픽스처 또는 합성), 가격표, 정책을 고정하고,
여기에 `expect` **재현성 계약**을 더한 작은 YAML 파일입니다. 하나를 실행하면 나이브 대 라우팅
before/after를 다시 유도하고, 오프라인 투영이 계약된 하한 아래로 떨어지면 **크게 실패**합니다.

이것이 저장소의 "설치하면 그냥 돌아간다"를 **점검 가능한 약속**으로 만드는 장치입니다.

파일은 `experiments/` 디렉터리에 둡니다.

!!! tip "비주얼로 먼저 보고 싶다면 — Experiment Atlas"
    각 실험이 **어떤 모델**로 **무엇을**, **어떤 방식**(순차 에스컬레이션 · 팬아웃 · 단일 콜)으로
    처리하는지 애니메이션 SVG로 한눈에 보려면 **[실험 아틀라스 · Experiment Atlas](experiment-atlas.md)**
    를 보세요. Azure Model Router 실제 구성(키리스 Entra) 따라하기까지 포함되어 있습니다.

## 최소 예시

```yaml title="experiments/hero.yaml"
name: hero
title: "같은 커버리지, 더 낮은 비용 — 30초 히어로 실행"
summary: >-
  합성 워크로드 100건을 '통과하는 가장 싼 모델 먼저, 실패할 때만 상위 모델로'
  라우팅해 모든 태스크에 프리미엄 모델을 쓰는 나이브 방식과 비교합니다.

dataset:
  workload: samples/telemetry/mixed-coding-workload.sample.jsonl
  signals: null        # null + synth:true → 결정론적 오프라인 신호 합성
  synth: true

policy: null           # null → 번들 시드 정책
pricing: null          # null → 번들 예시 가격 (measured=false)

spotlight: auto        # auto | <task_id> | none

expect:
  min_coverage: 1.0    # 라우팅은 커버리지를 유지해야 하고
  min_delta_pct: 0.20  # …나이브 청구서를 최소 20% 낮춰야 한다
  min_tasks: 100
```

!!! tip "팬아웃 다이얼 — `budget:` (선택)"
    실험은 라우터의 팬아웃 임계값을 조절할 수 있습니다. `compare_min_value`를 올리면
    가치가 그보다 낮은 태스크는 **단일 경로(ordered)**로 가고, 그만큼 앙상블 세금이
    줄어듭니다 — [실험 06](../lab-notebook/06-fanout-dial.md)이 이 다이얼을 씁니다.

    ```yaml
    budget:
      compare_min_value: 1.1      # 모든 태스크 가치(최대 1.0)보다 높게 → 팬아웃 전무
      min_compare_candidates: 2   # compare로 가려면 후보가 최소 2개
    ```

!!! tip "측정 브리지 — Azure AI Foundry Model Router (선택)"
    프런티어의 `model_router` arm은 단일 호출 라우팅 레이어의 **모양**을 보여주는 오프라인
    프록시입니다. 실제 Foundry Model Router의 **결정**을 끼워 넣으려면, 의존성 없는 게이트
    어댑터 `router.foundry_router.FoundryModelRouter`에 아래 환경 변수와 주입된 `client`
    콜러블을 줍니다(설정이 없으면 어댑터는 비활성, 오프라인 프록시가 대신). 라이브 결정을
    넣어도 비용·커버리지는 여전히 오프라인 투영(`measured = false`)이며 모델 **선택**만
    라이브입니다 — [실험 07](../lab-notebook/07-model-router.md) 참고.

    | 환경 변수 | 의미 |
    | --- | --- |
    | `AZURE_AI_FOUNDRY_ENDPOINT` | Foundry 엔드포인트 (또는 `AZURE_OPENAI_ENDPOINT`) |
    | `AZURE_AI_FOUNDRY_MODEL_ROUTER` | Model Router 배포 이름 (또는 `AZURE_MODEL_ROUTER_DEPLOYMENT`) |
    | `AZURE_AI_FOUNDRY_API_KEY` | API 키 (또는 `AZURE_OPENAI_API_KEY`) |

## 필드 레퍼런스

| 필드 | 의미 |
| --- | --- |
| `name` | 실험 이름(파일명 stem이 기본값) |
| `title` / `summary` | 사람이 읽는 제목/설명 |
| `dataset.workload` | 워크로드 JSONL 경로 (비우면 번들 샘플) |
| `dataset.signals` | 오프라인 신호 JSON 경로, 또는 `null`로 합성 |
| `dataset.synth` | `true`면 신호를 결정론적으로 합성 |
| `policy` | 정책 YAML 경로 (비우면 번들 시드) |
| `pricing` | 가격표 YAML 경로 (비우면 번들 예시 가격) |
| `budget.compare_min_value` | (선택) 팬아웃 임계값 — 태스크 가치가 이 값 이상일 때만 compare(팬아웃). 올릴수록 세금 ↓ (`adaptive.yaml` 참고) |
| `budget.min_compare_candidates` | (선택) compare로 가기 위한 최소 후보 수 |
| `spotlight` | `auto`, 특정 `task_id`, 또는 `none` |
| `expect.min_coverage` | 이 커버리지 이상을 유지해야 함 |
| `expect.min_delta_pct` | 나이브 청구서를 이 비율 이상 낮춰야 함 |
| `expect.max_delta_pct` | (선택) **상한** — 절감이 이 비율을 넘으면 안 됨(유령 절감 방지; `limits.yaml` 참고) |
| `expect.max_tax_ratio` | (선택) **팬아웃 세금 상한** — 팬아웃 원가/승자 비율이 이 값을 넘으면 안 됨(`adaptive.yaml` 참고) |
| `expect.min_escalation_gain` | (선택) **에스컬레이션 이득 하한** — mix 커버리지 − 단일 호출 `model_router` 커버리지가 이 값 이상이어야 함(`model-router.yaml` 참고) |
| `expect.min_tasks` | 최소 이만큼의 태스크를 다뤄야 함 |

경로는 저장소 루트 기준 상대 경로 또는 절대 경로로 씁니다.

## spotlight — 대표 태스크 강조

`spotlight`는 비용 인지 라우팅이 나이브 프리미엄 arm을 눈에 띄게 이기는 한 태스크를 고릅니다.

- `auto` — 수용된(accepted) 태스크 중 **나이브/라우팅 비용 비율**이 가장 큰 태스크
- `<task_id>` — 특정 태스크를 명시적으로 고정
- `none` — 스포트라이트 비활성화

## 재현성 계약이 하는 일

`run_experiment`는 재생 후 다음을 점검합니다.

- `coverage ≥ min_coverage`
- `delta_pct ≥ min_delta_pct`
- `delta_pct ≤ max_delta_pct` (설정된 경우에만 — 과장된 유령 절감을 막는 상한)
- `tax_ratio ≤ max_tax_ratio` (설정된 경우에만 — 팬아웃 세금 상한)
- `escalation_gain ≥ min_escalation_gain` (설정된 경우에만 — mix가 단일 호출 `model_router`보다 커버리지를 이만큼 더 벌어야 함)
- `tasks ≥ min_tasks`

하나라도 실패하면 `cost-router hero`/`experiment run`이 **0이 아닌 코드**로 종료합니다.
따라서 "돌아가긴 하는데 절감이 사라진" 회귀를 조용히 넘어가지 않습니다.

!!! tip "나만의 실험 만들기"
    ```bash
    cp experiments/hero.yaml experiments/my-workload.yaml
    # 워크로드/정책/가격을 여러분 것으로 바꾸고
    cost-router experiment run my-workload
    ```
    측정된 숫자를 원한다면 `samples/pricing/illustrative.yaml`을 복사해
    `your-tenant.yaml`(gitignored)에 실제 요율을 넣고 `pricing:`으로 가리키세요.
