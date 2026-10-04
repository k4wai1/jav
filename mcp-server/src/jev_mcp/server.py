"""Jam MCP server (stdio). Tools → Jam por WS. Bucle Jev en `loop.py` + tareas en `tasks/` (Fase 5)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import app as app_tools
from .tools import device as device_tools
from .tools import ui as ui_tools

mcp = FastMCP("jam")


@mcp.tool()
async def device_status() -> dict:
    """Estado: scopes, versión de Jam, app en foreground."""
    return await device_tools.device_status()


@mcp.tool()
async def list_packages(filter: str = "") -> dict:
    """Paquetes instalados (filtro opcional por subcadena). Vía adb."""
    return await device_tools.list_packages(filter)


@mcp.tool()
async def get_foreground() -> dict:
    """Paquete + activity en foreground."""
    return await device_tools.get_foreground()


@mcp.tool()
async def open_app(package: str) -> dict:
    """Abre una app (Shizuku) y verifica foreground."""
    return await app_tools.open_app(package)


@mcp.tool()
async def close_app(package: str) -> dict:
    """Cierra una app (force-stop) y verifica salida."""
    return await app_tools.close_app(package)


@mcp.tool()
async def read_screen() -> dict:
    """Pantalla normalizada: candidatos compactos + snapshot_id."""
    return await ui_tools.read_screen()


@mcp.tool()
async def tap_text(text: str) -> dict:
    """Toca el primer nodo que contenga el texto."""
    return await ui_tools.tap_text(text)


@mcp.tool()
async def tap_node(node_id: str, snapshot_id: int) -> dict:
    """Toca por id + snapshot (rápido, sin dump interno)."""
    return await ui_tools.tap_node(node_id, snapshot_id)


@mcp.tool()
async def type_text(node_id: str, snapshot_id: int, text: str) -> dict:
    """Escribe en un campo enfocado. Sin foco → NOT_FOCUSED (haz tap antes)."""
    return await ui_tools.type_text(node_id, snapshot_id, text)


@mcp.tool()
async def scroll(direction: str = "down", node_id: str | None = None) -> dict:
    """Scroll en dirección up|down|left|right, opcionalmente sobre un nodo."""
    return await ui_tools.scroll(direction, node_id)


@mcp.tool()
async def press_back() -> dict:
    """Botón atrás global."""
    return await ui_tools.press_back()


@mcp.tool()
async def press_home() -> dict:
    """Botón home global."""
    return await ui_tools.press_home()


@mcp.tool()
async def wait_for_text(text: str, timeout_ms: int = 5000) -> dict:
    """Espera a que aparezca un texto. Devuelve node_id + snapshot usable."""
    return await ui_tools.wait_for_text(text, timeout_ms)


@mcp.tool()
async def screenshot(fmt: str = "png", quality: int = 80) -> dict:
    """Captura vía takeScreenshot (w/h/via + base64)."""
    return await ui_tools.screenshot(fmt, quality)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
