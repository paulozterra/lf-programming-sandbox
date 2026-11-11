-- Source CHECK constraints relevant to the minimized selector fields.
ALTER TABLE public.lf_profile_selection_registry_v1 ADD CONSTRAINT selector_descriptor_status CHECK (descriptor_status IN ('CURRENT','STALE_SOURCE_CHANGED'));
ALTER TABLE public.lf_profile_selection_registry_v1 ADD CONSTRAINT selector_source_kind CHECK (source_kind IN ('GITHUB_SKILL','LF_ACTIVOS_RAW_PAYLOAD'));
ALTER TABLE public.lf_profile_selector_policy_v1 ADD CONSTRAINT selector_channels CHECK (cardinality(channels)>0 AND channels <@ ARRAY['PRODUCTO','PROGRAMACION','OPERACIONES']::text[]);
ALTER TABLE public.lf_profile_selector_policy_v1 ADD CONSTRAINT selector_entry_policy CHECK (entry_policy IN ('DIRECT','DERIVATION_ONLY'));
ALTER TABLE public.lf_profile_write_authority_v1 ADD CONSTRAINT selector_authority_status CHECK (status IN ('ACTIVE','PROPOSED','RETIRED'));
