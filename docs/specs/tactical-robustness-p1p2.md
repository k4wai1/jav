# tactical-robustness P1+P2 — robustez táctica, cero tools nuevas (2026-10-10)

> Estado: **normativo**. Redacta `@architect`, implementa `@coder`,
> certifica `@judge`. En conflicto, **AGENTS.md manda**.
>
> Alcance: cinco contratos tácticos. P1 = invalidación espuria (ticker del
> sistema) y nodo no clickable. P2 = glifos confusables (capa adaptadora) y
> tolerancia a 1-stale.
>
> Hechos verificados sobre el código real (leídos, no inferidos):
>
> - Go, módulo `github.com/k4wai1/jav`.
>   - `pkg/normalizer/normalizer.go`: `Candidate` (~72-84) **no** tiene
>     `Package` (sí `ResourceID`); `SerializeTable` (~492-499) emite
>     `[idx, class_short, zone, flags, label]`; `ScreenFingerprint`
>     (~638-664) hashea `id + (Text o Desc)` ordenados, sin excluir
>     volátiles. `pkg/normalizer` importa solo stdlib.
>   - `pkg/jev/jev.go`: `AskDecision(...)` (~355-441) **copia** cada fila en
>     `serial` y compone `state["table"]`.
>   - `pkg/director/director.go`: `BuildResolveState(...)` (~31-53) pone
>     `serial` **por referencia** en `state["table"]`; `targetKeys` se
>     deriva de `r[0]`.
>   - Golden: `pkg/normalizer/replay_test.go` (`TestReplayPythonParity`)
>     exige que `SerializeTable` sea **byte-idéntico** a
>     `pkg/normalizer/testdata/replay_expected.json`.
>   - `ScreenFingerprint` no tiene consumidor en Go fuera del test
>     `normalizer_test.go:112`.
> - Kotlin `android-app/app/src/main/java/dev/jev/jam/`:
>   - `service/JevAccessibilityService.kt`: `onAccessibilityEvent` (~74-79)
>     marca `uiDirty = true` para cualquier evento; `requireFreshNode`
>     (~130-136) lanza `STALE_SNAPSHOT` si `snapshotId != lastSnapshotId ||
>     uiDirty`; `verifySame` (~175-180) compara `text` + `viewIdResourceName`
>     + `className`; `tapLiveNode` (~192-214) intenta `ACTION_CLICK` si
>     `isClickable` y, si no, gesto al centro (sin walk-up); el `finally`
>     fuerza `uiDirty = true`.
>   - `ui/UiTreeExtractor.kt`: abstracción `A11yNode` / `RealA11yNode`, base
>     del fake JVM `app/src/test/java/dev/jev/jam/ui/FakeA11yNode.kt`
>     (reciclaje observable).
> - Gobernanza: **exactamente 35 tools**, forzadas por
>   `pkg/tools/register.go` y `cmd/audit-mcp/main.go` (`make audit-mcp` =
>   11/11 PASS).

## 0. Invariantes y no-objetivos

Invariantes que este documento NO rompe (verificables):

1. **35 tools exactas.** Ningún contrato añade, renombra ni elimina una
   tool. `via` es un valor de `evidence`, nunca una propiedad del
   `inputSchema`.
2. **`SerializeTable` intacta.** El enriquecimiento de glifos (§4) vive en
   una **capa adaptadora** invocada por `pkg/jev` y `pkg/director` al
   componer la tabla que va al modelo, nunca dentro de `SerializeTable`.
3. **Sin literales de app.** El anti-ticker no nombra paquetes: la
   volatilidad se decide por **tipo de evento** (`TYPE_WINDOW_CONTENT_CHANGED`),
   no por origen. Esto se corrigió tras medir en banco (§1.5): el filtro por
   `com.android.systemui` no reproducía/arreglaba el fallo.
4. **Sin keys.**
5. **`AGENTS.md §§1–3` y `PROTOCOL.md` siguen vigentes.** El `STALE` lo
   sintetiza el cliente/director; Jam y el servidor no inventan códigos.

No-objetivos: sin runtime toggle para el anti-ticker; sin tools nuevas; sin
tocar el extractor de nodos ni la poda de decoración.

## 1. Contrato P1-a — Anti-ticker Kotlin

### 1.1 Diagnóstico

`onAccessibilityEvent` marca `uiDirty = true` para **todo** evento, incluidos
los `TYPE_WINDOW_CONTENT_CHANGED`. Ese tipo se emite de forma constante por
ruido cosmético del sistema **y de la propia app** (relojes, cronómetros,
cursores, animaciones). Cada emisión caduca el `snapshot_id` recién leído y
un `tap_node` falla `STALE_SNAPSHOT` aunque el nodo objetivo no se movió.

