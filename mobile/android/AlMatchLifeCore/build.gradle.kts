import java.security.MessageDigest
import java.util.zip.ZipFile

plugins {
    id("com.android.library") version "8.11.2"
    id("com.android.application") version "8.11.2" apply false
    id("org.jetbrains.kotlin.android") version "2.4.10"
    id("com.google.gms.google-services") version "4.5.0" apply false
}

val webrtcAarPath = providers.gradleProperty("webrtcAar").orNull
val webrtcSha256 = providers.gradleProperty("webrtcSha256").orNull?.lowercase()
if ((webrtcAarPath == null) != (webrtcSha256 == null)) {
    throw GradleException("webrtcAar and webrtcSha256 must be supplied together")
}
val webrtcAarFile = webrtcAarPath?.let(::file)

android {
    namespace = "com.almatchlife.core"
    compileSdk = 36

    defaultConfig {
        minSdk = 26
        consumerProguardFiles("consumer-rules.pro")
    }

    sourceSets {
        getByName("main") {
            manifest.srcFile("AndroidManifest.integration.xml")
            java.setSrcDirs(listOf(
                "src/main/kotlin",
                "src/systemIntegration/kotlin",
            ) + if (webrtcAarFile != null) listOf("src/googleWebRtc/kotlin") else emptyList())
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    lint {
        targetSdk = 36
        abortOnError = true
        checkDependencies = true
        warningsAsErrors = true
        sarifReport = true
        xmlReport = true
        // AGP 9.3 is outside Kotlin 2.4's documented compatibility range (max 9.1).
        disable += "AndroidGradlePluginVersion"
        // Core 1.19 requires API 37 and AGP 9.1; this module deliberately targets API 36.
        disable += "GradleDependency"
    }

    testOptions {
        targetSdk = 36
        unitTests.isIncludeAndroidResources = true
    }

    buildFeatures {
        buildConfig = false
        aidl = false
        renderScript = false
        resValues = false
        shaders = false
    }
}

kotlin {
    jvmToolchain(17)
    compilerOptions {
        allWarningsAsErrors.set(true)
        freeCompilerArgs.add("-Xjsr305=strict")
    }
}

dependencies {
    // 1.17.x is the newest AndroidX Core line compatible with AGP 8.11 / API 36.
    implementation("androidx.core:core-ktx:1.17.0")
    implementation(platform("com.google.firebase:firebase-bom:34.16.0"))
    implementation("com.google.firebase:firebase-messaging")
    webrtcAarFile?.let { compileOnly(files(it)) }

    testImplementation(kotlin("test"))
    testImplementation("junit:junit:4.13.2")
}

val verifyWebRtcAar = webrtcAarFile?.let { artifact ->
    tasks.register("verifyWebRtcAar") {
        group = "verification"
        description = "Verifies the optional audited WebRTC AAR before compilation."
        inputs.file(artifact)
        inputs.property("expectedSha256", webrtcSha256.orEmpty())
        doLast {
            val inputArtifact = inputs.files.singleFile
            val expected = inputs.properties["expectedSha256"] as String
            if (!inputArtifact.isFile) throw GradleException("WebRTC AAR does not exist: $inputArtifact")
            if (inputArtifact.length() !in 1_000_000L..250_000_000L) {
                throw GradleException("WebRTC AAR size outside trusted bounds")
            }
            if (!expected.matches(Regex("^[a-f0-9]{64}$"))) throw GradleException("invalid WebRTC SHA-256")
            val digest = MessageDigest.getInstance("SHA-256").digest(inputArtifact.readBytes())
                .joinToString("") { "%02x".format(it) }
            if (digest != expected) throw GradleException("WebRTC AAR SHA-256 mismatch")
            ZipFile(inputArtifact).use { archive ->
                val entries = archive.entries().asSequence().toList()
                val names = entries.map { it.name }
                if (names.size != names.toSet().size || names.any {
                    it.startsWith("/") || it.split('/').any { part -> part == ".." }
                }) throw GradleException("unsafe WebRTC AAR entries")
                val required = setOf(
                    "AndroidManifest.xml",
                    "classes.jar",
                    "jni/arm64-v8a/libjingle_peerconnection_so.so",
                    "jni/x86_64/libjingle_peerconnection_so.so",
                )
                if (!names.containsAll(required)) throw GradleException("WebRTC AAR missing required entries")
                val expanded = entries.sumOf { entry -> entry.size.coerceAtLeast(0L) }
                if (expanded > 500_000_000L) throw GradleException("WebRTC AAR expands beyond trusted bound")
            }
        }
    }
}

tasks.named("preBuild").configure { verifyWebRtcAar?.let { dependsOn(it) } }
