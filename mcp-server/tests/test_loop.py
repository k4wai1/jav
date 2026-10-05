"""Tests de run_goal genérico con observar/decidir/ejecutar guionizados."""
import pytest

from jev_mcp import jev_client, loop


def state(n_cands=2, snap=7):
    cands = [{
        "id": f"n_{i}", "label": f"Item {i}", "text": f"Item {i}", "desc": "",
        "bounds": [0, 100 + 100 * i, 720, 200 + 100 * i],
        "clickable": True, "editable": False, "focused": False,
        "visible": True,
    } for i in range(n_cands)]
    return {"package": "com.example.settings", "activity": "Main",
            "snapshot_id": snap, "screen_height": 1600,
            "candidates": cands, "raw_count": n_cands}


def dec(action="TAP", target=0, conf=0.95, s2=False, text=""):
    return {"action": action, "target": target, "needs_system_2": s2,
            "conf": conf, "type_text": text}


def script_decide(decisions):
    calls = []

    async def fn(goal, rows, snapshot, history_summary="", s2_hint=""):
        calls.append({"rows": len(rows), "snapshot": snapshot,
                      "hint": s2_hint})
        d = decisions[min(len(decisions) - 1, len(calls) - 1)]
        return dict(d), {"in_tokens": 100, "out_tokens": 10}
    fn.calls = calls
    return fn


def ok_exec(executed):
    async def fn(action):
        executed.append(action)
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}
    return fn


async def fake_advise(goal, reason="", table_lines=None,
                      history_summary="", need_text=False):
    return ({"plan": ["reintentar"], "text": "hola" if need_text else "",
             "criteria": "", "stop": False},
            {"in_tokens": 50, "out_tokens": 5})


async def fake_verify_ok(goal, table_lines=None, history_summary="",
                         n_actions=0, final_snapshot=None):
    return ({"achieved": True, "evidence": "pantalla muestra efecto"},
            {"in_tokens": 20, "out_tokens": 5})


async def fake_verify_no(goal, table_lines=None, history_summary="",
                         n_actions=0, final_snapshot=None):
    return ({"achieved": False,
             "evidence": "pantalla sin efecto; 0 acciones"},
            {"in_tokens": 20, "out_tokens": 5})


@pytest.mark.asyncio
async def test_happy_tap_done():
    executed = []
    decide = script_decide([dec("TAP", 0), dec("DONE", "NONE")])
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_ok)
    assert r["ok"] and r["verified"], r
    assert r["steps"] == 2 and len(executed) == 1
    assert executed[0]["kind"] == "tap_node"
    assert r["jev_calls"] == 2 and r["s2_calls"] == 1
    assert r["total_cost"] > 0  # 100 in-tokens Jev a tarifa normativa


def _c(s):
    async def fn():
        return s
    return fn


@pytest.mark.asyncio
async def test_low_conf_escalates_without_touching_device():
    executed = []
    advised = []

    async def advise(goal, reason="", table_lines=None,
                     history_summary="", need_text=False):
        advised.append(reason)
        return ({"plan": ["p"], "text": "", "criteria": "", "stop": False},
                {"in_tokens": 0, "out_tokens": 0})

    decide = script_decide([dec("TAP", 0, conf=0.4), dec("DONE", "NONE")])
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=advise,
                            _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_ok)
    assert r["ok"], r
    assert executed == []  # ESCALATE nunca tapea
    assert advised and "LOW_CONF" in advised[0]
    assert r["s2_calls"] == 2  # 1 escalado + 1 verify DONE


@pytest.mark.asyncio
async def test_sensitive_needs_confirm():
    executed = []
    decide = script_decide([dec("TAP", 0)])
    r = await loop.run_goal("enviar informe al equipo",
                            _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec(executed))
    assert r["ok"] and not r["verified"] and r["needs_confirm"], r
    assert executed == []
    assert r["evidence"]["preview"]["action"] == "TAP"

    executed2 = []
    decide2 = script_decide([dec("TAP", 0), dec("DONE", "NONE")])
    r2 = await loop.run_goal("enviar informe al equipo",
                             _observe=_c(state()),
                             _decide=decide2, _advise=fake_advise,
                             _execute_fn=ok_exec(executed2), confirm=True,
                             _verify_done=fake_verify_ok)
    assert r2["ok"] and len(executed2) == 1, r2


