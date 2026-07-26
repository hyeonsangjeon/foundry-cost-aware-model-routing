# 측정 프로토콜 · Measurement Protocol

저장소의 실험 01–08은 **합성 텔레메트리에 대한 오프라인 투영**(`labels.measured = false`)입니다.
이 페이지가 규정하는 `cost-router measure` 러너(`src/router/measure.py`)는 그 투영을 **실측**으로
바꾸는 절차입니다 — 진짜 프롬프트를 실제 Azure 배포에 보내고, **실제로 청구된 토큰 usage**를
읽어 그 usage × 단가로 비용을 계산한 뒤, **지문이 찍힌 결정론적 스냅샷**으로 봉인합니다.

!!! danger "정직함 경계 — 일부러 엄격하게"
    - **`measured = true`는 방금 일어난 라이브 호출(`provenance = live`)에만 부여됩니다.**
      모킹·녹화·재생 경로는 `provenance = test|recorded`로 남아 `measured = false`입니다.
      커밋된 어떤 아티팩트도 `measured = true`를 사칭하지 않습니다.
    - **지출은 측정하되, 품질은 grader가 있을 때만 측정합니다.** grader가 없으면 커버리지는
      오프라인 신호 투영으로 떨어지고 그 사실이 summary에 라벨됩니다.
    - **라이브 모드는 로컬 전용입니다.** CI·자동화 파이프라인은 `measure replay`(자격 불필요)만
      실행합니다. 라이브 호출은 operator 승인 + 예산 상한 + prereg 게이트를 모두 통과해야 합니다.

---

## 1. 두 트랙 (D1) — 투영과 실측을 분리한다

| 트랙 | 라벨 | 출처 | 어디서 |
| --- | --- | --- | --- |
| **투영(projection)** | `measured = false` | 합성 신호 × illustrative 단가, 결정론 | 실험 01–08 |
| **실측(measured)** | `measured = true` | 실제 토큰 usage × 단가, 라이브 호출 | `measure --live` 스냅샷 |

핵심 콘텐츠는 두 트랙의 **격차 자체**입니다. 실측이 투영과 어긋나면 그것을 숨기지 않고
**prereg에 미리 적어 둔 격차 방향**과 나란히 게시합니다.

---

## 2. 명령 표면

```bash
# 1) dry-run 비용 추정표만 출력하고 종료(exit 2) — 라이브 호출 없음
cost-router measure run <experiment>

# 2) operator 승인 후에만: 실측 스윕 → §3 스냅샷
cost-router measure run <experiment> --live --budget-usd <cap> --yes

# 3) 자격 없이 스냅샷만으로 summary를 byte-동일하게 재계산(CI가 검사)
cost-router measure replay --run results/measured/<exp>/<run-id>

# 4) 실측 스냅샷을 범위/하한 계약에 대조(결정론)
cost-router measure verify --run results/measured/<exp>/<run-id> --contract <contract.yaml>
```

`measure run`은 `--live` 없이는 **항상 추정표만 출력하고 exit 2**로 끝납니다(`foundry arena`와
동일한 안전 기본값). 후보는 `--candidates` 또는 fleet의 ensemble 슬레이트에서, 단가는
`--pricing` > `FOUNDRY_PRICING_PATH` > 번들 기본값 순으로 해석합니다.

---

## 3. 스냅샷 규격 (§3)

라이브 런은 `results/measured/<exp>/<run-id>/` 아래 **5개 파일**을 씁니다.

```
manifest.json          # 실행 메타 + 모든 파일의 SHA-256 지문
prereg.md              # 라이브 런 "이전"에 커밋된 사전 예상 (§3.3)
traces.jsonl           # 원시 기록 1행 = 1 호출 시도
summary.json           # coverage·cost·savings·전략 분해·latency·429/재시도/캐시·실패 목록
pricing.snapshot.yaml  # 이 런에 쓰인 단가를 그대로 봉인
```

### 3.1 `manifest.json` 필드

`schema_version`, `run_id`, `exp_id`, `timestamp`, `runner_version`, `git_commit`,
`endpoint`(호스트만, 경로/키 마스킹), `region`, `deployments`, `candidates`(model/deployment/provider),
`n`, `budget_usd`, `partial`, `stopped_reason`, `measured_cost_usd`, `retry`(백오프 파라미터),
`pricing_path`, `pricing_version`, `prereg`(commit_hash/committed_at/bypassed/note),
`labels.measured`, `fingerprints`(파일별 `sha256:…`).

### 3.2 `traces.jsonl` 필수 필드 — 1행 = 1 호출 시도

`run_id, exp_id, task_id, repeat_idx(1..n), candidate_model, attempt_idx,`
`tokens:{input,cached,output,reasoning}, latency_ms, http_status, retries,`
`backoff_ms_total, cost_usd, pass|fail, score, fail_reason(nullable), labels:{measured}, ts`

429로 재시도되면 **시도마다 1행**을 남기고, 재시도가 소진되면 `fail_reason="throttle_exhausted"`,
정책상 재시도 자체는 `fail_reason="throttled_429"`로 표시합니다.

### 3.3 `prereg.md` 최소 내용 (D8)

예상 coverage / 예상 절감률(범위) · **projection 대비 격차의 예상 방향과 이유 한 줄** ·
이번 런에서 무엇이 나오면 "실패"인지 · 예산 상한.

---

## 4. 결정론과 지문

