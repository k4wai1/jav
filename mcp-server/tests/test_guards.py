"""Tests de compuertas deterministas (sin dispositivo ni Jev)."""
from jev_mcp.tasks.whatsapp import (
    find_chat_title,
    is_forbidden,
    name_hit,
    title_matches_strict,
)


def cand(id, text="", desc="", rid="", editable=False):
    return {"id": id, "text": text, "desc": desc, "resource_id": rid,
            "editable": editable, "label": text or desc}


def test_title_strict():
    assert title_matches_strict("Felix", "Felix")
    assert title_matches_strict("Felix", "Félix García")
    assert title_matches_strict("Felix", "Felix (trabajo)")
    assert not title_matches_strict("Felix", "Félix el del bar")
    assert not title_matches_strict("Felix", "Amigos de Felix")
    assert not title_matches_strict("Felix", "")
    assert not title_matches_strict("", "Felix")


def test_name_hit_variants():
    assert name_hit("Felix", cand("a", text="Félex"))
    assert name_hit("Felix", cand("a", text="FELIX"))
    assert name_hit("Felix", cand("a", text="felex"))
    assert not name_hit("Felix", cand("a", text="Carlos"))


def test_find_chat_title_rid():
    st = {"screen_height": 1600, "candidates": [
        cand("n_1", text="Felix", rid="com.whatsapp:id/contact_name"),
        cand("n_2", text="Buscar", rid="com.whatsapp:id/search"),
    ]}
    assert find_chat_title(st, "Felix")["id"] == "n_1"
    assert find_chat_title(st, "Carlos") is None


def test_find_chat_title_top_fallback():
    st = {"screen_height": 1600, "candidates": [
        {"id": "n_1", "text": "Felix", "desc": "", "resource_id": "x:id/foo",
         "editable": False, "label": "Felix", "bounds": [0, 100, 720, 200]},
        {"id": "n_2", "text": "Felix", "desc": "", "resource_id": "x:id/bar",
         "editable": False, "label": "Felix", "bounds": [0, 900, 720, 1000]},
    ]}
    assert find_chat_title(st, "Felix")["id"] == "n_1"


def test_forbidden():
    assert is_forbidden(cand("a", desc="Reenviar a…"))
    assert is_forbidden(cand("a", text="Forward"))
    assert is_forbidden(cand("a", desc="Compartir"))
    assert is_forbidden(cand("a", text="Eliminar"))
    assert not is_forbidden(cand("a", text="Felix"))
    assert not is_forbidden(cand("a", desc="Enviar mensaje"))
