# CLI 레퍼런스

모든 서브커맨드는 [`router.pipeline`](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/blob/main/src/router/pipeline.py)의
동일한 오케스트레이션을 감싸는 얇은 래퍼입니다. 그래서 CLI, 샘플 스크립트, eval이 정확히
같은 경로를 탑니다.

```bash
cost-router --help
cost-router --version
```

## 공통 데이터 플래그

`replay` · `route-once` · `evals` · `policy simulate/regression`에서 공통으로 쓰입니다.

| 플래그 | 의미 | 기본값 |
| --- | --- | --- |
| `--workload PATH` | 워크로드 JSONL | 번들 샘플 |
| `--signals PATH` | 오프라인 신호 JSON | 번들 샘플 |
| `--pricing PATH` | 가격표 YAML | 번들 예시 가격 |
| `--synth` | 모든 태스크의 신호를 결정론적으로 합성 | 꺼짐 |
| `--policy PATH` | 정책 YAML | 시드 정책 |

정책 우선순위: `--policy` > 환경변수 `COST_ROUTER_POLICY` > 번들 시드.

## hero — 히어로 실행 모드

플래그십 실험(`experiments/hero.yaml`)을 한 번에 실행하고 before/after · 스포트라이트 ·
재현성 자체 점검을 출력합니다. 계약을 통과하지 못하면 **0이 아닌 코드**로 종료합니다.

```bash
cost-router hero               # 텍스트 요약
cost-router hero --json        # 기계가 읽는 JSON
cost-router hero --ledger reports/hero.jsonl   # 감사 원장에 결정 기록
cost-router hero --serve       # 실행 후 대시보드 부팅 (http://127.0.0.1:8000)
cost-router hero --serve --host 0.0.0.0 --port 9000
```

## experiment — 명명된 실험

```bash
cost-router experiment list                # 사용 가능한 실험 목록
cost-router experiment run curated         # 이름으로 실행
cost-router experiment run hero --json
cost-router experiment run ./path/to/my.yaml   # 파일 경로로도 실행
cost-router experiment run curated --ledger reports/curated.jsonl
```

실험 YAML 스키마는 [실험 설정(YAML)](experiments.md)을 참고하세요.

## replay — 워크로드 재생

```bash
cost-router replay                 # 큐레이션 샘플 픽스처
cost-router replay --synth         # 전체 워크로드를 결정론적 신호로
cost-router replay --json          # 트레이스를 JSON으로
cost-router replay --synth --ledger reports/routing.jsonl
```

마지막에 나이브 대 라우팅 before/after 블록이 붙습니다.

## route-once — 단일 트레이스

```bash
cost-router route-once --task-id t-0003 --synth
cost-router route-once --task-id t-0001 --ledger reports/one.jsonl
```

한 태스크의 후보·시도·선택·비용을 담은 트레이스를 JSON으로 출력합니다.

## evals — 비용 대 baseline 요약

```bash
cost-router evals --synth
```

라우팅 비용 대 '항상 가장 비싼' baseline의 커버리지/비용 요약을 냅니다.

## serve — 오프라인 HTTP 서비스

```bash
cost-router serve                       # http://127.0.0.1:8000
cost-router serve --host 0.0.0.0 --port 9000 --policy src/policy/seed_policy.yaml
```

표준 라이브러리만으로 동작하는 오프라인 서비스입니다. 자세한 내용은
[대시보드](dashboard.md)를 참고하세요.

## policy — 정책 검사/검증/비교

```bash
cost-router policy show
cost-router policy validate --policy src/policy/seed_policy.yaml
cost-router policy diff --candidate samples/policy/candidate.example.yaml
cost-router policy simulate --policy samples/policy/candidate.example.yaml --synth
cost-router policy regression --candidate samples/policy/candidate.example.yaml --synth
```

`regression`은 기저 정책 대 후보 정책의 비용/커버리지 변화를 결정론적으로 비교합니다.

## ledger — 감사 원장 재생/검증

```bash
cost-router ledger replay --ledger reports/routing.jsonl
```

저장된 결정을 다시 돌려 정규 최종 페이로드를 바이트 단위로 검증합니다. 자세한 내용은
[감사 원장](ledger.md)을 참고하세요.
