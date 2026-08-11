# 정본 실행 계획 · Resolved Run Plan

미리보기(preview) · 사람 승인(approval) · 실행(run) · 원장(ledger) · 재생(replay)이
**서로 다른 설정을 각자 해석하면**, 승인한 것과 실행한 것이 어긋날 수
있습니다. 03A는 그 틈을 없앱니다. 하나의 로컬 설정 파일을 **한 번** 해석해
`ResolvedRunPlan` 이라는 **불변 객체**로 봉인하고 위 다섯 경로가 전부 그 동일한 객체를
읽습니다. 계획에는 결정론적 `plan_hash`가 붙고 승인은 그 해시에 묶입니다. 콕핏(cockpit)도
이제 이 계획에 연결됩니다 — `cost-router dashboard --live --config <파일>`은 정본
`ResolvedRunPlan`을 콕핏의 유일한 진실 원천으로 바인딩해 preview·승인·실행·abort·replay가
전부 같은 `plan_hash`를 키로 씁니다(03C, §9). 콕핏은 03B의 공유 abort 게이트와 지출 원장을
재사용하며 별도 취소·예산 경로를 만들지 않습니다.

이 페이지는 `src/router/run_plan.py`가 만드는 정본 계획과 그것을 다루는 CLI를 설명합니다.

!!! note "이 계획 자체는 오프라인입니다"
    `benchmark plan`은 **송신하지 않습니다**. 로컬 설정과 그것이 가리키는 워크로드·요율
    카드 파일만 읽어 지문을 뜨고, 계획을 **편집(redact)** 해 출력한 뒤 `plan_hash`를
    계산합니다. 실제 Azure 호출은 `--live`에 **일치하는 `--approve-plan`** 이 붙었을
    때만, 그것도 별도의 이음새([라이브 브릿지](foundry-live.md))에서만 일어납니다.

## 1. 세 개의 명령

```bash
# 1) 커밋된 템플릿에서 로컬 설정을 만든다 (자격증명 필드 없음).
cost-router config init                       # → .foundry.local.yaml

# 2) 계획을 해석·편집·해시한다. 송신 0.
cost-router benchmark plan --config .foundry.local.yaml

# 3) 사람이 계획을 검토한 뒤, 인쇄된 해시로 승인하고 실행한다.
cost-router benchmark run  --config .foundry.local.yaml \
    --live --approve-plan sha256:<...>
```

`config init`이 복사하는 템플릿은 저장소 루트의 `foundry.example.yaml`입니다.
`.foundry.local.yaml`은 gitignore되며 **자격증명을 절대 담지 않습니다** — `api_key`,
`access_token`, `bearer_token`, `client_secret`, `password`, `connection_string`,
`sas_token`, `secret_key` 키는 파싱 단계에서 거부됩니다. 인증은 키리스 Microsoft
Entra ID(`az login`)가 골든 패스입니다.

## 2. `plan_hash` — 무엇이 해시를 바꾸고, 무엇이 안 바꾸는가

`plan_hash`는 **비용·품질·실행에 영향을 주는 필드**만 정규화(sorted-key, tight JSON)해
계산한 SHA-256입니다. 원칙은 단순합니다.

| 바꾸면 해시가 **바뀐다** | 바꿔도 해시는 **그대로다** |
| --- | --- |
| `run_mode`, arms(배포·kind·provider), 워크로드 지문 | `display.locale` / `--locale` / 서버 locale |
| 요율 카드 지문, `budget_usd`, 승인 기준(ceiling/rate) | 순수 표시용 설정 |
| `max_output_tokens`, `repetitions`, `retry.max_retries` | |
| 엔드포인트(호스트만), `api_version`, `random_seed` | |

**cost/quality/execution을 움직이는 것을 바꾸면 해시도 바뀌고**, 순수 표시용을
바꾸면 그대로 남습니다. 이 양방향 계약은 회귀 테스트로 고정돼 있습니다
(`tests/test_live_config.py`).

!!! warning "엔드포인트는 호스트만 남기고 편집됩니다"
    계획에 들어가는 엔드포인트는 `scheme://host[:port]`로 축약돼 경로·쿼리·URL 내
    자격증명(userinfo)이 제거됩니다. `http://`와 URL에 박힌 자격증명은 거부됩니다.
    인쇄된 편집 계획만으로 `plan_hash`를 그대로 재현할 수 있습니다.

### 해석 우선순위

