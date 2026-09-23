"""Adj. Return %: the return of a position including what was realised on
partial sales. Rocket Lab on 23 September showed Return % +7.35% while the line
had made about +40% on the money put into it, 40% of it having been sold at
$127.28 in May."""
import pytest

from utils.line_returns import move_adjusted_return


def test_rocket_lab_including_the_may_trim():
    trades = [("buy", 745.71215511, 67.05), ("sell", 293.97377883, 127.28)]
    assert move_adjusted_return(trades, 451.73837628, 71.98) == pytest.approx(39.87, abs=0.05)


def test_a_line_never_sold_shows_nothing():
    """Its figure would equal Return %: the table shows a dash instead."""
    trades = [("buy", 100, 10.0), ("buy", 50, 8.0)]
    assert move_adjusted_return(trades, 150, 12.0) is None


def test_selling_below_todays_price_lowers_the_figure():
    """AMD-like: trimmed at 449, now 624. The line made less than a holder of
    the remaining shares alone would suggest."""
    trades = [("buy", 100, 245.0), ("sell", 30, 449.0)]
    adj = move_adjusted_return(trades, 70, 624.0)
    plain = (624.0 / 245.0 - 1) * 100
    assert adj < plain
    assert adj == pytest.approx((30 * 449 + 70 * 624 - 100 * 245) / (100 * 245) * 100)


def test_a_line_with_no_cost_is_ignored():
    assert move_adjusted_return([("sell", 10, 5.0)], 0, 5.0) is None
