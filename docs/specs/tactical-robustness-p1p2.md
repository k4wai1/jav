# tactical-robustness P1+P2 — robustez táctica, cero tools nuevas (2026-10-10)

> Estado: **normativo**. Redacta `@architect`, implementa `@coder`,
> certifica `@judge`. En conflicto, **AGENTS.md manda**.
>
> Alcance: ocho contratos tácticos. P1 = invalidación espuria (ticker del
> sistema) y nodo no clickable. P2 = glifos confusables (capa adaptadora) y
> tolerancia a 1-stale. **P3 (§8) = resiliencia S1: saneamiento Unicode de
> la etiqueta que va al modelo, retry ante envelope 2xx vacío/truncado, y
> `top_candidates` en el Fallback Soberano.**
>
> P3 es **aditivo y de capa interna**: no toca `pkg/tools/`, no añade ni
> renombra campos en ningún `inputSchema`, no registra tools nuevas y no
> altera los strings forenses `envelope S1 no-JSON`, `red S1 http %d` ni
> `red S1 falló tras retry`.
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
>   - `pkg/jev/jev.go`: `postJSON` (256-290) reintenta **solo** ante
>     `http.DefaultClient.Do` err (273); un 2xx con body vacío cae en
>     `decErr != nil` → `return` inmediato (284-286). `Endpoint` (22) es
>     `const` y su único uso es la línea 262. `cancel()` (272) se invoca
>     **antes** de leer el body (279). `Answer` (76-82) no lleva
>     distribución; `normAnswer` (218-254) conserva solo `probs[key]`
>     aunque `ValidateChoice` (138-216) devuelve el mapa completo
>     `map[string]float64` ya validado (alloc en 185). `AskDecision`
>     (357-368) copia la fila y aplica `FormatCandidateLabel` a `cp[4]`.
>   - `pkg/director/director.go`: `SovereignFallback` (123-129) devuelve
>     EXACTAMENTE `{ok:false, idx:nil, fallback_required:true, reason,
>     recovery_instruction, snapshot_id}`. La rama `NONE` (180-182)
>     retorna **antes** de registrar coste y sin `conf`; `LOW_CONF`
>     (191-201) añade `conf`, `cost_usd`, `usage`. El `toFloat` de
>     director (90-102) **no** contempla `json.Number` a diferencia del
>     de `pkg/jev` (118-133). `normalizer.MaxTable = 254`
>     (`normalizer.go:20`) ⇒ índices válidos `0..253`.
>     `ResolveElement` **no** está registrada como tool MCP (0
>     ocurrencias en `pkg/tools/`): `top_candidates` es campo de payload
>     de librería, nunca de `inputSchema`.
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

## 8. Contrato P3 — Resiliencia S1 (sanitización + retry + top_candidates)

Aditivo, sin tools nuevas, sin campos nuevos en ningún `inputSchema`.
`ResolveElement` no está registrada como tool MCP hoy (0 ocurrencias en
`pkg/tools/`), así que las tres piezas viven enteras en la capa de librería.

### 8.0 Diagnóstico (evidencia medida, no inferida)

| Fuente | Hecho |
|---|---|
| `logs/run-20261010-011841-cotidiano.jsonl:11` | `{"phase":"youtube","tool":"resolve_element","ok":false,"code":"TRANSPORT:envelope S1 no-JSON","lat_ms":1354.22}` |
| `docs/benchmarks/TASK_HISTORY.md:68` | endpoint OpenRouter **200 con body vacío ×5**, 34 nodos → BLOQUEO honesto, sin tap ciego |
| `docs/benchmarks/PERFORMANCE.md:86` | `408–1354 ms` por resolución fallida |
| `pkg/jev/jev.go:256-290` | `postJSON` reintenta **solo** ante error de transporte (273). Un 2xx con body vacío cae en `decErr != nil` → `return` **inmediato** (284-286) |
| `pkg/jev/jev.go:272` vs `:279` | `cancel()` se ejecuta **antes** de leer el body: el propio cliente puede truncar la respuesta |
| `pkg/director/director.go:123-129` | el Fallback Soberano no dice **qué** candidatos eran plausibles; solo "examina candidates/render" |

Tres huecos, tres contratos: **8.1** saneamiento de la etiqueta que ve el
modelo, **8.2** retry donde hoy no lo hay, **8.3** `top_candidates`.

### 8.1 Contrato P3-a — Saneamiento Unicode (capa adaptadora)

Helper **exportado y puro** en `pkg/normalizer`, junto a
`FormatCandidateLabel`, reutilizable por `pkg/jev` y `pkg/director` sin
duplicar la lógica. **Nunca** dentro del serializador canónico.

```go
// SanitizeMaxRunes tope de la etiqueta que va al modelo (runas, no bytes).
const SanitizeMaxRunes = 80

// SanitizeModelLabel capa adaptadora de saneamiento para la etiqueta que
// ve el modelo: elimina ruido de transporte (control chars, zero-width),
// colapsa espacios y acota longitud. NO la usa SerializeTable (paridad
// golden), ni BuildTable/Row.Label, ni TapIdx/by_idx, ni el forense.
func SanitizeModelLabel(text string) string
```

Forma canónica (la semántica es vinculante; el estilo es del `@coder`):

```go
func SanitizeModelLabel(text string) string {
	var b strings.Builder
	b.Grow(len(text))
	for _, r := range text {
		switch {
		case r < 0x20: // (a) C0: \n \r \t y resto
			continue
		case r >= 0x200b && r <= 0x200f: // (b) ZWSP/ZWJ/ZWNJ/BOM/LRM/RLM
			continue
		default:
			b.WriteRune(r)
		}
	}
	return truncateRunes(collapseU0020(b.String()), SanitizeMaxRunes)
}
```

`collapseU0020` colapsa **solo** U+0020 y recorta extremos; `truncateRunes`
corta duro en `SanitizeMaxRunes` runas. Helpers locales al paquete
(`collapseU0020`, `truncateRunes`), no exportados.

| # | Regla |
|---|---|
| 8.1.1 | Pura: sin env, sin reloj, sin I/O, sin `rand`. Misma entrada → misma salida, siempre. |
| 8.1.2 | **(a)** Eliminar (no sustituir) toda runa `r < 0x20`, incluidos `\n`, `\r`, `\t`. Consecuencia especificada: `"a\nb"` → `"ab"` (fusión de tokens). **Aceptado y testeado**: el label viene de un único nodo y un `\n` interior es ruido de `content_desc`; la identidad del nodo la decide `resource_id`/`bounds`, no el label (§2.1). Reversión en R1. |
| 8.1.3 | **(b)** Eliminar el rango cerrado `\u200b..\u200f` (ZWSP, ZWJ, ZWNJ, BOM, LRM, RLM). |
| 8.1.4 | **(c)** Colapsar cada racha de **U+0020** a un único espacio y recortar espacios en los extremos. **Prohibido usar `strings.Fields`**: parte por `unicode.IsSpace` y se comería U+00A0/U+2009/U+3000, que deben sobrevivir intactos. Determinismo byte a byte. |
| 8.1.5 | **(d)** Corte duro a **80 runas** (`utf8.RuneCountInString`), nunca bytes. Sin elipsis ni marcador: una runa 81 sería un glifo nuevo en el label y perturbaría la calibración de S1. El corte va **después** de (a)(b)(c). |
| 8.1.6 | El tope de 80 aplica **solo** a la salida de `SanitizeModelLabel`. El sufijo de rol de `FormatCandidateLabel` se añade **después** y puede exceder 80 (`"9"` → `"9 [digit nine]"`). `SanitizeModelLabel` no sabe que `FormatCandidateLabel` existe. |
| 8.1.7 | **Sin normalización Unicode**: nada de NFC/NFKC, ni case-folding, ni mapeo confusable→ASCII. Motivo concreto: NFKC colapsaría U+00D7 → `x` y rompería la regla exacta 4.3 de P2-a (`×` sí, `x` no). Ese trabajo ya lo hace el sufijo de rol. |
| 8.1.8 | `""`, `"9"`, `"×"`, `"OK"` salen intactos (aceptación vigente). |
| 8.1.9 | Si `cp[4]` no es `string`, no se toca (guarda vigente `len(cp) > 4` + aserción de tipo). |
| 8.1.10 | No añade imports a `pkg/normalizer`: `strings` y `unicode/utf8` ya están por `FormatCandidateLabel`. |

**Punto de aplicación: exactamente dos call sites, orden Sanitize → Format.**

```go
cp[4] = normalizer.FormatCandidateLabel(normalizer.SanitizeModelLabel(s))
```

1. `pkg/jev/jev.go` `AskDecision` (~362-366), dentro del bucle que ya copia
   cada fila.
2. `pkg/director/director.go` `BuildResolveState` (~47-51), sobre la copia.

| # | Regla |
|---|---|
| 8.1.11 | En ambos call sites el resultado es el **mismo one-liner**. `cp` ya es copia fresca en los dos ⇒ la tabla de entrada nunca se muta (tests vigentes siguen verdes sin tocarlos). |
| 8.1.12 | **NO se aplica** a `SerializeTable`, `BuildTable`, `Row.Label`, `TapIdx`/`by_idx`, al snapshot ni al JSONL de forense, ni a nada devuelto al cliente MCP. El modelo ve la etiqueta saneada; el cliente conserva la cruda para re-localizar por índice. Sanear la ruta de `TapIdx` podría romper la re-localización silenciosamente. |

**Aceptación 8.1** — `TestSanitizeModelLabel` (12 casos, todos obligatorios):

| # | Entrada | Salida |
|---|---|---|
| 1 | `""` | `""` |
| 2 | `"OK"` | `"OK"` |
| 3 | `"a\nb"` | `"ab"` |
| 4 | `"a\r\nb"` | `"ab"` |
| 5 | `"a\tb"` | `"ab"` |
| 6 | `"a\u200bb"` | `"ab"` |
| 7 | `"a\u200e b"` | `"a b"` (zero-width fuera, espacio colapsado) |
| 8 | `"a   b"` | `"a b"` |
| 9 | `"9  "` | `"9"` |
| 10 | 100×`"a"` | 80 runas de `"a"` |
| 11 | 40×`"€"` | 80 runas (240 bytes) intactos — cuenta runas, no bytes |
| 12 | `"a\u00a0\u00a0b"` | `"a\u00a0\u00a0b"` (NBSP **no** se colapsa: prueba de 8.1.4) |

