"""Channel store — SQLite-backed persistence for vector channels.

Implements PR-003 of the vector roadmap
(docs/roadmap/prs/PR-003-channel-store.md).

Three tables:

- ``channels``    — id, name (unique slug), visibility, type, limits, timestamps
- ``memberships`` — channel_id, member_handle, joined_at
- ``messages``    — id, channel_id, author_handle, body, mentions_json, created_at

A FTS5 virtual table indexes ``messages.body`` for full-text search.

All public APIs are sync (SQLite is sync); async wrappers come in PR-004
when the runtime layer is added.
"""

from __future__ import annotations

import json
import logging
import sqlite3
import time
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Optional
from uuid import uuid4

from .mention import extract_mentions
from .profile import AgentRegistry

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Enums
# ---------------------------------------------------------------------------


class ChannelVisibility(str, Enum):
    OPEN = "open"
    PRIVATE = "private"


class ChannelType(str, Enum):
    STREAM = "stream"
    DM = "dm"
    WORKFLOW = "workflow"


# ---------------------------------------------------------------------------
# Dataclasses
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Channel:
    """A channel record."""

    id: str
    name: str
    visibility: ChannelVisibility
    type: ChannelType
    created_at: float
    member_limit_soft: int = 50
    member_limit_hard: int = 200


@dataclass(frozen=True)
class Membership:
    """A channel membership record."""

    channel_id: str
    member_handle: str
    joined_at: float


@dataclass(frozen=True)
class Message:
    """A message posted to a channel."""

    id: str
    channel_id: str
    author_handle: str
    body: str
    mentions: list = field(default_factory=list)
    created_at: float = 0.0


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class ChannelError(Exception):
    """Base exception for channel store errors."""


class ChannelAlreadyExistsError(ChannelError):
    """A channel with this name already exists."""


class ChannelNotFoundError(ChannelError):
    """No channel with the given id/name."""


class DuplicateMembershipError(ChannelError):
    """The agent is already a member of this channel."""


class NotAMemberError(ChannelError):
    """The handle is not a registered agent profile."""


class NotInChannelError(ChannelError):
    """The agent is not a member of this channel."""


class ChannelTooLargeError(ChannelError):
    """Adding a member would exceed the hard member limit."""


class DmChannelFullError(ChannelError):
    """A DM channel is capped at exactly 2 members."""


class AuthorNotInChannelError(ChannelError):
    """The author of a message is not a member of the channel."""


# ---------------------------------------------------------------------------
# Schema (DDL)
# ---------------------------------------------------------------------------

_SCHEMA = """
CREATE TABLE IF NOT EXISTS channels (
    id                  TEXT PRIMARY KEY,
    name                TEXT UNIQUE NOT NULL,
    visibility          TEXT NOT NULL DEFAULT 'open',
    type                TEXT NOT NULL DEFAULT 'stream',
    created_at          REAL NOT NULL,
    member_limit_soft   INTEGER NOT NULL DEFAULT 50,
    member_limit_hard   INTEGER NOT NULL DEFAULT 200
);

CREATE TABLE IF NOT EXISTS memberships (
    channel_id      TEXT NOT NULL,
    member_handle   TEXT NOT NULL,
    joined_at       REAL NOT NULL,
    PRIMARY KEY (channel_id, member_handle),
    FOREIGN KEY (channel_id) REFERENCES channels(id)
);

CREATE TABLE IF NOT EXISTS messages (
    id              TEXT PRIMARY KEY,
    channel_id      TEXT NOT NULL,
    author_handle   TEXT NOT NULL,
    body            TEXT NOT NULL,
    mentions_json   TEXT NOT NULL DEFAULT '[]',
    created_at      REAL NOT NULL,
    FOREIGN KEY (channel_id) REFERENCES channels(id)
);

CREATE VIRTUAL TABLE IF NOT EXISTS messages_fts USING fts5(
    body,
    content='messages',
    content_rowid='rowid'
);

-- Triggers to keep FTS in sync
CREATE TRIGGER IF NOT EXISTS messages_ai AFTER INSERT ON messages BEGIN
    INSERT INTO messages_fts(rowid, body) VALUES (new.rowid, new.body);
END;

CREATE TRIGGER IF NOT EXISTS messages_ad AFTER DELETE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, body) VALUES ('delete', old.rowid, old.body);
END;

CREATE TRIGGER IF NOT EXISTS messages_au AFTER UPDATE ON messages BEGIN
    INSERT INTO messages_fts(messages_fts, rowid, body) VALUES ('delete', old.rowid, old.body);
    INSERT INTO messages_fts(rowid, body) VALUES (new.rowid, new.body);
END;
"""


