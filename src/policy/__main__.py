"""``python -m policy`` — show the seeded candidate models for each task class."""

from __future__ import annotations

from .ops import show_text


def main() -> int:
    print(show_text())
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
