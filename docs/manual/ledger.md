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

## 왜 원장인가

라우팅의 헤드라인 가치는 "가장 싼 청구서"가 아니라 **모든 라우팅 결정에 대한 감사 추적과
함께** 같은 커버리지를 더 낮은 비용으로 얻는 것입니다. 원장은 그 감사 추적을 **재현 가능하게**
만듭니다 — 저장된 입력만으로 동일한 결정을 다시 만들어낼 수 있어야 검증을 통과합니다.
