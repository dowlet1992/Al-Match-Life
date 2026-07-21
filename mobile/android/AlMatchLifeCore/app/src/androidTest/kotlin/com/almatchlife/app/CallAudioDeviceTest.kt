package com.almatchlife.app

import android.media.AudioManager
import android.os.Build
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.almatchlife.core.NativeCallType
import com.almatchlife.core.android.AndroidCallAudioController
import java.util.concurrent.CountDownLatch
import java.util.concurrent.TimeUnit
import kotlin.coroutines.Continuation
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.coroutines.startCoroutine
import org.junit.Assert.assertEquals
import org.junit.Assert.assertTrue
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CallAudioDeviceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val manager = context.getSystemService(AudioManager::class.java)

    @Suppress("DEPRECATION")
    @Test
    fun audioAndVideoRoutesRestoreDeviceStateAndDeactivateIsIdempotent() {
        val originalMode = manager.mode
        val originalMute = manager.isMicrophoneMute
        val originalSpeaker = manager.isSpeakerphoneOn
        val controller = AndroidCallAudioController(context)
        try {
            runSuspend { controller.activate(NativeCallType.AUDIO) }
            runSuspend { controller.deactivate() }
            assertEquals(originalMode, manager.mode)
            assertEquals(originalMute, manager.isMicrophoneMute)
            if (Build.VERSION.SDK_INT < Build.VERSION_CODES.S) assertEquals(originalSpeaker, manager.isSpeakerphoneOn)

            runSuspend { controller.activate(NativeCallType.VIDEO) }
            controller.route(preferSpeaker = false)
            runSuspend { controller.deactivate() }
            runSuspend { controller.deactivate() }
            assertEquals(originalMode, manager.mode)
            assertEquals(originalMute, manager.isMicrophoneMute)
        } finally {
            runSuspend { controller.deactivate() }
        }
    }

    private fun runSuspend(operation: suspend () -> Unit) {
        val latch = CountDownLatch(1)
        var completion: Result<Unit>? = null
        operation.startCoroutine(object : Continuation<Unit> {
            override val context = EmptyCoroutineContext
            override fun resumeWith(result: Result<Unit>) { completion = result; latch.countDown() }
        })
        assertTrue("Audio operation timed out", latch.await(10, TimeUnit.SECONDS))
        requireNotNull(completion).getOrThrow()
    }
}
