# PERFORMANCE.md — latencias medidas en hardware real (v1.2.1)

> Fuente única de números de rendimiento. El `README.md` resume y enlaza aquí;
> ante discrepancia, **este archivo manda**. Solo datos ya medidos en
> `docs/TESTING.md`, `docs/BUILD.md`, `docs/specs/paradigm-shift.md §5` y
> forense `logs/run-*.jsonl` + `mcp-server/logs/run-*.jsonl` +
> `logs/jav-e2e-*.md`. Nada proyectado, nada inventado. 100% genérico:
> sin paquetes, contactos, textos ni keys.

## 0. Bancos (fijos para todas las tablas)

- **Host:** Debian 13, Celeron 847 (2 núcleos @ 1.1 GHz), 3.7 GiB RAM
  (~1.7 libres) + 7.5 GiB swap, JDK 21. Toolchain en `~/Android/Sdk`.
  (`ARCHITECTURE.md §3`.)
- **KJ5:** TECNO KJ5, Android 13 (API 33), sin root, banco loop S1/S2 por Wi-Fi.
- **A10:** Alcatel/TCL 5002E, Android 10, 720×1440, serial `e03638e5`,
  **solo USB**, banco director v5. (`docs/TESTING.md §9–10`.)
- **LG7n:** TECNO LG7n, Android 12 (API 31), banco secundario Fases 1–4.

## 1. Percepción `dump_ui` (in-app, en dispositivo)

Fuente: `docs/TESTING.md §2–2b` + `ARCHITECTURE.md §3`.

| Árbol | Latencia medida |
|---|---|
| 13 nodos (onboarding) | **40 ms** (5 ms en caliente) |
| 66 nodos (ajustes, estático) | **106 ms**, anclas 26/26 = 100% |
| 124 nodos (chat vivo) | **264 ms**, anclas 73/86 = 84.9% vs piso de ruido uia-vs-uia 80.2% |
| Escalado | **~2 ms/nodo** (IPC por nodo); tope 500 nodos, peor caso **~1 s** |
| Referencia `uiautomator dump` | **4353 ms** (~16× más lento a igual carga) |

Contrato vigente: `dump_ui` sin campo `secure`; `root == null` = sin ventana
activa (transitorio). Superficie protegida solo como `SECURE_SURFACE` en
`screenshot`.

## 2. Host → dispositivo por ADB (incluyen ~63 ms ida/vuelta ADB)

Fuente: `ARCHITECTURE.md §3` (host→USB).

| Operación | Latencia medida |
|---|---|
| `shell echo` | 63 ms |
| `dumpsys window` | 80 ms |
| `input tap` | **151 ms** |
| `pm list` | 299 ms |
| `screencap` | **1409 ms** |
| `uiautomator dump` | **4353 ms** |

Conclusión registrada: el cuello es **percepción**, no input;
AccessibilityService in-process es la vía primaria.

## 3. Actuación + decisión (bucle histórico S1/S2, congelado)

Fuente: `docs/specs/paradigm-shift.md §5` + `logs/run-20261006-*.jsonl`.

| Etapa | Latencia medida |
|---|---|
| tap (`ACTION_CLICK` primero si clickable, `dispatchGesture` fallback, siempre `via`) | **~70 ms** (`avg_tap_ms 69.7` redo calculadora; `84.6` ajustes+batería) |
| S1 Jev (single-pass) | **~1.6 s** (`avg_s1_ms 1589.5` redo; pasos individuales 1318–2158 ms) |
| S2 DeepSeek-direct (histórico, **retirado 2026-10-07**; S2 vive solo en OpenRouter) | **~1.9 s/llamada** vs flash **~22 s/llamada** (corridas validación 2026-10-05/06) |
| `fast-path` v4 | ahorra 1 `dump`/paso (nunca salta compuertas) |

## 4. Carril nativo N0 + intents 1-salto (runtime Go, A10 USB)

Fuentes: `docs/BUILD.md §9` (medición manual WS `127.0.0.1:38472`) +
`logs/jav-e2e-20261008-093502.md` (2.ª corrida, e2e Go 35 tools).

