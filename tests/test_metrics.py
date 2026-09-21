"""Pure metric helpers (utils/metrics.py) and the trading-calendar alignment."""
import numpy as np
import pandas as pd
import pytest

from utils.metrics import (
    daily_returns, sharpe_ratio, max_drawdown, beta_vs_spy,
    annualized_volatility, var_95, monthly_returns_table,
)
from utils.portfolio import align_to_equity_calendar


def _idx(values, start="2026-04-10", freq="D"):
    return pd.Series(values, index=pd.date_range(start, periods=len(values), freq=freq), dtype=float)


def test_max_drawdown_peak_to_trough():
    s = _idx([100, 110, 121, 100, 105])
    assert max_drawdown(s) == pytest.approx(-17.36, abs=0.01)   # 121 -> 100


def test_max_drawdown_monotonic_is_zero():
    assert max_drawdown(_idx([100, 101, 102])) == 0.0


def test_sharpe_zero_vol_returns_none():
    assert sharpe_ratio(pd.Series([0.0, 0.0, 0.0])) is None


def test_beta_scales_with_market():
    rng = np.random.default_rng(0)
    m = pd.Series(rng.normal(0, 0.01, 300))
    p = 2.0 * m + rng.normal(0, 0.0001, 300)
    assert beta_vs_spy(p, m) == pytest.approx(2.0, abs=0.05)


def test_beta_needs_ten_points():
    assert beta_vs_spy(pd.Series([0.01] * 5), pd.Series([0.01] * 5)) is None


def test_weekend_zero_returns_dilute_vol_and_var():
    """Why align_to_equity_calendar exists: the same trading-day moves padded
    with flat weekend rows report a lower volatility and a milder VaR."""
    rng = np.random.default_rng(1)
    trading = pd.Series(100 * np.cumprod(1 + rng.normal(0, 0.02, 120)),
                        index=pd.bdate_range("2026-04-10", periods=120))
    padded = trading.reindex(pd.date_range(trading.index[0], trading.index[-1], freq="D")).ffill()
    vol_td, vol_77 = annualized_volatility(daily_returns(trading)), annualized_volatility(daily_returns(padded))
    assert vol_77 < vol_td * 0.9
    assert var_95(daily_returns(padded)) > var_95(daily_returns(trading))  # less negative


def test_align_to_equity_calendar_uses_benchmark_dates():
    port = _idx(np.linspace(100, 110, 21))                                  # 7/7 incl. weekends
    bench = pd.Series(1.0, index=pd.bdate_range("2026-04-10", periods=15))  # weekdays
    bench = bench.drop(pd.Timestamp("2026-04-17"))                          # a holiday
    out = align_to_equity_calendar(port, bench, None)
    assert (out.index.weekday < 5).all()
    assert pd.Timestamp("2026-04-17") not in out.index                      # holiday removed too


def test_align_ignores_24_7_benchmark_and_falls_back_to_weekdays():
    port = _idx(np.linspace(100, 110, 14))
    btc = pd.Series(1.0, index=pd.date_range("2026-04-10", periods=14, freq="D"))
    out = align_to_equity_calendar(port, btc, None)
    assert (out.index.weekday < 5).all() and len(out) == 10


def test_align_handles_empty():
    assert align_to_equity_calendar(pd.Series(dtype=float), None, None).empty


def test_monthly_returns_partial_inception_month_and_incomplete_month():
    # base 100 at T-1 (Apr 10), inception Apr 13; series runs to today so the
    # current month is incomplete and must be dropped.
    today = pd.Timestamp.today().normalize()
    idx = pd.date_range("2026-04-10", today, freq="D")
    s = pd.Series(np.linspace(100, 130, len(idx)), index=idx)
    t = monthly_returns_table(s, inception_date="2026-04-13")
    assert 2026 in t.index
    apr_close = s[s.index.month == 4].iloc[-1]
    assert t.loc[2026, "Apr"] == pytest.approx(apr_close - 100, abs=1e-6)  # partial month vs base 100
    cur = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"][today.month - 1]
    if today.day < 28:
        assert pd.isna(t.loc[2026, cur])                                       # incomplete month hidden
