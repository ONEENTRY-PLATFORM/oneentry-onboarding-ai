# Data model core (OneEntry CMS foundation)

This document covers three foundational concepts without which you cannot work meaningfully with `cms/`:

1. Base abstract entities — what each "domain" table inherits.
2. The JSONB structures `attributes_sets` and `localize_infos` — where "flexible" fields and translations live.
3. The dynamic consumer-table whitelist via `information_schema` — why the code does not hardcode lists of tables with attributes.

If you have just opened this folder and can read only one file — read this one.

---

## 1. Base abstract entities

File: `cms/src/shared/entities/`

| Class | File | What it adds |
|---|---|---|
| `BaseAbstractEntity` | `base-abstract.entity.ts` | `id` (PK), `createdDate` (`created_date`), `updatedDate` (`updated_date`), `version` (int, default 0), `identifier` (string, indexed) |
| `BaseAttributeSetsAbstractEntity` | `base-attribute-sets.abstract.entity.ts` | + `attributesSets` (jsonb `attributes_sets`), `attributeSetId` (int `attribute_set_id`, indexed) |
| `BasePositionAbstractEntity` | `base-position.abstract.entity.ts` | **`@deprectated` (sic, typo in code).** Empty inheritance from `BaseAbstractEntity`. NOT used by any entity in real code. Do not extend it. |

### What extends what (excerpt from grepping `extends Base*AbstractEntity`)

Entities that extend `BaseAttributeSetsAbstractEntity` (so they have `attributes_sets` jsonb + `attribute_set_id`):
- `AdminEntity` (`admins`)
- `BlockEntity` (`blocks`)
- `DiscountEntity` (`discounts`)
- `EventEntity` (`events`)
- `FormEntity` (`forms`)
- `PageEntity` (`pages`)
- `ProductEntity` (`products`)
- `TemplateEntity` (`templates`)
- `UserGroupEntity` (`user_groups`)

Entities that extend `BaseAbstractEntity` directly (they have `id/version/identifier` but **no** automatic `attribute_set_id`):
- `AttributesSetEntity` (`attributes_sets`)
- `CatalogImportTemplateEntity` (`catalog_import_templates`)
- `CollectionEntity` (`collections`)
- `DiscountSettingsEntity` (`discount_settings`)
- `IndexAttributeDataEntity` (`index_attribute_data`)
- `IndexAttributeEntity` (`index_attributes`)
- `MarkerEntity` (`markers`)
- `MenuEntity` (`menus`)
- `ModuleEntity` (`modules`)
- `OrderStatusEntity` (`order_statuses`)
- `OrderStorageEntity` (`orders_storage`)
- `PaymentAccountEntity` (`payment_accounts`)
- `PaymentSessionEntity` (`payment_sessions`)
- `PaymentStatusMapEntity` (`payment_status_map`)
- `ProductRelationsTemplateEntity` (`product_relations_templates`)
- `ProductStatusEntity` (`product_statuses`)
- `SettingsGeneralEntity` (`settings_general`)
- `TemplatePreviewsEntity` (`template_previews`)
- `UserEntity` (`users`) — but it manually adds its own `attribute_set_id` + `attributes_sets` (see below)
- `UsersAuthProviderEntity` (`users_auth_providers`)

### Special case: `UserEntity`

`users` extends `BaseAbstractEntity` (not `BaseAttributeSetsAbstractEntity`), but **manually** declares:
- `attributeSetId` (int, `attribute_set_id`),
- `attributesSets` (jsonb `attributes_sets`).

This means: from the perspective of information_schema scanning (see §3) `users` is also an attribute_set consumer.

> **HISTORY (2026-05-22):** earlier `UserEntity` also declared a system slot — `systemAttributeSetId` (int, `system_attribute_set_id`) + `systemAttributesSets` (jsonb, `@Exclude()`-d) — that stored cart/wishlist per language. Both columns were dropped by migration `1870797500001-drop-user-activity-system-attribute-set.ts` together with the `attributes_sets` row whose `identifier='user_activity_set'`. Cart and wishlist now live in dedicated normalized tables `cart_items` / `wishlist_items` (see [examples/18](./examples/18-user-activity-cart-wishlist.md)). Do not reintroduce a `system_attributes_sets` column.

