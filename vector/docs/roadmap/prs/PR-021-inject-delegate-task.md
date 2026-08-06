# PR-021: Inject real delegate_task for LLM responses

## Depends on
PR-011

## Problem
The `AgentRuntime` uses `FakeDelegate` by default, which returns a stub JSON string. When a user mentions `@gandalf` in a channel, the agent does not produce a real LLM response. The vector is a working UI with no actual AI.

## Requirements

### REQ-VEC-021-1: Inject delegate_task in plugin_api.py
The `plugin_api.py` `_get_service()` function MUST inject the real `delegate_task` from `tools.delegate_tool` when it is available in the Hermes environment. Fall back to `FakeDelegate` only when `delegate_task` cannot be imported (standalone testing).

### REQ-VEC-021-2: AgentRuntime delegate adaptation
The `AgentRuntime` MUST wrap `delegate_task` in an adapter that translates the vector protocol into `delegate_task(goal=..., context=..., role="leaf")`:
- `goal`: the composed prompt (system prompt + channel history + mention body)
- `context`: a summary of the channel context (other members, recent messages)
- `role`: always "leaf" (agents cannot delegate further — REQ-VEC-005-4)

### REQ-VEC-021-3: Response timeout
The delegate call MUST have a configurable timeout (default: 120s). If the delegate exceeds the timeout, the dispatcher records a timeout error message in the channel as the agent's response.

### REQ-VEC-021-4: Model resolution
When an agent has `model` and `provider` set, the delegate adapter MUST pass them via the `goal` context or a Hermes-specific parameter. When they are `None`, the delegate uses the session default.

### REQ-VEC-021-5: FakeDelegate stays for tests
`FakeDelegate` MUST remain the default when `delegate_task` is not importable (e.g. missing dependencies, test environment). Tests that only need the dispatch logic use `FakeDelegate` — no LLM calls.

## Acceptance Criteria

- AC-VEC-021-1: When Hermes backend is running, mentioning `@gandalf` produces a real LLM response
- AC-VEC-021-2: FakeDelegate is used when delegate_task import fails (test mode)
- AC-VEC-021-3: Agent with custom model/provider uses that model for responses
- AC-VEC-021-4: Timeout produces an error message in the channel (not a crash)
- AC-VEC-021-5: Existing tests pass without modification (they use FakeDelegate)

## Implementation Plan

### Files
- `plugins/vector-channels/dashboard/plugin_api.py` (~+40 LoC)
- `vector/src/vector/runtime.py` (~+30 LoC)

### Steps
1. `runtime.py`: Update `FakeDelegate` to clearly indicate it's a stub in its response
2. `runtime.py`: Add `HermesDelegate` class that wraps `delegate_task`:
   ```python
   class HermesDelegate:
       def __init__(self, delegate_fn):
           self._delegate = delegate_fn
       def __call__(self, goal, context, role="leaf", **kw):
           return self._delegate(goal=goal, context=context, role=role)
   ```
3. `plugin_api.py`: In `_get_service()`, try importing `delegate_task`:
   ```python
   try:
       from tools.delegate_tool import delegate_task
       delegate = HermesDelegate(delegate_task)
   except ImportError:
       delegate = FakeDelegate()
   ```
4. Pass `delegate` to `AgentRuntime(delegate=delegate)`
5. Add timeout: wrap the delegate call in `asyncio.wait_for` or a thread timeout
6. Test E2E: ensure FakeDelegate path still works for all existing tests

test_file: tests/test_pr_021.py
