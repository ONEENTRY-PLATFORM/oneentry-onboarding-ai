<!-- audit: 5/5 (2026-05-13) endpoints[POST /templates, PUT /templates/:id, DELETE /templates/:id, GET /templates/all, POST /template-previews, PUT /template-previews/:id, DELETE /template-previews/:id], fields[templates.general_type_id (FK), templates.title, template_previews.proportions jsonb (Record<string, TemplateProportionSet>), attribute_sets.schema[*].previewTemplateId (jsonb pointer, not FK)], queues[BULL_QUEUES.preview + jobs refresh-previews/refresh-preview/attribute-set-preview in PreviewConsumer (cms/src/modules/file-upload/consumers/preview.consumer.ts)], ws[AdminSocketGateway.sendMessage('template'/'template-preview', create/update/delete) — no separate channel], fk[templates.general_type_id->general_types.id, templates.position_id->positions.id, pages.template_id->templates.id, products.template_id->templates.id; attribute_sets.schema[*].previewTemplateId — jsonb reference WITHOUT FK] -->

# 11. Templates and previews

## Purpose

Scenarios:
- Create a UI template for catalog pages: "3×N grid with a top cover".
- Make a cover preview variant in `horizontal 200×100 / vertical 100×200 / square 200×200` format — `template_previews`.
- Apply a template to products or pages via `template_id`.
- Bind an image attribute to a specific preview template via `schema[k].previewTemplateId` → `PreviewConsumer` will regenerate all previews of that attribute.

OneEntry has **two different templates**:

| Entity | What it describes |
|---|---|
| `templates` (`TemplateEntity`) | Rendering template for **a whole entity** (page, product, block) in the UI |
| `template_previews` (`TemplatePreviewsEntity`) | Format of **the attribute's preview image** (proportions, alignment) |

Don't confuse them. The first is about layout, the second about thumbnail sizes.

## Entities and dependency hierarchy

```
general_types                       — entity type (forCatalogPages, forCommonPages, forBlocks, forProducts)
  ↑ general_type_id
templates                           — rendering template
                                      attribute_set_id (inherits BaseAttributeSetsAbstractEntity)
                                      identifier UNIQUE, title, position_id
  ↑ template_id
pages, products, blocks             — template consumers

template_previews                   — image preview format
                                      proportions jsonb (default/horizontal/vertical/square)
                                      identifier UNIQUE
  ↑ jsonb reference (NOT FK)
attributes_sets.schema[k].previewTemplateId — pointer to template_previews.id
                                              for image/groupOfImages attributes
```

| Table | Base class | Key fields |
|---|---|---|
| `templates` | `BaseAttributeSetsAbstractEntity` | `identifier` UNIQUE, `general_type_id` (FK), `title`, `position_id` (FK), inherits `attribute_set_id` + `localize_infos` |
| `template_previews` | `BaseAbstractEntity` | `identifier` UNIQUE, `title`, `proportions jsonb` |

`templates` has **its own `attribute_set`** — a template can have custom UI parameters (background color, overlay opacity, text alignment, etc.).

## Related `general_types`

`templates.general_type_id` points to a `general_types` row with `type` from the `GeneralType` enum (`cms/src/modules/general-types/types/general-types.enum.ts`): for templates this is usually `catalog_page` | `common_page` | `common_block` | `product_block` | `product`. This defines **which entities the template applies to** (the admin UI filters the template list when selecting on a page/product by this field).

## Full jsonb with data

### `templates` (catalog page template)

```json
{
  "id": 7,
  "identifier": "catalog-grid-3xN",
  "title": "3×N catalog grid",
  "generalTypeId": 4,
  "attributeSetId": 22,
  "positionId": 4,
  "localizeInfos": {
    "en_US": { "title": "Grid 3×N" }
  },
  "attributesSets": {
    "en_US": {
      "bg_color":   { "value": "#f8f9fa" },
      "card_align": { "values": ["left"], "titles": { "en_US": { "left": "Left" } } },
      "show_price": true
    }
  }
}
```

`bg_color`, `card_align`, `show_price` are **attributes of the template's own attribute_set** (id=22). These are not page data — they are the template config.

### `template_previews` (preview format)

```json
{
  "id": 3,
  "identifier": "product-card-cover",
  "title": "Product card cover",
  "positionId": 18,
  "proportions": {
    "default": {
      "horizontal": { "height": 200, "weight": 100, "alignmentType": "middleMiddle" },
      "vertical":   { "height": 100, "weight": 200, "alignmentType": "middleMiddle" },
      "square":     { "side": 200, "alignmentType": "middleMiddle" }
    },
    "thumbnail": {
      "horizontal": { "height": 80, "weight": 40, "alignmentType": "topLeft" },
      "vertical":   { "height": 40, "weight": 80, "alignmentType": "topLeft" },
      "square":     { "side": 80, "alignmentType": "topLeft" }
    }
  }
}
```

**`proportions` shape** — `Record<string, TemplateProportionSet>`. Keys (`default`, `thumbnail`) are **proportion markers** (the template can reference the desired one). Inside each — three orientations (`horizontal`, `vertical`, `square`) with `height`/`weight` (or `side` for square) + `alignmentType`.

### Using `previewTemplateId` in `attributes_sets.schema`

```json
{
  "id": 9,
  "schema": {
    "cover": {
      "type": "image",
      "identifier": "cover",
      "isProductPreview": true,
      "previewTemplateId": 3,
      "position": 3,
      "localizeInfos": { "en_US": { "title": "Cover" } }
    }
  }
}
```

