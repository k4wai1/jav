package dev.k4wai1.jav.socket

import org.junit.After
import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test

/** Fase 2b (AGENTS.md §3.5): 5 fallos/60 s por origen → 5 min de bloqueo. */
class AuthLockoutTest {

    private val origin = "100.64.0.9"

    @Before
    fun setUp() = AuthLockout.clear()

    @After
    fun tearDown() = AuthLockout.clear()

    @Test
    fun cuatroFallosPermitenElQuintoIntento() {
        val t0 = 1_000_000L
        repeat(4) { i ->
            assertFalse("fallo ${i + 1} no debe bloquear", AuthLockout.recordFailure(origin, t0 + i * 100))
        }
        assertFalse(AuthLockout.isLocked(origin, t0 + 500))
    }

    @Test
    fun cincoFallosEnMenosDe60sBloqueanElSexto() {
        val t0 = 2_000_000L
        var locked = false
        repeat(5) { locked = AuthLockout.recordFailure(origin, t0) }
        assertTrue("el 5.º fallo debe bloquear", locked)
        assertTrue(AuthLockout.isLocked(origin, t0 + 1_000))
        assertEquals(AuthLockout.LOCK_MS - 1_000, AuthLockout.retryAfterMs(origin, t0 + 1_000))
    }

    @Test
    fun fallosFueraDeLaVentanaNoBloquean() {
        val t0 = 3_000_000L
        // 4 fallos, luego uno 61 s después: el primero ya salió de la ventana.
        repeat(4) { i -> AuthLockout.recordFailure(origin, t0 + i * 100) }
        assertFalse(AuthLockout.recordFailure(origin, t0 + 61_000))
        assertFalse(AuthLockout.isLocked(origin, t0 + 61_100))
    }

    @Test
    fun tras5MinSeDesbloquea() {
        val t0 = 4_000_000L
        repeat(5) { AuthLockout.recordFailure(origin, t0) }
        assertTrue(AuthLockout.isLocked(origin, t0 + 100_000))
        assertFalse(AuthLockout.isLocked(origin, t0 + AuthLockout.LOCK_MS + 1))
        assertEquals(0L, AuthLockout.retryAfterMs(origin, t0 + AuthLockout.LOCK_MS + 1))
    }

    @Test
    fun exitoIntermedioReseteaElContador() {
        val t0 = 5_000_000L
        repeat(4) { i -> AuthLockout.recordFailure(origin, t0 + i * 100) }
        AuthLockout.recordSuccess(origin)
        assertFalse(AuthLockout.isLocked(origin, t0 + 500))
        // Tras el reset hacen falta 5 fallos nuevos para bloquear.
        var locked = false
        repeat(5) { i -> locked = AuthLockout.recordFailure(origin, t0 + 1_000 + i * 100) }
        assertTrue(locked)
    }

    @Test
    fun origenBloqueadoSigueBloqueadoSinAcumular() {
        val t0 = 6_000_000L
        repeat(5) { i -> AuthLockout.recordFailure(origin, t0 + i * 100) }
        // Intentos durante el bloqueo siguen devolviendo bloqueado.
        assertTrue(AuthLockout.recordFailure(origin, t0 + 10_000))
        assertTrue(AuthLockout.isLocked(origin, t0 + 20_000))
    }

    @Test
    fun origenesIndependientesNoSeAfectan() {
        val t0 = 7_000_000L
        repeat(5) { i -> AuthLockout.recordFailure("10.0.0.1", t0 + i * 100) }
        assertTrue(AuthLockout.isLocked("10.0.0.1", t0 + 500))
        assertFalse(AuthLockout.isLocked("10.0.0.2", t0 + 500))
    }
}
