# OneEntry Blueprint AI

Automatically generate a ready-to-import **OneEntry Platform blueprint** from any web application — driven by Claude Code AI subagents.

> ⚠️ **Disclaimer**
>
> This agent is powered by AI instructions and scripts, so errors may occur during Blueprint generation. Please verify the resulting data and structure after import.

---

## What this does

You point the agent at the folder of your existing web app (Next.js, React, Vue — any). It:

1. **Inspects** your source code (pages, forms, products, categories, blocks).
2. **Maps** the entities found onto the 24 OneEntry whitelist tables.
3. **Builds** a single `<project>.blueprint.json` file.
4. **Validates** it statically (12 deterministic checks) before you upload.

The output `blueprint.json` is uploaded to OneEntry Platform via `POST /api/admin/import/from-blueprint` and you get a fully populated admin panel: pages, menus, forms, attributes, products, blocks — without typing anything by hand.

---

## Requirements

- **[Claude Code](https://claude.com/claude-code)** installed and authenticated.
- **Python 3** (for the deterministic build/validate scripts).
- A target web application folder (the project you want to onboard to OneEntry).
- A running OneEntry Platform instance to upload the result into (or any OneEntry-compatible API endpoint).

---

## Installation

Clone this repo **next to** your app folder, or anywhere — you'll pass the app path as an argument.

```bash
git clone https://github.com/<your-org>/oneentry-blueprint-ai.git
cd oneentry-blueprint-ai
```

In Claude Code, point the project to this folder (`/init` or open it as the working directory). The slash command `/blueprint` becomes available automatically — Claude Code auto-discovers `.claude/commands/*.md` and `.claude/agents/*.md`.

---

## Usage

In Claude Code, type:

```
/blueprint /absolute/path/to/your/app
```

Examples:

```
/blueprint /Users/me/projects/my-next-shop
/blueprint /home/dev/work/restaurant-site
```

The pipeline runs four agents in sequence:

```
code-inspector → entity-mapper → blueprint-builder → blueprint-validator
```

When done you'll see one of three verdicts:

- ✅ **READY** — `output/<project>.blueprint.json` is safe to upload.
- ❌ **NOT READY** — validation found errors; check `output/<project>.validation.md`.
- ❌ **FAILED** — pipeline crashed early; report it as an issue.

---

## Output

All artifacts land in `output/`:

```
output/
├── <project>.inspector.yaml        ← raw entities discovered in your code
├── <project>.mapped.yaml           ← entities mapped to OneEntry's 24 tables
├── <project>.blueprint.json        ← FINAL — upload this one
├── <project>.validation.md         ← static validation report
└── <project>.log.md                ← full pipeline log
```

Upload `<project>.blueprint.json` to your OneEntry Platform:

```bash
curl -X POST "$ONEENTRY_API_URL/api/admin/import/from-blueprint?dry_run=false" \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  --data-binary @output/my-project.blueprint.json
```

Or use the OneEntry admin panel: **Settings → Import → Blueprint**.

> Tip: always do `dry_run=true` first.

---

## Folder map

| Folder                             | What it is                                                                               | Edit it?        |
| ---------------------------------- | ---------------------------------------------------------------------------------------- | --------------- |
| `.claude/agents/`                          | The 5 AI subagent prompts (Inspector, Mapper, Builder, Validator, Auditor)               | No              |
| `.claude/commands/blueprint.md`            | The `/blueprint` slash command — pipeline orchestrator                                   | No              |
| `rules/`                           | Business rules: attribute types, OneEntry invariants, entity patterns                    | Maintainer only |
| `rules/generated/`                 | Auto-generated from the OneEntry Platform source (table whitelist, FK, NOT NULL)         | Auto            |
| `scripts/`                         | Deterministic Python: `build-blueprint.py`, `validate-blueprint.py`, post-import helpers | No              |
| `templates/minimal-blueprint.json` | Reference structure for the BlueprintDto schema                                          | No              |
| `ClaudeInfos/`                     | Background reference about the OneEntry data model                                       | No              |
| `output/`                          | Your generated blueprints land here (gitignored)                                         | Yours           |

---

## OAuth / payment secrets

Some things **cannot** be auto-generated and must be entered manually in the OneEntry admin panel after import:

- Social auth credentials (Google / Apple / Facebook `client_id` + `client_secret`)
- Payment provider API keys (Stripe, Yookassa, etc.)
- SMTP credentials for `notice-service`

This is by design — secrets must never live in a blueprint file.

---

## Troubleshooting

| Symptom                                         | Try this                                                                                                                |
| ----------------------------------------------- | ----------------------------------------------------------------------------------------------------------------------- |
| `/blueprint` command not visible in Claude Code | Make sure you're inside this repo's folder; check `.claude/commands/blueprint.md` exists                                        |
| Validator reports `NOT READY`                   | Open `output/<project>.validation.md` — top of the file lists the errors with line refs                                 |
| Pipeline picks up wrong entities                | Refine your app's component / page naming; or open `output/<project>.inspector.yaml` and rerun the later steps manually |
| Want to regenerate `rules/generated/`           | Only the maintainer can — they need a local copy of the OneEntry Platform source                                        |

---

## Contributing

The agents (`.claude/agents/*.md`), rules (`rules/*.md`) and scripts (`scripts/*.py`) are versioned together. If you hit a bug — open an issue with:

- Your `output/<project>.log.md`
- Your `output/<project>.validation.md`
- A short description of what went wrong vs. expected

PRs welcome for new entity patterns, fixes to mapper heuristics, or post-import scripts.

---

## License

MIT
