package dev.k4wai1.jav.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.net.ConnectivityManager
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import dev.k4wai1.jav.R
import dev.k4wai1.jav.net.TailnetDetector
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
 * Fase 6a: Kill Switch (acción en notificación + Quick Settings Tile,
 * AGENTS.md §3.8): revoca tokens, detiene el servidor y para el FGS.
 */
class JevForegroundService : Service() {

    private var server: JamWsServer? = null
    private var wssServer: JamWsServer? = null
    private var netCallback: ConnectivityManager.NetworkCallback? = null

    @Volatile
    private var tailnetIp: String? = null

    private val registry = ClientRegistry()

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
        startForeground(NOTIFICATION_ID, buildNotification("Servidor ON 127.0.0.1:$PORT"))
        startedAtMs = System.currentTimeMillis()
        instance = this
        try {
            val token = AuthStore.getOrCreateToken(applicationContext)
            val dispatcher = CommandDispatcher(applicationContext)
            server = JamWsServer(PORT, dispatcher, JamWsServer.LOOPBACK, null, registry)
                .also { it.start() }
            serverOn = true
            JevLog.i(
                TAG,
                "JamWs token_sha256=" + AuthStore.sha8(token) +
                    " len=" + token.length + " url=ws://127.0.0.1:$PORT/"
            )
            // Fase 2b: 2.º listener WSS en la IP del tailnet (si existe).
            netCallback = TailnetDetector.watch(applicationContext) { ip -> onTailnet(ip) }
            onTailnet(TailnetDetector.detect())
        } catch (t: Throwable) {
            serverOn = false
            JevLog.e(TAG, "WS no arrancó", t)
        }
    }

    /**
     * Fase 2b: levanta/derrumba el listener WSS según la IP tailnet vigente.
     * Nunca `0.0.0.0`; sin tailnet solo corre el loopback (sin error).
     */
    @Synchronized
    private fun onTailnet(ip: String?) {
        if (ip == tailnetIp && (ip == null || wssServer != null)) return
        try {
            wssServer?.shutdown()
        } catch (t: Throwable) {
            JevLog.e(TAG, "shutdown wss falló", t)
        }
        wssServer = null
        tailnetIp = ip
        if (ip == null) {
            JevLog.i(TAG, "tailnet: no detectada")
            return
        }
        try {
            val ssl = TlsCertStore.sslContext(applicationContext)
            wssServer = JamWsServer(PORT, CommandDispatcher(applicationContext), ip, ssl, registry)
                .also { it.start() }
            JevLog.i(
                TAG,
                "JamWs WSS ON $ip:$PORT fp=" +
                    TlsCertStore.fingerprintSha256(applicationContext).take(16)
            )
        } catch (t: Throwable) {
            JevLog.e(TAG, "WSS tailnet no arrancó", t)
            wssServer = null
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
            server?.broadcastEvent(
                eventFrame("shell_grant", mapOf("mode" to mode, "sha256" to cmdSha))
            )
        } catch (t: Throwable) {
            JevLog.e(TAG, "broadcast shell_grant falló", t)
        }
        JevLog.i(TAG, "shell_grant mode=$mode")
    }

    override fun onDestroy() {
        TailnetDetector.unwatch(applicationContext, netCallback)
        netCallback = null
        try {
            wssServer?.shutdown()
        } catch (t: Throwable) {
            JevLog.e(TAG, "shutdown wss", t)
        }
        wssServer = null
        tailnetIp = null
        try {
            server?.shutdown()
        } catch (t: Throwable) {
            JevLog.e(TAG, "shutdown WS", t)
        }
        server = null
        serverOn = false
        if (instance === this) instance = null
        super.onDestroy()
    }

    /** Revoca tokens, audita, desconecta clientes y detiene el servidor/FGS. */
    private fun killSwitch() {
        JevLog.i(TAG, "Kill Switch disparado")
        killSwitchLocal(applicationContext)
        try {
            server?.revokeAll()
        } catch (t: Throwable) {
            JevLog.e(TAG, "revokeAll falló", t)
        }
        try {
            server?.shutdown()
        } catch (t: Throwable) {
            JevLog.e(TAG, "shutdown falló", t)
        }
        try {
            wssServer?.shutdown()
        } catch (t: Throwable) {
            JevLog.e(TAG, "shutdown wss falló", t)
        }
        server = null
        wssServer = null
        tailnetIp = null
        serverOn = false
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

        /** Tarjeta 1 (0/1, sin identidad) y gate tarjeta 3. */
        fun clientCount(): Int = instance?.server?.clientCount() ?: 0
        fun clientAuthed(): Boolean? = instance?.server?.clientAuthed()

        /** Tarjeta 3: tras regenerar, desconexión UNAUTHORIZED limpia. */
        fun revokeClients() {
            instance?.server?.revokeAll()
        }

        /** Fase 2b: URL WSS del tailnet si el listener está vivo, o null. */
        fun tailnetUrl(): String? = instance?.tailnetIp?.let { "wss://$it:$PORT/" }

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
