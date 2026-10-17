package dev.k4wai1.jav.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertTrue
import org.junit.Test

class LiveNodeReanchorTest {

    private fun expected(idx: Int = 1) = UiNode(
        id = "n_$idx", text = "Enviar", contentDesc = "send",
        className = "android.widget.Button", resourceId = "com.demo:id/send",
        bounds = listOf(40, 100, 240, 200), clickable = true, editable = false,
        scrollable = false, enabled = true, checked = false, focused = false,
        visible = true, children = emptyList()
    )

    private fun sendLive(b: List<Int> = listOf(40, 100, 240, 200)) = FakeA11yNode(
        text = "Enviar", contentDescription = "send",
        className = "android.widget.Button", viewIdResourceName = "com.demo:id/send",
        isClickable = true, boundsInScreen = b
    )

    private fun decoy() = FakeA11yNode(
        text = "Cancelar", className = "android.widget.Button",
        boundsInScreen = listOf(300, 300, 400, 400)
    )

    private fun rootOf(vararg kids: FakeA11yNode) = FakeA11yNode(
        text = "root", className = "android.widget.FrameLayout",
        boundsInScreen = listOf(0, 0, 1080, 2400), children = kids.toList()
    )

    @Test
    fun exactIndexReturnsSameNodeNoDrift() {
        val send = sendLive()
        val decoy = decoy()
        val root = rootOf(send, decoy)

        val res = LiveNodeReanchor.reanchor(root, expected(1), 1)

        assertEquals(ReanchorStatus.EXACT, res.status)
        assertFalse(res.reanchored)
        assertEquals("Enviar", res.node!!.text)
        assertFalse(send.recycled)
        assertTrue(decoy.recycled)
        assertFalse(root.recycled)
    }

    @Test
    fun driftWithinToleranceReanchors() {
        val decoy = decoy()
        val send = sendLive(listOf(45, 105, 245, 205))
        val root = rootOf(decoy, send)

        val res = LiveNodeReanchor.reanchor(root, expected(1), 1)

        assertEquals(ReanchorStatus.REANCHORED, res.status)
        assertTrue(res.reanchored)
        assertEquals("Enviar", res.node!!.text)
        assertTrue(decoy.recycled)
        assertFalse(send.recycled)
        assertFalse(root.recycled)
    }

    @Test
    fun largeDriftWithinNewLimitReanchors() {
        val decoy = decoy()
        val send = sendLive(listOf(40, 210, 240, 310))
        val root = rootOf(decoy, send)

        val res = LiveNodeReanchor.reanchor(root, expected(1), 1)

        assertEquals(ReanchorStatus.REANCHORED, res.status)
        assertEquals("Enviar", res.node!!.text)
        assertTrue(decoy.recycled)
        assertFalse(send.recycled)
        assertFalse(root.recycled)
    }

    @Test
    fun driftBeyondToleranceUniqueIdentityReanchors() {
        val decoy = decoy()
        val send = sendLive(listOf(40, 300, 240, 400))
        val root = rootOf(decoy, send)

        val res = LiveNodeReanchor.reanchor(root, expected(1), 1)

        assertEquals(ReanchorStatus.REANCHORED, res.status)
        assertTrue(res.reanchored)
        assertEquals("Enviar", res.node!!.text)
        assertTrue(decoy.recycled)
        assertFalse(send.recycled)
        assertFalse(root.recycled)
    }

    @Test
    fun twoFarIdenticalCandidatesFailsAmbiguous() {
        val first = sendLive(listOf(40, 500, 240, 600))
        val second = sendLive(listOf(40, 800, 240, 900))
        val root = rootOf(decoy(), first, second)

        val res = LiveNodeReanchor.reanchor(root, expected(1), 1)

        assertNull(res.node)
        assertEquals(ReanchorStatus.AMBIGUOUS, res.status)
        assertEquals("STALE_SNAPSHOT", res.status.errorCode)
        assertTrue(first.recycled)
        assertTrue(second.recycled)
        assertFalse(root.recycled)
    }

