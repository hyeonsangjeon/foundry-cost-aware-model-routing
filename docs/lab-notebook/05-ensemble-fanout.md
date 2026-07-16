# 실험 05 · 앙상블 팬아웃 세금 (Foundry 메트릭)

!!! abstract "한 줄 요약"
    비용 인지 라우팅은 **가치 높은 태스크에서만** 모든 후보로 팬아웃(compare 모드)하고,
    이긴 모델만 청구합니다. 하지만 트레이스의 `cost_usd`는 **승자만** 기록하므로, 팬아웃이
    *실제로* 쓴 돈(모든 후보 합)은 숨어 있습니다. 이 실험은 그 숨은 비용을 드러냅니다 —
    6개 태스크 팬아웃에 **$0.496812**를 쓰고 승자 **$0.132801**만 남깁니다. 나머지
    **$0.364011 (3.74×)** 이 **앙상블 세금**(진 모델을 돌린 값)입니다. 모든 수치는
    `measured = false`.

## 이 실험은 무엇인가

- **상황(언제):** "여러 모델을 앙상블로 다 돌리면(=OpenRouter식 베스트-오브-N) 더 좋지
  않을까?"라는 아이디어가 들어온 순간. 팬아웃은 품질을 올릴 수 있지만 **비용이 곱해집니다.**
  그 비용을 정직하게 계량해야 할 때.
- **작업(무엇을):** 손으로 고른 가치 높은 태스크 6건에, 값싼 후보는 검사 하나를 실패하고
  **중·상위 후보는 완전히 통과(동점)** 하도록 오프라인 신호를 붙입니다
  (`samples/responses/ensemble-fanout-signals.sample.json`). 예산 게이트가 이들을
  **compare 모드**로 보내 모든 후보를 평가(팬아웃)하고, 동점은 정책 순위상 **가장 싼 완전
  통과 모델**로 깨집니다.
- **실험(무엇을 검증):** (1) 라우팅이 **커버리지 100%**를 유지하면서 (2) 나이브 대비
  **~47% 절감**하고, 동시에 (3) 팬아웃이 쓴 총비용과 승자 비용의 차이 — **앙상블 세금** —
  을 공용 메트릭으로 정확히 회수함을 검증합니다.

이 실험은 실험 01·02(이득), 03(커버리지 절벽), 04(공짜 점심 없음)에 이은 **다섯 번째
정직함**입니다. 여기서는 *"앙상블은 공짜가 아니다 — 팬아웃에는 세금이 붙는다"* 를 숫자로
드러냅니다.

## 왜 세금이 숨는가

`route_tasks`가 compare 모드로 팬아웃하면 모든 후보를 평가하지만, 트레이스의 `cost_usd`는
**선택된 모델 하나**만 청구합니다. 즉 라우팅의 청구서(`total_cost_usd`)는 정직한 라우팅
비용이지만, **"모든 모델을 다 돌리는 앙상블"의 진짜 원가**는 아닙니다. 그 진짜 원가는
각 compare 태스크에서 **시도된 모든 후보의 비용 합**입니다.

`router.metrics.fanout_stats(traces)`가 바로 이 합을 회수합니다:

- `fanout_usd` — compare 태스크에서 시도된 **모든 후보** 비용의 합 (팬아웃 원가)
- `winner_usd` — 그중 **승자**의 비용 (라우팅이 실제 청구한 값)
- `ensemble_tax_usd` = `fanout_usd − winner_usd` — **진 모델을 돌린 값(세금)**
- `tax_ratio` = `fanout_usd / winner_usd` — 승자 대비 팬아웃이 몇 배인가

## 설정