`previewTemplateId: 3` is a **jsonb reference to `template_previews.id=3`**, WITHOUT a formal FK. The link is discovered by jsonb grep (`jsonb_path_query_first(schema, '$.**.previewTemplateId')` in `preview.consumer.ts:90`).

## Admin API

### `@Controller('templates')`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/templates?type=&langCode=` | `settings.templates.get` | List of templates filtered by general_type |
| `GET` | `/templates/all?langCode=` | — | Grouped list (for UI selector) |
| `GET` | `/templates/:id?langCode=` | — | Template details |
| `POST` | `/templates` | `settings.templates.create` | Create |
| `PUT` | `/templates/:id` | `settings.templates.update` | Update |
| `DELETE` | `/templates/:id` | `settings.templates.delete` | Delete (with `pagesService.resetTemplateId`) |
| `PUT` | `/templates/:id/position` | `settings.templates.changePositions` | Change position |
| `GET` | `/templates/marker-validation/:marker` | — | `identifier` uniqueness check |
| `GET` | `/templates/marker/:marker` | — | Lookup by `identifier` |

### `@Controller('template-previews')`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/template-previews?langCode=` | — | List |
| `GET` | `/template-previews/:id?langCode=` | — | Details |
| `POST` | `/template-previews` | `settings.templatePreview.create` | Create |
| `PUT` | `/template-previews/:id` | `settings.templatePreview.update` | Update (triggers `refresh-preview` job) |
| `DELETE` | `/template-previews/:id` | `settings.templatePreview.delete` | Delete |
| `PUT` | `/template-previews/:id/position` | `settings.templatePreview.changePositions` | Position |
| `GET` | `/template-previews/marker-validation/:marker` | — | `identifier` uniqueness |

```http
POST /template-previews

{
  "identifier": "product-card-cover",
  "title": "Product card cover",
  "proportions": {
    "default": {
      "horizontal": { "height": 200, "weight": 100, "alignmentType": "middleMiddle" },
      "vertical":   { "height": 100, "weight": 200, "alignmentType": "middleMiddle" },
      "square":     { "side": 200, "alignmentType": "middleMiddle" }
    }
  }
}
```

## Behind the scenes

### Bull queue `preview` (`BULL_QUEUES.preview = 'preview'`)

`PreviewConsumer` (lives in the `file-upload` module, not in template-previews — intentional, see 15) handles 3 job names:

| Job | When |
|---|---|
| `refresh-previews` | Periodic background — iterates **all** `template_previews`, calls `refresh-preview` for each. |
| `refresh-preview` | After `PUT /template-previews/:id` — regenerates thumbnails for all `attributes_sets` whose `schema[*].previewTemplateId === id`. |
| `attribute-set-preview` | After `PUT /attributes-sets/:id/schema` (when an attribute with `previewTemplateId` is added/removed) — `PreviewImageService.updatePreviewAndSetLinks`. |

The `refresh-preview` trigger fires like this:

```ts
// admin-template-previews.service.ts (conceptually):
await this.previewQueue.add('refresh-preview', { type: 'template', id });
```

### WS / notifications

There's **no dedicated WS channel** in this module. The shared `AdminSocketGateway.sendMessage(template, 'template', 'create' | 'update' | 'delete')` is used — the usual admin WS message to refresh the template list in other open admin tabs.

### Redis lock `bunch_products_creating`

`PUT /templates/:id` is blocked during **bulk product import** (`admin-templates.controller.ts:294-298`). The logic: while the `bunch_products_creating` Redis flag is set, the template can't be changed — otherwise imported products would land in a half-empty schema. Returns HTTP `423 Locked`.

### Template deletion

`DELETE /templates/:id` calls `pagesService.resetTemplateId(+id)` — all pages referencing the template reset `template_id=null`. In code TODO — extend to forms/blocks. Template files are not automatically deleted (a rendering template is only metadata + attribute_set).

### Journal

`JournalingEvents.TEMPLATE_CREATED/UPDATED/DELETED`, `TEMPLATE_PREVIEW_CREATED/UPDATED/DELETED`. `@Journalable(...)` decorators on the corresponding endpoints.

### Permissions

- `settings.templates.{get, create, update, delete, changePositions}`
- `settings.templatePreview.{create, update, delete, changePositions}`

## Links to other files

- [02-content-page.md](./02-content-page.md) — `pages.template_id → templates.id`. The page uses the template for UI.
- [01-catalog-product.md](./01-catalog-product.md) — `products.template_id → templates.id`. Same for products.
- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — adding `previewTemplateId` in `attributes_sets.schema[k]` for an image attribute.
- [15-file-upload-pipeline.md](./15-file-upload-pipeline.md) — `PreviewConsumer` lives in the `file-upload` module, uses `PreviewImageService` (based on `sharp`) to slice images per `proportions`.
- [19-third-party-modules.md](./19-third-party-modules.md) — `modules.used_templates jsonb` points to `templates.id`, preventing deletion of a template needed by a module.

## Antipattern

**"I'll put the rendering template right into the HTML page code (server-side template engine)."** Don't:

1. Tied to one layout version — every redesign requires a cms deploy.
2. Can't have multiple templates for one page (A/B UI test).
3. Localization breaks — template and content are mixed.

Correct way: `templates` stores ID + `attribute_set` with UI parameters. **Rendering is on the frontend** (cms_frontend / storefront); it reads `template_id` and applies the corresponding component.

**"I'll create a separate `email_templates` table for email templates."** Don't — email templates are stored in `events.localize_infos.template` (see [06-event-notification.md](./06-event-notification.md)). `templates` is a **UI template**, not an email template. Don't confuse them.
