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
5. **먼저 카탈로그로 확인, 그다음 승인 실행.** `cost-router measure catalog --workload
   samples/telemetry/my-workload.jsonl`로 **나갈 프롬프트 전문·검증 규칙·후보 모델·추정
   토큰·예상 비용**을 먼저 눈으로 확인 → 문제 없으면 `cost-router measure run --live
   --budget-usd <상한>`으로 승인 실행. 프롬프트가 바뀌면 manifest의 `workload_fingerprint`가
   달라져 **다른 실험으로 정직하게 기록**됩니다.

!!! tip "실행 전에 다 보인다"
    무엇이 나가는지는 실행 **전에** 확인할 수 있습니다 — `cost-router measure catalog`가
    태스크 목록, 각 프롬프트 전문, 검증 규칙, 후보 모델, 추정 토큰, dry-run 비용까지
    한 화면에 보여줍니다(유료 호출 0). "지금 이게 나갑니다"가 눈에 보인 다음에야
    (유료) 라이브 호출이 시작됩니다.

## 브라우저 콕핏 — `cost-router dashboard --live`

CLI 대신 **브라우저에서 같은 게이트**를 밟고 싶으면 로컬 콕핏을 씁니다. 5단계 레시피와
정확히 같은 순서(연결 확인 → 프롬프트·dry-run → 승인 → 실행 → 스냅샷)를 대시보드에서 그대로.

```bash
az login                      # Entra 자격증명은 환경에서 읽습니다 (브라우저에 입력란 없음)
cost-router dashboard --live  # 127.0.0.1 전용 + 임의 포트 + 세션 토큰 URL을 콘솔에 출력
```

- **바인딩.** `127.0.0.1`에만 붙고 임의 포트를 씁니다. 콘솔에 찍힌
  `http://127.0.0.1:<PORT>/?cockpit=1&token=…` URL로 들어가야 콕핏이 열립니다. 토큰이
  없거나 틀리면 `/cockpit/*` 라우트는 403이고, 공개(정적) 빌드에는 `cockpit=1`이 없어
  콕핏 자체가 렌더되지 않습니다.
- **연결 패널.** `foundry status`의 **마스킹된** 출력을 그대로 재사용 — 엔드포인트(호스트만),
  Entra 로그인 여부, 배포, 단가 파일. **자격증명 입력란은 없습니다**(환경/`az login`에서 읽음).
  누락 항목은 "무엇을 어떻게 설정하면 되는지" 인라인 안내.
- **프롬프트 · dry-run.** 나갈 프롬프트 전문·검증 규칙·후보 모델·예상 비용을 실행 전에 표시
  (유료 호출 0). CLI `measure catalog`와 같은 카탈로그입니다.
- **승인하고 실행.** 예산 상한을 넣고 `승인하고 실행`을 눌러야 (유료) 스윕이 시작됩니다 —
  이 버튼이 BOLT-01 §8의 **사람 승인 게이트**입니다. 자격증명·예산·승인·prereg 중 하나라도
  비면 정직하게 거부하고 이유를 표시합니다.
- **실시간 진행 · 스냅샷.** 진척·누적 지출 대 예산 게이지가 스트리밍되고, 예산 도달 시 즉시
  중단(`partial=true`). 완료되면 `results/measured/<exp>/<run-id>/`를 **다시 읽어 렌더**합니다
  (재생 경로가 곧 검증).

측정이 끝나면 공개 목업이 소비할 형태로 정리합니다(테넌트 단가 마스킹, 커밋은 사람이):

```bash
cost-router measure publish --run results/measured/<exp>/<run-id>
```
