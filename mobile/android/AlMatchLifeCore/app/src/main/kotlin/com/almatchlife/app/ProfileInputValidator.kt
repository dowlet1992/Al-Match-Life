package com.almatchlife.app

internal object ProfileInputValidator {
    fun validate(update: ProfileUpdate) {
        require(update.bio.length <= 1_000) { "Описание слишком длинное" }
        require(update.profession.length <= 160) { "Название профессии слишком длинное" }
        require(update.lookingFor.length <= 500) { "Поле поиска слишком длинное" }
        listOf(update.goals, update.interests, update.skills, update.languages).forEach { value ->
            require(value.length <= 1_200) { "Список слишком длинный" }
            val items = value.split(',', ';').map(String::trim).filter(String::isNotEmpty)
            require(items.size <= 12 && items.all { it.length <= 100 }) {
                "Допускается до 12 пунктов длиной не более 100 символов"
            }
        }
    }
}
