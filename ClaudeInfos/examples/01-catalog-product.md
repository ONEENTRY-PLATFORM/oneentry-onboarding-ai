<!-- audit: 5/5 (2026-05-13) endpoints[POST /products, POST /products/:id/copy, POST /products/set-status, POST /products/set-template, POST /products/empty-page, DELETE /products/:id, PUT /products/:id/change-visibility], fields[products.status_id, products.template_id, products.short_desc_template_id, products.import_id, products.attribute_schema_hash, products_pages_mn.page_id/product_id], queues[product-elastic (build-/update-product-index), relations-products, product-statuses], ws[socketService.sendMessage 'product' 'create'], fk[products_pages_mn.page_id->pages.id CASCADE, products.status_id->product_statuses.id SET NULL] -->

# 01. Product catalog (e-commerce, marketplace, B2B catalog)

## Purpose

Any product catalog:
- **E-commerce**: clothes, electronics, furniture, groceries — with photos, prices, sizes, colors, stock, SKU.
- **B2B catalog**: wholesale items with price lists and SKUs.
- **Marketplace**: items with multiple sellers, comparison, shipping options.
- **Restaurant menu / services**: a "product" with prep time, allergens, ingredients.

If the entity has **price, stock, SKU, status (in stock / on order), categories, variants** — it's `products`. If no price and status, pure content — it's [02-content-page.md](./02-content-page.md). If it's a set of uniform dictionary rows — see [09-collections.md](./09-collections.md).

## Entities and dependency hierarchy

```
pages (common)              — for catalog categories with general_type='catalog_page'
  ↑ page_id (CASCADE)
products_pages_mn           — M:N product ↔ category (product can be in multiple categories)
  ↓ product_id (CASCADE)
products                    — product card with attribute_set
  ↓ status_id (SET NULL)
product_statuses            — status dictionary: "In stock", "On order", "Sold out"
  ↑ block_id (M:N via product_blocks / block_products)
blocks                      — reusable blocks on product page (gallery, description, delivery)
  ↑ template_id
templates                   — HTML template of product card + its attribute_set
```

| Table | Base class | Key fields |
|---|---|---|
| `products` | `BaseAttributeSetsAbstractEntity` | `template_id`, `short_desc_template_id`, `localize_infos`, `is_visible`, `status_id` (FK SET NULL), `import_id` (from import), `attribute_schema_hash` / `attribute_key_value` (for Elastic indexing), `rating` jsonb, `file_upload_value` jsonb |
| `products_pages_mn` | `BaseEntity` | unique `(page_id, product_id)`, `position_id`, `category_path` |
| `product_statuses` | `BaseAbstractEntity` | `localize_infos`, `color`, hierarchy via `parent_id` |
| `product_relations_templates` | — | relations template: "similar", "compatible", "accessories" |

FK confirmed in `products/entities/product-page.entity.ts:65-75`:
```ts
@ManyToOne(() => PageEntity, ..., { onDelete: 'CASCADE', orphanedRowAction: 'delete' })
@ManyToOne(() => ProductEntity, ..., { onDelete: 'CASCADE', orphanedRowAction: 'delete' })
```
`products.status_id` — `SET NULL` (when a status is deleted, all products lose the reference but are not deleted themselves).

Order of creating a catalog from scratch:
1. **Product statuses** (`product_statuses`) — created via seed or manually through their own admin endpoint.
2. **Categories** (`pages` with `generalTypeId` = id of `catalog_page`) — see [02-content-page.md](./02-content-page.md) for page mechanics. Categories form a tree via `parent_id`.
3. **attribute_set of type `forProducts`** — defines what fields the product has (see below).
4. **Templates** — HTML templates for the product card (`template_id`) and short description (`short_desc_template_id`).
5. **Product** via `POST /products` (`CreateProductDto`) — `attributeSetId`, `localizeInfos`, `productPages` (list of categories), `statusId`, `templateId`.

## Related `general_types` and `attribute_sets`

`general_types`:
- `product` (id=1, changed in `1744702199257-update-general-types.ts` from `forCatalogProducts`).
- `catalog_page` (id=4) — for product categories.
- `product_preview` (id=5) — for preview cards in listings.
- `product_block` (id=10), `similar_products_block` (id=8), `frequently_ordered_block` — for blocks on the product page.

`AttributesSetType`:
- `forProducts` — product attributes (`price`, `sku`, `currency`, `cover`, `gallery`, `weight_kg`, `color`, `material`, `in_stock`).
- `forPages` — attributes of category pages.
- `forBlock` (`'forBlocks'`) — attributes of product card blocks.

Special flags in `SchemaItem` (`cms/src/modules/attributes-sets/attributes-sets.interface.ts:29-44`):
- `isPrice: true` — attribute is treated as price (for sorting, "price from/to" filters, discount calculations).
- `isSku: true` — SKU (shown in search, checked for uniqueness).
- `isCurrency: true` — currency.
- `isTaxRate: true` — tax rate.
- `isProductPreview: true` — image for preview (shown in catalog).
- `isCompress: true` — compress on upload.
- `isRatingValue: true` — for rating attribute.

