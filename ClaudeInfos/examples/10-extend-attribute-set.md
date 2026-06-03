<!-- audit: 5/5 (2026-05-13) endpoints[POST /attributes-sets, PUT /attributes-sets/:id, PUT /attributes-sets/:id/schema, DELETE /attributes-sets/:id, POST /attributes-sets/:id/copy-values, POST /attributes-sets/log-copy-entity], fields[attributes_sets.type_id, attributes_sets.schema jsonb, attributes_sets.hash, attributes_sets.properties jsonb; TWO different information_schema scans: (1) attribute_set_id FK column — isThereWhoUsingMe in base-attributes-sets.service.ts:259, (2) attributes_sets jsonb column — consumer 'update-changing' in attributes-sets.consumer.ts:75], queues[@InjectQueue('attributes-sets') + Processor 'attributes-sets' + job 'update-changing'], ws[attributesSetsChanging start/finish/error via AdminSocketGateway.sendSocketNotification on each job hook], fk[attributes_sets.type_id->attribute_set_types.id; consumer tables have NO formal FK on attributes_sets — link is by attribute_set_id column without CASCADE] -->

# 10. Extending an existing `attribute_set` (add an attribute to a product/admin/user)

## Purpose

The core document for understanding OneEntry's "flexible model". Any task like:
- "Add `weight_kg` to a product field."
- "Add a `consent_marketing` checkbox to a user."
- "Give the admin a custom `department` field."
- "Attach a certificate file to a category."

— is **NOT a table migration** and **NOT adding a column**. It's an **update of the `attribute_set` JSON schema** — an instant operation without downtime. Immediately after that, all ~89 entities with `attribute_set_id` start seeing the new attribute in the API.

If you're unsure whether you need a migration or to edit `attribute_set` — the answer is almost always "attribute_set". A column is only needed for:
1. A unique index (`email`, `login`, `import_id`).
2. An FK to another table (`status_id`, `parent_id`).
3. High-load range queries on millions of rows without Elasticsearch.

## Entities and dependency hierarchy

```
attribute_set_types         — type dictionary (forProducts, forPages, forBlocks, ...)
  ↑ type_id (no CASCADE)
attributes_sets             — attribute set: schema (jsonb), hash, properties (jsonb)
                              identifier UNIQUE
  ↑ attribute_set_id (NO FK, discovered via information_schema)
products, users, user_groups, admins, blocks, pages, templates, forms,
events, discounts, orders_storage, etc. — consumers (consumer tables)

  ↓ values are stored in their attributes_sets jsonb column
  → { [lang]: { [attrIdentifier]: value } }
```

**Critical:** consumer tables have NO formal FK to `attributes_sets` (no `@JoinColumn`, no CASCADE). The link is discovered on the fly via PostgreSQL `information_schema`:

```sql
SELECT table_name AS name
FROM information_schema.columns
WHERE column_name = 'attribute_set_id'
  AND table_name NOT IN ('index_attribute_data');
```

See `cms/src/modules/attributes-sets/services/base-attributes-sets.service.ts:256-275` (`isThereWhoUsingMe`). This means: a new entity with `attribute_set_id` automatically becomes a consumer without modifying the attribute_sets management code.

| Table | Base class | Key fields |
|---|---|---|
| `attributes_sets` | `BaseAbstractEntity` | `identifier` UNIQUE, `type_id` (FK on type), `title`, `schema` jsonb (`AttributesSetsSchema`), `hash` (for optimization), `properties` jsonb, `position_id`, `is_visible` |
| `attribute_set_types` | — | `forProducts`, `forPages`, `forBlocks` (`'forBlocks'`), `forOrders`, `forUsers`, `forUserGroups`, `forAdmins`, `forDiscounts` |

## Related `general_types` and `attribute_sets`

`AttributesSetType` (important: this is the **type** of the set, not to be confused with the attribute type inside the schema):
- `forAdmins` — admin custom fields (department, phone).
- `forBlock` (= `'forBlocks'`) — page block fields + form fields.
- `forOrders` — analytical / filtering order fields (values are stored in `form_data`, see [04-order-flow.md](./04-order-flow.md)).
- `forPages` — SEO fields, banner, page layout options.
- `forProducts` — product fields (price, SKU, color, stock).
- `forUsers` — user fields (loyalty_level, birth_date).
- `forUserGroups` — group fields (discount_percent, delivery_zone).
- `forDiscounts` — discount fields (banner, terms, landing_url).

`AttributeType` (attribute value type):
- Primitives: `string`, `integer`, `real`, `float`, `json`, `spam`.
- Text: `text`, `textWithHeader` (with header). Value — `{htmlValue, plainValue, mdValue, params}`.
- Time: `date`, `time`, `dateTime`, `timeInterval`. Value — `{fullDate, formattedValue, formatString}`.
- Files: `file`, `image`, `groupOfImages`. Value — `{filename, downloadLink, previewLink, size, params, contentType}`.
- Choice: `list` (value `{title, value, extended}`), `flag` (= `'radioButton'` — checkbox/radio).
- Special: `button`, `entity`.

