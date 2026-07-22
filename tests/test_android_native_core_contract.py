from pathlib import Path


ROOT = Path(__file__).resolve().parents[1] / "mobile" / "android" / "AlMatchLifeCore"
SOURCE = ROOT / "src" / "main" / "kotlin" / "com" / "almatchlife" / "core"


def read(relative: str) -> str:
    return (SOURCE / relative).read_text(encoding="utf-8")


def test_android_core_contains_no_provider_credentials_and_has_real_build_wrapper():
    combined = "\n".join(path.read_text(encoding="utf-8") for path in ROOT.rglob("*.kt"))
    assert "OPENAI_API_KEY" not in combined
    assert "FCM_SERVER_KEY" not in combined
    assert not (ROOT / "google-services.json").exists()
    assert (ROOT / "gradlew").exists()
    assert (ROOT / "gradle/wrapper/gradle-wrapper.jar").exists()


def test_android_profile_draft_is_process_private_and_device_gates_exist():
    app = ROOT / "app"
    draft = (app / "src/main/kotlin/com/almatchlife/app/ProfileDraftMemory.kt").read_text(encoding="utf-8")
    activity = (app / "src/main/kotlin/com/almatchlife/app/MainActivity.kt").read_text(encoding="utf-8")
    device = (app / "src/androidTest/kotlin/com/almatchlife/app/MainActivityDeviceTest.kt").read_text(encoding="utf-8")
    build = (app / "build.gradle.kts").read_text(encoding="utf-8")
    assert "object ProfileDraftMemory" in draft
    assert "getSharedPreferences(" not in draft
    assert "putString(" not in draft
    assert "File(" not in draft
    assert "ProfileDraftMemory.read(profile.email)" in activity
    assert "ProfileDraftMemory.clear(profile.email)" in activity
    assert 'putString("bio"' not in activity
    assert 'testInstrumentationRunner = "androidx.test.runner.AndroidJUnitRunner"' in build
    assert 'espresso-accessibility:3.7.0' in build
    assert "AccessibilityChecks.enable().setRunChecksFromRootView(true)" in device
    assert 'setFontScale("2.0")' in device
    assert 'shell("settings put system font_scale $value")' in device
    assert "it.toFloatOrNull()" in device
    assert '?: "1.0"' in device
    assert "content.draw(Canvas(it))" in device
    assert "PlatformTestStorageRegistry.getInstance().openOutputFile" in device


def test_android_notification_permission_ui_is_user_driven_and_recovers_from_settings():
    app = ROOT / "app"
    activity = (app / "src/main/kotlin/com/almatchlife/app/MainActivity.kt").read_text(encoding="utf-8")
    strings = (app / "src/main/res/values/strings.xml").read_text(encoding="utf-8")
    assert "requestNotificationPermission()" in activity
    assert "markRequestStarted()" in activity
    assert "canUseFullScreenIntent()" in activity
    assert "fullScreenSettingsIntent()" in activity
    assert 'currentNestedScreen == "notifications"' in activity
    assert "override fun onResume()" in activity
    assert "ActivityNotFoundException" in activity and "SecurityException" in activity
    assert "Приложение не включает это разрешение самостоятельно" in strings


def test_android_app_shell_spacing_is_density_safe_and_touch_targets_are_bounded():
    activity = (ROOT / "app/src/main/kotlin/com/almatchlife/app/MainActivity.kt").read_text(encoding="utf-8")
    for legacy in (
        "setPadding(32, 28, 32, 28)",
        "setPadding(24, 18, 24, 18)",
        "setPadding(16, 48, 16, 48)",
        "setMargins(0, 18, 0, 18)",
        "setMargins(if (message.mine) 56 else 0",
    ):
        assert legacy not in activity
    assert activity.count("minHeight = dp(48)") >= 4
    assert "setPadding(dp(20), dp(16), dp(20), dp(16))" in activity
    app = ROOT / "app/src/main/res"
    assert "windowLightNavigationBar" not in (app / "values/styles.xml").read_text(encoding="utf-8")
    assert "windowLightNavigationBar" not in (app / "values-night/styles.xml").read_text(encoding="utf-8")
    assert "windowLightNavigationBar" in (app / "values-v27/styles.xml").read_text(encoding="utf-8")
    assert "windowLightNavigationBar" in (app / "values-night-v27/styles.xml").read_text(encoding="utf-8")


def test_android_user_errors_are_typed_safe_and_never_render_arbitrary_exception_messages():
    app = ROOT / "app"
    mapper = (app / "src/main/kotlin/com/almatchlife/app/UserFacingFailure.kt").read_text(encoding="utf-8")
    activity = (app / "src/main/kotlin/com/almatchlife/app/MainActivity.kt").read_text(encoding="utf-8")
    assert "UnknownHostException" in mapper
    assert "SocketTimeoutException" in mapper
    assert 'cause.message == "authentication required"' in mapper
    assert "SAFE_VALIDATION_MESSAGES" in mapper
    assert "SAFE_AUTH_MESSAGES" in mapper
    assert "cause.message?.take" not in activity
    assert "mapped.validationMessage ?: getString" in activity
    for value in ("error_offline", "error_timeout", "error_session_expired", "error_service_unavailable"):
        assert f"R.string.{value}" in activity


