# 실험 09 · 실측 라우팅 — Foundry Model Router가 **실제로** 고른 모델들 (`measured = true`)

!!! abstract "한 줄 요약"
    실험 01–08은 모두 **합성 텔레메트리에 대한 오프라인 투영**(`measured = false`, 자리표시자
    모델)이었습니다. 이 실험은 그 경계를 넘습니다 — 실제 **Azure AI Foundry Model Router**
    배포에 큐레이션 5개 프롬프트를 **정말로 보내고**, 라우터가 고른 **실제 모델**과 **실제로
    청구된 토큰 usage**를 읽었습니다(**키 없이 Microsoft Entra ID** 인증). 결과: 단 하나의
    `model-router` 배포가 태스크에 따라 **`gpt-5.4`(3건)와 `grok-4-1-fast-reasoning`(2건)**으로
    실제 분기했습니다. 이 저장소 최초의 `measured = true` 실험이며, **지연도 여기서는 진짜
    wall-clock**입니다(실험 08의 예시적 투영과 대비).

## 이 실험은 무엇인가 — 투영에서 측정으로

- **상황(왜):** 저장소의 여덟 실험은 전부 정직하게 `measured = false`였습니다 — 네트워크도
  자격 증명도 없이, `mini-fast`·`premium-max` 같은 **자리표시자** 모델에 대한 결정론적 투영.
  강력하지만 늘 따라붙는 질문이 있었습니다: *"그래서 진짜 Foundry에 물리면 라우터가 **실제로**
  어떤 모델을 고르나?"*
- **작업(무엇을):** 이 작업 전용으로 **키리스(Entra 전용) AIServices 리소스**를 새로
  프로비저닝하고, 실제 **`model-router`** 배포 하나와 **GPT‑5.4 계열 후보**(`gpt-5.4-nano` ·
  `gpt-5.4-mini` · `gpt-5.4`)를 올린 뒤, [라이브 브릿지](../manual/foundry-live.md)로 큐레이션
  5개 프롬프트를 **실제로 호출**했습니다.
- **실험(무엇을 검증):** (1) 단일 `model-router` 배포가 태스크별로 **서로 다른 실제 모델**로
  분기하는가, (2) 응답이 그 선택을 **증명**하는가, (3) 이 전부가 **키 없이 Entra 토큰만으로**
  일어나는가 — 셋 다 **예**.

!!! danger "이건 계약 실험도, 결정론적 재현도 아니다 — 라이브 측정 스냅샷이다"
    실험 01–08은 `expect` 하한/상한을 둔 **오프라인·결정론** 실험이라 CI가 매번 같은 수치를
    재현합니다. 이 실험은 성격이 다릅니다 — **라이브 호출**이라 토큰·비용·지연은 호출마다
    변동하고(그게 `measured = true`의 본질), 여기 표는 **한 번의 실측 스냅샷**입니다. 저장소의
    기본 경로·CI·테스트는 이 실험을 돌리지 않으며(자격 증명·네트워크가 없으면 no-op), 여전히
    순수 표준 라이브러리·결정론으로 남습니다.

## 어떻게 한 건가 — 단일 배포, 라우터가 내부에서 분기

핵심은 **호출하는 배포는 하나(`model-router`)뿐**이라는 점입니다. 우리가 특정 모델을 고르지
않습니다 — Model Router가 프롬프트를 보고 **내부에서** 적합한 백엔드 모델로 라우팅하고, 그
선택을 **응답의 `model` 필드**로 되돌려줍니다.

```text
                         ┌─────────────────────────────────────────┐
  프롬프트 5건  ──────▶  │  단일 배포:  model-router (2025-11-18)     │
  (model=model-router)   │  ─ 라우터가 태스크를 보고 백엔드를 선택 ─  │
                         └───────────────┬──────────────┬──────────┘
                                         │              │
                    response.model =     ▼              ▼
                            gpt-5.4-2026-03-05     grok-4-1-fast-reasoning
                            (t-0003·0004·0005)      (t-0001·0006)
```

- **요청:** `chat.completions.create(model="model-router", …)` — 언제나 라우터 배포 이름.
- **증명:** 응답의 `response.model`이 **라우터가 실제로 태운 백엔드 모델**을 담습니다. 이 값이
  ground truth입니다([`_response_model`](../manual/foundry-live.md)).
- **비용:** 응답의 **실제 `usage`** 토큰으로 계산(`_usage_from_response`) — 합성 토큰이 아님.
- **인증:** 리소스가 `disableLocalAuth=true`(키 인증 꺼짐)라 **API 키 없이** `az login` 신원의
  Entra 토큰(`https://cognitiveservices.azure.com/.default`)으로만 호출.

## 결과 — 라우터가 실제로 고른 모델 (measured 스냅샷)

| 태스크 | 클래스 | 요청 배포 | **라우터가 실제로 서빙한 모델** | in | out | reasoning | 비용† | 지연‡ |
| --- | --- | --- | --- | ---: | ---: | ---: | ---: | ---: |
| t-0001 | generate | `model-router` | **`grok-4-1-fast-reasoning`** | 54 | 0 | 1078 | `$0.004326` | 11.11 s |
| t-0003 | repo_patch | `model-router` | `gpt-5.4-2026-03-05` | 72 | 541 | 10 | `$0.002276` | 6.72 s |
| t-0004 | plan | `model-router` | `gpt-5.4-2026-03-05` | 50 | 1032 | 158 | `$0.004810` | 12.19 s |
| t-0005 | validate | `model-router` | `gpt-5.4-2026-03-05` | 53 | 543 | 76 | `$0.002529` | 7.10 s |
| t-0006 | test | `model-router` | **`grok-4-1-fast-reasoning`** | 59 | 0 | 1293 | `$0.005187` | 10.84 s |

