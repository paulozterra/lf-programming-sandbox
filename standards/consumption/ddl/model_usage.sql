
CREATE SCHEMA IF NOT EXISTS ${schema};
CREATE TABLE ${schema}.model_usage_events(
id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
event_id uuid NOT NULL UNIQUE,order_ref text NOT NULL,lot_ref text NOT NULL,
stage text NOT NULL CHECK(stage IN ('PLAN','BUILD','RETRY','QUESTION','REPAIR','REVIEW')),
attempt integer NOT NULL CHECK(attempt>0),provider text NOT NULL,model text NOT NULL,service_tier text NOT NULL,
pricing_version text NOT NULL,price_row_sha256 char(64) NOT NULL CHECK(price_row_sha256 ~ '^[0-9a-f]{64}$'),
occurred_at timestamptz NOT NULL,input_tokens bigint CHECK(input_tokens>=0),
output_tokens bigint CHECK(output_tokens>=0),cache_read_tokens bigint CHECK(cache_read_tokens>=0),
cache_write_tokens bigint CHECK(cache_write_tokens>=0),
cache_write_ttl_breakdown jsonb NOT NULL DEFAULT '{}'::jsonb CHECK(jsonb_typeof(cache_write_ttl_breakdown)='object'),
measurement text NOT NULL CHECK(measurement IN ('MEASURED','UNMEASURED')),
provider_response_id text,cost_status text NOT NULL CHECK(cost_status IN ('CALCULATED','UNMEASURED')),
cost numeric(24,12) CHECK(cost>=0),currency text NOT NULL CHECK(currency ~ '^[A-Z]{3}$'),
expense_class text NOT NULL CHECK(expense_class IN ('USEFUL','WASTED')),
wasted_reason text,correlation_id uuid NOT NULL,worker_receipt_ref text NOT NULL,
created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
CHECK(expense_class<>'WASTED' OR
(wasted_reason IS NOT NULL AND wasted_reason IN
('FAILED_ATTEMPT','EXPIRED_PACKAGE_REWORK','TESTING_FINDING_REWORK','NON_CONVERGENT_ITERATION'))),
CHECK(measurement<>'MEASURED' OR
(provider_response_id IS NOT NULL AND btrim(provider_response_id)<>'')),
CHECK(cost_status<>'CALCULATED' OR
(measurement='MEASURED' AND input_tokens IS NOT NULL AND output_tokens IS NOT NULL
AND cache_read_tokens IS NOT NULL AND cache_write_tokens IS NOT NULL AND cost IS NOT NULL)));
COMMENT ON TABLE ${schema}.model_usage_events IS 'append-only';
CREATE INDEX ON ${schema}.model_usage_events(order_ref,lot_ref,stage);
CREATE TABLE ${schema}.model_usage_reclassifications(
id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
usage_event_id bigint NOT NULL REFERENCES ${schema}.model_usage_events(id),
expense_class text NOT NULL CHECK(expense_class IN ('USEFUL','WASTED')),
wasted_reason text,decided_at timestamptz NOT NULL DEFAULT now(),
decision_ref text NOT NULL,correlation_id uuid NOT NULL,
created_at timestamptz NOT NULL DEFAULT now(),updated_at timestamptz NOT NULL DEFAULT now(),
CHECK(expense_class<>'WASTED' OR
(wasted_reason IS NOT NULL AND wasted_reason IN
('FAILED_ATTEMPT','EXPIRED_PACKAGE_REWORK','TESTING_FINDING_REWORK','NON_CONVERGENT_ITERATION'))));
COMMENT ON TABLE ${schema}.model_usage_reclassifications IS 'append-only';
CREATE INDEX ON ${schema}.model_usage_reclassifications(usage_event_id,id DESC);
CREATE FUNCTION ${schema}.reject_mutation() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN RAISE EXCEPTION 'append-only model usage' USING ERRCODE='55000'; END; $$;
CREATE TRIGGER usage_no_update_delete BEFORE UPDATE OR DELETE ON ${schema}.model_usage_events
FOR EACH ROW EXECUTE FUNCTION ${schema}.reject_mutation();
CREATE TRIGGER usage_no_truncate BEFORE TRUNCATE ON ${schema}.model_usage_events
FOR EACH STATEMENT EXECUTE FUNCTION ${schema}.reject_mutation();
CREATE TRIGGER class_no_update_delete BEFORE UPDATE OR DELETE ON ${schema}.model_usage_reclassifications
FOR EACH ROW EXECUTE FUNCTION ${schema}.reject_mutation();
CREATE TRIGGER class_no_truncate BEFORE TRUNCATE ON ${schema}.model_usage_reclassifications
FOR EACH STATEMENT EXECUTE FUNCTION ${schema}.reject_mutation();
CREATE FUNCTION ${schema}.validate_ttl() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
DECLARE k text;v jsonb; total numeric:=0;
BEGIN
FOR k,v IN SELECT key,value FROM jsonb_each(NEW.cache_write_ttl_breakdown) LOOP
 IF k NOT IN ('5m','1h','30m','12h') OR jsonb_typeof(v)<>'number' OR v::text !~ '^[0-9]+$'
 THEN RAISE EXCEPTION 'INVALID_CACHE_TTL' USING ERRCODE='23514'; END IF;
 total:=total+(v::text)::numeric;
