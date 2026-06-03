# OneEntry blueprint usage guide — Part 2: Templates, Orders, Products, Relations

> **Part 2 of 3** of the usage guide. See `usage-guide.md` for index + §16–18; `usage-guide-schema.md` for §1–9 (attribute_sets / types / flags / validators / pages / forms / users / blocks).

## 10. Templates

At least 6 templates per project (see `templates-and-relations.md §1`):

```yaml
templates:
  - { identifier: catalog_page_default,     general_type_id: 4 }
  - { identifier: common_page_default,      general_type_id: 17 }
  - { identifier: product_default,          general_type_id: 1 }
  - { identifier: common_block_default,     general_type_id: 18 }
  - { identifier: product_block_default,    general_type_id: 10 }
  - { identifier: form_default,             general_type_id: 11 }
```

Every page/block/form must have a `template_id` for the matching default template. Without a template the admin sees "no template attached" in the editor.

### When to create additional templates

- If the project has custom templates for specific block types (e.g. `hero_slider_template`, `category_grid_template`) — create them.
- If every block uses one shared renderer — the default templates are enough.

---

## 11. Template Previews

`template_previews` — configuration of how cards/previews are rendered (proportions, alignment).

### Minimum — 2 previews

| identifier | proportions (horizontal × vertical × square) |
|---|---|
| **product_card** | 300×200 / 200×300 / 250 |
| **banner** | 1200×400 / 400×600 / 600 |

### ⚠ REQUIRED — `hero_slide` when there is a slider_block

If the blueprint has **at least one** block with `general_type_id=25` (slider_block, kind=carousel/category_tiles) — the mapper **must** create the `hero_slide` template_preview. Otherwise the slides will render at the default small proportions and the hero banner breaks.

| identifier | proportions |
|---|---|
| **hero_slide** | 1920×700 / 600×900 / 800 |

Validator **S52** flags a missing `hero_slide` when a slider_block is present.

```yaml
template_previews:
  - identifier: product_card
    proportions:
      default:
        horizontal: { height: 200, weight: 300, alignmentType: middleMiddle }
        vertical:   { height: 300, weight: 200, alignmentType: middleMiddle }
        square:     { side: 250, alignmentType: middleMiddle }
  - identifier: banner
    proportions:
      default:
        horizontal: { height: 400, weight: 1200, alignmentType: middleMiddle }
        vertical:   { height: 600, weight: 400,  alignmentType: middleMiddle }
        square:     { side: 600, alignmentType: middleMiddle }
  # Created when there is a slider_block
  - identifier: hero_slide
    proportions:
      default:
        horizontal: { height: 700, weight: 1920, alignmentType: middleMiddle }
        vertical:   { height: 900, weight: 600,  alignmentType: middleMiddle }
        square:     { side: 800, alignmentType: middleMiddle }
```

### When to create additional template_previews

- `category_tile` — if there is a category-grid with non-banner proportions
- `cart_item_thumb` — if the cart has non-standard proportions
- `product_gallery` — if there is a product detail page with a gallery

---

## 12. Orders Storage + Order Statuses

Create **only if** the project has a cart/checkout flow.

```yaml
orders_storage:
  - identifier: default
    general_type_id: 21              # order (STABLE)
    form: signin                     # FK to the signin form (or a dedicated checkout form)
    price_expiration: '10m'          # how long the captured price is held before recalculation
    localize_infos: { en_US: { title: 'Default Order Storage' } }

order_statuses:
  - { identifier: new,        is_default: true,  storage: default }
  - { identifier: processing, is_default: false, storage: default }
  - { identifier: shipped,    is_default: false, storage: default }
  - { identifier: delivered,  is_default: false, storage: default }
  - { identifier: cancelled,  is_default: false, storage: default }
  - { identifier: returned,   is_default: false, storage: default }
```

⚠ **Do not include `capture_mode`** — the `orders_storage` schema has no such field (it is commented out in the CMS entity class). Source of truth — `agents_datasets/rules/generated/table-columns.md` section `orders_storage`. If you send `capture_mode: 'manual'` — HTTP 500 "column does not exist".

---

## 13. Product Statuses

Standard 3:
```yaml
product_statuses:
  - { identifier: active,   is_default: true,  title: Active }
  - { identifier: draft,    is_default: false, title: Draft }
  - { identifier: archived, is_default: false, title: Archived }
```

Custom (`preorder`, `coming_soon`, `out_of_stock`) — add if present in the project code.

❌ Do not use them as tags/markers (validator S29). Markers are a `MarkerEntity` (`markers` table, out-of-whitelist).

---

## 14. Product Relations Templates

`product_relations_templates` is the universal mechanism for product relations in OneEntry. A relation is a rule that, given the current product, produces a list of others (variants, similar, complementary).

