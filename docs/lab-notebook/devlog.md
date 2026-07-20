# 개발 로그 · 실험일지

!!! abstract "이 문서는 무엇인가"
    실험(01–08)이 *"무엇을 검증했는가"*를 담는다면, 이 개발 로그는
    *"언제 · 어떤 상황에서 · 무슨 작업을 했는가"*를 시간순으로 남깁니다.
    각 항목은 **상황(왜) · 작업(무엇을) · 검증(효과)** 세 줄로 정리하며,
    수치가 등장하면 저장소 규약대로 항상 `measured = false`입니다.

    최신 항목이 맨 위입니다.

---

## 2026-07-21 · 아레나 입력 데이터 — 읽을 수 있는 문제 진술

!!! note "한 줄 요약"
    아레나가 태스크의 **메타데이터만**(클래스·난이도·토큰) 보여 줘 "그래서 무슨 문제인지"가
    없었습니다. 큐레이션 5건에 **사람이 읽는 문제 진술**(제목·프롬프트·합격 기준)을 붙여 CLI·
    웹앱에 띄웠습니다 — 단, **저작한 합성 예시**이지 공개 벤치마크가 아닙니다(`measured = false`).

- **상황(왜):** "이 프로토타입의 사용자 입력 테스트 데이터가 뭐냐"는 질문에서 출발. 아레나는
  구체적 문제 없이 숫자만 채워, 신규 사용자가 *"각 방법이 **무엇을** 푸는지"* 볼 수 없었습니다.
- **작업(무엇을):**
    - `samples/prompts/curated-arena.sample.json` 신설 — 태스크별 `title` · `prompt` ·
      `acceptance`. `note`/`labels`에 **저작-합성 출처**를 자체 문서화(`problem_basis =
      authored-synthetic`). `offline.load_task_prompts`로 로드.
    - `arena.head_to_head`/`bundled_head_to_head`에 `prompts` 옵션 인자 + 페이로드 `problem`
      키 + 메뉴 `title`. `pipeline.bundled_compare`가 기본 프롬프트를 읽어 스레드.
    - CLI `compare`가 표 위에 `problem` 블록(제목·줄바꿈 프롬프트·`expect:`)을, 대시보드가
      **문제 카드**(`renderArenaProblem`, 주입 안전 `textContent`)를 렌더.
    - **정직성 결정:** HumanEval·MBPP 등 공개 벤치마크를 붙이지 않음 — 합성 pass/fail 신호를
      실명 벤치마크에 붙이면 실측 평가로 오해되어 정직하지 않기 때문. 진짜 공개 데이터+채점은
      라이브 실측 브릿지(`measured = true`) 몫.
- **검증(효과):** `classify_task`가 명시적 `class` 필드를 우선하고 다섯 태스크 모두 이를 가져,
  **프롬프트는 표시 전용**이며 분류·비용에 무영향 — 고정 수치(t-0003 $0.032793 등)가 **그대로**
  임을 새 테스트로 확인(arena·CLI·서버·정적 export). 프롬프트를 빼도 아레나가 동작하도록
  `problem`은 선택적(`None`). `measured = false`.
    이 입력 데이터의 실험 기록은 [실험 08 · 아레나](08-arena.md)의 "입력 테스트 데이터" 절에
    정리했습니다.

---

## 2026-07-21 · 큐레이션 태스크 실측 전환 — live-sendable 워크로드

!!! note "한 줄 요약"
    "t-0001~t-0006을 전부 실측으로 바꾸자"는 요청. 실측 브릿지(`foundry_live`)는 이미 있었지만,
    번들 텔레메트리에 **프롬프트가 없어** 라이브로 보낼 수 없다는 마지막 블로커가 남아 있었습니다.
    큐레이션 5건에 보낼 수 있는 프롬프트를 담은 워크로드를 만들어, **크리덴셜만 있으면 한 명령**으로
    전부 `measured = true`가 되게 했습니다.

- **상황(왜):** 아레나·프런티어의 t-0001~t-0006은 전부 오프라인 목업(`measured = false`)입니다.
    실측 브릿지는 완비돼 있었지만(`measured_router_summary`·`AzureModelRouterClient`·grader·
    녹화 스냅샷), 라이브 호출에는 **프롬프트가 있는 워크로드**가 필요한데 번들에는 없었습니다.
- **작업(무엇을):**
    - `samples/telemetry/curated-arena-live.sample.jsonl` 신설 — 큐레이션 5건에 저작-합성
      프롬프트(08 아레나 입력 데이터)를 **임베드**한 live-sendable 워크로드. 메타데이터·토큰은
      기존 워크로드와 동일.
    - 이 워크로드로 실측 경로를 검증: 녹화 스냅샷 재생 → `measured = false`(결정론·무송신),
      주입한 mock SDK로 라이브 경로 → **5건 프롬프트 실제 전송 + `measured = true`**.
    - 문서: `foundry-live.md`의 "번들은 못 보냄" 노트를 **준비된 큐레이션 워크로드 + 한 명령**으로
      교체. `head-to-head.md`·`08-arena.md`에 "실측으로 보기/전환" 절 추가.
