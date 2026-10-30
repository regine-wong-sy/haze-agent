import threading
import time

class TTLCache:
    """Remembers values for `ttl` seconds. After that they are only handed out as "stale",
    until `max_stale` seconds have passed, so a caller can use them as a last resort."""
    def __init__(self, ttl, max_stale, clock=time.monotonic):
        self.ttl = ttl
        self.max_stale = max_stale
        self.clock = clock
        self._items = {}  #key -> (stored_at, value)
        self._lock = threading.Lock()

    def put(self, key, value):
        with self._lock:
            self._items[key] = (self.clock(), value)

    def get_fresh(self, key):
        return self._get(key, self.ttl)

    def get_stale(self, key):
        return self._get(key, self.max_stale)

    def _get(self, key, max_age):
        with self._lock:
            item = self._items.get(key)
        if item is None or self.clock() - item[0] > max_age:
            return None
        return item[1]

    def clear(self):
        with self._lock:
            self._items.clear()


class CircuitBreaker:
    """Stops calling a dependency that keeps failing. After `failures` failures in a row the
    breaker is open and allow() is False for `cooldown` seconds; then one call is let through
    to test it. If that call fails the breaker opens again, if it works the breaker closes."""
    def __init__(self, failures=2, cooldown=60, clock=time.monotonic):
        self.failures = failures
        self.cooldown = cooldown
        self.clock = clock
        self._failed = 0
        self._opened_at = 0.0
        self._lock = threading.Lock()

    def allow(self):
        with self._lock:
            if self._failed < self.failures:
                return True
            return self.clock() - self._opened_at >= self.cooldown

    def success(self):
        with self._lock:
            self._failed = 0

    def failure(self):
        with self._lock:
            self._failed += 1
            if self._failed >= self.failures:
                self._opened_at = self.clock()

    @property
    def state(self):
        with self._lock:
            return "closed" if self._failed < self.failures else "open"
