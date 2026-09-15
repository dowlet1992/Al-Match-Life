from collections import OrderedDict
from threading import RLock
from time import monotonic


class MediaAccessCache:
    """Short-lived positive authorization cache for bursty media Range requests."""

    def __init__(self, ttl_seconds=2.0, max_entries=4096, clock=None):
        self.ttl_seconds = max(float(ttl_seconds), 0.1)
        self.max_entries = max(int(max_entries), 1)
        self.clock = clock or monotonic
        self._entries = OrderedDict()
        self._lock = RLock()

    def allows(self, viewer_email, filename):
        key = (str(viewer_email or ""), str(filename or ""))
        now = self.clock()
        with self._lock:
            expires_at = self._entries.get(key)
            if expires_at is None:
                return False
            if expires_at <= now:
                self._entries.pop(key, None)
                return False
            self._entries.move_to_end(key)
            return True

    def remember_allowed(self, viewer_email, filename):
        key = (str(viewer_email or ""), str(filename or ""))
        with self._lock:
            self._entries[key] = self.clock() + self.ttl_seconds
            self._entries.move_to_end(key)
            while len(self._entries) > self.max_entries:
                self._entries.popitem(last=False)

    def clear(self):
        with self._lock:
            self._entries.clear()
