-- Experimental metadata only: no modifications to original tables.
CREATE TABLE public.lf_profile_area_policy_exp (
 profile_code text PRIMARY KEY REFERENCES public.lf_profile_selector_policy_v1(profile_code),
 areas jsonb NOT NULL,
 CHECK (jsonb_typeof(areas)='array' AND jsonb_array_length(areas)>0)
);
CREATE TABLE public.lf_project_area_pattern_exp (
 project_ref text NOT NULL, area text NOT NULL, path_prefix text NOT NULL,
 PRIMARY KEY(project_ref,area,path_prefix),
 CHECK (project_ref ~ '^[a-z0-9][a-z0-9_-]{1,80}$'),
 CHECK (area IN ('BACKEND','FRONTEND','DATA')),
 CHECK (left(path_prefix,1)<>'/' AND position('..' IN path_prefix)=0 AND position(chr(92) IN path_prefix)=0 AND right(path_prefix,1)='/')
);
-- Project A: Java/Angular/Flyway. Project B: Python/Vue/Alembic.
INSERT INTO public.lf_project_area_pattern_exp(project_ref,area,path_prefix) VALUES
 ('lf_java','BACKEND','src/main/java/'),
 ('lf_java','FRONTEND','web/src/'),
 ('lf_java','DATA','db/migration/'),
 ('lf_python','BACKEND','api/app/'),
 ('lf_python','FRONTEND','ui/src/'),
 ('lf_python','DATA','alembic/versions/');
INSERT INTO public.lf_profile_area_policy_exp(profile_code,areas) VALUES
 ('PERFIL-PROG-BACKEND-EXP','["BACKEND"]'::jsonb),
 ('PERFIL-PROG-BACKEND-SPRING-EXP','["BACKEND"]'::jsonb),
 ('PERFIL-PROG-FRONTEND-EXP','["FRONTEND"]'::jsonb),
 ('PERFIL-PROG-DATA-EXP','["DATA"]'::jsonb),
 ('PERFIL-PROG-BACKEND-NAME-FRONTEND-EXP','["FRONTEND"]'::jsonb);
