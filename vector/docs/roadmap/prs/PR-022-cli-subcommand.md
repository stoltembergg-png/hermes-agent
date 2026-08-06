# PR-022: Register `hermes vector` CLI subcommand

## Depends on
PR-016

## Problem
The vector CLI exists in `vector/src/vector/cli.py` (argparse + REPL with `agents add`, `agents list`, `channels add`, `channels add-member`, `chat`, etc.) but is not registered as a Hermes subcommand. Users cannot run `hermes vector agents add gandalf`.

## Requirements

### REQ-VEC-022-1: Register `vector` subcommand
Register `vector` in `hermes_cli/commands.py` `COMMAND_REGISTRY` as a passthrough subcommand. The handler delegates to `vector.cli.main(sys.argv[3:])` so users can run:
- `hermes vector agents add gandalf --system-prompt "..."`
- `hermes vector agents list`
- `hermes vector channels add dev-team --members human,gandalf`
- `hermes vector channels list`
- `hermes vector chat dev-team`

### REQ-VEC-022-2: Handler in cli.py
Add handler in `HermesCLI.process_command()`:
```python
elif canonical == "vector":
    args = cmd_original.split(None, 1)[1:] if len(cmd_original.split()) > 1 else []
    from vector.cli import main as vector_main
    vector_main(args)
```

### REQ-VEC-022-3: Help text
The `CommandDef` for `vector` MUST have:
- `description`: "Multi-agent channels: agents, channels, mentions, dispatch"
- `args_hint`: `"<subcommand> [args]"`
- `category`: `"Tools & Skills"`

### REQ-VEC-022-4: Gateway availability
The `vector` command SHOULD be available in the gateway (messaging platforms). Set `gateway_config_gate` to `vector.enabled` so it's only available when the vector plugin is enabled.

### REQ-VEC-022-5: CLI tests
Add tests in `tests/hermes_cli/` that verify `hermes vector agents list` runs without error (uses FakeDelegate, temp HERMES_HOME).

## Acceptance Criteria

- AC-VEC-022-1: `hermes vector agents add gandalf --system-prompt "test"` creates an agent
- AC-VEC-022-2: `hermes vector agents list` shows registered agents
- AC-VEC-022-3: `hermes vector channels add dev-team --members human,gandalf` creates a channel
- AC-VEC-022-4: `hermes vector channels list` shows channels with member counts
- AC-VEC-022-5: `hermes vector` with no args shows usage help

## Implementation Plan

### Files
- `hermes_cli/commands.py` (~+5 LoC)
- `cli.py` (~+15 LoC)
- `gateway/run.py` (~+10 LoC)
- `tests/hermes_cli/test_vector_cli.py` (NEW)

### Steps
1. Add `CommandDef("vector", "Multi-agent channels: agents, channels, mentions, dispatch", "Tools & Skills", aliases=("vec",), args_hint="<subcommand> [args]", gateway_config_gate="vector.enabled")`
2. Add handler in `process_command()` that passes remaining args to `vector.cli.main()`
3. Add gateway handler in `run.py` — same passthrough
4. Ensure `vector.cli.main()` works standalone (imports from `vector.src.vector`)
5. Write E2E test using `subprocess.run(["python", "-m", "hermes", "vector", "agents", "list"])` with temp `HERMES_HOME`

test_file: tests/test_pr_022.py