- **검증(효과):** `cost-router foundry live --workload curated-arena-live…`가 5건을 measured
    스코어링(녹화 → measured=false)으로 통과. mock SDK 라이브 경로는 프롬프트 5건 전송 후
    `provenance = live · measured = true · spend_source = provider-usage`. 새 테스트 3건으로
    (워크로드가 sendable · 녹화 offline · 라이브 measured) 고정. **경계:** 프롬프트는 저작-합성
    이지만 보내 받은 usage·비용은 실측이며, 정확도까지 측정하려면 grader 주입 필요.
    실측 실행은 사용자의 Azure 크리덴셜·네트워크·실제 비용이 있어야 하므로, 저장소는 경로를
    결정론적으로 검증하고 한 명령을 제공합니다.

---

## 2026-07-20 · 아레나 — "문제 하나, 네 가지 방법" 5분 wow 데모

!!! note "한 줄 요약"
    집계 패널은 워크로드 전체를 비교하지만, 신규 사용자가 먼저 던지는 질문은 *"이 문제 하나를
    두고 각 방법이 얼마·얼마나 느림·맞히나?"*입니다. 태스크를 고르면 네 열(가장 싼 모델 ·
    프리미엄 · 앙상블 · 비용 인지 라우터)이 **비용 · 지연 · 정확도**로 채워지는 HuggingFace
    Spaces식 화면을 웹앱·CLI 양쪽에 넣었습니다.

- **상황(왜):** 대시보드는 강력하지만 전부 **집계**라, "같은 문제 하나를 여러 방법으로 돌려
  비용·성능·정확도를 눈으로 비교"하는 즉각적 화면이 없었습니다. 사용자가 원한 것은 바로 그
  "누르면 바로 보이는" 5분 wow였습니다.
- **작업(무엇을):**
    - `router.arena` 신설 — 태스크 하나에 네 접근을 점수화(`head_to_head`,
      `bundled_head_to_head`). 비용·정확도는 기존 오프라인 기계(`classify_task`,
      `candidates_for`, `pricing.cost_usd`, `is_clean`, `ordered_select`)를 **그대로 재사용**해
      집계 패널과 구성상 일치. 라우터는 **승자만**, 앙상블은 **후보 전부**를 청구(팬아웃 세금).
    - **지연은 새 도입한 예시적 투영**(`project_latency_ms`, `measured = false`) — 티어별 처리량
      모델로 토큰 수를 ms로. 앙상블=병렬(max), 라우터=순차(sum). wall-clock 아님을 UI·문서·CLI에
      명시.
    - `pipeline.bundled_compare` → 서버 `GET /compare[?task=]` · 정적 `compare.json` ·
      CLI `cost-router compare [--task --json]` · 대시보드 **아레나 패널**(태스크 칩 · 4카드 ·
      축별 승자 강조 · 판정문). 한 번의 페이로드로 태스크 전환은 왕복 없이 클라이언트에서.
- **검증(효과):** 기본 `t-0003`에서 라우터가 **가장 싸면서 정답도 맞히지만 지연은 가장 느림**
  (순차 에스컬레이션) — "공짜 점심 없음"의 정직한 트레이드오프가 한 화면에 드러납니다. 정확도는
  이진값이라 통과한 세 접근(프리미엄·앙상블·라우터)을 동등하게 크레딧하고, 가장 싼 모델만
  실패합니다. 쉬운 `t-0001`은 가장 싼 모델이 세 축을 모두 이기고 라우터도 그걸 고름. 새 테스트로
  수치·비용 규약·지연 투영·승자 로직·엔드포인트·정적 export·CLI를 고정. `measured = false`.
    이 프로토타입 실행 기능의 실험 기록은 [실험 08 · 아레나](08-arena.md)에 정리했습니다.

---

## 2026-07-19 · `.env` 자동 로드 — 설정 처리 마무리

!!! note "한 줄 요약"
    라이브 브릿지의 마지막 빈틈: `.env.sample`과 CLI는 *"`.env`에 채운 뒤 `foundry live`"*
    라고 안내했지만, 정작 **`.env`를 읽는 코드가 없어** 사용자가 채워도 조용히 오프라인으로
    떨어졌습니다. 의존성 없는 `.env` 로더를 넣어 `foundry status`·`live`가 실제로 `.env`를
    로드하게 만들어, 문서가 약속한 워크플로를 진짜로 동작시켰습니다.

