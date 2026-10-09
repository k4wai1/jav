package dev.jev.jam.nat

/**
 * Reglas puras del catálogo native-apis (sin framework Android).
 * Testeables en JVM (`NatPoliciesTest`). El dispatcher las aplica;
 * la política de scopes vive en PROTOCOL (la anota @architect).
 */
object NatPolicies {

    /** Acciones que envían/comunican/pagan/borran headless → `confirm: true`. */
    val CRITICAL_ACTIONS = setOf(
        "android.intent.action.SEND",
        "android.intent.action.SENDTO",
        "android.intent.action.SEND_MULTIPLE",
        "android.intent.action.CALL"
    )

    /** Esquemas de URI que comunican cuando van con acción de envío. */
    val SEND_SCHEMES = setOf("sms", "smsto", "mms", "mmsto", "tel", "mailto")

    /**
     * Canonicaliza una acción de intent a su forma `android.intent.action.X`.
     * Estricta: trim + uppercase; acepta `SEND`, `ACTION_SEND`, `ACTION.SEND`,
     * `action.send`, `.SEND` y la forma completa con/sin prefijo
     * `android.intent.` (cualquier caja) → `android.intent.action.SEND`.
     * Igual para CALL, VIEW, SENDTO, SEND_MULTIPLE y DIAL. Desconocidas:
     * devuelve el input con trim (sin inventar).
     */
    fun canonicalizeAction(raw: String): String {
        val t = raw.trim().uppercase()
        if (t.isEmpty()) return ""
        var core = t
        // Prefijo `android.intent.` opcional (cubre `action.*` y `action_*`).
        if (core.startsWith("ANDROID.INTENT.")) {
            core = core.removePrefix("ANDROID.INTENT.")
        }
        core = when {
            core.startsWith("ACTION_") -> core.removePrefix("ACTION_")
            core.startsWith("ACTION.") -> core.removePrefix("ACTION.")
            core.startsWith(".") -> core.removePrefix(".")
            else -> core
        }
        return when (core) {
            "SEND", "SENDTO", "SEND_MULTIPLE", "CALL", "VIEW", "DIAL" ->
                "android.intent.action.$core"
            else -> raw.trim()
        }
    }

    /** Apertura/pre-relleno (P0) vs envío crítico (confirm). */
    fun isCritical(action: String, uri: String): Boolean {
        val a = canonicalizeAction(action)
        if (a in CRITICAL_ACTIONS) return true
        val scheme = uri.substringBefore(":", "").lowercase()
        if (scheme in SEND_SCHEMES &&
            (a == "android.intent.action.VIEW" || a in CRITICAL_ACTIONS)
        ) return true
        return false
    }

    /** Forma `a.b.c` para paquetes (igual que open_app/force_stop). */
    private val PKG_RE = Regex("^[a-zA-Z][a-zA-Z0-9_]*(\\.[a-zA-Z][a-zA-Z0-9_]*)+$")

    fun validPackage(pkg: String): Boolean = PKG_RE.matches(pkg)

    /** Esquemas aceptados por `open_url` (apertura, sin envío). */
    val URL_SCHEMES = setOf("http", "https", "tel", "mailto", "sms", "smsto", "geo")

    fun validUrl(url: String): Boolean {
        val scheme = url.substringBefore(":", "").lowercase()
        return scheme in URL_SCHEMES && url.length > scheme.length + 1
    }

    /** Milisegundos de una hora. */
    const val HOUR_MS = 3_600_000L

    /** Ventana de `get_app_usage` sin `window`: 1..24 h (spec §5, compat). */
    fun clampHours(h: Int): Int = h.coerceIn(1, 24)

    /** Ventana `raw` de `get_app_usage`: `hours` hasta 7 días (168 h). */
    fun clampRawHours(h: Int): Int = h.coerceIn(1, 168)

    /** Ventana de `list_events`: máx. 7 días por defecto (spec §8). */
    const val MAX_WINDOW_MS = 7L * 24 * 60 * 60 * 1000

    /** `window` aceptados por `get_app_usage` (null = compat `hours`). */
    val USAGE_WINDOWS = setOf("today", "week", "raw")

    fun validUsageWindow(w: String?): Boolean = w == null || w in USAGE_WINDOWS

    /**
     * Medianoche local del día de `now` (puro JVM, sin framework Android).
     * Se usa `Calendar` para respetar la zona horaria del dispositivo.
     */
    fun localMidnight(now: Long): Long {
        val c = java.util.Calendar.getInstance()
        c.timeInMillis = now
        c.set(java.util.Calendar.HOUR_OF_DAY, 0)
        c.set(java.util.Calendar.MINUTE, 0)
        c.set(java.util.Calendar.SECOND, 0)
        c.set(java.util.Calendar.MILLISECOND, 0)
        return c.timeInMillis
    }

    /**
     * `begin` (ms) de la ventana de `get_app_usage`:
     *  - null       → `hours` 1..24 (comportamiento previo)
     *  - `today`    → medianoche local de hoy
     *  - `week`     → hace 7 días
     *  - `raw`      → `hours` 1..168
     * Puro y determinista; `now` inyectable para test.
     */
    fun usageBegin(now: Long, window: String?, hours: Int): Long = when (window) {
        "today" -> localMidnight(now)
        "week" -> now - MAX_WINDOW_MS
        "raw" -> now - clampRawHours(hours) * HOUR_MS
        else -> now - clampHours(hours) * HOUR_MS
    }

    fun windowOk(rangeMs: Long): Boolean = rangeMs in 1..MAX_WINDOW_MS

    /** `settings_put`: solo namespace `system` (P1). Secure/Global → N2 (Fase 6+). */
    fun putAllowed(namespace: String): Boolean = namespace == "system"

    fun getAllowed(namespace: String): Boolean =
        namespace == "system" || namespace == "secure" || namespace == "global"

    /** Proyección mínima PII: trunca texto de terceros (notificaciones). */
    fun truncate(s: String, max: Int): String =
        if (s.length <= max) s else s.take(max)

    const val NOTIF_TEXT_MAX = 200
}
