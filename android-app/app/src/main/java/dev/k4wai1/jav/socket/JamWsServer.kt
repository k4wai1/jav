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
 * Estado compartido entre listeners (loopback `ws://` + WSS tailnet/LAN):
 * política **single-client** global (AGENTS.md §6) y scopes autenticados.
 *
 * v2.2.0: la consulta y la revocación viven aquí para que funcionen igual
 * si el cliente entró por loopback, Tailscale o Wi-Fi (antes solo se
 * miraba el listener loopback). `revokeAll` alcanza a todos.
 */
class ClientRegistry {
    /** Slot single-client: última conexión que posee el canal. */
    @Volatile
    var active: WebSocket? = null

    /**
     * v2.1.0: conexión nueva esperando `hello` mientras el slot está
     * ocupado por un cliente autenticado. No se corta al recién llegado:
     * si prueba credenciales válidas, evicta al anterior; si no, se cierra
     * solo él y el cliente legítimo sigue intacto.
     */
    @Volatile
    var candidate: WebSocket? = null
    val authedScopes = ConcurrentHashMap<WebSocket, Set<String>>()

    /** Clientes activos: 0/1 sin identidad (cualquier listener). */
    fun clientCount(): Int = synchronized(this) {
        val c = active
        if (c != null && c.isOpen) 1 else 0
    }

    /** ¿El cliente activo está autenticado? null = sin cliente. */
    fun clientAuthed(): Boolean? = synchronized(this) {
        val c = active
        when {
            c == null -> null
            !c.isOpen -> null
            else -> authedScopes.containsKey(c)
        }
    }

    /** Emite un evento al cliente autenticado, sea cual sea el listener. */
    fun broadcastEvent(frame: String) {
        val conn = active ?: return
        if (!conn.isOpen || !authedScopes.containsKey(conn)) return
        try {
            conn.send(frame)
        } catch (t: Throwable) {
            JevLog.e(TAG, "broadcast falló", t)
        }
    }

