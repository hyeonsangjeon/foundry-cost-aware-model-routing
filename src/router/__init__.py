"""Router package for model-routing experiments."""

from .classify import Classifier, RuleBasedClassifier, classify_task
from .select import SelectionAttempt, SelectionResult, compare_select, ordered_select
from .trace import build_trace

__version__ = "0.1.0"

__all__ = [
    "Classifier",
    "RuleBasedClassifier",
    "SelectionAttempt",
    "SelectionResult",
    "__version__",
    "build_trace",
    "classify_task",
    "compare_select",
    "ordered_select",
]
