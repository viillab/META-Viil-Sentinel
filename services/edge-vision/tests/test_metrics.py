import pytest

from sentinel_edge.metrics import summarize_binary


def test_confusion_matrix_and_binary_metrics():
    m = summarize_binary(
        [True, True, False, False, False],
        [True, False, True, False, False],
    )
    assert (m.true_positive, m.false_positive, m.true_negative, m.false_negative) == (1, 1, 2, 1)
    assert m.precision == 0.5
    assert m.recall == 0.5
    assert m.f1 == 0.5


def test_empty_and_mismatched_inputs_rejected():
    with pytest.raises(ValueError):
        summarize_binary([], [])
    with pytest.raises(ValueError):
        summarize_binary([True], [True, False])


def test_zero_positives_are_defined():
    m = summarize_binary([False, False], [False, False])
    assert m.f1 == m.precision == m.recall == 0.0
