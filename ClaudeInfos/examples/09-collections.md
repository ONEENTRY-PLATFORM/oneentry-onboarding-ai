<!-- audit: 5/5 (2026-05-13) endpoints[POST /integration-collections, PUT /integration-collections/:id, DELETE /integration-collections/:id/rows/:rowId], fields[collection_rows.collection_id, collections.form_id, selected_attribute_markers, lang_code], queues[—], ws[—], fk[collection_rows.collection_id -> collections.id CASCADE] -->

# 09. Collections (FAQ, cities, contacts, dictionaries)

## Purpose

Collections are "rows attached to a form" — without attributes and without a complex tree. They fit:
- **FAQ** (one Q-A per row).
- **Dictionaries of cities / addresses / stores**.
- **Lists of partners / certificates / phone numbers**.
- **Arbitrary tabular data** that the admin edits not via `pages`/`blocks` but via a dedicated list UI.

The fundamental difference from `pages`/`blocks`: a collection has no `attribute_set` of its own. The field structure is described by the **attached form** (`form_id`), and values are stored in `collection_rows.form_data` (jsonb).

If you have little data (≤10 rows), it rarely changes and doesn't need attribute-based filtering — that's a collection. If you need filters, statuses, media galleries, a parent tree — it's **not a collection**, it's `pages` (see [02-content-page.md](./02-content-page.md)) or `products` (see [01-catalog-product.md](./01-catalog-product.md)).

## Entities and dependency hierarchy

```
forms (opt.)       — describes the collection fields
  ↑ form_id
collections        — collection title + localization + form link
  ↑ collection_id (CASCADE on delete)
collection_rows    — concrete rows
```

| Table | Purpose | Key fields |
|---|---|---|
| `collections` | Collection header | `id`, `identifier` (marker), `localize_infos` (jsonb), `form_id` (nullable FK on `forms.id`), `selected_attribute_markers` (string, which attributes to show in the list UI) |
| `collection_rows` | Collection rows | `id`, `collection_id` (FK CASCADE), `lang_code`, `form_data` (jsonb), `entity_type` (nullable), `entity_id` (nullable) |

Creation order:
1. (Opt.) Create a `form` with the required fields — `POST /forms` (see [03-form-submission.md](./03-form-submission.md)).
2. Create a `collection`, passing `formId`.
3. Add rows via `POST /integration-collections/marker/:marker/rows`.

FKs confirmed in `cms/src/modules/collections/entities/collection-row.entity.ts:62-67`:
```ts
@ManyToOne(() => CollectionEntity, (os) => os.rows, {
  onDelete: 'CASCADE', orphanedRowAction: 'delete',
})
@JoinColumn({ name: 'collection_id', referencedColumnName: 'id' })
```

## Related `general_types` and `attribute_sets`

**A collection has no `attribute_set`.** That's its distinguishing trait: the field schema is not defined via `attributes_sets.schema` but via the attached `form` and its `attribute_set` (type `forBlocks` or `forUsers` depending on the form's purpose).

If a collection is detached (`form_id = null`), its rows can still store `form_data` of arbitrary shape (used in "collection as tag on an arbitrary entity" cases via `entity_type` / `entity_id`).

## Linking form to collection: `FormType.COLLECTION`

Source: `cms/src/modules/forms/types/form.type.ts:4` — `enum FormType { COLLECTION = 'collection' }`.

When a form is created specifically for a collection (not for order/registration/rating/arbitrary data submission), its `type` should be `'collection'`. This is a semantic marker: the admin shows such a form in the collections section and doesn't offer it in "order form" / "registration form" dropdowns.

**The link is directional:** the form doesn't reference the collection; the **collection references the form** via `collections.form_id` (see `cms/src/modules/collections/entities/collection.entity.ts:49-51`). One form `type: 'collection'` can be reused by several collections (then they share the field schema), but usually it's 1:1.

### Order of building the link in a blueprint

1. `attributes_sets` (type `forBlocks`, since `general_type_id=2`) with fields that will be in the collection rows (`question`, `answer`, `city_name`, `phone`, etc.).
2. `forms` with `type: 'collection'`, `processing_type: 'inner'` (or another suitable one), `attribute_set_id: @attributes_sets.<set>`.
3. `collections` with `form_id: @forms.<form>` and `identifier` (used as a marker in URLs `/integration-collections/marker/:marker/rows`).
4. Rows are added later via the API; they're not seeded in the blueprint (it's runtime data).

