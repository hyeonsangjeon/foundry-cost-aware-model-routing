# 프롬프트-보유 워크로드

실측(`measured = true`)을 하려면 워크로드에 **프롬프트**와 **기계가 읽는 검증
규칙**이 둘 다 있어야 합니다. 이 폴더는 그런 워크로드의 **스키마를 확정하고
예시를 두는 자리**입니다. 실제로 유료 실행에 쓰인 워크로드는 아래 "실측
워크로드는 어디에 있나"에 적어 두었습니다.

스키마와 바꿔 끼우는 법은 [커스터마이징 가이드](../../docs/ko/manual/customize.md),
지금 무엇이 실측 가능한지는 [워크로드 인벤토리](../../docs/ko/manual/workload-inventory.md)를
보세요.

## 태스크 스키마 (한 줄 = 한 태스크, JSONL)

```json
{"task_id": "…", "class": "generate",
 "system_prompt": "…", "user_prompt": "…",
 "validation": {"type": "regex", "pattern": "def\\s+solve"},
 "tokens": {"input": 1232, "cached": 448, "output": 418, "reasoning": 168}}
```

- `validation`은 `router.validation`이 **로드 시** 검사합니다(`validate_rule`). 알 수 없는
  타입·잘못된 정규식·주관적 판정은 실행 **전에** 시끄럽게 실패합니다.
- `tokens`는 사전 추정(dry-run) 비용 계산에만 쓰이는 계획치입니다. 측정값이 아니고,
  실제 청구 토큰과 다릅니다.
- 무엇이 나갈지는 실행 전에 `cost-router measure catalog --workload <파일>`로 전부 볼 수
  있습니다 — 프롬프트 전문·검증 규칙·후보 모델·추정 토큰·예상 비용.

## 이 폴더의 파일

| 파일 | 규모 | `evidence_tier` | 무엇인가 |
| --- | --- | --- | --- |
| `curated.template.jsonl` | 3 (예시) | — | **스키마 템플릿** — 스키마를 보여주는 예시일 뿐, 실험용 최종본 아님 |
| `validated-smoke.example.jsonl` | 3 | — | **스모크 테스트용 예시** — 프롬프트와 `validation` 규칙이 모두 들어간 최소 워크로드. 실측 경로를 끝까지 한 번 통과시켜 볼 때 씁니다 |

두 파일 모두 **예시**입니다. 결과를 인용할 워크로드가 아닙니다.

## 실측 워크로드는 어디에 있나

| 이름 | 규모 | `evidence_tier` | 위치와 상태 |
| --- | --- | --- | --- |
| `curated-24` | 24 | **`directional`** | ✅ **`benchmarks/original-coding/tasks.jsonl`에 있고, 유료 실행에 쓰였습니다.** 실험 11(VOID)·12·13이 이 파일을 지목했습니다 |
| `hero-100-prompts` | 100 | 더 강한 등급의 첫 후보 | 📋 **제안 단계 — 파일 없음.** 저장소 어디에도 아직 만들어지지 않았습니다 |

`curated-24`는 채점기(grader)와 정답·오답 고정 입력(fixtures)까지 함께 있는 완성된
워크로드이고, 세 번의 유료 실행이 모두 같은 지문(`workload_fingerprint
sha256:391d2f705e8b52c3826d20d80ef2c37b3c1e8a6eb69e8bd41bb2685ce46c0656`)으로 봉인돼
있습니다. 구성과 채점 방식은
[벤치마크 스위트 README](../../benchmarks/original-coding/README.md)를 보세요.

> **표본 크기 임계값의 출처.** Microsoft의 Model Router 평가 가이드는 **100개 이상**의 워크로드
> 프롬프트라야 통계적으로 신뢰할 만한 결과를 얻을 수 있고, **30개 미만**은 방향성(directional)
> 신호만 준다고 안내합니다 — 그래서 24개짜리 `curated-24`는 `evidence_tier = directional`입니다.
> 출처: <https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router#evaluate-model-router-for-your-workload>
> (확인일 **2026-07-29**)

!!! note "정직성·승인 경계"
    실측 워크로드의 태스크와 프롬프트는 **콘텐츠 설계**입니다. `curated.template.jsonl`은
    스키마를 확정하기 위한 **템플릿**이고, `hero-100-prompts`처럼 아직 없는 워크로드는
    **초안을 올려 운영자 승인을 받은 뒤에** 확정합니다.

    수치의 등급은 워크로드가 아니라 **그 수치가 어디서 나왔는지**로 갈립니다. 합성
    텔레메트리를 돌린 오프라인 실험(01–08)은 `measured = false` 프로젝션이고, 승인을 거쳐
    실제로 모델을 부른 실행(09·10·12·13)은 `measured = true`입니다. 실험 11도 실측이지만
    **무효(VOID)**입니다. 각각 단독으로도 무효 사유가 되는 두 가지가 겹쳤습니다 —
    `router-quality`의 **채점 커버리지가 79.2%(57/72)로 90% 문턱에 미달**했고, 전체
    셀의 **43.4%(125/288)가 요율 없음으로 비용이 보류(fail-closed)돼 런이
    cost-incomplete**가 됐습니다. 새 라이브 호출만 `measured = true`가 됩니다.

    **결과를 보고 태스크를 고치지 않습니다** (exp04 교훈) — 고쳐야 하면 경위를
    lab-notebook에 남깁니다.
