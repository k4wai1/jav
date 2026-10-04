"""Localización del título de pantalla. Pura, parametrizada.

El plugin pasa sus `rid_keys` (sufijos de resource_id propios de la app);
core no conoce ninguno. Estrategia: 1º por rid_keys, 2º por franja
superior (bounds.top < screen_height*top_frac).
"""
from __future__ import annotations

from .text_match import title_matches_strict


def find_title(state: dict, expected: str, *,
               rid_keys: tuple[str, ...], top_frac: float = 0.15) -> dict | None:
    """Título que matchea estricto, o None. Nunca nodos editables."""
    cands = state.get("candidates", [])
    for c in cands:
        if c.get("editable"):
            continue
        rid = c.get("resource_id") or ""
        if any(k in rid for k in rid_keys):
            if title_matches_strict(expected, c.get("text")):
                return c
    h = state.get("screen_height") or 0
    if h:
        top = h * top_frac
        for c in cands:
            if c.get("editable"):
                continue
            b = c.get("bounds") or [0, 0, 0, 0]
            if len(b) == 4 and b[1] < top and title_matches_strict(expected, c.get("text")):
                return c
    return None


def has_any_title(state: dict, *,
                  rid_keys: tuple[str, ...], top_frac: float = 0.15) -> bool:
    """¿Hay algún título de pantalla (estamos dentro de una vista)?"""
    h = state.get("screen_height") or 0
    for c in state.get("candidates", []):
        if c.get("editable"):
            continue
        rid = c.get("resource_id") or ""
        if any(k in rid for k in rid_keys):
            if (c.get("text") or "").strip():
                return True
    if h:
        top = h * top_frac
        for c in state.get("candidates", []):
            if c.get("editable"):
                continue
            b = c.get("bounds") or [0, 0, 0, 0]
            if len(b) == 4 and b[1] < top and (c.get("text") or "").strip():
                return True
    return False
