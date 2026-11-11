# CP3.1 — inventario fijado de productores LF

Commit origen: `882c7213f83887952a99ad0793174d535eb91233`
Repositorio origen: `cristhianlujan/claude-persona-lf-patch`
Destino: `pilot/lf_producers_pinned/`

Criterio: scripts candidatos PG-02 a PG-14, selector experimental, puente PG-04→PG-07 y cadena H4 EX6. Incluye pruebas, contratos/esquemas `.json`/`.sql` y fixtures de prueba referenciables. No incluye `profiles/`, `vendor/`, archivos `.age` ni claves.

Los productores se copian sin modificar. El orquestador solo los importará en etapas posteriores.

## pg02 (22 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/pg01_c4_readback_candidate_v1.sql` → `pilot/lf_producers_pinned/pg02/pg01_c4_readback_candidate_v1.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/pg01_technical_frame_v3_candidate_contract.json` → `pilot/lf_producers_pinned/pg02/pg01_technical_frame_v3_candidate_contract.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/pg01_technical_frame_v3_candidate_v1.py` → `pilot/lf_producers_pinned/pg02/pg01_technical_frame_v3_candidate_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/pg02_c4_evidence_adapter_v1.py` → `pilot/lf_producers_pinned/pg02/pg02_c4_evidence_adapter_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/pg02_classification_outcome_v1.py` → `pilot/lf_producers_pinned/pg02/pg02_classification_outcome_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/pg02_classifier_v1.py` → `pilot/lf_producers_pinned/pg02/pg02_classifier_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/pg02_pg00_bridge_v1.py` → `pilot/lf_producers_pinned/pg02/pg02_pg00_bridge_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/pg02_scope_isolation_v2.py` → `pilot/lf_producers_pinned/pg02/pg02_scope_isolation_v2.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_h2c4_pg03_c6_integration_v1.py` → `pilot/lf_producers_pinned/pg02/test_h2c4_pg03_c6_integration_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg01_c4_readback_candidate_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg01_c4_readback_candidate_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg01_c4_six_source_frame_synthetic_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg01_c4_six_source_frame_synthetic_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg01_technical_frame_v3_candidate_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg01_technical_frame_v3_candidate_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg02_c4_evidence_adapter_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg02_c4_evidence_adapter_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg02_classification_outcome_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg02_classification_outcome_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg02_classifier_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg02_classifier_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg02_domain_stack_layers_adversarial_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg02_domain_stack_layers_adversarial_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg02_h2c4_handoff_boundary_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg02_h2c4_handoff_boundary_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg02_independent_findings_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg02_independent_findings_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg02_pg00_bridge_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg02_pg00_bridge_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg02_pg01_binding_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg02_pg01_binding_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg02_scope_isolation_v2.py` → `pilot/lf_producers_pinned/pg02/test_pg02_scope_isolation_v2.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02/test_pg02_stack_layers_adversarial_v1.py` → `pilot/lf_producers_pinned/pg02/test_pg02_stack_layers_adversarial_v1.py` — prueba

## pg02_qualification (1 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg02_qualification/test_pg02_c5_independent_sample_v1.py` → `pilot/lf_producers_pinned/pg02_qualification/test_pg02_c5_independent_sample_v1.py` — prueba

## pg03_stack_source_candidate (4 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_stack_source_candidate/pg03_stack_source_v1.py` → `pilot/lf_producers_pinned/pg03_stack_source_candidate/pg03_stack_source_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_stack_source_candidate/test_pg03_stack_lock_v1.py` → `pilot/lf_producers_pinned/pg03_stack_source_candidate/test_pg03_stack_lock_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_stack_source_candidate/test_pg03_stack_semantics_v1.py` → `pilot/lf_producers_pinned/pg03_stack_source_candidate/test_pg03_stack_semantics_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_stack_source_candidate/test_pg03_stack_source_v1.py` → `pilot/lf_producers_pinned/pg03_stack_source_candidate/test_pg03_stack_source_v1.py` — prueba