Special flags in `SchemaItem` (`attributes-sets.interface.ts:23-55`):
`isPrice, isSku, isCurrency, isTaxRate, isPassword, isLogin, isSignUp, isNotificationEmail, isNotificationPhonePush, isNotificationPhoneSMS, isVisible, isProductPreview, isCompress, isIcon, isRatingValue`. They mark the attribute's role for UI/business logic.

## Full jsonb with data

### Existing products attribute_set (id=9, type `forProducts`)

```json
{
  "id": 9,
  "identifier": "products-coffee",
  "typeId": 5,
  "title": "Product attributes (coffee)",
  "isVisible": true,
  "hash": "a7c9d2...",
  "properties": {},
  "schema": {
    "price": { "type": "real",   "identifier": "price", "isPrice": true, "position": 1, "localizeInfos": { "en_US": { "title": "Price" } } },
    "sku":   { "type": "string", "identifier": "sku",   "isSku": true,   "position": 2, "localizeInfos": { "en_US": { "title": "SKU" } } },
    "cover": { "type": "image",  "identifier": "cover", "isProductPreview": true, "isCompress": true, "position": 3, "localizeInfos": { "en_US": { "title": "Cover" } } }
  }
}
```

### After `PUT /:id/schema` — `weight_kg` and `material` were added

```json
{
  "id": 9,
  "schema": {
    "price":     { "type": "real",   "identifier": "price",     "isPrice": true, "position": 1, "localizeInfos": { "en_US": { "title": "Price" } } },
    "sku":       { "type": "string", "identifier": "sku",       "isSku": true,   "position": 2, "localizeInfos": { "en_US": { "title": "SKU" } } },
    "cover":     { "type": "image",  "identifier": "cover",     "isProductPreview": true, "isCompress": true, "position": 3, "localizeInfos": { "en_US": { "title": "Cover" } } },
    "weight_kg": { "type": "real",   "identifier": "weight_kg", "position": 4, "localizeInfos": { "en_US": { "title": "Weight, kg" } } },
    "material":  { "type": "list",   "identifier": "material",  "position": 5,
                   "listType": "single",
                   "listTitles": { "en_US": { "wool": "Wool", "cotton": "Cotton", "synthetic": "Synthetic" } },
                   "localizeInfos": { "en_US": { "title": "Material" } } }
  }
}
```

### What happens to `products.attributes_sets` after extension

Before:
```json
{ "en_US": { "price": 1450, "sku": "ETH-YRG-250" } }
```

After — the same! **Existing product values are NOT changed.** New attributes appear as `undefined`/null until the admin fills them manually (or import populates them). Optionally via `POST /:id/copy-values` you can copy defaults from another set.

## Admin API (`@Controller('attributes-sets')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/attributes-sets` | `settings.attributesSets.create` | Create a new set |
| `PUT` | `/attributes-sets/:id` | `settings.attributesSets.update` | Update `title`, `properties`, `typeId` |
| `PUT` | `/attributes-sets/:id/schema` | `settings.attributes.changePositions` | **Key one!** Update the `schema` jsonb |
| `DELETE` | `/attributes-sets/:id` | `settings.attributesSets.delete` | Delete (checks `isThereWhoUsingMe` — if used by at least one entity, returns `{result: false, message: 'attribute_set_is_being_used'}`) |
| `PUT` | `/attributes-sets/:id/position` | — | Reorder sets |
| `PUT` | `/attributes-sets/:id/change-visibility` | `settings.attributesSets.switching` | Visibility |
| `POST` | `/attributes-sets/:id/copy-values` | — | Copy values from another set |
| `POST` | `/attributes-sets/log-copy-entity` | — | Journal the copy operation |

```http
PUT /attributes-sets/9/schema

{
  "price":     { "type": "real",   "identifier": "price",     "isPrice": true, "position": 1, "localizeInfos": { "en_US": { "title": "Price" } } },
  "sku":       { "type": "string", "identifier": "sku",       "isSku": true,   "position": 2, "localizeInfos": { "en_US": { "title": "SKU" } } },
  "cover":     { "type": "image",  "identifier": "cover",     "isProductPreview": true, "position": 3, "localizeInfos": { "en_US": { "title": "Cover" } } },
  "weight_kg": { "type": "real",   "identifier": "weight_kg", "position": 4, "localizeInfos": { "en_US": { "title": "Weight, kg" } } },
  "material":  { "type": "list",   "identifier": "material",  "position": 5, "localizeInfos": { "en_US": { "title": "Material" } } }
}
```

Returns `boolean`. Inside `AdminAttributesSetsService.updateSchema`:
1. Overwrites `attributes_sets.schema` jsonb.
2. Recomputes `hash` (for cache invalidation).
3. Pushes a job to Bull queue `'attributes-sets'`:
   ```ts
   await this.attributesSetsQueue.add('update-changing', { deletion, aId: id, id: null });
   ```

## Behind the scenes

### Bull queue `'attributes-sets'` + consumer

