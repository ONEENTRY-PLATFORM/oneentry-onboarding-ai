# Glossary

Internal terms specific to OneEntry CMS. If you are reading the code for the first time — open this file; some words are used in a non-standard sense.

---

## Attribute set (attribute set / attributes_sets)

The word is a **homonym** in this codebase:

1. **Metadata** — a row in the `attributes_sets` table (entity `AttributesSetEntity`, file `cms/src/modules/attributes-sets/entities/attributes-set.entity.ts`). Fields: `identifier`, `title`, `type_id` → `attribute_set_types`, `schema jsonb` (attribute description), `properties jsonb`, `position_id`.
2. **Values** — the `attributes_sets` jsonb column on consumer tables (products, pages, blocks, …). Type `Record<langCode, Record<attrId, value>>`. See [`data-model-core.md §2.1`](./data-model-core.md#21-attributes_sets-entity-attribute-values).

If the context is ambiguous — ask, or check the type: `AttributesSetEntity` = metadata, `AttributesSets` (the type) = values.

---

## Consumer table

A table that "consumes" an attribute set: it has an `attribute_set_id` column plus the `attributes_sets` jsonb. For example: `products`, `pages`, `blocks`, `templates`, `forms`, `events`, `admins`, `user_groups`, `discounts`, `users` (a special case: columns declared manually).

The full list is obtained dynamically via `SELECT table_name FROM information_schema.columns WHERE column_name = 'attribute_set_id'` (see [`data-model-core.md §3`](./data-model-core.md#3-dynamic-consumer-table-whitelist-via-information_schema)). There is no hardcoded list in the code, and there must not be one.

---

## Advisory blocker

A "do not edit X right now" signal that is not backed by a mutex but instead is broadcast over WebSocket and is honored by clients. In the CMS there are two flavors:

- **System blocker** — while a Bull job is running, a channel (for example `attributesSetsChanging`) is emitted. The frontend locks the UI.
- **User blocker** — while an admin is typing into a field, the `attributeChangingValue` channel is emitted with a ~5 second TTL. Other frontends lock the field.

For details see [`patterns-journal-blockers-versioning.md §2`](./patterns-journal-blockers-versioning.md#2-blockers).

**Do not confuse this with** `isPositionLocked` / `manageSortLocking` / `removeWithLocked` in `products` — those are **pinning of a product's position in sort order**, not edit blocking.

---

## CRDT document (Yjs)

A parallel mechanism for syncing a product / page between multiple open tabs. Implemented via yjs + y-websocket. Server side — `SyncSocketGateway` (`cms/src/modules/socket/sync-socket.gateway.ts`) on a dedicated port `WS_SYNC_SERVER_PORT` (default 3007). Used **only** for `products` and `pages`.

This means these two entities do not have a full-fledged `PUT /:id` for replacing the whole object — changes fly straight into the YJS doc, and the DB is written in parallel. See the root `CLAUDE.md` for frontend context.

---

## general_types ("general type" / GeneralType)

An enum-style table `general_types` with one row per entity type. The values come from the `GeneralType` enum (`cms/src/modules/general-types/types/general-types.enum.ts`): `common_page`, `catalog_page`, `error_page`, `external_page`, `Service` (sic, capital S), `product`, `product_preview`, `common_block`, `product_block`, `similar_products_block`, `frequently_ordered_block`, `slider_block`, `trending_block`, `recently_viewed_block`, `repeat_purchase_block`, `personal_recommendations_block`, `cart_complement_block`, `cart_similar_block`, `wishlist_similar_block`, `form`, `order`, `discount`.

It's used as the FK target of `pages.general_type_id`, `blocks.general_type_id`, `orders_storage.general_type_id`, `templates.general_type_id` (and so on). The same `GeneralType` can define a "behavior class" across multiple entities (for example, `forCatalogPages` applies to both pages and templates).

---

## Marker (marker / identifier)

In this codebase the word is used in several ways. Context determines the meaning:

1. **The `identifier` column** (string, indexed) — on every entity that uses `BaseAbstractEntity`, this is a unique text ID for machine addressing (e.g. `'main-menu'`, `'product_image_attr'`). Developer-facing objects are often addressed via identifier rather than the numeric `id`.
2. **The `marker` column** — on the `MarkerEntity` (`markers` table) it is the marker object itself: a unique, indexed string with localization. Used as a tag for attributes / sections.
3. **An attribute's `identifier`** in a set's schema — the `SchemaItem.identifier` field (e.g. `'string_id26'`) — a unique key of the attribute within the set. Values are stored under this identifier in the `attributes_sets` jsonb.

When someone says "marker" in a task, they almost always mean `identifier`, or a record in `markers`.

---

## schema-marker (= "SchemaItem special flag")

Boolean flags inside `attributes_sets.schema[*]` that mark the "semantic role" of a specific attribute within the set. The complete value list lives in `cms/src/modules/attributes-sets/types/schema-item.type.ts` (the `SchemaItem.is*: boolean` fields). Examples:
- `isPrice` — the attribute holds the product price (consumed by `index-data`, filtering, payments).
- `isSku` / `isCurrency` — SKU and currency respectively.
- `isProductPreview` / `isProductTitle` — which attribute to render in the catalog preview card.

These are used in code as `schemaItem.isPrice === true` — they are **flags inside an attribute set's schema**, not separate entities.

**Do not confuse with `MarkerEntity`** (the `markers` table, see the "Marker" section above) — `MarkerEntity` is a tag entity; a schema-marker is a boolean field in the set's jsonb schema.

Synonyms from older docs: "special flag", "SchemaItem special flag", "SchemaItem flag" — these appear in [`01-catalog-product.md`](./examples/01-catalog-product.md), [`10-extend-attribute-set.md`](./examples/10-extend-attribute-set.md), [`use-cases.md`](./use-cases.md). The new docs standardize on **schema-marker**.

---

## localize_infos

A `jsonb` column with the shape `{ [langCode]: { title, ...extra } }`. The TS type is `CommonLocalizeInfos` (`cms/src/shared/types/common.types.ts`). It is extended for specific entities: for example `PageLocalizeInfos` adds `plainContent`, `htmlContent`, `menuTitle`; `FormLocalizeInfos` adds `systemTitle`, `successMessage`, `unsuccessMessage`.

Who has it: pages, blocks, products (with a differently named type), collections, discounts, forms, markers, menus, modules, orders_storage, user_groups, and others. The dynamic list comes from `SELECT table_name FROM information_schema.columns WHERE column_name = 'localize_infos'`.

---

## Bull queue

A Redis-backed task queue from the `@nestjs/bull` package (Bull v3). The CMS registers 14 Bull queues: 13 in the `BULL_QUEUES` constant (`cms/src/config/constants.ts`) plus a standalone `attributes-sets` (registered via `@InjectQueue('attributes-sets')`, not part of the constant). Each queue is a separate Redis key.

A queue's consumer is a class decorated with `@Processor('<queue>')` and methods marked `@Process('<job-name>')`. The `@OnQueueActive` / `@OnQueueCompleted` / `@OnQueueFailed` / `@OnQueueError` hooks fire on every job.

See [`patterns-queues-and-ws.md`](./patterns-queues-and-ws.md) for the full table.

---

## Position (lexorank sort)

A dedicated `positions` table (entity `PositionEntity`, `cms/src/modules/position/entities/position.entity.ts`) stores an object's sort key as a lexorank string (e.g. `'0|hzzzzz:'`).

Fields: `object_type` (varchar `'page' / 'product' / 'module' / 'attribute-set' / ...`), `object_id`, `position` (text, indexed), `is_locked` (bool), `locked_position` (int, used for pinning), `object_category_id` (used when an object belongs to multiple categories).

The same object may have several `position` rows (one per category / one per menu). See `PositionEntity` — it has `@OneToOne` relations to pages, products, modules, admins, locales, templates, template_previews, attribute_sets, product_statuses, block_products, discounts.

---

## Journal event

A value of the `JournalingEvents` enum (`cms/src/modules/journal/types/journaling-events.ts`). 110 values at the time of writing: `productCreated`, `pageUpdated`, `orderDeleted`, …

It is passed to the `@Journalable(...)` decorator — the interceptor writes a row into `journal_records` with this value in the `journaling_event` column. See [`patterns-journal-blockers-versioning.md §1`](./patterns-journal-blockers-versioning.md#1-journal-admin-action-audit).

---

## Modules / GeneralTypes M2M

The `modules` table stores CMS "deploy units" (system or custom). Binding a module to entity types:
- **`module_general_types_mn`** — which `general_types` the module serves.
- **`module_attribute_set_types_mn`** — which `attribute_set_types` (e.g. `forProducts`, `forPages`) belong to it.

In other words, one module can "contain" several page / block types plus its own attribute sets. This is the foundation of the plugin system for integrators using the developer API.

---

## Identifier ≠ id

Most entities have both fields:
- `id` — numeric PK.
- `identifier` — a string, human/machine-readable key (e.g. `'main-products'`, `'admin-user-form'`).

External integrations (developer API, content API, import) usually work via `identifier` so they survive an entity being recreated with a new `id`. Inside the admin panel — via `id`.

---

## attribute_set_id ≠ attributes_set.id

A subtlety:
- `attribute_set_id` — FK on a consumer table → `attributes_sets.id`.
- `attributes_set.id` — primary key of the `attributes_sets` table itself.

Sometimes you'll see a variable named `aId` in code — that's the **attribute set id** (i.e. the set's ID), not the ID of a consumer entity. For example, in the Bull payload of `attributes-sets:update-changing` the `aId` field is `attributes_sets.id`.

---

## `forXxx` (attribute set type)

Values of the `AttributesSetType` enum (`cms/src/modules/attributes-sets/attributes-sets.interface.ts`):
- `forAdmins` — sets for admins
- `forBlock` (sic, the actual value is `'forBlocks'`) — for blocks
- `forOrders` — for orders
- `forPages` — for pages
- `forProducts` — for products
- `forUsers` — for users
- `forUserGroups` — for user groups
- `forDiscounts` — for discounts

`AttributesSetEntity.type` (via the FK `type_id`) tells you which "family" a set belongs to. This filters the UI for picking a set when editing a particular entity.

---

## Related documents

Main entry points after the glossary:
- [`use-cases.md`](./use-cases.md) — concrete tasks.
- [`data-model-core.md`](./data-model-core.md) — structure.
- [`00-index.md`](./00-index.md) — navigation.
