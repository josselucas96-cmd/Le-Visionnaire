"""Batching of the public Moves page (utils/moves.py).

Regression: trades of the same rebalance were drawn one by one, landing on the
same point of the NAV curve and hiding each other — Le Visionnaire's 13 trades
sit on 4 dates, so the chart showed 4 dots for 13 trades (reported 2026-09-22).
The page now draws at most two markers per date, one per side.
"""
from utils.moves import BUY, SELL, batch_numbers, count_trades, group_moves_by_date_and_side, side_of


def _t(date, action, ticker):
    key = "ticker_in" if action in ("IN", "SWITCH", "SPLIT") else "ticker_out"
    return {"date": date, "action": action, key: ticker}


# The real Visionnaire book: 13 trades on 4 dates.
VISIONNAIRE = [
    _t("2026-05-14", "TRIM", "AMD"), _t("2026-05-14", "IN", "CELH"), _t("2026-05-14", "IN", "HIMS"),
    _t("2026-05-14", "TRIM", "RKLB"), _t("2026-05-14", "TRIM", "TSLA"),
    _t("2026-05-26", "IN", "NIO"), _t("2026-05-26", "IN", "NU"),
    _t("2026-05-26", "IN", "SMCI"), _t("2026-05-26", "IN", "SOFI"),
    _t("2026-06-01", "IN", "ZETA"), _t("2026-06-01", "OUT", "AMZN"),
    _t("2026-06-12", "IN", "MTPLF"), _t("2026-06-12", "IN", "ZETA"),
]


def test_every_trade_belongs_to_exactly_one_marker():
    groups = group_moves_by_date_and_side(VISIONNAIRE)
    assert sum(g["n"] for g in groups) == len(VISIONNAIRE)     # all 13 trades plotted
    assert len(groups) == 6                                     # 4 dates, 2 of them two-sided


def test_a_rebalance_that_sells_and_buys_yields_one_marker_per_side():
    may14 = [g for g in group_moves_by_date_and_side(VISIONNAIRE) if g["date"] == "2026-05-14"]
    assert [(g["side"], g["n"]) for g in may14] == [(BUY, 2), (SELL, 3)]   # buys first
    jun12 = [g for g in group_moves_by_date_and_side(VISIONNAIRE) if g["date"] == "2026-06-12"]
    assert [(g["side"], g["n"]) for g in jun12] == [(BUY, 2)]             # buy-only day


def test_groups_are_chronological():
    assert [g["date"] for g in group_moves_by_date_and_side(VISIONNAIRE)] == [
        "2026-05-14", "2026-05-14", "2026-05-26", "2026-06-01", "2026-06-01", "2026-06-12"]


def test_sides():
    assert side_of(_t("2026-01-01", "IN", "X")) == BUY
    assert side_of(_t("2026-01-01", "SWITCH", "X")) == BUY
    assert side_of(_t("2026-01-01", "TRIM", "X")) == SELL
    assert side_of(_t("2026-01-01", "OUT", "X")) == SELL


def test_corporate_actions_are_never_plotted():
    moves = VISIONNAIRE + [_t("2026-09-08", "SPLIT", "ALCPB.PA")]
    assert side_of(_t("2026-09-08", "SPLIT", "ALCPB.PA")) is None
    assert sum(g["n"] for g in group_moves_by_date_and_side(moves)) == 13   # split excluded
    assert count_trades(moves) == (13, 1)
    assert count_trades([]) == (0, 0)


def test_batch_numbers_are_oldest_first():
    assert batch_numbers(VISIONNAIRE) == {
        "2026-05-14": 1, "2026-05-26": 2, "2026-06-01": 3, "2026-06-12": 4}


def test_empty_book():
    assert group_moves_by_date_and_side([]) == []
