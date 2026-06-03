# Dynamic IDs — strategy for working with unstable numeric identifiers

> **⚠ Universality note.** Examples below may reference fashion-shop terms (clothing / shoes / bags / women / men) — they are **illustrative**. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop, restaurant (`menu-item/dish/cuisine`), beauty salon (`service/master/treatment`), hotel (`room/suite/amenity`), EdTech (`course/lesson`), corporate site (`page/department/team`), personal cabinet (`section/setting`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is hand-written and universal.** Applies to every project using the OneEntry blueprint loader. Not edited by the auto-generator.

## Problem

OneEntry Platform has several entities whose `id` values are seeded via `INSERT ... RETURNING id` (rather than fixed `INSERT id=N`). The specific numeric values **may differ between instances** and depend on:

- the order in which migrations were applied
- previous manual DB edits by the admin
- whether new seeds were applied to a legacy instance

**Hardcoding these ids in a blueprint = HTTP 500 on load, or entities mis-classified in the OneEntry admin** (for example, a hero ends up in the "regular blocks" section instead of "sliders").

## ⚠ Authoritative default — the id snapshot in this file

**Target projects have no access to the cms code or to the customer's target DB.** Therefore the strategy is:

1. **The snapshot ids in the table below are the PRIMARY source**, not a fallback. The builder uses them by default.
2. The snapshot reflects the OneEntry migration order in a fresh **`develop`** DB (current as of the file's update date). On any fresh OneEntry installation on `develop` these ids will be identical.
3. Polling the target DB via `TARGET_DB_*` env variables is **optional verification** for cases where the customer provides access (usually during a test import into pre-prod). If the DB is available and the ids differ — the builder substitutes the real values and emits a warning.
4. If the builder runs without target DB access (the typical case) — it uses the snapshot ids from this file **as the correct default** and adds a marker field `dynamic_ids_source: 'snapshot_2026_05_20'` to `mapped.warnings`.
5. **If on the customer's production the ids differ from the snapshot** — this is a rare situation. After import the admin will see "the hero block is in the recently_viewed_block section" and will have to change the type manually via the OneEntry Platform UI. Validator S45 emits INFO with a hint.

**In other words:** the target pipeline must **confidently produce a correct blueprint** relying solely on this file. Access to a live OneEntry is a bonus, not a requirement.

## Inviolable: the target project has NO access to the CMS code

The pipeline (inspector / mapper / builder / validator) inside the target project works ONLY with:

- the target project's own source code (for `code-inspector`)
- `agents_datasets/rules/*.md` and `agents_datasets/rules/generated/*.md`
- `agents_datasets/ClaudeInfos/*.md`
- (optionally) the **target DB** of the customer's OneEntry Platform instance — where the blueprint will be loaded

Forbidden:

- reading any CMS TypeScript source files (they do not exist in the target project)
- referring to CMS entity files as a source of truth ("look at order-storage.entity.ts")
- relying on access to the cms repository

If a rule is not comprehensive enough — that is a **bug in the rule**, not a reason to dig into cms. Sources of truth must be fully described in `rules/` and `ClaudeInfos/`. Discrepancies (e.g. HTTP 500 "column does not exist" during import) trace to drift between `generated/table-columns.md` and the real target instance. Fix in the `msvc/` pipeline (`gen-rules.py` + regeneration), then distribute the updated `table-columns.md` to target projects.

## Catalog of dynamic identifiers (as of 2026-05-20)

⚠ The numbers in the "id on a fresh `develop` DB" column are a **snapshot**, not a constant. They may differ on the customer's production. Used only as a fallback / for debugging.

### general_types (entity type)

⚠ STABLE block. These ids are pinned by `init-db` or `update-general-types` migration and are identical on **every** OneEntry instance. Safe to hardcode:

| Category | type (marker) | id (STABLE) | Where pinned |
|---|---|---|---|
| product | `product` | **1** | `update-general-types.ts:11` |
| page | `error_page` | **3** | `update-general-types.ts:12` |
| page | `catalog_page` | **4** | `update-general-types.ts:13` |
| product | `product_preview` | **5** | `update-general-types.ts:14` |
| block | `similar_products_block` | **8** | `update-general-types.ts:15` |
| block | `product_block` | **10** | `update-general-types.ts:16` |
| form | `form` | **11** | `update-general-types.ts:17` |
| page | `common_page` | **17** | `update-general-types.ts:18` |
| block | `common_block` | **18** | `update-general-types.ts:19` |
| order | `order` | **21** | `update-general-types.ts:20` |
| discount | `discount` | **23** | `seed-discounts-general-type.ts` (seq-pinned via `setval`) |

⚠ DYNAMIC block. The numbers below are a snapshot from a fresh `develop` DB; on customer production they may differ (seed application order). **Always** also emit `general_type_marker` so the builder can resolve at build time:

| Category | type (marker) | id on a fresh `develop` DB | Where seeded |
|---|---|---|---|
| block | `frequently_ordered_block` | 24 | seed (early) |
| block | `slider_block` | 25 | seed `1870796800001` |
| block | `trending_block` | 26 | seed `1870797100000` |
| block | `recently_viewed_block` | 27 | seed `1870797200000` |
| block | `repeat_purchase_block` | 28 | seed `1870797200001` |
| block | `personal_recommendations_block` | 29 | seed `1870797300000` |
| block | `cart_complement_block` | 30 | seed `1870797400000` |
| block | `cart_similar_block` | 31 | seed `1870797500000` |
| block | `wishlist_similar_block` | 32 | seed `1870797600000` |

### user_groups

⚠ Updated 2026-05-20: verified on a fresh clean OneEntry DB (`test_db_dataset_clean`). **Only `guest` is preseeded** — NOT `user`, NOT `admin`.

| identifier | id on a fresh clean DB | Stability | Source |
|---|---|---|---|
| `guest` | **1** | STABLE | preseeded via `1745835025671-set-default-user-group.ts` (`INSERT id=1, identifier='guest'`) |
| `user` | — | **NOT preseeded** | Appears only if someone created a user/group manually or programmatically. The mapper **must create** it via the blueprint. |
| `admin` | — | **NOT preseeded** | Appears with `npm run seed:admins` (programmatically). **Not created** via the blueprint. |
| custom (vip, b2b, wholesaler) | — | DYNAMIC | created via the blueprint |

**Only `guest` (id=1) is preseeded** in a stock OneEntry Platform instance.

If the app needs to reference guest (for example for anonymous content access) — use the marker:
- `guest_preseeded` → literal `user_group_id: 1` (STABLE)

For the `user` group (registered users) — **create it via the blueprint** in `user_groups`:

```yaml
user_groups:
  - id: '@ug.user'
    identifier: 'user'
    attribute_set: 'forUserGroups'
    localize_infos: { en_US: { title: 'Registered Users' } }
    is_visible: true
```

And reference it via the token:

```yaml
users_auth_providers:
  - identifier: email
    user_group: user         # → token @ug.user
```

⚠ **The `user_preseeded` marker has been REMOVED** — it was based on an incorrect assumption. Use **only** `guest_preseeded` (id=1). All other user_groups are created via the blueprint.

### Permissions for user_groups — now in the whitelist (as of 2026-05-21)

`user_permissions` and `user_group_permissions_mn` are **in the loader's whitelist**.

**The loader uses an upsert strategy** (see `blueprint-loader.service.ts` NATURAL_KEYS):
- `user_permissions` — natural key `(path, section)`. If a permission is already preseeded (112 rows are created by migrations), the blueprint **reuses** its id through a token — no duplicates.
- `user_group_permissions_mn` — natural key `(group_id, permission_id)`. Re-import is idempotent.

⚠ **Full NATURAL_KEYS table** (including `collections` with natural key `(identifier)`, MUTABLE_COLUMNS, and SKIP_IF_PARENT_HAS_CHILDREN policy for `collection_rows`) — see `rules/whitelist-tables.md` "Natural-key upsert tables" + "MUTABLE_COLUMNS" sections. This file focuses on dynamic-id resolution; the loader-side upsert semantics are documented in full there.

In a typical OneEntry DB:
- 112 preseeded `user_permissions` from seeds (`1712162937171-seed-user-permission.ts` and others) — the blueprint **reuses** them, never duplicates them
- 109 preseeded `user_group_permissions_mn` links — all attached to `guest` (id=1)
- The `user` group (id=2) — 0 permissions out of the box, **the blueprint adds them**

**The mapper / post-mapper-fixer** generate a typical permission set for the `user` group:
```yaml
user_permissions:
  - id: '@perm._api_content_pages'
    path: '/api/content/pages'
    section: 'pages'
    rules:
      permissions:
        readAllRule: 0
        readRestrictionRule: 1
        addRule: false
        changeRule: false
        deleteRule: false
      additionalData: {}
    localize_infos:
      en_US: {title: '/api/content/pages'}

user_group_permissions_mn:
  - group_id: '@ug.user'
    permission_id: '@perm._api_content_pages'
```

The old `post-import-orchestrator.py` is no longer needed for permissions — this is automated in the blueprint.

### product_statuses / order_statuses

Usually stable through `is_default: true`/`false` without an explicit `id`. But if the blueprint contains the id token `@ps.active` and the target DB already has a status with identifier='active' — there is a conflict. The mapper must use `lookup` by identifier (not create duplicates).

## Strategy

### Step 1. Mapper (entity-mapper) — put a marker + snapshot id (NOT a fallback id!)

The mapper always emits both `general_type_marker` and `general_type_id`. **`general_type_id` is taken from the snapshot table above**, not from the fallback (18/10). This means the mapper, by default, emits the correct specialized id, not the base type.

```yaml
blocks:
  - identifier: 'hero'
    kind: 'carousel'                          # from the inspector
    general_type_marker: 'slider_block'       # ← marker — for later validation/verification
    general_type_id: 25                       # ← snapshot id from dynamic-ids.md (slider_block)
    attribute_set: 'forBlocks_slider'
    binding: 'page'
    pages: ['root']
```

If you have no matching marker (kind=static_content / products_collection / reviews / faq) — emit only a numeric `general_type_id` (18 or 10). These base types are STABLE and can be hardcoded.

The algorithm for picking a marker by `kind` is in `entity-mapper.md` Step 9.2.

### Step 2. Builder (blueprint-builder) — optional verification via the target DB

The mapper has already placed the correct ids from the snapshot. The builder then does the following:

#### 2.1 Default path (offline, no target DB) — WORKS ALWAYS

1. Takes `general_type_id` as is from mapped.yaml — they are already correct for a fresh `develop` DB.
2. Removes the `general_type_marker` field from the final JSON (the loader does not understand it).
3. Writes to `mapped.warnings`:
   ```
   dynamic_ids_source: 'snapshot_2026_05_20' — general_type_id for DYNAMIC blocks
   was taken from agents_datasets/rules/dynamic-ids.md (fresh develop DB). If the customer's
   production has different ids — after import the admin must change block types
   via the OneEntry Platform UI: Blocks → <block_id> → change type.
   ```

This is the **default**. No access to live OneEntry is required.

#### 2.2 Optional verify path — when the target DB is available

If `TARGET_DB_*` env variables are set (for example during a test import into pre-prod), the builder may optionally query the target DB:

```bash
# Credentials (any of the options)
docker exec "$TARGET_DB_CONTAINER" psql -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" -tAc \
  "SELECT type, id FROM general_types"
# OR
PGPASSWORD="$TARGET_DB_PASSWORD" psql -h "$TARGET_DB_HOST" -p "$TARGET_DB_PORT" \
  -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" -tAc "SELECT type, id FROM general_types"
# OR via HTTP
curl -H "Authorization: Bearer $TARGET_CMS_JWT" "$TARGET_CMS_API_URL/general-types"
```

For each block with a marker:
- If the id from the target DB **matches** the snapshot → leave it alone, remove the marker.
- If the id from the target DB **differs** from the snapshot → substitute the real value, remove the marker, add a warning:
  ```
  dynamic_id_override: '<block_id>' general_type_id changed from {snapshot} to {actual}
  (target DB has different ordering). Blueprint adjusted for target instance.
  ```
- If the marker is **not found** in the target DB (legacy DB without fresh seeds) → fall back to the fallback id (18/10), warning:
  ```
  block_type_fallback: '<block_id>' marker '<marker>' not in target DB.
  Apply migrations 1870796800001..1870797600000 OR upgrade block type manually after import.
  ```

#### 2.3 Timeout / DB query error

If the target DB is configured but unreachable (timeout / authentication failure) — **do not crash**. Fall back to the default offline path (Step 2.1) with a warning:
```
target_db_unreachable: TARGET_DB_* set but connection failed. Falling back to snapshot.
```

### Step 3. Validator — the final blueprint must contain no markers

The **final** `blueprint.json` must not include `general_type_marker`. The builder is required to remove it. If the field remains — that is **ERROR S44** (see `blueprint-validator.md`):

```
S44 <table>[<idx>] contains general_type_marker — builder failed to resolve it.
Loader will reject this field. Re-run builder with TARGET_DB_* env vars set.
```

### Step 4. Loader (cms) — accepts only numbers

The current OneEntry loader does not understand `general_type_marker` — it is an **internal pipeline field**, not part of `BlueprintDto`. In the JSON that goes to `/api/admin/import/from-blueprint`, only numeric `general_type_id` values may be present.

## Target DB credentials — how the builder finds them

Through environment variables / parameters from the orchestrator:

| variable | example | purpose |
|---|---|---|
| `TARGET_DB_HOST` | `localhost` or `127.0.0.1` | postgres host |
| `TARGET_DB_PORT` | `5422` | port |
| `TARGET_DB_USER` | `postgres` | user |
| `TARGET_DB_PASSWORD` | `12345` | password |
| `TARGET_DB_NAME` | `test_db_dataset_clean` | DB name |
| `TARGET_DB_CONTAINER` | `cms-sb-db` | alternative: docker container name for psql |
| `TARGET_DB_URL` | `postgresql://user:pw@host:port/db` | alternative: connection string |
| `TARGET_CMS_API_URL` + `TARGET_CMS_JWT` | `http://localhost:3013/api/admin` + JWT | alternative: HTTP API |

If **none** are set → offline mode (see Step 2.3). The builder does not crash, but emits a warning.

## Universal principle

> **Any entity whose id is determined by the DB through a `RETURNING id` seed must be referenced by name/marker, not by number.** This rule applies to:
> - general_types (this file, the primary case)
> - preseeded user_groups (`guest`=1, custom ones DYNAMIC)
> - preseeded statuses
> - any future enum-like entities with dynamic ids

When a new DYNAMIC entity appears in the rules, always add it to this file's "Catalog" section.

## Anti-patterns

- ❌ Hardcoding `general_type_id: 25` for the slider in the blueprint. On the customer's production it might be 27 — the slider will land in `recently_viewed_block`.
- ❌ Relying on "OneEntry's default migration order" — customers apply migrations at different times, in different orders, sometimes editing manually.
- ❌ Using a marker without a fallback `general_type_id`. If the builder is offline or the customer's DB is unavailable — without the fallback the block will not make it into the import.
- ❌ Leaving `general_type_marker` in the final blueprint.json. The loader will not accept it.
- ❌ Crashing when the target DB is unreachable — switch to offline mode with warnings.
