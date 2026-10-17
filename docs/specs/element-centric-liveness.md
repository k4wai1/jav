# Spec — Element-Centric Liveness (v1.2.4)

> Estado: **vigente** (implementado en v1.2.4).
> Origen: sesión de usuario real (2026-10-16/17): YouTube (video que refresca
> cada segundo) → copiar link → enviar a "Rupa" por WhatsApp → uso de apps.
> El agente sufrió `STALE_SNAPSHOT` en bucle pese a que el botón objetivo
> seguía intacto en pantalla.
>
> Enmienda parcial de `tactical-robustness-p1p2.md §10` (contrato P6):
> **deroga** la regla "Prohibido tocar `requireFreshNode`" (§10.1b.8) y el
> caso (c) de la tabla de tests §10.1c.

## 1. Problema observado

1. **Bloqueo global antes de mirar el elemento.**
   `requireFreshNode` abortaba con `STALE_SNAPSHOT` si
   `snapshotId != lastSnapshotId || uiDirty` **antes** de llegar a
   `reanchorOrThrow(expected)`. Cualquier evento no volátil (toast, banner,
   teclado, `TYPE_WINDOW_STATE_CHANGED`) o cualquier `dump` intermedio
   invalidaba todo, aunque el nodo objetivo no hubiera cambiado.
2. **Lecturas internas que consumían el snapshot del agente.**
   `get_foreground()` llamaba a `dumpUiTree()` (recorrido de hasta 500 nodos)
   y acuñaba un `snapshot_id` nuevo: el snapshot que el agente acababa de
   leer moría por una lectura ajena (`get_foreground` / `resolve_element`).
3. **Ceguera ante contactos que solo viven en la app.**
   Un chat fijado ("Rupa", bot de WhatsApp) no está en la agenda de Android:
   `list_contacts` → 0 matches y el agente se bloqueaba en vez de abrir la
   app de mensajería y mirar la lista/buscador.

## 2. Contrato

### C1 — `snapshotRing` de 8 en `JevAccessibilityService`

- `private val snapshotHistory = ArrayDeque<UiSnapshot>()` sincronizado
  (`historyLock`), con tope `MAX_SNAPSHOT_HISTORY = 8`.
- `dumpUiTree()` **siempre** registra el snapshot recién creado (raíz nula
  incluida: snapshot vacío). Se eliminan `lastSnapshotId` / `lastNodes`.
- `uiDirty` se conserva como señal de diagnóstico (se sigue marcando y
  limpiando), pero **ya no es compuerta de acción**.

### C2 — `requireFreshNode(nodeId, snapshotId): Pair<UiSnapshot, UiNode>`

- Busca el snapshot en `snapshotHistory` por `snapshotId`, **ignorando**
  `uiDirty` y la existencia de dumps posteriores.
- Fuera de la ventana de 8 → `JamError("snapshot_id fuera de la ventana de
  los últimos 8 snapshots; re-haz read_screen", "STALE_SNAPSHOT")`.
- `nodeId` ausente en ese snapshot → `JamError("nodo fuera del snapshot",
  "STALE_SNAPSHOT")`.

### C3 — Compuerta de paquete en `reanchorOrThrow(snap, expected)`

- Si `snap.packageName.isNotEmpty()` y
  `rootInActiveWindow.packageName != snap.packageName` →
  `JamError("la app en primer plano cambió de <viejo> a <nuevo>; vuelve a
  abrir <viejo> o haz read_screen", "STALE_SNAPSHOT")` y `root.recycle()`.
- Anti-espejo-Termux: jamás se tapea sobre una app distinta a la del snapshot.
- `root == null` → `SELECTOR_NOT_FOUND ("sin ventana activa")`.

### C4 — `LiveNodeReanchor`: drift 120 + match único con ancla

- `MAX_DRIFT_PX: 24 → 120` (banner/teclado/animación desplazan el botón).
- Pasos (sobre el árbol vivo, BFS ≤500 nodos):
  1. Índice BFS exacto + identidad completa (`text`, `resource_id`, `class`,
     `content_desc`) → `EXACT`.
  2. Match de identidad con centroide Chebyshev ≤ `maxDriftPx`:
     exactamente 1 → `REANCHORED`; >1 → `AMBIGUOUS`.
  3. **Nuevo**: 0 candidatos por drift y **exactamente 1** match de identidad
     visible en toda la ventana con **al menos un ancla no vacía**
     (`text` | `content_desc` | `resource_id`) → `REANCHORED`.
     0 matches → `NOT_FOUND`; >1 matches → `AMBIGUOUS`.
- Sin ancla no hay paso 3 (un match solo-`class` es `NOT_FOUND`).
- `AMBIGUOUS`/`NOT_FOUND` → `STALE_SNAPSHOT`; `NO_WINDOW` →
  `SELECTOR_NOT_FOUND` (sin cambios).

### C5 — `getForeground()` O(1)

- Lee `rootInActiveWindow?.packageName` con `recycle()` en `finally`.
- **No** llamá a `dumpUiTree()`: no recorre el árbol ni acuña
  `snapshot_id`. `activity` sigue siendo el último `TYPE_WINDOW_STATE_CHANGED`.

### C6 — `instructions` MCP: regla CONTACTS

- Bloque `CONTACTS` en `cmd/jav/main.go` (≤220 palabras totales, requisito
  `audit-mcp`): si `list_contacts` devuelve 0 matches, **no** detenerse: abrir
  la app de mensajería y buscar el chat en la lista visible o el buscador
  (muchos chats/bots no están en los contactos del sistema).

## 3. Restricciones

| # | Regla |
|---|---|
| R1 | Contrato externo WS sin cambios de método/schema; solo semántica de frescura y errores. `tools-count-38` intacto |
| R2 | `STALE_SNAPSHOT` conserva núcleo verbatim del hint (`spec_test.go`) |
| R3 | `audit-mcp` 12/12 PASS; instructions ≤220 palabras y tokens obligatorios intactos |
| R4 | Prohibido `su`; read-only para el usuario; sin dependencias nuevas |
| R5 | Flag anti-ticker (`isVolatileEvent`) intacto |

## 4. Aceptación

| # | Comprobación | Resultado exigido |
|---|---|---|
| A1 | `LiveNodeReanchorTest` | drift 200 px con identidad única → `REANCHORED`; 2 idénticos lejos → `AMBIGUOUS`; ausente → `NOT_FOUND`; sin ancla → `NOT_FOUND`; drift ≤120 → `REANCHORED` |
| A2 | `./gradlew :app:testDebugUnitTest` | 100 % verde |
| A3 | `go test ./...` (excepto `pkg/normalizer` preexistente) | verde |
| A4 | `go run ./cmd/audit-mcp --bin dist/jav-linux-amd64` | 12/12 PASS |
| A5 | Prueba en dispositivo (v1.2.4) | `tap_node` con snapshot de hace ≤8 dumps procede si el elemento vive; cambio de app → `STALE_SNAPSHOT` con hint de paquete |

## 5. Riesgos y reversión

| # | Riesgo | Reversión |
|---|---|---|
| R1 | Paso 3 toca un elemento homónimo único en otra zona (falso positivo) | bajar `MAX_DRIFT_PX` o exigir `resource_id` en `hasAnchor` |
| R2 | Ventana de 8 snapshots demasiado corta en ráfagas largas | subir `MAX_SNAPSHOT_HISTORY` (constante única) |
| R3 | `getForeground` O(1) pierde el efecto lateral de limpiar `uiDirty` | re-marcar `uiDirty = false` explícito o volver a `dumpUiTree()` |