def test_android_feed_images_are_same_origin_bounded_and_signature_checked():
    app = ROOT / "app"
    loader = (app / "src/main/kotlin/com/almatchlife/app/SafeRemoteImageLoader.kt").read_text(encoding="utf-8")
    application = (app / "src/main/kotlin/com/almatchlife/app/AlMatchApplication.kt").read_text(encoding="utf-8")
    client = (app / "src/main/kotlin/com/almatchlife/app/AppApiClient.kt").read_text(encoding="utf-8")
    activity = (app / "src/main/kotlin/com/almatchlife/app/MainActivity.kt").read_text(encoding="utf-8")
    assert "uri.scheme == origin.scheme && uri.host == origin.host && uri.port == origin.port" in loader
    assert "connection.instanceFollowRedirects = false" in loader
    assert 'setRequestProperty("Accept-Encoding", "identity")' in loader
    assert "MAX_BYTES = 3 * 1024 * 1024" in loader
    assert "MAX_DIMENSION = 4096" in loader
    assert "MAX_PIXELS = 12_000_000L" in loader
    assert "signatureMatches(contentType, bytes)" in loader
    assert '"image/jpeg"' in loader and '"image/png"' in loader and '"image/webp"' in loader
    assert "inJustDecodeBounds = true" in loader
    assert "imageUrls.size < 4" in client
    assert "imageUrls = imageUrls.distinct()" in client
    assert "val galleryUrls = post.imageUrls.take(4)" in activity
    assert "galleryUrls.forEachIndexed" in activity
    assert "applicationGraph.imageLoader.load(imageUrl)" in activity
    assert "HorizontalScrollView" in activity
    assert "bitmap?.recycle()" in activity
    assert "class DisconnectingImageFuture" in loader
    assert "connection.getAndSet(null)?.disconnect()" in loader
    assert "if (!future.complete(bitmap)) bitmap.recycle()" in loader
    assert "imageLoads += imageLoad" in activity
    assert "imageLoads -= imageLoad" in activity
    assert "imageLoads.toList().forEach { it.cancel(true) }" in activity
    assert "LruCache<String, ByteArray>(CACHE_BYTES)" in loader
    assert "CACHE_BYTES = 12 * 1024 * 1024" in loader
    assert "byteCache.remove(key)" in loader
    assert "decodeBounded(downloaded).also" in loader
    assert "byteCache.put(key, downloaded)" in loader
    assert "fun trimMemory(aggressive: Boolean)" in loader
    assert "byteCache.evictAll()" in loader
    assert "byteCache.trimToSize(CACHE_BYTES / 2)" in loader
    assert "override fun onTrimMemory(level: Int)" in application
    assert "RUNNING_LOW_MEMORY_LEVEL = 10" in application
    assert "UI_HIDDEN_MEMORY_LEVEL = 20" in application
    assert "apiExecutor = Executors.newFixedThreadPool(3)" in application
    assert "ArrayBlockingQueue(IMAGE_QUEUE_CAPACITY)" in application
    assert "IMAGE_WORKERS = 2" in application
    assert "IMAGE_QUEUE_CAPACITY = 12" in application
    assert "SafeRemoteImageLoader(endpoint, imageExecutor)" in application
    assert "AndroidUrlConnectionApiTransport(apiExecutor)" in application
    assert "}.onFailure { failure -> future.completeExceptionally(failure) }" in loader
    assert 'fun feed(cursor: String = ""): CompletableFuture<FeedPage>' in client
    assert "FEED_PAGE_SIZE = 10" in client
    assert "page.nextCursor.isNotEmpty()" in activity
    assert "requestPage(page.nextCursor, moreStatus)" in activity
    assert "!content.isAttachedToWindow" in activity
    assert "requestPage(cursor, loading)" in activity
    assert "!gallery.isAttachedToWindow" in activity
    assert "displayedBitmaps.forEach { if (!it.isRecycled) it.recycle() }" in activity
    assert "fun startImageLoad()" in activity
    assert "retryImage.visibility = View.VISIBLE" in activity
    assert "if (retryImage.isEnabled) startImageLoad()" in activity
    assert "val galleryLoaders = mutableListOf<() -> Unit>()" in activity
    assert "galleryLoaders.getOrNull(index + 1)?.invoke()" in activity
    assert "runWhenVisible(gallery) { galleryLoaders.firstOrNull()?.invoke() }" in activity
    assert "if (!advancedToNext)" in activity
    assert "view.getGlobalVisibleRect(visibleBounds)" in activity
    assert "removeOnScrollChangedListener(scrollListener)" in activity
    assert "view.removeOnAttachStateChangeListener(attachListener)" in activity
    assert "setText(R.string.media_waiting)" in activity
    assert "R.string.media_retry_description" in activity
    assert 'fun toggleFeedInteraction(postId: String, action: String)' in client
    assert 'action in setOf("like", "save")' in client
    assert "liked = item.requiredBoolean(\"liked\")" in client
    assert "saved = item.requiredBoolean(\"saved\")" in client
    assert 'toggle(likeButton, "like")' in activity
    assert 'toggle(saveButton, "save")' in activity
    assert "if (isDestroyed || !this.isAttachedToWindow)" in activity
    assert 'fun addFeedComment(postId: String, text: String)' in client
    assert "MAX_COMMENT_TEXT = 1_000" in client
    assert "InputFilter.LengthFilter(1_000)" in activity
    assert "commentComposer.visibility = View.GONE" in activity
    assert "appApi.addFeedComment(post.id" in activity


def test_android_push_payload_is_receiver_bound_expiring_and_stable():
    source = read("CallContracts.kt")
    assert 'receiver != currentEmail.trim().lowercase()' in source
    assert "expiresAt > nowEpochSeconds + 180" in source
    assert 'MessageDigest.getInstance("SHA-256")' in source
    assert '"al-match-life:${callType.wireValue}:$callId"' in source
    assert 'Regex("^[A-Za-z0-9_-]+$")' in source


def test_android_speech_state_machine_matches_server_contract():
    source = read("SpeechEngineState.kt")
    for state in ("IDLE", "CONNECTING", "STREAMING", "FALLBACK", "STOPPING", "STOPPED", "FAILED"):
        assert state in source
    assert "STREAMING to setOf(FALLBACK, STOPPING, FAILED)" in source
    assert "realtime.stop()" in source
    assert "fallback.stop()" in source


def test_android_realtime_transport_isolated_ephemeral_and_bounded():
    source = read("RealtimeSpeechTransport.kt")
    assert "addClonedMicrophoneTrack" in source
    assert 'uri.host?.lowercase() != "api.openai.com"' in source
    assert 'uri.path != "/v1/realtime/calls"' in source
    assert "MAX_SDP_BYTES = 64 * 1024" in source
    assert 'name=\\"sdp\\"; filename=\\"offer.sdp\\"' in source
    assert "session.expiresAt <= nowEpochSeconds() + 5" in source
    assert "candidate.close()" in source
    assert "partials.clear()" in source


def test_android_realtime_publishes_only_final_transcripts():
    source = read("RealtimeSpeechTransport.kt")
    assert '"conversation.item.input_audio_transcription.delta"' in source
    assert '"conversation.item.input_audio_transcription.completed"' in source
    assert '"error" -> errorHandler' in source
    publisher = source.split("class FinalCaptionPublisher", 1)[1]
    assert "if (!transcript.isFinal" in publisher
    assert "api.publishCaption" in publisher


def test_android_translation_is_latest_only_and_tts_is_safely_bounded():
    source = read("CaptionTranslationPlayback.kt")
    assert "presenter.showOriginal(caption)" in source
    assert "latestCaptionId == caption.id" in source
    assert "while (queue.size >= 2) queue.removeFirst()" in source
    assert "api.translatedSpeech" in source
    assert "ducker.setDucked(true)" in source
    assert source.count("ducker.setDucked(false)") >= 3
    assert "player.stop()" in source
    lifecycle = source.split("class AndroidSpeechCaptions", 1)[1]
    assert lifecycle.index("translation.stop()") < lifecycle.index("playback.cancel()") < lifecycle.index("engine.stop()")


