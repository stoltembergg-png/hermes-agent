# Feature spec — pr-009-gateway-api

test_file: tests/test_pr_009_gateway_api.py

## Acceptance criteria

AC IDs verified by scripts/verify-feature.sh:

- AC-VEC-009-1 — GET /api/vector/health returns 200, version, and storage type
- AC-VEC-009-2 — Agents and channels created via API persist after service recreation
- AC-VEC-009-3 — POST messages stores user message, dispatches @mention, stores agent response
- AC-VEC-009-4 — Non-member mention is not invoked (membership enforcement)
- AC-VEC-009-5 — Prior channel history reaches runtime via context argument
- AC-VEC-009-6 — Domain errors use stable error envelope without tracebacks
- AC-VEC-009-7 — Desktop plugin renders user and agent messages after one submission
- AC-VEC-009-8 — Desktop reload retains chronological history
- AC-VEC-009-9 — CI hermetic with no provider keys
- AC-VEC-009-10 — Failures upload complete evidence artifacts
