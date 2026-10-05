"""Tests de run_goal genérico con observar/decidir/ejecutar guionizados."""
import hashlib
import json

import pytest

from jev_mcp import jev_client, loop
from jev_mcp.core import loop_helpers as H


def state(n_cands=2, snap=7, package="com.example.settings"):
    cands = [{
        "id": f"n_{i}", "label": f"Item {i}", "text": f"Item {i}", "desc": "",
        "cls": "android.widget.Button", "class_short": "Button",
        "flags": "click",
        "bounds": [0, 100 + 100 * i, 720, 200 + 100 * i],
        "clickable": True, "editable": False, "focused": False,
        "scrollable": False, "visible": True,
    } for i in range(n_cands)]
    return {"package": package, "activity": "Main",
            "snapshot_id": snap, "screen_height": 1600,
            "candidates": cands, "raw_count": n_cands}


def dec(action="TAP", target=0, conf=0.95, s2=False, text=""):
    return {"action": action, "target": target, "needs_system_2": s2,
            "conf": conf, "type_text": text}


def script_decide(decisions):
    calls = []

    async def fn(goal, rows, snapshot, history_summary="",
                 s2_guidance="", current_app="", screen_goal="",
                 focused_field=None):
        calls.append({"rows": len(rows), "snapshot": snapshot,
                      "guidance": s2_guidance, "app": current_app,
                      "screen_goal": screen_goal,
                      "focused_field": focused_field})
        d = decisions[min(len(decisions) - 1, len(calls) - 1)]
        return dict(d), {"in_tokens": 100, "out_tokens": 10}
    fn.calls = calls
    return fn


def ok_exec(executed):
    async def fn(action):
        executed.append(action)
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}
    return fn


def hint_cmd(guidance="re-observe the screen"):
    return {"command": "HINT", "package": "", "target": "NONE", "text": "",
            "guidance_for_s1": guidance, "stop": False}


async def fake_advise(goal, reason="", table_lines=None,
                      history_summary="", need_text=False,
                      current_app="", screen_goal=""):
    if need_text:
        return ({"command": "TYPE", "package": "", "target": "NONE",
                 "text": "hola", "guidance_for_s1": "Type the S2 text.",
                 "stop": False},
                {"in_tokens": 50, "out_tokens": 5})
    return hint_cmd(), {"in_tokens": 50, "out_tokens": 5}


async def fake_verify_ok(goal, table_lines=None, history_summary="",
                         n_actions=0, final_snapshot=None):
    return ({"achieved": True, "evidence": "screen shows the effect"},
            {"in_tokens": 20, "out_tokens": 5})


async def fake_verify_no(goal, table_lines=None, history_summary="",
                         n_actions=0, final_snapshot=None):
    return ({"achieved": False,
             "evidence": "screen without effect; 0 actions"},
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
    assert r["jev_calls"] == 2 and r["s2_calls"] == 2, r  # bootstrap + verify
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
                     history_summary="", need_text=False,
                     current_app="", screen_goal=""):
        advised.append(reason)
        return hint_cmd(), {"in_tokens": 0, "out_tokens": 0}

    decide = script_decide([dec("TAP", 0, conf=0.4), dec("DONE", "NONE")])
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=advise,
                            _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_ok)
    assert r["ok"], r
    assert executed == []  # ESCALATE nunca tapea
    assert advised[0] == "bootstrap"
    assert advised[1].startswith("LOW_CONF")
    assert r["s2_calls"] == 3, r  # bootstrap + 1 escalado + 1 verify DONE


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
    assert "text_sha256" in r["evidence"]["preview"]

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
    async def bad(goal, rows, snapshot, history_summary="",
                  s2_guidance="", current_app="", screen_goal="",
                  focused_field=None):
        raise jev_client.JevHallucination("clave rara")

    r = await loop.run_goal("x", _observe=_c(state()),
                            _decide=bad, _advise=fake_advise,
                            _execute_fn=ok_exec([]))
    assert r["evidence"]["code"] in ("JEV_HALLUCINATION", "JEV_ERROR"), r


@pytest.mark.asyncio
async def test_s2_mock_aborta_s2_unavailable():
    """S2 stub (mock:true) en bootstrap → S2_UNAVAILABLE, nunca ciclar."""
    executed = []

    async def mock_advise(goal, reason="", table_lines=None,
                          history_summary="", need_text=False,
                          current_app="", screen_goal=""):
        return ({"command": "HINT", "package": "", "target": "NONE",
                 "text": "", "guidance_for_s1": "re-observe",
                 "stop": False, "mock": True},
                {"in_tokens": 0, "out_tokens": 0, "mock": True})

    decide = script_decide([dec("TAP", 0, conf=0.4)] * 5)
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=mock_advise,
                            _execute_fn=ok_exec(executed))
    assert not r["ok"] and r["evidence"]["code"] == "S2_UNAVAILABLE", r
    assert r["hint"] == "falta OPENROUTER_API_KEY o S2 caído", r
    assert executed == [] and r["steps"] == 0, r
    assert r["s2_calls"] == 1 and r["jev_calls"] == 0, r


@pytest.mark.asyncio
async def test_s2_excepcion_aborta_s2_unavailable():
    """S2 caído (excepción HTTP) en bootstrap → S2_UNAVAILABLE."""

    async def down_advise(goal, reason="", table_lines=None,
                          history_summary="", need_text=False,
                          current_app="", screen_goal=""):
        raise RuntimeError("404 guardrails")

    decide = script_decide([dec("TAP", 0, conf=0.4)] * 5)
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=down_advise,
                            _execute_fn=ok_exec([]))
    assert not r["ok"] and r["evidence"]["code"] == "S2_UNAVAILABLE", r
    assert r["hint"] == "falta OPENROUTER_API_KEY o S2 caído", r
    assert r["steps"] == 0, r


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
    assert r["steps"] == 3 and r["s2_calls"] == 3, r  # bootstrap + 2


