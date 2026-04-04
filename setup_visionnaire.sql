-- Reset positions de test et insérer le vrai portfolio Visionnaire
-- Prix d'entrée approximatifs au 1er janvier 2026 (à vérifier/corriger)

-- 1. Supprimer toutes les positions existantes
DELETE FROM transactions;
DELETE FROM positions;

-- 2. Mettre à jour la date d'inception
UPDATE settings SET value = '2026-01-01' WHERE key = 'inception_date';

-- 3. Insérer les 10 positions du Visionnaire (9.5% chacune = 95%, 5% cash)
INSERT INTO positions (ticker, name, weight, entry_price, entry_date, sector, geography, thematic, thesis_short, is_active)
VALUES
  ('TSLA',   'Tesla',                    9.5, 403.84, '2026-01-02', 'Tech',           'USA',   'Robotics / Automation', 'Optimus robot revolution — Tesla as the leading humanoid robotics company by 2030.',         true),
  ('HIMS',   'Hims & Hers Health',       9.5,  21.54, '2026-01-02', 'Healthcare',     'USA',   'Consumer Growth',       'DTC healthcare disruptor — future Amazon of personalized medicine.',                         true),
  ('MTPLF',  'Metaplanet',               9.5,   4.80, '2026-01-02', 'Finance',        'Japan', 'DAT / Bitcoin',         'Japanese MicroStrategy — asymmetric BTC proxy with small-cap torque.',                       true),
  ('META',   'Meta Platforms',           9.5, 589.93, '2026-01-02', 'Communication',  'USA',   'AI / Semi',             'AI-powered social dominance + Reality Labs optionality — best AI monetization story.',       true),
  ('CELH',   'Celsius Holdings',         9.5,  30.30, '2026-01-02', 'Consumer',       'USA',   'Consumer Growth',       'Future Monster of energy drinks — international expansion thesis still intact.',              true),
  ('NBIS',   'Nebius Group',             9.5,  23.50, '2026-01-02', 'Tech',           'Europe','AI / Semi',             'Under-the-radar AI infrastructure play — European GPU cloud with deep Yandex roots.',         true),
  ('NVDA',   'NVIDIA',                   9.5, 134.25, '2026-01-02', 'Tech',           'USA',   'AI / Semi',             'Picks & shovels of the AI revolution — dominant GPU monopoly with CUDA moat.',               true),
  ('CRSP',   'CRISPR Therapeutics',      9.5,  40.15, '2026-01-02', 'Healthcare',     'USA',   'Biotech / Genomics',    'Genomic revolution — binary but asymmetric; CTX001 approval rerates the whole company.',      true),
  ('RKLB',   'Rocket Lab USA',           9.5,  22.87, '2026-01-02', 'Industrials',    'USA',   'Space / Defense',       'Serious SpaceX competitor on small launchers — growing defense contracts, attractive valuation.', true),
  ('BMNR',   'BitMine Immersion Tech',   9.5,   3.10, '2026-01-02', 'Finance',        'USA',   'DAT / Bitcoin',         'DAT micro-cap — high-risk high-reward BTC proxy, kept as a small asymmetric bet.',            true);