@pytest.mark.asyncio
async def test_stale_x3_aborta():
    async def stale(action):
        return {"ok": False, "verified": False,
                "evidence": {"code": "STALE_SNAPSHOT", "error": "viejos"}}

    decide = script_decide([dec("TAP", 0), dec("TAP", 1)] * 4)
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=stale)
    assert not r["ok"] and r["evidence"]["code"] == "UI_UNSTABLE", r


@pytest.mark.asyncio
async def test_target_fuera_de_tabla_es_hallucination():
    decide = script_decide([dec("TAP", 250)])
    r = await loop.run_goal("abrir ajustes", _observe=_c(state(2)),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec([]))
    assert r["evidence"]["code"] == "JEV_HALLUCINATION", r


@pytest.mark.asyncio
async def test_forbidden_opt_in():
    decide = script_decide([dec("TAP", 0), dec("DONE", "NONE")])
    r = await loop.run_goal("mirar items",
                            _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec([]), forbidden=r"Item")
    assert r["evidence"]["code"] == "FORBIDDEN_TARGET", r
    r2 = await loop.run_goal("mirar items",
                             _observe=_c(state()),
                             _decide=script_decide(
                                 [dec("TAP", 0), dec("DONE", "NONE")]),
                             _advise=fake_advise,
                             _execute_fn=ok_exec([]),
                             _verify_done=fake_verify_ok)
    assert r2["ok"], r2  # sin pattern no hay filtro


@pytest.mark.asyncio
async def test_tabla_topada_254_mas_none(capsys):
    decide = script_decide([dec("DONE", "NONE")])
    st = state(300)
    r = await loop.run_goal("mirar items", _observe=_c(st),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec([]),
                            _verify_done=fake_verify_ok)
    assert r["ok"], r
    assert decide.calls[0]["rows"] == 254
    out = capsys.readouterr().out
    assert "[COST]" in out


@pytest.mark.asyncio
async def test_hallucination_en_decide():
    async def bad(goal, rows, snapshot, history_summary="", s2_hint=""):
        raise jev_client.JevHallucination("clave rara")

    r = await loop.run_goal("x", _observe=_c(state()),
                            _decide=bad, _advise=fake_advise,
                            _execute_fn=ok_exec([]))
    assert r["evidence"]["code"] in ("JEV_HALLUCINATION", "JEV_ERROR"), r


@pytest.mark.asyncio
async def test_s2_mock_aborta_s2_unavailable():
    """S2 stub (mock:true) → abort S2_UNAVAILABLE, nunca ciclar en giro."""
    executed = []

    async def mock_advise(goal, reason="", table_lines=None,
                          history_summary="", need_text=False):
        return ({"plan": ["re-observar"], "text": "", "criteria": "",
                 "stop": False, "mock": True},
                {"in_tokens": 0, "out_tokens": 0, "mock": True})

    decide = script_decide([dec("TAP", 0, conf=0.4)] * 5)
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=mock_advise,
                            _execute_fn=ok_exec(executed))
    assert not r["ok"] and r["evidence"]["code"] == "S2_UNAVAILABLE", r
    assert r["hint"] == "falta OPENROUTER_API_KEY o S2 caído", r
    assert executed == [] and r["steps"] == 1


@pytest.mark.asyncio
async def test_s2_excepcion_aborta_s2_unavailable():
    """S2 caído (excepción HTTP) → abort S2_UNAVAILABLE, sin traceback."""

    async def down_advise(goal, reason="", table_lines=None,
                          history_summary="", need_text=False):
        raise RuntimeError("404 guardrails")

    decide = script_decide([dec("TAP", 0, conf=0.4)] * 5)
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=down_advise,
                            _execute_fn=ok_exec([]))
    assert not r["ok"] and r["evidence"]["code"] == "S2_UNAVAILABLE", r
    assert r["hint"] == "falta OPENROUTER_API_KEY o S2 caído", r
    assert r["steps"] == 1


