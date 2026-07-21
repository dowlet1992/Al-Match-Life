package com.almatchlife.app

import com.almatchlife.core.ApiClientException
import java.net.SocketTimeoutException
import java.net.UnknownHostException
import java.util.concurrent.CompletionException
import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertNull

class UserFacingFailureMapperTest {
    @Test
    fun mapsNetworkAndSessionFailuresWithoutExposingDetails() {
        assertEquals(FailureKind.OFFLINE, UserFacingFailureMapper.map(UnknownHostException("secret.host")).kind)
        assertEquals(FailureKind.TIMEOUT, UserFacingFailureMapper.map(SocketTimeoutException("internal URL")).kind)
        assertEquals(
            FailureKind.SESSION_EXPIRED,
            UserFacingFailureMapper.map(CompletionException(ApiClientException("authentication required"))).kind,
        )
        val internal = UserFacingFailureMapper.map(ApiClientException("signal rejected: 503 at secret.host"))
        assertEquals(FailureKind.SERVICE_UNAVAILABLE, internal.kind)
        assertNull(internal.validationMessage)
    }

    @Test
    fun exposesOnlyAllowlistedValidationMessages() {
        val safe = UserFacingFailureMapper.map(IllegalArgumentException("Введите корректный email"))
        assertEquals("Введите корректный email", safe.validationMessage)
        val unsafe = UserFacingFailureMapper.map(IllegalArgumentException("Invalid response from https://secret.host"))
        assertEquals(FailureKind.GENERIC, unsafe.kind)
        assertNull(unsafe.validationMessage)
    }
}
