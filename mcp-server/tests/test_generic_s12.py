"""Contrato §12 (addendum 2026-10-06): S2-TAP-direct, first_result,
run_signature fail-fast y clipboard genérico.

100% genérico, sin literales de dominio: los paquetes/URLs son valores de
test aportados por stubs en runtime (no-normativos), nunca defaults.
"""
import hashlib
import json

import pytest

from jev_mcp import jev_client, loop
from jev_mcp.core import loop_helpers as H
from jev_mcp.s2_client import (
    VALID_COMMANDS,
    S2BadCommand,
    parse_command,
)
from jev_mcp.tools import clipboard as C


# --- utilidades locales (guionizado, sin dispositivo) ---


def cand(i, label="Item", cls="android.widget.Button", clickable=True,
         visible=True, scrollable=False, editable=False, focused=False):
    return {"id": f"n_{i}", "label": f"{label} {i}", "text": f"{label} {i}",
            "desc": "", "cls": cls, "class_short": cls.rsplit(".", 1)[-1],
            "flags": "click",
            "bounds": [0, 100 + 100 * i, 720, 200 + 100 * i],
            "clickable": clickable, "editable": editable, "focused": focused,
            "scrollable": scrollable, "visible": visible}


def state(cands, snap=7, package="com.example.settings"):
    return {"package": package, "activity": "Main",
            "snapshot_id": snap, "screen_height": 1600,
            "screen_width": 720, "candidates": cands,
            "raw_count": len(cands)}


def dec(action="TAP", target=0, conf=0.95, s2=False):
    return {"action": action, "target": target, "needs_system_2": s2,
            "conf": conf, "type_text": ""}


def script_decide(decisions):
    calls = []

    async def fn(goal, rows, snapshot, history_summary="",
                 s2_guidance="", current_app="", screen_goal="",
                 focused_field=None, first_result=None):
        calls.append({"rows": len(rows), "snapshot": snapshot,
                      "first_result": first_result})
        d = decisions[min(len(decisions) - 1, len(calls) - 1)]
        return dict(d), {"in_tokens": 100, "out_tokens": 10}
    fn.calls = calls
    return fn


def ok_exec(executed):
    async def fn(action):
        executed.append(action)
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}
    return fn


def hint_cmd():
    return {"command": "HINT", "package": "", "target": "NONE", "text": "",
            "guidance_for_s1": "re-observe the screen", "stop": False}


async def fake_verify_ok(goal, table_lines=None, history_summary="",
                         n_actions=0, final_snapshot=None):
    return ({"achieved": True, "evidence": "screen shows the effect"},
            {"in_tokens": 20, "out_tokens": 5})


def _c(s):
    async def fn():
        return s
    return fn


def tap_advise(target=0):
    async def advise(goal, reason="", table_lines=None,
                     history_summary="", need_text=False,
                     current_app="", screen_goal=""):
        if reason == "bootstrap":
            return hint_cmd(), {"in_tokens": 10, "out_tokens": 2}
        return ({"command": "TAP", "target": target,
                 "guidance_for_s1": "Tap the marked row to advance.",
                 "stop": False},
                {"in_tokens": 40, "out_tokens": 6})
    return advise


# --- §12.1: S2-TAP ejecutable ---


def test_valid_commands_incluye_tap():
    assert "TAP" in VALID_COMMANDS
    assert set(VALID_COMMANDS) == {"OPEN_APP", "TYPE", "TAP", "BACK", "HINT"}


def test_parse_command_tap_exige_int_obligatorio():
    out = parse_command({"command": "TAP", "target": 3,
                         "guidance_for_s1": "Tap the marked row."})
    assert out["command"] == "TAP" and out["target"] == 3
    assert out["stop"] is False
    for bad_target in ("NONE", None, "3", 999, -1, True):
        with pytest.raises(S2BadCommand):
            parse_command({"command": "TAP", "target": bad_target})
    with pytest.raises(S2BadCommand):
        parse_command({"command": "TAP"})  # sin target (default NONE)


def test_parse_command_tap_rechaza_none_explicito():
    with pytest.raises(S2BadCommand):
        parse_command({"command": "TAP", "target": "NONE",
                       "guidance_for_s1": "x"})


