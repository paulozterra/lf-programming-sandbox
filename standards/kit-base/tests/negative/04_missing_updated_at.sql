CREATE TABLE ${schema}.missing_times(id bigint GENERATED ALWAYS AS IDENTITY PRIMARY KEY,created_at timestamptz NOT NULL DEFAULT now());