def test_android_synthetic_speech_requires_server_metadata_and_size_cap():
    source = read("AuthenticatedApiClient.kt")
    assert 'header("X-AI-Generated-Voice")' in source
    assert 'responseCaptionId != captionId' in source
    assert 'responseVoice != voice' in source
    assert 'contentType != "audio/mpeg"' in source
    assert "MAX_SYNTHETIC_SPEECH_BYTES = 2 * 1024 * 1024" in source
    assert "ALLOWED_SYNTHETIC_VOICES" in source


def test_android_google_realtime_peer_is_isolated_bounded_and_cleanup_safe():
    source = (ROOT / "src/googleWebRtc/kotlin/com/almatchlife/core/webrtc/GoogleRealtimeSpeechPeerAdapter.kt").read_text(encoding="utf-8")
    assert "ClonedMicrophoneTrackProvider" in source
    assert 'createDataChannel(EVENTS_CHANNEL' in source
    assert 'const val EVENTS_CHANNEL = "oai-events"' in source
    assert "if (buffer.binary || closed.get()) return" in source
    assert "view.remaining() !in 1..MAX_EVENT_BYTES" in source
    assert "setLocalDescription(observer, offer)" in source
    close = source.split("override suspend fun close()", 1)[1]
    assert close.index("events?.close()") < close.index("microphoneHandle?.release()") < close.index("peer?.close()")
    assert "handle.track.dispose()" not in source


def test_android_realtime_json_decoder_is_fail_closed_and_allowlisted():
    source = (ROOT / "src/systemIntegration/kotlin/com/almatchlife/core/system/AndroidRealtimeEventJsonCodec.kt").read_text(encoding="utf-8")
    assert "bytes.size > MAX_EVENT_BYTES" in source
    assert "if (type !in ALLOWED_TYPES) return null" in source
    assert 'optJSONObject("error")' in source
    assert "it.length <= maximum" in source
    assert "conversation.item.input_audio_transcription.completed" in source


def test_android_mobile_json_codec_covers_all_wire_contracts_and_is_bounded():
    source = (ROOT / "src/systemIntegration/kotlin/com/almatchlife/core/system/AndroidMobileWireJsonCodec.kt").read_text(encoding="utf-8")
    for method in (
        "decodeSessionTokens", "decodeIceConfiguration", "decodeSignalPoll",
        "decodeCaptionPoll", "decodeCaptionTranslation", "decodeRealtimeSession",
    ):
        assert f"override fun {method}" in source
    assert "bytes.size > MAX_JSON_BYTES" in source
    assert "it.isFinite()" in source
    assert "MAX_SDP = 64 * 1024" in source
    assert "MAX_CANDIDATE = 4096" in source
    assert 'put("target_language", targetLanguage)' in source
    assert 'put("voice", it)' in source
    assert "JSONObject().apply(block).toString().toByteArray" in source


def test_android_synthetic_media_player_is_ephemeral_validated_and_once_only():
    source = (ROOT / "src/systemIntegration/kotlin/com/almatchlife/core/system/AndroidSyntheticSpeechPlayer.kt").read_text(encoding="utf-8")
    assert "AudioAttributes.USAGE_ASSISTANCE_ACCESSIBILITY" in source
    assert "AudioAttributes.CONTENT_TYPE_SPEECH" in source
    assert "MAX_MP3_BYTES = 2 * 1024 * 1024" in source
    assert "if (!id3 && !frameSync)" in source
    assert "File.createTempFile(TEMP_PREFIX, TEMP_SUFFIX, cacheDirectory)" in source
    assert "player.setDataSource(input.fd)" in source
    assert "if (!staged.delete())" in source
    assert "candidate.finished.compareAndSet(false, true)" in source
    assert "candidate.player.release()" in source
    assert "speech.captionId" not in source


def test_android_urlconnection_transport_is_bounded_nonredirecting_and_cancelable():
    source = (ROOT / "src/systemIntegration/kotlin/com/almatchlife/core/system/AndroidUrlConnectionApiTransport.kt").read_text(encoding="utf-8")
    assert "connection.instanceFollowRedirects = false" in source
    assert 'setRequestProperty("Accept-Encoding", "identity")' in source
    assert "connection.connectTimeout = connectTimeoutMillis" in source
    assert "connection.readTimeout = readTimeoutMillis" in source
    assert "total > maximumResponseBytes" in source
    assert "MAXIMUM_REQUEST_BYTES = 256 * 1024" in source
    assert "request.headers.size > MAXIMUM_HEADERS" in source
    assert "class DisconnectingFuture" in source
    assert "connection.get()?.disconnect()" in source
    assert "instanceFollowRedirects = true" not in source


def test_android_remote_caption_polling_overlaps_dedupes_and_survives_local_ai_failure():
    source = read("CaptionTranslationPlayback.kt")
    polling = source.split("class RemoteCaptionPolling", 1)[1].split("class LatestCaptionTranslation", 1)[0]
    assert "result.serverTime - CURSOR_OVERLAP_SECONDS" in polling
    assert "caption.id in processedIds" in polling
    assert "processedIds.size > MAX_PROCESSED_IDS" in polling
    assert "MAX_PROCESSED_IDS = 300" in polling
    assert "MAX_RETRY_MILLIS = 6_400L" in polling
    assert polling.index("translation.receive(caption)") < polling.index("remember(caption.id)")
    assert "playback?.enqueue(caption.id)" not in polling
    translation = source.split("class LatestCaptionTranslation", 1)[1].split("class SafeTranslatedSpeechPlayback", 1)[0]
    assert translation.index("presenter.showTranslation(caption, translation)") < translation.index("onTranslated(caption)")
    assert "fun resume()" in translation
    lifecycle = source.split("class AndroidSpeechCaptions", 1)[1]
    assert lifecycle.index("translation.resume()") < lifecycle.index("remote.start()") < lifecycle.index("engine.start()")
    assert "localSpeechError(failure)" in lifecycle
    assert lifecycle.index("remote.stop()") < lifecycle.index("translation.stop()") < lifecycle.index("playback.cancel()")