| Operación | Latencia medida |
|---|---|
| `open_url` con `package` explícito (1 salto, sin chooser, `via: startActivity-package`, foreground directo) | **~130 ms** (`latency_ms 130.3`) |
| `open_url` sin `package` (resolución sistema, chooser si >1 handler) | segundos (poll foreground; caso medido ~12.8 s total en `logs/run-intent-20261007-130650.jsonl`) |
| N0 típico e2e Go (`get_battery` 62 ms, `get_memory` 57 ms, `get_storage` 64 ms, `get_device_info` 52 ms, `settings_get` 49 ms, `open_url` VIEW 67 ms) | **~50–190 ms** por tool |
| `get_cpu basic` | 161 ms |
| `list_packages` (filtro vacío) | 135–139 ms |
| `read_screen` (fresco) | 165–435 ms según árbol |
| `scroll down` real | 460–515 ms |
| `press_back` / `press_home` reales | 55–67 ms / 61–66 ms |
| Media e2e Go 2.ª corrida (53 entradas: ok + planned + errores honestos) | **lat_media 173 ms**, lat_max 3073 ms (`get_location` TIMEOUT 3 s) |
| Media e2e Go 1.ª corrida (referencia) | lat_media 298 ms, lat_max 3658 ms (`send_intent` VIEW con poll) |
| Cotidiano 2026-10-10 A10 USB (`logs/run-20261010-011841-cotidiano.jsonl`): `open_url` morphe 1-salto (×3) | **73–199 ms** (`via: startActivity-package`, foreground morphe OK en reintentos) |
| Cotidiano 2026-10-10: `read_screen` morphe player 34 nodos / Fossify messages 11 nodos | **366–486 ms** / **162–192 ms** |
| Cotidiano 2026-10-10: `list_packages` 130 pkgs + filtros fossify/morphe/rvx/seal | **104–115 ms** |
| Cotidiano 2026-10-10: `device_status` (WS RTT/hello) / `get_foreground` / `press_back`+`press_home` | **190 ms** / **79–241 ms** / **56–134 ms + 44 ms** |
| Cotidiano 2026-10-10: `open_app` Fossify messages (Shizuku + poll foreground) | **5546 ms** (poll, no nativa) |
| Cotidiano 2026-10-10: S1 Jev resolve Fossify OK (`idx 0 conf 0.86`, sin tap) | **415 ms** (<1.8 s) |
| Cotidiano 2026-10-10: S1 Jev resolve YouTube BLOQUEO (`envelope S1 no-JSON`, endpoint 200 vacío ×5) | **408–1354 ms** (sin tap ciego, sin descarga) |

`package` desconocido → `PACKAGE_NOT_FOUND`; instalado sin handler →
`INTENT_UNRESOLVED`. Costo $0 (sin LLM). Detalle tabular en
`docs/TESTING.md §10`.

## 5. Ronda sintética 2026-10-15 (A10 API 29, APK P4/P5/P6 + fix WebP)

Fuente: `docs/TESTING.md §12` (crudo) + `docs/BUILD.md §16`. Sin LLM,
`n=20–30` por método, WS loopback con token del `.env`.

| Método | p50 | max |
|---|---|---|
| `get_foreground` | **26 ms** | 38 ms |
| `dump_ui` (30 n) | **74 ms** | 102 ms |
| `screenshot` webp q80 | **1037 ms** | 1041 ms |
| `screenshot` png q80 | **1101 ms** | 1119 ms |
| `get_device_info` / `get_memory` / `get_storage` / `get_battery` | **7–12 ms** | ≤21 ms |
| `get_cpu` (delta `/proc/stat`) | **131 ms** | 137 ms |

Escalado medido cross-app (8 apps, 14–117 nodos): **`~15 ms + ~1.4 ms/nodo`**
(117 n → 183 ms; ≤150 n ≤300 ms ✔), mejor que el `~2 ms/nodo` de §1.
Comparativa de ruta: `dump_ui` accesibilidad **74 ms** vs `uiautomator dump`
vía ADB **~2280 ms** (**~30×**); `screenshot` Jav **1037 ms/20 KB webp** vs
`adb screencap` **683 ms/93 KB png** (Jav paga serialización+base64 a cambio de
menos bytes y una sola conexión).

