package dev.jev.jam.nat

import android.app.ActivityManager
import android.content.Context
import android.content.Intent
import android.content.IntentFilter
import android.os.BatteryManager
import android.os.Build
import android.os.Environment
import android.os.PowerManager
import android.os.StatFs
import android.provider.Settings
import dev.jev.jam.shell.ShizukuBridge
import dev.jev.jam.socket.JamError
import java.io.File
import kotlinx.serialization.json.JsonArray
import kotlinx.serialization.json.JsonObject
import kotlinx.serialization.json.add
import kotlinx.serialization.json.buildJsonArray
import kotlinx.serialization.json.buildJsonObject
import kotlinx.serialization.json.put

/**
 * Lecturas N0 (sin permisos nuevos): batería, RAM, almacenamiento básico,
 * CPU básica, info de dispositivo, `settings_get`. Scope `read`, sin
 * `confirm`, sin PII. Todo responde < 4 KiB salvo foto (no aquí).
 */
object NativeDevice {

    fun getBattery(ctx: Context): JsonObject {
        val batt = ctx.registerReceiver(null, IntentFilter(Intent.ACTION_BATTERY_CHANGED))
        val level = batt?.getIntExtra(BatteryManager.EXTRA_LEVEL, -1) ?: -1
        val scale = batt?.getIntExtra(BatteryManager.EXTRA_SCALE, 100) ?: 100
        val pct = if (level >= 0 && scale > 0) (level * 100 / scale) else -1
        val status = batt?.getIntExtra(BatteryManager.EXTRA_STATUS, -1) ?: -1
        val plugged = batt?.getIntExtra(BatteryManager.EXTRA_PLUGGED, 0) ?: 0
        val tempTenths = batt?.getIntExtra(BatteryManager.EXTRA_TEMPERATURE, Int.MIN_VALUE)
        val bm = ctx.getSystemService(Context.BATTERY_SERVICE) as BatteryManager
        val pm = ctx.getSystemService(Context.POWER_SERVICE) as PowerManager
        val pluggedStr = when (plugged) {
            BatteryManager.BATTERY_PLUGGED_AC -> "ac"
            BatteryManager.BATTERY_PLUGGED_USB -> "usb"
            BatteryManager.BATTERY_PLUGGED_WIRELESS -> "wireless"
            else -> "none"
        }
        return buildJsonObject {
            put("level_pct", pct)
            put("capacity_pct", bm.getIntProperty(BatteryManager.BATTERY_PROPERTY_CAPACITY))
            put("charging", status == BatteryManager.BATTERY_STATUS_CHARGING ||
                status == BatteryManager.BATTERY_STATUS_FULL)
            put("plugged", pluggedStr)
            if (tempTenths != null && tempTenths != Int.MIN_VALUE) {
                put("temp_c", tempTenths / 10.0)
            }
            put("saver", pm.isPowerSaveMode)
        }
    }

    fun getMemory(ctx: Context): JsonObject {
        val am = ctx.getSystemService(Context.ACTIVITY_SERVICE) as ActivityManager
        val mi = ActivityManager.MemoryInfo()
        am.getMemoryInfo(mi)
        return buildJsonObject {
            put("avail_bytes", mi.availMem)
            put("total_bytes", mi.totalMem)
            put("threshold_bytes", mi.threshold)
            put("low_memory", mi.lowMemory)
        }
    }

    /** Básico P0 (`StatFs`); `fine` (N2) añade `df` por Shizuku. */
    fun getStorage(detail: String): JsonObject {
        val path = Environment.getDataDirectory().path
        val st = StatFs(path)
        val block = st.blockSizeLong
        val basic = buildJsonObject {
            put("path", path)
            put("total_bytes", block * st.blockCountLong)
            put("free_bytes", block * st.freeBlocksLong)
            put("avail_bytes", block * st.availableBlocksLong)
        }
        if (detail != "fine") return basic
        val r = ShizukuBridge.exec(listOf("df", "-k", "/data", "/sdcard"))
        val entries = buildJsonArray {
            for (line in r.stdout.lines()) {
                val c = line.trim().split(Regex("\\s+"))
                if (c.size < 6 || c[0] == "Filesystem") continue
                if (c[1].toLongOrNull() == null) continue
                add(buildJsonObject {
                    put("filesystem", c[0])
                    put("size_kb", c[1].toLongOrNull() ?: 0L)
                    put("used_kb", c[2].toLongOrNull() ?: 0L)
                    put("avail_kb", c[3].toLongOrNull() ?: 0L)
                    put("use_pct", c[4])
                    put("mounted_on", c.last())
                })
            }
        }
        return buildJsonObject {
            for ((k, v) in basic) put(k, v)
            put("fine", buildJsonObject {
                put("via", "shizuku")
                put("cmd", "df -k /data /sdcard")
                put("exit_code", r.exitCode)
                put("entries", entries)
            })
        }
    }

