# Filters — universal setup rules for any OneEntry project

> **⚠ Universality note.** Examples below frequently use fashion-shop terms (clothing / shoes / bags / women / men) because that is the reference test project. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop (`product/sku/brand/category`), restaurant (`menu-item/dish/cuisine/section`), beauty salon (`service/master/treatment/duration`), hotel (`room/suite/amenity`), EdTech (`course/lesson/level`), corporate site (`page/department/team`), personal cabinet (`section/setting/subscription`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **Hand-written, project-agnostic, grep-verified against the OneEntry filters + attribute indexing implementation.** Source of truth for how filters work in OneEntry and how the blueprint pipeline must treat them. Used by code-inspector, entity-mapper, post-import orchestration and blueprint-validator.
>
> Runtime model + indexing details are summarised inline in §1–§7 below — no external runtime doc link is needed in shop environments.

## 1. TL;DR — how filters really work in OneEntry

1. The data model is **three tables**, all **out of the 24-table blueprint whitelist**:

   | Table | Role |
   |---|---|
   | `filters` | Filter (e.g. "Catalog filter for /women") — `identifier`, `localizeInfos`, `scopeTypes` |
   | `filter_items_mn` | Polymorphic items — `objectType` ∈ {`page`, `product`, `attribute`, `discount`, `personal-discount`, `bonus`, `payment-method`, `admin`}, `objectId`, `attributeIdentifier?`, `attributeValueId?`, `valueText?` |
   | `filter_custom_items_mn` | Free-form content-only items (`localizeInfos`, `url`) |

2. **Attribute indexing is auto-triggered ONLY for products.** The blueprint loader explicitly enqueues a Bull `'index'` job at the end of `run()` — but **only when `tables.products` or `tables.products_pages_mn` is present** (verified against the loader's post-import side effect):
   ```ts
   if (!dryRun && (inserted['products'] || inserted['products_pages_mn'])) {
     await this.indexDataQueue.add('index', { aId: 0, userId: undefined, tableName: IndexTableType.PRODUCTS });
   }
   ```
   The `index-data.consumer.ts` `@Process('index')` handler then walks the relevant products' attributes and calls `IndexAttributeService.createOrUpdate()`, populating `index_attribute_data`. There is **NO `isFilter` flag on `SchemaItem`** — every attribute that appears in real product data becomes indexable. For projects with **no products** (content-only sites), the loader does NOT enqueue indexing; pages/blocks must be touched in the admin UI (which dispatches its own `'index'` jobs) before facets can render.

3. **The `SchemaItem` system flags are FIXED** (verified against the `SchemaItem` type definition used by `attributes_sets`):
   `isPrice`, `isSku`, `isCurrency`, `isTaxRate`, `isPassword`, `isLogin`, `isSignUp`, `isNotificationEmail`, `isNotificationPhonePush`, `isNotificationPhoneSMS`, `isVisible`, `isProductPreview`, `isCompress`, `isIcon`, `isRatingValue`, `splitPrice` (+ `splitParts`, `splitUnit`). Adding any other key (`isFilter`, `isIndexed`, `isFacet`, ...) into a `SchemaItem` will be persisted into the `attributes_sets.schema` jsonb (the loader does NOT filter unknown nested keys inside jsonb), but **no code reads it** — the field is dead weight. Validator S54 catches missing `isVisible: true` but does NOT catch invented flags. The reason `isFilter` doesn't work as a feature flag: the runtime decides what is filterable by the presence of items in `filter_items_mn`, not by attribute schema flags.

4. **Unknown top-level columns produce HTTP 500.** The loader assembles `INSERT (col1, col2, ...) VALUES (...)` from the raw row keys without a column whitelist (`blueprint-loader.service.ts:516`). If a row contains a column that doesn't exist in the target table, Postgres rejects the statement and the request returns HTTP 500. Validator S27 catches this statically before loading.

5. **Filters are configured strictly via REST API after the blueprint import** — there is no in-blueprint representation. See `post-import-orchestration.md` Step 7.

## 2. What the blueprint pipeline MUST do

Since there is nothing to write into the blueprint JSON itself for filters, the only useful work happens in two places:

### 2.1 Inspector — detect filter signals

See `code-inspector.md` Step 8.5. Goal: populate `detected_signals.filters` in inspector.yaml with:
- which UI components/hooks/query-params indicate facet filtering;
- which attribute identifiers appear as facets (`color`, `size`, `brand`, ...);
- which storefront pages render the filter UI (`women-clothing`, `men-bags`, `sale`, ...);
- the visible label of the filter panel, if found in code (NOT hallucinated).

### 2.2 Mapper — build `post_import_filters[]` task list

See `entity-mapper.md` Step 9.6. Goal: take the inspector signals and write `mapped.post_import_filters[]` — one task per filter that should be created after import. Also emit `out-of-whitelist-needs-post-import: filters …` warning.

⚠ The mapper does NOT touch `attributes_sets.schema` — no flag to set, no schema mutation.

## 3. Mapper task structure (`mapped.post_import_filters[]`)

```yaml
post_import_filters:
  - identifier: women-clothing           # MUST be unique per project; storefront fetches via GET /filters/marker/<identifier>
    page_identifier: women-clothing      # which catalog page this filter renders on; mapper resolves to objectId after import
    scope_types: [product, attribute]    # array of FilterScopeType — what kinds of items the filter is allowed to hold
    attribute_set_identifier: forProducts # which attribute_set's attributes are used as facets — orchestrator resolves to objectId after import
    attribute_identifiers:               # facet attributes (must exist in attribute_set_identifier.schema)
      - color
      - size
      - brand
      - price
    direct_items: []                     # rarely — pre-pinned page/product/discount items added on creation
    localize_infos:                      # null (in mapped.yaml) if inspector didn't capture the panel title.
                                         # Orchestrator converts null → { <default_lang>: { title: '' } } before POSTing,
                                         # because `IsLocalizeInfos` rejects null/empty. Admin fills the real title later via UI.
      en_US: { title: 'Filters' }
```

`FilterScopeType` enum values: `page`, `product`, `admin`, `attribute`, `discount`, `personal-discount`, `bonus`, `payment-method` + content-only `custom`.

## 4. Filter-attribute heuristics

Used by **inspector** to fill `attribute_candidates`, and by **mapper** as fallback when inspector hands over an empty list. These are about **which attributes to expose as catalog facets**, not about a flag on the schema.

> ⚠ **Vertical defaults.** `FACET_CANDIDATE_BY_NAME` below is populated with fashion-shop / e-commerce facet vocabulary (`sleeve`, `neckline`, `heel_height` are fashion-specific; `price`, `color`, `size`, `brand`, `material`, `rating`, `in_stock` are generic e-commerce). For other verticals, extend or replace per project:
> - **Hotel CMS**: `bed_count`, `view_type`, `floor`, `amenities_included`, `max_occupancy`, `wheelchair_accessible`.
> - **Restaurant CMS**: `cuisine`, `dietary`, `allergens`, `spiciness`, `calories`, `is_vegan`.
> - **LMS**: `difficulty_level`, `language`, `duration_hours`, `certification`, `instructor_tier`, `track`.
> - **Real-estate**: `property_type`, `bedrooms`, `bathrooms`, `square_meters`, `heating`, `parking`, `neighborhood`.
>
> The function `is_facet_candidate(attr_name, attr_type, list_titles)` is universal — it consults `FACET_CANDIDATE_BY_NAME` first, then `NEVER_USE_AS_FACET_BY_TYPE` / `NEVER_USE_AS_FACET_BY_NAME` (both universal), then falls back to type-based heuristics. Only the contents of `FACET_CANDIDATE_BY_NAME` are vertical-specific. Adding entries is non-destructive.

```python
FACET_CANDIDATE_BY_NAME = {
    # Always useful as facets — discrete or numeric, low cardinality
    # (fashion-shop / e-commerce defaults — extend per vertical)
    'price', 'color', 'size', 'brand', 'material', 'gender', 'season',
    'style', 'pattern', 'length', 'sleeve', 'neckline', 'fit',
    'heel_height', 'weight', 'volume', 'rating',
    'in_stock', 'is_new', 'is_featured', 'is_sale',
}

# 19 AttributeType values:
# string, text, textWithHeader, integer, real, float, dateTime, date, time,
# file, image, groupOfImages, radioButton (flag), list, button, entity, spam, json, timeInterval
NEVER_USE_AS_FACET_BY_TYPE = {
    'text', 'textWithHeader', 'image', 'groupOfImages', 'file',
    'json', 'dateTime', 'date', 'time', 'timeInterval',
    'entity', 'button', 'spam',
}
NEVER_USE_AS_FACET_BY_NAME = {'sku', 'barcode', 'name', 'title', 'slug', 'description'}

def is_facet_candidate(attr_name: str, attr_type: str, list_titles: dict | None) -> bool:
    """True if attribute makes sense as a catalog facet."""
    if attr_type in NEVER_USE_AS_FACET_BY_TYPE:
        return False
    if attr_name in NEVER_USE_AS_FACET_BY_NAME:
        return False
    if attr_name in FACET_CANDIDATE_BY_NAME:
        return True
    if attr_type == 'list' and list_titles:
        # Multi-select is the same enum type with `listType: 'multi'` — no separate `multiList` type.
        return True
    if attr_type == 'radioButton':
        # The boolean flag is `flag = 'radioButton'` in the enum; on `SchemaItem.type` it is the string 'radioButton'.
        return True
    if attr_type in {'integer', 'real', 'float'}:
        return True
    if attr_type == 'string':
        # Free-form string CAN be a facet when the value space is small (color names, brand names).
        # The mapper still has to decide based on attr_name (see FACET_CANDIDATE_BY_NAME).
        return False
    return False
```

⚠ This heuristic is used to BUILD the task list (`attribute_identifiers: [...]`) — NOT to mutate the attribute schema.

## 5. Inspector signal patterns

See `code-inspector.md` Step 8.5 for the full grep list. Quick reference:

```bash
# Filter UI components (any project, framework-agnostic regex)
<(FilterPanel|FilterSidebar|FacetList|CategoryFilter|PriceRangeSlider|ColorPicker|SizePicker|BrandFilter|FilterDrawer|FiltersBottomSheet|FilterChip|ActiveFilter)

# Filter hooks / state slices
(useFilters|useFacets|useProductFilters|filtersSlice|facetReducer|selectedFilters|filterState)

# URL query parameters used as facets — capture the param name
searchParams\.get\(['\"](color|size|brand|price_min|price_max|category|material|in_stock|gender)
\?(color|size|brand|price_min|price_max|in_stock|gender)=

# Third-party search/facet libraries
(algoliasearch|meilisearch|instantsearch|@elastic/react-search)
```

Output schema (inspector.yaml):

```yaml
detected_signals:
  filters:
    present: true | false
    signals:
      - { kind: component,   name: FilterPanel,           path: components/catalog/FilterPanel.tsx:12 }
      - { kind: query_param, name: color,                 path: app/(catalog)/[gender]/[category]/page.tsx:42 }
      - { kind: hook,        name: useProductFilters,     path: hooks/useProductFilters.ts:18 }
    attribute_candidates: [color, size, brand, price, in_stock]
    scope_pages:          [women-clothing, men-bags, sale]
    visible_label:        { en_US: 'Filters' }   # null if not found in source — DO NOT hallucinate
```

## 6. Archetype templates (which filters to default to)

Used by the mapper when the inspector signal is `present: false` but catalog pages exist.

| Project archetype | Default filters per catalog page | Items |
|---|---|---|
| **E-commerce / fashion** | one per `gtid=4` catalog | `attribute` items: `price`, `color`, `size`, `brand`, `material`, `season`, `style` |
| **E-commerce / electronics** | one per `gtid=4` catalog | `price`, `brand`, `screen_size`, `ram`, `storage`, `cpu`, `in_stock` |
| **E-commerce / grocery** | one per `gtid=4` catalog | `price`, `brand`, `unit`, `is_organic`, `dietary_*`, `in_stock` |
| **Marketplace / multi-vendor** | one per `gtid=4` catalog | `price`, `brand`, `seller`, `shipping_from`, `rating`, `condition` |
| **Content / blog / articles list** | one per articles-list page | items target the `forPages` attribute_set: `category`, `tags`, `author`, `published_date` |
| **B2B catalog** | one per catalog | `price`, `volume_discount`, `lead_time`, `industry`, `certification` |
| **Real estate** | one per listings page (products = listings) | `price`, `bedrooms`, `bathrooms`, `area`, `city`, `property_type` |
| **Discount/coupon landing** | one filter | mixed `attribute` (`category`) + direct `discount` items |
| **Payment-method picker (checkout)** | one filter | direct `payment-method` items |

## 7. Real REST API contract (post-import orchestrator)

Verified against the admin filters controller + DTOs.

### 7.1 Create filter

```http
POST {API_BASE}/api/admin/filters
Authorization: Bearer {ADMIN_JWT}
Content-Type: application/json

{
  "identifier":    "women-clothing",                          // REQUIRED, marker pattern /^[A-Za-z]+[a-zA-Z0-9_-]*$/, max 255
  "localizeInfos": { "en_US": { "title": "Filters" } },       // REQUIRED — non-empty object; each lang must be an object with string values
  "scopeTypes":    ["product", "attribute"]                   // OPTIONAL; FilterScopeType enum array
}
→ 200 (FilterEntity) { "id": 42, "identifier": "women-clothing", "localizeInfos": {...}, "scopeTypes": [...], "createdDate": "...", "updatedDate": "..." }
```

Important:
- Field is `localizeInfos`, **camelCase** (validated by `@IsLocalizeInfos()`).
- Field is `scopeTypes`, **camelCase** (enum array). NO `marker` field in the body.
- `marker` is only a URL segment in `GET /api/admin/filters/marker-validation/:marker` (admin) and `GET /api/content/filters/marker/:marker` (storefront). The "marker" value **== `identifier`** (verified: `BaseAbstractService.isExistMarker(identifier)` → `repo.findOne({ where: { identifier } })`).
- **`identifier` should match `markerPattern`** (`/^[A-Za-z]+[a-zA-Z0-9_-]*$/` — the standard OneEntry marker pattern from `general.config`). `CreateFilterDto` itself does NOT apply `@Matches(markerPattern)` — `POST /filters` accepts any string up to 255 chars — but URL-level validators on `GET /api/admin/filters/marker-validation/:marker`, `GET /api/admin/filters/marker/:marker` and `GET /api/content/filters/marker/:marker` reject non-matching markers (HTTP 400). A filter with `identifier="404"` is creatable but UNREACHABLE from storefront/admin lookups. Always start the identifier with a letter; allowed chars after: letters, digits, `_`, `-`.
- **`localizeInfos` is REQUIRED and must NOT be empty.** `IsLocalizeInfos` rejects: empty object, non-object values per lang, non-string nested values. If you don't have a title from the source code, send `{ "<lang>": { "title": "" } }` (empty string is a valid string).

### 7.2 Add items (batch)

```http
POST {API_BASE}/api/admin/filters/{filterId}/items
Authorization: Bearer {ADMIN_JWT}
Content-Type: application/json

{
  "items": [
    { "objectType": "attribute",      "objectId": 5,  "attributeIdentifier": "color" },
    { "objectType": "attribute",      "objectId": 5,  "attributeIdentifier": "size"  },
    { "objectType": "attribute",      "objectId": 5,  "attributeIdentifier": "brand", "valueText": "Nike" },
    {
      "objectType": "attribute", "objectId": 5,  "attributeIdentifier": "price",
      "isRange": true, "rangeFrom": 0, "rangeTo": 500,
      "allowedProductStatusIds": [1, 2]
    },
    { "objectType": "page",           "objectId": 12 },
    { "objectType": "product",        "objectId": 100 },
    { "objectType": "discount",       "objectId": 42 },
    { "objectType": "payment-method", "objectId": 3  }
  ]
}
→ 200 (FilterItemEntity[]) [ { "id": 100, "objectType": "attribute", "objectId": 5, "attributeIdentifier": "color", ... }, ... ]
```

Important:
- `objectType` is **camelCase**, value is `FilterScopeType` enum string.
- `objectId` is **required `int`** — for `attribute` items it is the **id of the parent `attributes_sets` row** (e.g. forProducts.id). For `page` it is `pages.id`, etc.
- `attributeIdentifier` is the key inside `attributes_sets.schema` (only used when `objectType=attribute`; ignored otherwise — set to null).
- `attributeValueId` is the `listTitles` row id (only for `list`/`radioButton` attributes when filtering to a single value).
- `valueText` is the raw string for `string`/`text` typed facets when filtering to a specific value.
- **`isRange` / `rangeFrom` / `rangeTo`** — for numeric attributes (`integer`, `real`, `float`) you can emit a range facet (price slider, weight slider, rating slider). Only valid when `objectType: 'attribute'` AND the attribute's type is numeric AND `attributeValueId`/`valueText` are NOT set. `rangeFrom <= rangeTo` enforced server-side.
- **`allowedProductStatusIds: number[]`** — restrict the item to products with these status ids (typical for "Sale price" facets that should only appear when a sale status is active). Service normalises this to `null` when the filter is not `forProducts`-scoped.
- NO `position_after` field. Position is set by the order in the `items[]` array (lexorank assigned server-side); to change later call `PUT /filters/:id/items/:itemId/position`.

#### 7.2.1 Bulk-replace attribute items (recommended for idempotency)

`filter_items_mn` has no UNIQUE constraint, so `POST /:id/items` is NOT idempotent — re-running it creates duplicates. For attribute-scoped items there is now a dedicated atomic-replace endpoint:

```http
PUT {API_BASE}/api/admin/filters/{filterId}/items/attribute/replace
{
  "attributeSetId":      5,        // REQUIRED int — the parent attributes_sets row id
  "attributeIdentifier": "color",  // REQUIRED string ≤255 — the schema key inside that set
  "items": [
    { "objectType": "attribute", "objectId": 5, "attributeIdentifier": "color" },
    { "objectType": "attribute", "objectId": 5, "attributeIdentifier": "color", "valueText": "red"  },
    { "objectType": "attribute", "objectId": 5, "attributeIdentifier": "color", "valueText": "blue" }
  ]
}
→ 200 (FilterItemEntity[])  [ { "id": 100, "objectType": "attribute", "objectId": 5, "attributeIdentifier": "color", ... }, ... ]
```

```http
# Example 2 — replace with range items (numeric attribute like price/weight):
PUT {API_BASE}/api/admin/filters/{filterId}/items/attribute/replace
{
  "attributeSetId":      5,
  "attributeIdentifier": "price",
  "items": [
    { "objectType": "attribute", "objectId": 5, "attributeIdentifier": "price",
      "isRange": true, "rangeFrom": 0, "rangeTo": 100,
      "allowedProductStatusIds": [1] },
    { "objectType": "attribute", "objectId": 5, "attributeIdentifier": "price",
      "isRange": true, "rangeFrom": 100, "rangeTo": 500,
      "allowedProductStatusIds": [1] }
  ]
}
→ 200 (FilterItemEntity[])

# Example 3 — clear all items for one (attributeSetId, attributeIdentifier) pair:
PUT {API_BASE}/api/admin/filters/{filterId}/items/attribute/replace
{
  "attributeSetId":      5,
  "attributeIdentifier": "deprecated_facet",
  "items": []
}
→ 200 (FilterItemEntity[])  []
```

Body shape (verified against `ReplaceAttributeFilterItemsDto`):
- `attributeSetId: number` — REQUIRED. The parent `attributes_sets` row id (e.g. `forProducts.id`).
- `attributeIdentifier: string` (≤255) — REQUIRED. The schema key inside that attribute_set.
- `items: AddFilterItemRecordDto[]` — REQUIRED array. Each item has the same shape as in §7.2 (`objectType`, `objectId`, `attributeIdentifier`, optional `attributeValueId`/`valueText`/`isRange`/`rangeFrom`/`rangeTo`/`allowedProductStatusIds`).

Behaviour (verified against `admin-filters.service.ts` + `admin-filters.controller.ts`):
- Deletes ALL existing attribute-typed items **for this filter that match the given `(attributeSetId, attributeIdentifier)` pair**, then inserts the new list.
- Other attribute-items in the same filter (for OTHER `(attributeSetId, attributeIdentifier)` pairs) are NOT touched.
- Page / product / discount / payment-method items are NOT touched.
- Response is `FilterItemEntity[]` — the array of newly saved items (NOT a `{ removed, added }` summary).
- Use this whenever the orchestrator re-runs filter setup against an existing filter — replace is idempotent per `(attributeSetId, attributeIdentifier)`, `POST /items` is not.

⚠ **One call per `(attributeSetId, attributeIdentifier)` pair.** To replace items for multiple attributes (`color`, `size`, `brand`, ...) — issue one PUT per attribute. The endpoint is intentionally narrow: it replaces ONE attribute's facet items atomically, not the whole filter.

Permission: `AdminPermissionsEnum['filter.items.add']` + `filter.items.remove`.

#### 7.2.2 Reorder an existing item

```http
PUT {API_BASE}/api/admin/filters/{filterId}/items/{itemId}/position
{ "position_after": <itemId|null> }   // null = move to head
```

Permission: `filter.items.changePositions`.

### 7.3 Add custom items (free-form content)

```http
POST {API_BASE}/api/admin/filters/{filterId}/custom-items
{
  "localizeInfos": { "en_US": { "title": "On Sale" } },
  "value":         "/sale",                          // required string — URL or arbitrary identifier
  "identifier":    "external-on-sale"                // optional
}
```

Verified against `CreateFilterCustomItemDto`: `localizeInfos`, `value` (required, NOT `url`), `identifier?`.

Additional custom-item endpoints (verified against `admin-filters.controller.ts`):
- `PUT /filters/:id/custom-items/:itemId` — update an existing custom item (full `UpdateFilterCustomItemDto`).
- `DELETE /filters/:id/custom-items/:itemId` — remove.
- `PUT /filters/:id/custom-items/:itemId/position` — reorder by lexorank, body `{ position_after: <itemId|null> }`.

### 7.4 Idempotency before creating

```http
GET {API_BASE}/api/admin/filters/marker-validation/{identifier}
→ 200 (MarkerValidDto) { "valid": true | false }      # true = identifier free, false = already taken
```

Or:
```http
GET {API_BASE}/api/admin/filters
→ 200 AdminFilterDto[]    # plain array (verified — admin-filters.controller.ts:90-93 returns Promise<AdminFilterDto[] | ContentFilterDto[]>)
```

⚠ **`filter_items_mn` has NO unique constraint** on `(filter_id, object_type, object_id, attribute_identifier)` (verified: `FilterItemEntity` only declares `@Index()` on individual columns, no `@Unique(...)`). Calling `POST /filters/:id/items` twice with the same payload will create duplicate items. The orchestrator's idempotency therefore relies on the **filter** existing — if the filter is missing it creates the filter + items in one shot; if the filter already exists it skips the entire task. This is acceptable because:
- A successful first run produces filter + items.
- A failed first run (filter created, items failed) leaves orphan filter with no items — admin must finish the attachment manually via OneEntry Platform UI.
- Re-running after success does NOT re-add items (filter exists → skip).

### 7.5 Required admin permissions (`AdminPermissionsEnum`)

The orchestrator's JWT must carry these permissions:

| Endpoint | Permission |
|---|---|
| `POST /api/admin/filters` | `filter.create` |
| `PUT /api/admin/filters/:id` | `filter.update` |
| `DELETE /api/admin/filters/:id` | `filter.delete` |
| `POST /api/admin/filters/:id/items` | `filter.items.add` |
| `DELETE /api/admin/filters/:id/items/:itemId` | `filter.items.remove` |
| `GET /api/admin/attributes-sets` | the default admin token covers this |

Verified against the `AdminPermissionsEnum` + `@GrantByPermission` decorators on the admin filters controller. If the orchestrator's account lacks `filter.*` permissions, the calls return HTTP 403 — the manual fallback is the OneEntry Platform UI → Filters module.

### 7.6 What CANNOT be auto-resolved

There are NO admin endpoints to look up `pages`/`products` by identifier (no `/marker/:marker` on `admin-pages.controller.ts` / `admin-products.controller.ts`). The `/marker/:marker` on `attributes-sets` exists but throws `MethodNotAllowedException`. The orchestrator therefore cannot create `direct_items` of types `page`, `product`, `discount`, `payment-method`, `admin`, `bonus` automatically — it must log them as **manual tasks** in `post-import.log.md`. Only `attribute` items are fully automated (via the `GET /attributes-sets` list lookup).

## 8. Anti-patterns (project-agnostic)

| ❌ Wrong | ✅ Right |
|---|---|
| Writing rows into `filters` / `filter_items_mn` inside the blueprint JSON | Emit `mapped.post_import_filters[]` + `out-of-whitelist-needs-post-import:` warning |
| Setting `isFilter: true` / `isIndexed: true` / `isFacet: true` on a `SchemaItem` | Don't. None of those flags exist in `SchemaItem`. Indexing is automatic. |
| Passing `marker`, `scope_types`, `localize_infos`, `object_type`, `attribute_identifier` (snake_case) in REST bodies | Use **camelCase**: `identifier`, `scopeTypes`, `localizeInfos`, `objectType`, `attributeIdentifier` |
| Passing only `attributeIdentifier` without `objectId` | Always include `objectId` = ID of the parent `attributes_sets` row |
| One global filter for the whole storefront | One filter per catalog page (or per group sharing a marker) |
| `attribute` items pointing to attributes that don't exist in the parent `attribute_set.schema` | Storefront returns empty items array. Match identifier exactly. |
| Setting `objectType='attribute'` for an attribute of type `text` / `textWithHeader` / `image` / `groupOfImages` / `file` / `json` / `dateTime` / `date` / `time` / `timeInterval` / `entity` | Aggregator can't bucket these — picker explodes or stays empty. Use the heuristic in §4. |
| Hardcoding filter `localizeInfos.<lang>.title` from the page identifier (Title-Cased identifier) | Hallucination — pass an empty string `""` (not `null`, which fails `IsLocalizeInfos` validation) and let the admin fill the visible label via OneEntry Platform UI. |

## 9. End-to-end pipeline example (universal)

1. **Inspector** scans the project, finds `<FilterPanel>` in `app/(catalog)/[gender]/[category]/page.tsx`, finds query params `color`/`size`/`brand`/`price_min`/`price_max`, emits `detected_signals.filters` with `scope_pages: [women-clothing, men-bags, kids-shoes, sale]` and `attribute_candidates: [color, size, brand, price]`.
2. **Mapper** copies the signals into `mapped.post_import_filters[]` — one entry per scope_page. Emits warning `out-of-whitelist-needs-post-import: 4 filters …`. Does NOT mutate `attributes_sets.schema`.
3. **Builder** writes blueprint JSON. The `attributes_sets` rows contain only the canonical `SchemaItem` system flags. No filter-related fields.
4. **Validator** checks the blueprint for whitelist/FK/etc. S60 verifies that catalog pages + `post_import_filters[]` are consistent.
5. **Loader** (`POST /api/admin/import/from-blueprint`) creates all whitelist entities. As `attributes_sets` rows land, the `'index-data'` Bull consumer fires automatically and creates `index_attributes` + `index_attribute_data` rows for ALL attributes (no opt-in).
6. **Post-import orchestrator Step 7** reads `mapped.post_import_filters[]`. For each task:
   - Resolves `attribute_set_identifier` → DB ID via `GET /api/admin/attributes-sets` (CRUD list) + client-side filter by `identifier`. The `/marker/:marker` endpoint on attributes-sets exists but throws `MethodNotAllowedException` — it is NOT usable.
   - `POST /filters` with camelCase body.
   - `POST /filters/:id/items` batch with `objectType='attribute'`, `objectId=<attribute_set_id>`, `attributeIdentifier=<each>`.
   - Logs each result; skips on duplicate identifier.
7. **Storefront** calls `GET /api/content/filters/marker/women-clothing` → receives facets populated from `index_attribute_data` (already filled by Bull during step 5).

## 10. Validator coverage

- **S60** — INFO when catalog pages exist but mapper didn't emit `post_import_filters[]` (full text in `blueprint-validator.md`).
- **S15** — WARNING for orphan blocks (covers the related orphan-content concern).
- **S31** — `out-of-whitelist:` warnings from mapper are converted to INFO in final report.

There is NO check for "isFilter on forbidden type" — the flag does not exist, so the check is impossible.

## 11. Cross-references

- Runtime model + SQL — summarised inline in §1 (polymorphic `filter_items_mn` keyed by `objectType`/`objectId`/`attributeIdentifier`).
- Index pipeline — summarised inline in §1 (Bull `'index-data'` queue enqueued only when products/products_pages_mn are touched; no `isFilter` flag exists, indexing covers every attribute in real product data).
- Real `SchemaItem` flags — listed inline in §1 (`isPrice`, `isSku`, `isCurrency`, `isTaxRate`, `isPassword`, `isLogin`, `isSignUp`, `isNotificationEmail`, `isNotificationPhonePush`, `isNotificationPhoneSMS`, `isVisible`, `isProductPreview`, `isCompress`, `isIcon`, `isRatingValue`, `splitPrice`+`splitParts`+`splitUnit`).
- Real DTOs — exact JSON shapes shown inline in §7 (`CreateFilterDto`, `AddFilterItemsDto`).
- Real Controllers — endpoint contract shown inline in §7 (`/api/admin/filters`, `/api/admin/filters/:id/items`, etc.).
- Anti-hallucination of titles — `oneentry-invariants.md` §18.
- Post-import REST flow — `post-import-orchestration.md` Step 7.
