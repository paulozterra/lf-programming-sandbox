"""Invariantes L1 de C8 compartidas por los validadores de catálogo y C9.

Los valores negociables viven exclusivamente en catalog.json.
"""
NON_WAIVABLE = frozenset({
    "STD-GEN-03", "STD-GEN-04", "STD-GEN-05", "STD-GEN-06", "STD-GEN-07",
    "STD-DB-06", "STD-DB-08", "STD-API-04", "STD-GIT-03", "STD-SB-02",
    "STD-SEC-01", "STD-SEC-02", "STD-SEC-04", "STD-AUD-01", "STD-AUD-03",
    "STD-CONS-01", "STD-CONS-02", "STD-CONS-03", "STD-CONS-04", "STD-MSG-02",
})
