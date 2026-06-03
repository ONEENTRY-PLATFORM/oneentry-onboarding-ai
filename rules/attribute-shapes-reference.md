# Attribute shapes — DATA + SCHEMA conventions (admin-UI source of truth)

> **⚠ Universality note.** These conventions are vertical-agnostic: e-commerce / restaurant / salon / hotel / EdTech / corporate / personal cabinet / SaaS — every project that has `attributes_sets` follows the same shape rules.

> **Companion file** to `oneentry-invariants.md` (sections §1–21 live there). This file holds the per-attribute-type shape contracts that every mapper / builder / orchestrator must obey, plus the storage-key formula and the slider/collection completeness invariants.

> **Empirically verified** against admin form renderers under `cms_frontend/src/components/shared/Custom/Attributes/Parameters/`. Keep IN SYNC if renderers change.

---

## Per-attribute-type data SHAPE convention (was §21.5) — CRITICAL for admin UI

⚠ **Beyond the storage-KEY convention (see §22 below), the admin UI also requires a specific value SHAPE per attribute type.** Plain scalar values that are syntactically valid JSON but the wrong shape produce empty dropdowns / disabled inputs in the admin without any error message. The pipeline MUST emit the correct shape from the start (or fix it in the post-import alignment step).

| Attribute type | Data shape at `<entity>.attributes_sets[lang][<type>_id<id>]` | Frontend code |
|---|---|---|
| `string`, `textarea` | plain string `"abc"` | `StringFieldsParameters.js:78` |
| `text` | `{htmlValue:"…", plainValue:"…", mdValue:"…", params:{editorMode:"HTML"}}` (object — NOT string) | `TextFieldsParameters.js:99,822-823` |
| `integer` / `real` | **string `"123.45"`** (NOT number — admin renderer does `.trim()`) | `NumberFieldsParameters.js:68-70` |
| `dateTime` / `date` / `time` | `{fullDate:"ISO", formattedValue, formatString}` (object — NOT bare ISO string) | `DateFieldsParameters.js:550` |
| `image` / `groupOfImages` | `[{filename, downloadLink, previewLink:{"1":[origUrl, previewUrl], ...}}]` — note **`previewLink` values are tuples `[url, url]`**, NOT bare strings | `ImageFieldsParameters/ImageFieldsParameters.js:59,98,113` |
| `file` | `[{filename, downloadLink, size?}]` (array, like image) | `FileFieldsParameters.js:329` |
| `radioButton` | `{value: "X"}` (object) — NOT boolean, NOT bare string, NOT `""` | `RadioButtonFieldsParameters.js:34,44,56` |
| `list` (single / multi) | `[{value: "OPT1"}, {value: "OPT2"}]` (array of `{value}` objects) | `ListFieldsParameters.js:101-102,137,150` |
| `entity` | array of `{id, type}` objects | `ListEntityParameters.js` |
| `button` | `{value, href}` object | `ButtonFieldsParameters.js` |
| `textWithHeader` | array `[{header, htmlValue, plainValue, mdValue, params, index}]` | `TextWithHeaderFieldsParameters.js:108-127` |
| `json` | arbitrary JSON value | `JsonFieldsParameters.js` |
| `timeInterval` | `{value, unit}` object | `TimeIntervalParameters.js` |
| `spam` | string + flag | `SpamFieldsParameters.js` |

🚨 **The single most common drift traps:**
1. `list` attributes saved as raw value (`"BrandX"`) or array of strings (`["S","M","L"]`) — admin silently renders empty dropdown.
2. `text` saved as plain string instead of `{htmlValue, plainValue, mdValue, params}` — editor shows blank.
3. `integer`/`real` saved as number — `NumberFieldsParameters.js:228` `.trim()` crashes if a validator demands it.
4. `image.previewLink: {1: "url"}` (bare string) — `ImageFieldsParameters` reads `Object.values(previewLink).map(p => p[1])` and gets the second character of the URL.
5. `radioButton` saved as bare string `"opt"` or `""` — `state?.value === undefined` → "not selected".

---

## SCHEMA shape (companion to DATA shape above)

Beyond the data side, the SCHEMA inside `attributes_sets.schema.attributeN` has its own contract that the admin enforces:

| Schema field | Required shape | Frontend reader |
|---|---|---|
| `listTitles[lang]` (for `list`, `radioButton`) | **ARRAY** `[{value, title, position}]` — NEVER dict `{"X":"X"}` | `ListFieldsParameters.js:109` (`Array.isArray`), `ListEntityOptions.js:441`, `AttributeWithValueViewer.js:246` |
| `multiselect` (for `list`) | boolean `true` for multi-value | `ShowAttributesFields.js` (via `isMulti` prop) |
| `listType` | only `'flat'` or `'nested'` (for `entity`-typed only). Values `'single'`/`'multiple'` are REJECTED — use `multiselect` instead | `ListEntityOptions.js:27-30` |
| `validators[lang]` | object with `stringInspectionValidator` / `regExpValidator` / `checkForNumberValidator` / `requiredValidator` keys — generated from `rules` | `StringFieldsParameters.js:227-465`, `NumberFieldsParameters.js`, `DateFieldsParameters.js` |
| `rules` | declarative constraints (`minLength`, `maxLength`, `pattern`, `minValue`, `maxValue`); admin does NOT read directly — `post-mapper-fixer.py::normalize_attribute_schema_shape` derives `validators[lang]` from these | storefront SDK only |
| `localizeInfos[lang]` | `{title, description?}` | universal |

