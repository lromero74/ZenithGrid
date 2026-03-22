"""Social models: friendships, friend requests, blocked users, game results, tournaments, chat."""

from datetime import datetime

from sqlalchemy import (
    Boolean,
    Column,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    UniqueConstraint,
)
from sqlalchemy.orm import relationship

from app.database import Base


class Friendship(Base):
    """
    Bidirectional friend relationship.

    Stored as two rows per friendship: (A→B) and (B→A).
    Created when recipient accepts a friend request.
    """
    __tablename__ = "friendships"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    friend_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    user = relationship("User", foreign_keys=[user_id])
    friend = relationship("User", foreign_keys=[friend_id])

    __table_args__ = (
        UniqueConstraint("user_id", "friend_id", name="uq_friendship"),
        {'schema': 'social'},
    )


class FriendRequest(Base):
    """Pending friend request. Deleted on accept or reject."""
    __tablename__ = "friend_requests"

    id = Column(Integer, primary_key=True, index=True)
    from_user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    to_user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    from_user = relationship("User", foreign_keys=[from_user_id])
    to_user = relationship("User", foreign_keys=[to_user_id])

    __table_args__ = (
        UniqueConstraint("from_user_id", "to_user_id", name="uq_friend_request"),
        {'schema': 'social'},
    )


class BlockedUser(Base):
    """User A blocks user B. Prevents friend requests from B to A."""
    __tablename__ = "blocked_users"

    id = Column(Integer, primary_key=True, index=True)
    blocker_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    blocked_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    blocker = relationship("User", foreign_keys=[blocker_id])
    blocked = relationship("User", foreign_keys=[blocked_id])

    __table_args__ = (
        UniqueConstraint("blocker_id", "blocked_id", name="uq_blocked_user"),
        {'schema': 'social'},
    )


class GameResult(Base):
    """Persistent record of a completed multiplayer game."""
    __tablename__ = "game_results"
    __table_args__ = {'schema': 'social'}

    id = Column(Integer, primary_key=True, index=True)
    room_id = Column(String, nullable=False, index=True)
    game_id = Column(String, nullable=False, index=True)
    mode = Column(String, nullable=False)  # "vs", "race"
    started_at = Column(DateTime, nullable=False)
    finished_at = Column(DateTime, default=datetime.utcnow)
    result_data = Column(JSON, nullable=True)
    tournament_id = Column(Integer, ForeignKey("tournaments.id"), nullable=True)

    players = relationship("GameResultPlayer", back_populates="game_result", cascade="all, delete-orphan")


class GameResultPlayer(Base):
    """Per-player result within a game."""
    __tablename__ = "game_result_players"
    __table_args__ = {'schema': 'social'}

    id = Column(Integer, primary_key=True, index=True)
    game_result_id = Column(
        Integer, ForeignKey("game_results.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("auth.users.id"), nullable=False, index=True)
    placement = Column(Integer, nullable=True)
    score = Column(Integer, nullable=True)
    is_winner = Column(Boolean, default=False)
    stats = Column(JSON, nullable=True)

    game_result = relationship("GameResult", back_populates="players")
    user = relationship("User", foreign_keys=[user_id])


class GameHistoryVisibility(Base):
    """Per-user privacy control for game history sharing."""
    __tablename__ = "game_history_visibility"
    __table_args__ = {'schema': 'social'}

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, unique=True)
    default_visibility = Column(String, default="all_friends")  # "all_friends", "opponents_only", "private"
    game_overrides = Column(JSON, nullable=True)

    user = relationship("User", foreign_keys=[user_id])


class GameHighScore(Base):
    """Per-user best score for each game, with score type support."""
    __tablename__ = "game_high_scores"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    game_id = Column(String, nullable=False)
    score = Column(Integer, nullable=False, default=0)
    score_type = Column(String(20), nullable=False, default="high_score")
    difficulty = Column(String(20), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint('user_id', 'game_id', 'score_type', name='uq_user_game_score_type'),
        {'schema': 'social'},
    )

    user = relationship("User", foreign_keys=[user_id])


class Tournament(Base):
    """Multi-game tournament among friends."""
    __tablename__ = "tournaments"
    __table_args__ = {'schema': 'social'}

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, nullable=False)
    creator_id = Column(Integer, ForeignKey("auth.users.id"), nullable=False, index=True)
    game_ids = Column(JSON, nullable=False)
    config = Column(JSON, nullable=True)
    status = Column(String, default="pending")  # "pending", "active", "completed"
    created_at = Column(DateTime, default=datetime.utcnow)
    started_at = Column(DateTime, nullable=True)
    finished_at = Column(DateTime, nullable=True)

    creator = relationship("User", foreign_keys=[creator_id])
    players = relationship("TournamentPlayer", back_populates="tournament", cascade="all, delete-orphan")
    game_results = relationship("GameResult", backref="tournament")


