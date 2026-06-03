# block-types — reference for OneEntry recommendation blocks

> **⚠ Universality note.** Examples below may reference fashion-shop terms (clothing / shoes / bags / women / men) — they are **illustrative**. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop, restaurant (`menu-item/dish/cuisine`), beauty salon (`service/master/treatment`), hotel (`room/suite/amenity`), EdTech (`course/lesson`), corporate site (`page/department/team`), personal cabinet (`section/setting`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is hand-written.** It maps 13 product-recommendation block types: `general_type_id` → `type` → data source → config → endpoints. Used by the builder and mapper when generating a "new arrivals" / "trending" / "bought with this" / etc. block.

## Source of truth

Hand-written, grep-verified against the OneEntry CMS implementation:
- `GeneralType` enum — the 13 recommendation types (ids 1, 8, 10, 18, 24-32) listed in the summary table below.
- `customSettings.*Config` typings — inline TypeScript schemas reproduced in §"customSettings.* — JSON schemas" below.
- `audienceFilter` — inline TypeScript schema reproduced in §"audienceFilter" below.
- Preview attribute_set generation logic for a block — summarised inline in the relevant sections below.

## Summary table

⚠ Column **Stability**: STABLE = the id is identical on any OneEntry Platform instance; **DYNAMIC** = the id depends on the instance (seed application order), **must not be hard-coded** in the blueprint — use `general_type_marker`. The id snapshot below is for a fresh `develop` DB as of 2026-05-31. The strategy is in `agents_datasets/rules/dynamic-ids.md`.

| id (snapshot) | type / marker | Stability | Purpose | Data source | customSettings |
|---|---|---|---|---|---|
| 1 | `product` | STABLE | Product card (system, not a UI block) | — | — |
| 8 | `similar_products_block` | STABLE (init-db) | Similar products | `similarProductRules` rules + `product_block_targets_mn` | `audienceFilter?` |
| 10 | `product_block` | STABLE | Storefront with a fixed product set (collection, legacy) | — | `audienceFilter?` |
| 18 | `common_block` | STABLE | Generic static content block (Hero without slider, banner, FAQ, reviews list) | `block_pages_mn` + `block_products_mn` | arbitrary |
| 24 | `frequently_ordered_block` | ⚠ **DYNAMIC** | "Bought together with this product" | `order_products` (co-purchase analysis) | `frequentlyOrderedConfig`, `audienceFilter?` |
| 25 | `slider_block` | ⚠ **DYNAMIC** | Hero carousel / any slider with rotating slides | `slides` table + link to the block (see §"Slides for slider_block" below) | no config yet |
| 26 | `trending_block` | ⚠ **DYNAMIC** | "Trending now" / "New Arrivals" | Cached tops from `product_view` + `product_purchase` (refresh ~15 min) | `trendingConfig`, `audienceFilter?` |
| 27 | `recently_viewed_block` | ⚠ **DYNAMIC** | "Recently viewed" | `product_view` events for the user/guest | `recentlyViewedConfig` |
| 28 | `repeat_purchase_block` | ⚠ **DYNAMIC** | "Buy again" (JWT required) | Materialized view `user_purchase_history` | `repeatPurchaseConfig` |
| 29 | `personal_recommendations_block` | ⚠ **DYNAMIC** | "You'll like" (persona-based) | `user_recommendations.product_ids[]` | `personalRecommendationsConfig` |
| 30 | `cart_complement_block` | ⚠ **DYNAMIC** | "Complete your cart" / "Complete the Look" / cross-sell | `findFrequentlyOrderedIds` over cart positions | `cartDrivenConfig`, `audienceFilter?` |
| 31 | `cart_similar_block` | ⚠ **DYNAMIC** | "Similar to items in cart" | `product_similarities` from cart positions | `cartDrivenConfig`, `audienceFilter?` |
| 32 | `wishlist_similar_block` | ⚠ **DYNAMIC** | "Similar to wishlist" | `product_similarities` from the wishlist | `cartDrivenConfig`, `audienceFilter?` |

> ⚠ ids 24-32 — DYNAMIC. On a fresh `develop` DB they take the numbers above, but **may differ on the customer's production**. In the blueprint **always** include both `general_type_marker: '<type>'` and a fallback `general_type_id` (10 or 18). When the target DB is available, the builder will substitute the real id for the marker. The full rules are in `agents_datasets/rules/dynamic-ids.md`.

## Content API endpoints (for the storefront)

| type | URL |
|---|---|
| `similar_products_block` | `GET /api/content/blocks/{marker}/similar-products` + the contextual `/products/{id}/similar-products` |
| `frequently_ordered_block` | `GET /api/content/blocks/{marker}/products/{id}/frequently-ordered` |
| `trending_block` | `GET /api/content/blocks/{marker}/trending` |
| `recently_viewed_block` | `GET /api/content/blocks/{marker}/recently-viewed` |
| `repeat_purchase_block` | `GET /api/content/blocks/{marker}/repeat-purchase` (JWT required) |
| `personal_recommendations_block` | `GET /api/content/blocks/{marker}/personal-recommendations` |
| `cart_complement_block` | `GET/POST /api/content/blocks/{marker}/cart-complement` |
| `cart_similar_block` | `GET/POST /api/content/blocks/{marker}/cart-similar` |
| `wishlist_similar_block` | `GET/POST /api/content/blocks/{marker}/wishlist-similar` |
| `product_block` / `common_block` | served via the standard `/api/content/blocks/{marker}/products` |

Detailed roundtrips — in `api-examples/`.

## Admin API — common

| Action | URL |
|---|---|
| List blocks | `GET /api/admin/blocks` |
| Create | `POST /api/admin/blocks` |
| Update | `PUT /api/admin/blocks/:id` |
| Preview (read-only test run) | `GET /api/admin/blocks/:id/preview` — permission `blocks.preview` |

The preview endpoint is described separately: `api-examples/13-admin-block-preview.md`.

## customSettings.* — JSON schemas

### `trendingConfig`

```ts
{
  limit?: number,          // default 12
  period?: 'day' | 'week' | 'month' | 'quarter',  // default 'week'
}
```

### `recentlyViewedConfig`

```ts
{
  limit?: number,          // default 10
}
```

### `repeatPurchaseConfig` (typed config — inline schema below)

```ts
{
  limit?: number,                                       // default 10
  minTimesPurchased?: number,                           // default 1
  sortBy?: 'lastPurchased' | 'mostFrequent',            // default 'lastPurchased'
}
```

### `personalRecommendationsConfig` (typed config — inline schema below)

```ts
{
  limit?: number,  // default 10
}
```

### `frequentlyOrderedConfig`

```ts
{
  limit?: number,
  fallbackToTrending?: boolean,
}
```

### `cartDrivenConfig` (typed config — inline schema below) — shared by `cart_complement_block` / `cart_similar_block` / `wishlist_similar_block`

```ts
{
  limit?: number,                  // default 12, clamp [1..50]
  excludeCartItems?: boolean,      // default true
  fallbackToTrending?: boolean,    // default true
}
```

### `audienceFilter` (typed config — inline schema below)

Available for all `*_block` types except `recently_viewed` / `repeat_purchase` / `personal_recommendations` (those are inherently personal). The detailed schema and operators are in `api-examples/12-audience-filter.md`.

```ts
{
  kind: 'none' | 'attribute',
  attribute?: string,    // marker of a user attribute (see user.formData[lang][n].marker)
  rules?: [{
    operator?: 'eq' | 'neq' | 'mth' | 'lth' | 'in' | 'nin' | 'exs' | 'nexs' | 'pat' | 'same',
    value: string,
    categoryPageIds: number[],  // <= 50
  }],
}
```

## Blueprint record examples

### Minimal `trending_block`

```yaml
blocks:
  - identifier: 'home_trending'
    general_type_id: 26
    type: 'trending_block'
    attribute_set_id: '@aset.forBlocks_default'
    custom_settings:
      trendingConfig: { limit: 12, period: 'week' }
```

### `cart_complement_block` with a fallback

```yaml
blocks:
  - identifier: 'cart_complement_page'
    general_type_id: 30
    type: 'cart_complement_block'
    attribute_set_id: '@aset.forBlocks_default'
    custom_settings:
      cartDrivenConfig: { limit: 12, excludeCartItems: true, fallbackToTrending: true }
```

### `trending_block` with an audience filter by gender

```yaml
blocks:
  - identifier: 'home_trending_targeted'
    general_type_id: 26
    type: 'trending_block'
    attribute_set_id: '@aset.forBlocks_default'
    custom_settings:
      trendingConfig: { limit: 12 }
      audienceFilter:
        kind: 'attribute'
        attribute: 'gender'
        rules:
          - { operator: 'eq', value: 'male',   categoryPageIds: [12, 14] }
          - { operator: 'eq', value: 'female', categoryPageIds: [22, 24] }
```

## Slides for `slider_block` (general_type 25)

A `slider_block` is meaningless without `slides[]` — the storefront renders nothing. **Slides are stored in a separate `slides` table** that is OUT of the blueprint loader whitelist. Slides must therefore be created **post-import** via REST.

### Table schema (`slides`)

DDL (verified against the OneEntry Platform):

| column | type | constraint |
|---|---|---|
| `id` | serial | PK |
| `block_id` | int | NOT NULL → `blocks(id)` ON DELETE CASCADE |
| `parent_id` | int | nullable → self-ref (nested tree, max depth 10) |
| `attribute_set_id` | int | nullable → `attributes_sets(id)` ON DELETE SET NULL |
| `attributes_sets` | jsonb | NOT NULL DEFAULT `{}` — `{lang: {attrId: value}}` |
| `is_visible` | boolean | NOT NULL DEFAULT TRUE |
| `time` | int | nullable, paired with `time_interval` |
| `time_interval` | varchar(8) | `'sec'` / `'ms'`, paired with `time` |
| `position_id` | int | nullable → `positions(id)` (lexorank) |
| `identifier` | varchar | optional natural key |

### Admin REST contract

REST contract (verified against the OneEntry Platform `admin-slides.controller`):

```http
POST   /api/admin/slides          body=CreateSlideDto
GET    /api/admin/slides?blockId=<id>
GET    /api/admin/slides/:id
PUT    /api/admin/slides/:id
DELETE /api/admin/slides/:id
PATCH  /api/admin/slides/:id/visibility
PATCH  /api/admin/slides/reorder
```

`CreateSlideDto` (DTO shape verified against the OneEntry Platform):
```ts
{
  blockId: number;                    // required
  parentId?: number | null;
  attributeSetId?: number | null;
  attributesSets?: { [lang]: { [attrId]: value } };
  isVisible?: boolean;                // default true
  time?: number | null;               // pair with timeInterval
  timeInterval?: 'sec' | 'ms' | null;
}
```

Required permission: `slides.create`.

### Mapping source data → slide payload

For a Next.js project with a `heroSlides.ts` (or `sliderSlides.ts` / `carouselSlides.ts`) file shaped as `Slide[]`, post-mapper-fixer's `_scan_slides()` parses each slide object and routes fields:

| Source field | → | OneEntry attribute identifier |
|---|---|---|
| `image` / `imageUrl` | → | `image` |
| `headline` / `title` | → | `title` |
| `subtext` / `subtitle` | → | `subtitle` |
| `eyebrow` | → | `eyebrow` (extra) |
| `cta` / `cta_label` / `button` | → | `cta_label` |
| `href` / `cta_url` / `link` | → | `cta_url` |

The corresponding `forBlocks_slider` attribute_set must include these identifiers in its `schema` so the attributes_sets jsonb values bind to defined attributes.

### Pipeline

1. **Entity-mapper** emits the `slider_block` row in `blocks[]` with `general_type_marker: 'slider_block'`, `general_type_id: 25`, and `attribute_set: 'forBlocks_slider'`. The `forBlocks_slider` schema MUST contain `image, title, subtitle, eyebrow, cta_label, cta_url` (type=`image`, `string`, `string`, `string`, `string`, `string`).
2. **post-mapper-fixer** `generate_post_import_slides(data, project_root, languages)` scans for `heroSlides.ts`-style files and writes `mapped.post_import_slides[]` — one task per parsed slide, attached to the first detected `slider_block` (typical projects have ONE hero slider).
3. **Loader** ignores `post_import_slides` (out-of-whitelist).
4. **Orchestrator** `task_post_import_slides()` GETs existing slides per block (idempotency) and POSTs missing entries.

### Anti-patterns

- ❌ Putting slide image URLs in `block.attributes_sets[lang].slide_1_image / slide_2_image / …` — slides are a separate table, not flat attributes on the block.
- ❌ Emitting one `slider_block` per slide. ONE block, multiple `slides[]` rows.
- ❌ Skipping the `forBlocks_slider` schema and binding slide attributes to `forBlocks_default`. Without a typed schema the admin slide-editor UI shows no fields.

## Anti-patterns

- ❌ Creating a block with `general_type_id` 25-31 on a DB without fresh seeds — the FK will fail.
- ❌ Setting `audienceFilter` on personal blocks (`recently_viewed`, `repeat_purchase`, `personal_recommendations`) — these are persona-blocks, the filter does not apply.
- ❌ Storing `period` in `recentlyViewedConfig` or `limit` over 50 in `cartDrivenConfig` — the clamp will strip it, but the config will look "strange" in the admin UI.
- ❌ Passing more than 50 entries in `audienceFilter.rules[].categoryPageIds` — there is `AUDIENCE_FILTER_MAX_CATEGORIES_PER_RULE = 50`.

## 🚨 PRIORITY RULE — title text dominates page context (added 2026-05-31)

⚠ This is the disambiguation rule for ALL `*_block` types in this file. **Title text wins over page context.** If a block is rendered on `/favorites` but its title says "Trending Now" — it is `trending_block` (26), NOT `wishlist_similar_block` (32). Page context alone NEVER promotes a block to `wishlist_similar` / `cart_similar` / `cart_complement` — those require explicit title confirmation.

**Required title patterns for context-only types** (if the title does NOT match — DEMOTE to `trending_block` / `similar_products_block` / `common_block`):

| type | id | Required title pattern (case-insensitive) |
|---|---|---|
| `wishlist_similar_block` | 32 | MUST contain `similar` AND (`wishlist` OR `favorites` / `favourites`). Examples: "Similar to your wishlist", "Based on your favorites". |
| `cart_similar_block` | 31 | MUST contain `similar` AND `cart`. Examples: "Similar to items in cart". |
| `cart_complement_block` | 30 | MUST match one of: "Complete the look", "Complete your cart", "Style with", "Pair with", "Outfit". |
| `trending_block` | 26 | MUST match one of: "Trending", "Popular", "Hot", "Best Sellers", "Top Sellers", "New Arrivals", "Just In", "Latest", "Newly Added", "Sale", "Clearance". Page agnostic — can live on root, catalog, favorites, account, etc. |

**Examples of correct disambiguation:**

| Page | Title | Correct type | Why |
|---|---|---|---|
| `/favorites` | "Trending Now" | `trending_block` (26) | title overrides page context — favorites_trending is a trending-driven recommendation displayed on favorites page |
| `/favorites` | "Similar to your wishlist" | `wishlist_similar_block` (32) | title confirms wishlist_similar |
| `/cart` | "Best Sellers" | `trending_block` (26) | title overrides cart context |
| `/cart` | "Similar to items in cart" | `cart_similar_block` (31) | title confirms cart_similar |
| `/cart` | "Complete the look" | `cart_complement_block` (30) | title confirms cart_complement |
| `/product/[id]` | "New Arrivals" | `trending_block` (26) | title overrides product page context |
| `/product/[id]` | "You may also like" | `similar_products_block` (8) | title confirms similar |

Enforcement: `entity-mapper.md` §9.2.2a (re-verification step), `blueprint-validator.md` S47 (post-build catch).

## See also

- `agents_datasets/rules/general-types.md` — general reference for `general_type_id`.
- `agents_datasets/rules/oneentry-invariants.md` §15 — general block rules.
- `api-examples/02-recently-viewed.md` ... `08-cart-driven-blocks.md` — content-API cases.
- `api-examples/12-audience-filter.md` — configuring the audience filter.
- `api-examples/13-admin-block-preview.md` — admin preview endpoint.