@pytest.mark.asyncio
async def test_forense_incluye_cost(tmp_path):
    logf = str(tmp_path / "run.jsonl")
    decide = script_decide([dec("TAP", 0), dec("DONE", "NONE")])
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec([]), log_path=logf,
                            _verify_done=fake_verify_ok)
    assert r["ok"], r
    lines = [json.loads(l) for l in open(logf, encoding="utf-8")]
    assert any("cost" in e for e in lines)
    assert any("done_verify" in e for e in lines)
    assert any("cost_s2_verify" in e for e in lines)
    assert any(e.get("phase") == "bootstrap" and "s2_command" in e
               for e in lines)


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
    assert r["s2_calls"] >= 2, r  # bootstrap + cada DONE pide verificación S2


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
            return ({"achieved": False, "evidence": "no effect"},
                    {"in_tokens": 20, "out_tokens": 5})
        assert n_actions >= 1
        return ({"achieved": True, "evidence": "visible effect"},
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


# --- v3: payload S1 en inglés + tabla con flags + bootstrap OPEN_APP ---


def test_build_table_enriquecida_con_flags():
    rows, by_idx = H.build_table([
        {"id": "n_1", "label": "Send", "cls": "android.widget.Button",
         "bounds": [0, 100, 720, 200], "clickable": True,
         "editable": False, "focused": False, "scrollable": False},
        {"id": "n_2", "label": "Message", "cls": "android.widget.EditText",
         "bounds": [0, 200, 720, 300], "clickable": False,
         "editable": True, "focused": True, "scrollable": False},
    ], 720, 1600)
    assert rows[0]["class_short"] == "Button"
    assert rows[0]["flags"] == "click"
    assert rows[1]["class_short"] == "EditText"
    assert rows[1]["flags"] == "edit|foc"
    # v4 §4: [idx, class_short, zone, flags, label], zone 3×3 en inglés.
    assert rows[0]["zone"] == "top-center"
    assert rows[1]["zone"] == "top-center"
    assert H.serialize_table(rows) == [
        [0, "Button", "top-center", "click", "Send"],
        [1, "EditText", "top-center", "edit|foc", "Message"],
    ]
    assert H.row_flags() == "—"
    assert H.row_flags(scrollable=True) == "scroll"
    assert H.short_class("") == "View"
    assert by_idx[1]["id"] == "n_2"


def test_zone_of_3x3_y_fallback_unknown():
    """v4 §4: tercios por centroide+resolución; unknown sin datos."""
    assert H.zone_of([0, 0, 100, 100], 900, 900) == "top-left"
    assert H.zone_of([400, 0, 500, 100], 900, 900) == "top-center"
    assert H.zone_of([800, 0, 900, 100], 900, 900) == "top-right"
    assert H.zone_of([0, 400, 100, 500], 900, 900) == "mid-left"
    assert H.zone_of([400, 400, 500, 500], 900, 900) == "mid-center"
    assert H.zone_of([800, 400, 900, 500], 900, 900) == "mid-right"
    assert H.zone_of([0, 800, 100, 900], 900, 900) == "bottom-left"
    assert H.zone_of([400, 800, 500, 900], 900, 900) == "bottom-center"
    assert H.zone_of([800, 800, 900, 900], 900, 900) == "bottom-right"
    assert H.zone_of([0, 0, 100, 100], 0, 0) == "unknown"  # sin resolución
    assert H.zone_of([0, 0, 0, 0], 900, 900) == "unknown"  # degenerados
    assert H.zone_of(None, 900, 900) == "unknown"
    rows, _ = H.build_table(
        [{"id": "n_0", "label": "X", "bounds": [0, 0, 100, 100]}])
    assert rows[0]["zone"] == "unknown"  # sin resolución se tolera
    assert H.serialize_table(rows) == [[0, "View", "unknown", "—", "X"]]
    # MAX_TABLE intacto: 254+NONE, sin poda a 20 (§9.5).
    assert H.MAX_TABLE == 254


@pytest.mark.asyncio
async def test_s1_payload_ingles_tabla_con_flags(monkeypatch):
    """ask_decision envía tabla [idx, class_short, zone, flags, label] +
    current_app + screen_goal, todo en inglés (plan-ahead v4 §4-§5)."""
    captured = {}

    async def fake_post(payload):
        captured.update(payload)
        return {"answers": {
            "action": {"choice": "TAP", "confidence": 0.9,
                       "probabilities": {"TAP": 0.52, "TYPE": 0.08,
                                         "SCROLL_DOWN": 0.08,
                                         "SCROLL_UP": 0.08, "BACK": 0.08,
                                         "DONE": 0.08, "ESCALATE": 0.08}},
            "target": {"choice": "1", "confidence": 0.8,
                       "probabilities": {"0": 0.1, "1": 0.8,
                                         "NONE": 0.1}},
            "needs_system_2": {"noul": 0.1}},
            "usage": {"in_tokens": 10, "out_tokens": 2}}

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(jev_client, "_post", fake_post)
    rows = [{"idx": 0, "id": "n_7", "label": "Message",
             "cls": "android.widget.EditText", "clickable": False,
             "editable": True, "focused": True, "scrollable": False,
             "bounds": [0, 0, 720, 200], "visible": True},
            {"idx": 1, "id": "n_3", "label": "Send",
             "cls": "android.widget.Button", "clickable": True,
             "editable": False, "focused": False, "scrollable": False,
             "bounds": [0, 200, 720, 300], "visible": True}]
    d, _ = await jev_client.ask_decision(
        "Send a message to Rupa saying I am on my way", rows, 42,
        history_summary="tap_node:n_7",
        s2_guidance="Thread is open. Tap the message input.",
        current_app="dev.jev.jam",
        screen_goal="Message thread with Rupa open, message input focused")
    assert d["action"] == "TAP" and d["target"] == 1
    state = captured["state"]
    assert state["current_app"] == "dev.jev.jam"
    assert state["screen_goal"].startswith("Message thread")
    table = state["table"]
    assert [r[0] for r in table] == [0, 1]  # idx estables
    assert [r[1] for r in table] == ["EditText", "Button"]  # class_short
    assert all(r[2] in H.ZONE_VALUES or r[2] == "unknown"  # zone v4 §4
               for r in table)
    assert [r[3] for r in table] == ["edit|foc", "click"]  # flags
    assert [r[4] for r in table] == ["Message", "Send"]  # label
    assert all(len(r) == 5 for r in table)  # 5 columnas, ni 4 ni 20
    # Cero instrucciones en español en questions + criteria.
    blob = json.dumps(captured["questions"], ensure_ascii=False).lower()
    for es in ("elige", "fila", "nunca inventes", "requiere redacci",
               "retrocede", "desplaza", "cumpli", "objetivo", "pantalla"):
        assert es not in blob, es
    for en in ("pick one primitive", "target table row index",
               "system-2 open-text"):
        assert en in blob, en


@pytest.mark.asyncio
async def test_bootstrap_open_app_antes_del_primer_s1():
    """Goal de mensajería con app fuera de foreground: el stub S2 emite
    OPEN_APP con el paquete runtime y el loop despacha open_app con ese
    paquete + re-observe antes del primer pass S1 (mocks, sin dispositivo)."""
    opened = []
    first_state = state(2, snap=1, package="com.example.launcher")
    second_state = state(2, snap=2, package="com.example.messenger")
    calls = {"n": 0}

    async def obs():
        calls["n"] += 1
        return first_state if calls["n"] == 1 else second_state

    async def advise(goal, reason="", table_lines=None,
                     history_summary="", need_text=False,
                     current_app="", screen_goal=""):
        if reason == "bootstrap":
            assert current_app == "com.example.launcher"
            return ({"command": "OPEN_APP",
                     "package": "com.example.messenger",
                     "guidance_for_s1": "App is open. Advance the goal.",
                     "stop": False},
                    {"in_tokens": 30, "out_tokens": 5})
        return hint_cmd(), {"in_tokens": 10, "out_tokens": 2}

    async def open_app(package):
        opened.append(package)
        return {"ok": True, "verified": True,
                "evidence": {"package": package}}

    decide = script_decide([dec("TAP", 0), dec("DONE", "NONE")])
    executed = []
    r = await loop.run_goal("write a message to Rupa saying I am on my way",
                            _observe=obs, _decide=decide, _advise=advise,
                            _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_ok,
                            _open_app=open_app, _bootstrap_delay_s=0)
    assert r["ok"], r
    assert opened == ["com.example.messenger"], opened
    # El primer pass S1 ya vio la app abierta (re-observe post-open_app).
    assert decide.calls[0]["app"] == "com.example.messenger", decide.calls
    assert decide.calls[0]["screen_goal"], decide.calls
    assert r["s2_calls"] >= 2, r  # bootstrap + verify DONE


@pytest.mark.asyncio
async def test_bootstrap_paquete_malo_aborta_sin_actuar():
    """OPEN_APP con package deforme → S2_BAD_COMMAND sin tocar el dispositivo."""
    opened = []

    async def advise(goal, reason="", table_lines=None,
                     history_summary="", need_text=False,
                     current_app="", screen_goal=""):
        return ({"command": "OPEN_APP", "package": "not-a-package",
                 "guidance_for_s1": "x", "stop": False},
                {"in_tokens": 5, "out_tokens": 2})

    async def open_app(package):
        opened.append(package)
        return {"ok": True, "verified": True, "evidence": {}}

    decide = script_decide([dec("TAP", 0)])
    r = await loop.run_goal("meta genérica", _observe=_c(state()),
                            _decide=decide, _advise=advise,
                            _execute_fn=ok_exec([]),
                            _open_app=open_app, _bootstrap_delay_s=0)
    assert not r["ok"] and r["evidence"]["code"] == "S2_BAD_COMMAND", r
    assert opened == []


@pytest.mark.asyncio
async def test_type_usa_payload_s2_solo_hash_en_forense(tmp_path):
    """TYPE S2 ejecutable directo (como OPEN_APP): bootstrap TYPE con campo
    enfocado+visible se despacha vía type_text con read-back; forense solo
    hash, nunca crudo."""
    logf = str(tmp_path / "run.jsonl")
    secret = "I am on my way"

    def field_with(text):
        return {"id": "n_0", "label": "Message", "text": text, "desc": "",
                "cls": "android.widget.EditText", "class_short": "EditText",
                "flags": "edit|foc",
                "bounds": [0, 200, 720, 300], "clickable": True,
                "editable": True, "focused": True, "scrollable": False,
                "visible": True,
                "resource_id": "com.example.messenger/id/message_input"}

    calls = {"n": 0}

    async def obs_evoluciona():
        # P0-2: el campo refleja el REPLACE solo tras el TYPE (read-back).
        calls["n"] += 1
        shown = "Message" if calls["n"] <= 2 else secret
        return {"package": "com.example.messenger", "activity": "Thread",
                "snapshot_id": 9, "screen_height": 1600,
                "candidates": [field_with(shown)], "raw_count": 1}

    async def advise(goal, reason="", table_lines=None,
                     history_summary="", need_text=False,
                     current_app="", screen_goal=""):
        if reason == "bootstrap":
            return ({"command": "TYPE", "target": "NONE", "text": secret,
                     "guidance_for_s1": "Type the S2 text into the field.",
                     "stop": False},
                    {"in_tokens": 30, "out_tokens": 5})
        return hint_cmd(), {"in_tokens": 10, "out_tokens": 2}

    typed = []

    async def exe(action):
        typed.append(action)
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}

    decide = script_decide([dec("DONE", "NONE")])
    r = await loop.run_goal("write a note", _observe=obs_evoluciona,
                            _decide=decide, _advise=advise,
                            _execute_fn=exe, _verify_done=fake_verify_ok,
                            log_path=logf, confirm=True)
    assert r["ok"], r
    assert typed and typed[0]["text"] == secret, typed
    assert typed[0]["kind"] == "type_text" and len(typed) == 1, typed
    raw = open(logf, encoding="utf-8").read()
    assert secret not in raw
    assert hashlib.sha256(secret.encode()).hexdigest() in raw
    assert '"input_verified": true' in raw
    assert "s2_direct_type" in raw


