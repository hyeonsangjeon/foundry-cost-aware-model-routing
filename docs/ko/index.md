# Foundry 비용 인지 모델 라우팅

> 이 저장소가 담은 결정: **태스크마다 '그래도 통과하는 가장 싼 모델'로 보내고, 통과율 이득이 비용을 넘어설 때만 상위 모델로 올리며, 그 결과를 증명한다.**

이 페이지는 프로젝트 설치, 실험 실행, 결과 확인, 재현 방법을 정리합니다. 포함된 실험은
오프라인·결정론적으로 실행됩니다. 네트워크나 외부 호출이 없고, 같은 입력이면 같은 결과가
나옵니다.

!!! success "실측 결과 (measured=true · directional)"
    실제 Azure Foundry 실측에서 `router-cost`(Model Router의 Cost 모드)의 비용은
    `direct-premium`(프리미엄 모델 직접 호출 · `gpt-5.6-sol`)보다 **95.2% 낮았습니다**.
    통과율 차이는 **4.17%p** 이내였습니다. 이 결과는 24과제·단일 테넌트·1회 측정에서
    나왔으므로 방향성(publishable) 결과이지 통계적 신뢰가 아닙니다.
    → [라우팅 모드 실측 결과 대시보드](manual/03d-results.md)

결과를 비교하기 전에 Foundry가 이미 하는 일과 이 저장소가 더하는 일을 나눠 보겠습니다.

!!! abstract "내장 Model Router 위에 얹히는 층 — 차별점 넷"
    Azure AI Foundry **내장 Model Router**는 배포 하나로 크로스 프로바이더 **모델 선택**을
    처리합니다. 이 저장소는 그것을 **대체하지 않습니다**. 실행 과정에 네 가지 통제를 더합니다.
    ① 답을 실행 신호로 확인하고 실패한 경우에만 상위 모델을 시도합니다(**검증**) · ② 여러 모델을
    함께 부른 추가 비용을 합산합니다(**앙상블 세금**) · ③ 승인한 지출 한도에서 멈춥니다(**비용
    거버너**) · ④ 나중에 다시 확인할 수 있도록 모든 결정을 기록합니다(**감사 원장**). *내장
    라우터는 모델을 고르고, 이 저장소는 결과를 확인하고 지출을 통제하고 실행 기록을 남깁니다.*

[실험 07 · 라우팅 레이어](lab-notebook/07-model-router.md)는 모델을 한 번만 고르는 방식과
실패한 뒤 다시 시도할 수 있는 방식을 비교합니다. 합성 데이터에서 일반 **`single-call`** arm은
한 번 고르고 멈춰 **통과율(pass rate) 52%**를 냅니다. 관찰-후-에스컬레이션은 첫 결과를
확인하고 실패한 경우에만 상위 모델로 옮겨 **100%**에 도달합니다. 두 숫자 모두
`measured = false` 투영입니다.

여기서 **통과율(pass rate)** 은 **끝까지 통과(해결)한 태스크의 비율**입니다. 오프라인 CLI·실험
계약은 이 필드를 `coverage`로 부릅니다. 실측 결과에는 답이 도착해 실제로 채점할 수 있었던 셀의
비율인 **채점 커버리지**도 따로 나옵니다. 둘은 다른 지표입니다
([용어집](manual/glossary.md)).

아래 두 트랙은 숫자가 오프라인 계산에서 나왔는지 실제 호출에서 나왔는지를 구분합니다.

