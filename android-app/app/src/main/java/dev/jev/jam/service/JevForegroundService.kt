package dev.jev.jam.service

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.Service
import android.content.Intent
import android.os.Build
import android.os.IBinder
import androidx.core.app.NotificationCompat
import dev.jev.jam.socket.AuthStore
import dev.jev.jam.socket.CommandDispatcher
import dev.jev.jam.socket.JamWsServer
import dev.jev.jam.util.JevLog

/**
 * Fase 2: hospeda el servidor WebSocket loopback. Vive mientras el
 * proceso viva; START_STICKY para que el sistema lo recupere.
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

    override fun onStartCommand(intent: Intent?, flags: Int, startId: Int): Int = START_STICKY

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

    private fun buildNotification(text: String) = NotificationCompat.Builder(this, CHANNEL_ID)
        .setContentTitle("Jam")
        .setContentText(text)
        .setSmallIcon(android.R.drawable.stat_sys_data_bluetooth)
        .setOngoing(true)
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
    }
}
