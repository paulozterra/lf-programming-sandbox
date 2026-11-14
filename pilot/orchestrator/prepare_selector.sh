#!/usr/bin/env bash
# T9.3: one authoritative loopback-only selector setup for CI and T7.
set -euo pipefail
# F5's frozen historical packet uses the original pinned selector without T1
# extension. That legacy mode is explicit and remains in this ONE setup script.
if [[ "${1:-}" != "" && "${1:-}" != "--legacy" && "${1:-}" != "--enable-t1" && "${1:-}" != "--bootstrap-only" && "${1:-}" != "--backend" ]] || [[ $# -gt 1 ]]; then
  echo SELECTOR_PREPARACION_MODO_INVALIDO >&2
  exit 2
fi
legacy="NO"
if [[ "${1:-}" == "--legacy" ]]; then legacy="YES"; fi
export SELECTOR_EXP_DISPOSABLE_DB=YES
export SELECTOR_EXP_TEST_DSN='postgresql://pilot:pilot@127.0.0.1:5432/selector_exp_test_cp33'
export ATOMIZE_T1_SELECTOR=YES
export PGPASSWORD=pilot
if [[ -n "${GITHUB_ENV:-}" ]]; then
  {
    printf 'SELECTOR_EXP_DISPOSABLE_DB=YES\n'
    printf 'SELECTOR_EXP_TEST_DSN=%s\n' "$SELECTOR_EXP_TEST_DSN"
    printf 'ATOMIZE_T1_SELECTOR=YES\n'
    printf 'PGPASSWORD=pilot\n'
  } >> "$GITHUB_ENV"
fi
# The historical CI performs bare bootstrap, then backend insertion,
# then T1 patterns. These transitions remain in the same canonical script.
if [[ "${1:-}" == "--backend" ]]; then
  pg_isready -h 127.0.0.1 -p 5432 -U pilot -d selector_exp_test_cp33
  psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -U pilot -d selector_exp_test_cp33 -c \
    "INSERT INTO public.lf_project_area_pattern_exp(project_ref,area,path_prefix) VALUES ('lf_java','BACKEND','apps/time-service/src/main/java/') ON CONFLICT DO NOTHING"
  echo SELECTOR_SHARED_BACKEND_READY
  exit 0
fi
# Upgrade an existing shared legacy selector ONLY after frozen regressions.
# Same recipe owns the environment, bootstrap and pattern transition.
if [[ "${1:-}" == "--enable-t1" ]]; then
  pg_isready -h 127.0.0.1 -p 5432 -U pilot -d selector_exp_test_cp33
  python3 -m pilot.orchestrator.selector_db --t1-patterns
  echo SELECTOR_SHARED_T1_READY
  exit 0
fi
docker run --detach --rm --name selector-disposable-db --network host \
  -e POSTGRES_USER=pilot -e POSTGRES_PASSWORD=pilot \
  -e POSTGRES_DB=selector_exp_test_cp33 \
  -e POSTGRES_INITDB_ARGS=--locale=C \
  postgres:17 -c listen_addresses=127.0.0.1
for attempt in $(seq 1 40); do
  if pg_isready -h 127.0.0.1 -p 5432 -U pilot -d selector_exp_test_cp33 >/dev/null 2>&1; then break; fi
  sleep 1
done
pg_isready -h 127.0.0.1 -p 5432 -U pilot -d selector_exp_test_cp33
python3 -m pilot.orchestrator.selector_db
if [[ "$legacy" == "NO" && "${1:-}" != "--bootstrap-only" ]]; then
  python3 -m pilot.orchestrator.selector_db --t1-patterns
fi
if [[ "${1:-}" != "--bootstrap-only" ]]; then
  psql -X -v ON_ERROR_STOP=1 -h 127.0.0.1 -U pilot -d selector_exp_test_cp33 -c \
    "INSERT INTO public.lf_project_area_pattern_exp(project_ref,area,path_prefix) VALUES ('lf_java','BACKEND','apps/time-service/src/main/java/') ON CONFLICT DO NOTHING"
fi
echo SELECTOR_SHARED_PREP_PASS
