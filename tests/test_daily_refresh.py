"""Guards and date logic of the nightly writer (daily_refresh.py). No network:
yfinance and the DB are replaced by fakes."""
from datetime import datetime, timezone

import numpy as np
import pandas as pd
import pytest

import daily_refresh as dr


# ── target date ───────────────────────────────────────────────────────────────
def test_target_is_yesterday_when_run_before_us_close():
    now = datetime(2026, 8, 28, 6, 4, tzinfo=timezone.utc)   # the real delayed run of 28 Aug
    assert dr.resolve_target_date(now) == "2026-08-27"


def test_target_is_today_after_close():
    assert dr.resolve_target_date(datetime(2026, 8, 28, 22, 40, tzinfo=timezone.utc)) == "2026-08-28"


def test_explicit_date_wins():
    assert dr.resolve_target_date(datetime(2026, 8, 28, 6, 0, tzinfo=timezone.utc), "2026-01-05") == "2026-01-05"


# ── close fetching: Yahoo empty rows ─────────────────────────────────────────
def _frame(dates, closes):
    return pd.DataFrame({"Close": closes}, index=pd.to_datetime(dates))


def test_fetch_close_skips_nan_rows_and_reports_real_date(monkeypatch):
    monkeypatch.setattr(dr.yf, "download",
                        lambda *a, **k: _frame(["2026-09-16", "2026-09-17"], [145.1, np.nan]))
    price, d = dr.fetch_close_price("EL.PA", "2026-09-17")
    assert (price, d) == (145.1, "2026-09-16")


def test_fetch_close_ignores_rows_after_target(monkeypatch):
    monkeypatch.setattr(dr.yf, "download",
                        lambda *a, **k: _frame(["2026-09-16", "2026-09-18"], [10.0, 11.0]))
    assert dr.fetch_close_price("X", "2026-09-17") == (10.0, "2026-09-16")


def test_fetch_close_none_when_nothing_before_target(monkeypatch):
    monkeypatch.setattr(dr.yf, "download", lambda *a, **k: _frame(["2026-09-18"], [11.0]))
    assert dr.fetch_close_price("X", "2026-09-17") == (None, None)


# ── FX as of date ─────────────────────────────────────────────────────────────
def test_fx_as_of_uses_last_valid_close_before_date(monkeypatch):
    monkeypatch.setattr(dr.yf, "download",
                        lambda *a, **k: _frame(["2026-09-15", "2026-09-16", "2026-09-17"], [1.16, 1.17, np.nan]))
    rates = dr._fx_to_usd(["EUR"], as_of="2026-09-17")
    assert rates["EUR"] == pytest.approx(1.17)


def test_pence_are_divided_by_100():
    assert dr._usd_factor("GBp", {"GBp": 1.35}) == pytest.approx(0.0135)
    assert dr._usd_factor("USD", {}) == 1.0


# ── the two corruption guards ────────────────────────────────────────────────
def test_refuses_backfill_of_a_date_with_later_moves(fake_sb):
    sb = fake_sb({"transactions": [
        {"portfolio_id": "batisseur", "date": "2026-06-04", "action": "IN", "ticker_in": "AVGO", "ticker_out": None},
        {"portfolio_id": "batisseur", "date": "2026-09-08", "action": "SPLIT", "ticker_in": "ALCPB.PA", "ticker_out": None},
    ]})
    with pytest.raises(dr.BookChangedAfterDate):
        dr.refresh_portfolio(sb, "batisseur", "2026-06-03")          # the row that got corrupted on 2026-06-04


def test_splits_do_not_count_as_moves(fake_sb):
    sb = fake_sb({"transactions": [
        {"portfolio_id": "nakamoto", "date": "2026-09-08", "action": "SPLIT", "ticker_in": "ALCPB.PA", "ticker_out": None},
    ]})
    assert dr._has_moves_after(sb, "nakamoto", "2026-09-02") == []


def _wire_nakamoto(monkeypatch, sb, price_alcpb):
    """Isolate refresh_portfolio from network: fixed close, FX, cash, capital."""
    monkeypatch.setattr(dr, "fetch_close_price", lambda tk, d, retries=3: (price_alcpb if tk == "ALCPB.PA" else 100.0, d))
    monkeypatch.setattr(dr, "_currency_map", lambda sb_, tks: {t: "USD" for t in tks})
    monkeypatch.setattr(dr, "_fx_to_usd", lambda ccys, as_of=None: {"USD": 1.0})
    monkeypatch.setattr(dr, "derive_cash_at_date", lambda *a, **k: 0.0)
    monkeypatch.setattr(dr, "get_initial_capital", lambda *a, **k: 1_000_000.0)
    monkeypatch.setattr(dr, "_previous_values", lambda *a, **k: {"ALCPB.PA": 86_535.0, "MSTR": 183_238.0})


