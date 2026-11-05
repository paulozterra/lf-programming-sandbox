from __future__ import annotations

from dataclasses import dataclass
from typing import Iterable


RECOVERABLE_SCHEMA_SQLSTATES = frozenset({"42703", "42P01", "23514"})


class SchemaObservationRequired(RuntimeError):
    """Raised when a governed query would use a column not observed from catalog readback."""


@dataclass(frozen=True)
class ObservedRelation:
    schema: str
    table: str
    columns: frozenset[str]

    @classmethod
    def from_catalog(cls, schema: str, table: str, columns: Iterable[str]) -> "ObservedRelation":
        observed = frozenset(column for column in columns if isinstance(column, str) and column)
        if not observed:
            raise SchemaObservationRequired(f"no catalog columns observed for {schema}.{table}")
        return cls(schema=schema, table=table, columns=observed)

    def require(self, *columns: str) -> tuple[str, ...]:
        requested = tuple(columns)
        missing = [column for column in requested if column not in self.columns]
        if missing:
            raise SchemaObservationRequired(
                f"unobserved columns for {self.schema}.{self.table}: {','.join(sorted(missing))}"
            )
        return requested


def schema_error_requires_reobservation(sqlstate: str | None) -> bool:
    """Fail closed: known schema/contract errors require fresh catalog observation before retry."""
    return sqlstate in RECOVERABLE_SCHEMA_SQLSTATES
