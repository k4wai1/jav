package dev.jev.jam

import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.view.View
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import dev.jev.jam.service.JevAccessibilityService
import dev.jev.jam.service.JevForegroundService
import dev.jev.jam.shell.ShizukuBridge
import dev.jev.jam.socket.AuthStore
import dev.jev.jam.socket.JamError
import dev.jev.jam.util.JevLog
import rikka.shizuku.Shizuku

/**
 * Fase 3a: onboarding con flujo de permiso Shizuku. El listener se
 * registra en onResume y se quita en onPause (no en onCreate: leak).
 * El botón de permiso solo aparece si Shizuku corre sin permiso.
 */
class MainActivity : AppCompatActivity() {

    private val shizukuListener =
        Shizuku.OnRequestPermissionResultListener { _, grantResult ->
            runOnUiThread {
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
        findViewById<Button>(R.id.btnDump).setOnClickListener { dumpToLogcat() }
        findViewById<Button>(R.id.btnShizuku).setOnClickListener { askShizuku() }
    }

    override fun onResume() {
        super.onResume()
        Shizuku.addRequestPermissionResultListener(shizukuListener)
        refreshStatuses()
    }

    override fun onPause() {
        Shizuku.removeRequestPermissionResultListener(shizukuListener)
        super.onPause()
    }

    private fun refreshStatuses() {
        findViewById<TextView>(R.id.tvAccessibility).text =
            "Accesibilidad: " + if (isAccessibilityOn()) "OK" else "APAGADA"
        val running = ShizukuBridge.isRunning()
        val granted = running && ShizukuBridge.hasPermission()
        findViewById<TextView>(R.id.tvShizuku).text = "Shizuku: " + when {
            !running -> "no iniciado — ábrelo"
            granted -> "OK (permiso)"
            else -> "sin permiso"
        }
        findViewById<Button>(R.id.btnShizuku).visibility =
            if (running && !granted) View.VISIBLE else View.GONE
        val server = if (JevForegroundService.serverOn) {
            "Servidor: ON 127.0.0.1:${JevForegroundService.PORT}\nToken: ${AuthStore.getOrCreateToken(this)}"
        } else {
            "Servidor: detenido"
        }
        findViewById<TextView>(R.id.tvServer).text = server
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
        Toast.makeText(this, "${snap.nodes.size} nodos en ${ms}ms", Toast.LENGTH_SHORT).show()
        JevLog.i(TAG, "dump snapshot=${snap.snapshotId} nodes=${snap.nodes.size} ms=$ms pkg=${snap.packageName}")
        for (n in snap.nodes) {
            JevLog.i(TAG, "JEVNODE ${n.id}|${n.text}|${n.resourceId}")
        }
    }

    companion object {
        private const val TAG = "JamUi"
    }
}