**Note:** the queue name is `'attributes-sets'`, it's NOT in the `BULL_QUEUES` constant (`cms/src/config/constants.ts`). Registration is direct via `@InjectQueue('attributes-sets')` (`admin-attributes-sets.service.ts:29`) and `@Processor('attributes-sets')` (`attributes-sets.consumer.ts:18`).

Job `'update-changing'` (see `attributes-sets.consumer.ts:58`) does the following:
1. Via `information_schema.columns WHERE column_name = 'attributes_sets'` finds all consumer tables (including future ones added later).

   > **Important — two different `information_schema.columns` scans in this module:**
   > - `isThereWhoUsingMe` (`base-attributes-sets.service.ts:259`) looks for tables with the FK column `attribute_set_id` (the full list of consumer entities attached to the set).
   > - consumer `'update-changing'` (`attributes-sets.consumer.ts:75`) looks for tables with the jsonb column `attributes_sets` (where attribute values themselves are stored and need updating).
   >
   > The column names are similar (`attribute_set_id` vs `attributes_sets`), but the logic and purpose are different.
2. Reads the current `schema` of the updated set.
3. For each consumer table:
   - If an attribute has `isProductPreview` / `isSku` / `isPrice` / `isCurrency` / `isIcon` / `isTaxRate` — these are markers requiring reindexing.
   - Updates `index_attribute_data` for filters and sorting.
   - Removes values of attributes removed from the schema (if `deletion=true`).
4. On completion emits a WebSocket event via consumer hooks.

### WebSocket — `attributesSetsChanging`

Consumer hooks **automatically** broadcast:
- `@OnQueueActive` → `socketService.sendSocketNotification({jobId, aId}, 'start', 'attributesSetsChanging')`.
- `@OnQueueCompleted` → `'finish'`.
- `@OnQueueFailed` / `@OnQueueError` → `'error'`.

This means: **any** new `@Process(...)` in `AttributesSetsConsumer` automatically gets start/finish/error broadcasts without extra code. Just put `aId: attributesSetId` in `job.data`.

On the frontend, `cms_frontend/src/components/shared/AppInformer.js` listens to this channel and writes `aId` into `blockersReducer.attributeSets[]`. The UI uses this array to block editing of sets currently being processed (see `agents_datasets/ClaudeInfos/patterns-journal-blockers-versioning.md` — this is an **advisory** lock, not a mutex).

### Journal

`ATTRIBUTES_SET_CREATED, ATTRIBUTES_SET_UPDATED, ATTRIBUTES_SET_DELETED, ATTRIBUTES_SET_VALUES_COPIED`.

`PUT /:id/schema` is marked `@Journalable(ATTRIBUTES_SET_UPDATED)` — the schema diff lands in the journal.

### Permissions

`settings.attributesSets.{create, update, delete, switching, changePositions}`, `settings.attributes.{create, update, delete, changePositions}`.

## Links to other files

- [01-catalog-product.md](./01-catalog-product.md) — a product `attribute_set` change is immediately reflected in product card UIs and catalog filters.
- [02-content-page.md](./02-content-page.md) — `forPages` `attribute_set` for page SEO fields.
- [08-users-and-groups.md](./08-users-and-groups.md) — extending `forUsers` / `forUserGroups`. The Bull consumer `change-user-attribute` (see [06-event-notification.md](./06-event-notification.md)) additionally handles user attribute changes.
- [07-import-catalog.md](./07-import-catalog.md) — bulk creation/update of attribute_set during blueprint import.
- `agents_datasets/ClaudeInfos/data-model-core.md` — fundamental explanation via information_schema.

## Antipattern

**"I'll just do ALTER TABLE products ADD COLUMN weight_kg numeric."** Don't:

1. That's a **migration**, requires a cms deploy and `typeorm:migration:run` on prod.
2. The product already has an `attributes_sets` jsonb column for this.
3. A column is not localized (and weight in the UK in pounds requires a different value!).
4. A column doesn't automatically integrate into `index_attribute_data`, Elastic, catalog filters, or the product edit UI.
5. A column is needed only when weight is range-searched in SQL on millions of rows (which is usually false for a catalog — Elastic handles it).

Correct way: `PUT /attributes-sets/9/schema` adds `weight_kg: { type: 'real', position: 4, localizeInfos: {...} }`. The Bull job `'attributes-sets'` itself:
- finds via `information_schema` all consumer tables (`products`, `users`, ...);
- updates indexes;
- broadcasts WS `attributesSetsChanging`;
- admin tabs see the new field in the product edit form within 1 second.

**"Let's add a separate `product_attributes` table with (product_id, attribute_id, value)."** The EAV antipattern in its purest form. OneEntry already does this natively via jsonb — it's indexed by PostgreSQL, instantly serialized, merged via CRDT, and requires no JOINs on read.

**"Delete attribute_set on production directly via SQL."** Don't: the `isThereWhoUsingMe` check (via the same `information_schema` scan) protects against deleting a used set. If you delete via SQL — consumers' `attribute_set_id` will dangle on a non-existent ID, and the next read of `attribute_set` via JOIN will return an empty schema / fail. Delete only via `DELETE /attributes-sets/:id`, which returns `attribute_set_is_being_used` if anyone is using it.
