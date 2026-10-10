package dev.jev.jam

import android.app.AppOpsManager
import android.content.ClipData
import android.content.ClipboardManager
import android.content.ComponentName
import android.content.Context
import android.content.Intent
import android.content.pm.PackageManager
import android.net.Uri
import android.os.Bundle
import android.os.PowerManager
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AlertDialog
import androidx.appcompat.app.AppCompatActivity
import androidx.core.app.ActivityCompat
import androidx.core.content.ContextCompat
import dev.jev.jam.service.JamNotificationListener
import dev.jev.jam.service.JevAccessibilityService
import dev.jev.jam.service.JevForegroundService
import dev.jev.jam.shell.ShizukuBridge
import dev.jev.jam.socket.AuthStore
import dev.jev.jam.socket.CommandDispatcher
import dev.jev.jam.socket.JamError
import dev.jev.jam.util.JevLog
import java.text.SimpleDateFormat
import java.util.Date
import java.util.Locale
import rikka.shizuku.Shizuku

/**
 * jam-ui-redesign: 4 tarjetas + cabecera (XML nativo, sin fragments ni
 * ViewModel). Refresca en `onResume` + callback Shizuku + resultado de
 * permisos. Sin polling ni observers continuos (la UI no mantiene vivo
 * el proceso; el FGS no cambia).
 *
 * N1 (native-apis): pide grants runtime en contexto y guía a los accesos
 * especiales. Sin grant cada método responde error honesto.
 */
class MainActivity : AppCompatActivity() {

    /** Tarjeta 4: "¿el operador toca o solo mira?" (sesión, sin persistencia). */
    private var localClicks = 0