- **상황(왜):** `FoundryConfig.from_env()`는 `os.environ`만 직접 읽는데, 저장소 어디에도
  `.env`를 환경으로 로드하는 코드가 없었습니다(python-dotenv 미사용). 결과적으로 안내대로
  `.env`를 채워도 `credentialed = no`로 남아 "설정 처리 미비"였습니다. 또 어댑터가 실제로
  받는 **대체 변수명**(`AZURE_OPENAI_*`, `AZURE_MODEL_ROUTER_DEPLOYMENT`,
  `APPLICATIONINSIGHTS_CONNECTION_STRING`, `COST_ROUTER_PRICING`)이 `.env.sample`에
  문서화돼 있지 않았습니다.
- **작업(무엇을):**
    - `foundry_live.load_dotenv_file()` 신설 — 표준 라이브러리만 쓰는 보수적 로더:
      **없으면 무해**, **export된 실제 환경 변수가 우선**(override=False), `KEY=VALUE`만 읽고
      주석·빈 줄·앞의 `export`·양끝 따옴표 처리, 셸 확장·명령 실행 없음. 설정한 키 이름만
      반환(값은 절대 로그·출력하지 않음).
    - CLI `foundry status`·`live`가 실행 초입에 이 로더를 호출(기본 `.env`, `--env-file`로
      변경 가능). `status`는 로드된 개수만 표시(`.env loaded : N setting(s)`)해 투명하되
      시크릿은 숨김.
    - `.env.sample`에 자동 로드·우선순위·대체 변수명 문서화, 매뉴얼 §1 갱신, `export`/`__all__`
      배선, `test_foundry_live.py`에 로더 파싱·우선순위·없는 파일 무해·CLI `--env-file` 3케이스.
- **검증(효과):** `foundry status --env-file <tmp>`가 채운 `.env`를 읽어 `credentialed = yes`로
  바뀌고, 엔드포인트는 호스트만·키는 마지막 4자만 노출(누출 0). override 가드로 CI/명시적
  export가 항상 우선. 전체 스위트 그린, ruff 클린, 시크릿 스캔·`.env.sample` 게이트 통과.
  기본 경로는 여전히 무송신·`measured = false`.

---

## 2026-07-19 · 라이브 Azure 실측 브릿지 + Foundry 설정 처리

!!! note "한 줄 요약"
    지금까지 전부 `measured = false` 오프라인 투영이었습니다. 정직함 규약이 예약해 둔
    *"여러분 테넌트의 라이브 eval → `measured = true`"* 행을 **실제로 채우는 코드**를
    추가했습니다 — 실제 Azure Model Router의 **토큰 usage로 비용을 계산**하고, 라이브
    호출에만 `measured = true`를 부여하는 격리된 opt-in 브릿지입니다. 기본 경로는 여전히
    오프라인·결정론이며, 크리덴셜이 없으면 녹화 스냅샷을 재생해 경로를 검증합니다.

- **상황(왜):** 웹앱 비교 데모(실험 클릭→메트릭, 히스토리컬 대시보드)는 완성됐지만, 유일하게
  남은 "실제 Azure 실측 연결"이 미배선이었습니다. 어댑터(`foundry_router.py`)는 모델 *선택*만
  교체할 뿐 여전히 `measured = false`였고, 실제 토큰·비용을 읽는 클라이언트도, 설정을 안전하게
  다루는 표면도 없었습니다.
- **작업(무엇을):**
    - `src/router/foundry_live.py` 신설 — `FoundryConfig`(모든 `AZURE_AI_FOUNDRY_*` 변수 수집 +
      **시크릿 마스킹 `status()`**), `RouterOutcome`(모델+실제 usage), `MeasuringRouterClient`
      프로토콜, `RecordedRouterClient`(결정론 재생), `AzureModelRouterClient`(SDK 지연 임포트,
      응답의 `model`·`usage`를 요율 토큰 종류로 매핑), `measured_router_summary`(합성 토큰이
      아닌 **실제 usage로 비용 계산**; 라이브에만 `measured=true`; grader 있으면
      `coverage_measured=true`; `model_aliases`로 벤더 이름→요율 키).
    - `.env.sample`에 실제 Foundry 변수 6종 추가, `pyproject`에 `foundry` 엑스트라(`openai`).
    - CLI `foundry status`(안전 진단)·`foundry live`(녹화 재생 기본, `--live`로 실제 호출,
      `--store`로 히스토리컬 대시보드에 기록).
    - 녹화 usage 픽스처(`model-router-usage.sample.json`) + `test_foundry_live.py`(설정 리댁션·
      게이팅·실측≠투영·라이브만 measured·grader·alias·Azure 목 클라이언트·CLI 20+ 케이스).
    - 매뉴얼 [라이브 실측 브릿지](../manual/foundry-live.md) + 정직함 규약/메트릭/CLI 상호 링크.