- **n = 3**(기본): 셀(task × candidate)마다 3회 반복해 분산을 보고합니다.
- **결정론적 재생(§3.4)**: `measure replay`가 `traces.jsonl` + `pricing.snapshot.yaml`만으로
  `summary.json`을 **byte-동일**하게 재계산합니다(자격 불필요). CI는 이 재생만 검사합니다.
- **지문**: 모든 스냅샷 파일의 정확한 바이트를 SHA-256으로 해시해 `manifest.fingerprints`에
  기록합니다. 재생 시 지문이 어긋나면 변조로 판정합니다.
- **직렬화**: JSON은 `indent=2, sort_keys=True, ensure_ascii=False` + 개행, traces는 한 줄에
  하나의 canonical(정렬된 키, 콤팩트) 레코드 — 두 경로가 같은 바이트를 만들도록 고정합니다.

---

## 5. 스로틀·캐시·과금

- **429 백오프**: 지수 백오프(기본 `max_retries=5`, `base_backoff_ms=500`, `backoff_factor=2`,
  상한 `max_backoff_ms=30000`). 파라미터는 manifest에 봉인되어 재생이 재시도 계상을 재현합니다.
- **캐시 토큰**: `tokens.cached`를 입력 토큰과 **분리 기록**하고 캐시 단가로 별도 과금합니다.
- **all-calls 과금 (D2)**: 팬아웃(앙상블) 전략은 **진 후보까지 전부 합산**해 과금합니다
  (`billing = sum-all-fanout`). "승자만 세는" 착시를 만들지 않습니다 — 이것이 앙상블 세금의
  실측 근거입니다.
- **예산 가드**: 누적 실측 비용이 `--budget-usd`에 도달하면 즉시 중단하고, 부분 결과를 정상
  스냅샷으로 저장한 뒤 `manifest.partial = true` · `stopped_reason`을 남깁니다. `--resume <run-id>`로
  끝난 셀을 건너뛰고 이어서 완주합니다.

---

## 6. 단가 출처와 freshness

- 단가는 **공개 모델·공개 단가**만 씁니다. 번들 `samples/pricing/foundry-ext-full.yaml`의
  OpenAI 계열은 공개 Azure list price를 따르고, 파트너 행은 계산을 투명히 하기 위한
  **round-number placeholder(견적 아님)** 입니다 — 실제 회계는 협상 요율을 드롭인하세요.
- 모든 게시 수치에는 **pricing snapshot 날짜**를 병기합니다. `measure verify`는 스냅샷이
  90일보다 오래되면 **비치명적 경고(freshness)**를 냅니다.

---

## 7. 예산 계획 (dry-run 기준)

아래는 5-태스크 prompt-bearing 워크로드(`samples/telemetry/curated-arena-live.sample.jsonl`)를
`--pricing samples/pricing/foundry-ext-full.yaml`(illustrative, 2025 snapshot), `--n 3`으로
**dry-run**한 planning 수치입니다. 캡은 output-token 편차를 흡수하도록 추정치 위에 헤드룸을 둡니다.

| 실험 | 측정 기반(후보×태스크×n) | dry-run 추정 | 권장 `--budget-usd` 캡 |
| --- | --- | --- | --- |
| exp02 Curated (pilot) | 11×5×3 = 165 calls | $1.03 | **$2** |
| exp07 Routing layer | `model-router` 1×5×3 = 15 | $0.21 | **$1** |
| exp03·04·06 Guardrails | 2–11 후보 ×5×3 | $0.22–$1.03 each | **$2 each** |
| exp05 Fan-out (D2) | 11×5×3 = 165 | $1.03 | **$3** |
| exp08 Arena | 11×5×3 = 165 | $1.03 | **$2** |
| exp01 Hero (100 tasks) | ⚠ 100-task prompt 워크로드 **선작성 필요** | ≈$20.6 | **$25** |

!!! warning "이 수치의 성격"
    dollar 값은 **illustrative** 단가(파트너 행 placeholder)에서 나온 planning 추정입니다.
    exp01/exp08을 전체 태스크 수로 실측하려면 그 규모의 prompt-bearing 워크로드를 먼저
    작성해야 합니다. 최종 예산 상한은 **operator가 승인 시 확정**합니다.

---

## 8. `measure verify` 계약 (7.2)

계약 YAML은 **정확값이 아니라 범위/하한**만 검사합니다(오프라인 `Expectation`과 같은 규약).
설정된 키만 채점됩니다.

| 키 | 의미 |
| --- | --- |
| `min_coverage` | 커버리지 하한 |
| `min_savings_pct` / `max_savings_pct` | naive 대비 절감률 대역 |
| `max_tax_ratio` | 팬아웃 세금(최고/최저 후보 비용비) 상한 |
| `min_escalation_gain` | observe-then-escalate가 회수하는 커버리지 하한 |
| `max_failure_rate` | 실패율 상한 |

---

## 9. 라이브 런 절차 (operator 게이트)

1. `cost-router foundry status`가 `credentialed: yes`(키리스 Entra)인지 확인.
2. `measure run <exp>`로 dry-run 추정표를 뽑아 **예산 상한**을 정한다.
3. `results/measured/<exp>/prereg.md`를 **런 시작 전에 커밋**한다(D8 게이트).
4. operator 승인 후 `measure run <exp> --live --budget-usd <cap> --yes` 실행.
5. `measure replay`로 byte-동일 재생, `measure verify`로 계약 대조 후 스냅샷을 커밋.

관련 문서: [라이브 실측 브릿지](foundry-live.md) · [감사 원장](ledger.md) ·
[실험 09 · 실측 라우팅](../lab-notebook/09-live-routing-proof.md) · [정직함 규약](../honesty.md)
