package dev.jev.jam.socket

import android.content.Context
import android.util.Base64
import java.security.MessageDigest
import java.security.SecureRandom

/**
 * Token bearer Fase 2: 32 bytes aleatorios en base64url, persistido en
 * SharedPreferences privadas (`allowBackup=false` en manifest).
 * Cifrado en Keystore = Fase 2b (hardening, ver ARCHITECTURE §9).
 */
object AuthStore {

    private const val PREFS = "jam_auth"
    private const val KEY = "ws_token"

    @Synchronized
    fun getOrCreateToken(ctx: Context): String {        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        prefs.getString(KEY, null)?.let { return it }
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        val token = Base64.encodeToString(
            bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING
        )
        prefs.edit().putString(KEY, token).apply()
        return token
    }

    /** Comparación en tiempo constante; vacío nunca valida. */
    fun verify(candidate: String, expected: String): Boolean {
        if (candidate.isEmpty() || expected.isEmpty()) return false
        return MessageDigest.isEqual(
            candidate.toByteArray(Charsets.UTF_8),
            expected.toByteArray(Charsets.UTF_8)
        )
    }

    /**
     * jam-ui-redesign §5: regeneración controlada. Sobrescribe KEY en
     * `jam_auth` y devuelve el nuevo valor. El llamador debe invalidar
     * además `authedScopes` del servidor (ver `JamWsServer.revokeAll`).
     */
    @Synchronized
    fun regenerateToken(ctx: Context): String {
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        val token = Base64.encodeToString(
            bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING
        )
        ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
            .edit().putString(KEY, token).apply()
        return token
    }

    /**
     * Máscara fija para UI: últimos 4 chars, nunca longitud ni prefijo.
     * Cero fuga opcional: si el token es corto, solo puntos.
     */
    fun masked(token: String): String =
        if (token.length >= 4) "••••" + token.takeLast(4) else "••••"

    /** Logcat seguro: 8 hex del SHA-256 (valor nunca). */
    fun sha8(token: String): String = try {
        val d = MessageDigest.getInstance("SHA-256")
            .digest(token.toByteArray(Charsets.UTF_8))
        d.take(4).joinToString("") { "%02x".format(it) }
    } catch (t: Throwable) {
        "?"
    }
}
