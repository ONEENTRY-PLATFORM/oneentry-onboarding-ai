# Mapper — source-data extraction (deep mapping)

> **⚠ Universality note.** All rules below are vertical-agnostic. Fashion-shop terms (`WomenCollection`, `clothing_type`, `women-shoes`) appear ONLY as illustrative examples drawn from the reference test project `new-shop-nextjs`. The **algorithms are structural**: file glob patterns, import graph, attribute extraction loops. Substitute domain vocabulary when applying to other verticals:
>
> | Reference (fashion) example | Restaurant equivalent | Hotel equivalent | EdTech equivalent | SaaS equivalent | Salon equivalent | Corporate equivalent |
> |---|---|---|---|---|---|---|
> | `WomenCollection.tsx` | `DishCarousel.tsx` | `RoomShowcase.tsx` | `CourseHighlights.tsx` | `PlanComparison.tsx` | `ServiceShowcase.tsx` | `DepartmentList.tsx` |
> | `clothing_type` | `dish_type`, `cuisine` | `room_type` | `course_level` | `plan_tier` | `service_type` | `team_role` |
> | `womenClothingProducts.ts` | `pizzas.ts`, `dishes.ts` | `rooms.ts`, `suites.ts` | `courses.ts`, `tracks.ts` | `plans.ts` | `services.ts` | (no catalog) |
> | `women-shoes` page id | `pizza` page id | `standard-room` page id | `beginner-track` page id | `professional` plan id | `manicure` page id | `engineering` page id |
>
> The extractor does NOT know about clothing or rooms — it walks the React import graph and pulls every key from every literal in the data files it discovers. Whatever your project calls things, the same code path applies.

> **Read first** if `mapped.yaml` shows blocks/products with empty `attributes_sets[lang]` (just defaults backfilled by post-mapper-fixer). The cause is almost always shallow inspection — this file tells the mapper exactly how to go deep.

## 🚨 CORE RULE

Mapper MUST extract **all** real data from source files into `attributes_sets[lang]` BEFORE post-mapper-fixer runs. The fixer only backfills MISSING keys with type-empty defaults (`[]`, `""`, `0`); it never invents values. If the mapped value is empty, **the admin sees "Not selected" in the dropdown** — looking like a bug.

When the source has data and the mapped row is still empty, the mapper failed.

## For every BLOCK

### Step 1 — resolve component

`blocks[].identifier` (snake_case) ↔ React component file (PascalCase) discovered anywhere in the project source tree (typical locations: `src/components/`, `src/app/components/`, `app/components/`, `components/`, `src/ui/`, `lib/components/` — the discovery is path-agnostic, search recursively). Example:
- `category_section` ↔ `CategorySection.tsx`
- `hero_slider` ↔ `HeroSlider.tsx`
- `discount_banner` ↔ `DiscountBanner.tsx`
- `catalog_trend_blocks` ↔ `CatalogTrendBlocks.tsx`

If the component file doesn't exist, the block identifier is likely wrong (rename or drop).

### Step 2 — find data sources (universal discovery, no fixed paths)

Source data location is project-specific (`src/data/`, `data/`, `app/data/`, `lib/data/`, `content/`, `fixtures/`, `_data/`, root-level `.json` files — all valid). Discovery is structural, not path-based.

#### Discovery algorithm

For each block (and again later for products), recursively scan **the entire project source tree** (typically `src/`, `app/`, `lib/`, `data/`, or whatever exists), with these per-file rules:

1. **File extensions to scan**: `.ts`, `.tsx`, `.js`, `.jsx`, `.mjs`, `.cjs`, `.json`, `.yaml`, `.yml`, `.toml`, `.graphql`, `.md` (front-matter blocks). Reject `node_modules/`, `.next/`, `dist/`, `build/`, `.git/`.

2. **For each file, look for data-shaped exports**, in any of these patterns:
   - **Array of objects** with consistent keys: `export const X = [{…}, {…}, …]`, `module.exports = [{…}]`, JSON array root.
   - **Keyed dictionary** of objects: `export const X = {key1: {…}, key2: {…}}`, JSON object root with consistent value shapes.
   - **Default-exported literal**: `export default [{…}]` / `export default {…}`.
   - **Inline component data**: a `const X = […]` declared inside a `.tsx` / `.jsx` file (no separate data file).
   - **Front-matter blocks** in `.md` / `.mdx` files: YAML between `---` markers.

