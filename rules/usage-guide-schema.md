# OneEntry blueprint usage guide — Part 1: Schema, Attributes, Forms, Users, Blocks

> **Part 1 of 3** of the usage guide (split for context-cost reasons). See `usage-guide.md` for index + sections §16–18 + checklist; `usage-guide-content.md` for §10–15 (templates / orders / products / relations).

## 1. attributes_sets — types and schema

`attribute_set.type_id` determines which entity the set can be attached to. **One attribute_set can be used only by entities of a SINGLE type_id.**

Numeric mapping verified against the CMS init seeds for `attribute_set_types` (ids 1-7 from the first seed, 8=forUserGroups, 9=forEvents, 10=system, 11=forDiscounts added by later seeds):

| type_id | name | attached to | example |
|---|---|---|---|
| 1 | forAdmins | admins | `forAdmins` |
| **2** | **forBlocks** | blocks (REQUIRED!) | `forBlocks_default`, `forBlocks_slider`, `forBlocks_reviews` |
| 3 | forOrders | orders | rare, usually empty |
| **4** | **forPages** | pages | `forPages` (default for all pages) |
| **5** | **forProducts** | products | `forProducts` (or several by product category) |
| **6** | **forUsers** | user_groups (`attribute_set_id`) | `forUsers` |
| **7** | **forForms** | forms | `forForms_signin`, `forForms_review`, ... |
| 8 | forUserGroups | user_groups (group metadata) | `forUserGroups` (usually empty `schema: {}`) |
| 9 | forEvents | events (out-of-whitelist module) | not used via the blueprint |
| 10 | system | internal/system attribute sets | not used via the blueprint |
| 11 | forDiscounts | discounts (out-of-whitelist module) | not used via the blueprint |

⚠ **Validator S16:** checks that every block has `attribute_set.type_id == 2`. A set of any other type → ERROR.

### Minimum set for any project

Every blueprint must contain at least:
- `forUsers` (type_id=6) — auth/profile
- `forUserGroups` (type_id=8) — group metadata, usually `schema: {}`
- `forProducts` (type_id=5) — if there are products
- `forPages` (type_id=4) — title, description, meta_*
- `forForms_signin` (type_id=7) — for the signin form (required)
- `forBlocks_default` (type_id=2) — if there are blocks
- `forAdmins` (type_id=1) — usually empty

### attribute_set schema structure

```yaml
attributes_sets:
  - id: '@aset.forProducts'
    identifier: 'forProducts'
    type_id: 5                                    # forProducts
    title: 'For products'
    schema:
      price:
        identifier: 'price'
        type: 'real'
        position: 1
        isPrice: true                             # system flag
        rules: { minValue: 0 }
        localizeInfos: { en_US: { title: 'Price' } }
      sku:
        identifier: 'sku'
        type: 'string'
        position: 2
        isSku: true
        rules: { pattern: '^[A-Z0-9-]+$' }
        localizeInfos: { en_US: { title: 'SKU' } }
      # ... remaining fields
```

---

## 2. Attribute types — 19 types

Full list from the `AttributeType` enum (verified — 19 entries: `string`, `text`, `textWithHeader`, `integer`, `real`, `float`, `dateTime`, `date`, `time`, `file`, `image`, `groupOfImages`, `radioButton` (enum key `flag`), `list`, `button`, `entity`, `spam`, `json`, `timeInterval`). Note: keys differ from values for two of them — the enum key `flag` maps to the value string `'radioButton'`; the others use the value as their key.

| type (value used in `SchemaItem.type`) | what it is for | example fields |
|---|---|---|
| `string` | short string (≤ ~255 chars) | `sku`, `name`, `brand`, `color`, `phone` |
| `text` | long free-form text | `description`, `body`, `message` |
| `textWithHeader` | text with a header label | rich-card sections |
| `integer` | whole number | `quantity`, `rating_count`, `age` |
| `real` | fractional number | `price`, `weight_kg`, `rating`, `heel_height` |
| `float` | fractional number (alias of `real` in practice; rare) | rare; prefer `real` |
| `dateTime` | date + time (camelCase!) | `last_login`, `published_at` |
| `date` | date (YYYY-MM-DD) | `release_date`, `dob`, `expiry_date` |
| `time` | time (HH:MM) | `opening_time` |
| `timeInterval` | interval / duration | `session_duration` |
| `file` | file URL | `spec_sheet`, `manual_pdf` |
| `image` | image URL | `cover`, `avatar`, `banner` |
| `groupOfImages` | array of image URLs | `gallery`, `slides_images` |
| `radioButton` | the boolean flag (enum key in code is `flag`, value is `'radioButton'`) | `in_stock`, `is_new`, `sign_up`, `accept_terms`, `is_featured` |
| `list` | enum of values; multi-select expressed via `listType: 'multi'` on the same type | `season`, `gender`, `size` (also multi: `pref_languages`) |
| `button` | UI button (rare) | call-to-action attributes |
| `entity` | reference to another entity (FK) | `featured_product`, `parent_category` |
| `spam` | spam-check field (rare) | reserved |
| `json` | arbitrary JSON (fallback; also used for arrays/maps without a known shape) | `metadata`, `custom_settings`, `addresses`, `related_products` arrays |

