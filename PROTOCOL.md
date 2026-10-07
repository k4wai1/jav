# PROTOCOL.md — contrato WebSocket app ↔ MCP

> Versión de protocolo: **1**. El primer frame de cada conexión es `hello`
> con `protocol_version`. Mismatch → cierre `PROTOCOL_MISMATCH`. Este archivo
> es la referencia exacta de mensajes; `ARCHITECTURE.md` es el porqué.

## 1. Transporte

- RFC 6455. Listener A: `ws://127.0.0.1:38472` (loopback, WS claro).
  Listener B (opt-in, Fase 2b): `wss://<ip-tailnet>:38472` (WSS obligatorio).
- Mensajes de texto, **una línea JSON por frame**. Frame máximo **4 MiB**
  (un PNG 720×1640 en base64 supera 1 MiB).
- Rate limit: 50 req/s global, 5/s para `shell`.
- **Single-client:** un solo cliente activo; el segundo recibe cierre `BUSY`.

## 2. Handshake

Primer frame del cliente (obligatorio, < 10 s o cierre):

```json
{"method": "hello", "protocol_version": 1,
 "client_version": "0.1.0",
 "token": "<bearer obligatorio, ver §3>",
 "client": "jev-mcp/0.1.0"}
```

Respuesta:

```json
{"ok": true, "protocol_version": 1, "app_version": "0.1.0",
 "scopes": ["read", "ui"],
 "caps": {"accessibility": true, "shizuku": true, "shell_grant": false}}
```

El gate real es `protocol_version`. `client_version` es informativo.

## 3. Auth y scopes

- Token: 32+ bytes base64url, AES-256/GCM en Keystore, en `hello`
  (**nunca en URL**), comparación en tiempo constante.
- **Token obligatorio en todos los binds, loopback incluido.**
  En Android cualquier app del teléfono puede abrir `127.0.0.1:38472`;
  el QR de onboarding ya entrega el token, cero coste UX.
- Sin token (cualquier bind) → cierre `UNAUTHORIZED`.
- Scopes del token: `read` · `ui` · `shell` · `admin`.
  Token por defecto = `read+ui`; `shell` requiere token elevado **más**
  grant activo (notificación en dispositivo: 1 comando / 5 min / 30 min).
- Lockout: 5 fallos del mismo origen en 60 s → bloqueo 5 min.

## 4. Comandos (cliente → app)

Todos: `{"id": "<uuid>", "method": "…", "params": {…}}`.
Respuestas: `{"id": "<uuid>", "ok": true, "result": {…}}` o
`{"id": "<uuid>", "ok": false, "error": "…", "code": "…"}`.

Las acciones (`tap`, `type`, `scroll`…) **no devuelven snapshot**:
el servidor no dumpea tras actuar (latencia incondicional).
El cliente verifica con `wait_for_node` / `dump_ui` cuando le importa.

### 4.0 Selectores (para `tap`, `wait_for_node`)

```json
{"text": "…", "text_contains": "…", "resource_id": "…|sufijo",
 "content_desc": "…", "class": "…", "clickable": true, "index": 0}
```

Semántica **AND** sobre los campos presentes; `resource_id` admite
sufijo (`endsWith`); `index` (default 0) elige el n-ésimo entre matches.
Primer match en orden de recorrido BFS. Determinista, sin fuzzy en v1.

| Método | Params | Result | Scope |
|---|---|---|---|
| `dump_ui` | `{}` | `{snapshot_id, package, activity, timestamp, nodes[]}` (sin ventana activa → `package: ""`, `nodes: []`) | read |
| `tap` | `{selector}` | `{node_id, via}` | ui |
| `tap_node` | `{node_id, snapshot_id}` | `{via}` (mismatch → `STALE_SNAPSHOT`) | ui |
| `type` | `{node_id, snapshot_id, text}` | `{chars}` (nodo sin foco → `NOT_FOCUSED`; el cliente hace `tap` previo explícito) | ui |
| `scroll` | `{direction: up\|down\|left\|right, node_id?}` | `{}` | ui |
| `press_back` / `press_home` | `{}` | `{}` | ui |
| `wait_for_node` | `{selector, timeout_ms}` | `{node_id, snapshot_id}` o `TIMEOUT` | ui |
| `screenshot` | `{format?: png\|webp, quality?}` | `{img_base64, w, h, via}`; superficie segura → `SECURE_SURFACE`; > 4 MiB → `PAYLOAD_TOO_LARGE` (hint: WebP q80). Fallback `screencap` en API 29 = Fase 3 | read |
| `set_clipboard` | `{text}` | `{chars}` (v5 §4.1: la propia Jam ejecuta `ClipboardManager.setPrimaryClip`; sin Shizuku, sin grant; `text` vacío → `VALIDATION_ERROR`; la lectura sigue por host `dumpsys`) | ui, sin grant |
| `open_app` | `{package}` | `{package, activity}` (`monkey -p <pkg> -c android.intent.category.LAUNCHER 1` por Shizuku; verificar con `get_foreground`) | ui, sin grant |
| `force_stop` | `{package}` | `{}` | shell, sin grant |
| `grant_permission` | `{package, permission}` | `{}` | shell, **con grant** |
| `get_foreground` | `{}` | `{package, activity}` | read |
| `list_packages` | `{filter?}` | `{packages[]}` (package visibility) | read |
| `shell` | `{command, confirm?}` | **Hasta Fase 6: `METHOD_NOT_ALLOWED` explícito** (`shell` gateado; ver §8) | shell, **con grant** |
| `get_audit` | `{limit?}` | `{entries[]}` (ring buffer, 500 entradas) | admin |

