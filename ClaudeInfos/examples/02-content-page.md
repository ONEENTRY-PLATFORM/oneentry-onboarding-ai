<!-- audit: 5/5 (2026-05-13) endpoints[POST /pages, PUT /pages/:id, PUT /pages/:id/config, POST /pages/copy/:id, POST /blocks, PUT /pages/:id/blocks/:blockId/position], fields[pages.general_type_id, pages.template_id, pages.parent_id, pages.config jsonb, blocks.custom_settings], queues[index-data via IndexTableType.BLOCKS in admin-blocks], ws[socketService.sendMessage 'page' 'create', 'block' 'create'], fk[block_pages_mn.page_id->pages.id CASCADE, block_pages_mn.block_id->blocks.id CASCADE] -->

# 02. Content page (static, blog, news, vacancies)

## Purpose

Any "non-product" page of the site:
- **About / contacts / privacy policy** — static with text, media, form.
- **Blog / news / press** — feed of uniform pages with author, date, cover.
- **Product landing / promo / landing page** — sections (hero, features, FAQ, CTA form) assembled from blocks.
- **Vacancies** — list of vacancies with description + application form.

For a product catalog — NOT here (see [01-catalog-product.md](./01-catalog-product.md)), although "catalog page" is also a `PageEntity`, just with `general_type='catalog_page'`. Rule: if the page has no linked `products`/`product_pages`/`product_blocks` — it's a content page, this doc.

## Entities and dependency hierarchy

```
templates           — layout template (html + css) and linked attribute_set
  ↑ template_id (opt., SET NULL on delete)
pages               — the page itself: parent_id hierarchy, page_url, localize_infos, config
  ↑ page_id (CASCADE)
block_pages_mn      — M:N relation, plus position_id, is_nested
  ↓ block_id (CASCADE)
blocks              — reusable content block (hero, FAQ, text block, slider)
  ↓ template_id (SET NULL)
templates
```

| Table | Base class | Key fields |
|---|---|---|
| `pages` | `BaseAttributeSetsAbstractEntity` | `general_type_id`, `parent_id`, `page_url` (unique URL segment), `template_id` (opt.), `localize_infos` jsonb (`{title, htmlContent, plainContent, mdContent, menuTitle}`), `is_visible`, `config` jsonb, `depth`, `category_path`, `position_id`, `rating` jsonb |
| `blocks` | `BaseAttributeSetsAbstractEntity` | `general_type_id`, `template_id` (SET NULL), `custom_settings` jsonb, `is_visible`, `product_page_urls` (string[] for auto-linking products) |
| `block_pages_mn` | `BaseEntity` | unique `(page_id, block_id)`, `is_nested`, `position_id` |
| `templates` | `BaseAttributeSetsAbstractEntity` | its own `attribute_set` — defines what fields are available on the block/page with this template |

Creation order:
1. (Opt.) Create `template` via `POST /templates` with the needed HTML markup and `attribute_set_id`.
2. Create `page` via `POST /pages`, specifying `generalTypeId` (see the `GeneralType` enum), `templateId` (opt.), `parentId` (opt.), `pageUrl`, `localizeInfos`.
3. Create `blocks` via `POST /blocks` — each block can be reused on different pages.
4. Attach blocks to the page (`block_pages_mn` records are created — the specific mechanism via `UpdateBlockDto.blocks: BlockPageIds[]` in `PUT /blocks/:id`, or via `PUT /pages/:id/blocks/:blockId/position`).

FK confirmed in `block_pages_mn.entity.ts:66-77`:
```ts
@ManyToOne(() => PageEntity, ..., { onDelete: 'CASCADE', orphanedRowAction: 'delete' })
@JoinColumn({ name: 'page_id' })
@ManyToOne(() => BlockEntity, ..., { onDelete: 'CASCADE', orphanedRowAction: 'delete' })
@JoinColumn({ name: 'block_id' })
```

## Related `general_types` and `attribute_sets`

`general_types.type` (from migration `1744702199257-update-general-types.ts`, checked against the `GeneralType` enum):

| Identifier | What |
|---|---|
| `common_page` (id=17) | Base content page (About, contacts, landings) |
| `catalog_page` (id=4) | Catalog category with products — [01](./01-catalog-product.md) |
| `error_page` (id=3) | 404 / 500 / other error pages |
| `product_preview` (id=5) | Product preview card (used inside the catalog) |
| `common_block` (id=18) | Generic block (text, media, CTA) |
| `product_block` (id=10) | "Products" block (fixed list) |
| `similar_products_block` (id=8) | "Similar products" block (dynamic) |
| `form` (id=11) | Form page |
| `external_page` | Link to an external URL |

Each `general_type` is linked to a module (`pages`, `blocks`) via `module_general_types_mn` — this controls which entity handler processes the request.

`AttributesSetType` for pages/blocks/templates:
- `forPages` — page attributes (SEO: `meta_title`, `meta_description`, `canonical`).
- `forBlocks` (enum `forBlock = 'forBlocks'`) — block attributes (e.g., `gallery_images`, `cta_button_text`, `background_color`).

