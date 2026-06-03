---
description: Blueprint pipeline — assemble blueprint.json from a target application via inspector → mapper → builder → validator
argument-hint: <absolute path to the target project>
---

# /blueprint — Blueprint Collector pipeline

You are the **orchestrator** of the Blueprint pipeline. You receive an application path from the user, sequentially invoke four subagents via the `Agent` tool (Task), and stop on any step failure. The output is five files in `agents_datasets/output/` plus a final report.

## Parameters from the user
$ARGUMENTS

Parsing:
- First argument — `target` (required, absolute path to the root of the project being analyzed).

If `target` is not provided or does not exist — ask the user and stop.

## Step 0. Preliminary checks

```bash
test -d "$target" || echo "Target not a directory"
project_name=$(basename "$target")

# Find agents_datasets/ — typically in the current working directory
agents_dir=$(find "$PWD" -maxdepth 3 -type d -name 'agents_datasets' 2>/dev/null | head -n1)
[ -z "$agents_dir" ] && { echo "ERROR: agents_datasets/ folder not found"; exit 1; }
output_dir="$agents_dir/output"
mkdir -p "$output_dir"
```

## Step 0.5. Auto-regenerate rules from cms (if available)

**Goal:** if the user/maintainer has a local copy of cms — refresh `rules/*.md` from the current entity files before launching the pipeline. This guarantees that new columns/UNIQUEs/seeds from cms are immediately taken into account.

```bash
# Find local cms — typical paths relative to the current project
cms_path=""
for candidate in \
  "$(dirname "$agents_dir")/cms" \
  "$(dirname "$(dirname "$agents_dir")")/cms" \
  "$(dirname "$(dirname "$(dirname "$agents_dir")")")/msvc/cms" \
  "${ONEENTRY_PLATFORM_PATH:-}"; do
  [ -z "$candidate" ] && continue
  if [ -d "$candidate/src/modules" ]; then
    cms_path="$candidate"
    break
  fi
done

if [ -n "$cms_path" ] && [ -f "$agents_dir/scripts/gen-rules.py" ]; then
  echo "Found cms at $cms_path — regenerating rules..."
  python3 "$agents_dir/scripts/gen-rules.py" --cms-path "$cms_path" 2>&1 | tail -10
  echo "Rules regenerated. If anything changed — commit and push agents_datasets/rules/."
else
  echo "cms not found locally — using shipped rules from agents_datasets/rules/ as-is."
fi
```

**Behavior:**
- If cms is found (typical scenario for the maintainer on their dev machine) → rules are overwritten from cms, the pipeline runs with fresh data.
- If cms is NOT found (typical scenario for the end user) → the step is silently skipped, rules are used as-is from git.

⚠ **If you are the maintainer and saw changes in `git diff agents_datasets/rules/` after this step** — be sure to commit and push, otherwise users' rules will remain stale.

Write a startup block to `$output_dir/$project_name.log.md`:
```markdown
# Blueprint pipeline log — <project_name>

**Target:** <target>
**Started:** <timestamp>

## 1. Inspector
...
```

## Step 1. Code Inspector

Invoke via the `Agent` tool with `subagent_type: 'code-inspector'`:

```yaml
target: '<absolute path>'
project_name: '<slug>'
output_dir: '<output_dir>'
```

If the subagent returned `status: FAIL` — stop, append to the log, return "Inspector failed: <reason>" to the user.

If `status: OK` — append to the log:
```markdown
## 1. Inspector — DONE
- Output: <output_dir>/<project>.inspector.yaml
- Stats: <domain_entities=N, pages=N, forms=N>
- Warnings: <N>
```

## Step 1.5. ⚠ Deterministic post-inspector fixer (REQUIRED)

```bash
python3 <agents_datasets>/scripts/post-inspector-fixer.py \
    <output_dir>/<project>.inspector.yaml \
    <project_root>
```

