"""Grouping helpers for the public Moves page.

Trades come in batches: a rebalance is several trades executed the same day.
Drawn one by one they land on the same point of the NAV curve and hide each
other — Le Visionnaire's 13 trades happen on 4 dates, so the chart showed 4
dots and looked wrong.

The page therefore draws, per date, at most two markers: one for the buy side
and one for the sell side, offset below and above the curve so a rebalance
that both sells and buys stays readable. Corporate actions (splits) are not
trades and never appear as markers. Pure functions, no Streamlit, unit-tested.
"""

BUY = "BUY"
SELL = "SELL"

# A SWITCH row carries both legs; its cash-out leg is the position being sold,
# but the row is recorded from the buy side, so it counts as a buy here.
_SIDE = {"IN": BUY, "SWITCH": BUY, "TRIM": SELL, "OUT": SELL}

SIDE_LABELS = {BUY: "Buy / reinforce", SELL: "Sell / reduce"}


def action_of(t) -> str:
    return (t.get("action") or "").upper()


def side_of(t) -> str | None:
    """BUY, SELL, or None for anything that is not a trade (SPLIT, DRIP)."""
    return _SIDE.get(action_of(t))


def group_moves_by_date_and_side(moves) -> list[dict]:
    """[{date, side, trades, n}] sorted by date then side (buys first).

    One entry = one marker on the chart. Non-trades are dropped.
    """
    batches: dict[tuple[str, str], list] = {}
    for t in moves:
        side = side_of(t)
        if side is None:
            continue
        batches.setdefault((str(t.get("date")), side), []).append(t)
    out = []
    for (d, side) in sorted(batches, key=lambda k: (k[0], k[1] != BUY)):
        trades = batches[(d, side)]
        out.append({"date": d, "side": side, "trades": trades, "n": len(trades)})
    return out


def batch_numbers(moves) -> dict[str, int]:
    """{date: rebalance number}, 1 = oldest. Lets the trade log show which
    trades were one decision."""
    return {d: i + 1 for i, d in enumerate(sorted({str(t.get("date")) for t in moves}))}


def count_trades(moves) -> tuple[int, int]:
    """(real trades, corporate actions). A split is not a decision."""
    ca = sum(1 for t in moves if side_of(t) is None)
    return len(moves) - ca, ca
