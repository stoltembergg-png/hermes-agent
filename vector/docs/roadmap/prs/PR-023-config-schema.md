# PR-023: Config schema for `vector:` namespace in config.yaml

## Depends on
PR-022

## Problem
There is no `vector:` section in `config.yaml`. The AGENTS.md spec calls for `vector.defaults.model`, `vector.defaults.provider`, `vector.dispatcher.max_depth`, and `vector.enabled` settings. Users have no way to configure vector defaults without editing config by hand.

## Requirements

### REQ-VEC-023-1: Default config schema
Add to `DEFAULT_CONFIG` in `cli.py`:
```yaml
vector:
  enabled: false
  defaults:
    model: null
    provider: null
    max_iterations: 50
  dispatcher:
    max_depth: 3
    timeout_seconds: 120
    mention_max_chars: 2000
  storage:
    db_path: null  # null = HERMES_HOME/vector/vector.db
    agents_yaml: null  # null = HERMES_HOME/vector/agents.yaml
```

### REQ-VEC-023-2: Config version bump
Bump `_config_version` by 1. Add migration in `_migrate_config()`:
- Old version: save current value → set new defaults for `vector:` section → update `_config_version`

### REQ-VEC-023-3: Setup wizard question
In the setup wizard (`hermes_cli/setup_wizard.py`), add a question:
"Enable Vector multi-agent channels? (y/N)"
If yes, set `vector.enabled: true`.

### REQ-VEC-023-4: Service uses config defaults
`VectorService.__init__` SHOULD read `vector.defaults.model` and `vector.defaults.provider` from config when an agent doesn't specify its own. The dispatcher reads `vector.dispatcher.max_depth` and `vector.dispatcher.timeout_seconds`.

### REQ-VEC-023-5: `hermes tools` toggle
Add `vector` to `hermes tools` toggle list so users can enable/disable vector from the tools command (not just config.yaml).

## Acceptance Criteria

- AC-VEC-023-1: Fresh `hermes setup` creates `vector:` section in config.yaml
- AC-VEC-023-2: Config migration from older version adds `vector:` section with defaults
- AC-VEC-023-3: `hermes tools` shows Vector in the list with a toggle
- AC-VEC-023-4: Agent without explicit model uses `vector.defaults.model` from config
- AC-VEC-023-5: Dispatcher respects `max_depth` from config

## Implementation Plan

### Files
- `cli.py` (~+30 LoC) — DEFAULT_CONFIG + migration
- `hermes_cli/setup_wizard.py` (~+15 LoC) — setup question
- `hermes_cli/tools_command.py` or equivalent (~+5 LoC) — tools toggle
- `vector/src/vector/service.py` (~+15 LoC) — read config defaults
- `vector/src/vector/dispatcher.py` (~+10 LoC) — read dispatcher config

### Steps
1. Add `vector` section to `DEFAULT_CONFIG` dict in `cli.py`
2. Bump `_config_version`
3. Add migration case in `_migrate_config()`:
   ```python
   if raw.get("_config_version", 0) < NEW_VERSION:
       raw.setdefault("vector", {"enabled": False, "defaults": {...}, ...})
       raw["_config_version"] = NEW_VERSION
   ```
4. In setup wizard, add vector enable question
5. In `VectorService.__init__`, accept `config: dict` param and read `vector.defaults`
6. In `Dispatcher.__init__`, read `vector.dispatcher.max_depth` and `vector.dispatcher.timeout_seconds`
7. Add `vector` to `hermes tools` toggle list

test_file: tests/test_pr_023.py