## pg03_strategy_candidate (32 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_architecture_d15_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_architecture_d15_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_assurance_envelope_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_assurance_envelope_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_c2_catalog_adapter_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_c2_catalog_adapter_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_c2_l3_type_b_binding_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_c2_l3_type_b_binding_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_c2_precedence_candidate_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_c2_precedence_candidate_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_c2_skill_receipt_binding_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_c2_skill_receipt_binding_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_c9_real_runtime_readiness_v1.sql` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_c9_real_runtime_readiness_v1.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_c9_subject_binding_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_c9_subject_binding_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_domain_judges_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_domain_judges_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_exception_routing_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_exception_routing_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_handoff_boundary_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_handoff_boundary_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_reuse_binding_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_reuse_binding_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_semantic_adapter_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_semantic_adapter_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_strategy_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_strategy_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/pg03_sufficiency_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/pg03_sufficiency_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg02_pg03_strategy_chain_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg02_pg03_strategy_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_analysis_rule_projection_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_analysis_rule_projection_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_architecture_d15_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_architecture_d15_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_assurance_envelope_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_assurance_envelope_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_c2_catalog_adapter_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_c2_catalog_adapter_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_c2_l3_type_b_binding_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_c2_l3_type_b_binding_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_c2_precedence_candidate_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_c2_precedence_candidate_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_c2_skill_receipt_binding_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_c2_skill_receipt_binding_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_c5_projection_integrity_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_c5_projection_integrity_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_c9_subject_binding_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_c9_subject_binding_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_domain_judges_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_domain_judges_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_exception_routing_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_exception_routing_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_handoff_boundary_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_handoff_boundary_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_reuse_binding_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_reuse_binding_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_semantic_adapter_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_semantic_adapter_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_strategy_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_strategy_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg03_strategy_candidate/test_pg03_sufficiency_v1.py` → `pilot/lf_producers_pinned/pg03_strategy_candidate/test_pg03_sufficiency_v1.py` — prueba

## pg04_semantic_partition_candidate (22 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/analysis_trial_b2b_app_shell_unadmitted_v1.json` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/analysis_trial_b2b_app_shell_unadmitted_v1.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/fixtures/programming_synthetic_lab_packet_v1.json` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/fixtures/programming_synthetic_lab_packet_v1.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/test_analysis_fresh_request_b2b_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/test_analysis_fresh_request_b2b_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tests/test_pg03_pg04_exact_handoff_bridge_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tests/test_pg03_pg04_exact_handoff_bridge_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tests/test_pg04_definition_of_done_candidate_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tests/test_pg04_definition_of_done_candidate_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tests/test_pg04_independent_review_request_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tests/test_pg04_independent_review_request_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tests/test_pg04_local_semantic_judge_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tests/test_pg04_local_semantic_judge_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tests/test_pg04_partition_admission_probe_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tests/test_pg04_partition_admission_probe_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tests/test_pg04_remaining_edges_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tests/test_pg04_remaining_edges_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tests/test_pg04_semantic_partition_candidate_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tests/test_pg04_semantic_partition_candidate_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tests/test_pg_programming_offline_lab_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tests/test_pg_programming_offline_lab_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg03_pg04_exact_handoff_bridge_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg03_pg04_exact_handoff_bridge_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg04_c6_repartition_proposal_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg04_c6_repartition_proposal_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg04_c7_coverage_dossier_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg04_c7_coverage_dossier_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg04_definition_of_done_candidate_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg04_definition_of_done_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg04_independent_review_request_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg04_independent_review_request_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg04_local_semantic_judge_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg04_local_semantic_judge_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg04_partition_admission_probe_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg04_partition_admission_probe_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg04_pg05_exit_candidate_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg04_pg05_exit_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg04_pg07_budget_feedback_candidate_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg04_pg07_budget_feedback_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg04_semantic_partition_candidate_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg04_semantic_partition_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg04_semantic_partition_candidate/tools/pg_programming_offline_lab_v1.py` → `pilot/lf_producers_pinned/pg04_semantic_partition_candidate/tools/pg_programming_offline_lab_v1.py` — productor

