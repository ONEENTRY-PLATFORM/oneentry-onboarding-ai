<!-- audit: 5/5 (2026-05-13) endpoints[POST /import/from-blueprint, POST /import/attribute-set, POST /import/pages, POST /import/check-pages, POST /import/products, PUT /import/products, DELETE /import/history/:id], fields[catalog_import_history.import_type enum, catalog_import_history.attributes_sets/pages/products/users/orders/form_modules/product_statuses/page_products/errors json[], catalog_import_templates.data jsonb, catalog_import_templates.is_active], queues[no Bull in import itself; RabbitMQ exchangeImport ('exchange-import') + queueImport ('queue-import') + routingKey 'websocket' — receives progress from import-backend], ws[via 'websocket' routing key cms relays import progress through AdminSocketGateway to clients], fk[catalog_import_history has no FK on created entities — it's a log for convenient rollback, not an FK link] -->

# 07. Catalog import from Excel / CSV / XML / JSON / SQL

## Purpose

Any bulk upload:
- **Project bootstrap**: 5000 products and 30 categories from an Excel export of legacy 1C.
- **Nightly stock sync**: ETL from ERP on cron.
- **Blog migration**: thousands of articles from WordPress XML.
- **Transferring customers from a legacy CRM**: csv → users.
- **Importing a dictionary of statuses / markers**.

Architecturally OneEntry has **two** mechanisms:
1. **`/import/from-blueprint`** (new, recommended) — declarative JSON blueprint that describes what and in what order to create (attribute_sets → pages → products → orders). One request — atomic transaction (with `dry_run` for verification).
2. **`/import/pages` + `/import/products` + `/import/attribute-set`** (old, marked `@ApiExcludeEndpoint()`, deprecated) — step-by-step import. Used by the legacy admin frontend. **Write new code on the blueprint API.**

In parallel there's a separate microservice **`import-backend/`** (Python FastAPI) — it takes large files (xlsx > 10MB, sql-dump), parses them asynchronously via `arq`, builds a blueprint and pushes it back to cms `/import/from-blueprint`. See `import-backend/README.md`.

## Entities and dependency hierarchy

```
catalog_import_templates    — import template (Excel column mapping → OneEntry markers)
catalog_import_history      — run log: what was created (for rollback)
                              (no FK to created entities — it's a denormalized log)

products.import_id          — populated on import, used for re-import
                              (update existing instead of creating a duplicate)
users.import_id, orders.import_id — same for users and orders
pages — no import_id (pages are matched by `pageUrl`)
```

| Table | Base class | Key fields |
|---|---|---|
| `catalog_import_templates` | `BaseAbstractEntity` | `name`, `data` jsonb (mapping), `is_active` |
| `catalog_import_history` | — | `import_type` enum (`catalog/users/orders/form-data`), `attributes_sets[]`, `pages[]`, `orders[]`, `products[]`, `users[]`, `form_modules[]`, `product_statuses[]`, `page_products` (jsonb map `pageId → productIds[]`), `errors[]` (ids of products with errors) |

The import history **contains no FKs** to the created entities (`pages: number[]` is stored as a plain json array). This is intentional: on rollback the import uses `pages: [id1, id2, ...]` → batch-delete those IDs. An FK would create a cascading CASCADE nightmare.

## Related `general_types` and `attribute_sets`

- Import has **no `general_type` of its own** (it's not a content entity).
- During catalog import these are created:
  - `attribute_set` (type `forProducts`) — `POST /import/attribute-set`.
  - `pages` (categories, `generalTypeId=4` for `catalog_page`) — `POST /import/pages`.
  - `products` (`generalTypeId=1` for `product`) — `POST /import/products`.
- **`product.import_id`** — critical field: unique product id from the source. Import uses it to find an "already existing" product and update it instead of creating a duplicate. Same logic for `users.import_id` and `orders.import_id`.
- The import template's `selectedAttributeMarkers` in the blueprint determines which Excel columns map to which `attribute.identifier` in the `attribute_set.schema`.

## Full jsonb with data

### Blueprint (simplified — real one is larger)

```json
{
  "dry_run": false,
  "auto_positions": true,
  "blueprint": {
    "attributes_sets": [
      {
        "ref": "as-products",
        "identifier": "products-coffee",
        "type": "forProducts",
        "localizeInfos": { "en_US": { "title": "Coffee product attributes" } },
        "schema": {
          "price":    { "type": "real",   "isPrice": true, "position": 1, "localizeInfos": { "en_US": { "title": "Price" } } },
          "sku":      { "type": "string", "isSku":   true, "position": 2, "localizeInfos": { "en_US": { "title": "SKU" } } },
          "cover":    { "type": "image",  "isProductPreview": true, "position": 3, "localizeInfos": { "en_US": { "title": "Cover" } } },
          "in_stock": { "type": "radioButton", "position": 4, "localizeInfos": { "en_US": { "title": "In stock" } } }
        }
      }
    ],
    "pages": [
      {
        "ref": "cat-coffee",
        "identifier": "coffee",
        "pageUrl": "coffee",
        "generalTypeId": 4,
        "parentId": null,
        "localizeInfos": { "en_US": { "title": "Coffee", "menuTitle": "Coffee" } }
      }
    ],
    "products": [
      {
        "ref": "prod-eth-1",
        "identifier": "coffee-ethiopia-yirgacheffe-250",
        "importId": "SKU-ETH-YRG-250",
        "attributeSetRef": "as-products",
        "pageRefs": ["cat-coffee"],
        "localizeInfos": { "en_US": { "title": "Coffee Ethiopia Yirgacheffe 250g" } },
        "attributesSets": {
          "en_US": {
            "price": 1450,
            "sku": "ETH-YRG-250",
            "in_stock": true,
            "cover": {
              "filename": "files/import/eth-yrg-250.jpg",
              "downloadLink": "https://cdn.example/cloud-static/files/import/eth-yrg-250.jpg",
              "previewLink": "",
              "size": 248901,
              "params": { "isImageCompressed": true },
              "contentType": "image/jpeg"
            }
          }
        }
      }
    ]
  }
}
```

The use of `ref` is local aliases within the blueprint. The service resolves them to real `id`s after entities are created.

### Import history

```json
{
  "id": 87,
  "createdDate": "2026-05-13T11:00:00.000Z",
  "importType": "catalog",
  "attributesSets": [9, 10],
  "pages": [56, 57, 58],
  "products": [1234, 1235, 1236, 1237, 1238],
  "users": [],
  "orders": [],
  "formModules": [],
  "productStatuses": [1],
  "pageProducts": "{ \"56\": [1234, 1235], \"57\": [1236, 1237, 1238] }",
  "errors": []
}
```

### Import template (mapping for the legacy admin import UI)

```json
{
  "id": 4,
  "name": "Excel — coffee products",
  "isActive": true,
  "data": {
    "fileType": "xlsx",
    "headerRow": 1,
    "sheets": ["Sheet1"],
    "columnMapping": {
      "A": { "attribute": "sku",       "type": "string" },
      "B": { "attribute": "title",     "isLocalize": true, "lang": "en_US", "path": "localizeInfos.en_US.title" },
      "C": { "attribute": "price",     "type": "real" },
      "D": { "attribute": "in_stock",  "type": "radioButton" }
    }
  }
}
```

## Admin API (`@Controller('import')`)

| Method | Path | Permission | Purpose | Status |
|---|---|---|---|---|
| `POST` | `/import/from-blueprint` | `import.data` | Declarative import of a whole blueprint | **recommended** |
| `POST` | `/import/attribute-set` | `import.data` | Create attribute_set from import data | `@ApiExcludeEndpoint()`, deprecated |
| `POST` | `/import/pages` | `import.data` | Batch page creation | `@ApiExcludeEndpoint()`, deprecated |
| `POST` | `/import/check-pages` | `import.data` | Check page existence | deprecated |
| `POST` | `/import/products` | `import.data` | Batch product creation | deprecated |
| `PUT` | `/import/products` | `import.data` | Append image files to products | deprecated |
| `DELETE` | `/import/history/:id` | — | Delete a history record |

```http
POST /import/from-blueprint?dry_run=false&auto_positions=true

{ "blueprint": { ... see above ... } }
```

Query parameters:
- `dry_run=true` — walk the blueprint and return "what would be created" without writing to the DB.
- `auto_positions=true` — automatically create `positions` records for all `position_id` fields.

Import templates are managed by a separate controller `catalog-import-template.controller.ts` (create/get/delete `catalog_import_templates`).

## Behind the scenes

- **The `import` module itself has NO Bull queues.** Import is a synchronous transaction in one HTTP request. If the file is large — the frontend shows progress via the `import-backend` microservice (see below).
- **RabbitMQ — exchange `exchange-import` + queue `queue-import` (routing key `websocket`)** — this is the **reverse** channel: `import-backend` (Python microservice) sends import progress to this exchange, cms subscribes via `RabbitmqAdminConsumerService` (`cms/src/modules/rabbitmq/services/rabbitmq-admin.consumer.service.ts:33-69`) and relays messages through `AdminSocketGateway` to all connected admin tabs:
  ```ts
  // assertQueue('queue-import') → bindQueue → 'exchange-import' (topic) → routingKey 'websocket'
  ```
  This is how the frontend sees "320/1000 rows processed", "errors: 5" in real time.
- **`import-backend` (Python)** — separate microservice. Accepts files (Excel/CSV/XML/JSON/SQL), parses, builds the blueprint, sends progress back via `exchange-import`, and finally calls cms `/import/from-blueprint` with the prepared blueprint. See `import-backend/README.md`.
- **WS.** Via `exchange-import` → `queue-import` → `socketService.emit` (`rabbitmq-admin.consumer.service.ts:92`) — progress flies to the admin tab. The cms import endpoints themselves do not emit WS events (they return the result in the HTTP response).
- **Journal.** Import operations are **not** covered by the `@Journalable` decorator (the log would be too voluminous — 5000 products in one import would produce 5000 entries). Instead, `catalog_import_history` is used, where there's one record per import with the list of created ids.
- **Permissions.** `import.data`, `import.data.createTemplate`, `import.data.deleteTemplate`.
- **`ImportType` enum** — `catalog`, `users`, `orders`, `form-data`. The import type defines what's processed and how to roll it back.

## Links to other files

- [01-catalog-product.md](./01-catalog-product.md) — the main import entity (`products.import_id`). After import, the Bull `product-elastic` queue starts for indexing.
- [02-content-page.md](./02-content-page.md) — categories are created as `pages` with `generalTypeId=catalog_page`.
- [08-users-and-groups.md](./08-users-and-groups.md) — `ImportType.USERS` imports users with `import_id`.
- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — import creates `attribute_set` and schema in one step. If you later need to add another attribute, that's a schema-edit task.

## Antipattern

**"I'll write a `node migrate.js` script that INSERTs products into `products` via SQL."** Don't:

1. INSERT into `products` without the correct `attribute_set_id` and valid `attributes_sets` jsonb produces "broken" products that won't show up in the admin.
2. Without writing to `index_attribute_data` (`BULL_QUEUES.indexData`), the product doesn't appear in filters/sorting.
3. Without the `product-elastic` job, the product isn't findable via search.
4. Without `products_pages_mn`, the product isn't attached to a category.

Correct way: build a blueprint → `POST /import/from-blueprint`. The service handles the correct order, updates indexes, creates positions.

**"One huge XML with 100k products — push it straight to `/import/from-blueprint`."** Also bad: the HTTP request will time out. For huge files:
1. Upload the file to `import-backend` (Python FastAPI, async).
2. It parses into chunks (e.g., 500 rows), builds the blueprint, sends in pieces.
3. Progress via `exchange-import` → WS → admin.

**"We make our own `migration_logs` table for import audit."** Don't — there's `catalog_import_history`. Deleting a record via `DELETE /import/history/:id` cascade-rolls back all created entities (using `pages[]`, `products[]`, etc., lists as a map of what to delete).
