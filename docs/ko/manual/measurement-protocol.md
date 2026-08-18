# 측정 프로토콜 · Measurement Protocol

저장소의 실험 01–08은 **합성 텔레메트리에 대한 오프라인 투영**(`labels.measured = false`)입니다.
이 페이지가 규정하는 `cost-router measure` 러너(`src/router/measure.py`)는 그 투영을 **실측**으로
바꾸는 절차입니다 — 진짜 프롬프트를 실제 Azure 배포에 보내고 **실제로 청구된 토큰 usage**를
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

# 2) 런 플랜을 해석해 plan_hash를 출력. 오프라인 — 아무것도 보내지 않음
cost-router benchmark plan --config .foundry.local.yaml

# 3) operator 승인 후에만: 실측 스윕 → §3 스냅샷
cost-router benchmark run --config .foundry.local.yaml --live --approve-plan sha256:<...>

# 4) 자격 없이 스냅샷만으로 summary를 byte-동일하게 재계산(CI가 검사)
cost-router measure replay --run <artifacts.local_root>/run/<run-id>

# 5) 실측 스냅샷을 범위/하한 계약에 대조(결정론)
cost-router measure verify --run <artifacts.local_root>/run/<run-id> --contract <contract.yaml>
```

`measure run`은 `--live` 없이는 **항상 추정표만 출력하고 exit 2**로 끝납니다(`foundry arena`와
동일한 안전 기본값). 후보는 `--candidates` 또는 fleet의 ensemble 슬레이트에서, 단가는
`--pricing` > `FOUNDRY_PRICING_PATH` > 번들 기본값 순으로 해석합니다.

`measure run --live`는 실측 경로가 **아닙니다**. 플랜을 해석하지 않으므로 디스패치 전에
거부하고 `benchmark run --live`를 안내합니다. 실측 경로는 `benchmark plan` → `--approve-plan`
→ `benchmark run --live`입니다(§9).

---

## 3. 스냅샷 규격 (§3)

라이브 런은 `<artifacts.local_root>/run/<run-id>/` 아래 **5개 파일**을 씁니다.

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

429로 재시도되면 **시도마다 1행**을 남기고 재시도가 소진되면 `fail_reason="throttle_exhausted"`,
정책상 재시도 자체는 `fail_reason="throttled_429"`로 표시합니다.

v2 유료 경로에서 **단가가 확인되지 않은 백엔드**로 라우팅된 셀은 금액을 지어내지 않고
`cost_usd=null` + `pricing.priced=false`(이유 포함)로 **fail-closed** 기록됩니다(§6.1).

### 3.3 `prereg.md` 최소 내용 (D8)

예상 coverage / 예상 절감률(범위) · **projection 대비 격차의 예상 방향과 이유 한 줄** ·
이번 런에서 무엇이 나오면 "실패"인지 · 예산 상한.

### 3.4 표본 크기와 증거 등급 (`evidence_tier`)

몇 개의 프롬프트를 돌려야 결과를 "결과"라고 부를 수 있는가 — 이 임계값은 우리가 정한 게
아니라 **Microsoft의 Model Router 평가 가이드**를 그대로 따릅니다.

> 워크로드 프롬프트 **100개 이상**이라야 통계적으로 신뢰할 만한 결과를 얻을 수 있고,
> **30개 미만**은 방향성(directional) 신호만 줍니다.
>
> — Microsoft Learn, *Evaluate model router for your workload*,
> <https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/model-router#evaluate-model-router-for-your-workload>
> (확인일 **2026-07-29**)

그래서 이 저장소는 워크로드마다 `evidence_tier`를 붙입니다:

| 워크로드 | 프롬프트 수 | `evidence_tier` | 근거 |
| --- | --- | --- | --- |
| `curated-24` | 24 | **`directional`** | 30 미만 — 방향성 신호만 |
| `hero-100-prompts` | 100 | 더 강한 등급의 **첫 후보** | 100 이상 권고를 충족 |

!!! note "인용 보존 규칙"
    위 URL과 **확인일(2026-07-29)** 은 이 임계값을 Microsoft에 귀속시키는 모든 자리에서
    함께 보존합니다. 원문이 나중에 바뀌더라도 **확인일은 그대로 두고** 이 저장소가 유지하는
    증거 정책과 현재 벤더 가이드를 구분해서 적습니다.

---

## 4. 결정론과 지문

- **n = 3**(기본): 한 셀은 (task × arm × 표본 n)이며, 각 (task × arm) 조합을 n=3회 반복 측정해
  분산을 보고합니다.
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
- **예산 가드**: 누적 실측 비용이 `--budget-usd`에 도달하면 즉시 중단하고 부분 결과를 정상
  스냅샷으로 저장한 뒤 `manifest.partial = true` · `stopped_reason`을 남깁니다. `--resume <run-id>`로
  끝난 셀을 건너뛰고 이어서 완주합니다.

---

## 6. 단가 출처와 freshness

- 단가는 **공개 모델·공개 단가**만 씁니다. 번들 `samples/pricing/foundry-ext-full.yaml`의
  OpenAI 계열은 공개 Azure list price를 따르고 파트너 행은 계산을 투명히 하기 위한
  **round-number placeholder(견적 아님)** 입니다 — 실제 회계는 협상 요율을 드롭인하세요.
- 모든 게시 수치에는 **pricing snapshot 날짜**를 병기합니다. `measure verify`는 스냅샷이
  90일보다 오래되면 **비치명적 경고(freshness)**를 냅니다.

### 6.1 요율 카드 스키마 — v1(오프라인 실험) vs v2(벤치/유료 측정)

이 저장소는 **두 요율 카드 스키마**를 의도적으로 공존시킵니다. 어떤 경로가 어느 것을
쓰는지는 고정돼 있습니다.

| 경로 | 스키마 | 과금 방식 | 미확인 백엔드 |
| --- | --- | --- | --- |
| 오프라인 실험 01–08 (`replay`·`evals`·`hero`·`compare`·`experiment`) | v1 `PricingTable` (`samples/pricing/*.yaml`) | 표당 단순 in/out 단가, 마크업 없음 | `default` 폴백으로 **fail-open** (합성 실험이라 무방) |
| 벤치/유료 측정 (`benchmark plan`·`benchmark run --live`·라이브 콕핏) | v2 `RateCardV2` (`schema_version: 2`, 예: `samples/pricing/foundry-ext-router.yaml`) | 정확한 alias map + Model Router **input-token 마크업**(라우터 arm) + 하위모델 in/out 합성 | rates에 없으면 **fail-closed**: `cost_usd=null`, `cost_complete=false`, 절감 주장에서 제외 |

- **스키마 판정**: 카드에 최상위 `schema_version` 키가 있으면 v2, 없으면 v1로 해석합니다.
  v1의 `version:`은 자유 리비전 정수라 `plan_hash`에 영향 없이 그대로 보존됩니다.
- **fail-closed의 이유**: v1 `default` 폴백을 유료 경로에 남기면 가격 미확인 백엔드(예:
  Azure Retail에 요율이 없는 Claude 5종)에 임의 단가가 붙어, 03Z에서 폐기한 "출처 없는
  절감 수치"가 되살아납니다. 그래서 벤치 경로는 **모르는 단가를 채우지 않고** 그 셀을
  unpriced로 봉인하고 그 런의 절감 주장을 `savings_claim_allowed=false`로 막습니다.
- **다섯 표면 동일 공식**: 같은 셀의 합성 비용이 dry-run 추정 · 예약 상한 · trace ·
  summary · replay에서 **동일**합니다. 회귀 테스트 `tests/test_rate_card_wiring.py`가
  이 동일성과 fail-closed(라우터 마크업 · Claude unpriced · v1 무변경)를 고정합니다.
- **tier 처리**: v2 카드는 키마다 **보수적 long-tier 단가 하나**만 저장하고 예약을 그
  값으로 잡습니다. 실제 tier가 판정되면 settle에서 반영하되, 판정 불가면 long을
  유지합니다(보수적 예약).
- 봉인된 스냅샷은 어느 엔진으로 과금했는지 함께 기록합니다(v2는 `pricing_engine:
  rate_card_v2` + 정규화된 카드). `measure replay`는 그 마커로 v1/v2 엔진을 되살려
  byte-동일 재계산을 보장합니다.

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
2. prereg를 작성해 **커밋한 뒤**, 그 `path`·`blob`·`commit`을 런 설정의
   `benchmark.preregistration`에 못박는다. D8 게이트는 커밋된 blob을 다시 읽어 대조하므로
   커밋 전이거나 커밋 뒤에 고친 파일은 디스패치 전에 거부된다. 못박는 순간 플랜이
   달라지므로 이 단계가 3번보다 **앞**이다.
3. `cost-router benchmark plan --config <파일>`로 플랜을 오프라인 해석한다. 아무것도 보내지
   않는다. 승인 요약의 계획 셀 수·전송 시도 범위·**최악 예약액**을 보고
   `benchmark.budget_usd`에 **예산 상한**을 정한다(`--budget-usd`로 덮어써도 된다).
4. operator 승인 후 출력된 `plan_hash`를 그대로 옮겨
   `cost-router benchmark run --config <파일> --live --approve-plan sha256:<...>` 실행.
   해시가 한 글자만 달라도 자격 조회 이전에 거부되므로 낡은 승인으로는 아무것도 나가지 않는다.
5. `measure replay --run <artifacts.local_root>/run/<run-id>`로 byte-동일 재생,
   `measure verify`로 계약 대조 후 스냅샷을 커밋.

`measure run --live`는 이 절차의 단계가 아니다. 플랜을 해석하지 않으므로 거부하고
`benchmark run --live`를 대신 안내한다. 플랜·승인 계약 전체는
[해석된 런 플랜](run-plan.md) 참고.

## 10. 라이브 진행률 지표는 진단용이다 (판정 아님)

detached 라이브 런은 `progress.json`과 stdout 한 줄로 진척을 노출한다. 셀
수·누적 비용·429·실패에 더해 **누적 grading coverage(게이트 기준선 표시)** 와
**arm별 pass 현황**을 함께 싣는다. 예:

```
progress: 142/288 cells  $1.83  429×0  fail×2  cov 96.5% [gate 90%]  [cell_done]
         cost 34/36 · balanced 34/35 · quality 33/36 · premium 36/36
```

목적은 오직 하나 — **조기 중단(abort) 판단**이다. 지난 void 런에서 quality
coverage가 79%로 무너지는 것을 30분 시점에 알았다면 abort할 수 있었다.

!!! danger "중간 지표로 실험을 바꾸면 prereg 위반"
    이 값들은 **진단용이지 판정이 아니다.** coverage 게이트(90%)와 품질 게이트
    (min_pass 0.60 / max_drop 10pp)는 **봉인된 스냅샷에 대해서만** `measure verify`
    로 판정한다. 중간 값을 보고 워크로드·arm·게이트·denominator를 바꾸면
    사전등록 위반이며 결과가 무효가 된다. 진행 중 허용되는 유일한 개입은
    **abort(전체 중단 + partial 스냅샷)** 뿐이다.

`progress.json`은 gitignored 런 디렉터리에만 쓰이고 지문 대상(§4)이 아니므로
스냅샷 바이트나 `plan_hash`에 영향을 주지 않는다 — replay는 여전히 byte-동일이다.

관련 문서: [라이브 실측 브릿지](foundry-live.md) · [감사 원장](ledger.md) ·
[실험 09 · 실측 라우팅](../lab-notebook/09-live-routing-proof.md) · [정직함 규약](../honesty.md)
