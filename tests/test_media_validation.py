from io import BytesIO

from werkzeug.datastructures import FileStorage

from backend.media_validation import allowed_mime_type


def upload(filename, payload):
    return FileStorage(stream=BytesIO(payload), filename=filename)


def test_media_validator_checks_extension_signature_pairs():
    assert allowed_mime_type(upload("photo.png", b"\x89PNG\r\n\x1a\ncontent")) is True
    assert allowed_mime_type(upload("photo.png", b"GIF89a-content")) is False
    assert allowed_mime_type(upload("clip.mp4", b"\x00\x00\x00\x18ftypmp42content")) is True
    assert allowed_mime_type(upload("document.pdf", b"%PDF-1.7\ncontent")) is True
    assert allowed_mime_type(upload("archive.zip", b"PK\x03\x04content")) is False


def test_media_validator_restores_stream_position():
    uploaded_file = upload("photo.jpg", b"\xff\xd8\xffcontent")
    uploaded_file.stream.seek(4)

    assert allowed_mime_type(uploaded_file) is True
    assert uploaded_file.stream.tell() == 4


def test_media_validator_accepts_opus_voice_recording_as_audio_webm():
    voice = FileStorage(
        stream=BytesIO(b"\x1a\x45\xdf\xa3opus-voice"),
        filename="voice-message.webm",
        content_type="audio/webm;codecs=opus",
    )

    assert allowed_mime_type(voice) is True
