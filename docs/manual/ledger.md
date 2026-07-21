# 감사 원장

라우팅 결정을 **추가 전용(append-only)·해시 체인 JSONL 원장**에 기록하고, 저장된 선택 입력을
다시 돌려 정규 최종 페이로드를 **바이트 단위로** 대조해 검증합니다. 모든 결정이 재현되고
필수 필드 완전성이 99% 이상일 때에만 검증을 통과합니다.

## 기록

```bash
cost-router replay --synth --ledger reports/routing.jsonl
cost-router route-once --task-id t-0003 --synth --ledger reports/one.jsonl
cost-router hero --ledger reports/hero.jsonl
```

## 검증(재생)

```bash
cost-router ledger replay --ledger reports/routing.jsonl
```

```text
records: 100
matched: 100
completeness: 100.0%
status: PASS
```

## 측정 원장 — 같은 무결성을 실측 실행에도

오프라인 원장은 계약상 `measured = false`입니다. 실제 라이브 호출(4-way 아레나 등)은
**분리된 측정 원장**(`src/router/ledger/measured.py`, `MeasuredArenaLedger`)에 쌓이며,
오프라인 원장을 **전혀 건드리지 않고** 같은 두 가지 보장을 받습니다:

- **변조 감지** — 각 줄은 정규 페이로드의 `record_hash`로 봉인되고 `previous_hash`로 앞줄과
  연결됩니다(오프라인 원장과 동일한 해시 프리미티브 → 바이트 단위로 동일한 해시).
- **결정론적 비용 재생** — 각 줄은 채점에 쓴 `pricing_snapshot`을 품어, 검증이 **기록된
  usage × 그 요율표**로 모든 호출 비용을 다시 계산해 일치를 확인합니다. 측정된 usage는 고정
  증거, 비용은 그 순수 함수 — 오프라인 원장이 "저장된 입력으로 결정을 재생"하는 것과 같은 정신.

```bash
cost-router ledger measured-replay --ledger runs/arena.jsonl
```

```text
records: 5
replayed: 5
  → each recorded call cost re-derived from its usage × the pinned rate card
status: PASS
```

!!! note "두 원장은 일부러 분리됩니다"
    오프라인 원장은 오프라인 투영만, 측정 원장은 실측 지출만 담습니다. 공유하는 것은 순수 해시
    프리미티브뿐이라 어느 쪽도 상대의 엄격함/정직 라벨을 흐리지 않습니다.

## 원장 레코드에 담기는 것

각 레코드는 하나의 자기완결적·재생 가능한 오프라인 라우팅 결정입니다.

- **정책/가격 해시 + 스냅샷** — 어떤 정책·요율로 결정했는지 고정
- **정규화된 태스크 프로필** — 클래스·난이도·위험(risk)
- **후보 순서와 신호** — 각 후보의 사전값, 오프라인 신호, 수용 여부
- **게이트 결정** — 선택 모드·값·이유(budget-gate-v1)
- **선택된 모델과 비용** — 그리고 정직한 오프라인 라벨
- **해시 체인** — `previous_hash` → `record_hash`로 이어지는 무결성 체인

## 청구 기준(billing basis)

현재 라우터는 **미리 계산된 오프라인 신호**에서 실행 하나를 선택합니다. 그 신호 조회는 모델
호출이 아닙니다. 그래서 원장 비용은 명시적으로 `selected-execution-only` 기준을 씁니다.

!!! warning "라이브 팬아웃은 별도 회계가 필요합니다"
    미래의 라이브 팬아웃 계층(여러 후보를 실제로 호출하는 앙상블)은 모든 패널/심판 호출을
    **각각 별도로** 회계해야 합니다. 오프라인 투영의 `selected-execution-only`를 라이브 비용으로
    오해하면 안 됩니다. 모든 레코드는 `labels.measured = false`를 유지합니다.

## 신호 출처 seam — 오프라인 원장의 정직 경계

라우터는 태스크별 `모델 → {applies, compiles, tests_pass, lint_pass}` 신호 맵에 대고 결정을
채점합니다. **그 신호가 어디서 오는지**는 이제 흩어진 `synth` / `signals_path` 불리언이 아니라,
하나의 주입 가능한 객체 `router.signals.SignalSource`로 표현됩니다:

| 출처 | `kind` | 오프라인 원장 허용? | 결정성 |
| --- | --- | --- | --- |
| `synth_signal_source()` | `synth` | ✅ | 워크로드+정책에서 결정론적 파생(무 I/O) |
| `fixture_signal_source(path)` | `fixture` | ✅ | 체크인된 JSON 스냅샷 재생 |
| measured / live 제공자 | `measured`·`live` | ❌ | 후보를 실제 실행한 실측(이 저장소 범위 밖) |

`SignalSource`는 단지 `(workload, policy) -> SignalBundle` 콜러블입니다. `SignalBundle`은
신호와 그 **출처(`kind`)**를 함께 묶어, 원장으로 흐르는 라벨이 신호와 절대 어긋나지 않게 합니다.
모든 실행 진입점(`run_replay` · `run_bundled_replay` · `run_route_once` · `run_evals`)이
`signal_source=`를 받아, 흐름 코드를 건드리지 않고 출처를 갈아끼울 수 있습니다.

```python
from router import run_bundled_replay, synth_signal_source

# 기본(오프라인): synth/fixture 그대로 — 결정론적
report = run_bundled_replay(synth=True)

# 미래의 실측 제공자를 주입 (kind="measured")
report = run_bundled_replay(signal_source=my_measured_source)
```

**정직 경계(핵심):** 엄격한 해시 체인 오프라인 원장은 **오프라인 투영만** 감사합니다.
`OFFLINE_SIGNAL_KINDS = {synth, fixture}` 밖의 `kind`(measured·live)는 레코드가 만들어지기
**전에** `assert_offline_ledger_kind`가 막습니다 — 실측 신호를 `--ledger`와 함께 주입하면
경계 특화 오류가 나고 **아무 것도 기록되지 않습니다**. 실측 지출은 별도의 측정 감사 경로로
가야 하며, 그래야 오프라인 투영이 오염되지 않습니다.

## 왜 원장인가

라우팅의 헤드라인 가치는 "가장 싼 청구서"가 아니라 **모든 라우팅 결정에 대한 감사 추적과
함께** 같은 커버리지를 더 낮은 비용으로 얻는 것입니다. 원장은 그 감사 추적을 **재현 가능하게**
만듭니다 — 저장된 입력만으로 동일한 결정을 다시 만들어낼 수 있어야 검증을 통과합니다.