---

## Validators S70 (recommended)

- **S70a** — `list` data must be `[{value:...}]` (or absent).
- **S70b** — `listTitles[lang]` must be array, not dict.
- **S70c** — `listType` must be `'flat'`/`'nested'` or absent.
- **S70d** — `text` data must be `{htmlValue,...}` object.
- **S70e** — `integer`/`real` data must be string.
- **S70f** — `image.previewLink` values must be `[url,url]` tuples.
- **S70g** — `radioButton` data must be `{value:X}` object.
- **S70h** — `date`/`dateTime`/`time` data must be `{fullDate,...}` object.

All S70 violations are auto-fixed by `post-mapper-fixer.py::transform_attribute_data_to_admin_shape` and `normalize_attribute_schema_shape` before blueprint-build — but mapper agents should emit correct shapes from the start so the transform is a no-op.

---

## §22. Attribute storage key convention — `{type}_id{innerId}`

**Source of truth — keep this section IN SYNC with admin-UI value-lookup code.**

The CMS stores attribute VALUES inside `attributes_sets` jsonb columns (on `products` / `pages` / `blocks` / `forms` / `user_groups` / `slides`) under a key that is **DIFFERENT** from the schema key:

| Where | Key format | Example |
|---|---|---|
| `attributes_sets.schema` (after loader normalization) | `attribute<innerId>` | `attribute1`, `attribute2`, … |
| `<entity>.attributes_sets[lang]` (admin-UI value lookup) | `<type>_id<innerId>` | `string_id1`, `list_id3`, `real_id5`, `image_id7`, `radioButton_id12` |

The admin-UI renderer (`ShowAttributesFields.js:175,206,269,…`) reads VALUES via the `<type>_id<innerId>` form. Mapper / builder / orchestrator MUST emit data under this key shape, NOT under the semantic identifier (`sku`, `brand`, `price`).

⚠ **Mechanical formula** (no ambiguity):

```
ui_key = schema.<attribute>.type + '_id' + schema.<attribute>.id
```

So for a schema item `{ id: 3, type: 'list', identifier: 'brand', ... }` the data key MUST be `list_id3` — never `attribute3`, never `brand`.

**Loader behaviour:** the blueprint loader normalizes `attributes_sets.schema` keys → `attribute<N>` on insert, but does **NOT** touch `<entity>.attributes_sets` jsonb. The pipeline therefore runs `task_align_attribute_keys` (in `post-import-orchestrator.py`) AFTER import to do a full DB-side rename `<semantic> → <type>_id<innerId>`.

**Anti-pattern check (S69):** validator MUST scan each entity's `attributes_sets[lang]` and verify EVERY key matches `<type>_id<innerId>` of an existing schema item; orphan / semantic / `attribute<N>` keys → ERROR. Universal across project types.

---

## §23. Slider-block min-slides invariant

Any block that is visibly slot-shaped — `general_type_id` ∈ {`slider_block`=25, `trending_block`=26, `recently_viewed_block`=27, `personal_recommendations_block`=29, `cart_complement_block`=30, `cart_similar_block`=31, `wishlist_similar_block`=32} — falls into ONE of two categories:

| Category | Required content | Examples |
|---|---|---|
| **Static-content slider** (`slider_block` typically) | MUST have ≥ 1 `slides[]` row before storefront render | hero carousel, category tiles slider, brand showcase |
| **Server-populated slider** (all `*_block` ids 26-32) | Empty `slides[]` is OK — content comes from runtime queries | `trending_block`, `recently_viewed_block`, `personal_recommendations_block`, `cart_complement_block`, … |

**Validator S66:** for each block with `general_type_id=25` that is `is_visible: true` AND bound to ≥1 page via `block_pages_mn` → MUST have a non-empty `slides` task in `mapped.post_import_slides[]` (or be expressly marked `mapped.notes.skip_slides: ['<block_identifier>']` for the rare placeholder cases).

**Anti-pattern:** demoting a `slider_block` to `common_block` (id=18) just because the project has no slide data is wrong — admins will lose the ability to add slides later. Either provide source data (heroSlides.ts / sliderConfig.ts / equivalents) OR add the explicit skip marker.

---

## §24. Visible-collection completeness invariant

A `collection` (`integration_collections` table) is **visible** if any of these is true:
- The collection's `identifier` is referenced from a published `page.attributes_sets` (e.g. an info page that renders FAQ accordion).
- A `block` carries the collection's identifier in its `attributes_sets` config.
- The collection's `identifier` matches a top-level page URL (e.g. `stores`, `faq`, `team`, `branches`).

**Validator S67:** for every visible collection, `COUNT(collection_rows WHERE collection_id = X) > 0`. Zero rows on a visible collection → **ERROR** (admin renders an empty Store Locator / FAQ accordion / Team grid — a silent broken UX).

Universal: applies to every project type that uses listing collections (FAQ everywhere; stores for retail/restaurant/salon/hotel; team for corporate/SaaS; testimonials for any B2C; partners for B2B).
