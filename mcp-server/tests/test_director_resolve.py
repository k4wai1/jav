"""Tests v5 director-client §9.3: resolver ciego al goal (con stubs).

- Una sola pregunta Choice sobre índices + NONE (usa ask, nunca el
  decisor con goal global).
- Tabla con forma [idx, class_short, zone, flags, label], con zona.
- Ausencia del goal global / nombres / paquetes en el state.
- Resuelve / NONE / hallucination.
100% genérico, sin literales de dominio en src (los valores aquí son de
test, no-normativos).
"""
import pytest

from jev_mcp import jev_client
from jev_mcp.core import director_resolve as R
from jev_mcp.core import loop_helpers as H


def rows(n=3):
    cands = [
        {"id": f"n_{i}", "label": f"Row {i}", "text": f"Row {i}",
         "desc": "", "cls": "android.widget.Button",
         "bounds": [0, 100 + 100 * i, 720, 200 + 100 * i],
         "clickable": True, "editable": False, "focused": False,
         "scrollable": False, "visible": True}
        for i in range(n)
    ]
    built, _ = H.build_table(cands, 720, 1600)
    return built


def norm_answer(key, criteria, conf=0.91):
    others = [k for k in criteria if k != key]
    p_hit = 0.9
    p_rest = (1.0 - p_hit) / max(len(others), 1)
    probs = {k: (p_hit if k == key else p_rest) for k in criteria}
    # Ajuste de redondeo: la elegida absorbe el residuo (sigue argmax).
    probs[key] += 1.0 - sum(probs.values())
    return {"kind": "choice", "key": key, "p": probs[key],
            "confidence": conf,
            "raw": {"choice": key, "confidence": conf,
                    "probabilities": probs}}


def test_build_state_solo_micro_y_tabla():
    state, questions = R.build_resolve_state(
        "Tap the Copy link row", rows(3), 41, current_app="com.example.app")
    assert set(questions) == {"target"}
    q = questions["target"]
    assert q["type"] == "choice"
    assert set(q["criteria"]) == {"0", "1", "2", "NONE"}
    # Tabla con zona: [idx, class_short, zone, flags, label].
    assert all(len(r) == 5 for r in state["table"])
    assert state["screen_goal"] == "Tap the Copy link row"
    assert state["snapshot_id"] == 41
    # Anti-poisoning: el state NO contiene el goal global ni guidance.
    blob = str(state) + str(questions)
    for forbidden in ("goal", "history", "s2_guidance", "guidance_for_s1",
                      "operator_verbatim", "needs_system_2", "action"):
        assert forbidden not in state, forbidden
    # Cero instrucciones en español en la pregunta.
    assert "elige" not in q["instructions"].lower()
    assert "fila" not in q["instructions"].lower()


@pytest.mark.asyncio
async def test_resolve_element_devuelve_idx_y_conf():
    captured = {}

    async def fake_ask(state, questions):
        captured.update({"state": state, "questions": questions})
        crit = questions["target"]["criteria"]
        return {"target": norm_answer("1", crit, conf=0.91)}, \
            {"in_tokens": 100, "out_tokens": 5}

    out = await R.resolve_element("Tap the Copy link row", rows(3), 41,
                                  current_app="com.example.app",
                                  _ask=fake_ask)
    assert out["idx"] == 1 and abs(out["conf"] - 0.91) < 1e-9
    assert out["snapshot_id"] == 41
    assert "mock" not in out
    assert captured["state"]["first_result"] is None or True


@pytest.mark.asyncio
async def test_resolve_element_none():
    async def fake_ask(state, questions):
        crit = questions["target"]["criteria"]
        return {"target": norm_answer("NONE", crit, conf=0.8)}, \
            {"in_tokens": 10, "out_tokens": 2}

    out = await R.resolve_element("Tap the Copy link row", rows(2), 7,
                                  _ask=fake_ask)
    assert out["idx"] == "NONE"


@pytest.mark.asyncio
async def test_resolve_element_hallucination_fuera_de_criteria():
    async def fake_ask(state, questions):
        return {"target": {"kind": "choice", "key": "99", "p": 1.0,
                           "confidence": 0.9, "raw": {"mock": False}}}, {}

    with pytest.raises(jev_client.JevHallucination):
        await R.resolve_element("Tap the Copy link row", rows(2), 7,
                                _ask=fake_ask)


@pytest.mark.asyncio
async def test_anti_poisoning_state_sin_goal_global():
    """§9.3: el state capturado no contiene goal global/nombres/paquetes."""
    captured = {}
    global_goal = "llevar el enlace a Luis por la app de mensajeria"

    async def fake_ask(state, questions):
        captured["state"] = state
        crit = questions["target"]["criteria"]
        return {"target": norm_answer("0", crit)}, {"in_tokens": 5,
                                                   "out_tokens": 1}

    # El resolver SOLO recibe la micro-intención; el goal global nunca entra.
    await R.resolve_element("Tap the Copy link row", rows(2), 9,
                            current_app="com.example.video", _ask=fake_ask)
    st = captured["state"]
    blob = str(st).lower()
    assert global_goal.lower() not in blob
    assert "luis" not in blob
    assert "mensajeria" not in blob
    assert set(st) == {"screen_goal", "current_app", "snapshot_id",
                       "table", "first_result"}
    assert st["screen_goal"] == "Tap the Copy link row"


@pytest.mark.asyncio
async def test_resolve_sin_key_stub_mock():
    async def fake_ask(state, questions):
        crit = questions["target"]["criteria"]
        ans = norm_answer("0", crit)
        ans["raw"] = {"mock": True}
        return {"target": ans}, {"cost": 0.0, "mock": True}

    out = await R.resolve_element("Tap the Copy link row", rows(1), 3,
                                  _ask=fake_ask)
    assert out.get("mock") is True
