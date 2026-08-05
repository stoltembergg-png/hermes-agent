"""Agent profile schema and registry.

Implements PR-001 of the vector roadmap
(docs/roadmap/prs/PR-001-agent-profile-schema.md).

Public surface:

- AgentProfile: frozen dataclass with handle, system_prompt, tools,
  model, provider, fallback_models, description, created_at, updated_at.
- AgentRegistry: in-memory store keyed by handle with .register() /
  .get() / .all() / .remove().
- Validation helpers: validate_handle(), validate_model_catalog(),
  validate_fallback_chain().
- Exceptions: InvalidHandleError, UnknownModelError,
  InvalidFallbackChainError, DuplicateHandleError.
"""

from __future__ import annotations

import json
import re
from collections.abc import Callable, Iterable, Mapping
from dataclasses import asdict, dataclass, field, fields
from datetime import UTC, datetime
from typing import Any

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

HANDLE_PATTERN = re.compile(r"^[a-z0-9._-]{2,32}$")


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------


class InvalidHandleError(ValueError):
    """Raised when a handle does not match the required slug shape."""


class UnknownModelError(ValueError):
    """Raised when a model or provider is not present in the live catalog."""


class InvalidFallbackChainError(ValueError):
    """Raised when the fallback chain is malformed (duplicates, contains primary, etc.)."""


class DuplicateHandleError(KeyError):
    """Raised when registering a profile with a handle already in the registry."""


# ---------------------------------------------------------------------------
# Validation helpers
# ---------------------------------------------------------------------------


def validate_handle(handle: str) -> str:
    """Validate and return the handle. Raises InvalidHandleError otherwise."""
    if not isinstance(handle, str):
        raise InvalidHandleError(f"handle must be str, got {type(handle).__name__}")
    if not HANDLE_PATTERN.match(handle):
        raise InvalidHandleError(
            f"invalid handle {handle!r}: must match {HANDLE_PATTERN.pattern}"
        )
    return handle


def validate_model_catalog(
    model: str | None,
    provider: str | None,
    *,
    catalog_provider: Callable[[str], bool] | None = None,
) -> None:
    """Validate that ``model`` and ``provider`` are present in the catalog.

    ``catalog_provider`` is a predicate that receives a ``"provider/model"``
    string and returns True if the model is known. When the predicate is
    None we skip catalog validation (used by tests that don't want to
    stub the catalog).
    """
    if catalog_provider is None:
        return
    if model is not None and not catalog_provider(model):
        raise UnknownModelError(f"unknown model: {model!r}")
    # provider is encoded as the prefix of model when model is set; we
    # only validate the provider field when it is set independently.
    if provider is not None and "/" not in (model or ""):
        # Caller set provider without an explicit model. Validate as
        # ``provider/<sentinel>`` if the catalog exposes a wildcard,
        # then fall back to the bare provider name.
        sentinel = f"{provider}/*"
        if not catalog_provider(sentinel) and not catalog_provider(provider):
            raise UnknownModelError(f"unknown provider: {provider!r}")


def validate_fallback_chain(
    primary_model: str | None,
    fallback_models: tuple[str, ...],
) -> tuple[str, ...]:
    """Validate the fallback chain invariants."""
    if not fallback_models:
        return fallback_models
    # No duplicates
    if len(fallback_models) != len(set(fallback_models)):
        seen: set[str] = set()
        dupes: list[str] = []
        for m in fallback_models:
            if m in seen and m not in dupes:
                dupes.append(m)
            seen.add(m)
        raise InvalidFallbackChainError(
            f"fallback_models contains duplicates: {dupes}"
        )
    # Must not contain the primary model
    if primary_model is not None and primary_model in fallback_models:
        raise InvalidFallbackChainError(
            f"fallback_models must not contain the primary model {primary_model!r}"
        )
    return fallback_models


# ---------------------------------------------------------------------------
# AgentProfile
# ---------------------------------------------------------------------------


def _utcnow() -> datetime:
    return datetime.now(UTC)