⚠ **Types that do NOT exist** (common hallucinations to avoid): `boolean` (use `radioButton`), `datetime` lowercase (use `dateTime`), `multiList` (use `list` with `listType: 'multi'`), `groupOfFiles` (use `json` for arrays of file URLs), `groupOfEntities` (use `json` for arrays of FKs).

### Attribute-type selection algorithm

1. **By field name** (heuristic, see the table below).
2. **By value type in code** (jsType from the inspector):
   - `string` → `string` (short, ≤255) or `text` (long/multiline) or `textWithHeader` (text with leading label)
   - `number` → `real` (if float / contains `.`) or `integer` (if whole)
   - `boolean` (JS bool) → `radioButton` (enum value — there is NO `boolean` AttributeType)
   - `string[]` of primitives → `list` (with `listTitles` enum); for multi-select use `list` + `listType: 'multi'` (NO separate `multiList` type)
   - `object[]` (arrays of structured records like saved addresses, related products by FK list) → `json` (NO `groupOfEntities` type)
   - `URL` (`http://...` or `/...`) → `image` (if `.jpg` / `.png` / `.webp` / `.gif` / `.avif`) or `file`
   - `string[]` of URLs to images → `groupOfImages` (the only "group" type that exists)
   - `string[]` of file URLs (non-image) → `json` (NO `groupOfFiles` type)
   - Date with time → `dateTime` (camelCase — NOT `datetime`)
3. **Fallback** → `json` (with a warning).

### Heuristics by name

| Pattern | type | system flag | rules / additionalFields |
|---|---|---|---|
| `*price*`, `*amount*`, `*cost*` (number) | `real` | `isPrice: true` | `minValue: 0` |
| `*sku*`, `*barcode*`, `*art*`, `*article*` | `string` | `isSku: true` | `pattern: '^[A-Z0-9-]+$'` |
| `*currency*`, `*ccy*` | `string` | `isCurrency: true` | `pattern: '^[A-Z]{3}$'` |
| `preview`, `cover`, `main_image`, `thumbnail` | `image` | `isProductPreview: true` (for products) | — |
| `gallery`, `images`, `photos`, `slides` | `groupOfImages` | — | — |
| `email` (in an auth form) | `string` | `isLogin: true` | `pattern: email` |
| `password` (in an auth form) | `string` | `isPassword: true` | `minLength: 8, maxLength: 128` |
| `sign_up`, `signup` (in the signin form) | `radioButton` | `isSignUp: true` | — |
| `phone`, `mobile`, `tel` | `string` | — | `additionalFields: { mask: '+# ### ### ####' }` |
| `dob`, `birthday`, `date_of_birth` | `date` | — | `minDate: '1900-01-01', maxDate: today` |
| `postcode`, `zip` | `string` | — | `pattern: '^[A-Z0-9 -]{3,10}$'` |
| `card_number`, `cc_number` | `string` | — | `pattern: '^[0-9]{13,19}$'` |
| `card_cvv`, `cvc` | `string` | — | `minLength: 3, maxLength: 4` |
| `rating` (0-5) | `real` | — | `minValue: 0, maxValue: 5` |
| `description`, `body`, `content`, `message` | `text` | — | — |
| `weight*`, `height*`, `volume*`, `*_kg`, `*_cm`, `*_l` | `real` | — | `minValue: 0` |
| `count`, `*_count`, `quantity`, `qty` | `integer` | — | `minValue: 0` |

---

## 3. System flags — exactly 1 per attribute_set

Each flag may be `true` on **no more than one** attribute within a single `attribute_set.schema`. Validator S11 enforces this.

| Flag | Where to use | What it does |
|---|---|---|
| `isPrice: true` | `forProducts.price` | marks the field as the "price" for the catalog |
| `isSku: true` | `forProducts.sku` | marks the SKU for search/import |
| `isCurrency: true` | `forProducts.currency` | partner of isPrice |
| `isProductPreview: true` | `forProducts.cover` | main image on the product card |
| `isLogin: true` | `forForms_signin.email` | login field |
| `isPassword: true` | `forForms_signin.password` | password field |
| `isSignUp: true` | `forForms_signin.sign_up` | login↔signup switch |