실행 필드는 `CLI 오버라이드 > 로컬 YAML > 레거시 env > 안전한 기본값` 순으로 해석되고
각 필드의 출처는 계획의 `sources` 맵에 기록됩니다(비밀은 절대 기록하지 않음). locale만
§12 예외로 `--locale > COST_ROUTER_LOCALE > display.locale > en` 을 따르며 **실행
의미론에는 전혀 영향을 주지 않습니다**(동작은 i18n 몫으로 예약만 됨).

## 3. 승인 화면 — planned cells와 전송 시도 범위

사람 승인 화면은 **계획된 셀 수(planned cells)** 와 셀당 **기본/최대 전송 시도
(base/max transport attempts)** 를 보여줍니다.

```
— approval summary —
  planned cells   : 12
  transport attempts / cell : base 1, max 4
      (retries may dispatch anywhere in [base, max] — not an exact call count)
  worst-case reservation : $0.10 (whole ceiling reserved before dispatch)
  approve with    : --approve-plan sha256:<...>
```

재시도 가능한 호출을 **"정확히 N번"** 이라고 말하지 않습니다. 스로틀된 셀은 `base`에서
`max` 사이 어디든 정당하게 전송할 수 있기 때문입니다(`max = 1 + retry.max_retries`).
`planned cells = 태스크 수 × repetitions × arms 수`.

!!! danger "승인은 해시에 묶인다 — 어긋나면 fail-closed"
    `--live` 실행은 `--approve-plan <plan_hash>` 를 요구하고, 그 값이 방금 해석된
    계획의 `plan_hash`와 **한 글자라도 다르면 디스패치 이전에 거부**됩니다(exit 1).
    자격증명은 그 뒤에야 조회됩니다. 오래됐거나(stale) 어긋난 승인으로는 어떤
    유료 호출도 나가지 않습니다.

## 4. Model Router arm은 명시적이며 사라지지 않는다

arms는 로컬 YAML의 **명시적 `arms:` 목록**에서 해석됩니다. `model_router` arm은 그
목록의 한 항목이라 "앙상블 역할만 읽는" 경로로는 **결코 누락될 수 없습니다**. 계획이
만드는 후보(candidate)와 봉인된 매니페스트의 후보는 항상 동일한 arms를 담습니다.

## 5. 단일 진실 원천 — 미리보기 = 승인 = 실행 = 매니페스트 = 재생 = 콕핏

같은 `plan_hash`가 여섯 지점을 관통합니다.

1. **미리보기**: `benchmark plan`이 편집 계획 + 해시를 인쇄.
2. **승인**: 사람이 그 해시를 `--approve-plan`으로 확인.
3. **실행**: 실행기가 계획의 후보·요율·예산으로 측정.
4. **매니페스트**: 봉인된 스냅샷에 동일한 `plan_hash`가 기록됨.
5. **재생**: `replay`가 매니페스트의 `plan_hash`를 그대로 되읽음.
6. **콕핏**: `dashboard --live --config`가 같은 계획을 바인딩해 preview·승인·실행·abort·
   snapshot이 모두 동일한 `plan_hash`에 묶입니다(03C). 브라우저는 계획 내용을 절대
   공급하지 않고 서버측 계획을 조종만 합니다.

이 동일성은 스크립트된 오프라인 클라이언트로 검증되므로 CI는 절대 송신하지 않습니다.

## 6. 레거시 설정 경로는 사용 중단(deprecated)

이전의 명령별 env/플래그 설정(`foundry live`, `foundry arena`, `measure run`,
`measure catalog`)은 **여전히 동작하지만 사용 중단**입니다. 이들은 정본 계획이 이제
소유하는 독립적 해석 의미론을 갖고 있어 호출하면 stderr로 안내를 냅니다.
`dashboard --live`도 `--config` 없이 실행하면 같은 이유로 사용 중단 경고를 냅니다 —
계획을 바인딩하지 않은 콕핏은 레거시 즉석(ad-hoc) 설정 경로로 떨어지기 때문입니다.

```
note: `cost-router foundry live` uses the legacy environment/flag config path,
deprecated by BOLT-03A in favor of the canonical run plan
(`cost-router config init` then `cost-router benchmark plan --config
.foundry.local.yaml`). See docs/manual/run-plan.md.
```

경고는 stderr로만 나가므로 `--json` stdout이나 캡처된 요약을 오염시키지 않습니다.
새 작업은 정본 계획 경로를 쓰세요.

## 관련 문서

- [라이브 실측 브릿지](foundry-live.md) — 실제 Azure Model Router 호출 이음새.
- [플릿 등록 & 모델 선택](fleet.md) — arms/요율 카드가 되는 아티팩트.
- [감사 원장](ledger.md) — 봉인된 스냅샷과 재생 무결성.
- [실험 설정(YAML)](experiments.md) — 실험 아티팩트 스키마.
