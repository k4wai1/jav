package dev.jev.jam.shell

import java.security.MessageDigest

/**
 * Política pura de `shell` (100% JVM, sin framework Android → testeable).
 * Clasifica comandos y aplica el rate limit específico de `shell`
 * (AGENTS.md §3.6: 5 req/s, independiente del 50 req/s general del WS).
 *
 * Denylist de irreversibles (AGENTS.md §3.7). Un comando de la denylist
 * exige `confirm: true` (scope admin); matar/desinstalar Jam es siempre
 * `FORBIDDEN_SELF`.
 */
object ShellPolicy {

    enum class PolicyVerdict { ALLOWED, NEEDS_CONFIRM, FORBIDDEN_SELF }

    /** Claves de `settings put secure`/`global` que rompen a la propia Jam. */
    private val CRITICAL_SETTINGS_KEYS = setOf(
        "enabled_accessibility_services",
        "accessibility_enabled",
        "enabled_notification_listeners"
    )

    /** `true` si `key` es una clave crítica de `settings put` (self-protect). */
    fun isCriticalSettingsKey(key: String): Boolean =
        key.trim().lowercase() in CRITICAL_SETTINGS_KEYS

    /** Normaliza para el match: minúsculas + espacios colapsados. */
    fun normalize(cmd: String): String =
        cmd.lowercase().replace(Regex("\\s+"), " ").trim()

    /**
     * Clasifica un comando de shell.
     *  - `FORBIDDEN_SELF`: mata/desinstala/deshabilita la propia Jam.
     *  - `NEEDS_CONFIRM`: coincidencia con la denylist de irreversibles.
     *  - `ALLOWED`: el resto.
     */
    fun classify(cmd: String): PolicyVerdict {
        val n = normalize(cmd)
        if (n.isEmpty()) return PolicyVerdict.ALLOWED
        if (isSelfHarm(n)) return PolicyVerdict.FORBIDDEN_SELF
        if (isDenylisted(n)) return PolicyVerdict.NEEDS_CONFIRM
        return PolicyVerdict.ALLOWED
    }

    /** Motivo legible de la denylist (para el preview); null si no aplica. */
    fun denylistReason(cmd: String): String? {
        val n = normalize(cmd)
        return when {
            isSelfHarm(n) -> "self_package"
            isDenylisted(n) -> "denylist_irreversible"
            else -> null
        }
    }

    private const val SELF = "dev.jev.jam"

    private fun isSelfHarm(n: String): Boolean {
        if (SELF !in n) return false
        val verbs = listOf(
            "pm uninstall", "cmd package uninstall", "uninstall",
            "force-stop", "force stop", "am force-stop", "am kill", "killall",
            "disable", "pm disable", "cmd package disable"
        )
        return verbs.any { it in n }
    }

    private fun isDenylisted(n: String): Boolean {
        // rm con -r y -f (cualquier orden) sobre raíz o glob.
        if (Regex("""\brm\b[^|;&]*\s-[a-z]*r[a-z]*f[a-z]*\b""").containsMatchIn(n) ||
            Regex("""\brm\b[^|;&]*\s-[a-z]*f[a-z]*r[a-z]*\b""").containsMatchIn(n)
        ) {
            if (Regex("""\brm\b[^|;&]*\s(/|/\*|/\s|\*)""").containsMatchIn(n)) return true
        }
        // rm -rf / (forma exacta explícita en AGENTS §3.7).
        if (Regex("""\brm\s+-rf\s+/(\s|$)""").containsMatchIn(n)) return true
        // Uninstall de paquetes (de sistema); self ya se filtró antes.
        if ("pm uninstall" in n || "cmd package uninstall" in n) return true
        // reboot a recuperación/bootloader/fastboot.
        if ("reboot recovery" in n || "reboot bootloader" in n ||
            "reboot fastboot" in n
        ) return true
        // dd / mkfs / wipe (irreversibles de disco/partición).
        if (Regex("""\bdd\b[^|;&]*\bof=""").containsMatchIn(n)) return true
        if (Regex("""\bmkfs(\.\w+)?\b""").containsMatchIn(n)) return true
        if (Regex("""\bwipe\b""").containsMatchIn(n)) return true
        // settings put secure/global de una clave crítica (auto-desconectar a11y).
        val sp = Regex("""\bsettings\s+put\s+(secure|global)\s+(\S+)""").find(n)
        if (sp != null && isCriticalSettingsKey(sp.groupValues[2])) return true
        return false
    }

    fun sha256Hex(s: String): String {
        val d = MessageDigest.getInstance("SHA-256").digest(s.toByteArray(Charsets.UTF_8))
        return d.joinToString("") { "%02x".format(it) }
    }

    /** Prefijo seguro del comando para UI: máx `max` chars. */
    fun previewPrefix(cmd: String, max: Int = 80): String =
        if (cmd.length <= max) cmd else cmd.take(max) + "…"

    /**
     * Rate limit de ventana deslizante (puro, `nowMs` inyectable).
     * `shell` = 5 req/s (AGENTS §3.6).
     */
    class SlidingWindowRateLimiter(
        private val max: Int,
        private val windowMs: Long
    ) {
        private val stamps = ArrayDeque<Long>()

        @Synchronized
        fun allow(nowMs: Long): Boolean {
            while (stamps.isNotEmpty() && nowMs - stamps.first() > windowMs) {
                stamps.removeFirst()
            }
            if (stamps.size >= max) return false
            stamps.addLast(nowMs)
            return true
        }
    }

    /** Instancia única del rate limit de `shell` (5 req/s). */
    val RATE = SlidingWindowRateLimiter(max = 5, windowMs = 1000L)

    fun allowRequest(nowMs: Long = System.currentTimeMillis()): Boolean = RATE.allow(nowMs)
}
