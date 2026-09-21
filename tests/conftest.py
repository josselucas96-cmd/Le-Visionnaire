"""Shared test plumbing: repo on sys.path, no network, a tiny fake Supabase client.

The fake supports the subset of the supabase-py query builder the code uses:
table().select().eq().gt().lt().gte().lte().in_().order().limit().execute()
plus insert/upsert/update/delete, recording writes so tests can assert on them.
"""
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))


class _Query:
    def __init__(self, sb, table):
        self.sb, self.table = sb, table
        self.filters, self.orders, self._limit = [], [], None
        self.op, self.payload = "select", None

    # filters
    def select(self, *_a, **_k): return self
    def eq(self, k, v):  self.filters.append(lambda r: r.get(k) == v); return self
    def neq(self, k, v): self.filters.append(lambda r: r.get(k) != v); return self
    def gt(self, k, v):  self.filters.append(lambda r: r.get(k) is not None and r.get(k) > v); return self
    def lt(self, k, v):  self.filters.append(lambda r: r.get(k) is not None and r.get(k) < v); return self
    def gte(self, k, v): self.filters.append(lambda r: r.get(k) is not None and r.get(k) >= v); return self
    def lte(self, k, v): self.filters.append(lambda r: r.get(k) is not None and r.get(k) <= v); return self
    def in_(self, k, vals): self.filters.append(lambda r: r.get(k) in set(vals)); return self
    def order(self, k, desc=False): self.orders.append((k, desc)); return self
    def limit(self, n): self._limit = n; return self
    def range(self, a, b): self._limit = b - a + 1; return self

    # writes
    def insert(self, rows): self.op, self.payload = "insert", rows; return self
    def upsert(self, rows, **_k): self.op, self.payload = "upsert", rows; return self
    def update(self, row): self.op, self.payload = "update", row; return self
    def delete(self): self.op = "delete"; return self

    def execute(self):
        rows = self.sb.tables.setdefault(self.table, [])
        if self.op == "select":
            out = [r for r in rows if all(f(r) for f in self.filters)]
            for k, desc in reversed(self.orders):
                out.sort(key=lambda r: (r.get(k) is None, r.get(k)), reverse=desc)
            if self._limit is not None:
                out = out[: self._limit]
            return _Res(out)
        if self.op in ("insert", "upsert"):
            payload = self.payload if isinstance(self.payload, list) else [self.payload]
            rows.extend(dict(r) for r in payload)
            self.sb.writes.append((self.op, self.table, payload))
            return _Res(payload)
        if self.op == "update":
            hit = [r for r in rows if all(f(r) for f in self.filters)]
            for r in hit:
                r.update(self.payload)
            self.sb.writes.append(("update", self.table, self.payload))
            return _Res(hit)
        if self.op == "delete":
            keep = [r for r in rows if not all(f(r) for f in self.filters)]
            gone = [r for r in rows if all(f(r) for f in self.filters)]
            self.sb.tables[self.table] = keep
            self.sb.writes.append(("delete", self.table, gone))
            return _Res(gone)
        raise RuntimeError(self.op)


class _Res:
    def __init__(self, data): self.data = data


class FakeSupabase:
    def __init__(self, tables=None):
        self.tables = {k: [dict(r) for r in v] for k, v in (tables or {}).items()}
        self.writes = []

    def table(self, name): return _Query(self, name)


@pytest.fixture
def fake_sb():
    return FakeSupabase
