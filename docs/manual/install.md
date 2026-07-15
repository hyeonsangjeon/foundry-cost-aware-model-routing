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

`cost-router hero`는 재현성 계약을 통과하지 못하면 **0이 아닌 종료 코드**로 실패합니다.
즉, "돌아가긴 하는데 숫자가 이상한" 상태를 조용히 넘어가지 않습니다.

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
