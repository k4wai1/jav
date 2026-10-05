"""Compuertas genéricas: core puro, sin literales de dominio (generic-dual-tier §7).

Sin default global de prohibidos: el filtrado es opt-in por goal via
`pattern` explícito. Cero imports de dominio.
"""
from jev_mcp.core import guards as G
from jev_mcp.core import loop_helpers as H
from jev_mcp.core import text_match as T
from jev_mcp.core import titles as TI


def cand(id, text="", desc="", rid="", editable=False):
    return {"id": id, "text": text, "desc": desc, "resource_id": rid,
            "editable": editable, "label": text or desc}


def test_is_forbidden_opt_in():
    # Sin pattern declarado no hay filtro (nunca global).
    assert G.is_forbidden(cand("a", desc="cualquier cosa")) is False
    assert G.is_forbidden(cand("a", text="borrar todo"), pattern=None) is False
    # Con pattern explícito del operador sí filtra.
    assert G.is_forbidden(cand("a", text="borrar todo"),
                          pattern=r"borrar|eliminar")
    assert G.is_forbidden(cand("a", desc="Eliminar cuenta"),
                          pattern=r"borrar|eliminar")
    assert not G.is_forbidden(cand("a", text="Ana"),
                              pattern=r"borrar|eliminar")
    # Regex inválida no rompe: no filtra.
    assert G.is_forbidden(cand("a", text="x"), pattern=r"([") is False


def test_no_global_default():
    assert not hasattr(G, "FORBIDDEN_DEFAULT")


def test_require_verified_y_tau():
    assert G.require_verified(True, "tap:n_1", "NO_VERIFY") is None
    r = G.require_verified(False, "tap:n_1", "NO_VERIFY")
    assert r["kind"] == "abort" and r["code"] == "NO_VERIFY"
    assert G.gate_tau(0.9, 0.70) is None
    assert G.gate_tau(0.70, 0.70) is None
    r = G.gate_tau(0.5, 0.70)
    assert r["kind"] == "escalate" and r["reason"] == "LOW_CONF"


def test_guarded_action_forbidden_explicito():
    cands = {"n_1": {"id": "n_1", "label": "L1"}}
    assert G.guarded_action("tap:n_1", cands, 7, forbidden=False) is None
    v = G.guarded_action("tap:n_1", cands, 7, forbidden=True)
    assert v["code"] == "FORBIDDEN_TARGET"
    assert G.guarded_action("escalate", cands, 7, forbidden=True) is None


def test_tabla_y_estructurales():
    rows, by_idx = H.build_table(
        [{"id": "n_1", "label": "Botón", "bounds": [0, 100, 720, 200],
          "clickable": True, "editable": False, "focused": False}])
    assert len(rows) == 1 and by_idx[0]["id"] == "n_1"
    assert H.validate_target(by_idx[0], 1600) is None
    assert H.validate_target(None)["code"] == "SELECTOR_NOT_FOUND"
    assert H.validate_target({"id": "x", "bounds": [0, 0, 0, 0]})["code"] \
        == "SELECTOR_NOT_FOUND"
    assert H.check_decision_json({"action": "TAP", "target": 0,
                                  "needs_system_2": False,
                                  "conf": 0.9}) is None
    assert H.check_decision_json({"action": "TAPEAR", "target": 0,
                                  "needs_system_2": False,
                                  "conf": 0.9})["code"] == "JEV_HALLUCINATION"
    assert H.check_decision_json({"action": "TAP", "target": 999,
                                  "needs_system_2": False,
                                  "conf": 0.9})["code"] == "JEV_HALLUCINATION"


def test_text_match_y_titles_genericos():
    assert T.title_matches_strict("Ajustes", "Ajustes")
    assert not T.title_matches_strict("Ajustes", "")
    assert T.name_hit("Ajustes", cand("a", text="AJUSTES"))
    assert not T.name_hit("Ajustes", cand("a", text="Reloj"))
    st = {"screen_height": 1600, "candidates": [
        cand("n_1", text="Ajustes", rid="x:id/title"),
    ]}
    assert TI.find_title(st, "Ajustes", rid_keys=("title",))["id"] == "n_1"
    assert TI.find_title(st, "Reloj", rid_keys=("title",)) is None