**What this means for AI:** determine whether an entity has an attribute_set by the presence of the `attribute_set_id` column in its table, not by `extends X`. The primary pattern is intersecting with `information_schema.columns WHERE column_name = 'attribute_set_id'`. See §3.

---

## 2. JSONB data structures

### 2.1. `attributes_sets` (entity attribute values)

A `attributes_sets jsonb` column on every consumer table. The TypeScript type:

```ts
// cms/src/modules/attributes-sets/attributes-sets.interface.ts
export type AttributesSets = Record<
  number | string,
  Record<string, string | number | boolean | null>
>;
```

Shape: `{ [langCode]: { [attrIdentifier]: value } }`.

Example (from `attributes-sets.consumer.ts`):
```json
{
  "en_US": { "string_id19": "value", "string_id18": "" }
}
```

`langCode` looks like `en_US`, `de_DE` (see `cms/src/modules/locales/entities/locale.entity.ts`, field `code`). `attrIdentifier` is the string identifier of an attribute in the set's schema (e.g. `string_id26`).

### 2.2. `localize_infos` (localized base fields)

A `localize_infos jsonb` column — shape `{ [langCode]: { title, ...extra } }`. Base type:

```ts
// cms/src/shared/types/common.types.ts
export type LocalizeInfo<T = {}> = T & { title: string };
export type CommonLocalizeInfos = Record<string, LocalizeInfo>;
```

Per-entity extensions (e.g. `PageLocalizeInfos` in `cms/src/modules/pages/pages.interface.ts` adds `plainContent`, `htmlContent`, `menuTitle`).

Who has `localize_infos`: `pages`, `products`, `blocks`, `collections`, `discounts`, `forms`, `markers`, `menus`, `modules`, `orders_storage`, and several others. The exact whitelist comes from grepping `localize_infos` in `cms/src/**/entities/*.entity.ts` or from `SELECT table_name FROM information_schema.columns WHERE column_name = 'localize_infos'` (see `index-data.service.ts:203`).

### 2.3. The attribute set `schema` (metadata)

In the `attributes_sets` table (entity `AttributesSetEntity`, file `cms/src/modules/attributes-sets/entities/attributes-set.entity.ts`) there is a `schema jsonb` column with shape `AttributesSetsSchema = Record<string, SchemaItem>`:

```ts
// cms/src/modules/attributes-sets/attributes-sets.interface.ts
export type SchemaItem = {
  type: AttributeType;          // string/text/integer/list/image/file/...
  identifier?: string;
  localizeInfos: SchemaItemLocalizeInfos;  // translations of the attribute's display name
  position?: number;
  isPrice?: boolean;
  isSku?: boolean;
  isCurrency?: boolean;
  isTaxRate?: boolean;
  isPassword?: boolean;
  isLogin?: boolean;
  isSignUp?: boolean;
  isNotificationEmail?: boolean;
  isNotificationPhonePush?: boolean;
  isNotificationPhoneSMS?: boolean;
  isProductPreview?: boolean;
  isIcon?: boolean;
  isRatingValue?: boolean;
  isVisible?: boolean;
  rules?: JSON;
  listType?: string;
  // ...
};
```

So the same `attributes_sets` table holds both **values** (on consumer tables in jsonb) and the set's **metadata** (on the `attributes_sets` table itself, in the `schema` field).

`AttributeType` (full list of values in `cms/src/modules/index-attributes-sets/types/attribute-types.enum.ts`): `string`, `text`, `textWithHeader`, `integer`, `real`, `float`, `dateTime`, `date`, `time`, `file`, `image`, `groupOfImages`, `radioButton` (enum value `flag`), `list`, `button`, `entity`, `spam`, `json`, `timeInterval`.

### 2.4. Attribute set type

`AttributeSetTypeEntity` (`cms/src/modules/attributes-sets/entities/attribute-set-type.entity.ts`, table `attribute_set_types`) — links a set with "what it is for":

```ts
export enum AttributesSetType {
  forAdmins = 'forAdmins',
  forBlock = 'forBlocks',
  forOrders = 'forOrders',
  forPages = 'forPages',
  forProducts = 'forProducts',
  forUsers = 'forUsers',
  forUserGroups = 'forUserGroups',
  forDiscounts = 'forDiscounts',
}
```

Relation `AttributesSetEntity → AttributeSetTypeEntity` is by `type_id` (see `attributes-set.entity.ts:18-31`).

