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
    fun getOrCreateToken(ctx: Context): String {
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
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
}
