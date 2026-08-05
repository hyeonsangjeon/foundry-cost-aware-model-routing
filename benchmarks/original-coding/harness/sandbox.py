"""Deterministic, network-free execution sandbox for the grading subprocess.

Activated at the very top of :mod:`harness.runner`, before any candidate code is
imported, so a submission can never reach the network or observe a nondeterministic
interpreter. Environment-level knobs (``PYTHONHASHSEED``, ``TZ``, ``LC_ALL``,
``LANG``) are set by the parent driver *before* the interpreter starts, because
they only take effect at startup; this module handles the rest at runtime.
"""

from __future__ import annotations

import random
import socket
import time


class NetworkBlocked(RuntimeError):
    """Raised when sandboxed code attempts any network access."""


def _blocked(*_args: object, **_kwargs: object) -> object:
    raise NetworkBlocked("network access is disabled in the benchmark sandbox")


def activate() -> None:
    """Freeze randomness/time and disable all outbound network primitives."""

    # Deterministic pseudo-randomness for any submission that seeds from default.
    random.seed(0)

    # Pin the timezone (parent also sets TZ=UTC in the environment).
    try:
        time.tzset()
    except AttributeError:  # pragma: no cover - non-Unix
        pass

    # Disable the socket layer wholesale. Blocking the constructors and the
    # common helpers covers urllib/http.client/smtplib/ftplib and friends, which
    # all funnel through these before any connection is attempted.
    socket.socket = _blocked  # type: ignore[assignment]
    socket.create_connection = _blocked  # type: ignore[assignment]
    for name in ("create_server", "getaddrinfo", "gethostbyname", "gethostbyname_ex"):
        if hasattr(socket, name):
            setattr(socket, name, _blocked)