Más los compuestos:

- `TestBuildResolveStateEnrichesLabelsZeroWidth`: `serial = {{0,…,"\u200b9"}}`
  → `state["table"].([]jev.SerialRow)[0][4] == "9 [digit nine]"` **y**
  `serial[0][4] == "\u200b9"` (entrada intacta). Es el caso de mayor valor:
  hoy el zero-width impide el enriquecimiento (2 runas, no 1).
- `TestAskDecisionSanitizesNoMutate`: `table[0][4] = "×\n"` → sin error y
  `table[0][4]` sigue siendo `"×\n"`.
- `TestBuildResolveStateEnrichesLabels` y `TestAskDecisionDoesNotMutateTable`
  se quedan **sin modificar**.

### 8.2 Contrato P3-b — Retry de envelope vacío (`pkg/jev`)

Estado actual: el bucle `for attempt := 0; attempt < 2; attempt++` solo
`continue` en el error de `Do` (273). El `return` de 284-286 mata el reintento
justo en el caso medido.

**Decisión vinculante — endpoint inyectable: `var endpointURL = Endpoint`.**

Opción elegida: una **var de paquete no exportada** inicializada a la `const`
`Endpoint`, que el test sustituye por la URL de `httptest.NewServer`.

- `Endpoint` (22) **no cambia**: sigue siendo `const` exportada, todo
  consumidor externo sigue compilando. Verificado: su único uso es la 262.
- Se **descarta** un setter exportado (`SetEndpoint`): añade superficie de API
  pública para una necesidad de test.
- Se **descarta** una env var (`JEV_ENDPOINT`): abriría una **segunda vía de
  redirección del tráfico S1**. AGENTS §2/§3 tratan la ruta a Shizuku/red como
  superficie sensible; el endpoint de S1 es fijo por contrato. Inyectable y
  no exportado significa que **solo los tests del paquete pueden tocarlo**.
- `postJSON` sigue sin llamar a `checkModelID` ni a `IsMock`: los tests la
  invocan en-package sin tocar `JEV_MODEL`.

```go
const Endpoint = "https://openrouter.ai/api/alpha/decisions" // sin cambios

// endpointURL override inyectable SOLO para tests (httptest).
// No hay env var: S1 solo puede ir al endpoint declarado (AGENTS §2/§3).
var endpointURL = Endpoint

const maxAttempts = 2 // 1 original + 1 retry

// envelopeEmptyMsg string forense CONGELADO: sobrevive en
// logs/*.jsonl como "TRANSPORT:envelope S1 no-JSON" y en los greps de
// diagnóstico. NO reescribir ni reenvolver.
const envelopeEmptyMsg = "envelope S1 no-JSON"

func postJSON(payload map[string]any) (map[string]any, error) {
	key := os.Getenv("OPENROUTER_API_KEY")
	var last error
	for attempt := 0; attempt < maxAttempts; attempt++ {
		ctx, cancel := context.WithTimeout(context.Background(), Timeout)
		body, _ := json.Marshal(payload)
		req, err := http.NewRequestWithContext(ctx, http.MethodPost, endpointURL, bytes.NewReader(body))
		if err != nil {
			cancel()
			return nil, err
		}
		req.Header.Set("Authorization", "Bearer "+key)
		req.Header.Set("Content-Type", "application/json")
		req.Header.Set("HTTP-Referer", "https://github.com/jev-android-mcp")
		req.Header.Set("X-Title", "jam-loop")
		resp, err := http.DefaultClient.Do(req)
		if err != nil {
			cancel()
			last = err
			sleepBeforeRetry(attempt)
			continue
		}
		var data map[string]any
		decErr := json.NewDecoder(resp.Body).Decode(&data)
		_ = resp.Body.Close()
		cancel() // R4: el body ya está leído; cancelar aquí no lo trunca
		// El status decide ANTES que el decode: un 4xx/5xx con body vacío
		// es "red S1 http N", no un envelope vacío, y NO se reintenta.
		if resp.StatusCode < 200 || resp.StatusCode >= 300 {
			return nil, &JevError{Msg: fmt.Sprintf("red S1 http %d", resp.StatusCode)}
		}
		// Envelope vacío = decode fallido, "null" o "{}" (data == nil / len 0).
		if decErr != nil || len(data) == 0 {
			last = &JevError{Msg: envelopeEmptyMsg}
			sleepBeforeRetry(attempt)
			continue
		}
		return data, nil
	}
	// El último fallo manda: conserva el string EXACTO del envelope vacío.
	if je, ok := last.(*JevError); ok && je.Msg == envelopeEmptyMsg {
		return nil, &JevError{Msg: envelopeEmptyMsg}
	}
	return nil, &JevError{Msg: fmt.Sprintf("red S1 falló tras retry: %v", last)}
}

// sleepBeforeRetry duerme solo entre intentos; el último no duerme.
func sleepBeforeRetry(attempt int) {
	if attempt < maxAttempts-1 {
		time.Sleep(500 * time.Millisecond)
	}
}
```

| # | Regla |
|---|---|
| 8.2.1 | Se reintenta, además del error de transporte, el caso **2xx con envelope vacío**: `decErr != nil` **O** `data == nil` **O** `len(data) == 0` (cubre body vacío, whitespace, `null` y `{}`). Los cuatro son reintentables con el mismo `sleep` de 500 ms. |
| 8.2.2 | **2 intentos máximos por request.** `maxAttempts = 2`. El último intento no duerme. Peor caso acotado: 500 ms + 2×`Timeout` ≈ 6.5 s. |
| 8.2.3 | Un no-2xx sigue siendo **error inmediato, sin reintento**, con su mensaje `red S1 http %d`. El status se evalúa **antes** que el decode, como hoy. |
| 8.2.4 | Al agotar intentos por envelope vacío/truncado, el error devuelto tiene el mensaje **exacto** `envelope S1 no-JSON` (no envuelto en `red S1 falló tras retry: %v`), para que el código forense `TRANSPORT:envelope S1 no-JSON` de `logs/*.jsonl` siga siendo reproducible byte a byte. El agotamiento por **transporte** conserva `red S1 falló tras retry: %v`. |
| 8.2.5 | `cancel()` se mueve a **después** de leer y cerrar el body (y se llama explícitamente en las dos ramas tempranas) para que `go vet`'s `lostcancel` siga verde. Esto es una **corrección, no un cambio de contrato**: cancelar antes de leer el body es una causa plausible del propio truncado que 8.2.1 intenta sobrevivir. |
| 8.2.6 | `Timeout = 3 s` por intento, sin cambios. Los headers (`Authorization`, `Content-Type`, `HTTP-Referer`, `X-Title`) no cambian. |
| 8.2.7 | Los tests que tocan `endpointURL` **no** usan `t.Parallel()` (mutan var de paquete) y restauran con `t.Cleanup`. |
| 8.2.8 | Ningún literal de app ni de endpoint de test entra en `pkg/` (B3). |

**Aceptación 8.2** — `pkg/jev/jev_test.go`, sobre `httptest.NewServer`:

| Test | Servidor | Aserción |
|---|---|---|
| `TestPostJSONRetriesEmptyEnvelope` | 200 vacío la 1ª, `{"answers":{}}` la 2ª | `err == nil`, `data != nil`, `hits == 2` |
| `TestPostJSONEmptyEnvelopeAlwaysFails` | 200 vacío siempre | `err.Error() == "envelope S1 no-JSON"` **exacto** (8.2.4), `hits == 2` |
| `TestPostJSONTruncatedJSONRetries` | `{"answers":` siempre | `err.Error() == "envelope S1 no-JSON"` exacto, `hits == 2` |
| `TestPostJSONNon2xxDoesNotRetry` | 500 siempre | `err.Error() == "red S1 http 500"`, `hits == 1` (protege 8.2.3) |
| `TestPostJSONTransportFailureStillWrapped` | servidor cerrado antes de llamar | `strings.HasPrefix(err.Error(), "red S1 falló tras retry:")`, `hits == 2` |

Esqueleto (el `@coder` lo completa):

```go
func TestPostJSONRetriesEmptyEnvelope(t *testing.T) {
	t.Setenv("OPENROUTER_API_KEY", "test-key")
	var hits int
	srv := httptest.NewServer(http.HandlerFunc(func(w http.ResponseWriter, r *http.Request) {
		hits++
		if hits == 1 {
			w.WriteHeader(http.StatusOK) // 200 sin body
			return
		}
		_, _ = w.Write([]byte(`{"answers":{}}`))
	}))
	prev := endpointURL
	endpointURL = srv.URL
	t.Cleanup(func() { endpointURL = prev; srv.Close() })
	data, err := postJSON(map[string]any{"model": "x"})
	if err != nil || data == nil || hits != 2 {
		t.Fatalf("retry ante envelope vacío: hits=%d err=%v", hits, err)
	}
}
```

Tiempo añadido a `go test ./pkg/jev/`: ~2 s (4 sleeps de 500 ms). Aceptable
frente al timeout por defecto de `go test`.

### 8.3 Contrato P3-c — `top_candidates` en el Fallback Soberano

**Decisión vinculante — distribución: campo `Probs` en `jev.Answer`, no
reparsear `Raw`.**

Motivo concreto y medido: `normAnswer` (231) ya recibe de `ValidateChoice` el
mapa completo `map[string]float64` (alloc fresco en 185, ya validado:
completo frente a `criteria`, finito, suma ±0.025, argmax). Tirarlo y
reparsear `Raw["probabilities"]` obligaría a `pkg/director` a duplicar esa
validación con su **propio** `toFloat` (90-102), que **no** contempla
`json.Number` a diferencia del de `pkg/jev` (118-133) → pérdida silenciosa de
entradas. `Probs` no añade validación, solo transporte. `Raw` se conserva
intacto para forense y retrocompatibilidad.

