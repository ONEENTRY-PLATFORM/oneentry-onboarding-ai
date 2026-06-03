# Post-Import Orchestration — out-of-whitelist automation

> **⚠ Universality note.** Examples below frequently use fashion-shop terms (clothing / shoes / bags / women / men) because that is the reference test project. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop (`product/sku/brand/category`), restaurant (`menu-item/dish/cuisine/section`), beauty salon (`service/master/treatment/duration`), hotel (`room/suite/amenity`), EdTech (`course/lesson/level`), corporate site (`page/department/team`), personal cabinet (`section/setting/subscription`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is hand-written and universal across projects.** It describes what the pipeline does **after** a blueprint has been successfully loaded via `POST /api/admin/import/from-blueprint`. It is not edited by the auto-generator.

## Why

Several OneEntry entities are not in the 24-table whitelist of the blueprint-loader, yet are needed for a production-ready import:

- `markers` — tags/markers on products/pages
- `menus` + `menu_pages_mn` — navigation menus
- `filters` + `filter_items_mn` + `filter_custom_items_mn` — catalog facets
- `payment_accounts` — Stripe/Yookassa/etc (only partially — without secrets)
- `events` + templates — email/push notifications
- `modules` — third-party plugin configuration

**Previously:** the mapper emitted warnings like "after import, the admin must …". This offloaded the work onto the user.

**Now:** the **pipeline itself** calls REST APIs after a successful blueprint-import.

## What CAN be done after import

⚠ As of 2026-05-21, `form_module_config`, `user_permissions`, `user_group_permissions_mn`, `collections`, `collection_rows`, `forms`, `form_data` are all IN the 24-table blueprint whitelist (`blueprint-loader.service.ts:23-48`). **Prefer creating them directly through the blueprint** — the loader supports natural-key upsert for `user_permissions` and `user_group_permissions_mn`, so preseeded rows are reused (`blueprint-loader.service.ts:51-57`). Only `markers`, `menus`, `filters` (and their nested rows) remain truly out-of-whitelist.

| Task | Whitelist? | Endpoint (verified) | Notes |
|---|---|---|---|
| **form_module_config** (attach data forms to Users) | **YES** (whitelist 2026-05-21) | No simple `POST /forms/module-config` exists; only `PUT /module-config/:configId/position` and `POST /module-config/init-position` (`admin-forms.controller.ts:402,443`) | Use blueprint or OneEntry Platform UI. |
| **user_permissions** | **YES** (whitelist) | `POST /api/admin/user-permissions` (body is `CreateUserPermissionDto[]` — BATCH array; `admin-user-permissions.controller.ts:247`). DTO fields: `localizeInfos`, `section`, `path`, `rules` (no `identifier`, no `group_id`). | Loader upserts on natural key. |
| **user_group_permissions_mn** | **YES** (whitelist) | NO standalone `/user-group-permissions-mn` controller. Binding via `PUT /api/admin/user-groups/:groupId/permissions/:permissionId/change` (toggle; `admin-user-groups.controller.ts:699`) OR `POST /api/admin/user-groups/:sourceGroupId/permissions/copy-to/:destGroupId` (merge; `:747`). | Use blueprint OR toggle endpoint. |
| **integration-collections** (FAQ/Stores/Loyalty) | **YES** (`collections` + `collection_rows` in whitelist) | `POST /api/admin/integration-collections` (`admin-collections.controller.ts:83`). `CreateCollectionDto` has ONLY `{identifier, localizeInfos}` — no `attribute_set_id`. Form binding goes through `CollectionEntity.formId` (a column update), and rows are added via a separate endpoint. | Prefer blueprint. |
| **markers** (tags/badges on products) | NO | `POST /api/admin/markers` (`admin-markers.controller.ts:81`) | Truly post-import. |
| **menus** (navigation) | NO | `POST /api/admin/menus` (`admin-menus.controller.ts:178`). `CreateMenuDto` accepts `pagesIds: number[]` in the create body — pages are attached in the same call. `PUT /menus/:id/page/:pageId/position` (`:274`) is only for changing the lexorank of already-attached pages. There is NO `/menu-pages-mn` controller. | Truly post-import. |
| **filters** (catalog facets) | NO | `POST /api/admin/filters` + `POST /api/admin/filters/:id/items` (see filters-setup.md §7) | Truly post-import. |

## What CANNOT be automated

| Task | Why |
|---|---|
| **payment_accounts** (Stripe API keys, webhook URL) | Real secrets + the choice of provider depends on the customer. Manual step only, via OneEntry Platform UI → Settings → Payment Accounts. |
| **events + Bull jobs** (email notifications) | Email templates + SMTP/notice-service configs — configured by the admin in Settings. |
| **modules / plugins** | Third-party integrations with their own configs. |

## I/O contract

### Input (from the orchestrator)

```yaml
blueprint_json:     '/abs/path/to/output/<project>.blueprint.json'   # for context
mapped_yaml:        '/abs/path/to/output/<project>.mapped.yaml'      # warnings + out-of-whitelist
project_name:       '<slug>'

# Credentials for the OneEntry Platform instance used for post-import API calls
target_cms_api_url: 'http://localhost:3013/api/admin'   # base URL
target_cms_jwt:     'eyJ...'                            # admin JWT

# Optional parameters
dry_run:            false   # true = log calls without executing
```

### Output

1. A file `<output_dir>/<project>.post-import.log.md` with a journal of every API call and its status.
2. In the final response:
   ```yaml
   status: PASS | PARTIAL | FAIL
   tasks_executed: N
   tasks_skipped: N (with reasons)
   tasks_failed: N
   report_file: '<abs path>'
   ```


## Algorithm

→ **Moved to [`post-import-algorithm.md`](./post-import-algorithm.md)** to keep this file under the Claude Code 40k context-cost threshold.

That file contains all 9 algorithm steps:
1. Read blueprint + mapped warnings
1.5. Build identifier → ID maps
2. `form_module_config` — attach data forms to Users
3. user-permissions for the user group
4. `integration-collections` (FAQ / Stores / Brands)
5. markers
6. menus
7. filters (catalog facets)
8. orphan blocks — fallback page attachment
8.4. Slides for `slider_block`
8.5. Error pages (`page_errors`) — bind HTTP codes
9. payment_accounts (manual — NOT automated)

Load it when implementing or auditing any post-import step.

## Report format `<project>.post-import.log.md`

```markdown
# Post-Import Orchestration — <project>

**Date:** <timestamp>
**Status:** PASS / PARTIAL / FAIL
**Tasks:** N executed, M skipped, K failed

## Executed (N)
- ✅ form_module_config for `feedback` — HTTP 201
- ✅ form_module_config for `reserve_in_store` — HTTP 201
- ✅ user_permission `/api/content/pages` (readAllRule) — HTTP 201
- ✅ user_permission `/api/content/products` (readAllRule) — HTTP 201
- ✅ integration_collection `faq` — 14 rows
- ✅ integration_collection `stores` — 6 rows

## Skipped (M)
- ⏭ payment_accounts — manual (Stripe API keys required)
- ⏭ markers — no Tag entity in project

## Failed (K)
- ❌ form_module_config for `xyz` — HTTP 500 (cause)

## Manual tasks required
- Settings → Payment Accounts → ... (3 actions)
- Settings → Email Templates → notification email for the contact form
```

## When to run

After step 4 (validator PASS) and **the actual successful blueprint load** via `POST /api/admin/import/from-blueprint?dry_run=false`. That is, this is **Step 6** in `.claude/commands/blueprint.md`:

```
Step 0. Pre-checks
Step 1. Inspector
Step 2. Mapper
Step 3. Builder
Step 4. Validator (S1-S57)
Step 4.5. Self-healing loop
Step 5. Import (POST blueprint)            ← new step (previously the user did it)
Step 6. Post-import orchestration         ← NEW step (this file)
Step 7. Final report
```

## Contract — what is allowed / forbidden

✅ **Allowed:**
- All REST APIs under `/api/admin/*` via an admin JWT
- Deduplication (if a permission/collection already exists — skip, do not recreate)
- Idempotent calls (re-runnable)

❌ **Forbidden:**
- Modifying records that **already** exist in the DB (only creating new ones / binding them)
- INSERT directly into the DB (must go through the REST API)
- Hardcoding API keys or secrets
- Performing actions without logging them in `.post-import.log.md`

## Anti-patterns

- ❌ Running post-import **before** a successful import (nothing to configure)
- ❌ Running post-import **a second time** without checking idempotency
- ❌ Failing on the first error — it must complete all tasks, record failures as failed, and not block the rest