@dataclass(frozen=True)
class AgentProfile:
    """A named agent profile.

    Implements REQ-VEC-001-1 .. REQ-VEC-001-6 of PR-001.
    """

    handle: str
    system_prompt: str
    tools: tuple[str, ...] = ()
    model: str | None = None
    provider: str | None = None
    fallback_models: tuple[str, ...] = ()
    description: str = ""
    created_at: datetime = field(default_factory=_utcnow)
    updated_at: datetime = field(default_factory=_utcnow)

    def __post_init__(self) -> None:
        # REQ-VEC-001-2 — handle shape
        validate_handle(self.handle)
        # REQ-VEC-001-6 — fallback chain invariants
        validate_fallback_chain(self.model, self.fallback_models)
        # Defensive normalization: tools must be tuple of strings.
        if isinstance(self.tools, list):
            object.__setattr__(self, "tools", tuple(self.tools))
        if isinstance(self.fallback_models, list):
            object.__setattr__(self, "fallback_models", tuple(self.fallback_models))

    # ------------------------------------------------------------------
    # (De)serialization — REQ-VEC-001-3 / REQ-VEC-001-4
    # ------------------------------------------------------------------

    def to_dict(self) -> dict[str, Any]:
        """Return a dict suitable for JSON / YAML serialization."""
        d = asdict(self)
        # datetime -> ISO 8601 string
        d["created_at"] = self.created_at.isoformat()
        d["updated_at"] = self.updated_at.isoformat()
        # tuple -> list for friendlier YAML/JSON (handle None defensively)
        d["tools"] = list(self.tools or ())
        d["fallback_models"] = list(self.fallback_models or ())
        return d

    @classmethod
    def from_dict(cls, data: Mapping[str, Any]) -> AgentProfile:
        """Build an AgentProfile from a dict (parsed JSON or YAML)."""
        d = dict(data)
        # Coerce tools and fallback_models to tuple.
        for key in ("tools", "fallback_models"):
            if key in d and d[key] is not None:
                d[key] = tuple(d[key])
        # Parse ISO 8601 datetimes back into datetime objects.
        for key in ("created_at", "updated_at"):
            if key in d and isinstance(d[key], str):
                d[key] = datetime.fromisoformat(d[key])
        # Filter unknown keys so callers can pass extra metadata.
        allowed = {f.name for f in fields(cls)}
        return cls(**{k: v for k, v in d.items() if k in allowed})

    # ---- JSON ----

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), ensure_ascii=False, sort_keys=True)

    @classmethod
    def from_json(cls, s: str) -> AgentProfile:
        return cls.from_dict(json.loads(s))

    # ---- YAML (optional, falls back to JSON-shape when PyYAML absent) ----

    def to_yaml(self) -> str:
        """Serialize to YAML.

        Tries PyYAML first; falls back to a hand-rolled minimal emitter
        so the module works without any third-party dependency.
        """
        d = self.to_dict()
        try:
            import yaml  # type: ignore

            return yaml.safe_dump(d, sort_keys=False, allow_unicode=True)
        except ImportError:
            return _yaml_fallback(d)

    @classmethod
    def from_yaml(cls, s: str) -> AgentProfile:
        try:
            import yaml  # type: ignore

            return cls.from_dict(yaml.safe_load(s))
        except ImportError:
            return cls.from_dict(_yaml_parse_fallback(s))


def _yaml_fallback(d: Mapping[str, Any]) -> str:
    """Minimal YAML emitter for our flat dict shape."""
    lines: list[str] = []
    for key, value in d.items():
        if isinstance(value, str):
            # Block-scalar only when multi-line; otherwise quoted
            if "\n" in value:
                lines.append(f"{key}: |")
                for ln in value.splitlines():
                    lines.append(f"  {ln}")
            else:
                # Use single quotes for safety.
                lines.append(f"{key}: '{value.replace(chr(39), chr(39) * 2)}'")
        elif isinstance(value, list):
            lines.append(f"{key}:")
            for item in value:
                lines.append(f"  - '{item}'")
        elif value is None:
            lines.append(f"{key}: null")
        else:
            lines.append(f"{key}: {value}")
    return "\n".join(lines) + "\n"