3. **Reject false positives**:
   - Configuration files (`.eslintrc`, `tsconfig`, `package.json`, build configs)
   - Test fixtures (path contains `__tests__`, `*.spec.*`, `*.test.*`)
   - Mock files (`__mocks__/`)
   - Library re-exports without their own data

4. **Decide if a file is a data source for a specific block**:
   - **Strong signal**: the block's component file imports a name from this file.
   - **Medium signal**: file name shares a token with the block identifier (after canonical normalization — see Step 1.5.1).
   - **Weak signal**: file exports a literal whose shape matches the block's schema fields by name.
   
   Prefer the strongest signal. Record evidence in `mapped.warnings[]` when discovery used a weak signal.

#### How to read a discovered data file

Don't rely on parsers that only handle one syntax. Use a tolerant strategy:

1. **JSON files** — parse with the standard JSON parser.
2. **YAML/TOML** — parse with the standard YAML/TOML parser.
3. **TS/JS files** — extract via balanced-bracket scanning between the first `[` or `{` after `export const X = ` / `export default` / `module.exports = `. Then strip TS-only syntax (type annotations, `as`, `satisfies`) and convert JS literals to JSON: keys → quoted strings, single quotes → double, trailing commas removed, backticks → double quotes (if no `${interpolation}`). When JSON.parse fails, fall back to a state-machine parser that walks balanced braces/brackets manually.
4. **MD front-matter** — slice between `---` markers and run YAML parser.

(post-mapper-fixer.py has `parse_data_file()` + `_extract_balanced_array()` + `_split_product_objects()` + `_parse_object_top_level()` already implementing this. Mapper agents should reuse the same approach — never assume the source is "regular ES6".)

#### Inline data, no separate file

Some projects keep data right inside the component (e.g. `const ITEMS = [...]` at the top of `Slider.tsx`). The scan should detect such literals when the imported-name discovery fails. Mark with a warning so the maintainer knows mapper inferred the data from JSX scope, not a canonical file.

### Step 3 — extract into `attributes_sets[lang]`

For each schema attribute of the block's `attribute_set`:

- **string / text / textarea**: take from `<h1>`, `<h2>`, `eyebrow`, `subtitle`, `cta_label` props/JSX text in component or data file.
- **image**: take `src` of `<Image>` / `<img>` / `imageUrl` / `image` field from data.
- **list** (chips, categories, links): take the array from data file, emit as `[{value: 'X'}, {value: 'Y'}]`.
- **groupOfImages**: take from `gallery: string[]` or array of `{src, alt}`.

---

## SLIDER blocks — dedicated extraction protocol

Slider-type blocks (`general_type_id=25 slider_block` and the derived variants `category_grid`, `trend_tiles`, `cross_sell`, etc.) carry their **content in a separate `slides` table**, not in `blocks.attributes_sets`. The block row holds only DEFAULT values for the slider's display config; each carousel item is a separate `post_import_slides[]` row.

Without this, the admin shows the block with **0 slides** and the storefront renders an empty carousel — the most common "block is broken" complaint.

### Recognition: which blocks are sliders

Recognize by ANY of:
1. `general_type_id` ∈ `{25, 26, 27, 29, 30, 31, 32}` (see `block-types.md`).
2. Component file imports a carousel library (`embla`, `swiper`, `keen-slider`, `react-slick`, `slick-carousel`).
3. Component file maps over an array prop into `<Slide>` / `<SwiperSlide>` / `<Card>` elements (visual carousel pattern).
4. Identifier contains `slider` / `carousel` / `grid` / `tiles` / `showcase` / `trending` / `featured_*`.

### Step A — locate the items array (universal patterns)

Sliders carry their content as an iterable. Mapper looks for ANY of these structural patterns in the block's component file and its discovered data sources (Step 2):

1. **In-file literal**: a top-level `const` whose value is an array of objects with consistent shape and length ≥ 2. The literal can be inside the component, in the same file, or in any file the component imports.
2. **Imported data export**: discovered via Step 2 (any path, any extension — `.ts` / `.json` / `.yaml` / inline / front-matter). Mapper uses the discovery result, not a fixed path.
3. **Runtime fetch**: `fetch('/api/…')`, `useQuery`, `useSWR`, GraphQL operation, async load. Mapper cannot resolve runtime values — emit a placeholder slide row and a `mapped.warnings[]` entry: `slider <X> uses runtime fetch — content depends on API response, mapper extracted defaults only`.

