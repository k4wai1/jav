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
    ])
    assert rows[0]["class_short"] == "Button"
    assert rows[0]["flags"] == "click"
    assert rows[1]["class_short"] == "EditText"
    assert rows[1]["flags"] == "edit|foc"
    assert H.serialize_table(rows) == [
        [0, "Button", "click", "Send"],
        [1, "EditText", "edit|foc", "Message"],
    ]
    assert H.row_flags() == "—"
    assert H.row_flags(scrollable=True) == "scroll"
    assert H.short_class("") == "View"
    assert by_idx[1]["id"] == "n_2"


@pytest.mark.asyncio
async def test_s1_payload_ingles_tabla_con_flags(monkeypatch):
    """ask_decision envía tabla [idx, class_short, flags, label] +
    current_app + screen_goal, todo en inglés (spec §3)."""
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
    assert state["table"] == [[0, "EditText", "edit|foc", "Message"],
                              [1, "Button", "click", "Send"]]
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
    """TYPE consume text_payload S2; el forense lleva hash, nunca crudo."""
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

    decide = script_decide([dec("TYPE", 0), dec("DONE", "NONE")])
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
