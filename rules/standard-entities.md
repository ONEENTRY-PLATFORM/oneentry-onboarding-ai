# Standard entities — required project entities

> **⚠ Universality note.** Examples below may reference fashion-shop terms (clothing / shoes / bags / women / men) — they are **illustrative**. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop, restaurant (`menu-item/dish/cuisine`), beauty salon (`service/master/treatment`), hotel (`room/suite/amenity`), EdTech (`course/lesson`), corporate site (`page/department/team`), personal cabinet (`section/setting`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is a self-contained mirror of OneEntry Platform rules.** Agents use only this file.

This file describes the recommended minimum that any OneEntry project must contain regardless of its source code. If the application is missing something — the mapper still adds it (for technical CMS completeness).

## Minimum required set

### attributes_sets (at least 5)

```yaml
- id: '@aset.users'
  identifier: 'forUsers'
  type_id: 6  # forUsers
  title: 'For users'
  schema:
    email: { type: string, isLogin: true, localizeInfos: { en_US: { title: Email } }, position: 1, identifier: email }
    password: { type: string, isPassword: true, localizeInfos: { en_US: { title: Password } }, position: 2, identifier: password }

- id: '@aset.user_groups'
  identifier: 'forUserGroups'
  type_id: 8
  title: 'For user groups'
  schema: {}

- id: '@aset.products_default'
  identifier: 'forProducts'
  type_id: 5
  title: 'Products default'
  schema:
    title: { type: string, localizeInfos: { en_US: { title: Title } }, position: 1, identifier: title }
    sku: { type: string, isSku: true, localizeInfos: { en_US: { title: SKU } }, position: 2, identifier: sku }
    price: { type: real, isPrice: true, localizeInfos: { en_US: { title: Price } }, position: 3, identifier: price }
    preview: { type: image, isProductPreview: true, isCompress: true, localizeInfos: { en_US: { title: Preview } }, position: 4, identifier: preview }

- id: '@aset.pages_default'
  identifier: 'forPages'
  type_id: 4
  title: 'Pages default'
  schema:
    title: { type: string, localizeInfos: { en_US: { title: Title } }, position: 1, identifier: title }
    description: { type: text, localizeInfos: { en_US: { title: Description } }, position: 2, identifier: description }

- id: '@aset.forms_signin'
  identifier: 'forForms_signin'
  type_id: 7
  title: 'Sign in/up form'
  schema:
    email: { type: string, isLogin: true, localizeInfos: { en_US: { title: Email } }, position: 1, identifier: email }
    password: { type: string, isPassword: true, localizeInfos: { en_US: { title: Password } }, position: 2, identifier: password }
    sign_up: { type: radioButton, isSignUp: true, localizeInfos: { en_US: { title: Sign up } }, position: 3, identifier: sign_up }

- id: '@aset.admins'
  identifier: 'forAdmins'
  type_id: 1
  title: 'For admins'
  schema: {}
```

### user_groups (at least 1 — `user`; `guest` is preseeded, `admin` is NOT a user_group)

⚠ **Do not include `guest`** — it is preseeded in any fresh OneEntry Platform DB with `id=1` (see `rules/preseeded-entities.md`). Including it leads to a 23505 PRIMARY KEY violation. To reference guest in an FK, use the **numeric** `user_group_id: 1`, not a token.

⚠ **Do NOT create an `admin` user_group via blueprint.** CMS administrators are managed by the dedicated `admins` module (see `npm run seed:admins` in the CMS), NOT through `user_groups`. The `user_groups` table is STOREFRONT-only — an `admin` row here would create a useless storefront group, confused with cms-admins. See `rules/oneentry-invariants.md` §2.

```yaml
- id: '@ug.user'
  identifier: 'user'
  attribute_set_id: '@aset.user_groups'
  localize_infos: { en_US: { title: User } }
  is_visible: true
```

### product_statuses (at least 3)

```yaml
- id: '@ps.active'
  identifier: 'active'
  is_default: true
  localize_infos: { en_US: { title: Active } }

- id: '@ps.draft'
  identifier: 'draft'
  is_default: false
  localize_infos: { en_US: { title: Draft } }

- id: '@ps.archived'
  identifier: 'archived'
  is_default: false
  localize_infos: { en_US: { title: Archived } }
```

### forms (at least 1 — login = signup)

```yaml
- id: '@form.signin'
  identifier: 'signin'
  type: 'sing_in_up'              # ⚠ typo from the FormType enum
  processing_type: 'db'
  attribute_set_id: '@aset.forms_signin'
  localize_infos: { en_US: { title: 'Sign in / Sign up', titleForSite: 'Account', successMessage: 'OK', unsuccessMessage: 'Error' } }
```

### Reviews / ratings — TWO forms, not one

⚠ **Never put text-review fields and rating fields in the same form.** OneEntry treats form `type` as a processing-pipeline switch:

| type | What admin module routes it to |
|---|---|
| `rating` | Aggregates numeric score per linked product (one float field expected) |
| `data` | Accumulates free-form submission records (user-generated content) |

A single form with mixed shape can do ONE of those, not both. If your project has BOTH a star-rating widget AND a free-form review-text field, emit **two separate forms**:

```yaml
- id: '@form.review_rating'
  identifier: 'review_rating'
  type: 'rating'
  attribute_set_id: '@aset.forForms_review_rating'   # ONLY {rating: real | integer}
  processing_type: 'db'
  localize_infos: { en_US: { title: 'Product rating' } }

- id: '@form.review_feedback'
  identifier: 'review_feedback'
  type: 'data'
  attribute_set_id: '@aset.forForms_review_feedback' # body / title / author_name / photos / verified_purchase / occasion / …
  processing_type: 'db'
  localize_infos: { en_US: { title: 'Customer review' } }
```

Universal across project types — e-commerce (product reviews), hotel (room reviews), restaurant (dish reviews), salon (service feedback), EdTech (course ratings) — all benefit from the split.

`post-mapper-fixer.split_review_form_into_rating_and_data()` does this automatically when it detects a mixed `review` form.

### users_auth_providers (at least 1 — email)

```yaml
- id: '@uap.email'
  identifier: 'email'
  type: 'email'
  form_id: '@form.signin'
  user_group_id: '@ug.user'        # after registration the user lands in user
  is_active: true
  is_check_code: false
  localize_infos: { en_US: { title: 'Email auth' } }
```

### pages (at least 1 — root)

```yaml
- id: '@page.root'
  identifier: 'root'
  parent_id: null
  general_type_id: 4               # "page" type from the general_types seed
  page_url: ''
  attribute_set_id: '@aset.pages_default'
  localize_infos: { en_US: { title: Home, plainContent: '', htmlContent: '', menuTitle: Home } }
  is_visible: true
```

## Optional subsystems (not added by default)

### user_permissions + user_group_permissions_mn

Included only if the source code explicitly contains:
- A `Permission`/`Role`/`Capability` enum (e.g. `enum UserPermission { READ_ORDERS, WRITE_REVIEWS, ... }`).
- Route guards / middleware checking permissions (e.g. `@RequirePermission('orders.read')`).
- A custom user-group structure beyond the default `guest` / `user` split (e.g. `vip`, `wholesaler`, `b2b`).

`user_permissions` is largely **preseeded** (~112 rows). Map any new permission by its `(path, section)` natural key — the loader upserts. The blueprint should emit only **project-specific** permissions, not duplicate every default. See `entity-mapper.md` Step 2 sub-section "Permissions for user_groups" for the inline emission template.

### form_module_config

Included only when a form must be advertised inside a specific admin module's form list (e.g. attaching the project's `signin` form to the Users module so it appears under "Users → Forms"). For `orders_storage.order_form_id` you typically do NOT need `form_module_config` — the attachment is already implicit via the storage row.