```go
// pkg/jev/jev.go — un campo más, al FINAL del struct (ver 8.3.11)
type Answer struct {
	Kind       string // "choice" | "noul" | "score"
	Key        string
	P          float64
	Confidence float64
	Raw        map[string]any
	// Probs: distribución choice completa que ya validó ValidateChoice.
	// nil en noul/score y en el stub {mock:true}. Solo lectura.
	Probs map[string]float64
}

// normAnswer, rama "choice": un campo más en el literal
return Answer{Kind: "choice", Key: key, P: probs[key],
	Confidence: conf, Raw: ans, Probs: probs}, nil
```

```go
// pkg/director/director.go
// TopCandidate un candidato recomendado del Fallback Soberano.
type TopCandidate struct {
	Idx  int     `json:"idx"`
	Prob float64 `json:"prob"`
}

// TopCandidatesMax candidatos máximos que se recomiendan al Director.
const TopCandidatesMax = 3

// TopCandidates ordena la distribución de mayor a menor prob; empate →
// menor idx. Descarta claves no numéricas ("NONE"), índices fuera de
// [0, normalizer.MaxTable-1] y probs no finitas. nil si no queda nada.
func TopCandidates(probs map[string]float64, n int) []TopCandidate {
	if len(probs) == 0 || n <= 0 {
		return nil
	}
	out := make([]TopCandidate, 0, len(probs))
	for k, v := range probs {
		i, err := strconv.Atoi(k)
		if err != nil || i < 0 || i > normalizer.MaxTable-1 {
			continue
		}
		if math.IsNaN(v) || math.IsInf(v, 0) {
			continue
		}
		out = append(out, TopCandidate{Idx: i, Prob: v})
	}
	// Orden total explícito: la iteración de map en Go es aleatoria.
	sort.Slice(out, func(a, b int) bool {
		if out[a].Prob != out[b].Prob {
			return out[a].Prob > out[b].Prob
		}
		return out[a].Idx < out[b].Idx
	})
	if len(out) > n {
		out = out[:n]
	}
	if len(out) == 0 {
		return nil
	}
	return out
}
```

Añade `sort` y `strconv` a los imports de `pkg/director`.

**Punto de aplicación en `ResolveElementWithTau`:**

```go
		conf = norm.Confidence
		if math.IsNaN(conf) || math.IsInf(conf, 0) || conf < 0.0 || conf > 1.0 {
			return SovereignFallback("S1_HALLUCINATION: … (conf no finita o fuera de [0,1])", snapshotID), nil
		}
		// P3: se calcula AQUÍ, antes de la rama NONE, que retorna antes.
		top := TopCandidates(norm.Probs, TopCandidatesMax)
		if norm.Key == "NONE" {
			fb := SovereignFallback("NO_TARGET: S1 eligió NONE; ningún candidato útil en esta pantalla", snapshotID)
			if len(top) > 0 {
				fb["top_candidates"] = top
			}
			return fb, nil
		}
```

y en la rama `LOW_CONF` (~192), **después** de los campos existentes:

```go
	fb := SovereignFallback(fmt.Sprintf("LOW_CONF: conf %.3f < tau %.2f; no actuar", conf, tau), snapshotID)
	fb["conf"] = conf // … tracker.Track / fb["cost_usd"] / fb["usage"] sin cambios …
	if len(top) > 0 {
		fb["top_candidates"] = top
	}
```

| # | Regla |
|---|---|
| 8.3.1 | **Aditivo puro.** Los 6 campos actuales conservan nombre, tipo y valor exactos. `SovereignFallback` **no** gana parámetros: su firma sigue `func SovereignFallback(reason string, snapshotID int64) map[string]any` (así todo llamante fuera de §8.3 queda intacto). `recovery_instruction` sigue siendo el literal `SovereignRecovery`. |
| 8.3.2 | `top_candidates` = array de `{"idx": int, "prob": number}` (struct `TopCandidate`, claves JSON exactas `idx`, `prob`). Nunca `null` dentro, nunca `idx: null`, **sin redondear** (float64 íntegro en el JSON). |
| 8.3.3 | Orden: `prob` descendente; **empate → `idx` ascendente**. Orden total explícito, nunca el orden de iteración del map. |
| 8.3.4 | Solo claves de índice **numéricas** dentro de `[0, normalizer.MaxTable-1]` = `0..253`. `"NONE"` queda **siempre** excluido, tenga la probabilidad que tenga. |
| 8.3.5 | Máximo 3 (`TopCandidatesMax`); si la distribución tiene menos claves válidas, devuelve menos. |
| 8.3.6 | Si `TopCandidates` devuelve `nil`, la clave **`top_candidates` está AUSENTE** del mapa. Nunca se emite `[]` vacío: "sin datos" y "cero candidatos" no se confunden. |
| 8.3.7 | **PRESENTE** si y solo si `ValidateChoice` pasó (distribución válida) **Y** (`conf < tau` **O** `norm.Key == "NONE"`). |
| 8.3.8 | **AUSENTE** en `S1_UNAVAILABLE` (153-155), `S1_NETWORK` (163), `S1_EMPTY_ENVELOPE` (167 y 189) y los tres `S1_HALLUCINATION` (174, 178, 185). En esas ramas no hay distribución válida que recomendar: no se inventa. |
| 8.3.9 | Rama `LOW_CONF`: conserva `conf`, `cost_usd` y `usage` tal cual (mismo `tracker.Track`, mismo orden de llamadas) y **añade** `top_candidates`. No se quita ni renombra nada. |
| 8.3.10 | Rama `NONE`: conserva **exactamente** su juego de campos actual y añade `top_candidates`. **P3 no le añade `conf` ni coste** (queda fuera de alcance; enmienda en 8.5.3). |
| 8.3.11 | El campo `Probs` va **al final** del struct `Answer`. Solo los literales **con clave** compilan contra él: verificado que `director_test.go` y `aiproviders_test.go` construyen `jev.Answer{Kind: …}` con clave, así que no se rompe nada. **Norma para el `@coder`: nunca literal posicional de `Answer`.** `stubPick` y las ramas `noul`/`score` dejan `Probs == nil`. |
| 8.3.12 | `norm.Probs` es de **solo lectura**. `ValidateChoice` lo aloca fresco (185), así que compartir la referencia es seguro; `pkg/director` jamás asigna en él. |
| 8.3.13 | La rama `ok:true` (214-219) **no** gana `top_candidates`. Y `pkg/tools/` **no se toca**: 0 líneas. `tools-count-35` y `tools-schema` de `audit-mcp` siguen verdes. |

**Aceptación 8.3** (`pkg/director/director_test.go`):

| Test | Montaje | Aserción |
|---|---|---|
| `TestResolveLowConfTopCandidates` | tabla 4 filas; `Probs:{"0":0.55,"1":0.30,"2":0.10,"3":0.05,"NONE":0.0}`, `Key:"0"`, `Confidence:0.40`, tau 0.70 | `top_candidates` presente, `len==3`, `[0]={0,0.55} [1]={1,0.30} [2]={2,0.10}`; `"NONE"` ausente; `conf`, `cost_usd` y `usage` siguen presentes |
| `TestResolveNoneTopCandidates` | `Key:"NONE"`, `Confidence:0.95`, `Probs:{"0":0.05,"NONE":0.95}` | `top_candidates == [{0,0.05}]` — **`NONE` se excluye aun siendo el de mayor `prob`** (aserción portante del contrato) |
| `TestResolveFallbacksWithoutTopCandidates` | los 4 casos restantes (red / envelope vacío / alucinación / sin key) | `if _, ok := out["top_candidates"]; ok { t.Fatal }`. Extender `assertFallback` con un `wantTop bool` |
| `TestResolveLowConfWithoutProbsKeepsCompat` | `Answer{Kind:"choice", Key:"0", Confidence:0.40}` sin `Probs` | sin panic, `top_candidates` **ausente**, `reason` conserva `LOW_CONF`. Es lo que mantiene vivos los `Answer` a mano de hoy |
| `TestTopCandidatesOrder` | `{"2":0.4,"1":0.4,"0":0.2}` | `[{1,0.4},{2,0.4},{0,0.2}]` (empate → idx menor). `{"NONE":0.9}` → `nil`. `{}` → `nil`. `{"999":0.9}` → `nil` (fuera de 0..253) |
| `TestNormAnswerCarriesProbs` (`pkg/jev`) | choice válida | `len(Probs) == len(criteria)` y `Probs[key] == P` |
| `TestStubAndOtherKindsHaveNoProbs` (`pkg/jev`) | `stubPick`, `noul`, `score` | `Probs == nil` → `top_candidates` ausente |

`TestResolveSovereignFallback` se **extiende**, no se reescribe: sigue
afirmando `err == nil`, `ok == false`, `idx == nil`,
`fallback_required == true`, `reason`, `recovery_instruction` y
`snapshot_id` en las 6 ramas.

### 8.4 Aceptación consolidada P3 (`@judge`, sin editar)

A1–A6 de §6 **siguen vigentes** para P1/P2. P3 se certifica con:

| # | Comprobación | Resultado exigido |
|---|---|---|
| B1 | `go build ./... && go vet ./... && go test ./...` | exit 0, sin `lostcancel` ni `printf` |
| B2 | `go run ./cmd/audit-mcp` | **11/11 PASS**, incluidos `tools-count-35`, `tools-schema`, `no-stdout-statico`, `stdout-puro-jsonrpc` |
| B3 | `grep -rniE 'whatsapp\|youtube\|morphe\|fossify\|contact_name\|verify_chat\|wrong_chat' pkg/ cmd/` | **vacío** (cero literales de app) |
| B4 | `go test ./pkg/normalizer/ -run TestReplayPythonParity -v` | PASS, y `git diff -- pkg/normalizer/normalizer.go` **solo añade** `SanitizeMaxRunes`, `SanitizeModelLabel` y sus helpers: `SerializeTable` y `FormatCandidateLabel` sin una línea tocada |
| B5 | Tests nuevos: 12 de saneamiento + 2 compuestos (`normalizer`), 5 de `postJSON` + 2 de `Probs` (`jev`), 5 de `top_candidates` (`director`) | verdes |
| B6 | Tests preexistentes **sin modificar**: `TestValidateChoiceOK`, `TestValidateChoiceRejects`, `TestAskStubWithoutKey`, `TestAskDecisionDoesNotMutateTable`, `TestReplayPythonParity`, `TestBuildResolveStateBlind`, `TestBuildResolveStateEnrichesLabels`, `TestResolveSovereignFallback`, `TestResolveWithoutS1KeyFails` | verdes tal cual (solo `assertFallback` crece un parámetro) |
| B7 | `grep -rn 'envelope S1 no-JSON' pkg/` | el string aparece **solo** como el valor de `envelopeEmptyMsg` y en la comparación de 8.2.4. Sin reescrituras de `red S1 http %d` ni de `red S1 falló tras retry: %v` |
| B8 | Cero escritura a stdout en el path tocado | `fmt.Print*` / `os.Stdout` ausentes en `pkg/normalizer`, `pkg/jev`, `pkg/director`. Solo `slog` (stderr) y nada más. Cubierto por `no-stdout-statico` de B2 |
| B9 | `git diff --stat -- pkg/tools/ cmd/audit-mcp/` | **vacío**. P3 no toca la superficie MCP |

