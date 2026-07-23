package com.almatchlife.app

import android.content.Context
import com.almatchlife.core.SessionTokens
import com.almatchlife.core.android.AndroidKeystoreTokenStore
import com.almatchlife.core.android.AndroidKeystoreStringStore
import com.almatchlife.core.android.SessionTokenCodec
import org.json.JSONObject

internal fun createSessionStore(context: Context): AndroidKeystoreTokenStore = AndroidKeystoreTokenStore(
    context.getSharedPreferences("encrypted_session", Context.MODE_PRIVATE),
    object : SessionTokenCodec {
        override fun encode(tokens: SessionTokens): ByteArray = JSONObject()
            .put("access_token", tokens.accessToken)
            .put("refresh_token", tokens.refreshToken)
            .toString()
            .toByteArray(Charsets.UTF_8)

        override fun decode(bytes: ByteArray): SessionTokens {
            require(bytes.size in 2..20_000)
            val json = JSONObject(bytes.toString(Charsets.UTF_8))
            val access = json.optString("access_token")
            val refresh = json.optString("refresh_token")
            require(access.length in 1..8192 && refresh.length in 1..8192)
            return SessionTokens(access, refresh)
        }
    },
)

internal class AuthenticatedIdentityStore(context: Context) {
    private val encrypted = AndroidKeystoreStringStore(
        context.getSharedPreferences("encrypted_identity", Context.MODE_PRIVATE),
        "al_match_life_identity_v1",
        320,
    )

    fun saveEmail(email: String) {
        val normalized = email.trim().lowercase()
        require(normalized.length in 3..254 && '@' in normalized && '\r' !in normalized && '\n' !in normalized)
        encrypted.save(normalized)
    }

    fun readEmail(): String? = encrypted.read()?.takeIf {
        it.length in 3..254 && '@' in it && '\r' !in it && '\n' !in it
    }

    fun clear() = encrypted.clear()
}
