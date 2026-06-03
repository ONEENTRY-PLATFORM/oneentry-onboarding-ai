<!-- audit: 5/5 (2026-05-13) endpoints[GET /index-attributes, GET /index-attributes/types], fields[index_attribute_data.data_id, index_attribute_data.table_name (IndexTableType products/pages/admins/users/user_groups/blocks/orders/templates/template_previews/discounts), index_attribute_data.attribute_in_set_id, index_attribute_data.lang_code, index_attribute_data.is_price/is_sku/is_currency/is_product_preview/is_icon/is_tax_rate, index_attribute_data.search_value, index_attribute_data.payment_stages jsonb, index_attributes.identifier+table_name UNIQUE], queues[@Processor('index-data') (= BULL_QUEUES.indexData) + jobs index/index-all], ws[indexData (start/processing/finish/error via AdminSocketGateway.sendSocketNotification), indexHealth (health statistics)], fk[index_attribute_data.attribute_id->index_attributes.id, index_attributes.type_id->index_attribute_types.id; logical (no formal FK): index_attribute_data.data_id->{table_name}.id, attribute_set_id->attributes_sets.id] -->

# 16. Attribute index: filters, search, prices

## Purpose

`attributes_sets` stores values **in jsonb** — convenient for writes, bad for search: "give me every product priced 1000-2000 $ with material `cotton`" over the jsonb column of millions of products is a scan with CPU overhead.

OneEntry's solution is the **denormalized index table `index_attribute_data`**: for every `(consumer_row, attribute, lang)` pair a separate row is written with a **flat value**, against which Postgres can already do fast SELECT with WHERE+ORDER+LIMIT.

Scenarios:

- Catalog frontend: "filter by price, by SKU, by checkbox attributes" — `GET /index-attributes?type=products` returns the expanded grid for filters.
- Admin "Products" tab with sorting by any attribute — `ORDER BY index_attribute_data.search_value`.
- Product lookup by part of SKU/name — fulltext on `search_value`.
- A product price change → automatic emit of `product.price-updated` → subscribers (the events module) send notifications to subscribers.

## Entities and dependency hierarchy

```
index_attribute_types          — dictionary of types of indexed attributes
  ↑ type_id
index_attributes               — registry of indexed attributes
                                 UNIQUE (identifier, table_name)
                                 — name jsonb, additionalInfo/additionalFields jsonb
  ↑ attribute_id (FK)
index_attribute_data           — actual values (denormalization)
                                 UNIQUE (data_id, attribute_id, table_name, identifier, lang_code)
                                 — search_value, value, flags, paymentStages jsonb

attributes_sets (jsonb)        — source of truth (changes here → reindex)
{consumer_table}.id            — data_id points to a specific row
                                 (consumer table: products/pages/admins/users/user_groups/blocks/orders/templates/template_previews/discounts)
```

| Table | Base class | Key fields |
|---|---|---|
| `index_attributes` | `BaseAbstractEntity` | UNIQUE `(identifier, table_name)`, `type_id` (FK), `name jsonb` (`CommonLocalizeInfos`), `additionalInfo`/`additionalFields jsonb`, `is_active` |
| `index_attribute_data` | `BaseAbstractEntity` | UNIQUE `(data_id, attribute_id, table_name, identifier, lang_code)`, flags `isPrice/isSku/isCurrency/isProductPreview/isIcon/isTaxRate`, `search_value`, `payment_stages jsonb` |
| `index_attribute_types` | — | Type dictionary |

**`IndexTableType`** (see `cms/src/modules/index-attributes-sets/types/index-table.type.ts`):
- `products`, `pages`, `admins`, `users`, `user_groups`, `blocks`, `orders`, `templates`, `template_previews`, `discounts`.

These are **all** consumer tables that can be indexed. When a new one is added in the future, it must be added to the enum.

## Connection to `attributes_sets` (source of truth)

`index_attribute_data` is a **derived** structure. The source of truth is:

1. `attributes_sets.schema` — which attributes belong to a set, plus their types.
2. `<consumer_table>.attributes_sets` jsonb — the values.

A schema or value change triggers a **reindex** via the Bull `index` job (see below). There is no direct write API for `index_attribute_data` — only through the consumer.

`index_attribute_data.attribute_in_set_id` is the "attribute key in the schema" shaped like `<type>_id<id>` (e.g. `image_id7`, `real_id12`). The frontend uses it to quickly resolve the attribute set from an index row.

## Full jsonb with data

### `index_attributes` (defining the "Price" attribute for products)

```json
{
  "id": 71,
  "identifier": "price",
  "tableName": "products",
  "typeId": 4,
  "isActive": true,
  "name": {
    "en_US": { "title": "Price" }
  },
  "additionalInfo": {
    "min": 0,
    "max": 999999,
    "currency": "USD",
    "splitParts": null
  },
  "additionalFields": {}
}
```

Similarly — for SKU (`identifier='sku'`), cover (`identifier='cover'`, `isProductPreview=true`), checkbox material (`identifier='material'`, `type='list'`).