- **워크로드:** `samples/telemetry/mixed-coding-workload.sample.jsonl`의 가치 높은 태스크 6건
- **신호:** [`samples/responses/ensemble-fanout-signals.sample.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/responses/ensemble-fanout-signals.sample.json)
  (값싼 후보는 검사 1개 실패, 중·상위는 완전 통과 동점)
- **정책·가격:** 번들 시드 정책·가격 (`measured = false`)

## 실행

```bash
cost-router experiment run ensemble
cost-router experiment run ensemble --json     # 계약 체크 + fanout 통계 전체
cost-router metrics emit ensemble              # Azure Foundry 형태의 메트릭 레코드
```

## 결과 — 47% 절감, 그러나 팬아웃은 3.74배

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $0.250728
  AFTER   cost-aware routing                   $0.132801
  SAVED   $0.117927  (47.0% lower)  at 100.0% coverage

reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 47.0% ≥ 40.0%
  PASS  tasks: 6 ≥ 6
```

라우팅 청구서는 **$0.132801**로 정직하게 싸지만, 그 6개 태스크를 compare로 팬아웃하며
실제로는 **$0.496812**어치 모델을 돌렸습니다. 태스크별로 보면:

| task | class | 팬아웃 후보 | 승자 | 팬아웃 원가 | 승자 비용 | 앙상블 세금 |
| --- | --- | --- | --- | --- | --- | --- |
| t-0003 | repo_patch | swift · balanced · deep · premium | **balanced-pro** | $0.179844 | $0.032793 | $0.147051 |
| t-0007 | plan | swift · balanced · deep | **balanced-pro** | $0.088090 | $0.029368 | $0.058722 |
| t-0024 | repo_patch | swift · balanced · deep · premium | **deep-reasoner** | $0.185132 | $0.061014 | $0.124118 |
| t-0036 | generate | mini · swift · balanced | **swift-coder** | $0.016324 | $0.002619 | $0.013705 |
| t-0015 | validate | mini · balanced · deep | **balanced-pro** | $0.013976 | $0.004946 | $0.009030 |
| t-0032 | test | mini · swift · balanced | **swift-coder** | $0.013446 | $0.002061 | $0.011385 |
| **합계** | | | | **$0.496812** | **$0.132801** | **$0.364011** |

**앙상블 세금 = $0.364011**, 즉 팬아웃 원가가 승자의 **3.74배**입니다.

!!! example "스포트라이트 — t-0032 (test)"
    라우팅은 `swift-coder`($0.002061)를 골랐고, 나이브 프리미엄 arm은 `balanced-pro`
    ($0.010589)를 씁니다 → **5.14× 저렴**. 하지만 이 한 태스크를 팬아웃하는 데는
    (mini·swift·balanced) **$0.013446**가 들어, 승자의 6.5배입니다. 절감과 팬아웃 세금은
    **동시에** 성립합니다.

## 전략 프런티어 — "다 돌리기"는 프런티어 밖

같은 정직함을 합성 100건 히어로 워크로드의 **전략 arm**으로도 확인합니다. 대시보드
프런티어에 네 번째 점 `all_ensemble`(모든 태스크에서 모든 모델 팬아웃)을 추가했습니다:

| 전략 | 비용 | 커버리지 |
| --- | --- | --- |
| all-mini (제일 싼 모델만) | $0.187913 | 22% |
| cost-aware mix (라우팅) | $1.659167 | 100% |
| all-premium (제일 비싼 모델만) | $2.226910 | 100% |
| **all-ensemble (전부 팬아웃)** | **$4.225226** | 100% |

`all-ensemble`은 커버리지 100%지만 **가장 비쌉니다** — premium보다도 1.9배. "그냥 다
돌리자"는 커버리지를 사지 못하는(이미 premium이 100%) 순수 낭비임을 프런티어가 시각적으로
드러냅니다.

## 공용 메트릭 클래스 — Foundry 형태로 저장·조회

이 실험이 도입한 재사용 자산은 `src/router/metrics.py`의 **공용 메트릭 모듈**입니다. CLI·HTTP
서비스·대시보드가 모두 이 하나를 공유하므로, 실험별 통계와 히스토리컬 대시보드가 숫자를
손으로 다시 계산하지 않습니다.

- `ExperimentMetrics` — 실행 하나의 정규화 스냅샷(비용·커버리지·팬아웃 세금 + 내용 주소
  기반 `run_id`). 순수·결정론적입니다.
- `ExperimentMetrics.to_metric_records()` — **Azure Monitor / OpenTelemetry** 메트릭
  데이터 포인트 형태(값·단위·`customDimensions`)로 렌더 — Azure AI Foundry 관측성에 그대로
  밀어 넣을 페이로드입니다.
- `JsonlMetricsStore` — 오프라인 히스토리 저장소(append-only JSONL). 히스토리컬 대시보드가
  여기서 읽습니다.
- `FoundryMetricsEmitter` — 연결 문자열(`AZURE_AI_FOUNDRY_CONNECTION_STRING` 등)이 있으면
  `configured = True`가 되지만, 실제 전송은 **주입된 sink**로만 일어납니다 → 기본 경로는
  절대 네트워크를 타지 않습니다(오프라인·테스트 안전).

자세한 사용법은 [메트릭 & Foundry](../manual/metrics.md) 매뉴얼을 참고하세요.

## 웹앱에서 보기 — 클릭하면 통계, 히스토리컬 대시보드

대시보드에 두 패널을 추가했습니다:

- **Experiments** — 실험 탭을 누르면 그 실험의 비용·커버리지·**앙상블 팬아웃 세금**·재현성
  계약이 즉시 뜹니다. `GET /experiments`(라이브) 또는 `experiments.json`(정적 export)에서
  Foundry 형태 메트릭을 읽습니다.
- **Historical dashboard** — 기록된 실행 이력 테이블. 라이브 서버에서 실험을 실행할 때마다
  한 줄씩 누적되고(`GET /metrics/history`), 정적 데모에서는 실험별 결정론 기준 스냅샷을
  보여줍니다.

[라이브 데모에서 보기 →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)

## 이 숫자를 정직하게 읽기

앙상블/팬아웃은 **품질을 올릴 수** 있습니다 — 하지만 그건 비용 실험이 아니라 품질 실험의
주장입니다. 이 저장소는 **오프라인 비용 관점**만 정직하게 다룹니다: *같은 커버리지에서
팬아웃은 승자만 청구하는 라우팅보다 항상 더 비싸다.* 앙상블을 켤지는, 팬아웃 세금
($0.364011, 3.74×)이 살 만한 품질 향상을 주는지 **측정된** 데이터로 판단할 문제입니다 —
이 실험은 그 **비용 축**을 정확히 계량해 그 판단의 절반을 제공합니다.

## 이 실험을 언제 쓰나

- "여러 모델 앙상블/베스트-오브-N을 도입하면 얼마나 더 드나?"를 **태스크당 팬아웃 세금**으로
  가늠할 때.
- 라우팅의 절감을 보고할 때, **팬아웃 원가를 감춘 채** 승자 비용만 자랑하지 않도록 세금을
  함께 노출할 때.
- 실험 통계를 Azure AI Foundry 관측성으로 내보낼 **공용 메트릭 스키마**가 필요할 때.

## 이 실험 재현하기

```bash
pip install -e .
cost-router experiment run ensemble          # 사람이 읽는 요약
cost-router experiment run ensemble --json    # 계약 체크 + fanout 통계
cost-router metrics emit ensemble             # Azure Foundry 형태의 메트릭 레코드
cost-router metrics history --store runs.jsonl   # (기록했다면) 히스토리 조회
```
