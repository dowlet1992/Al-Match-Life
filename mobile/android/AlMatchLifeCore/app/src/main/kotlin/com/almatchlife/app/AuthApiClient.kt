package com.almatchlife.app

import com.almatchlife.core.ApiRequest
import com.almatchlife.core.ApiTransport
import com.almatchlife.core.SessionTokenStore
import com.almatchlife.core.SessionTokens
import org.json.JSONObject
import java.net.URI
import java.util.concurrent.CompletableFuture

internal sealed interface AuthResult {
    data class Authenticated(val displayName: String) : AuthResult
    data class VerificationRequired(
        val contactType: String,
        val contactValue: String,
        val deliverySent: Boolean,
    ) : AuthResult
}

internal class AuthApiClient(
    private val origin: URI,
    private val transport: ApiTransport,
    private val tokenStore: SessionTokenStore,
) {
    fun login(login: String, password: String): CompletableFuture<AuthResult> {
        AuthInputValidator.login(login, password)
        return post("/api/auth/login", JSONObject().put("login", login.trim()).put("password", password))
            .thenApply(::decodeAuthOrVerification)
    }

    fun register(name: String, age: String, country: String, email: String, password: String): CompletableFuture<AuthResult> {
        val parsedAge = AuthInputValidator.registration(name, age, country, email, password)
        return post(
            "/api/auth/register",
            JSONObject()
                .put("name", name.trim())
                .put("age", parsedAge)
                .put("country", country.trim())
                .put("contact_type", "email")
                .put("email", email.trim().lowercase())
                .put("phone", "")
                .put("password", password),
        ).thenApply { response ->
            if (response.statusCode != 201) throw AuthException.forStatus(response.statusCode)
            decodeVerification(response.body)
        }
    }

    fun verify(contactType: String, contactValue: String, code: String): CompletableFuture<AuthResult> {
        AuthInputValidator.verification(contactType, contactValue, code)
        return post(
            "/api/auth/verify",
            JSONObject()
                .put("purpose", "account_verify")
                .put("contact_type", contactType)
                .put("contact_value", contactValue)
                .put("code", code.trim()),
        ).thenApply(::decodeAuthenticated)
    }

    private fun post(path: String, json: JSONObject): CompletableFuture<com.almatchlife.core.ApiResponse> {
        val uri = origin.resolve(path)
        check(uri.scheme == origin.scheme && uri.host == origin.host && uri.port == origin.port)
        val body = json.toString().toByteArray(Charsets.UTF_8)
        require(body.size <= MAX_AUTH_BODY_BYTES)
        return transport.execute(ApiRequest(
            method = "POST",
            uri = uri,
            headers = mapOf("Accept" to "application/json", "Content-Type" to "application/json"),
            body = body,
        )).whenComplete { _, _ -> body.fill(0) }
    }

    private fun decodeAuthOrVerification(response: com.almatchlife.core.ApiResponse): AuthResult {
        if (response.statusCode == 403) return decodeVerification(response.body)
        return decodeAuthenticated(response)
    }

    private fun decodeAuthenticated(response: com.almatchlife.core.ApiResponse): AuthResult {
        if (response.statusCode !in 200..299) throw AuthException.forStatus(response.statusCode)
        val json = parse(response.body)
        if (!json.optBoolean("ok") || !json.optBoolean("authenticated") || json.optString("token_type") != "Bearer") {
            throw AuthException("Invalid authentication response")
        }
        val tokens = SessionTokens(
            json.requiredBoundedString("access_token", MAX_TOKEN_BYTES),
            json.requiredBoundedString("refresh_token", MAX_TOKEN_BYTES),
        )
        tokenStore.save(tokens)
        val name = json.optJSONObject("user")?.optString("name")?.trim().orEmpty().take(100)
        return AuthResult.Authenticated(name)
    }

    private fun decodeVerification(bytes: ByteArray): AuthResult.VerificationRequired {
        val json = parse(bytes)
        if (!json.optBoolean("ok") || !json.optBoolean("verification_required")) {
            throw AuthException("Invalid verification response")
        }
        val type = json.requiredBoundedString("contact_type", 16)
        if (type !in setOf("email", "phone")) throw AuthException("Invalid verification contact")
        return AuthResult.VerificationRequired(
            type,
            json.requiredBoundedString("contact_value", 254),
            json.optBoolean("delivery_sent"),
        )
    }

    private fun parse(bytes: ByteArray): JSONObject {
        if (bytes.isEmpty() || bytes.size > MAX_AUTH_RESPONSE_BYTES) throw AuthException("Invalid server response")
        return runCatching { JSONObject(bytes.toString(Charsets.UTF_8)) }
            .getOrElse { throw AuthException("Invalid server response") }
    }

    private fun JSONObject.requiredBoundedString(name: String, maximum: Int): String {
        val value = optString(name).trim()
        if (value.isEmpty() || value.length > maximum) throw AuthException("Invalid server response")
        return value
    }

    private companion object {
        const val MAX_AUTH_BODY_BYTES = 8 * 1024
        const val MAX_AUTH_RESPONSE_BYTES = 64 * 1024
        const val MAX_TOKEN_BYTES = 8 * 1024
    }
}

internal class AuthException(message: String) : RuntimeException(message) {
    companion object {
        fun forStatus(status: Int): AuthException = AuthException(when (status) {
            400 -> "Проверьте введённые данные"
            401 -> "Неверный логин или пароль"
            409 -> "Такой аккаунт уже существует"
            429 -> "Слишком много попыток. Повторите позже"
            in 500..599 -> "Сервис временно недоступен"
            else -> "Не удалось выполнить запрос"
        })
    }
}
