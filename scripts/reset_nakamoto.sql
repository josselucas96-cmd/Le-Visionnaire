-- Le Nakamoto — RESET to today's inception (2026-05-11)
-- 9 positions, 100% invested (75% Anchor + 21% Exploratory + 4% Income overlay)
-- Entry prices: yfinance close on/before 2026-05-11

-- 1. Reset portfolio inception
UPDATE portfolios SET inception_date = '2026-05-11' WHERE id = 'nakamoto';

-- 2. Clear prior positions + transactions (clean slate)
DELETE FROM transactions WHERE portfolio_id = 'nakamoto';
DELETE FROM positions    WHERE portfolio_id = 'nakamoto';

-- 3. Insert the 9 launch positions
INSERT INTO positions (portfolio_id, ticker, name, layer, weight, entry_price, entry_date, sector, geography, thematic, thesis_short, is_active) VALUES
  ('nakamoto', 'MSTR', 'Strategy', 'Anchor', 27.0, 187.59, '2026-05-11', 'Tech', 'USA', 'Pure', 'Standard reference of the BTC treasury universe: largest BTC stack, mature ATM + preferreds machinery, institutional shareholder base.', true),
  ('nakamoto', 'MTPLF', 'Metaplanet', 'Anchor', 23.0, 2.23, '2026-05-11', 'Communication', 'Japan', 'Pure', 'Japanese MicroStrategy. Yen-debasement tailwind, aggressive ATM execution, smaller cap = higher per-share BTC accretion runway.', true),
  ('nakamoto', 'ASST', 'Strive Asset Management', 'Anchor', 15.0, 15.92, '2026-05-11', 'Finance', 'USA', 'Pure', 'Strive post-Asset Entities merger. Vivek Ramaswamy''s BTC treasury vehicle, distinct American capital pool and brand.', true),
  ('nakamoto', 'ALCPB.PA', 'Capital B', 'Anchor', 10.0, 0.6502, '2026-05-11', 'Tech', 'Europe', 'Pure', 'European BTC treasury leader (ex Blockchain Group), Euronext-listed, distinct EUR capital pool with same playbook.', true),
  ('nakamoto', 'OBTC3.SA', 'OranjeBTC', 'Exploratory', 8.0, 6.99, '2026-05-11', 'Finance', 'LatAm', 'Pure', 'Brazil''s largest listed BTC treasury, B3 listing — emerging-market BTC proxy with local currency debasement exposure.', true),
  ('nakamoto', 'GS9.F', 'H100 Group', 'Exploratory', 7.0, 0.125, '2026-05-11', 'Healthcare', 'Europe', 'Hybrid', 'Swedish medtech pivoted to BTC treasury. Nordic listing, distinct geography, hybrid balance sheet.', true),
  ('nakamoto', 'CASH3.SA', 'Méliuz', 'Exploratory', 3.0, 4.33, '2026-05-11', 'Consumer', 'LatAm', 'Hybrid', 'Brazilian fintech (cashback platform) with BTC treasury allocation. Hybrid operating business + BTC stack.', true),
  ('nakamoto', 'SWC.L', 'Smarter Web Company', 'Exploratory', 3.0, 39.0, '2026-05-11', 'Communication', 'Europe', 'Pure', 'UK web-services shell adopting an aggressive BTC treasury build. Small cap, high beta to BTC.', true),
  ('nakamoto', 'STRC', 'Strategy STRC Preferred', 'Income', 4.0, 99.99, '2026-05-11', 'Finance', 'USA', 'Pure', 'MSTR''s perpetual preferred shares, ~11.5% annual coupon paid monthly. Bitcoin-backed yield instrument, decouples coupon from BTC spot.', true);

-- Verify:
-- SELECT count(*), sum(weight), inception_date
-- FROM positions p JOIN portfolios pf ON pf.id = p.portfolio_id
-- WHERE p.portfolio_id = 'nakamoto' AND p.is_active = true
-- GROUP BY inception_date;
-- Expected: 9, 100, 2026-05-11