@pytest.mark.asyncio
async def test_s2_tap_direct_sin_repreguntar_s1(tmp_path):
    """S1 duda (conf<tau) → S2 TAP-direct ejecuta tap_node sin segunda
    pregunta S1: con max_steps=1 solo hay UNA llamada a decide."""
    logf = str(tmp_path / "run.jsonl")
    executed = []
    decide = script_decide([dec("TAP", 0, conf=0.4)])
    r = await loop.run_goal("look at items",
                            _observe=_c(state([cand(0), cand(1)])),
                            _decide=decide, _advise=tap_advise(0),
                            _execute_fn=ok_exec(executed),
                            log_path=logf, max_steps=1)
    assert len(executed) == 1 and executed[0]["kind"] == "tap_node", executed
    assert executed[0]["node_id"] == "n_0", executed
    assert len(decide.calls) == 1, decide.calls  # sin re-pregunta S1
    assert not r["ok"] and r["evidence"]["code"] == "STUCK", r
    lines = [json.loads(l) for l in open(logf, encoding="utf-8")]
    taps = [e for e in lines if e.get("phase") == "s2_direct_tap"]
    assert taps, lines
    assert taps[0]["target"] == 0 and taps[0]["node_id"] == "n_0"
    assert taps[0]["via"] == "test" and taps[0]["result"]["ok"] is True
    assert "snapshot" in taps[0] and "snapshot_after" in taps[0]
    assert "s2_command" in taps[0]


@pytest.mark.asyncio
async def test_s2_tap_idx_rotado_es_bad_command():
    """Target fuera de la tabla vigente → S2_BAD_COMMAND sin actuar."""
    executed = []
    decide = script_decide([dec("TAP", 0, conf=0.4)])
    r = await loop.run_goal("look at items",
                            _observe=_c(state([cand(0), cand(1)])),
                            _decide=decide, _advise=tap_advise(7),
                            _execute_fn=ok_exec(executed), max_steps=1)
    assert not r["ok"] and r["evidence"]["code"] == "S2_BAD_COMMAND", r
    assert executed == []


@pytest.mark.asyncio
async def test_s2_tap_no_visible_es_selector_not_found():
    """Fila no visible → SELECTOR_NOT_FOUND honesto, sin tocar."""
    executed = []
    decide = script_decide([dec("TAP", 0, conf=0.4)])
    r = await loop.run_goal("look at items",
                            _observe=_c(state([cand(0, visible=False)])),
                            _decide=decide, _advise=tap_advise(0),
                            _execute_fn=ok_exec(executed), max_steps=1)
    assert not r["ok"], r
    assert r["evidence"]["code"] == "SELECTOR_NOT_FOUND", r
    assert executed == []


@pytest.mark.asyncio
async def test_s2_tap_no_clickable_no_muta():
    """Sin clickable no hay mutación: guidance + re-observe + S1."""
    executed = []
    decide = script_decide([dec("TAP", 0, conf=0.4),
                            dec("DONE", "NONE", conf=0.95)])
    r = await loop.run_goal("look at items",
                            _observe=_c(state([cand(0, clickable=False)])),
                            _decide=decide, _advise=tap_advise(0),
                            _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_ok)
    assert r["ok"], r
    assert executed == []  # nunca dispatchGesture ciego desde S2-direct
    assert len(decide.calls) == 2, decide.calls  # S1 retomó tras re-observe


@pytest.mark.asyncio
async def test_s2_back_forense_phase(tmp_path):
    """BACK re-ratificado: forense phase s2_direct_back con via."""
    logf = str(tmp_path / "run.jsonl")
    first = state([cand(0), cand(1)], snap=11)
    second = state([cand(0), cand(1)], snap=12)
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
                 "stop": False}, {"in_tokens": 10, "out_tokens": 2})

    executed = []
    decide = script_decide([dec("TAP", 0, conf=0.3),
                            dec("DONE", "NONE", conf=0.95)])
    r = await loop.run_goal("go back once", _observe=obs,
                            _decide=decide, _advise=advise,
                            _execute_fn=ok_exec(executed),
                            _verify_done=fake_verify_ok, log_path=logf)
    assert r["ok"], r
    assert any(a.get("kind") == "back" for a in executed), executed
    raw = open(logf, encoding="utf-8").read()
    assert "s2_direct_back" in raw


