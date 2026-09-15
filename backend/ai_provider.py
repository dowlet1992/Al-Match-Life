import json
import os
import urllib.error
import urllib.parse
import urllib.request
from abc import ABC, abstractmethod


class AIProviderError(RuntimeError):
    pass


class AIProvider(ABC):
    @property
    @abstractmethod
    def name(self):
        raise NotImplementedError

    @property
    @abstractmethod
    def model(self):
        raise NotImplementedError

    @abstractmethod
    def is_available(self):
        raise NotImplementedError

    @abstractmethod
    def chat(self, messages, temperature=0.2, max_tokens=900):
        raise NotImplementedError


class OllamaProvider(AIProvider):
    def __init__(self, base_url=None, model=None, timeout=None):
        self.base_url = (base_url or os.environ.get("OLLAMA_BASE_URL", "http://127.0.0.1:11434")).rstrip("/")
        self._model = model or os.environ.get("OLLAMA_MODEL", "qwen2.5:7b")
        self.timeout = int(timeout or os.environ.get("OLLAMA_TIMEOUT_SECONDS", "90"))
        self._validate_endpoint()

    @property
    def name(self):
        return "ollama"

    @property
    def model(self):
        return self._model

    def _validate_endpoint(self):
        parsed = urllib.parse.urlsplit(self.base_url)
        local_hosts = {"127.0.0.1", "localhost", "::1"}
        allow_remote = os.environ.get("ALLOW_REMOTE_AI_PROVIDER", "").strip().lower() in {"1", "true", "yes"}
        if parsed.scheme not in {"http", "https"} or not parsed.hostname:
            raise ValueError("OLLAMA_BASE_URL must be an HTTP(S) URL")
        if not allow_remote and parsed.hostname.lower() not in local_hosts:
            raise ValueError("Remote Ollama endpoints require ALLOW_REMOTE_AI_PROVIDER=1")

    def is_available(self):
        request = urllib.request.Request(f"{self.base_url}/api/tags", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=min(self.timeout, 3)) as response:
                return 200 <= response.status < 300
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
            return False

    def chat(self, messages, temperature=0.2, max_tokens=900):
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": float(temperature),
                "num_predict": int(max_tokens),
                "num_ctx": int(os.environ.get("OLLAMA_CONTEXT_TOKENS", "4096")),
                "repeat_penalty": 1.12,
            },
            "keep_alive": os.environ.get("OLLAMA_KEEP_ALIVE", "15m"),
        }
        request = urllib.request.Request(
            f"{self.base_url}/api/chat",
            data=json.dumps(payload, ensure_ascii=False).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=self.timeout) as response:
                result = json.loads(response.read().decode("utf-8"))
        except (OSError, urllib.error.URLError, urllib.error.HTTPError, TimeoutError, json.JSONDecodeError) as error:
            raise AIProviderError(f"Ollama request failed: {error}") from error

        content = result.get("message", {}).get("content", "")
        if not isinstance(content, str):
            raise AIProviderError("Ollama returned an invalid response")
        return content.strip()


def get_ai_provider(environ=None):
    environ = os.environ if environ is None else environ
    provider_name = str(environ.get("AI_PROVIDER", "ollama")).strip().lower()
    if provider_name == "ollama":
        return OllamaProvider(
            base_url=environ.get("OLLAMA_BASE_URL"),
            model=environ.get("OLLAMA_MODEL"),
            timeout=environ.get("OLLAMA_TIMEOUT_SECONDS"),
        )
    raise ValueError(f"Unsupported AI_PROVIDER: {provider_name}")


def provider_status(environ=None, check_connection=False):
    try:
        provider = get_ai_provider(environ)
    except (TypeError, ValueError) as error:
        return {"enabled": False, "provider": "invalid", "model": "", "error": str(error)}
    return {
        "enabled": provider.is_available() if check_connection else True,
        "provider": provider.name,
        "model": provider.model,
        "error": "",
    }
