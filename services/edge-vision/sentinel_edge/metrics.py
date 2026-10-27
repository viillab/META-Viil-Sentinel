"""Binary candidate-detection metrics; no fabricated real-world performance."""
from dataclasses import dataclass


@dataclass(frozen=True)
class BinaryMetrics:
    true_positive: int
    false_positive: int
    true_negative: int
    false_negative: int
    precision: float
    recall: float
    f1: float


def summarize_binary(actual: list[bool], predicted: list[bool]) -> BinaryMetrics:
    if len(actual) != len(predicted):
        raise ValueError("actual and predicted must have equal lengths")
    if not actual:
        raise ValueError("evaluation requires at least one sample")
    tp = sum(y and p for y, p in zip(actual, predicted))
    fp = sum(not y and p for y, p in zip(actual, predicted))
    tn = sum(not y and not p for y, p in zip(actual, predicted))
    fn = sum(y and not p for y, p in zip(actual, predicted))
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = (2 * precision * recall / (precision + recall)) if precision + recall else 0.0
    return BinaryMetrics(tp, fp, tn, fn, precision, recall, f1)
