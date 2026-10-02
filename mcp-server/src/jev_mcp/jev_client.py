"""Cliente Jev (TypeSafe System One) vía OpenRouter.

Contrato: ask(state, questions) -> ({nombre: respuesta}, usage).
Respuestas normalizadas: choice -> clave elegida; noul -> true/false;
score -> número. Solo claves de `criteria`, o JEV_HALLUCINATION.

Shape real verificado en ~/Mango-mcp/logs/local-jev-response-101.json:
{"answers": {"q": {"choice": "k", "confidence": 0.9,
"probabilities": {...}, "type": "choice"}}, "usage": {"cost": ...}}.

Sin OPENROUTER_API_KEY -> stub happy-path (documentado, solo plomería).
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
