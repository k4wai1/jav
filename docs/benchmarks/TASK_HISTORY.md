# TASK_HISTORY.md — tareas cerradas con números reales (v1.0.2)

> Fuente única del historial de corridas. El `README.md` resume y enlaza aquí;
> ante discrepancia, **este archivo manda**. Solo filas con forense citado
> (`logs/` o `mcp-server/logs/`) y/o tabla en `docs/TESTING.md §9–10`.
> Nada inventado. 100% genérico: goals en inglés genérico, paquetes solo como
> valores runtime del forense citado, payloads como `len`/`sha256`, sin texto
> sensible, sin keys.

## 1. Bucle S1/S2 en KJ5 (histórico, loop congelado)

Fuente: `docs/TESTING.md §9` + `PLAN.md` Fase v5.

| Tarea (genérica, EN) | Resultado | Tiempo | Costo | Forense |
|---|---|---|---|---|
| Send a short text to a known contact (text len 10, `sha256:0b894166…`) — mensajería-A | SENT, verificado en pantalla (25 steps) | ~84.9 s | ~$0.0038 | `mcp-server/logs/run-rupa-1791164922.jsonl` |
| Send a short text to a known contact (text len 10, `sha256:0b894166…`, STALE-retry `stale_recovered` ×1) — mensajería-B | SENT, verificado en pantalla (12 steps) | ~22 s | ~$0.0023 | `mcp-server/logs/run-1791243623.jsonl` |
| Open the clock app and list alarms (read-only) | OK, read verified | segundos | <$0.0001 | `mcp-server/logs/run-clock-alarms-1791164291.jsonl` (+ `…369`, `…417` re-taps `via=action_click`/`gesture`) |

## 2. Director v5 en A10 USB — Fossify 5/5 (solo no-destructivo)

Fuente: `docs/TESTING.md §9` + `docs/specs/fossify-random.md §2–3`
(finales v2; v1 con fallos honestos `STALE`/`NO_TARGET`/display erróneo
conservada como historial en los mismos directorios).

| Tarea | Resultado real leído | Tiempo | Costo | Forense final |
|---|---|---|---|---|
| Describe visible gallery folders (read-only, folder lens, no media opened) | OK | 2.3 s | $0 (sin Jev: open+read) | `logs/run-fossify-gallery-1791341893.jsonl` |
| List alarms (volatile screen, STALE-loop → text-tap fix) | OK | 5.7 s | ~$0.000054 | `logs/run-fossify-clock-1791341904.jsonl` |
| Navigate to Download and list items (incl. scroll; header 13, 2 folders + 9 files observed) | OK | 9.1 s | ~$0.000133 | `logs/run-fossify-files-1791341918.jsonl` |
| Compute a 3-digit × 2-digit product (label-guard vs `9`/`×` confusion, double-snap verified) | OK | 15.5 s | ~$0.000311 | `logs/run-fossify-calc-1791341959.jsonl` |
| List songs (permission dialog accepted, playback omitted, track lens only) | OK | 5.6 s | ~$0.000104 | `logs/run-fossify-music-1791341936.jsonl` |
| **Fossify 5/5 total** | **todo OK** | **~38 s** | **~$0.0006** | 5 jsonls v2 arriba |

## 3. Director v5 en A10 USB — batería, bloqueos honestos e intents

Fuente: `docs/TESTING.md §9–10` + `docs/BUILD.md §9`.

