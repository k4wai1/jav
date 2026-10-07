# fossify-random — 5 tareas humanas no-destructivas (temporal)

> Estado: **informe de run 2026-10-07, temporal**. Lo redacta `@coder` como
> forense del run; no es contrato. El contrato vigente sigue en
> `generic-dual-tier.md` + `director-client.md` v5. En conflicto, **AGENTS.md manda**.
>
> Contrato 100% genérico: las apps (`org.fossify.*`) aparecen solo como
> **valores runtime** de este run (tabla + jsonls), nunca como literales
> normativos de `src/`. Sin commits de este doc (temporal) ni push.

## 0. Pre-vuelo (env + forward + hello + pantalla)

- Env: `.env` presente (`chmod 600`). Valores nunca impresos; solo
  presencia (`has_jev_key=yes`, `has_jam_token=yes`). `OPENROUTER_MODEL=typesafe/jev-1.13`.
- Forward: `adb -s e03638e5 forward tcp:38472 tcp:38472` → `forward_ok`.
- Hello Jam: `scopes=['read','ui']`, `app=0.1.0` → `hello_ok`.
- Pantalla: `mWakefulness=Awake`, `Display Power: state=ON` (sin wake necesario).
  Batería 99–100%.
- Dispositivo: 5002E (Alcatel/TCL), Android 10 (SDK 29), `720×1440`,
  serial `e03638e5`, **SOLO USB**. Paquetes verificados por
  `pm list packages | grep fossify`: messages, clock, filemanager,
  keyboard, musicplayer, home, math, gallery (los 8) + `dev.jev.jam`.
- Régimen: **SOLO no-destructivo, SIN `--confirm`**. Ninguna tarea pidió
  confirmación crítica (`needs_confirm` no disparó). Sin `shell` (Fase 6,
  `METHOD_NOT_ALLOWED` vigente). Sin commits, sin push.

## 1. Modo director v5 aplicado

Por paso: `open_app(package)` → `read_screen_state()` (dump_ui +
normalizer + tabla `0..253` + `snapshot_id` + `first_result`) →
`resolve_element("<micro-intención EN de ESTA pantalla>")` (1 Choice +
NONE, ciego al goal) → `tap_idx` (`ACTION_CLICK` primero si clickable,
`dispatchGesture` fallback, reporta `via`) → `read` de verificación.
Excepciones documentadas abajo (pantalla volátil del reloj, confusión
`9`/`×` de Jev): misma resolución auditada, ejecución por texto
equivalente, sin inventar nodos. Forense por paso
(`decided_by=director`, `screen_goal` micro, `jev:{idx,conf}`,
`via`, `cost [COST]`) en cada jsonl.

## 2. Tabla tarea → resultado REAL → tiempo → costo → observaciones