@pytest.mark.asyncio
async def test_s2_type_direct_en_escalate_con_target(tmp_path):
    """Repro run-1791201814: S1 TYPE conf<tau + S2 TYPE con target resuelto
    y campo enfocado+visible → despacho directo vía type_text (no solo hint).
    100% genérico, sin literales de dominio."""
    logf = str(tmp_path / "run.jsonl")
    secret = "hola mundo"

    def field_with(text):
        return {"id": "n_69", "label": "Message", "text": text, "desc": "",
                "cls": "android.widget.EditText", "class_short": "EditText",
                "flags": "edit|foc",
                "bounds": [0, 1300, 720, 1400], "clickable": True,
                "editable": True, "focused": True, "scrollable": False,
                "visible": True,
                "resource_id": "com.example.messenger/id/input"}

    calls = {"n": 0}

    async def obs():
        calls["n"] += 1
        shown = "Message" if calls["n"] <= 3 else secret
        return {"package": "com.example.messenger", "activity": "Thread",
                "snapshot_id": 421, "screen_height": 1600,
                "candidates": [field_with(shown)], "raw_count": 1}

    async def advise(goal, reason="", table_lines=None,
                     history_summary="", need_text=False,
                     current_app="", screen_goal=""):
        if reason == "bootstrap":
            return hint_cmd(), {"in_tokens": 10, "out_tokens": 2}
        if reason.startswith("LOW_CONF"):
            return ({"command": "TYPE", "target": 0, "text": secret,
                     "guidance_for_s1": "Type the S2 text into the field.",
                     "stop": False},
                    {"in_tokens": 40, "out_tokens": 6})
        return hint_cmd(), {"in_tokens": 10, "out_tokens": 2}

    typed = []

    async def exe(action):
        typed.append(action)
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}

    decide = script_decide([dec("TYPE", 0, conf=0.61),
                            dec("DONE", "NONE", conf=0.95)])
    r = await loop.run_goal("write a note", _observe=obs,
                            _decide=decide, _advise=advise,
                            _execute_fn=exe, _verify_done=fake_verify_ok,
                            log_path=logf, confirm=True)
    assert r["ok"], r
    assert len(typed) == 1 and typed[0]["kind"] == "type_text", typed
    assert typed[0]["text"] == secret, typed
    assert typed[0]["node_id"] == "n_69", typed
    raw = open(logf, encoding="utf-8").read()
    assert secret not in raw
    assert hashlib.sha256(secret.encode()).hexdigest() in raw
    assert "s2_direct_type" in raw
    assert '"input_verified": true' in raw


