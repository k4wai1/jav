package dev.k4wai1.jav.socket

import dev.k4wai1.jav.util.JevLog
import java.net.InetSocketAddress
import java.util.ArrayDeque
import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.Executors
import java.util.concurrent.TimeUnit
import javax.net.ssl.SSLContext
import org.java_websocket.WebSocket
import org.java_websocket.handshake.ClientHandshake
import org.java_websocket.server.DefaultSSLWebSocketServerFactory
import org.java_websocket.server.WebSocketServer

/**
 * Estado compartido entre listeners (loopback `ws://` + tailnet `wss://`,
 * Fase 2b): política **single-client** global (AGENTS.md §6) y scopes
 * autenticados, de modo que un cliente en el tailnet y otro en loopback
 * no conviven y `revokeAll` alcanza a ambos.
 */
class ClientRegistry {
    @Volatile
    var active: WebSocket? = null
    val authedScopes = ConcurrentHashMap<WebSocket, Set<String>>()
}

/**
 * Servidor WS/WSS. Bind por defecto `127.0.0.1:38472`; Fase 2b añade un
 * segundo listener bindeado a la IP del tailnet con `SSLContext` (WSS
 * obligatorio fuera de loopback, AGENTS.md §3.2). **Nunca `0.0.0.0`.**
 * Frame máximo 4 MiB, rate limit 50 req/s, `hello` obligatorio < 10 s.
 */
class JamWsServer(
    private val port: Int,
    private val dispatcher: CommandDispatcher,
    bindAddress: String = LOOPBACK,
    sslContext: SSLContext? = null,
    private val registry: ClientRegistry = ClientRegistry(),
    private val label: String = bindAddress
) : WebSocketServer(InetSocketAddress(bindAddress, port)) {

    init {
        if (sslContext != null) {
            setWebSocketFactory(DefaultSSLWebSocketServerFactory(sslContext))
        }
    }

    private val rateBuckets = ConcurrentHashMap<WebSocket, ArrayDeque<Long>>()
    private val scheduler = Executors.newSingleThreadScheduledExecutor()
    private val secure: Boolean = sslContext != null

    @Volatile
    var running: Boolean = false
        private set

    override fun onStart() {
        running = true
        JevLog.i(TAG, "JamWs ON $label:$port" + if (secure) " (wss)" else " (ws)")
    }

    override fun onOpen(conn: WebSocket, handshake: ClientHandshake) {
        val from = try {
            conn.remoteSocketAddress?.toString()
        } catch (t: Throwable) {
            "?"
        }
        synchronized(registry) {
            val cur = registry.active
            if (cur != null && cur.isOpen && cur !== conn) {
                conn.send(errResponse(null, "server busy", "BUSY"))
                conn.close(4001, "BUSY")
                return
            }
            registry.active = conn
        }
        JevLog.i(TAG, "cliente conectado desde $from ($label)")
        scheduler.schedule({
            if (!registry.authedScopes.containsKey(conn) && conn.isOpen) {
                conn.send(errResponse(null, "hello requerido en <10s", "UNAUTHORIZED"))
                conn.close(4401, "UNAUTHORIZED")
            }
        }, HELLO_TIMEOUT_MS, TimeUnit.MILLISECONDS)
    }

    override fun onClose(conn: WebSocket, code: Int, reason: String, remote: Boolean) {
        registry.authedScopes.remove(conn)
        rateBuckets.remove(conn)
        synchronized(registry) {
            if (registry.active === conn) registry.active = null
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
            val (scopes, frame) = dispatcher.hello(req, originOf(conn))
            if (scopes != null) registry.authedScopes[conn] = scopes
            conn.send(frame)
            return
        }
        val scopes = registry.authedScopes[conn]
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
            conn.send(dispatcher.dispatch(req, scopes, originOf(conn)))
        } catch (t: Throwable) {
            JevLog.e(TAG, "dispatch falló", t)
            conn.send(errResponse(req.id, "error interno", "INTERNAL_ERROR"))
        }
    }

    /** Origen sanitizado para el audit: `loopback` o IP (sin puerto efímero). */
    private fun originOf(conn: WebSocket): String {
        return try {
            val addr = conn.remoteSocketAddress ?: return "?"
            if (addr.address?.isLoopbackAddress == true) "loopback"
            else addr.address?.hostAddress ?: "?"
        } catch (t: Throwable) {
            "?"
        }
    }

    override fun onError(conn: WebSocket?, ex: Exception) {
        JevLog.e(TAG, "WS error", ex)
    }

    /** Emite un evento al cliente autenticado (de cualquier listener). */
    fun broadcastEvent(frame: String) {
        val conn = registry.active
        if (conn != null && conn.isOpen && registry.authedScopes.containsKey(conn)) {
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
    fun clientCount(): Int = synchronized(registry) {
        val c = registry.active
        if (c != null && c.isOpen) 1 else 0
    }

    /**
     * ¿El cliente activo está autenticado? null = sin cliente.
     * Usado por la tarjeta 1 y como gate de regeneración (tarjeta 3).
     */
    fun clientAuthed(): Boolean? {
        val c = synchronized(registry) { registry.active } ?: return null
        if (!c.isOpen) return null
        return registry.authedScopes.containsKey(c)
    }

    /**
     * jam-ui-redesign tarjeta 3: invalida `authedScopes` tras regenerar
     * el token; desconecta al cliente con `UNAUTHORIZED` limpio.
     */
    fun revokeAll() {
        val conns = registry.authedScopes.keys.toList()
        registry.authedScopes.clear()
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
        const val LOOPBACK = "127.0.0.1"
        const val MAX_FRAME = 4 * 1024 * 1024
        private const val MAX_RPS = 50
        private const val HELLO_TIMEOUT_MS = 10_000L
        private const val SHUTDOWN_TIMEOUT_MS = 1000L
    }
}
