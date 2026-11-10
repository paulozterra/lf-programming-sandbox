-- LOCAL DISPOSABLE SELECTOR EXP ONLY. Never apply on Supabase.
-- Each project/area may bind multiple skill_code@skill_version.
-- Priorities are explicit positive integers: 1 is highest.
-- NULL is allowed in the fixture so the resolver can demonstrate fail-closed blocking.
CREATE TABLE public.project_stack_binding_exp (
 project_ref text NOT NULL,
 area text NOT NULL CHECK (area IN ('BACKEND','FRONTEND','DATA')),
 skill_code text NOT NULL,
 skill_version text NOT NULL,
 skill_sha256 text NOT NULL CHECK (skill_sha256 ~ '^[0-9a-f]{64}$'),
 priority integer NULL CHECK(priority > 0),
 PRIMARY KEY(project_ref,area,skill_code,skill_version)
);
-- Runtime resolver independently checks non-NULL and unique priority for every area.