**Flujo de grant de `shell`:** la request **bloquea hasta 60 s**.
Aprobación "1 comando" → ejecuta solo si `SHA-256(command)` coincide
exacto; aprobación "5/30 min" → cubre cualquier `shell` en la ventana.
Denegación → `SHELL_DENIED`. Timeout 60 s → `TIMEOUT`.
Denylist (§8) → `SHELL_DENYLIST` salvo `admin` + `confirm: true`.

## 5. Esquema de nodo (`dump_ui`)

`nodes` es un **array plano**; el parentesco va por `children: [id]`.
`snapshot_id` es un contador monotónico persistido; `tap_node`/`type`
lo exigen y fallan con `STALE_SNAPSHOT` si cambió la UI.

```json
{"id": "n_0", "text": "Buscar", "content_desc": null,
 "class": "android.widget.EditText",
 "resource_id": "com.ejemplo.generico:id/campo_busqueda",
 "bounds": [100, 200, 900, 280],
 "clickable": true, "editable": true, "scrollable": false,
 "enabled": true, "checked": false, "focused": false,
 "visible": true, "children": ["n_1", "n_2"]}
```

Máx. 500 nodos, solo `visible`, recorrido iterativo.
**`dump_ui` no lleva campo `secure`**: `FLAG_SECURE` no oculta el árbol
de accesibilidad (TalkBack funciona en banca); solo bloquea capturas,
y eso se reporta en `screenshot` como `SECURE_SURFACE`. Sin ventana
activa: `package: ""`, `nodes: []` (típicamente transitorio).

## 6. Eventos (app → cliente, sin `id`)

```json
{"event": "ui_dirty", "package": "…", "activity": "…"}
{"event": "accessibility_state", "connected": true}
{"event": "shizuku_state", "available": true, "permission": true}
{"event": "shell_grant",
 "command_hash": "sha256:…", "scope": "once|5m|30m", "expires_at": 0}
{"event": "error", "code": "…", "message": "…"}
```

## 7. Códigos de error

`UNAUTHORIZED` · `FORBIDDEN` (sin scope) · `PROTOCOL_MISMATCH` ·
`METHOD_NOT_ALLOWED` · `VALIDATION_ERROR` · `RATE_LIMITED` · `BUSY` ·
`ACCESSIBILITY_DISABLED` · `SHIZUKU_UNAVAILABLE` · `SHIZUKU_DENIED` ·
`SELECTOR_NOT_FOUND` · `STALE_SNAPSHOT` · `NOT_FOCUSED` ·
`SECURE_SURFACE` (solo `screenshot`) ·
`PAYLOAD_TOO_LARGE` · `SHELL_DENIED` (sin grant) ·
`SHELL_DENYLIST` (requiere `admin` + `confirm: true`) · `TIMEOUT` ·
`INTERNAL_ERROR`.

## 8. Seguridad operativa

- Shell denylist: `rm -rf /`, `pm uninstall` de sistema,
  `reboot recovery`, `dd`, `wipe`, `settings put secure` crítico.
- Política de grant por método: `open_app` = scope `ui` sin grant;
  `force_stop` = scope `shell` sin grant (bajo riesgo);
  `grant_permission` y `shell` = scope `shell` **con grant**.
- Push/pull solo bajo `/sdcard/Download/jev-mcp/`.
- Rotación de token desde la app (QR nuevo); kill switch en
  Quick Settings tile + notificación (revoca tokens, detiene servidor).
- QR de onboarding: `{url, token, fingerprint}` (SHA-256 del cert, TOFU).
