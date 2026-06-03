# Usage Guide — how to use each OneEntry entity type (step by step)

> **⚠ Universality note.** Examples below frequently use fashion-shop terms (clothing / shoes / bags / women / men) because that is the reference test project. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop (`product/sku/brand/category`), restaurant (`menu-item/dish/cuisine/section`), beauty salon (`service/master/treatment/duration`), hotel (`room/suite/amenity`), EdTech (`course/lesson/level`), corporate site (`page/department/team`), personal cabinet (`section/setting/subscription`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is hand-written and universal across projects.** Not edited by the auto-generator.
> Source of truth for "which type to use when" decisions. Used by the mapper, the builder and the validator.
>
> ⚠ Not to be confused with `agents_datasets/ClaudeInfos/use-cases.md` (that one — about OneEntry use cases for the AI; this one — about the concrete entity types in the blueprint whitelist).

## ⚠ Language policy — blueprint instructions are written in ENGLISH

All blueprint-pipeline documentation is **English-only**. This applies to every file under:

- `agents_datasets/rules/**.md` (this file, `oneentry-invariants.md`, `filters-setup.md`, `users-architecture.md`, `post-import-orchestration.md`, etc.)
- `agents_datasets/.claude/agents/**.md` (`blueprint-validator.md`, `blueprint-builder.md`, `blueprint-auditor.md`, `code-inspector.md`, `entity-mapper.md`)
- `.claude/agents/**.md` (mirror of the above when used as Claude Code sub-agents)
- Inline comments in JSON examples, validator rule prose (`Source:`, `For each row in…`, `Severity: …`), `[ASSUMPTION]` blocks, warning/error message templates.

**Rationale:** the blueprint pipeline runs across projects, contributors and AI agents that operate in English. Mixing locales fragments grep, breaks token namespaces consistency, and forces translators on every change.

**Exceptions** (Russian allowed only here):
- Project-specific human chats and feature specs (`docs/specs/<slug>-<date>.md`) — author's choice.
- Translated string VALUES inside `localize_infos.<lang>.title|description|…` jsonb cells — those are project content, not pipeline documentation.
- JSDoc / inline code comments inside CMS backend source files follow the cms code-style rule (Russian comments). That is a separate rule for the *cms backend codebase*, not for the blueprint pipeline docs.

**When editing or adding rules, validator checks (Sxx), warning/error message templates, examples, anti-pattern blocks, archetype tables, agent prompts — write everything in English.** If you find any Russian prose in the listed files, translate it to English in the same edit.

## Contents

1. [attributes_sets — types and schema](#1-attributes_sets--types-and-schema)
2. [attribute types — 19 attribute types](#2-attribute-types--19-types)
3. [attribute system flags — isPrice, isSku, etc.](#3-system-flags--exactly-1-per-attribute_set)
4. [attribute validators (rules)](#4-validators-rules--required-minimums)
5. [pages — page types](#5-pages--types)
6. [forms — form types](#6-forms--types)
7. [user_groups](#7-user_groups)
8. [users_auth_providers](#8-users_auth_providers)
9. [blocks — all 12 types with the kind marker](#9-blocks--all-12-types)
10. [templates](#10-templates)
11. [template_previews](#11-template-previews)
12. [orders_storage + order_statuses](#12-orders-storage--order_statuses)
13. [product_statuses](#13-product_statuses)
14. [product_relations_templates — related products](#14-product-relations-templates)
15. [products + products_pages_mn](#15-products--products_pages_mn)
16. [mn tables — UNIQUE nuances](#16-mn-tables--unique-nuances)
17. [Localization (localize_infos)](#17-localization)
18. [Out-of-whitelist scenarios](#18-out-of-whitelist--what-does-not-go-through-the-blueprint)

---


## 1–9 → moved to `usage-guide-schema.md`

→ [`usage-guide-schema.md`](./usage-guide-schema.md) — attribute_sets, attribute types (19), system flags, validators, pages, forms, user_groups, users_auth_providers, blocks.

## 10–15 → moved to `usage-guide-content.md`

→ [`usage-guide-content.md`](./usage-guide-content.md) — templates, template previews, orders storage + statuses, product statuses, product relations templates, products + products_pages_mn.

## 16. mn tables — UNIQUE nuances

See `agents_datasets/rules/generated/unique-constraints.md`.

| Table | UNIQUE key |
|---|---|
| `block_pages_mn` | `(page_id, block_id)` |
| `block_products_mn` | `(product_id, block_id)` ← **NO `page_id`** |
| `product_blocks_mn` | `(product_id, block_id, lang_code)` |
| `products_pages_mn` | (no composite UNIQUE) |
| `orders_storage_payment_accounts` | `(storage_id, payment_account_id)` |

⚠ Especially for `block_products_mn`: one `(product, block)` pair = one row, regardless of how many pages the product is on. **Do not duplicate** (validator S21).

### lang_code in product_blocks_mn

Every `product_blocks_mn` row must include `lang_code` (NOT NULL in the DB). Validator S19.

---

## 17. Localization

See `agents_datasets/rules/oneentry-invariants.md §7` + entity-mapper Step 0.1.

- Every language from `detected_languages` — **everywhere** there is `localize_infos` / `localizeInfos`.
- Every language has an **identical key set** (`title`, `description`, `menuTitle`, ...).
- On the default language — the real text from the code.
- On the rest — translations from i18n (if the inspector found them), or a copy with a warning:
  ```
  untranslated <lang> for <entity>.<field> — admin should translate after import
  ```

### Anti-Hallucination (oneentry-invariants.md §18)

❌ If the code has `source: NOT_FOUND` — leave it `null`, do not substitute Title Case of the identifier.

```yaml
# inspector
pages:
  - identifier: 'men-clothing'
    title: { value: null, source: 'NOT_FOUND' }

# mapper → mapped.yaml
pages:
  - identifier: 'men-clothing'
    localize_infos:
      en_US: { title: null }      # ← null, not "Men Clothing"!
    # + warning: missing_title: pages.men-clothing.title — source NOT_FOUND
```

Validator S36 catches this as a WARNING.

---

## 18. Out-of-whitelist — what does NOT go through the blueprint

See `agents_datasets/ClaudeInfos/when-not-to-create-tables.md`.

Do not create as whitelist entities, record as an `out-of-whitelist:` warning:

| What | OneEntry entity | Mapper action |
|---|---|---|
| Tags/Markers/Flags | `markers` (`MarkerEntity`) or schema markers | warning |
| Discounts/Coupons | `discounts` + `discount_coupons` | warning |
| Events/Notifications | `events` + Bull queue | warning |
| Cart/Wishlist/RecentlyViewed as entities | `users.system_attributes_sets` jsonb | warning |
| Menus | `menus` + `menu_pages_mn` | warning |
| Modules/Plugins/Integrations | `modules` (`type=CUSTOM`) | warning |
| Search indices | `index_attributes` | INFO |
| **Catalog facets / filter panel** (`filters` + `filter_items_mn` + `filter_custom_items_mn`) | `filters` + `filter_items_mn` (out of whitelist). Indexing is automatic via Bull consumer. There is NO `isFilter` flag on `SchemaItem`. | Emit `mapped.post_import_filters[]` + `out-of-whitelist-needs-post-import: filters …` warning. Do NOT mutate `attributes_sets.schema`. See `agents_datasets/rules/filters-setup.md` (universal algorithm + real DTO contract). |
| Subscriptions/Plans | `subscriptions` | warning |
| Payment accounts | `payment_accounts` (manual setup) | warning |
| Audit/journal entries | via the `@Journalable` decorator | warning |
| Entity versioning | the built-in `entity-versions` | warning |

Warning format:
```
out-of-whitelist: detected <N> <thing> — should be <oneentry-mechanism>.
Skipped — manual setup in OneEntry Platform admin → <module>.
```

The `out-of-whitelist:` prefix is important — Validator S31 catches these warnings and converts them into INFO for the final report.

> **Note (2026-05-21 migration):** `collections` + `collection_rows`, `form_module_config`, `form_data`, `user_permissions`, `user_group_permissions_mn` used to live in this table — they are now **inside** the 24-table whitelist and must be emitted directly in `mapped.yaml.tables` (not as `out-of-whitelist:` warnings). See `rules/whitelist-tables.md` "Natural-key upsert tables".

---

## Minimal checklist before assembling the blueprint

1. `attributes_sets`: ≥ 5 sets (`forUsers`, `forUserGroups`, `forProducts`, `forPages`, `forForms_signin`).
2. `user_groups`: at least `user`; **do not create** `guest`/`admin`.
3. `users_auth_providers`: at least one email provider.
4. `forms`: at least `signin` (`type: sing_in_up`).
5. `product_statuses`: the standard 3 (`active`, `draft`, `archived`).
6. `pages`: correct `general_type_id` (4 for catalogs, 17 for everything else).
7. `templates`: 6 defaults (one per each key `general_type_id`).
8. `template_previews`: at least 2 (`product_card`, `banner`).
9. `products`: ≥ 1 sample.
10. `products_pages_mn`: products attached to catalogs.
11. `blocks`: each with `kind`, `attribute_set` (type_id=2), `general_type_marker` for DYNAMIC.
12. Localization: every language everywhere, identical keys.
13. NO hallucination: NOT_FOUND → null, not the Title Case of the identifier.
14. capture_mode: do not add (the field does not exist).
15. **Filters (`filters-setup.md`):** filters (`filters` / `filter_items_mn` / `filter_custom_items_mn`) are NOT in the whitelist and NOT in the blueprint JSON. The blueprint itself contains no filter-related fields — `SchemaItem` has a fixed set of system flags and `isFilter` is NOT one of them. For each catalog page (`gtid=4`) the mapper must emit a task in `mapped.post_import_filters[]` with `{identifier, scope_types, page_identifier, attribute_set_identifier, attribute_identifiers, direct_items, localize_infos}`. The orchestrator (post-import Step 7) creates `filters` + adds items via `POST /api/admin/filters` and `POST /api/admin/filters/:id/items` (camelCase DTO: `objectType`, `objectId`, `attributeIdentifier`).
16. **Hub pages (`oneentry-invariants.md` §19):** hub pages (`/women`, `/men`, parents of catalogs) have `general_type_id=17`, NOT 4. Catalog children have gtid=4.
17. **No orphan blocks (`oneentry-invariants.md` §21):** every `blocks` row must be referenced from `block_pages_mn`, `block_products_mn`, OR `product_blocks_mn`. Validator S15 emits WARNING.
18. **forUsers is wide, NOT split (`users-architecture.md`, 2026-05-20 rewrite):** put address, loyalty, subscription prefs, GDPR consents, social-connect flags directly into `forUsers.schema` (30-45 fields normal). Do NOT create `forForms_address` / `forForms_loyalty` / `forForms_subscriptions` / `forForms_consents`. Old S42 (>12 = anti-pattern) is INVERTED.
19. Validator: PASS (errors=0, warnings ≤ 5 on a medium-complexity project).