Use the patterns above structurally (not the example names below — those are illustrative). For instance, _"a top-level const that holds an array of similarly-shaped objects"_ is the structural rule; what the project calls it (`HERO_SLIDES`, `SPECIALS`, `ROOMS`, `FEATURED_COURSES`, `dishesOfDay`, `mainSlider_data`) is irrelevant — discovery sees them all the same way.

### Step B — map each item to a slide row

For each element of the items array, emit one `post_import_slides[]` row. The mapping from source item keys to slide schema fields is universal (irrespective of vertical):

| Source key (any of) | Target slide schema field | Mapped key |
|---|---|---|
| `title` / `heading` / `name` / `label` / `caption` | `title` | `string_id<N>` |
| `subtitle` / `description` / `text` / `body` | `subtitle` | `string_id<N>` |
| `eyebrow` / `kicker` / `category` / `tagline` | `eyebrow` | `string_id<N>` |
| `image` / `imageUrl` / `src` / `thumbnail` / `photo` | `image` | `image_id<N>` |
| `cta` / `ctaLabel` / `buttonText` / `linkLabel` | `cta_label` | `string_id<N>` |
| `href` / `link` / `url` / `to` / `ctaUrl` | `cta_url` | `string_id<N>` |

### Step C — inherit `attribute_set` from parent block

Each `post_import_slides[]` row MUST carry the parent block's `attribute_set` identifier. post-mapper-fixer uses it to resolve `attribute_set_id` and `<type>_id<N>` data keys.

### Full example (universal — fashion-shop concrete)

Source (illustrative — concrete path varies by project, use Step 2 discovery):
```ts
import { HERO_SLIDES } from '../data/heroSlides';
// HERO_SLIDES = [
//   { title: 'The Stylist Edit', subtitle: 'Curated looks…', eyebrow: "Women's Collection",
//     image: '/images/hero-1.jpg', cta: 'Shop the Edit', href: '/women/clothing' },
//   { title: 'New Season Men', ... },
//   { title: 'Up to 70% Off', ... },
// ]
```

Mapper output:
```yaml
blocks:
  - identifier: 'hero_slider'
    attribute_set: 'forBlocks_slider'
    general_type_id: 25
    attributes_sets:
      en_US: {}      # defaults only — content lives in slides

post_import_slides:
  - block_identifier: 'hero_slider'
    attribute_set: 'forBlocks_slider'
    is_visible: true
    attributes_sets:
      en_US:
        string_id1: 'The Stylist Edit'
        string_id3: 'Curated looks for the modern woman'
        string_id2: "Women's Collection"
        image_id4: [{filename: 'hero-1.jpg', downloadLink: '…', previewLink: {1:['…','…']}}]
        string_id5: 'Shop the Edit'
        string_id6: '/women/clothing'

  - block_identifier: 'hero_slider'
    attribute_set: 'forBlocks_slider'
    is_visible: true
    attributes_sets:
      en_US:
        string_id1: 'New Season Men'
        string_id3: "Discover the latest men's collection"
        string_id2: "Men's Collection"
        image_id4: [{filename: 'hero-2.jpg', downloadLink: '…', previewLink: {1:['…','…']}}]
        string_id5: 'Shop Now'
        string_id6: '/men/clothing'

  - block_identifier: 'hero_slider'
    attribute_set: 'forBlocks_slider'
    is_visible: true
    attributes_sets:
      en_US:
        string_id1: 'Up to 70% Off'
        string_id3: 'Final markdowns. Limited stock.'
        string_id2: 'Sale'
        image_id4: [{filename: 'hero-3.jpg', downloadLink: '…', previewLink: {1:['…','…']}}]
        string_id5: 'Shop Sale'
        string_id6: '/sale'
```

### Step D — nested slides (two universal patterns)

A slider block can render a 2-level hierarchy: top-level "tabs" / "categories" /
"sections" on top, sub-cards under each. Source code expresses this in **one of
two universal ways**. Both must be lifted into parent + child slides linked by
`parent_identifier`.

#### Pattern D1 — explicit nested array on the item

The parent item carries a `chips` / `sub_items` / `children` / `cards` /
`items` array. One real example (catalog showcase: top tabs `Women`/`Men`
each containing several sub-categories):

