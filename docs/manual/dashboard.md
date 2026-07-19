# 대시보드

같은 라우팅 파이프라인을 표준 라이브러리(`http.server`)만으로 구현한 작은 오프라인 서비스로
띄울 수 있습니다. 웹 프레임워크도, 프로바이더 호출도, 네트워크 송신도 없습니다.

## 실행

```bash
cost-router serve                 # http://127.0.0.1:8000
# 또는 히어로 실행과 함께
cost-router hero --serve
```

브라우저에서 `http://127.0.0.1:8000`을 열면 대시보드가 뜹니다. 페이지는 외부 자산·폰트 없이
단일 인라인 HTML/CSS/JS이며, 오직 이 서비스의 JSON 엔드포인트로만 same-origin fetch를 합니다.

!!! success "설치 없이 바로 보기"
    이 대시보드는 GitHub Pages에 정적으로도 게시돼 있어, 클론·설치 없이 바로 열 수 있습니다.

    [:material-open-in-new: 라이브 데모 (자동 재생)](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1){ .md-button target=_blank }

## 무엇을 보여주나

- **정책 표** — 클래스별 순위가 매겨진 후보 모델과 사전값
- **before / after** — 나이브(모든 태스크에 프리미엄) 대 비용 인지 라우팅
- **비용 × 커버리지 프런티어** — all-mini / all-premium / cost-aware mix 세 전략을
  비용(가로)·커버리지(세로) 산점도로 표시. 라이브러리 없는 인라인 SVG이며, **비용 인지 mix만**
  좌상단 '둘 다 이기는(both-win)' 코너(완전 커버리지 + 낮은 비용)에 위치합니다. all-mini는
  커버리지 축 아래로 무너지고, all-premium은 같은 커버리지지만 오른쪽 끝(최대 비용)에 있습니다.
- **스포트라이트 카드** — 비용 인지 라우팅이 나이브 프리미엄 arm을 가장 크게 이긴 한 태스크를
  두 카드(라우팅 vs 나이브)와 배율로 강조 (예: `24.1×` 더 저렴)
- **아레나(문제 하나, 네 가지 방법)** — "5분 wow" 패널. 태스크 하나를 골라 **같은 문제**를
  네 가지로 보냅니다: 가장 싼 모델 · 프리미엄 모델 · 모두에게 팬아웃하는 앙상블 · 값싼 것부터
  올라가는 비용 인지 라우터. 각 카드가 **비용 · 지연 · 정확도** 세 축을 채우고, 축마다 승자를
  강조합니다. 기본 태스크(`t-0003`)에서는 라우터가 **가장 싸면서 정답도 맞히지만**(프리미엄·앙상블도
  정답) **지연은 가장 느립니다**(순차 에스컬레이션) — 공짜 점심은 없다는 정직한 트레이드오프.
  `/compare`(라이브) 또는
  `compare.json`(정적)에서 읽으며, 태스크 전환은 왕복 없이 클라이언트에서 처리됩니다. 자세한
  내용은 [문제 하나, 네 가지 방법](head-to-head.md) 참고.
- **커버리지 절벽(정책 A/B)** — 같은 워크로드에 시드 정책과 비싼 fallback을 지운
  `cost-cut` 후보를 나란히 비교. 후보는 더 싸 보이지만 커버리지가 **100% → 67%(−33%p)** 로
  무너집니다. 이는 replay와 독립적으로 `/regression`에서 가져오며, 데이터가 없으면 조용히
  숨겨집니다. 자세한 해석은 [실험 03 · 커버리지 절벽](../lab-notebook/03-coverage-cliff.md) 참고.
- **팬아웃 다이얼(임계값 스윕)** — 예산 게이트의 `compare_min_value`를 0→1.01까지 훑으며
  각 단계의 팬아웃 태스크 수·커버리지·절감·앙상블 세금을 보여줍니다. **커버리지(100%)와
  절감(47%)은 평평한 직선**이고 팬아웃 세금만 **3.74× → $0.0000**으로 무너지는 계단을
  그립니다 — 커버리지·절감을 잃지 않고 세금만 끄는 다이얼입니다. `/fanout-sweep`에서
  가져오며 데이터가 없으면 숨겨집니다. [실험 06 · 적응형 팬아웃 다이얼](../lab-notebook/06-fanout-dial.md) 참고.
- **Experiments(클릭하면 통계)** — 실험 탭을 누르면 그 실험의 비용·커버리지·**앙상블 팬아웃
  세금**·재현성 계약이 즉시 뜹니다. `GET /experiments`(라이브) 또는 `experiments.json`(정적
  export)에서 Azure Foundry 형태의 오프라인 메트릭을 읽습니다. 자세한 내용은
  [실험 05 · 앙상블 팬아웃 세금](../lab-notebook/05-ensemble-fanout.md) 참고.
