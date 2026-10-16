package dev.k4wai1.jav.socket

/**
 * Fase 2b (AGENTS.md §3.5): lockout de autenticación por origen.
 *
 * Puro JVM y thread-safe para poder testearse en JUnit con reloj inyectado.
 * Regla: 5 fallos de `hello` (`UNAUTHORIZED`) del mismo `origin` en una
 * ventana de 60 s → bloqueo de 5 min. Un `hello` exitoso limpia la ventana.
 *
 * No conoce el token ni el socket: solo cuenta fallos por clave de origen
 * (`loopback` o IP, tal como los entrega `JamWsServer.originOf`).
 */
object AuthLockout {

    const val MAX_FAILS = 5
    const val WINDOW_MS = 60_000L
    const val LOCK_MS = 300_000L

    private class State {
        val fails = ArrayDeque<Long>()
        var lockedUntilMs = 0L
    }

    private val byOrigin = HashMap<String, State>()

    /** ¿El origen está bloqueado en `nowMs`? */
    @Synchronized
    fun isLocked(origin: String, nowMs: Long = System.currentTimeMillis()): Boolean {
        val s = byOrigin[origin] ?: return false
        return nowMs < s.lockedUntilMs
    }

    /** ms restantes de bloqueo (0 si no está bloqueado). */
    @Synchronized
    fun retryAfterMs(origin: String, nowMs: Long = System.currentTimeMillis()): Long {
        val s = byOrigin[origin] ?: return 0L
        val left = s.lockedUntilMs - nowMs
        return if (left > 0) left else 0L
    }

    /**
     * Registra un fallo de `hello`. Devuelve `true` si tras este fallo el
     * origen queda bloqueado (5.º fallo dentro de la ventana). Un origen ya
     * bloqueado no acumula más estado: se devuelve `true` sin tocar el reloj.
     */
    @Synchronized
    fun recordFailure(origin: String, nowMs: Long = System.currentTimeMillis()): Boolean {
        val s = byOrigin.getOrPut(origin) { State() }
        if (nowMs < s.lockedUntilMs) return true
        // Ventana deslizante: descartar fallos fuera de 60 s.
        while (s.fails.isNotEmpty() && nowMs - s.fails.first() > WINDOW_MS) {
            s.fails.removeFirst()
        }
        s.fails.addLast(nowMs)
        if (s.fails.size >= MAX_FAILS) {
            s.lockedUntilMs = nowMs + LOCK_MS
            s.fails.clear()
            return true
        }
        return false
    }

    /** Un `hello` exitoso limpia la ventana de fallos de ese origen. */
    @Synchronized
    fun recordSuccess(origin: String) {
        byOrigin.remove(origin)
    }

    /** Solo para tests: deja el estado limpio. */
    @Synchronized
    fun clear() {
        byOrigin.clear()
    }
}
