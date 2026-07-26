# 커스터마이징 가이드 — 본인 워크로드로 갈아끼우기 (D13)

이 저장소는 **본인 Foundry에서 그대로 돌려보라**는 전제로 만들어졌습니다. 그러려면 다섯
군데만 바꾸면 됩니다. 각 지점은 별도 파일이라, 코드를 건드리지 않고 설정만 교체하면
됩니다. `measured = false` 프로젝션은 오프라인으로 즉시, `measured = true` 실측은 `.env`
설정 + `az login` 후 [로컬 콕핏](../lab-notebook/09-live-routing-proof.md)의 승인 버튼으로.

## 바꾸는 곳 다섯

### 1. 프롬프트 (`system_prompt` / `user_prompt`)
- **어디:** 워크로드 JSONL — `samples/telemetry/<name>.jsonl`. 태스크 행에 프롬프트 필드를 붙입니다.
- **스키마(태스크 1건):**
  ```json
  {"task_id": "t-0001", "class": "generate",
   "system_prompt": "You are a terse senior engineer.",
   "user_prompt": "Write a Python function `solve(n)` returning the n-th prime.",
   "validation": {"type": "regex", "pattern": "def\\s+solve"}}
  ```
- **고르기:** 실험 YAML의 `dataset.workload`가 어떤 파일을 쓸지 지목합니다(`experiments/*.yaml`).
- 프롬프트가 없으면(텔레메트리 행만) 실제 모델을 부를 수 없어 **오프라인 투영만** 됩니다.

### 2. 검증 규칙 (`validation`)
- **어디:** 같은 태스크 행의 `validation` 블록. `router.validation`이 기계적으로 판정합니다.
- **규칙 타입:** `contains` · `not_contains` · `equals` · `regex` · `nonempty` · `json_valid`,
  그리고 이들을 묶는 `all` / `any`. **주관적 판정("좋아 보이면 통과") 금지** — 모두 출력
  문자열에 대한 순수 함수입니다.
  ```json
  {"type": "all", "rules": [
    {"type": "contains", "value": "def solve"},
    {"type": "not_contains", "value": "TODO"}
  ]}
  ```
- 규칙이 틀리면(알 수 없는 타입·정규식 오류) `validate_rule`이 **실행 전에 시끄럽게 실패**합니다.

### 3. 플릿 (후보 모델)
- **어디:** `samples/fleet/*.fleet.yaml` (예: `foundry-ext-full.fleet.yaml`, `foundry-5series.fleet.yaml`).
- **고르기:** `.env`의 `FOUNDRY_FLEET_PATH`(또는 `COST_ROUTER_FLEET`).
- arm별(cheapest/premium/router/ensemble) 어떤 배포를 부를지, provider가 무엇인지 정의합니다.

### 4. 단가 (pricing)
- **어디:** `samples/pricing/*.yaml` (예: `foundry-ext-full.yaml`; 본인 테넌트용은
  `your-tenant.example.yaml`을 복사해서 실단가로).
- **고르기:** `.env`의 `FOUNDRY_PRICING_PATH`(또는 `COST_ROUTER_PRICING`).
- dry-run 추정과 실측 비용 환산이 **같은 단가표**를 쓰도록 `measure`가 이 경로를 존중합니다.

### 5. 반복수 · 예산 (`n` · budget)
- **어디:** CLI 플래그 — `cost-router measure run --n <반복> --budget-usd <상한>`.
- `--n`은 셀당 반복(분산 확인용), `--budget-usd`는 **하드 상한**입니다. 라이브 실행은
  `--budget-usd` 없이는 거부되고, 상한 도달 시 즉시 멈추고 `partial = true` 스냅샷을 남깁니다.

## 5단계 레시피 — 내 워크로드 갈아끼우기

1. **워크로드 작성.** `samples/telemetry/my-workload.jsonl`에 태스크를 한 줄에 하나씩 —
   `task_id` · `class` · `system_prompt` · `user_prompt` · `validation`.
2. **검증 규칙 확인.** 각 `validation`이 기계 판정 가능한지(`router.validation.validate_rule`로
   로드 시 검사됨). 주관적 기준은 금지.
3. **실험에 연결.** 실험 YAML의 `dataset.workload`를 새 파일로 지목(또는 새 실험 YAML 작성).
4. **플릿·단가 지정.** `.env`에서 `FOUNDRY_FLEET_PATH`·`FOUNDRY_PRICING_PATH`를 본인 배포·단가로.
5. **먼저 dry-run, 그다음 승인 실행.** `cost-router measure run --dry-run`으로 예산·프롬프트를
   먼저 눈으로 확인 → 문제 없으면 `--live --budget-usd <상한>`으로 승인 실행. 프롬프트가
   바뀌면 manifest의 `workload_fingerprint`가 달라져 **다른 실험으로 정직하게 기록**됩니다.

!!! tip "실행 전에 다 보인다"
    무엇이 나가는지는 실행 **전에** 확인할 수 있습니다 — 태스크 목록, 각 프롬프트 전문,
    검증 규칙, 후보 모델, 추정 토큰까지. "지금 이게 나갑니다"가 한눈에 보인 다음에야
    (유료) 라이브 호출이 시작됩니다.
