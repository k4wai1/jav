package dev.jev.jam.socket

import dev.jev.jam.util.JevLog
import java.net.InetSocketAddress
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import org.java_websocket.WebSocket
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.server.WebSocketServer

/**
 * Servidor WS loopback (Fase 2). Un solo listener `127.0.0.1:38472`;
 * el listener WSS del tailnet llega en Fase 2b. Single-client (`BUSY`),
 * `hello` obligatorio < 10 s, frame máximo 4 MiB, rate limit 50 req/s.
 * Los mensajes se procesan en serie en el hilo del socket (los requests
 * del cliente son secuenciales por diseño del protocolo).
 */
class JamWsServer(
    private val port: Int,
    private val dispatcher: CommandDispatcher
) : WebSocketServer(InetSocketAddress("127.0.0.1", port)) {

    @Volatile
    private var active: WebSocket? = null
    private val authedScopes = ConcurrentHashMap<WebSocket, Set<String>>()
    private val rateBuckets = ConcurrentHashMap<WebSocket, ArrayDeque<Long>>()
    private val scheduler = Executors.newSingleThreadScheduledExecutor()

    @Volatile
    var running: Boolean = false
        private set

    override fun onStart() {
        running = true
        JevLog.i(TAG, "JamWs ON 127.0.0.1:$port")
    }

    override fun onOpen(conn: WebSocket, handshake: ClientHandshake) {
        val from = try {
            conn.remoteSocketAddress?.toString()
        } catch (t: Throwable) {
            "?"
        }
        synchronized(this) {
            val cur = active
            if (cur != null && cur.isOpen && cur !== conn) {
                conn.send(errResponse(null, "server busy", "BUSY"))
                conn.close(4001, "BUSY")
                return
            }
            active = conn
        }
        JevLog.i(TAG, "cliente conectado desde $from")
        scheduler.schedule({
            if (!authedScopes.containsKey(conn) && conn.isOpen) {
                conn.send(errResponse(null, "hello requerido en <10s", "UNAUTHORIZED"))
                conn.close(4401, "UNAUTHORIZED")
            }
        }, HELLO_TIMEOUT_MS, TimeUnit.MILLISECONDS)
    }

    override fun onClose(conn: WebSocket, code: Int, reason: String, remote: Boolean) {
        authedScopes.remove(conn)
        rateBuckets.remove(conn)
        synchronized(this) {
            if (active === conn) active = null
        }
        JevLog.i(TAG, "cliente desconectado ($reason)")
    }

    override fun onMessage(conn: WebSocket, message: String) {
        if (message.length > MAX_FRAME) {
            conn.send(errResponse(null, "frame excede 4 MiB", "PAYLOAD_TOO_LARGE"))
            return
        }
        val req = try {
            JamJson.decodeFromString(WsRequest.serializer(), message)
        } catch (t: Throwable) {
            conn.send(errResponse(null, "JSON inválido", "VALIDATION_ERROR"))
            return
        }
        if (req.method == "hello") {
            val (scopes, frame) = dispatcher.hello(req)
            if (scopes != null) authedScopes[conn] = scopes
            conn.send(frame)
            return
        }
        val scopes = authedScopes[conn]
        if (scopes == null) {
            conn.send(errResponse(req.id, "sin hello previo", "UNAUTHORIZED"))
            conn.close(4401, "UNAUTHORIZED")
            return
        }
        if (!checkRate(conn)) {
            conn.send(errResponse(req.id, "rate limit 50 req/s", "RATE_LIMITED"))
            return
        }
        try {
            conn.send(dispatcher.dispatch(req, scopes))
        } catch (t: Throwable) {
            JevLog.e(TAG, "dispatch falló", t)
            conn.send(errResponse(req.id, "error interno", "INTERNAL_ERROR"))
        }
    }

    override fun onError(conn: WebSocket?, ex: Exception) {
        JevLog.e(TAG, "WS error", ex)
    }

    /** Emite un evento al cliente autenticado, si lo hay. */
    fun broadcastEvent(frame: String) {
        val conn = active
        if (conn != null && conn.isOpen && authedScopes.containsKey(conn)) {
            try {
                conn.send(frame)
            } catch (t: Throwable) {
                JevLog.e(TAG, "broadcast falló", t)
            }
        }
    }

    /**
     * jam-ui-redesign tarjeta 1: 0/1 sin identidad (nunca token ni IP
     * en UI; el origen queda en el audit ring, no en pantalla).
     */
    fun clientCount(): Int = synchronized(this) {
        val c = active
        if (c != null && c.isOpen) 1 else 0
    }

    /**
     * ¿El cliente activo está autenticado? null = sin cliente.
     * Usado por la tarjeta 1 y como gate de regeneración (tarjeta 3).
     */
    fun clientAuthed(): Boolean? {
        val c = synchronized(this) { active } ?: return null
        if (!c.isOpen) return null
        return authedScopes.containsKey(c)
    }

    /**
     * jam-ui-redesign tarjeta 3: invalida `authedScopes` tras regenerar
     * el token; desconecta al cliente con `UNAUTHORIZED` limpio.
     * Normalmente no hay cliente autenticado (el gate lo impide), pero
     * se limpian restos (conexiones sin hello, sockets medio cerrados).
     */
    fun revokeAll() {
        val conns = authedScopes.keys.toList()
        authedScopes.clear()
        for (conn in conns) {
            try {
                if (conn.isOpen) conn.send(errResponse(null, "token regenerado", "UNAUTHORIZED"))
            } catch (t: Throwable) {
                JevLog.e(TAG, "revoke send falló", t)
            }
            try {
                conn.close(4401, "UNAUTHORIZED")
            } catch (t: Throwable) {
                JevLog.e(TAG, "revoke close falló", t)
            }
        }
    }

    fun shutdown() {
        try {
            scheduler.shutdownNow()
        } catch (t: Throwable) {
            JevLog.e(TAG, "scheduler no paró", t)
        }
        try {
            stop(SHUTDOWN_TIMEOUT_MS.toInt())
        } catch (t: InterruptedException) {
            Thread.currentThread().interrupt()
        } catch (t: Throwable) {
            JevLog.e(TAG, "stop falló", t)
        }
        running = false
    }

    private fun checkRate(conn: WebSocket): Boolean {
        val now = System.currentTimeMillis()
        val q = rateBuckets.computeIfAbsent(conn) { ArrayDeque() }
        synchronized(q) {
            while (q.isNotEmpty() && now - q.peekFirst() > 1000) q.removeFirst()
            if (q.size >= MAX_RPS) return false
            q.addLast(now)
            return true
        }
    }

    companion object {
        private const val TAG = "JamWs"
        const val MAX_FRAME = 4 * 1024 * 1024
        private const val MAX_RPS = 50
        private const val HELLO_TIMEOUT_MS = 10_000L
        private const val SHUTDOWN_TIMEOUT_MS = 1000L
    }
}
