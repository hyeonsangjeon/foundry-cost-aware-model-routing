# 실험 10 · 실측 원장 — 측정 런을 **durable하게 봉인·검증** (`measured = true` canonical audit)

!!! abstract "한 줄 요약"
    [실험 09](09-live-routing-proof.md)가 라우터가 **무엇을** 골랐는지 실측으로 증명했다면, 이
    실험은 그 **측정 지출을 되돌릴 수 없게 봉인**합니다 — 실제 라이브 아레나 런을 **변조 감지
    (해시 체인) + 결정론적 비용 재생(봉인된 요율표)**을 갖춘 canonical 감사 원장으로 굳혀,
    자격 증명도 네트워크도 없이 **누구나 독립적으로 재검증**하게 만듭니다. 커밋된 5행 원장
    [`samples/ledger/arena-measured.ledger.jsonl`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/ledger/arena-measured.ledger.jsonl)은
    한 줄 명령으로 `status: PASS`를 재현하고, **1바이트만 고쳐도 검증이 깨집니다.** 엄격한
    오프라인 원장(`measured = false`)은 **전혀 건드리지 않습니다** — 두 감사는 서로의 정직
    라벨을 흐리지 않게 분리돼 있습니다.

## 이 실험은 무엇인가 — 측정을 넘어 **감사 가능**으로