```ts
const CATEGORIES = [
  { title: 'Women', image: '…',
    chips: [
      { label: 'Coats', href: '/women/coats' },
      { label: 'Tops',  href: '/women/tops' },
    ] },
  { title: 'Men', image: '…',
    chips: [ … ] },
]
```

Lift to:
```yaml
post_import_slides:
  - identifier: 'cat-women'
    block_identifier: 'shop_by_category'
    attributes_sets: { en_US: { title: 'Women', image: '…' } }

  - identifier: 'cat-women-coats'
    block_identifier: 'shop_by_category'
    parent_identifier: 'cat-women'
    attributes_sets: { en_US: { title: 'Coats', cta_url: '/women/coats' } }
```

#### Pattern D2 — flat array with a "group" field on every item

A single flat array where each item carries a group key (`chip` / `tab` /
`section` / `category` / `group` / `parent` / `parent_id` / `tag`). The
group key's distinct values become the parent slides. One real example
(catalog grid with filter chips at the top, sub-cards beneath):

```ts
export const SHOP_CATEGORIES = [
  { id: 'coats',   label: 'Coats',   chip: 'Outerwear', image: '…' },
  { id: 'jackets', label: 'Jackets', chip: 'Outerwear', image: '…' },
  { id: 'shirts',  label: 'Shirts',  chip: 'Tops',      image: '…' },
  { id: 'jeans',   label: 'Jeans',   chip: 'Bottoms',   image: '…' },
  …
]
```

Lift to:
```yaml
post_import_slides:
  # parent (auto-generated from chip value, identifier = slugified chip name)
  - identifier: 'outerwear'
    block_identifier: 'shop_by_category'
    is_parent: true
    attributes_sets: { en_US: { title: 'Outerwear' } }

  # children — each inherits parent_identifier = slugified chip
  - identifier: 'coats'
    block_identifier: 'shop_by_category'
    parent_identifier: 'outerwear'
    attributes_sets: { en_US: { title: 'Coats', image: '…' } }
  - identifier: 'jackets'
    block_identifier: 'shop_by_category'
    parent_identifier: 'outerwear'
    attributes_sets: { en_US: { title: 'Jackets', image: '…' } }
```

`post-mapper-fixer.py` does the lift deterministically via
`_lift_groups_into_parents()`: it scans every item for the recognised group
field names (`_GROUP_FIELD_HINTS`), emits one parent per distinct value, and
attaches every original item to its parent via `parent_identifier`. Universal
across verticals — works for hospitality "by occasion" carousels, education
"by faculty" grids, restaurant "by season" menus, etc.

Without lifting, admin renders all items as siblings at the top level, and
the visual hierarchy (top tabs + nested cards) is lost.

### Step 3.5 — block attribute extraction (universal)

For blocks whose schema has identifier slots (`title`/`subtitle`/`eyebrow`/`image`/`href`/`cta`/…) but the LLM mapper left `attributes_sets[lang]` mostly empty, the deterministic `deep_extract_attributes_from_source` runs a 4-tier source lookup:

1. **Direct identifier** — `src_by_id[block.identifier]` (covers projects where the const name matches the block 1:1, e.g. `DISCOUNT_BANNER` ↔ block `discount_banner`).
2. **Canonicalised + plural variants** — `_canonical_key(ident)` + singular/plural toggles (e.g. block `new_arrivals` ↔ source key `newArrivals`).
3. **Token-overlap fallback** — set-intersection of underscore-split tokens (e.g. block `hero_slider` ↔ source `HERO_SLIDES`).
4. **Component → import trace** — finds the matching component file (`.tsx`/`.jsx` whose stem canonicalises to the block id), parses its `import { X } from '…data/…'` statements, and resolves each named import against `src_by_id`. This is the universal way to bridge cases like component `MenCollection` ↔ data export `SECTION_TITLES.bestSellers`.

Source indexes feeding `src_by_id` (all built per file, universally):
- `id`/`sku`/`slug`/`code`/`identifier`/`key` field on every dict row of an array export (typical for product / menu-item arrays).
- Outer key when source is `Record<key, dict>` (typical for grouped catalogs / mega menus).
- Exported const name slugified (`DISCOUNT_BANNER` → `discount_banner`) for single-object exports without an id field.
- File stem slugified (`banners.ts` → `banners`) as last-resort fallback.

All four key forms get **both** raw and canonical (`_canonical_key`) entries in the index, so downstream block lookups match regardless of source naming style (camelCase ↔ snake_case ↔ PascalCase ↔ kebab-case).

