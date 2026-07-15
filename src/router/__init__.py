"""Router package for model-routing experiments."""

from .baseline import (
    baseline_cost_usd,
    baseline_model_for_task,
    single_call_baseline_arms,
)
from .budget import BudgetDecision, BudgetGate
from .classify import Classifier, RuleBasedClassifier, classify_task
from .experiment import (
    Experiment,
    ExperimentResult,
    Spotlight,
    list_experiments,
    load_experiment,
    run_experiment,
)
from .offline import (
    load_signal_fixture,
    load_workload,
    route_task,
    route_tasks,
    summarize_traces,
    synthesize_shared_signals,
    synthesize_signals,
    synthesize_task_signals,
)
from .pipeline import (
    ReplayReport,
    batch_route_payload,
    find_samples_root,
    format_eval_report,
    format_regression_report,
    format_replay_json,
    format_replay_text,
    load_default_pricing,
    load_policy,
    policy_summary,
    regression_report,
    resolve_paths,
    resolve_policy_path,
    route_payload,
    run_bundled_replay,
    run_evals,
    run_replay,
    run_route_once,
    summarize_by_class,
)
from .pricing import PricingTable, TokenRates
from .profile import TaskProfile, profile_task, stratify_traces
from .select import SelectionAttempt, SelectionResult, compare_select, ordered_select
from .trace import build_trace

__version__ = "0.1.0"

__all__ = [
    "BudgetDecision",
    "BudgetGate",
    "Classifier",
    "Experiment",
    "ExperimentResult",
    "PricingTable",
    "ReplayReport",
    "RuleBasedClassifier",
    "SelectionAttempt",
    "SelectionResult",
    "Spotlight",
    "TokenRates",
    "TaskProfile",
    "__version__",
    "baseline_cost_usd",
    "baseline_model_for_task",
    "single_call_baseline_arms",
    "batch_route_payload",
    "build_trace",
    "classify_task",
    "compare_select",
    "find_samples_root",
    "format_eval_report",
    "format_regression_report",
    "format_replay_json",
    "format_replay_text",
    "list_experiments",
    "load_default_pricing",
    "load_experiment",
    "load_policy",
    "load_signal_fixture",
    "load_workload",
    "ordered_select",
    "policy_summary",
    "profile_task",
    "regression_report",
    "resolve_paths",
    "resolve_policy_path",
    "route_payload",
    "route_task",
    "route_tasks",
    "run_bundled_replay",
    "run_evals",
    "run_experiment",
    "run_replay",
    "run_route_once",
    "summarize_by_class",
    "summarize_traces",
    "stratify_traces",
    "synthesize_shared_signals",
    "synthesize_signals",
    "synthesize_task_signals",
]