@pytest.mark.asyncio
async def test_s2_type_sin_foco_no_despacha_directo():
    """TYPE S2 con target NONE y sin campo enfocado → no ejecuta; solo guarda
    payload para el próximo S1 (foco explícito exigible)."""
    def field_unfocused():
        return {"id": "n_1", "label": "Message", "text": "", "desc": "",
                "cls": "android.widget.EditText", "class_short": "EditText",
                "flags": "edit",
                "bounds": [0, 200, 720, 300], "clickable": True,
                "editable": True, "focused": False, "scrollable": False,
                "visible": True, "resource_id": "rid/input"}

    st = {"package": "com.example.app", "activity": "T",
          "snapshot_id": 5, "screen_height": 1600,
          "candidates": [field_unfocused()], "raw_count": 1}

    async def advise(goal, reason="", table_lines=None,
                     history_summary="", need_text=False,
                     current_app="", screen_goal=""):
        if reason == "bootstrap":
            return hint_cmd(), {"in_tokens": 5, "out_tokens": 2}
        return ({"command": "TYPE", "target": "NONE", "text": "hello",
                 "guidance_for_s1": "Type the text.",
                 "stop": False},
                {"in_tokens": 10, "out_tokens": 2})

    executed = []
    decide = script_decide([dec("TYPE", 0, conf=0.4),
                            dec("DONE", "NONE", conf=0.95)])
    r = await loop.run_goal("write a note", _observe=_c(st),
                            _decide=decide, _advise=advise,
                            _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_ok)
    # Sin foco no hay type_text directo (el focus-tap lo haría el S1 en el
    # paso siguiente; aquí el segundo paso es DONE verificado).
    assert not any(a.get("kind") == "type_text" for a in executed), executed
    assert r["ok"], r


