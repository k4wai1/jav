package dev.jev.jam.ui

import org.junit.Assert.assertEquals
import org.junit.Assert.assertFalse
import org.junit.Assert.assertTrue
import org.junit.Test

/**
 * Tests JVM del recorrido (Fase 1). Sin Robolectric: [FakeA11yNode]
 * implementa [A11yNode] en Kotlin puro.
 */
class UiTreeExtractorTest {

    @Test
    fun `arbol vacio con raiz nula es secure`() {
        val snap = UiTreeExtractor.extract(null, "p", 7L)
        assertTrue(snap.secure)
        assertTrue(snap.nodes.isEmpty())
        assertEquals(7L, snap.snapshotId)
        assertEquals("p", snap.packageName)
    }

    @Test
    fun `ids BFS contiguos y children validos`() {
        // raíz -> [a, b]; a -> [a1]
        val root = FakeA11yNode(
            text = "root",
            children = listOf(
                FakeA11yNode(text = "a", children = listOf(FakeA11yNode(text = "a1"))),
                FakeA11yNode(text = "b")
            )
        )
        val snap = UiTreeExtractor.extract(root, "p", 1L)
        assertFalse(snap.secure)
        assertEquals(listOf("n_0", "n_1", "n_2", "n_3"), snap.nodes.map { it.id })
        assertEquals(listOf("a", "a1", "b").sorted(), snap.nodes.drop(1).map { it.text.orEmpty() }.sorted())
        // BFS: n_0=root -> [n_1(a), n_2(b)]; n_1=a -> [n_3(a1)]; hojas vacías
        assertEquals(listOf("n_1", "n_2"), snap.nodes[0].children)
        assertEquals(listOf("n_3"), snap.nodes[1].children)
        assertTrue(snap.nodes[2].children.isEmpty())
        assertTrue(snap.nodes[3].children.isEmpty())
        // todo hijo referenciado existe en el snapshot
        val ids = snap.nodes.map { it.id }.toSet()
        snap.nodes.forEach { n -> assertTrue(ids.containsAll(n.children)) }
    }

    @Test
    fun `subarbol invisible se poda`() {
        val root = FakeA11yNode(
            children = listOf(
                FakeA11yNode(text = "visible"),
                FakeA11yNode(
                    text = "invisible",
                    isVisibleToUser = false,
                    children = listOf(FakeA11yNode(text = "nieto"))
                )
            )
        )
        val snap = UiTreeExtractor.extract(root, "p", 1L)
        assertEquals(2, snap.nodes.size) // raíz + "visible"
        assertEquals(listOf("n_0", "n_1"), snap.nodes.map { it.id })
        assertEquals("visible", snap.nodes[1].text)
    }

    @Test
    fun `tope 500 determinista`() {
        val kids = List(1200) { FakeA11yNode(text = "k$it") }
        val root = FakeA11yNode(children = kids)
        val a = UiTreeExtractor.extract(root, "p", 1L)
        val b = UiTreeExtractor.extract(root, "p", 2L)
        assertEquals(500, a.nodes.size)
        assertEquals(a.nodes.map { it.id }, b.nodes.map { it.id })
        assertEquals(a.nodes.map { it.text }, b.nodes.map { it.text })
    }

    @Test
    fun `mapeo de campos y bounds`() {
        val root = FakeA11yNode(
            text = "Buscar",
            contentDescription = "cd",
            className = "android.widget.EditText",
            viewIdResourceName = "com.x:id/s",
            boundsInScreen = listOf(100, 200, 900, 280),
            isClickable = true,
            isEditable = true,
            isScrollable = false,
            isEnabled = true,
            isChecked = false,
            isFocused = true
        )
        val n = UiTreeExtractor.extract(root, "com.x", 1L).nodes.single()
        assertEquals("Buscar", n.text)
        assertEquals("cd", n.contentDesc)
        assertEquals("android.widget.EditText", n.className)
        assertEquals("com.x:id/s", n.resourceId)
        assertEquals(listOf(100, 200, 900, 280), n.bounds)
        assertTrue(n.clickable)
        assertTrue(n.editable)
        assertFalse(n.scrollable)
        assertTrue(n.enabled)
        assertFalse(n.checked)
        assertTrue(n.focused)
        assertTrue(n.visible)
    }

    @Test
    fun `snapshotId monotonico lo pone el servicio`() {
        // El extractor solo propaga; el servicio incrementa (AtomicLong).
        assertEquals(41L, UiTreeExtractor.extract(FakeA11yNode(), "p", 41L).snapshotId)
        assertEquals(42L, UiTreeExtractor.extract(FakeA11yNode(), "p", 42L).snapshotId)
    }
}
