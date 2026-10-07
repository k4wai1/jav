"""Resolver v5 director-client §3: Jev señala, nunca planifica.

Via nueva y minima sobre ``jev_client.ask`` con UNA sola pregunta Choice
sobre indices (+ NONE) y ``state.screen_goal`` = micro-intencion en ingles
de LA pantalla actual. NUNCA lleva el goal global, historial, ni
``s2_guidance`` con semantica global (anti-poisoning §3.1).

Diferencia con el decisor single-pass de tres preguntas (congelado con
``loop.py`` §6): aquel lleva el goal global y decide accion. Este
resolver no emite TAP/TYPE/SCROLL/BACK/DONE, no redacta texto, no abre
apps, no verifica goals. La ACCION la decide el director; Jev solo
devuelve {idx, conf}.

100% generico, sin literales de dominio. Sin key -> stub {mock:true}.
"""
from __future__ import annotations

import math

from .. import jev_client
from ..core import loop_helpers as _h
from .cost import CostTracker, jev_model_id


def build_resolve_state(
    screen_goal: str,
    table: list,
    snapshot_id: int,
    *,
    current_app: str = "",
    first_result: int | None = None,
) -> tuple[dict, dict]:
    """Construye (state, questions) ciegos al goal global (puro).

    - ``screen_goal``: micro-intencion EN de la pantalla actual, una frase
      (p.ej. "Tap the Copy link row"). NUNCA el goal global.
    - ``table``: filas dict de build_table o ya serializadas
      [idx, class_short, zone, flags, label].
    - ``state`` solo contiene: screen_goal, current_app, snapshot_id,
      table, first_result. Cero goal global, cero nombres, cero paquetes
      objetivo, cero historial, cero s2_guidance.
    - ``questions``: una sola Choice "target" sobre {idx...|NONE}.
    """
    if isinstance(table, (list, tuple)) and table and isinstance(
        table[0], (list, tuple)
    ):
        serial = [list(r) for r in table]
        rows_norm: list[dict] = []
    else:
        rows_norm, _ = _h.build_table(list(table or []))
        serial = _h.serialize_table(rows_norm)
    if first_result is None and rows_norm:
        first_result = _h.first_result(rows_norm)
    target_keys = [str(r[0]) for r in serial] + ["NONE"]
    state = {
        "screen_goal": screen_goal or "",
        "current_app": current_app or "",
        "snapshot_id": snapshot_id,
        "table": serial,
        "first_result": first_result,
    }
    questions = {
        "target": {
            "type": "choice",
            "instructions": (
                "Pick the table row index that best matches the requested "
                "element on the current screen. Choose NONE if no candidate "
                "is useful. Never invent indices outside the table."
            ),
            "criteria": {k: k for k in target_keys},
        },
    }
    return state, questions


def parse_resolve_answer(answer: dict, criteria: dict) -> tuple[int | str, float]:
    """Valida Choice estricta y devuelve (idx|NONE, conf) (puro).

    Clave fuera de criteria -> JevHallucination, nunca actuar.
    conf no finita o fuera de [0,1] -> JevHallucination.
    """
    key, _probs, conf = jev_client.validate_choice(answer, criteria)
    try:
        conf_f = float(answer.get("confidence", conf))
    except (TypeError, ValueError):
        raise jev_client.JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            f"(conf no numerica: {answer.get('confidence')!r})"
        )
    if not math.isfinite(conf_f) or not 0.0 <= conf_f <= 1.0:
        raise jev_client.JevHallucination(
            "TypeSafe returned an invalid choice distribution. "
            "(conf no finita o fuera de [0,1])"
        )
    if key == "NONE":
        return "NONE", conf_f
    return int(key), conf_f


async def resolve_element(
    screen_goal: str,
    table: list,
    snapshot_id: int,
    *,
    current_app: str = "",
    first_result: int | None = None,
    _ask=None,
    _tracker: CostTracker | None = None,
    _run_id: str = "",
) -> dict:
    """Resuelve un elemento de la pantalla actual via Jev (UMA Choice).

    Usa ``ask``, NO ``ask_decision``. Solo viaja la micro-intencion EN +
    tabla con zona; nunca el goal global.

    Devuelve {idx: int|"NONE", conf: float, snapshot_id, usage, mock?}.
    Sin key -> stub {mock:true} (plomeria, nunca exito inventado).
    Coste via CostTracker (log [COST]).
    """
    state, questions = build_resolve_state(
        screen_goal,
        table,
        snapshot_id,
        current_app=current_app,
        first_result=first_result,
    )
    ask_fn = _ask or jev_client.ask
    answers, usage = await ask_fn(state, questions)
    if "target" not in answers:
        raise jev_client.JevError("Jev no respondio target")
    norm = answers["target"]
    # ask() ya normalizo via _norm (choice validada M1). Acepta tanto la
    # forma normalizada {key, confidence} como cruda {choice,...}.
    if isinstance(norm, dict) and "key" in norm:
        key = norm["key"]
        try:
            conf = float(norm.get("confidence", 0.0))
        except (TypeError, ValueError):
            raise jev_client.JevHallucination(
                "TypeSafe returned an invalid choice distribution. "
                f"(conf no numerica: {norm.get('confidence')!r})"
            )
        if not math.isfinite(conf) or not 0.0 <= conf <= 1.0:
            raise jev_client.JevHallucination(
                "TypeSafe returned an invalid choice distribution. "
                "(conf no finita o fuera de [0,1])"
            )
        criteria = questions["target"]["criteria"]
        if key not in criteria:
            raise jev_client.JevHallucination(
                "TypeSafe returned an invalid choice distribution. "
                f"(choice {key!r} fuera de criteria)"
            )
        idx: int | str = "NONE" if key == "NONE" else int(key)
    else:
        idx, conf = parse_resolve_answer(norm, questions["target"]["criteria"])
    mock = bool(isinstance(norm, dict) and isinstance(norm.get("raw"), dict)
                and norm["raw"].get("mock"))
    tracker = _tracker or CostTracker(run_id=_run_id)
    in_tok, out_tok, pcost = jev_client._usage_tokens(usage)
    step_cost = tracker.track(
        jev_model_id(), in_tok, out_tok, step=None, tier="s1",
        provider_cost=pcost,
    )
    out: dict = {
        "idx": idx,
        "conf": float(conf),
        "snapshot_id": snapshot_id,
        "usage": usage,
        "cost_usd": step_cost,
    }
    if mock or (isinstance(usage, dict) and usage.get("mock")):
        out["mock"] = True
    return out