| Tarea | Resultado REAL leído (snap) | Tiempo | [COST] Jev | Observaciones |
|---|---|---|---|---|
| (a) Galería: describir fotos/carpetas visibles | Carpetas: `Almacenamiento interno (18)`, `Seal (8)`, `Screenshots (7)`, `mix todo random (1)` (snap 242/602+, `18/47` nodos). Sin fotos individuales en raíz (vista de carpetas). | 2.3 s (final) / 2.4 s (v1) | 0.000000 (sin Jev: open+read, nada que tapear) | Solo lectura. Sin sustitución. |
| (b) Reloj: listar alarmas | Pestaña **Alarma**: `07:00 — Lun, Mar, Mié, Jue, Vie — Switch DESACTIVAR` + `09:00 — Dom, Sáb — Switch DESACTIVAR` (snap 604/605/668, `19/43`). Tabs: Reloj/Alarma/Cronómetro/Temporizador. Hora viva `22:4x`, fecha `mar., 6 oct.` | 5.7 s (final) | 0.000054 | v1 murió en `STALE_SNAPSHOT`: el reloj tickea cada segundo y el resolve (2.5 s) siempre expiraba antes del tap → bucle. Fix: misma resolución auditada (`Tap the Alarm tab` idx 9 conf 0.92) + ejecución `tap_text("Alarma")` (n_30, `via=gesture`) inmune a STALE. 2 artefactos de bucle (111/282 KB) eliminados del forense. |
| (c) Gestor: navegar a Download y listar | Dentro de `Download` (header `Almacenamiento interno › Download`): carpetas `exploit`, `Seal (9 elementos)` + APKs: `Brave Browser_1.84.130 (211.4 MB, 29-oct-2025)`, `youtube apkmirror 20.45.36 (170.6 MB, 28-abr-2026)`, `cx-file-explorer-2-6-1 (18.3 MB)`, `F-Droid (12.4 MB)`, `Island_6.4.2 (3.5 MB)`, `morphe-manager-1.15.0 (24.3 MB)`, `youtube-morphe-v20.47.62 (120.1 MB)`, `youtube-music-revanced-extended-v8.30.54 (63.4 MB)`, `youtube-revanced-extended-v20.05.46 (122 MB)`. Header declara **13 elementos**; tras scroll se observan 2 carpetas + 9 APKs nominales (2 no visibles en los dos snapshots, documentado). | 9.1 s (final) | 0.000133 | v1 `NO_TARGET` (micro `Tap the Download folder row` conf 0.59–0.60 < 0.70). Reformulación `Tap the text Download` → idx 29 (n_71) conf **0.94**. Primer tap (`via=gesture` sobre el label no-clickable) no navegó; re-lectura mostró que sí se entró a Download (latencia >0.8 s). Sin sustitución. |
| (d) Calculadora: 237×48 | **`237×48 = 11,376`** — expresión `237×48` (n_15), display `11,376` (n_16), snaps 650 y 708 (doble verificación independiente tras reset). | 15.5 s (final, incompleto en ×) + 2 verificaciones tap_text | 0.000311 (final) | Hallazgo: Jev confunde `9`/`×` sistemáticamente (`Tap the button labeled ×` → idx 9 `[n_28] 9` conf 0.65/0.60/0.80; `C` → `.` una vez). La guarda de etiqueta (`expect_contains`) evitó 3 taps erróneos (honesto `label_mismatch`, sin actuar). El final v5 queda en `display=237` (× sin resolver). El resultado **11,376** se verificó por vía equivalente documentada: reset (`close_app`+`open_app`, no-destructivo) + `tap_text` por botón (`C×3`, `2,3,7,×,4,8,=` todos `via=action_click`), snaps 642→650 y 700→708. Nota: `C` es backspace (3 pulsaciones para `0`), no clear-all. |
| (e) Reproductor: listar canciones (play 2 s aceptable) | Home: `112 Canciones`, `Todas las pistas` + tabs Listas/Carpetas/Artistas/Álbumes/Canciones (snap 653). En **Canciones** (snap 655/680, `40/82`): `02:21 / 03:55 / 02:29 / 00:00 / 03:36 / 02:54` + `86 - AVID Ending theme \| Fingerstyle Guitar Cover VeryNize (Very Nize • OTS)`, `86 Eighty Six ED2 - LilaS (Nekoconn • OTS)`, `[Animation] The Road Not Taken cover by Aether and Lumine CN VA - Genshin (Yxelixi • mix todo random)`, `[ENDING] Plastic Memories (DALEX LP • mix todo random)`, `Acheron & Black Swan Dance (Midnight City Music • OTS)`, `Again & Again - Plastic Memories OST…`. **Playback omitido**: list-only (no reproducir = menos efectos; documentado, permitido por el enunciado). | 5.6 s (final) / 11.1 s (v1 con permiso) | 0.000104 (final) | `open_app` inicial → `TIMEOUT` por diálogo de permiso (`permissioncontroller`: `¿Desea permitir que Reproductor de Música tenga acceso…?` + `PERMITIR/RECHAZAR`). Acto reversible no-destructivo: `resolve (Tap the ALLOW button)` + tap `PERMITIR`, documentado. Después `resolve (Tap the Songs row)` → idx 16 (n_47 `Canciones`) conf 0.85 + `tap_idx via=gesture`. Sin sustitución de app. |

**[COST] total final (5 jsonls v2): ≈ $0.000601** (`0 + 0.000054 + 0.000133 + 0.000311 + 0.000104`).
Suma v1 (exploración): ≈ $0.000584. Todas las líneas `[COST] provider=openrouter
model=typesafe/jev-1.13 … src=provider` están en stdout + `cost_usd` por paso
en cada jsonl (`CostTracker`). Sin `s2_cost` (S2 no disparó; todo intra-app
táctico). Sin key nunca hubo (stub no usado: key presente).

## 3. Forense (logs/)

Finales (v2, los que sostienen la tabla):

- `logs/run-fossify-gallery-1791341893.jsonl` (2.3 s, $0)
- `logs/run-fossify-clock-1791341904.jsonl` (5.7 s, $0.000054)
- `logs/run-fossify-files-1791341918.jsonl` (9.1 s, $0.000133, incluye scroll)
- `logs/run-fossify-calc-1791341959.jsonl` (15.5 s, $0.000311, × con `mismatch` honesto)
- `logs/run-fossify-music-1791341936.jsonl` (5.6 s, $0.000104)

Historial v1 (intentos, incluidos fallos honestos `STALE`/`NO_TARGET`/display
`237,948` por ×→9 sin guarda):

- `logs/run-fossify-gallery-1791340915.jsonl`
- `logs/run-fossify-clock-1791340918.jsonl`
- `logs/run-fossify-files-1791340924.jsonl`
- `logs/run-fossify-calc-1791340928.jsonl` (display erróneo `237,948` = `237948`, lección que motivó la guarda)
- `logs/run-fossify-music-1791340945.jsonl`

Evidencia de la calculadora correcta (vía equivalente `tap_text` tras reset,
doble snap 650/708 con `237×48`/`11,376`): stdout de las corridas manuales
+ `run-fossify-calc-1791341959.jsonl` (guarda que evitó el error). No se
inventa ningún valor: todo lo reportado salió de `read_screen_state`.

## 4. Sustituciones y desvíos (ninguna app sustituida)

Ninguna de las 5 apps se sustituyó. Desvíos de ejecución documentados (no de
alcance): (b) ejecución `tap_text` anti-`STALE` en reloj volátil; (c) doble
lectura por latencia de navegación; (d) reset `close+open` + `tap_text`
para `×`/`C` ante confusión Jev `9`/`×` (3 `mismatch` sin actuar); (e)
permiso `PERMITIR` (runtime media, reversible) + playback omitido (list-only).
Todo no-destructivo, sin `confirm:true`, sin `shell`, sin borrar/enviar/comprar.
