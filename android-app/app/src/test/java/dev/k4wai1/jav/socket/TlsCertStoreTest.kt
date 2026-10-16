package dev.k4wai1.jav.socket

import java.security.Security
import org.junit.Assert.assertEquals
import org.junit.Assert.assertNotNull
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Fase 2b: generación X.509v3 con BouncyCastle **explícito** (provider
 * local, sin registro JCA global) + fingerprint SHA-256.
 */
class TlsCertStoreTest {

    @Test
    fun generaCertificadoX509v3Autofirmado() {
        val pair = TlsCertFactory.generate("jam.local", 3650L)
        val cert = pair.cert
        assertEquals("X.509", cert.type)
        assertEquals(3, cert.version) // v3
        assertEquals("CN=jam.local", cert.subjectX500Principal.name)
        assertEquals("CN=jam.local", cert.issuerX500Principal.name)
        assertEquals("RSA", cert.publicKey.algorithm)
        assertEquals(2048, (cert.publicKey as java.security.interfaces.RSAPublicKey).modulus.bitLength())
        // Autofirmado: verifica con su propia clave pública.
        cert.verify(cert.publicKey)
    }

    @Test
    fun fingerprintEsSha256HexDe64() {
        val cert = TlsCertFactory.generate("jam.local", 3650L).cert
        val fp = TlsCertFactory.fingerprintSha256(cert)
        assertEquals(64, fp.length)
        assertTrue(fp.matches(Regex("[0-9a-f]{64}")))
        // Estable entre llamadas.
        assertEquals(fp, TlsCertFactory.fingerprintSha256(cert))
    }

    @Test
    fun noRegistraBouncyCastleEnJcaGlobal() {
        val before = Security.getProviders().size
        val hadBc = TlsCertFactory.globalProvidersContainBc()
        TlsCertFactory.generate("jam.local", 3650L)
        assertEquals("el nº de providers JCA no debe cambiar", before, Security.getProviders().size)
        assertEquals(hadBc, TlsCertFactory.globalProvidersContainBc())
    }

    @Test
    fun pkcs12RoundTripConservaPar() {
        val pair = TlsCertFactory.generate("jam.local", 3650L)
        val p12 = TlsCertFactory.toPkcs12(pair.key, pair.cert, "secreto")
        val (key, cert) = TlsCertFactory.fromPkcs12(p12, "secreto")
        assertNotNull(key)
        assertEquals(pair.cert, cert)
        assertEquals(
            TlsCertFactory.fingerprintSha256(pair.cert),
            TlsCertFactory.fingerprintSha256(cert)
        )
    }

    @Test
    fun sslContextConstruyeConKeyManager() {
        val pair = TlsCertFactory.generate("jam.local", 3650L)
        val ctx = TlsCertFactory.sslContext(pair.key, pair.cert)
        assertEquals("TLS", ctx.protocol)
        assertNotNull(ctx.socketFactory)
    }
}
