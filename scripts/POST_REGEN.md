# What to do after running `gen-rules.py`

> ⚠ **MAINTAINER-ONLY**. This guide is for the **maintainer** of `agents_datasets/` who ran the rules auto-generator from the `cms/` repo (sibling of `agents_datasets/` in the msvc monorepo). All `cms/...` paths mentioned below exist only in the maintainer's msvc-env — they are NOT present in shop environments where `agents_datasets/` is consumed by AI agents.

---

## Rule architecture

The project has two rule folders:

```
agents_datasets/rules/
├── attribute-types-mapping.md    ← MANUAL (edit yourself)
├── oneentry-invariants.md        ← MANUAL
├── coverage-checklist.md         ← MANUAL
├── standard-entities.md          ← MANUAL
│
└── generated/                    ← AUTO (gen-rules.py overwrites)
    ├── whitelist-tables.md
    ├── table-columns.md
    ├── unique-constraints.md
    └── preseeded-entities.md
```

**Rule:** the auto-generator writes ONLY to `rules/generated/`. If you manually edit a file there — the next script run will overwrite your changes. If you edit a file in the `rules/` root — the script leaves it alone.

---

## Step 1. Run gen-rules.py

```bash
cd "<path-to-agents_datasets>"
python3 scripts/gen-rules.py

# Or first a dry-run to see what would change without writing:
python3 scripts/gen-rules.py --dry-run
```

The script automatically looks for cms at `../cms` by default. If it's located elsewhere:
```bash
python3 scripts/gen-rules.py --cms-path /path/to/cms
```

---

## Step 2. Review what changed

```bash
git diff agents_datasets/rules/generated/
```

The diff will show changes only in 4 files:
- `rules/generated/table-columns.md`
- `rules/generated/unique-constraints.md`
- `rules/generated/preseeded-entities.md`
- `rules/generated/whitelist-tables.md`

Files in the `rules/` root (4 manual ones) should NOT appear in the diff. If they do — that was your manual edit, unrelated to the regeneration.

---

## Step 3. Verify that nothing broke

After regeneration, **new checks** or **new columns** may appear that the validator now accounts for. Verify this on a test project:

```
/blueprint /path/to/test/project
```

If new ERROR/WARNING entries appeared in `validation.md`:
- **New column in S27** → fine, the agent became more precise.
- **New UNIQUE in S21** → fine, a check was added.
- **Real regression in your project** → fix it.

---

## Step 4. If a NEW whitelist table was added to cms

The script works from the `WHITELIST_TABLES` list in `gen-rules.py`. If a new table was added to `ALLOWED_TABLES` in `cms/src/modules/import/sevices/blueprint/blueprint-loader.service.ts` — you must manually:

1. Add it to `WHITELIST_TABLES` in `gen-rules.py`.
2. Add the path to its entity in `ENTITY_PATHS`.
3. If it extends `BaseAttributeSetsAbstractEntity` — add it to `ATTR_SETS_EXTENDED`.
4. Re-run `gen-rules.py`.
5. Verify via `--dry-run` that the entity is parsed: you should see `✓ <new_table>: N cols, ...`.

---

## Step 5. Commit and push

```bash
git add agents_datasets/rules/generated/ agents_datasets/scripts/
git commit -m "regenerate rules from cms (changes: <short description>)"
git push
```

Users will receive fresh rules via `git pull` or a fresh download.

---

## When to run gen-rules.py

| When | What to do |
|---|---|
| After any `git pull` of cms | Run, review the diff |
| Before releasing agent updates | Run, make sure the rules are fresh |
| After adding a new entity column to cms | Run, verify it was picked up |
| Once a month | Run just for hygiene |
| Before every `/blueprint` | **Not needed** — step 0.5 in `.claude/commands/blueprint.md` already does it (if cms is found locally) |

---

## What's built into gen-rules.py

The script regenerates **fully self-contained** files. Each regenerated file contains:
- Auto data (column lists, UNIQUE keys, NOT NULL, INSERTs)
- **Embedded manual sections** (business logic, usage examples, ready-made python snippets for the validator/builder)

For example, `generated/unique-constraints.md` after regeneration contains:
- ✅ List of UNIQUE keys (auto)
- ✅ Deduplication algorithm with DEDUPE_RULES (auto + hardcoded template)
- ✅ Duplicate-drop semantics (hardcoded template in gen-rules.py)
- ✅ What the builder must do (hardcoded template)
- ✅ What the S21 validator must do (hardcoded template)
- ✅ Anti-patterns (hardcoded template)

In other words, **manual sections don't disappear** — they are baked into the generator templates. If you want to add a new one — edit the `gen_*_md()` functions in `scripts/gen-rules.py`.

---

## If something goes wrong

### The script crashed with an error

```bash
# Verify the cms path is correct (set OneEntry Platform source path)
python3 agents_datasets/scripts/gen-rules.py --cms-path "<path-to-oneentry-platform-source>" --dry-run
```

If you see `✗ <table>: NOT FOUND` — the entity file was not found, check the path in `ENTITY_PATHS`.

### Important info disappeared from a regenerated file

This means a manual section that used to be in the file is **not embedded in the gen-rules.py template**. Decide:
- If this info should always live in `rules/generated/<file>.md` → add it to the template in `gen-rules.py` (`gen_*_md` method), re-run.
- If this info is general business logic → move it to `rules/coverage-checklist.md` or `rules/oneentry-invariants.md` (they are NOT regenerated).
- If this info is an instruction for a specific agent → move it to `.claude/agents/blueprint-{builder,validator}.md`.

### Roll back the regeneration

```bash
git checkout agents_datasets/rules/generated/
```

---

## Post-regeneration checklist

- [ ] `python3 scripts/gen-rules.py` ran without errors (all 24 tables `✓`)
- [ ] `git diff rules/generated/` shows meaningful changes
- [ ] Files in the `rules/` root did NOT change (only `generated/`)
- [ ] Test `/blueprint` ran without new regressions
- [ ] `git commit && git push` is done