class TournamentPlayer(Base):
    """Player enrolled in a tournament."""
    __tablename__ = "tournament_players"

    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(
        Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("auth.users.id"), nullable=False, index=True)
    total_score = Column(Integer, default=0)
    placement = Column(Integer, nullable=True)
    archived = Column(Boolean, default=False)
    joined_at = Column(DateTime, default=datetime.utcnow)

    tournament = relationship("Tournament", back_populates="players")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("tournament_id", "user_id", name="uq_tournament_player"),
        {'schema': 'social'},
    )


class TournamentDeleteVote(Base):
    """Committee vote for tournament deletion. All players must vote to delete."""
    __tablename__ = "tournament_delete_votes"

    id = Column(Integer, primary_key=True, index=True)
    tournament_id = Column(
        Integer, ForeignKey("tournaments.id", ondelete="CASCADE"), nullable=False, index=True
    )
    user_id = Column(Integer, ForeignKey("auth.users.id"), nullable=False, index=True)
    voted_at = Column(DateTime, default=datetime.utcnow)

    __table_args__ = (
        UniqueConstraint("tournament_id", "user_id", name="uq_tournament_delete_vote"),
        {'schema': 'social'},
    )


# ---------- Chat ----------


class ChatChannel(Base):
    """Chat channel: DM (2 users), group (N users), or channel (open/admin-created)."""
    __tablename__ = "chat_channels"
    __table_args__ = {'schema': 'social'}

    id = Column(Integer, primary_key=True, index=True)
    type = Column(String, nullable=False)  # "dm", "group", "channel"
    name = Column(String, nullable=True)   # null for DMs, required for group/channel
    created_by = Column(Integer, ForeignKey("auth.users.id"), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)

    creator = relationship("User", foreign_keys=[created_by])
    members = relationship("ChatChannelMember", back_populates="channel", cascade="all, delete-orphan")
    messages = relationship("ChatMessage", back_populates="channel", cascade="all, delete-orphan")


class ChatChannelMember(Base):
    """Membership in a chat channel with role and read tracking."""
    __tablename__ = "chat_channel_members"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("chat_channels.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False, index=True)
    role = Column(String, default="member")  # "owner", "admin", "member"
    last_read_at = Column(DateTime, nullable=True)
    joined_at = Column(DateTime, default=datetime.utcnow)

    channel = relationship("ChatChannel", back_populates="members")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("channel_id", "user_id", name="uq_chat_channel_member"),
        {'schema': 'social'},
    )


class ChatMessage(Base):
    """A message in a chat channel. Supports edit, soft delete, reply, and pin."""
    __tablename__ = "chat_messages"

    id = Column(Integer, primary_key=True, index=True)
    channel_id = Column(Integer, ForeignKey("chat_channels.id", ondelete="CASCADE"), nullable=False)
    sender_id = Column(Integer, ForeignKey("auth.users.id"), nullable=False)
    content = Column(String(2000), nullable=False)
    media_url = Column(String(500), nullable=True)
    reply_to_id = Column(Integer, ForeignKey("chat_messages.id", ondelete="SET NULL"), nullable=True)
    is_pinned = Column(Boolean, default=False)
    edited_at = Column(DateTime, nullable=True)
    deleted_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    channel = relationship("ChatChannel", back_populates="messages")
    sender = relationship("User", foreign_keys=[sender_id])
    reply_to = relationship("ChatMessage", remote_side="ChatMessage.id", uselist=False)
    reactions = relationship("ChatMessageReaction", back_populates="message", cascade="all, delete-orphan")

    __table_args__ = (
        Index("ix_chat_messages_channel_created", "channel_id", "created_at"),
        {'schema': 'social'},
    )


class ChatMessageReaction(Base):
    """Emoji reaction on a chat message."""
    __tablename__ = "chat_message_reactions"

    id = Column(Integer, primary_key=True, index=True)
    message_id = Column(Integer, ForeignKey("chat_messages.id", ondelete="CASCADE"), nullable=False, index=True)
    user_id = Column(Integer, ForeignKey("auth.users.id", ondelete="CASCADE"), nullable=False)
    emoji = Column(String(32), nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    message = relationship("ChatMessage", back_populates="reactions")
    user = relationship("User", foreign_keys=[user_id])

    __table_args__ = (
        UniqueConstraint("message_id", "user_id", "emoji", name="uq_chat_reaction"),
        {'schema': 'social'},
    )
