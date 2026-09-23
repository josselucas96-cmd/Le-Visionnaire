"""The benchmark must be normalised on the portfolio's base date — or not at all.

Incident 2026-09-23. The benchmark used to be read as a column of the same
`yf.download` batch as the 20+ holdings and normalised on `raw.iloc[0]`. Yahoo
throttles those batches from cloud IPs and answers with a truncated column,
saying nothing. That day the live site anchored Le Visionnaire's Nasdaq 100 on
2026-05-05 instead of 2026-04-10 and published:

    Nasdaq 100 (inception)  +9.02%      Alpha  +11.31%

where the truth was +21.60% and -1.27%. The portfolio looked like it was
beating its benchmark by eleven points while it was in fact a point behind.
"""
import pandas as pd
import pytest

from utils import market
from utils.market import BenchmarkUnavailable, get_benchmark_index

ANCHOR = "2026-04-10"


def _frame(dates, closes):
    """A yfinance-shaped answer: a DataFrame with a 'Close' column."""
    return pd.DataFrame({"Close": closes}, index=pd.to_datetime(dates))


def _sessions(start, n):
    return list(pd.bdate_range(start, periods=n))


class _FakeTicker:
    """Stands in for yf.Ticker: benchmarks are fetched with Ticker(t).history."""
    answer = None

    def __init__(self, ticker):
        self.ticker = ticker

    def history(self, **kwargs):
        if isinstance(self.answer, Exception):
            raise self.answer
        return self.answer


def _patch(monkeypatch, frame):
    get_benchmark_index.clear()
    monkeypatch.setattr(_FakeTicker, "answer", frame)
    monkeypatch.setattr(market.yf, "Ticker", _FakeTicker)


def test_normalises_on_the_anchor_close(monkeypatch):
    days = _sessions("2026-04-10", 40)
    closes = [100.0] + [110.0] * 39          # +10% from the anchor
    _patch(monkeypatch, _frame(days, closes))

    idx = get_benchmark_index("QQQ", ANCHOR)

    assert idx.index[0] == pd.Timestamp(ANCHOR)
    assert idx.iloc[0] == pytest.approx(100.0)
    assert idx.iloc[-1] - 100 == pytest.approx(10.0)


def test_a_series_that_starts_after_the_anchor_is_refused(monkeypatch):
    """The exact production failure: data begins three weeks late."""
    days = _sessions("2026-05-05", 40)
    _patch(monkeypatch, _frame(days, [680.15] + [741.47] * 39))

    with pytest.raises(BenchmarkUnavailable) as e:
        get_benchmark_index("QQQ", ANCHOR)
    assert "2026-05-05" in str(e.value) and "2026-04-10" in str(e.value)


def test_a_holiday_anchor_falls_back_to_the_previous_close(monkeypatch):
    """T-1 can be a market holiday: the last close before it is the base."""
    days = [pd.Timestamp("2026-04-08"), pd.Timestamp("2026-04-09")] + _sessions("2026-04-13", 20)
    closes = [90.0, 100.0] + [120.0] * 20
    _patch(monkeypatch, _frame(days, closes))

    idx = get_benchmark_index("QQQ", ANCHOR)          # 2026-04-10 absent

    assert idx.index[0] == pd.Timestamp("2026-04-09")
    assert idx.iloc[-1] - 100 == pytest.approx(20.0)  # based on 100, not 90


def test_a_series_full_of_holes_is_refused(monkeypatch):
    """A half-delivered answer would distort volatility, beta and the chart."""
    days = _sessions("2026-04-10", 60)[::3]          # one session in three
    _patch(monkeypatch, _frame(days, [100.0] * len(days)))

    with pytest.raises(BenchmarkUnavailable) as e:
        get_benchmark_index("QQQ", ANCHOR)
    assert "sessions" in str(e.value)


def test_an_empty_answer_is_refused(monkeypatch):
    _patch(monkeypatch, pd.DataFrame())
    with pytest.raises(BenchmarkUnavailable):
        get_benchmark_index("QQQ", ANCHOR)


def test_a_download_that_raises_is_refused_not_swallowed(monkeypatch):
    _patch(monkeypatch, RuntimeError("429 Too Many Requests"))
    with pytest.raises(BenchmarkUnavailable) as e:
        get_benchmark_index("QQQ", ANCHOR)
    assert "429" in str(e.value)


def test_benchmarks_never_go_through_yf_download(monkeypatch):
    """yf.download is not thread-safe (see utils.market._YF_LOCK): the
    benchmark, the figure that matters most, must not depend on it."""
    def forbidden(*a, **k):
        raise AssertionError("benchmark fetched with yf.download")

    monkeypatch.setattr(market.yf, "download", forbidden)
    _patch(monkeypatch, _frame(_sessions("2026-04-10", 40), [100.0] + [105.0] * 39))
    assert get_benchmark_index("QQQ", ANCHOR).iloc[-1] - 100 == pytest.approx(5.0)
