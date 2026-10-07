"""Jam MCP server (stdio). Tools → Jam por WS. Agente genérico run_goal en `loop.py` (contrato docs/specs/generic-dual-tier.md)."""
from __future__ import annotations

from mcp.server.fastmcp import FastMCP

from .tools import app as app_tools
from .tools import device as device_tools
from .tools import native as native_tools
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


# --- Carril APIs directas (native-apis): sin Jev, sin UI --------------------

@mcp.tool()
async def get_battery() -> dict:
    """Batería: nivel %, cargando, enchufe, temperatura, ahorro. Sin PII."""
    return await native_tools.get_battery()


@mcp.tool()
async def get_memory() -> dict:
    """RAM: disponible/total/umbral/baja. Sin PII."""
    return await native_tools.get_memory()


@mcp.tool()
async def get_storage(detail: str = "basic") -> dict:
    """Almacenamiento interno total/libre. `fine` = N2 (METHOD_NOT_ALLOWED)."""
    return await native_tools.get_storage(detail)


@mcp.tool()
async def get_cpu(detail: str = "basic") -> dict:
    """CPU: procesadores + uso % instantáneo. `fine` = N2 (METHOD_NOT_ALLOWED)."""
    return await native_tools.get_cpu(detail)


@mcp.tool()
async def get_device_info() -> dict:
    """Hardware: modelo/ABI/pantalla/features/locale. Sin IDs persistentes."""
    return await native_tools.get_device_info()


@mcp.tool()
async def settings_get(namespace: str = "system", key: str = "") -> dict:
    """Lee un ajuste System/Secure/Global. Lectura, sin confirm."""
    return await native_tools.settings_get(namespace, key)


@mcp.tool()
async def settings_put(namespace: str = "system", key: str = "",
                        value: str = "", confirm: bool = False) -> dict:
    """Escribe ajuste System (P1). Sin confirm → planned. Secure/Global → N2."""
    return await native_tools.settings_put(namespace, key, value, confirm)


@mcp.tool()
async def open_url(url: str) -> dict:
    """Abre una URL en su app. Solo apertura; el envío va por carril Jev."""
    return await native_tools.open_url(url)


@mcp.tool()
async def send_intent(action: str, uri: str = "", package: str = "", mime: str = "",
                      confirm: bool = False, extras: dict | None = None) -> dict:
    """Lanza un intent (apertura/pre-relleno). Envíos sin confirm → planned."""
    return await native_tools.send_intent(action, uri, package, mime, confirm, extras)


@mcp.tool()
async def get_clipboard_device() -> dict:
    """Clipboard vía Jam en foreground. En bg Android 10+ → CLIPBOARD_EMPTY."""
    return await native_tools.get_clipboard_device()


@mcp.tool()
async def get_app_usage(hours: int = 24, window: str | None = None) -> dict:
    """Uso de apps agregado por paquete (top 50). `window`: today|week|raw;
    sin él, últimas `hours` (1..24). Requiere acceso a uso."""
    return await native_tools.get_app_usage(hours, window)


@mcp.tool()
async def list_contacts(query: str = "", limit: int = 50, offset: int = 0,
                        with_phone: bool = False) -> dict:
    """Contactos paginados, proyección mínima. Requiere READ_CONTACTS."""
    return await native_tools.list_contacts(query, limit, offset, with_phone)


@mcp.tool()
async def add_contact(display_name: str, phone: str = "", email: str = "",
                      confirm: bool = False) -> dict:
    """Alta de contacto (crítica). Sin confirm → planned+preview."""
    return await native_tools.add_contact(display_name, phone, email, confirm)


@mcp.tool()
async def list_events(time_min: int = 0, time_max: int = 0, calendar_id: int = 0,
                      include_location: bool = False) -> dict:
    """Eventos en ventana (máx 7 días). Requiere READ_CALENDAR."""
    return await native_tools.list_events(time_min, time_max, calendar_id, include_location)


@mcp.tool()
async def create_event(title: str, start_ms: int, end_ms: int, calendar_id: int = 0,
                       description: str = "", confirm: bool = False) -> dict:
    """Crea evento (crítico). Sin confirm → planned+preview."""
    return await native_tools.create_event(title, start_ms, end_ms, calendar_id,
                                           description, confirm)


@mcp.tool()
async def list_notifications() -> dict:
    """Notificaciones activas (título/texto≤200). Requiere listener habilitado."""
    return await native_tools.list_notifications()


@mcp.tool()
async def reply_notification(key: str, text: str, confirm: bool = False) -> dict:
    """Responde notificación vía RemoteInput (crítica). Sin confirm → planned."""
    return await native_tools.reply_notification(key, text, confirm)


@mcp.tool()
async def media_state() -> dict:
    """Sesiones multimedia activas (paquete/título/estado). Monta grant NL."""
    return await native_tools.media_state()


@mcp.tool()
async def media_control(action: str, package: str = "",
                        confirm: bool = False) -> dict:
    """Transporte play/pause/next/prev. `stop` → confirm."""
    return await native_tools.media_control(action, package, confirm)


@mcp.tool()
async def get_location(timeout_ms: int = 8000, max_age_s: int = 300) -> dict:
    """Ubicación foreground (caché primero; fix ≤30s). Sin fix → TIMEOUT."""
    return await native_tools.get_location(timeout_ms, max_age_s)


@mcp.tool()
async def take_photo(confirm: bool = False, camera: str = "back") -> dict:
    """Foto headless restringida (CAMERA+FGS+confirm). Sin confirm → planned."""
    return await native_tools.take_photo(confirm, camera)


def main() -> None:
    mcp.run()


if __name__ == "__main__":
    main()
