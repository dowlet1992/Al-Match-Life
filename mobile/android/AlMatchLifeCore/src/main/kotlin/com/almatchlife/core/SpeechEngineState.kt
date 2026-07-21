package com.almatchlife.core

enum class SpeechEngineState {
    IDLE, CONNECTING, STREAMING, FALLBACK, STOPPING, STOPPED, FAILED;

    fun canTransitionTo(next: SpeechEngineState): Boolean = next in transitions.getValue(this)

    companion object {
        private val transitions = mapOf(
            IDLE to setOf(CONNECTING, STOPPED),
            CONNECTING to setOf(STREAMING, FALLBACK, STOPPING, FAILED),
            STREAMING to setOf(FALLBACK, STOPPING, FAILED),
            FALLBACK to setOf(CONNECTING, STOPPING, FAILED),
            STOPPING to setOf(STOPPED),
            STOPPED to setOf(CONNECTING),
            FAILED to setOf(CONNECTING, STOPPING),
        )
    }
}

class InvalidSpeechTransition(from: SpeechEngineState, to: SpeechEngineState) :
    IllegalStateException("invalid speech transition: $from -> $to")

interface SpeechTransport { suspend fun start(); suspend fun stop() }

class SpeechEngineCoordinator(
    private val realtime: SpeechTransport,
    private val fallback: SpeechTransport,
) {
    var state: SpeechEngineState = SpeechEngineState.IDLE
        private set

    suspend fun start() {
        transition(SpeechEngineState.CONNECTING)
        try {
            realtime.start()
            transition(SpeechEngineState.STREAMING)
        } catch (realtimeFailure: Exception) {
            transition(SpeechEngineState.FALLBACK)
            try {
                fallback.start()
            } catch (fallbackFailure: Exception) {
                transition(SpeechEngineState.FAILED)
                fallbackFailure.addSuppressed(realtimeFailure)
                throw fallbackFailure
            }
        }
    }

    suspend fun stop() {
        if (state == SpeechEngineState.STOPPED) return
        if (state == SpeechEngineState.IDLE) { transition(SpeechEngineState.STOPPED); return }
        transition(SpeechEngineState.STOPPING)
        try { realtime.stop() } finally {
            try { fallback.stop() } finally { transition(SpeechEngineState.STOPPED) }
        }
    }

    private fun transition(next: SpeechEngineState) {
        if (!state.canTransitionTo(next)) throw InvalidSpeechTransition(state, next)
        state = next
    }
}