**Corrección sobre el diagnóstico inicial:** se supuso que el culpable era
solo el contenedor `com.android.systemui`. La medición en banco (§1.5) lo
refuta: en un reloj con segundos (Fossify Clock, su propia app) el `STALE`
persiste **con y sin** el filtro de SystemUI. La causa real es el
`TYPE_WINDOW_CONTENT_CHANGED` originado por la **app en foco**.

### 1.2 Firma y contrato

Helper puro (testeable en JVM, sin Robolectric): **ningún**
`TYPE_WINDOW_CONTENT_CHANGED` invalida el `snapshot_id`.

```kotlin
// Los TYPE_WINDOW_CONTENT_CHANGED son ruido cosmético (relojes, animaciones,
// cursores) del sistema Y de la propia app. No invalidan el snapshot por sí
// solos: la identidad real del nodo se valida en verifySame al actuar.
internal fun isVolatileEvent(eventType: Int?): Boolean =
    eventType == AccessibilityEvent.TYPE_WINDOW_CONTENT_CHANGED
```

`onAccessibilityEvent` pasa a:

```kotlin
override fun onAccessibilityEvent(event: AccessibilityEvent?) {
    if (event == null) {
        uiDirty = true
        return
    }
    if (!isVolatileEvent(event.eventType)) {
        uiDirty = true
    }
    if (event.eventType == AccessibilityEvent.TYPE_WINDOW_STATE_CHANGED) {
        event.className?.toString()?.let { lastActivity = it }
    }
}
```

| # | Regla |
|---|---|
| 1.1 | `TYPE_WINDOW_CONTENT_CHANGED` (de cualquier paquete) **no** invalida. Cualquier otro tipo → `uiDirty = true`. |
| 1.2 | `event == null` → `uiDirty = true`. |
| 1.3 | `lastActivity` solo se toca con `TYPE_WINDOW_STATE_CHANGED` (no volátil). |
| 1.4 | Los `finally { uiDirty = true }` de `tapLiveNode`/`typeNode`/`scrollBy` siguen intactos. |
| 1.5 | `dumpUiTree()` sigue acuñando `snapshot_id` y haciendo `uiDirty = false`. |
| 1.6 | Cero cambios en `requireFreshNode`; `verifySame` (text + resource_id + class) es la compuerta fina ante cambios reales. |

### 1.3 Trade-off asumido

Un cambio **real** que emita **solo** `TYPE_WINDOW_CONTENT_CHANGED` ya no
caduca el snapshot en la compuerta gruesa. Es aceptable porque:
(a) `verifySame` sigue lanzando `STALE_SNAPSHOT` si el nodo objetivo cambió
de texto/id/clase, que es la compuerta que de verdad protege la acción;
(b) el cambio era precisamente el que producía falsos `STALE` en pantallas
vivas; (c) reversión = reañadir la condición.

**Límite residual honesto:** otros tipos de evento que la app emite en
actualizaciones de contenido (p. ej. `TYPE_VIEW_TEXT_CHANGED` en un display
que cambia) **sí** siguen invalidando. Eso es correcto: el contenido cambió.
Si un caso concreto lo exige, se amplía la lista de tipos volátiles con
evidencia de banco; no se hace a ciegas.

### 1.4 Aceptación

- Test JVM `isVolatileEvent`:

| Entrada | Resultado |
|---|---|
| `TYPE_WINDOW_CONTENT_CHANGED` | volátil (no invalida) |
| `TYPE_WINDOW_STATE_CHANGED` | no volátil (invalida) |
| `TYPE_VIEW_CLICKED` | no volátil (invalida) |
| `null` | no volátil (invalida) |

### 1.5 Evidencia en banco (A10 `e03638e5`, Android 10, 2026-10-10)

APK debug reconstruido con el fix e instalado; accesibilidad activa; sonda
WS (`hello` → `dump_ui` → esperar 3.5 s → `type_text` sobre nodo no
enfocado) sobre el cliente `pkg/jam`. `NOT_FOCUSED` = snapshot fresco;
`STALE_SNAPSHOT` = caducado.

| Build | Pantalla | Muestras | Fresco | STALE |
|---|---|---|---|---|
| sin fix (ticker SystemUI) | Jam MainActivity (estática) | 3 | 3 | 0 |
| sin fix | Fossify Clock (viva) | 3 | 0 | **3** |
| fix SystemUI-only | Fossify Clock (viva) | 3 | 0 | **3** |
| **fix content-changed** | Fossify Clock (viva) | 3 | **3** | 0 |
| fix content-changed | Fossify Clock + `press_back` | 1 | 0 | 1 (control) |

Conclusiones: (1) el reloj de la barra de estado (avanza por minuto) no
reproduce el fallo; (2) el reloj con segundos de la app sí, y el filtro
SystemUI-only **no** lo arregla; (3) ignorar `TYPE_WINDOW_CONTENT_CHANGED`
lo arregla y el control de cambio real sigue caducando.