See `entity-mapper.md` Step 9.9.

#### Per-user data-form flags (universal)

When a form is bound to the **Users** module (`module_id=9`) AND the form is a data-capture form (`type=data`, or identifier prefixed with `profile_*` / `my_*` / `account_*`) — i.e. a per-user "personal cabinet" form (profile, address book, my orders, my bonuses, my data, refer-a-friend, feedback, …) — the row MUST set **two** boolean flags to `true`:

| Flag | DB column | Why |
|---|---|---|
| `is_global` | `is_global` | The form must be available to EVERY authenticated user automatically. Without it, admin sees an empty "entities" list (you'd have to manually add every user.id), and the storefront cannot render the form for a logged-in user it was never explicitly added to. |
| `view_only_user_data` | `view_only_user_data` | Each user must only see their OWN submitted data — never another user's records. Without it, every user reads every other user's submissions (privacy leak + UX nonsense for a "My Address" form). |

Universal across verticals: e-commerce "My Address" / "Refer a friend", restaurant "Allergens" / "Loyalty card", hotel "Guest preferences", salon "Skin profile", EdTech "Learning goals", SaaS "Account settings".

Counter-examples that stay `false / false`:
- `signin` / `login` / `signup` — auth forms, not data capture; bound to users module for permission scoping only.
- `checkout` / `order` — bound to the Orders module, not Users.
- `review_rating` / `review_feedback` — bound to the generic Forms module (public-facing UGC, not per-user private storage).

`post-mapper-fixer.py` enforces this rule in two phases: (1) when emitting new `form_module_config` rows, and (2) on a second pass that patches pre-existing mapper-emitted rows.

### collections + collection_rows

Included for any flat localised dictionary entity in the project: FAQ items, City/Store directory, Brand/Vendor list, Partner list, Testimonial list. One collection per group, rows carry `lang_code` and a `form_data` jsonb payload.

See `entity-mapper.md` Step 9.8 for the emission template.

### orders_storage + order_statuses

**MANDATORY** when the source code contains **any "transaction-like" subsystem** — not just e-commerce. Universal triggers across project types:

| Project type | Examples of triggering files / symbols |
|---|---|
| E-commerce shop | `cart`, `checkout`, `checkout/payment`, `useCart`, `OrderStatus`, `/orders/*` |
| Restaurant / food delivery | `cart`, `checkout`, `delivery`, `reservation`, `tableBooking`, `OrderTrackingStatus` |
| Beauty salon / clinic / barbershop | `appointment`, `booking`, `reserveSlot`, `BookingStatus`, `MasterAppointment` |
| Hotels / coworking | `reservation`, `booking`, `roomBooking`, `ReservationStatus` |
| SaaS / subscription product | `subscription`, `billing`, `plan`, `Invoice`, `BillingCycle` |
| Personal cabinet / fintech | `payment`, `transaction`, `wallet`, `PaymentStatus`, `transfer` |
| Courses / EdTech | `enroll`, `enrolment`, `purchase`, `LessonPayment`, `CourseOrder` |

Any one of these signals is enough — **do NOT skip orders_storage**. The downstream `payment_status_map` configuration (admin UI "Payment Status Settings") **cannot be auto-built** without it, leaving a broken admin payment workflow.

For project types that don't fit (pure brochure / landing / corporate brand site / blog / documentation portal) — explicitly write `warning: 'orders_storage skipped — project is informational only (no transaction subsystem)'` in `mapped.yaml.warnings`.

`general_type_id` is **STABLE**: it is always `21` ("order" type — see the `general_types` snapshot in `rules/dynamic-ids.md`). Emit both the marker and the numeric fallback:

```yaml
orders_storage:
  - id: '@ostorage.default'
    identifier: 'default'
    general_type_marker: 'order'   # marker for verification against target DB (rules/dynamic-ids.md)
    general_type_id: 21            # STABLE fallback — "order" type id (init-db seed)
    form_id: '@form.signin'        # or '@form.order' if a dedicated order form exists
    localize_infos: { en_US: { title: 'Default storage' } }

order_statuses:
  # The 4 standard statuses per rules/oneentry-invariants.md §4
  - id: '@os.new'
    identifier: 'new'
    storage_id: '@ostorage.default'   # NOT NULL
    is_default: true
    localize_infos: { en_US: { title: New } }
  - id: '@os.processing'
    identifier: 'processing'
    storage_id: '@ostorage.default'
    is_default: false
    localize_infos: { en_US: { title: Processing } }
  - id: '@os.done'
    identifier: 'done'
    storage_id: '@ostorage.default'
    is_default: false
    localize_infos: { en_US: { title: Done } }
  - id: '@os.cancelled'
    identifier: 'cancelled'
    storage_id: '@ostorage.default'
    is_default: false
    localize_infos: { en_US: { title: Cancelled } }
```

`post-mapper-fixer.generate_payment_status_maps()` then builds `mapped.post_import_payment_status_maps[]` deterministically by keyword-matching the 4 statuses against the 5 `PaymentStatusMapDto` keys (`waiting|partial|completed|canceled|expired`). The orchestrator runs `PUT /api/admin/payments/status-maps` for each task.

⚠ **Do NOT skip `orders_storage` just because the inspector did not name a `general_type_id`.** The value is always `21`. If you cannot decide whether the project really has orders — re-check the signals above before omitting; omission requires explicit `notes.orders: 'no signals detected'` proof in the inspector output.

### blocks / *_mn tables

**When to include:** the source code has obvious "page sections" (banners, hero-slider, related-products, reviews, product collections, new arrivals / sale on home or category pages).

**When NOT to include:** the project consists only of static pages without reusable sections.

See rule #15 in `oneentry-invariants.md`. For blocks — `attribute_set.type_id = 2` (`forBlocks`) is required.

#### Typical blocks (whitelist for code-inspector heuristics)

These component name/pattern matches in the code map unambiguously to blocks:

| Pattern (file/component name) | block identifier | block_type | Where it is usually mounted |
|---|---|---|---|
| `HeroSlider`, `Hero`, `MainBanner` | `hero` | slider | home, sometimes category |
| `Slider`, `Carousel`, `ImageSlider` | `slider` | slider | home, category |
| `PromoBlock`, `PromoBanner`, `Discount*` | `promo` | banner | home, category |
| `DiscountBanner` | `discount_banner` | banner | home, sale |
| `NewArrivals`, `LatestProducts` | `new_arrivals` | product_collection | home |
| `BestSellers`, `Featured*`, `Top*` | `featured` | product_collection | home |
| `RelatedProducts`, `Similar*`, `RecommendedProducts` | `related_products` | product_collection | product page (via `block_products_mn`) |
| `Reviews`, `Testimonials`, `RatingsBlock` | `reviews` | reviews | product page |
| `RecentlyViewed`, `LastViewed` | `recently_viewed` | product_collection | product page |
| `CategorySection`, `CollectionShowcase` | `category_section` | category_grid | home, catalog |
| `*Collection` (`MenCollection`, `WomenCollection`) | `collection_<name>` | product_collection | home, category |
| `CrossSell`, `CatalogCrossSell` | `cross_sell` | product_collection | catalog, product |
| `TrendBlocks`, `CatalogTrendBlocks` | `trend_blocks` | product_collection | catalog |
| `FaqSection`, `Faq` | `faq` | faq | static pages |
| `AboutUs`, `AboutSection` | `about` | text | about page |
| `Newsletter`, `Subscribe*` | `newsletter` | form | footer area (unless it is template-level) |
| `Banner` (generic) | `banner` | banner | various |

#### Typical block.attribute_set schemas

Minimum field set by block type (used by the builder if the block is recognized but the code lacks typed data):

```yaml
# Type "banner" / "promo"
schema:
  title:        { type: string, position: 1, identifier: title }
  subtitle:     { type: string, position: 2, identifier: subtitle }
  image:        { type: image,  position: 3, identifier: image }
  cta_label:    { type: string, position: 4, identifier: cta_label }
  cta_url:      { type: string, position: 5, identifier: cta_url }

# Type "slider"
schema:
  title:        { type: string, position: 1, identifier: title }
  slides:       { type: groupOfImages, position: 2, identifier: slides }
  autoplay_interval: { type: integer, position: 3, identifier: autoplay_interval }

# Type "product_collection"
schema:
  title:        { type: string, position: 1, identifier: title }
  description:  { type: text,   position: 2, identifier: description }
  # the products themselves are attached via block_products_mn / product_blocks_mn

# Type "faq"
schema:
  title:        { type: string, position: 1, identifier: title }
  items:        { type: json,   position: 2, identifier: items }    # array of {q,a}

# Type "reviews"
schema:
  title:        { type: string, position: 1, identifier: title }
  # the reviews themselves are a separate subsystem (outside the whitelist), or texts baked into the attribute_sets jsonb
```

#### Relation rules

When a block uses `block_pages_mn` / `block_products_mn` / `product_blocks_mn`:

| Block | Attachment via |
|---|---|
| hero / slider / banner / promo / category_section on a specific page | `block_pages_mn` (page_id = the page where the block is visible) |
| related_products / reviews / recently_viewed on a product page | `block_products_mn` (product_id + page_id) |
| product_collection with an explicit fixed list of products | `product_blocks_mn` (product_id + block_id + lang_code) — one row per product |

#### `block_pages_mn.is_nested` rule

Source: the `block_pages_mn.is_nested` column — `@Column('boolean', { name: 'is_nested', default: false })`. ApiProperty describes it as: "flag that the block may automatically be added to all nested products".

So:
- **`is_nested: true`** — the block is inherited by child pages/products inside this page (a typical case is a hero / promo on a catalog category page that should also be visible on the product cards inside it).
- **`is_nested: false`** — the block is shown **only** on the specific page in `page_id`, without propagating down the hierarchy.
- **Default:** `false` (the safest — the block is visible strictly where it is attached).

**Builder heuristic** (when source data is absent and a decision must be made):
- `page_id` points at a `catalog_page` or at a section root/category page **and** the block is semantically "section-wide content" (hero / promo / category_intro / brand_story) → `is_nested: true`.
- `page_id` points at a specific content page (`about`, `delivery`, a specific product card via `block_products_mn`) → `is_nested: false`.
- If the source code explicitly mentions "inherit", "nested", "cascade", "show on children" near the block — `is_nested: true`.
- In all other cases — `false`.

This affects **only** display, not storage: an extra `true` will not corrupt data, but will create "noise" on child pages. An extra `false` hides the block where it was expected.

## Unification matrix — which pairs merge and which do not

Important: this matrix is applied **before** writing the blueprint. See rule #16 in `oneentry-invariants.md`.

### Always merge

| Pattern A | Pattern B | → Result |
|---|---|---|
| Form `login` (email, password) | Form `signup` (email, password, ...) | One `signin` form (`type: sing_in_up`) with three attribute flags in the schema (isLogin / isPassword / isSignUp) |
| `forUsers` attribute_set | Any second attribute_set with the same fields for users | One `forUsers` |
| Product statuses `online`/`active`, `published`/`active` | — | One `active` (standard) |
| Product statuses `hidden`/`draft`, `unpublished`/`draft` | — | One `draft` |

### Merge by signature (with a warning)

| Pattern A | Pattern B | Condition |
|---|---|---|
| 2 blocks with identical schemas and the same semantic name | — | merge → one blocks record + two block_pages_mn entries |
| 2 attribute_sets with identical schemas and the same type_id | — | merge → one attribute_set reused by both entities |
| `profile-page-form` and `my-account-form` | both `type: 'data'` | merge → one `profile` form |

### Do NOT merge (semantic protection)

| Pattern A | Pattern B | Why |
|---|---|---|
| Order form (`type: 'order'`) | Feedback form (`type: 'data'`) | Different form enum type |
| Contact form `/contact` | Feedback form `/feedback` | Different endpoints, different processing (even if schemas match) — keep as 2 forms with warning "schemas identical, kept separate due to different semantics" |
| `cart-add-form` | `cart-remove-form` | Different UX goals |
| Hero-slider block | Reviews block | Different semantics (even if schemas accidentally match) |
| `forBlocks` attribute_set | `forProducts` attribute_set | Different type_id = different semantic level |
| Page `/sale` | Page `/new` | Different content categories, different semantics, do not merge even when the attribute_set schemas are identical |

### Rule for paired pages with auth semantics

| URL pair | Decision |
|---|---|
| `/login` + `/signup` | One `account` (or `signin`) page — because the forms are unified. |
| `/profile` + `/my-account` | One `account` page. |
| `/cart` + `/basket` | One `cart` page. |
| `/wishlist` + `/favorites` | One `favorites` page. |

### template_previews / templates

Included only if the source code has multi-template markup (for example, a template engine for emails, pages). By default the blueprint does without them (templates are all nullable FKs).

### product_relations_templates

Included only if the code has an obvious "related products / buy together" feature with configurable rules. By default — **do not include**.

## Slugs for standard pages (recommendation)

If the project is a typical e-commerce, it is recommended to create at least:

| slug | parent_id | Purpose |
|---|---|---|
| `root` | null | Home |
| `cart` | `@page.root` | Cart |
| `account` | `@page.root` | Account area |
| `favorites` | `@page.root` | Favorites |
| `catalog` | `@page.root` | Root catalog |
| `<category>` (e.g. `women-clothing`) | `@page.catalog` | Category |

Non-e-commerce: only `root` and themed sections following your own logic.
