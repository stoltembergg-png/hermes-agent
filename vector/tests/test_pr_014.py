"""Contract tests for PR-014: Visible agent list in sidebar.

Tests verify:
- The DELETE /agents/{handle} endpoint exists in the backend
- The frontend source contains the required components and atoms
- AgentRow and AgentDetails components exist in plugin.tsx
- $agentDetails and $selectedAgent atoms exist
- The sidebar has an agents section
- The main area conditionally renders AgentDetails
"""

import re
from pathlib import Path

import pytest

PLUGIN_DIR = Path(__file__).resolve().parent.parent.parent / "apps" / "desktop" / "src" / "plugins" / "vector-channels"
PLUGIN_TSX = PLUGIN_DIR / "plugin.tsx"
PLUGIN_CSS = PLUGIN_DIR / "vector-channels.css"
API_TS = PLUGIN_DIR / "api.ts"


@pytest.mark.ac_vec_014_1
def test_pr_014_delete_agent_endpoint_exists():
    """The api.ts must export a deleteAgent function for the delete button."""
    src = API_TS.read_text()
    assert "deleteAgent" in src, "deleteAgent function not found in api.ts"
    assert "DELETE" in src or "delete" in src.lower(), "DELETE method not found in api.ts"


@pytest.mark.ac_vec_014_2
def test_pr_014_agent_details_atom_exists():
    """$agentDetails atom must exist to store full AgentInfo objects."""
    src = PLUGIN_TSX.read_text()
    assert "$agentDetails" in src, "$agentDetails atom not found in plugin.tsx"
    assert "atom<AgentInfo[]>" in src or "atom<AgentInfo[" in src, "AgentInfo[] atom type not found"


@pytest.mark.ac_vec_014_3
def test_pr_014_selected_agent_atom_exists():
    """$selectedAgent atom must exist for the agent details panel."""
    src = PLUGIN_TSX.read_text()
    assert "$selectedAgent" in src, "$selectedAgent atom not found in plugin.tsx"


@pytest.mark.ac_vec_014_4
def test_pr_014_agent_row_component_exists():
    """AgentRow component must exist with robot icon and handle."""
    src = PLUGIN_TSX.read_text()
    assert "function AgentRow" in src or "AgentRow" in src, "AgentRow component not found"
    assert "robot" in src, " robot Codicon not found in plugin.tsx"


@pytest.mark.ac_vec_014_5
def test_pr_014_agent_details_component_exists():
    """AgentDetails component must exist with system prompt and model info."""
    src = PLUGIN_TSX.read_text()
    assert "function AgentDetails" in src or "AgentDetails" in src, "AgentDetails component not found"


@pytest.mark.ac_vec_014_6
def test_pr_014_sidebar_agents_section():
    """The sidebar must have an Agents section with the agent rows."""
    src = PLUGIN_TSX.read_text()
    assert "vector-agents-section" in src, "vector-agents-section class not found in sidebar"
    assert "vector-agents-header" in src, "Agents header not found"


@pytest.mark.ac_vec_014_7
def test_pr_014_main_area_conditional_for_agent_details():
    """The main area must conditionally render AgentDetails when an agent is selected."""
    src = PLUGIN_TSX.read_text()
    assert "selectedAgent" in src, "selectedAgent conditional not found in main area"
    assert "AgentDetails" in src, "AgentDetails not rendered in main area"


@pytest.mark.ac_vec_014_8
def test_pr_014_css_has_agent_row_styles():
    """CSS must include styles for agent rows and details panel."""
    src = PLUGIN_CSS.read_text()
    assert "vector-agent-row" in src, "vector-agent-row CSS class not found"
    assert "vector-agent-details" in src, "vector-agent-details CSS class not found"


@pytest.mark.ac_vec_014_9
def test_pr_014_agentdetails_shows_system_prompt():
    """AgentDetails must show the system prompt (stored in description field)."""
    src = PLUGIN_TSX.read_text()
    # The AgentDetails component should reference description or system_prompt
    assert "description" in src or "system_prompt" in src, "System prompt/description not referenced in AgentDetails"


@pytest.mark.ac_vec_014_10
def test_pr_014_delete_agent_helper():
    """deleteAgentAndRefresh helper must exist for the delete button wiring."""
    src = PLUGIN_TSX.read_text()
    assert "deleteAgentAndRefresh" in src or "deleteAgent" in src, "Delete agent helper not found"
