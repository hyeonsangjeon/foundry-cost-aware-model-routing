# 프롬프트-보유 워크로드 (BOLT-02 Phase B)

이 폴더는 **실측(`measured = true`) 가능한 워크로드** — 즉 프롬프트와 기계 검증
규칙을 갖춘 태스크 집합 — 이 들어가는 곳입니다. 스키마·바꿔 끼우는 법은
[커스터마이징 가이드](../../docs/manual/customize.md)를, 현재 무엇이 실측 가능한지는
[워크로드 인벤토리](../../docs/manual/workload-inventory.md)를 보세요.

## 태스크 스키마 (한 줄 = 한 태스크, JSONL)

```json
{"task_id": "…", "class": "generate",
 "system_prompt": "…", "user_prompt": "…",
 "validation": {"type": "regex", "pattern": "def\\s+solve"},
 "tokens": {"input": 1232, "cached": 448, "output": 418, "reasoning": 168}}
```

- `validation`은 `router.validation`이 **로드 시** 검사합니다(`validate_rule`). 알 수 없는
  타입·잘못된 정규식·주관적 판정은 실행 **전에** 시끄럽게 실패합니다.
- `tokens`는 dry-run 비용 추정에만 쓰이는 계획치입니다(측정값 아님).
- 무엇이 나갈지는 실행 전에 `cost-router measure catalog --workload <파일>`로 전부 볼 수
  있습니다 — 프롬프트 전문·검증 규칙·후보 모델·추정 토큰·예상 비용.

## 파일

| 파일 | 규모 | 상태 |
| --- | --- | --- |
| `curated.template.jsonl` | 3 (예시) | **스키마 템플릿** — 스키마를 보여주는 예시일 뿐, 실험용 최종본 아님 |
| `curated-24.jsonl` | 24 | 🚧 **미작성 — 운영자 승인 대기** (exp03·04·06·07 실측용) |
| `hero-100-prompts.jsonl` | 100 | 🚧 **미작성 — 운영자 승인 대기** (exp01 실측용) |

!!! note "정직성·승인 경계 (§9)"
    실측 워크로드의 태스크·프롬프트는 **콘텐츠 설계**입니다. `curated.template.jsonl`은
    스키마를 확정하기 위한 **템플릿**이며, `curated-24`/`hero-100-prompts` 본편은
    **초안을 올려 운영자 승인 후 확정**합니다. 승인·라이브 실행 전까지 이 저장소의 모든
    수치는 `measured = false` 프로젝션입니다. **결과를 보고 태스크를 고치지 않습니다**
    (exp04 교훈) — 고쳐야 하면 경위를 lab-notebook에 남깁니다.