# --- §12.2: first_result (hint, nunca poda) ---


def dense_rows():
    cands = [cand(i, label="Entry", cls="android.widget.TextView")
             for i in range(5)]
    cands.append(cand(5, label="", cls="android.widget.FrameLayout",
                      clickable=False, scrollable=True))
    rows, _ = H.build_table(cands, 720, 1600)
    return rows


def test_first_result_marca_densa_sin_podar():
    rows = dense_rows()
    assert len(rows) == 6  # tabla completa: NUNCA se recorta a 1
    assert H.first_result(rows) == 0  # primer interactivo del grupo


def test_first_result_none_sin_contenedor_claro():
    assert H.first_result([]) is None
    assert H.first_result(None) is None
    # Sin scrollable no hay lista densa: nunca inventar.
    rows, _ = H.build_table([cand(i) for i in range(5)], 720, 1600)
    assert H.first_result(rows) is None
    # Grupo menor que el mínimo tampoco marca.
    small = [cand(0), cand(1),
             cand(2, clickable=False, scrollable=True, label="")]
    r2, _ = H.build_table(small, 720, 1600)
    assert H.first_result(r2) is None


def test_table_lines_antepone_first_result():
    rows = dense_rows()
    lines = loop._table_lines(rows, H.first_result(rows))
    assert lines[0] == "FIRST_RESULT: 0"
    assert len(lines) == len(rows) + 1  # tabla completa + hint
    plain = loop._table_lines(rows)
    assert plain == lines[1:]
    assert loop._table_lines(rows, None) == plain  # None: sin línea


@pytest.mark.asyncio
async def test_ask_decision_state_lleva_first_result(monkeypatch):
    """El state S1 en inglés incluye first_result en cabecera."""
    captured = {}

    async def fake_post(payload):
        captured.update(payload)
        n = len(payload["state"]["table"])
        keys = [str(r[0]) for r in payload["state"]["table"]] + ["NONE"]
        probs_t = {k: (0.8 if k == "0" else 0.2 / max(n, 1)) for k in keys}
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
    rows = dense_rows()
    d, _ = await jev_client.ask_decision("goal", rows, 9,
                                         current_app="com.example.app")
    assert d["action"] == "TAP"
    assert captured["state"]["first_result"] == 0
    # Override explícito del loop se respeta.
    await jev_client.ask_decision("goal", rows, 9, first_result=3)
    assert captured["state"]["first_result"] == 3


@pytest.mark.asyncio
async def test_loop_pasa_first_result_a_s1_y_forense(tmp_path):
    """El loop calcula first_result, lo pasa al pass S1 y al forense."""
    logf = str(tmp_path / "run.jsonl")
    cands = [cand(i, label="Entry", cls="android.widget.TextView")
             for i in range(5)]
    cands.append(cand(5, label="", cls="android.widget.FrameLayout",
                      clickable=False, scrollable=True))
    decide = script_decide([dec("TAP", 0), dec("DONE", "NONE")])
    r = await loop.run_goal("look at items",
                            _observe=_c(state(cands)),
                            _decide=decide, _advise=tap_advise(0),
                            _execute_fn=ok_exec([]),
                            _verify_done=fake_verify_ok, log_path=logf)
    assert r["ok"], r
    assert decide.calls[0]["first_result"] == 0, decide.calls
    lines = [json.loads(l) for l in open(logf, encoding="utf-8")]
    assert any(e.get("first_result") == 0 for e in lines), lines


# --- §12.3: run_signature fail-fast ---


