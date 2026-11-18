package dev.k4wai1.jav.net

import android.content.Context
import android.net.ConnectivityManager
import android.net.LinkProperties
import android.net.Network
import dev.k4wai1.jav.util.JevLog
import java.net.Inet4Address
import java.net.NetworkInterface

/**
 * v2.1.0: detección de IPs **bindeables** del teléfono, sin `0.0.0.0`:
 *
 *  - Tailscale (CGNAT `100.64.0.0/10`).
 *  - Wi-Fi/LAN privada (RFC 1918: `10/8`, `172.16/12`, `192.168/16`) en
 *    interfaces de tipo Wi-Fi/Ethernet/hotspot (`wlan*`, `eth*`, `ap*`,
 *    `swlan*`), nunca VPN/`tun*` ajenas a Tailscale.
 *
 * Regla dura (AGENTS.md §3.1): el listener WSS solo se bindea a estas IPs
 * concretas; si no hay ninguna, no hay listener fuera de loopback.
 *
 * La re-detección usa `ConnectivityManager.NetworkCallback` (el broadcast
 * `CONNECTIVITY_CHANGE` está restringido desde Android 7).
 */
object NetworkDetector {

    private const val TAG = "JamNet"

    /** Interfaz Wi-Fi/Ethernet/hotspot (heurística estable en Android). */
    private fun isLanInterface(name: String): Boolean {
        val n = name.lowercase()
        return n.startsWith("wlan") || n.startsWith("wifi") ||
            n.startsWith("eth") || n.startsWith("ap") || n.startsWith("swlan")
    }

    private fun octets(ip: String): IntArray? {
        val parts = ip.split('.')
        if (parts.size != 4) return null
        val o = IntArray(4)
        for (i in 0..3) {
            val v = parts[i].toIntOrNull() ?: return null
            if (v < 0 || v > 255) return null
            o[i] = v
        }
        return o
    }

    /**
     * ¿`ip` (IPv4 punteada) cae en el rango CGNAT de Tailscale
     * `100.64.0.0/10` (`100.64.x.x` .. `100.127.x.x`)? Puro, testeable.
     */
    fun isTailnetIpv4(ip: String): Boolean {
        val o = octets(ip) ?: return false
        // /10 sobre 100.64.0.0: 100.01000000.0.0 → 100.64 .. 100.127
        return o[0] == 100 && o[1] in 64..127
    }

    /** ¿IPv4 privada RFC 1918 (`10/8`, `172.16/12`, `192.168/16`)? */
    fun isRfc1918Ipv4(ip: String): Boolean {
        val o = octets(ip) ?: return false
        return when {
            o[0] == 10 -> true
            o[0] == 172 && o[1] in 16..31 -> true
            o[0] == 192 && o[1] == 168 -> true
            else -> false
        }
    }

    /**
     * ¿IPv4 bindeable fuera de loopback? Tailscale o LAN privada. Excluye
     * loopback (`127/8`), link-local (`169.254/16`) y `0.0.0.0`.
     */
    fun isBindableIpv4(ip: String): Boolean {
        val o = octets(ip) ?: return false
        if (o[0] == 127 || o[0] == 0) return false
        if (o[0] == 169 && o[1] == 254) return false
        return isTailnetIpv4(ip) || isRfc1918Ipv4(ip)
    }

    /**
     * Todas las IPv4 bindeables de interfaces activas (tailnet primero,
     * luego LAN), sin duplicados. Puro respecto a red: solo lee interfaces.
     */
    fun detectAll(): List<String> {
        val tailnet = LinkedHashSet<String>()
        val lan = LinkedHashSet<String>()
        try {
            val ifaces = NetworkInterface.getNetworkInterfaces() ?: return emptyList()
            for (nif in ifaces) {
                if (!nif.isUp || nif.isLoopback) continue
                val name = nif.name ?: ""
                val lanIface = isLanInterface(name)
                for (addr in nif.inetAddresses) {
                    val ip = (addr as? Inet4Address)?.hostAddress ?: continue
                    // hostAddress puede traer el scope en IPv6; IPv4 es limpio.
                    when {
                        isTailnetIpv4(ip) -> tailnet.add(ip)
                        lanIface && isRfc1918Ipv4(ip) -> lan.add(ip)
                    }
                }
            }
        } catch (t: Throwable) {
            JevLog.e(TAG, "detectAll falló", t)
        }
        return (tailnet + lan).toList()
    }

    /** Primera IPv4 del tailnet en las interfaces activas, o `null`. */
    fun detect(): String? = detectAll().firstOrNull { isTailnetIpv4(it) }

    /** Primera IPv4 de la LAN/Wi-Fi privada, o `null`. */
    fun detectLan(): String? = detectAll().firstOrNull { isRfc1918Ipv4(it) }

    /**
     * Escucha cambios de red y avisa con la lista vigente de IPs
     * bindeables (posiblemente vacía). Devuelve el callback para
     * desregistrarlo.
     */
    fun watch(
        ctx: Context,
        onChange: (List<String>) -> Unit
    ): ConnectivityManager.NetworkCallback? {
        val cm = ctx.getSystemService(ConnectivityManager::class.java) ?: return null
        val cb = object : ConnectivityManager.NetworkCallback() {
            override fun onAvailable(network: Network) = onChange(detectAll())
            override fun onLost(network: Network) = onChange(detectAll())
            override fun onLinkPropertiesChanged(network: Network, lp: LinkProperties) =
                onChange(detectAll())
        }
        return try {
            cm.registerDefaultNetworkCallback(cb)
            cb
        } catch (t: Throwable) {
            JevLog.e(TAG, "watch red falló", t)
            null
        }
    }

    fun unwatch(ctx: Context, cb: ConnectivityManager.NetworkCallback?) {
        if (cb == null) return
        try {
            ctx.getSystemService(ConnectivityManager::class.java)?.unregisterNetworkCallback(cb)
        } catch (t: Throwable) {
            JevLog.e(TAG, "unwatch red falló", t)
        }
    }
}
