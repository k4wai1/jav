package dev.jev.jam.ui

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
    private val clickResult: Boolean = false
) : A11yNode {
    var recycled = false
        private set

    var clickAttempts = 0
        private set

    override val childCount: Int get() = children.size
    override fun getChild(index: Int): A11yNode = children[index]
    override fun parent(): A11yNode? = parentNode
    override fun performClick(): Boolean {
        clickAttempts++
        return clickResult
    }

    override fun recycle() {
        recycled = true
    }
}
