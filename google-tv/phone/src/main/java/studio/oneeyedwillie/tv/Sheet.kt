package studio.oneeyedwillie.tv

import android.app.Activity
import android.app.Dialog
import android.content.res.ColorStateList
import android.graphics.Color
import android.graphics.Typeface
import android.graphics.drawable.ColorDrawable
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.View
import android.view.ViewGroup
import android.view.Window
import android.widget.LinearLayout
import android.widget.ScrollView
import android.widget.Switch
import android.widget.TextView

/**
 * Bottom sheets in the phone app's own style (the same look as the More
 * sheet): dark, rounded top, a handle, a title, then rows and buttons.
 * Used for downloads instead of plain Android dialogs.
 */
class Sheet(private val activity: Activity, title: String, subtitle: String? = null) {
    private val dialog = Dialog(activity)
    val body: LinearLayout = LinearLayout(activity).apply {
        orientation = LinearLayout.VERTICAL
        setPadding(dp(20), dp(10), dp(20), dp(18))
        background = GradientDrawable().apply {
            setColor(SHEET)
            val r = dp(18).toFloat()
            cornerRadii = floatArrayOf(r, r, r, r, 0f, 0f, 0f, 0f)
        }
    }

    init {
        dialog.requestWindowFeature(Window.FEATURE_NO_TITLE)
        body.addView(View(activity).apply {
            background = GradientDrawable().apply { setColor(0xFF3A3F47.toInt()); cornerRadius = 99f }
        }, LinearLayout.LayoutParams(dp(36), dp(4)).apply { gravity = Gravity.CENTER_HORIZONTAL; bottomMargin = dp(14) })
        body.addView(TextView(activity).apply {
            text = title; textSize = 20f; setTextColor(Color.WHITE); typeface = Typeface.DEFAULT_BOLD
        })
        if (!subtitle.isNullOrBlank()) body.addView(TextView(activity).apply {
            text = subtitle; textSize = 14f; setTextColor(MUTED); setPadding(0, dp(3), 0, 0)
        })
        body.addView(View(activity), LinearLayout.LayoutParams(1, dp(12)))
    }

    fun dp(v: Int) = (v * activity.resources.displayMetrics.density + .5f).toInt()

    /** A paragraph of plain text. */
    fun text(text: String): Sheet {
        body.addView(TextView(activity).apply {
            this.text = text; textSize = 15f; setTextColor(0xFFD7DBE0.toInt()); setLineSpacing(0f, 1.2f)
            setPadding(0, 0, 0, dp(8))
        })
        return this
    }

    fun heading(text: String): Sheet {
        body.addView(TextView(activity).apply {
            this.text = text.uppercase(); textSize = 11f; letterSpacing = 0.12f
            setTextColor(0xFF8A929C.toInt()); typeface = Typeface.DEFAULT_BOLD
            setPadding(0, dp(10), 0, dp(6))
        })
        return this
    }

    /** One choice from a list (like quality): label on the left, detail on the right. */
    class Choice(val view: View, val select: (Boolean) -> Unit)

