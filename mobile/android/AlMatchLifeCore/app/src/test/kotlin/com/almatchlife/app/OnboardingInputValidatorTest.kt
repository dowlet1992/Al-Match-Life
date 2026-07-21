package com.almatchlife.app

import kotlin.test.Test
import kotlin.test.assertFailsWith

class OnboardingInputValidatorTest {
    @Test
    fun acceptsBoundedAnswers() {
        OnboardingInputValidator.validate(OnboardingAnswers("Партнёров", "Инженер", "Стартап", "AI", "Kotlin", "Русский"))
    }

    @Test
    fun rejectsEmptyAndOversizedLists() {
        assertFailsWith<IllegalArgumentException> {
            OnboardingInputValidator.validate(OnboardingAnswers("", "", "", "", "", ""))
        }
        assertFailsWith<IllegalArgumentException> {
            OnboardingInputValidator.validate(OnboardingAnswers("x", "", (1..13).joinToString(","), "", "", ""))
        }
    }
}