- **검증(효과):** 녹화 스냅샷 실측 `$0.156730 / 100%`가 오프라인 투영 `$0.087030 / 60%`과
  **다름**을 픽스처로 고정 — "실제 usage를 청구한다"는 핵심을 수치로 증명. 라이브 목
  클라이언트는 `measured=true / provenance=live`, 재생은 `measured=false / provenance=recorded`.
  시크릿은 `status()`에서 호스트+마지막 4자로만 노출(누출 0). 전체 스위트 그린, ruff 클린,
  기본 경로 무송신. 모든 번들 수치는 여전히 `measured = false`.

---

## 2026-07-18 · 스토리 아크 — 7개 실험을 하나의 이야기로

!!! note "한 줄 요약"
    실험 01–07이 각각 훌륭하지만, *"왜 이 순서인가 · 각 실험이 앞의 무슨 질문에 답하는가 ·
    전체가 무슨 한 문장을 방어하는가"*를 담은 **발표용 종합 페이지**가 없었습니다. 스토리
    아크 페이지를 신설해 일곱 실험을 **3막 내러티브**(이득 → 정직한 한계 → 비싼 지름길과
    그 대가)로 엮고, 재현성 계약이 각 반전을 어떻게 고정하는지 정리했습니다. 새 수치 없이
    기존 실측만 종합 — 모두 `measured = false`.

- **상황(왜):** 개별 실험 페이지 7개 + 개발 로그는 있었지만, 그 사이를 잇는 **연결
  조직**(왜 03이 02 다음인가, 05의 질문에 06이 어떻게 답하는가)이 흩어져 있었습니다.
  나중에 스토리라인을 발표·정리하려면 한 장의 내러티브 지도가 필요했습니다.
