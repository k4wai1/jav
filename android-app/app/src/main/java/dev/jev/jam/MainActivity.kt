package dev.jev.jam

import android.content.ComponentName
import android.content.pm.PackageManager
import android.os.Bundle
import android.provider.Settings
import android.widget.Button
import android.widget.TextView
import android.widget.Toast
import androidx.appcompat.app.AppCompatActivity
import dev.jev.jam.service.JevAccessibilityService
import dev.jev.jam.util.JevLog
import rikka.shizuku.Shizuku

/**
 * Fase 1: onboarding mínima. 3 indicadores + botón temporal que vuelca
 * el árbol a logcat (banco visual; el socket de Fase 2 lo reemplazará).
 */
class MainActivity : AppCompatActivity() {

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
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
        findViewById<TextView>(R.id.tvServer).text = "Servidor: pendiente (Fase 2)"
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
        JevLog.i(TAG, "dump snapshot=${snap.snapshotId} nodes=${snap.nodes.size} ms=$ms secure=${snap.secure}")
        for (n in snap.nodes) {
            JevLog.i(TAG, "JEVNODE ${n.id}|${n.text}|${n.resourceId}")
        }
    }

    companion object {
        private const val TAG = "JamUi"
    }
}
