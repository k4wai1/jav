package dev.k4wai1.jav.nat

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

/** v2.3.1: parsers de `open_app` (am start --user 0 + APP_DISABLED). */
class AppLaunchTest {

    @Test
    fun parseComponentTakesLastComponentLine() {
        val out = """
            priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=false
              com.example.app/.MainActivity
        """.trimIndent()
        assertEquals("com.example.app/.MainActivity", AppLaunch.parseComponent(out))
    }

    @Test
    fun parseComponentReturnsNullWhenNoActivity() {
        assertNull(AppLaunch.parseComponent("No activity found"))
        assertNull(AppLaunch.parseComponent(""))
    }

    @Test
    fun parseComponentIgnoresPriorityLine() {
        val out = "priority=0 preferredOrder=0 match=0x108000 specificIndex=-1 isDefault=false"
        assertNull(AppLaunch.parseComponent(out))
    }

    @Test
    fun disabledDetectedByExactPackageLine() {
        val out = """
            package:com.frozen.youtube
            package:com.other.app
        """.trimIndent()
        assertTrue(AppLaunch.isDisabledIn(out, "com.frozen.youtube"))
    }

    @Test
    fun disabledDoesNotMatchPrefixOrSuffix() {
        val out = "package:com.frozen.youtube.extra"
        assertFalse(AppLaunch.isDisabledIn(out, "com.frozen.youtube"))
        assertFalse(AppLaunch.isDisabledIn("", "com.frozen.youtube"))
    }
}