## Full jsonb with data

### Product "Coffee Ethiopia Yirgacheffe 250g"

```json
{
  "id": 1234,
  "identifier": "coffee-ethiopia-yirgacheffe-250",
  "templateId": 3,
  "shortDescTemplateId": 5,
  "statusId": 1,
  "importId": "SKU-ETH-YRG-250",
  "isVisible": true,
  "localizeInfos": {
    "en_US": { "title": "Coffee Ethiopia Yirgacheffe 250g" }
  },
  "attributeSetId": 9,
  "attributesSets": {
    "en_US": {
      "price":    1450,
      "currency": { "title": "$", "value": "USD", "extended": { "type": "string", "value": "USD" } },
      "sku":      "ETH-YRG-250",
      "weight_kg": 0.25,
      "in_stock": true,
      "is_new":   true,
      "release_date": {
        "fullDate": "2026-03-12T00:00:00.000Z",
        "formattedValue": "12-03-2026",
        "formatString": "DD-MM-YYYY"
      },
      "color": { "title": "Light roast", "value": "light", "extended": { "type": "string", "value": "light" } },
      "cover": {
        "filename": "files/project/product/1234/images/cover.jpg",
        "downloadLink": "https://cdn.example/cloud-static/files/project/product/1234/images/cover.jpg",
        "previewLink": "https://cdn.example/cloud-static/files/project/product/1234/images/cover-preview.jpg",
        "size": 248901,
        "params": { "isImageCompressed": true },
        "contentType": "image/jpeg"
      },
      "description": {
        "htmlValue": "<p>Citrus notes and jasmine.</p>",
        "plainValue": "Citrus notes and jasmine.",
        "mdValue": "Citrus notes and jasmine.",
        "params": { "isImageCompressed": true, "editorMode": "html" }
      }
    }
  },
  "rating": { "value": 4.7, "like": 28, "dislike": 1, "votes": 30, "method": "average" },
  "productPages": [
    { "pageId": 56, "productId": 1234, "categoryPath": "catalog/coffee", "positionId": 12001 },
    { "pageId": 57, "productId": 1234, "categoryPath": "catalog/coffee/single-origin", "positionId": 12002 }
  ]
}
```

### Corresponding `attribute_set.schema` (excerpt)

```json
{
  "price":    { "type": "real",   "identifier": "price",    "isPrice": true,    "position": 1, "localizeInfos": { "en_US": { "title": "Price" } } },
  "currency": { "type": "list",   "identifier": "currency", "isCurrency": true, "position": 2, "localizeInfos": { "en_US": { "title": "Currency" } } },
  "sku":      { "type": "string", "identifier": "sku",      "isSku": true,      "position": 3, "localizeInfos": { "en_US": { "title": "SKU" } } },
  "cover":    { "type": "image",  "identifier": "cover",    "isProductPreview": true, "isCompress": true, "position": 4, "localizeInfos": { "en_US": { "title": "Cover" } } },
  "in_stock": { "type": "radioButton", "identifier": "in_stock", "position": 5, "localizeInfos": { "en_US": { "title": "In stock" } } },
  "description": { "type": "text", "identifier": "description", "position": 6, "localizeInfos": { "en_US": { "title": "Description" } } }
}
```

## Admin API (`@Controller('products')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/products` | `catalog.products.create` | Create product |
| `POST` | `/products/:id/copy` | `catalog.products.copy` | Deep copy |
| `POST` | `/products/empty-page` | — | List of products without a category |
| `POST` | `/products/page/:id` | — | Search in a category with filters |
| `POST` | `/products/set-status` | `catalog.products.editStatus` | Bulk status change |
| `POST` | `/products/set-template` | `catalog.products.setTemplate` | Bulk change of templateId/shortDescTemplateId |
| `POST` | `/products/positions/:positionId/lock` | `catalog.products.lockPositions` | Pin product position in sorting (NOT an edit lock, see `data-model-core.md`) |
| `POST` | `/products/category/:id/copy` | — | Copy products to another category |
| `POST` | `/products/category/:id/move` | — | Move products |
| `DELETE` | `/products/:id` | `catalog.products.delete` | Delete |
| `DELETE` | `/products/delete/multi` | `catalog.products.deleteMany` | Batch delete |
| `DELETE` | `/products/category/:pageId` | — | Delete all products of a category |
| `DELETE` | `/products/category/:pageId/product/:id` | — | Detach product from a category |
| `PUT` | `/products/:id/change-visibility` | `catalog.products.switching` | Visibility |
| `PUT` | `/products/:id/nested-blocks/:blockId/position` | — | Reorder blocks on the product page |

