# Templates, Template Previews, Order Storages, Product Relations — required entities

> **⚠ Universality note.** Examples below frequently use fashion-shop terms (clothing / shoes / bags / women / men) because that is the reference test project. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop (`product/sku/brand/category`), restaurant (`menu-item/dish/cuisine/section`), beauty salon (`service/master/treatment/duration`), hotel (`room/suite/amenity`), EdTech (`course/lesson/level`), corporate site (`page/department/team`), personal cabinet (`section/setting/subscription`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is hand-written.** Rules for the mapper: what must be created in the blueprint in addition to pages/products/blocks.

## 1. Templates — entity rendering templates

Every entity of type `page`/`product`/`block`/`form` may have a **display template** (how it is rendered on the storefront). Without a template the admin sees "no template attached" in the editor.

### Minimum template set

```yaml
templates:
  - id: '@tpl.catalog_page_default'
    identifier: 'catalog_page_default'
    title: 'Default catalog page template'
    general_type_id: 4         # catalog_page
    attribute_set: 'forPages'
    attributes_sets: {}

  - id: '@tpl.common_page_default'
    identifier: 'common_page_default'
    title: 'Default common page template'
    general_type_id: 17        # common_page
    attribute_set: 'forPages'
    attributes_sets: {}

  - id: '@tpl.product_default'
    identifier: 'product_default'
    title: 'Default product card template'
    general_type_id: 1         # product
    attribute_set: 'forProducts'
    attributes_sets: {}

  - id: '@tpl.common_block_default'
    identifier: 'common_block_default'
    title: 'Default common block template'
    general_type_id: 18        # common_block
    attribute_set: 'forBlocks_default'
    attributes_sets: {}

  - id: '@tpl.product_block_default'
    identifier: 'product_block_default'
    title: 'Default product block template'
    general_type_id: 10        # product_block
    attribute_set: 'forBlocks_default'
    attributes_sets: {}

  - id: '@tpl.form_default'
    identifier: 'form_default'
    title: 'Default form template'
    general_type_id: 11        # form
    attribute_set: 'forForms_signin'
    attributes_sets: {}
```

**After generating pages/blocks/forms**, the mapper assigns the matching default template's `template_id`. This removes the "no template" warning in the admin UI.

## 2. Template Previews — preview settings

`template_previews` stores the configuration of how a card/preview is rendered (proportions, alignment).

```yaml
template_previews:
  - id: '@tpv.product_card'
    identifier: 'product_card'
    title: 'Product card preview'
    proportions:
      default:
        horizontal: { height: 200, weight: 300, alignmentType: 'middleMiddle' }
        vertical:   { height: 300, weight: 200, alignmentType: 'middleMiddle' }
        square:     { side: 250, alignmentType: 'middleMiddle' }

  - id: '@tpv.banner'
    identifier: 'banner'
    title: 'Banner preview'
    proportions:
      default:
        horizontal: { height: 400, weight: 1200, alignmentType: 'middleMiddle' }
        vertical:   { height: 600, weight: 400, alignmentType: 'middleMiddle' }
        square:     { side: 600, alignmentType: 'middleMiddle' }

  # ⚠ Always created by the mapper when there is at least one block with marker='slider_block'
  - id: '@tpv.hero_slide'
    identifier: 'hero_slide'
    title: 'Hero slide preview'
    proportions:
      default:
        horizontal: { height: 700, weight: 1920, alignmentType: 'middleMiddle' }
        vertical:   { height: 900, weight: 600, alignmentType: 'middleMiddle' }
        square:     { side: 800, alignmentType: 'middleMiddle' }
```

### Rules for creating previews

| Condition | Preview |
|---|---|
| Always (minimum) | `product_card`, `banner` |
| There is at least one block with marker='slider_block' (kind=carousel or category_tiles) | **required** — add `hero_slide` (full-HD proportions) |
| There are products with a gallery + a product detail page | optionally add `product_gallery` (square thumb proportions) |
| There is a category-tile block with NON-banner proportions | optionally add `category_tile` |

**The mapper creates at least 2 previews** (`product_card`, `banner`), plus `hero_slide` if there is a slider block. Validator S52 flags a missing `hero_slide` when a slider_block is present as a WARNING.

## 3. Orders Storages + Order Statuses

⚠ **If the project has a `cart`/`checkout` page — an orders_storage MUST be created.**

```yaml
orders_storage:
  - id: '@ostorage.default'
    identifier: 'default'
    general_type_id: 21          # 21 = order (STABLE)
    form: 'signin'                # FK to the signin form (or a dedicated checkout form)
    price_expiration: '10m'       # how long the fixed price is valid before re-calculation
    localize_infos:
      en_US:
        title: 'Default Order Storage'

# ⚠ DO NOT add `capture_mode` — the field is commented out in the CMS entity class
# (order-storage.entity.ts). This is an outdated example from early versions of the rules.
# If you include `capture_mode` in the blueprint, the load fails with HTTP 500
# "column 'capture_mode' of relation 'orders_storage' does not exist".
# Source of truth — `agents_datasets/rules/generated/table-columns.md` section `orders_storage`.

order_statuses:
  - { id: '@os.new',        identifier: 'new',        is_default: true,  storage: 'default', localize_infos: { en_US: { title: 'New' }}}
  - { id: '@os.processing', identifier: 'processing', is_default: false, storage: 'default', localize_infos: { en_US: { title: 'Processing' }}}
  - { id: '@os.shipped',    identifier: 'shipped',    is_default: false, storage: 'default', localize_infos: { en_US: { title: 'Shipped' }}}
  - { id: '@os.delivered',  identifier: 'delivered',  is_default: false, storage: 'default', localize_infos: { en_US: { title: 'Delivered' }}}
  - { id: '@os.cancelled',  identifier: 'cancelled',  is_default: false, storage: 'default', localize_infos: { en_US: { title: 'Cancelled' }}}
  - { id: '@os.returned',   identifier: 'returned',   is_default: false, storage: 'default', localize_infos: { en_US: { title: 'Returned' }}}
```

## 4. Product Relations Templates — relations between products

`product_relations_templates` is the **universal mechanism for linking products** in OneEntry. A relation is a rule that, given one product, produces a list of other products (the same product in other variants, similar items, complementary items, etc.).

### 4.1 Use cases (which relation to create when)

#### Variants — variants of one product (colors, sizes, configurations)

**The most frequent and important use case in e-commerce.** A single "iPhone 17" product with 3 color variants — these are **3 separate products** in the DB (each with its own SKU, price, images), linked via `product_relations_templates` with `identifier='variants'`.

On the product card the admin sees "iPhone 17 Black" + chips for switching to "Pink" / "Blue" — those chips are rendered by the UI based on this relation.

**Relation condition:** `same product_model` OR `same product_group` OR `same parent_sku`. The grouping attribute **must exist** in `forProducts.schema` (e.g. `product_model: 'iphone-17'`).

```yaml
product_relations_templates:
  - id: '@prt.variants'
    identifier: 'variants'
    name: 'Product Variants (colors/sizes)'
    is_active: true
    conditions:
      - field: 'product_model'        # an attribute in forProducts.schema
        operator: 'eq'
        value: '{self.product_model}' # reference to the current product
      - field: 'sku'
        operator: 'neq'               # exclude the product itself from the variants list
        value: '{self.sku}'
```

**Create IF:** the project has a color-picker / size-picker UI and the products share a common "parent" attribute (`product_model`, `parent_sku`, `product_group_id`).

#### Similar — similar products (same category / class)

"Similar to this product" — typically the same type and class, close in price.

**Condition:** the same `category` OR `clothing_type` OR another generic attribute, plus a price within ±20-50%.

```yaml
- id: '@prt.similar'
  identifier: 'similar'
  name: 'Similar Products'
  is_active: true
  conditions:
    - field: 'category'             # or 'clothing_type' / 'shoe_type' / etc — whichever attribute exists in forProducts
      operator: 'eq'
      value: '{self.category}'
    - field: 'price'
      operator: 'between'
      value: ['{self.price * 0.7}', '{self.price * 1.3}']
    - field: 'sku'
      operator: 'neq'
      value: '{self.sku}'
```

**Create IF:** the project has a `RelatedProducts` / `SimilarProducts` / "You may also like" block.

#### Cross-sell — complementary products (different category, but related class)

"Buy together with this" — a product from a different category but semantically related (shirt + trousers, phone + case).

**Condition:** a different `category`, the same `brand` or `style` or `season` — for the link.

```yaml
- id: '@prt.cross_sell'
  identifier: 'cross_sell'
  name: 'Cross-sell (complementary)'
  is_active: true
  conditions:
    - field: 'category'
      operator: 'neq'
      value: '{self.category}'      # different category
    - field: 'brand'                # OR 'style' / 'season' / 'collection_id'
      operator: 'eq'
      value: '{self.brand}'         # same brand or season
```

**Create IF:** there is a `CrossSell` / `CompleteTheLook` / `BoughtWith` block.

#### Upsell — more expensive products in the same category

"Better alternatives for a bit more" — to increase the basket value.

```yaml
- id: '@prt.upsell'
  identifier: 'upsell'
  name: 'Upsell (better options)'
  is_active: true
  conditions:
    - field: 'category'
      operator: 'eq'
      value: '{self.category}'
    - field: 'price'
      operator: 'gt'
      value: '{self.price * 1.2}'   # at least 20% more expensive
```

**Create IF:** there is an `Upsell` / "Premium options" block.

#### Recommended — general recommendations (no strict logic)

The most generic case — the admin tunes whatever rules they want later through the OneEntry Platform UI.

```yaml
- id: '@prt.recommended'
  identifier: 'recommended'
  name: 'Recommended Products'
  is_active: true
  conditions: []                    # empty — admin tunes it
```

**Create IF:** there is a `Recommended` / `ForYou` block without explicit semantics.

### 4.2 Condition rules

The mapper generates **default conditions** based on what is present in `forProducts.schema`:

| relation | requires this attribute in forProducts | if the attribute is missing |
|---|---|---|
| variants | `product_model` / `parent_sku` / `product_group` | DO NOT create the relation (warning) |
| similar | `category` / `clothing_type` / any generic | conditions=[] (admin will tune) |
| cross_sell | `brand` / `style` / `collection` | conditions=[] |
| upsell | `category` + `price` | conditions=[] |
| recommended | — | conditions=[] (always) |

**Mapper algorithm:**

```python
schema_attrs = forProducts.schema.keys()    # {'price', 'sku', 'category', 'brand', ...}

if 'product_model' in schema_attrs or 'parent_sku' in schema_attrs:
    # Create variants with conditions
    ...
elif any('Color' in p or 'variant' in p.lower() for p in inspector_components):
    # The code has variant switchers — try to deduce the attribute
    warning.append("variants_template_skipped: variant switcher detected but no product_model/parent_sku attribute in forProducts.schema. Add atribute first")
```

Operators: `eq`, `neq`, `lt`, `gt`, `lte`, `gte`, `between`, `in`, `nin`, `like`, `regex`. The value type is picked to match the field (string/number/array).

`{self.X}` — a placeholder, substituted at runtime with the X value from the current product. If X is absent on the product — the condition is skipped.

### 4.3 After import

Conditions in the blueprint are **defaults**. In OneEntry Platform the admin can:
- Change the operator (`eq` → `like`)
- Add / remove conditions
- Change ranges (`price * 0.7..1.3` → `price * 0.5..2.0`)
- Create new relation templates via the UI

This is acceptable behaviour — the blueprint provides a **starting point** with reasonable defaults, not a final configuration.

## 5. Special block_types — what CANNOT go through the blueprint

OneEntry has **8 dynamic block types** (added by seeds with `INSERT ... RETURNING id`):

| Type | Purpose |
|---|---|
| `frequently_ordered_block` | Frequently ordered |
| `trending_block` | Trending |
| `recently_viewed_block` | Recently viewed |
| `repeat_purchase_block` | Repeat purchase |
| `personal_recommendations_block` | Personal recommendations |
| `cart_complement_block` | Complementary cart items |
| `cart_similar_block` | Similar to cart items |
| `wishlist_similar_block` | Similar to wishlist |

⚠ **Their `general_type_id` is DYNAMIC** — the number differs between instances. The loader only accepts a number → the blueprint **cannot** set them correctly.

### What to do

1. The mapper creates the block with a **base** type (`general_type_id: 10` — product_block) + an identifier with an explicit marker:
   ```yaml
   blocks:
     - identifier: 'frequently_ordered_products'
       general_type_id: 10
       attribute_set: 'forBlocks_product_collection'
       # ... + custom_settings: { 'requires_special_type': 'frequently_ordered_block' }
   ```

2. In **validation.md** an INFO note must be added for the admin:
   ```
   After import, in the OneEntry admin UI:
   - Open the 'frequently_ordered_products' block
   - Change the type from 'product_block' to 'frequently_ordered_block'
   - Same for: trending_products, recently_viewed_products, repeat_purchase, personal_recommendations, cart_complement, cart_similar, wishlist_similar
   ```

## 6. Payment Accounts — NOT via the blueprint

`payment_accounts` (Stripe / Yookassa / Custom) — **NOT in the whitelist**. These are concrete payment providers with real API keys / webhook URLs — configured manually by the admin under `Settings → Payment accounts`.

The blueprint can **only** carry the `orders_storage_payment_accounts` link, but that works **only if the payment_account already exists** (FK to payment_accounts.id).

**Mapper rule:** do NOT create `orders_storage_payment_accounts` via the blueprint — leave it empty. In `validation.md` explicitly state:

```
After import (to activate payments):
1. Settings → Payment accounts → Add account → choose a type (Stripe/Yookassa/Custom)
2. Fill in the provider's API keys
3. Settings → Order storages → pick default → attach payment_account
4. Settings → Payment status map → configure mapping of payment statuses to order statuses
```

## 7. Payment Status Map — NOT via the blueprint

`payment_status_map` — the link between payment provider statuses and order statuses. **Not in the whitelist.** Done by the admin after the payment_account and orders_storage are created.

Add a reminder in `validation.md`.

## 8. Session/Refund statuses — these are enums in code, not configurable

| Enum | Values | Where used |
|---|---|---|
| PaymentSessionStatus | waiting, completed, canceled, expired | in cms code |
| PaymentRefundStatus | pending, succeeded, failed, cancelled | in cms code |
| PaymentAccountType | stripe, yookassa, custom | when creating a payment_account |

These are **hard-coded** enums — the blueprint does not control them and no configuration is needed.

## 9. ❌ What absolutely cannot go through the blueprint

| What needs to be done | How |
|---|---|
| Payment Accounts (Stripe/Yookassa) | Admin UI → Settings → Payment accounts |
| Payment Status Map | Admin UI → Settings → Payment status map |
| Permissions for user_groups | `user_group_permissions_mn` — IN the 24-table whitelist (since 2026-05-21), natural-key upsert on `(group_id, permission_id)` |
| Admin users (cms admins) | The `admins` module (id=5) — a separate entity |
| Dynamic general_types (frequently_ordered etc) | Through the blueprint only as the base type, then the admin changes it |

In `validation.md` the mapper must provide the **full list of manual steps**.

## 10. ✅ Attaching Data Submission forms to the Users module — IN the 24-table whitelist (since 2026-05-21)

`form_module_config` — **IN the 24-table whitelist** (see `rules/generated/whitelist-tables.md`). Include the bindings **directly in the blueprint** — the loader inserts them as plain rows in `form_module_config` (no natural-key upsert; UNIQUE `(form_id, module_id)` on duplicates will fail, so only create rows that are not preseeded).

**Typical blueprint row:**

```yaml
tables:
  form_module_config:
    - id: '@fmc.profile_edit_in_users'
      form_id: '@form.profile_edit'
      module_id: 9          # Users module id (preseeded)
      position_id: null     # loader fills via auto_positions=true
```

**What to do:** the mapper creates the data forms (`profile_edit`, `address_book`, `change_password`, `subscriptions_pref`, `consents`, `loyalty_card_request`, `social_connections`) as usual AND emits one `form_module_config` row per form referencing `module_id=9`. No post-import manual step is required for the typical case.

<details>
<summary>Legacy fallback (when blueprint-loader is older than 2026-05-21)</summary>

If the target cms is older than 2026-05-21 and rejects `form_module_config` with `Table 'form_module_config' is not whitelisted`, fall back to the manual admin step:

```
After importing the blueprint:
1. Go to the OneEntry Platform admin → 'Users' module.
2. Section 'Attached forms' (form_module_configs).
3. For each data form, manually create a binding with module_id=9 (Users), form_id=<form id>.
   Forms to attach: profile_edit, address_book, change_password, subscriptions_pref, consents, loyalty_card_request, social_connections.
```

Without this manual binding, the data forms exist in the DB but are not visible in the admin UI as "user extension forms".

</details>

This behaviour is mirrored in:
- `entity-mapper.md` Step 1 (forUsers section) — the warning format is already there.
- `blueprint-validator.md` S43 — INFO reminder for the admin.

`form_data` — the table for submitted form records (entity name is `form_data` snake_case; the URL path `/api/content/form-data` uses kebab-case but the loader/whitelist references the snake_case table name). **IN the 24-table whitelist** (since 2026-05-21), but this is runtime data (storefront → `POST /api/content/form-data`), not configuration. **DO NOT generate by default** — only include a small set of demo rows when explicitly required for seed/demo content.

## 11. ❌ admin user_group — DO NOT create

An `admin` user_group for storefront users is **meaningless** — it gets confused with cms admins (the `admins` module).

**Rule:** the mapper creates **only** the `user` user_group (or nothing at all, if all storefront users are guests). The `admin` user_group is **not created**.

OneEntry Platform admins are a **separate mechanism**, not managed via the blueprint.
