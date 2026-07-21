package com.almatchlife.app

internal object OnboardingInputValidator {
    fun validate(answers: OnboardingAnswers) {
        val fields = listOf(
            answers.lookingFor,
            answers.profession,
            answers.goals,
            answers.interests,
            answers.skills,
            answers.languages,
        )
        require(fields.any { it.isNotBlank() }) { "Заполните хотя бы одно поле или пропустите этот шаг" }
        fields.forEach { require(it.length <= 600) { "Поле слишком длинное" } }
        fields.drop(2).forEach { value ->
            require(value.split(',', ';').count { it.isNotBlank() } <= 12) { "Допускается не более 12 пунктов" }
        }
    }
}
