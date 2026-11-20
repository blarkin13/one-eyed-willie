package studio.oneeyedwillie.tv

import android.content.Context

/**
 * The same code builds two separate apps: Yarr Media for Google TV (this
 * module, package studio.oneeyedwillie.tv) and Yarr Media for Android phones
 * (google-tv/phone, its own package). Everything phone-specific is behind
 * [isTv] being false, so the TV app behaves exactly as it always has.
 */
object AppKind {
    const val TV_PACKAGE = "studio.oneeyedwillie.tv"
    fun isTv(context: Context): Boolean = context.packageName == TV_PACKAGE
}