## pg05_target_binding_candidate (7 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg05_target_binding_candidate/tests/test_pg05_chain_c1_c5_v1.py` → `pilot/lf_producers_pinned/pg05_target_binding_candidate/tests/test_pg05_chain_c1_c5_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg05_target_binding_candidate/tools/pg05_c1_target_binding_preflight_v1.py` → `pilot/lf_producers_pinned/pg05_target_binding_candidate/tools/pg05_c1_target_binding_preflight_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg05_target_binding_candidate/tools/pg05_c2_write_scope_candidate_v1.py` → `pilot/lf_producers_pinned/pg05_target_binding_candidate/tools/pg05_c2_write_scope_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg05_target_binding_candidate/tools/pg05_c3_collision_lock_plan_candidate_v1.py` → `pilot/lf_producers_pinned/pg05_target_binding_candidate/tools/pg05_c3_collision_lock_plan_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg05_target_binding_candidate/tools/pg05_c4_write_boundary_preflight_v1.py` → `pilot/lf_producers_pinned/pg05_target_binding_candidate/tools/pg05_c4_write_boundary_preflight_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg05_target_binding_candidate/tools/pg05_c5_independent_assurance_request_v1.py` → `pilot/lf_producers_pinned/pg05_target_binding_candidate/tools/pg05_c5_independent_assurance_request_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg05_target_binding_candidate/tools/pg05_pg06_exit_candidate_v1.py` → `pilot/lf_producers_pinned/pg05_target_binding_candidate/tools/pg05_pg06_exit_candidate_v1.py` — productor

## pg06_preflight_candidate (6 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg06_preflight_candidate/tests/test_pg06_c1_c5_chain_v1.py` → `pilot/lf_producers_pinned/pg06_preflight_candidate/tests/test_pg06_c1_c5_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg06_preflight_candidate/tools/pg06_c1_currentness_reuse_candidate_v1.py` → `pilot/lf_producers_pinned/pg06_preflight_candidate/tools/pg06_c1_currentness_reuse_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg06_preflight_candidate/tools/pg06_c2_toolchain_environment_candidate_v1.py` → `pilot/lf_producers_pinned/pg06_preflight_candidate/tools/pg06_c2_toolchain_environment_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg06_preflight_candidate/tools/pg06_c3_reversibility_plan_candidate_v1.py` → `pilot/lf_producers_pinned/pg06_preflight_candidate/tools/pg06_c3_reversibility_plan_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg06_preflight_candidate/tools/pg06_c4_baseline_capture_candidate_v1.py` → `pilot/lf_producers_pinned/pg06_preflight_candidate/tools/pg06_c4_baseline_capture_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg06_preflight_candidate/tools/pg06_c5_independent_assurance_request_v1.py` → `pilot/lf_producers_pinned/pg06_preflight_candidate/tools/pg06_c5_independent_assurance_request_v1.py` — productor

