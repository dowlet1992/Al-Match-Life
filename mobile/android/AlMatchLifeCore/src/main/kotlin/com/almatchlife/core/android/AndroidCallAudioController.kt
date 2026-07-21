package com.almatchlife.core.android

import android.Manifest
import android.content.Context
import android.content.pm.PackageManager
import android.media.AudioAttributes
import android.media.AudioDeviceCallback
import android.media.AudioDeviceInfo
import android.media.AudioFocusRequest
import android.media.AudioManager
import android.os.Build
import android.os.Handler
import android.os.Looper
import com.almatchlife.core.CallAudio
import com.almatchlife.core.NativeCallType

enum class CallAudioFocusEvent { GAINED, LOST_TRANSIENT, LOST_PERMANENT }

class AndroidCallAudioController(
    context: Context,
    private val focusEvent: (CallAudioFocusEvent) -> Unit = {},
) : CallAudio {
    private val applicationContext = context.applicationContext
    private val audioManager = applicationContext.getSystemService(AudioManager::class.java)
    private var active = false
    private var previousMode = AudioManager.MODE_NORMAL
    private var previousSpeaker = false
    private var previousMicrophoneMute = false
    private var legacyScoStarted = false
    private var preferSpeaker = false
    private var focusRequest: AudioFocusRequest? = null
    private var deviceCallbackRegistered = false
    private val deviceCallback = object : AudioDeviceCallback() {
        override fun onAudioDevicesAdded(addedDevices: Array<out AudioDeviceInfo>) = reroute()
        override fun onAudioDevicesRemoved(removedDevices: Array<out AudioDeviceInfo>) = reroute()
    }
    private val focusListener = AudioManager.OnAudioFocusChangeListener { change ->
        when (change) {
            AudioManager.AUDIOFOCUS_GAIN -> focusEvent(CallAudioFocusEvent.GAINED)
            AudioManager.AUDIOFOCUS_LOSS -> focusEvent(CallAudioFocusEvent.LOST_PERMANENT)
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT,
            AudioManager.AUDIOFOCUS_LOSS_TRANSIENT_CAN_DUCK -> focusEvent(CallAudioFocusEvent.LOST_TRANSIENT)
        }
    }

    override suspend fun activate(callType: NativeCallType) {
        if (active) return
        previousMode = audioManager.mode
        previousSpeaker = legacySpeakerphoneState()
        previousMicrophoneMute = audioManager.isMicrophoneMute
        val request = AudioFocusRequest.Builder(AudioManager.AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE)
            .setAudioAttributes(
                AudioAttributes.Builder()
                    .setUsage(AudioAttributes.USAGE_VOICE_COMMUNICATION)
                    .setContentType(AudioAttributes.CONTENT_TYPE_SPEECH)
                    .build(),
            )
            .setAcceptsDelayedFocusGain(false)
            .setOnAudioFocusChangeListener(focusListener, Handler(Looper.getMainLooper()))
            .build()
        if (audioManager.requestAudioFocus(request) != AudioManager.AUDIOFOCUS_REQUEST_GRANTED) {
            throw IllegalStateException("call audio focus denied")
        }
        focusRequest = request
        active = true
        try {
            audioManager.mode = AudioManager.MODE_IN_COMMUNICATION
            audioManager.isMicrophoneMute = false
            preferSpeaker = callType == NativeCallType.VIDEO
            audioManager.registerAudioDeviceCallback(deviceCallback, Handler(Looper.getMainLooper()))
            deviceCallbackRegistered = true
            route(preferSpeaker)
        } catch (failure: Exception) {
            deactivate()
            throw failure
        }
    }

    fun route(preferSpeaker: Boolean) {
        check(active) { "call audio is not active" }
        this.preferSpeaker = preferSpeaker
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) {
            val available = audioManager.availableCommunicationDevices
            val bluetoothAllowed = applicationContext.checkSelfPermission(Manifest.permission.BLUETOOTH_CONNECT) ==
                PackageManager.PERMISSION_GRANTED
            val preferredTypes = if (preferSpeaker) {
                listOf(AudioDeviceInfo.TYPE_BLUETOOTH_SCO, AudioDeviceInfo.TYPE_BLE_HEADSET, AudioDeviceInfo.TYPE_BUILTIN_SPEAKER)
            } else {
                listOf(AudioDeviceInfo.TYPE_BLUETOOTH_SCO, AudioDeviceInfo.TYPE_BLE_HEADSET, AudioDeviceInfo.TYPE_BUILTIN_EARPIECE)
            }
            preferredTypes.firstNotNullOfOrNull { type ->
                if (!bluetoothAllowed && type in setOf(
                        AudioDeviceInfo.TYPE_BLUETOOTH_SCO, AudioDeviceInfo.TYPE_BLE_HEADSET,
                    )) null
                else available.firstOrNull { it.type == type }
            }
                ?.let(audioManager::setCommunicationDevice)
        } else {
            @Suppress("DEPRECATION")
            if (audioManager.isBluetoothScoAvailableOffCall) {
                audioManager.startBluetoothSco()
                audioManager.isBluetoothScoOn = true
                legacyScoStarted = true
            } else {
                audioManager.isSpeakerphoneOn = preferSpeaker
            }
        }
    }

    override suspend fun deactivate() {
        if (!active && focusRequest == null) return
        active = false
        if (deviceCallbackRegistered) runCatching { audioManager.unregisterAudioDeviceCallback(deviceCallback) }
        deviceCallbackRegistered = false
        if (Build.VERSION.SDK_INT >= Build.VERSION_CODES.S) runCatching { audioManager.clearCommunicationDevice() }
        else if (legacyScoStarted) {
            @Suppress("DEPRECATION")
            runCatching { audioManager.isBluetoothScoOn = false }
            @Suppress("DEPRECATION")
            runCatching { audioManager.stopBluetoothSco() }
            legacyScoStarted = false
        }
        @Suppress("DEPRECATION")
        runCatching { audioManager.isSpeakerphoneOn = previousSpeaker }
        runCatching { audioManager.isMicrophoneMute = previousMicrophoneMute }
        runCatching { audioManager.mode = previousMode }
        focusRequest?.let { request -> runCatching { audioManager.abandonAudioFocusRequest(request) } }
        focusRequest = null
    }

    private fun reroute() {
        if (active) runCatching { route(preferSpeaker) }
    }

    @Suppress("DEPRECATION")
    private fun legacySpeakerphoneState(): Boolean =
        if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) audioManager.isSpeakerphoneOn else false
}
