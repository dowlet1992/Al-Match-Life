#!/bin/sh
set -eu

revision="e3000c87329bf7cfe1f345bf566c482a402d0d62"

if [ "$(uname -s)" != "Linux" ]; then
    echo "Official WebRTC Android builds require a Linux host." >&2
    echo "Use the manual android-webrtc workflow or run this script on Linux." >&2
    exit 5
fi

if [ "$#" -ne 2 ]; then
    echo "Usage: $0 /absolute/path/to/webrtc/src /absolute/output/directory" >&2
    exit 2
fi

source_dir="$1"
output_dir="$2"
case "$source_dir:$output_dir" in
    /*:/*) ;;
    *) echo "Both paths must be absolute." >&2; exit 2 ;;
esac

if [ ! -d "$source_dir/.git" ] || [ ! -f "$source_dir/tools_webrtc/android/build_aar.py" ] ||
        [ ! -s "$source_dir/LICENSE" ]; then
    echo "The source path is not an official WebRTC src checkout." >&2
    exit 2
fi

actual_revision="$(git -C "$source_dir" rev-parse HEAD)"
if [ "$actual_revision" != "$revision" ]; then
    echo "WebRTC revision mismatch: expected $revision, found $actual_revision" >&2
    exit 3
fi
if ! git -C "$source_dir" diff --quiet || ! git -C "$source_dir" diff --cached --quiet; then
    echo "WebRTC checkout must be clean." >&2
    exit 3
fi

mkdir -p "$output_dir"
artifact="$output_dir/libwebrtc-$revision.aar"
(
    # depot_tools resolves the checked-in GN binary relative to the active
    # gclient solution. Running from an arbitrary caller directory can make
    # its wrapper resolve itself recursively instead.
    cd "$source_dir"
    python3 tools_webrtc/android/build_aar.py \
        --output "$artifact" \
        --arch arm64-v8a x86_64
)
shasum -a 256 "$artifact" > "$artifact.sha256"

license_file="$output_dir/LICENSE.md"
# build_aar.py emits only the binary. Preserve the exact upstream license from
# the pinned checkout beside the AAR so the reviewed distribution is complete.
cp "$source_dir/LICENSE" "$license_file"
shasum -a 256 "$license_file" > "$license_file.sha256"

echo "Built $artifact"
echo "Use its recorded digest with -PwebrtcAar and -PwebrtcSha256."