## pg07_worker_candidate (22 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/fixtures/ex5c_owner_attempt_decision_v1.json` → `pilot/lf_producers_pinned/pg07_worker_candidate/fixtures/ex5c_owner_attempt_decision_v1.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/fixtures/lf-evidence-bundle-v1.json` → `pilot/lf_producers_pinned/pg07_worker_candidate/fixtures/lf-evidence-bundle-v1.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/fixtures/lf-evidence-bundle-v2.json` → `pilot/lf_producers_pinned/pg07_worker_candidate/fixtures/lf-evidence-bundle-v2.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/fixtures/lf-evidence-bundle-v3.json` → `pilot/lf_producers_pinned/pg07_worker_candidate/fixtures/lf-evidence-bundle-v3.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tests/test_ex5c_real_evidence_chain_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tests/test_ex5c_real_evidence_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tests/test_pg07_c1_c6_chain_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tests/test_pg07_c1_c6_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tests/test_pg07_ex5c_format_remediation_v3_adapter_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tests/test_pg07_ex5c_format_remediation_v3_adapter_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tests/test_pg07_real_worker_evidence_adapter_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tests/test_pg07_real_worker_evidence_adapter_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tests/test_pg08_ex5c_v2_format_lint_adapter_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tests/test_pg08_ex5c_v2_format_lint_adapter_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tests/test_pg08_ex5c_v3_candidate_bridge_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tests/test_pg08_ex5c_v3_candidate_bridge_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tests/test_pg09_pg10_ex5c_owner_decision_bridge_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tests/test_pg09_pg10_ex5c_owner_decision_bridge_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg07_c1_worker_dispatch_plan_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg07_c1_worker_dispatch_plan_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg07_c2_task_batch_projection_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg07_c2_task_batch_projection_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg07_c3_context_budget_projection_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg07_c3_context_budget_projection_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg07_c4_contract_first_standards_candidate_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg07_c4_contract_first_standards_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg07_c5_iteration_guard_candidate_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg07_c5_iteration_guard_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg07_c6_worker_batch_evidence_candidate_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg07_c6_worker_batch_evidence_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg07_ex5c_format_remediation_v3_adapter_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg07_ex5c_format_remediation_v3_adapter_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg07_real_worker_evidence_adapter_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg07_real_worker_evidence_adapter_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg08_ex5c_v2_format_lint_adapter_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg08_ex5c_v2_format_lint_adapter_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg08_ex5c_v3_candidate_bridge_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg08_ex5c_v3_candidate_bridge_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg07_worker_candidate/tools/pg09_pg10_ex5c_owner_decision_bridge_v1.py` → `pilot/lf_producers_pinned/pg07_worker_candidate/tools/pg09_pg10_ex5c_owner_decision_bridge_v1.py` — productor

## pg08_build_candidate (10 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg08_build_candidate/tests/test_pg08_full_chain_v1.py` → `pilot/lf_producers_pinned/pg08_build_candidate/tests/test_pg08_full_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg08_build_candidate/tools/pg08_c1_build_compilation_candidate_v1.py` → `pilot/lf_producers_pinned/pg08_build_candidate/tools/pg08_c1_build_compilation_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg08_build_candidate/tools/pg08_c2_format_lint_delta_candidate_v1.py` → `pilot/lf_producers_pinned/pg08_build_candidate/tools/pg08_c2_format_lint_delta_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg08_build_candidate/tools/pg08_c3_typecheck_candidate_v1.py` → `pilot/lf_producers_pinned/pg08_build_candidate/tools/pg08_c3_typecheck_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg08_build_candidate/tools/pg08_c4_test_flyway_candidate_v1.py` → `pilot/lf_producers_pinned/pg08_build_candidate/tools/pg08_c4_test_flyway_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg08_build_candidate/tools/pg08_c5_contract_lint_candidate_v1.py` → `pilot/lf_producers_pinned/pg08_build_candidate/tools/pg08_c5_contract_lint_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg08_build_candidate/tools/pg08_c6_check_receipts_candidate_v1.py` → `pilot/lf_producers_pinned/pg08_build_candidate/tools/pg08_c6_check_receipts_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg08_build_candidate/tools/pg08_c6_final_receipts_candidate_v1.py` → `pilot/lf_producers_pinned/pg08_build_candidate/tools/pg08_c6_final_receipts_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg08_build_candidate/tools/pg08_c7_arch_boundary_candidate_v1.py` → `pilot/lf_producers_pinned/pg08_build_candidate/tools/pg08_c7_arch_boundary_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg08_build_candidate/tools/pg08_c8_iac_container_candidate_v1.py` → `pilot/lf_producers_pinned/pg08_build_candidate/tools/pg08_c8_iac_container_candidate_v1.py` — productor

