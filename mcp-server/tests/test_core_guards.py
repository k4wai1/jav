"""Contrato core/guards.py: compuertas puras y parametrizadas."""
import pytest

from jev_mcp.core.guards import (
    InvalidAction,
    check_stuck_same,
    gate_tau,
    guarded_action,
    is_forbidden,
    require_verified,
)


def test_forbidden_opt_in():
    # Sin pattern no hay filtro (el default global está eliminado).
    assert is_forbidden({"text": "cualquier cosa", "desc": ""}) is False
    assert is_forbidden({"text": "x", "desc": ""}, pattern=None) is False
    assert is_forbidden({"text": "blip", "desc": ""}, pattern=r"blip")
    assert not is_forbidden({"text": "blip", "desc": ""}, pattern=r"blop")


def _hist(*sigs):
    return [{"action": {"kind": k, "node_id": n}} for k, n in sigs]


def test_stuck_same():
    a = {"kind": "tap_node", "node_id": "n_1", "key": "tap:n_1"}
    assert check_stuck_same(a, _hist(("tap_node", "n_1"))) is None  # 1 previa: ok
    r = check_stuck_same(a, _hist(("tap_node", "n_1"), ("tap_node", "n_1")))
    assert r is not None and r["code"] == "STUCK_SAME"
    assert check_stuck_same(a, _hist(("tap_node", "n_1"), ("tap_node", "n_2"))) is None
    assert check_stuck_same({"kind": "done"}, _hist()) is None  # no-nodo: pasa


def test_require_verified():
    assert require_verified(True, "tap:n_1", "NO_VERIFY") is None
    r = require_verified(False, "tap:n_1", "NO_VERIFY")
    assert r["kind"] == "abort" and r["code"] == "NO_VERIFY"


def test_guarded_action():
    cands = {"n_1": {"id": "n_1", "label": "L1"}}
    assert guarded_action("tap:n_1", cands, 7, forbidden=False) is None
    assert guarded_action("done", cands, 7, forbidden=False) is None
    v = guarded_action("tap:n_1", cands, 7, forbidden=True)
    assert v["code"] == "FORBIDDEN_TARGET"
    v = guarded_action("abort", cands, 7, forbidden=False)
    assert v["kind"] == "abort" and v["code"] == "JEV_ABORT"
    with pytest.raises(InvalidAction):
        guarded_action("zzz", cands, 7, forbidden=False)
    with pytest.raises(InvalidAction):
        guarded_action("tap:n_9", cands, 7, forbidden=False)
    with pytest.raises(InvalidAction):
        guarded_action("frobnicate:n_1", cands, 7, forbidden=False)


def test_guarded_action_acepta_escalate():
    cands = {"n_1": {"id": "n_1", "label": "L1"}}
    assert guarded_action("escalate", cands, 7, forbidden=False) is None
    assert guarded_action("escalate", cands, 7, forbidden=True) is None


def test_gate_tau():
    assert gate_tau(0.9, 0.70) is None
    assert gate_tau(0.70, 0.70) is None  # borde: igual pasa
    r = gate_tau(0.5, 0.70)
    assert r is not None and r["kind"] == "escalate"
    assert r["reason"] == "LOW_CONF"
    # no numéricos → escalado conservador, sin romper genericidad
    r = gate_tau(None, 0.70)
    assert r is not None and r["kind"] == "escalate"
    r = gate_tau("alta", "baja")
    assert r is not None and r["kind"] == "escalate"
