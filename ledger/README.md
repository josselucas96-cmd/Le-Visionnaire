# Ledger export & Bitcoin timestamps

This folder is the **independent copy of the Specula track record**, exported every night from the
database after the daily refresh (`.github/workflows/ledger-anchor.yml`, `scripts/export_ledger.py`).

| File | Content |
|---|---|
| `daily_holdings.csv` | One row per portfolio × day × position (`shares`, `price` in USD, `value`) plus one `CASH` row per day. NAV of a day = sum of `value`. |
| `positions.csv` | Every position ever opened (active and closed) with its cost basis. |
| `transactions.csv` | The trade log: every buy, trim, close, switch and split, with its timestamp and price. |
| `portfolios.csv` | Inception dates, initial capital, benchmarks. |
| `SHA256SUMS` | SHA-256 of each CSV at export time. |
| `MANIFEST.json` | Export time, row counts, last ledger date. |
| `proofs/SHA256SUMS-YYYY-MM-DD` + `.ots` | Daily snapshot of `SHA256SUMS` and its **OpenTimestamps proof**. |

## What the proof guarantees — and what it does not

An `.ots` proof shows that the exact bytes of `proofs/SHA256SUMS-<date>` **existed no later than a given
Bitcoin block**. Since that file lists the hash of every CSV, it pins the whole ledger as of that day:
any later modification of a historical row would change `daily_holdings.csv`, hence its hash, and
would not match the anchored snapshot.

It does **not** prove the data was *correct* when written. Correctness rests on the methodology
(prices are end-of-day closes from a public feed, reproducible by anyone), on the trade log, and on the
public corrections log (`/Methodology` on the site, `errata.toml` in this repository). A correction of a
past row is therefore visible twice: in the errata log, and as a diff between two anchored snapshots.

Proofs are created *pending* (the calendar servers aggregate requests) and are upgraded by later runs
once the Bitcoin transaction is confirmed — usually within a few hours.

## Verify a snapshot yourself

```bash
pip install opentimestamps-client
# 1. the snapshot hashes match the CSVs of that commit
git checkout <commit of that day>
sha256sum -c ledger/proofs/SHA256SUMS-2026-09-21      # (paths are relative to ledger/)
# 2. the snapshot existed at the attested Bitcoin block
ots info   ledger/proofs/SHA256SUMS-2026-09-21.ots   # shows the attestation (block height)
ots verify ledger/proofs/SHA256SUMS-2026-09-21.ots   # full check against a Bitcoin node
```

Without a local Bitcoin node, `ots info` gives the block height and the Merkle path; any block explorer
or the web verifier at https://opentimestamps.org can confirm it.