**라우터가 사용한 모델 집계:** `gpt-5.4-2026-03-05` × 3 · `grok-4-1-fast-reasoning` × 2.
`selection = azure-model-router` · `provenance = live` · `measured = true` · `spend_source =
provider-usage`. 라우팅 분포는 두 번의 독립 실행에서 **동일**했고(태스크→모델 매핑 안정),
토큰·비용·지연만 호출마다 변동했습니다 — 라이브 측정의 본질.

## 진짜라는 증거 — 응답 ID 형식이 모델마다 다르다

두 백엔드는 **서로 다른 형식의 응답 ID**를 돌려줍니다 — 목업으로는 만들 수 없는, 서로 다른
실제 백엔드가 서빙했다는 강력한 지문입니다:

| 서빙 모델 | 응답 ID 형식 | 예 |
| --- | --- | --- |
| `gpt-5.4-2026-03-05` | OpenAI 표준 `chatcmpl-…` | `chatcmpl-E3cromf…` |
| `grok-4-1-fast-reasoning` | 순수 UUID | `cca8d752-05f4-40…` |

그리고 실제 답변 텍스트도 나왔습니다(`finish_reason = stop`, 잘림 없음):

- **t-0001 · grok** — `import re`로 `slugify()`를 실제 구현한 파이썬 코드 블록.
- **t-0006 · grok** — `unittest`로 `merge_intervals` 테스트를 실제 작성.
- **t-0003·0004·0005 · gpt-5.4** — repo 패치 계획 · 커서 페이지네이션 설계 · retry diff 리뷰를 실제 작성.

## 정직함 경계 — 무엇이 측정이고 무엇이 아닌가

!!! warning "측정된 것 · 측정되지 않은 것"
    - **측정됨(진짜):** ① 라우터가 고른 **모델**(응답 `model`), ② **토큰 usage**(응답 `usage`),
      ③ **지연**(wall-clock — 실험 08의 투영과 달리 여기선 실측), ④ **키리스 Entra 인증**.
    - **측정 안 됨:** **정확도(pass/fail).** `grader`를 주입하지 않았으므로 각 답이 *맞았는지*는
      채점하지 않았습니다 → `coverage_measured = false`. 실제 apply/compile/test 하네스를
      물려야 정확도까지 실측됩니다.
    - **비용의 요율은 예시값.** 토큰은 실측이지만, 요율은 번들 `illustrative.yaml`의 **`default`
      요율**(gpt-5.4·grok 모두 여기에 해당)로 곱했습니다 — 여러분 테넌트의 **실제 청구액이
      아닙니다**. 실제 요율 YAML(`FOUNDRY_PRICING_PATH`)을 주면 그 값으로 계산됩니다.
    - **라이브 스냅샷.** 이 리소스는 이 작업용으로 만든 것이고, 표의 수치는 한 번의 실측
      스냅샷입니다. 재실행하면 라우팅 결정은 같아도 토큰·비용·지연은 달라질 수 있습니다.

## 실험 01–08 ↔ 실험 09

| | 실험 01–08 | 실험 09 (이 실험) |
| --- | --- | --- |
| 데이터 | 합성 텔레메트리 | 실제 프롬프트 → 실제 응답 |
| 모델 | 자리표시자(`mini-fast`…) | **실제**(`gpt-5.4` · `grok-4-1-fast-reasoning`) |
| 라벨 | `measured = false` | **`measured = true`** |
| 지연 | 예시적 투영(08) | **실측 wall-clock** |
| 정확도 | 오프라인 신호(`is_clean`) | 미채점(`coverage_measured = false`) |
| 재현 | 결정론(CI가 고정) | 라이브 스냅샷(호출마다 변동) |

실험 08이 "문제 하나를 네 방법으로 본" **오프라인 렌즈**였다면, 실험 09는 그 라우터 열을
**실제 Foundry에 물려** 라우터가 진짜로 무엇을 고르는지 확인한 **실측**입니다.

## 재현 방법

전제: 키리스 Entra 리소스에 `model-router` 배포 + GPT‑5.4 계열 후보, `.env`에
`AZURE_AI_FOUNDRY_ENDPOINT` · `AZURE_AI_FOUNDRY_MODEL_ROUTER=model-router` ·
`AZURE_AI_FOUNDRY_AUTH=entra`. 그다음 `az login`(디바이스 코드) 한 번.

```bash
# 1. 연결 확인 — credentialed: yes / auth: Microsoft Entra ID (keyless) 를 확인
cost-router foundry status

# 2. 실측 실행 — 큐레이션 프롬프트를 실제 라우터로 호출 (measured = true)
cost-router foundry live --live \
  --workload samples/telemetry/curated-arena-live.sample.jsonl \
  --pricing  samples/pricing/illustrative.yaml \
  --store    runs.jsonl --json
```

요약의 `labels.measured = true` · `model_counts`(라우터가 실제 고른 모델별 건수) ·
`total_cost_usd`(실측 토큰 기반)를 확인하세요. 임의 프롬프트도 같은 방식입니다 —
`--workload my-prompts.jsonl`. 채점까지 실측하려면 `grader`를 주입하세요
([foundry-live 매뉴얼](../manual/foundry-live.md)).

---

**관련 문서:** [라이브 실측 브릿지](../manual/foundry-live.md) · [실험 08 · 아레나](08-arena.md)
(오프라인 렌즈) · [개발 로그](devlog.md)
