package com.almatchlife.app

import android.app.Application
import com.almatchlife.core.AuthenticatedApiClient
import com.almatchlife.core.SessionTokenStore
import com.almatchlife.core.system.AndroidMobileWireJsonCodec
import com.almatchlife.core.system.AndroidUrlConnectionApiTransport
import com.almatchlife.core.system.FcmTokenSinkRegistry
import java.util.Locale
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.ArrayBlockingQueue
import java.util.concurrent.ThreadPoolExecutor
import java.util.concurrent.TimeUnit

class AlMatchApplication : Application() {
    lateinit var sessionStore: SessionTokenStore
        private set
    internal lateinit var authApi: AuthApiClient
        private set
    internal lateinit var appApi: AppApiClient
        private set
    internal lateinit var deviceIdentity: PushDeviceIdentity
        private set
    internal lateinit var imageLoader: SafeRemoteImageLoader
        private set
    private lateinit var apiExecutor: ExecutorService
    private lateinit var imageExecutor: ThreadPoolExecutor

    override fun onCreate() {
        super.onCreate()
        val endpoint = ApiEndpointPolicy.validate(BuildConfig.API_BASE_URL, BuildConfig.DEBUG)
        apiExecutor = Executors.newFixedThreadPool(3)
        imageExecutor = ThreadPoolExecutor(
            IMAGE_WORKERS,
            IMAGE_WORKERS,
            30L,
            TimeUnit.SECONDS,
            ArrayBlockingQueue(IMAGE_QUEUE_CAPACITY),
        ).apply { allowCoreThreadTimeOut(true) }
        imageLoader = SafeRemoteImageLoader(endpoint, imageExecutor)
        sessionStore = createSessionStore(this)
        deviceIdentity = PushDeviceIdentity(getSharedPreferences("push_device", MODE_PRIVATE))
        val transport = AndroidUrlConnectionApiTransport(apiExecutor)
        authApi = AuthApiClient(endpoint, transport, sessionStore)
        appApi = AppApiClient(
            AuthenticatedApiClient(endpoint, transport, sessionStore, AndroidMobileWireJsonCodec(), BuildConfig.DEBUG),
            sessionStore,
        )
        FcmTokenSinkRegistry.install(::syncFcmToken)
    }

    override fun onTrimMemory(level: Int) {
        super.onTrimMemory(level)
        if (!::imageLoader.isInitialized) return
        when {
            level >= UI_HIDDEN_MEMORY_LEVEL -> imageLoader.trimMemory(aggressive = true)
            level >= RUNNING_LOW_MEMORY_LEVEL -> imageLoader.trimMemory(aggressive = false)
        }
    }

    private companion object {
        // Stable values from ComponentCallbacks2; named locally because the running-low constant is deprecated on API 35.
        const val RUNNING_LOW_MEMORY_LEVEL = 10
        const val UI_HIDDEN_MEMORY_LEVEL = 20
        const val IMAGE_WORKERS = 2
        const val IMAGE_QUEUE_CAPACITY = 12
    }

    private fun syncFcmToken(token: String) {
        if (sessionStore.read() == null || !PushTokenValidator.isValid(token)) return
        appApi.registerPush(
            deviceIdentity.id(),
            token,
            BuildConfig.VERSION_NAME,
            Locale.getDefault().toLanguageTag(),
        )
    }
}