**What this means for AI:** check whether an `attributes_set_type` already fits your entity. If the task is "add customizable attributes to a discount" — `forDiscounts` already exists. If "to an order" — `forOrders`. If none fits — discuss with the user before adding a new one.

---

## 3. Dynamic consumer-table whitelist via `information_schema`

This is **the single most important pattern** in `cms/`. AI often tries to hardcode the list of attribute-consumer tables. Don't — the repo does this dynamically and must stay that way.

### Places where the code walks `information_schema`

1. **`isThereWhoUsingMe`** — `cms/src/modules/attributes-sets/services/base-attributes-sets.service.ts:256`. Checks whether anyone uses an attribute set:
   ```sql
   SELECT table_name as name FROM information_schema.columns
   WHERE column_name = 'attribute_set_id' AND table_name not in ('index_attribute_data')
   ```
   Then for every matching table it runs `SELECT ... WHERE d.attribute_set_id = $id LIMIT 1`. Returns `true` on the first hit.

2. **The Bull `update-changing` handler** — `cms/src/modules/attributes-sets/consumers/attributes-sets.consumer.ts:75`. When an attribute set changes (an attribute is added/removed from the schema), the Bull job walks every consumer table and updates its `attributes_sets` (adds an empty key for a new attribute or removes an existing one) with the filter:
   ```sql
   SELECT table_name as name FROM information_schema.columns
   WHERE column_name = 'attributes_sets' AND table_name != 'catalog_import_history'
   ```

3. **`collectConsumerTables`** — `cms/src/modules/attributes-sets/services/copy-attributes-set-values.service.ts:78`. Returns not just the table name but also a boolean `hasLocalizeInfos`. Used in the scenario of copying attribute values between languages.

4. **Attribute indexing** — `cms/src/modules/index-attributes-sets/services/index-data.service.ts`:
   - line 151: `SELECT table_name as name FROM information_schema.columns WHERE column_name = 'attributes_sets' AND table_name !='catalog_import_history'` — common pass;
   - line 203: the same query but `WHERE column_name = 'localize_infos'` — for localizable fields;
   - line 321: repeated for re-indexing.

5. **Seeds** — `cms/src/seeds/1691204640816-seed-attributes_set_date-correction.ts:22`, `cms/src/seeds/1724147125288-seed-list-multiselect-attr.ts:10` — both walk `information_schema` to fix up data across all consumer tables at once.

6. **Migrations that mutate the schema per table**: `cms/src/migrations/1870796200002-create-entity-versioning.ts:96`, `cms/src/migrations/1870796400000-entity-versions-cleanup-on-delete.ts:42`, and others — use the same approach to create triggers/functions across every consumer table.

### `IndexTableType` — a separate story

`cms/src/modules/index-attributes-sets/types/index-table.type.ts` is an **enum** listing tables that **may be** attribute-set consumer tables:

```ts
export enum IndexTableType {
  PRODUCTS = 'products',
  PAGES = 'pages',
  ADMINS = 'admins',
  USERS = 'users',
  USER_GROUPS = 'user_groups',
  BLOCKS = 'blocks',
  ORDERS = 'orders',
  TEMPLATES = 'templates',
  TEMPLATE_PREVIEW = 'template_previews',
  DISCOUNTS = 'discounts',
}
```

This enum is used in `index_attribute_data.table_name` to tag index rows. **It is NOT the source of truth** — the real list of consumer tables is computed via `information_schema`. `IndexTableType` is just typing for the column value.

The related enum `AttributesSetsTables` (`cms/src/shared/types/common.types.ts:22`) is a partial whitelist used by some specific checks; **do not treat it as the full list** of consumers.

### Why it is done this way

In OneEntry, entities (templates, modules, etc.) may be added by new migrations. A hardcoded list breaks with every new table. The dynamic approach via `information_schema` guarantees that a mass operation (`update-changing`, `copy-values`, re-index, migration) immediately sees a new table as long as it has the `attribute_set_id` or `attributes_sets` column.

**What this means for AI:**
- If you add an entity with `attribute_set_id` (either by extending `BaseAttributeSetsAbstractEntity` or by declaring the column manually) — it automatically becomes a consumer. No lists need updating.
- If you write a mass data migration over entities with attributes — repeat the pattern from `index-data.service.ts:151` or `base-attributes-sets.service.ts:256`. Don't hardcode.
- The exclusions (`catalog_import_history`, `index_attribute_data`) are service tables that happen to have the right columns but are not "real" consumers. If you add a similar service table — add it to `NOT IN (...)` next to these.

