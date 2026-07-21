package com.almatchlife.app

import android.graphics.Bitmap
import android.graphics.BitmapFactory
import android.graphics.Color
import android.os.Build
import androidx.test.platform.app.InstrumentationRegistry
import java.util.Locale
import org.junit.Assert.fail

internal object ScreenshotRegression {
    private const val CHANNEL_DELTA = 24
    private const val MAX_CHANGED_RATIO = 0.005
    private const val MAX_MEAN_CHANNEL_DELTA = 1.5

    fun assertApprovedIfEnabled(name: String, actual: Bitmap) {
        val instrumentation = InstrumentationRegistry.getInstrumentation()
        if (InstrumentationRegistry.getArguments().getString("screenshotRegression") != "true") return
        val asset = "screenshots/api-${Build.VERSION.SDK_INT}/$name.png"
        val expected: Bitmap = try {
            instrumentation.context.assets.open(asset).use(BitmapFactory::decodeStream)
        } catch (_: Exception) {
            null
        } ?: throw AssertionError("Approved screenshot baseline is missing: $asset")
        try {
            if (expected.width != actual.width || expected.height != actual.height) {
                fail("Screenshot size changed for $asset: ${expected.width}x${expected.height} -> ${actual.width}x${actual.height}")
            }
            val top = actual.height / 12
            val bottom = actual.height - top
            var changed = 0L
            var compared = 0L
            var totalChannelDelta = 0L
            for (y in top until bottom) for (x in 0 until actual.width) {
                val expectedPixel = expected.getPixel(x, y)
                val actualPixel = actual.getPixel(x, y)
                val red = kotlin.math.abs(Color.red(expectedPixel) - Color.red(actualPixel))
                val green = kotlin.math.abs(Color.green(expectedPixel) - Color.green(actualPixel))
                val blue = kotlin.math.abs(Color.blue(expectedPixel) - Color.blue(actualPixel))
                if (maxOf(red, green, blue) > CHANNEL_DELTA) changed += 1
                totalChannelDelta += red + green + blue
                compared += 1
            }
            val changedRatio = changed.toDouble() / compared
            val meanChannelDelta = totalChannelDelta.toDouble() / (compared * 3)
            if (changedRatio > MAX_CHANGED_RATIO || meanChannelDelta > MAX_MEAN_CHANNEL_DELTA) {
                fail(
                    "Screenshot regression for $asset: changed=${"%.3f".format(Locale.ROOT, changedRatio * 100)}%, " +
                        "mean-channel-delta=${"%.3f".format(Locale.ROOT, meanChannelDelta)}",
                )
            }
        } finally {
            expected.recycle()
        }
    }
}
