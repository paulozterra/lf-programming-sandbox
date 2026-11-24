-- Reverse only this migration's objects, in foreign-key dependency order.
-- Never cascade into unrelated objects or drop pre-existing application tables.
DROP TABLE IF EXISTS sbx_b2b_sessions;
DROP TABLE IF EXISTS sbx_b2b_login_attempts;
DROP TABLE IF EXISTS sbx_b2b_accounts;
DROP FUNCTION IF EXISTS sbx_b2b_touch_updated_at();
