"""Agent runtime — wraps Hermes ``delegate_task`` to run a profile.

Implements PR-004 of the vector roadmap
(docs/roadmap/prs/PR-004-agent-runtime.md).

The runtime takes an :class:`AgentProfile` plus a user message and
returns the agent's response.  It delegates the actual LLM call to a
``DelegateCallable`` (see ``_hermes.py``), which in production wraps
``tools.delegate_task.delegate_task`` and in tests is replaced by a
fake.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Optional

from ._hermes import DelegateCallable
from .profile import AgentProfile


# ---------------------------------------------------------------------------
# Result dataclass
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class RunResult:
    """The outcome of an ``AgentRuntime.run`` call."""

    output: str = ""
    tokens_used: int = 0
    duration_ms: int = 0
    status: str = "ok"  # "ok" | "error" | "timeout"
    error: Optional[str] = None  # exception class name or chain summary
    model_used: Optional[str] = None


# ---------------------------------------------------------------------------
# Transient vs non-transient error classification
# ---------------------------------------------------------------------------

# Kinds of errors that trigger fallback.  Everything else (auth,
# validation, bad-request) short-circuits.
_TRANSIENT_KINDS = frozenset({
    "rate_limited",
    "5xx",
    "network_timeout",
    "oom",
    "timeout",
})

# Exception class names that are considered transient.
_TRANSIENT_EXCEPTIONS = frozenset({
    "RateLimitError",
    "TimeoutError",
    "ConnectionError",
    "APITimeoutError",
    "InternalServerError",
    "OutOfMemoryError",
})


def _is_transient(error_kind: Optional[str], exception_name: Optional[str]) -> bool:
    """Return True if the error is transient (should trigger fallback)."""
    if error_kind and error_kind in _TRANSIENT_KINDS:
        return True
    if exception_name and exception_name in _TRANSIENT_EXCEPTIONS:
        return True
    return False


# ---------------------------------------------------------------------------
# AgentRuntime
# ---------------------------------------------------------------------------


class AgentRuntime:
    """Turns an :class:`AgentProfile` into a responding agent.

    Parameters
    ----------
    delegate
        The callable that runs the actual LLM call.  In production,
        this wraps ``delegate_task``; in tests, a ``FakeDelegate``.
    default_model
        Model to use when ``profile.model`` is ``None`` (inherits the
        calling session's model).
    default_provider
        Provider to use when ``profile.provider`` is ``None``.
    """

    def __init__(
        self,
        delegate: DelegateCallable,
        *,
        default_model: Optional[str] = None,
        default_provider: Optional[str] = None,
    ) -> None:
        self._delegate = delegate
        self._default_model = default_model
        self._default_provider = default_provider

    def run(
        self,
        profile: AgentProfile,
        message: str,
        *,
        context: str | None = None,
        timeout: float = 300,
    ) -> RunResult:
        """Run ``profile`` on ``message`` and return the result.

        Honors ``profile.model``, ``profile.provider``,
        ``profile.tools``, ``profile.system_prompt``, and
        ``profile.fallback_models``.

        When the primary model fails with a transient error and
        ``fallback_models`` is non-empty, each fallback is tried in
        order.  Non-transient errors short-circuit immediately.

        ``context`` is additional context (e.g. channel history)
        passed to the delegate alongside the system prompt.
        """
        # --- resolve effective model + provider ---
        primary_model = profile.model or self._default_model
        primary_provider = profile.provider or self._default_provider

        # --- build the list of (model, provider) attempts ---
        attempts: list[tuple[Optional[str], Optional[str]]] = [
            (primary_model, primary_provider),
        ]
        # Fallbacks only apply when the primary model is explicit.
        if profile.model is not None:
            for fb in profile.fallback_models:
                attempts.append((fb, primary_provider))

        # --- build the context (system prompt + optional channel history) ---
        if context:
            delegate_context = f"{profile.system_prompt}\n\n--- Channel history ---\n{context}"
        else:
            delegate_context = profile.system_prompt

        # --- prefix the user message with the handle ---
        prefixed_message = f"[{profile.handle}] {message}"

        # --- try each attempt ---
        chain: list[str] = []
        start = time.monotonic()

        for idx, (model, provider) in enumerate(attempts):
            label = model or "inherited"
            if idx == 0:
                chain_label = f"primary={label}"
            else:
                chain_label = f"fallback[{idx - 1}]={label}"

            try:
                raw = self._delegate(
                    goal=prefixed_message,
                    context=delegate_context,
                    role="leaf",
                    max_iterations=None,
                    model=model,
                    provider=provider,
                    tools=profile.tools,
                )
            except Exception as exc:
                exc_name = type(exc).__name__
                transient = _is_transient(None, exc_name)
                chain.append(f"{chain_label}: {exc_name}")
                if not transient:
                    # Non-transient: short-circuit, no more fallbacks.
                    return RunResult(
                        output="",
                        duration_ms=int((time.monotonic() - start) * 1000),
                        status="error",
                        error=exc_name,
                        model_used=label,
                    )
                # Transient exception: try next fallback.
                continue

            # Parse the raw output.
            parsed = _parse_delegate_output(raw, label)
            result = RunResult(
                output=parsed.output,
                tokens_used=parsed.tokens_used,
                duration_ms=int((time.monotonic() - start) * 1000),
                status=parsed.status,
                error=parsed.error,
                model_used=label,
            )

            if result.status == "ok":
                return result

            # Error or timeout — check if transient.
            transient = _is_transient(parsed._kind, None)

            chain.append(f"{chain_label}: {parsed._kind or result.error or result.status}")

            if not transient:
                # Non-transient: short-circuit.
                return result

            # Transient: try next fallback.

        # --- all attempts exhausted ---
        chain_summary = "; ".join(chain)
        return RunResult(
            output="",
            duration_ms=int((time.monotonic() - start) * 1000),
            status="error",
            error=chain_summary,
            model_used=primary_model,
        )


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


@dataclass
class _ParsedResult:
    output: str = ""
    tokens_used: int = 0
    status: str = "ok"
    error: Optional[str] = None
    _kind: Optional[str] = None


def _parse_delegate_output(raw: str, model_label: str) -> _ParsedResult:
    """Parse the raw delegate output string.

    The real ``delegate_task`` returns a JSON string with a ``results``
    array.  In tests, the fake delegate returns a direct string or a
    JSON-ish dict.  We handle both.
    """
    import json

    # Try JSON parse.
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        # Raw string — assume success.
        return _ParsedResult(output=raw, status="ok")

    # If it's a dict with "results", use the first result.
    if isinstance(data, dict):
        if "results" in data and isinstance(data["results"], list):
            results = data["results"]
            if results:
                first = results[0]
                if isinstance(first, dict):
                    status = first.get("status", "ok")
                    output = first.get("output", "") or first.get("summary", "")
                    error = first.get("error")
                    kind = first.get("kind")
                    tokens = first.get("tokens_used", 0)
                    return _ParsedResult(
                        output=output,
                        tokens_used=tokens,
                        status=status,
                        error=error,
                        _kind=kind,
                    )
        # Single dict
        status = data.get("status", "ok")
        output = data.get("output", "") or data.get("summary", "")
        error = data.get("error")
        kind = data.get("kind")
        tokens = data.get("tokens_used", 0)
        return _ParsedResult(
            output=output,
            tokens_used=tokens,
            status=status,
            error=error,
            _kind=kind,
        )

    # Fallback — raw string.
    return _ParsedResult(output=raw, status="ok")
