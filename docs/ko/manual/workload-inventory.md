# 워크로드 인벤토리 — 무엇이 실측 가능한가 (B1)

이 표는 저장소가 현재 들고 있는 **워크로드(태스크 집합)**, 각 워크로드의 **프롬프트·검증
보유 여부**, 그리고 그 워크로드로 어떤 실험이 도는지를 정리합니다. 목적은 딱 하나 —
**어떤 실험이 지금 당장 실측(`measured = true`) 가능하고, 어떤 실험은 아직 프로젝션
(`measured = false`)뿐인지**를 정직하게 못 박는 것입니다.

## 현재 워크로드

| 워크로드 | 태스크 | 프롬프트? | 기계 검증(`validation`)? | 사용 실험 | 실측 가능? |
| --- | --- | --- | --- | --- | --- |
| `samples/telemetry/mixed-coding-workload.sample.jsonl` | 100 | ❌ 없음 | ❌ 없음 | 01 히어로 · 02 큐레이션 · 05 앙상블 · 06 팬아웃 다이얼 · 07 단일호출 · limits · adaptive | ❌ **프로젝션 전용** |
| `samples/telemetry/curated-arena-live.sample.jsonl` | 5 | ▲ 별도 픽스처 | ❌ (사람용 `acceptance` 문자열) | 08 아레나 · `foundry live` 캡처 | ▲ 라이브 캡처는 가능하나 **커버리지 미채점** |
| `samples/prompts/curated-arena.sample.json` | 5 | ✅ `{title, prompt, acceptance}` | ❌ | 위 아레나/라이브의 프롬프트 원천 | — (프롬프트 픽스처) |

### 읽는 법

- **프롬프트 없음** = 태스크 행이 텔레메트리(`{task_id, class, difficulty, domain, tokens}`)일
  뿐, 모델에 보낼 `system_prompt`/`user_prompt`가 없음. 그래서 이 워크로드로는 **실제
  모델을 부를 수가 없고**, 오프라인 신호로 라우팅을 *투영*만 합니다(`measured = false`).
- **사람용 `acceptance`** = 큐레이션 아레나 픽스처는 사람이 읽는 합격 기준 문장을 갖지만,
  기계가 통과/실패를 자동 판정하는 규칙은 아닙니다. 실측 커버리지를 채점하려면
  **기계가 읽는 `validation` 규칙**([검증 규칙](customize.md) ·
  `router.validation`)이 필요합니다.

## 그래서 지금 실측 가능한 실험은?

**현재는 없습니다 — 전부 정직하게 프로젝션입니다.** 여덟 실험 모두 프롬프트 없는 100태스크
텔레메트리로 돌기 때문입니다. 실측(`measured = true`)으로 올리려면 프롬프트+검증을 갖춘
워크로드가 있어야 하고, 그게 BOLT-02 Phase B의 남은 작업입니다:

| 필요 워크로드 | 규모 | `evidence_tier` | 겨냥 실험 | 상태 |
| --- | --- | --- | --- | --- |
| `curated-24` | 중간(24) | **`directional`** | 03 · 04 · 06 · 07 | 🚧 **초안·승인 대기**(§9 콘텐츠 게이트) |
| `hero-100-prompts` | 100 | 더 강한 등급의 첫 후보 | 01 | 🚧 **초안·승인 대기** |

!!! quote "표본 크기 임계값의 출처"
    Microsoft의 Model Router 평가 가이드는 **100개 이상**의 워크로드 프롬프트라야 통계적으로
    신뢰할 만한 결과를 얻을 수 있고, **30개 미만**은 방향성(directional) 신호만 준다고 안내합니다.
    그래서 24개짜리 `curated-24`는 `evidence_tier = directional`입니다.
    출처: <https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router#evaluate-model-router-for-your-workload>
    (확인일 **2026-07-29**) · 자세한 규칙은 [측정 프로토콜 §3.4](measurement-protocol.md)

두 워크로드는 **프롬프트가 곧 실험**이므로(같은 파이프라인, 다른 프롬프트 = 다른 실험),
manifest에 **워크로드 지문**(`workload_fingerprint`, SHA-256)이 봉인되어 프롬프트가 바뀌면
격차 뷰가 서로 다른 실험으로 취급합니다. 스키마·검증 규칙·바꿔 끼우는 지점은
[커스터마이징 가이드](customize.md)를, 스키마 예시는
`samples/workloads/curated.template.jsonl`을 보세요. 어떤 워크로드든 실행 **전에**
`cost-router measure catalog --workload <파일>`로 나갈 프롬프트·검증 규칙·후보·추정 비용을
유료 호출 0으로 미리 볼 수 있습니다.

!!! note "정직성 경계"
    이 표는 **구현된 현재 상태**입니다. 실측 워크로드(`curated-24`·`hero-100-prompts`)의
    태스크·프롬프트는 콘텐츠 설계라 **초안을 올리고 운영자 승인 후 확정**합니다(결과를 보고
    태스크를 고치지 않습니다 — exp04의 교훈). 승인·라이브 실행 전까지 이 저장소의 모든
    수치는 `measured = false` 프로젝션입니다.
