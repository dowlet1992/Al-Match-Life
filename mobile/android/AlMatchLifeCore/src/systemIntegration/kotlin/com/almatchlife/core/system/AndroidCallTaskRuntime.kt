package com.almatchlife.core.system

import android.content.Context
import android.net.ConnectivityManager
import android.net.NetworkCapabilities
import com.almatchlife.core.BackgroundTask
import com.almatchlife.core.BackgroundTaskLauncher
import com.almatchlife.core.CancellationProbe
import com.almatchlife.core.NetworkStatus
import com.almatchlife.core.TaskSleeper
import java.util.concurrent.CompletableFuture
import java.util.concurrent.ExecutorService
import java.util.concurrent.Executors
import java.util.concurrent.ScheduledExecutorService
import java.util.concurrent.TimeUnit
import java.util.concurrent.atomic.AtomicBoolean
import kotlin.coroutines.Continuation
import kotlin.coroutines.EmptyCoroutineContext
import kotlin.coroutines.resume
import kotlin.coroutines.startCoroutine
import kotlin.coroutines.suspendCoroutine

class AndroidCallTaskRuntime(
    context: Context,
    private val workers: ExecutorService = Executors.newFixedThreadPool(3),
    private val timer: ScheduledExecutorService = Executors.newSingleThreadScheduledExecutor(),
) : AsyncCallExecutor, BackgroundTaskLauncher, TaskSleeper, NetworkStatus {
    private val connectivity = context.applicationContext
        .getSystemService(Context.CONNECTIVITY_SERVICE) as ConnectivityManager

    override fun submit(operation: suspend () -> Unit): CompletableFuture<Void> {
        val future = CompletableFuture<Void>()
        workers.execute {
            operation.startCoroutine(completion(future))
        }
        return future
    }

    override fun launch(block: suspend (CancellationProbe) -> Unit): BackgroundTask {
        val cancelled = AtomicBoolean(false)
        workers.execute {
            block.startCoroutine(
                object : CancellationProbe {
                    override val isCancelled: Boolean get() = cancelled.get()
                },
                completion(null),
            )
        }
        return object : BackgroundTask {
            override fun cancel() {
                cancelled.set(true)
            }
        }
    }

    override suspend fun sleep(milliseconds: Long) {
        require(milliseconds >= 0)
        suspendCoroutine { continuation ->
            timer.schedule({ continuation.resume(Unit) }, milliseconds, TimeUnit.MILLISECONDS)
        }
    }

    override suspend fun isOnline(): Boolean {
        val network = connectivity.activeNetwork ?: return false
        val capabilities = connectivity.getNetworkCapabilities(network) ?: return false
        return capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_INTERNET) &&
            capabilities.hasCapability(NetworkCapabilities.NET_CAPABILITY_VALIDATED)
    }

    fun shutdown() {
        workers.shutdownNow()
        timer.shutdownNow()
    }

    private fun completion(future: CompletableFuture<Void>?): Continuation<Unit> =
        object : Continuation<Unit> {
            override val context = EmptyCoroutineContext
            override fun resumeWith(result: Result<Unit>) {
                result.fold(
                    onSuccess = { future?.complete(null) },
                    onFailure = { failure ->
                        if (future != null) future.completeExceptionally(failure)
                        else Thread.currentThread().uncaughtExceptionHandler
                            ?.uncaughtException(Thread.currentThread(), failure)
                    },
                )
            }
        }
}