- **작업(무엇을):**
    - `docs/lab-notebook/story-arc.md` 신설 — **한 문장 논지**("관찰하고, 필요할 때만
      올려라 — 그리고 커버리지에 정직하라"), **7개 실험 여정 표**(질문→결과→무엇을 증명),
      **3막 구조**(1막 이득 01–02 / 2막 정직한 한계 03–04 / 3막 비싼 지름길 05–07),
      **정직함의 축**(모든 실험은 이득을 보이거나·위조를 반증하거나·대가를 통제), 재현성
      계약의 세 방향(하한/유령절감 상한/세금 상한/에스컬레이션 하한), 한 장의 프런티어,
      읽기 경로(5분/15분/전체), 전부 재현 루프.
    - nav 2번째 자리에 "스토리 아크 · 한눈에 보기" 배치(소개와 방법론 바로 다음),
      index.md 상단 콜아웃, README 내러티브 포인터를 스토리 아크로 갱신.
- **검증(효과):** 표의 모든 수치를 실측으로 재확인 — 01 −25.5% · 02 −56.7% · 03
  100%→67% · 04 0% · 05 −47%+3.74× · 06 세금 $0 · 07 단일 52% vs mix 100%(+48%p).
  mkdocs `--strict` 빌드 OK(내부 링크 전부 해소), 라이브 배포·200 확인. 코드·테스트 변경
  없음(순수 문서 종합). 모든 수치 `measured = false`.

!!! quote "정직한 단서"
    스토리 아크는 새 주장을 만들지 않습니다 — 이미 CI가 지키는 일곱 실험의 실측을
    **재배열**해 읽기 쉽게 했을 뿐입니다. 승리 슬라이드만 있는 저장소와 달리, 여기서는
    실험 다섯(03–07)이 가드레일이라는 점을 한 페이지로 드러냅니다.

---

## 2026-07-16 · 실험 07 「라우팅 레이어」 — 한 번 고르기 vs 관찰하고 올리기

!!! note "한 줄 요약"
    Azure AI Foundry **Model Router**를 프런티어의 **일급 arm**으로 올렸습니다. Model Router는
    앙상블이 아니라 프롬프트마다 모델을 **한 번** 고르는 *단일 호출* 라우팅 레이어입니다 —
    이 저장소의 킬러 히어로 방법론이 최적화하는 바로 그 계층. 합성 100건에서 단일 호출은
    커버리지 **52%**에 그치고, 관찰-후-에스컬레이션 mix는 비슷한 비용(**$1.59 vs $1.66**)에
    **100%**를 채웁니다 — 그 이득 **+48%p**를 새 계약 `min_escalation_gain`이 고정합니다.
    모든 수치는 `measured = false`.

- **상황(왜):** "Foundry Model Router로 앙상블하자"는 요청은 개념 혼동에서 출발했습니다 —
  Model Router는 앙상블이 아니라 **단일 호출 라우터**입니다. 사용자와 정리한 결론: 이건
  곁다리가 아니라 이 저장소의 라우팅 레이어(킬러 히어로 방법론)와 **같은 계층**이니
  프런티어의 일급 arm으로 넣는다.
- **작업(무엇을):**
    - **arm** `baseline.py`에 `model_router_pick`(난이도 floor 픽 `int(value×N)`) +
      공유 채점기 `score_single_call_arm` + `model_router_summary`(measured=false,
      equivalent=illustrative). `pipeline.py` `_strategy_comparison`에 다섯 번째 전략
      `model_router` 배선.
    - **계약** `experiment.py`에 `expect.min_escalation_gain`(mix 커버리지 − 단일 호출
      커버리지 하한)과 `_evaluate`의 `escalation_gain` 검사. 실험 자산
      `experiments/model-router.yaml`(합성 100건, `min_escalation_gain: 0.30`).
    - **측정 브리지** `foundry_router.py` — 의존성 없는 게이트 어댑터
      `FoundryModelRouter`(env 게이트, 주입 `client`, 기본 무egress) + `summary_from_choices`
      /`live_router_summary`/`load_recorded_choices`. 기록 픽스처
      `samples/responses/model-router-choices.sample.json`.
    - **웹앱** `dashboard.py` 프런티어에 다섯 번째 점 `model_router`(파란 점) + 라우팅
      레이어 주석(상대 링크 → 실험 07). 정적 export에도 포함.
    - 실험노트 [실험 07](07-model-router.md), nav·index·README·experiments·매뉴얼(experiments/
      dashboard) 교차 링크, CI 계약에 `experiment run model-router` 추가.
- **검증(효과):** `experiment run model-router` → coverage 100% · saved 25.5% ·
  **escalation_gain +48%p**(mix 100% − 단일 호출 52%) ≥ 30%. 프런티어 5점 배선 확인
  (synth: model_router $1.587646/52%, 선택이 5개 모델에 고루 분산). 상한/하한 가드 물림
  확인(하한 0.60으로 올리면 FAIL). 어댑터 게이트 확인(설정·client 없으면 비활성 →
  RuntimeError; 기록 픽스처 채점 $0.127136/100%, 라이브 provenance). 새 테스트
  `test_model_router.py`(18개) + `test_replay`/`test_server` 갱신으로 **pytest 289개 통과** ·
  ruff clean · mkdocs strict OK. 모든 수치 `measured = false`.

!!! quote "정직한 단서"
    `model_router` arm은 단일 호출 라우터의 **모양**을 보여주는 프록시일 뿐 Azure의 내부
    로직이 아닙니다(`equivalent = illustrative`). 실제 라우터의 선택 실력은 **측정된 값**이라
    게이트 어댑터로 끼워 넣도록 열어 두었고, 라이브 결정을 넣어도 비용·커버리지는 오프라인
    투영으로 남습니다(`measured = false`) — 오직 모델 **선택**만 라이브입니다.

---

## 2026-07-16 · 실험 06 「적응형 팬아웃 다이얼」 — 세금을 끄는 다이얼

!!! note "한 줄 요약"
    실험 05가 던진 질문("앙상블 팬아웃 세금 3.74×를 어떻게 하냐")에 대한 **정직한 해법**입니다.
    팬아웃 세금은 고정 비용이 아니라 **다이얼**입니다 — 예산 게이트의 `compare_min_value`
    임계값을 올리면 팬아웃하는 태스크가 줄고, **커버리지(100%)·절감(47%)은 그대로**인 채
    세금만 **3.74× → $0.000000**으로 계단처럼 무너집니다. 모든 수치는 `measured = false`.

- **상황(왜):** 실험 05는 "그냥 다 앙상블"의 숨은 세금을 드러냈지만, *"그럼 세금을 어떻게
  줄이나"* 는 미해결로 남겼습니다. 라우터에는 이미 적응형 팬아웃 로직(`BudgetGate`,
  가치 임계값)이 있었지만, 실험·계약·웹앱으로 노출되지 않아 이 다이얼이 보이지 않았습니다.
- **작업(무엇을):**
    - **재사용 가능한 예산 레버**를 `pipeline.py`에 관통시킴 — `run_replay`/`run_bundled_replay`
      /`_replay_report`에 `budget_gate` 파라미터 추가, `route_tasks`로 전달.
    - **실험 스키마 확장** `experiment.py` — `budget:` 블록(`compare_min_value`·
      `min_compare_candidates`)과 `Experiment.budget_gate()`, 그리고 양방향 계약 상한
      `expect.max_tax_ratio`(팬아웃 세금 상한, `_evaluate`의 `fanout_tax_ceiling` 검사).
    - 실험 자산 `experiments/adaptive.yaml`(`compare_min_value: 1.1` → 모든 태스크 가치보다
      높아 팬아웃 전무, `max_tax_ratio: 0.01`).
    - **팬아웃 스윕** `bundled_fanout_sweep`(pipeline) + `GET /fanout-sweep`(server) +
      `fanout-sweep.json` 정적 export(`build_static_site.py`).
    - **웹앱** `dashboard.py`에 팬아웃 다이얼 패널 신설 — 임계값 스윕 막대(세금)와 평평한
      두 선(커버리지·절감)을 함께 그려 "세금만 내려가는 계단"을 시각화(`/fanout-sweep`).
    - 실험노트 [실험 06](06-fanout-dial.md), nav·index·README·experiments·매뉴얼(experiments/
      dashboard) 교차 링크, CI 계약에 `experiment run adaptive` 추가.