@pytest.mark.asyncio
async def test_s2_back_se_ejecuta_directo():
    """BACK S2 ordenado ante escalado → press_back + re-observe (como OPEN_APP)."""
    first = state(2, snap=11, package="com.example.app")
    second = state(2, snap=12, package="com.example.app")
    calls = {"n": 0}

    async def obs():
        calls["n"] += 1
        return first if calls["n"] <= 2 else second

    async def advise(goal, reason="", table_lines=None,
                     history_summary="", need_text=False,
                     current_app="", screen_goal=""):
        if reason == "bootstrap":
            return hint_cmd(), {"in_tokens": 5, "out_tokens": 2}
        return ({"command": "BACK", "guidance_for_s1": "Go back.",
                 "stop": False},
                {"in_tokens": 10, "out_tokens": 2})

    executed = []
    decide = script_decide([dec("TAP", 0, conf=0.3),
                            dec("DONE", "NONE", conf=0.95)])
    r = await loop.run_goal("go back once", _observe=obs,
                            _decide=decide, _advise=advise,
                            _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_ok)
    assert r["ok"], r
    assert any(a.get("kind") == "back" for a in executed), executed


# --- P0-1: focused_field en el state S1 ---


def _field_cand(text="", focused=True):
    return {"id": "n_0", "label": "Message", "text": text, "desc": "",
            "cls": "android.widget.EditText", "class_short": "EditText",
            "flags": "edit|foc" if focused else "edit",
            "bounds": [0, 200, 720, 300], "clickable": True,
            "editable": True, "focused": focused, "scrollable": False,
            "visible": True,
            "resource_id": "com.example.messenger/id/message_input"}


def _field_state(text="", snap=5, ff=None):
    st = {"package": "com.example.messenger", "activity": "Thread",
          "snapshot_id": snap, "screen_height": 1600,
          "candidates": [_field_cand(text)], "raw_count": 1}
    if ff is not None:
        st["focused_field"] = ff
    return st


@pytest.mark.asyncio
async def test_s1_state_carries_focused_field_en(monkeypatch):
    """P0-1: el state S1 en inglés incluye campo enfocado + contenido."""
    captured = {}

    async def fake_post(payload):
        captured.update(payload)
        n = len(payload["state"]["table"])
        keys = [str(r[0]) for r in payload["state"]["table"]] + ["NONE"]
        probs_t = {k: (0.8 if k == "0" else 0.2 / max(n, 1))
                   for k in keys}
        s = sum(probs_t.values())
        probs_t = {k: v / s for k, v in probs_t.items()}
        probs_t["0"] = probs_t["0"] + (1.0 - sum(probs_t.values()))
        return {"answers": {
            "action": {"choice": "TAP", "confidence": 0.9,
                       "probabilities": {"TAP": 0.52, "TYPE": 0.08,
                                         "SCROLL_DOWN": 0.08,
                                         "SCROLL_UP": 0.08, "BACK": 0.08,
                                         "DONE": 0.08, "ESCALATE": 0.08}},
            "target": {"choice": "0", "confidence": 0.8,
                       "probabilities": probs_t},
            "needs_system_2": {"noul": 0.1}},
            "usage": {"in_tokens": 10, "out_tokens": 2}}

    monkeypatch.setenv("OPENROUTER_API_KEY", "test-key")
    monkeypatch.setattr(jev_client, "_post", fake_post)
    rows = [{"idx": 0, "id": "n_0", "label": "Message",
             "cls": "android.widget.EditText", "clickable": True,
             "editable": True, "focused": True, "scrollable": False,
             "bounds": [0, 200, 720, 300], "visible": True}]
    d, _ = await jev_client.ask_decision(
        "goal", rows, 9, current_app="com.example.messenger",
        focused_field={"label": "Message", "holds": "hola mundo"})
    assert d["action"] == "TAP"
    ff = captured["state"]["focused_field"]
    assert ff == {"label": "Message", "holds": "hola mundo"}, ff
    assert set(captured["state"]) == {
        "goal", "screen_goal", "operator_verbatim", "current_app",
        "snapshot_id", "table", "focused_field", "history", "s2_guidance"}
    # Sin campo → "empty"; password → máscara, nunca el valor.
    await jev_client.ask_decision("goal", rows, 9, focused_field=None)
    assert captured["state"]["focused_field"] == {"label": "none",
                                                  "holds": "empty"}
    await jev_client.ask_decision(
        "goal", rows, 9,
        focused_field={"label": "Password", "holds": "a password, not read"})
    assert captured["state"]["focused_field"]["holds"] == (
        "a password, not read")


@pytest.mark.asyncio
async def test_loop_pasa_focused_field_del_observe_a_s1():
    """El loop propaga focused_field del observe al pass S1."""
    ff = {"label": "Message", "kind": "text", "holds": "hola mundo"}
    decide = script_decide([dec("TAP", 0), dec("DONE", "NONE")])
    r = await loop.run_goal("mirar items",
                            _observe=_c(_field_state("", ff=ff)),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec([]),
                            _verify_done=fake_verify_ok)
    assert r["ok"], r
    assert decide.calls[0]["focused_field"] == ff, decide.calls


# --- P0-2: TYPE replace + read-back (doble-type) ---


@pytest.mark.asyncio
async def test_type_replace_then_readback_ok(tmp_path):
    """TYPE escribe vía open-text S2 y el read-back confirma (1 type)."""
    logf = str(tmp_path / "run.jsonl")
    calls = {"n": 0}

    async def obs():
        calls["n"] += 1
        shown = "" if calls["n"] <= 2 else "hola"
        return _field_state(shown)

    typed = []

    async def exe(action):
        typed.append(action)
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}

    decide = script_decide([dec("TYPE", 0), dec("DONE", "NONE")])
    r = await loop.run_goal("mirar items", _observe=obs,
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=exe, _verify_done=fake_verify_ok,
                            log_path=logf)
    assert r["ok"], r
    assert [a["kind"] for a in typed] == ["type_text"], typed
    assert typed[0]["text"] == "hola", typed
    raw = open(logf, encoding="utf-8").read()
    assert '"input_verified": true' in raw
    assert '"fingerprint_before"' in raw and '"fingerprint_after"' in raw


