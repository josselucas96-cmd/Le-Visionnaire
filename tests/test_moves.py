"""Batching of the public Moves page (utils/moves.py).

Regression: trades of the same rebalance were drawn one by one, landing on the
same point of the NAV curve and hiding each other — Le Visionnaire's 13 trades
sit on 4 dates, so the chart showed 4 dots for 13 trades (reported 2026-09-22).
"""
from utils.moves import MIXED, batch_numbers, count_trades, group_moves_by_date


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


def test_every_trade_belongs_to_exactly_one_batch():
    groups = group_moves_by_date(VISIONNAIRE)
    assert len(groups) == 4                                   # 4 markers…
    assert sum(g["n"] for g in groups) == len(VISIONNAIRE)    # …covering all 13 trades


def test_batches_are_chronological_and_sized():
    groups = group_moves_by_date(VISIONNAIRE)
    assert [g["date"] for g in groups] == ["2026-05-14", "2026-05-26", "2026-06-01", "2026-06-12"]
    assert [g["n"] for g in groups] == [5, 4, 2, 2]


def test_category_is_the_action_when_homogeneous_and_mixed_otherwise():
    cats = {g["date"]: g["category"] for g in group_moves_by_date(VISIONNAIRE)}
    assert cats["2026-05-14"] == MIXED      # 3 trims + 2 buys
    assert cats["2026-05-26"] == "IN"       # 4 buys
    assert cats["2026-06-01"] == MIXED      # a close and a buy
    assert cats["2026-06-12"] == "IN"


def test_batch_numbers_are_oldest_first():
    assert batch_numbers(VISIONNAIRE) == {
        "2026-05-14": 1, "2026-05-26": 2, "2026-06-01": 3, "2026-06-12": 4}


def test_split_is_a_corporate_action_not_a_trade():
    moves = VISIONNAIRE + [_t("2026-09-08", "SPLIT", "ALCPB.PA")]
    assert count_trades(moves) == (13, 1)
    assert count_trades([]) == (0, 0)


def test_empty_book():
    assert group_moves_by_date([]) == []