def test_android_build_is_version_pinned_checksum_verified_and_secret_free():
    build = (ROOT / "build.gradle.kts").read_text(encoding="utf-8")
    wrapper = (ROOT / "gradle/wrapper/gradle-wrapper.properties").read_text(encoding="utf-8")
    workflow = (ROOT.parents[2] / ".github/workflows/android-core.yml").read_text(encoding="utf-8")
    assert 'id("com.android.library") version "8.11.2"' in build
    assert 'id("org.jetbrains.kotlin.android") version "2.4.10"' in build
    assert 'id("com.google.gms.google-services") version "4.5.0" apply false' in build
    assert "compileSdk = 36" in build
    assert "minSdk = 26" in build
    assert build.count("targetSdk = 36") == 2
    assert "jvmToolchain(17)" in build
    assert 'firebase-bom:34.16.0' in build
    assert "webrtcAar and webrtcSha256 must be supplied together" in build
    assert "WebRTC AAR SHA-256 mismatch" in build
    assert "unsafe WebRTC AAR entries" in build
    assert '"jni/arm64-v8a/libjingle_peerconnection_so.so"' in build
    assert '"jni/x86_64/libjingle_peerconnection_so.so"' in build
    lock = (ROOT / "webrtc-source.lock").read_text(encoding="utf-8")
    assert "revision=e3000c87329bf7cfe1f345bf566c482a402d0d62" in lock
    assert "depot_tools_revision=980d6af16e06ff993a52029019dc0628c0a0e1f0" in lock
    assert "architectures=arm64-v8a,x86_64" in lock
    assert "gradle-8.14.4-bin.zip" in wrapper
    assert "distributionSha256Sum=f1771298a70f6db5a29daf62378c4e18a17fc33c9ba6b14362e0cdf40610380d" in wrapper
    assert 'java-version: "17"' in workflow
    assert '"platforms;android-36" "build-tools;35.0.0"' in workflow
    assert "google-services.json" not in build


def test_android_ci_runs_installed_apk_on_minimum_and_modern_emulators():
    workflow = (ROOT.parents[2] / ".github/workflows/android-core.yml").read_text(encoding="utf-8")
    assert "device-tests:" in workflow
    assert "needs: verify-android" in workflow
    assert "api-level: 26" in workflow
    assert "api-level: 35" in workflow
    assert "reactivecircus/android-emulator-runner@v2.38.0" in workflow
    assert ":app:connectedDebugAndroidTest" in workflow
    assert "connected_android_test_additional_output" in workflow
    assert "android-device-api-${{ matrix.api-level }}" in workflow


def test_android_screenshot_regression_is_opt_in_bounded_and_missing_baseline_fails():
    app = ROOT / "app"
    build = (app / "build.gradle.kts").read_text(encoding="utf-8")
    comparator = (app / "src/androidTest/kotlin/com/almatchlife/app/ScreenshotRegression.kt").read_text(encoding="utf-8")
    device = (app / "src/androidTest/kotlin/com/almatchlife/app/MainActivityDeviceTest.kt").read_text(encoding="utf-8")
    assert 'gradleProperty("amlScreenshotRegression")' in build
    assert 'getString("screenshotRegression") != "true"' in comparator
    assert '"screenshots/api-${Build.VERSION.SDK_INT}/$name.png"' in comparator
    assert "Approved screenshot baseline is missing" in comparator
    assert "MAX_CHANGED_RATIO = 0.005" in comparator
    assert "MAX_MEAN_CHANNEL_DELTA = 1.5" in comparator
    assert "expected.width != actual.width" in comparator
    assert device.count("ScreenshotRegression.assertApprovedIfEnabled") == 2


def test_android_release_requires_final_identity_firebase_and_external_signing():
    app_build = (ROOT / "app/build.gradle.kts").read_text(encoding="utf-8")
    assert 'providers.gradleProperty("amlApplicationId")' in app_build
    assert 'configuredId != "com.almatchlife.app"' in app_build
    assert "isValidApplicationId(configuredId)" in app_build
    assert 'file("google-services.json")' in app_build
    assert 'firebaseConfig.length() in 1..262_144' in app_build
    for variable in (
        "AML_ANDROID_KEYSTORE_FILE", "AML_ANDROID_KEYSTORE_PASSWORD",
        "AML_ANDROID_KEY_ALIAS", "AML_ANDROID_KEY_PASSWORD",
    ):
        assert f'environmentVariable("{variable}")' in app_build
    assert 'if (completeSigningEnvironment) signingConfig' in app_build
    assert "storePassword = signingStorePassword" in app_build


def test_android_official_webrtc_build_is_linux_only_pinned_and_auditable():
    script = (ROOT / "build-official-webrtc.sh").read_text(encoding="utf-8")
    workflow = (ROOT.parents[2] / ".github/workflows/android-webrtc.yml").read_text(encoding="utf-8")
    assert '"$(uname -s)" != "Linux"' in script
    assert 'cd "$source_dir"' in script
    assert "workflow_dispatch:" in workflow
    assert "contents: read" in workflow
    assert "DEPOT_TOOLS_REVISION: 980d6af16e06ff993a52029019dc0628c0a0e1f0" in workflow
    assert 'gclient sync --revision "src@${WEBRTC_REVISION}" --no-history' in workflow
    assert './verify-build.sh -PwebrtcAar="${artifact}" -PwebrtcSha256="${digest}"' in workflow
    assert "LICENSE.md" in workflow


def test_android_native_lifecycle_orders_primary_call_before_optional_ai():
    source = read("NativeCallLifecycle.kt")
    accepted = source.index('signaling.send("accepted"')
    audio = source.index("audio.activate", accepted)
    media = source.index("media.start", audio)
    captions = source.index("captions.start", media)
    assert accepted < audio < media < captions
    assert "optionalFeatureError(failure)" in source
    assert 'reason = "connection_lost"' in source
    assert '"android_${UUID.randomUUID()' in source


def test_android_tokens_use_non_exportable_aes_gcm_key_and_ciphertext_only():
    source = read("android/AndroidKeystoreTokenStore.kt")
    assert 'ANDROID_KEY_STORE = "AndroidKeyStore"' in source
    assert 'TRANSFORMATION = "AES/GCM/NoPadding"' in source
    assert ".setKeySize(256)" in source
    assert ".setRandomizedEncryptionRequired(true)" in source
    assert "GCMParameterSpec(128" in source
    assert ".putString(IV_KEY" in source
    assert ".putString(CIPHERTEXT_KEY" in source
    assert 'putString("access' not in source
    assert "plaintext.fill(0)" in source
    assert "catch (failure: AEADBadTagException)" in source