### Anti-patterns

- ❌ Two `isPrice: true` in one set (even if a product has 2 prices). Make `sale_price` a field without the flag.
- ❌ `isLogin: true` outside the signin form (e.g. on `forForms_address.email`). In data forms it is just an email field.
- ❌ `isProductPreview: true` on a non-image attribute. Only allowed for `type: image`.

---

## 4. Validators (rules) — required minimums

### email
```yaml
rules: { pattern: "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$" }
```

### password
```yaml
rules: { minLength: 8, maxLength: 128 }
```

### phone (via `additionalFields`, not `rules`)
```yaml
additionalFields: { mask: "+## ### ### ####" }
```

### dob (date of birth)
```yaml
rules:
  minDate: "1900-01-01"
  maxDate: "<today>"   # the mapper substitutes YYYY-MM-DD
```

### postcode
```yaml
rules: { pattern: "^[A-Z0-9 -]{3,10}$" }
```

### card_number
```yaml
rules: { pattern: "^[0-9]{13,19}$" }
```

### card_cvv
```yaml
rules: { minLength: 3, maxLength: 4 }
```

### rating
```yaml
rules: { minValue: 1, maxValue: 5 }
```

If a field is found but the validator is not set — validator S26 raises a WARNING.

---

## 5. Pages — types

Source: `agents_datasets/rules/general-types.md`.

| identifier pattern | general_type_id | type | examples |
|---|---|---|---|
| `*-clothing`, `*-shoes`, `sale`, `new`, `catalog-*` | **4** | `catalog_page` | product catalog pages |
| `404`, `500`, `error-*` | 3 | `error_page` | special error pages |
| `*-preview` | 5 | `product_preview` | product preview page (renders the card) |
| `cart`, `checkout*`, `account*`, `info`, `about`, `contact`, `faq`, `terms`, `privacy`, `stores`, `careers`, `sitemap`, `root`, `home`, `favorites` | **17** | `common_page` | regular content / system pages |
| `external-*` | 22 | `external_page` | rare (link to an external URL) |

### Heuristic

> If a page **renders a list of products** — `4` (catalog_page).
> Otherwise — `17` (common_page).

### page_url — single slug, not a path

`page_url` is **only the last segment**, no `/`. Hierarchy goes through `parent_id`.

```yaml
# ❌ NO:
- { identifier: 'women-clothing', page_url: 'women/clothing' }
# ✅ YES:
- { identifier: 'women', parent: 'root', page_url: 'women' }                # hub
- { identifier: 'women-clothing', parent: 'women', page_url: 'clothing' }   # leaf
```

Validator S32 checks for `/` inside page_url.

### Hub pages (intermediate)

If there is `<X>-<Y>`, you **must** create an intermediate `<X>` as a hub page with `general_type_id: 17`. Without a hub the URL hierarchy is broken.

⚠ **A hub page's gtid is ALWAYS 17 (common_page), regardless of the gtid of its children.** Catalog children can have gtid=4 — that's expected. The hub itself has no product list, only content (banners, category cards). See `oneentry-invariants.md` §19 for the full rule + validator S41 extension.

```yaml
# ✅ correct
- { identifier: women,          general_type_id: 17, parent: root }       # hub
- { identifier: women-clothing, general_type_id: 4,  parent: women }      # catalog
- { identifier: women-shoes,    general_type_id: 4,  parent: women }      # catalog

# ❌ wrong — hub forced to catalog gtid, will show "empty catalog" in admin
- { identifier: women,          general_type_id: 4,  parent: root }
```

### Checkout flow — the full funnel

If there is any `checkout*` page — all 4 are **required**:
- `checkout` (hub, 17)
- `checkout-delivery` (17)
- `checkout-payment` (17)
- `checkout-confirmation` (17) ← often forgotten

Validator S24 checks for the presence of a `checkout_address` form.

---

## 6. Forms — types

⚠ **Main principle:** a form in OneEntry is a **submission into `form_data`** with processing (db/email/script). Profile operations on a user (changing name/password/address/settings) are **not forms** but attributes in `forUsers` (see §7 and `rules/users-architecture.md`).

From the DB enum `forms_type_enum`:

⚠ **`FormType` enum has exactly 5 values** (verified): `order`, `sing_in_up` (legacy typo; not `sign_in_up`), `collection`, `data`, `rating`. Anything else (`'comments'`, `'simple'`, `'contact'`) is NOT a valid `forms.type`.

