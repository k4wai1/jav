package dev.jev.jam.shell

import android.app.NotificationChannel
import android.app.NotificationManager
import android.app.PendingIntent
import android.content.Context
import android.content.Intent
import android.os.Build
import androidx.core.app.NotificationCompat
import dev.jev.jam.service.JevForegroundService
import dev.jev.jam.util.JevLog
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit

/**
 * Grant interactivo de `shell` (AGENTS.md §2.6, §3.7, §9.4).
 *
 * El estado vive en memoria del proceso y **expira solo**. La request
 * bloquea hasta 60 s en `requestGrantBlocking`; el operador resuelve por
 * los botones de la notificación (que llegan a
 * `JevForegroundService.onStartCommand`). Denegación o timeout →
 * `false` (el dispatcher traduce a `SHELL_DENIED`).
 */
object ShellGrantManager {

    private const val TAG = "JamShell"

    const val ACTION_GRANT_ONCE = "dev.jev.jam.action.SHELL_GRANT_ONCE"
    const val ACTION_GRANT_5M = "dev.jev.jam.action.SHELL_GRANT_5M"
    const val ACTION_GRANT_30M = "dev.jev.jam.action.SHELL_GRANT_30M"
    const val ACTION_GRANT_DENY = "dev.jev.jam.action.SHELL_GRANT_DENY"

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

    private var pendingLatch: CountDownLatch? = null

    @Volatile
    private var pendingSha: String? = null

    @Volatile
    private var pendingGranted: Boolean = false

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
     * Pide grant y **bloquea** hasta `timeoutMs` (60 s por defecto).
     * Devuelve `true` si quedó concedido (y consume el 1-comando),
     * `false` si el operador denegó, venció el timeout o se revocó.
     */
    fun requestGrantBlocking(
        ctx: Context,
        cmd: String,
        timeoutMs: Long = 60_000L
    ): Boolean {
        val sha = ShellPolicy.sha256Hex(cmd)
        val now = System.currentTimeMillis()
        if (hasActiveGrant(sha, now)) {
            consumeSingle(sha)
            return true
        }
        val latch = CountDownLatch(1)
        synchronized(this) {
            pendingLatch = latch
            pendingSha = sha
            pendingGranted = false
        }
        postGrantRequest(ctx, cmd, sha)
        val ok = try {
            latch.await(timeoutMs, TimeUnit.MILLISECONDS) && pendingGranted
        } catch (t: InterruptedException) {
            Thread.currentThread().interrupt()
            false
        } finally {
            cancelGrantRequest(ctx)
            synchronized(this) {
                pendingLatch = null
                pendingSha = null
            }
        }
        if (ok) consumeSingle(sha)
        return ok
    }

    /**
     * Resuelve la solicitud pendiente desde `JevForegroundService`.
     * Devuelve `(mode, sha256)` a emitir por WS como evento `shell_grant`,
     * o `null` si no había solicitud pendiente.
     */
    @Synchronized
    fun resolve(action: String, sha256Extra: String?): Pair<String, String>? {
        val latch = pendingLatch ?: return null
        val sha = sha256Extra ?: pendingSha ?: ""
        val mode = when (action) {
            ACTION_GRANT_ONCE -> MODE_ONCE
            ACTION_GRANT_5M -> MODE_5M
            ACTION_GRANT_30M -> MODE_30M
            ACTION_GRANT_DENY -> MODE_DENY
            else -> return null
        }
        val now = System.currentTimeMillis()
        when (mode) {
            MODE_ONCE -> {
                singleCmdSha256 = sha
                pendingGranted = true
            }
            MODE_5M -> {
                grantUntilMs = now + WINDOW_5M_MS
                pendingGranted = true
            }
            MODE_30M -> {
                grantUntilMs = now + WINDOW_30M_MS
                pendingGranted = true
            }
            else -> pendingGranted = false
        }
        latch.countDown()
        return mode to sha
    }

    /** Revoca cualquier grant y libera la solicitud pendiente como denegada. */
    @Synchronized
    fun revoke() {
        grantUntilMs = 0L
        singleCmdSha256 = null
        pendingGranted = false
        pendingLatch?.countDown()
    }

    /** ¿Hay una solicitud esperando al operador? (para la UI del tile). */
    @Synchronized
    fun isPending(): Boolean = pendingLatch != null

    // ---- notificación de solicitud (canal alta importancia) ----

    private fun postGrantRequest(ctx: Context, cmd: String, sha: String) {
        try {
            val nm = ctx.getSystemService(NotificationManager::class.java)
            if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.O) {
                if (nm.getNotificationChannel(CHANNEL_ID) == null) {
                    nm.createNotificationChannel(
                        NotificationChannel(
                            CHANNEL_ID,
                            "Jam shell grant",
                            NotificationManager.IMPORTANCE_HIGH
                        )
                    )
                }
            }
            val title = "Shell grant: " + ShellPolicy.previewPrefix(cmd, 80)
            val text = "SHA-256 " + sha.take(8) + " · elige el alcance"
            val n = NotificationCompat.Builder(ctx, CHANNEL_ID)
                .setContentTitle("Jam")
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

    private fun cancelGrantRequest(ctx: Context) {
        try {
            ctx.getSystemService(NotificationManager::class.java).cancel(NOTIFICATION_ID)
        } catch (t: Throwable) {
            JevLog.e(TAG, "no se pudo cancelar la solicitud de grant", t)
        }
    }
}