```http
POST /products

{
  "identifier": "coffee-ethiopia-yirgacheffe-250",
  "templateId": 3,
  "shortDescTemplateId": 5,
  "statusId": 1,
  "attributeSetId": 9,
  "localizeInfos": { "en_US": { "title": "Coffee Ethiopia Yirgacheffe 250g" } },
  "attributesSets": {
    "en_US": { "price": 1450, "sku": "ETH-YRG-250", "in_stock": true }
  },
  "productPages": [{ "pageId": 56, "productId": null }]
}
```

After creation the controller sends `socketService.sendMessage({ pageIds }, 'product', 'create')` (`admin-products.controller.ts:449`) — all admin tabs that have the corresponding categories open immediately show the new product.

### Important about `PUT /products/:id`

**There is no full `PUT /products/:id` for overwriting the card content** (see `agents_datasets/ClaudeInfos/data-model-core.md`). Card content (`localize_infos`, `attributes_sets`) is edited via **y-websocket CRDT** on `WS_SYNC_SERVER_PORT=3007` — the frontend creates a `Y.Doc` via `cms_frontend/src/sync-store/sync-product.store.js`, changes are written to the DB via `sync-socket.gateway.ts`. This means:
- Two admins who opened the same card **see each other's edits** in real time.
- `PUT /products/:id/change-visibility`, `POST /set-status`, `POST /set-template` — admin REST for metadata.

## Behind the scenes

- **Bull queue `product-elastic`** — `BULL_QUEUES.productElastic = 'product-elastic'`. Consumer `ProductElasticConsumer` (`cms/src/modules/products/consumers/product-elastic.consumer.ts`) accepts jobs:
  - `'build-product-index'` — full reindex (every N minutes or when attribute schema changes).
  - `'update-product-index'` — incremental (changes since last `last-updated-at` in Redis).
  This updates the external Elasticsearch with filters/sorting/full-text search. If the tariff doesn't allow Elastic — the consumer silently skips (`isAvailableForTariff()`).
- **Bull queue `relations-products`** (`findProductRelations = 'relations-products'`) — background recalculation of relations via `product_relations_templates` (similar, accessories).
- **Bull queue `product-statuses`** (`productStatuses = 'product-statuses'`) — background processing of status changes (e.g., auto-removing "new" tag after N days).
- **WS channel `'product' / 'create'` / `'update'` / `'delete'`** — `AdminSocketGateway.sendMessage`.
- **y-websocket** — separate WS server on `WS_SYNC_SERVER_PORT=3007` (`sync-socket.gateway.ts`) for CRDT synchronization of the card.
- **Journal** — `PRODUCT_CREATED, PRODUCT_UPDATED, PRODUCT_DELETED, PRODUCT_STATUS_CREATED/UPDATED/DELETED, PRODUCT_RELATION_TEMPLATE_*, ATTRIBUTE_PRODUCT_*`.
- **Permissions** — `catalog.products.{create,update,delete,switching,copy,deleteMany,updateCategories,lockPositions,changePositions,outputSettings,filterSearch,editStatus,setTemplate,createRelationTemplate,updateRelationTemplate}`.
- **`import_id`** — filled in when the product comes from [07-import-catalog.md](./07-import-catalog.md). Import uses it to find the "existing" product for updating instead of creating a duplicate.

## Links to other files

- [02-content-page.md](./02-content-page.md) — catalog categories are `pages` with `general_type='catalog_page'`.
- [04-order-flow.md](./04-order-flow.md) — `order_products.product_id` references `products.id`.
- [05-discount-promo.md](./05-discount-promo.md) — `discounts` filter products by their `attribute_set` (e.g., a discount on products with `category='coffee'`).
- [07-import-catalog.md](./07-import-catalog.md) — bulk loading of products from Excel/XML.
- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — how to add a new attribute to all products without migration.

## Antipattern

**"Let's add `products.price` and `products.cover` columns."** Don't. Price and cover are attributes:

1. Open the `attribute_set` of type `forProducts` (you can create a new one or use an existing one).
2. Add to `schema`:
   - `price` with `type: 'real', isPrice: true`.
   - `cover` with `type: 'image', isProductPreview: true, isCompress: true`.
3. Save via `PUT /attributes-sets/:id/schema` (see [10-extend-attribute-set.md](./10-extend-attribute-set.md)). The Bull queue `change-product-attribute` will recompute values for all linked products.
4. Storefront reads the price via `GET /content/products/...` — it arrives in `attributesSets.en_US.price`.

Price-as-column is only justified in a very narrow case: when you need PostgreSQL indexes on a million products with range queries and Elasticsearch indexing is impossible (`product-elastic` already provides filters on `isPrice` attributes). In practice for the OneEntry catalog — it's an attribute.

**"Let's make a separate table for product statuses."** It already exists — `product_statuses`. Don't create another one with the same fields. Just create new records via the existing admin endpoint.

**"Let's put a mutex on product editing."** There's no mutex in cms (see `agents_datasets/ClaudeInfos/data-model-core.md`). Product editing is CRDT via y-websocket, two admins see each other's edits. `lockPositions` is **pinning the sort order**, NOT a card edit lock.
