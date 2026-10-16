package dev.jev.jam.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.app.Service
import android.content.Context
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import androidx.core.content.ContextCompat
import dev.jev.jam.R
import dev.jev.jam.socket.AuditLog
import dev.jev.jam.socket.AuthStore
import dev.jev.jam.socket.CommandDispatcher
import dev.jev.jam.socket.JamWsServer
import dev.jev.jam.util.JevLog

/**
 * Fase 2: hospeda el servidor WebSocket loopback. Vive mientras el
 * proceso viva; START_STICKY para que el sistema lo recupere.
 *
 * Fase 6a: Kill Switch (acción en notificación + Quick Settings Tile,
 * AGENTS.md §3.8): revoca tokens, detiene el servidor y para el FGS.
 */
class JevForegroundService : Service() {

    private var server: JamWsServer? = null

    override fun onBind(intent: Intent?): IBinder? = null

    override fun onCreate() {
        super.onCreate()
        ensureChannel()
        startForeground(NOTIFICATION_ID, buildNotification("Servidor ON 127.0.0.1:$PORT"))
        startedAtMs = System.currentTimeMillis()
        instance = this
        try {
            val token = AuthStore.getOrCreateToken(applicationContext)
            server = JamWsServer(PORT, CommandDispatcher(applicationContext)).also { it.start() }
            serverOn = true
            JevLog.i(
                TAG,
                "JamWs token_sha256=" + AuthStore.sha8(token) +
                    " len=" + token.length + " url=ws://127.0.0.1:$PORT/"
            )
        } catch (t: Throwable) {
            serverOn = false
            JevLog.e(TAG, "WS no arrancó", t)
        }
    }

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int {
        if (intent?.action == ACTION_KILL_SWITCH) {
            killSwitch()
            return START_NOT_STICKY
        }
        return START_STICKY
    }

    override fun onDestroy() {
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
        server = null
        serverOn = false
        stopForeground(STOP_FOREGROUND_REMOVE)
        stopSelf()
    }

    private fun buildNotification(text: String) = NotificationCompat.Builder(this, CHANNEL_ID)
        .setContentTitle("Jam")
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
                        "Jam",
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
        const val ACTION_KILL_SWITCH = "dev.jev.jam.action.KILL_SWITCH"

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
