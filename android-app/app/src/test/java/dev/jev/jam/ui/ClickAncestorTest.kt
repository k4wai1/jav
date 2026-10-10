package dev.jev.jam.ui

import org.junit.Assert.assertFalse
import org.junit.Assert.assertNull
import org.junit.Assert.assertSame
import org.junit.Assert.assertTrue
import org.junit.Test

class ClickAncestorTest {

    @Test
    fun `sube un nivel al padre clickable`() {
        val parent = FakeA11yNode(isClickable = true, clickResult = true)
        val child = FakeA11yNode(parentNode = parent)
        assertSame(parent, ClickAncestor.find(child))
    }

    @Test
    fun `sube dos niveles`() {
        val grand = FakeA11yNode(isClickable = true, clickResult = true)
        val mid = FakeA11yNode(parentNode = grand)
        val child = FakeA11yNode(parentNode = mid)
        assertSame(grand, ClickAncestor.find(child))
    }

    @Test
    fun `tope tres niveles`() {
        val l4 = FakeA11yNode(isClickable = true, clickResult = true)
        val l3 = FakeA11yNode(parentNode = l4)
        val l2 = FakeA11yNode(parentNode = l3)
        val l1 = FakeA11yNode(parentNode = l2)
        val child = FakeA11yNode(parentNode = l1)
        assertNull(ClickAncestor.find(child))
    }

    @Test
    fun `ignora ancestro invisible`() {
        val parent = FakeA11yNode(isClickable = true, clickResult = true, isVisibleToUser = false)
        val child = FakeA11yNode(parentNode = parent)
        assertNull(ClickAncestor.find(child))
    }

    @Test
    fun `ignora ancestro clickable que rechaza el click`() {
        val parent = FakeA11yNode(isClickable = true, clickResult = false)
        val child = FakeA11yNode(parentNode = parent)
        assertNull(ClickAncestor.find(child))
    }

    @Test
    fun `prescinde de ancestro no clickable y sube al siguiente`() {
        val top = FakeA11yNode(isClickable = true, clickResult = true)
        val mid = FakeA11yNode(isClickable = false, parentNode = top)
        val child = FakeA11yNode(parentNode = mid)
        assertSame(top, ClickAncestor.find(child))
    }

    @Test
    fun `recicla los no ganadores en exito`() {
        val winner = FakeA11yNode(isClickable = true, clickResult = true)
        val skipped = FakeA11yNode(isClickable = false, parentNode = winner)
        val child = FakeA11yNode(parentNode = skipped)
        assertSame(winner, ClickAncestor.find(child))
        assertTrue(skipped.recycled)
        assertFalse(winner.recycled)
        assertFalse(child.recycled)
    }

    @Test
    fun `recicla todo si no hay ganador`() {
        val top = FakeA11yNode(isClickable = false)
        val mid = FakeA11yNode(isClickable = false, parentNode = top)
        val child = FakeA11yNode(parentNode = mid)
        assertNull(ClickAncestor.find(child))
        assertTrue(mid.recycled)
        assertTrue(top.recycled)
        assertFalse(child.recycled)
    }
}