Fixes **deterministically** (without LLM instability):
1. **Title-mapping bug** — each block's title comes from ITS OWN source file (fixes mis-mapping WomenCollection ↔ NewArrivals).
2. **Inline blocks** — `recently_viewed`/`wishlist` via Redux state + JSX render in pages/*.tsx.
3. **404 page** — added if `NotFoundPage.tsx` is found.

Log:
```markdown
## 1.5. Post-inspector fixer — DONE
Applied N fixes:
  - <list from script output>
```

## Step 2. Entity Mapper

Invoke `Agent` with `subagent_type: 'entity-mapper'`:

```yaml
input_file: '<output_dir>/<project>.inspector.yaml'
output_dir: '<output_dir>'
project_name: '<slug>'
```

Analyze the output and append to the log.

## Step 2.5. ⚠ Deterministic post-mapper fixer (REQUIRED)

```bash
python3 <agents_datasets>/scripts/post-mapper-fixer.py \
    <output_dir>/<project>.mapped.yaml \
    <project_root>
```

Fixes structural regressions in the mapper:
1. **`isVisible: true`** on each schema-item (otherwise attributes are "hidden" in the admin UI and the edit form is empty).
2. **404 page** — double safety (in case post-inspector-fixer didn't run / the inspector didn't pick up this fix).
3. **Hub/catalog titles** — fills null titles from `title-derivations.json` → `hub_titles` (cart→Shopping Cart, accessories→Accessories) AND from `composite_catalog` for `{gender}-{category}` leaves (women-accessories→"Women's Accessories", men-shoes→"Men's Shoes"). See `oneentry-invariants.md` §18 «Justified exceptions».
4. **user user_group** — created if there are auth-providers and it is missing.
5. **orders_storage.form** → form with type='order' (not signin).

Log:
```markdown
## 2.5. Post-mapper fixer — DONE
Applied N fixes:
  - <list from script output>
```

## Step 3. Blueprint Builder (deterministic Python)

⚠ **As of 2026-06-02 the builder is a deterministic Python script**, not an AI
agent. The previous AI builder silently dropped tables it didn't know about
(slides / menus / discounts / page_errors / etc.) — the Python version cannot
drift because it hoists every whitelisted table from mapped.yaml in a fixed
order.

```bash
python3 "$agents_dir/scripts/build-blueprint.py" \
  "$output_dir/$project_name.mapped.yaml" \
  "$output_dir/$project_name.blueprint.json" \
  2>&1 | tee -a "$output_dir/$project_name.log.md"
```

The script writes:
- `$output_dir/$project_name.blueprint.json` — final blueprint
- `$output_dir/$project_name.blueprint.json.builder-warnings.json` — dedup +
  table-filter warnings sidecar

If exit code is non-zero — **STOP** and report the error to the user.

## Step 4. Blueprint pre-load validator (deterministic Python)

⚠ **As of 2026-06-02 the validator is `scripts/validate-blueprint.py`**, not
an AI agent. It runs 12 deterministic checks (CHK-001..012) that catch the
gap patterns previously discovered only after a successful but empty admin
UI: missing slides, unbound menus, dropped post_import_* arrays, unresolved
`@token` references, missing `validators[lang]`, orphan forms.

```bash
python3 "$agents_dir/scripts/validate-blueprint.py" \
  "$output_dir/$project_name.blueprint.json" \
  --mapped "$output_dir/$project_name.mapped.yaml" \
  > "$output_dir/$project_name.validation.md" 2>&1
exit_code=$?
```

Append to `$project_name.log.md`:
```markdown
## 4. Validator — DONE
- Status: PASS (exit 0) / FAIL (exit 2)
- Errors: <N from validation.md>
- Warnings: <N from validation.md>
- Report: <output_dir>/<project>.validation.md
```

Exit codes:
- `0` — all checks pass, blueprint is safe to import
- `2` — at least one ERR-level check failed, do NOT import as-is
- `1` — user error (file not found, bad JSON)

## Step 4.5. ⚠ Self-healing loop (if the validator returned FAIL)

**Do NOT return NOT READY to the user** until you have tried auto-fix. The pipeline should attempt to resolve **known error patterns** on its own before shifting responsibility to the user.

### 4.5.1 Recognized patterns and auto-fixes

| Validator error | Root cause | Auto-fix |
|---|---|---|
| **S27** "unknown column `X` for table `Y`" | Builder placed a column that doesn't exist in `table-columns.md` OR `table-columns.md` is incomplete (doesn't account for inheritance). | 1. Query the real DB (if accessible) — does column `X` exist in table `Y`. <br>2. If the **DB has it**, `table-columns.md` **doesn't** → this is a `gen-rules.py` bug. Don't block the user — manually append the column to `table-columns.md` (as a hot-patch), flag it as a warning for the maintainer. <br>3. If the **DB doesn't have it** and builder set it — this is a builder/mapper bug. Remove the field from the corresponding rows, re-run the validator. |
| **S44** "`general_type_marker` remains in JSON" | Builder forgot to remove it. | Remove the field, re-run the validator. |
| **S47** "title 'X' matches type Y, but block has generic id Z" | Mapper classified incorrectly. | Hot-fix: change the block's `general_type_id` to the expected one (Y) directly in blueprint.json. Better — re-run the mapper with a hint about the specific block. |
| **S46-final** "block contains 'kind' field" | Builder forgot to remove `kind`. | Remove the field, re-run the validator. |
| **S20** "user_groups contains preseeded 'guest'" | Mapper created it. | Remove the row from `user_groups[]`, update FK tokens `@ug.guest` → literal `1`. |

### 4.5.2 Self-healing algorithm

```
attempt = 0
max_attempts = 3
while validator_status == FAIL and attempt < max_attempts:
    attempt += 1
    for error in validator.errors:
        pattern = match_known_pattern(error)
        if pattern:
            apply_autofix(pattern, error)
        else:
            unfixable.append(error)

    if unfixable:
        break    # don't loop on unresolvable ERRORs

    rerun(validator)

if validator_status == PASS:
    log "Pipeline recovered: applied N auto-fixes (see detail in log.md)"
elif unfixable:
    log "Pipeline could not fix: {unfixable}. These are maintainer-level bugs."
```

### 4.5.3 Logging in `<project>.log.md`

```markdown
## 4.5. Self-healing loop

**Triggered** after validator FAIL (attempt 1).

### Recognized patterns
- S27 templates.attribute_set_id (6 rows) — mismatch table-columns.md ↔ entity inheritance
  - **Auto-fix**: add `attribute_set_id`, `attributes_sets` to `table-columns.md` section `templates` (inherited from BaseAttributeSetsAbstractEntity)
  - **Maintainer-action**: update `gen-rules.py` to parse `extends BaseAttributeSetsAbstractEntity`

### Re-validation after fixes
- Status: PASS

### Summary
- Auto-fixes applied: 1
- Maintainer issues remaining: 1 (as warning, does not block the pipeline)
```

### 4.5.4 When to escalate to the user

- **Don't escalate ERRORs that you fixed automatically** — the user shouldn't see them.
- If the auto-fix didn't help — escalate as before, but with a **specific instruction**: "the pipeline tried X, it didn't work, do Y manually".
- Maintainer issues (rule/agent bugs) — a separate "Actions for maintainer" section in the final report, **not for the project user**.

## Step 5. ⚠ Import + Post-import orchestration (OPTIONAL, if a target OneEntry Platform is available)

### 5.1 Import the blueprint into the target OneEntry Platform

If the user has access to a OneEntry Platform instance (`TARGET_CMS_API_URL` + login/password) — upload the blueprint:

```bash
TOKEN=$(curl -s "$TARGET_CMS_API_URL/auth/login" -X POST \
    -H 'Content-Type: application/json' \
    -d "{\"login\":\"$TARGET_LOGIN\",\"password\":\"$TARGET_PASSWORD\"}" \
    | python3 -c "import sys,json; print(json.load(sys.stdin)['accessToken'])")

curl -X POST "$TARGET_CMS_API_URL/import/from-blueprint?auto_positions=true&dry_run=false" \
    -H "Authorization: Bearer $TOKEN" \
    -H 'Content-Type: application/json' \
    --data-binary @<output_dir>/<project>.blueprint.json
```

If HTTP 201 — proceed to the final report. If ERROR — escalate as FAILED.

> **Since 2026-05-21:** `user_permissions`, `user_group_permissions_mn`,
> `form_module_config`, `collections`, `collection_rows` are now **in the whitelist**
> of the blueprint-loader and are applied in a single HTTP call. The old `post-import-orchestrator.py`
> can be used as a fallback for **very old** OneEntry Platform instances where these tables
> are not yet in the whitelist — otherwise it only generates a TG notification.

### 5.2 OAuth credentials (the only manual step)

If `users_auth_providers` contains `type=social` (google/apple/facebook) — the admin must:

1. OneEntry Platform UI → **Settings → Auth Providers → <provider>**
2. Fill in `config`: `client_id`, `client_secret`, `redirect_uri`
3. Obtain them in the provider's console (Google Cloud, Apple Developer, Facebook Developers)

Without this, social login does not work (secrets physically cannot be placed in the blueprint).

The following also require manual configuration (if applicable to the project):
- **Payment accounts**: Settings → Payment Accounts → Stripe/Yookassa API keys
- **SMTP / notice-service**: for processing_type=email forms

⚠ If `TARGET_CMS_API_URL` is not set — **skip step 5.1**, give the user manual upload instructions.

## Step 6. Final report

⚠ **Output logic (after self-healing):**

| Builder | Validator initial | After self-healing | Verdict | What to tell the user |
|---|---|---|---|---|
| OK | PASS | — | ✅ READY | "blueprint.json is ready to upload" |
| OK | FAIL | PASS (auto-fix worked) | ✅ READY | "blueprint.json is ready; the pipeline self-fixed N issues (see log)" |
| OK | FAIL | FAIL (could not fix) | ❌ NOT READY | "blueprint.json was created, the validator found N **non-auto-fixable** errors. Details in log.md → section 'Actions for maintainer'. **This is a maintainer task, not yours.**" |
| FAIL | — | — | ❌ FAILED | "Pipeline stopped at builder self-check. This is a maintainer bug." |

On **NOT READY** or **FAILED**, be sure to write in large text "**Do NOT upload blueprint.json to OneEntry — it contains errors that will break the import**" plus a note that this is a **maintainer task**.

Final message:

```markdown
## Blueprint pipeline — <project_name>

> ⚠️ **Disclaimer (always show this to the user, regardless of status):**
> This agent is powered by AI instructions and scripts, so errors may occur during Blueprint generation. Please verify the resulting data and structure after import.

**Target:** <target>
**Status:** ✅ READY / ❌ NOT READY / ❌ FAILED

### ⚠ Can blueprint.json be uploaded?
**YES** (if READY) / **NO** (if NOT READY/FAILED) — <reason in one line>

### Files
- Blueprint JSON: <output_dir>/<project>.blueprint.json (<size> bytes) — or "not created" if FAILED
- Inspector YAML: <output_dir>/<project>.inspector.yaml
- Mapped YAML:    <output_dir>/<project>.mapped.yaml
- Log:            <output_dir>/<project>.log.md
- Validation:     <output_dir>/<project>.validation.md

### Stats
- Tables: <list of table:count>
- Inspector entities: <N>
- Pages: <N>
- Products: <N>

### Validation
- Static: PASS/FAIL (<N errors, M warnings>)
- (If FAIL) Top errors: <first 5 lines from the errors section of validation.md>

### What to do next
- **READY** → Upload `blueprint.json` to OneEntry Platform (`POST /api/admin/import/from-blueprint`).
- **NOT READY** → Open `validation.md`, fix the causes of the errors (often this means correcting the entities recognized by the inspector, or reformulating the `target` project).
- **FAILED** → Notify the maintainer — it's a bug in the agents, not in your project.

### Known warnings
- ...
```

## Hard rules

1. **Don't write code manually** — everything goes through the 4 subagents.
2. **Don't fail on validator FAIL** — give the report to the user, let them iterate.
3. **All paths are absolute.**
4. **Don't edit files created by subagents** — only read and log.
5. **Always include the AI disclaimer in the final report**, regardless of status (READY / NOT READY / FAILED). Render it as a visually distinct callout (`> ⚠️ ...`) near the top of the message so the user cannot miss it. Exact wording:
   > This agent is powered by AI instructions and scripts, so errors may occur during Blueprint generation. Please verify the resulting data and structure after import.

## Error behavior

| Stage | Error | Action |
|---|---|---|
| Inspector | failed | Stop. Verdict ❌ FAILED, reason. |
| Mapper | failed | Stop. Verdict ❌ FAILED. |
| Builder | failed (self-check) | Stop — do NOT run validator (no file). Verdict ❌ FAILED, errors in report. |
| Validator | static FAIL | Don't stop. Write validation.md, give to user with verdict ❌ NOT READY. **JSON was created, but must not be uploaded.** |
| Everything OK | — | Verdict ✅ READY, blueprint.json ready for upload. |
