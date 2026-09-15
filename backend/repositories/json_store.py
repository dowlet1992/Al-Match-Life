import copy
import json
import os
import tempfile
import threading
from collections import OrderedDict

from backend.data_encryption import decrypt_bytes, encrypt_bytes


class JsonStore:
    _cache = OrderedDict()
    _lock = threading.RLock()
    _max_cache_entries = 128

    def __init__(self, path, default):
        self.path = os.path.abspath(os.fspath(path))
        self.default = default

    @classmethod
    def _remember(cls, path, signature, data):
        cls._cache[path] = (signature, copy.deepcopy(data))
        cls._cache.move_to_end(path)
        while len(cls._cache) > cls._max_cache_entries:
            cls._cache.popitem(last=False)

    @staticmethod
    def _signature(path):
        stat = os.stat(path)
        return stat.st_mtime_ns, stat.st_size

    @classmethod
    def clear_cache(cls):
        with cls._lock:
            cls._cache.clear()

    def load(self):
        with self._lock:
            try:
                signature = self._signature(self.path)
                cached = self._cache.get(self.path)
                if cached and cached[0] == signature:
                    self._cache.move_to_end(self.path)
                    return copy.deepcopy(cached[1])
                with open(self.path, "rb") as file:
                    payload = decrypt_bytes(file.read())
                data = json.loads(payload.decode("utf-8"))
                self._remember(self.path, signature, data)
                return copy.deepcopy(data)
            except (FileNotFoundError, json.JSONDecodeError, OSError):
                self._cache.pop(self.path, None)
                return copy.deepcopy(self.default)

    def save(self, data):
        with self._lock:
            self._save_locked(data)

    def _save_locked(self, data):
        directory = os.path.dirname(self.path)
        if directory:
            os.makedirs(directory, exist_ok=True)

        target_directory = directory or "."
        fd, temp_path = tempfile.mkstemp(
            prefix=".tmp-",
            suffix=".json",
            dir=target_directory,
        )

        try:
            serialized = json.dumps(data, ensure_ascii=False, separators=(",", ":")).encode("utf-8") + b"\n"
            payload = encrypt_bytes(serialized)
            with os.fdopen(fd, "wb") as file:
                file.write(payload)
                file.flush()
                os.fsync(file.fileno())
            os.replace(temp_path, self.path)
            self._remember(self.path, self._signature(self.path), data)
        except Exception:
            self._cache.pop(self.path, None)
            try:
                os.unlink(temp_path)
            except OSError:
                pass
            raise
