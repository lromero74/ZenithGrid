"""Bounded, privacy-safe request and browser startup timing aggregation."""

import math
import threading
from collections import defaultdict, deque


_MAX_SAMPLES = 500
_server_samples: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=_MAX_SAMPLES))
_client_samples: dict[str, deque[float]] = defaultdict(lambda: deque(maxlen=_MAX_SAMPLES))
_lock = threading.Lock()


def _percentile(values: list[float], percentile: float) -> float:
    if not values:
        return 0.0
    ordered = sorted(values)
    index = max(0, math.ceil(percentile * len(ordered)) - 1)
    return round(ordered[index], 1)


def record_server_timing(method: str, route: str, duration_ms: float) -> None:
    """Record a bounded server sample without user, account, or query data."""
    key = f"{method.upper()} {route}"
    with _lock:
        _server_samples[key].append(float(duration_ms))


def record_client_timings(route: str, timings: dict[str, float]) -> None:
    """Record browser startup measures keyed only by route and metric name."""
    safe_route = route if route.startswith("/") and len(route) <= 80 else "/unknown"
    with _lock:
        for name, duration in timings.items():
            if not name.startswith("zenith:bootstrap-to-") or len(name) > 120:
                continue
            if 0 <= duration <= 120_000:
                _client_samples[f"{safe_route} {name}"].append(float(duration))


def _summarize(samples: dict[str, deque[float]]) -> dict[str, dict]:
    return {
        key: {
            "count": len(values),
            "p50_ms": _percentile(list(values), 0.50),
            "p95_ms": _percentile(list(values), 0.95),
            "max_ms": round(max(values), 1),
        }
        for key, values in sorted(samples.items())
        if values
    }


def get_performance_snapshot() -> dict:
    """Return aggregate percentiles; raw samples and identities never leave memory."""
    with _lock:
        return {
            "server": _summarize(_server_samples),
            "client": _summarize(_client_samples),
        }


def clear_performance_samples() -> None:
    """Clear in-memory samples (used by tests and operational resets)."""
    with _lock:
        _server_samples.clear()
        _client_samples.clear()
