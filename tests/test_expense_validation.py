from __future__ import annotations

from tripsplitexpenses.money import auto_adjust_rounding, split_difference


def test_split_difference_reports_expected_minus_entered():
    assert split_difference(2500, {"a": 1250, "b": 1249}) == 1


def test_auto_adjust_is_limited_to_one_cent():
    assert auto_adjust_rounding(2500, {"a": 1250, "b": 1249}) == {"a": 1250, "b": 1250}
    assert auto_adjust_rounding(2500, {"a": 1200, "b": 1200}) is None