**Mejoras cerradas en la ronda:** `screenshot{format:webp}` dejó de devolver
`INTERNAL_ERROR` (era `WEBP_LOSSY`, API 30+, sobre API 29) → `{ok, via:"screencap"}`;
`tap_node` sin dump interno (P4) y memoria `[tried]` evitan re-percibir; secretos
fuera de `candidates` (P5). Detalle de causa/efecto en `docs/BUILD.md §15` y `§16`.

## 6. Costos (modelo vigente)

- S1 Jev: **`$0.042` in / `$0.00` out por MTok** (normativo).
- S2: tasa configurable vía env (`GLM_RATE_IN` / `GLM_RATE_OUT`), default =
  placeholder ajustable, nunca verdad oficial. (`docs/specs/go-migration-plan.md §0`.)
- Por corrida: **<$0.003** (detalle por tarea en `docs/benchmarks/TASK_HISTORY.md`).
- Cada llamada S1/S2 loguea `[COST]` + campo `cost` por paso en el forense.

## 7. Cómo reproducir (sin inventar bancos)

```bash
make build          # binario dist/jav-linux-amd64 (cmd/jav, stdio)
go test ./...       # suite Go (sin dispositivo)
adb forward tcp:38472 tcp:38472
# e2e Go 35 tools contra Jav: ver logs/jav-e2e-*.md (cabecera del informe)
```

Historial Python (`mcp-server/`, `uv run pytest`, 148 en verde) congelado como
referencia: sus jsonls forenses siguen citándose en `TASK_HISTORY.md`, pero el
runtime activo es 100% Go.

## 8. Sesión persistente + `jav pair` (v1.2.1, WSS/Tailnet, TECNO real)

Fuente: prueba de campo 2026-10-16, VPS `racknerd-54f9d67`
(`100.77.106.123`) → **TECNO Pova 4** (`100.105.124.102`), `wss://…:38472/` por
Tailnet (`tailscale ping` ≈ **176 ms**), cliente MCP stdio Go v1.2.1. "Antes" =
`dial`+`hello` por llamada (v1.2.0 / `1.2.1-dev` sin persistencia); "después" =
sesión persistente compartida (`pkg/jam`, `sharedMu`).

| Medición | Antes (dial+hello por llamada) | Después (persistente v1.2.1) |
|---|---|---|
| Ráfaga n=10 mixta (`get_foreground`/`get_battery`/`read_screen`) | avg **989 ms** (min 829, max 1321) | avg **320 ms** (min 132, max 875) |
| 20× tools ligeras (`get_foreground`/`get_battery`) | — | avg **237 ms**; `get_battery` avg **142 ms** (min 120, max 180) |
| `device_status` ×10 consecutivos | — (riesgo `4001: BUSY`) | avg **336 ms**, **BUSY=0**, `isError=0` |
| Frames `hello` por ráfaga de 10 | **11** | **0** (reusa el `hello` de warmup) |
| `jav pair` (hello + `get_device_info` + Auto-TOFU) | `openssl` a mano + `.env` | **~0.98 s**, un solo comando, sin `.env` |

Desglose del "antes" (v1.2.0, avg de 6): `dial+hello` ≈ **1074 ms** +
`close` ≈ **248 ms** + comando ≈ **207 ms** → **~86 %** de cada llamada era
churn TLS/WS. La sesión persistente elimina ese churn: el costo por llamada
pasa a ser casi todo el comando en el dispositivo (tools ligeras **~140 ms**).

**Cierre ordenado (bug `4001: BUSY`):** el servidor Android es single-client y
solo libera el slot en `onClose`; un cierre TCP abrupto (solo FIN) no lo dispara
hasta su timeout de conexión perdida (~2 min) → `websocket: close 4001: BUSY`.
`Client.Close` ahora envía un frame `close` y espera el eco del peer
(≤ `closeTimeout` 500 ms): el slot se libera de inmediato.