- **Historical dashboard(히스토리컬)** — 기록된 실험 실행 이력 테이블. 라이브 서버에서 실험을
  실행할 때마다 한 줄씩 누적되고(`GET /metrics/history`), 정적 데모에서는 실험별 결정론 기준
  스냅샷을 보여줍니다.
- **비용 × 커버리지 프런티어** 에는 네 번째 점 `all-ensemble`(모든 태스크에서 모든 모델
  팬아웃)이 함께 찍혀, "그냥 다 돌리기"가 커버리지 100%지만 **가장 비싼** 프런티어 밖 코너에
  있음을 드러냅니다. 다섯 번째 점 `model_router`(**파란 점**)는 Azure AI Foundry Model Router
  형태의 **단일 호출** 라우팅 레이어 — 프롬프트마다 한 모델을 미리 고르고 에스컬레이션이 없어
  **낮은 커버리지**로 both-win 코너 밖 아래에 앉습니다. 자세한 해석은
  [실험 07 · 라우팅 레이어](../lab-notebook/07-model-router.md) 참고.
- **태스크별 라우팅 결정 애니메이션** — 클래스·선택 모델·이유·비용
- **집계** — 클래스별 비용, 모델 사용량, 모드/이유 통계

상단의 `full synthetic workload (100 tasks)` 토글을 켜면 전체 합성 워크로드가 재생되며,
before/after가 20초 안에 명확히 채워집니다. 스포트라이트 카드는 재생 요약의
`spotlight` 필드(자동 선택된 대표 태스크)에서 렌더링됩니다.

!!! tip "히어로 자동 실행"
    `cost-router hero --serve`가 안내하는 `http://127.0.0.1:8000/?run=1` 주소를 열면
    페이지 로드 즉시 재생이 시작됩니다. 쿼리 파라미터 `?run=1`(또는 `?autorun`)이 있으면
    정책 로딩 후 자동으로 replay가 실행됩니다.

!!! note "모든 숫자는 오프라인 투영"
    대시보드의 수치는 `make replay`/서비스와 **구성상 동일**하며(같은 파이프라인 호출),
    측정값이 아닙니다. 모델 이름은 일반 자리표시자입니다.

## 엔드포인트

| 메서드 | 경로 | 설명 |
| --- | --- | --- |
| GET | `/` · `/dashboard` | 대시보드 HTML |
| GET | `/healthz` | 라이브니스 프로브 |
| GET | `/policy` | 정책 버전과 클래스별 후보 |
| GET | `/replay?synth=true` | 워크로드 재생 결과(트레이스+요약) |
| GET | `/regression` | 정책 A/B 회귀(커버리지 절벽) 요약 |
| GET | `/fanout-sweep` | 팬아웃 임계값 스윕(적응형 팬아웃 다이얼) 요약 |
| GET | `/compare` · `/compare?task=<id>` | 아레나: 문제 하나에 네 가지 방법(비용·지연·정확도) |
| GET | `/experiments` | 모든 실험 카드 + Foundry 형태 오프라인 메트릭 |
| GET | `/experiment?name=<name>` | 실험 하나를 실행하고 히스토리에 기록(라이브 타임스탬프) |
| GET | `/metrics/history` | 히스토리컬 대시보드용 기록된 실행 이력 |
| POST | `/route` | 태스크 한 건 라우팅 |
| POST | `/batch-route` | 여러 태스크 라우팅 |

```bash
curl -s http://127.0.0.1:8000/healthz
curl -s "http://127.0.0.1:8000/replay?synth=true" | head -c 400
```

## 정적 사이트로 내보내기

라이브 서비스 대신 정적 호스팅용으로 페이로드를 미리 렌더링할 수 있습니다.

```bash
python scripts/build_static_site.py cost-router-dashboard
```

`/healthz`, `/policy`, `/replay`, `/regression`, `/fanout-sweep`, `/compare`, `/experiments`,
`/metrics/history` JSON을
평면 파일로 굽고, 동일한 대시보드 HTML/JS가 라이브 라우트 대신 그 파일들을 fetch하도록
엔드포인트 맵을 주입합니다. 주입되는 경로는 **상대경로**(`healthz.json` 등, 앞에 `/` 없음)라서
사이트 루트든, 프로젝트 Pages 하위 경로(`…/foundry-cost-aware-model-routing/demo/`)든 어디에
올려도 그대로 동작합니다. 결과는 결정론적이며 번들 합성 워크로드에서만 생성됩니다.

이 저장소의 `docs` 워크플로는 매뉴얼 사이트를 빌드한 뒤 이 스크립트로 대시보드를 `_site/demo/`에
구워 함께 배포합니다. 그래서 위의 [라이브 데모](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)가
항상 최신 라우팅 결과를 반영합니다.

## 컨테이너로 실행

```bash
make docker-build     # 이미지 빌드
make docker-run       # 포트 8000으로 서비스 실행
```
