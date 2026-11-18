package dev.k4wai1.jav.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.net.nsd.NsdManager
import android.net.nsd.NsdServiceInfo
import android.net.wifi.WifiManager
import android.os.Build
import android.os.IBinder
import android.os.PowerManager
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import dev.k4wai1.jav.R
import dev.k4wai1.jav.net.NetworkDetector
import dev.k4wai1.jav.socket.AuditLog
import dev.k4wai1.jav.socket.AuthStore
import dev.k4wai1.jav.socket.ClientRegistry
import dev.k4wai1.jav.socket.CommandDispatcher
import dev.k4wai1.jav.socket.JamWsServer
import dev.k4wai1.jav.socket.TlsCertStore
import dev.k4wai1.jav.socket.eventFrame
import dev.k4wai1.jav.shell.ShellGrantManager
import dev.k4wai1.jav.util.JevLog

/**
 * Fase 2: hospeda el servidor WebSocket loopback. Vive mientras el
 * proceso viva; START_STICKY para que el sistema lo recupere.
 *
 * v2.1.0: además del loopback, levanta un listener WSS **por cada IP
 * bindeable** detectada (Tailscale `100.64/10` y Wi-Fi privada RFC 1918),
 * publica `_jav-mcp._tcp` por mDNS (NsdManager) y mantiene WakeLock
 * parcial + WifiLock de baja latencia para que el deep sleep no estrangule
 * el servidor. **Nunca `0.0.0.0`.**
 *
 * Fase 6a: Kill Switch (acción en notificación + Quick Settings Tile,
 * AGENTS.md §3.8): revoca tokens, detiene el servidor y para el FGS.
 */
class JevForegroundService : Service() {

    private var server: JamWsServer? = null
    private val wssServers = HashMap<String, JamWsServer>()
    private var netCallback: ConnectivityManager.NetworkCallback? = null

    /**
     * v2.3.0: un único dispatcher para todos los listeners (loopback +
     * WSS). Mantiene contadores de sesión/audit coherentes entre rutas.
     */
    private var dispatcher: CommandDispatcher? = null

    @Volatile
    private var tailnetIp: String? = null

    @Volatile
    private var lanIp: String? = null

    private var nsdManager: NsdManager? = null
    private var mdnsListener: NsdManager.RegistrationListener? = null

    private var wakeLock: PowerManager.WakeLock? = null
    private var wifiLock: WifiManager.WifiLock? = null

