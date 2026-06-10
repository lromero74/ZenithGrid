"""Time helpers.

`datetime.utcnow()` is deprecated as of Python 3.12. `utcnow()` is a drop-in
replacement that returns the SAME value it always did — a *naive* UTC timestamp
— using the non-deprecated timezone-aware API.

Naive UTC is preserved deliberately: the ORM models and the comparisons spread
throughout this codebase assume naive UTC datetimes. Returning an aware datetime
here would raise "can't compare offset-naive and offset-aware datetimes" at
runtime. Anywhere you would have written ``datetime.utcnow()`` (or passed
``datetime.utcnow`` as a callable default), use ``utcnow`` instead.
"""

from datetime import datetime, timezone


def utcnow() -> datetime:
    """Return the current UTC time as a naive ``datetime`` (tzinfo stripped)."""
    return datetime.now(timezone.utc).replace(tzinfo=None)


def utcfromtimestamp(ts: float) -> datetime:
    """Naive UTC ``datetime`` from a POSIX timestamp.

    Drop-in for the deprecated ``datetime.utcfromtimestamp(ts)`` — same naive
    UTC value, using the non-deprecated timezone-aware API.
    """
    return datetime.fromtimestamp(ts, timezone.utc).replace(tzinfo=None)
