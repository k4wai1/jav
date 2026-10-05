"""Agente simple y general: run_goal(goal: str) (generic-dual-tier §1, §6-7).

Ciclo bootstrap → observe→decide→mutate→verify, un paso = una primitiva.
Sin paquetes, contactos ni fases prefijadas; sin literales de dominio.

- Bootstrap §5.3: observe (foreground + dump_ui fresco) → S2-director con
  {goal, current_app, table_lines} ANTES del primer pass S1. Si la app
  requerida no está en foreground, S2 emite OPEN_APP primero y el loop
  ejecuta `mcp.open_app(package)` + ~600 ms + dump fresco antes del
  primer S1. Sin dump fresco no hay S1. S2 stub en bootstrap →
  S2_UNAVAILABLE inmediato (nunca ciclar en giro ni adivinar paquetes).
- S1 Jev (jev_client.ask_decision, single-pass, 100% en inglés) decide
  [TAP,TYPE,SCROLL_DOWN,SCROLL_UP,BACK,DONE,ESCALATE] + target 0..253|NONE
  + needs_system_2 + conf sobre la tabla enriquecida
  [idx, class_short, flags, label] + current_app + screen_goal.
- S2 GLM-5.3 (s2_client.advise) devuelve comandos EJECUTABLES
  {command: OPEN_APP|TYPE|BACK|HINT, package/target/text/guidance_for_s1/
  stop} ante bootstrap / ESCALATE / conf < TAU (0.70) / redacción abierta
  / bloqueo semántico. S2 nunca tapea directo: el loop ejecuta
  (OPEN_APP/BACK) o inyecta s2_guidance + text_payload en el siguiente
  pass S1 (TYPE/HINT).
- TYPE usa `text_payload` de S2 vía ACTION_SET_TEXT; en forense solo
  `text_payload_hash` (sha256) + `s2_text_len`, nunca el texto crudo.
- Cada llamada LLM pasa por CostTracker (log [COST] + `cost` en forense
  + acumulado jev_cost/s2_cost/total_cost en el resultado; el bootstrap
  S2 también pasa por CostTracker con step 0).
- Compuertas §8: estructurales siempre (JSON válido, target en tabla
  vigente, visible, coords en pantalla, snapshot fresco, comando S2
  válido con package con forma y text no vacío en TYPE); críticas /
  irreversibles exigen preview + confirm:true (sin él se planean sin
  ejecutar: needs_confirm). FORBIDDEN solo opt-in por goal (forbidden?).
- type exige foco explícito: sin focused → tap previo explícito (nada
  implícito). Acciones no devuelven snapshot; el cliente verifica.
- snapshot mismatch ×3 → UI_UNSTABLE; misma (kind,node_id) ×3 → STUCK_SAME;
  misma decisión (action+target) ×3 sin cambio útil de snapshot → STUCK_SAME;
  S2 mock/stub → S2_UNAVAILABLE inmediato (nunca ciclar en giro).
- DONE nunca directo: gate DONE→S2 (s2_client.verify_done, misma key)
  con snapshot final + historial; achieved=true → ok; rechazo → sigue
  el loop (máx steps), nunca éxito falso. Verificación + coste en
  forense (`done_verify` + `cost_s2_verify` + [COST]).
"""
from __future__ import annotations

import asyncio
import hashlib
import json
import time

from . import jev_client, s2_client
from .core import guards as _guards
from .core import loop_helpers as _h
from .core.cost import CostTracker
from .core.cost import glm_model_id as _glm_id
from .core.cost import jev_model_id as _jev_id
from .tools import app as app_tools
from .tools import ui as ui_tools

TAU = 0.70
MAX_STALE_STREAK = 3
STUCK_N = 2  # 2 previas iguales + actual = ×3 → STUCK_SAME
BOOTSTRAP_DELAY_S = 0.6  # estabilización tras open_app antes del re-dump

CLOSED_ACTIONS = {"tap_node", "type_text", "scroll", "back", "done",
                  "abort", "noop", "escalate", "open_app"}


class ObserveError(Exception):
    def __init__(self, code: str, error: str):
        super().__init__(f"{code}: {error}")
        self.code = code
        self.error = error


