# Coverage checklist — what must be verified when assembling the blueprint

> **⚠ Universality note.** Examples below frequently use fashion-shop terms (clothing / shoes / bags / women / men) because that is the reference test project. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop (`product/sku/brand/category`), restaurant (`menu-item/dish/cuisine/section`), beauty salon (`service/master/treatment/duration`), hotel (`room/suite/amenity`), EdTech (`course/lesson/level`), corporate site (`page/department/team`), personal cabinet (`section/setting/subscription`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is a self-contained reference.** Agents use only this file.
>
> ⚠ **Related critical rules** (a violation produces a blueprint that looks catastrophically illogical in the admin UI):
> - `rules/general-types.md` — correct `general_type_id` for pages/blocks/forms (mapping 4=catalog/17=common/18=common_block/10=product_block/11=form/21=order)
> - `rules/users-architecture.md` — minimal forUsers + Data Submission forms for extended user data

The purpose of this file: give inspector / mapper / builder / validator an explicit checklist of what must end up in the blueprint, so there are no systemic omissions. Each item is mandatory unless explicitly marked optional.

---

## 1. Product attributes (`forProducts.schema`)

### 1.1 Base fields (mandatory for any e-commerce)
- `title`, `sku` (isSku), `price` (isPrice), `sale_price`, `preview` (image, isProductPreview), `gallery` (groupOfImages), `brand`, `description` (text), `in_stock` (radioButton), `colors`, `sizes`, `material`, `style`.

### 1.2 Category-specific fields (clothing)
If the project has a clothing category, also verify:
- `clothing_type`, `season`, `fit`, `silhouette`, `collar`, `neckline`, `sleeve`, `hood`, `pockets`, `lining_material`, `material_origin`, `material_finish`.

### 1.3 Category-specific fields (shoes)
If the project has shoes:
- `shoe_type`, `upper_material`, `sole`, `sole_material`, `insole_material`, `closure`, `heel_height`, `width`, `technologies`, `is_waterproof`.

### 1.4 Category-specific fields (bags)
If the project has bags:
- `bag_type`, `bag_size`, `strap_width`, `frame`, `closure_type`, `inner_pockets`, `outer_pockets`, `volume_liters`.

### 1.5 Accessories
- `accessory_type`, `gender_target`, `gift_packaging_available`.

### 1.6 Social / system
- `rating` (real, min=0, max=5), `rating_count` (integer), `views_count` (integer), `is_featured` (radioButton), `is_new` (radioButton), `tags` (list, multiple).

**Mapper rule:** read **at least 3 category files** (e.g. `data/women-clothing.ts`, `data/women-shoes.ts`, `data/women-bags.ts`) and **union** all fields found in Product objects. Do not limit yourself to a single base `Product` interface from a barrel file.

---

## 2. User attributes — see `rules/users-architecture.md` (single source of truth)

⚠ **Policy revised 2026-05-31** after v3 import revealed three failure modes:
1. `forForms_checkout` carried duplicated user-profile fields (`email`, `phone`, `address_*`, etc.).
2. `forUsers` exploded to 35 fields and made the user-card UI unusable.
3. `forUserGroups` was always empty when the project actually used group-level discount/VIP logic.

The current policy:

### 2.1 `forUsers` — NARROW (~10 fields)

Allowed in `forUsers.schema`: **auth (email, password, sign_up) + base identity (first_name, last_name, phone, gender, birthday, avatar)**. Nothing else.

Anything else (addresses, loyalty, preferences, subscriptions, consents, social, referral, saved_cards) is **forbidden** in `forUsers.schema` — see §2.2.

### 2.2 Extended profile data → Account-section data-forms

Each interactive section in the project's `account/` directory (typically `src/app/pages/account/**/*Section.tsx`) with real form signals (`<form>`, `onSubmit`, `useForm`, ≥2 inputs) → a dedicated `forForms_<section>` set + a `form_module_config` row with `module_id: 9` (Users module).

Typical mapping:
- `MyDataSection` → `forForms_my_data` (Personal Info + addresses).
- `SubscriptionsSection` → `forForms_subscriptions` (newsletter/SMS/push toggles + consents).
- `LoyaltySection` (only if has editable form) → `forForms_loyalty`.
- `ServiceMaintenanceSection` → `forForms_service_request` (already covered).
- `FeedbackSection` → `forForms_feedback` (already covered).
- `ReferSection` → `forForms_refer_a_friend` (already covered).

Read-only sections (`HistorySection`, `MyOrdersSection`, `WishlistSection`, `WaitingListSection`, `LoyaltyCard` display widget, `BonusesSection`) → **NO form**.

### 2.3 `forForms_checkout` — NARROW (order-specific fields only)

Allowed: **delivery + payment + order extras** (delivery_method, delivery_instructions, payment_method, card_*, promo_code, agreed_terms, save_address, gift_wrap, order_notes).

**Forbidden** in `forForms_checkout.schema`: `email`, `phone`, `full_name`, `first_name`, `last_name`, `address_line1`, `address_line2`, `city`, `country`, `postcode` — they live in `forUsers` + `forForms_my_data`. The frontend reads user identity/addresses from those sources at checkout time.

Guest checkout fallback: **Pattern A** (default) — add `guest_*` prefixed fields to `forForms_checkout`. **Pattern B** — only when inspector finds a dedicated `app/guest-checkout/` route → emit separate `forForms_checkout_guest`.

### 2.4 `forUserGroups` — fields when groups carry business logic

If inspector finds signals (`userGroup`, `loyaltyTier`, `default_discount`, `vip_status`, B2B/wholesale, group-level permissions in code) → emit fields: `default_discount` (real), `vip_status` (list), `allowed_payment_methods` (json), `allowed_delivery_methods` (json), `min_order_amount` (real), `max_credit_limit` (real), `group_meta` (json).

Otherwise → keep `schema: {}` (valid).

### 2.5 `form_module_config` bindings for Users-module forms

Every Account-section form must have a `form_module_config` row with `module_id: 9` (Users module). Without it the admin won't see the form in the Users module's screen and submissions won't surface in user cards.

Full whitelist, source signals, anti-patterns and field-level specs — see `rules/users-architecture.md` (single source of truth).

---

## 3. Pages — hierarchy and anti-patterns

### 3.1 Required pages (if present in the project — must be carried over)

**The inspector must** scan `app/**/page.tsx` (Next.js App Router) or `pages/*.tsx` (Pages Router) and **return ALL** routes found to the mapper. The mapper must not skip existing routes.

Particularly often missed:
- ⚠ `checkout/confirmation` — final step of the funnel after payment
- ⚠ `download/*` — internal download pages
- ⚠ `not-found`, `error`, `offline` — technical (can be omitted)

**Base set for e-commerce:**
- **Funnel:** `cart`, `checkout`, `checkout-delivery`, `checkout-payment`, **`checkout-confirmation`**.
- **Account:** `account` (root for the user area).
- **Catalog:** root catalog + promo category pages (see section 3.2).
- **Info:** `about-us`, `contact`, `faq`, `terms`, `privacy-policy`, `delivery-info`, `returns` — usually via a generic InfoPage.

### 3.2 ⚠ CRITICAL: `page_url` is ALWAYS a single slug, with NO `/`

OneEntry builds the URL through the **`parent_id` hierarchy**, not through slashes in `page_url`. Each `page_url` is **one segment** without `/`.

❌ **Do not do this:**
```json
{"identifier": "women-clothing", "page_url": "women/clothing", "parent_id": "@page.root"}
```
The real URL will be `/women%2Fclothing` (encoded), or routing breaks.

✅ **Correct — hierarchy via parent:**
```json
{"identifier": "women",          "page_url": "women",    "parent_id": "@page.root"}
{"identifier": "women-clothing", "page_url": "clothing", "parent_id": "@page.women"}
```
Real URL: `/women/clothing` through the correct hierarchy.

**Mapper algorithm:**
1. Get from the inspector the list of real routes (e.g. `women/clothing`, `women/shoes`, `men/clothing`...).
2. Extract every **unique parent-level segment** (`women`, `men`, `checkout`).
3. Create a **promo page for each parent segment** (as a hub page). For catalog, promo pages usually go with `attribute_set: forPages`, with a title from the project (often from breadcrumbs).
4. Place children under each parent with `page_url` = only the last segment.

### 3.3 Anti-pattern: sub-categories as pages

**❌ Do not do this:**
```
women → women-clothing → women-clothing-coats
                       → women-clothing-shirts
                       → ... (50+ sub-categories)
```

If in the project `WomenClothingPage.tsx` renders **one page with a filter** by clothing type — this is a **URL parameter** or a `list` attribute value, not a separate page.

**✅ Correct:**
```
women → women-clothing  (one page)
```
Sub-categories go into `forProducts.schema.clothing_type.listTitles`.

**Mapper heuristic:**
- Physical file `app/women/clothing/coats/page.tsx` → create a page.
- Hard-coded filter inside `WomenClothingPage` → NOT a page, a listTitle entry on an attribute.
- More than 20 pages at depth 3+ in a single branch — almost certainly an anti-pattern.

### 3.4 Parent-child hierarchy
- `root` (depth=0) — mandatory
- First-level categories — `cart`, `checkout`, `account`, `women`, `men`, `info` etc. (depth=1)
- Sub-categories — `women-clothing`, `checkout-delivery` (depth=2)
- Info pages under `info` — depth=2

### 3.5 Identifier must match the real slug

If `INFO_SLUGS` (or `pageRegistry`) contains the slug `sitemap` — the identifier in the blueprint **must be `sitemap`**, not `sitemap-page`. Otherwise the OneEntry Platform frontend will not find the page on lookup.

A clash between an identifier and another entity (e.g. the project has both a `sitemap` page and a `sitemap.ts` route handler) — keep the identifier as `sitemap`, do not add a suffix.

---

## 4. Blocks

### 4.1 What counts as a block
- **YES:** Hero, Slider, Banner, CategoryGrid, Promo, Collection (best/new/sale), TrendBlocks, CrossSell, Reviews, FAQ, Stores, Loyalty card visualisation, Featured-products, RelatedProducts.
- **NO:** Header, Footer, Navigation, Sidebar (these are template-level), modals (LoginModal, MiniCart, QuickViewModal — UI overlays), SkeletonLoaders, ErrorBoundary, Provider wrappers.
- **GREY AREA:** account-area sections (BonusesSection, MyOrdersSection etc.) — **usually NOT blocks**, they are page sections attached to one page. Do not multiply them.

### 4.2 Attribute_sets for different block types

The minimum required ones:
- `forBlocks_default` — title + description.
- `forBlocks_slider` — title + slides (groupOfImages) + autoplay_interval.
- `forBlocks_banner` — title + subtitle + image + cta_label + cta_url.
- `forBlocks_collection` — title + description + cta_url + product_refs (list).
- `forBlocks_category_grid` — title + items (json array with category+image).
- `forBlocks_reviews` — title + min_rating filter.
- `forBlocks_faq` — title + items (json array of question+answer).
- `forBlocks_loyalty` — if there is a LoyaltyCard block: tier_name, points, next_level_amount, perks.

---

## 5. Forms — only those actually in the project

⚠ **IMPORTANT — rule changed.** Previously the mapper created forms from the checklist "if the project has a similar page". This led to forms appearing that **physically don't exist** in the code (Contact, Address book, Refer-friend without a form — only text sections).

**New rule:** the mapper creates a form **only if the code actually contains a `<form>`, an `onSubmit`, or 2+ `<input>` elements** in an identifiable component. Do not create "by analogy" if there is only a text info page or a display-only showcase section.

### 5.1 Form catalog with "when to create" markers

**`signin`** (always): required for authentication, a OneEntry invariant. Always create it, even if there is no LoginModal in the code — add it as a stub.

**`checkout`** (when project has a checkout/cart flow): a **single** form of type `order` covering delivery + payment + extras. Never split into `checkout_address` / `checkout_payment` — that's an anti-pattern (see §2.3 + `rules/users-architecture.md` "Checkout = ONE form, not several").

The rest **are created only if there is an explicit source** (a component with real form signals — `<form>` / `onSubmit` / `useForm` / ≥2 inputs):

| Form | type | Module binding (form_module_config) | Marker "exists in project" | Fields |
|---|---|---|---|---|
| `checkout` | `order` | Orders (via orders_storage.form_id) | DeliveryPage + PaymentPage (merge into one!) — see §2.3 | delivery_method, delivery_instructions, payment_method, card_*, promo_code, agreed_terms, save_address, gift_wrap, order_notes. **Plus** `guest_*` fallback fields if Pattern A applies. **NO** email/phone/full_name/address_* — those come from `forUsers` + `forForms_my_data`. |
| `my_data` | `data` | **Users (id=9)** | `MyDataSection.tsx` or `EditProfile*.tsx` with `<form>` / inputs for first_name/phone/address | first_name, last_name, phone, gender, birthday, addresses (json — array of address objects), default_address_id |
| `subscriptions` | `data` | **Users (id=9)** | `SubscriptionsSection.tsx` / `PreferencesForm.tsx` / `ConsentDialog.tsx` with toggles / inputs | pref_email_newsletter, pref_sms_notifications, pref_push_notifications, pref_order_updates, pref_new_arrivals, pref_sale_alerts, newsletter_frequency (list), consent_marketing, consent_data_processing, consent_cross_border |
| `loyalty` | `data` | **Users (id=9)** | `LoyaltySection.tsx` **with an editable form** (skip if read-only display) | loyalty_card_number, preferred_store (list), preferred_communication (list), preferred_categories (list, multiple) |
| `service_request` | `data` | **Users (id=9)** | `ServiceMaintenanceSection.tsx` with a form for a service request | category (list), description (text), attachments (groupOfImages) |
| `feedback` | `data` | **Users (id=9)** | `FeedbackSection.tsx` or `Feedback*Form.tsx` with `<textarea>` + `<input>` | rating, category (list), order_id, message (text), attachments |
| `refer_a_friend` | `data` | **Users (id=9)** | `ReferSection.tsx` or `Refer*Form.tsx` with `<input type="email">` for a friend (NOT just rendering an existing referral code!) | friend_email, message (text) |
| `review` | `rating` | (rating module, not Users) | `WriteReviewModal.tsx` or `*Review*Form.tsx` with `<form>`/`<textarea>`/rating | rating (integer 1-5), title (string), body (text), recommend (radioButton), verified_purchase (radioButton) |
| `contact` | `data` or `email` | (not module-bound) | **A real form** in `Contact*` (NOT just an info page with text!) — needs `<input name="email">` + `<textarea>` | name, email, subject (list), message (text), attachments |
| `newsletter` | `data` | (not user-specific) | In `Footer.tsx` or similar there is `<input type="email">` + `subscribe`/`onSubmit` | email |
| `reserve_in_store` | `data` | (per-product, not Users) | `ReserveInStoreModal.tsx` with `<input>` elements | product_id, store_id, size (list), color (list), date (date), full_name, phone |
| `notify_back_in_stock` | `data` | (per-product, not Users) | `NotifyBackInStock*.tsx` or `WaitingListSection` with `<input email>` | email, product_id, size, color |
| `track_order` | `data` | (not module-bound) | In the `track-order` info page OR in `TrackOrder*.tsx` there is an `<input>` for order_number | order_number, email |
| `comments` | `data` | (per-page, not Users) | `CommentsSection` under a product/article | author_name, message |

### 5.1.1 ❌ Forbidden form identifiers (anti-patterns)

These were valid in older revisions of this checklist. They are now **anti-patterns** — mapper must NOT emit them; route to the right home:

| Forbidden identifier | Goes to |
|---|---|
| `profile_edit` / `edit_profile` | `my_data` |
| `change_password` | `users_auth_providers` + `password` field in `forUsers` |
| `address_book` | `addresses` field inside `forForms_my_data.schema` |
| `payment_methods` | out-of-whitelist (`payment_accounts`) |
| `subscriptions_pref` | `subscriptions` |
| `consents` | `subscriptions` (consent_* fields) |
| `social_connections` | additional providers in `users_auth_providers` |
| `loyalty_card_request` | `loyalty` (or skip if read-only) |
| `promo_code` | a FIELD inside `forForms_checkout.schema`, not a form |
| `checkout_address`, `checkout_payment`, `checkout_confirmation` | merged into the single `checkout` form |

### 5.2 Mapper algorithm — "create or not"

```python
def should_create_form(form_id: str, project_files: dict[str, str]) -> bool:
    """project_files: {filename → content}"""
    if form_id == 'signin':
        return True  # invariant: always

    markers = COVERAGE_MARKERS[form_id]  # from table 5.1
    for marker_pattern in markers:
        for fname, content in project_files.items():
            if marker_pattern.matches(fname):
                # Extra check: is there really a form?
                if has_form_signals(content):
                    return True
    return False

def has_form_signals(content: str) -> bool:
    """True if the file actually contains a form, not just text."""
    has_form_tag = '<form' in content
    has_on_submit = 'onSubmit' in content
    has_use_form = 'useForm' in content
    input_count = content.count('<input ')
    textarea_count = content.count('<textarea')
    # Minimum: 2 inputs/textareas OR <form>/onSubmit
    return has_form_tag or has_on_submit or has_use_form or (input_count + textarea_count >= 2)
```

**If `should_create_form()` returned False — DO NOT create.** Better to skip a form than add a fake one.

### 5.3 Anti-pattern: empty form

**❌ Do not leave a form `attribute_set` with `schema: {}`.** If a form is in the blueprint — it MUST have at least 1 field (except signin, which has at least 3 fields by invariant).

The **validator** checks (S22): for each form in `tables.forms[]`, find its attribute_set and assert that `schema` is non-empty.

### 5.4 Anti-pattern: logical duplication

- `change_password` — NEVER a separate form. It's a `users_auth_providers` endpoint, period.
- `address_book` — NEVER a separate form. Addresses live as a `json`-typed `addresses` field inside `forForms_my_data.schema`.
- `checkout` — NEVER split. One order = one form. Address & contact at checkout come from `forUsers` + `forForms_my_data` (or `guest_*` fallback for guest checkout).
- `forForms_checkout` MUST NOT duplicate user-profile fields — see §2.3.

The **validator** adds S38 — every form must have a source file noted in `mapped.yaml`. If the source is missing or empty — WARNING.

---

## 6. Validators (`rules` + `additionalFields` in schema items)

### 6.0 🚨 CORE RULE — user-input attributes MUST have validators AND UX hints

**Every attribute that accepts data entered by an end-user in the storefront app MUST have BOTH `rules` AND `additionalFields`.** Source of truth: [`agents_datasets/rules/attribute-validators.md`](attribute-validators.md). This applies to all `forUsers` + all `forForms_*` attribute sets. Admin-input sets (`forProducts_*`, `forPages`, `forBlocks_*`) get obvious length/range validators + helperText where it improves admin UX.

Two independent requirements:

- **`rules`** — constraints that block submit (pattern, minLength, maxLength, minValue, maxValue, minDate, maxDate, required).
- **`additionalFields`** — UX hints (NOT validation): `placeholder` example inside the empty input, `helperText` permanent description under the input, `mask` auto-formatting for fixed-shape values (phone/card/expiry/cvv), `prefix`/`suffix` for currency/units, `step` for numeric inputs, `tooltip` for extended hover help, `autoComplete` HTML hint (browser-saved values), `inputType` override (email/tel/url/number/password). **`placeholder` is required for every user-input string/number/date attribute** — bare input boxes hurt UX. **`helperText` is required wherever `rules` are non-trivial** so the user understands WHY their input was rejected.

Enforcement is automated via `post-mapper-fixer.py::enrich_attribute_validators(data)` (runs as Fix 8 in `fix_mapped`). The fixer applies the canonical table by `identifier` with set-default semantics (never overwrites hand-set keys — only fills missing keys). The canonical table covers ~68 identifiers with both `rules` and `additionalFields` populated.

### 6.1 Required validators (subset — see `attribute-validators.md` for full ~50 entries)
| Field | rules + additionalFields |
|---|---|
| `email` | `pattern: "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"`, `maxLength: 254` |
| `password` | `minLength: 8`, `maxLength: 128` |
| `phone` | `additionalFields.mask: "+## ### ### ####"`, `additionalFields.placeholder: "+1 555 123 4567"` |
| `first_name`/`last_name` | `minLength: 1`, `maxLength: 50` |
| `full_name` | `minLength: 2`, `maxLength: 100` |
| `birthday`/`date_of_birth` | `minDate: "1900-01-01"` |
| `address_line1` | `minLength: 1`, `maxLength: 200` |
| `city` | `minLength: 1`, `maxLength: 100` |
| `country` | `minLength: 2`, `maxLength: 60` |
| `postcode`/`zip`/`zip_code` | `minLength: 3`, `maxLength: 12` |
| `card_number` | `pattern: "^[0-9]{13,19}$"`, `additionalFields.mask: "#### #### #### ####"` |
| `card_expiry` | `pattern: "^(0[1-9]\|1[0-2])/[0-9]{2}$"`, `additionalFields.mask: "##/##"`, `placeholder: "MM/YY"` |
| `card_cvv` | `pattern: "^[0-9]{3,4}$"`, `additionalFields.mask: "####"` |
| `agreed_terms`, `consent_data_processing` | `required: true` |
| `price` | `minValue: 0`, `maxValue: 9999999` |
| `rating` | `minValue: 0`, `maxValue: 5` |
| `title` | `minLength: 1`, `maxLength: 200` |
| `description` | `maxLength: 5000` |
| `message`/`notes`/`feedback`/`review_text` | `maxLength: 2000` |
| `sku` | `pattern: "^[a-zA-Z0-9_-]+$"`, `minLength: 1`, `maxLength: 50` |
| `cta_url`/`website`/`canonical` | `pattern: "^(https?://\|/)[^\\s]+$"`, `maxLength: 500` |
| `meta_title` | `maxLength: 70` |
| `meta_description` | `maxLength: 160` |
| `friend_email`/`friend_emails` | `pattern: "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$"` |

### 6.2 Validator coverage check (added 2026-05-31)

- **S63 (a) Rules coverage** — for each user-input attribute set (forUsers + forForms_*), measure `attrs_with_rules / attrs_total`. If a known-critical field (`email`, `phone`, `password`, `card_*`, `birthday`, `postcode`, `address_line1`, `city`, `country`) is present without `rules` → ERROR. If overall coverage < 80% → WARN.
- **S63 (b) AdditionalFields coverage** — for the same user-input sets, measure `attrs_with_additionalFields / attrs_total`. If a known-critical field is present without `additionalFields.placeholder` → ERROR. If a user-input string/text/number/date attribute has no `placeholder` → WARN. If overall coverage < 60% → WARN.
- **S63 (c) HelperText for non-trivial rules** — if an attribute has a `rules.pattern` (regex) or `rules.minLength` ≥ 5 or `rules.required: true`, it MUST have `additionalFields.helperText`. Otherwise WARN.

Critical-field detection: blueprint-validator scans the schema by `identifier`; missing `rules` AND missing `additionalFields.placeholder` on a critical field = ERROR.

Run `python3 agents_datasets/scripts/post-mapper-fixer.py <mapped.yaml> <project_root>` to auto-enrich before re-building the blueprint. The fixer fills ~68 known identifiers from the canonical table in `attribute-validators.md`.

---

## 7. What the validator must check

| Check | Severity |
|---|---|
| **S22** Empty form attribute_set (`schema: {}`) — except `forUserGroups` and `forAdmins` which are intentionally empty in many projects | ERROR (a form with no fields is meaningless) |
| **S23** Page subcategory explosion (>20 pages at depth ≥3 in a single branch) | WARNING (anti-pattern) |
| **S24** Checkout flow incomplete (there is a `cart`/`checkout` page, but no `checkout` form of type `order` with delivery + payment fields) | WARNING |
| **S25** Addresses NOT present in `forForms_my_data.schema.addresses` (if there is a `checkout` or `account` page) | WARNING (frontend has nowhere to read addresses at checkout) |
| **S26** Required validators missing (email without pattern, password without minLength) | WARNING |
| **S42** `forUsers.schema` has >15 fields | WARNING. ERROR if any of {`addresses`, `address_line1`, `loyalty_*`, `pref_*`, `consent_*`, `social_*_connected`, `saved_cards`, `referral_code`, `bonuses_balance`} are present — these must move to account-section forms. |
| **S49** Anti-pattern form identifier present (`profile_edit`, `change_password`, `address_book`, `payment_methods`, `subscriptions_pref`, `consents`, `social_connections`, `loyalty_card_request`, `promo_code`, `checkout_address`, `checkout_payment`, `checkout_confirmation`) | WARNING — see §5.1.1 for the correct home. |
| **S51** `forForms_checkout.schema` contains user-profile fields (`email`, `phone`, `full_name`, `first_name`, `last_name`, `address_line1`, `address_line2`, `city`, `country`, `postcode` — without `guest_` prefix) | WARNING — duplicates `forUsers` / `forForms_my_data`. |
| **S52** Account-section form (`my_data`, `subscriptions`, `loyalty`, `service_request`, `feedback`, `refer_a_friend`) exists in `tables.forms` but has no `form_module_config` row with `module_id: 9` | WARNING — admin won't see the form in the Users module. |

These checks are **lower criticality** than S1-S21 (they will not produce 23505 on import, but indicate an incomplete blueprint).

---

## 8. New whitelist entities (post 2026-05-21)

Six tables moved INTO the 24-table whitelist on 2026-05-21 and now have explicit coverage requirements:

### 8.1 `collections` + `collection_rows`

**When to emit:** project contains an entity that is a flat localised list — FAQ, City/Store, Brand/Vendor, Partner, Testimonial-as-list.

**Coverage rules:**
- One `collection` per logical group (e.g. one for `faq_general`, another for `faq_shipping`).
- Each `collection_row` carries `lang_code` and `form_data` (jsonb with the row payload).
- `collections.identifier` is the natural key — loader upserts. Re-import is safe.
- `collection_rows` skip-if-parent-has-children: on re-import, existing rows survive.
- See `agents/entity-mapper.md` Step 9.8 for the inline emission template.

### 8.2 `form_module_config`

**When to emit:** a form must be advertised inside an admin module (Users / Catalog / Orders) so the admin sees it in the module's forms list.

**Coverage rules:**
- For the `signin` form bind to module 9 (Users): `{ module_id: 9, form_id: '@form.signin', is_global: true }`.
- For order checkout forms — usually the `orders_storage.order_form_id` already covers attachment; emit `form_module_config` only when explicit "this form appears in module X" semantics are required.
- Composite UNIQUE `(module_id, form_id)` — builder Step 13.5 dedupe rules MUST include this pair.
- See `agents/entity-mapper.md` Step 9.9 for the inline emission template.

### 8.3 `form_data`

**When to emit:** never from greenfield blueprint. `form_data` rows are runtime submissions written by users via the public form API; blueprint should NOT seed historical submissions.

If the table key appears in your blueprint — that's almost certainly a mapper bug. The validator should flag it.

### 8.4 `user_permissions` + `user_group_permissions_mn`

**When to emit:** project has a custom permission scheme (typically inferred from `agents_datasets/rules/users-architecture.md` use-cases — multi-role app with non-default permissions).

**Coverage rules:**
- `user_permissions` natural key = `(path, section)`. ~112 rows are preseeded by cms migrations — do NOT regenerate identifiers for those, just reuse via `(path, section)` and loader upserts.
- `user_group_permissions_mn` natural key = `(group_id, permission_id)`; UNIQUE constraint via `@Index({ unique: true })`. Within one blueprint, dedupe per `(group_id, permission_id)` defensively.
- See `agents/entity-mapper.md` Step 2 "Permissions for user_groups — emit via blueprint" for the inline template.

---

## Summary for agents

**Inspector** — walks all product categories (at least 3 files), all account sections, all modals/forms. Does not stop at a single base interface.

**Mapper** — applies this checklist and **always** fills missed standard fields (even if not found explicitly in code, but the project clearly implies them — there is a checkout → address fields are needed).

**Builder** — does not write a blueprint with empty forms. Self-check S22 at step 13.6.

**Validator** — runs S22-S26 (as WARNINGs) and highlights gaps in `validation.md`. This does not block the load, but tells the user what to follow up on.
