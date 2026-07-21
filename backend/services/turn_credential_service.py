import threading
import time


TURN_TOKEN_TTL_SECONDS = 3600
TURN_CACHE_SECONDS = 3000
FALLBACK_ICE_SERVERS = [
    {"urls": "stun:stun.l.google.com:19302"},
    {"urls": "stun:stun1.l.google.com:19302"},
]


class TurnCredentialService:
    def __init__(self, client=None):
        self.client = client
        self._cache = {}
        self._lock = threading.RLock()

    @staticmethod
    def _normalize_servers(servers):
        normalized = []
        for server in servers if isinstance(servers, list) else []:
            if not isinstance(server, dict):
                continue
            urls = server.get("urls")
            url_values = urls if isinstance(urls, list) else [urls]
            url_values = [str(url or "").strip() for url in url_values]
            url_values = [url for url in url_values if url.startswith(("stun:", "turn:", "turns:"))]
            if not url_values:
                continue
            item = {"urls": url_values if isinstance(urls, list) else url_values[0]}
            if any(url.startswith(("turn:", "turns:")) for url in url_values):
                username = str(server.get("username", "") or "").strip()
                credential = str(server.get("credential", "") or "").strip()
                if not username or not credential:
                    continue
                item.update({"username": username, "credential": credential})
            normalized.append(item)
        return normalized

    def get_ice_configuration(self, cache_key, now=None):
        now = float(now if now is not None else time.time())
        cache_key = str(cache_key or "")
        with self._lock:
            cached = self._cache.get(cache_key)
            if cached and float(cached.get("cache_until", 0)) > now:
                return {key: value for key, value in {**cached, "cached": True}.items() if key != "cache_until"}

        if self.client is None:
            return {
                "ice_servers": list(FALLBACK_ICE_SERVERS),
                "provider": "stun_fallback",
                "ttl": 0,
                "expires_at": 0,
                "cached": False,
            }

        try:
            token = self.client.tokens.create(ttl=TURN_TOKEN_TTL_SECONDS)
            ice_servers = self._normalize_servers(getattr(token, "ice_servers", []))
            if not any(
                str(url).startswith(("turn:", "turns:"))
                for server in ice_servers
                for url in (server["urls"] if isinstance(server.get("urls"), list) else [server.get("urls")])
            ):
                raise ValueError("TURN provider returned no relay server")
            result = {
                "ice_servers": ice_servers,
                "provider": "twilio",
                "ttl": TURN_TOKEN_TTL_SECONDS,
                "expires_at": now + TURN_TOKEN_TTL_SECONDS,
                "cached": False,
            }
            with self._lock:
                self._cache[cache_key] = {**result, "cache_until": now + TURN_CACHE_SECONDS}
                if len(self._cache) > 2000:
                    self._cache = {
                        key: value for key, value in self._cache.items()
                        if float(value.get("cache_until", 0)) > now
                    }
            return result
        except Exception:
            return {
                "ice_servers": list(FALLBACK_ICE_SERVERS),
                "provider": "stun_fallback",
                "ttl": 0,
                "expires_at": 0,
                "cached": False,
            }
