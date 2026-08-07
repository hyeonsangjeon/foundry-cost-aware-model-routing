# 메트릭 & Azure Foundry

`src/router/metrics.py`는 실험 실행 하나를 **정규화된 메트릭 레코드**로 바꾸는 단일 지점입니다.
CLI·HTTP 서비스·대시보드가 모두 이 **공용 클래스**를 공유하므로, 실험별 통계와 히스토리컬
대시보드가 숫자를 손으로 다시 계산하지 않습니다.

!!! note "저장소의 약속을 그대로 지킵니다"
    - **오프라인·결정론적** — 추출은 순수 함수입니다. 같은 `ExperimentResult`는 같은
      `ExperimentMetrics`(내용 주소 기반 `run_id` 포함)를 냅니다. 네트워크를 타지 않습니다.
    - **`measured = false`** — 합성 데이터에 대한 투영이지, 측정된 Azure 지출이 아닙니다.
    - **Foundry-ready, not Foundry-coupled** — Azure Monitor / OpenTelemetry 메트릭 형태로
      렌더하지만, 실제 전송은 **주입된 sink**로만 일어납니다.

## 핵심 구성요소

| 이름 | 역할 |
| --- | --- |
| `fanout_stats(traces)` | compare(앙상블) 트레이스에서 **앙상블 팬아웃 세금**을 회수 (`fanout_usd` · `winner_usd` · `ensemble_tax_usd` · `tax_ratio`) |
| `ExperimentMetrics` | 실행 하나의 정규화 스냅샷(불변 dataclass) — 비용·커버리지·팬아웃 세금 + `run_id` |
| `ExperimentMetrics.to_metric_records()` | Azure Monitor / OTel 메트릭 데이터 포인트 리스트로 렌더 |
| `extract_experiment_metrics(result)` | `ExperimentResult` → `ExperimentMetrics` (순수·결정론적) |
| `JsonlMetricsStore` | append-only JSONL 히스토리 저장소 (`record` · `history` · `latest_per_experiment`) |
| `FoundryMetricsEmitter` | 연결 문자열 인지 Foundry 이미터(오프라인 캡처 + 주입 sink) |
| `record_experiment_metrics(...)` | 실행을 추출→저장소·이미터로 팬아웃하는 공용 엔트리 포인트 |

## 앙상블 팬아웃 세금

비용 인지 라우팅은 **가치 높은 태스크에서만** compare 모드로 모든 후보에 팬아웃하고, 이긴
모델만 청구합니다. 트레이스의 `cost_usd`는 승자만 기록하므로 팬아웃 원가는 숨어 있습니다.
`fanout_stats`가 그 숨은 비용을 회수합니다.

```python
from router.metrics import fanout_stats

stats = fanout_stats(report.traces)
# {'ensemble_tasks': 6, 'fanout_usd': 0.496812, 'winner_usd': 0.132801,
#  'ensemble_tax_usd': 0.364011, 'tax_ratio': 3.741, ...}
```

`ensemble_tax_usd = fanout_usd − winner_usd` 는 **진 모델을 돌린 값**입니다. 자세한 실험은
[실험 05 · 앙상블 팬아웃 세금](../lab-notebook/05-ensemble-fanout.md) 참고.

## Azure Foundry 형태로 내보내기

```bash
cost-router metrics emit ensemble
# 오프라인: "local capture (offline)" — 네트워크 송신 없음
```

연결 문자열이 있으면 이미터가 `configured = True`가 됩니다(그래도 기본 경로는 전송하지 않고
로컬 캡처만 합니다 — 실제 전송은 주입된 sink의 몫):

```bash
export AZURE_AI_FOUNDRY_CONNECTION_STRING="InstrumentationKey=...;IngestionEndpoint=https://..."
cost-router metrics emit ensemble --connection-string "$AZURE_AI_FOUNDRY_CONNECTION_STRING"
# "Azure Foundry (configured)" — 여전히 오프라인 캡처. 전송은 sink 주입 시에만.
```

각 레코드는 Azure Monitor customMetric / OTel 데이터 포인트 형태입니다:

```json
{
  "name": "router.ensemble.tax_usd",
  "value": 0.364011,
  "unit": "USD",
  "timestamp": "2026-01-01T00:00:00Z",
  "dimensions": {
    "experiment": "ensemble", "source": "fixture",
    "run_id": "38fb40ba53080601", "measured": "false",
    "policy": "seed", "pricing": "illustrative"
  }
}
```

## 히스토리 저장·조회 (히스토리컬 대시보드)

실험을 실행하며 메트릭을 히스토리 저장소에 기록하면, 대시보드의 **Historical dashboard**
패널과 `metrics history` 명령이 그 이력을 읽습니다.

```bash
cost-router experiment run ensemble --metrics-store runs.jsonl
cost-router hero --metrics-store runs.jsonl
cost-router metrics history --store runs.jsonl
cost-router metrics history --store runs.jsonl --experiment ensemble --json
```

라이브 서비스도 같은 저장소를 쓸 수 있습니다:

```python
from router.metrics import JsonlMetricsStore
from router.server import RouterService, serve

service = RouterService(metrics_store=JsonlMetricsStore("runs.jsonl"))
# GET /experiment?name=ensemble 를 부를 때마다 한 줄씩 히스토리에 누적됩니다.
```

!!! tip "결정론과 라이브의 분리"
    `GET /experiments`와 정적 `experiments.json`은 **순수 투영**이라 `recorded_at`이 `null`이고
    항상 같은 값을 냅니다. `GET /experiment?name=`은 **실시간 동작**으로 현재 시각을 찍어
    히스토리에 한 줄을 더합니다. 그래서 정적 데모는 재현 가능하고, 라이브 서버는 활동에 따라
    히스토리가 자랍니다.

## Foundry sink 주입 (전송이 실제로 일어나는 유일한 지점)

```python
from router.metrics import FoundryMetricsEmitter, extract_experiment_metrics

def push_to_foundry(records):
    ...  # Azure Monitor exporter 등 실제 전송 (여러분의 배포에서 구현)

emitter = FoundryMetricsEmitter(
    connection_string="InstrumentationKey=...",
    sink=push_to_foundry,   # 전송은 오직 이 주입된 sink로만
)
emitter.emit(extract_experiment_metrics(result))
```

sink를 주입하지 않으면 레코드는 `emitter.captured`에만 쌓입니다 — 완전 오프라인·테스트 안전.

!!! tip "여기까지는 `measured = false` — 실측으로 넘어가려면"
    이 페이지의 메트릭은 전부 합성 데이터에 대한 투영입니다. 실제 Azure Model Router의 토큰
    usage로 **측정된 지출**(`measured = true`)을 얻으려면
    [라이브 실측 브릿지](foundry-live.md)를 참고하세요.