def test_android_callstyle_has_safe_actions_and_full_screen_eligibility():
    source = read("android/IncomingCallNotifier.kt")
    assert "Notification.CallStyle.forIncomingCall(caller, decline, answer)" in source
    assert "PendingIntent.FLAG_UPDATE_CURRENT or PendingIntent.FLAG_IMMUTABLE" in source
    assert ".setComponent(actionReceiver)" in source
    assert ".setPackage(context.packageName)" in source
    assert "notificationManager.canUseFullScreenIntent()" in source
    assert "if (canUseFullScreenIntent()) builder.setFullScreenIntent" in source
    assert "NotificationManager.IMPORTANCE_HIGH" in source


def test_android_call_notification_is_private_cancelable_and_process_deduplicated():
    source = read("android/IncomingCallNotifier.kt")
    assert "Notification.VISIBILITY_PRIVATE" in source
    assert 'setContentText("Open the app to view caller details")' in source
    assert "ledger.contains(ledgerKey(payload))" in source
    assert "ledger.edit().putString(ledgerKey(payload), payload.eventId).commit()" in source
    assert "catch (failure: RuntimeException)" in source
    assert "notificationManager.cancel(notificationId(payload))" in source
    assert "payload.stableUuid.hashCode()" in source


def test_android_api_client_is_origin_locked_and_retries_auth_only_once():
    source = read("AuthenticatedApiClient.kt")
    assert 'throw ApiClientException("HTTPS is required")' in source
    assert 'uri.userInfo != null || uri.query != null || uri.fragment != null' in source
    assert 'resolved.scheme != baseUri.scheme || resolved.host != baseUri.host' in source
    assert 'if (response.statusCode != 401)' in source
    assert "else refreshSingleFlight(tokens.accessToken).thenCompose" in source
    assert source.count("refreshSingleFlight(tokens.accessToken).thenCompose") == 1
    assert 'safeHeaders["Authorization"] = "Bearer $accessToken"' in source
    assert "'\\r' in token || '\\n' in token" in source


def test_android_refresh_rotation_is_single_flight_atomic_and_failure_clears_session():
    source = read("AuthenticatedApiClient.kt")
    assert "private val refreshLock = Any()" in source
    assert "private var refreshInFlight: CompletableFuture<SessionTokens>?" in source
    assert "refreshInFlight?.let { return@synchronized it }" in source
    assert "if (current.accessToken != staleAccessToken)" in source
    assert 'uri = endpoint("/api/auth/refresh")' in source
    assert "tokenStore.save(it)" in source
    assert "if (refreshInFlight === candidate)" in source
    assert "if (failure != null) tokenStore.clear()" in source
    assert ".get()" not in source
    assert "suspendCoroutine" in source


def test_android_signaling_requires_exact_server_acknowledgement():
    source = read("AuthenticatedApiClient.kt")
    assert 'path = "/api/calls/${payload.callId}/signals"' in source
    assert "acknowledgement.eventId != eventId" in source
    assert 'throw ApiClientException("signal acknowledgement mismatch")' in source
    assert "requireIdentifier(eventId, 16, 80" in source


def test_android_call_coordinator_reserves_before_reporting_and_bounds_deduplication():
    source = read("VoipCallCoordinator.kt")
    reserve = source.index("active[payload.stableUuid] = payload")
    report = source.index("system.reportIncoming(reserved.payload)")
    assert reserve < report
    assert "private val lock = Any()" in source
    assert "private val maximumSeenEvents = 256" in source
    assert "while (seenEventIds.size > maximumSeenEvents)" in source
    assert "if (payload.eventId in seenEventIds)" in source
    assert "active.remove(reserved.payload.stableUuid, reserved.payload)" in source


def test_android_call_coordinator_actions_are_once_only_and_connection_loss_is_terminal():
    source = read("VoipCallCoordinator.kt")
    assert "if (uuid in accepted || !accepting.add(uuid))" in source
    assert "if (!retained) lifecycle.stop()" in source
    assert "val payload = take(uuid) ?: return" in source
    assert "lifecycle.connectionLost(payload)" in source
    assert "system.reportEnded(uuid, SystemCallEndReason.FAILED)" in source
    assert "if (result.second) lifecycle.end(result.first) else lifecycle.decline(result.first)" in source
    assert "accepting.remove(uuid)" in source


def test_android_person_webrtc_loads_turn_before_peer_and_acks_after_processing():
    source = read("PersonWebRtcTransport.kt")
    ice = source.index("val configuration = signaling.ice(payload)")
    peer = source.index("val candidate = factory.make(configuration)")
    media = source.index("candidate.addLocalMedia(payload.callType)")
    assert ice < peer < media
    process = source.index("process(message)")
    remember = source.index("rememberProcessed(message.id)", process)
    ack = source.index("signaling.acknowledge(currentPayload, ackBatch)", remember)
    assert process < remember < ack
    assert "result.serverTime - 1.0" in source
    assert "while (processedIds.size > 600)" in source
    assert "ackBatch.forEach { acknowledged" in source


def test_android_person_webrtc_queues_ice_until_sdp_and_requeues_failed_tail():
    source = read("PersonWebRtcTransport.kt")
    assert "if (!localDescriptionPublished || currentPayload == null)" in source
    assert "signaling.sendDescription(currentPayload, \"answer\", answer" in source
    assert "localDescriptionPublished = true" in source
    assert "snapshot.second.drop(index).asReversed()" in source
    assert "while (pendingLocalCandidates.size > 128)" in source
    assert 'eventId("ice")' in source


def test_android_incoming_recovery_is_offline_aware_bounded_and_glare_free():
    source = read("PersonWebRtcTransport.kt")
    assert "var delay = 5_000L" in source
    assert "if (!network.isOnline())" in source
    assert "RecoveryStatus.WaitingForNetwork" in source
    assert "delay = 1_000L" in source
    assert "if (attempt >= 3)" in source
    assert "minOf(5_000L * (attempt + 1), 10_000L)" in source
    assert 'failureHandler(PersonTransportException("recovery exhausted"))' in source
    assert "createOffer" not in source
    assert "createAnswer" in source


def test_android_person_webrtc_stop_invalidates_tasks_and_detaches_callbacks():
    source = read("PersonWebRtcTransport.kt")
    stop = source.index("override suspend fun stop()")
    assert "generation += 1" in source[stop:]
    assert "snapshot.second?.cancel()" in source[stop:]
    assert "snapshot.third?.cancel()" in source[stop:]
    assert "setLocalCandidateHandler {}" in source[stop:]
    assert "setConnectionStateHandler {}" in source[stop:]
    assert "pendingAckIds.clear()" in source[stop:]
    assert "pendingLocalCandidates.clear()" in source[stop:]


