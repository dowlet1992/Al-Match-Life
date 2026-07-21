package com.almatchlife.core.system

import com.almatchlife.core.RealtimeEventCodec
import com.almatchlife.core.RealtimeProviderEvent
import org.json.JSONObject

/** Minimal fail-closed decoder for the only provider events consumed by call captions. */
class AndroidRealtimeEventJsonCodec : RealtimeEventCodec {
    override fun decode(bytes: ByteArray): RealtimeProviderEvent? {
        if (bytes.isEmpty() || bytes.size > MAX_EVENT_BYTES) return null
        val jsonObject = runCatching { JSONObject(bytes.toString(Charsets.UTF_8)) }.getOrNull() ?: return null
        val type = jsonObject.optString("type").bounded(MAX_TYPE_LENGTH) ?: return null
        if (type !in ALLOWED_TYPES) return null
        val error = jsonObject.optJSONObject("error")
        return RealtimeProviderEvent(
            type = type,
            itemId = jsonObject.optString("item_id").bounded(MAX_ID_LENGTH),
            delta = jsonObject.optString("delta").bounded(MAX_TEXT_LENGTH),
            transcript = jsonObject.optString("transcript").bounded(MAX_TEXT_LENGTH),
            errorCode = error?.optString("code")?.bounded(MAX_ERROR_LENGTH),
        )
    }

    private fun String?.bounded(maximum: Int): String? =
        this?.takeIf { it.isNotEmpty() && it.length <= maximum && '\u0000' !in it }

    private companion object {
        const val MAX_EVENT_BYTES = 64 * 1024
        const val MAX_TYPE_LENGTH = 96
        const val MAX_ID_LENGTH = 128
        const val MAX_TEXT_LENGTH = 16 * 1024
        const val MAX_ERROR_LENGTH = 128
        val ALLOWED_TYPES = setOf(
            "conversation.item.input_audio_transcription.delta",
            "conversation.item.input_audio_transcription.completed",
            "error",
        )
    }
}
