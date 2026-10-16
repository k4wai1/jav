package dev.k4wai1.jav.net

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.Network
import dev.k4wai1.jav.util.JevLog
import java.net.Inet4Address
import java.net.NetworkInterface

/**
 * Fase 2b (AGENTS.md §3.1/§5.9): detección de la IP del tailnet
 * (CGNAT `100.64.0.0/10`) para bindear el 2.º listener WSS.
 *
 * Nunca asume `0.0.0.0`: si no hay IP tailnet, no hay listener WSS.
 * La re-detección usa `ConnectivityManager.NetworkCallback` (el broadcast
 * `CONNECTIVITY_CHANGE` está restringido desde Android 7).
 */
object TailnetDetector {

    private const val TAG = "JamNet"

    /**
     * ¿`ip` (IPv4 punteada) cae en el rango CGNAT de Tailscale
     * `100.64.0.0/10` (`100.64.x.x` .. `100.127.x.x`)? Puro, testeable.
     */
    fun isTailnetIpv4(ip: String): Boolean {
        val parts = ip.split('.')
        if (parts.size != 4) return false
        val o = IntArray(4)
        for (i in 0..3) {
            val v = parts[i].toIntOrNull() ?: return false
            if (v < 0 || v > 255) return false
            o[i] = v
        }
        // /10 sobre 100.64.0.0: 100.01000000.0.0 → 100.64 .. 100.127
        return o[0] == 100 && o[1] in 64..127
    }

    /** Primera IPv4 del tailnet en las interfaces activas, o `null`. */
    fun detect(): String? {
        return try {
            val ifaces = NetworkInterface.getNetworkInterfaces() ?: return null
            var found: String? = null
            for (nif in ifaces) {
                if (!nif.isUp || nif.isLoopback) continue
                for (addr in nif.inetAddresses) {
                    val ip = (addr as? Inet4Address)?.hostAddress ?: continue
                    if (isTailnetIpv4(ip)) {
                        found = ip
                        break
                    }
                }
                if (found != null) break
            }
            found
        } catch (t: Throwable) {
            JevLog.e(TAG, "detect tailnet falló", t)
            null
        }
    }

    /**
     * Escucha cambios de red y avisa con la IP tailnet vigente (o `null`).
     * Devuelve el callback para poder desregistrarlo.
     */
    fun watch(ctx: Context, onChange: (String?) -> Unit): ConnectivityManager.NetworkCallback? {
        val cm = ctx.getSystemService(ConnectivityManager::class.java) ?: return null
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) = onChange(detect())
            override fun onLost(network: Network) = onChange(detect())
            override fun onLinkPropertiesChanged(network: Network, lp: LinkProperties) =
                onChange(detect())
        }
        return try {
            cm.registerDefaultNetworkCallback(cb)
            cb
        } catch (t: Throwable) {
            JevLog.e(TAG, "watch tailnet falló", t)
            null
        }
    }

    fun unwatch(ctx: Context, cb: ConnectivityManager.NetworkCallback?) {
        if (cb == null) return
        try {
            ctx.getSystemService(ConnectivityManager::class.java)?.unregisterNetworkCallback(cb)
        } catch (t: Throwable) {
            JevLog.e(TAG, "unwatch tailnet falló", t)
        }
    }
}
