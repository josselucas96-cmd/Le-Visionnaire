"""Grouping helpers for the public Moves page.

Trades come in batches: a rebalance is several trades executed the same day.
Drawn one by one they land on the same point of the NAV curve and hide each
other — Le Visionnaire's 13 trades happen on 4 dates, so the chart showed 4
dots and looked wrong.

The page therefore draws ONE marker per trade date, whose glyph says what
happened that day: a green disc (bought only), a red disc (sold only), or a
disc split in two — red on top, green at the bottom — when the day did both.
Corporate actions (splits) are not trades and never appear on the chart.
Pure functions, no Streamlit, unit-tested.
"""

BUY = "BUY"
SELL = "SELL"
BOTH = "BOTH"

# A SWITCH row carries both legs but is recorded from the buy side.
_SIDE = {"IN": BUY, "SWITCH": BUY, "TRIM": SELL, "OUT": SELL}

SIDE_LABELS = {BUY: "Buy / reinforce", SELL: "Sell / reduce"}


def action_of(t) -> str:
    return (t.get("action") or "").upper()


def side_of(t) -> str | None:
    """BUY, SELL, or None for anything that is not a trade (SPLIT, DRIP)."""
    return _SIDE.get(action_of(t))


def _ticker(t) -> str:
    return t.get("ticker_in") or t.get("ticker_out") or ""


def group_moves_by_date(moves) -> list[dict]:
    """[{date, buys, sells, n, kind}] sorted by date ascending.

    One entry = one marker. `kind` is BUY, SELL or BOTH. Each side's trades are
    sorted by ticker so the tooltip always reads the same way.
    """
    batches: dict[str, dict] = {}
    for t in moves:
        side = side_of(t)
        if side is None:
            continue
        b = batches.setdefault(str(t.get("date")), {"buys": [], "sells": []})
        b["buys" if side == BUY else "sells"].append(t)

    out = []
    for d in sorted(batches):
        buys = sorted(batches[d]["buys"], key=_ticker)
        sells = sorted(batches[d]["sells"], key=_ticker)
        kind = BOTH if (buys and sells) else (BUY if buys else SELL)
        out.append({"date": d, "buys": buys, "sells": sells,
                    "n": len(buys) + len(sells), "kind": kind})
    return out


def batch_numbers(moves) -> dict[str, int]:
    """{date: rebalance number}, 1 = oldest. Lets the trade log show which
    trades were one decision."""
    return {d: i + 1 for i, d in enumerate(sorted({str(t.get("date")) for t in moves}))}


def count_trades(moves) -> tuple[int, int]:
    """(real trades, corporate actions). A split is not a decision."""
    ca = sum(1 for t in moves if side_of(t) is None)
    return len(moves) - ca, ca
