# 30초 설치

이 실험은 **오프라인·결정론적**입니다. 네트워크도, 자격 증명도, 외부 API 호출도 없습니다.
저장소에 포함된 합성 샘플만으로 모든 것이 동일하게 재현됩니다.

## 요구사항

- **Python 3.11 이상** (3.12 권장)
- `pip` (또는 [`uv`](https://docs.astral.sh/uv/) 등 동등한 도구)

## 설치

```bash
git clone https://github.com/hyeonsangjeon/foundry-cost-aware-model-routing
cd foundry-cost-aware-model-routing
pip install -e .
```

`pip install -e .`는 `cost-router` 콘솔 스크립트를 설치합니다. 개발 도구(ruff, pytest)까지
원하면:

```bash
pip install -e ".[dev]"     # 또는:  make dev
```

!!! tip "uv를 쓴다면"
    ```bash
    uv venv --python 3.12 .venv
    uv pip install --python .venv/bin/python -e ".[dev]"
    ```

## 바로 실행

```bash
cost-router hero            # 플래그십 실험 (합성 100건) — before/after 한 번에
cost-router experiment list # 사용 가능한 실험 목록
cost-router replay          # 큐레이션 샘플 재생
cost-router replay --synth  # 전체 워크로드를 결정론적 신호로 재생
```

설치 없이 `make`나 `python -m router`로도 동일하게 실행됩니다:

```bash
make replay        make replay-all
make evals         make evals-all
make check         make test
```

## 잘 설치됐는지 확인

```bash
cost-router --version
cost-router hero           # 마지막 줄에 reproducibility PASS가 보이면 정상
```

`cost-router hero`에는 **재현성 계약**이 걸려 있습니다 — 커버리지·절감률·태스크 수가 미리 정한
기준을 만족해야 통과입니다. 이 계약을 통과하지 못하면 **0이 아닌 종료 코드**로 실패합니다.
즉, "돌아가긴 하는데 숫자가 이상한" 상태를 조용히 넘어가지 않습니다.

## 얼마나 걸리나 — 지원 인터프리터 실측

아래는 **fresh clone → 설치 → 첫 결과**를 지원 인터프리터(**CPython 3.11 · 3.12**)에서
실제로 재본 값입니다. 이전에 인용하던 macOS/Python 3.14 관측치는 **지원 집합 밖**이라
더 이상 기준으로 쓰지 않습니다.

| 구간 | Python 3.11.15 | Python 3.12.13 | 성격 |
| --- | --- | --- | --- |
| `git clone --depth 1` | 1.17 s | 1.37 s | 텔레메트리 (네트워크 변동) |
| `venv` + `pip install -e .` (콜드 캐시) | 7.18 s | 4.83 s | 텔레메트리 |
| `venv` + `pip install -e .` (웜 캐시) | 6.59 s | 4.60 s | 텔레메트리 |
| **설치 후 `cost-router hero --json`** | **0.12 s** | **0.12 s** | **제품 약속 구간** |

- **설치 후 구간이 곧 제품 약속입니다** — 설치가 끝난 뒤 결과까지 **1초 미만**.
  네트워크에 의존하지 않아 결정론적입니다.
- clone·install은 공개 네트워크·러너 편차가 커서 별도 임계값을 두지 않고 **텔레메트리로만**
  기록합니다. 콜드/웜 모두 위 표에 있습니다.
- 설치 후 값은 3회 실행 중 최소·중앙값이 모두 0.12 s(첫 실행 0.18 s)였습니다.

!!! note "측정 환경 (metadata)"
    - **OS**: `Linux-3.10.102-x86_64-with-glibc2.35` (Ubuntu 22.04.5 LTS), `x86_64`, 8 vCPU
    - **인터프리터**: CPython **3.11.15**, **3.12.13** (uv 배포 빌드)
    - **캐시**: 콜드 = `pip install --no-cache-dir`, 웜 = 공유 pip 캐시 재사용
    - **네트워크**: GitHub에서 `--depth 1` 공개 클론 (Azure 호출 0)
    - **명령**: `cost-router hero --json` (오프라인 결정론 투영, `measured = false`)

!!! warning "이 숫자의 성격"
    위 초 단위 값은 지원 인터프리터 전반에서 반복 측정이 쌓이기 전까지의 **관측된 목표치**입니다.
    보장된 성능 지표(p95)도, 서비스 수준 약속(SLA)도 아닙니다. 또한 이 오프라인 경로를
    **"10분"** 으로 부르지 않습니다 — 10분은 자격 증명이 필요한 기존-Foundry 경로에만 해당합니다.

## 개발 검증 게이트 (선택)

```bash
make check     # 셸 문법 · 파이썬 컴파일 · 시크릿 스캔 · pytest · ruff
make test      # pytest
make lint      # ruff check .
```

## 다음 단계

- 왜 이렇게 라우팅하는지 → [핵심 개념](concept.md)
- 어떤 커맨드가 있는지 → [CLI 레퍼런스](cli.md)
- 나만의 실험 만들기 → [실험 설정(YAML)](experiments.md)