### Step 4 (legacy section heading) — emit `post_import_slides[]` for slider-type blocks

If the block component renders a carousel/slider (`HeroSlider`, `CategorySection` with chips, `TrendBlocks` with tiles), each item in the source array becomes a slide:

```yaml
post_import_slides:
  - block_identifier: 'hero_slider'
    attribute_set: 'forBlocks_slider'   # inherit from parent block aset
    is_visible: true
    attributes_sets:
      en_US:
        string_id1: 'The Stylist Edit'      # title
        string_id2: "Women's Collection"    # eyebrow
        string_id3: 'Curated looks…'        # subtitle
        image_id4:                          # image
          - filename: 'hero-1.jpg'
            downloadLink: 'https://images.unsplash.com/photo-…'
            previewLink: { 1: ['…', '…'] }
        string_id5: 'Shop the Edit'         # cta_label
        string_id6: '/women/clothing'       # cta_url
```

**Do not leave `post_import_slides` empty for static-content slider blocks** (`general_type_id=25`) — the admin shows an empty carousel and S66 / CHK-003 flag it.

## For every PRODUCT

### Step 1 — find catalog source files (universal discovery)

Catalog data files have NO fixed path or extension. Use the discovery algorithm from "Step 2 — find data sources (universal discovery, no fixed paths)" above.

**A file is a catalog source if** (any one is sufficient):
1. It exports an array literal where each element has a stable `id`/`sku`/`code`/`slug` field — clear catalog row shape.
2. It exports a keyed dictionary (`{id1: {…}, id2: {…}}`) where every value has the same shape — also catalog rows.
3. It is referenced by a catalog-list component (`ProductList`, `ItemGrid`, `MenuSection`, `RoomGrid`, or any component whose name normalizes to a catalog-listing concept) AND it satisfies (1) or (2).
4. It is a JSON / YAML / TOML file at any depth whose root is an array or keyed dict matching (1) or (2).

**Read the entire file**, not the first N items. Sampling produces incomplete blueprints.

When multiple catalog files exist (one per category — common pattern), discover all of them and merge into the products list. The category each product belongs to is inferred from:
- The source file's name (canonical-normalized), if it shares a token with a page identifier registered in `mapped.yaml::pages[]`.
- A `category` / `type` / `kind` field on the product (canonical-normalized).
- Identifier prefix (`wc-1`, `dish-pizza-7`, `room-suite-12` — first `-`-separated token), matched against page identifiers.
- Manual override emitted by the mapper into `mapped.warnings[]`.

### Step 1.5 — KEY MATCHING ALGORITHM (universal, vertical-agnostic)

This is the core algorithm — **structural, not domain-specific**. It works whether your source field is `galleryImages`, `bilderGalerie`, `imageList`, `pictures` or `medya_dosyalari`. No hardcoded synonym tables.

**Goal**: given a source-data key (e.g. `galleryImages`, `outerMaterial`, `country_of_origin`) and a schema identifier (e.g. `gallery`, `outer_material`, `brand_country`), decide if they refer to the same concept.

#### Step 1.5.1 — Canonical normalization

Apply to BOTH source key and schema identifier:

```python
def canonical(key):
    s = re.sub(r'(?<!^)(?=[A-Z])', '_', key)   # camelCase → snake_case
    s = re.sub(r'[-\s]+', '_', s)              # dashes/spaces → underscore
    s = s.lower().strip('_')                   # lowercase + trim
    s = re.sub(r'_+', '_', s)                  # collapse repeats
    return s
```

After this:
- `galleryImages`, `gallery_images`, `gallery-images`, `Gallery Images`, `GALLERY_IMAGES` → all become `gallery_images`
- `outerMaterial`, `outer-material`, `Outer Material` → `outer_material`
- `countryOfOrigin`, `country_of_origin`, `Country of Origin` → `country_of_origin`

#### Step 1.5.2 — Token set comparison

Split into word tokens; compare as sets with these rules (apply in order, first match wins):

