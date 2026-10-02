package dev.jev.jam

import android.content.ComponentName
import android.content.Intent
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import androidx.core.content.ContextCompat
import dev.jev.jam.service.JevAccessibilityService
import dev.jev.jam.service.JevForegroundService
import dev.jev.jam.socket.AuthStore
import dev.jev.jam.util.JevLog
import rikka.shizuku.Shizuku

/**
 * Fase 2: onboarding. 3 indicadores + token + botón temporal de volcado
 * a logcat (banco visual hasta que el socket lo reemplace del todo).
 * Arranca el ForegroundService (servidor WS) al abrir.
 */
class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        ContextCompat.startForegroundService(this, Intent(this, JevForegroundService::class.java))
        setContentView(R.layout.activity_main)
        findViewById<Button>(R.id.btnDump).setOnClickListener { dumpToLogcat() }
    }

    override fun onResume() {
        super.onResume()
        refreshStatuses()
    }

    private fun refreshStatuses() {
        findViewById<TextView>(R.id.tvAccessibility).text =
            "Accesibilidad: " + if (isAccessibilityOn()) "OK" else "APAGADA"
        findViewById<TextView>(R.id.tvShizuku).text = "Shizuku: " + shizukuStatus()
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

    private fun shizukuStatus(): String {
        return try {
            if (!Shizuku.pingBinder()) return "no iniciado"
            if (Shizuku.checkSelfPermission() == PackageManager.PERMISSION_GRANTED) {
                "OK (permiso)"
            } else {
                "sin permiso"
            }
        } catch (t: Throwable) {
            "no disponible"
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
