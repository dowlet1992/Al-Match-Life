CONTRACT_VERSION = 1


def build_contract():
    """Platform-neutral contract consumed by Android, iOS, and web call engines."""
    return {
        "version": CONTRACT_VERSION,
        "states": ["idle", "connecting", "streaming", "fallback", "stopping", "stopped", "failed"],
        "transitions": {
            "idle": ["connecting", "stopped"],
            "connecting": ["streaming", "fallback", "stopping", "failed"],
            "streaming": ["fallback", "stopping", "failed"],
            "fallback": ["connecting", "stopping", "failed"],
            "stopping": ["stopped"],
            "stopped": ["connecting"],
            "failed": ["connecting", "stopping"],
        },
        "realtime_events": {
            "partial": "conversation.item.input_audio_transcription.delta",
            "final": "conversation.item.input_audio_transcription.completed",
            "error": "error",
        },
        "audio_policy": {
            "separate_microphone_track": True,
            "raw_audio_persisted": False,
            "voice_cloning": False,
            "synthetic_voice_required": True,
            "speech_queue_max_items": 2,
            "duck_remote_audio_to": 0.28,
            "stop_on_call_end": True,
            "stop_on_consent_revoked": True,
        },
        "fallback_policy": {
            "multipart_chunk_seconds": 4,
            "max_consecutive_failures": 3,
            "remote_caption_polling_continues": True,
        },
        "security": {
            "credential_type": "ephemeral",
            "cache_control": "no-store",
            "bearer_required_for_native": True,
            "provider_api_key_exposed": False,
        },
    }