- **상황(왜):** 실험 09는 저장소 최초의 `measured = true`였지만, 측정 지출은 무결성도 재생도
  없는 **평면 append-only JSONL**로만 남았습니다. 오프라인 실험(01–08)은 이미
  [재현성 계약](index.md#_2)으로 지켜지는데, 정작 **실측 지출**은 오프라인 투영이 받는 감사
  수준 — *"이 수치가 변조되지 않았고, 기록된 토큰에서 정말 유도되는가"* — 을 못 받았습니다.
- **작업(무엇을):** 측정 아레나 런을 **canonical 해시 체인 원장**
  ([`MeasuredJsonlLedger`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/src/router/ledger/measured.py))
  으로 봉인합니다. 각 행은 정규 페이로드에 대한 `record_hash`로 밀봉되고 `previous_hash`로
  앞 행에 사슬처럼 엮이며, **자신을 채점한 요율표(`pricing_snapshot`)를 통째로 내장**합니다.
  검증은 `cost-router ledger measured-replay` 한 줄이면 됩니다.
- **실험(무엇을 검증):** (1) 측정 런의 **변조가 감지**되는가, (2) 기록된 **usage × 봉인된 요율**로
  비용이 **결정론적으로 재생**되는가, (3) 이 전부가 **엄격한 오프라인 원장을 건드리지 않고**
  일어나는가 — 셋 다 **예**.

!!! note "이 페이지의 원장은 실측 usage를 재봉인한 것 — 새 지출이 아니다"
    커밋된 샘플은 실험 09/[아레나](08-arena.md)에서 **이미 실측·커밋된 토큰 usage**
    ([`samples/responses/foundry-arena-measured.json`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/responses/foundry-arena-measured.json))
    를 canonical 원장 형태로 **재봉인**한 것입니다 — 검증을 보이기 위해 새 Azure 호출을 하지
    않습니다(비용 0). 봉인 로직은 라이브 경로(`foundry arena --live --ledger`)가 쓰는 것과
    **동일**하며, `captured_at`을 캡처 타임스탬프에 고정해 **바이트 단위로 재현**됩니다. 새
    라이브 원장을 만드는 명령은 [재현 방법](#_8)에 있습니다.

## 두 가지 무결성 보장 — 왜 이게 "감사"인가

측정 원장의 모든 행은 **서로 독립적인 두 검사**를 통과해야 유효합니다:

| 보장 | 무엇을 막나 | 메커니즘 |
| --- | --- | --- |
| **변조 감지** | 기록된 그 어떤 바이트도 몰래 못 고침 | 정규 페이로드의 `record_hash` + 앞 행과 잇는 `previous_hash` 사슬 — 한 글자만 바뀌어도 사슬이 끊김 |
| **결정론적 비용 재생** | 위조된 비용을 진짜인 척 못 함 | 행에 **봉인된 `pricing_snapshot`** 을 내장 → 검증이 각 호출 비용을 `usage × 그 요율표`로 **다시 유도**해 일치를 확인. usage는 고정 증거, 비용은 그 순수 함수 |

두 감사는 **의도적으로 분리**됩니다: [오프라인 원장](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/src/router/ledger/record.py)은
오직 `measured = false` 투영만, 이 측정 원장은 오직 `measured = true` 실측 지출만 담습니다.
공유 코드는 **순수 해시 프리미티브**(`stable_hash` / `canonical_json`)뿐이라, 해시는 두 감사에서
바이트 단위로 동일하면서도 서로의 정직 라벨을 흐리지 않습니다.

## 엔드투엔드 흐름 — 라이브 콜에서 재검증까지

```text
  ┌──────────────────────┐   측정된 usage        ┌───────────────────────────┐
  │  foundry arena --live │ ───(실제 토큰)────▶   │  MeasuredJsonlLedger        │
  │  (키리스 Entra 호출)   │                       │  · record_hash 로 각 행 봉인 │
  │  cheapest·premium·     │   봉인된 요율표        │  · previous_hash 로 사슬 연결│
  │  ensemble·router       │ ───(pricing_snapshot)▶│  · usage×요율 을 행에 내장   │
  └──────────────────────┘                       └─────────────┬─────────────┘
                                                                │  append-only JSONL
                            ┌──────────────────────────────┐    ▼
   status: PASS / FAIL  ◀── │  ledger measured-replay        │  arena-measured.ledger.jsonl
                            │  · 사슬 무결성 확인             │
                            │  · usage×봉인요율 로 비용 재유도 │
                            └──────────────────────────────┘
```

핵심: 원장은 **자기 완결적**입니다. 검증에 원본 워크로드도, 네트워크도, 자격 증명도, 심지어
바깥의 요율 YAML조차 필요 없습니다 — 각 행이 자신을 채점한 요율표를 이미 품고 있으니까요.

## 측정 원장 행 해부

`arena-measured.ledger.jsonl`의 한 행(하나의 아레나 태스크 = 네 팔 전부)은 이렇게 생겼습니다:

| 필드 | 뜻 |
| --- | --- |
| `schema_version` | 원장 스키마 버전(현재 `1`) |
| `captured_at` | 봉인 시각(ISO-8601) |
| `pricing_version` · `pricing_hash` | 봉인된 요율표 버전과 그 SHA-256 지문 |
| **`pricing_snapshot`** | 이 행이 채점된 요율표 통째(기본 요율 + 등장 모델별 요율) — **비용 재생의 근거** |
| **`outcome`** | 측정 아레나 결과 하나: `task_id` · `arms{cheapest·premium·ensemble·router}` · 각 팔의 `calls[]`(모델·**실측 usage**·비용·지연) · `labels.measured = true` |
| **`previous_hash`** | 앞 행의 `record_hash`(첫 행은 `null` = genesis) |
| **`record_hash`** | 위 전부에 대한 SHA-256 — 이 행의 **변조 감지 봉인** |

커밋된 샘플의 첫 행 예: `task_id = t-0001`, arms = `cheapest·ensemble·premium·router`,
`labels = {measured: true, provenance: live, cost_basis: list-price, spend_source: provider-usage}`,
`pricing_snapshot.models = [gpt-5.4, gpt-5.4-mini, gpt-5.4-nano, grok-4-1-fast-reasoning]`,
`previous_hash = null`(genesis).

### 해시 체인 (커밋된 5행)

각 행의 `record_hash`가 다음 행의 `previous_hash`가 되어 **끊기지 않는 사슬**을 이룹니다 —
어느 행이든 삭제·삽입·수정하면 사슬이 그 자리에서 끊깁니다:

```text
  t-0001   previous_hash = null (genesis)   record_hash = 2ebe46b76991…
  t-0003   previous_hash = 2ebe46b76991…    record_hash = 9f70f421498e…
  t-0004   previous_hash = 9f70f421498e…    record_hash = a3d0d95451ff…
  t-0005   previous_hash = a3d0d95451ff…    record_hash = 89b6da64fa12…
  t-0006   previous_hash = 89b6da64fa12…    record_hash = 8847b126d77e…
```

## 검증 — 한 줄로 `status: PASS`

```bash
cost-router ledger measured-replay --ledger samples/ledger/arena-measured.ledger.jsonl
```

```text
records: 5
replayed: 5
  → each recorded call cost re-derived from its usage × the pinned rate card
status: PASS
```

`replayed == records`는 **다섯 행 전부**에서 사슬이 온전하고, 기록된 모든 호출 비용이
봉인된 요율표로 다시 유도돼 정확히 일치했다는 뜻입니다.

## 변조를 잡는다 — 두 개의 독립 방어선

!!! danger "데모 A — 비용 위조(재봉인 안 함): `record_hash` 불일치"
    라우터 팔의 비용 하나를 `$0.014502 → $0.000001`로 몰래 고치고 **다시 봉인하지 않으면**,
    정규 페이로드가 더는 `record_hash`와 맞지 않아 즉시 잡힙니다:

    ```text
    error: invalid measured ledger record at …:3: measured ledger record_hash does not match its canonical payload
    status: FAIL
    ```

!!! danger "데모 B — 위조 후 재봉인(해시는 유효): 비용 재생이 잡는다"
    영리한 공격자가 비용을 위조한 뒤 **`record_hash`까지 다시 계산**하면 변조 감지는 통과합니다.
    하지만 두 번째 방어선이 남습니다 — 검증이 봉인된 `pricing_snapshot`으로 비용을 **다시
    유도**하는데, 위조된 값은 `usage × 요율`과 맞지 않습니다:

    ```json
    {
      "issues": ["arms.router.calls[0].cost_usd"],
      "record_hash": "c566e85cbd18f66e…",
      "task_id": "t-0001"
    }
    ```
    ```text
    status: FAIL
    ```

    **핵심:** 해시 체인은 *어떤 바이트가* 바뀌었는지 잡고, 비용 재생은 *비용이 usage와
    일관되는지* 잡습니다. 위조가 성립하려면 **두 검사를 동시에** 속여야 하는데, 봉인된 요율표가
    고정돼 있는 한 불가능합니다.

## 정직함 경계 — 무엇이 실측이고 무엇이 아닌가

!!! warning "측정된 것 · 아닌 것"
    - **측정됨(진짜):** 라우터가 고른 **모델**과 호출별 **토큰 usage** — 실험 09/아레나에서
      실제 키리스 Entra 호출로 청구된 값(`provenance = live`, `spend_source = provider-usage`).
    - **비용의 요율은 예시값(list price).** 토큰은 실측이지만, 요율은 공개 리스트 가격
      ([`foundry-5series.yaml`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/samples/pricing/foundry-5series.yaml))
      입니다 — 여러분 테넌트의 **실제 청구액이 아닙니다**(`cost_basis = list-price`). 실제
      요율 YAML을 봉인하면 그 값으로 재생됩니다.
    - **정확도는 미채점.** 그래더를 붙이지 않았으므로 각 답의 정오는 이 원장에 없습니다
      (실험 09와 동일 경계).
    - **오프라인 원장은 불변.** measured 행은 이 canonical 측정 원장에만 들어가고, 엄격한
      오프라인 원장(`measured = false`)에는 **결코** 새어 들어가지 않습니다.

## 실측 스냅샷 헤드라인 (이 원장이 봉인한 지출)

원장이 굳힌 아레나 스냅샷의 네 팔 총계(실측 usage × 리스트 요율):

| 팔 | 전략 | 총비용† | 평균 지연‡ |
| --- | --- | ---: | ---: |
| `cheapest` | 항상 가장 작은 티어 | `$0.001191` | 9.08 s |
| `premium` | 항상 프런티어 단일 호출 | `$0.015368` | 4.11 s |
| **`router`** | **단일 `model-router` 배포** | **`$0.020806`** | 12.18 s |
| `ensemble` | 3개 팬아웃 후 최선 | `$0.022046` | 8.33 s |

라우터가 실제로 태운 모델: **`gpt-5.4` × 3 · `grok-4-1-fast-reasoning` × 2**. †요율은 예시값,
토큰은 실측. ‡실측 wall-clock. (실험 08 렌즈·실험 09 실측과 동일 캡처.)

## 실험 09 ↔ 실험 10

| | 실험 09 (실측 라우팅) | 실험 10 (이 실험) |
| --- | --- | --- |
| 무엇을 증명 | 라우터가 **무엇을** 골랐나(모델·usage) | 그 측정 지출이 **변조 불가·재검증 가능**한가 |
| 산출물 | 라이브 스냅샷 JSON | **해시 체인 canonical 원장**(`.jsonl`) |
| 검증 | 응답 ID 지문(눈으로) | `measured-replay` — 사슬 + 비용 재생(기계로) |
| 재현 | 라이브 재실행(수치 변동) | **커밋된 원장은 오프라인 결정론 재검증**(`PASS` 고정) |
| 정직 라벨 | `measured = true` | `measured = true` — **엄격 오프라인 원장 불변** |

실험 09가 *"라우터가 진짜 무엇을 고르나"* 였다면, 실험 10은 *"그 실측 지출을 나중에 아무도
조용히 못 고치게, 그리고 누구나 스스로 확인하게"* 입니다.

## 재현 방법

```bash
# 1. 커밋된 실측 원장을 그 자리에서 재검증 — 오프라인·결정론, PASS 고정
cost-router ledger measured-replay --ledger samples/ledger/arena-measured.ledger.jsonl

# 2. 커밋된 원장을 캡처 아티팩트에서 재생성 — 바이트 단위로 동일(오프라인, 비용 0)
python scripts/build_measured_ledger_sample.py

# 3. 라이브로 아예 새 측정 원장을 만들기 — 실제 키리스 Entra 호출(비용 발생)
cost-router foundry arena --live --max-output-tokens 3000 \
  --pricing samples/pricing/foundry-5series.yaml \
  --ledger  runs-arena.ledger.jsonl
#   → flush 직후 자동 검증: "ledger: +5 measured row(s) … (hash-chain + cost-replay: OK)"
```

3번은 실험 09처럼 자격 증명·네트워크가 필요하며 토큰·비용은 호출마다 변동합니다. 1·2번은
아무 데서나 재현되는 **결정론적 감사**입니다 — 그게 이 실험의 핵심입니다.

---

**관련 문서:** [실험 09 · 실측 라우팅](09-live-routing-proof.md)(무엇을 골랐나) ·
[실험 08 · 아레나](08-arena.md)(오프라인 렌즈) ·
[라이브 실측 브릿지](../manual/foundry-live.md) ·
[Foundry 실전 구성](../manual/foundry-setup.md) · [개발 로그](devlog.md)