    private val registry = ClientRegistry()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
        startForeground(NOTIFICATION_ID, buildNotification("Servidor ON 127.0.0.1:$PORT"))
        startedAtMs = System.currentTimeMillis()
        instance = this
        acquireLocks()
        try {
            val token = AuthStore.getOrCreateToken(applicationContext)
            val disp = CommandDispatcher(applicationContext)
            dispatcher = disp
            server = JamWsServer(
                PORT, disp, JamWsServer.LOOPBACK, null, registry
            ) { renewWakeLock() }.also { it.start() }
            serverOn = true
            JevLog.i(
                TAG,
                "JamWs token_sha256=" + AuthStore.sha8(token) +
                    " len=" + token.length + " url=ws://127.0.0.1:$PORT/"
            )
            // v2.1.0: listeners WSS en tailnet y/o LAN Wi-Fi detectadas.
            netCallback = NetworkDetector.watch(applicationContext) { ips -> onNetwork(ips) }
            onNetwork(NetworkDetector.detectAll())
        } catch (t: Throwable) {
            serverOn = false
            JevLog.e(TAG, "WS no arrancó", t)
        }
    }

    /**
     * v2.1.0: reconcilia los listeners WSS con las IPs privadas vigentes.
     * Nunca `0.0.0.0`: solo IPs concretas de Tailscale/RFC 1918; sin
     * ninguna, solo queda el loopback (sin error). Registra mDNS solo
     * cuando hay LAN (en datos móviles no tiene sentido).
     */
    @Synchronized
    private fun onNetwork(ips: List<String>) {
        tailnetIp = ips.firstOrNull { NetworkDetector.isTailnetIpv4(it) }
        lanIp = ips.firstOrNull { NetworkDetector.isRfc1918Ipv4(it) }
        val wanted = ips.filter { NetworkDetector.isBindableIpv4(it) }.distinct()

        val it = wssServers.keys.iterator()
        while (it.hasNext()) {
            val ip = it.next()
            if (ip in wanted) continue
            try {
                wssServers[ip]?.shutdown()
            } catch (t: Throwable) {
                JevLog.e(TAG, "shutdown wss $ip falló", t)
            }
            it.remove()
            JevLog.i(TAG, "WSS OFF $ip:$PORT")
        }
        val disp = dispatcher ?: return
        for (ip in wanted) {
            if (wssServers.containsKey(ip)) continue
            try {
                val ssl = TlsCertStore.sslContext(applicationContext)
                val s = JamWsServer(
                    PORT, disp, ip, ssl, registry
                ) { renewWakeLock() }.also { it.start() }
                wssServers[ip] = s
                JevLog.i(
                    TAG,
                    "JamWs WSS ON $ip:$PORT fp=" +
                        TlsCertStore.fingerprintSha256(applicationContext).take(16)
                )
            } catch (t: Throwable) {
                JevLog.e(TAG, "WSS $ip no arrancó", t)
            }
        }
        // mDNS solo con LAN viva; no re-registrar en cada evento de red.
        if (lanIp != null) {
            if (mdnsListener == null) startMdns()
        } else {
            stopMdns()
        }
        notifyStatus()
        JevLog.i(
            TAG,
            "red: tailnet=${tailnetIp ?: "-"} lan=${lanIp ?: "-"} wss=${wssServers.size}"
        )
    }

    // ---- mDNS (v2.1.0: descubrimiento sin IPs manuales) ----

    /** Publica `_jav-mcp._tcp.` con el puerto del servidor WS. */
    private fun startMdns() {
        stopMdns()
        val nsd = getSystemService(NsdManager::class.java) ?: return
        val info = NsdServiceInfo().apply {
            serviceName = mdnsName()
            serviceType = MDNS_TYPE
            port = PORT
        }
        val listener = object : NsdManager.RegistrationListener {
            override fun onServiceRegistered(info: NsdServiceInfo) {
                JevLog.i(TAG, "mDNS ON ${info.serviceName} $MDNS_TYPE:$PORT")
            }

            override fun onRegistrationFailed(info: NsdServiceInfo, errorCode: Int) {
                JevLog.e(TAG, "mDNS registro falló ($errorCode)", null)
            }

            override fun onServiceUnregistered(info: NsdServiceInfo) {}

            override fun onUnregistrationFailed(info: NsdServiceInfo, errorCode: Int) {
                JevLog.e(TAG, "mDNS baja falló ($errorCode)", null)
            }
        }
        try {
            nsd.registerService(info, NsdManager.PROTOCOL_DNS_SD, listener)
            nsdManager = nsd
            mdnsListener = listener
        } catch (t: Throwable) {
            JevLog.e(TAG, "mDNS no arrancó", t)
        }
    }

    private fun stopMdns() {
        val nsd = nsdManager ?: return
        val listener = mdnsListener ?: return
        try {
            nsd.unregisterService(listener)
        } catch (t: Throwable) {
            JevLog.e(TAG, "mDNS no se pudo dar de baja", t)
        }
        nsdManager = null
        mdnsListener = null
    }

    /** Etiqueta DNS-SD estable y legible ("Jav-<modelo>"). */
    private fun mdnsName(): String {
        val model = Build.MODEL ?: ""
        val clean = model.replace(Regex("[^A-Za-z0-9._-]"), "-").trim('-')
        return if (clean.isEmpty()) "Jav" else "Jav-$clean"
    }

    // ---- WakeLock / WifiLock (v2.1.0: deep sleep) ----

    private fun acquireLocks() {
        try {
            val pm = getSystemService(PowerManager::class.java)
            wakeLock = pm?.newWakeLock(PowerManager.PARTIAL_WAKE_LOCK, "jav:ws")?.apply {
                setReferenceCounted(false)
                acquire(WAKE_LOCK_TIMEOUT_MS)
            }
        } catch (t: Throwable) {
            JevLog.e(TAG, "WakeLock no adquirido", t)
        }
        try {
            @Suppress("DEPRECATION")
            val wm = applicationContext.getSystemService(WifiManager::class.java)
            @Suppress("DEPRECATION")
            wifiLock = wm?.createWifiLock(WifiManager.WIFI_MODE_FULL_LOW_LATENCY, "jav:wifi")
                ?.apply {
                    setReferenceCounted(false)
                    acquire()
                }
        } catch (t: Throwable) {
            JevLog.e(TAG, "WifiLock no adquirido", t)
        }
    }

    /** Renueva el WakeLock parcial con cada frame WS recibido. */
    private fun renewWakeLock() {
        val wl = wakeLock ?: return
        try {
            if (wl.isHeld) wl.release()
        } catch (t: Throwable) {
            JevLog.e(TAG, "WakeLock release falló", t)
        }
        try {
            wl.acquire(WAKE_LOCK_TIMEOUT_MS)
        } catch (t: Throwable) {
            JevLog.e(TAG, "WakeLock renew falló", t)
        }
    }

    private fun releaseLocks() {
        try {
            if (wakeLock?.isHeld == true) wakeLock?.release()
        } catch (t: Throwable) {
            JevLog.e(TAG, "WakeLock release falló", t)
        }
        wakeLock = null
        try {
            if (wifiLock?.isHeld == true) wifiLock?.release()
        } catch (t: Throwable) {
            JevLog.e(TAG, "WifiLock release falló", t)
        }
        wifiLock = null
    }

    private fun notifyStatus() {
        try {
            val text = buildString {
                append("Servidor ON 127.0.0.1:").append(PORT)
                if (wssServers.isNotEmpty()) {
                    append(" · WSS ").append(wssServers.keys.joinToString(", "))
                }
            }
            getSystemService(NotificationManager::class.java)
                ?.notify(NOTIFICATION_ID, buildNotification(text))
        } catch (t: Throwable) {
            JevLog.e(TAG, "notificación no actualizada", t)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        when (intent?.action) {
            ACTION_KILL_SWITCH -> {
                killSwitch()
                return START_NOT_STICKY
            }
            ShellGrantManager.ACTION_GRANT_ONCE,
            ShellGrantManager.ACTION_GRANT_5M,
            ShellGrantManager.ACTION_GRANT_30M,
            ShellGrantManager.ACTION_GRANT_DENY -> {
                resolveShellGrant(intent)
                return START_STICKY
            }
        }
        return START_STICKY
    }

    /**
     * Fase 6b: resuelve la solicitud de grant de `shell` (botones de la
     * notificación) y emite `shell_grant` por WS para que el cliente
     * sepa el desenlace. El `CountDownLatch` del manager se libera dentro
     * de `resolve`, desbloqueando la request que esperaba.
     */
    private fun resolveShellGrant(intent: Intent) {
        val action = intent.action ?: return
        val sha = intent.getStringExtra(ShellGrantManager.EXTRA_SHA256)
        val resolved = ShellGrantManager.resolve(action, sha) ?: return
        val (mode, cmdSha) = resolved
        try {
            // v2.2.0: el evento alcanza al cliente esté en loopback,
            // tailnet o LAN (antes solo se miraba el listener loopback).
            registry.broadcastEvent(
                eventFrame("shell_grant", mapOf("mode" to mode, "sha256" to cmdSha))
            )
        } catch (t: Throwable) {
            JevLog.e(TAG, "broadcast shell_grant falló", t)
        }
        JevLog.i(TAG, "shell_grant mode=$mode")
    }

    override fun onDestroy() {
        NetworkDetector.unwatch(applicationContext, netCallback)
        netCallback = null
        stopMdns()
        for ((ip, s) in wssServers.toList()) {
            try {
                s.shutdown()
            } catch (t: Throwable) {
                JevLog.e(TAG, "shutdown wss $ip", t)
            }
        }
        wssServers.clear()
        tailnetIp = null
        lanIp = null
        try {
            server?.shutdown()
        } catch (t: Throwable) {
            JevLog.e(TAG, "shutdown WS", t)
        }
        server = null
        serverOn = false
        releaseLocks()
        dispatcher = null
        if (instance === this) instance = null
        super.onDestroy()
    }

    /** Revoca tokens, audita, desconecta clientes y detiene el servidor/FGS. */
    private fun killSwitch() {
        JevLog.i(TAG, "Kill Switch disparado")
        killSwitchLocal(applicationContext)
        try {
            // v2.2.0: revoca y cierra sesiones de TODOS los listeners.
            registry.revokeAll()
        } catch (t: Throwable) {
            JevLog.e(TAG, "revokeAll falló", t)
        }
        try {
            server?.shutdown()
        } catch (t: Throwable) {
            JevLog.e(TAG, "shutdown falló", t)
        }
        for ((ip, s) in wssServers.toList()) {
            try {
                s.shutdown()
            } catch (t: Throwable) {
                JevLog.e(TAG, "shutdown wss $ip falló", t)
            }
        }
        wssServers.clear()
        stopMdns()
        server = null
        tailnetIp = null
        lanIp = null
        serverOn = false
        releaseLocks()
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun buildNotification(text: String) = NotificationCompat.Builder(this, CHANNEL_ID)
        .setContentTitle("Jav")
        .setContentText(text)
        .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
        .setOngoing(true)
        .addAction(
            R.drawable.ic_jam_kill,
            "Kill Switch",
            PendingIntent.getService(
                this,
                0,
                Intent(this, JevForegroundService::class.java).setAction(ACTION_KILL_SWITCH),
                PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
            )
        )
        .build()

    private fun ensureChannel() {
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
            val manager = getSystemService(NotificationManager::class.java)
            if (manager.getNotificationChannel(CHANNEL_ID) == null) {
                manager.createNotificationChannel(
                    NotificationChannel(
                        CHANNEL_ID,
                        "Jav",
                        NotificationManager.IMPORTANCE_LOW
                    )
                )
            }
        }
    }

    companion object {
        private const val TAG = "JamWs"
        private const val CHANNEL_ID = "jam_server"
        private const val NOTIFICATION_ID = 1
        const val PORT = 38472

        /** v2.1.0: tipo DNS-SD anunciado por NsdManager. */
        const val MDNS_TYPE = "_jav-mcp._tcp."

        /** WakeLock parcial renovado por frame; 10 min sin tráfico → cae. */
        private const val WAKE_LOCK_TIMEOUT_MS = 10 * 60_000L

        /** Fase 6a: acción de Kill Switch (notificación + QS tile). */
        const val ACTION_KILL_SWITCH = "dev.k4wai1.jav.action.KILL_SWITCH"

        @Volatile
        var serverOn: Boolean = false
            private set

        /**
         * jam-ui-redesign tarjeta 1: arranque para "desde HH:MM:SS".
         * 0 = aún no arrancado en este proceso.
         */
        @Volatile
        var startedAtMs: Long = 0L
            private set

        @Volatile
        private var instance: JevForegroundService? = null

        /** Tarjeta 1 (0/1, sin identidad) y gate tarjeta 3.
         *  v2.2.0: delega en el registry compartido (cualquier listener). */
        fun clientCount(): Int = instance?.registry?.clientCount() ?: 0
        fun clientAuthed(): Boolean? = instance?.registry?.clientAuthed()

        /** Tarjeta 3: tras regenerar, desconexión UNAUTHORIZED limpia
         *  en todos los listeners (loopback + WSS tailnet/LAN). */
        fun revokeClients() {
            instance?.registry?.revokeAll()
        }

        /** Fase 2b: URL WSS del tailnet si el listener está vivo, o null. */
        fun tailnetUrl(): String? = instance?.tailnetIp?.let { "wss://$it:$PORT/" }

        /** v2.1.0: URL WSS de la LAN Wi-Fi si el listener está vivo. */
        fun lanUrl(): String? = instance?.lanIp?.let { "wss://$it:$PORT/" }

        /** v2.1.0: todas las URLs WSS vivas (tailnet + LAN). */
        fun wssUrls(): List<String> =
            instance?.let { svc ->
                svc.wssServers.keys.sorted().map { "wss://$it:$PORT/" }
            } ?: emptyList()

        /** Fase 2b: fingerprint SHA-256 (hex) del cert autofirmado (TOFU). */
        fun certFingerprint(): String? = instance?.let {
            try {
                TlsCertStore.fingerprintSha256(it.applicationContext)
            } catch (t: Throwable) {
                null
            }
        }

        /**
         * Fase 6a: Kill Switch desde notificación o QS tile. Si el
         * servicio vive, delega en su `onStartCommand`; si no, aplica
         * igualmente el efecto local (token nuevo + audit).
         */
        fun triggerKillSwitch(ctx: Context) {
            val svc = instance
            if (svc == null) {
                killSwitchLocal(ctx)
                return
            }
            try {
                ContextCompat.startForegroundService(
                    svc,
                    Intent(svc, JevForegroundService::class.java).setAction(ACTION_KILL_SWITCH)
                )
            } catch (t: Throwable) {
                JevLog.e(TAG, "kill switch no arrancó", t)
                killSwitchLocal(ctx)
            }
        }

        /** Efecto local: rota el token y deja constancia en el audit ring. */
        private fun killSwitchLocal(ctx: Context) {
            ShellGrantManager.revoke()
            try {
                AuthStore.regenerateToken(ctx)
            } catch (t: Throwable) {
                JevLog.e(TAG, "regenerate token falló", t)
            }
            try {
                AuditLog.record("kill_switch", "admin", "", "OK", "local")
            } catch (t: Throwable) {
                JevLog.e(TAG, "audit kill_switch falló", t)
            }
        }
    }
}
