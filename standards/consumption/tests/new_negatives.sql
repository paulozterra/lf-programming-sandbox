-- Tests de coste no medido y semántica de gasto. Cada excepción debe ser CHECK 23514.
DO $$
BEGIN
 BEGIN
  INSERT INTO consumption_test.model_usage_events
  (event_id,work_request_ref,work_batch_ref,execution_stage,attempt,provider,model,service_tier,pricing_version,price_row_sha256,occurred_at,measurement,cost_status,cost,currency,expense_class,correlation_id,worker_receipt_ref)
  VALUES('00000000-0000-4000-8000-000000000008','w','b','PLAN',1,'openai','gpt-6.1-sol','standard','0.1.0',repeat('a',64),now(),'UNMEASURED','UNMEASURED',99,'USD','USEFUL','00000000-0000-4000-8000-000000000002','r');
  RAISE EXCEPTION 'B4_INVALID_COST_ACCEPTED';
 EXCEPTION WHEN SQLSTATE '23514' THEN NULL; WHEN OTHERS THEN RAISE; END;
 BEGIN
  INSERT INTO consumption_test.model_usage_events
  (event_id,work_request_ref,work_batch_ref,execution_stage,attempt,provider,model,service_tier,pricing_version,price_row_sha256,occurred_at,measurement,cost_status,currency,expense_class,wasted_reason,correlation_id,worker_receipt_ref)
  VALUES('00000000-0000-4000-8000-000000000009','w','b','PLAN',1,'openai','gpt-6.1-sol','standard','0.1.0',repeat('a',64),now(),'UNMEASURED','UNMEASURED','USD','USEFUL','FAILED_ATTEMPT','00000000-0000-4000-8000-000000000002','r');
  RAISE EXCEPTION 'M1_USEFUL_REASON_ACCEPTED';
 EXCEPTION WHEN SQLSTATE '23514' THEN NULL; WHEN OTHERS THEN RAISE; END;
 BEGIN
  INSERT INTO consumption_test.model_usage_events
  (event_id,work_request_ref,work_batch_ref,execution_stage,attempt,provider,model,service_tier,pricing_version,price_row_sha256,occurred_at,measurement,cost_status,currency,expense_class,cache_write_ttl_breakdown,correlation_id,worker_receipt_ref)
  VALUES('00000000-0000-4000-8000-000000000010','w','b','PLAN',1,'openai','gpt-6.1-sol','standard','0.1.0',repeat('a',64),now(),'UNMEASURED','UNMEASURED','USD','USEFUL','{"30m":10}','00000000-0000-4000-8000-000000000002','r');
  RAISE EXCEPTION 'M2_TTL_WITHOUT_TOTAL_ACCEPTED';
 EXCEPTION WHEN SQLSTATE '23514' THEN NULL; WHEN OTHERS THEN RAISE; END;
 BEGIN
  INSERT INTO consumption_test.model_usage_reclassifications
  (usage_event_id,expense_class,wasted_reason,decision_ref,correlation_id)
  VALUES(1,'USEFUL','FAILED_ATTEMPT','invalid','00000000-0000-4000-8000-000000000002');
  RAISE EXCEPTION 'M1_USEFUL_RECLASS_REASON_ACCEPTED';
 EXCEPTION WHEN SQLSTATE '23514' THEN NULL; WHEN OTHERS THEN RAISE; END;
END $$;