### 8.5 Riesgos y reversión

| # | Riesgo | Reversión |
|---|---|---|
| R1 | La eliminación (no sustitución) de control chars **fusiona tokens**: un `content_desc` multilínea llega al modelo como una palabra pegada. Aceptado por 8.1.2; el texto íntegro sigue disponible vía `read_screen` | cambiar el `continue` de 8.1.2 por `b.WriteRune(' ')` (1 línea) |
| R2 | El corte a 80 runas pierde el discriminante final de un label muy largo (`content_desc` extenso) | subir `SanitizeMaxRunes` (const única); el texto completo sigue en `read_screen` |
| R3 | El retry sube el peor caso: 500 ms + 2×`Timeout` ≈ **6.5 s** por llamada S1 (el incidente medía 1354 ms). Acotado por `maxAttempts=2` y `Timeout=3s`; el Director no debe encadenar llamadas S1 a ciegas | `maxAttempts = 1` degrada al comportamiento actual |
| R4 | Mover `cancel()` tras la lectura del body (8.2.5) es una corrección: sin ella, el retry podría estar sobreviviendo a un truncado auto-infigido y enmascararlo | restaurar `cancel()` a la línea 272 |
| R5 | `top_candidates` invita al Director a tapear el "segundo mejor" sin verificar. **Mitigación ya vigente y que este contrato no abre**: `idx` sigue siendo `nil` en el fallback y `recovery_instruction` sigue siendo la directiva ("examina candidates/render y ejecuta tap_node/tap_text directo"). `top_candidates` dice **dónde mirar**, nunca **qué actuar**. `TestResolveSovereignFallback` conserva la aserción `out["idx"] != nil → Fatal` en las 6 ramas | eliminar el bloque `fb["top_candidates"]` (2 líneas) |
| R6 | El campo nuevo `Answer.Probs` rompe literales **posicionales**. Hoy no hay ninguno (verificado); 8.3.11 lo prohíbe | mover el campo a una struct aparte si hiciera falta |
| R7 | `endpointURL` podría apuntarse a un tercero si alguien lo expone después. Hoy es no exportado y sin env var: **solo los tests del paquete lo tocan** | sustituir por la `const Endpoint` en 262 |
| R8 | **Preexistente, NO lo arregla P3**: la rama `NONE` (180-182) retorna sin pasar por `tracker.Track`, así que una resolución con `NONE` **no registra coste**. No se toca para no mezclar un cambio de instrumentación en un contrato de resiliencia | enmienda del orquestador (8.5.3) |

Enmiendas propuestas al orquestador (no aplicadas aquí):

1. Documentar `top_candidates` como campo **de resultado** del fallback
   soberano en `PROTOCOL.md` / `MCP_SPEC_GUIDELINES.md` **cuando**
   `resolve_element` se registre como tool (hoy no lo está).
2. Documentar `via = "click_ancestor"` (arrastrado de §7).
3. Decidir el destino de R8: registrar coste en la rama `NONE`, o documentar
   que `NONE` es deliberadamente gratis porque no consume decisión útil.

## 9. Contrato P4 — Conciencia de estado en `read_screen` (`focused_field` endurecido + `screen_fingerprint`/`diff_since_last` + memoria `[tried]`)

> Redacta `@architect`, implementa `@coder`, certifica `@judge`. Aditivo y de
> capa interna. **NO** cambia el `inputSchema` de ninguna de las 35 tools
> (`cmd/audit-mcp` debe seguir 11/11 PASS), **NO** escribe a `stdout`, y **NO**
> toca `SerializeTable` ni `FormatCandidateLabel` (paridad golden intacta).
> 100% genérico: cero literales de app.

### 9.0 Superficie real (leída, no inferida)

- `pkg/normalizer/normalizer.go`:
  - `FocusedField{Label,Kind,Holds,IsPassword}` + `AsView() → {label,kind,holds}`
    (~124-157). `PassMask = "a password, not read"`; `HoldsMax = 140`.
  - `theFocusedField(nodes)` (~227-260) detecta secreto con `isPassword()`
    (~190-198) sobre `class + resource_id + hint + content_desc`.
  - `Row{Idx,ID,Label,Text,ResourceID,Bounds,Clickable,Editable,Focused,
    Scrollable,Visible,ClassShort,Zone,Flags}` (~400-415);
    `BuildTable` (~471-496); `ScreenFingerprint([]Candidate)` ya existe (~742-774)
    pero **no** incluye paquete y devuelve sha256 completo (64 hex).
  - `volatileTextRe` (~46) excluye relojes/porcentajes.
- `pkg/tools/helpers.go`: `readScreenState()` (~288-326) arma `evidence` inline
  con `package/activity/snapshot_id/focused_field/first_result/candidates/render`.
- `pkg/tools/ui.go`: `hTapNode` (~35-51) y `hTypeText` (~53-74) actúan y
  verifican con `read_screen` (sin post-snapshot).
- `pkg/director/director.go`: `BuildResolveState(...)` (~33-66) copia la tabla
  serial y la pasa por `FormatCandidateLabel(SanitizeModelLabel(...))`;
  `ResolveElementWithTau` (~190-284). `pkg/jev/jev.go`: `AskDecision` (~388-479)
  con `AskDecisionOpts` y el mismo saneado de labels.

### 9.1 P4-a — `focused_field` endurecido (nunca viaja el secreto)

1. `AsView()` **ya** garantiza `{label,kind,holds}` con `kind="password"` y
   `holds=PassMask` cuando `IsPassword` (9.0). Se **conserva** sin cambios.
2. Se amplía la detección de secreto en `theFocusedField`: además de
   `isPassword(class,rid,hint,desc)`, cuenta la **propiedad nativa** del nodo
   `password` / `is_password` (`boolVal`). Criterio: `secret := isPassword(...)
   || boolVal(n,"password") || boolVal(n,"is_password")`.
3. Criterio de aceptación: para un editable enfocado con `text` normal →
   `{label,kind:"text",holds:<text≤140>}`; para uno detectado secreto →
   `{label,kind:"password",holds:"a password, not read"}` y **jamás** el texto
   real en `focused_field`.

### 9.2 P4-b — `screen_fingerprint` (corta, determinista) y `diff_since_last`

1. Nuevo, en `pkg/normalizer` (puro): `ScreenFingerprintRows(pkg string,
   rows []Row) string` = **12 hex** de `sha256` sobre `pkg` + por fila
   (en orden) `ClassShort`, `Zone`, `Flags` y `SanitizeModelLabel(Label)`,
   **excluyendo** filas volátiles (`isVolatileNode`-equivalente sobre
   `Row.Text`) y **sin** `snapshot_id`. `""` si no queda ninguna fila.
   - Helpers exportados puros: `LabelIsVolatile(text string) bool`.
2. Nuevo paquete `pkg/uitrack` (memoria de proceso, `sync.Mutex`, toda la
   superficie con lock; **no** hay E/S ni red):
   - `Observe(fp string, snapshotID int64, pkg, focusKey string, labels
     []string, idxByNode map[string]int) Diff` guarda la lectura y calcula el
     diff contra la anterior. `focusKey = label+"\x00"+kind` de `focused_field`.
   - `Diff{Changed bool, PrevSnapshotID int64, SamePackage bool,
     FocusChanged bool, AddedLabels []string, RemovedLabels []string}` con
     **tope 5** etiquetas por lista; en la **primera** lectura:
     `prev_snapshot_id=0`, `changed=true`, `same_package=true`,
     `focus_changed=false`, listas vacías.
   - `AddedLabels` = etiquetas limpias (9.2.1) presentes ahora y ausentes antes;
     `RemovedLabels` = al revés. Solo se calculan si `Changed`.
3. `readScreenState` añade, **solo** en `evidence` (aditivo):
   `screen_fingerprint` (9.2.1), `diff_since_last` (mapa de 9.2.2 con las
   claves JSON del enunciado) y `tried_node_ids` (9.3.2). El resto de claves
   no cambia de tipo ni de nombre.

### 9.3 P4-c — memoria anti-bucle `tried_nodes` / marcador `[tried]`

1. `pkg/uitrack` mantiene `tried` por `screen_fingerprint`, **acotado a los
   últimos 16 fingerprints** (evicción FIFO; el vigente nunca se evicta en la
   misma operación). API:
   - `MarkTried(nodeID string, idx int)`: registra contra el fingerprint
     vigente (el de la última `Observe`); si `idx < 0`, lo resuelve por el
     `idxByNode` guardado. `nodeID==""` es no-op.
   - `TriedIDs(fp string) []string` (orden de inserción) y
     `CurrentTriedIdx() map[int]bool` (índices probados del fingerprint vigente).
   - `Reset()` para tests.
2. Tras éxito de `hTapNode` / `hTypeText` (`pkg/tools/ui.go`), se llama
   `uitrack.MarkTried(nodeID, -1)`. `readScreenState` expone
   `evidence.tried_node_ids = uitrack.TriedIDs(fp)` (vista del fingerprint
   **vigente**, no de otro).