### Example of a `type: 'collection'` form

```json
{
  "id": 7,
  "identifier": "cities-form",
  "type": "collection",
  "processingType": "inner",
  "attributeSetId": 42,
  "localizeInfos": {
    "en_US": {
      "title": "City form",
      "titleForSite": "",
      "successMessage": "",
      "unsuccessMessage": "",
      "urlAddress": "",
      "database": "0",
      "script": "0"
    }
  },
  "templateId": null,
  "selectedAttributeMarkers": "city_name,phone"
}
```

And the matching collection linked to it:

```json
{
  "id": 12,
  "identifier": "cities",
  "formId": 7,
  "selectedAttributeMarkers": "city_name,phone",
  "localizeInfos": {
    "en_US": { "title": "Branch cities" }
  }
}
```

### When to use `type: 'collection'` vs `type: 'data'`

| Scenario | `forms.type` | Why |
|---|---|---|
| FAQ, cities, contacts, dictionaries with admin CRUD via the collections UI | `'collection'` | Semantics of "dictionary", admin shows it in the right section |
| Arbitrary form submission on storefront (contact form, feedback) with direct write to `form_data` | `'data'` | This is a user-input form, not a dictionary; see [03-form-submission.md](./03-form-submission.md) |
| Orders | `'order'` | Tightly bound to orders_storage / processing flow |
| Registration / login | `'sing_in_up'` | Tightly bound to the auth flow |
| Ratings / reviews | `'rating'` | Tightly bound to rating aggregation |

If the builder is on the fence between `'collection'` and `'data'` — ask: "is this form edited by the admin to populate a dictionary, or is it a storefront form for the user?". The first = `'collection'`, the second = `'data'`.

## Full jsonb with data

### Collection "Branch cities"

```json
{
  "id": 12,
  "identifier": "cities",
  "formId": 7,
  "selectedAttributeMarkers": "city_name,phone",
  "localizeInfos": {
    "en_US": { "title": "Branch cities" }
  }
}
```

### Collection row — Moscow

```json
{
  "id": 145,
  "collectionId": 12,
  "langCode": "en_US",
  "entityType": null,
  "entityId": null,
  "formData": {
    "en_US": [
      { "marker": "city_name",   "type": "string",  "value": "Moscow" },
      { "marker": "phone",       "type": "string",  "value": "+7 495 123-45-67" },
      { "marker": "address",     "type": "text",
        "value": [{
          "htmlValue": "<p>Tverskaya, 1</p>",
          "plainValue": "Tverskaya, 1",
          "mdValue": "Tverskaya, 1",
          "params": { "isImageCompressed": true, "editorMode": "html" }
        }]
      },
      { "marker": "opens_at", "type": "time",
        "value": { "fullDate": "2026-05-13T09:00:00.000Z", "formattedValue": "09:00", "formatString": "HH:mm" }
      },
      { "marker": "is_main", "type": "radioButton", "value": true },
      { "marker": "region", "type": "list",
        "value": { "title": "Central", "value": "central", "extended": { "type": "string", "value": "central" } }
      }
    ]
  }
}
```

Note:
- `form_data` is a `FormDataLangType` (`{ [lang]: FormDataItem[] }`), an array of `{marker, type, value}` triples. It's **NOT** `{ [lang]: { [marker]: value } }` as in `attributes_sets`.
- The `flag` type in the `attributes_sets` schema is written as `'radioButton'`, and the same in `form_data` (`AttributeType.flag = 'radioButton'`).
- Values of structural types (`text`, `image`, `dateTime`, `list`) are objects, not strings. See `cms/src/modules/index-attributes-sets/types/attribute-value.type.ts`.

## Admin API

All endpoints live under `@Controller('integration-collections')`. `AdminCollectionsController` extends `DeveloperCollectionsController` extends `BaseCollectionsController` — so the admin has access to the full set. Auth — `AdminAuthGuard`.

### Create a collection

```http
POST /integration-collections
Authorization: Bearer <admin-token>
Content-Type: application/json

{
  "identifier": "cities",
  "localizeInfos": {
    "en_US": { "title": "Branch cities" }
  }
}
```

Decorator: `@Journalable(COLLECTION_CREATED)`, `@GrantByPermission('collections.collection.create')`. Returns `CollectionEntity`.

