# Foundry 비용 인지 모델 라우팅

> 이 저장소가 담은 결정: **태스크마다 '그래도 통과하는 가장 싼 모델'로 보내고, 통과율 이득이 비용을 넘어설 때만 상위 모델로 올리며, 그 결과를 증명한다.**

한국어 매뉴얼과 실험노트에 오신 것을 환영합니다. 여기 담긴 실험은 오프라인·결정론적입니다 —
네트워크나 외부 호출 없이, 언제 돌려도 같은 결과가 나옵니다. 이 사이트는 그 실험을
**설치하고, 돌리고, 눈으로 확인하고, 재현**하는 방법을 정리합니다.

!!! success "실측 결과 (measured=true · directional)"
    실제 Azure Foundry 실측에서 `router-cost` arm이 `direct-premium` 대비
    **95.2% 저렴**했고, 통과율 격차는 **4.17%p** 이내였습니다 — 24과제·단일 테넌트·1회의
    방향성(publishable) 결과입니다.
    → [라우팅 모드 실측 결과 대시보드](manual/03d-results.md)

이 결과가 어디서 나오는지 — 이 저장소가 어떤 층인지부터 보겠습니다.

!!! abstract "내장 Model Router 위에 얹히는 층 — 차별점 넷"
    **모델 선택**은 Azure AI Foundry **내장 Model Router**가 이미 잘 합니다(배포 하나·크로스
    프로바이더). 이 저장소는 그것을 **대체하지 않고 그 위에 얹힙니다** — ① 실행 신호로 **검증**하고
    실패만 에스컬레이션 · ② **앙상블 세금**을 계량 · ③ **비용 거버너**로 지출을 게이트 · ④ 모든
    결정을 **감사 원장**에 봉인. *선택은 내장이, 검증·거버넌스·감사는 이 저장소가.*

이 대비를 한 화면에 담은 센터피스가 [실험 07 · 라우팅 레이어](lab-notebook/07-model-router.md)
입니다. 여기서 **통과율(pass rate)** 은 **끝까지 통과(해결)한 태스크의 비율**입니다 — 오프라인
CLI·실험 계약은 이 값을 `coverage`로 출력하며, 이는 측정 결과에서 따로 보고하는 **채점
커버리지**(채점된 셀 비율)와는 다른 지표입니다([용어집](manual/glossary.md)). 합성 데이터 위의
일반 **`single-call`** arm은 통과율 **52%**에 그치고, 관찰-후-에스컬레이션은 **100%**를
채웁니다 (`measured = false` 투영).

단, 위 숫자들을 정확히 읽으려면 두 가지 트랙과 그 한계를 구분해야 합니다.

!!! warning "정직함이 먼저입니다 — 두 트랙"
    이 저장소는 두 종류의 숫자를 **라벨로 구분**합니다. 여기서 `measured`는 그 숫자가 실제
    모델 호출로 측정된 값인지, 아니면 오프라인 계산에 그친 값인지를 나타내는 라벨입니다.
    **투영 트랙(실험 01–08)** 은 합성 데이터에 대한 오프라인 투영이라
    (`labels.measured = false`), 모델 이름도 모두 일반 자리표시자입니다.
    **실측 트랙(실험 09·10·12)** 은 실제 Azure Foundry 호출로 측정되고
    (`measured = true`) 실제 배포명을 씁니다. 다만 `evidence_tier = directional` —
    24과제·단일 테넌트·1회 측정이라, 통계적 신뢰가 아니라 **방향성 신호**입니다.
    각 페이지의 라벨을 확인하세요 — 실제 절감은 여러분의 워크로드 구성과 요율에 따라 달라집니다.

## 30초 안에 확인하기

```bash
git clone https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing
cd foundry-cost-aware-model-routing
pip install -e .          # cost-router 콘솔 스크립트 설치
cost-router hero          # 플래그십 실험을 한 번에 실행
```

`cost-router hero`가 출력하는 before/after 블록(합성 워크로드 100건):

```text
before / after  (offline projection over synthetic data; labels.measured=false)
  BEFORE  naive: premium model on every task   $2.23
  AFTER   cost-aware routing                   $1.66
  SAVED   $0.57  (25.5% lower)  at 100.0% coverage

spotlight  t-0078 · validate · clean-first
  routed  mini-fast      $0.0003
  naive   deep-reasoner  $0.0071   (24.1x more)

reproducibility  PASS
  PASS  coverage: 100.0% ≥ 100.0%
  PASS  savings: 25.5% ≥ 20.0%
  PASS  tasks: 100 ≥ 100
```

대시보드로 라이브 관찰까지 한 번에:

