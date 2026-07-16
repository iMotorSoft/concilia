# Lat Documentation Policy

This policy governs the Living Architecture (LAT) documentation in `lat.md/`.

## Principles

- **Single canonical source**: Each architectural concern has exactly one LAT document.
- **Code anchors**: Source code references LAT docs via `@lat:doc-name` comments.
- **Living**: LAT docs are updated when architecture changes; they are not append-only logs.
- **Validated**: `lat check` verifies link resolution and structural integrity.

## Document Lifecycle

1. **Propose**: New concern → create `lat.md/concern-name.md` with `status: draft`
2. **Review**: Team validates against implementation
3. **Adopt**: Change `status: canonical`, add to `lat.md/lat.md` index
4. **Maintain**: Update on every architectural change to the concern

## Naming Convention

- File: `kebab-case.md` (e.g., `sicom-integration-policy.md`)
- Reference: `@lat:sicom-integration-policy`
- Title: PascalCase in YAML frontmatter (optional)

## Required Frontmatter

```yaml
---
title: "SICOM Integration Policy"
status: canonical
owner: "@concilia-team"
last_reviewed: "2026-07-16"
---
```

## Link Resolution

- `[[doc-name]]` → `lat.md/doc-name.md` (relative wiki-link)
- `@lat:doc-name` → code anchor, resolved by `lat check`
- External refs use full URLs

## Forbidden

- Duplicate concerns across multiple LAT files
- Runtime status in LAT (use `SrvRestAstroLS_v1/docs/status_actual.md`)
- Implementation details that belong in code comments
- Unresolved `[[...]]` or `@lat:` references

## Validation

`lat check` runs on:
- CI for `lat.md/` changes
- Pre-commit for `@lat:` changes in code
- Manual before merging architecture-affecting PRs

Checks:
- All `[[...]]` resolve to existing files
- All `@lat:` in code resolve to canonical LAT docs
- Frontmatter present and valid
- No circular dependency chains > 3 hops