    /**
     * v2.2.0: revoca todas las sesiones (autenticadas o no) de cualquier
     * listener: limpia scopes, olvida candidate/active y cierra con
     * `UNAUTHORIZED` limpio. Necesario tras regenerar el token o el Kill
     * Switch.
     */
    fun revokeAll() {
        val conns = LinkedHashSet<WebSocket>()
        synchronized(this) {
            conns.addAll(authedScopes.keys)
            candidate?.let { conns.add(it) }
            active?.let { conns.add(it) }
            authedScopes.clear()
            candidate = null
            active = null
        }
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

    private companion object {
        private const val TAG = "JamWs"
    }
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
    private val label: String = bindAddress,
    private val onTraffic: (() -> Unit)? = null
) : WebSocketServer(InetSocketAddress(bindAddress, port)) {

    init {
        if (sslContext != null) {
            setWebSocketFactory(DefaultSSLWebSocketServerFactory(sslContext))
        }
        // v2.1.0: ping-pong automático de Java-WebSocket. Una conexión
        // muerta (sin pong) se detecta en ~10 s, liberando el slot
        // single-client; antes quedaba en BUSY hasta el timeout TCP (~2 min).
        connectionLostTimeout = PING_INTERVAL_S
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
        var evicted: WebSocket? = null
        synchronized(registry) {
            val cur = registry.active
            when {
                cur == null || !cur.isOpen -> registry.active = conn
                cur === conn -> {}
                registry.authedScopes.containsKey(cur) -> {
                    // Cliente autenticado vivo: no se corta ni al nuevo ni
                    // al anterior en onOpen. El nuevo debe probar `hello`
                    // válido para evictar (onMessage); si falla, se cierra
                    // solo él y el legítimo conserva el slot.
                    val pending = registry.candidate
                    if (pending != null && pending !== conn && pending.isOpen) {
                        evicted = pending
                    }
                    registry.candidate = conn
                }
                else -> {
                    // Fantasma sin hello: evicta ya (v2.1.0: nada de BUSY
                    // a un cliente legítimo por una conexión muerta).
                    evicted = cur
                    registry.candidate = null
                    registry.active = conn
                }
            }
        }
        if (evicted != null) evict(evicted!!, "conexión fantasma sin hello")
        JevLog.i(TAG, "cliente conectado desde $from ($label)")
        scheduler.schedule({
            if (!registry.authedScopes.containsKey(conn) && conn.isOpen) {
                conn.send(errResponse(null, "hello requerido en <10s", "UNAUTHORIZED"))
                conn.close(4401, "UNAUTHORIZED")
            }
        }, HELLO_TIMEOUT_MS, TimeUnit.MILLISECONDS)
    }

    /** v2.1.0: cierra una conexión obsoleta sin tocar el slot nuevo. */
    private fun evict(conn: WebSocket, reason: String) {
        registry.authedScopes.remove(conn)
        rateBuckets.remove(conn)
        try {
            if (conn.isOpen) conn.send(errResponse(null, "conexión reemplazada: $reason", "EVICTED"))
        } catch (t: Throwable) {
            JevLog.e(TAG, "evict send falló", t)
        }
        try {
            if (conn.isOpen) conn.close(EVICTED_CODE, "EVICTED")
        } catch (t: Throwable) {
            JevLog.e(TAG, "evict close falló", t)
        }
        JevLog.i(TAG, "conexión evictada ($reason)")
    }

    override fun onClose(conn: WebSocket, code: Int, reason: String, remote: Boolean) {
        registry.authedScopes.remove(conn)
        rateBuckets.remove(conn)
        synchronized(registry) {
            if (registry.active === conn) registry.active = null
            if (registry.candidate === conn) registry.candidate = null
        }
        JevLog.i(TAG, "cliente desconectado ($reason)")
    }

    override fun onMessage(conn: WebSocket, message: String) {
        // v2.1.0: cada frame renueva el WakeLock parcial del servicio.
        try {
            onTraffic?.invoke()
        } catch (t: Throwable) {
            JevLog.e(TAG, "onTraffic falló", t)
        }
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
            if (scopes == null) {
                // Token inválido: se cierra SOLO esta conexión; el cliente
                // autenticado anterior (si lo hay) conserva el slot.
                conn.send(frame)
                conn.close(4401, "UNAUTHORIZED")
                return
            }
            var old: WebSocket? = null
            synchronized(registry) {
                val cur = registry.active
                if (cur != null && cur !== conn && cur.isOpen) old = cur
                registry.active = conn
                registry.candidate = null
                registry.authedScopes[conn] = scopes
            }
            if (old != null) evict(old!!, "nuevo hello válido")
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
    fun broadcastEvent(frame: String) = registry.broadcastEvent(frame)

    /**
     * jam-ui-redesign tarjeta 1: 0/1 sin identidad (nunca token ni IP
     * en UI; el origen queda en el audit ring, no en pantalla).
     */
    fun clientCount(): Int = registry.clientCount()

    /**
     * ¿El cliente activo está autenticado? null = sin cliente.
     * Usado por la tarjeta 1 y como gate de regeneración (tarjeta 3).
     */
    fun clientAuthed(): Boolean? = registry.clientAuthed()

    /**
     * jam-ui-redesign tarjeta 3: invalida `authedScopes` tras regenerar
     * el token; desconecta al cliente con `UNAUTHORIZED` limpio.
     * v2.2.0: incluye `active` y alcanza a todos los listeners.
     */
    fun revokeAll() = registry.revokeAll()

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

        /** v2.1.0: ping-pong cada 10 s (detecta conexiones muertas). */
        private const val PING_INTERVAL_S = 10

        /** v2.1.0: cierre limpio de la conexión reemplazada. */
        private const val EVICTED_CODE = 4002
    }
}
