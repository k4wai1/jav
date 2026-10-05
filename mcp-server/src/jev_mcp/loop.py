"""Agente simple y general: run_goal(goal: str) (plan-ahead v4 §6).

Ciclo bootstrap-compilador → observe→decide→mutate→verify(coalescido),
un paso = una primitiva. Sin paquetes, contactos ni fases prefijadas;
sin literales de dominio.

- Bootstrap compilador (v4 §2): observe (foreground + `dump_ui` fresco)
  → S2-compilador UNA vez (s2_client.compile_goal → `EXECUTE_GOAL` con
  package/screen_goal_en/preloaded_inputs/expected_terminal_state/
  guidance_for_s1/stop) ANTES del primer pass S1. Con `package` no vacío
  y app distinta del foreground → `mcp.open_app(package)` + ~600 ms +
  dump fresco antes del primer S1. Sin dump fresco no hay S1. S2 stub en
  bootstrap → S2_UNAVAILABLE inmediato (nunca ciclar ni adivinar).
  `preloaded_inputs` se guarda en memoria (`pending_payloads`); los TYPE
  del camino feliz los inyectan SIN reconsultar a S2 (§2.3). Comandos
  v3 (OPEN_APP/TYPE/BACK/HINT) siguen como vía de anomalía post-paso 0.
- S1 Jev (jev_client.ask_decision, single-pass, 100% en inglés) decide
  [TAP,TYPE,SCROLL_DOWN,SCROLL_UP,BACK,DONE,ESCALATE] + target 0..253|NONE
  + needs_system_2 + conf sobre la tabla
  [idx, class_short, zone, flags, label] + current_app + screen_goal_en.
- Fast-path S1 (v4 §3, FAST_TAU = 0.85, TAU = 0.70 intacto): TAP/SCROLL/
  BACK/TYPE trivial no-sensible con conf ≥ 0.85 despacha sin consultas
  secundarias y sin post-read redundante (el dump de verificación se
  reutiliza como observe siguiente). NUNCA salta compuertas (estructural,
  foco, confirm críticas, FORBIDDEN, STALE, STUCK, DONE-gate S2). DONE y
  ESCALATE nunca son fast-path.
- TYPE usa el payload del slot (§2.3) vía ACTION_SET_TEXT; en forense
  solo `slot/len/sha256`, nunca el texto crudo. Foco explícito exigible;
  read-back `confirm_input`; `consumed:true` al verificar.
- Cada llamada LLM pasa por CostTracker (log [COST] + `cost` en forense
  + acumulado jev_cost/s2_cost/total_cost en el resultado; el paso 0
  también pasa por CostTracker con step 0, tier s2).
- Compuertas §7: estructurales siempre (JSON válido, target en tabla
  vigente, visible, coords en pantalla, snapshot fresco, plan/comando S2
  válido); críticas/irreversibles exigen preview + confirm:true (sin él
  se planean sin ejecutar: needs_confirm). FORBIDDEN solo opt-in
  (forbidden?). DONE siempre con gate S2 (`verify_done` con
  `expected_terminal_state` + snapshot final + historial).
- type exige foco explícito: sin focused → tap previo explícito (nada
  implícito). Acciones no devuelven snapshot; el cliente verifica.
- snapshot mismatch ×3 → UI_UNSTABLE; misma (kind,node_id) ×3 → STUCK_SAME;
  misma decisión (action+target) ×3 sin cambio útil de snapshot → STUCK_SAME;
  S2 mock/stub → S2_UNAVAILABLE inmediato (nunca ciclar en giro).
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
from .core.cost import glm_model_id as _glm_id  # compat (tests/tools)
from .core.cost import s2_model_id as _s2_id
from .core.cost import jev_model_id as _jev_id
from .tools import app as app_tools
from .tools import ui as ui_tools

TAU = 0.70
# Fast-path S1 (plan-ahead v4 §3.1): conf ≥ 0.85 + trivial + no-sensible.
# TAU intacto; DONE/ESCALATE nunca son fast-path.
FAST_TAU = 0.85
MAX_STALE_STREAK = 3
STUCK_N = 2  # 2 previas iguales + actual = ×3 → STUCK_SAME
BOOTSTRAP_DELAY_S = 0.6  # estabilización tras open_app antes del re-dump

# Hint conservador temporal ante S2_EMPTY_RESPONSE (P0-4, 100% EN):
# UNA re-pregunta S1; sin TYPE sin payload ni DONE sin veredicto.
DEGRADED_S1_HINT = (
    "System-2 unavailable (empty response). Proceed conservatively: "
    "only TAP a visible field, BACK, or ESCALATE; "
    "never TYPE without text_payload, never DONE.")

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
    """Tabla serializada para S2: `idx class_short zone flags label` (v4 §4)."""
    return [f"{r['idx']} {r.get('class_short', 'View')} "
            f"{r.get('zone', 'unknown')} {r.get('flags', '—')} "
            f"{r['label']}" for r in rows]


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


def _slot_summaries(pending: dict) -> dict:
    """Resumen forense de slots: {slot: {len, sha256, consumed}} (v4 §2).

    Nunca texto crudo: solo longitud + hash + estado de consumo.
    """
    return {slot: {"len": v.get("len", 0),
                   "sha256": v.get("sha256", ""),
                   "consumed": bool(v.get("consumed", False))}
            for slot, v in (pending or {}).items()}


def _redacted_plan(plan: dict, pending: dict | None = None,
                   goal: str = "") -> dict:
    """Plan EXECUTE_GOAL apto para forense (v4 §2 + §7).

    Sin payloads crudos (solo slots con len/sha256). `screen_goal_en` /
    `expected_terminal_state` viajan en claro salvo contenido sensible
    (entonces solo len + hash).
    """
    red = {"command": plan.get("command"),
           "package": plan.get("package", ""),
           "guidance_for_s1": plan.get("guidance_for_s1", ""),
           "stop": bool(plan.get("stop", False))}
    for key in ("screen_goal_en", "expected_terminal_state"):
        val = plan.get(key, "") or ""
        if val and _h.is_sensitive(goal, str(val)):
            red[key + "_len"] = len(str(val))
            red[key + "_sha256"] = _payload_hash(str(val))
        else:
            red[key] = val
    red["slots"] = _slot_summaries(
        pending if pending is not None
        else {s: {"text": t} for s, t in
              (plan.get("preloaded_inputs", {}) or {}).items()})
    # Normaliza entradas construidas ad-hoc al mismo esquema len/sha256.
    for slot, summ in red["slots"].items():
        if "len" not in summ:
            text = summ.pop("text", "")
            summ["len"] = len(text)
            summ["sha256"] = _payload_hash(text)
            summ["consumed"] = False
    return red


def _select_pending_slot(pending: dict) -> str | None:
    """Slot a inyectar en TYPE (v4 §2.3.2, determinista, sin literales).

    Un solo slot pendiente → ese; varios → el primero no consumido en
    orden de inserción del plan; cero pendientes → None (anomalía:
    el loop escala a S2 en vez de reintentar a ciegas).
    """
    if not pending:
        return None
    for slot, meta in pending.items():
        if not meta.get("consumed", False):
            return slot
    return None


def _resolve_s2_type_row(target, rows: list | None,
                         by_idx: dict | None) -> dict | None:
    """Resuelve el campo destino de un TYPE S2 (genérico, sin literales).

    - target int → fila de `by_idx` (None si ausente/rotada).
    - target NONE → la única editable enfocada + visible (None si 0 o >1).
    Exige foco explícito: sin focused no hay despacho directo (el TYPE S1
    hará el tap previo). El llamante valida visible/coords/editable.
    """
    if rows is None:
        return None
    if isinstance(target, int):
        if not isinstance(by_idx, dict):
            return None
        return by_idx.get(target)
    focused = [r for r in rows
               if r.get("editable") and r.get("focused")
               and r.get("visible", True)]
    if len(focused) == 1:
        return focused[0]
    return None


async def run_goal(goal: str, *, max_steps: int = 20,
                   timeout_s: float = 60,
                   log_path: str | None = None,
                   confirm: bool = False,
                   forbidden: str | None = None,
                   _observe=None, _decide=None, _advise=None,
                   _execute_fn=None, _verify=None,
                   _verify_done=None, _open_app=None,
                   _compile=None,
                   _bootstrap_delay_s: float = BOOTSTRAP_DELAY_S) -> dict:
    """Ejecuta un objetivo en lenguaje natural sobre Android.

    goal: texto libre del operador. Sin paquetes ni contactos.
    confirm: true habilita acciones críticas/irreversibles (con preview
    auditada); sin él se planean sin ejecutar (needs_confirm).
    forbidden: pattern regex opt-in; sin él no hay filtro.
    Devuelve {ok, verified, evidence, hint}-compatible + costes y forense
    en log_path (JSONL por paso: conf, tau/fast_tau, fast_path, coalesced,
    slot+hash, cost, snapshots).
    """
    observe_fn = _observe or _default_observe
    decide_fn = _decide or jev_client.ask_decision
    advise_fn = _advise or s2_client.advise
    execute_fn = _execute_fn or _execute
    open_app_fn = _open_app or app_tools.open_app
    # Compilador paso 0 (v4 §2): seam propio; si el llamante solo inyectó
    # _advise (tests legacy de anomalía), el bootstrap usa _advise con
    # parse dual (plan o comando legacy). En producción usa compile_goal.
    compile_fn = _compile or (
        None if _advise is not None else s2_client.compile_goal)
    run_id = str(int(time.time()))
    tracker = CostTracker(run_id=run_id)
    t0 = time.time()
    history: list = []
    stale_streak = 0
    jev_calls = 0
    s2_calls = 0
    step = 0
    s2_guidance = ""
    screen_goal = goal  # verbatim hasta que el plan aporte screen_goal_en
    operator_verbatim = True  # False cuando el plan S2 aporta screen_goal_en
    expected_terminal_state = ""  # referencia del gate DONE→S2 (v4 §2.1)
    text_payload = ""  # texto exacto S2 (vía anomalía) → ACTION_SET_TEXT
    text_payload_hash = ""
    # Slots pre-cargados del plan (v4 §2.2): orden de inserción S2 +
    # {text, len, sha256, consumed}. Sin reconsulta en el camino feliz.
    pending_payloads: dict[str, dict] = {}
    pending_state: dict | None = None
    prev_dec_sig: tuple | None = None
    prev_snapshot: int | None = None
    same_dec_streak = 0
    # P0-4: racha de S2 vacíos (máx 1 degradación por snapshot; reset al
    # avanzar snapshot o ante S2 válido) + hint conservador de un solo uso.
    s2_empty_streak = 0
    s2_empty_snap: int | None = None
    degraded_hint_once = False
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

    def bump_s2_empty(snapshot: int) -> int:
        """Racha de S2 vacíos acotada por snapshot (P0-4).

        Mismo snapshot → streak+1; snapshot nuevo → streak=1 (reset al
        avanzar). El llamante aborta si ≥2, o degrada UNA vez.
        """
        nonlocal s2_empty_streak, s2_empty_snap
        if snapshot == s2_empty_snap:
            s2_empty_streak += 1
        else:
            s2_empty_streak = 1
            s2_empty_snap = snapshot
        return s2_empty_streak

    def reset_s2_empty() -> None:
        """S2 válido: cierra el incidente (sin cargo extra en CostTracker)."""
        nonlocal s2_empty_streak, s2_empty_snap
        s2_empty_streak = 0
        s2_empty_snap = None

    def arm_degraded_hint() -> None:
        """Arma la re-pregunta S1 conservadora de un solo uso (P0-4)."""
        nonlocal degraded_hint_once
        degraded_hint_once = True

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
        nonlocal s2_guidance, screen_goal, operator_verbatim
        g = cmd.get("guidance_for_s1", "") or ""
        if g:
            s2_guidance = g
            if cmd.get("command") == "HINT":
                screen_goal = g
                operator_verbatim = False

    async def s2_compile(rows: list, current_app: str):
        """Consulta al S2-compilador paso 0 y valida el plan (v4 §2.1).

        Vía `compile_fn` (producción: s2_client.compile_goal) o, en
        compat legacy (tests que solo inyectan _advise), vía `advise_fn`
        con parse dual: EXECUTE_GOAL si encaja, si no comando de anomalía
        v3. Devuelve (kind, obj, usage) con kind ∈ {"plan", "anomaly"}.
        Mock/excepción los traduce el llamante; comando inválido →
        S2BadCommand. Nunca actúa.
        """
        if compile_fn is not None:
            out, usage = await compile_fn(
                goal, table_lines=_table_lines(rows),
                history_summary=_history_summary(history),
                current_app=current_app)
            return "plan", s2_client.parse_execute_goal(out), usage
        out, usage = await advise_fn(
            goal, reason="bootstrap", table_lines=_table_lines(rows),
            history_summary=_history_summary(history),
            need_text=False, current_app=current_app,
            screen_goal=screen_goal)
        try:
            return "plan", s2_client.parse_execute_goal(out), usage
        except s2_client.S2BadCommand:
            if isinstance(out, dict) and out.get("command") in (
                    s2_client.VALID_COMMANDS):
                return "anomaly", s2_client.parse_command(out), usage
            raise

    async def apply_plan(plan: dict, current_snapshot: int,
                         current_app: str):
        """Aplica el plan EXECUTE_GOAL del paso 0 (v4 §2.2, compilador).

        Guarda screen_goal_en + expected_terminal_state + guidance +
        preloaded_inputs (pending_payloads); con `package` no vacío y app
        distinta del foreground → open_app + ~600 ms + re-observe fresco
        en `pending_state`. Sin dump fresco no hay S1. `stop:true` solo
        cierra tras `verify_final` determinista. Devuelve resultado final
        si cierra/falla; None si el loop debe continuar.
        """
        nonlocal screen_goal, operator_verbatim, expected_terminal_state
        nonlocal s2_guidance, pending_payloads, pending_state
        s2_guidance = plan.get("guidance_for_s1", "") or s2_guidance
        if plan.get("screen_goal_en"):
            screen_goal = plan["screen_goal_en"]
            operator_verbatim = False
        expected_terminal_state = plan.get("expected_terminal_state", "") or ""
        pending_payloads = {}
        for slot, payload in (plan.get("preloaded_inputs", {}) or {}).items():
            pending_payloads[str(slot)] = {
                "text": str(payload), "len": len(str(payload)),
                "sha256": _payload_hash(str(payload)), "consumed": False}
        if plan.get("stop"):
            ok, evidence = await (_verify(goal, observe_fn)
                                  if _verify
                                  else _default_verify(goal, observe_fn))
            return done(ok, evidence, max(step, 0))
        package = plan.get("package", "") or ""
        if package and package != current_app:
            res = await open_app_fn(package)
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

    async def apply_s2(cmd: dict, current_snapshot: int,
                     rows: list | None = None,
                     by_idx: dict | None = None,
                     screen_h: int = 0,
                     pre_state: dict | None = None):
        """Aplica un comando S2 validado (§5.1 + §5.2, v3 ejecutable).

        OPEN_APP/BACK mutan vía sus tools y dejan `pending_state` fresco.
        TYPE con texto S2: siempre guarda `text_payload` + guidance; si el
        target está resuelto y el campo está enfocado + visible + editable,
        lo EJECUTA directo vía `type_text` (igual que OPEN_APP), con
        read-back y forense (solo hash/longitud, nunca crudo). Si no hay
        campo enfocado/visible o no es verificable, solo guarda payload y
        deja que el próximo TYPE S1 lo ejecute (foco explícito exigible).
        HINT no muta. Devuelve resultado final si cierra/falla; None si
        el loop debe continuar (re-observe → S1).
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
            row = _resolve_s2_type_row(cmd.get("target", "NONE"),
                                       rows, by_idx)
            if row is None:
                return None
            bad_row = _h.validate_target(row, screen_h)
            if bad_row:
                return None
            if (not row.get("editable") or not row.get("focused")
                    or not row.get("visible", True)):
                return None
            verification = _h.prepare_input_verification(row, text_payload)
            if verification is None:
                return None
            label = row.get("label", "") or ""
            if _h.is_sensitive(goal, label + " " + text_payload) and not confirm:
                preview = {"action": "TYPE",
                           "target_id": row.get("id"),
                           "label": label,
                           "text_len": len(text_payload),
                           "text_sha256": text_payload_hash,
                           "snapshot": current_snapshot,
                           "s2_direct": True}
                log({"step": step, "phase": "s2_direct_type",
                     "snapshot": current_snapshot,
                     "s2_command": _redacted_command(cmd),
                     "planned": True, "preview": preview})
                r = done(True, {"planned": True, "preview": preview,
                                "needs_confirm": True}, max(step, 0))
                r["verified"] = False
                r["needs_confirm"] = True
                r["hint"] = ("acción crítica: re-ejecuta con confirm=true "
                             "tras revisar el preview")
                return r
            internal = {"kind": "type_text", "node_id": row["id"],
                        "snapshot_id": current_snapshot,
                        "text": text_payload,
                        "key": f"type:{row['id']}"}
            before_fp = _h.screen_fingerprint(
                (pre_state or {}).get("candidates", [])) if pre_state else ""
            res = await execute_fn(internal)
            if not res.get("ok"):
                ev = res.get("evidence", {}) or {}
                if ev.get("code") == "STALE_SNAPSHOT":
                    # Deuda AGENTS.md 2026-10-02: reintento en el bucle,
                    # no en la app. Re-observa UNA vez, re-resuelve por id
                    # y reintenta la misma acción UNA vez; segundo STALE →
                    # UI_UNSTABLE. Genérico, sin literales de dominio.
                    log({"step": step, "phase": "s2_direct_type",
                         "snapshot": current_snapshot,
                         "s2_command": _redacted_command(cmd),
                         "text_payload_hash": text_payload_hash,
                         "s2_text_len": len(text_payload),
                         "result": {"ok": False, "evidence": ev},
                         "stale_retry": True, "attempt": 1})
                    history.append({"step": step,
                                    "action": {"kind": "type_text",
                                               "node_id": row["id"],
                                               "s2_direct": True},
                                    "result": res,
                                    "snapshot": current_snapshot})
                    try:
                        fresh = await observe_fn()
                    except ObserveError as e2:
                        log({"step": step, "phase": "s2_direct_type",
                             "snapshot": current_snapshot,
                             "stale_retry": True, "attempt": 1,
                             "reobserve": {"ok": False, "code": e2.code}})
                        history.append({"step": step,
                                        "action": {"kind": "type_text",
                                                   "node_id": row["id"],
                                                   "s2_direct": True,
                                                   "stale_retry": True},
                                        "result": {"ok": False,
                                                   "evidence": {
                                                       "code": e2.code}},
                                        "snapshot": current_snapshot})
                        return done(False, {
                            "code": "UI_UNSTABLE",
                            "error": ("STALE + re-observe fallido "
                                      f"({e2.code}); UI mutando")}, max(step, 1))
                    frows, _ = _h.build_table(
                        fresh.get("candidates", []),
                        fresh.get("screen_width", 0) or 0,
                        fresh.get("screen_height", 0) or 0)
                    fsnap = fresh.get("snapshot_id", current_snapshot)
                    fsh = fresh.get("screen_height", 0) or screen_h
                    nid = row.get("id", "")
                    nrow = next((r for r in frows if r.get("id") == nid),
                                None)
                    if nrow is None or _h.validate_target(nrow, fsh):
                        log({"step": step, "phase": "s2_direct_type",
                             "snapshot": fsnap, "stale_retry": True,
                             "target_vanished": nrow is None,
                             "node_id": nid})
                        pending_state = fresh
                        return None
                    if (not nrow.get("editable")
                            or not nrow.get("focused")
                            or not nrow.get("visible", True)):
                        pending_state = fresh
                        return None
                    retry_internal = {"kind": "type_text",
                                      "node_id": nid,
                                      "snapshot_id": fsnap,
                                      "text": text_payload,
                                      "key": f"type:{nid}"}
                    res2 = await execute_fn(retry_internal)
                    if not res2.get("ok"):
                        ev2 = res2.get("evidence", {}) or {}
                        log({"step": step, "phase": "s2_direct_type",
                             "snapshot": fsnap,
                             "s2_command": _redacted_command(cmd),
                             "text_payload_hash": text_payload_hash,
                             "result": {"ok": False, "evidence": ev2},
                             "stale_retry": True, "attempt": 2})
                        history.append({"step": step,
                                        "action": {"kind": "type_text",
                                                   "node_id": nid,
                                                   "s2_direct": True,
                                                   "stale_retry": True},
                                        "result": res2, "snapshot": fsnap})
                        if ev2.get("code") == "STALE_SNAPSHOT":
                            return done(False, {
                                "code": "UI_UNSTABLE",
                                "error": ("STALE reintentado una vez; "
                                          "UI mutando")}, max(step, 1))
                        return done(False, {
                            "code": ev2.get("code", "?"),
                            "error": ev2.get("error", "?")}, max(step, 1))
                    log({"step": step, "phase": "s2_direct_type",
                         "snapshot": fsnap, "stale_retry": True,
                         "recovered": True})
                    res = res2
                    current_snapshot = fsnap
                    row = nrow
                    rebuilt = _h.prepare_input_verification(row,
                                                            text_payload)
                    if rebuilt is not None:
                        verification = rebuilt
                else:
                    log({"step": step, "phase": "s2_direct_type",
                         "snapshot": current_snapshot,
                         "s2_command": _redacted_command(cmd),
                         "text_payload_hash": text_payload_hash,
                         "s2_text_len": len(text_payload),
                         "result": {"ok": False, "evidence": ev}})
                    history.append({"step": step,
                                    "action": {"kind": "type_text",
                                               "node_id": row["id"],
                                               "s2_direct": True},
                                    "result": res,
                                    "snapshot": current_snapshot})
                    return done(False, {"code": ev.get("code", "?"),
                                        "error": ev.get("error", "?")},
                                max(step, 1))
            try:
                post_state = await observe_fn()
            except ObserveError as e:
                log({"step": step, "phase": "s2_direct_type",
                     "snapshot": current_snapshot,
                     "s2_command": _redacted_command(cmd),
                     "text_payload_hash": text_payload_hash,
                     "s2_text_len": len(text_payload),
                     "input_verified": False,
                     "input_unverified_reason": f"read-back observe: {e.code}",
                     "fingerprint_before": before_fp})
                history.append({"step": step,
                                "action": {"kind": "type_text",
                                           "node_id": row["id"],
                                           "s2_direct": True},
                                "result": res,
                                "snapshot": current_snapshot})
                r = done(False, {"code": e.code, "error": e.error},
                         max(step, 1))
                r["hint"] = "revisa conexión con Jam"
                return r
            after_fp = _h.screen_fingerprint(
                post_state.get("candidates", []))
            first = [post_state]

            async def _reobserve():
                if first:
                    return first.pop()
                return await observe_fn()

            ok_v, vinfo = await _h.confirm_input(
                verification, _reobserve,
                timeout_ms=_h.INPUT_TIMEOUT_MS, poll_ms=_h.POLL_MS)
            log({"step": step, "phase": "s2_direct_type",
                 "snapshot": current_snapshot,
                 "s2_command": _redacted_command(cmd),
                 "text_payload_hash": text_payload_hash,
                 "s2_text_len": len(text_payload),
                 "result": {"ok": True,
                            "evidence": res.get("evidence")},
                 "input_verified": ok_v,
                 "input_attempts": vinfo.get("attempts"),
                 "input_snapshot": vinfo.get("snapshot"),
                 "fingerprint_before": before_fp,
                 "fingerprint_after": after_fp})
            history.append({"step": step,
                            "action": {"kind": "type_text",
                                       "node_id": row["id"],
                                       "s2_direct": True},
                            "result": res, "snapshot": current_snapshot})
            if not ok_v:
                return done(False, {
                    "code": "input_unverified",
                    "error": ("Text was sent, but its complete value could not "
                              "be confirmed on screen within timeout. "
                              "Inspect before retrying.")}, max(step, 1))
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

    async def _verify_type(entry: dict, history: list, step: int,
                           pre_state: dict, row: dict | None, text: str,
                           res: dict, snapshot: int, observe_fn,
                           internal: dict,
                           slot: str | None = None) -> dict | None:
        """Read-back tras TYPE REPLACE (P0-2, patrón M2 + v4 §2.3/§3.2).

        None = verificado (el llamante hace `continue`). Dict = resultado
        final `input_unverified` SIN retype ciego. La acción ya se ejecutó:
        se registra en historial + forense aunque el read falle
        (log-antes-de-observar). En forense solo slot/hash/longitud +
        fingerprints, nunca texto crudo. Al verificar con slot del plan:
        `consumed:true`. El read-back válido y nuevo se deja en
        `pending_state` como observe siguiente (coalescido v4 §3.2).
        """
        nonlocal pending_state
        before_fp = _h.screen_fingerprint(
            (pre_state or {}).get("candidates", []))
        verification = _h.prepare_input_verification(row, text)
        entry["result"] = {"ok": True, "evidence": res.get("evidence")}
        entry["text_payload_hash"] = _payload_hash(text)
        entry["s2_text_len"] = len(text)
        entry["fingerprint_before"] = before_fp
        if verification is None:
            entry["input_verified"] = False
            entry["input_unverified_reason"] = (
                "target no verificable (no-editable/password/texto vacío)")
            history.append({"step": step, "action": internal,
                            "result": res, "snapshot": snapshot})
            log(entry)
            return done(False, {
                "code": "input_unverified",
                "error": ("Text was sent to a target that cannot be "
                          "read back. Inspect before retrying.")}, step)
        try:
            post_state = await observe_fn()
        except ObserveError as e:
            entry["input_verified"] = False
            entry["input_unverified_reason"] = f"read-back observe: {e.code}"
            history.append({"step": step, "action": internal,
                            "result": res, "snapshot": snapshot})
            log(entry)
            r = done(False, {"code": e.code, "error": e.error}, step)
            r["hint"] = "revisa conexión con Jam"
            return r
        entry["fingerprint_after"] = _h.screen_fingerprint(
            post_state.get("candidates", []))
        first = [post_state]

        async def _reobserve():
            if first:
                return first.pop()
            return await observe_fn()

        ok_v, vinfo = await _h.confirm_input(
            verification, _reobserve,
            timeout_ms=_h.INPUT_TIMEOUT_MS, poll_ms=_h.POLL_MS)
        entry["input_verified"] = ok_v
        entry["input_attempts"] = vinfo.get("attempts")
        entry["input_snapshot"] = vinfo.get("snapshot")
        if ok_v:
            if slot is not None and slot in pending_payloads:
                pending_payloads[slot]["consumed"] = True
                entry["slot_consumed"] = True
            after_snap = post_state.get("snapshot_id", snapshot)
            entry["snapshot_after"] = after_snap
            if after_snap != snapshot:
                pending_state = post_state
                entry["coalesced"] = True
        history.append({"step": step, "action": internal,
                        "result": res, "snapshot": snapshot})
        log(entry)
        if not ok_v:
            return done(False, {
                "code": "input_unverified",
                "error": ("Text was sent, but its complete value could not "
                          "be confirmed on screen within timeout. "
                          "Inspect before retrying.")}, step)
        return None

    async def _coalesce_verify(entry: dict, snapshot: int) -> dict | None:
        """Post-read coalescido tras mutación ok (v4 §3.2).

        Un solo dump: verifica este paso Y observa el siguiente (se deja
        en `pending_state` si el snapshot es nuevo). Ante STALE rige la
        racha existente (×3 → UI_UNSTABLE); ante fallo de lectura →
        `pending_state = None` y el paso siguiente re-observa normal.
        None = seguir; dict = abort UI_UNSTABLE.
        """
        nonlocal pending_state, stale_streak
        try:
            post = await observe_fn()
        except ObserveError as e:
            pending_state = None
            entry["coalesced"] = False
            if e.code == "STALE_SNAPSHOT":
                stale_streak += 1
                if stale_streak >= MAX_STALE_STREAK:
                    return {"code": "UI_UNSTABLE",
                            "error": "3 STALE seguidos"}
            return None
        after = post.get("snapshot_id", snapshot)
        entry["snapshot_after"] = after
        if after != snapshot:
            pending_state = post
            entry["coalesced"] = True
        else:
            pending_state = None
            entry["coalesced"] = False
        return None

    try:
        # --- Bootstrap compilador (v4 §2): observe → S2-compilador
        # EXECUTE_GOAL paso 0 → [open_app si package ∧ ¬foreground + ~600 ms
        # + re-observe] + preloaded en memoria. Antes del primer pass S1;
        # sin dump fresco no hay S1. Comandos v3 solo como anomalía. ---
        try:
            bstate = await observe_fn()
        except ObserveError as e:
            r = done(False, {"code": e.code, "error": e.error}, 0)
            r["hint"] = "revisa conexión con Jam"
            return r
        bscreen_w = bstate.get("screen_width", 0) or 0
        bscreen_h = bstate.get("screen_height", 0) or 0
        brows, bby_idx = _h.build_table(bstate.get("candidates", []),
                                         bscreen_w, bscreen_h)
        bsnap = bstate.get("snapshot_id", -1)
        bapp = bstate.get("package", "") or ""
        s2_calls += 1
        try:
            bkind, bcmd, busage = await s2_compile(brows, bapp)
        except s2_client.S2EmptyResponse as e:
            bkind, bcmd, busage = "empty", None, {}
            err = f"S2_EMPTY_RESPONSE: {e}"[:220]
            streak = bump_s2_empty(bsnap)
            if streak >= 2:
                log({"step": 0, "phase": "bootstrap", "error": err,
                     "s2_empty": True, "s2_empty_streak": streak})
                return s2_unavailable(
                    err, "reintentar: null-content transitorio de S2", 0)
            # P0-4: no abortar al primer vacío: UNA re-pregunta S1
            # conservadora con el dump fresco ya en mano (pending_state).
            arm_degraded_hint()
            log({"step": 0, "phase": "bootstrap", "error": err,
                 "s2_empty": True, "degraded": True,
                 "s2_empty_streak": streak})
            history.append({"step": 0,
                            "action": {"kind": "bootstrap",
                                       "command": "DEGRADED_S1"},
                            "result": {"ok": True,
                                       "evidence": {"s2_empty": True}},
                            "snapshot": bsnap})
            pending_state = bstate
            bcmd = None
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
            bcost = tracker.track(_s2_id(), bi, bo, step=0, tier="s2",
                                   provider_cost=bpc)
            log({"step": 0, "phase": "bootstrap", "cost_s2": bcost,
                 "error": {"code": "S2_UNAVAILABLE",
                           "error": "S2 respondió mock/stub; sin plan real"}})
            return s2_unavailable("S2 respondió mock/stub; sin plan real",
                                  "falta OPENROUTER_API_KEY o S2 caído", 0)
        if bcmd is None:
            pass  # P0-4: bootstrap degradado (pending_state ya fijado)
        elif bkind == "plan":
            reset_s2_empty()  # S2 válido: cierra el incidente
            bi, bo, bpc = _s2_tokens(busage)
            bcost = tracker.track(_s2_id(), bi, bo, step=0, tier="s2",
                                   provider_cost=bpc)
            fin = await apply_plan(bcmd, bsnap, bapp)
            # Forense del paso 0 con el plan ya aplicado (slots visibles).
            log({"step": 0, "phase": "bootstrap", "goal": goal,
                 "snapshot": bsnap, "current_app": bapp,
                 "s2_plan": _redacted_plan(bcmd, pending_payloads, goal),
                 "operator_verbatim": operator_verbatim,
                 "cost_s2": bcost})
            history.append({"step": 0,
                            "action": {"kind": "bootstrap",
                                       "command": bcmd.get("command")},
                            "result": {"ok": True,
                                       "evidence": _redacted_plan(
                                           bcmd, pending_payloads, goal)},
                            "snapshot": bsnap})
            if fin is not None:
                return fin
        else:
            reset_s2_empty()  # S2 válido: cierra el incidente
            bi, bo, bpc = _s2_tokens(busage)
            bcost = tracker.track(_s2_id(), bi, bo, step=0, tier="s2",
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
            fin = await apply_s2(bcmd, bsnap, brows, bby_idx,
                                 bscreen_h, bstate)
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
            screen_w = state.get("screen_width", 0) or 0
            screen_h = state.get("screen_height", 0) or 0
            rows, by_idx = _h.build_table(state.get("candidates", []),
                                          screen_w, screen_h)
            snapshot = state.get("snapshot_id", -1)
            current_app = state.get("package", "") or ""
            # P0-1: campo enfocado + contenido al state S1 (del observe si
            # read_screen lo trae; si no, derivado de candidates).
            ff = state.get("focused_field")
            if not isinstance(ff, dict):
                ff = _h.focused_field_view(state.get("candidates", []))

            # --- S1 single-pass (100% en inglés, §3) ---
            eff_guidance = s2_guidance
            if degraded_hint_once:
                # P0-4: UNA re-pregunta conservadora (temporal, un solo uso).
                eff_guidance = (f"{s2_guidance} {DEGRADED_S1_HINT}".strip()
                                if s2_guidance else DEGRADED_S1_HINT)
                degraded_hint_once = False
            try:
                decision, usage = await decide_fn(
                    goal, rows, snapshot,
                    history_summary=_history_summary(history),
                    s2_guidance=eff_guidance,
                    current_app=current_app,
                    screen_goal=screen_goal,
                    focused_field=ff)
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
                     "fast_tau": FAST_TAU, "fast_path": False,
                     "coalesced": False,
                     "screen_goal": screen_goal,
                     "operator_verbatim": operator_verbatim,
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
                    streak = bump_s2_empty(snapshot)
                    entry["s2_empty"] = True
                    entry["s2_empty_streak"] = streak
                    if streak >= 2:
                        # Persiste → abort honesto (STUCK_SAME×3 y
                        # STALE×3 siguen contando en paralelo).
                        entry["error"] = err
                        log(entry)
                        r = done(False, err, step)
                        r["hint"] = ("reintentar: null-content transitorio "
                                     "de S2")
                        return r
                    # P0-4: UNA re-pregunta S1 conservadora (sin TYPE sin
                    # payload ni DONE sin veredicto); el loop re-observa.
                    arm_degraded_hint()
                    entry["degraded"] = True
                    log(entry)
                    return None
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
                s2_cost = tracker.track(_s2_id(), si, so, step=step,
                                        tier="s2", provider_cost=spc)
                reset_s2_empty()  # S2 válido: cierra el incidente
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
                fin = await apply_s2(cmd, snapshot, rows, by_idx,
                                     screen_h, state)
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
                    final_state.get("candidates", []),
                    final_state.get("screen_width", 0) or 0,
                    final_state.get("screen_height", 0) or 0)
                final_snap = final_state.get("snapshot_id", snapshot)
                n_eff = sum(
                    1 for h in history
                    if h.get("action", {}).get("kind") in
                    ("tap_node", "type_text", "scroll", "back")
                    and h.get("result", {}).get("ok"))
                verify_fn = _verify_done or s2_client.verify_done
                s2_calls += 1
                try:
                    try:
                        v_out, v_usage = await verify_fn(
                            goal,
                            table_lines=_table_lines(final_rows),
                            history_summary=_history_summary(history),
                            n_actions=n_eff,
                            final_snapshot=final_snap,
                            expected_terminal_state=expected_terminal_state)
                    except TypeError:
                        # Dobles legacy sin expected_terminal_state.
                        v_out, v_usage = await verify_fn(
                            goal,
                            table_lines=_table_lines(final_rows),
                            history_summary=_history_summary(history),
                            n_actions=n_eff,
                            final_snapshot=final_snap)
                except s2_client.S2EmptyResponse as e:
                    err = {"code": "S2_UNAVAILABLE",
                           "error": f"S2_EMPTY_RESPONSE: {e}"[:220]}
                    streak = bump_s2_empty(final_snap)
                    entry["s2_empty"] = True
                    entry["s2_empty_streak"] = streak
                    if streak >= 2:
                        entry["error"] = err
                        log(entry)
                        r = done(False, err, step)
                        r["hint"] = ("reintentar: null-content transitorio "
                                     "de S2")
                        return r
                    # P0-4: DONE-rechazado (sin veredicto S2 no hay éxito):
                    # UNA re-pregunta S1 conservadora, sigue el loop.
                    arm_degraded_hint()
                    entry["degraded"] = True
                    entry["done_rejected"] = True
                    entry["done_reject_reason"] = "S2_EMPTY_RESPONSE"
                    log(entry)
                    history.append({
                        "step": step,
                        "action": {"kind": "done_verify",
                                   "achieved": False,
                                   "n_actions": n_eff},
                        "result": {"ok": False,
                                   "evidence": {"s2_empty": True}},
                        "snapshot": final_snap})
                    continue
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
                v_cost = tracker.track(_s2_id(), si, so, step=step,
                                       tier="s2", provider_cost=spc)
                reset_s2_empty()  # veredicto S2 válido: cierra el incidente
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

            # TYPE: payload del plan o de S2-anomalía (S1 nunca redacta);
            # foco explícito exigible. En forense solo slot/len/hash.
            text = ""
            slot = None
            if action == "TYPE":
                # Camino feliz v4 §2.3: slot pre-cargado, SIN reconsulta.
                # El payload S2 manda; decision.type_text se ignora.
                slot = _select_pending_slot(pending_payloads)
                if slot is not None:
                    text = pending_payloads[slot]["text"]
                    entry["slot"] = slot
                    entry["from_plan"] = True
                    entry["s2_text_len"] = len(text)
                    entry["text_payload_hash"] = pending_payloads[slot][
                        "sha256"]
                if slot is None:
                    if s2_empty_streak >= 1 and not text_payload:
                        # P0-4 degradado: nunca TYPE sin text_payload ni
                        # open-text inventado → escalate normal (si S2
                        # sigue vacío, el streak aborta; si se recuperó,
                        # aporta texto o guidance).
                        fin = await escalate("DEGRADED_NO_TEXT para TYPE")
                        if fin is not None:
                            return fin
                        continue
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
                        streak = bump_s2_empty(snapshot)
                        entry["s2_empty"] = True
                        entry["s2_empty_streak"] = streak
                        if streak >= 2:
                            entry["error"] = err
                            log(entry)
                            r = done(False, err, step)
                            r["hint"] = ("reintentar: null-content "
                                         "transitorio de S2")
                            return r
                        # P0-4: UNA re-pregunta S1 conservadora (el TYPE
                        # sin payload va a planned/escalate, nunca se
                        # escribe inventado).
                        arm_degraded_hint()
                        entry["degraded"] = True
                        log(entry)
                        continue
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
                    t_cost = tracker.track(_s2_id(), si, so, step=step,
                                           tier="s2", provider_cost=spc)
                    reset_s2_empty()  # texto S2 válido: cierra el incidente
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

            # Fast-path v4 §3.1: solo ahorra S2 + dumps duplicados. Todas
            # las compuertas ya evaluaron (estructural, foco en TYPE,
            # confirm en críticas, FORBIDDEN, STUCK, DONE-gate). DONE y
            # ESCALATE nunca llegan aquí.
            if conf >= FAST_TAU:
                entry["fast_path"] = True
            res = await execute_fn(internal)
            if action == "TYPE" and res.get("ok"):
                # P0-2: read-back con timeout tras REPLACE (M2). Éxito →
                # sigue (slot consumido + coalescido dentro); fallo →
                # input_unverified SIN retype ciego.
                fin = await _verify_type(
                    entry, history, step, state, row, text, res,
                    snapshot, observe_fn, internal, slot=slot)
                if fin is not None:
                    return fin
                stale_streak = 0
                continue
            entry["result"] = {"ok": res.get("ok"),
                               "evidence": res.get("evidence")}
            if res.get("ok"):
                # Post-read coalescido v4 §3.2: el dump de verificación se
                # reutiliza como observe del paso siguiente (un dump menos,
                # nunca verificación menos).
                abort = await _coalesce_verify(entry, snapshot)
                log(entry)
                history.append({"step": step, "action": internal,
                                "result": res, "snapshot": snapshot})
                if abort is not None:
                    return done(False, abort, step)
                stale_streak = 0
                continue
            code = (res.get("evidence", {}) or {}).get("code", "?")
            if (code == "STALE_SNAPSHOT"
                    and internal.get("kind") in ("tap_node", "type_text")):
                # Deuda AGENTS.md 2026-10-02: reintento en el bucle, no en
                # la app. Re-observa UNA vez, re-resuelve el target por id
                # en la tabla nueva y reintenta la misma acción UNA vez;
                # segundo STALE → UI_UNSTABLE (cuenta en el streak
                # existente). Genérico, sin literales de dominio.
                stale_streak += 1
                entry["result"] = {"ok": False,
                                   "evidence": res.get("evidence")}
                entry["stale_retry"] = True
                entry["stale_attempt"] = 1
                log(entry)
                history.append({"step": step, "action": internal,
                                "result": res, "snapshot": snapshot})
                try:
                    fresh_state = await observe_fn()
                except ObserveError as e2:
                    if e2.code == "STALE_SNAPSHOT":
                        stale_streak += 1
                    rentry = {"step": step, "phase": "stale_retry",
                              "snapshot": snapshot,
                              "node_id": internal.get("node_id"),
                              "reobserve": {"ok": False, "code": e2.code},
                              "stale_streak": stale_streak}
                    log(rentry)
                    if e2.code == "STALE_SNAPSHOT":
                        return done(False, {
                            "code": "UI_UNSTABLE",
                            "error": ("STALE + re-observe fallido "
                                      f"({e2.code}); UI mutando")}, step)
                    r = done(False, {"code": e2.code, "error": e2.error},
                             step)
                    r["hint"] = "revisa conexión con Jam"
                    return r
                frows, _ = _h.build_table(
                    fresh_state.get("candidates", []),
                    fresh_state.get("screen_width", 0) or 0,
                    fresh_state.get("screen_height", 0) or 0)
                fsnap = fresh_state.get("snapshot_id", snapshot)
                fsh = fresh_state.get("screen_height", 0) or screen_h
                nid = internal.get("node_id", "")
                nrow = next((r for r in frows if r.get("id") == nid), None)
                if nrow is None or _h.validate_target(nrow, fsh):
                    log({"step": step, "phase": "stale_retry",
                         "snapshot": fsnap, "node_id": nid,
                         "target_vanished": nrow is None,
                         "stale_streak": stale_streak})
                    pending_state = fresh_state
                    if stale_streak >= MAX_STALE_STREAK:
                        return done(False, {"code": "UI_UNSTABLE",
                                            "error": "3 STALE seguidos"},
                                    step)
                    continue
                retry_internal = dict(internal)
                retry_internal["snapshot_id"] = fsnap
                res2 = await execute_fn(retry_internal)
                if res2.get("ok"):
                    stale_streak = 0
                    if action == "TYPE":
                        rentry = {"step": step, "goal": goal,
                                  "snapshot": fsnap,
                                  "n_cands": len(frows), "conf": conf,
                                  "tau": TAU, "fast_tau": FAST_TAU,
                                  "fast_path": False, "coalesced": False,
                                  "screen_goal": screen_goal,
                                  "operator_verbatim": operator_verbatim,
                                  "cost": entry.get("cost"),
                                  "decision": decision,
                                  "stale_retry": True, "stale_attempt": 2,
                                  "stale_recovered": True,
                                  "slot": slot,
                                  "text_payload_hash": _payload_hash(text),
                                  "s2_text_len": len(text)}
                        fin = await _verify_type(
                            rentry, history, step, fresh_state, nrow,
                            text, res2, fsnap, observe_fn,
                            retry_internal, slot=slot)
                        if fin is not None:
                            return fin
                        continue
                    rentry2 = dict(entry)
                    rentry2["snapshot"] = fsnap
                    rentry2["stale_attempt"] = 2
                    rentry2["stale_recovered"] = True
                    rentry2["result"] = {"ok": True,
                                         "evidence": res2.get("evidence")}
                    abort = await _coalesce_verify(rentry2, fsnap)
                    log(rentry2)
                    history.append({"step": step,
                                    "action": retry_internal,
                                    "result": res2, "snapshot": fsnap})
                    if abort is not None:
                        return done(False, abort, step)
                    continue
                code2 = (res2.get("evidence", {}) or {}).get("code", "?")
                stale_streak += 1
                log({"step": step, "phase": "stale_retry",
                     "snapshot": fsnap, "node_id": nid,
                     "result": {"ok": False,
                                "evidence": res2.get("evidence")},
                     "stale_attempt": 2, "stale_streak": stale_streak})
                history.append({"step": step, "action": retry_internal,
                                "result": res2, "snapshot": fsnap})
                return done(False, {
                    "code": "UI_UNSTABLE" if code2 == "STALE_SNAPSHOT"
                    else code2,
                    "error": ("STALE reintentado una vez; UI mutando"
                              if code2 == "STALE_SNAPSHOT"
                              else (res2.get("evidence", {}) or {}).get(
                                  "error", "?"))}, step)
            log(entry)
            history.append({"step": step, "action": internal, "result": res,
                            "snapshot": snapshot})
            code = (res.get("evidence", {}) or {}).get("code", "?")
            if code == "STALE_SNAPSHOT":
                stale_streak += 1
                if stale_streak >= MAX_STALE_STREAK:
                    return done(False, {"code": "UI_UNSTABLE",
                                        "error": "3 STALE seguidos"}, step)
                continue
            err = (res.get("evidence", {}) or {}).get("error", "?")
            return done(False, {"code": code, "error": err}, step)
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