## pg09_iteration_candidate (7 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg09_iteration_candidate/tests/test_pg09_iteration_chain_v1.py` → `pilot/lf_producers_pinned/pg09_iteration_candidate/tests/test_pg09_iteration_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg09_iteration_candidate/tools/pg09_c1_iteration_cost_governor_candidate_v1.py` → `pilot/lf_producers_pinned/pg09_iteration_candidate/tools/pg09_c1_iteration_cost_governor_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg09_iteration_candidate/tools/pg09_c1_iteration_cost_governor_candidate_v2.py` → `pilot/lf_producers_pinned/pg09_iteration_candidate/tools/pg09_c1_iteration_cost_governor_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg09_iteration_candidate/tools/pg09_c2_convergence_guard_candidate_v1.py` → `pilot/lf_producers_pinned/pg09_iteration_candidate/tools/pg09_c2_convergence_guard_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg09_iteration_candidate/tools/pg09_c3_quality_bypass_guard_candidate_v1.py` → `pilot/lf_producers_pinned/pg09_iteration_candidate/tools/pg09_c3_quality_bypass_guard_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg09_iteration_candidate/tools/pg09_c4_typed_escalation_candidate_v1.py` → `pilot/lf_producers_pinned/pg09_iteration_candidate/tools/pg09_c4_typed_escalation_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg09_iteration_candidate/tools/pg09_c5_adversarial_assurance_candidate_v1.py` → `pilot/lf_producers_pinned/pg09_iteration_candidate/tools/pg09_c5_adversarial_assurance_candidate_v1.py` — productor

## pg10_conflict_candidate (7 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg10_conflict_candidate/tests/test_pg10_decision_chain_v1.py` → `pilot/lf_producers_pinned/pg10_conflict_candidate/tests/test_pg10_decision_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg10_conflict_candidate/tools/pg10_c1_conflict_inventory_candidate_v1.py` → `pilot/lf_producers_pinned/pg10_conflict_candidate/tools/pg10_c1_conflict_inventory_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg10_conflict_candidate/tools/pg10_c2_precedence_legacy_guard_candidate_v1.py` → `pilot/lf_producers_pinned/pg10_conflict_candidate/tools/pg10_c2_precedence_legacy_guard_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg10_conflict_candidate/tools/pg10_c3_typed_decision_routing_candidate_v1.py` → `pilot/lf_producers_pinned/pg10_conflict_candidate/tools/pg10_c3_typed_decision_routing_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg10_conflict_candidate/tools/pg10_c4_human_decision_packet_candidate_v1.py` → `pilot/lf_producers_pinned/pg10_conflict_candidate/tools/pg10_c4_human_decision_packet_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg10_conflict_candidate/tools/pg10_c5_negative_assurance_candidate_v1.py` → `pilot/lf_producers_pinned/pg10_conflict_candidate/tools/pg10_c5_negative_assurance_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg10_conflict_candidate/tools/pg10_decision_lineage_dedup_candidate_v1.py` → `pilot/lf_producers_pinned/pg10_conflict_candidate/tools/pg10_decision_lineage_dedup_candidate_v1.py` — productor

## pg11_integrity_candidate (15 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tests/test_pg10_pg11_bridge_and_waiver_time_v1.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tests/test_pg10_pg11_bridge_and_waiver_time_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tests/test_pg11_integrity_chain_v1.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tests/test_pg11_integrity_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_c1_diff_hygiene_candidate_v1.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_c1_diff_hygiene_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_c1_diff_hygiene_candidate_v2.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_c1_diff_hygiene_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_c2_terminology_catalog_candidate_v1.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_c2_terminology_catalog_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_c2_terminology_catalog_candidate_v2.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_c2_terminology_catalog_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_c3_suppression_waiver_candidate_v1.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_c3_suppression_waiver_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_c3_suppression_waiver_candidate_v2.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_c3_suppression_waiver_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_c4_diff_requirement_batch_trace_candidate_v1.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_c4_diff_requirement_batch_trace_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_c4_diff_requirement_batch_trace_candidate_v2.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_c4_diff_requirement_batch_trace_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_c5_independent_reviewer_candidate_v1.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_c5_independent_reviewer_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_c5_independent_reviewer_candidate_v2.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_c5_independent_reviewer_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_integrity_extension_candidate_v1.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_integrity_extension_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_pg10_handoff_bridge_candidate_v1.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_pg10_handoff_bridge_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg11_integrity_candidate/tools/pg11_pg10_handoff_bridge_candidate_v2.py` → `pilot/lf_producers_pinned/pg11_integrity_candidate/tools/pg11_pg10_handoff_bridge_candidate_v2.py` — productor