| type | for what | invariant |
|---|---|---|
| `sing_in_up` | login + signup in one form | identifier='signin', exactly 3 attributes (email, password, sign_up) |
| `order` | the **entire checkout** in one form (attached to orders_storage via form_module_config) | identifier='checkout' (or 'order_form'), includes delivery + payment + promo_code fields |
| `rating` | review with a rating | review with a rating field |
| `data` | generic submission to `form_data` (contact/feedback/reserve/refer/newsletter/track_order/comments/etc.) | a general submission |
| `collection` | data collection for later display as an integration collection | rare |

### Form whitelist for e-commerce — typically 5-9 items

| identifier | type | processing_type | fields |
|---|---|---|---|
| **signin** | `sing_in_up` | `db` | email (isLogin), password (isPassword), sign_up (isSignUp) |
| **checkout** | **`order`** | `db` | full_name, phone, email, address_line1, address_line2, city, postcode, country, delivery_method, delivery_instructions, payment_method, card_number, card_holder, card_expiry, card_cvv, **promo_code**, save_address, agreed_terms |
| **review** | `rating` | `db` | rating, headline, body, recommend |
| **contact** | `data` | `email` | name, email, subject, message, attachments |
| **feedback** | `data` | `db` | rating, category, order_id, message |
| **newsletter** | `data` | `db`/`script` | email |
| **reserve_in_store** | `data` | `email`/`db` | product_id, store_id, size, full_name, phone, pickup_date |
| **refer_a_friend** | `data` | `email` | friend_emails, message |
| **track_order** | `data` | `db` | order_number, email |
| **comments** | `data` | `db` | author_name, message — there is no `comments` value in `FormType`; use `data` |

### ❌ What is NOT a form (full anti-pattern list)

Validator S49 catches these identifiers as ERROR. All these "forms" are actually **`forUsers` attributes** or **a field on `checkout`**:

| Anti-pattern identifier | What it really is |
|---|---|
| `profile_edit`, `profile_my_data`, `edit_profile` | `forUsers` attributes: first_name, last_name, phone, dob, gender, sizes |
| `change_password`, `password_change` | The `password` field (isPassword) in `forUsers`; password change goes through the `users_auth_providers` endpoint |
| `address_book`, `addresses` | The `addresses` attribute (`type: json` — arrays of structured records use `json`; there is no `groupOfEntities` type) in `forUsers` |
| `payment_methods`, `saved_cards` | The `saved_cards` (json) attribute in `forUsers` or the out-of-whitelist `payment_accounts` |
| `subscriptions_pref`, `subscriptions`, `preferences` | `pref_*` (radioButton) attributes in `forUsers` |
| `consents`, `gdpr_consents` | `consent_*` attributes in `forUsers` |
| `loyalty_card_request`, `loyalty` | `loyalty_*` attributes in `forUsers` |
| `social_connections`, `oauth_connections` | `social_*` attributes in `forUsers` |
| **`promo_code`** | A **field** `promo_code` (string) in `forForms_checkout` (inside the `order` form) |
| `checkout_address`, `checkout_payment`, `checkout_confirmation` | **Merge into a SINGLE** form `checkout` (`type: order`) with all the fields. Validator S50 catches this. |

### Required fields in forms

| identifier | invariant fields |
|---|---|
| `signin` | `email` (isLogin), `password` (isPassword), `sign_up` (isSignUp, radioButton) — **exactly these 3** |
| `checkout` (`order`) | **minimum** full_name, phone, address_line1, city, postcode, country, payment_method. Recommended also: promo_code, agreed_terms |
| `review` (`rating`) | rating (real/integer, 1-5), headline, body |
| `feedback`, `contact` | name, email, message |
| `newsletter` | email |

### Anti-patterns

- ❌ Creating `login` and `signup` as two forms. Always **one** `signin` with `type: sing_in_up`.
- ❌ Splitting checkout into 2-3 forms (`checkout_address`/`checkout_payment`/`checkout_confirmation`). **One form** with `type: order`, the multi-step UI is a frontend concern.
- ❌ Creating `change_password`/`address_book`/`subscriptions_pref`/etc as forms. These are **`forUsers` attributes**.
- ❌ Creating `promo_code` as a form. That is a **field** in `forForms_checkout`.
- ❌ Creating a form without a real source component in the project (validator S38).
- ❌ Adding `isLogin/isPassword/isSignUp` flags to `data`/`order`/`rating` forms (only on signin).
- ❌ Using `type='data'` for the checkout form (the correct value is `type='order'` so the loader attaches it to orders_storage via form_module_config).

---

## 7. user_groups

