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
- **스포트라이트 카드** — 비용 인지 라우팅이 나이브 프리미엄 arm을 가장 크게 이긴 한 태스크를
  두 카드(라우팅 vs 나이브)와 배율로 강조 (예: `24.1×` 더 저렴)
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

`/healthz`, `/policy`, `/replay` JSON을 평면 파일로 굽고, 동일한 대시보드 HTML/JS가 라이브
라우트 대신 그 파일들을 fetch하도록 엔드포인트 맵을 주입합니다. 주입되는 경로는 **상대경로**
(`healthz.json` 등, 앞에 `/` 없음)라서 사이트 루트든, 프로젝트 Pages 하위 경로
(`…/foundry-cost-aware-model-routing/demo/`)든 어디에 올려도 그대로 동작합니다. 결과는
결정론적이며 번들 합성 워크로드에서만 생성됩니다.

이 저장소의 `docs` 워크플로는 매뉴얼 사이트를 빌드한 뒤 이 스크립트로 대시보드를 `_site/demo/`에
구워 함께 배포합니다. 그래서 위의 [라이브 데모](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)가
항상 최신 라우팅 결과를 반영합니다.

## 컨테이너로 실행

```bash
make docker-build     # 이미지 빌드
make docker-run       # 포트 8000으로 서비스 실행
```