    @Test
    fun uniqueIdentityWithoutAnchorFailsNotFound() {
        val bare = UiNode(
            id = "n_1", text = null, contentDesc = null,
            className = "android.widget.Button", resourceId = null,
            bounds = listOf(40, 100, 240, 200), clickable = true, editable = false,
            scrollable = false, enabled = true, checked = false, focused = false,
            visible = true, children = emptyList()
        )
        val live = FakeA11yNode(
            text = null, contentDescription = null,
            className = "android.widget.Button", viewIdResourceName = null,
            boundsInScreen = listOf(40, 500, 240, 600)
        )
        val root = rootOf(decoy(), live)

        val res = LiveNodeReanchor.reanchor(root, bare, 1)

        assertNull(res.node)
        assertEquals(ReanchorStatus.NOT_FOUND, res.status)
        assertTrue(live.recycled)
        assertFalse(root.recycled)
    }

    @Test
    fun targetGoneFailsNotFound() {
        val decoy = decoy()
        val root = rootOf(decoy)

        val res = LiveNodeReanchor.reanchor(root, expected(1), 1)

        assertNull(res.node)
        assertEquals(ReanchorStatus.NOT_FOUND, res.status)
        assertEquals("STALE_SNAPSHOT", res.status.errorCode)
        assertTrue(decoy.recycled)
        assertFalse(root.recycled)
    }

    @Test
    fun twoCandidatesFailsAmbiguous() {
        val decoy = decoy()
        val first = sendLive()
        val second = sendLive(listOf(50, 110, 250, 210))
        val root = rootOf(decoy, first, second)

        val res = LiveNodeReanchor.reanchor(root, expected(1), 1)

        assertNull(res.node)
        assertEquals(ReanchorStatus.AMBIGUOUS, res.status)
        assertEquals("STALE_SNAPSHOT", res.status.errorCode)
        assertTrue(decoy.recycled)
        assertTrue(first.recycled)
        assertTrue(second.recycled)
        assertFalse(root.recycled)
    }

    @Test
    fun nullRootIsNoWindow() {
        val res = LiveNodeReanchor.reanchor(null, expected(), 1)

        assertNull(res.node)
        assertEquals(ReanchorStatus.NO_WINDOW, res.status)
        assertEquals("SELECTOR_NOT_FOUND", res.status.errorCode)
    }

    @Test
    fun invisibleRootIsNoWindowAndBorrowed() {
        val root = FakeA11yNode(
            text = "root", className = "android.widget.FrameLayout",
            isVisibleToUser = false, boundsInScreen = listOf(0, 0, 1080, 2400)
        )

        val res = LiveNodeReanchor.reanchor(root, expected(), 1)

        assertEquals(ReanchorStatus.NO_WINDOW, res.status)
        assertNull(res.node)
        assertFalse(root.recycled)
    }

    @Test
    fun identityMismatchFailsNotFound() {
        val badText = FakeA11yNode(
            text = "Reenviar", contentDescription = "send",
            className = "android.widget.Button", viewIdResourceName = "com.demo:id/send",
            boundsInScreen = listOf(40, 100, 240, 200)
        )
        val badResource = FakeA11yNode(
            text = "Enviar", contentDescription = "send",
            className = "android.widget.Button", viewIdResourceName = "com.demo:id/other",
            boundsInScreen = listOf(40, 100, 240, 200)
        )
        val badClass = FakeA11yNode(
            text = "Enviar", contentDescription = "send",
            className = "android.widget.TextView", viewIdResourceName = "com.demo:id/send",
            boundsInScreen = listOf(40, 100, 240, 200)
        )
        val badDesc = FakeA11yNode(
            text = "Enviar", contentDescription = "cancelar",
            className = "android.widget.Button", viewIdResourceName = "com.demo:id/send",
            boundsInScreen = listOf(40, 100, 240, 200)
        )

        for (live in listOf(badText, badResource, badClass, badDesc)) {
            val res = LiveNodeReanchor.reanchor(rootOf(live), expected(1), 1)
            assertEquals(ReanchorStatus.NOT_FOUND, res.status)
            assertNull(res.node)
        }
    }
}
