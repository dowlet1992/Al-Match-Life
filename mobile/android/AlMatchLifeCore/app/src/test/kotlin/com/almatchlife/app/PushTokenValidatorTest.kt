package com.almatchlife.app

import kotlin.test.Test
import kotlin.test.assertFalse
import kotlin.test.assertTrue

class PushTokenValidatorTest {
    @Test
    fun acceptsBoundedPrintableToken() {
        assertTrue(PushTokenValidator.isValid("token-" + "a".repeat(40)))
    }

    @Test
    fun rejectsShortControlAndOversizedTokens() {
        assertFalse(PushTokenValidator.isValid("short"))
        assertFalse(PushTokenValidator.isValid("a".repeat(40) + "\n"))
        assertFalse(PushTokenValidator.isValid("a".repeat(4097)))
    }
}