# ---------------------------------------------------------------------------
# ChannelStore
# ---------------------------------------------------------------------------


class ChannelStore:
    """SQLite-backed channel store."""

    def __init__(
        self,
        db_path: str | Path = ":memory:",
        registry: Optional[AgentRegistry] = None,
    ) -> None:
        self.db_path = str(db_path)
        self.registry = registry
        self._conn = sqlite3.connect(self.db_path)
        self._conn.row_factory = sqlite3.Row
        self._conn.executescript(_SCHEMA)
        self._conn.commit()

    # -- lifecycle ----------------------------------------------------------

    def close(self) -> None:
        self._conn.close()

    def __enter__(self) -> "ChannelStore":
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    # -- channels -----------------------------------------------------------

    def create(
        self,
        name: str,
        *,
        visibility: ChannelVisibility | str = ChannelVisibility.OPEN,
        type: ChannelType | str = ChannelType.STREAM,
        member_limit_soft: int = 50,
        member_limit_hard: int = 200,
    ) -> Channel:
        """Create a new channel and persist it."""
        vis = ChannelVisibility(visibility) if isinstance(visibility, str) else visibility
        ctype = ChannelType(type) if isinstance(type, str) else type
        channel = Channel(
            id=str(uuid4()),
            name=name,
            visibility=vis,
            type=ctype,
            created_at=time.time(),
            member_limit_soft=member_limit_soft,
            member_limit_hard=member_limit_hard,
        )
        try:
            self._conn.execute(
                "INSERT INTO channels (id, name, visibility, type, created_at, "
                "member_limit_soft, member_limit_hard) VALUES (?,?,?,?,?,?,?)",
                (
                    channel.id,
                    channel.name,
                    channel.visibility.value,
                    channel.type.value,
                    channel.created_at,
                    channel.member_limit_soft,
                    channel.member_limit_hard,
                ),
            )
            self._conn.commit()
        except sqlite3.IntegrityError as exc:
            raise ChannelAlreadyExistsError(
                f"a channel named {name!r} already exists"
            ) from exc
        return channel

    def get(self, identifier: str) -> Channel:
        """Get a channel by id or by name (slug)."""
        row = self._conn.execute(
            "SELECT * FROM channels WHERE id = ? OR name = ?",
            (identifier, identifier),
        ).fetchone()
        if row is None:
            raise ChannelNotFoundError(f"no channel with id/name {identifier!r}")
        return _row_to_channel(row)

    def list_channels(self) -> list[Channel]:
        rows = self._conn.execute(
            "SELECT * FROM channels ORDER BY created_at"
        ).fetchall()
        return [_row_to_channel(r) for r in rows]

    # -- membership --------------------------------------------------------

    def add_member(self, channel_id: str, handle: str) -> Membership:
        """Add ``handle`` to a channel.

        Validates the handle against the agent registry (if configured),
        enforces soft/hard limits, and DM cap of 2.
        """
        channel = self.get(channel_id)

        # --- validate agent is registered ---
        if self.registry is not None:
            try:
                if self.registry.get(handle) is None:
                    raise NotAMemberError(
                        f"no agent profile registered for handle {handle!r}"
                    )
            except KeyError as exc:
                raise NotAMemberError(
                    f"no agent profile registered for handle {handle!r}"
                ) from exc

        # --- check not already a member ---
        existing = self._conn.execute(
            "SELECT 1 FROM memberships WHERE channel_id = ? AND member_handle = ?",
            (channel_id, handle),
        ).fetchone()
        if existing is not None:
            raise DuplicateMembershipError(
                f"{handle!r} is already a member of channel {channel.name!r}"
            )

        # --- count current members ---
        count = self._conn.execute(
            "SELECT COUNT(*) FROM memberships WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()[0]

        # --- DM cap ---
        if channel.type == ChannelType.DM and count >= 2:
            raise DmChannelFullError(
                f"DM channel {channel.name!r} already has 2 members"
            )

        # --- hard cap ---
        if count + 1 > channel.member_limit_hard:
            raise ChannelTooLargeError(
                f"channel {channel.name!r} has {count} members; "
                f"adding one would exceed hard limit {channel.member_limit_hard}"
            )

        # --- soft cap warning ---
        if count + 1 >= channel.member_limit_soft:
            logger.warning(
                "channel %r has %d members; adding one reaches soft limit %d",
                channel.name,
                count,
                channel.member_limit_soft,
            )

        membership = Membership(
            channel_id=channel_id,
            member_handle=handle,
            joined_at=time.time(),
        )
        self._conn.execute(
            "INSERT INTO memberships (channel_id, member_handle, joined_at) "
            "VALUES (?,?,?)",
            (membership.channel_id, membership.member_handle, membership.joined_at),
        )
        self._conn.commit()
        return membership

    def add_team(self, channel_id: str, handles: list[str]) -> list[Membership]:
        """Atomically add multiple members.

        If any handle fails validation, the entire operation is rolled back.
        """
        try:
            self._conn.execute("BEGIN")
            results = []
            for h in handles:
                # Call _add_member_impl without commit (we control tx here)
                results.append(self._add_member_impl(channel_id, h))
            self._conn.execute("COMMIT")
            return results
        except Exception:
            self._conn.execute("ROLLBACK")
            raise

    def _add_member_impl(self, channel_id: str, handle: str) -> Membership:
        """Like add_member but assumes the caller controls the transaction."""
        channel = self.get(channel_id)
        if self.registry is not None:
            try:
                if self.registry.get(handle) is None:
                    raise NotAMemberError(
                        f"no agent profile registered for handle {handle!r}"
                    )
            except KeyError as exc:
                raise NotAMemberError(
                    f"no agent profile registered for handle {handle!r}"
                ) from exc
        existing = self._conn.execute(
            "SELECT 1 FROM memberships WHERE channel_id = ? AND member_handle = ?",
            (channel_id, handle),
        ).fetchone()
        if existing is not None:
            raise DuplicateMembershipError(
                f"{handle!r} is already a member of channel {channel.name!r}"
            )
        count = self._conn.execute(
            "SELECT COUNT(*) FROM memberships WHERE channel_id = ?",
            (channel_id,),
        ).fetchone()[0]
        if channel.type == ChannelType.DM and count >= 2:
            raise DmChannelFullError(
                f"DM channel {channel.name!r} already has 2 members"
            )
        if count + 1 > channel.member_limit_hard:
            raise ChannelTooLargeError(
                f"channel {channel.name!r} has {count} members; "
                f"adding one would exceed hard limit {channel.member_limit_hard}"
            )
        if count + 1 >= channel.member_limit_soft:
            logger.warning(
                "channel %r has %d members; adding one reaches soft limit %d",
                channel.name,
                count,
                channel.member_limit_soft,
            )
        membership = Membership(
            channel_id=channel_id, member_handle=handle, joined_at=time.time()
        )
        self._conn.execute(
            "INSERT INTO memberships (channel_id, member_handle, joined_at) "
            "VALUES (?,?,?)",
            (membership.channel_id, membership.member_handle, membership.joined_at),
        )
        return membership

    def members(self, channel_id: str) -> list[str]:
        """Return the handles of all members of a channel."""
        rows = self._conn.execute(
            "SELECT member_handle FROM memberships WHERE channel_id = ? "
            "ORDER BY joined_at",
            (channel_id,),
        ).fetchall()
        return [r[0] for r in rows]

    def remove_member(self, channel_id: str, handle: str) -> None:
        """Remove a member from a channel."""
        cur = self._conn.execute(
            "DELETE FROM memberships WHERE channel_id = ? AND member_handle = ?",
            (channel_id, handle),
        )
        if cur.rowcount == 0:
            raise NotInChannelError(
                f"{handle!r} is not a member of channel {channel_id!r}"
            )
        self._conn.commit()

    # -- messages ----------------------------------------------------------

    def post(
        self,
        channel_id: str,
        author_handle: str,
        body: str,
        *,
        known_names: Optional[list[str]] = None,
    ) -> Message:
        """Post a message to a channel.

        Mentions are auto-extracted from ``body`` and stored as JSON.
        If ``known_names`` is provided, multi-word names are resolved.
        """
        # Author must be a member
        member = self._conn.execute(
            "SELECT 1 FROM memberships WHERE channel_id = ? AND member_handle = ?",
            (channel_id, author_handle),
        ).fetchone()
        if member is None:
            raise AuthorNotInChannelError(
                f"{author_handle!r} is not a member of channel {channel_id!r}"
            )

        mentions = extract_mentions(body, known_names=known_names)
        msg = Message(
            id=str(uuid4()),
            channel_id=channel_id,
            author_handle=author_handle,
            body=body,
            mentions=mentions,
            created_at=time.time(),
        )
        self._conn.execute(
            "INSERT INTO messages (id, channel_id, author_handle, body, "
            "mentions_json, created_at) VALUES (?,?,?,?,?,?)",
            (
                msg.id,
                msg.channel_id,
                msg.author_handle,
                msg.body,
                json.dumps(msg.mentions),
                msg.created_at,
            ),
        )
        self._conn.commit()
        return msg

    def history(
        self,
        channel_id: str,
        *,
        limit: int = 50,
        before_id: Optional[str] = None,
    ) -> list[Message]:
        """Return messages in chronological order (oldest first).

        When multiple messages share the same ``created_at`` timestamp (common
        in tests that post in rapid succession), insertion order (``rowid``)
        is used as a stable tiebreaker.
        """
        if before_id is not None:
            # Find the rowid of the before_id message so we can use
            # it as a stable insertion-order cursor (timestamps can
            # be identical for messages posted in rapid succession).
            before_row = self._conn.execute(
                "SELECT rowid FROM messages WHERE id = ?", (before_id,)
            ).fetchone()
            if before_row is None:
                return []
            before_rowid = before_row[0]
            # Messages inserted *before* this one (lower rowid).
            rows = self._conn.execute(
                "SELECT m.*, m.rowid as _rowid FROM messages m "
                "WHERE m.channel_id = ? AND m.rowid < ? "
                "ORDER BY m.rowid DESC LIMIT ?",
                (channel_id, before_rowid, limit),
            ).fetchall()
        else:
            rows = self._conn.execute(
                "SELECT m.*, m.rowid as _rowid FROM messages m "
                "WHERE m.channel_id = ? "
                "ORDER BY m.created_at DESC, m.rowid DESC LIMIT ?",
                (channel_id, limit),
            ).fetchall()
        # Reverse to chronological (oldest first)
        rows = list(reversed(rows))
        return [_row_to_message(r) for r in rows]

    def search(
        self, channel_id: str, query: str, *, limit: int = 20
    ) -> list[Message]:
        """Full-text search within a channel using FTS5."""
        # Build FTS5 query — escape special characters by quoting
        fts_query = " ".join(f'"{word}"' for word in query.split() if word)
        if not fts_query:
            return []
        rows = self._conn.execute(
            "SELECT m.* FROM messages m "
            "JOIN messages_fts f ON f.rowid = m.rowid "
            "WHERE m.channel_id = ? AND messages_fts MATCH ? "
            "ORDER BY rank LIMIT ?",
            (channel_id, fts_query, limit),
        ).fetchall()
        return [_row_to_message(r) for r in rows]

    # -- low-level ---------------------------------------------------------

    @property
    def connection(self) -> sqlite3.Connection:
        """Expose the underlying connection for tests/advanced use."""
        return self._conn


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _row_to_channel(row: sqlite3.Row) -> Channel:
    return Channel(
        id=row["id"],
        name=row["name"],
        visibility=ChannelVisibility(row["visibility"]),
        type=ChannelType(row["type"]),
        created_at=row["created_at"],
        member_limit_soft=row["member_limit_soft"],
        member_limit_hard=row["member_limit_hard"],
    )


def _row_to_message(row: sqlite3.Row) -> Message:
    mentions = json.loads(row["mentions_json"]) if row["mentions_json"] else []
    return Message(
        id=row["id"],
        channel_id=row["channel_id"],
        author_handle=row["author_handle"],
        body=row["body"],
        mentions=mentions,
        created_at=row["created_at"],
    )