def _yaml_parse_fallback(s: str) -> dict[str, Any]:
    """Tiny YAML reader sufficient for our emitter's output."""
    out: dict[str, Any] = {}
    current_list_key: str | None = None
    for raw_line in s.splitlines():
        if not raw_line.strip() or raw_line.lstrip().startswith("#"):
            continue
        stripped = raw_line.rstrip()
        if current_list_key is not None and stripped.startswith("  - "):
            item = stripped[4:].strip().strip("'").replace("''", "'")
            out[current_list_key].append(item)
            continue
        current_list_key = None
        if ":" not in stripped:
            continue
        key, _, value = stripped.partition(":")
        key = key.strip()
        value = value.strip()
        if value == "":
            # Could be the start of a list or block scalar.
            # We don't try to handle block scalars in this minimal parser
            # — round-trip via from_yaml/from_json on multiline values
            # is supported only when PyYAML is installed.
            out[key] = []
            current_list_key = key
        elif value == "null":
            out[key] = None
        elif value.startswith("'") and value.endswith("'") and len(value) >= 2:
            out[key] = value[1:-1].replace("''", "'")
        else:
            out[key] = value
    return out


# ---------------------------------------------------------------------------
# AgentRegistry
# ---------------------------------------------------------------------------


class AgentRegistry:
    """In-memory registry of agent profiles keyed by handle.

    Supports optional YAML persistence via ``save_to_yaml`` / ``load_from_yaml``
    for CLI use (PR-006). When persistence is not needed, the registry
    works purely in memory.
    """

    def __init__(self, profiles: Iterable[AgentProfile] | None = None) -> None:
        self._profiles: dict[str, AgentProfile] = {}
        if profiles:
            for p in profiles:
                self.register(p)

    # ----- mutations -----

    def register(self, profile: AgentProfile) -> AgentProfile:
        if profile.handle in self._profiles:
            raise DuplicateHandleError(
                f"profile with handle {profile.handle!r} already registered"
            )
        self._profiles[profile.handle] = profile
        return profile

    def remove(self, handle: str) -> AgentProfile:
        try:
            return self._profiles.pop(handle)
        except KeyError as exc:
            raise KeyError(f"no profile registered with handle {handle!r}") from exc

    # ----- queries -----

    def get(self, handle: str) -> AgentProfile:
        try:
            return self._profiles[handle]
        except KeyError as exc:
            raise KeyError(f"no profile registered with handle {handle!r}") from exc

    def has(self, handle: str) -> bool:
        return handle in self._profiles

    def all(self) -> list[AgentProfile]:
        return sorted(self._profiles.values(), key=lambda p: p.handle)

    def __len__(self) -> int:
        return len(self._profiles)

    def __contains__(self, handle: object) -> bool:
        return isinstance(handle, str) and handle in self._profiles

    def __iter__(self):
        return iter(sorted(self._profiles))

    # ----- persistence (PR-006) -----

    def save_to_yaml(self, path: str | Any) -> None:
        """Save all profiles to a YAML file. The file is a YAML document
        with a top-level ``profiles`` list. Each profile is serialized
        via ``AgentProfile.to_dict()``."""
        import yaml

        data = {"profiles": [p.to_dict() for p in self.all()]}
        with open(path, "w", encoding="utf-8") as f:
            yaml.dump(data, f, default_flow_style=False, sort_keys=False)

    @classmethod
    def load_from_yaml(cls, path: str | Any) -> AgentRegistry:
        """Load profiles from a YAML file written by ``save_to_yaml``.

        Returns an empty registry if the file does not exist.
        """
        import os

        if not os.path.exists(path):
            return cls()
        import yaml

        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        profiles = []
        for entry in data.get("profiles", []):
            profiles.append(AgentProfile.from_dict(entry))
        return cls(profiles)