### `index_attribute_data` (index rows for product id=57)

```json
[
  {
    "id": 9101,
    "dataId": 57,
    "tableName": "products",
    "attributeId": 71,
    "attributeSetId": 9,
    "attributeInSetId": "real_id12",
    "langCode": "en_US",
    "value": "1450",
    "searchValue": "1450",
    "isPrice": true,
    "isSku": false,
    "isCurrency": false,
    "isProductPreview": false,
    "isIcon": false,
    "isTaxRate": false,
    "position": 1,
    "paymentStages": null,
    "updatedDate": "2026-05-13T11:24:18.000Z"
  },
  {
    "id": 9102,
    "dataId": 57,
    "tableName": "products",
    "attributeId": 72,
    "attributeSetId": 9,
    "attributeInSetId": "string_id14",
    "langCode": "en_US",
    "value": "ETH-YRG-250",
    "searchValue": "eth-yrg-250",
    "isPrice": false,
    "isSku": true,
    "isCurrency": false,
    "isProductPreview": false,
    "isIcon": false,
    "isTaxRate": false,
    "position": 2
  },
  {
    "id": 9103,
    "dataId": 57,
    "tableName": "products",
    "attributeId": 73,
    "attributeSetId": 9,
    "attributeInSetId": "image_id17",
    "langCode": "en_US",
    "value": "files/project/product/57/coffee-arabica-hero.jpg",
    "searchValue": null,
    "isPrice": false,
    "isSku": false,
    "isProductPreview": true,
    "isCompress": false,
    "position": 3
  },
  {
    "id": 9104,
    "dataId": 57,
    "tableName": "products",
    "attributeId": 71,
    "attributeSetId": 9,
    "attributeInSetId": "real_id12",
    "langCode": "de_DE",
    "value": "1450",
    "searchValue": "1450",
    "isPrice": true,
    "position": 1
  }
]
```

**Every (data_id, attribute, lang_code) gets its own row.** For one product with 10 attributes and 3 locales you get **30 rows** in the index. That's expected — the index is designed for fast reads, not minimal footprint.

### Split-price example (`payment_stages` jsonb on an index row)

If a product's price splits into stages (see also [12-payments-and-refunds.md](./12-payments-and-refunds.md#payment_stages-prepayment--balance)):

```json
{
  "id": 9105,
  "dataId": 57,
  "tableName": "products",
  "attributeId": 71,
  "attributeInSetId": "real_id12",
  "langCode": "en_US",
  "value": "4350",
  "isPrice": true,
  "paymentStages": [
    { "marker": "prepayment", "title": "Prepayment 30%", "value": 1305.00, "position": 1 },
    { "marker": "balance",    "title": "Balance",        "value": 3045.00, "position": 2 }
  ]
}
```

`paymentStages` is computed from `attributes_sets.schema[k].splitPrice/splitUnit/splitParts` during indexing.

