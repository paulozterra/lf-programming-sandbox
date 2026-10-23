-- Tests of contract in disposable schema consumption_test, synthetic only.
INSERT INTO consumption_test.model_usage_events
(event_id,order_ref,lot_ref,stage,attempt,provider,model,service_tier,pricing_version,price_row_sha256,occurred_at,
input_tokens,output_tokens,cache_read_tokens,cache_write_tokens,cache_write_ttl_breakdown,measurement,provider_response_id,
cost_status,cost,currency,expense_class,correlation_id,worker_receipt_ref)
VALUES ('00000000-0000-4000-8000-000000000001','work-1','batch-1','REVIEW',1,'anthropic','claude-sonnet-5','standard','0.1.0',
repeat('a',64),now(),100,20,0,10,'{"5m":10}', 'MEASURED','response-1','CALCULATED',0.001000000000,'USD','USEFUL',
'00000000-0000-4000-8000-000000000002','receipt-1');
INSERT INTO consumption_test.model_usage_reclassifications
(usage_event_id,expense_class,wasted_reason,decided_at,decision_ref,correlation_id)
VALUES(1,'WASTED','FAILED_ATTEMPT',now()+interval '1 year','decision-a','00000000-0000-4000-8000-000000000002');
INSERT INTO consumption_test.model_usage_reclassifications
(usage_event_id,expense_class,decided_at,decision_ref,correlation_id)
VALUES(1,'USEFUL',now()-interval '1 year','decision-b','00000000-0000-4000-8000-000000000002');
DO $$
DECLARE actual text;
BEGIN
 SELECT effective_expense_class INTO actual FROM consumption_test.model_usage_effective_class WHERE id=1;
 IF actual<>'USEFUL' THEN RAISE EXCEPTION 'LATEST_INSERT_DID_NOT_WIN';END IF;
 IF NOT EXISTS(SELECT 1 FROM consumption_test.model_usage_by_stage WHERE stage='REVIEW' AND calls=1)
 THEN RAISE EXCEPTION 'STAGE_VIEW_FAILURE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM consumption_test.model_usage_by_lot WHERE calls=1)
 THEN RAISE EXCEPTION 'LOT_VIEW_FAILURE'; END IF;
 IF NOT EXISTS(SELECT 1 FROM consumption_test.model_usage_by_order WHERE calls=1)
 THEN RAISE EXCEPTION 'ORDER_VIEW_FAILURE'; END IF;
END $$;
DO $$
DECLARE tbl text;statement text;
BEGIN
 FOR tbl IN SELECT unnest(ARRAY['model_usage_events','model_usage_reclassifications']) LOOP
  FOREACH statement IN ARRAY ARRAY['UPDATE','DELETE','TRUNCATE'] LOOP
   BEGIN
    IF statement='UPDATE' THEN
      EXECUTE format('UPDATE consumption_test.%I SET updated_at=now()',tbl);
    ELSIF statement='DELETE' THEN
      EXECUTE format('DELETE FROM consumption_test.%I',tbl);
    ELSE
      EXECUTE format('TRUNCATE consumption_test.%I CASCADE',tbl);
    END IF;
    RAISE EXCEPTION 'MUTATION_WAS_ALLOWED';
   EXCEPTION WHEN SQLSTATE '55000' THEN NULL; WHEN OTHERS THEN RAISE;
   END;
  END LOOP;
 END LOOP;
END $$;
DO $$
BEGIN
 BEGIN
  INSERT INTO consumption_test.model_usage_events
  (event_id,order_ref,lot_ref,stage,attempt,provider,model,service_tier,pricing_version,price_row_sha256,
  occurred_at,measurement,cost_status,currency,expense_class,correlation_id,worker_receipt_ref,wasted_reason)
  VALUES('00000000-0000-4000-8000-000000000003','w','b','PLAN',1,'openai','gpt-5.6-terra','standard','0.1.0',
  repeat('a',64),now(),'UNMEASURED','UNMEASURED','USD','WASTED','00000000-0000-4000-8000-000000000002','r',NULL);
  RAISE EXCEPTION 'WASTED_WITHOUT_REASON_ACCEPTED';
 EXCEPTION WHEN SQLSTATE '23514' THEN NULL; WHEN OTHERS THEN RAISE; END;
 BEGIN
  INSERT INTO consumption_test.model_usage_events
  (event_id,order_ref,lot_ref,stage,attempt,provider,model,service_tier,pricing_version,price_row_sha256,
  occurred_at,measurement,cost_status,cost,currency,expense_class,correlation_id,worker_receipt_ref)
  VALUES('00000000-0000-4000-8000-000000000004','w','b','PLAN',1,'openai','gpt-5.6-terra','standard','0.1.0',
  repeat('a',64),now(),'MEASURED','CALCULATED',0.000000000100,'USD','USEFUL','00000000-0000-4000-8000-000000000002','r');
  RAISE EXCEPTION 'NULL_TOKENS_ACCEPTED';
 EXCEPTION WHEN SQLSTATE '23514' THEN NULL; WHEN OTHERS THEN RAISE; END;
 BEGIN
  INSERT INTO consumption_test.model_usage_events
  (event_id,order_ref,lot_ref,stage,attempt,provider,model,service_tier,pricing_version,price_row_sha256,
  occurred_at,measurement,cost_status,currency,expense_class,correlation_id,worker_receipt_ref)
  VALUES('00000000-0000-4000-8000-000000000005','w','b','PLAN',1,'openai','gpt-5.6-terra','standard','0.1.0',
  repeat('a',64),now(),'UNMEASURED','UNMEASURED','usd','USEFUL','00000000-0000-4000-8000-000000000002','r');
  RAISE EXCEPTION 'LOWERCASE_CURRENCY_ACCEPTED';
 EXCEPTION WHEN SQLSTATE '23514' THEN NULL; WHEN OTHERS THEN RAISE; END;
 BEGIN
  INSERT INTO consumption_test.model_usage_events
  (event_id,order_ref,lot_ref,stage,attempt,provider,model,service_tier,pricing_version,price_row_sha256,
  occurred_at,measurement,cost_status,currency,expense_class,correlation_id,worker_receipt_ref,
  cache_write_tokens,cache_write_ttl_breakdown)
  VALUES('00000000-0000-4000-8000-000000000006','w','b','PLAN',1,'openai','gpt-5.6-terra','standard','0.1.0',
  repeat('a',64),now(),'UNMEASURED','UNMEASURED','USD','USEFUL','00000000-0000-4000-8000-000000000002','r',
  10,'{"30m":999}');
  RAISE EXCEPTION 'TTL_OVERFLOW_ACCEPTED';
 EXCEPTION WHEN SQLSTATE '23514' THEN NULL; WHEN OTHERS THEN RAISE; END;
END $$;