@pytest.mark.asyncio
async def test_type_mismatch_yields_input_unverified_without_retype(
        monkeypatch):
    """Campo parcial → input_unverified con UN solo type_text (sin retype)."""
    monkeypatch.setattr(H, "INPUT_TIMEOUT_MS", 120)
    monkeypatch.setattr(H, "POLL_MS", 20)

    async def advise(goal, reason="", table_lines=None,
                     history_summary="", need_text=False,
                     current_app="", screen_goal=""):
        if reason == "bootstrap":
            return ({"command": "TYPE", "target": "NONE",
                     "text": "hola mundo",
                     "guidance_for_s1": "Type the S2 text into the field.",
                     "stop": False},
                    {"in_tokens": 30, "out_tokens": 5})
        return hint_cmd(), {"in_tokens": 10, "out_tokens": 2}

    typed = []

    async def exe(action):
        typed.append(action)
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}

    decide = script_decide([dec("TYPE", 0), dec("DONE", "NONE")])
    r = await loop.run_goal("mirar items",
                            _observe=_c(_field_state("hola")),
                            _decide=decide, _advise=advise,
                            _execute_fn=exe, _verify_done=fake_verify_ok,
                            confirm=True)
    assert not r["ok"] and r["evidence"]["code"] == "input_unverified", r
    assert "could not be confirmed" in r["evidence"]["error"], r
    assert [a["kind"] for a in typed] == ["type_text"], typed  # 1 vez


# --- P0-4: S2-vacío degradado ×1 ---


@pytest.mark.asyncio
async def test_s2_empty_degrades_once_then_aborts(tmp_path):
    """S2 vacío: 1 TAP-visible degradado ejecuta; 2º vacío → S2_UNAVAILABLE."""
    from jev_mcp import s2_client as _s2
    logf = str(tmp_path / "run.jsonl")

    async def empty_advise(goal, reason="", table_lines=None,
                           history_summary="", need_text=False,
                           current_app="", screen_goal=""):
        raise _s2.S2EmptyResponse("content None o vacío")

    async def empty_verify(goal, table_lines=None, history_summary="",
                           n_actions=0, final_snapshot=None):
        raise _s2.S2EmptyResponse("content None o vacío")

    executed = []
    decide = script_decide([dec("TAP", 0, conf=0.8), dec("DONE", "NONE")])
    r = await loop.run_goal("abrir ajustes", _observe=_c(state()),
                            _decide=decide, _advise=empty_advise,
                            _execute_fn=ok_exec(executed),
                            _verify_done=empty_verify, log_path=logf)
    assert not r["ok"] and r["evidence"]["code"] == "S2_UNAVAILABLE", r
    assert "S2_EMPTY_RESPONSE" in r["evidence"]["error"], r
    assert [a["kind"] for a in executed] == ["tap_node"], executed
    assert r["s2_calls"] == 2, r  # bootstrap + verify DONE
    assert "System-2 unavailable" in decide.calls[0]["guidance"], decide.calls
    lines = [json.loads(line) for line in open(logf, encoding="utf-8")]
    assert any(line.get("s2_empty") is True for line in lines)
    assert any(line.get("degraded") is True for line in lines)


# --- plan-ahead v4: S2-compilador paso 0 + fast-path + coalescido ---


def _plan_compile(package="", slots=None, screen_goal_en="",
                  terminal="", guidance="Advance the goal.", stop=False):
    """Stub S2-compilador: valores runtime, nunca literales en src/."""
    plan = {"command": "EXECUTE_GOAL", "package": package,
            "screen_goal_en": screen_goal_en or "Goal screen visible",
            "preloaded_inputs": dict(slots or {}),
            "expected_terminal_state": terminal or "Effect visible",
            "guidance_for_s1": guidance, "stop": stop}
    calls = {"n": 0}

    async def fn(goal, table_lines=None, history_summary="",
                 current_app=""):
        calls["n"] += 1
        return dict(plan), {"in_tokens": 30, "out_tokens": 5}
    fn.calls = calls
    fn.plan = plan
    return fn


def _editable_field(id="n_0", label="Note", text="", focused=False,
                    bounds=None):
    return {"id": id, "label": label, "text": text, "desc": "",
            "cls": "android.widget.EditText", "class_short": "EditText",
            "flags": "edit|foc" if focused else "edit",
            "bounds": list(bounds or [60, 500, 660, 600]),
            "clickable": True, "editable": True, "focused": focused,
            "scrollable": False, "visible": True,
            "resource_id": f"com.example.app/id/{id}"}