1. **Exact match** — `tokens(src) == tokens(schema)`. Done.
2. **Plural normalization** — strip trailing `s`/`es`/`ies` from each token; compare again. (`materials` → `material`, `images` → `image`, `categories` → `category`)
3. **Schema is subset of source** — every token of the schema identifier appears in the source key. (`gallery` ⊆ `gallery_images`; `material` ⊆ `outer_material` is REJECTED — see step 4 disambiguation.)
4. **Disambiguation guard**: if multiple schema identifiers are subsets of the source key (`material` and `outer_material` both subset `outer_material`), pick the LONGER schema identifier (more specific). So `outer_material` source matches schema `outer_material`, not `material`.
5. **Source is subset of schema** — every token of source appears in schema. (`country` ⊆ `brand_country`.)
6. **Single-word substring** — when both are single-token, check substring inclusion (`image` ⊂ `images` ⊂ `gallery_images`).
7. **No match** → leave source key as-is; post-mapper-fixer's data transform may drop it as orphan with a warning.

The algorithm is **purely structural**. It needs zero vertical knowledge — `dishType` ↔ `dish_type`, `medyaDosyalari` ↔ `medya_dosyalari`, `accessoryType` ↔ `accessory_type` all resolve via the same token operations.

#### Step 1.5.3 — Truly universal synonyms (the only hardcoded set)

The list below covers concepts that are **identical across every business vertical** — names that have no domain meaning. Mapper MAY use this as a synonym hint BEFORE step 1.5.2 token matching (i.e. rewrite source key to its canonical synonym, then run the token algorithm).

| Concept | Universal synonyms |
|---|---|
| identifier | `id`, `sku`, `code`, `slug`, `key`, `uid` |
| display name | `name`, `title`, `label`, `caption`, `heading` |
| description | `description`, `desc`, `details`, `body`, `content`, `text`, `about`, `info` |
| price | `price`, `cost`, `amount` |
| image (single) | `image`, `img`, `photo`, `picture`, `thumbnail`, `cover`, `preview` |
| image (multiple) | `images`, `gallery`, `photos`, `pictures`, `media` |
| href / link | `href`, `link`, `url`, `to`, `route` |

That's it. Everything else is structural — `dishType ↔ dish_type` works without anyone teaching the mapper what a dish is.

### Specs array extraction (universal pattern)

Many source data files store extra metadata in a flat `specs: [{label, value}]` array (or `attributes`, `features`, `details`, `properties`). Mapper MUST flatten these into individual schema fields where a label matches an identifier.

Example source:
```ts
{
  id: 'ma-2', name: 'Bifold Wallet', material: 'Natural Leather',
  specs: [
    { label: 'Type', value: 'Bifold Wallet' },
    { label: 'Dimensions', value: '11 × 9 × 1.5 cm' },
    { label: 'Country of Origin', value: 'Italy' },
    { label: 'Closure', value: 'Bifold' },
  ],
}
```

For each `{label, value}` pair, normalize the `label`, look up against the schema's identifier list (also normalized), and if matched — emit into `attributes_sets[lang]`. So `'Country of Origin' → 'countryoforigin' → matches schema 'brand_country' via synonym 'countryOfOrigin'` → set `list_id<N>` for brand_country.

If no schema identifier matches, mapper MAY emit the spec as a free-form `string` attribute (extending the schema with `additionalFields: { sourceFrom: 'specs.<label>' }`), but only when the schema is being grown anyway. Otherwise drop the spec with a warning.

### Reviews / nested arrays (rarely needed for product attrs)

Source arrays like `reviews: [...]` or `relatedProducts: [...]` are typically EXCLUDED from product `attributes_sets` — they have their own tables (`form_data` / `product_relations_templates`). Mapper should NOT try to flatten them into product attributes.

### Step 2 — extract ALL fields per product

For each product object in the array, **iterate every non-system key** and match it against the schema's identifier list via Step 1.5 algorithm. There is no static "source→target" table — mapping is dynamic per-project based on what the source emits and what the schema declares.

Pseudocode:

```python
for product in source_products:
    for src_key, src_value in product.items():
        if src_key in {'specs','attributes','features','properties'}:
            # see "Specs array extraction" below
            continue
        if src_key in {'reviews','relatedProducts','options'}:
            # see "Nested arrays" below
            continue
        schema_id = match_to_schema(src_key, schema_identifiers)  # Step 1.5
        if schema_id:
            mapped[product_id][schema_id] = transform_value(src_value, schema_id)
        else:
            warnings.append(f'{product_id}.{src_key} — no matching schema attribute')
```

**System keys to skip** (universal, in any project):
- `id`, `_id`, `__typename`, `version`, `createdAt`, `updatedAt`, `lastModified` — entity metadata, never product attributes
- Function references / React components / non-serialisable values

