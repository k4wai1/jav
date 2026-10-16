package dev.k4wai1.jav.socket

import java.security.MessageDigest
import java.util.ArrayDeque
import kotlinx.serialization.Serializable

/**
 * Entrada del audit ring (AGENTS.md §3.8). NUNCA guarda argumentos,
 * texto ni token en claro: solo el hash SHA-256 (16 hex) de los params
 * y el origen sanitizado.
 */
@Serializable
data class AuditEntry(
    val seq: Long,
    val ts: Long,
    val method: String,
    val scope: String,
    val args_sha256: String,
    val result: String,
    val origin: String
)

/**
 * Fase 6a: audit log en dispositivo, ring buffer de [MAX_ENTRIES]
 * entradas, puro JVM (sin Android → test JVM directo). Escritura
 * O(1) y consulta O(n≤500); seguridad por lock, no por copia.
 */
object AuditLog {

    const val MAX_ENTRIES = 500

    private val lock = Any()
    private val buffer = ArrayDeque<AuditEntry>(MAX_ENTRIES)
    private var seq: Long = 0L

    /**
     * Registra un método con su resultado real. `argsRaw` es el
     * `params.toString()`; se reduce a [hashArgs] antes de almacenar.
     */
    fun record(
        method: String,
        scope: String,
        argsRaw: String,
        result: String,
        origin: String,
        ts: Long = System.currentTimeMillis()
    ): AuditEntry {
        val entry: AuditEntry
        synchronized(lock) {
            seq += 1
            entry = AuditEntry(
                seq = seq,
                ts = ts,
                method = method,
                scope = scope,
                args_sha256 = hashArgs(argsRaw),
                result = result,
                origin = origin
            )
            buffer.addLast(entry)
            while (buffer.size > MAX_ENTRIES) buffer.removeFirst()
        }
        return entry
    }

    /**
     * Entradas con `seq > sinceSeq`, las más recientes al final.
     * Devuelve como máximo `limit` (las últimas del subconjunto).
     */
    fun list(limit: Int = 50, sinceSeq: Long = 0L): List<AuditEntry> {
        val bounded = if (limit < 1) 1 else limit
        synchronized(lock) {
            val filtered = ArrayList<AuditEntry>(buffer.size)
            for (e in buffer) if (e.seq > sinceSeq) filtered.add(e)
            if (filtered.size <= bounded) return filtered
            return filtered.subList(filtered.size - bounded, filtered.size)
        }
    }

    /** Vacía el ring y reinicia la secuencia (uso de test/administración). */
    fun clear() {
        synchronized(lock) {
            buffer.clear()
            seq = 0L
        }
    }

    fun size(): Int = synchronized(lock) { buffer.size }

    /** Primeros 16 hex del SHA-256 de los params; jamás el texto en claro. */
    fun hashArgs(raw: String): String = try {
        val d = MessageDigest.getInstance("SHA-256").digest(raw.toByteArray(Charsets.UTF_8))
        d.take(8).joinToString("") { "%02x".format(it) }
    } catch (t: Throwable) {
        "?"
    }
}
