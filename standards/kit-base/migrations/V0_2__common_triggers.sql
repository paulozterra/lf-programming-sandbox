CREATE FUNCTION ${schema}.set_updated_at() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$ BEGIN NEW.updated_at := now(); RETURN NEW; END; $$;
CREATE FUNCTION ${schema}.reject_mutation() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$ BEGIN RAISE EXCEPTION 'append-only table' USING ERRCODE = '55000'; END; $$;
CREATE FUNCTION ${schema}.close_legal_document() RETURNS trigger LANGUAGE plpgsql SECURITY INVOKER AS $$
BEGIN
 IF TG_OP = 'DELETE' THEN RAISE EXCEPTION 'legal document cannot be deleted'; END IF;
 IF OLD.valid_to IS NOT NULL OR NEW.valid_to IS NULL OR NEW.valid_to <= OLD.valid_from THEN RAISE EXCEPTION 'only first valid_to closure allowed'; END IF;
 NEW.updated_at := now();
 IF (to_jsonb(NEW) - 'valid_to' - 'updated_at') IS DISTINCT FROM (to_jsonb(OLD) - 'valid_to' - 'updated_at') THEN RAISE EXCEPTION 'only valid_to may change'; END IF;
 RETURN NEW;
END; $$;
CREATE TRIGGER errors_updated_at BEFORE UPDATE ON ${schema}.errors FOR EACH ROW EXECUTE FUNCTION ${schema}.set_updated_at();
CREATE TRIGGER messages_updated_at BEFORE UPDATE ON ${schema}.messages FOR EACH ROW EXECUTE FUNCTION ${schema}.set_updated_at();
CREATE TRIGGER navigation_event_types_updated_at BEFORE UPDATE ON ${schema}.navigation_event_types FOR EACH ROW EXECUTE FUNCTION ${schema}.set_updated_at();
CREATE TRIGGER error_occurrences_immutable BEFORE UPDATE OR DELETE ON ${schema}.error_occurrences FOR EACH ROW EXECUTE FUNCTION ${schema}.reject_mutation();
CREATE TRIGGER audit_events_immutable BEFORE UPDATE OR DELETE ON ${schema}.audit_events FOR EACH ROW EXECUTE FUNCTION ${schema}.reject_mutation();
CREATE TRIGGER navigation_events_immutable BEFORE UPDATE OR DELETE ON ${schema}.navigation_events FOR EACH ROW EXECUTE FUNCTION ${schema}.reject_mutation();
CREATE TRIGGER consents_immutable BEFORE UPDATE OR DELETE ON ${schema}.consents FOR EACH ROW EXECUTE FUNCTION ${schema}.reject_mutation();
CREATE TRIGGER legal_documents_controlled BEFORE UPDATE OR DELETE ON ${schema}.legal_documents FOR EACH ROW EXECUTE FUNCTION ${schema}.close_legal_document();
REVOKE ALL ON ALL FUNCTIONS IN SCHEMA ${schema} FROM PUBLIC;