def test_android_signaling_adapter_encodes_query_and_validates_turn_before_use():
    client = read("AuthenticatedApiClient.kt")
    signaling = read("AuthenticatedPersonCallSignaling.kt")
    assert "encodeQueryValue(key)" in client
    assert '.replace("+", "%20")' in client
    assert "query.size > 16" in client
    assert "configuration.expiresAt <= nowEpochSeconds() + 5.0" in signaling
    assert "configuration.servers.isEmpty()" in signaling
    assert 'normalized.startsWith("turns:")' in signaling
    assert 'get(payload, "ice-servers")' in signaling


def test_android_signaling_adapter_bounds_sdp_ice_and_ack_batches():
    source = read("AuthenticatedPersonCallSignaling.kt")
    assert "sdp.length > 64 * 1024" in source
    assert "candidate.candidate.length > 4096" in source
    assert "unique.size > 50 || unique.size != eventIds.size" in source
    assert "decodeAcknowledgedEventIds(response.body).toSet() != unique.toSet()" in source
    assert "acknowledgement.eventId != eventId" in source
    assert "response.statusCode !in 200..299" in source


def test_google_webrtc_android_adapter_is_unified_plan_turn_and_media_configured():
    source = (ROOT / "src/googleWebRtc/kotlin/com/almatchlife/core/webrtc/GoogleWebRtcPeerAdapter.kt").read_text(encoding="utf-8")
    assert "PeerConnection.IceServer.builder(server.urls)" in source
    assert "setUsername" in source and "setPassword" in source
    assert "PeerConnection.SdpSemantics.UNIFIED_PLAN" in source
    assert "PeerConnection.BundlePolicy.MAXBUNDLE" in source
    assert "PeerConnection.RtcpMuxPolicy.REQUIRE" in source
    assert "GATHER_CONTINUALLY" in source
    assert 'MediaConstraints.KeyValuePair("googEchoCancellation", "true")' in source
    assert 'MediaConstraints.KeyValuePair("googNoiseSuppression", "true")' in source


def test_google_webrtc_android_camera_is_front_bounded_and_locally_persisted():
    source = (ROOT / "src/googleWebRtc/kotlin/com/almatchlife/core/webrtc/GoogleWebRtcPeerAdapter.kt").read_text(encoding="utf-8")
    assert "Camera2Enumerator(context)" in source
    assert "firstOrNull(enumerator::isFrontFacing)" in source
    assert "it.width <= 1280 && it.height <= 720" in source
    assert "minOf(selected.framerate.max / 1000, 30)" in source
    create = source.index("override suspend fun createAnswer()")
    local = source.index("setLocalDescription(observer, answer)", create)
    returned = source.index("return answer.description", local)
    assert create < local < returned


def test_google_webrtc_android_close_is_idempotent_and_releases_capture_first():
    source = (ROOT / "src/googleWebRtc/kotlin/com/almatchlife/core/webrtc/GoogleWebRtcPeerAdapter.kt").read_text(encoding="utf-8")
    close = source.index("override suspend fun close()")
    body = source[close:]
    assert "closed.compareAndSet(false, true)" in body
    assert body.index("capturer?.stopCapture()") < body.index("peer?.close()")
    for resource in ("capturer?.dispose()", "surfaceHelper?.dispose()", "videoTrack?.dispose()", "videoSource?.dispose()", "audioTrack?.dispose()", "audioSource?.dispose()", "peer?.dispose()"):
        assert resource in body


def test_android_call_audio_uses_communication_mode_bluetooth_and_restores_state():
    source = read("android/AndroidCallAudioController.kt")
    assert "AudioManager.MODE_IN_COMMUNICATION" in source
    assert "availableCommunicationDevices" in source
    assert "AudioDeviceInfo.TYPE_BLE_HEADSET" in source
    assert "setCommunicationDevice" in source
    assert "startBluetoothSco()" in source
    assert "stopBluetoothSco()" in source
    assert "audioManager.mode = previousMode" in source
    assert "audioManager.isMicrophoneMute = previousMicrophoneMute" in source


def test_android_fcm_service_validates_receiver_expiry_and_rotated_token():
    source = (ROOT / "src/systemIntegration/kotlin/com/almatchlife/core/system/AlMatchFirebaseMessagingService.kt").read_text(encoding="utf-8")
    assert "VoipPayloadValidator.validate(message.data, currentEmail" in source
    assert "System.currentTimeMillis() / 1000" in source
    assert "runtime.receivePush(payload)" in source
    assert "token.length > 4096" in source
    assert "registerFcmToken(token)" in source
    assert "getOrNull() ?: return" in source


def test_android_system_actions_are_explicit_bounded_and_async_safe():
    source = (ROOT / "src/systemIntegration/kotlin/com/almatchlife/core/system/IncomingCallActionReceiver.kt").read_text(encoding="utf-8")
    notifier = read("android/IncomingCallNotifier.kt")
    assert "intent.component?.className != javaClass.name" in source
    assert "intent.`package` != context.packageName" in source
    assert 'Regex("^[A-Za-z0-9_-]{8,128}$")' in source
    assert "val pending = goAsync()" in source
    assert "whenComplete { _, _ -> pending.finish() }" in source
    assert ".putExtra(\"call_type\", payload.callType.wireValue)" in notifier
    assert '.putExtra("call_event_id", payload.eventId)' in notifier
    assert "VALID_EVENT_ID" in source
    assert "decline(callId, callType, eventId)" in source


def test_android_answer_requests_media_before_typed_foreground_service():
    activity = (ROOT / "src/systemIntegration/kotlin/com/almatchlife/core/system/IncomingCallActivity.kt").read_text(encoding="utf-8")
    service = (ROOT / "src/systemIntegration/kotlin/com/almatchlife/core/system/OngoingCallService.kt").read_text(encoding="utf-8")
    permission = activity.index("requestPermissions")
    start = activity.index("startForegroundService")
    assert permission < start
    assert "Manifest.permission.RECORD_AUDIO" in activity
    assert "callType == NativeCallType.VIDEO" in activity
    assert "FOREGROUND_SERVICE_TYPE_MICROPHONE" in service
    assert "FOREGROUND_SERVICE_TYPE_CAMERA" in service
    assert "hasRuntimePermissions(callType)" in service
    assert "activeCallId == callId" in service
    assert "ServiceCompat.stopForeground" in service
    assert "EXTRA_CALL_EVENT_ID" in activity
    assert "EXTRA_CALL_EVENT_ID" in service
    assert "catch (_: RuntimeException)" in activity
    assert "runCatching { AndroidCallRuntimeRegistry.require() }" in service


