package dev.k4wai1.jav.shell

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import dev.k4wai1.jav.service.JevForegroundService
import dev.k4wai1.jav.util.JevLog

/**
 * Grant interactivo de `shell` (AGENTS.md §2.6, §3.7, §9.4).
 *
 * El estado vive en memoria del proceso y **expira solo**. v2.3.1: la
 * request **no bloquea**; si falta grant se publica la notificación y se
 * responde `planned`, y el agente repite el comando tras aprobar. El
 * operador resuelve por los botones (que llegan a
 * `JevForegroundService.onStartCommand`).
 */
object ShellGrantManager {

    private const val TAG = "JamShell"

    const val ACTION_GRANT_ONCE = "dev.k4wai1.jav.action.SHELL_GRANT_ONCE"
    const val ACTION_GRANT_5M = "dev.k4wai1.jav.action.SHELL_GRANT_5M"
    const val ACTION_GRANT_30M = "dev.k4wai1.jav.action.SHELL_GRANT_30M"
    const val ACTION_GRANT_DENY = "dev.k4wai1.jav.action.SHELL_GRANT_DENY"

    const val EXTRA_SHA256 = "sha256"

    const val MODE_ONCE = "once"
    const val MODE_5M = "5m"
    const val MODE_30M = "30m"
    const val MODE_DENY = "deny"

    private const val WINDOW_5M_MS = 5L * 60 * 1000
    private const val WINDOW_30M_MS = 30L * 60 * 1000

    private const val CHANNEL_ID = "jam_shell_grant"
    private const val NOTIFICATION_ID = 2

    @Volatile
    private var grantUntilMs: Long = 0L

    @Volatile
    private var singleCmdSha256: String? = null

    @Volatile
    private var pendingSha: String? = null

    @Volatile
    private var pendingAtMs: Long = 0L

    /** ¿Hay grant vigente? (ventana activa o 1-comando pendiente). */
    @Synchronized
    fun hasActiveGrant(
        cmdSha256: String? = null,
        nowMs: Long = System.currentTimeMillis()
    ): Boolean {
        if (nowMs < grantUntilMs) return true
        val s = singleCmdSha256
        return cmdSha256 != null && s != null && cmdSha256 == s
    }

    /** Consume el grant de 1 comando si coincide (las ventanas no se consumen). */
    @Synchronized
    private fun consumeSingle(cmdSha256: String) {
        if (singleCmdSha256 == cmdSha256) singleCmdSha256 = null
    }

    /**
     * v2.3.1: grant **no bloqueante**. Devuelve `true` si el comando ya
     * está cubierto (ventana activa, o grant de 1 comando que se consume
     * aquí) y `false` si acaba de publicar la notificación y hay que
     * reintentar tras aprobarla.
     *
     * Antes bloqueaba hasta 60 s en el hilo del WebSocket; con
     * `connectionLostTimeout = 10` el servidor cerraba la conexión a los
     * ~20 s (close 1006) antes de que el operador pudiera aprobar.
     */
    fun requestGrant(ctx: Context, cmd: String): Boolean {
        val sha = ShellPolicy.sha256Hex(cmd)
        if (hasActiveGrant(sha)) {
            consumeSingle(sha)
            return true
        }
        synchronized(this) {
            pendingSha = sha
            pendingAtMs = System.currentTimeMillis()
        }
        postGrantRequest(ctx, cmd, sha)
        return false
    }

    /**
     * Resuelve la solicitud pendiente desde `JevForegroundService`.
     * Devuelve `(mode, sha256)` a emitir por WS como evento `shell_grant`,
     * o `null` si no había solicitud pendiente.
     */
    @Synchronized
    fun resolve(action: String, sha256Extra: String?): Pair<String, String>? {
        val sha = sha256Extra ?: pendingSha ?: return null
        val mode = when (action) {
            ACTION_GRANT_ONCE -> MODE_ONCE
            ACTION_GRANT_5M -> MODE_5M
            ACTION_GRANT_30M -> MODE_30M
            ACTION_GRANT_DENY -> MODE_DENY
            else -> return null
        }
        val now = System.currentTimeMillis()
        when (mode) {
            MODE_ONCE -> singleCmdSha256 = sha
            MODE_5M -> grantUntilMs = now + WINDOW_5M_MS
            MODE_30M -> grantUntilMs = now + WINDOW_30M_MS
            else -> {}
        }
        pendingSha = null
        pendingAtMs = 0L
        return mode to sha
    }

    /** Revoca cualquier grant y descarta la solicitud pendiente. */
    @Synchronized
    fun revoke() {
        grantUntilMs = 0L
        singleCmdSha256 = null
        pendingSha = null
        pendingAtMs = 0L
    }

    /** ¿Hay una solicitud esperando al operador? (para la UI del tile). */
    @Synchronized
    fun isPending(): Boolean =
        pendingSha != null && System.currentTimeMillis() - pendingAtMs < 60_000L

    // ---- notificación de solicitud (canal alta importancia) ----

    private fun postGrantRequest(ctx: Context, cmd: String, sha: String) {
        try {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (nm.getNotificationChannel(CHANNEL_ID) == null) {
                    nm.createNotificationChannel(
                        NotificationChannel(
                            CHANNEL_ID,
                            "Jav shell grant",
                            NotificationManager.IMPORTANCE_HIGH
                        )
                    )
                }
            }
            val title = "Shell grant: " + ShellPolicy.previewPrefix(cmd, 80)
            val text = "SHA-256 " + sha.take(8) + " · elige el alcance"
            val n = NotificationCompat.Builder(ctx, CHANNEL_ID)
                .setContentTitle("Jav")
                .setContentText(text)
                .setStyle(NotificationCompat.BigTextStyle().bigText("$title\n$text"))
                .setSmallIcon(android.R.drawable.ic_lock_lock)
                .setOngoing(true)
                .setPriority(NotificationCompat.PRIORITY_HIGH)
                .addAction(0, "1 cmd", grantIntent(ctx, ACTION_GRANT_ONCE, sha, 10))
                .addAction(0, "5 min", grantIntent(ctx, ACTION_GRANT_5M, sha, 11))
                .addAction(0, "30 min", grantIntent(ctx, ACTION_GRANT_30M, sha, 12))
                .addAction(0, "Denegar", grantIntent(ctx, ACTION_GRANT_DENY, sha, 13))
                .build()
            nm.notify(NOTIFICATION_ID, n)
        } catch (t: Throwable) {
            JevLog.e(TAG, "no se pudo publicar la solicitud de grant", t)
        }
    }

    private fun grantIntent(ctx: Context, action: String, sha: String, code: Int): PendingIntent {
        val i = Intent(ctx, JevForegroundService::class.java)
            .setAction(action)
            .putExtra(EXTRA_SHA256, sha)
        return PendingIntent.getService(
            ctx,
            code,
            i,
            PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE
        )
    }

    /** Cancela la notificación de solicitud (tras resolver o revocar). */
    fun cancelRequest(ctx: Context) {
        try {
            ctx.getSystemService(NotificationManager::class.java).cancel(NOTIFICATION_ID)
        } catch (t: Throwable) {
            JevLog.e(TAG, "no se pudo cancelar la solicitud de grant", t)
        }
    }
}