Full use-case reference with conditions — `agents_datasets/rules/templates-and-relations.md §4`.

### 14.1 Use cases — which relation to create when

| relation | for what | example |
|---|---|---|
| **`variants`** | different variants of one product (colors/sizes) | iPhone 17 Black + Pink + Blue (3 SKUs, shared model) |
| `similar` | similar products (same category, close price) | "Similar" / "You may also like" block |
| `cross_sell` | complementary from another category, same brand/style | "Complete the Look", "Bought together" |
| `upsell` | more expensive alternatives in the same category | "Premium options" |
| `recommended` | general recommendations with no strict logic | block without explicit semantics |

### 14.2 Variants — the most important use case

iPhone 17 Black, Pink, Blue — these are **3 separate products** in the DB, linked through `variants`. On the Black product card the UI shows Pink/Blue chips that, when clicked, lead to the corresponding SKU. Relation condition: a common attribute like `product_model`.

**Schema requirement:** `forProducts.schema` must include a `product_model` attribute (or `parent_sku` / `product_group_id`) — otherwise variants will not work.

```yaml
# in forProducts.schema
product_model:
  type: 'string'      # 'iphone-17', 'macbook-air-m3'
  position: 5
  localizeInfos: { en_US: { title: 'Product Model' } }
```

```yaml
# in product_relations_templates
- identifier: 'variants'
  name: 'Product Variants'
  is_active: true
  conditions:
    - { field: 'product_model', operator: 'eq', value: '{self.product_model}' }
    - { field: 'sku', operator: 'neq', value: '{self.sku}' }
```

### 14.3 Similar/Cross-sell/Upsell — typical conditions

```yaml
# Similar — same category + close price
- identifier: 'similar'
  conditions:
    - { field: 'category', operator: 'eq',      value: '{self.category}' }
    - { field: 'price',    operator: 'between', value: ['{self.price * 0.7}', '{self.price * 1.3}'] }
    - { field: 'sku',      operator: 'neq',     value: '{self.sku}' }

# Cross-sell — different category, same brand/style
- identifier: 'cross_sell'
  conditions:
    - { field: 'category', operator: 'neq', value: '{self.category}' }
    - { field: 'brand',    operator: 'eq',  value: '{self.brand}' }

# Upsell — same category, at least 20% more expensive
- identifier: 'upsell'
  conditions:
    - { field: 'category', operator: 'eq', value: '{self.category}' }
    - { field: 'price',    operator: 'gt', value: '{self.price * 1.2}' }

# Recommended — no logic (the admin tunes it)
- identifier: 'recommended'
  conditions: []
```

### 14.4 Mapper algorithm

| has in forProducts.schema | create relation |
|---|---|
| `product_model` or `parent_sku` or `product_group_id` | **variants** |
| `category` (or `clothing_type` / `shoe_type` / etc) | **similar** |
| `brand` (or `style` / `collection`) | **cross_sell** |
| `category` + `price` (always present for products) | **upsell** |
| none of the above | only **recommended** with conditions=[] |

If the project shows a **variant switcher in the UI** (components with names like `*ColorPicker`/`*SizePicker`/`VariantSelector`) but `forProducts.schema` has NO grouping attribute — the mapper emits a warning:
```
variants_template_skipped: variant switcher detected in code, but forProducts.schema has no
product_model/parent_sku/product_group_id attribute. Add the grouping attribute first,
then re-run the pipeline.
```

### 14.5 Operators

`eq`, `neq`, `lt`, `gt`, `lte`, `gte`, `between`, `in`, `nin`, `like`, `regex`.

`{self.X}` — a placeholder, replaced at runtime with X's value from the current product. If X is undefined — the condition is skipped.

### 14.6 After import

The `conditions` in the blueprint are **defaults**. In OneEntry Platform the admin can:
- change the operator (`eq` → `like`)
- add / remove conditions
- expand ranges (`±30%` → `±50%`)
- create new relation templates

---

## 15. Products + products_pages_mn

```yaml
products:
  - identifier: 'wc-001'
    sku: 'WC-001'
    attribute_set: forProducts
    title: 'Black T-shirt'
    fields:                  # values in the product's attributes_sets jsonb
      price: 199.99
      sku: 'WC-001'
      preview: 'https://.../wc-001.jpg'
      ...

products_pages_mn:
  - { productId: '@product.wc-001', pageId: '@page.women-clothing' }
  - { productId: '@product.wc-001', pageId: '@page.catalog' }       # global catalog
```

⚠ **`products_pages_mn` is the only mn table with camelCase columns** (`pageId`, `productId`). All other mn tables use snake_case (`page_id`, `block_id`). Validator S18.

### Limits

- If there are more than 1000 products — a stratified sample by category (up to 1000 total).
- At least 1 sample product if there are none in the code.

---

