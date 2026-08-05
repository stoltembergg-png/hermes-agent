"""Vector CLI — argparse + asyncio REPL.

Implements PR-006 of the vector roadmap
(docs/roadmap/prs/PR-006-cli.md).

Commands:

- ``vector agents add <handle> --system "..." [--model ...] [--provider ...]
  [--tools "a,b,c"] [--fallback-models "m1,m2"]``
- ``vector agents list``
- ``vector channels add <name> --members "a,b,c"``
- ``vector channels add-member <name> <handle>``
- ``vector channels add-team <name> --handles "a,b,c,..."``
- ``vector channels list``
- ``vector chat --channel <name>``
- ``vector --version``

Persistence:

- Profiles: ``$HERMES_HOME/vector/agents.yaml``
- Channels: ``$HERMES_HOME/vector/vector.db`` (SQLite)
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path
from typing import Optional

from .channel import (
    ChannelStore,
    ChannelTooLargeError,
    AuthorNotInChannelError,
    NotAMemberError,
)
from .dispatcher import Dispatcher
from .profile import (
    AgentProfile,
    AgentRegistry,
    DuplicateHandleError,
    InvalidHandleError,
    UnknownModelError,
)
from .runtime import AgentRuntime

SOFT_CAP = 50
HARD_CAP = 200

__version__ = "0.1.0"


# ---------------------------------------------------------------------------
# Path helpers
# ---------------------------------------------------------------------------


def _vector_dir() -> Path:
    """Return the vector data directory under HERMES_HOME."""
    hermes_home = os.environ.get("HERMES_HOME")
    if hermes_home:
        base = Path(hermes_home)
    else:
        base = Path.home() / ".hermes"
    d = base / "vector"
    d.mkdir(parents=True, exist_ok=True)
    return d


def _agents_path() -> Path:
    return _vector_dir() / "agents.yaml"


def _db_path() -> Path:
    return _vector_dir() / "vector.db"


def _load_registry() -> AgentRegistry:
    return AgentRegistry.load_from_yaml(_agents_path())


def _save_registry(reg: AgentRegistry) -> None:
    reg.save_to_yaml(_agents_path())


def _load_store(registry: AgentRegistry) -> ChannelStore:
    return ChannelStore(str(_db_path()), registry=registry)


# ---------------------------------------------------------------------------
# Command handlers
# ---------------------------------------------------------------------------


def cmd_agents_add(args: argparse.Namespace) -> int:
    reg = _load_registry()
    tools = tuple(
        t.strip() for t in args.tools.split(",") if t.strip()
    ) if args.tools else ()
    fallback = (
        [m.strip() for m in args.fallback_models.split(",") if m.strip()]
        if args.fallback_models
        else None
    )
    try:
        profile = AgentProfile(
            handle=args.handle,
            system_prompt=args.system,
            tools=tools,
            model=args.model,
            provider=args.provider,
            fallback_models=fallback,
            description=args.description,
        )
    except (InvalidHandleError, UnknownModelError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    try:
        reg.register(profile)
    except DuplicateHandleError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    _save_registry(reg)
    print(f"Agent '{args.handle}' added.")
    return 0


def cmd_agents_list(args: argparse.Namespace) -> int:
    reg = _load_registry()
    profiles = reg.all()
    if not profiles:
        print("No agents registered.")
        return 0
    print(f"{'Handle':<20} {'Model':<30} {'Provider':<15} {'Tools'}")
    print("-" * 80)
    for p in profiles:
        tools_str = ", ".join(p.tools) if p.tools else ""
        model_str = p.model or "(default)"
        provider_str = p.provider or "(default)"
        print(f"{p.handle:<20} {model_str:<30} {provider_str:<15} {tools_str}")
    return 0


def cmd_channels_add(args: argparse.Namespace) -> int:
    reg = _load_registry()
    store = _load_store(reg)
    members = [m.strip() for m in args.members.split(",") if m.strip()] if args.members else []
    try:
        ch = store.create(args.name)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        store.close()
        return 1
    added = 0
    for m in members:
        try:
            store.add_member(ch.id, m)
            added += 1
        except (NotAMemberError, ChannelTooLargeError) as exc:
            print(f"Warning: {exc}", file=sys.stderr)
        except Exception as exc:
            print(f"Warning: could not add {m!r}: {exc}", file=sys.stderr)
    store.close()
    print(f"Channel '{args.name}' created with {added} member(s).")
    if added >= SOFT_CAP:
        print(f"Warning: channel has {added} members (soft cap {SOFT_CAP}).", file=sys.stderr)
    return 0


def cmd_channels_add_member(args: argparse.Namespace) -> int:
    reg = _load_registry()
    store = _load_store(reg)
    channels = store.list_channels()
    channel = None
    for ch in channels:
        if ch.name == args.name:
            channel = ch
            break
    if channel is None:
        print(f"Error: channel '{args.name}' not found.", file=sys.stderr)
        store.close()
        return 1
    try:
        store.add_member(channel.id, args.handle)
    except ChannelTooLargeError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        store.close()
        return 1
    except NotAMemberError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        store.close()
        return 1
    store.close()
    print(f"Member '{args.handle}' added to channel '{args.name}'.")
    return 0


def cmd_channels_add_team(args: argparse.Namespace) -> int:
    """Add multiple members atomically: all or nothing."""
    reg = _load_registry()
    store = _load_store(reg)
    handles = [h.strip() for h in args.handles.split(",") if h.strip()]
    channels = store.list_channels()
    channel = None
    for ch in channels:
        if ch.name == args.name:
            channel = ch
            break
    if channel is None:
        print(f"Error: channel '{args.name}' not found.", file=sys.stderr)
        store.close()
        return 1
    # Check current member count
    current = set(store.members(channel.id))
    total = len(current) + len(handles)
    if total > HARD_CAP:
        print(
            f"Error: adding {len(handles)} members would exceed hard cap "
            f"({total} > {HARD_CAP}). Rolled back.",
            file=sys.stderr,
        )
        store.close()
        return 1
    added = 0
    failed = False
    for h in handles:
        try:
            store.add_member(channel.id, h)
            added += 1
        except (NotAMemberError, ChannelTooLargeError, DuplicateHandleError) as exc:
            print(f"Error: {exc} — rolling back {added} additions.", file=sys.stderr)
            # Rollback: remove all that were added
            for added_h in handles[:added]:
                try:
                    store.remove_member(channel.id, added_h)
                except Exception:
                    pass
            failed = True
            break
    store.close()
    if failed:
        return 1
    if added >= SOFT_CAP:
        print(f"Warning: channel now has {added} members (soft cap {SOFT_CAP}).",
              file=sys.stderr)
    print(f"Added {added} member(s) to channel '{args.name}'.")
    return 0


def cmd_channels_list(args: argparse.Namespace) -> int:
    reg = _load_registry()
    store = _load_store(reg)
    channels = store.list_channels()
    if not channels:
        print("No channels.")
        store.close()
        return 0
    print(f"{'Name':<25} {'Members':>7}")
    print("-" * 35)
    for ch in channels:
        count = len(store.members(ch.id))
        print(f"{ch.name:<25} {count:>7}")
    store.close()
    return 0


def cmd_chat(args: argparse.Namespace) -> int:
    """Interactive REPL."""
    reg = _load_registry()
    store = _load_store(reg)
    channels = store.list_channels()
    channel = None
    for ch in channels:
        if ch.name == args.channel:
            channel = ch
            break
    if channel is None:
        print(f"Error: channel '{args.channel}' not found.", file=sys.stderr)
        store.close()
        return 1
    # Build a runtime with the real delegate (or a stub if unavailable).
    try:
        from ._hermes import HermesDelegate
        delegate = HermesDelegate()
    except ImportError:
        print("Warning: Hermes delegate not available. Using stub.", file=sys.stderr)
        class StubDelegate:
            def __call__(self, *, goal, context=None, role="leaf",
                         max_iterations=None, model=None, provider=None, tools=None):
                import json
                return json.dumps({"results": [{"status": "ok", "output": "(no response)"}]})
        delegate = StubDelegate()
    runtime = AgentRuntime(delegate)
    disp = Dispatcher(store, runtime, reg)
    print(f"Vector chat — channel: {args.channel}  (type /quit to exit)")
    # Add "user" as a member so the REPL can post.
    if not reg.has("user"):
        reg.register(AgentProfile(
            handle="user", system_prompt="You are a user.", model=None,
        ))
        _save_registry(reg)
    if "user" not in set(store.members(channel.id)):
        try:
            store.add_member(channel.id, "user")
        except Exception:
            pass
    try:
        while True:
            try:
                line = input("> ")
            except (EOFError, KeyboardInterrupt):
                print()
                break
            if line.strip() == "/quit":
                break
            if not line.strip():
                continue
            # Post the user message.
            store.post(channel.id, "user", line)
            # Dispatch.
            result = disp.dispatch(channel.id, "user", line)
            for entry in result.entries:
                if entry.response:
                    print(f"@{entry.handle} > {entry.response}")
    finally:
        store.close()
    return 0


# ---------------------------------------------------------------------------
# Parser
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="vector", description="Multi-agent orchestration CLI")
    parser.add_argument("--version", action="version", version=f"vector {__version__}")
    sub = parser.add_subparsers(dest="command")

    # --- agents ---
    agents = sub.add_parser("agents", help="Manage agent profiles")
    agents_sub = agents.add_subparsers(dest="agents_command")
    add_p = agents_sub.add_parser("add", help="Add a new agent profile")
    add_p.add_argument("handle", help="Agent handle")
    add_p.add_argument("--system", required=True, help="System prompt")
    add_p.add_argument("--model", default=None, help="Model ID")
    add_p.add_argument("--provider", default=None, help="Provider name")
    add_p.add_argument("--tools", default=None, help="Comma-separated tool names")
    add_p.add_argument("--fallback-models", default=None, help="Comma-separated fallback models")
    add_p.add_argument("--description", default=None, help="Description")
    add_p.set_defaults(func=cmd_agents_add)
    list_p = agents_sub.add_parser("list", help="List agent profiles")
    list_p.set_defaults(func=cmd_agents_list)

    # --- channels ---
    channels = sub.add_parser("channels", help="Manage channels")
    ch_sub = channels.add_subparsers(dest="channels_command")
    ch_add = ch_sub.add_parser("add", help="Create a channel")
    ch_add.add_argument("name", help="Channel name")
    ch_add.add_argument("--members", default=None, help="Comma-separated member handles")
    ch_add.set_defaults(func=cmd_channels_add)
    ch_add_member = ch_sub.add_parser("add-member", help="Add a single member")
    ch_add_member.add_argument("name", help="Channel name")
    ch_add_member.add_argument("handle", help="Member handle to add")
    ch_add_member.set_defaults(func=cmd_channels_add_member)
    ch_add_team = ch_sub.add_parser("add-team", help="Add multiple members atomically")
    ch_add_team.add_argument("name", help="Channel name")
    ch_add_team.add_argument("--handles", required=True, help="Comma-separated handles")
    ch_add_team.set_defaults(func=cmd_channels_add_team)
    ch_list = ch_sub.add_parser("list", help="List channels")
    ch_list.set_defaults(func=cmd_channels_list)

    # --- chat ---
    chat = sub.add_parser("chat", help="Interactive REPL")
    chat.add_argument("--channel", required=True, help="Channel name")
    chat.set_defaults(func=cmd_chat)

    return parser


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if not hasattr(args, "func"):
        parser.print_help()
        return 0
    try:
        return args.func(args)
    except Exception as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    sys.exit(main())