**Auto-TOFU:** `jav pair 100.105.124.102 <token>` vinculó **TECNO LG7n (SDK 31)**
con `cert_fingerprint 036898d996256f8e…` (coincide con el prefijo del cert
`CN=jav.local` de la app, válido hasta 2036). Auditoría del teléfono: todas las
entradas `origin=100.77.106.123` (IP del VPS), **nunca** loopback; scopes
mapeados (`auth`/`n0`/`ui`/`read`/`admin`).

## 9. Token budget de arranque medido con cliente real (v1.2.2)

Fuente: `cmd/jav-tokens` (harness stdio, JSON-RPC puro) contra
`dist/jav-linux-amd64` v1.2.2, **sin dispositivo**: `initialize` + `tools/list` +
`resources/read`. Tokenizer **real** `tiktoken` (`cl100k_base`, familia GPT-4),
no la aproximación `bytes/4` de `cmd/audit-mcp`. Reproducir: `make tokens`.

| Plano | Bytes | Tokens (cl100k) |
|---|---|---|
| `instructions` (initialize) | 1 721 | **385** (218 palabras) |
| `tools/list` (38 tools, payload completo) | 13 095 | **3 166** |
| **carga cognitiva** (instructions + Σ descripciones) | 6 563 | **1 783** |
| ficha individual `android://tool/read_screen` | 915 | **230** |
| ficha individual `android://tool/tap_node` | 866 | **233** |
| **total arranque** (instructions + tools/list) | 14 816 | **3 551** |

**Objetivo ≤3000 tokens → ✅ sobre la carga cognitiva (1 783).** El *total
arranque* (3 551) es mayor porque incluye el **esquema MCP fijo** (nombres,
`inputSchema`, `annotations` de las 38 tools), que no es reducible sin romper el
contrato; `audit-mcp` ya lo documenta como "no reducible".

**Desvío vs `audit-mcp` (bytes/4):** 1 631 → 1 783 = **Δ +9.3 %** (dentro del
umbral ±20 %). Conclusión: la aproximación `bytes/4` de `audit-mcp` es un proxy
razonable para la carga cognitiva; **no** hace falta reajustar `CompactDesc`.

**Reproducibilidad:** el primer uso descarga el BPE `cl100k_base` de
`openaipublic` y lo cachea; las corridas siguientes son offline (~0.6 s).
`--encoding o200k_base` está disponible pero fuerza otra descarga de red.

## 10. Certificación viva 38/38 (v1.2.5+opt, 2026-10-17, TECNO LG7n)

Fuente: script stdio JSON-RPC (`/tmp/opencode/cert38.py`) → `dist/jav-linux-amd64`
→ WSS/Tailnet al TECNO LG7n (SDK 31), app v1.2.5 (CI) en foreground,
Shizuku root + accesibilidad activos, **sin USB** (cable desconectado).
Sesión persistente: 1 `hello`; latencias **calientes** salvo lo indicado.
40 llamadas: **29 OK** + **11 errores honestos/de compuerta** (ninguna tool
colgó, 0 timeouts). `tools/list` 38/38 y recursos/prompts completos.

