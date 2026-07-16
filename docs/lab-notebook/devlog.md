# 개발 로그 · 실험일지

!!! abstract "이 문서는 무엇인가"
    실험(01–05)이 *"무엇을 검증했는가"*를 담는다면, 이 개발 로그는
    *"언제 · 어떤 상황에서 · 무슨 작업을 했는가"*를 시간순으로 남깁니다.
    각 항목은 **상황(왜) · 작업(무엇을) · 검증(효과)** 세 줄로 정리하며,
    수치가 등장하면 저장소 규약대로 항상 `measured = false`입니다.

    최신 항목이 맨 위입니다.

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
