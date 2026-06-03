# Block bindings — universal rules for `block_pages_mn` / `block_products_mn` / `product_blocks_mn`

> **⚠ Universality note.** Applies to ANY project vertical: e-commerce, restaurant, salon, hotel, EdTech, corporate, personal cabinet, SaaS. The discovery algorithm is source-driven and vertical-agnostic — substitute domain vocabulary where convenient.
>
> **⚠ Stack-specific globs.** The file globs and import-graph parser below assume a **React / Next.js** project (extension `.tsx`/`.jsx`; ES `import` syntax; component basename = file stem in PascalCase). For other stacks the discovery is conceptually identical but uses different conventions:
> - **Vue** → `*.vue` SFCs; component basename = `<file_stem>` (with PascalCase); imports parsed from `<script>` block (ES or `defineComponent`).
> - **Angular** → `*.component.ts` paired with `*.component.html`; component name = `@Component({ selector: ... })`; imports declared in `@NgModule.imports[]` / standalone component metadata.
> - **Svelte** → `*.svelte`; imports parsed from `<script>` block.
> - **Astro / SolidJS** → `*.astro` / `*.tsx` with framework-specific import patterns.
>
> The algorithm (index → import graph → BFS depth 4 → page role detection) is universal; replace the file extension and import parser per stack. **All block / page identifiers in this file remain stack-independent — they are OneEntry-side names.**

## What this is

`block_pages_mn` is the OneEntry junction table that says **"render block X on page Y"**. Without bindings the admin cannot show blocks on storefront pages and the storefront API returns empty block lists per page.

Mapper agents historically emitted only direct (depth-0) imports — that misses every block reached through wrapper components (`CatalogTemplate.tsx`, `AccessoriesCatalog.tsx`, `ProductDetailPage.tsx`), causing complaints like _"блоков на категории нет"_.

## Source-driven discovery (canonical algorithm)

`post-mapper-fixer.py::fill_block_pages_mn_from_source(data, project_root)` runs this automatically. **Mapper agents do NOT need to emit `block_pages_mn` manually** — emit `blocks[]` only, the fixer derives the bindings.

Algorithm:

1. **Index components.** Walk `<project_root>/src/app/components/**/*.tsx` (and `src/components/`, `app/components/`). Key = file stem (PascalCase) → file path.

2. **Build import graph.** For each component file, parse `import … from '<path>'` statements. The last path segment, if PascalCase and present in the component index, becomes a child node. Result: `{ParentComponent: {ChildA, ChildB, …}}`.

3. **Resolve block → component.** For each `blocks[].identifier` (snake_case), compute the PascalCase counterpart (`hero_slider` → `HeroSlider`). If `<Pascal>.tsx` exists in the component index, this block is _scannable_.

4. **Page → reachable components (BFS depth 4).** For every page file (`src/app/pages/*Page.tsx`, `src/pages/*.tsx`, `src/app/**/page.tsx`), collect direct imports and expand via the import graph to depth 4. Subtract a fixed `SKIP` set (Header, Footer, ProductCard, ImageWithFallback, etc. — global chrome / leaf utilities).