- **검증(효과):** `experiment run adaptive` → coverage 100% · saved 47.0% · **팬아웃 세금
  0.00×**(routed $0.132801 유지). 스윕(baseline $0.250728): thr 0.00 → 6개 팬아웃, 세금
  $0.364011(3.74×) → thr 1.01 → 0개 팬아웃, 세금 **$0.000000**. 커버리지·절감은 전 구간 불변.
  상한 가드 물림 확인(앙상블에 `max_tax_ratio=0.01` 적용 시 3.74×로 FAIL). 정적 export 2회
  빌드 diff 동일(결정론). 새 테스트(`test_adaptive.py` 10 + server/build 확장)로 **pytest 270개
  통과** · ruff clean · mkdocs strict OK. 모든 수치 `measured = false`.

!!! quote "정직한 단서"
    이 오프라인 투영에서 compare(팬아웃)는 승자를 **바꾸지 않으므로** 순수 세금입니다. 실제
    시스템에선 best-of-N이 **품질**을 올릴 수 있는데, 이 투영은 그 향상을 모델링하지 않습니다 —
    그러니 세금을 내기 전에 **향상을 먼저 측정**하세요.

[라이브 데모에서 보기 →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)

---

## 2026-07-16 · 실험 05 「앙상블 팬아웃 세금」 + Foundry 메트릭 공용 모듈 & 웹앱

!!! note "한 줄 요약"
    "애저 파운드리 기능으로 앙상블 모델을 다 돌리고, 그 비용을 공통 클래스로 저장·조회하며,
    웹앱에서 실험을 누르면 통계가 뜨고 히스토리컬 대시보드에도 나오게"라는 요청을 구현했습니다.
    정직한 축은 **앙상블 팬아웃 세금** — compare 모드는 모든 후보를 돌리지만 승자만 청구하므로,
    "그냥 다 앙상블"은 같은 커버리지에 훨씬 더 냅니다(합성 히어로에서 all-ensemble $4.23 vs
    mix $1.66). 모든 수치는 `measured = false`.

- **상황(왜):** 실험 01–04는 단일 라우팅의 이득/경계를 다뤘지만, "여러 모델 앙상블/베스트-오브-N
  (OpenRouter식)"의 **비용**은 비어 있었습니다. 게다가 실험별 통계를 Azure Foundry 형태로
  저장·실시간 조회하고 웹앱·히스토리컬 대시보드에서 보고 싶다는 요구가 있었습니다.
- **작업(무엇을):**
    - **공용 메트릭 모듈** `src/router/metrics.py` 신설 — `fanout_stats`(팬아웃 세금 회수),
      `ExperimentMetrics`(정규화 스냅샷 + `to_metric_records()`로 Azure Monitor/OTel 형태),
      `JsonlMetricsStore`(오프라인 히스토리), `FoundryMetricsEmitter`(연결 문자열 인지 +
      **주입 sink로만** 전송 → 기본 경로는 무송신), `record_experiment_metrics`.
    - `src/router/pipeline.py`에 `summary["fanout"]`와 전략 arm `all_ensemble`(전부 팬아웃)을
      추가, `baseline.py`에 `ensemble_all_summary`.
    - 실험 자산 `experiments/ensemble.yaml` + `samples/responses/ensemble-fanout-signals.sample.json`
      (값싼 후보는 검사 1개 실패, 중·상위는 완전 통과 동점 → 승자=가장 싼 통과 모델).
    - **서버 엔드포인트** `GET /experiments`(카드+메트릭) · `GET /experiment?name=`(실행+히스토리
      기록) · `GET /metrics/history`(히스토리컬 피드)를 `src/router/server.py`에 추가.
    - **CLI** `experiment run --metrics-store` · `hero --metrics-store` · 새 `metrics`
      서브커맨드(`history`·`emit`).
    - **웹앱** `src/router/dashboard.py`에 Experiments 패널(탭 클릭 → 비용·커버리지·팬아웃
      세금·계약)과 Historical dashboard 테이블을 추가하고, 프런티어에 4번째 점 `all-ensemble`을
      추가. `scripts/build_static_site.py`가 `experiments.json`·`metrics-history.json`을 상대
      엔드포인트로 구워 Pages 정적 데모에도 동일 렌더.
    - 매뉴얼 [메트릭 & Foundry](../manual/metrics.md) 신설, 실험노트
      [실험 05](05-ensemble-fanout.md), nav·index·README·experiments 교차 링크, CI 계약에
      `experiment run ensemble` 추가.
