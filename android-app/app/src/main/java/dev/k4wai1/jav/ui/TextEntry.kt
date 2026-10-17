package dev.k4wai1.jav.ui

/**
 * Fallback de escritura desacoplado del framework para ser testeable en JVM.
 * Primero ACTION_SET_TEXT; si el nodo lo rechaza (típico de inputs dentro de
 * WebViews), se prepara el clipboard y se intenta ACTION_PASTE.
 *
 * v1.2.5: el token `__PASTE__` (texto literal) significa "pega el clipboard
 * del dispositivo": se salta `setText` y `preparePaste` (jamás se pisa el
 * clipboard) y va directo a `ACTION_PASTE` sobre el nodo enfocado.
 */
object TextEntry {
    const val VIA_SET_TEXT = "action_set_text"
    const val VIA_PASTE = "action_paste"

    /** Token-payload: `type_text(text="__PASTE__")` = pegar clipboard. */
    const val PASTE_TOKEN = "__PASTE__"

    /**
     * Intenta [A11yNode.setText] y, si devuelve false, invoca [preparePaste]
     * (setClipboard) y prueba [A11yNode.performPaste]. Con [PASTE_TOKEN] va
     * directo a `performPaste` sin tocar el clipboard. Devuelve el `via`
     * usado (`action_set_text` o `action_paste`) o null si falla.
     */
    fun write(node: A11yNode, text: CharSequence, preparePaste: () -> Unit): String? {
        if (text.toString() == PASTE_TOKEN) {
            return if (node.performPaste()) VIA_PASTE else null
        }
        if (node.setText(text)) return VIA_SET_TEXT
        preparePaste()
        if (node.performPaste()) return VIA_PASTE
        return null
    }
}
