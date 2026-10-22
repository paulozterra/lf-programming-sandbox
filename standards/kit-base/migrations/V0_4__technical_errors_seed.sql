INSERT INTO ${schema}.errors(error_code,technical_category,http_status,copy_status,is_active)
VALUES ('${trace_prefix}-TEC-001','INTERNAL',500,'PENDING_COPY',true),
('${trace_prefix}-TEC-002','SERVICE_UNAVAILABLE',503,'PENDING_COPY',true),
('${trace_prefix}-TEC-003','TIMEOUT',504,'PENDING_COPY',true),
('${trace_prefix}-TEC-004','INVALID_DATA',422,'PENDING_COPY',true),
('${trace_prefix}-TEC-005','FORBIDDEN',403,'PENDING_COPY',true),
('${trace_prefix}-TEC-006','NOT_FOUND',404,'PENDING_COPY',true)
ON CONFLICT(error_code) DO NOTHING;
