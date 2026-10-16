package dev.jev.jam.ui

/**
 * Fallback de escritura desacoplado del framework para ser testeable en JVM.
 * Primero ACTION_SET_TEXT; si el nodo lo rechaza (típico de inputs dentro de
 * WebViews), se prepara el clipboard y se intenta ACTION_PASTE.
 */
object TextEntry {
    const val VIA_SET_TEXT = "action_set_text"
    const val VIA_PASTE = "action_paste"

    /**
     * Intenta [A11yNode.setText] y, si devuelve false, invoca [preparePaste]
     * (setClipboard) y prueba [A11yNode.performPaste]. Devuelve el `via` usado
     * (`action_set_text` o `action_paste`) o null si ambos fallan.
     */
    fun write(node: A11yNode, text: CharSequence, preparePaste: () -> Unit): String? {
        if (node.setText(text)) return VIA_SET_TEXT
        preparePaste()
        if (node.performPaste()) return VIA_PASTE
        return null
    }
}
