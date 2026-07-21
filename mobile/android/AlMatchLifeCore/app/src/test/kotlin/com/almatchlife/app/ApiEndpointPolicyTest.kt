package com.almatchlife.app

import kotlin.test.Test
import kotlin.test.assertEquals
import kotlin.test.assertFailsWith

class ApiEndpointPolicyTest {
    @Test
    fun acceptsHttpsOrigin() {
        assertEquals("api.example.com", ApiEndpointPolicy.validate("https://api.example.com", false).host)
    }

    @Test
    fun permitsEmulatorLoopbackOnlyInDebug() {
        assertEquals("10.0.2.2", ApiEndpointPolicy.validate("http://10.0.2.2:5000", true).host)
        assertFailsWith<IllegalArgumentException> {
            ApiEndpointPolicy.validate("http://10.0.2.2:5000", false)
        }
    }

    @Test
    fun rejectsCredentialsPathsAndNonLoopbackHttp() {
        listOf(
            "https://user:secret@api.example.com",
            "https://api.example.com/v1",
            "http://api.example.com",
        ).forEach { value ->
            assertFailsWith<IllegalArgumentException>(value) { ApiEndpointPolicy.validate(value, true) }
        }
    }
}
