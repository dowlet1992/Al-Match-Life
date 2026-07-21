package com.almatchlife.core

import java.util.UUID

enum class SystemCallEndReason { REMOTE_ENDED, DECLINED, FAILED, UNANSWERED }
enum class PushDisposition { REPORTED, CANCELLED, DUPLICATE, IGNORED }

interface SystemCallReporter {
    suspend fun reportIncoming(payload: VoipCallPayload)
    suspend fun reportEnded(uuid: UUID, reason: SystemCallEndReason)
}

interface ManagedCallLifecycle {
    suspend fun accept(payload: VoipCallPayload)
    suspend fun decline(payload: VoipCallPayload)
    suspend fun end(payload: VoipCallPayload)
    suspend fun connectionLost(payload: VoipCallPayload)
    suspend fun stop()
}

class VoipCallCoordinator(
    private val system: SystemCallReporter,
    private val lifecycle: ManagedCallLifecycle,
) {
    private val lock = Any()
    private val active = mutableMapOf<UUID, VoipCallPayload>()
    private val accepted = mutableSetOf<UUID>()
    private val accepting = mutableSetOf<UUID>()
    private val seenEventIds = ArrayDeque<String>()
    private val maximumSeenEvents = 256

    suspend fun receive(payload: VoipCallPayload): PushDisposition {
        val reserved = synchronized(lock) {
            if (payload.eventId in seenEventIds) return@synchronized Reservation.Duplicate
            remember(payload.eventId)
            if (payload.eventType == PushEventType.CALL_CANCELLED) {
                val current = active.remove(payload.stableUuid)
                accepted.remove(payload.stableUuid)
                accepting.remove(payload.stableUuid)
                if (current?.callId == payload.callId) Reservation.Cancel(current) else Reservation.Ignore
            } else if (active.containsKey(payload.stableUuid)) {
                Reservation.Duplicate
            } else {
                active[payload.stableUuid] = payload
                Reservation.Incoming(payload)
            }
        }
        return when (reserved) {
            Reservation.Duplicate -> PushDisposition.DUPLICATE
            Reservation.Ignore -> PushDisposition.IGNORED
            is Reservation.Cancel -> {
                try { lifecycle.stop() } finally {
                    system.reportEnded(reserved.payload.stableUuid, SystemCallEndReason.REMOTE_ENDED)
                }
                PushDisposition.CANCELLED
            }
            is Reservation.Incoming -> {
                try {
                    system.reportIncoming(reserved.payload)
                    PushDisposition.REPORTED
                } catch (failure: Exception) {
                    synchronized(lock) { active.remove(reserved.payload.stableUuid, reserved.payload) }
                    lifecycle.stop()
                    throw failure
                }
            }
        }
    }

    suspend fun accept(uuid: UUID) {
        val payload = synchronized(lock) {
            val current = active[uuid] ?: return@synchronized null
            if (uuid in accepted || !accepting.add(uuid)) return@synchronized null
            current
        } ?: return
        try {
            lifecycle.accept(payload)
            val retained = synchronized(lock) {
                accepting.remove(uuid)
                if (active[uuid] == payload) {
                    accepted.add(uuid)
                    true
                } else false
            }
            if (!retained) lifecycle.stop()
        } catch (failure: Exception) {
            synchronized(lock) {
                accepting.remove(uuid)
                accepted.remove(uuid)
                active.remove(uuid, payload)
            }
            lifecycle.stop()
            system.reportEnded(uuid, SystemCallEndReason.FAILED)
            throw failure
        }
    }

    fun restoreActive(payload: VoipCallPayload) {
        synchronized(lock) { active.putIfAbsent(payload.stableUuid, payload) }
    }

    suspend fun decline(uuid: UUID) {
        val payload = take(uuid) ?: return
        try { lifecycle.decline(payload) } finally {
            try { lifecycle.stop() } finally { system.reportEnded(uuid, SystemCallEndReason.DECLINED) }
        }
    }

    suspend fun endFromSystem(uuid: UUID) {
        val result = synchronized(lock) {
            val payload = active.remove(uuid) ?: return@synchronized null
            accepting.remove(uuid)
            payload to accepted.remove(uuid)
        } ?: return
        try {
            if (result.second) lifecycle.end(result.first) else lifecycle.decline(result.first)
        } finally { lifecycle.stop() }
    }

    suspend fun timedOut(uuid: UUID) {
        if (take(uuid) == null) return
        lifecycle.stop()
        system.reportEnded(uuid, SystemCallEndReason.UNANSWERED)
    }

    suspend fun remoteEnded(uuid: UUID) {
        if (take(uuid) == null) return
        lifecycle.stop()
        system.reportEnded(uuid, SystemCallEndReason.REMOTE_ENDED)
    }

    suspend fun connectionFailed(uuid: UUID) {
        val payload = take(uuid) ?: return
        try { lifecycle.connectionLost(payload) } finally {
            try { lifecycle.stop() } finally { system.reportEnded(uuid, SystemCallEndReason.FAILED) }
        }
    }

    private fun take(uuid: UUID): VoipCallPayload? = synchronized(lock) {
        accepting.remove(uuid)
        accepted.remove(uuid)
        active.remove(uuid)
    }

    private fun remember(eventId: String) {
        seenEventIds.addLast(eventId)
        while (seenEventIds.size > maximumSeenEvents) seenEventIds.removeFirst()
    }

    private sealed interface Reservation {
        object Duplicate : Reservation
        object Ignore : Reservation
        data class Cancel(val payload: VoipCallPayload) : Reservation
        data class Incoming(val payload: VoipCallPayload) : Reservation
    }
}

class ManagedNativeCallLifecycle(private val lifecycle: NativeCallLifecycle) : ManagedCallLifecycle {
    override suspend fun accept(payload: VoipCallPayload) = lifecycle.accept(payload)
    override suspend fun decline(payload: VoipCallPayload) = lifecycle.decline(payload)
    override suspend fun end(payload: VoipCallPayload) = lifecycle.end(payload)
    override suspend fun connectionLost(payload: VoipCallPayload) = lifecycle.connectionLost(payload)
    override suspend fun stop() = lifecycle.stop()
}
