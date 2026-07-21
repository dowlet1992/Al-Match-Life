package com.almatchlife.app

import kotlin.test.Test
import kotlin.test.assertFailsWith

class ProfileInputValidatorTest {
    @Test
    fun acceptsBoundedProfile() {
        ProfileInputValidator.validate(ProfileUpdate("Bio", "Engineer", "Team", "Startup", "AI", "Kotlin", "Russian"))
    }

    @Test
    fun rejectsOversizedTextAndLists() {
        assertFailsWith<IllegalArgumentException> {
            ProfileInputValidator.validate(ProfileUpdate("x".repeat(1001), "", "", "", "", "", ""))
        }
        assertFailsWith<IllegalArgumentException> {
            ProfileInputValidator.validate(ProfileUpdate("", "", "", (1..13).joinToString(","), "", "", ""))
        }
    }
}
