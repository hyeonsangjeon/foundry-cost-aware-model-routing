"""Router package for model-routing experiments."""

from .baseline import baseline_cost_usd, baseline_model_for_task
from .budget import BudgetDecision, BudgetGate
from .classify import Classifier, RuleBasedClassifier, classify_task
from .offline import (
    load_signal_fixture,
    load_workload,
    route_task,
    route_tasks,
    summarize_traces,
    synthesize_signals,
    synthesize_task_signals,
)
from .pipeline import (
    ReplayReport,
    find_samples_root,
    format_eval_report,
    format_replay_json,
    format_replay_text,
    resolve_paths,
    run_evals,
    run_replay,
    run_route_once,
)
from .pricing import PricingTable, TokenRates
from .select import SelectionAttempt, SelectionResult, compare_select, ordered_select
from .trace import build_trace

__version__ = "0.1.0"

__all__ = [
    "BudgetDecision",
    "BudgetGate",
    "Classifier",
    "PricingTable",
    "ReplayReport",
    "RuleBasedClassifier",
    "SelectionAttempt",
    "SelectionResult",
    "TokenRates",
    "__version__",
    "baseline_cost_usd",
    "baseline_model_for_task",
    "build_trace",
    "classify_task",
    "compare_select",
    "find_samples_root",
    "format_eval_report",
    "format_replay_json",
    "format_replay_text",
    "load_signal_fixture",
    "load_workload",
    "ordered_select",
    "resolve_paths",
    "route_task",
    "route_tasks",
    "run_evals",
    "run_replay",
    "run_route_once",
    "summarize_traces",
    "synthesize_signals",
    "synthesize_task_signals",
]