3. Adaptador (capa que ve el modelo): nueva función aditiva
   `BuildResolveStateWithTried(screenGoal, serial, snapshotID, currentApp,
   firstResult, triedIdx map[int]bool)`; `BuildResolveState` delega con
   `nil` (firma intacta). Para cada fila cuyo `idx` (col `0`) esté en
   `triedIdx`, el **flags** (col `3`) recibe el sufijo `|tried`
   (`—` → `tried`), vía `normalizer.AddFlag`. En `pkg/jev`, `AskDecisionOpts`
   gana el campo aditivo `TriedIdx map[int]bool` con el mismo criterio.
   `ResolveElementWithTau` pasa `uitrack.CurrentTriedIdx()`.
   **`SerializeTable` no se toca** (paridad golden): el marcado ocurre solo en
   las copias que van al modelo.
4. Criterio de aceptación: `tried_node_ids` crece al tapear en el mismo
   `screen_fingerprint` y se vacía al cambiar de pantalla (fingerprint nuevo);
   la representación enviada a S1/S2 lleva `tried` en la fila probada.

### 9.4 Restricciones duras (idénticas a §8)

| # | Regla |
|---|---|
| C1 | `inputSchema` de las 35 tools sin cambios → `audit-mcp` 11/11 PASS |
| C2 | Cero `fmt.Print*`/`os.Stdout` en el código tocado (solo `slog` a stderr) |
| C3 | `SerializeTable`, `FormatCandidateLabel`, `Row.Label` y el golden `testdata/replay_expected.json` intactos |
| C4 | Cero literales de app; sin dependencias nuevas (`go.mod` no cambia) |
| C5 | Memoria acotada: ≤16 fingerprints; listas de diff ≤5 |

### 9.5 Riesgos y reversión

| # | Riesgo | Reversión |
|---|---|---|
| R9 | Estado global de proceso (`uitrack`) compartido entre `read_screen` y el adaptador: en tests paralelos podría cruzar datos | `Reset()` entre casos; evicción acotada. Alternativa: inyectar el set por parámetro (ya soportado en 9.3.3) |
| R10 | **Residual, NO lo cierra P4**: el `text` real de un nodo secreto sigue apareciendo en `evidence.candidates` y en `render`/`FormatState` (no en `focused_field`). Enmascararlo cambiaría `Compact`/`FormatState` → toca otro contrato (P5) | contrato P5 dedicado (enmascarar `candidates`/`render` sin tocar `SerializeTable`) |
| R11 | `prev_snapshot_id=0` en la primera lectura puede confundirse con el snapshot real 0 | `changed=true` lo desambigua; documentado en 9.2.2 |

## 10. Contrato P6 — Reanclaje de nodo vivo + foco en editables + fallback screencap (API 29)

> Redacta `@architect`, implementa `@coder`, certifica `@judge`.
> Alcance: **capa Android** (`android-app/app/src/main/java/dev/jev/jam/`).
> Toca `service/JevAccessibilityService.kt`, `ui/UiTreeExtractor.kt`
> (interfaz + `RealA11yNode`), un helper nuevo en `ui/`, `FakeA11yNode` y
> un test nuevo. **No toca `pkg/` (Go), ni `PROTOCOL.md`, ni `register.go`,
> ni `android-app/app/build.gradle.kts`.**
> Sustituye dos helpers privados del servicio por **un helper puro,
> testeable en JVM sin Robolectric**. Cero tools nuevas, cero campos
> nuevos en el protocolo.

### 10.0 Diagnóstico (evidencia medida, no inferida)

| Fuente | Hecho verificado |
|---|---|
| `service/JevAccessibilityService.kt:157-188` | `findLiveNodeByIndex` devuelve el nodo en **posición BFS** `index` sin mirar identidad: si la UI cambió por encima, devuelve el nodo equivocado y `verifySame` aborta. El tap se pierde aunque el nodo siga existiendo dos posiciones más abajo |
| `service/...:190-195` | `verifySame` compara solo `text` + `viewIdResourceName` + `className`. **No** compara `contentDescription`, ni la posición |
| `service/...:207-237` | `tapLiveNode` deriva `idx` de `node.id.removePrefix("n_")`; cadena `action_click → click_ancestor → gesture`; `finally { live.recycle(); uiDirty = true }` |
| `service/...:239-263` | `typeNode` reutiliza `findLiveNodeByIndex` + `verifySame`; `!isFocused` → `NOT_FOCUSED`; `ACTION_SET_TEXT` con `Bundle` |
| `service/...:374-381` | `takeScreenshotBlocking` en `SDK_INT < R` lanza `INTERNAL_ERROR` con el literal `fallback screencap = Fase 3c`: **`screenshot` está muerto en API 29** |
| `service/...:352-372` | `screenshotPng` devuelve `ScreenshotData(b64, w, h, "takeScreenshot")`: `via` **hardcodeado** |
| `ui/UiTreeExtractor.kt:11-33` | `A11yNode` expone `performClick()` pero **no** `ACTION_FOCUS` ni `ACTION_SET_TEXT`; `boundsInScreen` es `List<Int>` = `[l,t,r,b]` |
| `ui/ClickAncestor.kt:19-39` | Patrón de referencia: helper puro, nodo de entrada **prestado**, recicla todo lo obtenido salvo el ganador (`MAX_HOPS = 3`) |
| `shell/ShizukuBridge.kt:118-139` | `exec(cmd, timeoutMs = 15_000)` → `ExecResult(exit, stdout, stderr)`; llama `requireReady()` **antes** (propaga `SHIZUKU_UNAVAILABLE`/`SHIZUKU_DENIED`); exit `124` → `TIMEOUT` |
| `shell/ShellUserService.kt` | drena stdout con `bufferedReader().readText()` (**texto UTF-8**): un PNG crudo se corrompe. **Base64 obligatorio** |
| `ui/UiTreeExtractor.kt:72-135` | `MAX_NODES = 500`; los ids `n_i` se asignan **en orden de encolado** y los nodos se añaden **en orden de descolado** ⇒ `nodes[j].id == "n_j"`: el índice *es* la posición BFS |
| `app/src/test/.../FakeA11yNode.kt` | fake JVM con `recycled` y `clickAttempts` observables. Sin Robolectric; solo `junit:junit:4.13.2` |

Gate `AGENTS.md §2.2` verificado al redactar: `grep -rn 'su -c\|exec(.*su\|ProcessBuilder(.*su' android-app/app/src/` → **1 hit**, `shell/ShizukuBridge.kt:118` (falso positivo por `Re**su**lt`).

### 10.1 Contrato P6-a — `LiveNodeReanchor` (helper puro)

Archivo nuevo: `android-app/app/src/main/java/dev/jev/jam/ui/LiveNodeReanchor.kt`.
**Tres símbolos de primer nivel**, API exacta y cerrada:

```kotlin
package dev.jev.jam.ui

/**
 * Resultado de [LiveNodeReanchor.reanchor]. Invariante: `node != null`
 * <=> `status.found`. Cuando `node != null` es propiedad del helper y
 * **el llamador debe reciclarlo** (`node.recycle()`).
 */
enum class ReanchorStatus(val errorCode: String?) {
    EXACT(null),
    REANCHORED(null),
    NOT_FOUND("STALE_SNAPSHOT"),
    AMBIGUOUS("STALE_SNAPSHOT"),
    NO_WINDOW("SELECTOR_NOT_FOUND");
    val found: Boolean get() = errorCode == null
}

data class ReanchorResult(
    val node: A11yNode?,
    val status: ReanchorStatus
) {
    /** true solo si se recuperó por proximidad (paso 2), no por posición. */
    val reanchored: Boolean get() = status == ReanchorStatus.REANCHORED
}

object LiveNodeReanchor {
    /** Tope de nodos visitados: el mismo del extractor. */
    const val MAX_NODES: Int = UiTreeExtractor.MAX_NODES
    /** Deriva máxima tolerada del centroide, en px lógicos de a11y. */
    const val MAX_DRIFT_PX: Int = 24

    fun reanchor(
        root: A11yNode?,
        expected: UiNode,
        expectedIdx: Int,
        maxDriftPx: Int = MAX_DRIFT_PX,
        maxNodes: Int = MAX_NODES
    ): ReanchorResult

    fun matchesIdentity(live: A11yNode, expected: UiNode): Boolean
}
```

| # | Regla |
|---|---|
| 10.1.1 | **Puro**: sin Android, sin `JamError`, sin reloj, sin estado global. Falla con `ReanchorStatus`, nunca con excepción (así el JVM testea sin `android.jar`). `matchesIdentity` y `reanchor` son `public` |
| 10.1.2 | **Invariante duro**: `node != null` ⟺ `status.found`. `EXACT`/`REANCHORED` → nodo no nulo; `NOT_FOUND`/`AMBIGUOUS`/`NO_WINDOW` → `node == null` |
| 10.1.3 | `matchesIdentity(live, expected)` compara **exactamente 4 campos**, con `null == null` válido: `live.text?.toString() == expected.text` ∧ `live.viewIdResourceName == expected.resourceId` ∧ `live.className?.toString() == expected.className` ∧ `live.contentDescription?.toString() == expected.contentDesc`. Un solo campo distinto ⇒ falso. **Añade `contentDesc` respecto al `verifySame` actual** (3 campos) |
| 10.1.4 | Recorrido **BFS iterativo**, orden **idéntico** al de `UiTreeExtractor.extract`: raíz = índice `0`; se encolan los hijos **visibles** en orden `0 until childCount`; los hijos invisibles se **podan** (y se reciclan al instante); índice = posición de **descolado**; tope `maxNodes` |
| 10.1.5 | **Paso 1**: el nodo descolado en posición `expectedIdx` que cumple `matchesIdentity` → `ReanchorResult(n, EXACT)` y **corte inmediato** del recorrido (caso rápido, latencia idéntica a la de hoy) |
| 10.1.6 | Si el nodo de `expectedIdx` **no** cumple identidad, el recorrido **continúa y ese nodo se expande igual** (sus hijos se encolan). Prohibido saltarse su expansión: se perderían candidatos |
| 10.1.7 | **Paso 2**: todo nodo visible con `matchesIdentity` **y** centroide a distancia **Chebyshev** `max(|dx|, |dy|) <= maxDriftPx` del centroide de `expected.bounds` entra en `candidates`, **en orden BFS**. **Prohibido mezclar Manhattan**: la métrica es L∞ en todo el contrato |
| 10.1.8 | Centroide = `(bounds[0]+bounds[2])/2, (bounds[1]+bounds[3])/2` con **división entera de Kotlin** (trunca hacia cero, también en negativos). `bounds.size != 4` ⇒ el nodo **no** es candidato de proximidad (pero sí puede ser `EXACT` en el paso 1) |
| 10.1.9 | **Paso 3**: exactamente 1 candidato ⇒ `ReanchorResult(candidato, REANCHORED)`. **Paso 4**: `0` ⇒ `NOT_FOUND`; `>1` ⇒ `AMBIGUOUS`. En ambos, `node == null` |
| 10.1.10 | Guardas previas: `root == null` \|\| `!root.isVisibleToUser` \|\| `maxNodes < 1` ⇒ `NO_WINDOW` (sin tocar el árbol). `expectedIdx < 0` ⇒ `NOT_FOUND` |
| 10.1.11 | `NO_WINDOW` se decide **solo** en la guarda previa. Si la guarda pasó, el BFS visita ≥1 nodo ⇒ 0 candidatos significa `NOT_FOUND`, nunca `NO_WINDOW` |
| 10.1.12 | **Reciclaje**: la raíz es **prestada** ⇒ el helper **jamás** la recicla (ni en `NO_WINDOW`); el llamador la recicla en su `finally`. Todo nodo obtenido por `getChild(i)` es del helper: se recicla **salvo el ganador**, incluidos los que quedaron encolados sin visitar por `maxNodes`. Mismas reglas que `ClickAncestor.find` |
| 10.1.13 | Sin `IOException`, sin `try/catch` alrededor de `getChild` salvo el patrón `?: continue` ya usado por el extractor. Determinista: no lee reloj, ni entorno, ni `Build.VERSION` |
| 10.1.14 | **Cambio observable**: el caso "el índice cae fuera del árbol" hoy da `SELECTOR_NOT_FOUND` y pasa a `STALE_SNAPSHOT` (`NOT_FOUND`). Ambos son honestos y el cliente re-dumpea; `STALE_SNAPSHOT` describe mejor la causa. Enmienda propuesta a `PROTOCOL.md §4` |

