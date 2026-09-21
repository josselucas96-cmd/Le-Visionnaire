"""Export the ledger (daily_holdings, positions, transactions, portfolios) to
deterministic CSV files under ledger/, with a SHA256SUMS file.

Why
---
Supabase is the working store; this is the independent copy. Committed daily
by the nightly workflow, the git history becomes a tamper-evident record of
the track record, and ledger/SHA256SUMS is what gets anchored in Bitcoin with
OpenTimestamps (see .github/workflows/daily-refresh.yml and ledger/README.md).

    python scripts/export_ledger.py [--out ledger]

Deterministic: rows sorted on their natural keys, fixed column order, LF line
endings, so the hash only changes when the data changes.
"""
import argparse
import csv
import hashlib
import json
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def _client():
    url, key = os.environ.get("SUPABASE_URL"), os.environ.get("SUPABASE_KEY")
    if not (url and key):
        import tomllib
        with open(ROOT / ".streamlit" / "secrets.toml", "rb") as f:
            s = tomllib.load(f)
        url, key = s["supabase_url"], s["supabase_key"]
    from supabase import create_client
    return create_client(url, key)


def _fetch_all(sb, table, columns, order):
    rows, off = [], 0
    while True:
        q = sb.table(table).select(",".join(columns))
        for k in order:
            q = q.order(k)
        r = q.range(off, off + 999).execute().data
        rows += r
        if len(r) < 1000:
            break
        off += 1000
    return rows


TABLES = {
    "daily_holdings": (["portfolio_id", "date", "ticker", "shares", "price", "value"], ["portfolio_id", "date", "ticker"]),
    "positions":      (["portfolio_id", "ticker", "name", "layer", "sector", "geography", "thematic", "weight", "shares",
                        "entry_price", "entry_date", "exit_date", "is_active"], ["portfolio_id", "ticker", "entry_date"]),
    "transactions":   (["portfolio_id", "date", "executed_at", "action", "ticker_in", "ticker_out", "weight_in", "weight_out",
                        "price_in", "price_out", "entry_price_out", "reason"], ["portfolio_id", "date", "executed_at"]),
    "portfolios":     (["id", "name", "inception_date", "initial_capital", "benchmark_primary", "benchmark_secondary", "is_active"], ["id"]),
}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--out", default="ledger")
    a = ap.parse_args()
    out = ROOT / a.out
    out.mkdir(parents=True, exist_ok=True)
    sb = _client()
    manifest = {"exported_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"), "tables": {}}
    sums = []
    for table, (cols, order) in TABLES.items():
        rows = _fetch_all(sb, table, cols, order)
        path = out / f"{table}.csv"
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=cols, lineterminator="\n", extrasaction="ignore")
            w.writeheader()
            for r in rows:
                w.writerow({c: ("" if r.get(c) is None else r.get(c)) for c in cols})
        digest = hashlib.sha256(path.read_bytes()).hexdigest()
        sums.append(f"{digest}  {path.name}")
        info = {"rows": len(rows), "sha256": digest}
        if table == "daily_holdings" and rows:
            info["last_date"] = max(r["date"] for r in rows)
        manifest["tables"][table] = info
        print(f"{table:<15} {len(rows):6d} rows  {digest[:12]}…")
    (out / "SHA256SUMS").write_text("\n".join(sums) + "\n", encoding="utf-8")
    (out / "MANIFEST.json").write_text(json.dumps(manifest, indent=1) + "\n", encoding="utf-8")
    print(f"written to {out}/ (SHA256SUMS + MANIFEST.json)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
