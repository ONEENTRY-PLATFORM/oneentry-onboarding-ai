# `forProducts` architecture in OneEntry

> **⚠ Universality note.** Examples below frequently use fashion-shop terms (clothing / shoes / bags / women / men) because that is the reference test project. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop (`product/sku/brand/category`), restaurant (`menu-item/dish/cuisine/section`), beauty salon (`service/master/treatment/duration`), hotel (`room/suite/amenity`), EdTech (`course/lesson/level`), corporate site (`page/department/team`), personal cabinet (`section/setting/subscription`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is hand-written.** It describes the correct product data model.
> - Created 2026-05-31 after v4 import showed four failure modes:
>   1. `forProducts_*.schema` contained discount fields (`sale_price`, `discount_amount`, `discount_percent`) — these belong to the **Discounts module**, not to product attributes.
>   2. `forProducts_*.schema` contained status flags (`in_stock` as radioButton) — `in_stock` is a **product_status** row, not an attribute.
>   3. `forProducts_*.schema` contained marketing flags as separate radioButton attributes (`is_new`, `is_featured`, `is_bestseller`) — these should be consolidated into a **single `tags: type=list`** attribute.
>   4. Repeated text values (`brand`, `brand_country`, `material`, `style`, `silhouette`, `fit`, `closure_type`, `upper_material`, `sole_material`, `lining_material`, `material_origin`, `material_finish`, etc.) were emitted as `type=string` instead of `type=list` with `listTitles` — admin cannot filter / drop-down them in UI.

## Core principle: forProducts NARROW = only product-specific attributes

In OneEntry:

- A **product** (`products` table) carries `attributes_sets.schema` from `forProducts_<segment>` (`attribute_set` type_id=5). The jsonb schema describes **product-intrinsic data** only: title, sku, price, cover, gallery, description, specs, plus segment-specific physical traits.
- **Status** of a product (in_stock / out_of_stock / preorder / sold_out / draft / archived) → row in `product_statuses` (preseeded enum, FK = `products.status_id`).
- **Discounts** (sale prices, percent-off, BOGO, tiered) → entities in the `discounts` module (out-of-whitelist for blueprint, configured via `post_import_discounts[]` REST).
- **Marketing badges** (NEW, FEATURED, BESTSELLER, FLAGSHIP, LIMITED, SALE) → single `tags: type=list` attribute on `forProducts_*` (one attribute, list of values), NOT separate radioButton attributes per badge.
- **Repeated dictionary values** (brand names, country origins, materials, styles, fits) → `type=list` attribute with `listTitles` populated from values found in project mock data.

## ❌ FORBIDDEN_PRODUCT_FIELDS — never in `forProducts_*.schema`

| Field pattern | Where it goes instead |
|---|---|
| `sale_price`, `discount_price`, `original_price`, `oldPrice` (display-only old/new price pair) | **`post_import_discounts[]`** (Discounts module). Product retains `price: real` only; the discount engine recalculates effective price at runtime. |
| `discount_amount`, `discount_percent`, `discount_pct`, `percentOff` (% off / fixed amount) | **`post_import_discounts[]`** task. Mapper emits one task per discount pattern found by inspector. |
| `promo_code`, `coupon_code`, `voucher_code` (single-product field) | **`discount_coupons`** (out-of-whitelist, manual setup). Do NOT add as attribute. |
| `in_stock`, `availability`, `stock_status`, `is_available`, `inStock` (any boolean / status flag) | **`product_statuses`** (preseeded enum: `in_stock`, `out_of_stock`, `preorder`, `coming_soon`, `sold_out`, `discontinued`, `draft`, `archived`). Product references via `status_id`. |
| `stock_quantity`, `stock_count` (numeric inventory) | **Out-of-whitelist** (inventory module). Product's `status_id` reflects the boolean side (in/out of stock). |
| `is_new`, `is_featured`, `is_bestseller`, `is_flagship`, `is_limited`, `is_hot`, `is_sale` (marketing flags) | **Consolidate** into single `tags: type=list` attribute with `listTitles: { en_US: { NEW: 'New', FEATURED: 'Featured', BESTSELLER: 'Bestseller', FLAGSHIP: 'Flagship', LIMITED: 'Limited', SALE: 'Sale' } }`. One attribute, multi-select list, instead of 5+ radioButtons. |
| `rating`, `rating_count`, `average_rating`, `reviews_count` (computed aggregates) | **Out-of-whitelist** (reviews engine maintains these in a separate aggregate table). Do NOT add as editable attribute — they are read-only and auto-updated by review submissions. |
| `view_count`, `purchase_count`, `wishlist_count` | **Out-of-whitelist** (analytics module). Read-only computed metrics. |
| `category_ids`, `tag_ids`, `collection_ids` (M2M to other entities) | **`products_pages_mn`** (category) / `product_blocks_mn` (collections). Do NOT duplicate as jsonb attribute. |

If inspector reports such fields → mapper routes them to the right destination (statuses / discounts / tags consolidation / out-of-whitelist warning) instead of adding to `forProducts_*.schema`.

## REPEATED_VALUES_AS_LIST heuristic

When inspector collects products and discovers a string attribute whose values **repeat across multiple products with a bounded vocabulary**, mapper MUST convert it to `type: list` with `listTitles` filled from the discovered values.

### Heuristic decision rule

For each candidate attribute on `forProducts_<segment>.schema`:

```
IF attribute.type IN [string, text] AND
   COUNT(distinct values across all products in segment) <= 20 AND
   COUNT(occurrences) >= 2 AND                              # repeats at least twice
   MAX(LENGTH(value)) <= 60                                 # short, dictionary-like
THEN
   attribute.type := 'list'
   attribute.listTitles[lang] := { v: v.title_case() for v in distinct_values }
```

### Whitelist of fields that ALWAYS get `type: list`

> ⚠ **Fashion / e-commerce vertical defaults.** The whitelist below contains attribute identifiers from the fashion-retail reference project. The **rule** is universal — "fields that semantically belong to a closed vocabulary should be `type: list` so the admin can extend values via UI" — but the **specific identifier set is vertical-rooted**. For other verticals, extend OR replace per project:
>
> - **Hotel CMS**: `bed_type`, `view_type`, `floor_type`, `amenities_included`, `bathroom_type`, `room_category`
> - **Restaurant CMS**: `cuisine`, `dietary`, `allergens`, `spiciness`, `cooking_method`, `temperature`, `course_type`
> - **LMS**: `difficulty_level`, `language`, `instructor_tier`, `certification`, `track`, `prerequisites_category`
> - **Real-estate**: `property_type`, `heating`, `parking`, `flooring`, `amenities`, `neighborhood_class`
> - **B2B SaaS**: `plan_tier`, `feature_category`, `integration_type`, `compliance_level`
>
> The function `if attribute_name in WHITELIST_ALWAYS_LIST: type='list'` is universal; the contents of `WHITELIST_ALWAYS_LIST` are project-specific. Adding entries is non-destructive; removing breaks fashion projects.

Even if inspector finds only 1 value in current mock data (project is small), the following semantic fields **must** be emitted as `type: list` (so admin can extend the vocabulary later in UI):

```
brand, brand_country, country_of_origin,
material, material_origin, material_finish, upper_material, sole_material, lining_material, outer_material, insole_material,
style, silhouette, fit, season, gender_target,
closure_type, sole_type, sole_construction, heel_width, heel_counter, toe_shape, stitch_type, shoe_height,
collar, neckline, sleeve, hood, pockets, lining_material,
clothing_type, shoe_type, bag_type, accessory_type, bag_size,
frame, technologies, width,
size, color
```

`listTitles` is populated from values inspector found in `apps/<project>/src/data/products/*.ts` mock arrays.

### Anti-whitelist — NEVER convert to list

- Numeric fields (`real`, `integer`): `price`, `weight`, `height`, `width_cm`, `heel_height`, `sole_thickness`, `shaft_volume`, `rating`, `rating_count`.
- Unique-by-nature: `title`, `sku`, `slug`, `id`, `cover`, `gallery`, `image_url`.
- Free-text: `description`, `short_description`, `notes`, `care_instructions`, `disclaimer`.
- Date / time fields.
- JSON / image / file fields.

## ✓ Allowed `forProducts_<segment>.schema` fields (template)

> ⚠ **Fashion / e-commerce vertical template.** The schema templates below (Common core + Clothing-specific + Shoes-specific + Bags-specific + Accessories-specific) are concrete templates for a **fashion retail vertical**. The currency `listTitles` (`USD/EUR/GBP`) and tag `listTitles` (`NEW/FEATURED/BESTSELLER/FLAGSHIP/LIMITED/SALE`) reflect typical fashion-shop vocabulary. For other verticals, **replace the templates entirely** while keeping the structural rules (`type` choice, `rules`/`additionalFields` discipline, segment-per-category split):
>
> - **Hotel CMS** → `forRooms_<segment>` per room category (Standard / Suite / Villa): `bed_count`, `area_sqm`, `view_type`, `amenities_included`, `max_occupancy`, `floor`, `bed_type`.
> - **Restaurant CMS** → `forMenu_<segment>` (Starters / Mains / Desserts / Drinks): `cuisine`, `dietary` (vegan/vegetarian/halal), `allergens`, `spiciness`, `calories`, `cooking_time`.
> - **LMS** → `forCourses_<segment>` (Frontend / Backend / Design / Data): `difficulty_level`, `language`, `duration_hours`, `instructor_id`, `certification`, `prerequisites`.
> - **Real-estate** → `forListings_<segment>` (Sale / Rent / Commercial): `property_type`, `bedrooms`, `bathrooms`, `square_meters`, `year_built`, `heating`, `parking`.
>
> The Common core block is most reusable across verticals: `title` / `sku`-equivalent (`id` / `slug` / `code`) / `price` (where applicable) / `cover` / `gallery` / `description` are universal. **Always-emit-as-list** semantics from the prior whitelist applies the same way.

Each segment (clothing / shoes / bags / accessories) shares a **common core** + adds segment-specific physical traits:

### Common core (all segments)
```yaml
title:         { type: string,        rules: { minLength: 1, maxLength: 200 } }
sku:           { type: string,        rules: { minLength: 1, maxLength: 50 } }
brand:         { type: list,          listTitles: { en_US: {} } }   # populated from data
brand_country: { type: list,          listTitles: { en_US: {} } }
price:         { type: real,          rules: { minValue: 0 } }
currency:      { type: list,          listTitles: { en_US: { USD: 'USD', EUR: 'EUR', GBP: 'GBP' } } }
cover:         { type: image }
gallery:       { type: groupOfImages }
description:   { type: text }
tags:          { type: list,          listTitles: { en_US: { NEW: 'New', FEATURED: 'Featured', BESTSELLER: 'Bestseller', FLAGSHIP: 'Flagship', LIMITED: 'Limited', SALE: 'Sale' } } }
colors:        { type: list,          listTitles: { en_US: {} } }   # hex or named
sizes:         { type: list,          listTitles: { en_US: {} } }   # XS/S/M/L/XL or 38/39/40
material:      { type: list,          listTitles: { en_US: {} } }
style:         { type: list,          listTitles: { en_US: {} } }
season:        { type: list,          listTitles: { en_US: { spring: 'Spring', summer: 'Summer', autumn: 'Autumn', winter: 'Winter', all_season: 'All-season' } } }
```

### Clothing-specific
```yaml
clothing_type:    { type: list }
fit:              { type: list }
silhouette:       { type: list }
collar:           { type: list }
neckline:         { type: list }
sleeve:           { type: list }
hood:             { type: list }
pockets:          { type: list }
lining_material:  { type: list }
material_origin:  { type: list }
material_finish:  { type: list }
product_details:  { type: text }   # free-form, do NOT promote to list
specs:            { type: text }
```

### Shoes-specific
```yaml
shoe_type:           { type: list }
upper_material:      { type: list }
sole_material:       { type: list }
sole_type:           { type: list }
sole_construction:   { type: list }
sole_thickness:      { type: real }
insole_material:     { type: list }
closure_type:        { type: list }
heel_height:         { type: real }
heel_width:          { type: list }
heel_counter:        { type: list }
shoe_height:         { type: list }
shaft_volume:        { type: real }
toe_shape:           { type: list }
stitch_type:         { type: list }
width:               { type: list }
technologies:        { type: list }
```

### Bags-specific
```yaml
bag_type:        { type: list }
bag_size:        { type: list }
strap_width:     { type: real }
frame:           { type: list }
closure_type:    { type: list }
upper_material:  { type: list }
lining_material: { type: list }
```

### Accessories-specific
```yaml
accessory_type:   { type: list }
outer_material:   { type: list }
material:         { type: list }
gender_target:    { type: list,  listTitles: { en_US: { female: 'Female', male: 'Male', unisex: 'Unisex' } } }
```

## Attribute sets per segment — multi-product pattern

OneEntry whitelist allows multiple `forProducts_<segment>` sets when segments have meaningfully different physical traits. Mapper creates one set per segment found by inspector:

- `forProducts_clothing` (type_id=5)
- `forProducts_shoes` (type_id=5)
- `forProducts_bags` (type_id=5)
- `forProducts_accessories` (type_id=5)

Each product row references the appropriate `attribute_set_id` based on its category page. Do NOT collapse into one mega-set with all 80+ fields — that breaks UI usability.

## `product_statuses` setup (single source of truth for stock)

Preseeded standard set (mapper emits these always):

```yaml
product_statuses:
  - { identifier: in_stock,      is_default: true,  localize_infos: { en_US: { title: 'In stock' } } }
  - { identifier: out_of_stock,  is_default: false, localize_infos: { en_US: { title: 'Out of stock' } } }
  - { identifier: preorder,      is_default: false, localize_infos: { en_US: { title: 'Pre-order' } } }
  - { identifier: coming_soon,   is_default: false, localize_infos: { en_US: { title: 'Coming soon' } } }
  - { identifier: sold_out,      is_default: false, localize_infos: { en_US: { title: 'Sold out' } } }
  - { identifier: discontinued,  is_default: false, localize_infos: { en_US: { title: 'Discontinued' } } }
  - { identifier: draft,         is_default: false, localize_infos: { en_US: { title: 'Draft' } } }
  - { identifier: archived,      is_default: false, localize_infos: { en_US: { title: 'Archived' } } }
```

Each `products[]` row in blueprint sets `status_id: '@ps.in_stock'` by default. Admin can change individual products to other statuses via UI.

If inspector found a `stock_status: 'out_of_stock'` value on a specific product → mapper sets that product's `status_id: '@ps.out_of_stock'` (NOT an attribute).

## End-to-end checklist for mapper

For each `forProducts_<segment>.schema`:

1. ✅ Apply REPEATED_VALUES_AS_LIST → convert dictionary-like strings to list + listTitles.
2. ✅ Filter FORBIDDEN_PRODUCT_FIELDS → strip discount / status / individual marker fields.
3. ✅ Consolidate marketing flags → single `tags: list`.
4. ✅ Verify all `list`-type attributes have `listTitles` populated from mock data (empty `listTitles: { en_US: {} }` is allowed only for fields in the must-have list-whitelist when no values found in mock data; admin fills in UI).
5. ✅ Emit `post_import_discounts[]` task list from `inspector.discount_signals[]` (see `discounts-setup.md`).
6. ✅ Emit standard `product_statuses[]` (8 rows above) into `blueprint.tables.product_statuses`.

## Cross-references

- `agents_datasets/rules/discounts-setup.md` — Discounts module setup (post-import REST).
- `agents_datasets/rules/users-architecture.md` — analogous NARROW principle for forUsers.
- `agents_datasets/rules/oneentry-invariants.md` §15 — product_statuses preseeded rules.
- `agents_datasets/agents/entity-mapper.md` Step 3.2 (REPEATED_VALUES_AS_LIST) and Step 3.3 (FORBIDDEN_PRODUCT_FIELDS filter).
- `agents_datasets/agents/code-inspector.md` Step 5.8 (discount_signals detection) and Step 5.9 (repeated-values extraction for listTitles).
