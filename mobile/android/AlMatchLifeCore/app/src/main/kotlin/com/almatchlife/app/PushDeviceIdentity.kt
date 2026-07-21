package com.almatchlife.app

import android.annotation.SuppressLint
import android.content.SharedPreferences
import java.util.UUID

internal class PushDeviceIdentity(private val preferences: SharedPreferences) {
    @SuppressLint("UseKtx") // A stable ID must be durable before it is registered remotely.
    fun id(): String {
        preferences.getString(KEY, null)?.takeIf(PATTERN::matches)?.let { return it }
        val created = "android-${UUID.randomUUID()}"
        check(preferences.edit().putString(KEY, created).commit()) { "could not persist push device ID" }
        return created
    }

    private companion object {
        const val KEY = "push_device_id_v1"
        val PATTERN = Regex("^[A-Za-z0-9][A-Za-z0-9._:-]{15,127}$")
    }
}

internal object PushTokenValidator {
    fun isValid(token: String): Boolean = token.length in 32..4096 && token.all { it.code in 0x21..0x7e }
}
