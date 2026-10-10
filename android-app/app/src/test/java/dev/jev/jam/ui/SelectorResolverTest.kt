package dev.jev.jam.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertNull
import org.junit.Test

/** Tests JVM del selector semántico (PROTOCOL.md §4.0). */
class SelectorResolverTest {

    private val nodes = listOf(
        UiNode("n_0", "Buscar", null, "android.widget.EditText", "com.x:id/search",
            listOf(0, 0, 100, 50), clickable = true, editable = true,
            scrollable = false, enabled = true, checked = false, focused = false,
            visible = true, children = emptyList()),
        UiNode("n_1", "Buscar", null, "android.widget.TextView", "com.x:id/label",
            listOf(0, 60, 100, 90), clickable = false, editable = false,
            scrollable = false, enabled = true, checked = false, focused = false,
            visible = true, children = emptyList()),
        UiNode("n_2", "Enviar", "enviar mensaje", "android.widget.Button", "com.x:id/send",
            listOf(0, 100, 100, 150), clickable = true, editable = false,
            scrollable = false, enabled = true, checked = false, focused = false,
            visible = true, children = emptyList()),
        // Icono sin texto: solo content-desc (caso YouTube/lupa).
        UiNode("n_3", null, "Buscar", "android.widget.ImageView", "com.x:id/search_icon",
            listOf(0, 160, 100, 210), clickable = true, editable = false,
            scrollable = false, enabled = true, checked = false, focused = false,
            visible = true, children = emptyList())
    )

    @Test
    fun `texto exacto primer match`() {
        assertEquals("n_0", SelectorResolver.resolve(nodes, Selector(text = "Buscar"))?.id)
    }

    @Test
    fun `AND con clickable desambigua`() {
        val r = SelectorResolver.resolve(nodes, Selector(text = "Buscar", clickable = false))
        assertEquals("n_1", r?.id)
    }

    @Test
    fun `text_contains parcial`() {
        assertEquals("n_2", SelectorResolver.resolve(nodes, Selector(textContains = "nv"))?.id)
    }

    @Test
    fun `resource_id por sufijo`() {
        assertEquals("n_2", SelectorResolver.resolve(nodes, Selector(resourceId = "id/send"))?.id)
        assertEquals("n_0", SelectorResolver.resolve(nodes, Selector(resourceId = "com.x:id/search"))?.id)
    }

    @Test
    fun `index elige el n-esimo`() {
        assertEquals("n_1", SelectorResolver.resolve(nodes, Selector(text = "Buscar", index = 1))?.id)
        assertNull(SelectorResolver.resolve(nodes, Selector(text = "Buscar", index = 5)))
    }

    @Test
    fun `sin match devuelve null`() {
        assertNull(SelectorResolver.resolve(nodes, Selector(text = "Inexistente")))
        assertNull(SelectorResolver.resolve(nodes, Selector(resourceId = "id/otro")))
    }

    @Test
    fun `text_contains hibrido matchea content-desc sin texto`() {
        // tap_text("Buscar") debe resolver el icono sin texto (n_3 vive
        // solo en content-desc). Con index=2 saltamos n_0/n_1 (texto).
        assertEquals("n_3", SelectorResolver.resolve(nodes, Selector(textContains = "Buscar", index = 2))?.id)
    }

    @Test
    fun `text_contains case-insensitive`() {
        assertEquals("n_0", SelectorResolver.resolve(nodes, Selector(textContains = "BUSCAR"))?.id)
        assertEquals("n_3", SelectorResolver.resolve(nodes, Selector(textContains = "buscar", index = 2))?.id)
    }

    @Test
    fun `text_contains parcial sobre content-desc`() {
        // "ensa" vive en "enviar mensaje" (n_2 desc) y en "Enviar" (texto).
        assertEquals("n_2", SelectorResolver.resolve(nodes, Selector(textContains = "ENSA"))?.id)
    }
}
