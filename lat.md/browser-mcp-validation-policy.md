# Browser MCP Validation Policy

This policy governs browser-based validation using Playwright + Chromium in Concilia.

## Gate Definition

**Playwright + Chromium is the E2E gate**. Browser MCP is exploratory only.

| Tool | Purpose | Gate |
|------|---------|------|
| Playwright + Chromium | Regression, CI, release blocker | ✅ Required PASS |
| Browser MCP | Exploration, debugging, ad-hoc | ❌ Not a gate |

## Test Organization

```
clientA/e2e/
├── fixtures/           # Test data (upload files)
├── pages/              # Page Object Models
│   ├── UploadPage.ts
│   ├── WizardPage.ts
│   └── ResultsPage.ts
├── specs/
│   ├── upload.spec.ts
│   ├── wizard.spec.ts
│   ├── reconciliation.spec.ts
│   └── a11y.spec.ts
├── utils/
│   └── auth.ts         # Login helper using env creds
└── playwright.config.ts
```

## Test Requirements

### Authentication

- Credentials via `CONCILIA_E2E_ADMIN_EMAIL` / `CONCILIA_E2E_ADMIN_PASSWORD`
- Tests **skipped** (not failed) if credentials absent
- Separate test user, not production admin

### Data Isolation

- Each test uploads its own files
- Cleanup via `afterEach` (delete uploads via API)
- No shared state between tests

### Assertions

- **Visual**: Snapshot only for layout regression (opt-in)
- **Functional**: DOM state, API responses, computed values
- **Performance**: `page.waitForLoadState('networkidle')` + custom metrics

## CI Integration

```yaml
# .github/workflows/e2e.yml
- name: Preflight
  run: uv run scripts/preflight.py --all
- name: Build frontend
  run: cd SrvRestAstroLS_v1/clientA && pnpm build
- name: Start servers
  run: |
    ./SrvRestAstroLS_v1/backend-dev.sh start
    ./SrvRestAstroLS_v1/astro-dev.sh start
- name: E2E
  env:
    CONCILIA_E2E_ADMIN_EMAIL: ${{ secrets.CONCILIA_E2E_ADMIN_EMAIL }}
    CONCILIA_E2E_ADMIN_PASSWORD: ${{ secrets.CONCILIA_E2E_ADMIN_PASSWORD }}
  run: cd SrvRestAstroLS_v1/clientA && pnpm test:e2e
```

## Local Execution

```bash
# Start servers
./SrvRestAstroLS_v1/backend-dev.sh start
./SrvRestAstroLS_v1/astro-dev.sh start

# Run E2E (requires credentials)
CONCILIA_E2E_ADMIN_EMAIL=... \
CONCILIA_E2E_ADMIN_PASSWORD=... \
cd SrvRestAstroLS_v1/clientA && pnpm test:e2e

# Debug headed
pnpm test:e2e --headed --debug
```

## Browser MCP Usage

- **Allowed**: Exploring new flows, debugging flaky tests, visual inspection
- **Not allowed**: Replacing Playwright tests, CI validation, release decisions
- **Output**: Saved to `data/reports/browser-mcp/{timestamp}/`

## Flaky Test Protocol

1. Run 3x locally → if flaky, investigate root cause
2. Add `test.retry(2)` only after root cause documented
3. File issue with `flaky` label
4. Fix or quarantine within 1 sprint

## Forbidden

- `page.waitForTimeout()` as primary wait (use `waitForSelector`, `waitForResponse`)
- Hardcoded `localhost:3058` (use `baseURL` from config)
- Production credentials in CI secrets (use dedicated test account)
- Browser MCP screenshots as test evidence