    /** Básica P0: nº de CPUs + uso instantáneo vía delta de `/proc/stat`. */
    fun getCpu(detail: String): JsonObject {
        val cpus = Runtime.getRuntime().availableProcessors()
        val a = readCpuJiffies()
        try {
            Thread.sleep(120)
        } catch (t: InterruptedException) {
            Thread.currentThread().interrupt()
        }
        val b = readCpuJiffies()
        var usagePct = -1.0
        if (a != null && b != null) {
            val idleA = a[3] + a[4]
            val idleB = b[3] + b[4]
            val totalA = a.sum()
            val totalB = b.sum()
            val dTotal = totalB - totalA
            if (dTotal > 0) usagePct = (dTotal - (idleB - idleA)).toDouble() / dTotal * 100.0
        }
        val basic = buildJsonObject {
            put("processors", cpus)
            put("usage_pct", usagePct)
        }
        if (detail != "fine") return basic
        val r = ShizukuBridge.exec(listOf("top", "-b", "-n", "1", "-m", "10"))
        val procs = buildJsonArray {
            for (line in r.stdout.lines()) {
                val c = line.trim().split(Regex("\\s+"))
                if (c.size < 3) continue
                val pid = c[0].toIntOrNull() ?: continue
                add(buildJsonObject {
                    put("pid", pid)
                    put("name", c.last())
                    if (c.size >= 2) put("cpu_pct", c.getOrNull(8) ?: "")
                })
            }
        }
        return buildJsonObject {
            for ((k, v) in basic) put(k, v)
            put("fine", buildJsonObject {
                put("via", "shizuku")
                put("cmd", "top -b -n 1 -m 10")
                put("exit_code", r.exitCode)
                put("processes", procs)
                put("raw", r.stdout.take(4000))
            })
        }
    }

    private fun readCpuJiffies(): LongArray? {
        return try {
            val line = File("/proc/stat").bufferedReader().use { it.readLine() }
                ?: return null
            if (!line.startsWith("cpu ")) return null
            line.removePrefix("cpu").trim().split(Regex("\\s+"))
                .take(8).map { it.toLongOrNull() ?: 0L }.toLongArray()
        } catch (t: Throwable) {
            null
        }
    }

    /**
     * Hardware P0 sin identificadores persistentes (sin ANDROID_ID, IMEI,
     * MAC ni serial): solo modelo/ABI/pantalla/features/locale/zona.
     */
    fun getDeviceInfo(ctx: Context): JsonObject {
        val dm = ctx.resources.displayMetrics
        val pm = ctx.packageManager
        fun feat(name: String) = pm.hasSystemFeature(name)
        return buildJsonObject {
            put("manufacturer", Build.MANUFACTURER)
            put("model", Build.MODEL)
            put("device", Build.DEVICE)
            put("sdk_int", Build.VERSION.SDK_INT)
            put("abis", buildJsonArray { Build.SUPPORTED_ABIS.forEach { add(it) } })
            put("screen_w", dm.widthPixels)
            put("screen_h", dm.heightPixels)
            put("density_dpi", dm.densityDpi)
            put("locale", java.util.Locale.getDefault().toLanguageTag())
            put("timezone", java.util.TimeZone.getDefault().id)
            put("features", buildJsonObject {
                put("camera", feat(android.content.pm.PackageManager.FEATURE_CAMERA_ANY))
                put("telephony", feat(android.content.pm.PackageManager.FEATURE_TELEPHONY))
                put("bluetooth", feat(android.content.pm.PackageManager.FEATURE_BLUETOOTH))
                put("nfc", feat(android.content.pm.PackageManager.FEATURE_NFC))
            })
        }
    }

    /** `settings_get` (System/Secure/Global en lectura; escritura → `settings_put`). */
    fun settingsGet(ctx: Context, namespace: String, key: String): JsonObject {
        if (!NatPolicies.getAllowed(namespace)) {
            throw JamError("namespace debe ser system|secure|global", "VALIDATION_ERROR")
        }
        if (key.isBlank()) throw JamError("key vacía", "VALIDATION_ERROR")
        val value = try {
            when (namespace) {
                "system" -> Settings.System.getString(ctx.contentResolver, key)
                "secure" -> Settings.Secure.getString(ctx.contentResolver, key)
                else -> Settings.Global.getString(ctx.contentResolver, key)
            }
        } catch (t: SecurityException) {
            throw JamError("lectura denegada para $namespace/$key", "FORBIDDEN")
        }
        return buildJsonObject {
            put("namespace", namespace)
            put("key", key)
            put("found", value != null)
            if (value != null) put("value", value)
        }
    }
}
