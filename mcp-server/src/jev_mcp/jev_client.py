"""Cliente S1 Jev (TypeSafe System One) vía OpenRouter.

Dos niveles:
- `ask(state, questions)`: batch genérico verificado (contrato abajo).
- `ask_decision(goal, table, snapshot_id, ...)`: single-pass por paso
  (contrato generic-dual-tier §2): 1 llamada resuelve action + target +
  needs_system_2 + conf. Implementado sobre `ask` con 3 preguntas
  cerradas (action ∈ 7, target ∈ 0..253|NONE, needs_system_2 noul);
  S1 nunca genera texto libre (el slot type_text solo se acepta si es
  extractivo del goal/UI; la redacción abierta la provee S2).

Contrato ask: ask(state, questions) -> ({nombre: respuesta}, usage).
Respuestas normalizadas: choice -> clave elegida; noul -> true/false;
score -> número. Solo claves de `criteria`, o JEV_HALLUCINATION.

Shape real verificado en ~/Mango-mcp/logs/local-jev-response-101.json:
{"answers": {"q": {"choice": "k", "confidence": 0.9,
"probabilities": {...}, "type": "choice"}}, "usage": {"cost": ...}}.

Sin OPENROUTER_API_KEY -> stub honesto (documentado, solo plomería).
Comparte OPENROUTER_API_KEY con S2 (s2_client).
"""
from __future__ import annotations

import asyncio
import logging
import math
import os

import httpx

log = logging.getLogger("jev")

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")
TIMEOUT_S = 3.0

# Tolerancia de suma de distribución (patrón M1, P0-3).
PROB_SUM_TOL = 0.025
ARGMAX_EPS = 1e-6

DECISION_ACTIONS = ("TAP", "TYPE", "SCROLL_DOWN", "SCROLL_UP",
                    "BACK", "DONE", "ESCALATE")


class JevError(Exception):
    pass


class JevHallucination(JevError):
    pass


def is_mock() -> bool:
    return not os.environ.get("OPENROUTER_API_KEY")


def _stub_pick(name: str, q: dict):
    kind = q.get("type")
    crit = q.get("criteria", {})
    if kind == "noul":
        return {"kind": "noul", "key": "true", "p": 1.0,
                "confidence": 1.0, "raw": {"mock": True}}
    if kind == "score":
        levels = crit if isinstance(crit, list) else list(crit)
        key = levels[-1] if levels else "1"
        return {"kind": "score", "key": str(key), "p": 1.0,
                "confidence": 1.0, "raw": {"mock": True}}
    keys = list(crit) if isinstance(crit, dict) else []
    return {"kind": "choice", "key": keys[0] if keys else "",
            "p": 1.0, "confidence": 1.0, "raw": {"mock": True}}


def _finite01(v) -> bool:
    return isinstance(v, (int, float)) and math.isfinite(v) and 0.0 <= v <= 1.0


def validate_choice(answer: dict, criteria: dict) -> tuple[str, dict, float]:
    """Valida distribución choice estricta (patrón M1, P0-3).

    Exige: answer dict con choice ∈ criteria; `probabilities` dict
    (no-lista) completa (len == len(criteria), toda id presente);
    confidence + probs finitas en [0,1]; |sum(probs)-1| ≤ 0.025;
    probs[choice] es argmax (eps 1e-6). Fallo → JevHallucination con el
    mensaje normativo. El loop consume SOLO la rama elegida: jamás lee
    otras entradas de probs como fallback.
    Devuelve (choice, probs, confidence).
    """
    if not isinstance(answer, dict):
        raise JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            f"(answer no es objeto: {type(answer).__name__})")
    crit = criteria or {}
    choice = answer.get("choice", answer.get("selected", answer.get("value")))
    if choice not in crit:
        raise JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            f"(choice {choice!r} fuera de criteria)")
    probs = answer.get("probabilities", None)
    if not isinstance(probs, dict):
        raise JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            "(probabilities ausente o no-dict)")
    if len(probs) != len(crit) or any(k not in probs for k in crit):
        raise JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            f"(probs incompleta: {len(probs)}/{len(crit)})")
    conf = answer.get("confidence", 0.0)
    try:
        conf_f = float(conf)
    except (TypeError, ValueError):
        raise JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            f"(confidence no numérica: {conf!r})")
    if not _finite01(conf_f) or not all(_finite01(v) for v in probs.values()):
        raise JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            "(confidence/probs no finitas o fuera de [0,1])")
    if abs(sum(float(v) for v in probs.values()) - 1.0) > PROB_SUM_TOL:
        raise JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            f"(suma={sum(float(v) for v in probs.values()):.3f} ±{PROB_SUM_TOL})")
    if float(probs[choice]) + ARGMAX_EPS < max(float(v) for v in probs.values()):
        raise JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            f"(choice {choice!r} no es argmax)")
    return choice, {k: float(v) for k, v in probs.items()}, conf_f


