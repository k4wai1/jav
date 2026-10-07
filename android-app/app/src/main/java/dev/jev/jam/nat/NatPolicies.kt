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

    /** Apertura/pre-relleno (P0) vs envío crítico (confirm). */
    fun isCritical(action: String, uri: String): Boolean {
        if (action in CRITICAL_ACTIONS) return true
        val scheme = uri.substringBefore(":", "").lowercase()
        if (scheme in SEND_SCHEMES &&
            (action == "android.intent.action.VIEW" || action in CRITICAL_ACTIONS)
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

    /** Ventana de `get_app_usage`: 1..24 h (spec §5). */
    fun clampHours(h: Int): Int = h.coerceIn(1, 24)

    /** Ventana de `list_events`: máx. 7 días por defecto (spec §8). */
    const val MAX_WINDOW_MS = 7L * 24 * 60 * 60 * 1000

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