def test_build_run_signature_campos_y_progreso():
    fp_a, fp_b = "a" * 64, "b" * 64
    moving = H.build_run_signature(code="STUCK_SAME", stalled_step="TAP:12",
                                   snapshot_first=1, snapshot_last=5,
                                   fingerprint_first=fp_a,
                                   fingerprint_last=fp_b)
    assert moving == {"code": "STUCK_SAME", "stalled_step": "TAP:12",
                      "snapshot_first": 1, "snapshot_last": 5,
                      "fingerprint_first": fp_a, "fingerprint_last": fp_b,
                      "progress": True}
    stalled = H.build_run_signature(code="STUCK_SAME",
                                    stalled_step="ESCALATE:NONE",
                                    snapshot_first=7, snapshot_last=7,
                                    fingerprint_first=fp_a,
                                    fingerprint_last=fp_a)
    assert stalled["progress"] is False
    # Fingerprint igual también estanca aunque el snapshot rote.
    fp_same = H.build_run_signature(code="STUCK", stalled_step="TAP:0",
                                    snapshot_first=1, snapshot_last=2,
                                    fingerprint_first=fp_a,
                                    fingerprint_last=fp_a)
    assert fp_same["progress"] is False


def test_same_signature_regla_operativa():
    base = H.build_run_signature(code="STUCK_SAME", stalled_step="TAP:12",
                                 snapshot_first=7, snapshot_last=7,
                                 fingerprint_first="a" * 64,
                                 fingerprint_last="a" * 64)
    assert H.same_signature(base, dict(base)) is True
    other_code = dict(base, code="TIMEOUT")
    assert H.same_signature(base, other_code) is False
    other_step = dict(base, stalled_step="TAP:13",
                      fingerprint_first="x" * 64, fingerprint_last="y" * 64)
    assert H.same_signature(base, other_step) is False
    # Mismo code + mismo par fingerprint estancado, distinto stalled_step.
    fp_pair = dict(base, stalled_step="ESCALATE:NONE")
    assert H.same_signature(base, fp_pair) is True
    assert H.same_signature(base, None) is False
    assert H.same_signature("x", dict(base)) is False


@pytest.mark.asyncio
async def test_run_goal_emite_run_signature_determinista(tmp_path):
    """Toda corrida ok:false trae run_signature; mismo historial →
    misma firma (fail-fast: NO relanzar igual firma)."""
    logf = str(tmp_path / "run.jsonl")

    async def run_once(log):
        decide = script_decide([dec("TAP", 0, conf=0.95)] * 5)
        return await loop.run_goal("look at items",
                                   _observe=_c(state([cand(0), cand(1)])),
                                   _decide=decide, _advise=tap_advise(0),
                                   _execute_fn=ok_exec([]), log_path=log,
                                   max_steps=6)

    r1 = await run_once(logf)
    assert not r1["ok"], r1
    sig = r1.get("run_signature")
    assert set(sig) == {"code", "stalled_step", "snapshot_first",
                        "snapshot_last", "fingerprint_first",
                        "fingerprint_last", "progress"}, sig
    assert sig["code"] == "STUCK_SAME" and sig["progress"] is False
    r2 = await run_once(None)
    assert H.same_signature(r1["run_signature"],
                            r2["run_signature"]) is True
    finals = [json.loads(l) for l in open(logf, encoding="utf-8")
              if "run_signature" in l]
    assert finals and finals[-1]["run_signature"] == sig, finals


# --- §12.4: clipboard genérico ---


def _dumpsys_with(url):
    return ("Clipboard service:\n  Primary clip:\n"
            f"  {{ text/plain {{T(a1b2) {{{url}}}}}"
            " mPrivateTimestamp=123 }}\n")


def test_parse_dumpsys_clipboard():
    url = "https://example.com/n/abc123"
    assert C.parse_dumpsys_clipboard(_dumpsys_with(url)) == url
    assert C.parse_dumpsys_clipboard("") == ""
    assert C.parse_dumpsys_clipboard("sin sección relevante") == ""
    assert C.parse_dumpsys_clipboard(
        "Primary clip:\n  { text/plain {T(x) {plain text}} }") == ""


def test_clipboard_error_solo_forma():
    assert C.clipboard_error("https://example.com/n/abc123") is None
    assert C.clipboard_error("http://example.com/x") is None
    err = C.clipboard_error("")
    assert err["code"] == "CLIPBOARD_EMPTY"
    err = C.clipboard_error("plain text without shape")
    assert err["code"] == "CLIPBOARD_EMPTY"


