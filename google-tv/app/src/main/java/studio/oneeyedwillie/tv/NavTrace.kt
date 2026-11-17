package studio.oneeyedwillie.tv

import android.content.Context
import android.content.pm.ApplicationInfo
import android.util.Log

/**
 * Remote-navigation and seek diagnostics (logcat tag "OEWNav").
 *
 * Enabled only for debuggable builds, so the debug APK can still be traced with
 * `adb logcat -s OEWNav` while a release build stays quiet. The message is a
 * lambda, so nothing is formatted when tracing is off.
 */
object NavTrace {
    const val TAG = "OEWNav"

    @Volatile
    var enabled = false
        private set

    fun init(context: Context) {
        enabled = (context.applicationInfo.flags and ApplicationInfo.FLAG_DEBUGGABLE) != 0
    }

    inline fun log(message: () -> String) {
        if (enabled) Log.i(TAG, message())
    }
}
