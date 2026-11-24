from datetime import date
from decimal import Decimal

from app.services.evaluation_service import _prf, results_match


def test_results_match_ignores_names_order_and_numeric_representation():
    expected = [[1, "a", Decimal("10.50")], [2, "b", Decimal("3")]]
    actual = [[3.0, 2, "b"], [10.5, 1, "a"]]  # different column order and row order, float vs Decimal
    assert results_match(expected, actual, ordered=False)


def test_ordered_comparison_respects_row_order():
    a, b = [[1], [2]], [[2], [1]]
    assert results_match(a, b, ordered=False) and not results_match(a, b, ordered=True)


def test_mismatches_are_detected():
    assert not results_match([[1, 2]], [[1]], False)  # different width
    assert not results_match([[1], [2]], [[1]], False)  # different row count
    assert not results_match([[1.01]], [[1.05]], False)
    assert not results_match([[None]], [[0]], False)


def test_month_and_timestamp_representations_are_equivalent():
    assert results_match([[date(2026, 1, 1)]], [["2026-01-01T00:00:00"]], False)
    assert results_match([["2026-01"]], [["2026-01-01"]], False)


def test_precision_recall():
    assert _prf(["a", "b"], ["a", "c", "d", "b"]) == (1.0, 0.5)
    assert _prf(["a", "b"], ["a"]) == (0.5, 1.0)
    assert _prf([], ["a"]) == (None, None)
    assert _prf(["a"], []) == (0.0, 0.0)


def test_extra_columns_are_tolerated_only_by_the_lenient_comparison():
    from app.services.evaluation_service import results_match, results_match_allowing_extra_columns

    expected = [["Asha", "Rao", 100.0], ["Ravi", "Kumar", 250.5]]
    actual = [[7, "Asha", "Rao", 100.0], [9, "Ravi", "Kumar", 250.5]]  # extra leading id column
    assert not results_match(expected, actual, ordered=False)
    assert results_match_allowing_extra_columns(expected, actual, ordered=False)
    # wrong values are still wrong, whatever the extra columns
    assert not results_match_allowing_extra_columns(expected, [[7, "Asha", "Rao", 99.0], [9, "Ravi", "Kumar", 250.5]], ordered=False)
    # fewer columns than expected, or a different row count, never matches
    assert not results_match_allowing_extra_columns(expected, [["Asha", "Rao"], ["Ravi", "Kumar"]], ordered=False)
    assert not results_match_allowing_extra_columns(expected, actual[:1], ordered=False)
