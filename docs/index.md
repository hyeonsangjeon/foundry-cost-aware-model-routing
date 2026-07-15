# Foundry 비용 인지 모델 라우팅

> 이 저장소가 담은 결정: **태스크마다 '그래도 통과하는 가장 싼 모델'로 보내고, 커버리지 이득이 비용을 넘어설 때만 상위 모델로 올리며, 그 결과를 증명한다.**

한국어 매뉴얼과 실험노트에 오신 것을 환영합니다. 이 사이트는 오프라인·결정론적으로 동작하는
비용 인지 라우팅 실험을 **설치하고, 돌리고, 눈으로 확인하고, 재현**하는 방법을 정리합니다.

!!! warning "정직함이 먼저입니다"
    이 저장소의 모든 숫자는 **합성 데이터에 대한 오프라인 투영**입니다
    (`labels.measured = false`). 측정된 절감이 아니며, 모델 이름은 모두 일반 자리표시자입니다.
    실제 절감은 여러분의 워크로드 구성과 요율에 따라 달라집니다.

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
  BEFORE  naive: premium model on every task   $2.226910
  AFTER   cost-aware routing                   $1.659167
  SAVED   $0.567743  (25.5% lower)  at 100.0% coverage

spotlight  t-0078 · validate · clean-first
  routed  mini-fast      $0.000293
  naive   deep-reasoner  $0.007059   (24.1x more)

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

## 무엇을 보게 되나요

<div class="grid cards" markdown>

-   :material-rocket-launch: **히어로 실행 모드**

    ---

    실험을 설정한 상태에서 한 커맨드로 before/after와 스포트라이트, 재현성
    자체 점검까지 한 번에. → [실험 01 · 히어로](lab-notebook/01-hero.md)

-   :material-scale-balance: **같은 커버리지, 더 낮은 비용**

    ---

    가장 싼 arm은 22% 커버리지로 무너지고, 프리미엄 arm은 100%지만 최대 비용.
    라우팅은 **100% 커버리지를 지키며** 비용을 낮춥니다. → [핵심 개념](manual/concept.md)

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