```bash
cost-router hero --serve   # 실행 후 오프라인 대시보드를 띄웁니다
# 브라우저에서 http://127.0.0.1:8000/?run=1 열기 → 로드 즉시 자동 재생
```

!!! success "설치 없이 바로 체험 · 인터랙티브 오프라인 데모"
    클론하기 전에 결과부터 눈으로 보고 싶다면, 브라우저에서 바로 열 수 있는
    **인터랙티브 오프라인 데모**가 준비돼 있습니다. 열자마자 합성 워크로드 100건의
    before/after와 스포트라이트가 자동 재생됩니다.

    [:material-rocket-launch: 인터랙티브 오프라인 데모 열기 (자동 재생)](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1){ .md-button .md-button--primary target=_blank }

    이 데모는 GitHub Pages에 미리 렌더링된 정적 파일입니다 — 서버도, 네트워크
    호출도, 비밀값도 없고 **과금되는 라이브 대시보드가 아닙니다**. 숫자는
    `cost-router hero`와 동일하게 생성됩니다.

## 목업이 아니라 당신의 Azure로 — 브라우저 콕핏

위 오프라인 데모는 **이미 측정해 커밋해 둔 결과의 목업**(읽기 전용)입니다. 같은 화면을
**당신의 Foundry 배포로 실시간**으로 돌리려면 로컬 콕핏을 씁니다 — 브라우저에 자격증명은
한 번도 들어가지 않습니다(`127.0.0.1` 전용 + 세션 토큰, Entra는 `az login`에서 읽음).

!!! note "콕핏은 최신 측정 배선을 반영하는 작업이 진행 중입니다 (이슈 #55)"
    콕핏 실행 경로는 아직 최신 측정 배선(03B-2 v2 요율 · 03D-1 채점 브리지)을 받지 못했습니다
    — 예를 들어 라이브 클라이언트가 `max_output_tokens`를 주입하지 않아 기본값 512를 씁니다.
    지금 **정확한 실측은 CLI 경로**를 사용하세요. 배선 상세는
    [이슈 #55](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/issues/55),
    측정 방법은 [측정 프로토콜](manual/measurement-protocol.md)을 보세요.

```bash
az login                      # 키리스 Entra — 브라우저에 입력란 없음
cost-router dashboard --live  # 127.0.0.1 + 임의 포트 + 세션 토큰 URL 출력
```

연결 확인 → 나갈 프롬프트·dry-run 비용 → **승인하고 실행**(사람 게이트) → 실시간 진행 →
`results/measured/<exp>/<run-id>` 스냅샷 재생까지, 목업과 **똑같은 UI**로. 처음부터 끝까지의
설정은 [Foundry 실전 구성](manual/foundry-setup.md) → [커스터마이징·콕핏](manual/customize.md) →
[감사 원장](manual/ledger.md) 순서를 그대로 따라가면 됩니다.

## 무엇을 보게 되나요

<div class="grid cards" markdown>

-   :material-check-decagram: **실측 결과 · router-cost 95.2% 절감**

    ---

    실제 Azure Foundry 실측(`measured=true` · directional): `router-cost`가
    `direct-premium` 대비 **95.2% 저렴**, 통과율 격차 4.17%p 이내.
    → [라우팅 모드 실측 결과](manual/03d-results.md)

-   :material-rocket-launch: **히어로 실행 모드**

    ---

    실험을 설정한 상태에서 한 커맨드로 before/after와 스포트라이트, 재현성
    자체 점검까지 한 번에. → [실험 01 · 히어로](lab-notebook/01-hero.md)

-   :material-scale-balance: **같은 통과율, 더 낮은 비용**

    ---

    가장 싼 arm은 22% 통과율로 무너지고, 프리미엄 arm은 100%지만 최대 비용.
    라우팅은 **100% 통과율을 지키며** 비용을 낮춥니다. → [핵심 개념](manual/concept.md)

-   :material-file-document-check: **재현 가능한 감사 원장**

    ---

    모든 라우팅 결정을 해시 체인 JSONL에 기록하고, 저장된 입력을 다시 돌려
    바이트 단위로 검증합니다. → [감사 원장](manual/ledger.md)

-   :material-flask: **실험노트**

    ---

    방법론, 정직 라벨, 실제 수치를 기록한 랩 노트. → [실험노트 소개](lab-notebook/index.md)

</div>

## 다음 단계

- 처음이라면 → [30초 설치](manual/install.md)
- 왜 이렇게 라우팅하는지 → [핵심 개념](manual/concept.md)
- 나만의 실험을 만들고 싶다면 → [실험 설정(YAML)](manual/experiments.md)
- 이 프로젝트의 주장 경계 → [정직함 규약](honesty.md)