## 2. Contrato P1-b — Anti-ticker Go

### 2.1 Diagnóstico

`ScreenFingerprint` hashea el texto de todos los candidatos. Un reloj que
avanza o un porcentaje que cambia altera el hash y `BuildRunSignature` lo lee
como "sin progreso".

### 2.2 Firma y contrato

En `pkg/normalizer/normalizer.go`:

```go
var volatileTextRe = regexp.MustCompile(`^(\d{1,2}:\d{2}(:\d{2})?|\d{1,3}\s*%)$`)

// isVolatileNode true → el candidato NO entra en la firma de pantalla.
func isVolatileNode(c Candidate) bool {
    eff := c.Text
    if eff == "" {
        eff = c.Desc
    }
    t := strings.TrimSpace(eff)
    return t != "" && volatileTextRe.MatchString(t)
}
```

`ScreenFingerprint` cambia solo en el filtrado: omite `isVolatileNode`, y si
tras filtrar no queda ningún par devuelve `""` (para no confundir "sin dato"
con "estancado", dado que `BuildRunSignature` usa `fpFirst != ""`).

| # | Regla |
|---|---|
| 2.1 | La cadena efectiva es `Text`, y `Desc` solo si `Text` vacío (igual que hoy). |
| 2.2 | `TrimSpace` solo para el cotejo; al hash entra el texto sin recortar. |
| 2.3 | Regex `^(\d{1,2}:\d{2}(:\d{2})?|\d{1,3}\s*%)$`. Sin literal de app: el filtro es por **forma** del texto (cubre tickers de cualquier app). |
| 2.4 | Lista solo volátil → `""`. |
| 2.5 | `isVolatileNode` no exportada (test interno). |
| 2.6 | Los nodos de decoración de sistema (sin texto) no llegan siquiera a `Candidate` (los poda `keep`/`DecorSubstr`); no hace falta un check por `ResourceID`. |
| 2.7 | `SerializeTable` no se toca; los volátiles siguen en la tabla del modelo. |

### 2.3 Aceptación

- `TestFingerprintIgnoresVolatile`: misma lista con `9:40` vs `9:41` y con
  un reloj en `Desc` → mismo hash.
- `TestFingerprintEmptyWhenAllVolatile`: lista solo volátil → `""`.
- No-regresión: lista estable + volátil == lista sin el volátil.
- `TestFingerprintStable` y `TestReplayPythonParity` siguen verdes.

## 3. Contrato P1-c — Walk-up clickable

### 3.1 Diagnóstico

`tapLiveNode` hace `ACTION_CLICK` solo si el nodo vivo es `isClickable`. En
muchas apps el clickable es el ancestro (el hijo es un `TextView`/`ViewGroup`
decorativo); el fallback actual es un gesto al centro del hijo, que algunas
apps filtran o interpretan como scroll.

### 3.2 Comportamiento

En `tapLiveNode`, **después** de que `ACTION_CLICK` sobre el propio nodo falle
y **antes** del gesto:

1. Ascender con `getParent()` hasta **3 niveles**.
2. Primer ancestro `isClickable && isVisibleToUser` con
   `performAction(ACTION_CLICK) == true` → `TapResult(node.id, "click_ancestor")`.
3. Si ninguno → camino gestual actual sin cambios (`via = "gesture"`).
4. `verifySame(live, node)` se ejecuta **antes** de todo, igual que hoy.
5. Reciclar todo nodo obtenido por `getParent()`, también en la ruta de éxito.

### 3.3 Sellado para test JVM

Añadir `fun parent(): A11yNode?` a `A11yNode`; `RealA11yNode` →
`info.getParent()?.let(::RealA11yNode)`; `FakeA11yNode` gana un parámetro
`parent: FakeA11yNode?`. Nuevo helper puro:

```kotlin
object ClickAncestor {
    const val MAX_HOPS = 3
    /** Primer ancestro clickable y visible a <= maxHops. Recicla todo lo
     *  obtenido salvo lo devuelto. */
    fun find(node: A11yNode?, maxHops: Int = MAX_HOPS): A11yNode?
}
```

`tapLiveNode` lo invoca con `ClickAncestor.find(RealA11yNode(live))`; el
envoltorio raíz es prestado (no se recicla en el helper).

### 3.4 Aceptación

- `TestWalkUpClickable`: 1–3 niveles → `click_ancestor`; 4 niveles → gesto;
  ancestro invisible/`performAction=false` → se ignora.
- `TestWalkUpRecycles`: tras `find()` todo nodo obtenido tiene
  `recycled == true` salvo el devuelto; con `null`, todos reciclados.
- `via = "click_ancestor"` es aditivo (PROTOCOL §4 no enumera valores).

