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
import os

import httpx

log = logging.getLogger("jev")

ENDPOINT = "https://openrouter.ai/api/alpha/decisions"
MODEL = os.environ.get("JEV_MODEL", "typesafe/jev-1.13")
TIMEOUT_S = 3.0

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


def _norm(name: str, q: dict, ans: dict) -> dict:
    kind = q.get("type", "?")
    crit = q.get("criteria", {})
    if kind == "choice":
        key = ans.get("choice", ans.get("selected", ans.get("value")))
        if key not in (crit or {}):
            raise JevHallucination(f"{name}: Jev devolvió {key!r} fuera de criteria")
        probs = ans.get("probabilities", {}) or {}
        return {"kind": "choice", "key": key,
                "p": float(probs.get(key, ans.get("confidence", 0.0))),
                "confidence": float(ans.get("confidence", 0.0)), "raw": ans}
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
                       s2_hint: str = "") -> tuple[dict, dict]:
    """Single-pass S1: 1 llamada -> {action, target, needs_system_2, conf}.

    `table`: filas {idx, id, label, ...} (0..253). Sin key -> stub honesto
    {mock: true} que tapea la primera fila si existe (plomería).
    Clave/target fuera de criteria -> JevHallucination, nunca actuar.
    """
    target_keys = [str(r["idx"]) for r in table] + ["NONE"]
    state = {
        "goal": goal,
        "snapshot_id": snapshot_id,
        "table": [(r["idx"], r["id"], r["label"]) for r in table],
        "history": history_summary,
        "s2_hint": s2_hint,
    }
    questions = {
        "action": {
            "type": "choice",
            "instructions": (
                "Elige UNA primitiva para avanzar el goal. TAP toca un nodo; "
                "TYPE escribe en un campo (solo si el texto ya existe en "
                "goal/UI, nunca inventes texto); SCROLL_* desplaza; BACK "
                "retrocede; DONE si el goal ya se cumplió (verificado en "
                "pantalla); ESCALATE si conf < 0.70, anomalía o necesitas "
                "redacción abierta."),
            "criteria": {a: a for a in DECISION_ACTIONS},
        },
        "target": {
            "type": "choice",
            "instructions": (
                "Fila de la tabla objetivo (índice). NONE si la acción no "
                "necesita nodo (BACK/DONE/ESCALATE) o no hay candidato útil. "
                "Nunca inventes índices fuera de la tabla."),
            "criteria": {k: k for k in target_keys},
        },
        "needs_system_2": {
            "type": "noul",
            "instructions": ("¿Requiere redacción abierta o desambiguación "
                             "de Sistema 2 (texto a escribir no presente)?"),
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
    decision = {
        "action": a_action["key"],
        "target": "NONE" if tgt == "NONE" else int(tgt),
        "needs_system_2": a_s2["key"] == "true",
        "conf": float(min(a_action.get("confidence", 0.0),
                          a_target.get("confidence", 0.0))),
        "type_text": "",
    }
    if is_mock():
        decision["mock"] = True
        if table and decision["action"] == "TAP" and decision["target"] == "NONE":
            decision["target"] = table[0]["idx"]
    return decision, usage
