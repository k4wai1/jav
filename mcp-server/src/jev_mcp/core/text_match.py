"""Coincidencia tolerante de nombres y títulos estrictos. Puro, parametrizado.

Sin literales de app: `needle`/`expected` y los candidatos son parámetros.
"""
from __future__ import annotations

import re
import unicodedata


def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def skeleton(s: str) -> str:
    return re.sub(r"[aeiou\s]", "", norm(s))


def name_hit(needle: str, cand: dict) -> bool:
    """Tolerante: palabra len>2 en norm(texto+desc) o skeleton len>=3 contenido."""
    words = [w for w in norm(needle).split() if len(w) > 2]
    hay = f"{norm(cand.get('text'))} {norm(cand.get('desc'))}"
    for w in words:
        if w in hay:
            return True
        sk = skeleton(w)
        if len(sk) >= 3 and sk in skeleton(hay):
            return True
    return False


def title_matches_strict(expected: str, title: str) -> bool:
    """Igualdad en norm, o expected+apellido-simple / expected+(paréntesis).

    Ante la duda, False (abort seguro > acción equivocada).
    """
    a, b = norm(expected), norm(title or "")
    if not a or not b:
        return False
    if b == a:
        return True
    if b.startswith(a + "("):
        return True
    if b.startswith(a + " "):
        rest = b[len(a) + 1:].strip()
        if rest and " " not in rest:
            return True
    return False