def test_unapplied_split_is_refused(fake_sb, monkeypatch):
    sb = fake_sb({"positions": [
        {"portfolio_id": "nakamoto", "ticker": "ALCPB.PA", "shares": 130_682.87, "is_active": True},
        {"portfolio_id": "nakamoto", "ticker": "MSTR", "shares": 1_439.31, "is_active": True},
    ], "transactions": []})
    _wire_nakamoto(monkeypatch, sb, price_alcpb=5.96)                     # restated x10 price, old share count
    monkeypatch.setattr(dr, "ALLOW_JUMPS", False)
    monkeypatch.setattr(dr, "detect_split", lambda *a, **k: None)         # no network; no split known -> must block
    with pytest.raises(dr.SuspiciousValueJump) as e:
        dr.refresh_portfolio(sb, "nakamoto", "2026-09-10")
    assert "ALCPB.PA" in str(e.value)
    assert not [w for w in sb.writes if w[1] == "daily_holdings"]        # nothing written


def test_normal_day_writes_rows(fake_sb, monkeypatch):
    sb = fake_sb({"positions": [
        {"portfolio_id": "nakamoto", "ticker": "ALCPB.PA", "shares": 13_068.29, "is_active": True},
        {"portfolio_id": "nakamoto", "ticker": "MSTR", "shares": 1_439.31, "is_active": True},
    ], "transactions": []})
    _wire_nakamoto(monkeypatch, sb, price_alcpb=6.60)                     # post-split shares: value ~86K, no jump
    monkeypatch.setattr(dr, "ALLOW_JUMPS", False)
    r = dr.refresh_portfolio(sb, "nakamoto", "2026-09-10")
    assert r["rows_written"] == 3                                          # 2 tickers + CASH
    written = [w for w in sb.writes if w[1] == "daily_holdings"]
    assert written and all(row["date"] == "2026-09-10" for row in written[0][2])


# ── as-of book reconstruction ────────────────────────────────────────────────
def _bat_sb(fake_sb):
    """Bâtisseur around Rebalance #1 (4 June): current book holds AVGO, not RACE."""
    return fake_sb({
        "positions": [
            {"portfolio_id": "batisseur", "ticker": "NVDA", "shares": 407.12468193, "is_active": True},
            {"portfolio_id": "batisseur", "ticker": "AVGO", "shares": 71.73876084, "is_active": True},
        ],
        "transactions": [
            {"portfolio_id": "batisseur", "date": "2026-06-04", "executed_at": "2026-06-04T13:35:00+00:00", "action": "IN",
             "ticker_in": "AVGO", "ticker_out": None, "weight_in": 2.9537, "weight_out": None, "price_in": 411.73, "entry_price_out": None, "reason": None},
            {"portfolio_id": "batisseur", "date": "2026-06-04", "executed_at": "2026-06-04T13:38:41+00:00", "action": "OUT",
             "ticker_in": None, "ticker_out": "RACE", "weight_in": None, "weight_out": 2.0, "price_in": None, "entry_price_out": 325.44, "reason": None},
            {"portfolio_id": "nakamoto", "date": "2026-09-08", "action": "SPLIT", "ticker_in": "ALCPB.PA", "ticker_out": None, "reason": "0.1-for-1 split"},
        ],
    })


def test_book_as_of_reverses_a_buy_and_a_close(fake_sb):
    sb = _bat_sb(fake_sb)
    book, n = dr.book_as_of(sb, "batisseur", "2026-06-03", 1_000_000.0)
    assert n == 2
    assert "AVGO" not in book                                   # bought the day after
    assert book["RACE"] == pytest.approx(2.0 * 1_000_000 / 100 / 325.44, rel=1e-6)   # closed the day after
    assert book["NVDA"] == pytest.approx(407.12468193)


def test_book_as_of_is_identity_when_no_later_trade(fake_sb):
    sb = _bat_sb(fake_sb)
    book, n = dr.book_as_of(sb, "batisseur", "2026-06-05", 1_000_000.0)
    assert n == 0 and set(book) == {"NVDA", "AVGO"}


def test_split_is_not_reversed_because_feed_restates_history(fake_sb):
    sb = fake_sb({"positions": [{"portfolio_id": "nakamoto", "ticker": "ALCPB.PA", "shares": 13_068.29, "is_active": True}],
                  "transactions": [{"portfolio_id": "nakamoto", "date": "2026-09-08", "action": "SPLIT", "ticker_in": "ALCPB.PA",
                                    "ticker_out": None, "reason": "0.1-for-1 split"}]})
    book, _ = dr.book_as_of(sb, "nakamoto", "2026-09-07", 1_000_000.0)
    assert book["ALCPB.PA"] == pytest.approx(13_068.29)        # post-split basis kept