### Update a collection (attach a form, change title)

```http
PUT /integration-collections/12

{
  "identifier": "cities",
  "formId": 7,
  "localizeInfos": {
    "en_US": { "title": "Branch cities" }
  }
}
```

Permission: `collections.collection.update`. `UpdateCollectionDto` requires `formId`, `identifier`, `localizeInfos` (see `dto/update-collection.dto.ts`).

### Add a row

```http
POST /integration-collections/marker/cities/rows?langCode=en_US

{
  "formIdentifier": "cities-form",
  "formData": {
    "en_US": [
      { "marker": "city_name", "type": "string", "value": "Moscow" },
      { "marker": "phone",     "type": "string", "value": "+7 495 123-45-67" }
    ]
  }
}
```

The endpoint lives in `BaseCollectionsController` — `@Post('/marker/:marker/rows')`. Permission is checked at the role level (the admin controller inherits the guard). All `formData` checks are in `FormDataValidationMiddleware`.

### Update a row

```http
PUT /integration-collections/marker/cities/rows/145?langCode=en_US

{
  "formIdentifier": "cities-form",
  "formData": { "en_US": [ { "marker": "city_name", "type": "string", "value": "Moscow (Center)" } ] }
}
```

### Delete a row

```http
DELETE /integration-collections/12/rows/145
```

Permission: `collections.row.delete`. There's also a base `DELETE /marker/:marker/rows/:id`.

### Delete multiple rows at once (batch)

```http
DELETE /integration-collections/12/rows

{
  "deleteAll": false,
  "ids": [145, 146, 147]
}
```

`DeleteFormDataDto` takes `ids: number[]` and a `deleteAll: boolean` flag. If `deleteAll: true` — `ids` is ignored.

### Delete a collection

```http
DELETE /integration-collections/12
```

Permission: `collections.collection.delete`. `collection_rows` are cascade-deleted (`onDelete: 'CASCADE'`).

## Behind the scenes

- **Bull queues — NONE.** Collections don't start background processing: writes are synchronous, the response returns immediately.
- **WS events — NONE.** No `attributesSetsChanging`, no system locks. A collection is edited by one admin without advisory locks.
- **Journal.** All mutating endpoints are marked with `@Journalable`:
  - `COLLECTION_CREATED` / `COLLECTION_UPDATED` / `COLLECTION_DELETED`,
  - `COLLECTION_ROW_CREATED` / `COLLECTION_ROW_UPDATED` / `COLLECTION_ROW_DELETED`.
  Logged as `{admin, path, params, body, result}` via interceptor (see `agents_datasets/ClaudeInfos/patterns-journal-blockers-versioning.md`).
- **Permissions.** `AdminPermissionsEnum`:
  - `collections.collection.{get,create,update,delete}`,
  - `collections.row.{get,create,update,delete}`.
- **`entity_type` / `entity_id`** on `collection_rows` — optional links to another entity (e.g., `entity_type='products'`, `entity_id=42`). Useful for the "collection of attachments on a product" case (photo reviews, certificates, docs). The fields are indexed (`@Index()`), but **there's no formal FK** — it's a "weak" link, integrity is not guaranteed.

## Links to other files

- [02-content-page.md](./02-content-page.md) — when you need media, templates, and SEO (instead of a collection).
- [03-form-submission.md](./03-form-submission.md) — how to create the `form` for `form_id` link to a collection.
- [08-users-and-groups.md](./08-users-and-groups.md) — a collection can be attached to a user via `entity_type='users'`.

## Antipattern

**"Let's build the FAQ with a new `faq_items` table."** Don't. FAQ is a collection:

1. Create a `form` with two fields (`question`, `answer: text`).
2. Create a `collection` with `identifier='faq'` and `formId` from step 1.
3. Add rows via `POST /integration-collections/marker/faq/rows`.

No migrations, no new entities; the frontend reads `GET /content/collections/marker/faq/rows`. Same approach for cities, contacts, partners, certificates, telegram channels, and any other "row-object" dictionaries.

**When a collection does NOT fit:** when you need statuses, user-driven ordering, tree hierarchy, media galleries, storefront filters, bulk import from Excel. For a catalog — [01-catalog-product.md](./01-catalog-product.md). For a content page — [02-content-page.md](./02-content-page.md).