    private val shizukuListener =
        Shizuku.OnRequestPermissionResultListener { _, grantResult ->
            runOnUiThread {
                localClicks++
                Toast.makeText(
                    this,
                    if (grantResult == PackageManager.PERMISSION_GRANTED) "Permiso concedido"
                    else "Permiso denegado",
                    Toast.LENGTH_SHORT
                ).show()
                refreshStatuses()
            }
        }

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ContextCompat.startForegroundService(this, Intent(this, JevForegroundService::class.java))
        setContentView(R.layout.activity_main)
        findViewById<TextView>(R.id.tvHeaderVersion).text =
            "v" + BuildConfig.VERSION_NAME + " · proto v" + CommandDispatcher.PROTOCOL_VERSION
        findViewById<Button>(R.id.btnDump).setOnClickListener { localClicks++; dumpToLogcat() }
        findViewById<Button>(R.id.btnShizuku).setOnClickListener { localClicks++; askShizuku() }
        findViewById<Button>(R.id.btnA11ySettings).setOnClickListener {
            localClicks++
            startActivity(Intent(Settings.ACTION_ACCESSIBILITY_SETTINGS))
        }
        findViewById<Button>(R.id.btnBattery).setOnClickListener { localClicks++; askBatteryIgnore() }
        findViewById<Button>(R.id.btnCopyToken).setOnClickListener { localClicks++; copyToken() }
        findViewById<Button>(R.id.btnRegenToken).setOnClickListener { localClicks++; confirmRegen() }
        findViewById<Button>(R.id.btnPerms).setOnClickListener { localClicks++; askReadPerms() }
        findViewById<Button>(R.id.btnUsage).setOnClickListener {
            localClicks++
            startActivity(Intent(Settings.ACTION_USAGE_ACCESS_SETTINGS))
        }
        findViewById<Button>(R.id.btnNotif).setOnClickListener {
            localClicks++
            startActivity(Intent(Settings.ACTION_NOTIFICATION_LISTENER_SETTINGS))
        }
        findViewById<Button>(R.id.btnWriteSettings).setOnClickListener {
            localClicks++
            startActivity(Intent(Settings.ACTION_MANAGE_WRITE_SETTINGS))
        }
    }

    override fun onResume() {
        super.onResume()
        try {
            Shizuku.addRequestPermissionResultListener(shizukuListener)
        } catch (t: Throwable) {
            JevLog.e(TAG, "shizuku listener no registrado", t)
        }
        refreshStatuses()
    }

    override fun onPause() {
        try {
            Shizuku.removeRequestPermissionResultListener(shizukuListener)
        } catch (t: Throwable) {
            JevLog.e(TAG, "shizuku listener no retirado", t)
        }
        super.onPause()
    }

    // ---- tarjeta 1: servidor ----

    private fun refreshServer() {
        val on = JevForegroundService.serverOn
        val tvState = findViewById<TextView>(R.id.tvServerState)
        tvState.text = if (on) "● ON" else "● DETENIDO"
        tvState.setTextColor(if (on) COL_GREEN else COL_RED)
        findViewById<TextView>(R.id.tvServerBind).text =
            "ws://127.0.0.1:" + JevForegroundService.PORT + "/"
        val n = JevForegroundService.clientCount()
        val authed = JevForegroundService.clientAuthed()
        findViewById<TextView>(R.id.tvServerClients).text =
            "clientes: " + n + " · autenticado: " + when {
                n == 0 -> "—"
                authed == true -> "sí"
                else -> "no"
            }
        findViewById<TextView>(R.id.tvServerProto).text =
            "protocolo v" + CommandDispatcher.PROTOCOL_VERSION
        val started = JevForegroundService.startedAtMs
        findViewById<TextView>(R.id.tvServerUptime).text =
            if (started > 0) "desde " + HHMMSS.format(Date(started)) else "desde …"
        val hint = findViewById<TextView>(R.id.tvServerHint)
        if (!on) {
            hint.visibility = View.VISIBLE
            hint.text = "reabre la app; si persiste revisa logcat tag JamWs"
        } else {
            hint.visibility = View.GONE
        }
    }

    // ---- tarjeta 2: permisos ----

    private fun refreshPerms() {
        // Accesibilidad (no bloquea force_stop/screenshot degradado: ámbar, no rojo global).
        val a11y = isAccessibilityOn()
        val tvA11y = findViewById<TextView>(R.id.tvPermA11y)
        tvA11y.text = if (a11y) "● Accesibilidad: OK" else "● Accesibilidad: APAGADA (ACCESSIBILITY_DISABLED)"
        tvA11y.setTextColor(if (a11y) COL_GREEN else COL_AMBER)
        findViewById<Button>(R.id.btnA11ySettings).visibility =
            if (a11y) View.GONE else View.VISIBLE

        // Shizuku: trichotomía + UID/versión si la API los expone.
        val running = ShizukuBridge.isRunning()
        val granted = running && ShizukuBridge.hasPermission()
        val tvSh = findViewById<TextView>(R.id.tvPermShizuku)
        tvSh.text = "Shizuku: " + when {
            !running -> "● no iniciado — ábrelo y arráncalo (SHIZUKU_UNAVAILABLE)"
            granted -> "● OK (" + shizukuDetail() + ")"
            else -> "● sin permiso (SHIZUKU_DENIED)"
        }
        tvSh.setTextColor(
            when {
                granted -> COL_GREEN
                !running -> COL_AMBER
                else -> COL_RED
            }
        )
        findViewById<Button>(R.id.btnShizuku).visibility =
            if (running && !granted) View.VISIBLE else View.GONE

        // Batería: relevante (el SO mata el FGS).
        val (batOk, batText) = batteryState()
        val tvBat = findViewById<TextView>(R.id.tvPermBattery)
        tvBat.text = batText
        tvBat.setTextColor(
            when (batOk) {
                true -> COL_GREEN
                false -> COL_AMBER
                null -> COL_AMBER
            }
        )
        findViewById<Button>(R.id.btnBattery).visibility =
            if (batOk == false) View.VISIBLE else View.GONE

        // Grants N1 colapsados (opcionales).
        findViewById<TextView>(R.id.tvGrants).text = "Grants N1: uso=" + onOff(hasUsageAccess()) +
            " notif=" + onOff(JamNotificationListener.isConnected()) +
            " contactos=" + onOff(ok(android.Manifest.permission.READ_CONTACTS)) +
            " calendario=" + onOff(ok(android.Manifest.permission.READ_CALENDAR)) +
            " ubicación=" + onOff(ok(android.Manifest.permission.ACCESS_FINE_LOCATION) ||
                ok(android.Manifest.permission.ACCESS_COARSE_LOCATION)) +
            " cámara=" + onOff(ok(android.Manifest.permission.CAMERA))
    }

    /** UID/versión vía API estable 13.1.5; sin inventar PID (no hay API). */
    private fun shizukuDetail(): String = try {
        "permiso API_V23 concedido · uid=" + Shizuku.getUid() + " · v" + Shizuku.getVersion()
    } catch (t: Throwable) {
        "permiso concedido (API_V23)"
    }

    private fun batteryState(): Pair<Boolean?, String> {
        return try {
        val pm = getSystemService(PowerManager::class.java) ?: return null to "● Batería: desconocida"
        if (pm.isIgnoringBatteryOptimizations(packageName)) {
            true to "● Batería: OK (optimización ignorada)"
        } else {
            false to "● Batería: optimizada (el SO puede matar el FGS)"
        }
    } catch (t: Throwable) {
        null to "● Batería: desconocida"
    }
    }

    private fun askBatteryIgnore() {
        try {
            startActivity(
                Intent(
                    Settings.ACTION_REQUEST_IGNORE_BATTERY_OPTIMIZATIONS,
                    Uri.parse("package:" + packageName)
                )
            )
        } catch (t: Throwable) {
            try {
                startActivity(Intent(Settings.ACTION_IGNORE_BATTERY_OPTIMIZATION_SETTINGS))
            } catch (t2: Throwable) {
                Toast.makeText(this, "no se pudo abrir ajustes de batería", Toast.LENGTH_LONG).show()
            }
        }
    }

    // ---- tarjeta 3: token ----

    private fun refreshToken() {
        // Máscara fija: últimos 4, nunca longitud ni prefijo en UI.
        val mask = AuthStore.masked(AuthStore.getOrCreateToken(this))
        findViewById<TextView>(R.id.tvTokenMask).text = "Token: " + mask
        findViewById<TextView>(R.id.tvTokenHint).visibility = View.GONE
    }

    private fun copyToken() {
        val token = AuthStore.getOrCreateToken(this)
        try {
            val cm = getSystemService(Context.CLIPBOARD_SERVICE) as ClipboardManager
            cm.setPrimaryClip(ClipData.newPlainText("jam-token", token))
            Toast.makeText(this, "copiado", Toast.LENGTH_SHORT).show()
        } catch (t: Throwable) {
            Toast.makeText(this, "clipboard falló", Toast.LENGTH_LONG).show()
        }
    }

    private fun confirmRegen() {
        AlertDialog.Builder(this)
            .setTitle("Regenerar token")
            .setMessage("Invalida el cliente actual. ¿Continuar?")
            .setPositiveButton("Regenerar") { _, _ -> regenToken() }
            .setNegativeButton("Cancelar", null)
            .show()
    }

    private fun regenToken() {
        // Gate: con cliente autenticado conectado se aborta (evita bloqueo a mitad de sesión).
        if (JevForegroundService.clientAuthed() == true) {
            val hint = findViewById<TextView>(R.id.tvTokenHint)
            hint.visibility = View.VISIBLE
            hint.text = "desconecta el cliente antes de regenerar"
            Toast.makeText(this, "desconecta el cliente antes", Toast.LENGTH_LONG).show()
            return
        }
        AuthStore.regenerateToken(this)
        JevForegroundService.revokeClients()
        Toast.makeText(this, "token regenerado", Toast.LENGTH_SHORT).show()
        refreshStatuses()
    }

    // ---- tarjeta 4: monitor ----

    private fun refreshMonitor() {
        findViewById<TextView>(R.id.tvMonCounts).text =
            "N0 " + CommandDispatcher.n0() +
                " · N1 " + CommandDispatcher.n1() +
                " · UI " + CommandDispatcher.ui() +
                " · clics " + localClicks + " (sesión)"
        val lastAt = CommandDispatcher.lastAtMs
        findViewById<TextView>(R.id.tvMonLast).text =
            "último: " + CommandDispatcher.lastMethod +
                " " + CommandDispatcher.lastResult +
                if (lastAt > 0) " " + HHMMSS.format(Date(lastAt)) else ""
        val sid = CommandDispatcher.lastSnapshotId
        findViewById<TextView>(R.id.tvMonSnap).text =
            if (sid < 0) "snapshot …" else "snapshot #" + sid +
                " · " + CommandDispatcher.lastSnapshotNodes +
                " nodos · " + CommandDispatcher.lastSnapshotMs + " ms"
    }

    private fun refreshStatuses() {
        refreshServer()
        refreshPerms()
        refreshToken()
        refreshMonitor()
    }

    // ---- resto (sin cambios de comportamiento) ----

    private fun onOff(b: Boolean) = if (b) "OK" else "no"

    private fun ok(perm: String) =
        ContextCompat.checkSelfPermission(this, perm) == PackageManager.PERMISSION_GRANTED

    private fun hasUsageAccess(): Boolean {
        return try {
            val ops = getSystemService(AppOpsManager::class.java)
            @Suppress("DEPRECATION")
            ops.checkOpNoThrow(
                AppOpsManager.OPSTR_GET_USAGE_STATS, android.os.Process.myUid(), packageName
            ) == AppOpsManager.MODE_ALLOWED
        } catch (t: Throwable) {
            false
        }
    }

    private fun askReadPerms() {
        ActivityCompat.requestPermissions(
            this,
            arrayOf(
                android.Manifest.permission.READ_CONTACTS,
                android.Manifest.permission.READ_CALENDAR,
                android.Manifest.permission.ACCESS_FINE_LOCATION,
                android.Manifest.permission.CAMERA
            ),
            REQ_READ
        )
    }

    override fun onRequestPermissionsResult(
        requestCode: Int, permissions: Array<out String>, grantResults: IntArray
    ) {
        super.onRequestPermissionsResult(requestCode, permissions, grantResults)
        if (requestCode == REQ_READ) {
            val n = grantResults.count { it == PackageManager.PERMISSION_GRANTED }
            Toast.makeText(this, "Concedidos $n de ${grantResults.size}", Toast.LENGTH_SHORT).show()
            refreshStatuses()
        }
    }

    private fun isAccessibilityOn(): Boolean {
        val flat = ComponentName(this, JevAccessibilityService::class.java).flattenToString()
        val enabled =
            Settings.Secure.getString(contentResolver, Settings.Secure.ENABLED_ACCESSIBILITY_SERVICES).orEmpty()
        return enabled.split(':').any { it == flat }
    }

    private fun askShizuku() {
        try {
            ShizukuBridge.requestPermission()
        } catch (e: JamError) {
            Toast.makeText(this, e.message, Toast.LENGTH_LONG).show()
        }
    }

    private fun dumpToLogcat() {
        val svc = JevAccessibilityService.instance
        if (svc == null) {
            Toast.makeText(this, "Accesibilidad apagada", Toast.LENGTH_SHORT).show()
            return
        }
        val start = System.nanoTime()
        val snap = svc.dumpUiTree()
        val ms = (System.nanoTime() - start) / 1_000_000
        CommandDispatcher.recordSnapshot(snap.snapshotId, snap.nodes.size, ms)
        Toast.makeText(this, "${snap.nodes.size} nodos en ${ms}ms", Toast.LENGTH_SHORT).show()
        JevLog.i(TAG, "dump snapshot=" + snap.snapshotId + " nodes=" + snap.nodes.size + " ms=" + ms)
        for (n in snap.nodes) {
            JevLog.i(TAG, "JEVNODE " + n.id + "|" + n.text + "|" + n.resourceId)
        }
        refreshMonitor()
    }

    companion object {
        private const val TAG = "JamUi"
        private const val REQ_READ = 41
        private val HHMMSS = SimpleDateFormat("HH:mm:ss", Locale.getDefault())
        // Puntos de estado legibles en claro/oscuro.
        private const val COL_GREEN = 0xFF2E7D32.toInt()
        private const val COL_RED = 0xFFC62828.toInt()
        private const val COL_AMBER = 0xFFEF6C00.toInt()
    }
}
