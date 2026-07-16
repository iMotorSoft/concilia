# Root Cause Debugging Policy

This policy governs non-trivial bug investigation in Concilia.

## When Required

Apply this policy when:
- Bug not reproducible in unit test
- Intermittent failure (CI flake, race condition)
- Data corruption / inconsistency
- Performance regression > 2x baseline
- Security incident

## Process

### 1. Reproduce (Time-boxed: 30 min)

- Minimal reproduction script in `scripts/debug/`
- Capture: exact input, environment, stack trace
- If not reproducible → **stop**, label "cannot reproduce", monitor

### 2. Isolate (Time-boxed: 1 hour)

| Dimension | Technique |
|-----------|-----------|
| Code path | Bisect via `git bisect` + test script |
| Data | Compare canonical parquet before/after |
| Config | Diff env vars, feature flags |
| Concurrency | Run with `PYTHONASYNCIODEBUG=1` |
| External | Mock service vs real preflight |

### 3. Hypothesize

Document in `data/reports/debug/{date}-{slug}/hypothesis.md`:

```markdown
## Hypothesis
Root cause: [specific mechanism]
Evidence: [logs, diffs, traces]
Prediction: [if fix X, then Y observable]
```

### 4. Verify

- Write failing test (unit or integration)
- Apply minimal fix
- Run focused test suite
- Run preflight if service-related

### 5. Document

Final report in `data/reports/debug/{date}-{slug}/report.md`:

```markdown
# Root Cause: [Title]

## Summary
[1 paragraph]

## Timeline
- YYYY-MM-DD HH:MM: First occurrence
- ...

## Root Cause
[Technical explanation with code references]

## Fix
[Link to PR/commit]

## Prevention
- Test added: [path]
- Monitoring: [metric/alert]
- Architecture: [ADR if needed]
```

## Tools

| Tool | Purpose |
|------|---------|
| `py-spy` | CPU profiling |
| `memray` | Memory profiling |
| `psycopg` logging | Query tracing (`DEBUG=psycopg.pool`) |
| `litestar` debug toolbar | Request/response inspection |
| Playwright trace | E2E failure analysis |
| `git bisect` | Regression isolation |

## Forbidden

- "Works on my machine" as closure
- Fix without reproduction
- Fix without test
- Silent log level changes to hide errors
- Blaming external service without preflight evidence