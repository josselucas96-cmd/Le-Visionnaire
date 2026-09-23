"""A page must never wait on Yahoo without limit.

Incident 2026-09-23: Le Bâtisseur's page sat on "Running get_history(...)" for
more than five minutes on Streamlit Cloud (Yahoo throttling the shared IP,
yfinance retrying), while st.cache_data made every visitor wait behind the one
stuck call. Downloads now run under a hard deadline, and a failed download is
not memoised.
"""
import time

import pandas as pd
import pytest

from utils import market


@pytest.fixture(autouse=True)
def _fresh_lock(monkeypatch):
    """A test that leaves a sleeping fake download must not hold the shared
    lock over the next test."""
    import threading
    monkeypatch.setattr(market, "_YF_LOCK", threading.Lock())


def test_a_hanging_download_is_abandoned_at_the_deadline(monkeypatch):
    monkeypatch.setattr(market.yf, "download", lambda *a, **k: time.sleep(30))
    t0 = time.time()
    with pytest.raises(TimeoutError):
        market.yf_download("AAA", start="2026-01-01", deadline=0.5)
    assert time.time() - t0 < 5


def test_get_history_returns_empty_instead_of_hanging(monkeypatch):
    market.get_history.clear()
    monkeypatch.setattr(market, "YF_DEADLINE_S", 0.5)
    monkeypatch.setattr(market.yf, "download", lambda *a, **k: time.sleep(30))
    t0 = time.time()
    out = market.get_history(("AAA", "BBB"), "2026-01-01", benchmarks=())
    assert out.empty and time.time() - t0 < 5


def test_a_failed_download_is_not_cached(monkeypatch):
    """The next visitor must get a fresh attempt, not an hour of empty frame."""
    market.get_history.clear()
    monkeypatch.setattr(market.yf, "download", lambda *a, **k: pd.DataFrame())
    assert market.get_history(("CCC",), "2026-01-01", benchmarks=()).empty

    frame = pd.DataFrame({"Close": [1.0, 2.0]}, index=pd.to_datetime(["2026-01-02", "2026-01-05"]))
    monkeypatch.setattr(market.yf, "download", lambda *a, **k: frame)
    assert list(market.get_history(("CCC",), "2026-01-01", benchmarks=())["CCC"]) == [1.0, 2.0]


def test_a_download_that_answers_goes_through(monkeypatch):
    frame = pd.DataFrame({"Close": [10.0]}, index=pd.to_datetime(["2026-01-02"]))
    monkeypatch.setattr(market.yf, "download", lambda *a, **k: frame)
    assert market.yf_download("DDD", start="2026-01-01", deadline=5) is frame


# ── yf.download is not thread-safe: the app must never run two at once ──────
# 2026-09-23: a 'SPY' download run alongside Le Bâtisseur's holdings came back
# as Circle, six trials out of six, and the live page published Circle's return
# as the S&P 500's. The same collision anchored the Visionnaire's Nasdaq 100 on
# Le Bâtisseur's start date that morning.
import threading


def test_downloads_never_overlap(monkeypatch):
    state = {"now": 0, "peak": 0}
    guard = threading.Lock()

    def fake_download(*a, **k):
        with guard:
            state["now"] += 1
            state["peak"] = max(state["peak"], state["now"])
        time.sleep(0.05)
        with guard:
            state["now"] -= 1
        return pd.DataFrame({"Close": [1.0]}, index=pd.to_datetime(["2026-01-02"]))

    monkeypatch.setattr(market.yf, "download", fake_download)
    threads = [threading.Thread(target=market.yf_download, args=(f"T{i}",), kwargs={"deadline": 10})
               for i in range(6)]
    for t in threads: t.start()
    for t in threads: t.join()
    assert state["peak"] == 1


def test_a_benchmark_response_carrying_another_ticker_is_refused(monkeypatch):
    """The exact live failure: asked for SPY, received Circle."""
    from utils.market import BenchmarkUnavailable, get_benchmark_index
    get_benchmark_index.clear()
    days = pd.bdate_range("2026-04-20", periods=60)
    crcl = pd.DataFrame({("Close", "CRCL"): [100.0] * 60}, index=days)
    crcl.columns = pd.MultiIndex.from_tuples(crcl.columns)

    class _Ticker:
        def __init__(self, t): pass
        def history(self, **k): return crcl

    monkeypatch.setattr(market.yf, "Ticker", _Ticker)
    with pytest.raises(BenchmarkUnavailable) as e:
        get_benchmark_index("SPY", "2026-05-05")
    assert "CRCL" in str(e.value)


def test_a_history_frame_with_foreign_tickers_is_refused(monkeypatch):
    market.get_history.clear()
    days = pd.bdate_range("2026-04-20", periods=20)
    mixed = pd.DataFrame({("Close", "AAA"): [1.0] * 20, ("Close", "ZZZ"): [2.0] * 20}, index=days)
    mixed.columns = pd.MultiIndex.from_tuples(mixed.columns)
    monkeypatch.setattr(market.yf, "download", lambda *a, **k: mixed)
    assert market.get_history(("AAA", "BBB"), "2026-04-20", benchmarks=()).empty
