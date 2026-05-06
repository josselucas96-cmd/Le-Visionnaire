-- Le Bâtisseur v7 — INSERT positions
-- Inception: 2026-05-06 (per IPS Finale)
-- Entry prices: 2026-05-06 closes
-- 26 positions, 94.5% invested, 5.5% cash, UCITS V compliant

-- 1. Update portfolio metadata (inception date)
UPDATE portfolios SET inception_date = '2026-05-06' WHERE id = 'batisseur';

-- 2. Safety: clear any prior positions for this portfolio
DELETE FROM positions WHERE portfolio_id = 'batisseur';

-- 3. Insert 26 active positions
INSERT INTO positions (portfolio_id, ticker, name, layer, weight, entry_price, entry_date, sector, geography, thematic, thesis_short, is_active) VALUES
  ('batisseur', 'NVDA', 'NVIDIA', 'Obvious', 8.0, 196.5, '2026-05-06', 'Information Technology', 'USA', 'AI / Semi', 'AI infrastructure leader, dominant GPU position with strong moat in accelerated computing.', true),
  ('batisseur', 'CSU.TO', 'Constellation Software', 'Obvious', 7.0, 2464.54, '2026-05-06', 'Information Technology', 'Canada', 'Software', 'Disciplined serial acquirer of vertical market software, exceptional capital allocation.', true),
  ('batisseur', 'AMZN', 'Amazon', 'Obvious', 6.0, 273.55, '2026-05-06', 'Consumer Discretionary', 'USA', 'Cloud', 'Multi-engine compounder: AWS, retail, advertising; best-in-class operational leverage.', true),
  ('batisseur', 'META', 'Meta Platforms', 'Obvious', 6.0, 604.96, '2026-05-06', 'Communication Services', 'USA', 'Social Platform', 'Asymmetric AI capex bet, strong network effects across WhatsApp/Instagram/Facebook.', true),
  ('batisseur', 'MELI', 'MercadoLibre', 'Obvious', 5.0, 1817.3101, '2026-05-06', 'Consumer Discretionary', 'LatAm', 'Consumer Growth', 'Latin America e-commerce + fintech ecosystem with structural demographic tailwind.', true),
  ('batisseur', 'LLY', 'Eli Lilly', 'Obvious', 5.0, 988.87, '2026-05-06', 'Healthcare', 'USA', 'Obesity', 'GLP-1 leader (Mounjaro/Zepbound) with broad pipeline across obesity, neuro, oncology.', true),
  ('batisseur', 'JPM', 'JPMorgan Chase', 'Obvious', 4.5, 309.4, '2026-05-06', 'Financials', 'USA', 'Fintech', 'Best-in-class capital allocation, scale advantage, technology investment paying off.', true),
  ('batisseur', 'BABA', 'Alibaba', 'Obvious', 4.0, 132.26, '2026-05-06', 'Consumer Discretionary', 'Asia ex-Japan', 'Consumer Growth', 'China e-commerce + cloud, accelerating buybacks, AI capex underappreciated.', true),
  ('batisseur', 'MSFT', 'Microsoft', 'Haute Qualité', 4.0, 411.38, '2026-05-06', 'Information Technology', 'USA', 'Software', 'Office + Azure backbone, cloud + productivity dual-engine compounding.', true),
  ('batisseur', 'V', 'Visa', 'Haute Qualité', 4.0, 322.03, '2026-05-06', 'Financials', 'USA', 'Fintech', 'Global payments network with structural moat and predictable free cash flow.', true),
  ('batisseur', 'BSX', 'Boston Scientific', 'Haute Qualité', 4.0, 55.98, '2026-05-06', 'Healthcare', 'USA', 'Healthcare Equipment', 'Cardiology and electrophysiology leader, switching cost moat in implantable devices.', true),
  ('batisseur', 'FICO', 'Fair Isaac', 'Haute Qualité', 3.0, 1066.27, '2026-05-06', 'Information Technology', 'USA', 'Fintech', 'Credit scoring monopoly with network effects and pricing power.', true),
  ('batisseur', 'VRSK', 'Verisk Analytics', 'Haute Qualité', 3.0, 180.45, '2026-05-06', 'Industrials', 'USA', 'Software', 'Insurance data analytics monopoly with recurring revenue model.', true),
  ('batisseur', 'ISRG', 'Intuitive Surgical', 'Haute Qualité', 3.0, 451.38, '2026-05-06', 'Healthcare', 'USA', 'Healthcare Equipment', 'Robotic surgery leader with razor-and-blade recurring revenue model.', true),
  ('batisseur', 'ULTA', 'Ulta Beauty', 'Haute Qualité', 3.0, 532.53, '2026-05-06', 'Consumer Discretionary', 'USA', 'Consumer Growth', 'Hybrid prestige + mass beauty retail moat with strong loyalty program.', true),
  ('batisseur', 'RACE', 'Ferrari', 'Haute Qualité', 2.0, 325.44, '2026-05-06', 'Consumer Discretionary', 'Europe', 'Luxury', 'Iconic luxury brand with scarcity-driven pricing power and supply discipline.', true),
  ('batisseur', 'RMS.PA', 'Hermès', 'Haute Qualité', 2.0, 1668.0, '2026-05-06', 'Consumer Discretionary', 'Europe', 'Luxury', 'Ultra-luxury brand with consistent pricing power and multi-generational moat.', true),
  ('batisseur', 'EL.PA', 'EssilorLuxottica', 'Diversification', 3.0, 176.8, '2026-05-06', 'Healthcare', 'Europe', 'Healthcare Equipment', 'Vertically integrated eyewear leader, smart glasses partnership with Meta.', true),
  ('batisseur', 'WM', 'Waste Management', 'Diversification', 3.0, 224.49, '2026-05-06', 'Industrials', 'USA', 'Other', 'Landfill regulatory monopoly with structural physical moat.', true),
  ('batisseur', 'NVO', 'Novo Nordisk', 'Diversification', 3.0, 44.87, '2026-05-06', 'Healthcare', 'Europe', 'Obesity', 'GLP-1 obesity franchise with attractive valuation post correction; pipeline optionality.', true),
  ('batisseur', 'VICI', 'VICI Properties', 'Diversification', 2.0, 28.27, '2026-05-06', 'Real Estate', 'USA', 'Other', 'Casino property REIT, regulatory moat, attractive yield, long-term triple-net leases.', true),
  ('batisseur', 'IBE.MC', 'Iberdrola', 'Diversification', 2.0, 19.725, '2026-05-06', 'Utilities', 'Europe', 'Energy Transition', 'Spanish utility with renewables exposure and regulated cash flows.', true),
  ('batisseur', 'DPZ', 'Domino''s Pizza', 'Diversification', 2.0, 331.73, '2026-05-06', 'Consumer Discretionary', 'USA', 'Consumer Growth', 'Asset-light franchise model, strong ROIC, technology-led ordering platform.', true),
  ('batisseur', 'STZ', 'Constellation Brands', 'Diversification', 2.0, 149.8, '2026-05-06', 'Consumer Staples', 'USA', 'Consumer Growth', 'Premium beer portfolio (Modelo, Corona) with brand strength and pricing power.', true),
  ('batisseur', 'ZM', 'Zoom', 'Tactical', 2.0, 109.1, '2026-05-06', 'Information Technology', 'USA', 'Software', 'Anthropic stake creates substantial sum-of-parts value relative to current EV.', true),
  ('batisseur', 'CRCL', 'Circle', 'Tactical', 2.0, 114.19, '2026-05-06', 'Financials', 'USA', 'Fintech', 'USDC stablecoin issuer with infrastructure moat in crypto rails.', true);

-- Verify:
-- SELECT count(*), sum(weight) FROM positions WHERE portfolio_id='batisseur' AND is_active=true;
-- Expected: 26 positions, sum(weight) = 94.5