## Admin API (`@Controller('index-attributes')`)

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/index-attributes?type=products` | Get the list of indexed attributes for the type + data. `type` is a required query parameter, value from `IndexTableType`. |
| `GET` | `/index-attributes/types` | List of available attribute types (`index_attribute_types`). |

Protected by `AdminAuthGuard`, **without a specific `@GrantByPermission`** — any authenticated admin can read the index (it's service info for the UI).

```http
GET /index-attributes?type=products
```

Returns a structure like:

```json
[
  {
    "id": 71,
    "identifier": "price",
    "tableName": "products",
    "name": { "en_US": { "title": "Price" } },
    "type": { "id": 4, "title": "real" },
    "additionalInfo": { "min": 0, "max": 999999 },
    "attributeData": [
      { "dataId": 57, "value": "1450", "langCode": "en_US", "isPrice": true },
      { "dataId": 58, "value": "890",  "langCode": "en_US", "isPrice": true }
    ]
  }
]
```

## Behind the scenes

### Bull queue `index-data` (`BULL_QUEUES.indexData = 'index-data'`)

`IndexDataConsumer` (`cms/src/modules/index-attributes-sets/consumers/index-data.consumer.ts:33`) — `@Processor('index-data')`. Job names:

| Job | Payload | What it does |
|---|---|---|
| `index` | `{ aId, tableName, deletion?: boolean }` | Full reindex of one consumer table (`products` / `pages` / ...). When `deletion=true` it clears orphans + `refreshViews(tableName)`. |
| `index-all` | `{}` | Background periodic (by cron). Walks every table from `IndexTableType` and emits WS statistics on the `indexHealth` channel. |

### Triggers of the `index` job

- `PUT /attributes-sets/:id/schema` (schema changed, see 10) → indirectly via `AttributesSetsConsumer.update-changing` → `indexDataQueue.add('index', ...)`.
- Direct attribute changes for a specific entity (`PUT /products/:id`, `PUT /pages/:id`, etc.).
- Entity deletion → `index` with `deletion=true`.

### WS channels

The consumer's hooks auto-broadcast via `AdminSocketGateway.sendSocketNotification`:

| Channel | When |
|---|---|
| `indexData` | `start` (`@OnQueueActive`) / `finish` (`@OnQueueCompleted`) / `error` (`@OnQueueFailed/@OnQueueError`) |
| `indexData` | `processing` — inside `@Process('index')` periodically, with payload `IndexNotificationType { total, current, time }` |
| `indexHealth` | `@Process('index-all')` sends an index health summary |

The frontend `cms_frontend/src/components/shared/AppInformer.js` subscribes to `indexData` and writes statuses into `blockersReducer.indexProductsStatus` — the UI disables "Reindex" while work is in progress.

### Stop mechanism via EventEmitter2

```ts
@OnEvent('stop.index-data')
public onStopIndex() {
  this.locker = true;
}
```

Any other code in cms can call `eventEmitter.emit('stop.index-data')` → the consumer sets `locker=true` → the current chunk finishes indexing, the remainder of the job is skipped, `job.remove()` is called. Used for urgent stops (for example, an admin presses "Stop" in the UI).

### EventEmitter2: `product.price-updated`

```ts
export const PRODUCT_PRICE_UPDATED_EVENT = 'product.price-updated';
// payload: { productIds: number[], langCodes: string[] }
```

At the end of indexing in `@Process('index')` for `tableName=products`, if the index touched attributes with `isPrice=true`, the consumer emits this event. Subscribers (the `events` module) catch it and check:
- Are there `events` with `type='attribute'`, `attribute='price'`, `conditions='less'`?
- If yes → enqueue a `change-product-attribute` job in the Bull `events` queue → notification to subscribers (see [06-event-notification.md](./06-event-notification.md)).

This is **decoupling** — the index doesn't know about events, the events module doesn't know about the index, the connection is only through EventEmitter2.

### Materialized views and `refreshViews`

In the `index-data` consumer, a number of tables maintain materialized views (e.g. `mv_products_index`) for the hottest reads. `IndexDataService.refreshViews(tableName)` rebuilds the related view after a reindex.

### Filtering during indexing

- Attributes with `schema[k].isVisible === false` are NOT indexed (`is_active=false` on the `index_attributes` side).
- Attributes of type `text`/`textWithHeader` are indexed by `plainValue`, not `htmlValue` (so that search doesn't hit markup).
- `groupOfImages` → a separate row for each file with a sequential `position`.

### Journal

Indexing **is not journaled** — it's a background process, not an admin action.

### Permissions

No specific permissions. The endpoint is protected by `AdminAuthGuard` + the basic `viewer` role.

## Cross-references

- [01-catalog-product.md](./01-catalog-product.md) — the catalog uses `index_attribute_data` for sorting/filtering products. The `product-elastic` Bull queue is a separate mechanism for the **Elastic index** — don't confuse it with `index-data`.
- [06-event-notification.md](./06-event-notification.md) — `EventsProcessor` listens to `product.price-updated` to trigger notifications.
- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — `PUT /attributes-sets/:id/schema` → reindex via the `attributes-sets` queue → `index-data` queue.
- [12-payments-and-refunds.md](./12-payments-and-refunds.md) — the `paymentStages` jsonb on an index row is synchronized with the `payment_stages` table.
- [15-file-upload-pipeline.md](./15-file-upload-pipeline.md) — `image` attributes create an index row with a link to S3 and `isProductPreview=true`.
- `agents_datasets/ClaudeInfos/patterns-queues-and-ws.md` — the general WS notification pattern via `sendSocketNotification`.

## Antipatterns

**"I'll plug in Elasticsearch and write products there in parallel with Postgres."** Don't do it for admin filters:

1. For the catalog frontend and admin tables, `index_attribute_data` already gives `O(log n)` queries — Postgres indexes on `data_id`, `attribute_id`, `search_value`, `lang_code` are enough.
2. Elastic is a separate dependency, separate cluster, separate update strategy.
3. Double writes mean double sync errors.
4. Background reindex (`index-all`) and the stop mechanism already exist — for Elastic they would need to be duplicated.

When Elastic **is appropriate**:
- Full-text search with morphology, facets, and ML ranking — for the **storefront** (a user query like `"freshly roasted coffee 250g"`).
- cms already has a dedicated Bull queue `product-elastic` (`BULL_QUEUES.productElastic`) for that — it updates an external Elastic. It's **not a replacement** for `index-data`, but a parallel channel for storefront search.

**"I'll put flat values straight on `products` as columns like `price_indexed`, `sku_indexed`."** Don't:

1. You'll end up with dozens of columns (`price`, `sku`, `cover`, `weight`, `material`, ...) — every new attribute = ALTER TABLE.
2. Localization breaks — a single column can't carry different values for `en_US` and `de_DE`.
3. Removing an attribute from the schema → ALTER TABLE DROP COLUMN with downtime.

`index_attribute_data` is the right solution: one table, the schema doesn't change, reindex happens in the background.