5. **Page identifier derivation — ROLE-BASED, not name-based.** Page filenames are project-specific (`HomePage.tsx` in one project, `index.tsx` / `app/page.tsx` in another, `RootScreen.tsx` in a third). Mapper agents MUST detect the **role** of each page, then derive the identifier from how the page is registered in the mapper's `pages[]` array — NOT from the React filename.

   ### Universal role detection rules
   
   For each page file, classify by **structural signals** (route + content + metadata), then look up the role's canonical identifier in `mapped.yaml::pages[]`:
   
   | Role | Structural signals (any one is sufficient) | Mapped identifier (project-defined) |
   |---|---|---|
   | **root / landing** | Next.js `src/app/page.tsx` or `pages/index.tsx`; CRA `App.tsx`'s default route `/`; file named `Home*` / `Landing*` / `Root*` / `Index*`; only page whose route segment is `''` or `/` | usually `'root'` (OneEntry convention) |
   | **catalog hub** | Imports a `CatalogTemplate` / `ProductList` / `CategoryGrid` wrapper; route ends with category slug without `[…]` dynamic segment; rendered for ALL items of a category | identifier of the parent category page (e.g. `'women'`, `'men'`, `'pizzas'`, `'rooms'`) |
   | **catalog leaf** | Same wrappers as hub but route has 2 segments (`/women/shoes`, `/menu/desserts`); typically combines hub-id + leaf-id with separator `-` | derived: `<hub>-<leaf>` (`women-shoes`, `menu-desserts`) — but mapper must check what's actually in `pages[]` |
   | **dynamic detail** | Route uses `[slug]` / `[id]` / `:id`; file imports a single-entity fetcher (`getProductById`, `getCourseBySlug`) | NOT a static page — bind via "ProductDetailPage special-case" (Step 6) |
   | **utility** | Login screens, downloads, redirects, file uploaders; usually no content blocks | skip (don't bind blocks) |
   | **error** | `not-found.tsx`, `error.tsx`, `app/[…catchAll]/page.tsx`, file named `NotFound*` / `Error*` / `404*` / `500*` | OneEntry convention: `'404'`, `'500'`, `'offline'` (matches HTTP codes) |
   | **info / static content** | Reads from a CMS-like data file (`infoPages.ts`, `policies.ts`) with one render template per slug | identifier per item in the data file (`'about-us'`, `'faq'`, `'privacy'`) |
   
   ### How mapper picks the right identifier
   
   ```
   for each <Page>.tsx in src/app/pages/ (or framework equivalent):
     1. detect role via signals above
     2. if utility/error/etc → skip block binding
     3. otherwise: look up the matching page in `mapped.yaml::pages[]`
        - by route URL → match `page.page_url`
        - by parent + slug → match parent_id + page_url
        - by component → if a page registers `source_component: <X>Page.tsx`
     4. emit binding using THAT page's identifier
   ```
   
   ### Filename fallback (only when role detection inconclusive)
   
   If role detection fails AND `mapped.yaml::pages[]` does not register the source file, fallback to kebab-case of the PascalCase basename minus `Page` suffix: `WomenShoesPage → women-shoes`, `DishMenuPage → dish-menu`, `RoomCategoriesPage → room-categories`. Emit a warning so the maintainer can verify.
   
   ### Reference example table (PROJECT-SPECIFIC — for new-shop-nextjs only)
   
   The aliases below worked for `apps/new-shop-nextjs` because mapper there registered the corresponding pages with these identifiers. For ANY OTHER project, the role detector picks an identifier from that project's `pages[]` — these aliases must not be hardcoded into the mapper logic.
   
   ```
   HomePage         → root              (role: landing)
   WomenCatalogPage → women             (role: catalog hub — Women)
   MenCatalogPage   → men               (role: catalog hub — Men)
   NewArrivalsPage  → new               (role: catalog hub — New Arrivals)
   SalePage         → sale              (role: catalog hub — Sale)
   CartPage         → cart              (role: e-commerce cart)
   FavoritesPage    → favorites         (role: wishlist)
   AccountPage      → account           (role: user account)
   StoreLocationsPage → stores          (role: integration collection)
   NotFoundPage     → 404               (role: error)
   ConfirmationPage → checkout-confirmation  (role: checkout step)
   DeliveryPage     → checkout-delivery
   PaymentPage      → checkout-payment
   ProductDetailPage → (special — Step 6)
   FilterSystemDownloadPage → (utility — skip)
   InfoPage         → (dynamic hub — skip)
   <Other>Page      → kebab-case fallback
   ```

6. **ProductDetailPage special-case.** Dynamic routes don't correspond to a single page identifier. Components reachable from `ProductDetailPage` (recommendations, reviews, recently-viewed, similar-products) bind to **every catalog leaf** (`pages` where `general_type_id ∈ {4 catalog_page, 17 common_page}` and `identifier != root`). Same set of blocks renders for every product detail view across all categories.

7. **Catalog wrappers.** Wrappers like `CatalogTemplate.tsx`, `AccessoriesCatalog.tsx`, `ShoesCatalog.tsx` get expanded automatically via the BFS — no special handling needed.

8. **Idempotence.** Existing `block_pages_mn` rows (deduplicated by `(block, page)` tuple) are preserved.

## What mapper agents MUST emit

- `blocks[]` with `identifier` matching the React component file name (snake_case): `HeroSlider.tsx` → `'hero_slider'`, `CatalogCrossSell.tsx` → `'catalog_cross_sell'`.
- `pages[]` with **canonical identifiers derived from the project's route/page hierarchy** (see `agents/code-inspector.md` "Route hierarchy → page tree" — every file-system route becomes a page; identifier = slugified segments joined by `-`). The alias table in the previous section is illustrative for one specific test project; for ANY other project the role detector picks identifiers from that project's actual `pages[]` — never hardcode them into the mapper logic.
- **Skip** `block_pages_mn` entirely. The fixer handles it.

## What mapper agents MUST NOT do

- Don't emit hand-crafted `block_pages_mn` rows that bypass the source-scan — they'll be silently merged but inconsistent with the codebase.
- Don't rename block identifiers away from the React component basename — the scan will lose the link.
- Don't emit catalog wrapper components (`CatalogTemplate`, `AccessoriesCatalog`) as blocks — they're page-level containers, not OneEntry blocks. Only the leaf blocks they render (trend_blocks, cross_sell, special_offers, etc.) should appear in `blocks[]`.

## Skip-list (global chrome / non-block components)

Components that are present in `src/app/components/` but should NEVER be treated as blocks:

```
Header / HeaderMegaMenu / HeaderMobileDrawer / MiniCart / Footer
CheckoutStepper / LoginModal / Providers / ErrorBoundary
ProductCard / ProductCardSkeleton / ColorSwatch / ImageWithFallback
MobileFilterPanel / MobileFilterBody / CatalogMobileSort / CatalogListProductCard
FormField / SizeDropdown / QtyControl / RadioCard / NoFilterResults
JsonLd / HomeScrollNotify
```

These appear in nearly every page; they are layout/utility, not content blocks.

## Validator coverage

`scripts/validate-blueprint.py` includes:
- **CHK-024** (was: products w/o page binding) — `products_pages_mn` non-empty.
- *(planned)* CHK-026 — for every visible block with a `forBlocks_*` schema, expect ≥1 row in `block_pages_mn` (warn-level: blocks that exist but nowhere render).

## Example output

For `apps/new-shop-nextjs` (Next.js fashion catalog), the depth-4 scan derives:

```
@block.hero_slider            → @page.root
@block.category_section       → @page.root
@block.women_collection       → @page.root
@block.men_collection         → @page.root
@block.new_arrivals           → @page.root
@block.promo_block            → @page.root
@block.discount_banner        → @page.root
@block.catalog_trend_blocks   → @page.women, @page.men, @page.women-{clothing,shoes,bags,accessories}, @page.men-{shoes,…}   (via CatalogTemplate / AccessoriesCatalog / ShoesCatalog wrappers)
@block.catalog_cross_sell     → (same 8 catalog leaves)
@block.recommendations_carousel → all catalog leaves (via ProductDetailPage special-case)
@block.product_reviews        → all catalog leaves
@block.recently_viewed        → all catalog leaves
```

Total: 20–30 bindings for a 15-block / 40-page project.

## Universality across verticals

| Vertical | Example dynamic detail page | Catalog leaves |
|---|---|---|
| E-commerce | `ProductDetailPage` | `women-clothing`, `men-shoes`, … |
| Restaurant | `DishDetailPage` | `pizza`, `pasta`, `salads`, … |
| Hotel | `RoomDetailPage` | `standard`, `suite`, `villa` |
| EdTech | `CourseDetailPage` | `beginner`, `advanced`, … |
| SaaS | `PlanDetailPage` | `pricing`, `features` |
| Salon | `ServiceDetailPage` | `haircut`, `coloring`, `manicure` |
| Corporate | `(N/A — usually no dynamic detail)` | departments, teams |

The fixer's wrapper-expansion + dynamic-page special-case work identically — the heuristic is purely structural (BFS over imports), not domain-specific.

---

# Part 2 — Block ↔ Product binding (`block_products_mn` / `product_blocks_mn`)

OneEntry has TWO product-bound block junction tables (different semantics):

| Table | Meaning | Used when |
|---|---|---|
| `block_products_mn` | "This BLOCK lists/contains these products" — used for static curated lists | A block is a hand-picked carousel: `featured_products`, `sale_block`, `editor_picks` |
| `product_blocks_mn` | "This PRODUCT shows these blocks on its detail page" — used for per-product extra content | A specific product needs extra blocks beyond the default detail page (e.g. a "warranty" block only on electronics) |

Both are out-of-band — most projects do NOT need per-product bindings (every product reuses the same set of detail-page blocks). Per-product bindings are an opt-in advanced feature.

## Default policy (recommended for ~95% of projects)

- **`block_products_mn`** — empty unless the project has a hand-curated block. Curation rule: if a block component renders a hard-coded `productIds: [N, M, …]` array (rare), then emit one row per `(block, product)` pair.
- **`product_blocks_mn`** — empty. The default product-detail page renders blocks via `ProductDetailPage → block_pages_mn[page='product-detail']` (or per the `ProductDetailPage special-case` from Part 1). Per-product overrides are advanced and require explicit project requirements.

## When mapper MUST emit `block_products_mn`

Search source for:

```ts
// Hard-coded product references inside a block component:
<FeaturedProducts productIds={[1, 5, 12]} />

const PROMO_PRODUCTS = ['wc-1', 'wc-3', 'ms-2'];   // SKUs

// Or inside a data file:
export const SALE_BLOCK_ITEMS = ['wc-1', 'mc-2', 'wb-1'];
```

If found, emit one `block_products_mn` row per `(block_identifier, product_identifier)`. Builder converts to `block_id` + `product_id` tokens.

```yaml
block_products_mn:
  - block: 'featured_products'
    product: 'wc-1'
  - block: 'featured_products'
    product: 'wc-3'
```

## When mapper MUST emit `product_blocks_mn`

Search source for:

```ts
// A specific product overrides the default detail page block list:
const PRODUCT_DETAIL_BLOCKS = {
  'wc-1': ['warranty_block', 'sizing_guide'],
  'mc-3': ['warranty_block', 'tech_specs'],
};

// Or block.entityIds reference in the block config:
{ identifier: 'warranty_block', entityIds: [{id: 'wc-1'}, {id: 'mc-3'}] }
```

If found, emit one row per `(product, block)`:

```yaml
product_blocks_mn:
  - product: 'wc-1'
    block: 'warranty_block'
```

## Anti-patterns

- ❌ Emit `block_products_mn` for every product × every catalog block. That's 120 × 6 = 720 rows for no functional benefit; the same content is reachable via `block_pages_mn`.
- ❌ Emit `product_blocks_mn` to "tag" featured products. That's a `discount` / `product_status` / `attribute marker` concern, not block binding.
- ❌ Mix the two semantics. `block_products_mn` = "block lists products", `product_blocks_mn` = "product shows blocks". Mapper picks ONE based on the source pattern.

## Validator coverage

- **CHK-021** (block aset data filled) — warns if a block has a non-empty schema but no data; flags blocks where source extraction failed.
- *(planned)* CHK-027 — for every block with `general_type_marker ∈ {featured_products, sale_block, editor_picks}` and zero `block_products_mn` rows, warn (curated block without contents).

## Universality across verticals

| Vertical | Likely curated block | Per-entity override |
|---|---|---|
| E-commerce | `featured_products`, `sale_block`, `bestsellers` | `warranty_block` per electronics product |
| Restaurant | `chef_picks`, `seasonal_specials` | `nutrition_facts` per dish |
| Hotel | `featured_rooms`, `seasonal_deals` | `room_amenities_extra` per suite |
| EdTech | `recommended_courses`, `trending_tracks` | `course_syllabus` per course |
| SaaS | `feature_highlights` | `compliance_docs` per enterprise plan |
| Salon | `master_recommendations`, `seasonal_treatments` | `aftercare_instructions` per chemical service |

The mapping rule (hard-coded product list → `block_products_mn`; per-entity override → `product_blocks_mn`) is structural; only the domain term changes.

---

# Part 3 — Decision tree (which table to populate)

When mapper encounters a block, decide which mn-table(s) to fill:

```
Block component imported in a page file?
├── Yes → block_pages_mn  (Part 1)
└── No  → skip page binding

Block component renders a hard-coded list of product IDs/SKUs?
├── Yes → block_products_mn  (Part 2 — curated content)
└── No  → skip

Specific products override their default block set?
├── Yes → product_blocks_mn  (Part 2 — per-product override)
└── No  → skip (use the default detail page block list via page binding)
```

All three are populated by `post-mapper-fixer.py::fill_block_pages_mn_from_source` (page binding only) and via mapper hand-emission (curated lists, overrides). The fixer's source scan is purely page-oriented; product bindings are mapper-only.
