package dev.k4wai1.jav.util

import android.util.Log
import dev.k4wai1.jav.BuildConfig

/**
 * Log debug-only: en release no emite nada (sin logging en producción).
 */
object JevLog {
    fun d(tag: String, msg: String) {
        if (BuildConfig.DEBUG) Log.d(tag, msg)
    }

    fun i(tag: String, msg: String) {
        if (BuildConfig.DEBUG) Log.i(tag, msg)
    }

    fun w(tag: String, msg: String) {
        if (BuildConfig.DEBUG) Log.w(tag, msg)
    }

    fun e(tag: String, msg: String, t: Throwable? = null) {
        if (BuildConfig.DEBUG) Log.e(tag, msg, t)
    }
}
