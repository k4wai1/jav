package dev.k4wai1.jav.socket

import android.content.Context
import dev.k4wai1.jav.util.JevLog
import java.io.ByteArrayInputStream
import java.io.ByteArrayOutputStream
import java.math.BigInteger
import java.security.KeyFactory
import java.security.KeyPair
import java.security.KeyPairGenerator
import java.security.KeyStore
import java.security.MessageDigest
import java.security.PrivateKey
import java.security.SecureRandom
import java.security.Security
import java.security.cert.CertificateFactory
import java.security.cert.X509Certificate
import java.security.spec.PKCS8EncodedKeySpec
import java.util.Date
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec
import javax.net.ssl.KeyManagerFactory
import javax.net.ssl.SSLContext
import org.bouncycastle.asn1.x500.X500Name
import org.bouncycastle.asn1.x509.BasicConstraints
import org.bouncycastle.asn1.x509.Extension
import org.bouncycastle.cert.jcajce.JcaX509CertificateConverter
import org.bouncycastle.cert.jcajce.JcaX509v3CertificateBuilder
import org.bouncycastle.jce.provider.BouncyCastleProvider
import org.bouncycastle.operator.jcajce.JcaContentSignerBuilder

/**
 * Fase 2b (AGENTS.md §3.1/§3.2/§5.3, ARCHITECTURE §2.1/§2.4): certificado
 * X.509v3 autofirmado (`CN=jam.local`, RSA-2048, 10 años) para el listener
 * WSS del tailnet.
 *
 * Gotcha §5.3: **nunca** `Security.addProvider` global. BouncyCastle se
 * instancia local y se pasa explícito a los builders.
 *
 * El material se guarda cifrado en `filesDir` con una clave AES de
 * `AndroidKeyStore`, de modo que un root/pull del APK no exponga la privada.
 */
object TlsCertStore {

    private const val TAG = "JamTls"
    private const val FILE_ENC = "jam_tls.p12.enc"
    private const val KEYSTORE = "AndroidKeyStore"
    private const val ALIAS = "jam_tls_key"
    private const val IV_LEN = 12
    private const val TAG_BITS = 128
    private const val CN = "jam.local"
    private const val VALIDITY_DAYS = 3650L
    private const val P12_PASS = "jam-tls"

    @Volatile
    private var cached: TlsMaterial? = null

    private class TlsMaterial(val key: PrivateKey, val cert: X509Certificate)

    /** Contexto TLS con el par autofirmado; se genera una vez por instalación. */
    @Synchronized
    fun sslContext(ctx: Context): SSLContext {
        val m = material(ctx)
        return TlsCertFactory.sslContext(m.key, m.cert)
    }

    /** SHA-256 del DER del cert en hex (pinning TOFU, 64 hex). */
    @Synchronized
    fun fingerprintSha256(ctx: Context): String =
        TlsCertFactory.fingerprintSha256(material(ctx).cert)

    private fun material(ctx: Context): TlsMaterial {
        cached?.let { return it }
        val file = ctx.filesDir.resolve(FILE_ENC)
        if (file.exists()) {
            load(file.readBytes())?.let {
                cached = it
                return it
            }
            JevLog.e(TAG, "TLS ilegible; se regenera el certificado")
        }
        val fresh = TlsCertFactory.generate(CN, VALIDITY_DAYS)
        try {
            file.writeBytes(encrypt(TlsCertFactory.toPkcs12(fresh.key, fresh.cert, P12_PASS)))
        } catch (t: Throwable) {
            JevLog.e(TAG, "no se pudo persistir TLS", t)
        }
        val m = TlsMaterial(fresh.key, fresh.cert)
        cached = m
        JevLog.i(TAG, "cert generado CN=$CN fp=" + TlsCertFactory.fingerprintSha256(fresh.cert).take(16))
        return m
    }

    private fun load(enc: ByteArray): TlsMaterial? = try {
        val pair = TlsCertFactory.fromPkcs12(decrypt(enc), P12_PASS)
        TlsMaterial(pair.first, pair.second)
    } catch (t: Throwable) {
        JevLog.e(TAG, "carga TLS falló", t)
        null
    }