- **검증(효과):** `experiment run ensemble` → coverage 100% · saved 47.0% (routed $0.132801 vs
  naive $0.250728), fanout_usd $0.496812 · **ensemble_tax_usd $0.364011 (3.74×)** · 스포트라이트
  t-0032(5.14×). `/experiments`·`/experiment`·`/metrics/history` 200, 히스토리 시드 4행 +
  라이브 append 검증. 정적 export 2회 빌드 diff 동일(결정론). node 렌더 프로브로 프런티어 4점 +
  실험 카드 5 KPI 확인. 새 테스트(`test_metrics.py`·`test_ensemble.py` + server/cli/build
  확장)로 **pytest 257개 통과** · ruff clean · mkdocs strict OK. 완전 오프라인 유지 — Foundry
  전송은 주입 sink에서만. 모든 수치 `measured = false`.

[라이브 데모에서 보기 →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)

---

## 2026-07-16 · ③ README 히어로 폴리시 — 실험 아크 표

!!! note "한 줄 요약"
    저장소에 처음 온 사람이 README 상단에서 **정직한 전체 서사**를 한눈에 보도록, 실험
    01–04를 "질문 → 결과" **아크 표**로 응집했습니다. 01·02는 이득, 03·04는 가드레일 —
    *"라우팅이 이기는 곳과, 일부러 안 이기는 곳"*을 나란히 보여줍니다.

- **상황(왜):** 실험 4개가 본문 여기저기에 흩어져, README만 보고는 "이득 실험"과 "정직한
  반례/경계"가 하나의 논지임을 파악하기 어려웠습니다. 30초 첫인상에서 정직함 규약이 곧
  세일즈 포인트임을 드러내야 했습니다.
- **작업(무엇을):** README 상단(Quickstart 직후)에 **실험 아크 표**(01 −25.5% · 02 −56.7% ·
  03 100%→67% · 04 0% 절감)를 추가하고, 각 행을 실험노트로 링크. 라이브 데모 링크에도 이번에
  추가된 **프런티어·커버리지 절벽** 시각화를 명시.
- **검증(효과):** 표·링크가 게시된 실험노트 경로(01–04)와 일치. 순수 문서 변경이라 코드·수치·
  재현성 무영향. 모든 수치는 `measured = false`.

---

## 2026-07-16 · ② 대시보드에 커버리지 절벽(정책 A/B) 패널

!!! note "한 줄 요약"
    실험 03의 **커버리지 절벽**을 문서 밖 대시보드에서도 바로 보이게 했습니다. 같은 워크로드에
    시드 정책과 비싼 fallback을 지운 `cost-cut` 후보를 나란히 비교 — 후보는 싸 보이지만
    커버리지가 **100% → 67%(−33%p)** 로 무너지는 걸 막대·배지로 드러냅니다.

- **상황(왜):** 커버리지 절벽은 실험노트(03)에는 있지만, "30초 안에 차이를 본다"는 히어로
  대시보드에는 없었습니다. *"싸 보이는 정책이 사실은 일을 버리고 있다"*는 반례를 라이브
  데모에서도 즉시 보여줘야 정직함 규약이 완성됩니다.
- **작업(무엇을):**
    - `src/router/pipeline.py`에 `bundled_coverage_cliff()` — 시드 vs `cost-cut` 정책의
      결정론 회귀를 대시보드용 콤팩트 페이로드로 묶는 함수를 추가.
    - `src/router/server.py`에 `GET /regression` 엔드포인트, `src/router/dashboard.py`에
      `#cliffPanel`(막대 A/B + `−33%p` 배지 + takeaway) + `renderCliff()` + replay와
      독립적인 비치명적 fetch를 추가. 데이터가 없으면 패널은 조용히 숨습니다.
    - `scripts/build_static_site.py`가 `regression.json`을 내보내고 상대 엔드포인트로 주입 —
      Pages 정적 데모에서도 동일하게 렌더링. 대시보드 매뉴얼에 항목·엔드포인트 추가.
- **검증(효과):** `/regression` 200 (base 100%/$1.66 · candidate 67%/$0.73 · Δ−0.33),
  node 렌더 프로브로 막대 폭(100.0%/67.0%)·`−33%p`·takeaway("dropped work") 고정,
  정적 export `regression.json` 회귀 테스트 추가. 완전 오프라인(외부 참조 0) 유지. pytest 212개
  통과 · ruff clean · mkdocs strict OK. 모든 수치는 `measured = false`.

---

## 2026-07-16 · 실험 04 「공짜 점심은 없다」 + 양방향 계약

