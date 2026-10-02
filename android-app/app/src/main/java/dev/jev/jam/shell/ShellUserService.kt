package dev.jev.jam.shell

import java.util.concurrent.TimeUnit

/**
 * Corre con UID shell. IMPORTANTE: lo instancia Shizuku vía app_process
 * (`ServiceStarter`), no el framework Android — por eso extiende el Stub
 * AIDL directamente (es un IBinder) y NO extiende Service. Sin entrada
 * `<service>` en el manifest (Shizuku resuelve por ComponentName).
 * Sin llamadas al framework aquí: el proceso es mínimo.
 */
class ShellUserService : IShellService.Stub() {

    private val lock = Any()
    private var lastOut = ""
    private var lastErr = ""

    override fun exec(cmd: Array<String>?, timeoutMs: Long): Int {
        if (cmd == null || cmd.isEmpty()) {
            setOutputs("", "cmd vacío")
            return 127
        }
        val proc = try {
            ProcessBuilder(*cmd).redirectErrorStream(false).start()
        } catch (t: Throwable) {
            setOutputs("", "spawn falló: ${t.message}")
            return 127
        }
        val out = StringBuilder()
        val err = StringBuilder()
        val tOut = Thread {
            try {
                proc.inputStream.bufferedReader().use { out.append(it.readText()) }
            } catch (t: Throwable) {
                err.append("[stdout cortado]")
            }
        }
        val tErr = Thread {
            try {
                proc.errorStream.bufferedReader().use { err.append(it.readText()) }
            } catch (t: Throwable) {
                err.append("[stderr cortado]")
            }
        }
        tOut.start()
        tErr.start()
        val finished = try {
            proc.waitFor(timeoutMs, TimeUnit.MILLISECONDS)
        } catch (t: Throwable) {
            false
        }
        if (!finished) {
            proc.destroy()
            setOutputs(out.toString(), err.toString() + "[timeout]")
            return 124
        }
        tOut.join(2000)
        tErr.join(2000)
        setOutputs(out.toString(), err.toString())
        return proc.exitValue()
    }

    override fun getStdout(): String = synchronized(lock) {
        val s = lastOut
        lastOut = ""
        s
    }

    override fun getStderr(): String = synchronized(lock) {
        val e = lastErr
        lastErr = ""
        e
    }

    private fun setOutputs(o: String, e: String) = synchronized(lock) {
        lastOut = o
        lastErr = e
    }
}
