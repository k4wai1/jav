"""Tests de verificación read-back tras TYPE (patrón M2, P0-2)."""
import pytest

from jev_mcp.core import loop_helpers as H


def row(**kw):
    base = {"idx": 0, "id": "n_0", "label": "Message", "text": "",
            "resource_id": "com.example.messenger/id/message_input",
            "bounds": [0, 200, 720, 300], "clickable": True,
            "editable": True, "focused": True, "scrollable": False,
            "visible": True, "class_short": "EditText", "flags": "edit|foc"}
    base.update(kw)
    return base


def cand(**kw):
    base = {"id": "n_0", "label": "Message", "text": "",
            "resource_id": "com.example.messenger/id/message_input",
            "bounds": [0, 200, 720, 300]}
    base.update(kw)
    return base


def test_input_matches_exact_span():
    v = H.prepare_input_verification(row(), "hola mundo")
    assert v is not None and v["target"]["id"] == "n_0"
    assert v["text"] == "hola mundo"
    # rid estable: matchea aunque cambie el resto.
    assert H.input_matches(
        [cand(text="hola mundo", bounds=[9, 9, 9, 9])], v) is True
    # texto parcial → no matchea.
    assert H.input_matches([cand(text="hola")], v) is False
    # fallback id+hint+bounds sin rid estable.
    v2 = H.prepare_input_verification(row(resource_id=""), "hola mundo")
    assert H.input_matches(
        [cand(resource_id="", text="hola mundo")], v2) is True
    assert H.input_matches(
        [cand(resource_id="", text="hola mundo",
              bounds=[1, 2, 3, 4])], v2) is False
    # exactamente 1: duplicado con mismo texto no confirma.
    assert H.input_matches(
        [cand(text="hola mundo"), cand(text="hola mundo")], v) is False


def test_prepare_rechaza_no_verificable():
    assert H.prepare_input_verification(row(editable=False), "x") is None
    assert H.prepare_input_verification(None, "x") is None
    assert H.prepare_input_verification(row(), "") is None
    assert H.prepare_input_verification(
        row(resource_id="com.example.messenger/id/password",
            label="Password"), "x") is None


@pytest.mark.asyncio
async def test_confirm_input_ok_al_primer_poll():
    v = H.prepare_input_verification(row(), "hola mundo")
    calls = {"n": 0}

    async def obs():
        calls["n"] += 1
        return {"snapshot_id": 11, "candidates": [cand(text="hola mundo")]}

    ok, info = await H.confirm_input(v, obs)
    assert ok and info == {"snapshot": 11, "attempts": 0}
    assert calls["n"] == 1


@pytest.mark.asyncio
async def test_confirm_input_timeout_sin_match(monkeypatch):
    monkeypatch.setattr(H, "INPUT_TIMEOUT_MS", 90)
    monkeypatch.setattr(H, "POLL_MS", 10)
    v = H.prepare_input_verification(row(), "hola mundo")

    async def obs():
        return {"snapshot_id": 12, "candidates": [cand(text="hola")]}

    ok, info = await H.confirm_input(v, obs)
    assert not ok and info["snapshot"] == 12 and info["attempts"] >= 1
