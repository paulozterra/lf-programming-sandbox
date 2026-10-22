ALTER TABLE ${schema}.error_occurrences ADD CONSTRAINT fk_custom FOREIGN KEY(error_id) REFERENCES ${schema}.errors(id);
