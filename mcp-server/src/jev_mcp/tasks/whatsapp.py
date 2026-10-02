"""send_whatsapp(contact, text): bucle observe→decide→mutate→verify.

Fases: SEARCH → TYPE_CONTACT → PICK → VERIFY_CHAT → FOCUS_MSG →
TYPE_MSG → SEND → VERIFY → DONE.
Jev elige DENTRO de cada fase; las compuertas son deterministas
(ver interpret): título del chat, blacklist, foco, texto en input.
La verificación final es determinista, nunca solo-Jev.
"""
from __future__ import annotations

import os
import re
import time
import unicodedata

from .. import jev_client
from ..tools import app as app_tools
from ..tools import ui as ui_tools

WA = "com.whatsapp"
LEVELS = ["0%", "25%", "50%", "75%", "100%"]

FORBIDDEN_DESC = re.compile(
    r"reenviar|forward|compartir|share|eliminar|delete|borrar", re.I)


def norm(s: str) -> str:
    return unicodedata.normalize("NFKD", s or "").encode("ascii", "ignore").decode().lower()


def skeleton(s: str) -> str:
    return re.sub(r"[aeiou\s]", "", norm(s))


def name_hit(contact: str, cand: dict) -> bool:
    """Coincidencia tolerante: 'Felix' casa con 'Félex'/'FELIX'/'felex'."""
    words = [w for w in norm(contact).split() if len(w) > 2]
    hay = f"{norm(cand.get('text'))} {norm(cand.get('desc'))}"
    for w in words:
        if w in hay:
            return True
        sk = skeleton(w)
        if len(sk) >= 3 and sk in skeleton(hay):
            return True
    return False


def title_matches_strict(contact: str, title: str) -> bool:
    """El título ES el contacto (+ apellido simple o paréntesis).
    Casa: 'Felix', 'Felix García', 'Felix (trabajo)'.
    No casa: 'Félix el del bar', 'Amigos de Felix', ''.
    Ante la duda, NO matchea (abort seguro > envío equivocado)."""
    a, b = norm(contact), norm(title or "")
    if not a or not b:
        return False
    if b == a:
        return True
    if b.startswith(a + "("):
        return True
    if b.startswith(a + " "):
        rest = b[len(a) + 1:].strip()
        if rest and " " not in rest:
            return True
    return False


def find_chat_title(state: dict, contact: str) -> dict | None:
    """Título del chat abierto que matchea estricto, o None."""
    cands = state.get("candidates", [])
    for c in cands:
        if c.get("editable"):
            continue
        rid = c.get("resource_id") or ""
        if any(k in rid for k in ("contact_name", "conversation_name",
                                  "conversation_contact", "title",
                                  "toolbar_title", "conversacion")):
            if title_matches_strict(contact, c.get("text")):
                return c
    h = state.get("screen_height") or 0
    if h:
        top = h * 0.15
        for c in cands:
            if c.get("editable"):
                continue
            b = c.get("bounds") or [0, 0, 0, 0]
            if len(b) == 4 and b[1] < top and title_matches_strict(contact, c.get("text")):
                return c
    return None


def is_forbidden(c: dict) -> bool:
    t = f"{c.get('desc') or ''} {c.get('text') or ''}"
    return bool(FORBIDDEN_DESC.search(t))


def is_search_trigger(c: dict) -> bool:
    # Sin exigir clickable: el fallback a gesto cubre nodos no clicables
    # (AGENTS §5.13). Jev elige por texto/descripción.
    t = f"{c.get('text')} {c.get('desc')}"
    return bool(re.search(r"busca|search", t, re.I))


def is_msg_box(c: dict) -> bool:
    if not c.get("editable"):
        return False
    rid = c.get("resource_id") or ""
    t = f"{c.get('text')} {c.get('desc')}"
    return ("entry" in rid or "input" in rid or "mensaje" in rid.lower()
            or bool(re.search(r"mensaje|message", t, re.I)))


