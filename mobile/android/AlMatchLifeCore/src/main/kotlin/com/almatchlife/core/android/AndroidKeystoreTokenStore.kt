package com.almatchlife.core.android

import android.annotation.SuppressLint
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import com.almatchlife.core.SessionTokenStore
import com.almatchlife.core.SessionTokens
import java.security.KeyStore
import javax.crypto.AEADBadTagException
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

interface SessionTokenCodec {
    fun encode(tokens: SessionTokens): ByteArray
    fun decode(bytes: ByteArray): SessionTokens
}

@SuppressLint("UseKtx") // commit() success is part of the atomic encrypted-session contract.
class AndroidKeystoreTokenStore(
    private val preferences: SharedPreferences,
    private val codec: SessionTokenCodec,
) : SessionTokenStore {
    private val keyStore = KeyStore.getInstance(ANDROID_KEY_STORE).apply { load(null) }

    override fun save(tokens: SessionTokens) {
        require(tokens.accessToken.isNotBlank() && tokens.refreshToken.isNotBlank())
        val plaintext = codec.encode(tokens)
        try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
            val ciphertext = cipher.doFinal(plaintext)
            check(preferences.edit()
                .putString(IV_KEY, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
                .putString(CIPHERTEXT_KEY, Base64.encodeToString(ciphertext, Base64.NO_WRAP))
                .commit()) { "could not persist encrypted session" }
        } finally {
            plaintext.fill(0)
        }
    }

    override fun read(): SessionTokens? {
        val iv = preferences.getString(IV_KEY, null) ?: return null
        val ciphertext = preferences.getString(CIPHERTEXT_KEY, null) ?: return null
        return try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(
                Cipher.DECRYPT_MODE,
                keyStore.getKey(KEY_ALIAS, null) as? SecretKey ?: return null,
                GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)),
            )
            val plaintext = cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP))
            try { codec.decode(plaintext) } finally { plaintext.fill(0) }
        } catch (failure: AEADBadTagException) {
            clear()
            null
        }
    }

    override fun clear() {
        check(preferences.edit().remove(IV_KEY).remove(CIPHERTEXT_KEY).commit()) {
            "could not clear encrypted session"
        }
    }

    private fun getOrCreateKey(): SecretKey {
        (keyStore.getKey(KEY_ALIAS, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                KEY_ALIAS,
                KeyProperties.PURPOSE_ENCRYPT or KeyProperties.PURPOSE_DECRYPT,
            )
                .setKeySize(256)
                .setBlockModes(KeyProperties.BLOCK_MODE_GCM)
                .setEncryptionPaddings(KeyProperties.ENCRYPTION_PADDING_NONE)
                .setRandomizedEncryptionRequired(true)
                .build(),
        )
        return generator.generateKey()
    }

    private companion object {
        const val ANDROID_KEY_STORE = "AndroidKeyStore"
        const val TRANSFORMATION = "AES/GCM/NoPadding"
        const val KEY_ALIAS = "al_match_life_session_v1"
        const val IV_KEY = "session_iv_v1"
        const val CIPHERTEXT_KEY = "session_ciphertext_v1"
    }
}
