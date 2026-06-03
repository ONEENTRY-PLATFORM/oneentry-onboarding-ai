# When NOT to create a new table

In OneEntry CMS most "seemingly new" data is already modeled by existing mechanisms. This file is a checklist: open it before you reach for `CREATE TABLE`. The goal is to prevent schema bloat and preserve compatibility with the dynamic machinery (`information_schema`, journal, blockers, versions).

> **If none of the items apply** — discuss the new entity with the user through the analyst. Do not introduce a new table on your own.

---

## 1. You need to "add a field to a product / page / admin / user group / form / discount / template / event"

**Extend the `attribute_set` — don't add a new column or a new table.**

Why (in code):
- Any entity with an `attribute_set_id` column (see the list in [`data-model-core.md §1`](./data-model-core.md#1-base-abstract-entities)) already has:
  - the `attributes_sets` jsonb column for values,
  - metadata in `attributes_sets.schema`,
  - indexing via `index_attribute_data`,
  - automatic migration of the values when the schema changes, via `attributes-sets:update-changing` (a Bull handler in `cms/src/modules/attributes-sets/consumers/attributes-sets.consumer.ts:58`).
- If you add a custom SQL column — none of the above will work; you'll have to wire everything by hand.

**Exception:** if the field is an indexable business entity (status_id, parent_id, position_id, page_url) — yes, a dedicated column makes sense. Tell-tale sign: you'll be using it in `WHERE` clauses on hot queries.

---

## 2. You need "a list of FAQ items / cities / countries / brands / reviews / partners"

**Use `collections` + `collection_rows`.**

Why (in code):
- `CollectionEntity` (`cms/src/modules/collections/entities/collection.entity.ts`) — a single container.
- `CollectionRowEntity` (`cms/src/modules/collections/entities/collection-row.entity.ts`) — a row: `form_data jsonb { [lang]: [{ marker, type, value }, ...] }`. That is, an arbitrary localized structure without migrations.
- The form used for editing in the UI: `collections.form_id` → `forms`. The editing UI is rendered automatically from the form's schema.
- A generic reference to another entity: `collection_rows.entity_type` + `entity_id` (e.g. a review attached to a product as `entityType='products', entityId=42`).

**Do not create:** `faq`, `cities`, `brands`, `partners`, `reviews_for_products`.

---

## 3. You need "a new kind of block on a page" (slider, video, text+image, similar products, etc.)

**Use the existing `BlockEntity` + `custom_settings jsonb`, or add a value to `GeneralType`.**

Why (in code):
- `BlockEntity.customSettings jsonb` (`cms/src/modules/blocks/entities/block.entity.ts:53`) typed as `BlockCustomSettings` (`cms/src/modules/blocks/types/block.types.ts:43`):
  ```ts
  interface BlockCustomSettings {
    sliderDelay?: number;
    sliderDelayType: string;
    productConfig: BlockLangProductConfig;
    similarProductRules: FilterBlockProducts;
    condition: BlockLangCondition;
    frequentlyOrderedConfig?: FrequentlyOrderedConfig;
  }
  ```
  — the jsonb is already extensible: add a new field for your kind of block.
- If the behavior is fundamentally different (e.g. requires server-side product selection logic) — add a value to the `GeneralType` enum (`cms/src/modules/general-types/types/general-types.enum.ts`) plus a seed in `general_types`. Example: `FrequentlyOrderedBlock = 'frequently_ordered_block'` (see that same file).
- Block attributes — through an `attribute_set` of type `forBlocks`.

**Do not create:** `slider_blocks`, `video_blocks`, `text_blocks` — those are all `blocks` with different `general_type_id` or different `customSettings`.

---

## 4. You need "a new kind of page" (landing, FAQ page, services page, etc.)

**Add a value to the `GeneralType` enum + a seed, and use `PageEntity` + your own `attribute_set`.**

Why (in code):
- `pages.general_type_id` → `general_types` (see `PageEntity:33-44`).
- Current values: `CommonPage`, `ErrorPage`, `CatalogPage`, `ExternalPage`, `Service` (sic, capital S) — from `general-types.enum.ts`.
- Arbitrary page settings — `pages.config jsonb`.
- Localized texts — `pages.localize_infos jsonb`.

**Do not create:** `landing_pages`, `faq_pages`, `service_pages`.

---

## 5. You need to "accept user input via a form" (application, review, vote, service request)

**Use `forms` + `form_data`.**

Why (in code):
- `FormEntity` (`cms/src/modules/forms/entities/form.entity.ts`) — form description + `attribute_set` (fields).
- `FormDataEntity` (`cms/src/modules/form-data/entities/form-data.entity.ts`) — submitted data: `form_identifier`, `form_data jsonb`, `user_identifier`, `entity_identifier`, `status: FormDataStatusType`, `ip`, `fingerprint`, `is_user_admin`.
- `FormType` enum: `ORDER`, `SIGN_IN_UP`, `COLLECTION`, `DATA`, `RATING` (`cms/src/modules/forms/types/form.type.ts`).
- `FormProcessingType` enum: `db` / `email` / `script` — where the data goes after submission.
- The link between a form and a concrete "receiving module" (e.g. user registration): `FormModuleConfigEntity` + `FormModuleMnEntity`.

**Do not create:** `contact_requests`, `vacancy_applications`, `feedback`.

---

## 6. You need "a new event type for notifications" (e.g. on sign-up or on price change)

**Use `events` — it is already universal.**

Why (in code):
- `EventEntity` (`cms/src/modules/events/entities/event.entity.ts`) — fields:
  - `type: EventType` (`'attribute'` / `'status'`),
  - `actions jsonb`: `{ isPush, isWebsocket, isEmail, isWorkflows }`,
  - `mailing jsonb` (`Mailing { conditions, period: MailingPeriod, scheduleAttr, ... }`),
  - `whomType: WhomType` (`ALL` / `SUBS` / `USER_GROUP`).
- The worker `EventsProcessor` (`cms/src/modules/events/consumers/events.consumer.ts`) already handles: `change-product-attribute`, `change-product-status`, `sign-up`, `send-user`, `change-password`, `change-order-status`, `change-user-form-data`, `submit-form-data`, `mailing`, `refund`, `discount-start`, `discount-end`, `bonus-accrual`, `bonus-expiration` (names from `BULL_CONSUMERS` in `cms/src/config/constants.ts:39`).

**Do not create:** `notification_templates`, `event_handlers`. Create a row in `events` with the right `actions` and `mailing.conditions`.

---

## 7. You need to "log admin actions" (create, delete, update)

**Use the `@Journalable` decorator — NOT your own table.**

Why (in code):
- `cms/src/modules/journal/decorators/journalable.decorator.ts` — the `@Journalable(JournalingEvents.X)` decorator on a controller method attaches `'journaling-event'` metadata.
- `DeveloperJournalInterceptor` (`cms/src/modules/journal/developer-journal.interceptor.ts:79-100`) reads the metadata and writes a row into `journal_records` (`JournalRecordEntity`) with fields `action`, `entityId`, `delta jsonb`, `admin`, `result`, `error`, `journaling_event`, `module_name`.
- If the right `JournalingEvents` value doesn't exist — add it in `cms/src/modules/journal/types/journaling-events.ts`. If the right `ModuleNameEnum` value doesn't exist — add it in `cms/src/modules/journal/types/module-name-enum.ts` (key = controller name without `Controller`, uppercase).
- GET requests are intentionally skipped by the interceptor (`developer-journal.interceptor.ts:75`).

**Do not create:** `admin_action_log`, `user_audit`.

---

## 8. You need to "store entity change history" (for rollback)

**Use `entity_versions` — it is universal and works automatically for every table with `attributes_sets`.**

Why (in code):
- `EntityVersionEntity` (`cms/src/modules/entity-versions/entities/entity-version.entity.ts`) — `entity_name`, `entity_id`, `version`, `action varchar(10)`, `data jsonb`, `admin_id`. Unique `(entityName, entityId, version)`.
- The migrations `cms/src/migrations/1870796200002-create-entity-versioning.ts` and `1870796400000-entity-versions-cleanup-on-delete.ts` create triggers via `information_schema` — the list of tables is discovered dynamically (see [`data-model-core.md §3`](./data-model-core.md#3-dynamic-consumer-table-whitelist-via-information_schema)).

**Do not create:** `products_history`, `pages_history`.

---

## 9. You need "free-form" entity or module settings (arbitrary config)

**Use the existing jsonb column that already lives on the entity.**

Available "free-form" jsonb fields (all grep-confirmed):
- `attributes_sets.properties` (jsonb) — attribute set properties.
- `pages.config` (jsonb `Record<string, number>`) — catalog page output settings.
- `modules.config` (jsonb `Record<string, any>`) — module settings.
- `blocks.custom_settings` (jsonb `BlockCustomSettings`) — block settings.
- `events.actions` (jsonb), `events.mailing` (jsonb) — event settings.
- `general_types` (via `ModuleEntity.config`) — shared settings.
- `users.state` (jsonb) — user-side client state.
- `orders.discount_config` (jsonb).
- `orders.form_data` (jsonb).
- `form_data.form_data` (jsonb).
- `collection_rows.form_data` (jsonb).

**Do not create:** `xxx_settings`, `xxx_config` — these are almost certainly jsonb inside an existing table.

---

## 10. You need to "index an arbitrary attribute for fast search"

**Use `index_attributes` + `index_attribute_data`.**

Why (in code):
- `IndexAttributeEntity` (`cms/src/modules/index-attributes-sets/entities/index-attribute.entity.ts`) — the registry of which attributes on which consumer tables are indexed.
- `IndexAttributeDataEntity` (`cms/src/modules/index-attributes-sets/entities/index-attribute-data.entity.ts`) — a denormalized "attribute value per language" row. Unique index on `(dataId, attributeId, tableName, identifier, langCode)`.
- Bull queue `index-data`, consumer `IndexDataConsumer` (`@Process('index')`, `@Process('index-all')`) — `cms/src/modules/index-attributes-sets/consumers/index-data.consumer.ts`.

**Do not create:** `searchable_products`, `searchable_pages`.

---

## 11. You need to "link entity X to entity Y" (M2M)

First check whether a generic reference already exists. The CMS has plenty:
- `CollectionRowEntity.entity_type` + `entity_id` — a generic reference from a collection row to any entity.
- `PositionEntity.objectType` + `objectId` (+ `objectCategoryId`) — a generic position binding to any object.
- `EntityVersionEntity.entityName` + `entityId` — a generic version binding.
- `JournalRecordEntity.entityId` + `moduleName` — a generic journal-record binding.

If you really need a **hard** link (FK with CASCADE on delete, an index) — yes, an M2M table is in order. The repo follows the `<a>_<b>_mn` template (e.g. `block_pages_mn`, `menu_pages_mn`, `module_general_types_mn`, `users_groups_mn`, `module_attribute_set_types_mn`).

---

## 12. You need "cart", "wishlist", "recently viewed", or "user order history"

**Use the existing machinery — do NOT create tables.** All required tables and services already exist.

Why (in code):
- **Cart / wishlist for authenticated users — already there as dedicated normalized tables:**
  - `cart_items` (`CartItemEntity`) — `userId`, `productId`, `qty`, `addedAt`, BIGSERIAL id, `UNIQUE(user_id, product_id)`, FK `ON DELETE CASCADE` on both `users.id` and `products.id`. Index `idx_cart_user(user_id)`. **Language-agnostic** — no `lang_code`.
  - `wishlist_items` (`WishlistItemEntity`) — same shape minus `qty`.
  - Operate through `CartService` / `WishlistService` (`cms/src/modules/user-activity/services/`). Add/update is `INSERT ... ON CONFLICT (user_id, product_id) DO UPDATE` (cart) / `DO NOTHING` (wishlist), wrapped in a transaction with `pg_advisory_xact_lock(userId)` to serialize concurrent writes from the same user.
  - The legacy `users.system_attributes_sets jsonb` storage (per-language `cart`/`wishlist` inside the user row) was **removed** by migration `1870797500001-drop-user-activity-system-attribute-set.ts` (2026-05-22). Do not reintroduce it.
- **Guest cart / wishlist:** `GuestCartStorageService`, `GuestWishlistStorageService` (`cms/src/modules/user-activity/services/`) — keyed by `guestId` (a UUID from the `X-Guest-Id` header). Redis keys `cart:guest:<uuid>` (TTL 30 days) and `wishlist:guest:<uuid>` (TTL 90 days); hard limit `CART_MAX_ITEMS = WISHLIST_MAX_ITEMS = 500`. Constants live in `cms/src/modules/user-activity/types/guest-storage-config.ts`.
- **Recently viewed / trending / search history / recommendations — already there as content endpoints on `content-blocks.controller.ts`:**
  - `GET /api/content/blocks/:marker/trending`
  - `GET /api/content/blocks/:marker/recently-viewed`
  - `GET /api/content/blocks/:marker/repeat-purchase`
  - `GET /api/content/blocks/:marker/personal-recommendations`
  - `GET /api/content/blocks/:marker/cart-complement`
  - `GET /api/content/blocks/:marker/cart-similar`
  - `GET /api/content/blocks/:marker/wishlist-similar`

  Backed by **implemented** Bull consumers in `cms/src/modules/user-activity/consumers/`: `TrendingConsumer`, `RecommendationConsumer`, `RefreshPurchaseHistoryConsumer`, `SegmentsRecomputeConsumer`, `DormantReactivationConsumer`, `CleanupOldActivityConsumer`, `FlushActivityBufferConsumer`. Job names — `BULL_CONSUMERS` (`cms/src/config/constants.ts:40-70`).
- **A user's order history:** `orders.user_id` + `orders_history` (via the `OrderEntity.history` relation).

**Do not create:** `user_cart`, `user_wishlist`, `carts (user_id, items jsonb)`, `wishlists`, `recently_viewed`, `user_orders_history`, `personal_recommendations`, `trending_products`. Everything you need is in `cart_items`, `wishlist_items`, `user_activity_events`, the `user-activity` Bull queue, and the recommendation content endpoints listed above.

---

## Summary: decision tree

```
Need to store a new field?
  → Does the entity have attribute_set_id?
    → YES → extend the attribute_set schema (§1)
    → NO → is there an existing jsonb column with a fitting meaning (§9)?
      → YES → put it there
      → NO → do you actually need a column? (hot WHERE / index?)
        → YES → SQL column (with a migration)
        → NO → extend a jsonb or create an attribute_set

Need to store a list of similar records?
  → Is it a form for accepting user input? → forms + form_data (§5)
  → Just a list / reference data? → collections + collection_rows (§2)

Need a new "type" (page / block / product / order)?
  → Differences only in data? → new attribute_set, same general_type
  → Differences in output logic? → new value in GeneralType + a seed (§3, §4)

Need to react to an event (push / email / WS)?
  → events + EventsProcessor (§6)

Need to journal? → @Journalable (§7)
Need version history? → entity_versions (§8)
Need a cart / wishlist / view history? → §12
```

---

## Related documents

- [`data-model-core.md`](./data-model-core.md) — what an attribute_set is, jsonb columns, `information_schema`.
- [`use-cases.md`](./use-cases.md) — concrete "if you need X, use Y" cases.
- [`entities-catalog.md`](./entities-catalog.md) — full entity reference.