def _norm(name: str, q: dict, ans: dict) -> dict:
    kind = q.get("type", "?")
    crit = q.get("criteria", {})
    if kind == "choice":
        key, probs, conf = validate_choice(ans, crit)
        return {"kind": "choice", "key": key,
                "p": float(probs[key]),
                "confidence": conf, "raw": ans}
    if kind == "noul":
        p = float(ans.get("noul", ans.get("p", 0.0)))
        return {"kind": "noul", "key": "true" if p >= 0.5 else "false",
                "p": p, "confidence": abs(p - 0.5) * 2, "raw": ans}
    if kind == "score":
        for k in ("score", "value", "position", "level"):
            if isinstance(ans.get(k), (int, float)):
                v = float(ans[k])
                return {"kind": "score", "key": str(v), "p": v,
                        "confidence": 1.0, "raw": ans}
        log.warning("jev score con forma desconocida: %s", ans)
        return {"kind": "score", "key": "?", "p": 0.0,
                "confidence": 0.0, "raw": ans}
    raise JevError(f"{name}: tipo de pregunta desconocido: {kind}")


async def _post(payload: dict) -> dict:
    headers = {"Authorization": f"Bearer {os.environ['OPENROUTER_API_KEY']}",
               "Content-Type": "application/json",
               "HTTP-Referer": "https://github.com/jev-android-mcp",
               "X-Title": "jam-loop"}
    last: Exception | None = None
    for attempt in (0, 1):
        try:
            async with httpx.AsyncClient(timeout=TIMEOUT_S) as c:
                r = await c.post(ENDPOINT, headers=headers, json=payload)
                r.raise_for_status()
                return r.json()
        except (httpx.TransportError, httpx.TimeoutException) as e:
            last = e
            await asyncio.sleep(0.5)
    raise JevError(f"red Jev falló tras retry: {last}")


async def ask(state: dict, questions: dict) -> tuple[dict, dict]:
    """Una request con TODAS las preguntas (batch). Devuelve (answers, usage)."""
    if is_mock():
        log.info("jev stub (sin OPENROUTER_API_KEY): happy-path")
        return ({n: _stub_pick(n, q) for n, q in questions.items()},
                {"cost": 0.0, "mock": True})
    body = {"model": MODEL, "state": state, "questions": questions}
    data = await _post(body)
    raw_answers = data.get("answers", {})
    out = {}
    for name, q in questions.items():
        if name not in raw_answers:
            raise JevError(f"Jev no respondió {name}")
        out[name] = _norm(name, q, raw_answers[name])
    return out, data.get("usage", {})


def _usage_tokens(usage: dict) -> tuple[int, int, float | None]:
    """(in_tokens, out_tokens, provider_cost|None) desde usage heterogéneo."""
    if not isinstance(usage, dict):
        return 0, 0, None
    in_tok = usage.get("in_tokens", usage.get("prompt_tokens", 0)) or 0
    out_tok = usage.get("out_tokens", usage.get("completion_tokens", 0)) or 0
    cost = usage.get("cost")
    try:
        in_tok, out_tok = int(in_tok), int(out_tok)
    except (TypeError, ValueError):
        in_tok, out_tok = 0, 0
    try:
        cost = float(cost) if cost is not None else None
    except (TypeError, ValueError):
        cost = None
    return in_tok, out_tok, cost