!!! note "한 줄 요약"
    라우팅이 이득을 못 주는 **정직한 경계**를 실험으로 추가했습니다. 모든 태스크가 어려워
    최상위 모델만 통과하는 워크로드에서 라우팅은 **커버리지 100% · 절감 0.0%** — 나이브와
    비용이 정확히 같습니다. 더불어 `expect`에 `max_delta_pct` **상한**을 추가해, 과장된
    **유령 절감**이 새어 나오면 CI가 깨지게 만들었습니다.

- **상황(왜):** 실험 01·02는 "라우팅=이득", 03은 "잘못 튜닝하면 커버리지 붕괴"를 보여줬지만,
  *"올바르게 써도 이득이 0인 경계"*는 비어 있었습니다. "라우팅 켜면 항상 싸지지?"라는 기대의
  한계를 정직하게 그어야 했습니다.
- **작업(무엇을):**
    - `src/router/experiment.py`의 `Expectation`에 `max_delta_pct`(선택적 상한)를 추가 —
      설정된 실험에만 `savings_ceiling` 체크가 붙는 **양방향 재현성 계약**으로 확장.
    - hard 태스크 6건에 대해 **최상위 후보만 통과**하는 신호셋
      (`samples/responses/hard-tasks-signals.sample.json`)과 실험
      (`experiments/limits.yaml`)을 신설. 계약은 `min_coverage: 1.0` + `max_delta_pct: 0.0`.
    - `docs/lab-notebook/04-no-free-lunch.md`, nav·index·README·experiments 교차 링크,
      CI 계약 스텝(`experiment run limits`) 추가.
- **검증(효과):** `cost-router experiment run limits` → coverage 100% · saved 0.0%
  (routed $0.236785 = naive $0.236785). 가드 검증: hero(25.5% 절감)에 상한 0.0%를 걸면
  `savings_ceiling`가 **의도대로 실패**. 결정론 수치를 `tests/test_limits.py`(6개)로 고정.
  모든 수치는 `measured = false`.

---

## 2026-07-15 · ③ CI를 Node 24로 (위생 작업)

!!! note "한 줄 요약"
    GitHub Actions가 Node20 액션에 **지원 종료(deprecation)** 경고를 내기 시작 —
    워크플로 액션을 모두 **Node 24 런타임** 버전으로 올렸습니다. 실험 코드·수치·재현성에는
    영향이 없는 순수 인프라 위생 작업입니다.

- **상황(왜):** 러너가 Node20 기반 액션에 대해 곧 강제로 Node24로 대체하며 경고를 표시.
  경고를 방치하면 로그가 지저분해지고, 장기적으로 빌드가 깨질 위험이 있습니다.
- **작업(무엇을):** `.github/workflows/ci.yml`·`docs.yml`의 액션을 node24 런타임 릴리스로 범프.
    - `actions/checkout` `v4 → v5`
    - `actions/setup-python` `v5 → v6`
    - `actions/upload-pages-artifact` `v3 → v5`
    - `actions/deploy-pages` `v4 → v5`
- **검증(효과):** 입력 계약(예: `upload-pages-artifact`의 `path`, `_site` 아티팩트)이 그대로라
  동작 변화 없음. PR CI가 `checkout`·`setup-python`을, 병합 후 Pages 배포가 나머지 두 액션을
  실제로 검증합니다. 실험의 어떤 수치도 바뀌지 않습니다.

---

## 2026-07-15 · ② 비용 × 커버리지 프런티어 차트 ([PR #8](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/pull/8))

!!! note "한 줄 요약"
    대시보드에 **비용(x) × 커버리지(y) 2D 산점도**를 추가 — 세 전략 중 **mix만** 좌상단
    "both-win"(싸고 넓은) 코너에 도달하는 것을 한눈에 보여줍니다. 라이브러리 없이 인라인 SVG.

- **상황(왜):** 대시보드에는 이미 세 전략(`all-mini` · `all-premium` · `mix`)의 비용 막대와
  커버리지 알약이 있었지만, *"왜 mix만 좋은 트레이드오프인가"*가 숫자로만 흩어져 있어
  한눈에 들어오지 않았습니다.
- **작업(무엇을):** 같은 `summary["strategies"]` 데이터를 비용(가로) × 커버리지(세로)
  평면에 점으로 찍는 **프런티어 산점도**를 추가. `all-mini`는 좌하단(싸지만 좁음),
  `all-premium`은 우상단(넓지만 비쌈), `mix`만 좌상단 green "both-win" 존에 위치.
  순수 인라인 SVG로 그려 외부 의존성이 없습니다.
- **검증(효과):** node 프로브로 세 점의 좌표(NaN 없음, mix가 premium보다 왼쪽)를 확인하고
  `tests/test_server.py`에 회귀 테스트를 추가. 정적 내보내기(`/demo/`)에도 자동 포함됩니다.
  모든 좌표의 바탕 수치는 `measured = false`.

[라이브 데모에서 프런티어 보기 →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)
