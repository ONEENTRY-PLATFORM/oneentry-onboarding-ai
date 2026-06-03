# Whitelist tables — 24 allowed tables + usage rules

> **⚠ Universality note.** Examples below may reference fashion-shop terms (clothing / shoes / bags / women / men) — they are **illustrative**. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop, restaurant (`menu-item/dish/cuisine`), beauty salon (`service/master/treatment`), hotel (`room/suite/amenity`), EdTech (`course/lesson`), corporate site (`page/department/team`), personal cabinet (`section/setting`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

⚠ **Source of truth — `rules/generated/whitelist-tables.md`** (auto-generated from the cms loader). It contains exactly **24** tables. This file is synchronized with it.

> **This file is hand-written.** It contains rationale, the FK graph, and common pitfalls. The `gen-rules.py` script does not write to this file.
>
> **The machine-readable registry** of 24 tables + NOT NULL columns per-table lives in `rules/generated/whitelist-tables.md` — it is kept in sync automatically with the cms loader and entity files.

## Whitelist principle

The OneEntry loader accepts a blueprint **only for 24 pre-approved tables**. If `blueprint.tables` contains a key outside the whitelist, the loader immediately fails with 400 `Table 'X' is not whitelisted`.

This protects against accidental inserts into internal tables (positions, attribute_set_types, general_types, etc.) — data there is managed by seeds and code, not by users.

## 24 allowed tables

See `rules/generated/whitelist-tables.md` (the current list from the cms loader).

Summary:
```
attributes_sets, templates, template_previews, pages, products,
products_pages_mn, blocks, block_pages_mn, block_products_mn,
product_blocks_mn, forms, form_module_config, form_data,
user_groups, users_auth_providers, user_permissions,
user_group_permissions_mn, collections, collection_rows,
product_statuses, order_statuses, orders_storage,
orders_storage_payment_accounts, product_relations_templates
```

**6 tables added on 2026-05-21** (previously out-of-whitelist, now blueprint-loadable):
`form_module_config`, `form_data`, `user_permissions`,
`user_group_permissions_mn`, `collections`, `collection_rows`.

## FK graph (relationship map)

Source: the blueprint loader's `fk-graph` registry. This section is **also reproduced in `generated/whitelist-tables.md`** as part of the registry, but is duplicated here for ease of reading.

```
templates:                       attribute_set_id → attributes_sets
pages:                           attribute_set_id, template_id, parent_id (self)
blocks:                          attribute_set_id, template_id
products:                        attribute_set_id, template_id, status_id
products_pages_mn:               pageId, productId          ← camelCase!
block_pages_mn:                  page_id, block_id
block_products_mn:               product_id, block_id, page_id
product_blocks_mn:               product_id, block_id
forms:                           attribute_set_id, template_id
form_module_config:              form_id (→ forms), module_id (= 9 for Users)
form_data:                       form_module_id (→ form_modules_mn — junction of forms↔modules; NOT directly to forms)
user_groups:                     attribute_set_id, parent_id (self)
users_auth_providers:            user_group_id, form_id
user_permissions:                — (natural key = path + section)
user_group_permissions_mn:       group_id (→ user_groups), permission_id (→ user_permissions)
collections:                     form_id (→ forms, optional)
collection_rows:                 collection_id (→ collections)
orders_storage:                  form_id
order_statuses:                  storage_id
orders_storage_payment_accounts: storage_id, payment_account_id
```

## What is NOT in the whitelist (important to know)

- **`positions`** — internal table for sorting. Do not insert directly. The loader creates positions itself via `auto_positions=true`.
- **`general_types`** — reference table of entity types (1=catalog, 2=catalog-list, 3=product, 4=page, 5=block...). Seed data only. In the blueprint you use it as a numeric `general_type_id` value.
- **`attribute_set_types`** — reference table of set types (1=forAdmins, 2=forBlocks, ..., 9=forEvents). Seed only.
- **`addresses`** — not in the whitelist. Addresses must be implemented as fields in `forUsers` (see `coverage-checklist.md` section 2.3).
- **`reviews`** as a separate table — does not exist. Implement via a product page block (`product_blocks_mn` + a special attribute_set of type `reviews`).
- **`payment_accounts`** — target table for the FK from `orders_storage_payment_accounts`. The payment_accounts entries themselves are not created via the blueprint (they are pre-populated by the admin). If you need to reference one — use the numeric id.
- **`markers`** — out-of-whitelist. Created via `POST /api/admin/markers` after import.
- **`menus`**, **`menu_pages_mn`** — out-of-whitelist. Created via `POST /api/admin/menus` after import.
- **`filters`**, **`filter_items_mn`**, **`filter_custom_items_mn`** — out-of-whitelist. Created via `POST /api/admin/filters` + `/filters/:id/items` after import.
- **`events`** + templates — out-of-whitelist (manual setup).
- **`modules`** / third-party — out-of-whitelist (manual setup).
- **`discounts`**, **`discount_coupons`** — out-of-whitelist (UI configuration).
- **`cart_items`**, **`wishlist_items`**, **`user_activity_events`** — runtime data, not blueprint-loadable.

## Natural-key upsert tables (since 2026-05-21)

For three new whitelist tables the loader does **natural-key upsert** instead of `INSERT`. If a row with the same key already exists (e.g. preseeded), the loader updates it instead of failing on UNIQUE.

Source: the blueprint loader's `NATURAL_KEYS` map.

| Table | Natural key columns | Notes |
|---|---|---|
| `user_permissions` | `(path, section)` | 112 preseeded rows — reuse via natural key, do NOT regenerate identifiers |
| `user_group_permissions_mn` | `(group_id, permission_id)` | 109 preseeded for guest (id=1); user (id=2) starts with 0 |
| `collections` | `(identifier)` | Identifier is unique; reused on re-import |

**`collection_rows` — skip-if-parent-has-children behaviour:** if the parent `collections` row already has rows in DB, the loader **skips** the rows from blueprint (does NOT update). This means re-importing a blueprint will NOT overwrite existing collection content — manual UI edits survive. To force-update rows, clear them in the admin first.

**`form_module_config` — plain INSERT** (no natural key). Duplicate `(form_id, module_id)` rows will conflict on the UNIQUE constraint — only create if not preseeded.

## NOT NULL columns

See `rules/generated/whitelist-tables.md` — the full per-table registry is there.

The most common pitfalls:
- `templates.general_type_id` — required
- `pages.general_type_id` — required (default is usually 4)
- `forms.processing_type` — required (`'db'`)
- `users_auth_providers.type` — required (`'email'`)
- `order_statuses.storage_id` — required (if there are order_statuses, an orders_storage is required)
- `attributes_sets.type_id` — required (number 1-11; blueprint usually uses 1-8 — 9=forEvents/10=system/11=forDiscounts belong to out-of-whitelist modules)
- `product_blocks_mn.lang_code` — required (for example `'en_US'`)
- **`form_module_config.form_id`** — required (FK to `forms`); `module_id` typically `9` (Users)
- **`user_permissions.localize_infos`** — required (jsonb with at least the default language)
- **`user_permissions.path`** — required (string; together with `section` it forms the natural key, see NATURAL_KEYS upsert)
- **`user_permissions.section`** — required (enum; values from `AdminPermissionsSectionEnum` / content section enums)
- **`user_group_permissions_mn.group_id`** — required (FK to `user_groups`)
- **`user_group_permissions_mn.permission_id`** — required (FK to `user_permissions`)
- **`collection_rows.collection_id`** — required (FK to `collections`)

## MUTABLE_COLUMNS — what loader UPDATE on natural-key upsert

When a row is matched by NATURAL_KEYS, the loader does not just register the
token on the existing id; it also UPDATEs a fixed set of "mutable" columns from
the blueprint payload. Source: the blueprint loader's `MUTABLE_COLUMNS` map.

| Table | Mutable columns on upsert | Notes |
|---|---|---|
| `user_permissions` | `rules`, `localize_infos` | `path`/`section` are immutable (they form the key) |
| `user_group_permissions_mn` | _(none)_ | Loader registers the token and skips UPDATE — link is binary |
| `collections` | `localize_infos`, `selected_attribute_markers`, `form_id` | `identifier` is immutable (key); other metadata is refreshed |

**Implication for builder:** if you want to update `rules` on a preseeded
permission, just put it in the row alongside `(path, section)` — loader will
UPDATE. If you want to keep `rules` untouched on re-import, do not include the
key in `tables.user_permissions`.

## What the validator must do

- **S1** — all `tables.*` keys ⊆ whitelist (from generated/whitelist-tables.md)
- **S5** — tokens only in FK fields (per the FK map)
- **S6** — required NOT NULL columns are populated

## If a new whitelist table is added to cms

> ⚠ **MAINTAINER-ONLY** steps below — they reference paths inside the `cms/` repo (sibling of `agents_datasets/` in the msvc monorepo) and the maintainer's `agents_datasets/scripts/` toolchain. Not relevant in shop environments.

1. Open the blueprint loader's `ALLOWED_TABLES` constant in the `cms/` repo.
2. Copy the new table name into the `WHITELIST_TABLES` array in `agents_datasets/scripts/gen-rules.py`.
3. Copy the path to its entity into `ENTITY_PATHS` in the same script.
4. Run `python3 agents_datasets/scripts/gen-rules.py` — `generated/*.md` will be updated.
5. If the new table has FKs — add the relationship to the "FK graph" section of **this** file (hand-written).
6. `git diff agents_datasets/` → `git commit` → `git push`.