async def ask_decision(goal: str, table: list, snapshot_id: int, *,
                       history_summary: str = "",
                       s2_guidance: str = "",
                       s2_hint: str = "",
                       current_app: str = "",
                       screen_goal: str = "",
                       focused_field: dict | None = None) -> tuple[dict, dict]:
    """Single-pass S1: 1 llamada -> {action, target, needs_system_2, conf}.

    Contrato generic-dual-tier §3 (normativo v3): `state` + `questions`
    100% en inglés — claves, instrucciones, etiquetas de tabla. La tabla
    viaja enriquecida como [idx, class_short, flags, label]; el `id`
    opaco y los `bounds` quedan en `by_idx` del loop. Cabecera siempre
    con `current_app` (foreground real) + `screen_goal` (sub-objetivo en
    inglés; sin `screen_goal` S2 se usa el goal verbatim con
    `operator_verbatim: true`; el goal original se conserva en forense).

    `table`: filas {idx, class_short, flags, label, ...} (0..253).
    `focused_field`: vista {label, holds} del campo enfocado (P0-1);
    viaja como `state.focused_field` (EN; "empty"/máscara si no hay).
    `s2_hint` es alias legacy de `s2_guidance`. Sin key -> stub honesto
    {mock: true} que tapea la primera fila si existe (plomería).
    Clave/target fuera de criteria -> JevHallucination, nunca actuar.
    """
    from .core import loop_helpers as _h

    guidance = s2_guidance or s2_hint or ""
    screen = screen_goal or goal
    if isinstance(table, (list, tuple)) and table and isinstance(table[0], (list, tuple)):
        serial = [list(r) for r in table]
    else:
        rows_norm, _ = _h.build_table(list(table or []))
        serial = _h.serialize_table(rows_norm)
    target_keys = [str(r[0]) for r in serial] + ["NONE"]
    if isinstance(focused_field, dict) and focused_field.get("label"):
        ff_label = str(focused_field.get("label") or "none")
        ff_holds = focused_field.get("holds", "empty")
        ff_view = {"label": ff_label,
                   "holds": str(ff_holds) if ff_holds else "empty"}
    else:
        ff_view = {"label": "none", "holds": "empty"}
    state = {
        "goal": goal,
        "screen_goal": screen,
        "operator_verbatim": not bool(screen_goal),
        "current_app": current_app,
        "snapshot_id": snapshot_id,
        "table": serial,
        "focused_field": ff_view,
        "history": history_summary,
        "s2_guidance": guidance,
    }
    questions = {
        "action": {
            "type": "choice",
            "instructions": (
                "Pick ONE primitive to advance the goal. TAP taps a node; "
                "TYPE types into a field (only with text already present in "
                "goal/UI or S2 text_payload, never invent text); SCROLL_* "
                "scrolls; BACK goes back; DONE only if the goal is already "
                "achieved on screen; ESCALATE on conf < 0.70, anomaly, or "
                "open-text need."),
            "criteria": {a: a for a in DECISION_ACTIONS},
        },
        "target": {
            "type": "choice",
            "instructions": (
                "Target table row index. NONE if the action needs no node "
                "(BACK/DONE/ESCALATE) or there is no useful candidate. "
                "Never invent indices outside the table."),
            "criteria": {k: k for k in target_keys},
        },
        "needs_system_2": {
            "type": "noul",
            "instructions": ("Does this step require System-2 open-text "
                             "composition or disambiguation (text to type "
                             "not present)?"),
        },
    }
    if is_mock():
        answers, usage = await ask(state, questions)
    else:
        answers, usage = await ask(state, questions)
    a_action = answers["action"]
    a_target = answers["target"]
    a_s2 = answers["needs_system_2"]
    tgt = a_target["key"]
    # Consume SOLO la rama elegida (M1): jamás leer otras entradas de
    # `probabilities` como fallback; conf = min de las dos ramas con
    # check de finitud (NaN/Inf → hallucination, nunca actuar).
    conf_raw = min(a_action.get("confidence", 0.0),
                   a_target.get("confidence", 0.0))
    try:
        conf_val = float(conf_raw)
    except (TypeError, ValueError):
        raise JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            f"(conf no numérica: {conf_raw!r})")
    if not math.isfinite(conf_val):
        raise JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            "(conf no finita)")
    decision = {
        "action": a_action["key"],
        "target": "NONE" if tgt == "NONE" else int(tgt),
        "needs_system_2": a_s2["key"] == "true",
        "conf": conf_val,
        "type_text": "",
    }
    if is_mock():
        decision["mock"] = True
        if serial and decision["action"] == "TAP" and decision["target"] == "NONE":
            decision["target"] = serial[0][0]
    return decision, usage
