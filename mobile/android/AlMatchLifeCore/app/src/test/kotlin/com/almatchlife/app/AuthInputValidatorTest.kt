package com.almatchlife.app

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class AuthInputValidatorTest {
    @Test
    fun acceptsValidRegistration() {
        assertEquals(28, AuthInputValidator.registration("Alice", "28", "Germany", "alice@example.com", "strongpass123"))
    }

    @Test
    fun rejectsUnderageAndMalformedEmail() {
        assertFailsWith<IllegalArgumentException> {
            AuthInputValidator.registration("Alice", "15", "Germany", "alice@example.com", "strongpass123")
        }
        assertFailsWith<IllegalArgumentException> {
            AuthInputValidator.registration("Alice", "28", "Germany", "not-email", "strongpass123")
        }
    }

    @Test
    fun rejectsWeakPasswordAndMalformedCode() {
        assertFailsWith<IllegalArgumentException> { AuthInputValidator.login("alice@example.com", "short") }
        assertFailsWith<IllegalArgumentException> { AuthInputValidator.verification("email", "alice@example.com", "12ab") }
    }
}
