"""Contract tests for PR-019: Message timestamps + author avatars."""

import re
from pathlib import Path

PLUGIN_TSX = Path(__file__).resolve().parents[2] / "apps/desktop/src/plugins/vector-channels/plugin.tsx"
CSS_FILE = Path(__file__).resolve().parents[2] / "apps/desktop/src/plugins/vector-channels/vector-channels.css"


def test_message_row_has_avatar():
    src = PLUGIN_TSX.read_text()
    assert "vector-message-avatar" in src, "MessageRow should have avatar element"


def test_avatar_shows_initial():
    src = PLUGIN_TSX.read_text()
    assert "charAt(0)" in src, "Avatar should use first char of handle"
    assert "toUpperCase" in src, "Avatar initial should be uppercase"


def test_message_row_has_timestamp():
    src = PLUGIN_TSX.read_text()
    assert "vector-message-time" in src, "Timestamp element should exist"


def test_timestamp_formatted_with_hours_minutes():
    src = PLUGIN_TSX.read_text()
    assert "hour: '2-digit'" in src or "hour:'2-digit'" in src, "Timestamp should use 2-digit hour"
    assert "minute: '2-digit'" in src or "minute:'2-digit'" in src, "Timestamp should use 2-digit minute"


def test_message_row_wrapper_class():
    src = PLUGIN_TSX.read_text()
    assert "vector-message-row" in src, "MessageRow should use vector-message-row class"


def test_author_handle_preserved():
    src = PLUGIN_TSX.read_text()
    assert "author_handle" in src, "author_handle should still be referenced"


def test_css_avatar_style():
    css = CSS_FILE.read_text()
    assert ".vector-message-avatar" in css, "Avatar CSS class should exist"
    assert "border-radius" in css, "Avatar should have border-radius"
    assert "flex" in css, "Avatar should use flexbox"


def test_css_message_row_style():
    css = CSS_FILE.read_text()
    assert ".vector-message-row" in css, "Message row CSS should exist"
    assert "display: flex" in css or "display:flex" in css, "Message row should be flex"