async def _default_observe() -> dict:
    res = await ui_tools.read_screen()
    if not res.get("ok"):
        ev = res.get("evidence", {}) or {}
        raise ObserveError(ev.get("code", "OBSERVE_FAILED"),
                           ev.get("error", "read_screen falló"))
    return res.get("evidence", {})


async def _default_verify(goal: str, observe_fn) -> tuple[bool, dict]:
    """verify_final determinista: re-lee pantalla. Nunca solo-Jev."""
    st = await observe_fn()
    return True, {"goal": goal, "snapshot": st.get("snapshot_id"),
                  "n_cands": len(st.get("candidates", []))}


async def _execute(action: dict) -> dict:
    kind = action.get("kind")
    if kind == "noop":
        return {"ok": True, "verified": True, "evidence": {"noop": True}}
    if kind == "escalate":
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
    if kind == "back":
        return await ui_tools.press_back()
    raise jev_client.JevHallucination(f"acción fuera del enum: {kind}")


def _history_summary(history: list, last: int = 3) -> str:
    parts = []
    for h in history[-last:]:
        a = h.get("action", {})
        parts.append(f"{a.get('kind')}:{a.get('node_id', '-')}")
    return "; ".join(parts)


def _table_lines(rows: list[dict]) -> list[str]:
    """Tabla enriquecida serializada para S2: `idx class_short flags label`."""
    return [f"{r['idx']} {r.get('class_short', 'View')} "
            f"{r.get('flags', '—')} {r['label']}" for r in rows]


