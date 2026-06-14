"""Shared async-session-maker injection for class-based monitors/services.

Monitors that may run on a secondary event loop accept an injected async
session maker (one bound to that loop's engine) and fall back to the
application default when none is injected. This single source of truth
replaces the per-monitor ``set_session_maker`` / ``_get_sm`` copies.
"""


class SessionMakerMixin:
    """Provides ``set_session_maker()`` / ``_get_sm()`` for monitor-style classes.

    The injected maker defaults to ``None`` via this class attribute, so
    subclasses don't need to initialise ``self._session_maker`` themselves.
    """

    _session_maker = None

    def set_session_maker(self, sm):
        """Inject a session maker (used when running on the secondary event loop)."""
        self._session_maker = sm

    def _get_sm(self):
        """Return the injected session maker, falling back to the default."""
        from app.database import async_session_maker
        return self._session_maker or async_session_maker
