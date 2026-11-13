"""Deterministic request -> fixture catalogue resolver; no semantic guessing."""
from __future__ import annotations

import json
from pathlib import Path
import re


class CatalogueBlocked(ValueError):
    pass


CODE = re.compile(r"[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+\Z")


def catalogue(root: Path) -> dict[str, Path]:
    base = root / "analysis/fixtures"
    if not base.is_dir() or base.is_symlink():
        raise CatalogueBlocked("PANTALLA_NO_EN_CATALOGO")
    result = {}
    for pin in sorted(base.glob("*/SOURCE_PIN.json")):
        if pin.is_symlink() or pin.parent.is_symlink():
            raise CatalogueBlocked("PANTALLA_NO_EN_CATALOGO")
        try:
            data = json.loads(pin.read_text("utf-8"))
        except (OSError, ValueError) as exc:
            raise CatalogueBlocked("PANTALLA_NO_EN_CATALOGO") from exc
        code = data.get("fixture_id")
        if not isinstance(code, str) or not CODE.fullmatch(code) or code in result:
            raise CatalogueBlocked("PANTALLA_NO_EN_CATALOGO")
        result[code] = pin.parent
    return result


def resolve(root: Path, raw: bytes) -> tuple[str, Path]:
    try:
        request = raw.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise CatalogueBlocked("PEDIDO_AMBIGUO") from exc
    if not request.strip():
        raise CatalogueBlocked("PEDIDO_AMBIGUO")
    names = catalogue(root)
    # Match entire identifiers, never substrings of another screen code.
    mentioned = [code for code in names
                 if re.search(r"(?<![A-Za-z0-9_-])" + re.escape(code)
                              + r"(?![A-Za-z0-9_-])", request)]
    if len(mentioned) > 1 or not mentioned:
        # A code-like token that does not exist is a different error from
        # a request without an unambiguous catalogue reference.
        unknown = [s for s in re.findall(
            r"(?<![A-Za-z0-9_-])[A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+(?![A-Za-z0-9_-])",
            request) if s not in names]
        if len(mentioned) == 0 and len(unknown) == 1:
            raise CatalogueBlocked("PANTALLA_NO_EN_CATALOGO")
        raise CatalogueBlocked("PEDIDO_AMBIGUO")
    return mentioned[0], names[mentioned[0]]
