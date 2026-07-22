package com.almatchlife.app

import android.graphics.Bitmap
import android.os.ParcelFileDescriptor
import androidx.test.core.app.ActivityScenario
import androidx.test.espresso.Espresso.onView
import androidx.test.espresso.accessibility.AccessibilityChecks
import androidx.test.espresso.assertion.ViewAssertions.matches
import androidx.test.espresso.matcher.ViewMatchers.isCompletelyDisplayed
import androidx.test.espresso.matcher.ViewMatchers.isDisplayed
import androidx.test.espresso.matcher.ViewMatchers.withText
import android.widget.Button
import org.hamcrest.Matchers.allOf
import org.hamcrest.Matchers.isA
import androidx.test.ext.junit.runners.AndroidJUnit4
import androidx.test.platform.io.PlatformTestStorageRegistry
import androidx.test.platform.app.InstrumentationRegistry
import java.io.FileInputStream
import org.junit.After
import org.junit.Assert.assertTrue
import org.junit.Before
import org.junit.Test
import org.junit.runner.RunWith

/** Runs on a real Android device or emulator; this is intentionally not a JVM/Robolectric test. */
@RunWith(AndroidJUnit4::class)
class MainActivityDeviceTest {
    private val instrumentation = InstrumentationRegistry.getInstrumentation()
    private var originalFontScale = "1.0"

    @Before
    fun enableAccessibilityChecks() {
        originalFontScale = shell("settings get system font_scale").trim().ifBlank { "1.0" }
        AccessibilityChecks.enable().setRunChecksFromRootView(true)
    }

    @After
    fun restoreDeviceState() {
        shell("settings put system font_scale $originalFontScale")
        AccessibilityChecks.disable()
    }

    @Test
    fun loginScreenPassesAccessibilityChecks() {
        ActivityScenario.launch(MainActivity::class.java).use {
            onView(allOf(withText(R.string.sign_in), isA(Button::class.java))).check(matches(isDisplayed()))
        }
    }

    @Test
    fun loginPrimaryActionRemainsVisibleAtTwoHundredPercentFontScale() {
        shell("settings put system font_scale 2.0")
        ActivityScenario.launch(MainActivity::class.java).use {
            onView(allOf(withText(R.string.sign_in), isA(Button::class.java))).check(matches(isCompletelyDisplayed()))
            val screenshot = capture("login-font-200")
            ScreenshotRegression.assertApprovedIfEnabled("login-font-200", screenshot)
        }
    }

    @Test
    fun loginScreenshotIsCapturedForRegressionBaseline() {
        ActivityScenario.launch(MainActivity::class.java).use {
            onView(allOf(withText(R.string.sign_in), isA(Button::class.java))).check(matches(isCompletelyDisplayed()))
            val screenshot = capture("login-default")
            assertTrue("Screenshot must contain visual content", screenshot.hasVisualContent())
            ScreenshotRegression.assertApprovedIfEnabled("login-default", screenshot)
        }
    }

    private fun capture(name: String): Bitmap {
        instrumentation.waitForIdleSync()
        val bitmap = requireNotNull(instrumentation.uiAutomation.takeScreenshot())
        PlatformTestStorageRegistry.getInstance().openOutputFile("screenshots/$name.png").use { stream ->
            check(bitmap.compress(Bitmap.CompressFormat.PNG, 100, stream))
        }
        return bitmap
    }

    private fun Bitmap.hasVisualContent(): Boolean {
        if (width < 320 || height < 480) return false
        val samples = HashSet<Int>()
        val xStep = (width / 16).coerceAtLeast(1)
        val yStep = (height / 24).coerceAtLeast(1)
        for (x in 0 until width step xStep) for (y in 0 until height step yStep) samples += getPixel(x, y)
        return samples.size >= 4
    }

    private fun shell(command: String): String {
        val descriptor: ParcelFileDescriptor = instrumentation.uiAutomation.executeShellCommand(command)
        return descriptor.use { FileInputStream(it.fileDescriptor).bufferedReader().use { reader -> reader.readText() } }
    }
}
