package dev.k4wai1.jav.socket

import android.content.Context
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import dev.k4wai1.jav.util.JevLog
import java.security.KeyStore
import java.security.MessageDigest
import java.security.SecureRandom
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Token bearer: 32 bytes aleatorios en base64url, persistido en
 * SharedPreferences privadas (`allowBackup=false`).
 *
 * Fase 2b (ARCHITECTURE §2.5): en reposo se cifra con AES/GCM/NoPadding de
 * 256 bits cuya clave vive en `AndroidKeyStore` (alias `jam_token_key`).
 * Se guarda `iv(12) || ciphertext` en Base64 bajo `ws_token_enc`.
 *
 * Migración suave: si existe el `ws_token` plano previo y aún no hay
 * `ws_token_enc`, se cifra ESE MISMO valor, se borra la clave plana y se
 * devuelve el token de siempre → el `.env` del operador sigue válido.
 */
object AuthStore {

    private const val PREFS = "jam_auth"
    private const val KEY = "ws_token"          // legado en claro (se migra)
    private const val KEY_ENC = "ws_token_enc"  // iv+ct Base64
    private const val KEYSTORE = "AndroidKeyStore"
    private const val ALIAS = "jam_token_key"
    private const val IV_LEN = 12
    private const val TAG_LEN_BITS = 128
    private const val TAG = "JamWs"

    @Synchronized
    fun getOrCreateToken(ctx: Context): String {
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)

        prefs.getString(KEY_ENC, null)?.let { enc ->
            decrypt(enc)?.let { return it }
            JevLog.e(TAG, "token cifrado ilegible; se rota (Keystore)")
        }

        // Migración suave del token plano previo.
        prefs.getString(KEY, null)?.let { plain ->
            val enc = encrypt(plain)
            if (enc != null) {
                prefs.edit().putString(KEY_ENC, enc).remove(KEY).apply()
                JevLog.i(TAG, "token migrado a Keystore (mismo valor)")
                return plain
            }
            JevLog.e(TAG, "no se pudo cifrar el token; se mantiene en claro")
            return plain
        }

        // Token nuevo (32 bytes) ya cifrado.
        val token = newToken()
        val enc = encrypt(token)
        val edit = prefs.edit()
        if (enc != null) edit.putString(KEY_ENC, enc) else edit.putString(KEY, token)
        edit.apply()
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
     * jam-ui-redesign §5: regeneración controlada. Genera 32 bytes nuevos y
     * los persiste ya cifrados. El llamador debe invalidar además
     * `authedScopes` del servidor (ver `JamWsServer.revokeAll`).
     */
    @Synchronized
    fun regenerateToken(ctx: Context): String {
        val token = newToken()
        val prefs = ctx.getSharedPreferences(PREFS, Context.MODE_PRIVATE)
        val enc = encrypt(token)
        val edit = prefs.edit().remove(KEY)
        if (enc != null) edit.putString(KEY_ENC, enc) else edit.putString(KEY, token)
        edit.apply()
        return token
    }

    private fun newToken(): String {
        val bytes = ByteArray(32)
        SecureRandom().nextBytes(bytes)
        return Base64.encodeToString(
            bytes, Base64.URL_SAFE or Base64.NO_WRAP or Base64.NO_PADDING
        )
    }

    /** Cifra `plain` → Base64(iv||ct). `null` si el Keystore no está disponible. */
    private fun encrypt(plain: String): String? = try {
        val cipher = Cipher.getInstance("AES/GCM/NoPadding")
        cipher.init(Cipher.ENCRYPT_MODE, secretKey())
        val iv = cipher.iv
        val ct = cipher.doFinal(plain.toByteArray(Charsets.UTF_8))
        Base64.encodeToString(iv + ct, Base64.NO_WRAP)
    } catch (t: Throwable) {
        JevLog.e(TAG, "encrypt token falló", t)
        null
    }

    private fun decrypt(enc: String): String? = try {
        val raw = Base64.decode(enc, Base64.NO_WRAP)
        if (raw.size <= IV_LEN) {
            null
        } else {
            val cipher = Cipher.getInstance("AES/GCM/NoPadding")
            cipher.init(
                Cipher.DECRYPT_MODE,
                secretKey(),
                GCMParameterSpec(TAG_LEN_BITS, raw, 0, IV_LEN)
            )
            String(cipher.doFinal(raw, IV_LEN, raw.size - IV_LEN), Charsets.UTF_8)
        }
    } catch (t: Throwable) {
        JevLog.e(TAG, "decrypt token falló", t)
        null
    }

    /** Clave AES-256 en AndroidKeyStore; se crea una vez (alias fijo). */
    private fun secretKey(): SecretKey {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, KEYSTORE)
        gen.init(
            KeyGenParameterSpec.Builder(
                ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return gen.generateKey()
    }

    /**
     * Máscara fija para UI: últimos 4 chars, nunca longitud ni prefijo.
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
