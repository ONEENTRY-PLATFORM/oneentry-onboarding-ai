# general_types — correct values for general_type_id

> **⚠ Universality note.** Examples below frequently use fashion-shop terms (clothing / shoes / bags / women / men) because that is the reference test project. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop (`product/sku/brand/category`), restaurant (`menu-item/dish/cuisine/section`), beauty salon (`service/master/treatment/duration`), hotel (`room/suite/amenity`), EdTech (`course/lesson/level`), corporate site (`page/department/team`), personal cabinet (`section/setting/subscription`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is hand-written.** Contains the critical rule for choosing `general_type_id`. Not edited by the autogenerator.

## Source of truth

The reference list of types is the series of seeds and the `GeneralType` enum in the CMS repository. If you are in a target project (without access to cms code) — **this file is your source of truth** + `agents_datasets/rules/dynamic-ids.md`. If there is a mismatch with a real OneEntry Platform instance — it's a bug in the rule, not a reason to dig into cms.

## Real values (as of 2026-05-31 on a fresh `develop` DB)

⚠ **Stability** column:
- **STABLE** — the id is fixed by an init migration, identical on any OneEntry Platform instance.
- **DYNAMIC** — id is assigned via `INSERT ... RETURNING id`, **may differ** across instances (depends on seed application order). NEVER hardcode these ids in a blueprint directly. See `agents_datasets/rules/dynamic-ids.md`.

| id | type | Stability | Where to use |
|---|---|---|---|
| 1 | `product` | STABLE | products (`products` table — usually auto via product status) |
| 3 | `error_page` | STABLE | special error page (404, 500) |
| **4** | **`catalog_page`** | STABLE | **ONLY** product catalog pages (women-clothing, men-shoes, sale, new-arrivals, etc.) |
| 5 | `product_preview` | STABLE | product preview page |
| 8 | `similar_products_block` | STABLE (seeded in init-db) | similar products blocks |
| 10 | `product_block` | STABLE | blocks bound to products (recommendations, related) |
| 11 | `form` | STABLE | forms (`forms` table) |
| **17** | **`common_page`** | STABLE | **regular pages** (info, root, account, cart, checkout, stores, favorites — EVERYTHING that's not a product catalog) |
| 18 | `common_block` | STABLE | regular content blocks (Hero WITHOUT a slider, Banner, FAQ, CategoryGrid) |
| 20 | `service` | STABLE | service entity |
| 21 | `order` | STABLE | `orders_storage` — order system |
| 22 | `external_page` | STABLE | external pages (rare) |
| 23 | `discount` | STABLE | discounts (outside whitelist for blueprint) |
| 24 | `frequently_ordered_block` | ⚠ **DYNAMIC** | "Bought with this item" (joint purchase analysis) |
| 25 | `slider_block` | ⚠ **DYNAMIC** | hero carousel / slider (any blocks with slide changes) |
| 26 | `trending_block` | ⚠ **DYNAMIC** | "Trending now" — tops by events (refresh ~15 min) |
| 27 | `recently_viewed_block` | ⚠ **DYNAMIC** | "Recently viewed" — `product_view` events of user/guest |
| 28 | `repeat_purchase_block` | ⚠ **DYNAMIC** | "Buy again" — `user_purchase_history`, **JWT required** |
| 29 | `personal_recommendations_block` | ⚠ **DYNAMIC** | "You'll like it" — `user_recommendations` (persona-based, fallback to trending) |
| 30 | `cart_complement_block` | ⚠ **DYNAMIC** | "Complete the cart" — co-orders by cart items |
| 31 | `cart_similar_block` | ⚠ **DYNAMIC** | "Similar to items in cart" |
| 32 | `wishlist_similar_block` | ⚠ **DYNAMIC** | "Similar to wishlist" |

⚠ The numbers 24-32 in the "id" column are a **snapshot** of a fresh `develop` DB as of 2026-05-31. On any other instance the order may be different. The mapper places a **marker** (the string name of the type), and the builder resolves it into a real id via the target DB. Full strategy — `agents_datasets/rules/dynamic-ids.md`.

A detailed reference of all 12 block types with their `customSettings` — `agents_datasets/rules/block-types.md`.

## Typical mistake: setting `4` on every page

**DON'T do this:**
```yaml
pages:
  - { identifier: 'root',     general_type_id: 4 }   # WRONG! root is common_page
  - { identifier: 'account',  general_type_id: 4 }   # WRONG!
  - { identifier: 'cart',     general_type_id: 4 }   # WRONG!
  - { identifier: 'checkout', general_type_id: 4 }   # WRONG!
  - { identifier: 'about-us', general_type_id: 4 }   # WRONG!
```

In the OneEntry admin panel these pages will appear **in the "Product catalogs" section** instead of "Content pages". The admin will be surprised.

## Correct mapping for pages

```yaml
pages:
  # Content / utility pages -> common_page (17)
  - { identifier: 'root',                  general_type_id: 17 }   # home
  - { identifier: 'cart',                  general_type_id: 17 }
  - { identifier: 'checkout',              general_type_id: 17 }   # hub
  - { identifier: 'checkout-delivery',     general_type_id: 17 }
  - { identifier: 'checkout-payment',      general_type_id: 17 }
  - { identifier: 'checkout-confirmation', general_type_id: 17 }
  - { identifier: 'account',               general_type_id: 17 }
  - { identifier: 'favorites',             general_type_id: 17 }
  - { identifier: 'stores',                general_type_id: 17 }
  - { identifier: 'info',                  general_type_id: 17 }   # info hub
  - { identifier: 'about-us',              general_type_id: 17 }
  - { identifier: 'contact',               general_type_id: 17 }
  # ... all info pages -> 17
  - { identifier: 'women',                 general_type_id: 17 }   # category hub — NAVIGATIONAL common_page, not a catalog
  - { identifier: 'men',                   general_type_id: 17 }

  # Product catalogs -> catalog_page (4)
  - { identifier: 'women-clothing',     general_type_id: 4 }
  - { identifier: 'women-shoes',        general_type_id: 4 }
  - { identifier: 'women-bags',         general_type_id: 4 }
  - { identifier: 'women-accessories',  general_type_id: 4 }
  - { identifier: 'men-clothing',       general_type_id: 4 }
  - { identifier: 'men-shoes',          general_type_id: 4 }
  - { identifier: 'men-bags',           general_type_id: 4 }
  - { identifier: 'men-accessories',    general_type_id: 4 }
  - { identifier: 'sale',               general_type_id: 4 }   # sale catalog
  - { identifier: 'new',                general_type_id: 4 }   # new arrivals catalog
```

**Heuristic:** if the page **displays a product list** (in the project's real route) -> `4` (catalog_page). Otherwise -> `17` (common_page).

Indicators of a catalog_page in code:
- File `<X>CatalogPage.tsx`, `<X>Catalog.tsx`
- Uses `productsApi`, `useGetProductsQuery`, `<ProductCard>`, `<CatalogGrid>`
- Imports `homepageProducts.ts` / `women-clothing.ts` / etc.

Indicators of a common_page:
- File `*Page.tsx` without product logic (CartPage, AccountPage, FavoritesPage)
- Info page (rendered via `[...slug]` with infoPages.ts)
- Hub pages (women, men, info — navigational, without their own content)

## Correct mapping for blocks

⚠ Base rule: place STABLE ids directly, place DYNAMIC ones via `general_type_marker` + fallback id. Full algorithm — `dynamic-ids.md`, classification by semantics — `block-types.md`.

```yaml
blocks:
  # Regular static blocks -> common_block (18) — STABLE
  - { identifier: 'category_section', kind: static_content,   general_type_id: 18 }
  - { identifier: 'discount_banner',  kind: static_content,   general_type_id: 18 }
  - { identifier: 'promo_block',      kind: static_content,   general_type_id: 18 }
  - { identifier: 'faq',              kind: faq,              general_type_id: 18 }
  - { identifier: 'store_locations',  kind: static_content,   general_type_id: 18 }
  - { identifier: 'product_reviews',  kind: reviews,          general_type_id: 18 }

  # Hero/slider -> slider_block (DYNAMIC, via marker)
  - { identifier: 'hero',             kind: carousel,         general_type_marker: 'slider_block',          general_type_id: 18 }

  # Showcases of a fixed product set -> product_block (10) — STABLE
  - { identifier: 'men_collection',   kind: products_collection, general_type_id: 10 }
  - { identifier: 'women_collection', kind: products_collection, general_type_id: 10 }
  - { identifier: 'best_sellers',     kind: products_collection, general_type_id: 10 }

  # Trending/new -> trending_block (DYNAMIC, via marker)
  - { identifier: 'new_arrivals',     kind: trending,         general_type_marker: 'trending_block',        general_type_id: 10 }
  - { identifier: 'trend_blocks',     kind: trending,         general_type_marker: 'trending_block',        general_type_id: 10 }

  # Similar/related -> similar_products_block (STABLE id 8) or DYNAMIC marker
  - { identifier: 'related_products', kind: similar,          general_type_id: 8 }
  - { identifier: 'similar_products', kind: similar,          general_type_id: 8 }

  # Cross-sell/complete the look -> cart_complement_block (DYNAMIC)
  - { identifier: 'special_offers',   kind: complete_the_look, general_type_marker: 'cart_complement_block', general_type_id: 10 }
  - { identifier: 'cross_sell',       kind: cross_sell,        general_type_marker: 'cart_complement_block', general_type_id: 10 }

  # Other specialized blocks (DYNAMIC, markers)
  - { identifier: 'recently_viewed',           kind: recently_viewed, general_type_marker: 'recently_viewed_block',          general_type_id: 10 }
  - { identifier: 'repeat_purchase',           kind: repeat_purchase, general_type_marker: 'repeat_purchase_block',          general_type_id: 10 }
  - { identifier: 'for_you',                   kind: recommendations, general_type_marker: 'personal_recommendations_block', general_type_id: 10 }
  - { identifier: 'frequently_bought_together', kind: bought_together, general_type_marker: 'frequently_ordered_block',     general_type_id: 10 }
  - { identifier: 'wishlist_similar',          kind: wishlist_similar, general_type_marker: 'wishlist_similar_block',        general_type_id: 10 }
```

⚠ `kind` — required field, set by the inspector (see `code-inspector.md` Step N — block classification). The mapper uses `kind` to choose the marker (`entity-mapper.md` Step 9.2). When the target DB is available, the builder replaces the marker with the real id (`blueprint-builder.md` resolution step). Validator S46 raises a WARNING if a block has no `kind`.

## Correct mapping for forms and orders_storage

```yaml
forms:
  - { identifier: 'signin', type: 'sing_in_up', general_type_id: 11 }   # 11 = form
  - { identifier: 'profile_my_data', type: 'data', general_type_id: 11 }
  - { identifier: 'review', type: 'rating', general_type_id: 11 }       # type=rating for reviews!

orders_storage:
  - { identifier: 'default', general_type_id: 21 }   # 21 = order
```

## Rule for the validator

S41 (new check): for each `page`/`block`/`form`/`orders_storage` — verify that `general_type_id` matches the correct semantics (see the table above). If unsuitable — WARNING.

```python
ALLOWED_GENERAL_TYPES = {1, 3, 4, 5, 8, 10, 11, 17, 18, 20, 21, 22, 23, 24, 25, 26, 27, 28, 29, 30, 31, 32}
# 1=Product, 3=ErrorPage, 4=CatalogPage, 5=ProductPreview, 8=SimilarProductsBlock,
# 10=ProductBlock, 11=Form, 17=CommonPage, 18=CommonBlock, 20=Service, 21=Order,
# 22=ExternalPage, 23=Discount, 24=FrequentlyOrderedBlock, 25=SliderBlock,
# 26=TrendingBlock, 27=RecentlyViewedBlock, 28=RepeatPurchaseBlock,
# 29=PersonalRecommendationsBlock, 30=CartComplementBlock, 31=CartSimilarBlock,
# 32=WishlistSimilarBlock (all verified against the `GeneralType` enum).

# Rough rules
PAGE_TYPE_HEURISTIC = {
    'catalog_keywords': {'clothing', 'shoes', 'bags', 'accessories', 'sale', 'new', 'catalog'},
    'common_keywords': {'cart', 'checkout', 'account', 'favorites', 'info', 'about', 'faq', 'terms', 'privacy', 'contact', 'help', 'sitemap', 'root', 'home', 'stores', 'careers'},
}

for p in tables.get('pages', []):
    gtid = p.get('general_type_id')
    if gtid not in ALLOWED_GENERAL_TYPES:
        errors.append(f"S41 page {p.get('id')} general_type_id={gtid} not in {ALLOWED_GENERAL_TYPES}")
        continue
    ident = p.get('identifier','').lower()
    is_catalog_like = any(k in ident for k in PAGE_TYPE_HEURISTIC['catalog_keywords'])
    is_common_like = any(k in ident for k in PAGE_TYPE_HEURISTIC['common_keywords'])
    if gtid == 4 and is_common_like and not is_catalog_like:
        warnings.append(f"S41 page {p.get('id')} has general_type_id=4 (catalog_page), but identifier suggests common_page (17)")
    if gtid == 17 and is_catalog_like and not is_common_like:
        warnings.append(f"S41 page {p.get('id')} has general_type_id=17 (common_page), but identifier suggests catalog_page (4)")
```