@pytest.mark.asyncio
async def test_misma_decision_x3_aborta_stuck_same():
    """Misma (action+target) ×3 sin cambio útil → STUCK_SAME (vía ESCALATE)."""
    executed = []
    decide = script_decide([dec("TAP", 0, conf=0.4)] * 5)
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec(executed))
    assert not r["ok"] and r["evidence"]["code"] == "STUCK_SAME", r
    assert executed == []  # todo fue ESCALATE: nunca se tocó el dispositivo
    assert r["steps"] == 3 and r["s2_calls"] == 2, r


@pytest.mark.asyncio
async def test_forense_incluye_cost(tmp_path):
    logf = str(tmp_path / "run.jsonl")
    decide = script_decide([dec("TAP", 0), dec("DONE", "NONE")])
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec([]), log_path=logf,
                            _verify_done=fake_verify_ok)
    assert r["ok"], r
    import json
    lines = [json.loads(l) for l in open(logf, encoding="utf-8")]
    assert any("cost" in e for e in lines)
    assert any("done_verify" in e for e in lines)
    assert any("cost_s2_verify" in e for e in lines)


@pytest.mark.asyncio
async def test_done_cero_acciones_rechazado_sigue_loop():
    """Repro del fallo run-1791192273: DONE conf=0.83 con 0 taps.

    S1 declara DONE en step 2 anclado en el mismo snapshot; S2 dice
    no-cumplido → el loop NO acepta éxito falso: sigue (máx steps)
    hasta STUCK_SAME/TIMEOUT. Genérico, sin app.
    """
    executed = []
    decide = script_decide([dec("DONE", "NONE", conf=0.83)] * 5)
    r = await loop.run_goal("meta genérica", _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_no,
                            max_steps=5)
    assert not r["ok"], r  # nunca éxito falso
    assert executed == []  # 0 primitivas, como en el log original
    assert r["jev_calls"] >= 3, r  # siguió el loop, no aceptó DONE
    assert r["s2_calls"] >= 2, r  # cada DONE pide verificación S2


@pytest.mark.asyncio
async def test_done_rechazado_luego_aceptado():
    """DONE rechazado una vez, tras 1 tap S2 confirma → ok."""
    executed = []
    calls = {"n": 0}

    async def verify_seq(goal, table_lines=None, history_summary="",
                         n_actions=0, final_snapshot=None):
        calls["n"] += 1
        if calls["n"] == 1:
            assert n_actions == 0
            return ({"achieved": False, "evidence": "sin efecto"},
                    {"in_tokens": 20, "out_tokens": 5})
        assert n_actions >= 1
        return ({"achieved": True, "evidence": "efecto visible"},
                {"in_tokens": 20, "out_tokens": 5})

    decide = script_decide([dec("DONE", "NONE"), dec("TAP", 0),
                            dec("DONE", "NONE")])
    r = await loop.run_goal("meta genérica", _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec(executed),
                            _verify_done=verify_seq, max_steps=6)
    assert r["ok"] and r["verified"], r
    assert r["evidence"]["verified_by"] == "s2", r
    assert r["evidence"]["n_actions"] >= 1, r
    assert len(executed) == 1


@pytest.mark.asyncio
async def test_done_verify_mock_aborta():
    """S2 verify stub → S2_UNAVAILABLE, nunca éxito."""

    async def mock_verify(goal, table_lines=None, history_summary="",
                          n_actions=0, final_snapshot=None):
        return ({"achieved": False, "evidence": "", "mock": True},
                {"in_tokens": 0, "out_tokens": 0, "mock": True})

    decide = script_decide([dec("DONE", "NONE")])
    r = await loop.run_goal("meta genérica", _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec([]),
                            _verify_done=mock_verify)
    assert not r["ok"] and r["evidence"]["code"] == "S2_UNAVAILABLE", r


@pytest.mark.asyncio
async def test_done_verify_empty_aborta():
    """S2 verify vacío persistente → S2_UNAVAILABLE con hint reintento."""
    from jev_mcp import s2_client as _s2

    async def empty_verify(goal, table_lines=None, history_summary="",
                           n_actions=0, final_snapshot=None):
        raise _s2.S2EmptyResponse("content None o vacío")

    decide = script_decide([dec("DONE", "NONE")])
    r = await loop.run_goal("meta genérica", _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec([]),
                            _verify_done=empty_verify)
    assert not r["ok"] and r["evidence"]["code"] == "S2_UNAVAILABLE", r
    assert "S2_EMPTY_RESPONSE" in r["evidence"]["error"], r