| identifier | When to create | id (in a fresh DB) |
|---|---|---|
| `guest` | **NEVER** — preseeded | 1 |
| `admin` | **NEVER** via blueprint — `admin` user_group has no storefront purpose. CMS admin accounts are managed by the separate `admins` module (created via `npm run seed:admins` or admin UI), not by `user_groups`. | — (NOT preseeded; do not occupy id=2) |
| `user` | ALWAYS | DYNAMIC |
| `vip` / `wholesaler` / `b2b` / etc | if present in the project code (explicit branching by role) | DYNAMIC |

⚠ Previous versions of this doc incorrectly claimed `admin` was preseeded with id=2. **It is not.** Only `guest` (id=1) is preseeded. Verified against the CMS `set-default-user-group` seed (the only seed touching `user_groups`).

⚠ If the app needs a reference to `guest` (for example in `users_auth_providers`) — use the marker `guest_preseeded` in mapped.yaml; the builder turns it into a literal `user_group_id: 1`:

```yaml
users_auth_providers:
  - identifier: anonymous
    type: email
    user_group: guest_preseeded   # the builder substitutes 1
```

---

## 8. users_auth_providers

At least one is required — an email provider:

```yaml
users_auth_providers:
  - identifier: email
    type: email
    form: signin
    user_group: user
```

Additional ones (google/apple/facebook social login):
- **Do not create via the blueprint** — configured manually by the admin after import (`out-of-whitelist:` warning).

---

## 9. Blocks — all 12 types

Full reference — `agents_datasets/rules/block-types.md`. Dynamic-id strategy — `agents_datasets/rules/dynamic-ids.md`.

| kind (inspector) | general_type_marker | fallback general_type_id | attachment | customSettings |
|---|---|---|---|---|
| `static_content` | — | 18 (common_block) | page | arbitrary |
| `products_collection` | — | 10 (product_block) | page (fixed product list) | arbitrary |
| `carousel` | `slider_block` | 18 | page (for hero/banner) | — |
| `trending` / `new_arrivals` | `trending_block` | 10 | page (home/catalog) | `trendingConfig: {limit, period}` |
| `recently_viewed` | `recently_viewed_block` | 10 | page (any user page) | `recentlyViewedConfig: {limit}` |
| `repeat_purchase` | `repeat_purchase_block` | 10 | page (account/orders) | `repeatPurchaseConfig: {limit, minTimesPurchased, sortBy}` |
| `recommendations` / `for_you` | `personal_recommendations_block` | 10 | page (home/account) | `personalRecommendationsConfig: {limit}` |
| `similar` / `related` | `similar_products_block` (STABLE 8) | 8 | product_page | `audienceFilter?` |
| `cross_sell` / `complete_the_look` | `cart_complement_block` | 10 | product_page or cart | `cartDrivenConfig: {limit, excludeCartItems, fallbackToTrending}` |
| `bought_together` / `frequently_ordered` | `frequently_ordered_block` | 10 | product_page | `frequentlyOrderedConfig: {limit, fallbackToTrending}` |
| `wishlist_similar` | `wishlist_similar_block` | 10 | favorites page | `cartDrivenConfig` |
| `reviews` | — | 18 (common_block) | product_page | arbitrary |
| `faq` | — | 18 (common_block) | page (info) | arbitrary |

### customSettings — JSON schemas

```yaml
# trending_block
custom_settings: { trendingConfig: { limit: 12, period: 'week' } }

# recently_viewed_block
custom_settings: { recentlyViewedConfig: { limit: 10 } }

# repeat_purchase_block
custom_settings: { repeatPurchaseConfig: { limit: 10, minTimesPurchased: 1, sortBy: 'lastPurchased' } }

# personal_recommendations_block
custom_settings: { personalRecommendationsConfig: { limit: 10 } }

# cart_complement / cart_similar / wishlist_similar
custom_settings: { cartDrivenConfig: { limit: 12, excludeCartItems: true, fallbackToTrending: true } }

# frequently_ordered_block
custom_settings: { frequentlyOrderedConfig: { limit: 12, fallbackToTrending: true } }

# slider_block — no config yet (slides go through a separate slides entity)
custom_settings: {}
```

### Anti-patterns for blocks

- ❌ Creating Header/Footer/Navigation as blocks — that is the template level.
- ❌ Duplicating `hero_home` and `hero_category` — use one `hero` block attached to 2 pages via `block_pages_mn`.
- ❌ Creating a block without links (page/product) — orphan, useless (validator S15).
- ❌ Attaching `forBlocks_*` (type_id=2) to a page/product — only to blocks.
- ❌ Hardcoding DYNAMIC `general_type_id` (24-32) without a `general_type_marker` — it breaks on a different instance.

---

