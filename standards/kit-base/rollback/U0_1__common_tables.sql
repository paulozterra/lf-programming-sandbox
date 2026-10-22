DO $$
DECLARE t text; populated boolean;
BEGIN
 FOR t IN SELECT unnest(ARRAY['errors','error_occurrences','messages','audit_events','navigation_event_types','navigation_events','legal_documents','consents']) LOOP
  EXECUTE format('SELECT EXISTS(SELECT 1 FROM %I.%I LIMIT 1)', '${schema}', t) INTO populated;
  IF populated THEN RAISE EXCEPTION 'bootstrap rollback requires empty table %', t; END IF;
 END LOOP;
END $$;
DROP TABLE ${schema}.consents,${schema}.legal_documents,${schema}.navigation_events,${schema}.navigation_event_types,${schema}.audit_events,${schema}.messages,${schema}.error_occurrences,${schema}.errors;
