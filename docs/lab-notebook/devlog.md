# 개발 로그 · 실험일지

!!! abstract "이 문서는 무엇인가"
    실험(01·02·03)이 *"무엇을 검증했는가"*를 담는다면, 이 개발 로그는
    *"언제 · 어떤 상황에서 · 무슨 작업을 했는가"*를 시간순으로 남깁니다.
    각 항목은 **상황(왜) · 작업(무엇을) · 검증(효과)** 세 줄로 정리하며,
    수치가 등장하면 저장소 규약대로 항상 `measured = false`입니다.

    최신 항목이 맨 위입니다.

---

## 2026-07-15 · ③ CI를 Node 24로 (위생 작업)

!!! note "한 줄 요약"
    GitHub Actions가 Node20 액션에 **지원 종료(deprecation)** 경고를 내기 시작 —
    워크플로 액션을 모두 **Node 24 런타임** 버전으로 올렸습니다. 실험 코드·수치·재현성에는
    영향이 없는 순수 인프라 위생 작업입니다.

- **상황(왜):** 러너가 Node20 기반 액션에 대해 곧 강제로 Node24로 대체하며 경고를 표시.
  경고를 방치하면 로그가 지저분해지고, 장기적으로 빌드가 깨질 위험이 있습니다.
- **작업(무엇을):** `.github/workflows/ci.yml`·`docs.yml`의 액션을 node24 런타임 릴리스로 범프.
    - `actions/checkout` `v4 → v5`
    - `actions/setup-python` `v5 → v6`
    - `actions/upload-pages-artifact` `v3 → v5`
    - `actions/deploy-pages` `v4 → v5`
- **검증(효과):** 입력 계약(예: `upload-pages-artifact`의 `path`, `_site` 아티팩트)이 그대로라
  동작 변화 없음. PR CI가 `checkout`·`setup-python`을, 병합 후 Pages 배포가 나머지 두 액션을
  실제로 검증합니다. 실험의 어떤 수치도 바뀌지 않습니다.

---

## 2026-07-15 · ② 비용 × 커버리지 프런티어 차트 ([PR #8](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/pull/8))

!!! note "한 줄 요약"
    대시보드에 **비용(x) × 커버리지(y) 2D 산점도**를 추가 — 세 전략 중 **mix만** 좌상단
    "both-win"(싸고 넓은) 코너에 도달하는 것을 한눈에 보여줍니다. 라이브러리 없이 인라인 SVG.

- **상황(왜):** 대시보드에는 이미 세 전략(`all-mini` · `all-premium` · `mix`)의 비용 막대와
  커버리지 알약이 있었지만, *"왜 mix만 좋은 트레이드오프인가"*가 숫자로만 흩어져 있어
  한눈에 들어오지 않았습니다.
- **작업(무엇을):** 같은 `summary["strategies"]` 데이터를 비용(가로) × 커버리지(세로)
  평면에 점으로 찍는 **프런티어 산점도**를 추가. `all-mini`는 좌하단(싸지만 좁음),
  `all-premium`은 우상단(넓지만 비쌈), `mix`만 좌상단 green "both-win" 존에 위치.
  순수 인라인 SVG로 그려 외부 의존성이 없습니다.
- **검증(효과):** node 프로브로 세 점의 좌표(NaN 없음, mix가 premium보다 왼쪽)를 확인하고
  `tests/test_server.py`에 회귀 테스트를 추가. 정적 내보내기(`/demo/`)에도 자동 포함됩니다.
  모든 좌표의 바탕 수치는 `measured = false`.

[라이브 데모에서 프런티어 보기 →](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1)