## Full jsonb with data

> **Anti-hallucination (for dataset-pipeline agents).** All string values inside `localize_infos` (`title`, `menuTitle`, `plainContent`, `htmlContent`, `mdContent`) and string attributes in `attributes_sets.<lang>` must come from **real sources in the target project's code** (see `agents_datasets/rules/oneentry-invariants.md` §18, `agents_datasets/agents/code-inspector.md` §3.6). Reconstructing these values from the identifier, file name, or "common sense" is forbidden. If the value isn't found in code — the field = `null`, and `entity-mapper` records a warning. Suspicious matches with Title Case of the identifier are caught by `blueprint-validator` (S36, WARNING).

### Page "About" (`common_page`)

```json
{
  "id": 87,
  "identifier": "about",
  "generalTypeId": 17,
  "parentId": null,
  "pageUrl": "about",
  "templateId": 12,
  "isVisible": true,
  "depth": 0,
  "showChildren": false,
  "config": {},
  "categoryPath": null,
  "rating": {},
  "localizeInfos": {
    "en_US": {
      "title": "About",
      "menuTitle": "About",
      "htmlContent": "<h1>Who we are</h1><p>Brewing coffee since 2012.</p>",
      "plainContent": "Who we are. Brewing coffee since 2012.",
      "mdContent": "# Who we are\n\nBrewing coffee since 2012."
    }
  },
  "attributeSetId": 41,
  "attributesSets": {
    "en_US": {
      "meta_title": "About Coffee Co — roasting since 2012",
      "meta_description": "Specialty coffee since 2012. Meet the team and the roasters.",
      "canonical": "https://example.com/en/about",
      "hero_image": {
        "filename": "files/project/page/87/images/hero.jpg",
        "downloadLink": "https://cdn.example/cloud-static/files/project/page/87/images/hero.jpg",
        "previewLink": "https://cdn.example/cloud-static/files/project/page/87/images/hero-preview.jpg",
        "size": 248901,
        "params": { "isImageCompressed": true },
        "contentType": "image/jpeg"
      },
      "published_at": {
        "fullDate": "2024-01-15T09:00:00.000Z",
        "formattedValue": "15-01-2024",
        "formatString": "DD-MM-YYYY"
      },
      "is_indexed": true,
      "author_name": "John Doe",
      "reading_time_minutes": 4
    }
  }
}
```

### Block "Hero banner"

```json
{
  "id": 201,
  "identifier": "about-hero",
  "generalTypeId": 18,
  "templateId": 7,
  "isVisible": true,
  "customSettings": { "layout": "centered", "overlayOpacity": 0.4 },
  "productPageUrls": [],
  "localizeInfos": {
    "en_US": { "title": "Hero — About" }
  },
  "attributeSetId": 23,
  "attributesSets": {
    "en_US": {
      "headline": "Coffee that changes mornings",
      "subheadline": {
        "htmlValue": "<p>Fresh roast. Our own logistics.</p>",
        "plainValue": "Fresh roast. Our own logistics.",
        "mdValue": "Fresh roast. Our own logistics.",
        "params": { "isImageCompressed": true, "editorMode": "html" }
      },
      "cta_text": "Shop coffee",
      "cta_url": "/catalog/coffee",
      "is_dark_theme": true,
      "background": {
        "filename": "files/project/block/201/images/bg.jpg",
        "downloadLink": "https://cdn.example/cloud-static/files/project/block/201/images/bg.jpg",
        "previewLink": "https://cdn.example/cloud-static/files/project/block/201/images/bg-preview.jpg",
        "size": 408120,
        "params": { "isImageCompressed": true },
        "contentType": "image/jpeg"
      }
    }
  }
}
```

## Admin API

`@Controller('pages')`, `@Controller('blocks')`. Auth — `AdminAuthGuard`.

### Create a page

```http
POST /pages

{
  "identifier": "about",
  "generalTypeId": 17,
  "parentId": null,
  "pageUrl": "about",
  "templateId": 12,
  "localizeInfos": {
    "en_US": { "title": "About", "menuTitle": "About", "htmlContent": "<h1>Who we are</h1>", "plainContent": "Who we are.", "mdContent": "# Who we are" }
  }
}
```

After saving, the admin controller calls `socketService.sendMessage(payload, 'page', 'create')` (`admin-pages.controller.ts:237`) — the frontend refreshes the page tree in all open tabs.

### Edit SEO/page attributes

**Note (see `agents_datasets/ClaudeInfos/data-model-core.md`):** `pages` (like `products`) **do not** have a normal `PUT /pages/:id` for full content overwrite — content changes go via y-websocket CRDT (`WS_SYNC_SERVER_PORT=3007`, see `sync-socket.gateway.ts`). However, the `PUT /pages/:id` endpoint does exist — it's used to update **metadata** (title, marker, parentId, templateId, isVisible). Content (`localize_infos.htmlContent`, `attributes_sets`) is written by the frontend via the Yjs doc, and `sync` persists it to the DB.

