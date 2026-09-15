import mimetypes
import os


UPLOAD_SIZE_LIMITS = {
    "image": 15 * 1024 * 1024,
    "video": 80 * 1024 * 1024,
    "audio": 25 * 1024 * 1024,
    "document": 10 * 1024 * 1024,
}

ALLOWED_MIME_TYPES = {
    "image/jpeg", "image/png", "image/gif", "image/webp",
    "video/mp4", "video/webm", "video/quicktime",
    "audio/mpeg", "audio/mp4", "audio/wav", "audio/ogg", "audio/webm",
    "application/pdf", "text/plain",
}


def _size_limit(mime_type, limits):
    if mime_type.startswith("image/"):
        return limits["image"]
    if mime_type.startswith("video/"):
        return limits["video"]
    if mime_type.startswith("audio/"):
        return limits["audio"]
    return limits["document"]


def allowed_mime_type(uploaded_file, limits=None):
    limits = limits or UPLOAD_SIZE_LIMITS
    declared_type = str(getattr(uploaded_file, "mimetype", "") or "").split(";", 1)[0].lower()
    guessed_type, _ = mimetypes.guess_type(uploaded_file.filename)
    mime_type = declared_type if declared_type in ALLOWED_MIME_TYPES else guessed_type
    if mime_type not in ALLOWED_MIME_TYPES:
        return False

    try:
        current_position = uploaded_file.stream.tell()
        uploaded_file.stream.seek(0, os.SEEK_END)
        file_size = uploaded_file.stream.tell()
        uploaded_file.stream.seek(0)
        header = uploaded_file.stream.read(64)
        uploaded_file.stream.seek(current_position)
    except (AttributeError, OSError, TypeError, ValueError):
        return False

    if file_size <= 0 or file_size > _size_limit(mime_type, limits):
        return False
    if mime_type == "image/jpeg":
        return header.startswith(b"\xff\xd8\xff")
    if mime_type == "image/png":
        return header.startswith(b"\x89PNG\r\n\x1a\n")
    if mime_type == "image/gif":
        return header.startswith((b"GIF87a", b"GIF89a"))
    if mime_type == "image/webp":
        return header.startswith(b"RIFF") and header[8:12] == b"WEBP"
    if mime_type in {"video/mp4", "video/quicktime", "audio/mp4"}:
        return b"ftyp" in header[:32]
    if mime_type in {"video/webm", "audio/webm"}:
        return header.startswith(b"\x1a\x45\xdf\xa3")
    if mime_type == "audio/mpeg":
        return header.startswith(b"ID3") or (
            len(header) >= 2 and header[0] == 0xFF and (header[1] & 0xE0) == 0xE0
        )
    if mime_type == "audio/wav":
        return header.startswith(b"RIFF") and header[8:12] == b"WAVE"
    if mime_type == "audio/ogg":
        return header.startswith(b"OggS")
    if mime_type == "application/pdf":
        return header.startswith(b"%PDF-")
    if mime_type == "text/plain":
        if b"\x00" in header:
            return False
        try:
            header.decode("utf-8")
            return True
        except UnicodeDecodeError:
            return False
    return False