@pytest.mark.asyncio
async def test_bootstrap_compilador_abre_paquete_y_type_sin_reconsulta(
        tmp_path):
    """v4 §2 + §10.5: stub S2 emite EXECUTE_GOAL con package runtime +
    preloaded + screen_goal_en + expected_terminal_state; el loop despacha
    open_app + re-observe antes del primer S1, y el TYPE posterior consume
    el slot SIN nueva llamada S2 (forense solo len/sha256)."""
    import hashlib as _hl
    logf = str(tmp_path / "run.jsonl")
    secret = "hello plan"
    package = "com.example.messenger"
    seen_goals = []

    snaps = {"n": 0}
    dev = {"focused": False, "text": ""}  # estado dirigido por acciones

    async def obs():
        snaps["n"] += 1
        if snaps["n"] == 1:
            return {"package": "com.example.launcher", "activity": "Home",
                    "snapshot_id": 1, "screen_height": 1600,
                    "screen_width": 720, "candidates": [], "raw_count": 0}
        # Tras open_app: campo visible sin foco; el focus-tap le da foco;
        # el TYPE deja el payload (read-back). Dirigido por acciones, no
        # por conteo (robusto ante el observe coalescido).
        return {"package": package, "activity": "Thread",
                "snapshot_id": snaps["n"], "screen_height": 1600,
                "screen_width": 720,
                "candidates": [_editable_field(text=dev["text"],
                                              focused=dev["focused"])],
                "raw_count": 1}

    async def open_app(pkg):
        seen_goals.append(pkg)
        return {"ok": True, "verified": True, "evidence": {"package": pkg}}

    typed = []

    async def exe(action):
        typed.append(action)
        if action.get("kind") == "tap_node":
            dev["focused"] = True
        if action.get("kind") == "type_text":
            dev["text"] = action.get("text", "")
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}

    async def verify(goal, table_lines=None, history_summary="",
                     n_actions=0, final_snapshot=None,
                     expected_terminal_state=""):
        assert expected_terminal_state == "Effect visible on screen", \
            expected_terminal_state
        return ({"achieved": True, "evidence": "effect visible"},
                {"in_tokens": 20, "out_tokens": 5})

    comp = _plan_compile(package=package, slots={"note": secret},
                         screen_goal_en="Thread open, input focused",
                         terminal="Effect visible on screen")
    decide = script_decide([dec("TYPE", 0), dec("TYPE", 0),
                            dec("DONE", "NONE")])
    r = await loop.run_goal("write a note", _observe=obs, _decide=decide,
                            _compile=comp, _execute_fn=exe,
                            _verify_done=verify, _open_app=open_app,
                            _bootstrap_delay_s=0, log_path=logf)
    assert r["ok"] and r["verified"], r
    assert seen_goals == [package], seen_goals  # open_app solo bootstrap
    assert comp.calls["n"] == 1, comp.calls  # UNA consulta S2 pre-pasos
    # S2 total = paso 0 + verify DONE: cero reconsultas entre TYPEs.
    assert r["s2_calls"] == 2, r
    assert decide.calls[0]["app"] == package, decide.calls  # re-observe
    assert decide.calls[0]["screen_goal"] == "Thread open, input focused"
    kinds = [a["kind"] for a in typed]
    assert kinds[0] == "tap_node" and kinds[-1] == "type_text", kinds
    assert typed[-1]["text"] == secret, typed  # inyección verbatim
    raw = open(logf, encoding="utf-8").read()
    assert secret not in raw  # forense sin texto crudo
    assert _hl.sha256(secret.encode()).hexdigest() in raw
    assert '"slot": "note"' in raw and '"slot_consumed": true' in raw
    assert '"from_plan": true' in raw


@pytest.mark.asyncio
async def test_multi_slot_orden_insercion_sin_reconsulta(tmp_path):
    """v4 §2.3.2 (S4): N slots → orden de inserción S2; read-back como
    detector; cero consultas S2 entre los TYPEs del camino feliz."""
    logf = str(tmp_path / "run.jsonl")
    first, second = "alpha entry", "beta entry"
    snaps = {"n": 0}
    dev = {"a": "", "b": "", "focus_b": False}  # dirigido por acciones

    async def obs():
        snaps["n"] += 1
        return {"package": "com.example.app", "activity": "Form",
                "snapshot_id": 50 + snaps["n"], "screen_height": 1600,
                "screen_width": 720,
                "candidates": [
                    _editable_field(id="n_0", label="Field A",
                                    text=dev["a"], focused=True,
                                    bounds=[60, 300, 660, 400]),
                    _editable_field(id="n_1", label="Field B",
                                    text=dev["b"],
                                    focused=dev["focus_b"] or bool(dev["b"]),
                                    bounds=[60, 900, 660, 1000])],
                "raw_count": 2}

    typed = []

    async def exe(action):
        typed.append(action)
        if action.get("kind") == "tap_node" and action.get("node_id") == "n_1":
            dev["focus_b"] = True
        if action.get("kind") == "type_text":
            if action.get("node_id") == "n_0":
                dev["a"] = action.get("text", "")
            elif action.get("node_id") == "n_1":
                dev["b"] = action.get("text", "")
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}

    comp = _plan_compile(slots={"first": first, "second": second})
    decide = script_decide([dec("TYPE", 0), dec("TYPE", 1), dec("TYPE", 1),
                            dec("DONE", "NONE")])
    r = await loop.run_goal("fill the form", _observe=obs, _decide=decide,
                            _compile=comp, _execute_fn=exe,
                            _verify_done=fake_verify_ok,
                            log_path=logf, confirm=True)
    assert r["ok"], r
    assert comp.calls["n"] == 1, comp.calls
    assert r["s2_calls"] == 2, r  # paso 0 + verify: nada entre TYPEs
    writes = [a["text"] for a in typed if a["kind"] == "type_text"]
    assert writes == [first, second], writes  # orden de inserción
    raw = open(logf, encoding="utf-8").read()
    assert first not in raw and second not in raw
    assert raw.count('"slot_consumed": true') == 2


