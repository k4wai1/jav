"""Motor observe→decide→mutate→verify. Genérico; la tarea define preguntas.

Cada iteración = 1 llamada Jev (batch decide+verify). Acciones en enum
cerrado: tap_node | type_text | scroll | done | abort | noop | escalate.
`noop` es no-op explícito para fases de solo-verificación (se loguea,
no toca el dispositivo). `escalate` es no-op que escala a Sistema 2
(se loguea con fase/candidatas/conf, no toca el dispositivo).
Nada más llega al dispositivo.
"""
from __future__ import annotations

import json
import os
import time

from . import jev_client
from .tools import ui as ui_tools

CLOSED_ACTIONS = {"tap_node", "type_text", "scroll", "done", "abort", "noop",
                  "escalate"}
MAX_STALE_STREAK = 3


async def _execute(action: dict) -> dict:
    kind = action.get("kind")
    if kind == "noop":
        return {"ok": True, "verified": True,
                "evidence": {"noop": True}}
    if kind == "escalate":
        # Como noop: no toca el dispositivo; loguea y escala a Sistema 2.
        return {"ok": True, "verified": True,
                "evidence": {"escalated": True,
                             "reason": action.get("reason", "ESCALATE"),
                             "conf": action.get("conf"),
                             "tau": action.get("tau")}}
    if kind == "tap_node":
        return await ui_tools.tap_node(action["node_id"], action["snapshot_id"])
    if kind == "type_text":
        return await ui_tools.type_text(action["node_id"],
                                        action["snapshot_id"], action["text"])
    if kind == "scroll":
        return await ui_tools.scroll(action.get("direction", "down"),
                                     action.get("node_id"))
    raise jev_client.JevHallucination(f"acción fuera del enum: {kind}")


def _is_sensitive(task, action: dict) -> bool:
    hook = getattr(task, "is_sensitive", None)
    return bool(hook(action)) if callable(hook) else False


async def run(task, max_steps: int = 20, timeout_s: float = 60,
              ask_fn=None, dry_run: bool = False,
              log_path: str | None = None) -> dict:
    ask_fn = ask_fn or jev_client.ask
    t0 = time.time()
    history: list = []
    stale_streak = 0
    calls = 0
    total_cost = 0.0
    step = 0
    logf = open(log_path, "a", encoding="utf-8") if log_path else None

    def log(entry: dict) -> None:
        if logf is None:
            return
        logf.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logf.flush()

    try:
        while step < max_steps and (time.time() - t0) < timeout_s:
            step += 1
            state = await task.observe()
            questions = task.questions(state, history)
            answers, usage = await ask_fn(state, questions)
            calls += 1
            total_cost += float(usage.get("cost", 0.0) or 0.0)
            try:
                action = task.interpret(answers, state, history)
            except jev_client.JevHallucination as e:
                log({"step": step, "phase": _phase(task),
                     "snapshot": state.get("snapshot_id"),
                     "answers": _short(answers), "error": str(e)})
                return _fail("JEV_HALLUCINATION", str(e), history, step,
                             t0, calls, total_cost)
            if action.get("kind") not in CLOSED_ACTIONS:
                log({"step": step, "phase": _phase(task), "error": "bad-kind",
                     "action": action})
                return _fail("JEV_HALLUCINATION",
                             f"acción inválida: {action.get('kind')}",
                             history, step, t0, calls, total_cost)
            entry = {"step": step, "phase": _phase(task),
                     "snapshot": state.get("snapshot_id"),
                     "n_cands": len(state.get("candidates", [])),
                     "cands": [(c.get("id"), c.get("label"))
                               for c in state.get("candidates", [])],
                     "options": list((questions.get("next_action") or {})
                                     .get("criteria", {}).keys()),
                     "answers": _short(answers),
                     "chosen_action": action}
            if action["kind"] == "done":
                ok, evidence = await task.verify_final(state)
                entry["final"] = {"ok": ok, "evidence": evidence}
                log(entry)
                return _done(ok, evidence, history, step, t0, calls, total_cost)
            if action["kind"] == "abort":
                log(entry)
                return _fail(action.get("code", "JEV_ABORT"),
                             action.get("reason", "abort de Jev"),
                             history, step, t0, calls, total_cost)
            if dry_run and _is_sensitive(task, action):
                entry["planned"] = True
                log(entry)
                return {"ok": True, "verified": False,
                        "evidence": {"dry_run": True, "planned_send": action,
                                     "phase": _phase(task),
                                     "snapshot": state.get("snapshot_id")},
                        "steps": step,
                        "duration_ms": int((time.time() - t0) * 1000),
                        "jev_calls": calls, "jev_cost": total_cost,
                        "history": history}
            res = await _execute(action)
            entry["result"] = {"ok": res.get("ok"),
                               "evidence": res.get("evidence")}
            log(entry)
            history.append({"step": step, "action": action, "result": res,
                            "snapshot": state.get("snapshot_id")})
            if not res.get("ok"):
                code = res.get("evidence", {}).get("code", "?")
                if code == "STALE_SNAPSHOT" and stale_streak < MAX_STALE_STREAK:
                    stale_streak += 1
                    continue
                if code == "STALE_SNAPSHOT":
                    return _fail("UI_UNSTABLE", "3 STALE seguidos", history,
                                 step, t0, calls, total_cost)
                return _fail(code, res.get("evidence", {}).get("error", "?"),
                             history, step, t0, calls, total_cost)
            stale_streak = 0
        code = "TIMEOUT" if (time.time() - t0) >= timeout_s else "STUCK"
        return _fail(code, f"{step} pasos sin done", history, step, t0,
                     calls, total_cost)
    finally:
        if logf is not None:
            logf.close()


def _phase(task) -> str:
    phases = getattr(task, "PHASES", [])
    idx = getattr(task, "phase", "?")
    if isinstance(idx, int) and 0 <= idx < len(phases):
        return phases[idx]
    return str(idx)


def _short(answers: dict) -> dict:
    return {n: {"key": a.get("key"), "p": round(float(a.get("p", 0.0)), 3)}
            for n, a in (answers or {}).items()
            if isinstance(a, dict)}


def _done(ok: bool, evidence: dict, history: list, steps: int,
          t0: float, calls: int, cost: float) -> dict:
    return {"ok": ok, "verified": bool(ok), "evidence": evidence,
            "steps": steps, "duration_ms": int((time.time() - t0) * 1000),
            "jev_calls": calls, "jev_cost": cost, "history": history}


def _fail(code: str, error: str, history: list, steps: int,
          t0: float, calls: int, cost: float) -> dict:
    return {"ok": False, "verified": False,
            "evidence": {"code": code, "error": error},
            "steps": steps, "duration_ms": int((time.time() - t0) * 1000),
            "jev_calls": calls, "jev_cost": cost, "history": history}
