-- ============================================================================
-- RLS lock-down — PREPARED, NOT APPLIED (as of 2026-09-21)
-- ----------------------------------------------------------------------------
-- Goal: the anon key (embedded in the public app, and in the browser after
-- the Next.js migration) can only READ; every write goes through the
-- service_role key, which bypasses RLS and lives only in server-side secrets
-- (GitHub Actions: SUPABASE_SERVICE_KEY; Streamlit Cloud: supabase_service_key).
--
-- PRE-REQUISITES — do NOT run before all three are true, or the nightly
-- refresh and the cockpit will fail their writes (the watchdog would flag
-- it the next morning, but the ledger would miss a day):
--   1. GitHub repo secret SUPABASE_SERVICE_KEY set (Supabase → Settings → API
--      → service_role). daily-refresh.yml / ledger-anchor.yml / monthly-
--      reports.yml / publish-report.yml already prefer it when present.
--   2. Streamlit Cloud secret supabase_service_key set. utils/data.get_client()
--      already prefers it when present.
--   3. One green nightly run + one cockpit dry test with the new keys.
-- Then: apply this file (Supabase SQL editor or MCP apply_migration), run the
-- verification block at the end, and delete the anon key exposure note in
-- CLAUDE.md. Rotate the anon key afterwards (it was pasted in a chat log).
-- ============================================================================

-- 1) Enable RLS everywhere it is off (reads will still be allowed by the
--    policies below; without policies RLS blocks everything for anon).
alter table public.daily_holdings   enable row level security;
alter table public.current_prices   enable row level security;
alter table public.nav_history      enable row level security;
alter table public.research         enable row level security;

-- 2) Drop the temporary "anon can do anything" policies.
drop policy if exists anon_all          on public.positions;
drop policy if exists anon_all          on public.transactions;
drop policy if exists anon_all          on public.position_snapshots;
drop policy if exists anon_full_access  on public.current_prices;
drop policy if exists allow_all_research on public.research;

-- 3) Public read-only for the anon key on what the site displays.
create policy anon_read on public.portfolios         for select to anon using (true);
create policy anon_read on public.positions          for select to anon using (true);
create policy anon_read on public.transactions       for select to anon using (true);
create policy anon_read on public.daily_holdings     for select to anon using (true);
create policy anon_read on public.current_prices     for select to anon using (true);
create policy anon_read on public.dividend_factors   for select to anon using (true);
create policy anon_read on public.fundamentals       for select to anon using (true);
create policy anon_read on public.research           for select to anon using (true);
create policy anon_read on public.articles           for select to anon using (status = 'published');
create policy anon_read on public.settings           for select to anon using (true);
create policy anon_read on public.events             for select to anon using (true);
create policy anon_read on public.position_snapshots for select to anon using (true);
-- nav_history: legacy, nobody reads it publicly → no anon policy (RLS blocks).

-- 4) No INSERT/UPDATE/DELETE policy for anon anywhere: writes require
--    service_role (bypasses RLS). Storage buckets (research-docs,
--    article-images, audit-workbook) keep their own policies — review them
--    in the dashboard: public read, uploads by service_role only.

-- ── Verification (run after applying) ──────────────────────────────────────
-- select tablename, rowsecurity from pg_tables where schemaname='public' order by 1;
-- select tablename, policyname, cmd, roles from pg_policies where schemaname='public' order by 1,2;
-- Expected: rowsecurity = true on every table; only SELECT policies for {anon}.