def _payload_hash(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def _redacted_command(cmd: dict) -> dict:
    """Comando S2 apto para forense: sin texto crudo, solo hash + longitud."""
    red = {"command": cmd.get("command"),
           "package": cmd.get("package", ""),
           "target": cmd.get("target", "NONE"),
           "guidance_for_s1": cmd.get("guidance_for_s1", ""),
           "stop": bool(cmd.get("stop", False))}
    text = cmd.get("text", "") or ""
    if text:
        red["text_len"] = len(text)
        red["text_sha256"] = _payload_hash(text)
    return red


async def run_goal(goal: str, *, max_steps: int = 20,
                   timeout_s: float = 60,
                   log_path: str | None = None,
                   confirm: bool = False,
                   forbidden: str | None = None,
                   _observe=None, _decide=None, _advise=None,
                   _execute_fn=None, _verify=None,
                   _verify_done=None, _open_app=None,
                   _bootstrap_delay_s: float = BOOTSTRAP_DELAY_S) -> dict:
    """Ejecuta un objetivo en lenguaje natural sobre Android.

    goal: texto libre del operador. Sin paquetes ni contactos.
    confirm: true habilita acciones críticas/irreversibles (con preview
    auditada); sin él se planean sin ejecutar (needs_confirm).
    forbidden: pattern regex opt-in; sin él no hay filtro.
    Devuelve {ok, verified, evidence, hint}-compatible + costes y forense
    en log_path (JSONL por paso: conf, tau, cost, s2_command,
    text_payload_hash).
    """
    observe_fn = _observe or _default_observe
    decide_fn = _decide or jev_client.ask_decision
    advise_fn = _advise or s2_client.advise
    execute_fn = _execute_fn or _execute
    open_app_fn = _open_app or app_tools.open_app
    run_id = str(int(time.time()))
    tracker = CostTracker(run_id=run_id)
    t0 = time.time()
    history: list = []
    stale_streak = 0
    jev_calls = 0
    s2_calls = 0
    step = 0
    s2_guidance = ""
    screen_goal = goal  # verbatim hasta que S2 aporte screen_goal (HINT)
    text_payload = ""  # texto exacto S2 → ACTION_SET_TEXT; S1 nunca redacta
    text_payload_hash = ""
    pending_state: dict | None = None
    prev_dec_sig: tuple | None = None
    prev_snapshot: int | None = None
    same_dec_streak = 0
    logf = open(log_path, "a", encoding="utf-8") if log_path else None

    def log(entry: dict) -> None:
        if logf is None:
            return
        logf.write(json.dumps(entry, ensure_ascii=False) + "\n")
        logf.flush()

    def costs() -> dict:
        return {"jev_cost": tracker.jev_cost, "s2_cost": tracker.s2_cost,
                "total_cost": tracker.total_cost_usd,
                "jev_calls": jev_calls, "s2_calls": s2_calls}

    def done(ok: bool, evidence: dict, steps: int) -> dict:
        d = {"ok": ok, "verified": bool(ok), "evidence": evidence,
             "steps": steps, "duration_ms": int((time.time() - t0) * 1000),
             "history": history}
        d.update(costs())
        return d

    def s2_unavailable(error: str, hint: str, steps: int) -> dict:
        r = done(False, {"code": "S2_UNAVAILABLE", "error": error}, steps)
        r["hint"] = hint
        return r

    async def s2_direct(reason: str, rows: list, current_app: str,
                        need_text: bool = False,
                        usage_step: int | None = None):
        """Consulta a S2-director y valida el comando ejecutable.

        Devuelve (cmd, usage). El llamante traduce mock/excepción a
        S2_UNAVAILABLE y comando inválido a S2_BAD_COMMAND. Nunca actúa.
        """
        out, usage = await advise_fn(
            goal, reason=reason, table_lines=_table_lines(rows),
            history_summary=_history_summary(history),
            need_text=need_text, current_app=current_app,
            screen_goal=screen_goal)
        return s2_client.parse_command(out), usage

    def note_guidance(cmd: dict) -> None:
        """Inyecta guidance_for_s1 (+ screen_goal en HINT) para el próximo S1."""
        nonlocal s2_guidance, screen_goal
        g = cmd.get("guidance_for_s1", "") or ""
        if g:
            s2_guidance = g
            if cmd.get("command") == "HINT":
                screen_goal = g

    async def apply_s2(cmd: dict, current_snapshot: int):
        """Aplica un comando S2 validado (§5.2). Nunca tapea directo.

        Devuelve resultado final si el comando cierra el goal o falla;
        None si el loop debe continuar (re-observe → S1). TYPE solo guarda
        text_payload + guidance (el TYPE S1 va en el paso siguiente con
        snapshot fresco). HINT no muta. OPEN_APP/BACK mutan vía sus tools
        y dejan `pending_state` fresco.
        """
        nonlocal text_payload, text_payload_hash, pending_state
        command = cmd.get("command")
        if command == "TYPE":
            text_payload = cmd.get("text", "") or ""
            text_payload_hash = _payload_hash(text_payload)
            note_guidance(cmd)
            if cmd.get("stop"):
                ok, evidence = await (_verify(goal, observe_fn)
                                      if _verify
                                      else _default_verify(goal, observe_fn))
                return done(ok, evidence, max(step, 0))
            return None
        if command == "HINT":
            note_guidance(cmd)
            if cmd.get("stop"):
                ok, evidence = await (_verify(goal, observe_fn)
                                      if _verify
                                      else _default_verify(goal, observe_fn))
                return done(ok, evidence, max(step, 0))
            return None
        if command == "BACK":
            note_guidance(cmd)
            res = await execute_fn({"kind": "back", "key": "back"})
            history.append({"step": step, "action": {"kind": "back"},
                            "result": res, "snapshot": current_snapshot})
            if not res.get("ok"):
                ev = res.get("evidence", {}) or {}
                return done(False, {"code": ev.get("code", "?"),
                                    "error": ev.get("error", "?")},
                            max(step, 1))
            try:
                pending_state = await observe_fn()
            except ObserveError as e:
                return done(False, {"code": e.code, "error": e.error},
                            max(step, 1))
            return None
        if command == "OPEN_APP":
            note_guidance(cmd)
            res = await open_app_fn(cmd.get("package", ""))
            if not res.get("ok"):
                ev = res.get("evidence", {}) or {}
                return done(False, {"code": ev.get("code", "?"),
                                    "error": ev.get("error", "?")},
                            max(step, 1))
            await asyncio.sleep(_bootstrap_delay_s)
            try:
                pending_state = await observe_fn()
            except ObserveError as e:
                return done(False, {"code": e.code, "error": e.error},
                            max(step, 1))
            return None
        return done(False, {"code": "S2_BAD_COMMAND",
                            "error": f"command no aplicable: {command!r}"},
                    max(step, 1))

    try:
        # --- Bootstrap §5.3: observe → S2-director → [OPEN_APP → open_app
        # + ~600 ms + re-observe] | [HINT/TYPE → guidance/payload]. Antes
        # del primer pass S1; sin dump fresco no hay S1. ---
        try:
            bstate = await observe_fn()
        except ObserveError as e:
            r = done(False, {"code": e.code, "error": e.error}, 0)
            r["hint"] = "revisa conexión con Jam"
            return r
        brows, _ = _h.build_table(bstate.get("candidates", []))
        bsnap = bstate.get("snapshot_id", -1)
        bapp = bstate.get("package", "") or ""
        s2_calls += 1
        try:
            bcmd, busage = await s2_direct("bootstrap", brows, bapp)
        except s2_client.S2EmptyResponse as e:
            err = f"S2_EMPTY_RESPONSE: {e}"[:220]
            log({"step": 0, "phase": "bootstrap", "error": err})
            r = s2_unavailable(err, "reintentar: null-content transitorio "
                                   "de S2", 0)
            return r
        except s2_client.S2BadCommand as e:
            err = {"code": "S2_BAD_COMMAND", "error": str(e)[:220]}
            log({"step": 0, "phase": "bootstrap", "error": err})
            return done(False, err, 0)
        except Exception as e:
            err = f"S2 falló ({type(e).__name__}): {e}"[:220]
            log({"step": 0, "phase": "bootstrap", "error": err})
            return s2_unavailable(err, "falta OPENROUTER_API_KEY o S2 caído",
                                  0)
        if _is_s2_mock(bcmd, busage):
            bi, bo, bpc = _s2_tokens(busage)
            bcost = tracker.track(_glm_id(), bi, bo, step=0, tier="s2",
                                   provider_cost=bpc)
            log({"step": 0, "phase": "bootstrap", "cost_s2": bcost,
                 "error": {"code": "S2_UNAVAILABLE",
                           "error": "S2 respondió mock/stub; sin plan real"}})
            return s2_unavailable("S2 respondió mock/stub; sin plan real",
                                  "falta OPENROUTER_API_KEY o S2 caído", 0)
        bi, bo, bpc = _s2_tokens(busage)
        bcost = tracker.track(_glm_id(), bi, bo, step=0, tier="s2",
                               provider_cost=bpc)
        log({"step": 0, "phase": "bootstrap", "goal": goal,
             "snapshot": bsnap, "current_app": bapp,
             "s2_command": _redacted_command(bcmd), "cost_s2": bcost})
        history.append({"step": 0,
                        "action": {"kind": "bootstrap",
                                   "command": bcmd.get("command")},
                        "result": {"ok": True,
                                   "evidence": _redacted_command(bcmd)},
                        "snapshot": bsnap})
        fin = await apply_s2(bcmd, bsnap)
        if fin is not None:
            return fin

        while step < max_steps and (time.time() - t0) < timeout_s:
            step += 1
            if pending_state is not None:
                state = pending_state
                pending_state = None
            else:
                try:
                    state = await observe_fn()
                except ObserveError as e:
                    log({"step": step, "goal": goal, "error": str(e)})
                    r = done(False, {"code": e.code, "error": e.error}, step)
                    r["hint"] = "revisa conexión con Jam"
                    return r
            rows, by_idx = _h.build_table(state.get("candidates", []))
            snapshot = state.get("snapshot_id", -1)
            screen_h = state.get("screen_height", 0) or 0
            current_app = state.get("package", "") or ""

            # --- S1 single-pass (100% en inglés, §3) ---
            try:
                decision, usage = await decide_fn(
                    goal, rows, snapshot,
                    history_summary=_history_summary(history),
                    s2_guidance=s2_guidance,
                    current_app=current_app,
                    screen_goal=screen_goal)
            except jev_client.JevError as e:
                log({"step": step, "snapshot": snapshot, "error": str(e)})
                return done(False, {"code": "JEV_ERROR", "error": str(e)}, step)
            jev_calls += 1
            in_tok, out_tok, pcost = jev_client._usage_tokens(usage)
            step_cost = tracker.track(_jev_id(), in_tok, out_tok,
                                      step=step, tier="s1",
                                      provider_cost=pcost)
            conf = decision.get("conf", 0.0)

            entry = {"step": step, "goal": goal, "snapshot": snapshot,
                     "n_cands": len(rows), "conf": conf, "tau": TAU,
                     "cost": step_cost, "decision": decision}

            bad = _h.check_decision_json(decision)
            if bad:
                entry["error"] = bad
                log(entry)
                return done(False, bad, step)
            action = decision["action"]

            # --- anti-giro (ii): misma decisión (action+target) ×3 sin
            # cambio de snapshot útil → STUCK_SAME. Va ANTES de la
            # compuerta tau para cubrir también bucles de ESCALATE que
            # nunca ejecutan (el check_stuck_same de abajo solo ve
            # acciones ejecutadas). Genérico, sin literales de dominio.
            dec_sig = (action, decision.get("target", "NONE"))
            if dec_sig == prev_dec_sig and snapshot == prev_snapshot:
                same_dec_streak += 1
            else:
                prev_dec_sig = dec_sig
                prev_snapshot = snapshot
                same_dec_streak = 1
            if same_dec_streak >= 3:
                err = {"code": "STUCK_SAME",
                       "error": f"misma decisión {same_dec_streak}× "
                                f"seguidas sin cambio útil: {dec_sig}"}
                entry["error"] = err
                log(entry)
                return done(False, err, step)

            async def escalate(reason: str, need_text: bool = False) -> dict | None:
                """Vía S2-director: comando ejecutable, aplicar §5.2.

                Devuelve resultado final si S2 pide stop o el comando
                falla; None si continuar (re-observe → S1). S2 mock/stub
                o comando inválido → abort honesto, nunca ciclar ni
                tapear.
                """
                nonlocal s2_calls
                s2_calls += 1  # cuenta el intento (real o stub): audita S2
                try:
                    cmd, s2_usage = await s2_direct(
                        reason, rows, current_app, need_text=need_text,
                        usage_step=step)
                except s2_client.S2EmptyResponse as e:
                    err = {"code": "S2_UNAVAILABLE",
                           "error": f"S2_EMPTY_RESPONSE: {e}"[:220]}
                    entry["error"] = err
                    log(entry)
                    r = done(False, err, step)
                    r["hint"] = ("reintentar: null-content transitorio "
                                 "de S2")
                    return r
                except s2_client.S2BadCommand as e:
                    err = {"code": "S2_BAD_COMMAND",
                           "error": str(e)[:220]}
                    entry["error"] = err
                    log(entry)
                    return done(False, err, step)
                except Exception as e:
                    err = {"code": "S2_UNAVAILABLE",
                           "error": f"S2 falló ({type(e).__name__}): {e}"[:220]}
                    entry["error"] = err
                    log(entry)
                    r = done(False, err, step)
                    r["hint"] = "falta OPENROUTER_API_KEY o S2 caído"
                    return r
                if _is_s2_mock(cmd, s2_usage):
                    err = {"code": "S2_UNAVAILABLE",
                           "error": "S2 respondió mock/stub; sin plan real"}
                    entry["error"] = err
                    log(entry)
                    r = done(False, err, step)
                    r["hint"] = "falta OPENROUTER_API_KEY o S2 caído"
                    return r
                si, so, spc = _s2_tokens(s2_usage)
                s2_cost = tracker.track(_glm_id(), si, so, step=step,
                                        tier="s2", provider_cost=spc)
                entry["escalated"] = True
                entry["s2_reason"] = reason
                entry["s2_command"] = _redacted_command(cmd)
                entry["cost_s2"] = s2_cost
                log(entry)
                history.append({"step": step,
                                "action": {"kind": "escalate",
                                           "reason": reason, "conf": conf},
                                "result": {"ok": True,
                                           "evidence": _redacted_command(cmd)},
                                "snapshot": snapshot})
                fin = await apply_s2(cmd, snapshot)
                if fin is not None:
                    return fin
                return None

            if _guards.gate_tau(conf, TAU) is not None and action != "DONE":
                fin = await escalate(f"LOW_CONF conf={conf} < tau={TAU}")
                if fin is not None:
                    return fin
                continue
            if action == "ESCALATE":
                fin = await escalate("S1 pidió escalado",
                                     need_text=bool(decision.get("needs_system_2")))
                if fin is not None:
                    return fin
                continue
            if action == "DONE":
                # Gate DONE→S2: nunca aceptar directo. Re-lee pantalla
                # fresca + pide a S2 (real, misma key) `goal-achieved?`
                # contra snapshot final + historial. Solo achieved=true
                # → ok. Rechazo → sigue el loop (máx steps), no éxito
                # falso. Verificación + coste en forense. Genérico.
                try:
                    final_state = await observe_fn()
                except ObserveError as e:
                    log({"step": step, "goal": goal,
                         "error": f"verify observe: {e}"})
                    r = done(False, {"code": e.code, "error": e.error},
                             step)
                    r["hint"] = "revisa conexión con Jam"
                    return r
                final_rows, _ = _h.build_table(
                    final_state.get("candidates", []))
                final_snap = final_state.get("snapshot_id", snapshot)
                n_eff = sum(
                    1 for h in history
                    if h.get("action", {}).get("kind") in
                    ("tap_node", "type_text", "scroll", "back")
                    and h.get("result", {}).get("ok"))
                verify_fn = _verify_done or s2_client.verify_done
                s2_calls += 1
                try:
                    v_out, v_usage = await verify_fn(
                        goal,
                        table_lines=_table_lines(final_rows),
                        history_summary=_history_summary(history),
                        n_actions=n_eff,
                        final_snapshot=final_snap)
                except s2_client.S2EmptyResponse as e:
                    err = {"code": "S2_UNAVAILABLE",
                           "error": f"S2_EMPTY_RESPONSE: {e}"[:220]}
                    entry["error"] = err
                    log(entry)
                    r = done(False, err, step)
                    r["hint"] = ("reintentar: null-content transitorio "
                                 "de S2")
                    return r
                except Exception as e:
                    err = {"code": "S2_UNAVAILABLE",
                           "error": f"S2 falló ({type(e).__name__}): {e}"[:220]}
                    entry["error"] = err
                    log(entry)
                    r = done(False, err, step)
                    r["hint"] = "falta OPENROUTER_API_KEY o S2 caído"
                    return r
                if _is_s2_mock(v_out, v_usage):
                    err = {"code": "S2_UNAVAILABLE",
                           "error": "S2 respondió mock/stub; sin veredicto"}
                    entry["error"] = err
                    log(entry)
                    r = done(False, err, step)
                    r["hint"] = "falta OPENROUTER_API_KEY o S2 caído"
                    return r
                si, so, spc = _s2_tokens(v_usage)
                v_cost = tracker.track(_glm_id(), si, so, step=step,
                                       tier="s2", provider_cost=spc)
                achieved = bool((v_out or {}).get("achieved", False))
                v_ev = str((v_out or {}).get("evidence", "") or "")[:500]
                entry["done_verify"] = {
                    "achieved": achieved, "evidence": v_ev,
                    "n_actions": n_eff, "final_snapshot": final_snap}
                entry["cost_s2_verify"] = v_cost
                log(entry)
                history.append({
                    "step": step,
                    "action": {"kind": "done_verify",
                               "achieved": achieved,
                               "n_actions": n_eff},
                    "result": {"ok": achieved,
                               "evidence": {"s2": v_ev}},
                    "snapshot": final_snap})
                if achieved:
                    evidence = {
                        "goal": goal, "snapshot": final_snap,
                        "n_cands": len(final_rows),
                        "n_actions": n_eff,
                        "s2_evidence": v_ev,
                        "verified_by": "s2"}
                    log({"step": step, "final": {"ok": True},
                         "cost_total": tracker.total_cost_usd})
                    return done(True, evidence, step)
                s2_guidance = (v_ev or
                               "S2: goal not reached; re-observe and advance")
                log({"step": step, "done_rejected": True,
                     "n_actions": n_eff, "final_snapshot": final_snap,
                     "s2_evidence": v_ev,
                     "cost_total": tracker.total_cost_usd})
                continue

            target = decision.get("target", "NONE")
            row = by_idx.get(target) if isinstance(target, int) else None
            needs_node = action in ("TAP", "TYPE") or (
                action in ("SCROLL_DOWN", "SCROLL_UP") and target != "NONE")
            if isinstance(target, int) and target not in by_idx:
                err = {"code": "JEV_HALLUCINATION",
                       "error": f"target {target} fuera de la tabla vigente"}
                entry["error"] = err
                log(entry)
                return done(False, err, step)
            if needs_node and row is None:
                fin = await escalate(f"NO_TARGET para {action}")
                if fin is not None:
                    return fin
                continue
            if row is not None:
                bad_row = _h.validate_target(row, screen_h)
                if bad_row:
                    entry["error"] = bad_row
                    log(entry)
                    return done(False, bad_row, step)
                if _guards.is_forbidden(
                        {"text": row["label"], "desc": ""}, pattern=forbidden):
                    err = {"code": "FORBIDDEN_TARGET",
                           "error": f"target prohibido por goal: {row['label']}"}
                    entry["error"] = err
                    log(entry)
                    return done(False, err, step)

            internal = _to_internal(action, row, snapshot, decision)
            stuck = _guards.check_stuck_same(internal, history, n=STUCK_N)
            if stuck is not None:
                entry["error"] = stuck
                log(entry)
                return done(False, {"code": stuck["code"],
                                    "error": stuck["reason"]}, step)

            # TYPE: texto solo vía text_payload S2 (S1 nunca redacta);
            # foco explícito exigible. En forense solo hash, nunca crudo.
            text = ""
            if action == "TYPE":
                text = text_payload or decision.get("type_text", "") or ""
                if not text:
                    s2_calls += 1  # intento S2 open-text (audita S2 real)
                    try:
                        cmd, s2_usage = await s2_direct(
                            "open-text", rows, current_app,
                            need_text=True, usage_step=step)
                    except s2_client.S2EmptyResponse as e:
                        err = {"code": "S2_UNAVAILABLE",
                               "error": f"S2_EMPTY_RESPONSE: {e}"[:220]}
                        entry["error"] = err
                        log(entry)
                        r = done(False, err, step)
                        r["hint"] = ("reintentar: null-content transitorio "
                                     "de S2")
                        return r
                    except s2_client.S2BadCommand as e:
                        err = {"code": "S2_BAD_COMMAND",
                               "error": str(e)[:220]}
                        entry["error"] = err
                        log(entry)
                        return done(False, err, step)
                    except Exception as e:
                        err = {"code": "S2_UNAVAILABLE",
                               "error": f"S2 falló ({type(e).__name__}): {e}"[:220]}
                        entry["error"] = err
                        log(entry)
                        r = done(False, err, step)
                        r["hint"] = "falta OPENROUTER_API_KEY o S2 caído"
                        return r
                    if _is_s2_mock(cmd, s2_usage):
                        err = {"code": "S2_UNAVAILABLE",
                               "error": "S2 respondió mock/stub; sin texto real"}
                        entry["error"] = err
                        log(entry)
                        r = done(False, err, step)
                        r["hint"] = "falta OPENROUTER_API_KEY o S2 caído"
                        return r
                    si, so, spc = _s2_tokens(s2_usage)
                    t_cost = tracker.track(_glm_id(), si, so, step=step,
                                           tier="s2", provider_cost=spc)
                    entry["s2_command"] = _redacted_command(cmd)
                    entry["cost_s2"] = t_cost
                    if cmd.get("command") != "TYPE" or not cmd.get("text"):
                        fin = await escalate("S2 sin texto para TYPE")
                        if fin is not None:
                            return fin
                        continue
                    text_payload = cmd.get("text", "")
                    text_payload_hash = _payload_hash(text_payload)
                    note_guidance(cmd)
                    text = text_payload
                    entry["s2_text_len"] = len(text)
                    entry["text_payload_hash"] = text_payload_hash
                else:
                    entry["text_payload_hash"] = _payload_hash(text)
                    entry["s2_text_len"] = len(text)
                internal["text"] = text
                if not row.get("focused", False):
                    focus_act = {"kind": "tap_node", "node_id": row["id"],
                                 "snapshot_id": snapshot,
                                 "key": f"tap:{row['id']}"}
                    res = await execute_fn(focus_act)
                    entry["focus_tap"] = {"action": focus_act,
                                         "ok": res.get("ok")}
                    log(entry)
                    history.append({"step": step, "action": focus_act,
                                    "result": res, "snapshot": snapshot})
                    if not res.get("ok"):
                        ev = res.get("evidence", {}) or {}
                        return done(False, {"code": ev.get("code", "?"),
                                            "error": ev.get("error", "?")}, step)
                    continue  # re-observar; el TYPE va en el próximo paso

            label = row["label"] if row else ""
            if _h.is_sensitive(goal, label + " " + text) and not confirm:
                preview = {"action": action,
                           "target_id": row["id"] if row else None,
                           "label": label,
                           "text_len": len(text) if text else 0,
                           "text_sha256": _payload_hash(text) if text else "",
                           "snapshot": snapshot}
                entry["planned"] = True
                entry["preview"] = preview
                log(entry)
                r = done(True, {"planned": True, "preview": preview,
                                "needs_confirm": True}, step)
                r["verified"] = False
                r["needs_confirm"] = True
                r["hint"] = ("acción crítica: re-ejecuta con confirm=true "
                             "tras revisar el preview")
                return r

            res = await execute_fn(internal)
            entry["result"] = {"ok": res.get("ok"),
                               "evidence": res.get("evidence")}
            log(entry)
            history.append({"step": step, "action": internal, "result": res,
                            "snapshot": snapshot})
            if not res.get("ok"):
                code = (res.get("evidence", {}) or {}).get("code", "?")
                if code == "STALE_SNAPSHOT":
                    stale_streak += 1
                    if stale_streak >= MAX_STALE_STREAK:
                        return done(False, {"code": "UI_UNSTABLE",
                                            "error": "3 STALE seguidos"}, step)
                    continue
                err = (res.get("evidence", {}) or {}).get("error", "?")
                return done(False, {"code": code, "error": err}, step)
            stale_streak = 0
        code = "TIMEOUT" if (time.time() - t0) >= timeout_s else "STUCK"
        return done(False, {"code": code,
                            "error": f"{step} pasos sin done"}, step)
    finally:
        if logf is not None:
            logf.close()


def _is_s2_mock(s2_out: dict | None, s2_usage: dict | None) -> bool:
    """True si S2 respondió stub (sin key o caída): nunca seguir ciclando."""
    for d in (s2_out, s2_usage):
        if isinstance(d, dict) and d.get("mock") is True:
            return True
    return False


def _s2_tokens(usage: dict) -> tuple[int, int, float | None]:
    if not isinstance(usage, dict):
        return 0, 0, None
    try:
        return (int(usage.get("in_tokens", 0) or 0),
                int(usage.get("out_tokens", 0) or 0), None)
    except (TypeError, ValueError):
        return 0, 0, None


def _to_internal(action: str, row: dict | None, snapshot: int,
                 decision: dict) -> dict:
    if action == "TAP":
        return {"kind": "tap_node", "node_id": row["id"],
                "snapshot_id": snapshot, "key": f"tap:{row['id']}"}
    if action == "TYPE":
        return {"kind": "type_text", "node_id": row["id"],
                "snapshot_id": snapshot, "text": decision.get("type_text", ""),
                "key": f"type:{row['id']}"}
    if action in ("SCROLL_DOWN", "SCROLL_UP"):
        direction = "down" if action == "SCROLL_DOWN" else "up"
        d = {"kind": "scroll", "direction": direction,
             "key": f"scroll:{direction}"}
        if row is not None:
            d["node_id"] = row["id"]
            d["key"] = f"scroll:{direction}:{row['id']}"
        return d
    if action == "BACK":
        return {"kind": "back", "key": "back"}
    raise jev_client.JevHallucination(f"acción fuera del enum: {action}")