def test_android_integration_manifest_is_private_and_declares_exact_fgs_types():
    source = (ROOT / "AndroidManifest.integration.xml").read_text(encoding="utf-8")
    assert 'android.permission.FOREGROUND_SERVICE_MICROPHONE' in source
    assert 'android.permission.FOREGROUND_SERVICE_CAMERA' in source
    assert 'android:foregroundServiceType="camera|microphone"' in source
    assert 'android.permission.POST_NOTIFICATIONS' in source
    assert 'android.permission.USE_FULL_SCREEN_INTENT' in source
    assert 'android.permission.MANAGE_OWN_CALLS' not in source
    assert 'android:exported="true"' not in source


def test_android_audio_focus_is_exclusive_observed_and_abandoned_with_routes():
    source = read("android/AndroidCallAudioController.kt")
    assert "AUDIOFOCUS_GAIN_TRANSIENT_EXCLUSIVE" in source
    assert "USAGE_VOICE_COMMUNICATION" in source
    assert "CONTENT_TYPE_SPEECH" in source
    assert "AUDIOFOCUS_REQUEST_GRANTED" in source
    assert "CallAudioFocusEvent.LOST_PERMANENT" in source
    assert "CallAudioFocusEvent.LOST_TRANSIENT" in source
    assert "registerAudioDeviceCallback" in source
    assert "unregisterAudioDeviceCallback" in source
    assert "abandonAudioFocusRequest" in source
    assert "override fun onAudioDevicesRemoved" in source
    assert "deviceCallbackRegistered" in source
    assert source.index("active = true") < source.index("audioManager.mode = AudioManager.MODE_IN_COMMUNICATION")
    assert "if (!active && focusRequest == null) return" in source
    assert "runCatching { audioManager.unregisterAudioDeviceCallback" in source
    assert "runCatching { audioManager.abandonAudioFocusRequest" in source


def test_android_device_audio_test_restores_state_and_checks_idempotent_cleanup():
    source = (ROOT / "app/src/androidTest/kotlin/com/almatchlife/app/CallAudioDeviceTest.kt").read_text(encoding="utf-8")
    assert "NativeCallType.AUDIO" in source
    assert "NativeCallType.VIDEO" in source
    assert source.count("controller.deactivate()") >= 4
    assert "assertEquals(originalMode, manager.mode)" in source
    assert "assertEquals(originalMute, manager.isMicrophoneMute)" in source
    assert "latch.await(10, TimeUnit.SECONDS)" in source


def test_android_production_runtime_is_bounded_recoverable_and_cancel_survives_process_death():
    source = (ROOT / "src/systemIntegration/kotlin/com/almatchlife/core/system/ProductionAndroidCallRuntime.kt").read_text(encoding="utf-8")
    coordinator = read("VoipCallCoordinator.kt")
    assert "private val maximumContexts = 32" in source
    assert "resolver.resolveAuthorized(callId, expectedType, expectedEventId)" in source
    assert "expectedType != null && expectedEventId != null" in source
    assert "payload.callId != callId" in source
    assert "payload.callType != expectedType" in source
    assert "payload.eventId != expectedEventId" in source
    assert "cached.eventId == expectedEventId" in source
    assert "else pushCancellation(payload)" in source
    assert "coordinator.restoreActive(payload)" in source
    assert "active.putIfAbsent(payload.stableUuid, payload)" in coordinator
    assert "whenComplete { _, failure" in source


def test_official_android_webrtc_build_packages_pinned_upstream_license():
    script = (ROOT / "build-official-webrtc.sh").read_text(encoding="utf-8")
    workflow = (ROOT.parents[2] / ".github/workflows/android-webrtc.yml").read_text(encoding="utf-8")
    assert '[ ! -s "$source_dir/LICENSE" ]' in script
    assert 'cp "$source_dir/LICENSE" "$license_file"' in script
    assert 'shasum -a 256 "$license_file"' in script
    assert '${{ runner.temp }}/webrtc-output/LICENSE.md' in workflow
    assert '${{ runner.temp }}/webrtc-output/*.sha256' in workflow
    assert 'target_os = [\'android\']' in workflow
    assert workflow.index("target_os = ['android']") < workflow.index('gclient sync --revision')


def test_android_incoming_context_resolution_is_authenticated_exact_and_expiry_bounded():
    client = (ROOT / "app/src/main/kotlin/com/almatchlife/app/AppApiClient.kt").read_text(encoding="utf-8")
    assert "fun resolveIncomingCallContext(" in client
    assert 'path = "/api/calls/$callId/context"' in client
    assert '"call_type" to callType.wireValue' in client
    assert '"event_id" to eventId' in client
    assert "returnedCallId != callId" in client
    assert "returnedCallType != callType.wireValue" in client
    assert "returnedEventId != eventId" in client
    assert "VoipPayloadValidator.validate(" in client


def test_android_notification_permission_flow_never_auto_reprompts_or_assumes_full_screen():
    source = (ROOT / "src/systemIntegration/kotlin/com/almatchlife/core/system/NotificationPermissionController.kt").read_text(encoding="utf-8")
    assert "shouldShowRequestPermissionRationale" in source
    assert "NotificationPermissionState.EXPLANATION_REQUIRED" in source
    assert "NotificationPermissionState.SETTINGS_REQUIRED" in source
    assert "markRequestStarted" in source
    assert "ACTION_APP_NOTIFICATION_SETTINGS" in source
    assert "notificationManager.areNotificationsEnabled()" in source
    assert "notificationManager.canUseFullScreenIntent()" in source
    assert "ACTION_MANAGE_APP_USE_FULL_SCREEN_INTENT" in source
    assert "requestPermissions" not in source


def test_android_social_lists_are_mobile_paginated_strict_and_relationship_aware():
    client = (ROOT / "app/src/main/kotlin/com/almatchlife/app/AppApiClient.kt").read_text(encoding="utf-8")
    activity = (ROOT / "app/src/main/kotlin/com/almatchlife/app/MainActivity.kt").read_text(encoding="utf-8")
    strings = (ROOT / "app/src/main/res/values/strings.xml").read_text(encoding="utf-8")
    assert 'fun socialList(profileEmail: String, kind: String, cursor: String = "")' in client
    assert 'kind in setOf("followers", "following")' in client
    assert 'cursor.matches(Regex("^[A-Za-z0-9_-]+$"))' in client
    assert "array.length() > SOCIAL_PAGE_SIZE" in client
    assert 'root.isNull("next_cursor")' in client
    assert "boundedBoolean" in client
    assert "isMutual != (isFollowing && followsYou)" in client
    assert "fun setFollowing(profileEmail: String, following: Boolean)" in client
    assert 'method = if (following) "POST" else "DELETE"' in client
    assert 'loadSocialList(profile, "followers")' in activity
    assert 'loadSocialList(profile, "following")' in activity
    assert "R.string.mutual_follow" in activity
    assert "R.string.follows_you" in activity
    assert "R.string.load_more" in activity
    assert '<string name="followers_count">' in strings
    assert '<string name="following_count">' in strings


