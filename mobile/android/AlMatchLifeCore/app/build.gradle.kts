import java.net.URI

plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

val releaseApiBaseUrl = providers.gradleProperty("amlReleaseApiBaseUrl")
val releaseApplicationId = providers.gradleProperty("amlApplicationId")
val reviewedWebRtcAar = providers.gradleProperty("webrtcAar").orNull?.let(rootProject::file)
val firebaseConfig = file("google-services.json")
val signingStoreFile = providers.environmentVariable("AML_ANDROID_KEYSTORE_FILE").orNull?.let(::file)
val signingStorePassword = providers.environmentVariable("AML_ANDROID_KEYSTORE_PASSWORD").orNull
val signingKeyAlias = providers.environmentVariable("AML_ANDROID_KEY_ALIAS").orNull
val signingKeyPassword = providers.environmentVariable("AML_ANDROID_KEY_PASSWORD").orNull
val completeSigningEnvironment = signingStoreFile != null && signingStorePassword != null &&
    signingKeyAlias != null && signingKeyPassword != null

if (firebaseConfig.isFile) apply(plugin = "com.google.gms.google-services")

android {
    namespace = "com.almatchlife.app"
    compileSdk = 36

    defaultConfig {
        applicationId = releaseApplicationId.getOrElse("com.almatchlife.app")
        minSdk = 26
        targetSdk = 36
        versionCode = 1
        versionName = "0.1.0-internal"
        testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"
        testInstrumentationRunnerArguments["screenshotRegression"] =
            providers.gradleProperty("amlScreenshotRegression").getOrElse("false")
        buildConfigField("boolean", "WEBRTC_ARTIFACT_PRESENT", (reviewedWebRtcAar != null).toString())
    }

    signingConfigs {
        if (completeSigningEnvironment) create("production") {
            storeFile = signingStoreFile
            storePassword = signingStorePassword
            keyAlias = signingKeyAlias
            keyPassword = signingKeyPassword
        }
    }

    buildTypes {
        debug {
            applicationIdSuffix = ".debug"
            versionNameSuffix = "-debug"
            buildConfigField("String", "API_BASE_URL", "\"http://10.0.2.2:5000\"")
        }
        release {
            isMinifyEnabled = true
            if (completeSigningEnvironment) signingConfig = signingConfigs.getByName("production")
            buildConfigField(
                "String",
                "API_BASE_URL",
                releaseApiBaseUrl.map { "\"${it.replace("\\", "\\\\").replace("\"", "\\\"")}\"" }
                    .getOrElse("\"https://invalid.almatchlife.local\""),
            )
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"), "proguard-rules.pro")
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    buildFeatures {
        buildConfig = true
    }

    lint {
        abortOnError = true
        warningsAsErrors = true
        targetSdk = 36
        sarifReport = true
        xmlReport = true
        // Versions are pinned centrally to the API 36-compatible toolchain.
        disable += setOf("AndroidGradlePluginVersion", "GradleDependency")
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
    implementation(project(":"))
    implementation("androidx.core:core-ktx:1.17.0")
    implementation(platform("com.google.firebase:firebase-bom:34.16.0"))
    implementation("com.google.firebase:firebase-messaging")
    reviewedWebRtcAar?.let { implementation(files(it)) }

    testImplementation(kotlin("test"))
    testImplementation("junit:junit:4.13.2")
    androidTestImplementation("androidx.test:core-ktx:1.7.0")
    androidTestImplementation("androidx.test:runner:1.7.0")
    androidTestImplementation("androidx.test.ext:junit-ktx:1.3.0")
    androidTestImplementation("androidx.test.espresso:espresso-core:3.7.0")
    androidTestImplementation("androidx.test.espresso:espresso-accessibility:3.7.0")
}

tasks.matching { it.name.startsWith("assembleRelease") || it.name.startsWith("bundleRelease") }.configureEach {
    doFirst {
        val configured = releaseApiBaseUrl.orNull
        require(configured != null && ApiEndpointPolicyForBuild.isValidProductionUrl(configured)) {
            "Release requires -PamlReleaseApiBaseUrl=https://your-api.example with no path, query, or fragment"
        }
        val configuredId = releaseApplicationId.orNull.orEmpty()
        require(ApiEndpointPolicyForBuild.isValidApplicationId(configuredId) && configuredId != "com.almatchlife.app") {
            "Release requires -PamlApplicationId=com.yourcompany.product with a final non-provisional ID"
        }
        require(completeSigningEnvironment && signingStoreFile?.isFile == true) {
            "Release requires AML_ANDROID_KEYSTORE_FILE, AML_ANDROID_KEYSTORE_PASSWORD, " +
                "AML_ANDROID_KEY_ALIAS, and AML_ANDROID_KEY_PASSWORD"
        }
        require(firebaseConfig.isFile && firebaseConfig.length() in 1..262_144) {
            "Release requires an untracked app/google-services.json (maximum 256 KiB)"
        }
    }
}

object ApiEndpointPolicyForBuild {
    private val applicationId = Regex("^[a-z][a-z0-9_]*(\\.[a-z][a-z0-9_]*){2,}$")

    fun isValidApplicationId(value: String): Boolean = value.length in 5..150 && applicationId.matches(value)

    fun isValidProductionUrl(value: String): Boolean = runCatching {
        val uri = URI(value)
        uri.scheme == "https" && !uri.host.isNullOrBlank() && uri.userInfo == null &&
            (uri.path.isNullOrEmpty() || uri.path == "/") && uri.query == null && uri.fragment == null
    }.getOrDefault(false)
}
