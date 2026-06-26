"""Baseline cost helpers for local eval summaries.

The implementation now lives in :mod:`router.baseline` so the installed CLI can
reuse it; this module re-exports it to keep the ``evals.baselines`` name stable.
"""

from __future__ import annotations

from router.baseline import baseline_cost_usd, baseline_model_for_task

__all__ = ["baseline_cost_usd", "baseline_model_for_task"]
