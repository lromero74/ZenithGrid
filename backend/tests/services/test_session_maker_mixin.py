"""Tests for the shared SessionMakerMixin.

Verifies the single-source-of-truth session-maker injection used by the
class-based monitors (rebalance, auto-buy, perps, delisted-pair, content).
"""

from app.services.session_maker_mixin import SessionMakerMixin


class _Dummy(SessionMakerMixin):
    """Minimal consumer that does not initialise _session_maker itself."""


class TestSessionMakerMixin:
    def test_injected_session_maker_is_returned(self):
        """Happy path: set_session_maker() value is returned by _get_sm()."""
        mock_sm = object()
        d = _Dummy()
        d.set_session_maker(mock_sm)
        assert d._get_sm() is mock_sm

    def test_falls_back_to_default_when_not_injected(self):
        """Edge case: _get_sm() returns app default when nothing injected."""
        from app.database import async_session_maker

        d = _Dummy()
        assert d._get_sm() is async_session_maker

    def test_default_is_none_without_init(self):
        """Failure-mode guard: a subclass that never sets _session_maker still
        resolves to the default rather than raising AttributeError."""
        d = _Dummy()
        assert d._session_maker is None
        # And re-injecting None continues to fall back, not raise.
        d.set_session_maker(None)
        from app.database import async_session_maker

        assert d._get_sm() is async_session_maker
