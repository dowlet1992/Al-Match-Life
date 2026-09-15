import importlib.util
import json
import os
import secrets
import tempfile
import threading
import urllib.error
import urllib.request
from abc import ABC, abstractmethod


class SpeechProvider(ABC):
    @property
    @abstractmethod
    def name(self):
        raise NotImplementedError

    @abstractmethod
    def is_available(self):
        raise NotImplementedError

    @abstractmethod
    def transcribe(self, audio_bytes, filename, content_type, language=""):
        raise NotImplementedError


class FasterWhisperProvider(SpeechProvider):
    _models = {}
    _model_lock = threading.RLock()

    def __init__(self, environ=None):
        self.environ = os.environ if environ is None else environ
        self.model_name = str(self.environ.get("WHISPER_MODEL", "base")).strip() or "base"
        self.device = str(self.environ.get("WHISPER_DEVICE", "auto")).strip() or "auto"
        self.compute_type = str(self.environ.get("WHISPER_COMPUTE_TYPE", "int8")).strip() or "int8"

    @property
    def name(self):
        return "faster-whisper"

    def is_available(self):
        return importlib.util.find_spec("faster_whisper") is not None

    def _model(self):
        if not self.is_available():
            raise RuntimeError("faster-whisper is not installed")
        cache_key = (self.model_name, self.device, self.compute_type)
        with self._model_lock:
            model = self._models.get(cache_key)
            if model is None:
                from faster_whisper import WhisperModel
                model = WhisperModel(self.model_name, device=self.device, compute_type=self.compute_type)
                self._models[cache_key] = model
            return model

    def transcribe(self, audio_bytes, filename, content_type, language=""):
        suffix = os.path.splitext(filename)[1] or ".audio"
        temporary_path = ""
        try:
            with tempfile.NamedTemporaryFile(prefix="aml-speech-", suffix=suffix, delete=False) as handle:
                handle.write(audio_bytes)
                temporary_path = handle.name
            segments, info = self._model().transcribe(
                temporary_path,
                language=language if language and language != "unknown" else None,
                vad_filter=True,
            )
            text = " ".join(str(segment.text).strip() for segment in segments if str(segment.text).strip()).strip()
            detected = str(getattr(info, "language", "") or "").strip().lower()
            return {"ok": True, "text": text, "model": self.model_name, "detected_language": detected} if text else {
                "ok": False, "error": "empty_transcription",
            }
        finally:
            if temporary_path:
                try:
                    os.unlink(temporary_path)
                except OSError:
                    pass


class OpenAISpeechProvider(SpeechProvider):
    def __init__(self, environ=None, urlopen=None):
        self.environ = os.environ if environ is None else environ
        self.urlopen = urlopen or urllib.request.urlopen
        self.api_key = str(self.environ.get("OPENAI_API_KEY", "")).strip()
        self.model_name = str(self.environ.get("OPENAI_TRANSCRIPTION_MODEL", "gpt-4o-mini-transcribe")).strip()

    @property
    def name(self):
        return "openai"

    def is_available(self):
        return bool(self.api_key)

    @staticmethod
    def _multipart_body(fields, filename, content_type, audio_bytes):
        boundary = "----AIMatchLife" + secrets.token_hex(16)
        chunks = []
        for name, value in fields.items():
            chunks.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="{name}"\r\n\r\n'.encode(), str(value).encode("utf-8"), b"\r\n"])
        chunks.extend([f"--{boundary}\r\n".encode(), f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode(), f"Content-Type: {content_type}\r\n\r\n".encode(), audio_bytes, b"\r\n", f"--{boundary}--\r\n".encode()])
        return boundary, b"".join(chunks)

    def transcribe(self, audio_bytes, filename, content_type, language=""):
        fields = {"model": self.model_name, "response_format": "json"}
        if language and language != "unknown":
            fields["language"] = language
        boundary, body = self._multipart_body(fields, filename, content_type, audio_bytes)
        request = urllib.request.Request(
            "https://api.openai.com/v1/audio/transcriptions", data=body,
            headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": f"multipart/form-data; boundary={boundary}"}, method="POST",
        )
        try:
            with self.urlopen(request, timeout=30) as response:
                payload = json.loads(response.read().decode("utf-8"))
            text = str(payload.get("text", "")).strip() if isinstance(payload, dict) else ""
            detected = str(payload.get("language", "")).strip().lower() if isinstance(payload, dict) else ""
            return {"ok": True, "text": text, "model": self.model_name, "detected_language": detected} if text else {"ok": False, "error": "empty_transcription"}
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, KeyError):
            return {"ok": False, "error": "transcription_provider_failed"}


def get_speech_provider(environ=None, urlopen=None):
    environ = os.environ if environ is None else environ
    provider_name = str(environ.get("SPEECH_PROVIDER", "faster-whisper")).strip().lower()
    if provider_name in {"faster-whisper", "whisper", "local"}:
        return FasterWhisperProvider(environ)
    if provider_name == "openai":
        return OpenAISpeechProvider(environ, urlopen=urlopen)
    raise ValueError(f"Unsupported SPEECH_PROVIDER: {provider_name}")


def speech_provider_status(environ=None):
    try:
        provider = get_speech_provider(environ)
        return {"enabled": provider.is_available(), "provider": provider.name}
    except (TypeError, ValueError):
        return {"enabled": False, "provider": "invalid"}