**Value transformation** is type-aware (separate from key matching) — see `attribute-shapes-reference.md` for the canonical per-type shape rules (string vs object for `text`, array of `{value}` for `list`, etc.).

### Step 3 — never invent

If a field is absent in the source product, **do not** emit it in `attributes_sets[lang]`. post-mapper-fixer backfills with empty shape (`[]`, `""`) so the admin shows "Not selected" — that is the correct visualization of "unknown for this row".

## Common failures (and how to recognise them in mapped.yaml)

| Symptom | Cause | Fix |
|---|---|---|
| Block `attributes_sets[lang]` has only the derived title and no other strings | Mapper read only the component's `<h2>` — never opened the imported data file | Follow Step 2 chain: component → imports → data files → extract |
| Slider block has 0 `post_import_slides[]` | Mapper missed the data file (`heroSlides.ts` / `categories.ts`) | Emit each array element as a slide row |
| Product list-attribute is empty for some products | Source product doesn't have the field — correct! Backfill default `[]` is shown as "Not selected" | Verify intent; if the field should be filled, extract from the right key (`materials` vs `material`, `colors` vs `availableColors`) |
| Product has `material: 'Leather'` (singular) but blueprint shows empty | Mapper extracted as `materials` (plural source key) but schema key is `material` (singular). The post-mapper-fixer `transform_attribute_data_to_admin_shape` renames identifier → schema key only if they match exactly — `materials ≠ material` → orphan dropped | Apply Step 1.5 normalization + synonym table BEFORE matching to schema identifier |
| Product has `galleryImages: [url, url]` but blueprint `gallery` field is `[]` | camelCase source key `galleryImages` doesn't match schema identifier `gallery` (exact-string compare fails) | Step 1.5 normalize: `galleryImages → galleryimages` contains `gallery` → synonym match |
| Product has `accessoryType: 'Belt'` in source but admin shows "Not selected" for Accessory Type | Same camelCase issue. mapper compared `accessoryType` ≠ `accessory_type` literally | Step 1.5 normalize both sides: `accessorytype` ↔ `accessorytype` → match |
| Product specs contain `[{label:'Country of Origin', value:'Italy'}]` but admin's Brand Country field is empty | mapper skipped `specs` array. Schema has `brand_country` identifier; spec label `'Country of Origin'` is a synonym (see synonym table); normalize → `countryoforigin` ≈ `brandcountry` via synonym | Implement "Specs array extraction" step — flatten specs into individual fields via synonym lookup |
| Admin form shows "Not selected" for some attributes but mapper says it extracted everything | These fields are GENUINELY ABSENT in the source data (not just under a different name). Backfill defaults render as "Not selected" — the correct visualization of "unknown". If the project SHOULD have these fields, add them to the source data first | Verify by searching the project tree for the field name (case-insensitive, any extension). If no match — the field is absent and admin "Not selected" is correct |
| Block edit page shows the block "as expected for its aset" but with no data | Mapper bound the wrong `attribute_set` (e.g. `forBlocks_default` instead of `forBlocks_category_grid`) — schema has 1 field instead of 6 | Verify `attribute_set` matches block kind: hero→slider, shop_by_category→category_grid, banner→banner, faq→faq, etc. See `rules/block-types.md` |

## Universality across project types

| Vertical | Catalog data file | Slider data file | Block component examples |
|---|---|---|---|
| Restaurant | `dishes.ts`, `menuSections.ts` | `featuredDishes.ts`, `chefRecommendations.ts` | `HeroBanner`, `MenuCategories`, `SpecialOffers`, `ChefsPick` |
| Hotel | `rooms.ts`, `amenities.ts` | `featuredRooms.ts`, `seasonalOffers.ts` | `RoomTypes`, `Amenities`, `SeasonalOffers`, `LocationMap` |
| EdTech | `courses.ts`, `tracks.ts` | `featuredCourses.ts`, `learningPaths.ts` | `CourseCategories`, `FeaturedTrack`, `Testimonials`, `Instructors` |
| SaaS | `plans.ts`, `features.ts` | `comparisonTable.ts`, `testimonials.ts` | `PricingTable`, `FeatureMatrix`, `Testimonials`, `CTABanner` |
| Salon | `services.ts`, `masters.ts` | `featuredServices.ts`, `gallery.ts` | `ServiceCategories`, `MasterShowcase`, `BookingCTA` |

The extraction algorithm is identical; only the file names and field names change.
