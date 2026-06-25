"""``cost-router`` command-line entry point.

This is a thin stub for the initial scaffold.
"""

from __future__ import annotations

import argparse

from . import __version__


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="cost-router",
        description="Model-routing experiment CLI.",
    )
    parser.add_argument("--version", action="version", version=f"cost-router {__version__}")
    return parser


def main(argv: list[str] | None = None) -> int:
    build_parser().parse_args(argv)
    print(f"cost-router {__version__}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