@pytest.mark.asyncio
async def test_fast_path_coalescido_un_solo_dump(tmp_path):
    """v4 §3 + §10.7: conf ≥ 0.85 trivial → fast_path + verify coalescido
    (el dump de verificación se reutiliza como observe siguiente)."""
    logf = str(tmp_path / "run.jsonl")
    snaps = {"n": 0}
    obs_calls = {"n": 0}

    async def obs():
        obs_calls["n"] += 1
        snaps["n"] += 1
        return {"package": "com.example.app", "activity": "Main",
                "snapshot_id": 200 + snaps["n"], "screen_height": 1600,
                "screen_width": 720, "candidates": [{
                    "id": "n_0", "label": "Item 0", "text": "Item 0",
                    "desc": "", "cls": "android.widget.Button",
                    "bounds": [0, 100, 720, 200], "clickable": True,
                    "editable": False, "focused": False,
                    "scrollable": False, "visible": True}],
                "raw_count": 1}

    executed = []
    decide = script_decide([dec("TAP", 0, conf=0.9),
                            dec("DONE", "NONE", conf=0.95)])
    comp = _plan_compile()
    r = await loop.run_goal("look at items", _observe=obs, _decide=decide,
                            _compile=comp, _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_ok, log_path=logf)
    assert r["ok"], r
    assert executed and executed[0]["kind"] == "tap_node"
    # Bootstrap(1) + step1-observe(1) + verify-coalescido(1, reusado en
    # step2 sin re-observar) + DONE-verify(1) = 4 dumps en 2 pasos.
    assert obs_calls["n"] == 4, obs_calls
    lines = [json.loads(line) for line in open(logf, encoding="utf-8")]
    tap_entries = [e for e in lines if e.get("decision", {}).get(
        "action") == "TAP"]
    assert tap_entries and tap_entries[0]["fast_path"] is True
    assert tap_entries[0]["coalesced"] is True
    assert tap_entries[0]["snapshot_after"] != tap_entries[0]["snapshot"]


@pytest.mark.asyncio
async def test_fast_path_no_salta_compuertas():
    """v4 §3.1: fast-path NUNCA salta STUCK (misma decisión ×3 conf .95)."""
    decide = script_decide([dec("TAP", 0, conf=0.95)] * 5)
    r = await loop.run_goal("look at items", _observe=_c(state()),
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=ok_exec([]))
    assert not r["ok"] and r["evidence"]["code"] == "STUCK_SAME", r


@pytest.mark.asyncio
async def test_s2_empty_never_types_without_payload():
    """En degradación, TYPE sin payload nunca escribe (planned/escalate)."""
    from jev_mcp import s2_client as _s2
    calls = {"n": 0}

    async def advise_once_empty(goal, reason="", table_lines=None,
                                history_summary="", need_text=False,
                                current_app="", screen_goal=""):
        calls["n"] += 1
        if calls["n"] == 1:
            raise _s2.S2EmptyResponse("content None o vacío")
        return hint_cmd(), {"in_tokens": 10, "out_tokens": 2}

    executed = []
    decide = script_decide([dec("TYPE", 0, conf=0.9)])
    r = await loop.run_goal("mirar items", _observe=_c(state()),
                            _decide=decide, _advise=advise_once_empty,
                            _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_ok, max_steps=6)
    assert not r["ok"], r
    assert [a["kind"] for a in executed] != ["type_text"]
    assert not any(a["kind"] == "type_text" for a in executed), executed
    assert r["evidence"]["code"] == "STUCK_SAME", r


# --- Deuda AGENTS.md 2026-10-02: reintento STALE en el bucle ---


@pytest.mark.asyncio
async def test_stale_retry_recovers_once(tmp_path):
    """STALE → re-observe UNA vez + retry misma acción → ok.

    Repro genérica de run-1791243353 (type/tap con snapshot viejo por
    mutación entre dump y ejecución): el bucle re-observa, re-resuelve
    por id y reintenta UNA vez. Sin literales de dominio.
    """
    logf = str(tmp_path / "run.jsonl")
    snaps = {"n": 0}

    async def obs_fresco():
        snaps["n"] += 1
        return state(2, snap=100 + snaps["n"])

    calls = {"n": 0}

    async def exe_stale_once(action):
        calls["n"] += 1
        if calls["n"] == 1:
            assert action["kind"] == "tap_node"
            return {"ok": False, "verified": False,
                    "evidence": {"code": "STALE_SNAPSHOT",
                                 "error": "snapshot obsoleto"}}
        assert action["kind"] == "tap_node"
        # El retry usa el snapshot fresco y el mismo node_id.
        assert action["snapshot_id"] == 100 + snaps["n"], action
        assert action["node_id"] == "n_0", action
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}

    decide = script_decide([dec("TAP", 0), dec("DONE", "NONE")])
    r = await loop.run_goal("mirar items", _observe=obs_fresco,
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=exe_stale_once,
                            _verify_done=fake_verify_ok,
                            log_path=logf)
    assert r["ok"] and r["verified"], r
    assert calls["n"] == 2, calls  # 1 STALE + 1 retry ok
    lines = [json.loads(l) for l in open(logf, encoding="utf-8")]
    assert any(e.get("stale_retry") is True for e in lines), lines
    assert any(e.get("stale_recovered") is True for e in lines), lines


@pytest.mark.asyncio
async def test_stale_retry_twice_aborts_unstable():
    """STALE en intento + STALE en retry → UI_UNSTABLE.

    Segundo STALE cuenta en el streak existente y aborta honesto,
    sin tercer intento ciego.
    """
    async def obs_fresco():
        return state(2, snap=50)

    calls = {"n": 0}

    async def exe_siempre_stale(action):
        calls["n"] += 1
        return {"ok": False, "verified": False,
                "evidence": {"code": "STALE_SNAPSHOT",
                             "error": "snapshot obsoleto"}}

    decide = script_decide([dec("TAP", 0)] * 4)
    r = await loop.run_goal("mirar items", _observe=obs_fresco,
                            _decide=decide, _advise=fake_advise,
                            _execute_fn=exe_siempre_stale)
    assert not r["ok"] and r["evidence"]["code"] == "UI_UNSTABLE", r
    assert calls["n"] == 2, calls  # intento + UNA reintentada, nada más
    assert r["steps"] == 1, r
