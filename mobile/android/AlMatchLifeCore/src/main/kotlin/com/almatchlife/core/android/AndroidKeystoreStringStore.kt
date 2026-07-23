package com.almatchlife.core.android

import android.annotation.SuppressLint
import android.content.SharedPreferences
import android.security.keystore.KeyGenParameterSpec
import android.security.keystore.KeyProperties
import android.util.Base64
import java.security.KeyStore
import javax.crypto.AEADBadTagException
import javax.crypto.Cipher
import javax.crypto.KeyGenerator
import javax.crypto.SecretKey
import javax.crypto.spec.GCMParameterSpec

/**
 * Small encrypted store for process-restorable, non-secret identity metadata.
 * The value is still encrypted because an email address is personal data.
 */
@SuppressLint("UseKtx")
class AndroidKeystoreStringStore(
    private val preferences: SharedPreferences,
    private val keyAlias: String,
    private val maximumUtf8Bytes: Int,
) {
    private val keyStore = KeyStore.getInstance(ANDROID_KEY_STORE).apply { load(null) }

    fun save(value: String) {
        val plaintext = value.toByteArray(Charsets.UTF_8)
        require(plaintext.size in 1..maximumUtf8Bytes)
        try {
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(Cipher.ENCRYPT_MODE, getOrCreateKey())
            val saved = preferences.edit()
                .putString(IV_KEY, Base64.encodeToString(cipher.iv, Base64.NO_WRAP))
                .putString(CIPHERTEXT_KEY, Base64.encodeToString(cipher.doFinal(plaintext), Base64.NO_WRAP))
                .commit()
            check(saved) { "could not persist encrypted value" }
        } finally {
            plaintext.fill(0)
        }
    }

    fun read(): String? {
        val iv = preferences.getString(IV_KEY, null) ?: return null
        val ciphertext = preferences.getString(CIPHERTEXT_KEY, null) ?: return null
        return try {
            val key = keyStore.getKey(keyAlias, null) as? SecretKey ?: return null
            val cipher = Cipher.getInstance(TRANSFORMATION)
            cipher.init(
                Cipher.DECRYPT_MODE,
                key,
                GCMParameterSpec(128, Base64.decode(iv, Base64.NO_WRAP)),
            )
            val plaintext = cipher.doFinal(Base64.decode(ciphertext, Base64.NO_WRAP))
            try {
                if (plaintext.size !in 1..maximumUtf8Bytes) return null
                plaintext.toString(Charsets.UTF_8)
            } finally {
                plaintext.fill(0)
            }
        } catch (failure: AEADBadTagException) {
            clear()
            null
        } catch (failure: IllegalArgumentException) {
            clear()
            null
        }
    }

    fun clear() {
        check(preferences.edit().remove(IV_KEY).remove(CIPHERTEXT_KEY).commit()) {
            "could not clear encrypted value"
        }
    }

    private fun getOrCreateKey(): SecretKey {
        (keyStore.getKey(keyAlias, null) as? SecretKey)?.let { return it }
        val generator = KeyGenerator.getInstance(KeyProperties.KEY_ALGORITHM_AES, ANDROID_KEY_STORE)
        generator.init(
            KeyGenParameterSpec.Builder(
                keyAlias,
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
        const val IV_KEY = "value_iv_v1"
        const val CIPHERTEXT_KEY = "value_ciphertext_v1"
    }
}