def test_clipboard_slot_opaco():
    url = "https://example.com/n/abc123"
    slot = C.clipboard_slot(url)
    assert slot == {"text": url, "len": len(url),
                    "sha256": hashlib.sha256(url.encode()).hexdigest(),
                    "consumed": False}


class _Proc:
    def __init__(self, stdout):
        self.stdout = stdout


def test_read_clipboard_dumpsys_y_vacio():
    url = "https://example.com/n/abc123"
    r = C.read_clipboard(_run=lambda *a, **k: _Proc(_dumpsys_with(url)))
    assert r["ok"] and r["evidence"]["text"] == url, r
    assert r["evidence"]["via"] == "dumpsys"
    assert r["evidence"]["clipboard_len"] == len(url)
    assert r["evidence"]["clipboard_sha256"] == (
        hashlib.sha256(url.encode()).hexdigest())
    empty = C.read_clipboard(_run=lambda *a, **k: _Proc(""))
    assert not empty["ok"], empty
    assert empty["evidence"]["code"] == "CLIPBOARD_EMPTY", empty


def test_read_clipboard_fallback_paste_readback():
    url = "https://example.com/n/abc123"
    r = C.read_clipboard(_run=lambda *a, **k: _Proc(""),
                         _fallback_text=url)
    assert r["ok"] and r["evidence"]["via"] == "paste-readback", r
    # Fallback sin forma tampoco inventa: sigue CLIPBOARD_EMPTY.
    bad = C.read_clipboard(_run=lambda *a, **k: _Proc(""),
                           _fallback_text="plain")
    assert not bad["ok"]
    assert bad["evidence"]["code"] == "CLIPBOARD_EMPTY"


@pytest.mark.asyncio
async def test_clipboard_slot_inyecta_via_type_sin_crudo(tmp_path):
    """Contenido verificado entra como slot opaco `clipboard` y el TYPE
    destino lo escribe vía ACTION_SET_TEXT + confirm_input; forense solo
    len+sha256, nunca crudo."""
    logf = str(tmp_path / "run.jsonl")
    url = "https://example.com/n/abc123"

    def field_with(text, focused=True):
        return {"id": "n_0", "label": "Note", "text": text, "desc": "",
                "cls": "android.widget.EditText", "class_short": "EditText",
                "flags": "edit|foc" if focused else "edit",
                "bounds": [0, 200, 720, 300], "clickable": True,
                "editable": True, "focused": focused, "scrollable": False,
                "visible": True,
                "resource_id": "com.example.app/id/n_0"}

    calls = {"n": 0}

    async def obs():
        calls["n"] += 1
        shown = "" if calls["n"] <= 2 else url
        focused = calls["n"] >= 2
        return {"package": "com.example.app", "activity": "Form",
                "snapshot_id": 30 + calls["n"], "screen_height": 1600,
                "screen_width": 720,
                "candidates": [field_with(shown, focused)], "raw_count": 1}

    async def compile_clip(goal, table_lines=None, history_summary="",
                           current_app=""):
        return ({"command": "EXECUTE_GOAL", "package": "",
                 "screen_goal_en": "Form open, input focused",
                 "preloaded_inputs": {C.CLIPBOARD_SLOT: url},
                 "expected_terminal_state": "Link visible in the field",
                 "guidance_for_s1": "Type the clipboard payload.",
                 "stop": False},
                {"in_tokens": 30, "out_tokens": 5})

    typed = []

    async def exe(action):
        typed.append(action)
        return {"ok": True, "verified": True, "evidence": {"via": "test"}}

    decide = script_decide([dec("TYPE", 0), dec("DONE", "NONE")])
    r = await loop.run_goal("look at items", _observe=obs, _decide=decide,
                            _compile=compile_clip, _execute_fn=exe,
                            _verify_done=fake_verify_ok, log_path=logf)
    assert r["ok"], r
    writes = [a["text"] for a in typed if a["kind"] == "type_text"]
    assert writes and writes[-1] == url, typed
    raw = open(logf, encoding="utf-8").read()
    assert url not in raw  # opaco: nunca crudo en forense
    assert hashlib.sha256(url.encode()).hexdigest() in raw
    assert '"slot": "clipboard"' in raw
    assert '"input_verified": true' in raw