---

## 4. `general_types` — entity types

The `general_types` table (entity `GeneralTypeEntity`, file `cms/src/modules/general-types/general-types.entity.ts`) stores entity-type "markers". This is an enum-style table: a single field `type varchar(50) unique`.

The full set of values lives in `cms/src/modules/general-types/types/general-types.enum.ts`:

```ts
export enum GeneralType {
  CommonPage = 'common_page',
  ErrorPage = 'error_page',
  CatalogPage = 'catalog_page',
  Product = 'product',
  ProductPreview = 'product_preview',
  CommonBlock = 'common_block',
  ProductBlock = 'product_block',
  SimilarProductsBlock = 'similar_products_block',
  Form = 'form',
  Order = 'order',
  Service = 'Service',          // sic, capital S
  ExternalPage = 'external_page',
  Discount = 'discount',
  FrequentlyOrderedBlock = 'frequently_ordered_block',
  TrendingBlock = 'trending_block',
  RecentlyViewedBlock = 'recently_viewed_block',
  RepeatPurchaseBlock = 'repeat_purchase_block',
  SliderBlock = 'slider_block',
  PersonalRecommendationsBlock = 'personal_recommendations_block',
  CartComplementBlock = 'cart_complement_block',
  CartSimilarBlock = 'cart_similar_block',
  WishlistSimilarBlock = 'wishlist_similar_block',
}
```

The seven recommendation/cart-driven block types (`trending_block`, `recently_viewed_block`, `repeat_purchase_block`, `personal_recommendations_block`, `cart_complement_block`, `cart_similar_block`, `wishlist_similar_block`) are served by dedicated content endpoints in `content-blocks.controller.ts` and powered by Bull consumers in `cms/src/modules/user-activity/consumers/` — see [examples/18](./examples/18-user-activity-cart-wishlist.md) for the wiring.

`GeneralTypeEntity` is M2M-linked to `ModuleEntity` through the `module_general_types_mn` table (see `module.entity.ts:103`).

Entities that reference `general_types` via `general_type_id`:
- `pages` (via `PageEntity.generalTypeId` / `generalType`) — defines the page type (`common_page` / `catalog_page` / `error_page` / `external_page`).
- `blocks` (via `BlockEntity.generalTypeId` / `generalType`) — defines the block type (`common_block` / `product_block` / `similar_products_block` / `frequently_ordered_block` / `slider_block` / `trending_block` / `recently_viewed_block` / `repeat_purchase_block` / `personal_recommendations_block` / `cart_complement_block` / `cart_similar_block` / `wishlist_similar_block`).
- `orders_storage` (via `OrderStorageEntity.generalTypeId`).
- `templates` (via `TemplateEntity.generalTypeId`).

**What this means for AI:** before creating a new table for "another kind of page" or "another kind of block" — look at the `GeneralType` enum. If the value you need isn't there, often it is enough to add it to the enum plus a seed in `general_types`, rather than introduce a separate table.

---

## 5. The relationships on one diagram

```
                       attribute_set_types (forProducts, forPages, ...)
                                |
                            type_id ↓
                       attributes_sets ──── schema (jsonb) ──── SchemaItem[*]
                          (id, identifier,
                           title, schema,
                           properties)
                                |
                                |  attribute_set_id (FK on the consumer table)
                                ↓
        ┌────────────────┬──────┴──────┬─────────────────┬─────────────┐
   products          pages         blocks            forms          templates   ...  (discovered dynamically via information_schema)
   (+attrs_sets,   (+attrs_sets,  ...                                            
    +localize_infos) +localize_infos)
```

In parallel — `general_types`:
```
general_types (common_page, catalog_page, product_block, ...)
                  |
            general_type_id ↓
            pages / blocks / orders_storage / templates
```

And the index — `index_attribute_data` (one row per (data_id, table_name, attribute_id, attribute_in_set_id, lang_code)) — a denormalized table for fast search by attribute values; populated by the `index-data` consumer.

---

## The short rule

Before any task that says "add a new field / new type / new table", open:
1. This document (to know what already exists).
2. [`use-cases.md`](./use-cases.md) (to see how it has already been done).
3. [`when-not-to-create-tables.md`](./when-not-to-create-tables.md) (to see when a table is unnecessary).
