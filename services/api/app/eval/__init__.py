"""Deterministic eval gates built on DeepEval's metric contract.

`run_gate` scores a generated artifact against pure-Python metrics. Scores are
0..1, higher is better; a gate passes only when every metric clears its
threshold. No model is involved, so the gates are reproducible and run offline.
"""

from .harness import all_gates, build_gate_input, failure_message, run_gate
from .metrics import DEEPEVAL_AVAILABLE, MetricResult, metrics_for

__all__ = [
    "DEEPEVAL_AVAILABLE",
    "MetricResult",
    "all_gates",
    "build_gate_input",
    "failure_message",
    "metrics_for",
    "run_gate",
]
