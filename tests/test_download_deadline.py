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
