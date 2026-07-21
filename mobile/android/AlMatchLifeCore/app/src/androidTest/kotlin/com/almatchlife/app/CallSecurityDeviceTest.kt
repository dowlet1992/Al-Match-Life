package com.almatchlife.app

import android.Manifest
import android.content.ComponentName
import android.content.pm.PackageManager
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.app.InstrumentationRegistry
import com.almatchlife.core.system.AlMatchFirebaseMessagingService
import com.almatchlife.core.system.IncomingCallActionReceiver
import com.almatchlife.core.system.IncomingCallActivity
import com.almatchlife.core.system.OngoingCallService
import org.junit.Assert.assertFalse
import org.junit.Assert.assertEquals
import org.junit.Test
import org.junit.runner.RunWith

@RunWith(AndroidJUnit4::class)
class CallSecurityDeviceTest {
    private val context = InstrumentationRegistry.getInstrumentation().targetContext
    private val packageManager = context.packageManager

    @Suppress("DEPRECATION")
    @Test
    fun mergedCallComponentsRemainPrivateOnInstalledApk() {
        assertFalse(packageManager.getReceiverInfo(
            ComponentName(context, IncomingCallActionReceiver::class.java), 0,
        ).exported)
        assertFalse(packageManager.getActivityInfo(
            ComponentName(context, IncomingCallActivity::class.java), 0,
        ).exported)
        assertFalse(packageManager.getServiceInfo(
            ComponentName(context, OngoingCallService::class.java), 0,
        ).exported)
        assertFalse(packageManager.getServiceInfo(
            ComponentName(context, AlMatchFirebaseMessagingService::class.java), 0,
        ).exported)
    }

    @Suppress("DEPRECATION")
    @Test
    fun installedApkDeclaresOnlyRequiredCallCapabilities() {
        val requested = packageManager.getPackageInfo(context.packageName, PackageManager.GET_PERMISSIONS)
            .requestedPermissions.orEmpty().toSet()
        assertEquals(true, Manifest.permission.POST_NOTIFICATIONS in requested)
        assertEquals(true, Manifest.permission.RECORD_AUDIO in requested)
        assertEquals(true, Manifest.permission.CAMERA in requested)
        assertEquals(false, "android.permission.MANAGE_OWN_CALLS" in requested)
    }
}