def is_send(c: dict) -> bool:
    rid = c.get("resource_id") or ""
    t = f"{c.get('text')} {c.get('desc')}"
    return bool(c.get("clickable")) and (
        "send" in rid or bool(re.search(r"enviar|\bsend\b", t, re.I)))


class SendWhatsappTask:
    PHASES = ("SEARCH", "TYPE_CONTACT", "PICK", "VERIFY_CHAT", "FOCUS_MSG",
              "TYPE_MSG", "SEND", "VERIFY")
    S_VERIFY = 3
    S_FOCUS = 4
    S_SEND = 6
    MAX_VERIFY_TRIES = 2

    def __init__(self, contact: str, text: str):
        self.contact = contact
        self.text = text
        self.phase = 0
        self.excluded: set[str] = set()
        self.verify_tries = 0
        self.last_pick_id = ""
        self.chat_verified = False
        self.chat_title = ""

    # ---- hooks del loop ----

    def is_sensitive(self, action: dict) -> bool:
        """Solo el tap de enviar es sensible (dry-run lo planea, no lo ejecuta)."""
        return action.get("kind") == "tap_node" and self.phase == self.S_SEND

    # ---- observación ----

    async def ensure_open(self) -> dict:
        return await app_tools.open_app(WA)

    async def observe(self) -> dict:
        import asyncio
        import logging
        last = None
        for _ in range(4):
            r = await ui_tools.read_screen()
            if not r.get("ok"):
                ev = r.get("evidence", {})
                return {"package": "", "candidates": [], "snapshot_id": -1,
                        "screen_height": 0,
                        "error": ev.get("code", "?"),
                        "error_text": ev.get("error", "?")}
            ev = r["evidence"]
            last = {"package": ev.get("package", ""),
                    "activity": ev.get("activity", ""),
                    "snapshot_id": ev.get("snapshot_id", -1),
                    "screen_height": ev.get("screen_height", 0),
                    "candidates": ev.get("candidates", [])}
            # Pantalla en transición (vacía pero con app): re-observar,
            # no abortar por un dump transitorio.
            if last["package"] == WA and last["candidates"]:
                return last
            if last["package"] != WA:
                return last
            await asyncio.sleep(0.3)
        logging.getLogger("jev").info("observe: vacío tras reintentos")
        return last

    async def go_home(self, tries: int = 5) -> bool:
        """Vuelve a la lista de chats (monkey reanuda donde quedó)."""
        import asyncio
        for _ in range(tries):
            st = await self.observe()
            if any(is_search_trigger(c) for c in st.get("candidates", [])):
                return True
            r = await ui_tools.press_back()
            if not r.get("ok"):
                return False
            await asyncio.sleep(1)
        st = await self.observe()
        return any(is_search_trigger(c) for c in st.get("candidates", []))

    # ---- preguntas ----

    def _cands(self, state: dict) -> list:
        return state.get("candidates", [])

    def _base_q(self, history: list) -> dict:
        last = (f" | paso previo: {history[-1]['action']} "
                f"ok={history[-1]['result'].get('ok')}" if history else " | inicio")
        return {
            "last_ok": {
                "type": "noul",
                "instructions": f"¿El estado actual muestra el efecto del paso previo?{last}",
                "criteria": {"true": "efecto visible", "false": "sin efecto"}},
            "progress": {
                "type": "score",
                "instructions": f"Progreso de enviar mensaje a {self.contact}",
                "criteria": LEVELS},
        }

    def questions(self, state: dict, history: list) -> dict:
        if state.get("error"):
            return {"next_action": {
                "type": "choice", "instructions": "Sin lectura de pantalla, abortar.",
                "criteria": {"abort": "no hay estado"}}}
        phase = self.PHASES[min(self.phase, len(self.PHASES) - 1)]
        cands = [c for c in self._cands(state) if not is_forbidden(c)]
        fn = {"SEARCH": self._q_search, "TYPE_CONTACT": self._q_type_contact,
              "PICK": self._q_pick, "VERIFY_CHAT": self._q_verify,
              "FOCUS_MSG": self._q_focus, "TYPE_MSG": self._q_type_msg,
              "SEND": self._q_send, "VERIFY": self._q_done}[phase]
        return {"next_action": fn(state, cands), **self._base_q(history)}

    def _q_search(self, state: dict, cands: list) -> dict:
        trig = [c for c in cands if is_search_trigger(c)]
        ed = [c for c in cands if c.get("editable")]
        crit = {f"tap:{c['id']}": c["label"] for c in trig}
        if not trig and ed:
            crit = {f"type:{c['id']}": c["label"] for c in ed[:2]}
        crit["abort"] = "no hay búsqueda visible"
        return {"type": "choice",
                "instructions": "¿Qué candidato abre la búsqueda de contactos? Elige por texto/descripción (clickable NO es señal fiable).",
                "criteria": crit}

    def _q_type_contact(self, state: dict, cands: list) -> dict:
        ed = [c for c in cands if c.get("editable")]
        if not ed:
            return {"type": "choice", "instructions": "Sin campo, abortar.",
                    "criteria": {"abort": "no hay campo"}}
        tgt = next((c for c in ed if c.get("focused")), ed[0])
        if tgt.get("focused"):
            return {"type": "choice",
                    "instructions": "Campo enfocado: escribir el nombre del contacto.",
                    "criteria": {f"type:{tgt['id']}": tgt["label"],
                                 "abort": "campo equivocado"}}
        return {"type": "choice",
                "instructions": "Campo sin foco: tocarlo primero.",
                "criteria": {f"tap:{tgt['id']}": tgt["label"],
                             "abort": "campo equivocado"}}

    def _q_pick(self, state: dict, cands: list) -> dict:
        hits = [c for c in cands
                if c["id"] not in self.excluded and name_hit(self.contact, c)][:5]
        if not hits:
            return {"type": "choice",
                    "instructions": f"Sin resultados para '{self.contact}', abortar.",
                    "criteria": {"abort": "sin resultados"}}
        crit = {f"tap:{c['id']}": c["label"] for c in hits}
        crit["abort"] = "ninguno es el contacto"
        return {"type": "choice",
                "instructions": f"¿Qué candidato es el chat de {self.contact}? Si hay varios, elige el primero (más reciente); evita duplicados con calificadores como (trabajo).",
                "criteria": crit}

    def _q_verify(self, state: dict, cands: list) -> dict:
        title = find_chat_title(state, self.contact)
        if title is not None:
            return {"type": "choice",
                    "instructions": f"El chat abierto muestra título '{title.get('text')}'. ¿Es el chat correcto de {self.contact} para enviar el mensaje?",
                    "criteria": {"proceed": f"sí, es {title.get('text')}",
                                 "abort": "no es el chat"}}
        # Sin título: reintento con el siguiente match (máx 2), si no abort.
        # Pero nunca dentro de un chat: tapear ahí re-selecciona mensajes.
        if self._has_any_title(state):
            return {"type": "choice",
                    "instructions": "Estamos dentro de otro chat (hay título, pero no es el contacto). Abortar sin tocar nada.",
                    "criteria": {"abort": "WRONG_CHAT"}}
        tried = set(self.excluded) | ({self.last_pick_id} if self.last_pick_id else set())
        rest = [c for c in cands
                if c["id"] not in tried and name_hit(self.contact, c)][:3]
        if rest and self.verify_tries < self.MAX_VERIFY_TRIES:
            crit = {f"tap:{c['id']}": f"reintentar con {c['label']}" for c in rest}
            crit["abort"] = "ninguno convence"
            return {"type": "choice",
                    "instructions": "El chat abierto no muestra el título esperado. ¿Reintentar con otro candidato?",
                    "criteria": crit}
        return {"type": "choice",
                "instructions": "Chat incorrecto y sin alternativas. Abortar.",
                "criteria": {"abort": "WRONG_CHAT"}}

    def _q_focus(self, state: dict, cands: list) -> dict:
        boxes = [c for c in cands if is_msg_box(c)] or \
                [c for c in cands if c.get("editable")]
        if not boxes:
            return {"type": "choice", "instructions": "Sin campo, abortar.",
                    "criteria": {"abort": "sin campo"}}
        box = boxes[0]
        if box.get("focused"):
            return {"type": "choice",
                    "instructions": "Campo ya enfocado: escribir directo.",
                    "criteria": {f"type:{box['id']}": box["label"],
                                 "abort": "campo equivocado"}}
        return {"type": "choice",
                "instructions": "Tocar el campo del mensaje para enfocarlo.",
                "criteria": {f"tap:{box['id']}": box["label"],
                             f"type:{box['id']}": box["label"] + " (si ya tiene foco)",
                             "abort": "campo equivocado"}}

    def _q_type_msg(self, state: dict, cands: list) -> dict:
        boxes = [c for c in cands if c.get("editable")]
        if not boxes:
            return {"type": "choice", "instructions": "Sin campo, abortar.",
                    "criteria": {"abort": "sin campo"}}
        tgt = next((c for c in boxes if c.get("focused")), boxes[0])
        if tgt.get("focused"):
            return {"type": "choice",
                    "instructions": "Escribir el mensaje.",
                    "criteria": {f"type:{tgt['id']}": tgt["label"],
                                 "abort": "campo equivocado"}}
        return {"type": "choice",
                "instructions": "Sin foco: tocar primero.",
                "criteria": {f"tap:{tgt['id']}": tgt["label"],
                             "abort": "campo equivocado"}}

    def _q_send(self, state: dict, cands: list) -> dict:
        want = norm(self.text)
        filled = [c for c in cands
                  if c.get("editable") and want and want in norm(c.get("text"))]
        if not filled:
            boxes = [c for c in cands if c.get("editable")]
            if not boxes:
                return {"type": "choice", "instructions": "Sin campo, abortar.",
                        "criteria": {"abort": "sin campo"}}
            tgt = next((c for c in boxes if c.get("focused")), boxes[0])
            return {"type": "choice",
                    "instructions": "El campo no muestra el mensaje: escribirlo (de nuevo).",
                    "criteria": {f"type:{tgt['id']}": tgt["label"],
                                 "abort": "campo equivocado"}}
        sends = [c for c in cands if is_send(c)]
        if not sends:
            return {"type": "choice",
                    "instructions": "Sin botón de enviar visible, abortar.",
                    "criteria": {"abort": "sin enviar"}}
        crit = {f"tap:{c['id']}": c["label"] for c in sends[:3]}
        crit["abort"] = "no es el botón"
        return {"type": "choice",
                "instructions": "¿Qué candidato envía el mensaje? (send/Enviar; ignora mic/adjuntar/reenviar).",
                "criteria": crit}

    def _q_done(self, state: dict, cands: list) -> dict:
        return {"type": "choice",
                "instructions": "¿El chat muestra el mensaje enviado?",
                "criteria": {"done": "mensaje visible", "abort": "no se envió"}}

    # ---- interpretación con compuertas ----

    def interpret(self, answers: dict, state: dict, history: list) -> dict:
        if state.get("error"):
            return {"kind": "abort", "code": state["error"],
                    "reason": state.get("error_text", "")}
        phase = self.PHASES[min(self.phase, len(self.PHASES) - 1)]
        if phase == "VERIFY_CHAT":
            return self._interpret_verify(answers, state)
        # La acción se rige por la fase que HIZO la pregunta (asked),
        # no por la avanzada: avanzar es para el paso siguiente.
        asked = phase
        # Avance mecánico: si el paso previo EJECUTÓ bien, se avanza;
        # la fase siguiente valida el nuevo estado por sí misma.
        # last_ok (opinión de Jev) se loguea pero no bloquea: lo que
        # detecta repeticiones inútiles es el guard STUCK_SAME de abajo.
        prev_ok = bool(history) and bool(history[-1]["result"].get("ok"))
        if not history:
            pass  # primer paso: quedarse en SEARCH
        elif (asked == "SEND" and history[-1]["action"].get("kind") == "type_text"
                and prev_ok):
            pass  # re-type en SEND: re-evaluar sin avanzar
        elif prev_ok:
            self.phase = min(self.phase + 1, len(self.PHASES) - 1)
        key = answers.get("next_action", {}).get("key", "")
        snap = state.get("snapshot_id", -1)
        if key == "done":
            return {"kind": "done", "key": key}
        action = self._action_for(key, state, snap, asked)
        if action.get("kind") in ("tap_node", "type_text") and action.get("node_id"):
            sig = (action["kind"], action["node_id"])
            prev = [(h["action"].get("kind"), h["action"].get("node_id"))
                    for h in history[-2:]]
            if len(prev) == 2 and all(s == sig for s in prev):
                return {"kind": "abort", "key": key, "code": "STUCK_SAME",
                        "reason": f"misma acción 3× seguidas: {sig}"}
        return action

    def _has_any_title(self, state: dict) -> bool:
        """¿Hay algún título de pantalla (estamos dentro de un chat/vista)?"""
        h = state.get("screen_height") or 0
        for c in self._cands(state):
            if c.get("editable"):
                continue
            rid = c.get("resource_id") or ""
            if any(k in rid for k in ("contact_name", "conversation_name",
                                      "title", "toolbar_title", "conversacion")):
                if (c.get("text") or "").strip():
                    return True
        if h:
            top = h * 0.15
            for c in self._cands(state):
                if c.get("editable"):
                    continue
                b = c.get("bounds") or [0, 0, 0, 0]
                if len(b) == 4 and b[1] < top and (c.get("text") or "").strip():
                    return True
        return False

    def _interpret_verify(self, answers: dict, state: dict) -> dict:
        key = answers.get("next_action", {}).get("key", "")
        title = find_chat_title(state, self.contact)
        if key == "proceed" and title is not None:
            self.chat_verified = True
            self.chat_title = title.get("text") or ""
            self.phase = min(self.phase + 1, len(self.PHASES) - 1)
            return {"kind": "noop", "key": key}
        if key.startswith("tap:"):
            # Reintento solo fuera de chats: dentro, tapear re-selecciona
            # mensajes (UI de reenvío). Ahí se aborta, no se tapea.
            if self._has_any_title(state):
                return {"kind": "abort", "key": key, "code": "WRONG_CHAT",
                        "reason": "en otro chat; sin reintentos dentro"}
            nid = key[4:]
            if self.last_pick_id:
                self.excluded.add(self.last_pick_id)
            self.verify_tries += 1
            self.last_pick_id = nid
            cands = {c["id"]: c for c in self._cands(state)}
            if nid not in cands or is_forbidden(cands[nid]):
                return {"kind": "abort", "key": key, "code": "FORBIDDEN_TARGET",
                        "reason": "reintento inválido o prohibido"}
            snap = state.get("snapshot_id", -1)
            return {"kind": "tap_node", "key": key, "node_id": nid,
                    "snapshot_id": snap}
        self.verify_tries += 1
        return {"kind": "abort", "key": key, "code": "WRONG_CHAT",
                "reason": f"chat sin título de {self.contact}"}

    def _action_for(self, key: str, state: dict, snap: int, phase: str) -> dict:
        cands = {c["id"]: c for c in self._cands(state)}
        if key in ("abort", "done") or ":" not in key:
            if key not in ("abort", "done"):
                raise jev_client.JevHallucination(f"clave fuera de criteria: {key}")
            if key == "done":
                return {"kind": "done", "key": key}
            return {"kind": "abort", "key": key, "code": "JEV_ABORT",
                    "reason": "Jev eligió abort"}
        kind, nid = key.split(":", 1)
        if nid not in cands:
            raise jev_client.JevHallucination(f"nodo {nid} no está en el estado")
        cand = cands[nid]
        if is_forbidden(cand):
            return {"kind": "abort", "key": key, "code": "FORBIDDEN_TARGET",
                    "reason": f"target prohibido: {cand.get('label')}"}
        if kind == "tap":
            self.last_pick_id = nid  # todo tap cuenta para exclusion en reintentos
            if phase == "SEND":
                return self._guarded_send(nid, snap, state)
            return {"kind": "tap_node", "key": key, "node_id": nid,
                    "snapshot_id": snap}
        if kind == "type":
            if not cand.get("editable"):
                return {"kind": "abort", "key": key, "code": "NOT_EDITABLE",
                        "reason": "target no editable"}
            if phase in ("FOCUS_MSG", "TYPE_MSG", "SEND") and not self.chat_verified:
                return {"kind": "abort", "key": key, "code": "NO_VERIFY",
                        "reason": "chat sin verificar; no se escribe"}
            txt = self.contact if phase in ("SEARCH", "TYPE_CONTACT", "PICK") else self.text
            return {"kind": "type_text", "key": key, "node_id": nid,
                    "snapshot_id": snap, "text": txt}
        raise jev_client.JevHallucination(f"acción desconocida: {kind}")

    def _guarded_send(self, nid: str, snap: int, state: dict) -> dict:
        """SEND solo si: chat verificado + texto en input + botón send real."""
        if not self.chat_verified:
            return {"kind": "abort", "key": f"tap:{nid}", "code": "NO_VERIFY",
                    "reason": "chat sin verificar; no se envía"}
        want = norm(self.text)
        filled = any(c.get("editable") and want and want in norm(c.get("text"))
                     for c in self._cands(state))
        if not filled:
            return {"kind": "abort", "key": f"tap:{nid}", "code": "SEND_UNSAFE",
                    "reason": "input sin el texto; no se envía"}
        cand = {c["id"]: c for c in self._cands(state)}[nid]
        if not is_send(cand):
            return {"kind": "abort", "key": f"tap:{nid}", "code": "SEND_UNSAFE",
                    "reason": "no es botón de enviar"}
        return {"kind": "tap_node", "key": f"tap:{nid}", "node_id": nid,
                "snapshot_id": snap}

    async def verify_final(self, state: dict) -> tuple[bool, dict]:
        """Check determinista: texto en el chat, fuera del input."""
        fresh = await ui_tools.read_screen()
        if not fresh.get("ok"):
            return False, {"reason": "sin lectura final"}
        cands = fresh["evidence"]["candidates"]
        want = norm(self.text)
        for c in cands:
            if c.get("editable"):
                continue
            if want and want in norm(c.get("text")):
                return True, {"node_id": c["id"], "label": c["label"],
                              "snapshot_id": fresh["evidence"]["snapshot_id"]}
        return False, {"reason": f"'{self.text}' no está en el chat"}


async def send_whatsapp(contact: str, text: str, max_steps: int = 20,
                        dry_run: bool = False,
                        log_path: str | None = None) -> dict:
    import time as _time
    from .. import loop as loop_mod
    task = SendWhatsappTask(contact, text)
    if log_path is None:
        os.makedirs("logs", exist_ok=True)
        log_path = f"logs/run-{int(_time.time())}.jsonl"
    opened = await task.ensure_open()
    if not opened.get("ok"):
        return {"ok": False, "verified": False,
                "evidence": {"code": "OPEN_FAILED", "error": opened},
                "steps": 0, "duration_ms": 0, "jev_calls": 0,
                "jev_cost": 0.0, "history": []}
    if not await task.go_home():
        return {"ok": False, "verified": False,
                "evidence": {"code": "NO_HOME",
                             "error": "sin lista de chats tras backs"},
                "steps": 0, "duration_ms": 0, "jev_calls": 0,
                "jev_cost": 0.0, "history": []}
    return await loop_mod.run(task, max_steps=max_steps, dry_run=dry_run,
                              log_path=log_path)