!!! warning "정직함이 먼저입니다 — 두 트랙"
    모든 결과는 두 트랙 중 하나에 속합니다. `measured` 라벨은 숫자가 실제 모델 호출에서
    나왔는지, 오프라인 계산에서 나왔는지를 알려 줍니다.

    **투영 트랙(실험 01–08)** 은 합성 데이터로 계산합니다(`labels.measured = false`). 실제 모델을
    부르지 않으며 모델 이름도 일반 자리표시자입니다. 이 숫자는 측정된 절감이 아닙니다.

    **실측 트랙(실험 09·10·11·12)** 은 실제 Azure Foundry 호출(`measured = true`)과 실제
    배포명을 씁니다. 그래도 근거 수준은 `evidence_tier = directional`입니다.
    24과제·단일 테넌트·1회 측정에서 나온 **방향성 신호**이지 통계적 신뢰가 아닙니다. 실험 11은
    사전등록 기준을 넘지 못해 **무효(VOID)**입니다. 측정 자체는 남지만 계획한 비교의 근거로는
    쓸 수 없습니다. 각 페이지의 라벨을 확인하세요. 실제 절감은 여러분의 워크로드 구성과 요율에
    따라 달라집니다.

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
    클론하기 전에 결과를 보려면 브라우저에서 **인터랙티브 오프라인 데모**를 여세요.
    합성 워크로드 100건의 before/after와 스포트라이트가 자동으로 재생됩니다.

    [:material-rocket-launch: 인터랙티브 오프라인 데모 열기 (자동 재생)](https://hyeonsangjeon.github.io/foundry-cost-aware-model-routing/demo/?run=1){ .md-button .md-button--primary target=_blank }

    이 데모는 GitHub Pages에 미리 렌더링된 정적 파일입니다 — 서버도, 네트워크
    호출도, 비밀값도 없고 **과금되는 라이브 대시보드가 아닙니다**. 숫자는
    `cost-router hero`와 동일하게 생성됩니다.

## 목업이 아니라 당신의 Azure로 — 브라우저 콕핏

위 오프라인 데모는 읽기 전용이며 이미 측정해 커밋한 결과를 보여 줍니다. 로컬 콕핏은 같은
화면을 **당신의 Foundry 배포로 실시간** 실행합니다. 브라우저에는 자격증명이 들어가지 않습니다.
`127.0.0.1`과 세션 토큰만 쓰고 Entra 로그인은 `az login`에서 읽습니다.

!!! note "콕핏은 최신 측정 배선을 반영하는 작업이 진행 중입니다 (이슈 #55)"
    콕핏 실행 경로에는 아직 최신 측정 배선(03B-2 v2 요율 · 03D-1 채점 브리지)이 없습니다.
    예를 들어 라이브 클라이언트는 `max_output_tokens`를 설정하지 않아 기본값 512를 씁니다.
    지금 **정확한 실측은 CLI 경로**를 사용하세요. 배선 상세는
    [이슈 #55](https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing/issues/55),
    측정 방법은 [측정 프로토콜](manual/measurement-protocol.md)을 보세요.

```bash
az login                      # 키리스 Entra — 브라우저에 입력란 없음
cost-router dashboard --live  # 127.0.0.1 + 임의 포트 + 세션 토큰 URL 출력
```

같은 UI에서 먼저 연결을 확인하고 나갈 프롬프트와 dry-run 비용을 보여 줍니다. 사람이
**승인하고 실행**(사람 게이트)을 선택하기 전에는 실행하지 않습니다. 그다음 실시간 진행 상황을
보여 주고 `results/measured/<exp>/<run-id>` 스냅샷을 재생합니다. 전체 설정은
[Foundry 실전 구성](manual/foundry-setup.md) → [커스터마이징·콕핏](manual/customize.md) →
[감사 원장](manual/ledger.md) 순서로 진행하면 됩니다.

## 무엇을 보게 되나요

<div class="grid cards" markdown>

-   :material-check-decagram: **실측 결과 · router-cost 95.2% 절감**

    ---

    실제 Azure Foundry 실측(`measured=true` · directional)에서 `router-cost`의 비용은
    `direct-premium`보다 **95.2% 낮았습니다**. 통과율 차이는 4.17%p 이내였습니다.
    → [라우팅 모드 실측 결과](manual/03d-results.md)

-   :material-rocket-launch: **히어로 실행 모드**

    ---

    한 커맨드가 before/after 결과, 스포트라이트 태스크, 재현성 자체 점검을 출력합니다.
    → [실험 01 · 히어로](lab-notebook/01-hero.md)

-   :material-scale-balance: **같은 통과율, 더 낮은 비용**

    ---

    항상 가장 싼 모델만 고르면 태스크의 22%만 풉니다. 항상 프리미엄 모델을 고르면 100%를
    풀지만 비용이 가장 큽니다. 라우팅은 싼 모델부터 시작해 실패하면 상위 모델로 옮기므로
    **100% 통과율을 지키며** 비용을 낮춥니다. → [핵심 개념](manual/concept.md)

-   :material-file-document-check: **재현 가능한 감사 원장**

    ---

    모든 라우팅 결정을 해시 체인 JSONL에 기록합니다. 저장된 입력을 다시 돌렸을 때 결과가
    바이트 단위로 같아야 합니다. → [감사 원장](manual/ledger.md)

-   :material-flask: **실험노트**

    ---

    실험노트에는 각 실험을 어떻게 돌렸는지, 어떤 정직 라벨이 붙는지, 어떤 숫자가 나왔는지를
    기록합니다. → [실험노트 소개](lab-notebook/index.md)

</div>

## 다음 단계

- 처음이라면 → [30초 설치](manual/install.md)
- 왜 이렇게 라우팅하는지 → [핵심 개념](manual/concept.md)
- 나만의 실험을 만들고 싶다면 → [실험 설정(YAML)](manual/experiments.md)
- 이 프로젝트의 주장 경계 → [정직함 규약](honesty.md)