```http
PUT /pages/87

{
  "identifier": "about",
  "parentId": null,
  "templateId": 12,
  "isVisible": true,
  "version": 3
}
```

### Catalog config (for `catalog_page` with products)

```http
PUT /pages/87/config

{
  "rowsPerPage": 3,
  "productsPerRow": 4
}
```

Permission: `catalog.products.outputSettings`. Used for the catalog — defines the product grid.

### Copy a page

```http
POST /pages/copy/87
```

Permission: `pages.copy`. Creates a deep copy (page + its localizations + block bindings).

### Create a block

```http
POST /blocks

{
  "identifier": "about-hero",
  "generalTypeId": 18,
  "templateId": 7,
  "localizeInfos": { "en_US": { "title": "Hero — About" } },
  "attributesSets": {}
}
```

After creation — `socketService.sendMessage(payload, 'block', 'create')` + push to `index-data` (job `'index'` with `tableName: IndexTableType.BLOCKS`) — `admin-blocks.controller.ts:513-518`.

### Place a block at a position on a page

```http
PUT /pages/87/blocks/201/position

{
  "position": "0|hzzzzz:"
}
```

Permission: `pages.blocks.changePositions`. Internally creates/updates `block_pages_mn` with `position_id`. The `position` field stores a fractional-ranking string (used by the ranking library — there are no "1, 2, 3", there are `'0|i00000:'`, `'0|hzzzzz:'`, which allow inserting between without renumbering).

Similarly — `PUT /pages/:id/nested-blocks/:blockId/position` for nested blocks (`is_nested=true` in `block_pages_mn`).

### Delete a page

```http
DELETE /pages/87
```

Permission: `pages.delete`. `block_pages_mn` rows are cascade-deleted (CASCADE). The blocks themselves remain (they can be linked to other pages).

### Visibility

```http
PUT /pages/87/change-visibility
```

Permission: `pages.switching`. Toggles `is_visible`.

## Behind the scenes

- **Bull `index-data`** — starts after block creation (`tableName: IndexTableType.BLOCKS`). Rebuilds `index_attribute_data` for filtering blocks by attributes.
- **WS channels:**
  - `'page' / 'create'`, `'page' / 'update'`, `'page' / 'delete'` — from `admin-pages.controller.ts`.
  - `'block' / 'create'`, `'block' / 'update'`, `'block' / 'delete'` — from `admin-blocks.controller.ts`.
- **y-websocket (CRDT) for page content** — `sync-socket.gateway.ts` on `WS_SYNC_SERVER_PORT=3007`. Frontend opens a `Y.Doc` via `WebsocketProvider` (see `cms_frontend/src/sync-store/sync-page.store.js`), all `htmlContent`/`attributes_sets` edits are merged via CRDT and pushed to the DB via sync. This means: two admins who opened the same page simultaneously see each other's edits in real time (not a lock, but a merge).
- **Journal** — `PAGE_CREATED, PAGE_UPDATED, PAGE_DELETED, BLOCK_CREATED, BLOCK_UPDATED, BLOCK_DELETED`.
- **Permissions** — long list: `pages.{create,update,updateBlockAndForms,delete,copy,move,switching,changePositions}`, `pages.blocks.changePositions`, `pages.blocks.nested.changePositions`, `pages.forms.changePositions`, `pages.settings.update`, `pages.errorStatus.{create,delete}`, `blocks.{create,update,delete}`.

## Links to other files

- [01-catalog-product.md](./01-catalog-product.md) — product page with `general_type='catalog_page'`. Same `PageEntity`, but with linked `product_pages`/`product_blocks`.
- [03-form-submission.md](./03-form-submission.md) — how to insert a form into a page (via `block_pages_mn` with a `form`-type block).
- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — how to add a new SEO field to all `forPages`.
- [09-collections.md](./09-collections.md) — alternative for simple dictionaries instead of `pages`.

## Antipattern

**"Let's make a separate `blog_posts` table for the blog with columns `title`, `slug`, `cover`, `body`, `author`, `published_at`."** Don't. A blog is `pages`:

1. Create a parent page `pages/blog` (`generalTypeId=17`, `parentId=null`).
2. Each article is a child `pages` with `parentId=87` (blog's id), `generalTypeId=17`, `pageUrl='2024/welcome-to-coffee'`.
3. Article attributes go in `attributes_sets` of the corresponding `forPages` set: `cover` (`image`), `author_name` (`string`), `published_at` (`dateTime`), `reading_time_minutes` (`integer`), `is_indexed` (`radioButton` = `flag`).
4. Article body — `localize_infos.htmlContent` (frontend writes via y-websocket sync).
5. Storefront reads `GET /content/pages/:url` and filters by `parent_id` for the blog article list.

Same for "news", "vacancies", "case studies", "team", "departments". **When a separate table is justified:** only if you need transactions with PK-level consistency, index scans over millions of rows, or non-standard data types (geo, tsvector with weights, etc.). Not needed for content pages.
