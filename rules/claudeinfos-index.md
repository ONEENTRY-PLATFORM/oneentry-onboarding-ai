# `agents_datasets/ClaudeInfos/` — map of the semantic layer for dataset agents

> **⚠ Universality note.** The navigation rules below are vertical-agnostic. Whether the inspector recognizes products (e-commerce), dishes (restaurant), services (salon), rooms (hotel), courses (EdTech), pages (corporate), sections (personal cabinet), or plans (SaaS) — the same routing applies: catalog-style items → `products-architecture.md`, navigation → `menus-setup.md`, filtering → `filters-setup.md`. The vocabulary changes; the layer mapping does not.

> **This file is not rules but navigation.** It indicates which files from `agents_datasets/ClaudeInfos/` to load into an agent's context based on what the inspector recognized. Hard rules (table whitelist, mandatory NOT NULL columns, UNIQUE keys) remain in `agents_datasets/rules/`.

---

## Section 1. Purpose and role

`agents_datasets/ClaudeInfos/` is internal OneEntry Platform documentation, collected separately from pipeline agents. It contains:

- **`use-cases.md`** (31 cases) — semantic mapping "I want X → use Y" (book store → `products`, FAQ → `collections`, cart → `user_activity_events`, etc.).
- **`examples/*.md`** (19 practical examples) — real jsonb structures, attribute names, admin endpoints, Bull queues.
- **`when-not-to-create-tables.md`** — 12 anti-patterns "instead of a new table use …".
- **`data-model-core.md`** — TS types `AttributesSets`, `LocalizeInfo`, `SchemaItem`, description of the dynamic consumer-table whitelist.
- **`entities-catalog.md`** — catalog of 89+ entities (`*.entity.ts`).
- **`modules-catalog.md`** — module catalog: controllers, consumers, queues.
- **`glossary.md`** — internal terms (for example, `schema marker` vs `MarkerEntity`).
- **`patterns-*.md`** — patterns for controllers, queues, journal, blockers, versioning.

**What this is for agents:**

- **code-inspector** — after recognizing a domain entity, sets `likely_use_case` and a link to the example file to give the mapper a hint.
- **entity-mapper** — for each `likely_use_case` loads the corresponding example and takes reference attribute names (`price`, `sku`, `cover`, `gallery` instead of `productPrice`, `imageUrl`, etc.), which improves consistency with the real CMS structure.
- **blueprint-builder** — takes reference `localize_infos` defaults (`titleForSite`, `successMessage`, `unsuccessMessage`).
- **blueprint-validator** — for semantic checks (S28-S31): collections-like pages, markers-like entities, events as forms.

**Priority rule:**

```
agents_datasets/rules/  — LAW (whitelist, NOT NULL, UNIQUE)
agents_datasets/ClaudeInfos/           — REFERENCE (canonical names, anti-patterns, examples)

On conflict — the truth is in rules/. agents_datasets/ClaudeInfos/ is marked "may be outdated" (audit comments).
```

---

## Section 2. Trigger table

If the inspector recognized a trigger from column 2 in the project — the agent must read the corresponding file (column 3) and account for the result in mapping. Column 4 indicates whether the target entity falls into the whitelist of 24 tables.

