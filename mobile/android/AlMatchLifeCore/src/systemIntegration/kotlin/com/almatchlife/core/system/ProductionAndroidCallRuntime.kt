package com.almatchlife.core.system

import com.almatchlife.core.NativeCallType
import com.almatchlife.core.PushDisposition
import com.almatchlife.core.SystemCallEndReason
import com.almatchlife.core.SystemCallReporter
import com.almatchlife.core.VoipCallCoordinator
import com.almatchlife.core.VoipCallPayload
import com.almatchlife.core.failedFutureCompat
import com.almatchlife.core.android.IncomingCallNotifier
import java.util.UUID
import java.util.concurrent.CompletableFuture

fun interface AsyncCallExecutor {
    fun submit(operation: suspend () -> Unit): CompletableFuture<Void>
}

fun interface CallContextResolver {
    fun resolveAuthorized(callId: String, callType: NativeCallType): CompletableFuture<VoipCallPayload>
}

fun interface FcmTokenRegistrar { fun register(token: String) }

class ProductionAndroidCallRuntime(
    private val emailProvider: () -> String?,
    private val coordinator: VoipCallCoordinator,
    private val executor: AsyncCallExecutor,
    private val resolver: CallContextResolver,
    private val tokenRegistrar: FcmTokenRegistrar,
    private val pushCancellation: (VoipCallPayload) -> Unit,
    private val failureHandler: (Throwable) -> Unit,
) : AndroidCallRuntime {
    private val lock = Any()
    private val contexts = LinkedHashMap<String, VoipCallPayload>()
    private val maximumContexts = 32

    override fun currentEmail(): String? = emailProvider()?.trim()?.lowercase()?.takeIf { it.isNotEmpty() }

    override fun receivePush(payload: VoipCallPayload) {
        if (payload.eventType == com.almatchlife.core.PushEventType.INCOMING_CALL) remember(payload)
        else pushCancellation(payload)
        executor.submit {
            val disposition = coordinator.receive(payload)
            if (disposition == PushDisposition.CANCELLED) forget(payload.callId)
        }.whenComplete { _, failure -> if (failure != null) failureHandler(unwrap(failure)) }
    }

    override fun registerFcmToken(token: String) = tokenRegistrar.register(token)

    override fun decline(callId: String, callType: NativeCallType, eventId: String): CompletableFuture<Void> =
        withContext(callId, callType, eventId) { payload ->
        coordinator.restoreActive(payload)
        coordinator.decline(payload.stableUuid)
        forget(callId)
    }

    override fun startAcceptedCall(callId: String, callType: NativeCallType, eventId: String): CompletableFuture<Void> =
        withContext(callId, callType, eventId) { payload ->
            coordinator.restoreActive(payload)
            coordinator.accept(payload.stableUuid)
        }

    override fun stopCall(callId: String): CompletableFuture<Void> = withContext(callId, null, null) { payload ->
        coordinator.restoreActive(payload)
        coordinator.endFromSystem(payload.stableUuid)
        forget(callId)
    }

    private fun withContext(
        callId: String,
        expectedType: NativeCallType?,
        expectedEventId: String?,
        operation: suspend (VoipCallPayload) -> Unit,
    ): CompletableFuture<Void> {
        val cached = synchronized(lock) { contexts[callId] }
        val contextFuture = when {
            cached != null && (expectedType == null || cached.callType == expectedType) &&
                (expectedEventId == null || cached.eventId == expectedEventId) ->
                CompletableFuture.completedFuture(cached)
            expectedType != null -> resolver.resolveAuthorized(callId, expectedType)
            else -> failedFutureCompat(IllegalStateException("call context unavailable"))
        }
        return contextFuture.thenCompose { payload ->
            if (payload.callId != callId || (expectedType != null && payload.callType != expectedType) ||
                (expectedEventId != null && payload.eventId != expectedEventId)
            ) {
                return@thenCompose failedFutureCompat(IllegalStateException("resolved call mismatch"))
            }
            remember(payload)
            executor.submit { operation(payload) }
        }
    }

    private fun remember(payload: VoipCallPayload): Unit = synchronized(lock) {
        contexts[payload.callId] = payload
        while (contexts.size > maximumContexts) contexts.remove(contexts.keys.first())
    }

    private fun forget(callId: String) = synchronized(lock) { contexts.remove(callId) }
    private fun unwrap(value: Throwable): Throwable = value.cause ?: value
}

class NotificationSystemCallReporter(
    private val notifier: IncomingCallNotifier,
) : SystemCallReporter {
    private val active = mutableMapOf<UUID, VoipCallPayload>()

    override suspend fun reportIncoming(payload: VoipCallPayload) {
        synchronized(active) { active[payload.stableUuid] = payload }
        notifier.receive(payload)
    }

    override suspend fun reportEnded(uuid: UUID, reason: SystemCallEndReason) {
        val payload = synchronized(active) { active.remove(uuid) } ?: return
        notifier.clear(payload)
    }
}
