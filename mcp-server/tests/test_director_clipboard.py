"""Tests v5 §4.1/§10: set_clipboard + get_clipboard (con stubs, sin Jam).

Vía elegida: Jam `set_clipboard` (ClipboardManager, sin shell) + read-back
de forma host. Mientras Jam no lo exponga: CLIPBOARD_UNSUPPORTED
(jam-api-missing) honesto y el director usa type_text directo.
"""
import hashlib

import pytest

from jev_mcp.tools import clipboard as C


URL = "https://example.com/n/abc123"


def _dumpsys_with(url):
    return ("Clipboard service:\n  Primary clip:\n"
            f"  {{ text/plain {{T(a1b2) {{{url}}}}}"
            " mPrivateTimestamp=123 }}\n")


class _Proc:
    def __init__(self, stdout):
        self.stdout = stdout


class _JamOk:
    def __init__(self):
        self.calls = []

    async def set_clipboard(self, text):
        self.calls.append(text)
        return {"chars": len(text)}


class _JamMissing:
    async def set_clipboard(self, text):
        from jev_mcp.socket_client import JamError

        raise JamError("METHOD_NOT_ALLOWED",
                       "método desconocido: set_clipboard")


@pytest.mark.asyncio
async def test_set_clipboard_ok_con_readback():
    jam = _JamOk()
    r = await C.set_clipboard(
        URL, _jam=jam,
        _run=lambda *a, **k: _Proc(_dumpsys_with(URL)))
    assert r["ok"] and r["verified"] is True, r
    assert jam.calls == [URL]
    assert r["evidence"]["via"] == "jam-api"
    assert r["evidence"]["clipboard_len"] == len(URL)
    assert r["evidence"]["clipboard_sha256"] == (
        hashlib.sha256(URL.encode()).hexdigest())


@pytest.mark.asyncio
async def test_set_clipboard_sin_forma_no_toca_jam():
    jam = _JamOk()
    for bad in ("", "plain text without shape"):
        r = await C.set_clipboard(bad, _jam=jam)
        assert not r["ok"], r
        assert r["evidence"]["code"] == "CLIPBOARD_EMPTY", r
    assert jam.calls == []


@pytest.mark.asyncio
async def test_set_clipboard_jam_missing_unsupported():
    r = await C.set_clipboard(
        URL, _jam=_JamMissing(),
        _run=lambda *a, **k: _Proc(_dumpsys_with(URL)))
    assert not r["ok"], r
    assert r["evidence"]["code"] == "CLIPBOARD_UNSUPPORTED", r
    assert "jam-api-missing" in r["evidence"]["error"]


@pytest.mark.asyncio
async def test_set_clipboard_readback_sin_forma():
    jam = _JamOk()
    r = await C.set_clipboard(URL, _jam=jam,
                              _run=lambda *a, **k: _Proc(""))
    assert not r["ok"], r
    assert r["evidence"]["code"] == "CLIPBOARD_EMPTY", r


def test_get_clipboard_alias_de_read_clipboard():
    assert C.get_clipboard is C.read_clipboard
    r = C.get_clipboard(_run=lambda *a, **k: _Proc(_dumpsys_with(URL)))
    assert r["ok"] and r["evidence"]["text"] == URL, r


@pytest.mark.asyncio
async def test_director_tap_idx_resuelve_vigente():
    from jev_mcp import director as D

    cands = [
        {"id": "n_0", "label": "Copy link", "text": "Copy link",
         "desc": "", "cls": "android.widget.Button",
         "bounds": [0, 100, 720, 200],
         "clickable": True, "editable": False, "focused": False,
         "scrollable": False, "visible": True},
        {"id": "n_1", "label": "Cancel", "text": "Cancel",
         "desc": "", "cls": "android.widget.Button",
         "bounds": [0, 300, 720, 400],
         "clickable": True, "editable": False, "focused": False,
         "scrollable": False, "visible": True},
    ]
    calls = []

    async def fake_tap(node_id, snapshot_id):
        calls.append((node_id, snapshot_id))
        return {"ok": True, "verified": True,
                "evidence": {"node_id": node_id, "via": "action_click"}}

    r = await D.tap_idx(0, 41, candidates=cands, screen_height=1600,
                        _tap=fake_tap)
    assert r["ok"] and calls == [("n_0", 41)], (r, calls)
    # Índice fuera de tabla -> SELECTOR_NOT_FOUND sin tocar.
    r2 = await D.tap_idx(7, 41, candidates=cands, screen_height=1600,
                         _tap=fake_tap)
    assert not r2["ok"], r2
    assert r2["evidence"]["code"] == "SELECTOR_NOT_FOUND", r2
    assert len(calls) == 1