| # | Trigger in inspector.yaml | File `agents_datasets/ClaudeInfos/` | Whitelist? |
|---|---|---|---|
| 1 | Product/Item/SKU + fields `{price, sku, stock}` | `examples/01-catalog-product.md` + `use-cases.md` (case 1) | ✅ |
| 2 | Pages with slug ∈ `{about, blog, news, faq, terms, privacy}` | `examples/02-content-page.md` + `use-cases.md` (case 2) | ✅ |
| 3 | Pages with bound products / slug ∈ `{catalog, women, men, sale}` | `examples/01-catalog-product.md` + `use-cases.md` (case 3) | ✅ |
| 4 | Forms identifier ∈ `{signin, login, signup, register}` | `examples/03-form-submission.md` + `use-cases.md` (case 6) | ✅ |
| 5 | Forms identifier ∈ `{contact, feedback, review, newsletter, track}` | `examples/03-form-submission.md` | ✅ |
| 6 | Cart/Checkout/Order/OrderItem | `examples/04-order-flow.md` + `use-cases.md` (cases 12, 13) | ✅ |
| 7 | FAQ/City/Country/Brand/Partner/Testimonial | `when-not-to-create-tables.md` (item 2) + `examples/09-collections.md` | ✅ (via `collections` + `collection_rows`, since 2026-05-21) |
| 8 | Subscription/Plan/Coupon/Discount/Bonus | `examples/05-discount-promo.md` + `examples/17-subscriptions-billing.md` | ❌ |
| 9 | Event/Notification/PushTemplate | `examples/06-event-notification.md` | ❌ |
| 10 | Cart/Wishlist/RecentlyViewed/Favorites (as entities) | `examples/18-user-activity-cart-wishlist.md` + `when-not-to-create-tables.md` (item 12) | ❌ |
| 11 | Menu/Header-menu/Footer-menu | `examples/13-menus-and-markers.md` + `use-cases.md` (case 7) | ❌ |
| 12 | Marker/Tag/Flag as an entity | `glossary.md` (Marker / schema marker) | partial |
| 13 | File upload / image gallery (as an attribute) | `examples/15-file-upload-pipeline.md` | ✅ (via attribute type) |
| 14 | Search index / facets | `examples/16-index-attributes-search.md` | ❌ |
| 15 | Module/Plugin/Integration/ThirdParty | `examples/19-third-party-modules.md` | ❌ |
| 16 | Permission/Role guards in routes / RBAC config / `Role` enum | `agents_datasets/rules/users-architecture.md` + `agents_datasets/.claude/agents/entity-mapper.md` Step 2 sub-section "Permissions" | ✅ (via `user_permissions` + `user_group_permissions_mn`, since 2026-05-21; natural-key upsert by `(path, section)` / `(group_id, permission_id)`) |
| 17 | Form-module attachment (registration form bound to Users module, rating form bound to a product module) | `agents_datasets/.claude/agents/entity-mapper.md` Step 9.9 | ✅ (via `form_module_config`, since 2026-05-21; composite UNIQUE `(module_id, form_id)`) |

**Notes:**

- Trigger #13 (file upload) is partially in the whitelist — the files themselves are not stored as a table, but attributes of type `image`/`file`/`groupOfImages` live inside `forProducts.schema` (see `attribute-types-mapping.md`).
- Trigger #12 (markers) — partial: if it's about a `schema marker` (flags `isPrice`, `isSku`, `isProductPreview` inside `SchemaItem`) — this always applies in the whitelist (the mapper sets flags on the relevant fields). If it's about `MarkerEntity` (the `markers` table) — out-of-whitelist.

---

## Section 3. Reading rules

1. **Limit ≤5 `agents_datasets/ClaudeInfos/` files per agent run.** If there are more triggers — read only those for which `inspector.yaml` has a `likely_use_case` or explicit matches by entity names.

2. **Source priority on conflict:**
   ```
   rules/generated/whitelist-tables.md       ← law (whitelist of 24 tables)
   rules/generated/table-columns.md          ← law (allowed columns per-table)
   rules/generated/unique-constraints.md     ← law (UNIQUE keys)
   rules/generated/preseeded-entities.md     ← law (what's already seeded in the DB)
   rules/<everything else .md>               ← law (invariants, coverage-checklist, ...)
   agents_datasets/ClaudeInfos/*.md                         ← reference (canonical names, anti-patterns)
   ```
   If `agents_datasets/ClaudeInfos/` recommends something that contradicts `rules/` — follow `rules/`, add a note to the `warnings:` section of mapped.yaml or validation.md.