Esqueleto normativo (estructura obligatoria; nombres sugeridos):

```kotlin
fun reanchor(root, expected, expectedIdx, maxDriftPx, maxNodes): ReanchorResult {
    if (root == null || !root.isVisibleToUser || maxNodes < 1) return ReanchorResult(null, NO_WINDOW)
    if (expectedIdx < 0) return ReanchorResult(null, NOT_FOUND)

    val queue = ArrayDeque<A11yNode>()          // FIFO: BFS
    val owned = ArrayList<A11yNode>()           // todo lo que salga de getChild
    val candidates = ArrayList<A11yNode>()
    val want = centroid(expected.bounds)
    queue.add(root)
    var visited = 0
    var winner: A11yNode? = null
    var status = NOT_FOUND

    while (queue.isNotEmpty() && visited < maxNodes) {
        val n = queue.removeFirst()
        if (visited == expectedIdx && matchesIdentity(n, expected)) {
            winner = n; status = EXACT
            break
        }
        if (matchesIdentity(n, expected)) {
            val c = centroid(n.boundsInScreen)
            if (c != null && want != null && chebyshev(c, want) <= maxDriftPx) candidates.add(n)
        }
        visited++
        for (i in 0 until n.childCount) {           // idéntico al extractor
            val ch = n.getChild(i) ?: continue
            if (!ch.isVisibleToUser) { ch.recycle(); continue }
            owned.add(ch); queue.add(ch)
        }
    }
    if (winner == null) {
        when (candidates.size) {
            1 -> { winner = candidates[0]; status = REANCHORED }
            0 -> status = NOT_FOUND
            else -> status = AMBIGUOUS
        }
    }
    for (n in owned) if (n !== winner) n.recycle()  // incluye sobrantes encolados
    return ReanchorResult(winner, status)
}

private fun centroid(b: List<Int>): Pair<Int, Int>? =
    if (b.size == 4) (b[0] + b[2]) / 2 to (b[1] + b[3]) / 2 else null

private fun chebyshev(a: Pair<Int, Int>, b: Pair<Int, Int>): Int =
    maxOf(kotlin.math.abs(a.first - b.first), kotlin.math.abs(a.second - b.second))
```

Traducción a error en el servicio (literales **conservados** de hoy):

| `status` | `JamError` (mensaje, código) |
|---|---|
| `NOT_FOUND` | `("la UI cambió entre dump y acción; re-haz dump_ui", "STALE_SNAPSHOT")` — literal idéntico al de `verifySame` actual |
| `AMBIGUOUS` | `("el nodo se duplicó en pantalla; re-haz dump_ui", "STALE_SNAPSHOT")` |
| `NO_WINDOW` | `("el nodo ya no existe", "SELECTOR_NOT_FOUND")` — literal idéntico al de `findLiveNodeByIndex` nulo |

### 10.1-bis Contrato P6-b — Puente `A11yNode` ↔ nativo (DECISIÓN)

**Decisión (obligatoria): extender `A11yNode` con dos métodos de acción y
reemplazar `findLiveNodeByIndex` + `verifySame` por `LiveNodeReanchor` en
`tapLiveNode` y `typeNode`.** Hace ambos caminos **JVM-testables** (el
`Bundle` de `ACTION_SET_TEXT` sale del servicio) y elimina el *drift*
posicional (§10.1.14).

| # | Regla |
|---|---|
| 10.1b.1 | `A11yNode` gana `fun performFocus(): Boolean` y `fun setText(text: CharSequence): Boolean`. Solo estos dos; ningún otro cambio de interfaz |
| 10.1b.2 | `RealA11yNode.performFocus()` = `info.performAction(AccessibilityNodeInfo.ACTION_FOCUS)`. `RealA11yNode.setText(t)` = `Bundle` con `ACTION_ARGUMENT_SET_TEXT_CHARSEQUENCE` + `info.performAction(ACTION_SET_TEXT, args)` (imports `android.os.Bundle` en `UiTreeExtractor.kt`) |
| 10.1b.3 | `FakeA11yNode` (test) implementa ambos con parámetros por defecto `focusResult: Boolean = true`, `setTextResult: Boolean = true` y contadores observables `focusAttempts`, `setTextAttempts`, `lastSetText: CharSequence?` |
| 10.1b.4 | `LiveNodeReanchor` **no** lleva acciones: sigue siendo puro. El puente es solo `performFocus`/`setText`; `performClick` ya existía (precedente) |
| 10.1b.5 | El servicio gana **un** helper privado nuevo y borra dos: `private fun reanchorOrThrow(expected: UiNode): A11yNode` (**elimina** `findLiveNodeByIndex` y `verifySame`; `grep -c 'findLiveNodeByIndex\|verifySame'` → **0**) |
| 10.1b.6 | `reanchorOrThrow` calcula `idx` desde `expected.id.removePrefix("n_").toIntOrNull()` y lanza `("node_id inválido","VALIDATION_ERROR")` si no parsea. Toma `root = rootInActiveWindow`; si es `null` lanza `NO_WINDOW`; si no, envuelve en `try { LiveNodeReanchor.reanchor(RealA11yNode(root), expected, idx) } finally { root.recycle() }` — así la raíz prestada se recicla **siempre** |
| 10.1b.7 | Si `status.found` es falso, `reanchorOrThrow` lanza `JamError(mensaje, status.errorCode!!)` con la tabla de arriba; rama inalcanzable `EXACT/REANCHORED` con nodo nulo = `IllegalStateException("reanchor inconsistente: $status")` (bug, no estado de UI) |
| 10.1b.8 | `tapLiveNode` y `typeNode` conservan su `finally { live.recycle(); uiDirty = true }`. **Prohibido** tocar `requireFreshNode` (`STALE_SNAPSHOT` por `snapshotId`/`uiDirty`) |
| 10.1b.9 | La rama de gesto usa la abstracción: `val bs = live.boundsInScreen; if (bs.size != 4) throw JamError("nodo sin bounds","INTERNAL_ERROR")`; centroide `(bs[0]+bs[2])/2, (bs[1]+bs[3])/2` (regla entera de 10.1.8) y `toPhysical(cx, cy)` |
| 10.1b.10 | `ClickAncestor.find(live)` recibe el `A11yNode` directamente (hoy `RealA11yNode(live)`). El ancestro se recicla en cuanto se usa, como hoy |
| 10.1b.11 | `via` conserva **exactamente** el dominio `{action_click, click_ancestor, gesture}` y el orden de preferencia de 10.2.2. Sin valores nuevos |

```kotlin
private fun reanchorOrThrow(expected: UiNode): A11yNode {
    val idx = expected.id.removePrefix("n_").toIntOrNull()
        ?: throw JamError("node_id inválido", "VALIDATION_ERROR")
    val root = rootInActiveWindow
        ?: throw JamError("el nodo ya no existe", "SELECTOR_NOT_FOUND")
    val res = try {
        LiveNodeReanchor.reanchor(RealA11yNode(root), expected, idx)
    } finally {
        root.recycle()
    }
    val live = res.node
    if (res.status.found && live != null) return live
    when (res.status) {
        ReanchorStatus.NOT_FOUND -> throw JamError("la UI cambió entre dump y acción; re-haz dump_ui", "STALE_SNAPSHOT")
        ReanchorStatus.AMBIGUOUS -> throw JamError("el nodo se duplicó en pantalla; re-haz dump_ui", "STALE_SNAPSHOT")
        ReanchorStatus.NO_WINDOW -> throw JamError("el nodo ya no existe", "SELECTOR_NOT_FOUND")
        else -> throw IllegalStateException("reanchor inconsistente: ${res.status}")
    }
}
```

### 10.2 Contrato P6-c — Foco en editables tras el tap

