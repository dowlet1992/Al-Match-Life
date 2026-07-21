package com.almatchlife.app

internal object AuthInputValidator {
    fun login(login: String, password: String) {
        require(login.trim().length in 3..254) { "Введите email или телефон" }
        validatePassword(password)
    }

    fun registration(name: String, age: String, country: String, email: String, password: String): Int {
        require(name.trim().length in 2..100) { "Введите имя" }
        val parsedAge = age.trim().toIntOrNull()
        require(parsedAge != null && parsedAge in 16..120) { "Возраст должен быть от 16 до 120 лет" }
        require(country.trim().length in 2..100) { "Введите страну" }
        val normalizedEmail = email.trim()
        require(normalizedEmail.length <= 254 && EMAIL.matches(normalizedEmail)) { "Введите корректный email" }
        validatePassword(password)
        return parsedAge
    }

    fun verification(contactType: String, contactValue: String, code: String) {
        require(contactType in setOf("email", "phone") && contactValue.length in 3..254)
        require(code.trim().length in 4..12 && code.trim().all(Char::isDigit)) { "Введите код подтверждения" }
    }

    private fun validatePassword(password: String) {
        require(password.length in 8..128) { "Пароль должен содержать от 8 до 128 символов" }
    }

    private val EMAIL = Regex("^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$")
}
