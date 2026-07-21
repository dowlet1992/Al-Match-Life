# Al Match Life Android

This directory contains the native Android call foundation. It is intentionally
kept independent from an application shell so the final package name, signing
configuration, Firebase project, and WebRTC binary are not guessed.

The `app` module is an installable internal shell using the provisional
`com.almatchlife.app.debug` debug application ID. It validates the API origin at
startup and permits cleartext traffic only to Android-emulator loopback in debug
builds. Release builds require an explicit HTTPS origin and disable cleartext
traffic:

```text
./verify-build.sh
./gradlew :app:assembleRelease \
  -PamlReleaseApiBaseUrl=https://api.example.com \
  -PamlApplicationId=com.yourcompany.product
```

Release additionally requires the untracked `app/google-services.json` for the
same final application ID and these environment variables: `AML_ANDROID_KEYSTORE_FILE`,
`AML_ANDROID_KEYSTORE_PASSWORD`, `AML_ANDROID_KEY_ALIAS`, and
`AML_ANDROID_KEY_PASSWORD`. Signing secrets and keystores must remain outside
the repository. Debug builds continue to work without Firebase or production
signing and retain the `.debug` suffix.

Device tests capture screenshot candidates by default. After reviewing and
placing approved PNGs under `app/src/androidTest/assets/screenshots/api-26/`
and `api-35/`, activate bounded pixel comparison with
`-PamlScreenshotRegression=true`. The comparator ignores system-bar bands,
requires identical dimensions, and fails on either excessive changed pixels or
mean RGB drift; a missing baseline fails closed when the gate is enabled.

Install the internal APK on a connected emulator or test phone with:

```text
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

Implemented contracts:

- strict, receiver-bound and expiring FCM call payload validation;
- stable call UUIDs and bounded event deduplication;
- accepted -> audio -> primary media -> optional AI captions lifecycle;
- Android Keystore AES-256-GCM session-token storage;
- origin-locked authenticated API requests with single-flight refresh rotation;
- exact signaling acknowledgement validation before an event is accepted;
- once-only system answer/decline/cancel coordination across concurrent callbacks;
- receiver-safe person-to-person WebRTC signaling, ICE queueing, ACK, and recovery contracts;
- authenticated TURN/poll/SDP/ICE/ACK adapter with bounded typed payloads;
- opt-in Google WebRTC AAR adapter with Unified Plan, bounded Camera2 capture, and deterministic cleanup;
- Android communication-audio routing with Bluetooth/speaker selection and state restoration;
- FCM, explicit call actions, permission-gated incoming Activity, and typed foreground-service integration sources;
- exclusive audio-focus/device-route observation and user-driven notification/full-screen permission state;
- bounded production runtime composition with authorized process-death call recovery;
- isolated Realtime AI WebRTC transcription using short-lived server-minted credentials;
- opt-in Google WebRTC Realtime peer with an injected cloned mic track and bounded text-only provider events;
- fail-closed Android JSON reduction for only the documented transcription delta/final/error event shapes;
- bounded explicit Android JSON codec for auth rotation, TURN/signaling, captions, translation, and Realtime sessions;
- non-redirecting bounded Android URLConnection transport with timeout and disconnect-on-cancel behavior;
- lifecycle-owned remote-caption polling with cursor overlap, bounded deduplication, and retry backoff;
- typed caption publication/polling/translation and metadata-validated synthetic MP3 responses;
- bounded two-caption TTS playback with remote-audio ducking and immediate call-shutdown cancellation;
- Android MediaPlayer speech adapter with MP3 signature validation and immediately unlinked private-cache staging;
- Android 12+ `CallStyle` incoming-call notifications with answer/decline;
- Android 14 full-screen-intent eligibility checks and a safe heads-up fallback.

The app shell still needs product screens and runtime composition for auth,
profile, feed, messages, WebRTC media, and FCM registration. No provider
credential belongs in this repository or in the APK.

The standalone reproducible library build is pinned to JDK 17, Gradle 8.14.4,
AGP 8.11.2, Kotlin 2.4.10, AndroidX Core 1.17.0, compile/target SDK 36, and min
SDK 26. The base source sets have been locally compiled, linted with warnings as
errors, unit-tested, and assembled into a debug AAR. Run `./verify-build.sh`
with JDK 17 and Android SDK 36; CI runs the same gates.

Google WebRTC sources are intentionally excluded unless both properties are
provided. This prevents an old or silently replaced native binary from entering
the build:

```text
./verify-build.sh -PwebrtcAar=/absolute/path/google-webrtc.aar \
  -PwebrtcSha256=<64-lowercase-hex-digest>
```

The reviewed upstream source and `depot_tools` revision are pinned in
`webrtc-source.lock`. Prepare an official Chromium/WebRTC checkout at that
exact revision (including its pinned DEPS), then build the two required 64-bit
ABIs with:

```text
./build-official-webrtc.sh /absolute/path/to/webrtc/src /absolute/output
```

Upstream currently supports Android builds only on Linux. From macOS, run the
manual **Android WebRTC AAR** GitHub Actions workflow; it performs the pinned
checkout, builds both ABIs, compiles the opt-in Kotlin adapters against the
result, and uploads the AAR plus license and checksum records.

The build also produces the upstream third-party license notice and SHA-256
records. The Gradle gate rejects an AAR with the wrong digest, unsafe ZIP paths,
unexpected expansion size, or missing `classes.jar`, arm64, or x86_64 native
libraries. Keep the generated license notice with distribution records.

Firebase uses the official BoM, but `google-services.json`, application signing,
and provider credentials remain host-app responsibilities and must not be added
to this library.
