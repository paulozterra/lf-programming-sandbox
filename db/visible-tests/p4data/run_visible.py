"""P4 visible check (DATA): the migration exists, applies on a fresh disposable
PostgreSQL database and creates a table with a `priority` column.
The hidden exam checks more behaviour derived from the request."""
import os
import subprocess
import uuid

DSN = "postgresql://pilot:pilot@127.0.0.1:5432/"
MIGRATION = "db/migration/V1__reminders_priority.sql"


def psql(db, *args):
    return subprocess.run(["psql", DSN + db, "-X", "-q", "-At", "-v", "ON_ERROR_STOP=1", *args],
                          capture_output=True, text=True, timeout=60)


assert os.path.isfile(MIGRATION), ("MIGRATION_MISSING", MIGRATION)
db = "v9_" + uuid.uuid4().hex[:12]
assert psql("pilot", "-c", "CREATE DATABASE " + db).returncode == 0, "CREATE_DB_FAIL"
try:
    r = psql(db, "-f", MIGRATION)
    assert r.returncode == 0, ("MIGRATION_APPLY_FAIL", r.stderr[-400:])
    r = psql(db, "-c", "select count(*) from information_schema.columns "
                       "where table_schema='public' and lower(column_name)='priority'")
    assert r.stdout.strip() == "1", ("PRIORITY_COLUMN_NOT_FOUND", r.stdout)
finally:
    psql("pilot", "-c", "DROP DATABASE IF EXISTS " + db + " WITH (FORCE)")
print("P4_DATA_VISIBLE_OK")
