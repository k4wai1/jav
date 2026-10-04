"""Tests del loop con decisiones guionizadas (sin dispositivo ni Jev)."""
import pytest

from jev_mcp import jev_client, loop
from jev_mcp.tools import ui as ui_tools

STATE = {"package": "com.whatsapp", "snapshot_id": 7, "candidates": []}


class ScriptTask:
    """Tarea guionizada: answers fijos por paso, done al final."""

    def __init__(self, actions):
        self.actions = list(actions)
        self.i = 0

    async def observe(self):
        return dict(STATE)

    def questions(self, state, history):
        return {"next": {"type": "choice", "instructions": "x",
                         "criteria": {"a": "a", "b": "b"}}}

    def interpret(self, answers, state, history):
        a = self.actions[self.i]
        self.i += 1
        return a

    async def verify_final(self, state):
        return True, {"by": "test"}


def ans(kind="tap_node", **kw):
    d = {"kind": kind}
    d.update(kw)
    return d


@pytest.mark.asyncio
async def test_happy_path(monkeypatch):
    async def fake_tap(node_id, snapshot_id):
        return {"ok": True, "verified": True, "evidence": {"via": "gesture"}}
    monkeypatch.setattr(ui_tools, "tap_node", fake_tap)

    async def ask(state, questions):
        return {"next": {"kind": "choice", "key": "a", "p": 1.0,
                         "confidence": 1.0, "raw": {}}}, {"cost": 0.0}

    task = ScriptTask([ans(node_id="n_1", snapshot_id=7), {"kind": "done"}])
    r = await loop.run(task, ask_fn=ask)
    assert r["ok"] and r["verified"]
    assert r["steps"] == 2 and len(r["history"]) == 1


@pytest.mark.asyncio
async def test_stale_retry_then_ok(monkeypatch):
    calls = {"n": 0}

    async def flaky(node_id, snapshot_id):
        calls["n"] += 1
        if calls["n"] < 3:
            return {"ok": False, "verified": False,
                    "evidence": {"code": "STALE_SNAPSHOT", "error": "viejos"}}
        return {"ok": True, "verified": True, "evidence": {}}
    monkeypatch.setattr(ui_tools, "tap_node", flaky)

    async def ask(state, questions):
        return {"next": {"kind": "choice", "key": "a", "p": 1.0,
                         "confidence": 1.0, "raw": {}}}, {"cost": 0.0}

    task = ScriptTask([ans(node_id="n_1", snapshot_id=7),
                       ans(node_id="n_1", snapshot_id=8),
                       ans(node_id="n_1", snapshot_id=9),
                       {"kind": "done"}])
    r = await loop.run(task, ask_fn=ask)
    assert r["ok"], r
    assert calls["n"] == 3


@pytest.mark.asyncio
async def test_stale_x3_aborta(monkeypatch):
    async def stale(node_id, snapshot_id):
        return {"ok": False, "verified": False,
                "evidence": {"code": "STALE_SNAPSHOT", "error": "viejos"}}
    monkeypatch.setattr(ui_tools, "tap_node", stale)

    async def ask(state, questions):
        return {"next": {"kind": "choice", "key": "a", "p": 1.0,
                         "confidence": 1.0, "raw": {}}}, {"cost": 0.0}

    task = ScriptTask([ans(node_id="n_1", snapshot_id=i) for i in range(9)]
                      + [{"kind": "done"}])
    r = await loop.run(task, ask_fn=ask)
    assert not r["ok"] and r["evidence"]["code"] == "UI_UNSTABLE", r


@pytest.mark.asyncio
async def test_hallucination():
    class BadTask(ScriptTask):
        def interpret(self, answers, state, history):
            raise jev_client.JevHallucination("clave rara")

    async def ask(state, questions):
        return {}, {"cost": 0.0}

    r = await loop.run(BadTask([{"kind": "done"}]), ask_fn=ask)
    assert r["evidence"]["code"] == "JEV_HALLUCINATION", r


@pytest.mark.asyncio
async def test_abort_con_motivo():
    async def ask(state, questions):
        return {"next": {"kind": "abort", "reason": "no veo el chat",
                         "code": "NO_MATCH"}}, {"cost": 0.0}

    class AbortTask(ScriptTask):
        def interpret(self, answers, state, history):
            return answers["next"]

    r = await loop.run(AbortTask([]), ask_fn=ask)
    assert not r["ok"] and r["evidence"]["code"] == "NO_MATCH", r


@pytest.mark.asyncio
async def test_escalate_aceptado_sin_tocar_dispositivo(monkeypatch):
    assert "escalate" in loop.CLOSED_ACTIONS
    # _execute no debe llamar a tools UI: si lo intenta, el test falla.
    async def _boom(*a, **kw):
        raise AssertionError("escalate no debe tocar el dispositivo")
    monkeypatch.setattr(ui_tools, "tap_node", _boom)
    monkeypatch.setattr(ui_tools, "type_text", _boom)
    monkeypatch.setattr(ui_tools, "scroll", _boom)
    r = await loop._execute({"kind": "escalate", "reason": "LOW_CONF",
                             "conf": 0.5, "tau": 0.70})
    assert r["ok"] and r["verified"]
    assert r["evidence"]["escalated"] is True

    async def ask(state, questions):
        return {"next": {"kind": "choice", "key": "a", "p": 1.0,
                         "confidence": 1.0, "raw": {}}}, {"cost": 0.0}

    task = ScriptTask([{"kind": "escalate", "reason": "LOW_CONF"},
                       {"kind": "done"}])
    r = await loop.run(task, ask_fn=ask)
    assert r["ok"] and r["verified"], r
    assert r["history"][0]["action"]["kind"] == "escalate"
