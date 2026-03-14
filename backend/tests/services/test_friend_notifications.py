"""
Tests for friend notification broadcasts (online presence, request accepted).
"""

import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from app.models import User
from app.models.social import Friendship
from app.services.friend_notifications import (
    broadcast_friend_online,
    notify_friend_request_accepted,
)


@pytest.fixture
async def two_friends(db_session):
    """Create two users who are friends."""
    user_a = User(id=1, email="a@test.com", display_name="Alice", hashed_password="x", is_active=True)
    user_b = User(id=2, email="b@test.com", display_name="Bob", hashed_password="x", is_active=True)
    db_session.add_all([user_a, user_b])
    # Bidirectional friendship
    db_session.add(Friendship(user_id=1, friend_id=2))
    db_session.add(Friendship(user_id=2, friend_id=1))
    await db_session.commit()
    return user_a, user_b


@pytest.fixture
def mock_ws_manager():
    """Mock WebSocket manager with controllable online users."""
    mgr = AsyncMock()
    mgr.get_connected_user_ids = MagicMock(return_value=set())
    mgr.send_to_user = AsyncMock()
    return mgr


# ── broadcast_friend_online ──────────────────────────────────────────


class TestBroadcastFriendOnline:
    """Tests for the friend online notification broadcast."""

    @pytest.mark.asyncio
    async def test_notifies_online_friend(self, db_session, two_friends, mock_ws_manager):
        """When Alice comes online and Bob is connected, Bob gets notified."""
        mock_ws_manager.get_connected_user_ids.return_value = {2}  # Bob is online

        await broadcast_friend_online(mock_ws_manager, db_session, user_id=1)

        mock_ws_manager.send_to_user.assert_called_once_with(2, {
            "type": "friend:online",
            "user_id": 1,
            "display_name": "Alice",
        })

    @pytest.mark.asyncio
    async def test_skips_offline_friends(self, db_session, two_friends, mock_ws_manager):
        """When Alice comes online but Bob is offline, no notification sent."""
        mock_ws_manager.get_connected_user_ids.return_value = set()  # Nobody online

        await broadcast_friend_online(mock_ws_manager, db_session, user_id=1)

        mock_ws_manager.send_to_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_non_friends(self, db_session, two_friends, mock_ws_manager):
        """Online users who are NOT friends don't get notified."""
        # User 3 is online but not a friend of user 1
        mock_ws_manager.get_connected_user_ids.return_value = {3}

        await broadcast_friend_online(mock_ws_manager, db_session, user_id=1)

        mock_ws_manager.send_to_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_no_friends_at_all(self, db_session, mock_ws_manager):
        """User with no friends — no crash, no notifications."""
        user = User(id=10, email="lonely@test.com", display_name="Lonely", hashed_password="x", is_active=True)
        db_session.add(user)
        await db_session.commit()

        mock_ws_manager.get_connected_user_ids.return_value = {10}

        await broadcast_friend_online(mock_ws_manager, db_session, user_id=10)

        mock_ws_manager.send_to_user.assert_not_called()

    @pytest.mark.asyncio
    async def test_multiple_online_friends(self, db_session, mock_ws_manager):
        """Notifies all online friends, not just one."""
        user_a = User(id=1, email="a@test.com", display_name="Alice", hashed_password="x", is_active=True)
        user_b = User(id=2, email="b@test.com", display_name="Bob", hashed_password="x", is_active=True)
        user_c = User(id=3, email="c@test.com", display_name="Carol", hashed_password="x", is_active=True)
        db_session.add_all([user_a, user_b, user_c])
        db_session.add(Friendship(user_id=1, friend_id=2))
        db_session.add(Friendship(user_id=2, friend_id=1))
        db_session.add(Friendship(user_id=1, friend_id=3))
        db_session.add(Friendship(user_id=3, friend_id=1))
        await db_session.commit()

        mock_ws_manager.get_connected_user_ids.return_value = {2, 3}

        await broadcast_friend_online(mock_ws_manager, db_session, user_id=1)

        assert mock_ws_manager.send_to_user.call_count == 2
        notified_ids = {call.args[0] for call in mock_ws_manager.send_to_user.call_args_list}
        assert notified_ids == {2, 3}

    @pytest.mark.asyncio
    async def test_send_failure_does_not_crash(self, db_session, two_friends, mock_ws_manager):
        """If sending to a friend fails, it doesn't propagate."""
        mock_ws_manager.get_connected_user_ids.return_value = {2}
        mock_ws_manager.send_to_user.side_effect = Exception("connection lost")

        # Should not raise
        await broadcast_friend_online(mock_ws_manager, db_session, user_id=1)


# ── notify_friend_request_accepted ───────────────────────────────────


class TestNotifyFriendRequestAccepted:
    """Tests for the friend request accepted notification."""

    @pytest.mark.asyncio
    async def test_notifies_requester(self, db_session, mock_ws_manager):
        """When Bob accepts Alice's request, Alice gets notified."""
        bob = User(id=5, email="bob@test.com", display_name="Bob", hashed_password="x", is_active=True)
        db_session.add(bob)
        await db_session.commit()

        await notify_friend_request_accepted(mock_ws_manager, db_session, acceptor_id=5, requester_id=3)

        mock_ws_manager.send_to_user.assert_called_once_with(3, {
            "type": "friend:request_accepted",
            "user_id": 5,
            "display_name": "Bob",
        })

    @pytest.mark.asyncio
    async def test_fallback_display_name(self, db_session, mock_ws_manager):
        """If acceptor has no display_name, uses 'Player {id}' fallback."""
        user = User(id=7, email="noname@test.com", display_name=None, hashed_password="x", is_active=True)
        db_session.add(user)
        await db_session.commit()

        await notify_friend_request_accepted(mock_ws_manager, db_session, acceptor_id=7, requester_id=1)

        msg = mock_ws_manager.send_to_user.call_args[0][1]
        assert msg["display_name"] == "Player 7"

    @pytest.mark.asyncio
    async def test_send_failure_does_not_crash(self, db_session, mock_ws_manager):
        """If requester is offline and send fails, no crash."""
        user = User(id=8, email="x@test.com", display_name="X", hashed_password="x", is_active=True)
        db_session.add(user)
        await db_session.commit()

        mock_ws_manager.send_to_user.side_effect = Exception("not connected")

        # Should not raise
        await notify_friend_request_accepted(mock_ws_manager, db_session, acceptor_id=8, requester_id=99)
