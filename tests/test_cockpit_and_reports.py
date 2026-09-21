"""Cockpit cash guard (utils/data.add_position) and monthly-report helpers."""
import pytest

import utils.data as data
import generate_monthly_report as gmr


def _buy(ticker="ZZZ", weight=1.0, price=10.0):
    return {"ticker": ticker, "name": "t", "weight": weight, "entry_price": price, "layer": "Tactical",
            "sector": "Tech", "geography": "USA", "thematic": "Other", "entry_date": "2026-09-19"}


def test_add_position_refuses_overdraft(fake_sb, monkeypatch):
    sb = fake_sb({"positions": [], "transactions": [], "settings": []})
    monkeypatch.setattr(data, "get_client", lambda: sb)
    monkeypatch.setattr(data, "get_cash_amount", lambda pid: 100.0)          # almost empty book
    monkeypatch.setattr(data, "_get_initial_capital", lambda sb_, pid: 1_000_000.0)
    with pytest.raises(ValueError, match="Insufficient cash"):
        data.add_position(_buy(weight=1.0), "test")                           # $10,000 > $100
    assert sb.writes == []                                                    # nothing written


def test_add_position_tolerates_rounding(fake_sb, monkeypatch):
    sb = fake_sb({"positions": [], "transactions": [], "settings": []})
    monkeypatch.setattr(data, "get_client", lambda: sb)
    _cash = lambda pid: 9_999.50                                            # 50 cents short: within $1 tolerance
    _cash.clear = lambda: None                                                # the real one is st.cache_data-wrapped
    monkeypatch.setattr(data, "get_cash_amount", _cash)
    monkeypatch.setattr(data, "_get_initial_capital", lambda sb_, pid: 1_000_000.0)
    monkeypatch.setattr(data, "_snapshot_positions", lambda *a, **k: None)
    data.add_position(_buy(weight=1.0), "test")
    kinds = [w[1] for w in sb.writes]
    assert "positions" in kinds and "transactions" in kinds


def test_month_end():
    assert gmr.month_end("2026-06") == "2026-06-30"
    assert gmr.month_end("2026-02") == "2026-02-28"


def test_missing_commentary_renders_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(gmr, "COMMENTS_DIR", tmp_path)
    market, mgmt, draft = gmr.load_comments("visionnaire", "2026-06-30")
    assert draft and market == gmr.DRAFT_MARKET


def test_commentary_file_makes_it_final(tmp_path, monkeypatch):
    monkeypatch.setattr(gmr, "COMMENTS_DIR", tmp_path)
    (tmp_path / "visionnaire").mkdir()
    (tmp_path / "visionnaire" / "2026-06.toml").write_text(
        'market_comment = ["a", "b"]\nmgmt_comment = ["c {pf_mtd_pct}"]\n', encoding="utf-8")
    market, mgmt, draft = gmr.load_comments("visionnaire", "2026-06-30")
    assert not draft and market == ["a", "b"] and mgmt == ["c {pf_mtd_pct}"]


def test_empty_commentary_lists_still_draft(tmp_path, monkeypatch):
    monkeypatch.setattr(gmr, "COMMENTS_DIR", tmp_path)
    (tmp_path / "nakamoto").mkdir()
    (tmp_path / "nakamoto" / "2026-06.toml").write_text('market_comment = []\nmgmt_comment = ["x"]\n', encoding="utf-8")
    assert gmr.load_comments("nakamoto", "2026-06-30")[2] is True