END LOOP;
IF NEW.cache_write_tokens IS NOT NULL AND total<>NEW.cache_write_tokens
THEN RAISE EXCEPTION 'CACHE_TTL_SUM_MISMATCH' USING ERRCODE='23514'; END IF;
RETURN NEW;
END; $$;
CREATE TRIGGER usage_ttl BEFORE INSERT ON ${schema}.model_usage_events
FOR EACH ROW EXECUTE FUNCTION ${schema}.validate_ttl();
CREATE VIEW ${schema}.model_usage_effective_class WITH (security_invoker=true) AS
SELECT u.*,COALESCE(r.expense_class,u.expense_class) AS effective_expense_class,
COALESCE(r.wasted_reason,u.wasted_reason) AS effective_wasted_reason
FROM ${schema}.model_usage_events u LEFT JOIN LATERAL (
SELECT expense_class,wasted_reason FROM ${schema}.model_usage_reclassifications r
WHERE r.usage_event_id=u.id ORDER BY r.id DESC LIMIT 1) r ON true;
CREATE VIEW ${schema}.model_usage_by_stage WITH (security_invoker=true) AS
SELECT order_ref,lot_ref,stage,currency,effective_expense_class,COUNT(*) AS calls,
SUM(input_tokens) AS input_tokens,SUM(output_tokens) AS output_tokens,
SUM(cache_read_tokens) AS cache_read_tokens,SUM(cache_write_tokens) AS cache_write_tokens,SUM(cost) AS cost
FROM ${schema}.model_usage_effective_class GROUP BY order_ref,lot_ref,stage,currency,effective_expense_class;
CREATE VIEW ${schema}.model_usage_by_lot WITH (security_invoker=true) AS
SELECT order_ref,lot_ref,currency,effective_expense_class,COUNT(*) AS calls,SUM(cost) AS cost,
SUM(cache_read_tokens) AS cache_read_tokens,SUM(input_tokens) AS input_tokens
FROM ${schema}.model_usage_effective_class GROUP BY order_ref,lot_ref,currency,effective_expense_class;
CREATE VIEW ${schema}.model_usage_by_order WITH (security_invoker=true) AS
SELECT order_ref,currency,effective_expense_class,COUNT(*) AS calls,SUM(cost) AS cost,
SUM(cache_read_tokens) AS cache_read_tokens,SUM(input_tokens) AS input_tokens
FROM ${schema}.model_usage_effective_class GROUP BY order_ref,currency,effective_expense_class;
REVOKE ALL ON ALL TABLES IN SCHEMA ${schema} FROM PUBLIC;
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ${schema} FROM PUBLIC;
