"""Contract tests for PR-015: Sidebar button icons + UX clarity."""

import re
from pathlib import Path

PLUGIN_TSX = Path(__file__).resolve().parents[2] / "apps/desktop/src/plugins/vector-channels/plugin.tsx"
CSS_FILE = Path(__file__).resolve().parents[2] / "apps/desktop/src/plugins/vector-channels/vector-channels.css"


def test_sidebar_btn_class_exists():
    source = PLUGIN_TSX.read_text(encoding="utf-8")
    assert "vector-sidebar-btn" in source, "vector-sidebar-btn class missing from plugin.tsx"


def test_codicon_add_in_source():
    source = PLUGIN_TSX.read_text(encoding="utf-8")
    assert 'Codicon name="add"' in source, "Codicon 'add' missing"


def test_codicon_new_file_in_source():
    source = PLUGIN_TSX.read_text(encoding="utf-8")
    assert 'Codicon name="new-file"' in source, "Codicon 'new-file' missing"


def test_title_attributes_exist():
    source = PLUGIN_TSX.read_text(encoding="utf-8")
    assert 'title="Create channel"' in source or 'title="Create Channel"' in source
    assert 'title="Add agent"' in source or 'title="Add Agent"' in source


def test_member_count_badge_in_channel_row():
    source = PLUGIN_TSX.read_text(encoding="utf-8")
    assert "vector-channel-badge" in source, "vector-channel-badge missing from plugin.tsx"


def test_css_sidebar_btn_class_exists():
    css = CSS_FILE.read_text(encoding="utf-8")
    assert ".vector-sidebar-btn" in css, "vector-sidebar-btn class missing from CSS"


def test_css_channel_badge_class_exists():
    css = CSS_FILE.read_text(encoding="utf-8")
    assert ".vector-channel-badge" in css, "vector-channel-badge class missing from CSS"


def test_css_hover_state_exists():
    css = CSS_FILE.read_text(encoding="utf-8")
    assert ":hover" in css, "hover state missing from CSS"
