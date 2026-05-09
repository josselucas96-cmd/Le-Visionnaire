-- Add user-editable valuation inputs to positions table.
-- Run once in Supabase SQL Editor.

ALTER TABLE positions
    ADD COLUMN IF NOT EXISTS expected_revenue_growth NUMERIC,
    ADD COLUMN IF NOT EXISTS expected_gross_margin   NUMERIC,
    ADD COLUMN IF NOT EXISTS expected_op_margin      NUMERIC;

-- Verify (should return 3 rows):
-- SELECT column_name, data_type FROM information_schema.columns
-- WHERE table_name='positions'
--   AND column_name IN ('expected_revenue_growth','expected_gross_margin','expected_op_margin');
