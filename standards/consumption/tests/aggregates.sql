-- Casos sintéticos adicionales del contrato de consumo C11.
INSERT INTO consumption_test.model_usage_events
(event_id,work_request_ref,work_batch_ref,execution_stage,attempt,provider,model,service_tier,pricing_version,price_row_sha256,occurred_at,measurement,cost_status,currency,expense_class,correlation_id,worker_receipt_ref)
VALUES('00000000-0000-4000-8000-000000000007','work-1','batch-1','REVIEW',2,'openai','gpt-6.1-sol','standard','0.1.0',repeat('a',64),now(),'UNMEASURED','UNMEASURED','USD','USEFUL','00000000-0000-4000-8000-000000000002','receipt-2');
DO $$
BEGIN
 IF NOT EXISTS (SELECT 1 FROM consumption_test.model_usage_by_stage WHERE execution_stage='REVIEW' AND calls=2 AND unmeasured_calls=1 AND cost=0.001000000000) THEN RAISE EXCEPTION 'AGGREGATE_STAGE_FAILURE'; END IF;
 IF NOT EXISTS (SELECT 1 FROM consumption_test.model_usage_by_work_batch WHERE calls=2 AND unmeasured_calls=1 AND cost=0.001000000000) THEN RAISE EXCEPTION 'AGGREGATE_BATCH_FAILURE'; END IF;
 IF NOT EXISTS (SELECT 1 FROM consumption_test.model_usage_by_work_request WHERE calls=2 AND unmeasured_calls=1 AND cost=0.001000000000) THEN RAISE EXCEPTION 'AGGREGATE_REQUEST_FAILURE'; END IF;
END $$;
