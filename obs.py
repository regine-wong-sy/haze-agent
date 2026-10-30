import json
import logging
import sys
import threading
import time
from collections import Counter

#one JSON object per line on stdout, so Render's log search can filter on any field
log = logging.getLogger("haze")
if not log.handlers:
    handler = logging.StreamHandler(sys.stdout)
    handler.setFormatter(logging.Formatter("%(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)
    log.propagate = False

_lock = threading.Lock()
_counts = Counter()
_timings = {}  #name -> {"count", "total", "max"} in seconds
_started = time.time()

def event(name, **fields):
    log.info(json.dumps({"ts": round(time.time(), 3), "event": name, **fields}, default=str))

def count(name, n=1):
    with _lock:
        _counts[name] += n

def observe(name, seconds):
    with _lock:
        t = _timings.setdefault(name, {"count": 0, "total": 0.0, "max": 0.0})
        t["count"] += 1
        t["total"] += seconds
        t["max"] = max(t["max"], seconds)

def snapshot():
    """Counters and timings since this process started (they reset on every deploy or restart)."""
    with _lock:
        timings = {name: {"count": t["count"], "avg_s": round(t["total"] / t["count"], 3), "max_s": round(t["max"], 3)}
                   for name, t in _timings.items()}
        return {"uptime_s": round(time.time() - _started), "counts": dict(_counts), "timings": timings}

def reset():
    """For tests."""
    with _lock:
        _counts.clear()
        _timings.clear()
