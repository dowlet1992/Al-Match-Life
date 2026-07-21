package com.almatchlife.app

import com.almatchlife.core.ApiClientException
import java.io.IOException
import java.net.ConnectException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.util.concurrent.CompletionException
import java.util.concurrent.ExecutionException

internal enum class FailureKind { OFFLINE, TIMEOUT, SESSION_EXPIRED, SERVICE_UNAVAILABLE, INVALID_INPUT, GENERIC }
internal data class UserFacingFailure(val kind: FailureKind, val validationMessage: String? = null)

internal object UserFacingFailureMapper {
    fun map(failure: Throwable): UserFacingFailure {
        val cause = unwrap(failure)
        if (cause is IllegalArgumentException && cause.message in SAFE_VALIDATION_MESSAGES) {
            return UserFacingFailure(FailureKind.INVALID_INPUT, cause.message)
        }
        if (cause is AuthException) {
            val message = cause.message
            if (message in SAFE_AUTH_MESSAGES) return UserFacingFailure(FailureKind.INVALID_INPUT, message)
            return UserFacingFailure(FailureKind.SERVICE_UNAVAILABLE)
        }
        return UserFacingFailure(when (cause) {
            is SocketTimeoutException -> FailureKind.TIMEOUT
            is UnknownHostException, is ConnectException -> FailureKind.OFFLINE
            is IOException -> FailureKind.OFFLINE
            is ApiClientException -> if (cause.message == "authentication required") {
                FailureKind.SESSION_EXPIRED
            } else FailureKind.SERVICE_UNAVAILABLE
            else -> FailureKind.GENERIC
        })
    }

    private fun unwrap(failure: Throwable): Throwable {
        var current = failure
        repeat(4) {
            val nested = when (current) {
                is CompletionException, is ExecutionException -> current.cause
                else -> null
            } ?: return current
            current = nested
        }
        return current
    }

    private val SAFE_VALIDATION_MESSAGES = setOf(
        "Введите email или телефон", "Введите имя", "Возраст должен быть от 16 до 120 лет",
        "Введите страну", "Введите корректный email", "Введите код подтверждения",
        "Пароль должен содержать от 8 до 128 символов", "Описание слишком длинное",
        "Название профессии слишком длинное", "Поле поиска слишком длинное", "Список слишком длинный",
        "Допускается до 12 пунктов длиной не более 100 символов", "Введите сообщение",
        "Сообщение не должно превышать 2000 символов",
    )
    private val SAFE_AUTH_MESSAGES = setOf(
        "Проверьте введённые данные", "Неверный логин или пароль", "Такой аккаунт уже существует",
        "Слишком много попыток. Повторите позже", "Сервис временно недоступен", "Не удалось выполнить запрос",
    )
}
