"""Router package for model-routing experiments."""

from .budget import BudgetDecision, BudgetGate
from .classify import Classifier, RuleBasedClassifier, classify_task
from .offline import load_signal_fixture, load_workload, route_task, route_tasks, summarize_traces
from .pricing import PricingTable, TokenRates
from .select import SelectionAttempt, SelectionResult, compare_select, ordered_select
from .trace import build_trace

__version__ = "0.1.0"

__all__ = [
    "BudgetDecision",
    "BudgetGate",
    "Classifier",
    "PricingTable",
    "RuleBasedClassifier",
    "SelectionAttempt",
    "SelectionResult",
    "TokenRates",
    "__version__",
    "build_trace",
    "classify_task",
    "compare_select",
    "load_signal_fixture",
    "load_workload",
    "ordered_select",
    "route_task",
    "route_tasks",
    "summarize_traces",
]