## pg12_identity_candidate (13 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tests/test_pg12_identity_chain_v1.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tests/test_pg12_identity_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_c1_candidate_identity_v1.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_c1_candidate_identity_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_c1_candidate_identity_v2.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_c1_candidate_identity_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_c2_execution_inputs_usage_candidate_v1.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_c2_execution_inputs_usage_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_c2_execution_inputs_usage_candidate_v2.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_c2_execution_inputs_usage_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_c3_check_results_link_candidate_v1.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_c3_check_results_link_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_c3_check_results_link_candidate_v2.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_c3_check_results_link_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_c4_persistence_readback_request_candidate_v1.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_c4_persistence_readback_request_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_c4_persistence_readback_request_candidate_v2.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_c4_persistence_readback_request_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_disposable_postgres_readback_v1.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_disposable_postgres_readback_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_disposable_postgres_readback_v2.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_disposable_postgres_readback_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_git_identity_and_pg11_bridge_v1.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_git_identity_and_pg11_bridge_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg12_identity_candidate/tools/pg12_git_identity_and_pg11_bridge_v2.py` → `pilot/lf_producers_pinned/pg12_identity_candidate/tools/pg12_git_identity_and_pg11_bridge_v2.py` — productor

## pg13_freeze_candidate (13 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tests/test_pg13_disposable_git_enforcement_v1.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tests/test_pg13_disposable_git_enforcement_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tests/test_pg13_freeze_chain_v1.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tests/test_pg13_freeze_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_c1_freeze_intent_candidate_v1.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_c1_freeze_intent_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_c1_freeze_intent_candidate_v2.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_c1_freeze_intent_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_c2_rebuild_comparison_candidate_v1.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_c2_rebuild_comparison_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_c2_rebuild_comparison_candidate_v2.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_c2_rebuild_comparison_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_c3_mutation_block_candidate_v1.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_c3_mutation_block_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_c3_mutation_block_candidate_v2.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_c3_mutation_block_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_disposable_git_mutation_test_v1.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_disposable_git_mutation_test_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_ex5c_reconstructed_freeze_attack_v1.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_ex5c_reconstructed_freeze_attack_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_ex5c_reconstructed_freeze_attack_v2.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_ex5c_reconstructed_freeze_attack_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_pg12_exact_freeze_bridge_v1.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_pg12_exact_freeze_bridge_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg13_freeze_candidate/tools/pg13_pg12_exact_freeze_bridge_v2.py` → `pilot/lf_producers_pinned/pg13_freeze_candidate/tools/pg13_pg12_exact_freeze_bridge_v2.py` — productor

## pg14_testing_handoff_candidate (15 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tests/test_pg14_final_chain_v1.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tests/test_pg14_final_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_c1_testing_execution_contract_candidate_v1.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_c1_testing_execution_contract_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_c1_testing_execution_contract_candidate_v2.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_c1_testing_execution_contract_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_c2_completeness_guard_v1.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_c2_completeness_guard_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_c2_completeness_guard_v2.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_c2_completeness_guard_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_c2_testing_payload_candidate_v1.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_c2_testing_payload_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_c2_testing_payload_candidate_v2.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_c2_testing_payload_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_c3_testing_admission_readback_request_candidate_v1.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_c3_testing_admission_readback_request_candidate_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_c3_testing_admission_readback_request_candidate_v2.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_c3_testing_admission_readback_request_candidate_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_disposable_testing_readback_v1.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_disposable_testing_readback_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_disposable_testing_readback_v2.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_disposable_testing_readback_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_local_testing_receiver_v1.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_local_testing_receiver_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_local_testing_receiver_v2.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_local_testing_receiver_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_pg13_freeze_bridge_v1.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_pg13_freeze_bridge_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/pg14_testing_handoff_candidate/tools/pg14_pg13_freeze_bridge_v2.py` → `pilot/lf_producers_pinned/pg14_testing_handoff_candidate/tools/pg14_pg13_freeze_bridge_v2.py` — productor