| # | Regla |
|---|---|
| 10.2.1 | `tapLiveNode` se reestructura: los tres `return` tempranos colapsan en un único `val via: String` + un `return TapResult(node.id, via)` al final. El bloque de foco (10.2.3) va **antes** del `finally` que recicla `live` |
| 10.2.2 | Orden de preferencia **intacto**: `live.isClickable && live.performClick()` ⇒ `action_click`; si no, `ClickAncestor.find(live) != null` ⇒ `click_ancestor` (reciclando el ancestro); si no, gesto al centro ⇒ `gesture`. Un fallo de gesto sigue lanzando `("gesto rechazado por el sistema","INTERNAL_ERROR")` |
| 10.2.3 | Tras un tap **exitoso** (cualquier `via`), si `node.editable \|\| live.isEditable` ⇒ `live.performFocus()`, **best-effort**: si devuelve `false` se registra `JevLog.d(TAG, "performFocus rechazado tras $via")` y **NO** se lanza nada |
| 10.2.4 | Si `performFocus()` lanza excepción, se atrapa con `try { … } catch (t: Throwable) { JevLog.d(TAG, "performFocus lanzó: ${t.message}") }`. Un fallo de foco **jamás** cambia el `ok` de la acción |
| 10.2.5 | `typeNode` **conserva** `if (!live.isFocused) throw JamError("el nodo no tiene foco; haz tap antes","NOT_FOCUSED")`. **Prohibido el tap implícito** |
| 10.2.6 | `typeNode` usa `live.setText(text)` (10.1b.2) en lugar del `Bundle` a mano. Si devuelve `false` ⇒ `("ACTION_SET_TEXT rechazado","INTERNAL_ERROR")` (literal actual). Devuelve `text.length` |
| 10.2.7 | `uiDirty = true` se sigue poniendo en el `finally` de ambas acciones |

### 10.3 Contrato P6-d — Fallback `screencap` para `SDK_INT < 30`

| # | Regla |
|---|---|
| 10.3.1 | `takeScreenshotBlocking()` abre con `if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) return screencapBlocking()` y **elimina** el `JamError("takeScreenshot requiere API 30+ …","INTERNAL_ERROR")`. El camino API 30+ queda **byte por byte** como está (latch, `copy` antes de `close()`, `ERROR_TAKE_SCREENSHOT_SECURE_WINDOW` → `SECURE_SURFACE`) |
| 10.3.2 | `private fun screencapBlocking(): Bitmap` = `ShizukuBridge.exec(listOf("sh", "-c", "screencap -p | base64"), timeoutMs = SCREENSHOT_TIMEOUT_MS)`. **Base64 es obligatorio**: `ShellUserService` drena con `readText()` (UTF-8) y un PNG crudo se corrompe |
| 10.3.3 | `sh -c` porque el comando es una **tubería**. Se escribe literalmente `"sh"`, **nunca** `"su"`: la línea no debe contener la secuencia `su` tras `exec(` (gate §2.2) |
| 10.3.4 | `ShizukuBridge.exec` **no** se envuelve en `try/catch`: `SHIZUKU_UNAVAILABLE`, `SHIZUKU_DENIED` y `TIMEOUT` (exit 124) se propagan tal cual desde `requireReady()`/el bridge |
| 10.3.5 | `exitCode != 0` ⇒ `JamError("screencap falló (exit $exitCode): ${stderr.take(200)}", "INTERNAL_ERROR")` (mismo formato que el fallo de `monkey` en `openApp`) |
| 10.3.6 | Antes de decodificar: `val b64 = stdout.filter { !it.isWhitespace() }` (elimina el salto de línea de toybox `base64`, que envuelve a 76 columnas). Vacío ⇒ `JamError("captura vacía o superficie protegida (screencap)", "SECURE_SURFACE")` |
| 10.3.7 | `Base64.decode(b64, Base64.DEFAULT)` dentro de `try { … } catch (t: IllegalArgumentException)` ⇒ el mismo `SECURE_SURFACE`. `BitmapFactory.decodeByteArray` nulo ⇒ el mismo `SECURE_SURFACE` |
| 10.3.8 | `screenshotPng` reporta `via = if (Build.VERSION.SDK_INT < Build.VERSION_CODES.R) "screencap" else "takeScreenshot"`. Dominio final de `via` en `screenshot`: `{takeScreenshot, screencap}`. **No cambia el schema**: `via` ya existe en `ScreenshotData` |
| 10.3.9 | Intactos: el check `b64.length > MAX_SCREENSHOT_B64` ⇒ `("imagen excede 4 MiB; usa format=webp, quality=80","PAYLOAD_TOO_LARGE")`, el `finally { if (!bmp.isRecycled) bmp.recycle() }`, `WEBP_LOSSY` en API 30+ y la validación `format ∈ {png, webp}` |
| 10.3.10 | Sin test JVM para 10.3: depende de `Build.VERSION` y de `ShizukuBridge`. Se certifica por compilación + inspección (F2/F10) |

```kotlin
private fun screencapBlocking(): Bitmap {
    val r = ShizukuBridge.exec(
        listOf("sh", "-c", "screencap -p | base64"), timeoutMs = SCREENSHOT_TIMEOUT_MS
    )
    if (r.exitCode != 0) {
        throw JamError("screencap falló (exit ${r.exitCode}): ${r.stderr.take(200)}", "INTERNAL_ERROR")
    }
    val b64 = r.stdout.filter { !it.isWhitespace() }
    if (b64.isEmpty()) {
        throw JamError("captura vacía o superficie protegida (screencap)", "SECURE_SURFACE")
    }
    val raw = try {
        Base64.decode(b64, Base64.DEFAULT)
    } catch (t: IllegalArgumentException) {
        throw JamError("captura vacía o superficie protegida (screencap)", "SECURE_SURFACE")
    }
    return BitmapFactory.decodeByteArray(raw, 0, raw.size)
        ?: throw JamError("captura vacía o superficie protegida (screencap)", "SECURE_SURFACE")
}
```

### 10.4 Contrato P6-e — Tests JVM (`LiveNodeReanchorTest.kt`)

Archivo nuevo: `android-app/app/src/test/java/dev/jev/jam/ui/LiveNodeReanchorTest.kt`.
JUnit 4 + `FakeA11yNode`. **Sin Robolectric, sin dependencias nuevas.**

Montaje compartido (centroide esperado = `(140, 150)`):

```kotlin
private fun expected(idx: Int = 1) = UiNode(
    id = "n_$idx", text = "Enviar", contentDesc = "send",
    className = "android.widget.Button", resourceId = "com.demo:id/send",
    bounds = listOf(40, 100, 240, 200), clickable = true, editable = false,
    scrollable = false, enabled = true, checked = false, focused = false,
    visible = true, children = emptyList()
)

private fun sendLive(b: List<Int> = listOf(40, 100, 240, 200)) = FakeA11yNode(
    text = "Enviar", contentDescription = "send",
    className = "android.widget.Button", viewIdResourceName = "com.demo:id/send",
    isClickable = true, boundsInScreen = b
)

private fun decoy() = FakeA11yNode(
    text = "Cancelar", className = "android.widget.Button",
    boundsInScreen = listOf(300, 300, 400, 400)
)

private fun rootOf(vararg kids: FakeA11yNode) = FakeA11yNode(
    text = "root", className = "android.widget.FrameLayout",
    boundsInScreen = listOf(0, 0, 1080, 2400), children = kids.toList()
)
```

| Id | Test | Montaje | Aserción |
|---|---|---|---|
| (a) `exactIndexReturnsSameNodeNoDrift` | `rootOf(sendLive(), decoy())`, `expectedIdx=1` | `status == EXACT`, `reanchored == false`, `node!!.text == "Enviar"`, `sendLive.recycled == false`, `decoy.recycled == true`, **`root.recycled == false`** |
| (b) `driftWithinToleranceReanchors` | `rootOf(decoy(), sendLive(listOf(45,105,245,205)))`, `expectedIdx=1` | centroide (145,155) ⇒ Chebyshev 5 ≤ 24: `status == REANCHORED`, `reanchored == true`, `node!!.text == "Enviar"`, `decoy.recycled == true`, `root.recycled == false` |
| (c) `driftBeyondToleranceFailsNotFound` | `rootOf(decoy(), sendLive(listOf(40,300,240,400)))`, `expectedIdx=1` | Chebyshev 200 > 24: `node == null`, `status == NOT_FOUND`, `errorCode == "STALE_SNAPSHOT"`, `decoy.recycled == true`, `sendLive.recycled == true`, `root.recycled == false` |
| (d) `twoCandidatesFailsAmbiguous` | `rootOf(decoy(), sendLive(), sendLive(listOf(50,110,250,210)))`, `expectedIdx=1` | dos candidatos (Chebyshev 0 y 10): `node == null`, `status == AMBIGUOUS`, `errorCode == "STALE_SNAPSHOT"`, **ambos** `recycled == true`, `root.recycled == false` |
| (e) `nullRootIsNoWindow` | `reanchor(null, expected(), 1)` | `node == null`, `status == NO_WINDOW`, `errorCode == "SELECTOR_NOT_FOUND"`; **no** excepción |
| (f) `invisibleRootIsNoWindowAndBorrowed` | `FakeA11yNode(..., isVisibleToUser = false)` | `NO_WINDOW` y `root.recycled == false` |
| (g) `identityMismatchFailsNotFound` | 4 casos (`text`, `viewIdResourceName`, `className`, `contentDescription` distintos), siempre en `expectedIdx` | los 4 ⇒ `NOT_FOUND` y `node == null` (10.1.3 estricto) |

Exigido además: `build.gradle.kts` sin cambios de dependencias y los
tests preexistentes (`ClickAncestorTest`, `UiTreeExtractorTest`,
`SelectorResolverTest`, `DisplayScaleTest`, `WsProtocolTest`,
`NatPoliciesTest`, `VolatileEventTest`) **verdes sin editar**.

### 10.5 Restricciones duras y aceptación consolidada

| # | Restricción |
|---|---|
| D1 | **PROHIBIDO `su`**. Gate: `grep -rn 'su -c\|exec(.*su\|ProcessBuilder(.*su' android-app/app/src/` ⇒ **exactamente 1 hit**, el preexistente `shell/ShizukuBridge.kt:118`. Ninguna línea nueva puede añadir hits |
| D2 | `android-app/app/build.gradle.kts` **intacto**: sin Robolectric, sin dependencias nuevas |
| D3 | `typeNode` mantiene `NOT_FOCUSED`; **tap implícito prohibido** |
| D4 | `PROTOCOL.md`, `pkg/`, `register.go` y `cmd/audit-mcp` **sin tocar**. Cero tools nuevas |
| D5 | Geometría en **px lógicos de accesibilidad** (los mismos en `expected.bounds` y `live.boundsInScreen`); `toPhysical` solo en el gesto, nunca en la comparación de deriva |
| D6 | `via` de `tap` ∈ `{action_click, click_ancestor, gesture}`; `via` de `screenshot` ∈ `{takeScreenshot, screencap}` |
| D7 | 100% genérico: cero literales de app, cero literales de paquete |

