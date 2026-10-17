package dev.k4wai1.jav.shell

import java.util.concurrent.TimeUnit

/**
 * Corre con el UID de Shizuku (root o shell). IMPORTANTE: lo instancia
 * Shizuku vía app_process (`ServiceStarter`), no el framework Android —
 * por eso extiende el Stub AIDL directamente (es un IBinder) y NO extiende
 * Service. Sin entrada `<service>` en el manifest (Shizuku resuelve por
 * ComponentName). Sin llamadas al framework aquí: el proceso es mínimo.
 *
 * v1.2.5: `getClipboardText()` usa la técnica scrcpy — appops
 * `READ_CLIPBOARD` para `com.android.shell` + reflexión sobre el binder
 * `IClipboard` (firmas validadas por TIPOS, no solo por conteo).
 * Todo best-effort: "" cuando no se puede; nunca lanza al caller.
 *
 * IMPORTANTE (UID): `ClipboardService.addActiveOwnerLocked` exige que el
 * caller SEA el dueño del paquete que alega (`com.android.shell` = 2000).
 * Con caller root (Shizuku root) lanza SecurityException y el sistema
 * BORRA el clipboard (ClipboardService.java:386). Por eso:
 *  - uid 2000 → lectura directa en este proceso (binder ya abierto);
 *  - uid 0 → subproceso `app_process` del propio APK: `main()` baja a
 *    2000 ANTES de tocar /dev/binder y escribe el texto por stdout;
 *  - otro uid → "" (jamás llamar a IClipboard: podría vaciar el clip).
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

    override fun getClipboardText(): String {
        return try {
            allowShellClipboardRead()
            when (android.os.Process.myUid()) {
                2000 -> readClipboardBinder()
                0 -> readClipboardViaSubprocess()
                else -> ""
            }
        } catch (t: Throwable) {
            ""
        }
    }

    /** appops best-effort (idempotente); scrcpy deja el allow puesto. */
    private fun allowShellClipboardRead() {
        try {
            ProcessBuilder(
                "appops", "set", "com.android.shell", "READ_CLIPBOARD", "allow"
            ).start().waitFor(3, TimeUnit.SECONDS)
        } catch (t: Throwable) {
            // Sin permiso para cambiar el op: se intenta la lectura igual.
        }
    }

    /**
     * Shizuku root: el kernel debe ver `callingUid=2000` al llamar a
     * `IClipboard`. Se lanza un `app_process` del propio APK con el mismo
     * camino que usa Shizuku (`ServiceStarter`): `main()` baja a 2000
     * antes de abrir /dev/binder, lee y escribe el texto por stdout.
     * Sin `su` (AGENTS §2): solo app_process + Os.setuid.
     */
    private fun readClipboardViaSubprocess(): String {
        val apk = apkPath() ?: return ""
        val proc = try {
            ProcessBuilder(
                "/system/bin/app_process", "/system/bin",
                "dev.k4wai1.jav.shell.ShellUserService"
            ).also { it.environment()["CLASSPATH"] = apk }.start()
        } catch (t: Throwable) {
            return ""
        }
        val out = StringBuilder()
        val reader = Thread {
            try {
                proc.inputStream.bufferedReader().use { out.append(it.readText()) }
            } catch (t: Throwable) {
                // stdout cortado: se devuelve lo leído
            }
        }
        reader.start()
        val finished = try {
            proc.waitFor(CLIP_READ_TIMEOUT_MS, TimeUnit.MILLISECONDS)
        } catch (t: Throwable) {
            false
        }
        if (!finished) {
            proc.destroy()
            return ""
        }
        reader.join(1000)
        return out.toString()
    }

    private fun apkPath(): String? = try {
        val p = ProcessBuilder("pm", "path", "dev.k4wai1.jav").start()
        val out = p.inputStream.bufferedReader().use { it.readText() }
        p.waitFor(3, TimeUnit.SECONDS)
        out.lineSequence()
            .firstOrNull { it.startsWith("package:") }
            ?.removePrefix("package:")?.trim()
            ?.takeIf { it.isNotEmpty() }
    } catch (t: Throwable) {
        null
    }

    private fun setOutputs(o: String, e: String) = synchronized(lock) {
        lastOut = o
        lastErr = e
    }

    companion object {

        private const val CLIP_READ_TIMEOUT_MS = 5_000L

        /**
         * Entrada `app_process` del subproceso de clipboard (Shizuku root):
         * baja a UID 2000 ANTES de abrir /dev/binder para que `IClipboard`
         * vea `callingUid=2000` (= dueño de `com.android.shell`). Con uid 0
         * la llamada borraría el clipboard (`ClipboardService` línea 386).
         * Nunca imprime nada si no se pudo bajar a 2000 (no tocar binder).
         */
        @JvmStatic
        fun main(args: Array<String>) {
            val uid = try {
                if (android.system.Os.getuid() == 0) {
                    android.system.Os.setgid(2000)
                    android.system.Os.setuid(2000)
                }
                android.system.Os.getuid()
            } catch (t: Throwable) {
                -1
            }
            if (uid == 2000) {
                print(readClipboardBinder())
            }
        }

        private fun readClipboardBinder(): String {
            return try {
                val binder = serviceManager("clipboard") ?: return ""
                val clipboard = asInterface("android.content.IClipboard\$Stub", binder) ?: return ""
                val clip = getPrimaryClipReflect(clipboard) ?: return ""
                if (clip.itemCount <= 0) return ""
                clip.getItemAt(0)?.text?.toString().orEmpty()
            } catch (t: Throwable) {
                ""
            }
        }

        private fun serviceManager(name: String): android.os.IBinder? = try {
            val sm = Class.forName("android.os.ServiceManager")
            sm.getMethod("getService", String::class.java).invoke(null, name) as? android.os.IBinder
        } catch (t: Throwable) {
            null
        }

        private fun asInterface(stubClass: String, binder: android.os.IBinder): Any? = try {
            Class.forName(stubClass)
                .getMethod("asInterface", android.os.IBinder::class.java)
                .invoke(null, binder)
        } catch (t: Throwable) {
            null
        }

        /**
         * Firmas reales de `IClipboard.getPrimaryClip` según versión:
         *  (String) · (String, int) · (String, String, int)
         *  (String, String, int, int) · (String, String, int, int, listener)
         * Se validan los TIPOS (no solo el conteo): primer String = `pkg`
         * ("com.android.shell"), segundo String = `attributionTag` (null),
         * ints = `userId`/`deviceId` (0), listener = null. La que exista y
         * acepte, gana.
         */
        private fun getPrimaryClipReflect(clipboard: Any): android.content.ClipData? {
            val pkg = "com.android.shell"
            for (m in clipboard.javaClass.methods) {
                if (m.name != "getPrimaryClip") continue
                val args = argsFor(m.parameterTypes, pkg) ?: continue
                try {
                    val r = m.invoke(clipboard, *args)
                    if (r is android.content.ClipData) return r
                } catch (t: Throwable) {
                    // Firma presente pero rechazada (SecurityException, tipos):
                    // se prueban las restantes.
                }
            }
            return null
        }

        private fun argsFor(types: Array<Class<*>>, pkg: String): Array<Any?>? {
            val intCls = Integer.TYPE
            return when {
                types.size == 1 && types[0] == String::class.java ->
                    arrayOf<Any?>(pkg)
                types.size == 2 && types[0] == String::class.java && types[1] == intCls ->
                    arrayOf<Any?>(pkg, 0)
                types.size == 3 && types[0] == String::class.java &&
                    types[1] == String::class.java && types[2] == intCls ->
                    arrayOf<Any?>(pkg, null, 0)
                types.size == 4 && types[0] == String::class.java &&
                    types[1] == String::class.java && types[2] == intCls && types[3] == intCls ->
                    arrayOf<Any?>(pkg, null, 0, 0)
                types.size == 5 && types[0] == String::class.java &&
                    types[1] == String::class.java && types[2] == intCls && types[3] == intCls ->
                    arrayOf<Any?>(pkg, null, 0, 0, null)
                else -> null
            }
        }
    }
}