    private fun encrypt(plain: ByteArray): ByteArray {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.ENCRYPT_MODE, secretKey())
        return c.iv + c.doFinal(plain)
    }

    private fun decrypt(enc: ByteArray): ByteArray {
        val c = Cipher.getInstance("AES/GCM/NoPadding")
        c.init(Cipher.DECRYPT_MODE, secretKey(), GCMParameterSpec(TAG_BITS, enc, 0, IV_LEN))
        return c.doFinal(enc, IV_LEN, enc.size - IV_LEN)
    }

    private fun secretKey(): SecretKey {
        val ks = KeyStore.getInstance(KEYSTORE).apply { load(null) }
        (ks.getEntry(ALIAS, null) as? KeyStore.SecretKeyEntry)?.let { return it.secretKey }
        val gen = KeyGenerator.getInstance("AES", KEYSTORE)
        gen.init(
            android.security.keystore.KeyGenParameterSpec.Builder(
                ALIAS,
                android.security.keystore.KeyProperties.PURPOSE_ENCRYPT or
                    android.security.keystore.KeyProperties.PURPOSE_DECRYPT
            )
                .setBlockModes(android.security.keystore.KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(android.security.keystore.KeyProperties.ENCRYPTION_PADDING_NONE)
                .setKeySize(256)
                .build()
        )
        return gen.generateKey()
    }
}

/**
 * Núcleo puro JVM (testeable sin Android): genera el par + certificado con
 * BouncyCastle **explícito** (provider local, sin registrar en JCA).
 */
internal object TlsCertFactory {

    class Pair2(val key: PrivateKey, val cert: X509Certificate)

    private val bc = BouncyCastleProvider()

    fun generate(cn: String, validityDays: Long): Pair2 {
        val kpg = KeyPairGenerator.getInstance("RSA")
        kpg.initialize(2048, SecureRandom())
        val kp: KeyPair = kpg.generateKeyPair()

        val serial = BigInteger(160, SecureRandom()).abs()
        val now = System.currentTimeMillis()
        val notBefore = Date(now - 60_000L)
        val notAfter = Date(now + validityDays * 24L * 3600L * 1000L)
        val name = X500Name("CN=$cn")

        val builder = JcaX509v3CertificateBuilder(
            name, serial, notBefore, notAfter, name, kp.public
        )
        // Fuerza versión 3 (X.509v3) con basicConstraints + keyUsage.
        builder.addExtension(Extension.basicConstraints, true, BasicConstraints(false))
        val signer = JcaContentSignerBuilder("SHA256WithRSA")
            .setProvider(bc)
            .build(kp.private)
        val cert = JcaX509CertificateConverter().setProvider(bc).getCertificate(builder.build(signer))
        cert.verify(kp.public)
        return Pair2(kp.private, cert)
    }

    fun fingerprintSha256(cert: X509Certificate): String {
        val d = MessageDigest.getInstance("SHA-256").digest(cert.encoded)
        return d.joinToString("") { "%02x".format(it) }
    }

    fun toPkcs12(key: PrivateKey, cert: X509Certificate, password: String): ByteArray {
        val ks = KeyStore.getInstance("PKCS12")
        ks.load(null, null)
        ks.setKeyEntry("jam", key, password.toCharArray(), arrayOf(cert))
        val out = ByteArrayOutputStream()
        ks.store(out, password.toCharArray())
        return out.toByteArray()
    }

    fun fromPkcs12(bytes: ByteArray, password: String): Pair<PrivateKey, X509Certificate> {
        val ks = KeyStore.getInstance("PKCS12")
        ks.load(ByteArrayInputStream(bytes), password.toCharArray())
        val key = ks.getKey("jam", password.toCharArray()) as PrivateKey
        val cert = ks.getCertificate("jam") as X509Certificate
        return key to cert
    }

    fun sslContext(key: PrivateKey, cert: X509Certificate): SSLContext {
        val ks = KeyStore.getInstance("PKCS12")
        ks.load(null, null)
        ks.setKeyEntry("jam", key, "x".toCharArray(), arrayOf(cert))
        val kmf = KeyManagerFactory.getInstance(KeyManagerFactory.getDefaultAlgorithm())
        kmf.init(ks, "x".toCharArray())
        val ctx = SSLContext.getInstance("TLS")
        ctx.init(kmf.keyManagers, null, null)
        return ctx
    }

    /** Solo para tests: ¿BC sigue sin estar registrado en el JCA global? */
    fun globalProvidersContainBc(): Boolean = Security.getProvider("BC") != null

    // Utilidades sin uso en producción, expuestas para tests/robustez.
    fun certFromDer(der: ByteArray): X509Certificate =
        CertificateFactory.getInstance("X.509")
            .generateCertificate(ByteArrayInputStream(der)) as X509Certificate

    @Suppress("unused")
    fun keyFromPkcs8(der: ByteArray): PrivateKey =
        KeyFactory.getInstance("RSA").generatePrivate(PKCS8EncodedKeySpec(der))

    // Referencia para que el compilador no elimine las constantes del provider.
    @Suppress("unused")
    private val providerName: String = bc.name
}