**Aceptación consolidada P6 (`@judge`, sin editar)**

| # | Comprobación | Resultado exigido |
|---|---|---|
| F1 | `cd android-app && ./gradlew :app:testDebugUnitTest --console=plain` | BUILD SUCCESSFUL; los 7 tests de `LiveNodeReanchorTest` verdes; los preexistentes intactos |
| F2 | `cd android-app && ./gradlew :app:assembleDebug --console=plain` | BUILD SUCCESSFUL |
| F3 | `grep -rn 'su -c\|exec(.*su\|ProcessBuilder(.*su' android-app/app/src/` | **1 línea**: `shell/ShizukuBridge.kt:118`. Ni una más |
| F4 | `grep -n 'findLiveNodeByIndex\|verifySame' android-app/app/src/main/java/dev/jev/jam/service/JevAccessibilityService.kt` | **vacío** |
| F5 | `grep -n '"takeScreenshot"' android-app/app/src/main/java/dev/jev/jam/service/JevAccessibilityService.kt` | el `via` hardcodeado ya no aparece en `screenshotPng` |
| F6 | `git diff -- android-app/app/build.gradle.kts` | vacío |
| F7 | `grep -rni 'robolectric' android-app/app/build.gradle.kts android-app/app/src/` | vacío |
| F8 | `git diff --stat -- pkg/ cmd/` en la raíz | vacío |
| F9 | `go test ./... && go run ./cmd/audit-mcp` en la raíz | tests verdes y **11/11 PASS** |
| F10 | Inspección de `git diff -- android-app/app/src/main/java/dev/jev/jam/`: los tres `return` de `tapLiveNode` colapsan en `via`; el bloque de foco va **antes** del `finally`; `screenshotPng` calcula `via` por SDK | conforme |

**Enmiendas propuestas al orquestador (no aplicadas aquí):**

1. `PROTOCOL.md §4`: documentar `via = "screencap"` como segundo valor de
   `via` en `screenshot`, y `via ∈ {action_click, click_ancestor, gesture}`
   (arrastrada de §8).
2. `PROTOCOL.md §4`: el índice fuera del árbol ahora responde
   `STALE_SNAPSHOT` y no `SELECTOR_NOT_FOUND` (10.1.14).
3. `ARCHITECTURE.md`/`README.md` de `android-app/`: `screenshot` en API 29
   pasa a depender de Shizuku; sin Shizuku el código es
   `SHIZUKU_UNAVAILABLE` (antes `INTERNAL_ERROR`). La lectura (`dump_ui`)
   sigue sin depender de Shizuku.

### 10.6 Riesgos y reversión

| # | Riesgo | Reversión |
|---|---|---|
| R12 | Añadir 2 métodos a `A11yNode` rompe implementaciones futuras | Kotlin admite cuerpo por defecto en interfaces: `fun performFocus(): Boolean = false` / `fun setText(t: CharSequence): Boolean = false` |
| R13 | La identidad incluye `contentDescription` (antes 3 campos): un nodo cuyo `desc` cambia entre dump y acción falla donde antes no. Más `STALE_SNAPSHOT` falsos, nunca acciones sobre el nodo equivocado | quitar una línea de `matchesIdentity` (vuelve a 3 campos) |
| R14 | La tolerancia de 24 px puede anclar a un "gemelo" idéntico si está a >24 px. Mitigado por la regla de unicidad (0 o >1 ⇒ fallo) | bajar `MAX_DRIFT_PX` a `0` (solo EXACT) |
| R15 | `performFocus()` best-effort puede desplazar el foco en un flujo donde Jev solo quería "abrir" un editable. Mitigado: solo tras tap, solo en editables, y `typeNode` sigue exigiendo `isFocused` | borrar el bloque de foco en `tapLiveNode` |
| R16 | El camino `screenshot` en API 29 añade ~200–600 ms y **cambia el código de error** sin Shizuku: `INTERNAL_ERROR` → `SHIZUKU_UNAVAILABLE` | revertir 10.3.1 a `INTERNAL_ERROR` |
| R17 | En superficie `FLAG_SECURE`, `screencap` suele devolver **imagen negra con exit 0**: el decode funciona y el cliente recibe una imagen válida sin saberlo. `SECURE_SURFACE` solo se emite si el decode falla | revertir §10.3 (API 29 sin captura) o aceptar el negro documentado. El camino API 30+ no tiene este problema |
| R18 | Doble compresión en API 29 (PNG de `screencap` → `Bitmap` → recompresión): CPU y RAM extra (`decodeByteArray` de 1080×2400 ≈ 10 MB) | revertir §10.3 |
| R19 | El recorrido completo del BFS en el paso 2 sube la latencia de `tap_node` en el caso "el nodo se movió". El caso rápido (`EXACT`) corta en el índice, como hoy | bajar `maxNodes` (p. ej. `200`) |

## 11. Contrato P5 — Enmascarado de secretos en `candidates`/`render` (cierra R10)

> Redacta `@architect`, implementa `@coder`, certifica `@judge`. Aditivo y de
> capa interna. **Cierra R10** (§9.5): el `text` tipeado de un campo secreto
> ya no aparece en `evidence.candidates` ni en `render`/`FormatState`. **NO**
> cambia el `inputSchema` de las 35 tools (`audit-mcp` 11/11 PASS), **NO**
> escribe a `stdout`, y **NO** altera el golden ni el Python de referencia.
> 100% genérico: cero literales de app.

### 11.0 Superficie real (leída, no inferida)

- `pkg/normalizer/normalizer.go`:
  - `PassMask = "a password, not read"` (~32); `PasswordMarkers =
    [password, passwd, passcode, pin, credential]` (~61).
  - `Candidate{...}` + `Compact()` (~103-122); `Normalize(...)` (~339-383).
  - `theFocusedField` (~227) usa `isPassword(class,rid,hint,desc)` +
    propiedad nativa `password`/`is_password` (§9.1).
  - `BuildTable` (~496) fija `Row.Label = c.Compact()` y `Row.Text = c.Text`;
    `SerializeTable` emite `[idx,class_short,zone,flags,label]` (~524).
- `pkg/tools/helpers.go`: `readScreenState()` (~302-312) arma `candidates`
  inline con `"label": cd.Compact()` y `"text": cd.Text` (fuga de R10).

### 11.1 P5-a — detección `isPasswordNode(n)` (única fuente de verdad)

`isPasswordNode(n map[string]any) bool` = **`editable` obligatorio** y, dentro
de él, propiedad nativa `password`/`is_password` **o** marcador de
`PasswordMarkers` en `class`/`resource_id`/`hint`/`content_desc` (reusa
`isPassword`). `theFocusedField` pasa a invocarla (antes duplicaba el criterio).
La exigencia de `editable` es **funcional, no cosmética**: un secreto tipeado
solo vive en un input; sin ella, badges/indicadores no editables como
`resource_id=…/pin_indicator` (presentes en `wa_home.json`) darían falso
positivo y romperían la paridad golden.

### 11.2 P5-b — enmascarado en `Compact()` y `SafeText()`

1. `Candidate` gana el campo aditivo `Secret bool`, fijado en `Normalize` con
   `isPasswordNode(n)`.
2. `Compact()`: si `Secret`, **nunca** renderiza `c.Text`; muestra la etiqueta
   derivada `secretLabel(Desc,ResourceID,ID)` = `content_desc` →
   basename(`resource_id`) → `id` → `SecretMask = "••••"`.
3. Nuevo `SafeText() string`: `SecretMask` si `Secret && Text != ""`; si no,
   `Text`. Es la superficie para `evidence.candidates["text"]`.
4. `pkg/tools/helpers.go`: `"text": cd.SafeText()` (antes `cd.Text`). El resto
   de claves de `candidates` no cambia.

### 11.3 Restricciones duras (idénticas a §8/§9)

| # | Regla |
|---|---|
| E1 | `inputSchema` de las 35 tools sin cambios → `audit-mcp` 11/11 PASS |
| E2 | Cero `fmt.Print*`/`os.Stdout` en el código tocado (solo `slog` a stderr) |
| E3 | `FormatCandidateLabel` y `testdata/replay_expected.json` **intactos**. `Compact` **sí** cambia (ahora enmascara), pero **solo** para nodos `Secret`; el golden no contiene ninguno ⇒ `TestReplayPythonParity` sigue PASS |
| E4 | Cero literales de app; sin dependencias nuevas (`go.mod` no cambia) |
| E5 | El secreto nunca se deriva de `Text` para etiquetas (mismo criterio que §9.1) |

### 11.4 Aceptación (`@judge`)

| # | Comprobación | Resultado exigido |
|---|---|---|
| G1 | `go test ./...` | verde (incluye P5 y P4) |
| G2 | `go test ./pkg/normalizer/ -run TestReplayPythonParity -v` | `wa_home`/`jam_live_18` paridad exacta |
| G3 | `go run ./cmd/audit-mcp` | `AUDIT OK: 11/11 PASS` |
| G4 | Test P5: editable con secreto (nativo o marcador) | `focused_field.AsView()` sin secreto; `render` sin el secreto; `SerializeTable` sin el secreto; `SafeText()=="••••"` |
| G5 | `git diff --stat -- pkg/ cmd/` | solo `pkg/normalizer/` y `pkg/tools/helpers.go` |

### 11.5 Riesgos y reversión

| # | Riesgo | Reversión |
|---|---|---|
| R20 | El gate `editable` deja sin enmascarar un secreto en un nodo no editable (poco realista) | quitar el gate en `isPasswordNode` (asumiendo el falso positivo `pin_indicator`) |
| R21 | `Compact()` enmascarado propaga a `Row.Label`/`SerializeTable` para nodos `Secret`: si el golden algún día incluyera uno, fallaría la paridad | regenerar golden con el mismo criterio de enmascarado (o revertir 11.2) |
| R22 | `SafeText()` sustituye por un literal fijo: el modelo pierde longitud/forma del secreto (intencional) | devolver `secretLabel(...)` también en `SafeText` |