def test_late_backfill_uses_as_of_book_and_removes_stale_rows(fake_sb, monkeypatch):
    sb = _bat_sb(fake_sb)
    sb.tables["daily_holdings"] = [                                      # the corrupted row: AVGO present on 3 June
        {"portfolio_id": "batisseur", "date": "2026-06-03", "ticker": "AVGO", "value": 30_000.0},
        {"portfolio_id": "batisseur", "date": "2026-06-03", "ticker": "NVDA", "value": 80_000.0},
        {"portfolio_id": "batisseur", "date": "2026-06-03", "ticker": "CASH", "value": 55_000.0},
    ]
    monkeypatch.setattr(dr, "fetch_close_price", lambda tk, d, retries=3: (100.0, d))
    monkeypatch.setattr(dr, "_currency_map", lambda sb_, tks: {t: "USD" for t in tks})
    monkeypatch.setattr(dr, "_fx_to_usd", lambda ccys, as_of=None: {"USD": 1.0})
    monkeypatch.setattr(dr, "derive_cash_at_date", lambda *a, **k: 55_000.0)
    monkeypatch.setattr(dr, "get_initial_capital", lambda *a, **k: 1_000_000.0)
    monkeypatch.setattr(dr, "_previous_values", lambda *a, **k: {})
    r = dr.refresh_portfolio(sb, "batisseur", "2026-06-03")
    tickers = {row["ticker"] for row in sb.tables["daily_holdings"] if row["date"] == "2026-06-03"}
    assert tickers == {"NVDA", "RACE", "CASH"}                          # AVGO removed, RACE restored
    assert ("delete", "daily_holdings", [{"portfolio_id": "batisseur", "date": "2026-06-03", "ticker": "AVGO", "value": 30_000.0}]) in sb.writes


# ── automatic split application ──────────────────────────────────────────────
def _nak_presplit_sb(fake_sb):
    return fake_sb({"positions": [
        {"id": 1, "portfolio_id": "nakamoto", "ticker": "ALCPB.PA", "shares": 130_682.8665, "units": 130_682.8665, "entry_price": 0.7652, "is_active": True},
        {"id": 2, "portfolio_id": "nakamoto", "ticker": "MSTR", "shares": 1_439.31, "units": None, "entry_price": 187.59, "is_active": True},
    ], "transactions": []})


def test_detected_split_is_applied_instead_of_blocking(fake_sb, monkeypatch):
    sb = _nak_presplit_sb(fake_sb)
    _wire_nakamoto(monkeypatch, sb, price_alcpb=5.96)                    # restated price, old share count -> x9 jump
    monkeypatch.setattr(dr, "ALLOW_JUMPS", False)
    monkeypatch.setattr(dr, "detect_split", lambda tk, d, window_days=14: (0.1, "2026-09-08") if tk == "ALCPB.PA" else None)
    r = dr.refresh_portfolio(sb, "nakamoto", "2026-09-10")
    pos = next(p for p in sb.tables["positions"] if p["ticker"] == "ALCPB.PA")
    assert pos["shares"] == pytest.approx(13_068.28665) and pos["entry_price"] == pytest.approx(7.652)
    splits = [t for t in sb.tables["transactions"] if t["action"] == "SPLIT"]
    assert len(splits) == 1 and splits[0]["date"] == "2026-09-08" and "0.1-for-1" in splits[0]["reason"]
    row = next(x for w in sb.writes if w[1] == "daily_holdings" for x in w[2] if x["ticker"] == "ALCPB.PA")
    assert row["shares"] == pytest.approx(13_068.28665) and row["value"] == pytest.approx(13_068.28665 * 5.96, rel=1e-6)
    assert r["rows_written"] == 3


def test_jump_without_matching_split_still_blocks(fake_sb, monkeypatch):
    sb = _nak_presplit_sb(fake_sb)
    _wire_nakamoto(monkeypatch, sb, price_alcpb=5.96)
    monkeypatch.setattr(dr, "ALLOW_JUMPS", False)
    monkeypatch.setattr(dr, "detect_split", lambda *a, **k: None)
    with pytest.raises(dr.SuspiciousValueJump):
        dr.refresh_portfolio(sb, "nakamoto", "2026-09-10")
    assert not [t for t in sb.tables["transactions"] if t["action"] == "SPLIT"]


def test_apply_split_db_is_idempotent(fake_sb):
    sb = _nak_presplit_sb(fake_sb)
    assert dr.apply_split_db(sb, "nakamoto", "ALCPB.PA", 0.1, "2026-09-08") is True
    assert dr.apply_split_db(sb, "nakamoto", "ALCPB.PA", 0.1, "2026-09-08") is False   # second call: no-op
    assert next(p for p in sb.tables["positions"] if p["ticker"] == "ALCPB.PA")["shares"] == pytest.approx(13_068.28665)