| Grupo | Tool | ms | Resultado |
|---|---|---|---|
| state | `device_status` | 1 254 | ok (frío: incluye dial+hello) |
| state | `get_foreground` | 32 | ok (O(1), sin snapshot) |
| state | `list_packages` | 23 | `ADB_FAILED` honesto (host-adb por diseño; sin USB) |
| state | `get_battery` | 306 | ok |
| state | `get_memory` | 245 | ok |
| state | `get_storage` | 33 | ok |
| state | `get_cpu` | 340 | ok |
| state | `get_device_info` | 316 | ok |
| state | `get_audit` | 296 | ok (ring 500) |
| ui | `press_home` | 210 | ok (wake real) |
| ui | `read_screen` | 263 | ok |
| ui | `tap_node` (snapshot 0) | 10 | `STALE_SNAPSHOT` (compuerta) |
| ui | `tap_text` (texto ausente) | 77 | `SELECTOR_NOT_FOUND` |
| ui | `type_text` (snapshot 0) | 263 | `STALE_SNAPSHOT` |
| ui | `scroll down` | 538 | ok (real) |
| ui | `press_back` | 107 | ok (real) |
| ui | `wait_for_text` (1 500 ms) | 1 642 | `TIMEOUT` (compuerta) |
| ui | `open_app` (Settings) | 1 835 | ok + verificación de foreground |
| ui | `close_app` (Settings) | 975 | ok (force_stop sin grant) |
| ui | `screenshot` (PNG default) | 21 497 | ok (`via=takeScreenshot`; usar `fmt=webp`) |
| native | `settings_get` | 699 | ok |
| native | `settings_put` | 480 | **planned** (preview; sin ejecutar) |
| native | `open_url` | 360 | ok (ejecuta por diseño; `via=startActivity`) |
| native | `send_intent` VIEW | 375 | ok (ejecuta; las acciones SEND/CALL sí exigen confirm) |
| native | `get_clipboard_device` ×2 | 2 679 / 2 347 | ok `via=shizuku-iclipboard` (baseline pre-opt) |
| native | `get_app_usage` | 368 | ok |
| native | `list_contacts` (0 matches) | 267 | ok |
| native | `add_contact` | 182 | **planned** (retest con `display_name`) |
| native | `list_events` | 241 | ok |
| native | `create_event` | 92 | **planned** |
| native | `list_notifications` | 20 | `NOTIFICATION_LISTENER_DISABLED` (cap ausente) |
| native | `reply_notification` | 31 | **planned** |
| native | `media_state` | 28 | `MEDIA_SESSIONS_UNAVAILABLE` (listener) |
| native | `media_control stop` | 28 | **planned** |
| native | `get_location` | 275 | `LOCATION_UNAVAILABLE` (proveedores off) |
| native | `take_photo` | 77 | **planned** (FGS obligatorio) |
| native | `adb_shell rm -rf /` | 982/19 | **planned** `reason=denylist_irreversible` |
| native | `adb_shell` self-harm | 461 | `SHELL_DENYLIST` (sin grant) |
| native | `adb_shell rm -rf / + confirm` | 60 365 | `SHELL_DENIED` (grant no tapeado; bloqueo real 60 s) |
| resolve | `resolve_element` (S1) | 3 052 | ok + `evidence.cost` **$0.000053** (1 llamada) |

**Recursos y prompts**: `android://tools/catalog|state|ui|native|resolve` +
`android://tool/read_screen` leídos 6/6 (1–8 ms en Go; 966–18 018 chars);
`prompts/list` = `navigate_and_copy`, `send_verified`, `troubleshoot_app`;
`prompts/get` 3/3 (1 mensaje cada uno).

**Nota latencias**: este banco (PC local ↔ TECNO por Tailnet en la misma red)
da tools ligeras de **~30–40 ms** calientes (vs ~140 ms VPS→TECNO de §8);
las cifras grandes incluyen el **efecto** real en el dispositivo (open_app,
screenshot PNG, scroll, clipboard pre-opt) más el roundtrip.

**Post-opt (APK con caché de `appops`/`apkPath`, instalado 2026-10-17 por
USB)**: 8 lecturas de clipboard — primera de ráfaga **3.3–3.9 s**
(`app_process` en frío), resto **1.65–2.2 s**, **avg caliente 1 858 ms**
(pre-opt 2 168–2 679 ms; ~15–25 % mejor). El clip sobrevive todas las lecturas
(mismo `sha256`, 0 `Clearing clipboard`). Los ~150 ms del directive no son
alcanzables: el costo dominante es el spawn de `app_process` por lectura
(aislamiento uid 2000). `list_packages` con USB: **347 ms** (cierra el
`ADB_FAILED` de la tabla).

**Hallazgo + fix**: `adb_shell` planned devolvía `verified:true`
(`jamCall` no mapeaba `planned`); corregido a `verified:false` y retestado en
vivo (`ok:true verified:false planned:true`). Detalle: `docs/BUILD.md §31`,
narrativa: `TASK_HISTORY.md §11`.
