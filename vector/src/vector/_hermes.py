"""Internal Hermes delegate wrapper.

This module isolates the real `delegate_task` call behind a thin callable
so ``AgentRuntime`` (and its tests) can mock it cleanly without importing
the full Hermes process machinery.

The real ``delegate_task`` in ``tools/delegate_tool.py`` does **not**
accept ``model`` / ``provider`` / ``tools`` kwargs — the child agent
inherits from the parent agent or from ``delegation.provider / model``
in config.yaml.  The vector runtime works around this by exposing a
wider interface here; the default implementation calls ``delegate_task``
with only the kwargs it accepts, and model/tool selection is expected
to be handled by the caller at a higher layer (via config or by
constructing the child agent directly).

For tests, a ``FakeDelegate`` replaces this callable entirely.
"""

from __future__ import annotations

from typing import Any, Optional, Protocol


class DelegateCallable(Protocol):
    """Protocol for a delegate invocation."""

    def __call__(
        self,
        *,
        goal: str,
        context: Optional[str] = None,
        role: str = "leaf",
        max_iterations: Optional[int] = None,
        model: Optional[str] = None,
        provider: Optional[str] = None,
        tools: Optional[tuple] = None,
    ) -> str: ...


def default_delegate(
    *,
    goal: str,
    context: Optional[str] = None,
    role: str = "leaf",
    max_iterations: Optional[int] = None,
    model: Optional[str] = None,
    provider: Optional[str] = None,
    tools: Optional[tuple] = None,
) -> str:
    """Call the real Hermes ``delegate_task``.

    This is a thin adapter.  It forwards ``goal``, ``context``, ``role``,
    and ``max_iterations`` to ``delegate_task``.  The ``model``,
    ``provider``, and ``tools`` kwargs are **not** accepted by the real
    ``delegate_task`` (which inherits from the parent agent); they are
    consumed by the vector runtime to configure the child via other
    mechanisms (config overrides, direct AIAgent construction, etc.).

    In production, this function needs a ``parent_agent`` reference to
    pass to ``delegate_task``.  It is injected at runtime via the
    ``AgentRuntime`` constructor.
    """
    raise NotImplementedError(
        "default_delegate requires a parent_agent context. "
        "In production, AgentRuntime is constructed with a parent_agent. "
        "In tests, a FakeDelegate is used instead."
    )