## 4. Contrato P2-a — Glifos confusables (capa adaptadora)

### 4.1 Firma

Paquete `normalizer`, pública, pura:

```go
func FormatCandidateLabel(text string) string
```

Roles:

```go
var confusableRoles = map[string]string{
    "9": "digit nine",
    "×": "multiplication sign",
    "+": "plus sign",
    "-": "minus sign",
    "C": "clear",
    ".": "decimal point",
}
```

| # | Regla |
|---|---|
| 4.1 | Se decide sobre `TrimSpace(text)`; si `utf8.RuneCountInString != 1`, devolver `text` tal cual. |
| 4.2 | Si es 1 runa y está en el mapa → `TrimSpace(text) + " [" + role + "]"`. |
| 4.3 | Clave exacta: `C` mayúscula sí, `c` no; `×` U+00D7 sí, `x` no. |
| 4.4 | Determinista, sin env/time. |
| 4.5 | Etiquetas de 2+ runas intactas. |

### 4.2 Punto de aplicación (capa adaptadora)

**`SerializeTable` no se toca.** Aplicar al componer la tabla del modelo:

- `pkg/jev/jev.go` `AskDecision`: dentro del bucle que ya copia cada fila,
  transformar `cp[4]` si es string.
- `pkg/director/director.go` `BuildResolveState`: **copiar** `serial` a una
  tabla nueva (hoy entra por referencia), transformar `[4]`, y usar la copia
  en `state["table"]`. `targetKeys` sigue derivándose de `r[0]` → los índices
  no se renumeran.

### 4.3 Aceptación

- Test de los 12 casos (`"9"`→`9 [digit nine]`, `" 9 "`→`9 [digit nine]`,
  `"99"`/`"+1"`/`"c"`/`""`→identidad).
- `TestReplayPythonParity` verde; `git diff` no toca `SerializeTable`.
- `pkg/director`: la fila de entrada queda intacta y
  `state["table"][0][4] == "9 [digit nine]"`.
- `pkg/jev`: `AskDecision` no muta la tabla recibida y `criteria` conserva la
  clave `"0"`.

## 5. Contrato P2-b — Tolerancia a 1-stale (solo diseño)

Sin tarea de implementación; el cliente/director lo cumple con las tools
actuales.

- **Identidad de destino** = `(text exacto, resource_id exacto, bounds exacto)`.
- Misma identidad + `snapshot_id` distinto → re-leer, re-localizar por
  identidad y reintentar **una vez** (no se vuelve a consultar a S1).
- Identidad distinta → paso nuevo (vuelve al decisor con tabla fresca).
- Segundo `STALE_SNAPSHOT` con la misma identidad → `UI_UNSTABLE` + firma de
  corrida (`BuildRunSignature`) + forense JSONL.
- No añade ninguna tool; la política vive en el cliente/director.

Nota: se adopta **1 reintento** (lectura del bloque `instructions` normativo
§1 de `MCP_SPEC_GUIDELINES.md`). Existe una discrepancia preexistente con la
fila `UI_UNSTABLE` de §3.2 (`STALE×3`) que el orquestador debe alinear por
enmienda; no se corrige aquí.

## 6. Aceptación consolidada (`@judge`)

| # | Comprobación | Resultado exigido |
|---|---|---|
| A1 | `make audit-mcp` | 11/11 PASS, `tools-count-35` verde |
| A2 | `go test ./...` | verde, incluido `TestReplayPythonParity` |
| A3 | `git diff -- pkg/normalizer/normalizer.go` | `SerializeTable` sin cambios |
| A4 | `git diff -- pkg/tools/register.go cmd/audit-mcp` | vacío |
| A5 | Tests JVM nuevos (P1-a, P1-c) + Go (P1-b, P2-a) | verdes |
| A6 | `grep -rn 'su -c\|exec(.*su\|ProcessBuilder(.*su' android-app/` | vacío |

## 7. Riesgos y reversión

| Riesgo | Reversión |
|---|---|
| Supresión SystemUI oculta un cambio real | retirar la condición en `onAccessibilityEvent` |
| Fingerprint ciego a reloj/batería | revertir el `continue` |
| Walk-up toca ancestro con otros bounds | `MAX_HOPS = 0` degrada a gesto |
| Sufijo de rol altera calibración S1 | quitar la llamada en la capa adaptadora |
| Copia divergente en `BuildResolveState` | test de §4.3 lo detecta |

Enmiendas propuestas para el orquestador (no aplicadas aquí): documentar
`via = "click_ancestor"` en `PROTOCOL.md §4`; alinear `MCP_SPEC_GUIDELINES.md`
§3.2 con §1 en el conteo de `STALE`; corregir las citas a `wait_for_node`
(no existe; la tool es `wait_for_text`).