| Tarea (genérica, EN) | Resultado | Tiempo | Costo | Forense |
|---|---|---|---|---|
| Read battery level in system settings (level lens, `avg_tap_ms 84.6`) | OK | ~23.1 s total | ~$0.00067 | `logs/run-20261006-204303.jsonl` (`summary_b` + `end` `jev_cost 0.00067`) |
| Compute a division on stock calculator (redo; taps verificados por display) | **BLOQUEO por entorno** (`summary_b_redo ok_all: false`, `avg_tap_ms 69.7`, `avg_s1_ms 1589.5`) → B1 no certificable | n/a | $0 | `logs/run-20261006-204449-calc.jsonl` |
| Multi-app: copy a video link, paste into a downloader site, start download | **BLOQUEO honesto** (`verify_download ok: false`, `DOWNLOAD_NOT_STARTED`; `INPUT_UNFOCUSABLE` ×4 + `CLIPBOARD_EMPTY` + `CONVERT_UNRESPONSIVE` intermedios; 25 phases) | n/a | ~$0.0011 | `logs/run-20261007-yt-brave.jsonl` |
| Open a short video link via `open_url` without `package` (system resolution) | OK → chooser `ResolverActivity` (multi-handler, expected) | ~12.8 s total | $0 | `logs/run-intent-20261007-130650.jsonl` |
| Resolve the same chooser with two taps (select handler + `Once`) | Chooser persists after first tap (`via: gesture` ×2); no default changed (honest, no 1-hop claim) | ~16.0 s | $0 | mismo jsonl (`A2_*`) |
| Open a search URL via `send_intent` `VIEW` (no `package`) | OK → browser foreground, results hint + query present | ~13.2 s + re-poll 18.5 s | $0 | mismo jsonl (`testB_*`, `B2_*`) |
| Open a short video link via `open_url` with `package` set (explicit component, 1 hop) | OK `{ok:true, verified:true, via:"startActivity-package", latency_ms:130.3}`, foreground directo, no chooser | ~0.13 s call | $0 | `docs/BUILD.md §9` (manual WS, sin jsonl) |
| Open a short video link with unknown `package` | Honesto `PACKAGE_NOT_FOUND` | ms | $0 | `docs/BUILD.md §9` |
| Open a short video link with installed `package` without handler | Honesto `INTENT_UNRESOLVED` | ms | $0 | `docs/BUILD.md §9` |

## 4. Techo de costo

Costo por corrida **<$0.003** en todas las filas con LLM (las de director
puro/intents son $0). Tarifas: Jev `$0.042` in / `$0.00` out por MTok
(normativo); S2 por env (placeholder ajustable). Cada paso loguea `[COST]`.

## 5. Cotidiano 2026-10-10 en A10 USB (solo lectura + 1 tap omitido por bloqueo)

Fuente: `logs/run-20261010-011841-cotidiano.jsonl` (15 pasos) + reintentos
YouTube en stdout (`open_url` ×3 OK, `read` 34 nodos, resolves S1 ×4
`envelope S1 no-JSON`). Banco 5002E Android 10 USB `e03638e5`, binario Go
por stdio, pantalla ON, forward `tcp:38472`. Sin commits, sin push,
sin descargas, sin crear alarma/mensaje.

| Tarea (genérica, EN) | Resultado | Tiempo | Costo | Forense |
|---|---|---|---|---|
| Open a video link via `open_url` with explicit client `package` (1 hop, no chooser) | OK ×3 (`via: startActivity-package`, 73–199 ms; foreground morphe `MainActivity` en reintentos; primer intento cayó a `systemui` transitorio) | ~0.07–0.20 s/call | $0 | `logs/run-20261010-011841-cotidiano.jsonl` (`youtube/open_url`) |
| Resolve Play/Pause or Share button via Jev S1 on the player screen (34 nodes) | **BLOQUEO honesto** (`envelope S1 no-JSON` ×5, 408–1354 ms; endpoint OpenRouter 200 vacío en debug sintético n=2/10/34) → **sin tap ciego, sin descarga** | n/a (Jev 0.4–1.4 s) | $0 afectable | mismo jsonl (`youtube/resolve_element` FAIL) |
| Open the messages app and resolve a field via Jev S1 (read-only, no create) | OK resolve (`idx 0 conf 0.86`, 415 ms) + persistencia por re-`read` (162 ms); **NO tap/type, NO crear alarma/mensaje** | ~6 s (`open_app` 5546 ms poll + reads) | ~$0.00004 (`[COST]` S1) | mismo jsonl (`fossify/*`) |
| Verify a clean open-source APK is installed via `list_packages` (no install/uninstall) | OK (130 pkgs; fossify 8, morphe 2, rvx 1, seal 0; 104–115 ms) | ms | $0 | mismo jsonl (`paquetes/*`) |
