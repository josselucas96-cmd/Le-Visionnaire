"""Grouping helpers for the public Moves page.

Trades come in batches: a rebalance is several trades executed the same day.
Drawn one by one they land on the same point of the NAV curve and hide each
other — Le Visionnaire's 13 trades happen on 4 dates, so the chart showed 4
dots and looked wrong. These helpers turn the flat transaction list into one
entry per date, which the page renders as a single marker carrying the whole
batch. Pure functions, no Streamlit, so they are unit-tested.
"""

MIXED = "MIXED"


def _action(t) -> str:
    return (t.get("action") or "").upper()


def group_moves_by_date(moves) -> list[dict]:
    """[{date, trades, category, n}] sorted by date ascending.

    `category` is the batch's single action (IN / TRIM / OUT / SWITCH / SPLIT)
    or MIXED when the day mixes several — which is what a real rebalance looks
    like (sell one name, buy another).
    """
    batches: dict[str, list] = {}
    for t in moves:
        batches.setdefault(str(t.get("date")), []).append(t)
    out = []
    for d in sorted(batches):
        trades = batches[d]
        actions = {_action(t) for t in trades}
        out.append({
            "date": d,
            "trades": trades,
            "category": next(iter(actions)) if len(actions) == 1 else MIXED,
            "n": len(trades),
        })
    return out


def batch_numbers(moves) -> dict[str, int]:
    """{date: rebalance number}, 1 = oldest. Lets the trade log show which
    trades were one decision."""
    return {d: i + 1 for i, d in enumerate(sorted({str(t.get("date")) for t in moves}))}


def count_trades(moves) -> tuple[int, int]:
    """(real trades, corporate actions). A split is not a decision."""
    ca = sum(1 for t in moves if _action(t) == "SPLIT")
    return len(moves) - ca, ca