## selector_experimental (30 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/SOURCE_PIN.json` → `pilot/lf_producers_pinned/selector_experimental/SOURCE_PIN.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/expected/catalog.json` → `pilot/lf_producers_pinned/selector_experimental/expected/catalog.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/expected/producto_1.json` → `pilot/lf_producers_pinned/selector_experimental/expected/producto_1.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/expected/producto_2.json` → `pilot/lf_producers_pinned/selector_experimental/expected/producto_2.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/expected/programacion_1.json` → `pilot/lf_producers_pinned/selector_experimental/expected/programacion_1.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/expected/programacion_2.json` → `pilot/lf_producers_pinned/selector_experimental/expected/programacion_2.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/expected/sin_canal.json` → `pilot/lf_producers_pinned/selector_experimental/expected/sin_canal.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/experimental/area_policy_exp.sql` → `pilot/lf_producers_pinned/selector_experimental/experimental/area_policy_exp.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/experimental/functions_exp.sql` → `pilot/lf_producers_pinned/selector_experimental/experimental/functions_exp.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/experimental/seed_profiles_exp.sql` → `pilot/lf_producers_pinned/selector_experimental/experimental/seed_profiles_exp.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/integration/pg05_profile_assignment_bridge_v1.py` → `pilot/lf_producers_pinned/selector_experimental/integration/pg05_profile_assignment_bridge_v1.py` — productor/puente
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/integration/test_pg04_pg07_selector_bridge_v1.py` → `pilot/lf_producers_pinned/selector_experimental/integration/test_pg04_pg07_selector_bridge_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/data/lf_activos.sql` → `pilot/lf_producers_pinned/selector_experimental/original/data/lf_activos.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/data/lf_operation_execution.sql` → `pilot/lf_producers_pinned/selector_experimental/original/data/lf_operation_execution.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/data/lf_profile_selection_registry_v1.sql` → `pilot/lf_producers_pinned/selector_experimental/original/data/lf_profile_selection_registry_v1.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/data/lf_profile_selector_policy_v1.sql` → `pilot/lf_producers_pinned/selector_experimental/original/data/lf_profile_selector_policy_v1.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/data/lf_profile_write_authority_v1.sql` → `pilot/lf_producers_pinned/selector_experimental/original/data/lf_profile_write_authority_v1.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/data/lf_router_action_registry.sql` → `pilot/lf_producers_pinned/selector_experimental/original/data/lf_router_action_registry.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/functions/lf_profile_execution_source_eligibility_v1.sql` → `pilot/lf_producers_pinned/selector_experimental/original/functions/lf_profile_execution_source_eligibility_v1.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/functions/lf_profile_selector_catalog_v1.sql` → `pilot/lf_producers_pinned/selector_experimental/original/functions/lf_profile_selector_catalog_v1.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/functions/lf_profile_selector_descriptor_sync_v1.sql` → `pilot/lf_producers_pinned/selector_experimental/original/functions/lf_profile_selector_descriptor_sync_v1.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/functions/lf_profile_selector_semantic_finalize_v1.sql` → `pilot/lf_producers_pinned/selector_experimental/original/functions/lf_profile_selector_semantic_finalize_v1.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/functions/lf_profile_selector_semantic_prepare_v2_3args.sql` → `pilot/lf_producers_pinned/selector_experimental/original/functions/lf_profile_selector_semantic_prepare_v2_3args.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/functions/lf_profile_selector_semantic_prepare_v2_4args.sql` → `pilot/lf_producers_pinned/selector_experimental/original/functions/lf_profile_selector_semantic_prepare_v2_4args.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/functions/lf_profile_selector_semantic_validate_v1.sql` → `pilot/lf_producers_pinned/selector_experimental/original/functions/lf_profile_selector_semantic_validate_v1.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/schema/bootstrap.sql` → `pilot/lf_producers_pinned/selector_experimental/original/schema/bootstrap.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/schema/constraints.sql` → `pilot/lf_producers_pinned/selector_experimental/original/schema/constraints.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/original/schema/tables.sql` → `pilot/lf_producers_pinned/selector_experimental/original/schema/tables.sql` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/tests/test_experimental.py` → `pilot/lf_producers_pinned/selector_experimental/tests/test_experimental.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/selector_experimental/tests/test_parity.py` → `pilot/lf_producers_pinned/selector_experimental/tests/test_parity.py` — prueba

