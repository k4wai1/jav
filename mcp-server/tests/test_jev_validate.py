"""Tests de validateChoice estricta (patrón M1, P0-3).

Toda distribución inválida → JevHallucination; el loop consume SOLO la
rama elegida (nunca fallback a ramas no elegidas).
"""
import pytest

from jev_mcp import jev_client
from jev_mcp.jev_client import JevHallucination, validate_choice

CRIT = {"a": "a", "b": "b", "c": "c"}


def ans(choice, probs, conf=0.9):
    return {"choice": choice, "confidence": conf, "probabilities": probs}


def test_ok_argmax_completa():
    k, probs, conf = validate_choice(
        ans("b", {"a": 0.1, "b": 0.8, "c": 0.1}), CRIT)
    assert k == "b" and probs["b"] == 0.8 and conf == 0.9


def test_rechaza_probs_incompletas():
    with pytest.raises(JevHallucination):
        validate_choice(ans("a", {"a": 1.0}), CRIT)


def test_rechaza_suma_lejana_de_1():
    with pytest.raises(JevHallucination):
        validate_choice(ans("a", {"a": 0.2, "b": 0.2, "c": 0.1}), CRIT)


def test_rechaza_no_argmax():
    with pytest.raises(JevHallucination):
        validate_choice(ans("a", {"a": 0.2, "b": 0.7, "c": 0.1}), CRIT)


@pytest.mark.parametrize("bad", ["NaN", "inf", "-inf", 1.5, -0.1])
def test_rechaza_conf_no_finita_o_fuera_de_rango(bad):
    import math
    conf = {"NaN": math.nan, "inf": math.inf,
            "-inf": -math.inf}.get(bad, bad)
    with pytest.raises(JevHallucination):
        validate_choice(ans("b", {"a": 0.1, "b": 0.8, "c": 0.1}, conf=conf),
                        CRIT)


def test_rechaza_probs_no_finitas_y_no_dict():
    with pytest.raises(JevHallucination):
        validate_choice(ans("b", {"a": 0.1, "b": float("nan"),
                                  "c": 0.9}), CRIT)
    with pytest.raises(JevHallucination):
        validate_choice({"choice": "b", "confidence": 0.9,
                         "probabilities": [0.1, 0.8, 0.1]}, CRIT)


def test_rechaza_choice_fuera_de_criteria():
    with pytest.raises(JevHallucination):
        validate_choice(ans("z", {"a": 0.4, "b": 0.4, "c": 0.2}), CRIT)


def test_solo_la_rama_elegida_actua():
    """Rama no elegida con p alta se ignora: solo `choice` decide."""
    out = jev_client._norm("q", {"type": "choice", "criteria": CRIT},
                           ans("c", {"a": 0.45, "b": 0.1, "c": 0.45}))
    assert out["key"] == "c" and out["p"] == 0.45
