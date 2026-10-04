"""Contrato core/text_match.py: mecanismos parametrizados, datos genéricos."""
from jev_mcp.core.text_match import (
    name_hit,
    norm,
    skeleton,
    title_matches_strict,
)


def test_norm_skeleton():
    assert norm("García LÓPEZ") == "garcia lopez"
    assert skeleton("García") == "grc"


def test_title_strict_generic():
    assert title_matches_strict("Ana", "Ana")
    assert title_matches_strict("Ana", "Ána García")
    assert title_matches_strict("Ana", "Ana (trabajo)")
    assert not title_matches_strict("Ana", "Ána la del bar")
    assert not title_matches_strict("Ana", "Amigos de Ana")
    assert not title_matches_strict("Ana", "")
    assert not title_matches_strict("", "Ana")


def _cand(id, text="", desc=""):
    return {"id": id, "text": text, "desc": desc}


def test_name_hit_generic():
    assert name_hit("Ana", _cand("a", text="Ána"))
    assert name_hit("Ana", _cand("a", text="ANA"))
    assert not name_hit("Ana", _cand("a", text="Carlos"))
    assert not name_hit("An", _cand("a", text="An"))  # palabra len<=2 no cuenta
