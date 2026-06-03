# `agents_datasets/ClaudeInfos/` — documentation map

This folder is internal OneEntry CMS documentation for AI agents (not for end users). It captures **what already exists in the system**, so that when picking up a new task you don't end up proposing entities that are already modeled by existing mechanisms.

> **Scope: `cms/` (backend) only.** The frontend (`cms_frontend/`), `notice-service`, and `import-backend` are not covered here (see the respective repos).

---

## Entry rule

Whenever you pick up a new task (shop X / catalog Y / form Z / integration W):

1. **Open [`use-cases.md`](./use-cases.md)** — the primary file mapping "if you need X, use Y" (30+ cases).
2. **If nothing fits — open [`when-not-to-create-tables.md`](./when-not-to-create-tables.md)** — a list of "instead of a new table, do this".
3. **If it is still unclear** — open [`data-model-core.md`](./data-model-core.md) to understand the foundation (attribute_sets, jsonb, information_schema).

Do not propose a new table until you've gone through these three steps.

---

## File map

| File | When to read |
|---|---|
| [`use-cases.md`](./use-cases.md) | Every time. "If you need X, use Y." |
| [`when-not-to-create-tables.md`](./when-not-to-create-tables.md) | Every time the thought "let's create a new table" comes up. |
| [`data-model-core.md`](./data-model-core.md) | When you need to understand how the "flexible model" works — attribute_sets, jsonb, information_schema. |
| [`entities-catalog.md`](./entities-catalog.md) | Reference for 100+ entities in `cms/src/**/*.entity.ts`. |
| [`modules-catalog.md`](./modules-catalog.md) | Module reference: controllers, consumers, queues. |
| [`patterns-controllers.md`](./patterns-controllers.md) | Splitting controllers into admin / developer / content / base. AdminPermissionsEnum. |
| [`patterns-queues-and-ws.md`](./patterns-queues-and-ws.md) | Bull queues, consumers, WS channels. RabbitMQ in brief. |
| [`patterns-journal-blockers-versioning.md`](./patterns-journal-blockers-versioning.md) | @Journalable, advisory blockers, entity_versions. |
| [`glossary.md`](./glossary.md) | Internal terms with non-obvious or non-standard meanings. |
| [`examples/00-index.md`](./examples/00-index.md) | Top-10 practical examples: full jsonb + admin endpoint + Bull/WS. Use when you need a concrete "how exactly". |

---

## Zero-hallucination principle

In these files, **every** class / file / method / table / enum-value name has been grep-validated against the OneEntry Platform source. If you read something and aren't sure — verify it yourself against the OneEntry Platform source tree:

```bash
grep -rn "<name>" "<path-to-oneentry-platform-source>" --include="*.ts"
```

If grep returns nothing — it's either marked `TBD: verify` or it has become outdated (the repo evolves). Open the current code; don't trust the document blindly.

---

## What is NOT covered

- The frontend `cms_frontend/` (React patterns, redux, Storybook). See the root `CLAUDE.md` for context.
- `notice-service` (push/email via Firebase/APN). Separate repo.
- `import-backend` (Python FastAPI for imports). See `import-backend/README.md`.
- Individual migrations and seeds.
- Legacy repos (`cms-client-app`, `cms_provisioner`, `pushservice`, `backend_chebotarev`, `CLO`, `todos`).
- Contents of the `notion/` export (marked as "may be outdated" in the root CLAUDE.md).

---

## Relationship with the root CLAUDE.md

The root `CLAUDE.md` in `msvc/` contains general working rules (git, run commands, known bugs). The files here (`agents_datasets/ClaudeInfos/*.md`) are a deeper description of the CMS backend data model and architectural patterns.

When the root CLAUDE.md and `agents_datasets/ClaudeInfos/` disagree — the truth lives in `agents_datasets/ClaudeInfos/` (because these files are grep-validated more strictly).