## ex6_real_chain_candidate (20 archivos)

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/evidence/ex6_run_42707967927_receipt_index.json` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/evidence/ex6_run_42707967927_receipt_index.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/evidence/ex6_task_registration.json` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/evidence/ex6_task_registration.json` — contrato/esquema o fixture
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tests/test_ex6_bundle_index_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tests/test_ex6_bundle_index_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tests/test_ex6_chain_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tests/test_ex6_chain_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tests/test_ex6_evidence_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tests/test_ex6_evidence_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tests/test_ex6_local_v2.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tests/test_ex6_local_v2.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tests/test_ex6_n1_one_pass_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tests/test_ex6_n1_one_pass_v1.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tests/test_ex6_pg09_native_v2.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tests/test_ex6_pg09_native_v2.py` — prueba
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_build_lint_index_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_build_lint_index_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_build_lint_inputs_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_build_lint_inputs_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_local_freeze_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_local_freeze_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_n1_one_pass_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_n1_one_pass_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_n1_receipts_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_n1_receipts_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_one_pass_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_one_pass_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_pg06_evidence_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_pg06_evidence_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_pg07_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_pg07_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_pg12_pg13_v2.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_pg12_pg13_v2.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_real_chain_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_real_chain_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_real_world_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_real_world_v1.py` — productor
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/ex6_real_chain_candidate/tools/ex6_source_truth_v1.py` → `pilot/lf_producers_pinned/ex6_real_chain_candidate/tools/ex6_source_truth_v1.py` — productor

## Verificación

El manifiesto `SOURCE_PIN.json` se genera con `origin_path`, `destination_path` y `sha256` de cada copia. El test recalcula el SHA-256 y bloquea modificaciones, omisiones o rutas adicionales.

- `sandbox/lf_contract_gate_test/programming_agent_four_stage/c6_context_gate/context_gate_v1.py` → `pilot/lf_producers_pinned/c6_context_gate/context_gate_v1.py` — módulo/prueba importado por productor (dependencia adicional verificada)
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/c6_context_gate/checkpoint_bridge_v1.py` → `pilot/lf_producers_pinned/c6_context_gate/checkpoint_bridge_v1.py` — módulo/prueba importado por productor (dependencia adicional verificada)
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/c6_context_gate/test_context_gate_v1.py` → `pilot/lf_producers_pinned/c6_context_gate/test_context_gate_v1.py` — módulo/prueba importado por productor (dependencia adicional verificada)
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/c6_context_gate/test_checkpoint_bridge_v1.py` → `pilot/lf_producers_pinned/c6_context_gate/test_checkpoint_bridge_v1.py` — módulo/prueba importado por productor (dependencia adicional verificada)
- `sandbox/lf_contract_gate_test/programming_agent_four_stage/wave1_boundary_contracts/testing_admission_contract_v1.json` → `pilot/lf_producers_pinned/wave1_boundary_contracts/testing_admission_contract_v1.json` — contrato original (dependencia adicional verificada)
