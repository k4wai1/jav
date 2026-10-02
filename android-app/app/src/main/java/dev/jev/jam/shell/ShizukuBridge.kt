package dev.jev.jam.shell

import android.content.ComponentName
import android.content.ServiceConnection
import android.content.pm.PackageManager
import android.os.IBinder
import dev.jev.jam.BuildConfig
import dev.jev.jam.socket.JamError
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import rikka.shizuku.Shizuku

/**
 * Puerta privilegiada (UID shell) vía Shizuku UserService. La app es
 * non-root: este objeto es la ÚNICA vía de shell (AGENTS.md §2).
 * Shizuku lo arranca el usuario; aquí solo se pide permiso y se enlaza.
 * `shell` arbitrario NO se expone hasta Fase 6 (ver CommandDispatcher).
 *
 * Nota API 13.x: `Shizuku.newProcess` ya no es público; el camino
 * soportado es UserService (AIDL) enlazado con `bindUserService`.
 */
object ShizukuBridge {

    const val REQUEST_CODE = 4242

    fun isRunning(): Boolean = try {
        Shizuku.pingBinder()
    } catch (t: Throwable) {
        false
    }

    fun hasPermission(): Boolean = try {
        isRunning() && Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED
    } catch (t: Throwable) {
        false
    }

    /** Solo pide el permiso. Nunca intenta arrancar Shizuku. */
    fun requestPermission() {
        if (!isRunning()) {
            throw JamError(
                "Shizuku no está iniciado. Ábrelo, arráncalo y reintenta.",
                "SHIZUKU_UNAVAILABLE"
            )
        }
        Shizuku.requestPermission(REQUEST_CODE)
    }

    fun requireReady() {
        if (!isRunning()) {
            throw JamError(
                "Shizuku no está iniciado. Ábrelo (app Shizuku), arráncalo y reintenta.",
                "SHIZUKU_UNAVAILABLE"
            )
        }
        if (!hasPermission()) {
            throw JamError(
                "Permiso Shizuku denegado. Concédelo a Jam en la pantalla principal.",
                "SHIZUKU_DENIED"
            )
        }
    }

    data class ExecResult(val exitCode: Int, val stdout: String, val stderr: String)

    @Volatile
    private var shell: IShellService? = null
    private val bindLock = Any()

    private fun tryPing(s: IShellService): Boolean = try {
        s.asBinder().pingBinder()
    } catch (t: Throwable) {
        false
    }

    private fun service(): IShellService {
        val cached = shell
        if (cached != null && tryPing(cached)) return cached
        synchronized(bindLock) {
            val cached2 = shell
            if (cached2 != null && tryPing(cached2)) return cached2
            return bindNow()
        }
    }

    private fun bindNow(): IShellService {
        val latch = CountDownLatch(1)
        var svc: IShellService? = null
        val args = Shizuku.UserServiceArgs(
            ComponentName(BuildConfig.APPLICATION_ID, ShellUserService::class.java.name)
        ).daemon(false).processNameSuffix("shell").version(1).tag("jam-shell")
        val conn = object : ServiceConnection {
            override fun onServiceConnected(name: ComponentName?, binder: IBinder?) {
                svc = IShellService.Stub.asInterface(binder)
                latch.countDown()
            }

            override fun onServiceDisconnected(name: ComponentName?) {
                svc = null
            }
        }
        try {
            Shizuku.bindUserService(args, conn)
        } catch (t: Throwable) {
            throw JamError("bindUserService falló: ${t.message}", "SHIZUKU_UNAVAILABLE")
        }
        if (!latch.await(BIND_TIMEOUT_MS, TimeUnit.MILLISECONDS) || svc == null) {
            throw JamError("no se pudo enlazar el servicio shell", "SHIZUKU_UNAVAILABLE")
        }
        shell = svc
        return svc!!
    }

    /**
     * Ejecuta un comando con UID shell. El dispatcher es single-thread,
     * así que no hay carreras en el getStdout/getStderr posterior.
     */
    fun exec(cmd: List<String>, timeoutMs: Long = 15_000): ExecResult {
        requireReady()
        val s = service()
        val exit = try {
            s.exec(cmd.toTypedArray(), timeoutMs)
        } catch (t: Throwable) {
            shell = null
            throw JamError("llamada shell falló: ${t.message}", "SHIZUKU_UNAVAILABLE")
        }
        if (exit == 124) throw JamError("comando excedió ${timeoutMs}ms", "TIMEOUT")
        val out = try {
            s.stdout
        } catch (t: Throwable) {
            ""
        }
        val err = try {
            s.stderr
        } catch (t: Throwable) {
            ""
        }
        return ExecResult(exit, out, err)
    }

    private const val BIND_TIMEOUT_MS = 10_000L
}
