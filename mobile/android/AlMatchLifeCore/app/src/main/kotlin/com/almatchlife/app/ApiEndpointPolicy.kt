package com.almatchlife.app

import java.net.URI

internal object ApiEndpointPolicy {
    fun validate(value: String, debug: Boolean): URI {
        val uri = runCatching { URI(value) }.getOrElse { throw IllegalArgumentException("Invalid API URL") }
        require(!uri.host.isNullOrBlank() && uri.userInfo == null && uri.query == null && uri.fragment == null) {
            "API URL must contain only an origin"
        }
        require(uri.path.isNullOrEmpty() || uri.path == "/") { "API URL must not contain a path" }
        val permitted = uri.scheme == "https" || debug && uri.scheme == "http" && uri.host in LOOPBACK_HOSTS
        require(permitted) { "HTTPS is required outside loopback debug development" }
        return uri
    }

    private val LOOPBACK_HOSTS = setOf("localhost", "127.0.0.1", "10.0.2.2")
}
