#!/bin/sh
set -eu

if ! command -v java >/dev/null 2>&1; then
    echo "JDK 17 is required (java was not found)." >&2
    exit 2
fi

java_major="$(java -version 2>&1 | sed -n '1s/.*version "\([0-9][0-9]*\).*/\1/p')"
if [ "$java_major" != "17" ]; then
    echo "JDK 17 is required (found major version ${java_major:-unknown})." >&2
    exit 2
fi

if [ -z "${ANDROID_HOME:-}" ] && [ -z "${ANDROID_SDK_ROOT:-}" ]; then
    echo "ANDROID_HOME or ANDROID_SDK_ROOT must point to an SDK containing API 36." >&2
    exit 2
fi

expected_wrapper="7d3a4ac4de1c32b59bc6a4eb8ecb8e612ccd0cf1ae1e99f66902da64df296172"
actual_wrapper="$(shasum -a 256 gradle/wrapper/gradle-wrapper.jar | awk '{print $1}')"
if [ "$actual_wrapper" != "$expected_wrapper" ]; then
    echo "Gradle wrapper JAR checksum mismatch." >&2
    exit 3
fi

exec ./gradlew --no-daemon \
    :testDebugUnitTest :lintDebug :assembleDebug \
    :app:testDebugUnitTest :app:lintDebug :app:assembleDebug "$@"
