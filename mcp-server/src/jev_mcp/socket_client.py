"""Cliente WebSocket mínimo hacia Jam (Fase 2).

Protocolo: PROTOCOL.md. Sin Jev todavía: hello + dump_ui + tap.
Uso: JEV_WS_URL + JEV_TOKEN en entorno (ver ../.env.example).
"""
from __future__ import annotations

import json
import uuid

from websockets.asyncio.client import connect


class JamError(Exception):
    def __init__(self, code: str, error: str):
        super().__init__(f"{code}: {error}")
        self.code = code
        self.error = error


class JamClient:
    def __init__(self, url: str, token: str):
        self.url = url
        self.token = token
        self._ws = None
        self.scopes: list[str] = []
        self.app_version = ""

    async def __aenter__(self) -> "JamClient":
        self._ws = await connect(self.url, max_size=4 * 1024 * 1024)
        await self.hello()
        return self

    async def __aexit__(self, *exc) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    async def _send(self, method: str, params: dict | None = None) -> dict:
        """Respuesta cruda (con ok/result/error/code)."""
        assert self._ws is not None
        req = {"id": uuid.uuid4().hex[:8], "method": method, "params": params or {}}
        await self._ws.send(json.dumps(req))
        return json.loads(await self._ws.recv())

    async def call(self, method: str, params: dict | None = None) -> dict:
        """Lanza JamError si !ok; si ok devuelve `result`."""
        res = await self._send(method, params)
        if not res.get("ok"):
            raise JamError(res.get("code", "?"), res.get("error", "?"))
        return res.get("result", {})

    async def hello(self) -> dict:
        """El handshake responde plano (sin envoltura result)."""
        res = await self._send("hello", {
            "protocol_version": 1,
            "client_version": "0.1.0",
            "token": self.token,
            "client": "jev-mcp/0.1.0",
        })
        if not res.get("ok"):
            raise JamError(res.get("code", "?"), res.get("error", "?"))
        self.scopes = res.get("scopes", [])
        self.app_version = res.get("app_version", "")
        return res

    async def dump_ui(self) -> dict:
        return await self.call("dump_ui")

    async def tap(self, selector: dict) -> dict:
        return await self.call("tap", {"selector": selector})

    async def get_foreground(self) -> dict:
        return await self.call("get_foreground")

    async def wait_for_node(self, selector: dict, timeout_ms: int = 5000) -> dict:
        return await self.call("wait_for_node", {"selector": selector, "timeout_ms": timeout_ms})

    async def press_back(self) -> dict:
        return await self.call("press_back")

    async def press_home(self) -> dict:
        return await self.call("press_home")

    async def open_app(self, package: str) -> dict:
        return await self.call("open_app", {"package": package})

    async def force_stop(self, package: str) -> dict:
        return await self.call("force_stop", {"package": package})

    async def screenshot(self, fmt: str = "png", quality: int = 80) -> dict:
        return await self.call("screenshot", {"format": fmt, "quality": quality})

    async def set_clipboard(self, text: str) -> dict:
        """Escribe el clipboard via Jam (ClipboardManager, sin shell)."""
        return await self.call("set_clipboard", {"text": text})