    fun choices(rows: List<Pair<String, String>>, selected: Int, onPick: (Int) -> Unit): Sheet {
        val made = mutableListOf<Choice>()
        rows.forEachIndexed { i, (label, detail) ->
            val dot = View(activity)
            val name = TextView(activity).apply { text = label; textSize = 16f; setTextColor(Color.WHITE) }
            val size = TextView(activity).apply { text = detail; textSize = 14f; setTextColor(MUTED) }
            val row = LinearLayout(activity).apply {
                orientation = LinearLayout.HORIZONTAL
                gravity = Gravity.CENTER_VERTICAL
                minimumHeight = dp(52)
                setPadding(dp(14), 0, dp(14), 0)
                isClickable = true; isFocusable = true
                addView(dot, LinearLayout.LayoutParams(dp(20), dp(20)))
                addView(name, LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f).apply { leftMargin = dp(14) })
                addView(size)
            }
            val choice = Choice(row) { on ->
                dot.background = GradientDrawable().apply {
                    shape = GradientDrawable.OVAL
                    if (on) { setColor(ACTIVE); setStroke(dp(5), 0xFF1E2A33.toInt()) } else { setColor(Color.TRANSPARENT); setStroke(dp(2), 0xFF5A616B.toInt()) }
                }
                row.background = GradientDrawable().apply {
                    cornerRadius = dp(12).toFloat()
                    setColor(if (on) 0xFF1B2430.toInt() else Color.TRANSPARENT)
                    if (on) setStroke(dp(1), 0xFF35506A.toInt())
                }
                name.typeface = if (on) Typeface.DEFAULT_BOLD else Typeface.DEFAULT
            }
            made.add(choice)
            row.setOnClickListener { made.forEachIndexed { j, c -> c.select(j == i) }; onPick(i) }
            body.addView(row, LinearLayout.LayoutParams(-1, ViewGroup.LayoutParams.WRAP_CONTENT).apply { bottomMargin = dp(6) })
        }
        made.forEachIndexed { j, c -> c.select(j == selected) }
        return this
    }

    /** An on/off option. */
    fun toggle(label: String, on: Boolean, changed: (Boolean) -> Unit): Sheet {
        val switch = Switch(activity).apply {
            isChecked = on
            thumbTintList = ColorStateList(arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()), intArrayOf(ACTIVE, 0xFFC4C9CF.toInt()))
            trackTintList = ColorStateList(arrayOf(intArrayOf(android.R.attr.state_checked), intArrayOf()), intArrayOf(0xFF3D6680.toInt(), 0xFF3A3F47.toInt()))
            setOnCheckedChangeListener { _, value -> changed(value) }
        }
        body.addView(LinearLayout(activity).apply {
            orientation = LinearLayout.HORIZONTAL
            gravity = Gravity.CENTER_VERTICAL
            minimumHeight = dp(50)
            setPadding(dp(4), 0, 0, 0)
            isClickable = true
            setOnClickListener { switch.toggle() }
            addView(TextView(activity).apply { text = label; textSize = 15f; setTextColor(0xFFE6E9ED.toInt()) },
                LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f))
            addView(switch)
        })
        return this
    }

    /** The main action (filled) or a quiet one; either closes the sheet first. */
    fun button(text: String, primary: Boolean = false, action: () -> Unit = {}): Sheet {
        body.addView(TextView(activity).apply {
            this.text = text; textSize = 16f; gravity = Gravity.CENTER
            typeface = Typeface.DEFAULT_BOLD
            setTextColor(if (primary) 0xFF081018.toInt() else 0xFFE6E9ED.toInt())
            background = GradientDrawable().apply {
                cornerRadius = dp(26).toFloat()
                setColor(if (primary) ACTIVE else 0xFF22262C.toInt())
            }
            isClickable = true; isFocusable = true
            setOnClickListener { dialog.dismiss(); action() }
        }, LinearLayout.LayoutParams(-1, dp(52)).apply { topMargin = dp(if (primary) 14 else 8) })
        return this
    }

    fun onClose(action: () -> Unit): Sheet { dialog.setOnCancelListener { action() }; return this }

    fun show(): Sheet {
        val scroller = ScrollView(activity).apply { addView(body); isVerticalScrollBarEnabled = false }
        if (android.os.Build.VERSION.SDK_INT >= 30) scroller.setOnApplyWindowInsetsListener { _, insets ->
            body.setPadding(dp(20), dp(10), dp(20), dp(18) + insets.getInsets(android.view.WindowInsets.Type.navigationBars()).bottom)
            insets
        }
        dialog.setContentView(scroller)
        dialog.window?.apply {
            setBackgroundDrawable(ColorDrawable(Color.TRANSPARENT))
            setGravity(Gravity.BOTTOM)
            // Phones in landscape (the offline player): don't stretch edge to edge.
            val wide = activity.resources.configuration.screenWidthDp > 600
            setLayout(if (wide) dp(520) else ViewGroup.LayoutParams.MATCH_PARENT, ViewGroup.LayoutParams.WRAP_CONTENT)
            attributes = attributes.apply { windowAnimations = android.R.style.Animation_InputMethod }
        }
        dialog.show()
        return this
    }

    companion object {
        const val SHEET = 0xFF111317.toInt()
        const val ACTIVE = 0xFFA9DDFF.toInt()
        const val MUTED = 0xFF9AA0A6.toInt()
    }
}
