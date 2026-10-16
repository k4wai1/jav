package dev.k4wai1.jav.ui

/** Fake para tests JVM: sin framework Android, reciclaje no-op. */
class FakeA11yNode(
    override val text: CharSequence? = null,
    override val contentDescription: CharSequence? = null,
    override val className: CharSequence? = "android.view.View",
    override val viewIdResourceName: String? = null,
    override val isClickable: Boolean = false,
    override val isEditable: Boolean = false,
    override val isScrollable: Boolean = false,
    override val isEnabled: Boolean = true,
    override val isChecked: Boolean = false,
    override val isFocused: Boolean = false,
    override val isVisibleToUser: Boolean = true,
    override val boundsInScreen: List<Int> = listOf(0, 0, 10, 10),
    private val children: List<FakeA11yNode> = emptyList(),
    private val parentNode: FakeA11yNode? = null,
    private val clickResult: Boolean = false,
    private val focusResult: Boolean = true,
    private val setTextResult: Boolean = true,
    private val pasteResult: Boolean = true
) : A11yNode {
    var recycled = false
        private set

    var clickAttempts = 0
        private set

    var focusAttempts = 0
        private set

    var setTextAttempts = 0
        private set

    var pasteAttempts = 0
        private set

    var lastSetText: CharSequence? = null
        private set

    override val childCount: Int get() = children.size
    override fun getChild(index: Int): A11yNode = children[index]
    override fun parent(): A11yNode? = parentNode
    override fun performClick(): Boolean {
        clickAttempts++
        return clickResult
    }

    override fun performFocus(): Boolean {
        focusAttempts++
        return focusResult
    }

    override fun setText(text: CharSequence): Boolean {
        setTextAttempts++
        lastSetText = text
        return setTextResult
    }

    override fun performPaste(): Boolean {
        pasteAttempts++
        return pasteResult
    }

    override fun recycle() {
        recycled = true
    }
}