3. **Fallback if `likely_use_case` is missing** (old inspector.yaml without this field, or inspector didn't recognize any use case):
   - entity-mapper reads only `claudeinfos-index.md` (this file) + basic `rules/standard-entities.md`.
   - Mapping is performed by field-name heuristics without loading example files.
   - A line `'no likely_use_case in inspector — fallback to standard-entities heuristics'` is added to `warnings:`.

4. **`agents_datasets/ClaudeInfos/` is marked "may be outdated"** — each example has an audit comment `<!-- audit: 5/5 (YYYY-MM-DD) endpoints[...], fields[...], ... -->`. Use as a reference, not as law. If you have access to the live CMS API (via `API_BASE`) and an example name doesn't resolve — record in a warning, don't trust the doc blindly.

5. **Triggers from section 2 are NOT activated automatically.** The agent must first confirm that the project actually has the corresponding entities (not just the string `'cart'` in code). For each trigger, the inspector must confirm presence by analyzing fields/routes/components.

6. **When you do NOT need to use `agents_datasets/ClaudeInfos/`:**
   - The project is empty/small, everything is resolved via `standard-entities.md` (signin form, basic pages, basic forProducts).
   - The inspector did not recognize any use case (low-signal project).
   - The trigger points to an out-of-whitelist scenario — read `when-not-to-create-tables.md`, **do not include** the corresponding table in the blueprint, add a warning.

---

## Section 4. FAQ / Memo

**Q: No trigger matched — what should I do?**
A: Fall back to `agents_datasets/rules/standard-entities.md` and `coverage-checklist.md`. Mapping proceeds via field-name heuristics. In warnings — the line `'no _ClaudeInfos trigger matched; used standard-entities fallback'`.

**Q: Multiple triggers fired — read all of them?**
A: Yes, but the limit is ≤5 files per run. If there are more triggers — prioritize by `likely_use_case` from inspector.yaml; otherwise by the descending number of entities in the group (more products → read `01-catalog-product.md` first).

**Q: Conflict between `agents_datasets/ClaudeInfos/` and `rules/` — whom to trust?**
A: `rules/`. `agents_datasets/ClaudeInfos/` is marked "may be outdated". If an example recommendation contradicts the whitelist of 24 tables or table-columns — ignore the example, record a warning.

**Q: Should the whitelist of 24 tables be extended to cover out-of-whitelist scenarios?**
A: NO. The whitelist is a contract of the blueprint-loader in cms. Out-of-whitelist scenarios (markers, discounts, events, user_activity_events, menus, modules, index_attributes, filters) **are not loaded via blueprint**. In such cases the mapper generates a warning, the validator writes S28-S31, and the user configures them manually in OneEntry Platform after import. Note: since 2026-05-21 `collections` / `collection_rows` / `form_module_config` / `form_data` / `user_permissions` / `user_group_permissions_mn` have moved INTO the whitelist and are loaded via blueprint directly (natural-key upsert for the permission and collection tables).

**Q: The user added a new file to `agents_datasets/ClaudeInfos/examples/` — what should be done?**
A: This file (`claudeinfos-index.md`) is **not auto-generated**. After adding a new example, you need to manually add a row to Section 2 (the trigger table) pointing to the new file and its whitelist status.

**Q: Can `agents_datasets/ClaudeInfos/` be used as a source to generate new rules/*.md?**
A: No — it's for pipeline agents, not for the generator (`scripts/gen-rules.py` reads only cms). If new auto-generated rules are needed — add them in `scripts/gen-rules.py`.

**Q: inspector.yaml has `likely_use_case: catalog-product` but the project has no products — what should the mapper do?**
A: The inspector may have been mistaken (e.g., a `Product` interface exists but there are no actual products). The mapper reads `01-catalog-product.md`, but leaves `mapped.yaml.products: []` empty; in warnings — `'likely_use_case=catalog-product, but products[] is empty in inspector — skipping forProducts attributes or creating as sample'`.

---

## Related documents

- `agents_datasets/rules/oneentry-invariants.md` — main invariants (login=signup, system flags ≤1, etc.).
- `agents_datasets/rules/coverage-checklist.md` — what the blueprint must contain.
- `agents_datasets/rules/standard-entities.md` — standard entities (signin form, user_groups, product_statuses).
- `agents_datasets/rules/users-architecture.md` — forUsers ≤12 fields + Data Submission forms.
- `agents_datasets/rules/generated/whitelist-tables.md` — law: whitelist of 24 tables.
- `agents_datasets/ClaudeInfos/00-index.md` — navigation for `agents_datasets/ClaudeInfos/`.
- `agents_datasets/ClaudeInfos/use-cases.md` — main use-cases file (31 cases).
- `agents_datasets/ClaudeInfos/when-not-to-create-tables.md` — anti-patterns (12 items).
