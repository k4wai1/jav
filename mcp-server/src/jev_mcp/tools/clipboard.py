"""Portapapeles genérico multi-app (contrato generic-dual-tier §12.4).

Flujo: la app-origen expone copiar y el enlace queda en el clipboard del
SO; el host lo lee para verificar y lo inyecta como `text_payload` en la
app-destino. 100% genérico, sin paquetes ni títulos en lo normativo.

- Lectura en el HOST vía `adb shell dumpsys clipboard` (nunca shell en
  el dispositivo: hasta Fase 6 el dispatcher responde METHOD_NOT_ALLOWED;
  el `dumpsys` corre en el host adb, no vía Shizuku-`shell`). Fallback
  opcional pegado-en-campo-efímero + read-back (vía hook inyectable, el
  pegado + lectura del `text` del nodo enfocado, nunca ACTION_SET_TEXT).
- Verificación solo por forma genérica de enlace (`https?://`, sin
  literales de dominio). Vacío o sin forma -> `CLIPBOARD_EMPTY` honesto,
  sin inventar contenido, sin avanzar al destino.
- Inyección como slot opaco `clipboard` ({len, sha256}, nunca crudo en
  forense si el goal es sensible) consumido por el TYPE destino vía
  `ACTION_SET_TEXT` con read-back `confirm_input` (§5.4, maquinaria
  existente de `pending_payloads`: cualquier slot pre-cargado vale).
"""
from __future__ import annotations

import hashlib
import re
import subprocess

#: Slot opaco bajo el que el contenido verificado entra a `pending_payloads`.
CLIPBOARD_SLOT = "clipboard"

#: Vía de lectura para forense (nunca contenido crudo si el goal es sensible).
VIA_DUMPSYS = "dumpsys"
VIA_PASTE_READBACK = "paste-readback"

#: Forma genérica de enlace: solo esquema, sin literales de dominio.
URL_SHAPE_RE = re.compile(r"https?://[^\s'\"}\]]+")

#: Sección del volcado host que porta el clip primario.
PRIMARY_CLIP_RE = re.compile(r"primary clip", re.IGNORECASE)


def _clean_url(raw: str) -> str:
    return (raw or "").strip().rstrip(".,;)")


def parse_dumpsys_clipboard(output: str) -> str:
    """Extrae el primer enlace con forma del clip primario (puro).

    Busca la sección `Primary clip` del volcado host y devuelve el primer
    token con forma `https?://` (limpio de puntuación envolvente).
    Sin sección, vacío o sin forma -> "" (el llamante lo traduce a
    `CLIPBOARD_EMPTY`). Nunca inventa contenido.
    """
    if not output or not PRIMARY_CLIP_RE.search(output):
        return ""
    section = PRIMARY_CLIP_RE.split(output, maxsplit=1)[1]
    m = URL_SHAPE_RE.search(section)
    return _clean_url(m.group(0)) if m else ""


def clipboard_error(text: str) -> dict | None:
    """Verificación por forma. None = pasa; dict = `CLIPBOARD_EMPTY`.

    Exige contenido no vacío con forma genérica de enlace. Puro.
    """
    if text and URL_SHAPE_RE.search(text):
        return None
    return {"code": "CLIPBOARD_EMPTY",
            "error": ("clipboard without link shape (empty or no "
                      "https?://); copy first, do not invent content")}


def clipboard_slot(text: str) -> dict:
    """Slot opaco `clipboard` para `pending_payloads` (puro).

    Guarda {text, len, sha256, consumed}: el texto viaja en memoria al
    `ACTION_SET_TEXT`; en forense solo len+sha256, nunca crudo.
    """
    text = text or ""
    return {"text": text, "len": len(text),
            "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest(),
            "consumed": False}


def read_clipboard(_run=None, _fallback_text: str | None = None) -> dict:
    """Lee el clipboard en el host adb y lo verifica por forma.

    `_run`: hook inyectable `(cmd, ...) -> CompletedProcess` (default
    `subprocess.run`; los tests inyectan stub). `_fallback_text`: texto
    del pegado-en-campo-efímero + read-back cuando el `dumpsys` no da
    forma (vía `paste-readback`). Devuelve envolvente {ok, verified,
    evidence, hint}-compatible: ok con {text, clipboard_len,
    clipboard_sha256, via}; fallo honesto `CLIPBOARD_EMPTY` sin tocar
    el dispositivo. Nunca ejecuta shell en el dispositivo.
    """
    run = _run or subprocess.run
    text, via = "", VIA_DUMPSYS
    try:
        proc = run(["adb", "shell", "dumpsys", "clipboard"],
                   capture_output=True, text=True, timeout=10)
        out = getattr(proc, "stdout", "") or ""
    except Exception as e:
        out = ""
        fb_err = f"adb dumpsys failed ({type(e).__name__})"
    else:
        fb_err = ""
    text = parse_dumpsys_clipboard(out)
    if clipboard_error(text) is not None and _fallback_text:
        text, via = _fallback_text or "", VIA_PASTE_READBACK
    err = clipboard_error(text)
    if err is not None:
        hint = fb_err or ("copy the link first; "
                         "do not invent content")
        return {"ok": False, "verified": False,
                "evidence": {"code": err["code"], "error": err["error"],
                             "via": via},
                "hint": hint}
    slot = clipboard_slot(text)
    return {"ok": True, "verified": False,
            "evidence": {"text": text, "clipboard_len": slot["len"],
                         "clipboard_sha256": slot["sha256"], "via": via},
            "hint": "inject as opaque slot 'clipboard' via ACTION_SET_TEXT"}
