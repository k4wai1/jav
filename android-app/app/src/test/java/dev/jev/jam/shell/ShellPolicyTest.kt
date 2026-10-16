package dev.jev.jam.shell

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

class ShellPolicyTest {

    private val NEEDS_CONFIRM = ShellPolicy.PolicyVerdict.NEEDS_CONFIRM
    private val FORBIDDEN_SELF = ShellPolicy.PolicyVerdict.FORBIDDEN_SELF
    private val ALLOWED = ShellPolicy.PolicyVerdict.ALLOWED

    @Test
    fun denylistIrreversibles() {
        val cases = listOf(
            "rm -rf /",
            "rm -rf /*",
            "rm -rf *",
            "rm -fr /",
            "pm uninstall com.example.app",
            "cmd package uninstall com.example.app",
            "reboot recovery",
            "reboot bootloader",
            "dd if=/dev/zero of=/dev/block/mmcblk0",
            "mkfs.ext4 /dev/block/mmcblk0p1",
            "wipe data",
            "settings put secure enabled_accessibility_services dev.a/dev.B"
        )
        for (c in cases) {
            assertEquals("«$c» debe exigir confirm", NEEDS_CONFIRM, ShellPolicy.classify(c))
        }
    }

    @Test
    fun forbiddenSelf() {
        for (c in listOf(
            "pm uninstall dev.jev.jam",
            "cmd package uninstall dev.jev.jam",
            "am force-stop dev.jev.jam",
            "pm disable dev.jev.jam"
        )) {
            assertEquals("«$c» es self-harm", FORBIDDEN_SELF, ShellPolicy.classify(c))
        }
    }

    @Test
    fun allowedNormales() {
        for (c in listOf(
            "ls -l /sdcard",
            "echo hola",
            "dumpsys battery",
            "settings get secure foo",
            "df -k /data /sdcard",
            "top -b -n 1 -m 10",
            "rm /sdcard/foo.txt"
        )) {
            assertEquals("«$c» debe permitirse", ALLOWED, ShellPolicy.classify(c))
        }
    }

    @Test
    fun normalizaCajaYEspacios() {
        assertEquals(NEEDS_CONFIRM, ShellPolicy.classify("RM   -RF   /"))
        assertEquals(NEEDS_CONFIRM, ShellPolicy.classify("  Reboot   Recovery "))
    }

    @Test
    fun claveCriticaSettings() {
        assertTrue(ShellPolicy.isCriticalSettingsKey("enabled_accessibility_services"))
        assertTrue(ShellPolicy.isCriticalSettingsKey("ACCESSIBILITY_ENABLED"))
        assertFalse(ShellPolicy.isCriticalSettingsKey("screen_brightness"))
    }

    @Test
    fun rateLimitCincoPorSegundo() {
        val rl = ShellPolicy.SlidingWindowRateLimiter(max = 5, windowMs = 1000L)
        // 5 permitidos en la misma ventana.
        for (i in 0 until 5) {
            assertTrue("req $i debe pasar", rl.allow(1000L))
        }
        assertFalse("la 6ª en la ventana debe rebotar", rl.allow(1000L))
        // Al salir de la ventana, vuelve a permitir.
        assertTrue("fuera de ventana debe pasar", rl.allow(2001L))
    }

    @Test
    fun sha256HexVectoresConocidos() {
        assertEquals(
            "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
            ShellPolicy.sha256Hex("")
        )
        assertEquals(
            "ba7816bf8f01cfea414140de5dae2223b00361a396177a9cb410ff61f20015ad",
            ShellPolicy.sha256Hex("abc")
        )
    }

    @Test
    fun previewTruncaAOchenta() {
        val long = "x".repeat(120)
        val p = ShellPolicy.previewPrefix(long, 80)
        assertEquals(81, p.length) // 80 + "…"
        assertTrue(p.endsWith("…"))
        assertEquals("corto", ShellPolicy.previewPrefix("corto", 80))
    }

    @Test
    fun denylistReason() {
        assertEquals("denylist_irreversible", ShellPolicy.denylistReason("reboot recovery"))
        assertEquals("self_package", ShellPolicy.denylistReason("am force-stop dev.jev.jam"))
        assertEquals(null, ShellPolicy.denylistReason("ls /"))
    }
}
