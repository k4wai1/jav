# PERFORMANCE.md — latencias medidas en hardware real (v1.0.2)

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

## 5. Costos (modelo vigente)

- S1 Jev: **`$0.042` in / `$0.00` out por MTok** (normativo).
- S2: tasa configurable vía env (`GLM_RATE_IN` / `GLM_RATE_OUT`), default =
  placeholder ajustable, nunca verdad oficial. (`docs/specs/go-migration-plan.md §0`.)
- Por corrida: **<$0.003** (detalle por tarea en `docs/benchmarks/TASK_HISTORY.md`).
- Cada llamada S1/S2 loguea `[COST]` + campo `cost` por paso en el forense.

## 6. Cómo reproducir (sin inventar bancos)

```bash
make build          # binario dist/jav-linux-amd64 (cmd/jav, stdio)
go test ./...       # suite Go (sin dispositivo)
adb forward tcp:38472 tcp:38472
# e2e Go 35 tools contra Jam: ver logs/jav-e2e-*.md (cabecera del informe)
```

Historial Python (`mcp-server/`, `uv run pytest`, 148 en verde) congelado como
referencia: sus jsonls forenses siguen citándose en `TASK_HISTORY.md`, pero el
runtime activo es 100% Go.
