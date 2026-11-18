package dev.k4wai1.jav.net

import android.content.Context
import android.net.ConnectivityManager

/**
 * Compat v1.2.x: alias histórico de [NetworkDetector] (Fase 2b solo
 * tailnet). Se mantiene para no romper llamadas/tests existentes; el
 * código nuevo usa [NetworkDetector] (v2.1.0: tailnet + LAN Wi-Fi).
 */
@Deprecated("Usa NetworkDetector (v2.1.0: tailnet + LAN)")
object TailnetDetector {

    fun isTailnetIpv4(ip: String): Boolean = NetworkDetector.isTailnetIpv4(ip)

    fun detect(): String? = NetworkDetector.detect()

    fun watch(ctx: Context, onChange: (String?) -> Unit): ConnectivityManager.NetworkCallback? =
        NetworkDetector.watch(ctx) { ips ->
            onChange(ips.firstOrNull { NetworkDetector.isTailnetIpv4(it) })
        }

    fun unwatch(ctx: Context, cb: ConnectivityManager.NetworkCallback?) =
        NetworkDetector.unwatch(ctx, cb)
}