def test_android_primary_screens_use_equal_thumb_reachable_bottom_navigation():
    activity = (ROOT / "app/src/main/kotlin/com/almatchlife/app/MainActivity.kt").read_text(encoding="utf-8")
    strings = (ROOT / "app/src/main/res/values/strings.xml").read_text(encoding="utf-8")
    navigation = activity.split("private fun displayMain", 1)[1].split("private fun dp", 1)[0]
    assert 'PrimaryNavItem("home", R.string.nav_home, R.drawable.ic_nav_home)' in navigation
    assert 'PrimaryNavItem("matches", R.string.nav_matches, R.drawable.ic_nav_ai)' in navigation
    assert 'PrimaryNavItem("feed", R.string.nav_feed, R.drawable.ic_nav_feed)' in navigation
    assert 'PrimaryNavItem("messages", R.string.nav_messages, R.drawable.ic_nav_messages)' in navigation
    assert "LinearLayout.LayoutParams(0, ViewGroup.LayoutParams.WRAP_CONTENT, 1f)" in navigation
    assert "minHeight = dp(48)" in navigation
    assert "if (item.key == selected)" in navigation
    assert "contentDescription = getString(item.label)" in navigation
    for screen in ("home", "matches", "feed", "messages"):
        assert f'displayMain(content, profile, "{screen}")' in activity
    login = activity.split("private fun showLogin", 1)[1].split("private fun showRegistration", 1)[0]
    assert "display(content)" in login
    assert "displayMain" not in login
    for name in ("nav_home", "nav_matches", "nav_feed", "nav_messages"):
        assert f'<string name="{name}">' in strings


def test_android_navigation_restores_state_uses_vectors_and_respects_system_bars():
    activity = (ROOT / "app/src/main/kotlin/com/almatchlife/app/MainActivity.kt").read_text(encoding="utf-8")
    drawable_root = ROOT / "app/src/main/res/drawable"
    assert "WindowCompat.enableEdgeToEdge(window)" in activity
    assert "WindowInsetsCompat.Type.systemBars()" in activity
    assert "ViewCompat.setOnApplyWindowInsetsListener" in activity
    assert 'outState.putString(PRIMARY_SECTION_STATE, currentPrimarySection)' in activity
    assert 'savedInstanceState?.getString(PRIMARY_SECTION_STATE)' in activity
    assert "openPrimarySection(profile, currentPrimarySection)" in activity
    assert 'PRIMARY_SECTIONS = setOf("home", "matches", "feed", "messages")' in activity
    assert "setCompoundDrawablesRelativeWithIntrinsicBounds" in activity
    assert "drawable.setTint" in activity
    for name in ("ic_nav_home.xml", "ic_nav_ai.xml", "ic_nav_feed.xml", "ic_nav_messages.xml"):
        source = (drawable_root / name).read_text(encoding="utf-8")
        assert '<vector xmlns:android="http://schemas.android.com/apk/res/android"' in source
        assert 'android:width="22dp"' in source
        assert 'android:fillColor="@android:color/transparent"' in source


def test_android_light_and_dark_themes_share_semantic_tokens_without_activity_rgb_literals():
    activity = (ROOT / "app/src/main/kotlin/com/almatchlife/app/MainActivity.kt").read_text(encoding="utf-8")
    light_colors = (ROOT / "app/src/main/res/values/colors.xml").read_text(encoding="utf-8")
    dark_colors = (ROOT / "app/src/main/res/values-night/colors.xml").read_text(encoding="utf-8")
    light_style = (ROOT / "app/src/main/res/values/styles.xml").read_text(encoding="utf-8")
    dark_style = (ROOT / "app/src/main/res/values-night/styles.xml").read_text(encoding="utf-8")
    light_style_v27 = (ROOT / "app/src/main/res/values-v27/styles.xml").read_text(encoding="utf-8")
    dark_style_v27 = (ROOT / "app/src/main/res/values-night-v27/styles.xml").read_text(encoding="utf-8")
    tokens = (
        "app_background", "app_surface", "app_surface_variant", "app_primary",
        "app_primary_container", "app_match_surface", "app_message_sent",
        "app_outline", "app_text_primary", "app_text_secondary", "app_nav_inactive",
    )
    for token in tokens:
        assert f'name="{token}"' in light_colors
        assert f'name="{token}"' in dark_colors
        assert f"R.color.{token}" in activity or token in {"app_text_primary", "app_text_secondary"}
    assert "Color.rgb" not in activity
    assert "Color.WHITE" not in activity
    assert "ContextCompat.getColor" in activity
    assert '<item name="android:windowLightStatusBar">true</item>' in light_style
    assert '<item name="android:windowLightNavigationBar">true</item>' in light_style_v27
    assert '<item name="android:windowLightStatusBar">false</item>' in dark_style
    assert '<item name="android:windowLightNavigationBar">false</item>' in dark_style_v27


def test_android_nested_state_restore_is_allowlisted_pii_free_and_large_text_safe():
    activity = (ROOT / "app/src/main/kotlin/com/almatchlife/app/MainActivity.kt").read_text(encoding="utf-8")
    assert 'outState.putString(NESTED_SCREEN_STATE, currentNestedScreen)' in activity
    assert 'savedInstanceState?.getString(NESTED_SCREEN_STATE)' in activity
    assert "RESTORABLE_NESTED_SCREENS" in activity
    assert '"social_followers" -> loadSocialList(profile, "followers")' in activity
    assert '"social_following" -> loadSocialList(profile, "following")' in activity
    assert '"notifications" -> showNotifications(profile)' in activity
    assert '"profile_editor" -> showProfileEditor(profile)' in activity
    save_state = activity.split("override fun onSaveInstanceState", 1)[1].split("private fun showLogin", 1)[0]
    assert "email" not in save_state.lower()
    assert "otherEmail" not in save_state
    assert "dp(56)" not in activity.split("private fun displayMain", 1)[1]
    assert "ViewGroup.LayoutParams.WRAP_CONTENT, 1f" in activity
    assert "ViewCompat.setAccessibilityHeading(this, true)" in activity
    assert "ACCESSIBILITY_LIVE_REGION_POLITE" in activity
    assert "IMPORTANT_FOR_ACCESSIBILITY_YES" in activity
