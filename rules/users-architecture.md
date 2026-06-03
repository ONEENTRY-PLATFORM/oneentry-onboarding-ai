# `forUsers` and forms architecture in OneEntry

> **⚠ Universality note.** Examples below may reference fashion-shop terms (clothing / shoes / bags / women / men) — they are **illustrative**. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop, restaurant (`menu-item/dish/cuisine`), beauty salon (`service/master/treatment`), hotel (`room/suite/amenity`), EdTech (`course/lesson`), corporate site (`page/department/team`), personal cabinet (`section/setting`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is hand-written.** It describes the correct user data model.
> - Rewritten 2026-05-20 after the forUsers-minimal + Data Submission anti-pattern was discovered.
> - **Rewritten again 2026-05-31** after v3 import showed three new failure modes:
>   1. `forForms_checkout` carried user-profile fields (`email`, `phone`, `full_name`, `address_line1/2`, `city`, `country`, `postcode`, `save_address`) duplicating `forUsers`.
>   2. `forUsers` exploded to 35 fields (loyalty, preferences, subscriptions, consents, social, referral, saved_cards) — the admin user-card became unusable.
>   3. `forUserGroups` was emitted as empty `{}` only to satisfy FK — a missed opportunity for group-level fields when the project actually used groups for discounts / VIP / permissions.

## Core principle: forms ≠ user editing — BUT user data is split into focused forms per Account section

In OneEntry:

- A **form** (`forms` table) = a **submission** (request / review / contact / personal-info edit / preferences update) → a record in `form_data` table → optional processing (db / email / script).
- A **user** = an entity in the `users` table with attributes from `forUsers` (`attribute_set` type_id=6). Auth + base identity fields are stored **directly in `users.attributes_sets` jsonb**.
- **Extended user data** (addresses, loyalty, preferences, subscriptions, consents, social, referral, saved_cards) lives as **dedicated data-forms attached to the Users module** via `form_module_config` (`module_id: 9`), NOT as fields on `forUsers`.

See `agents_datasets/ClaudeInfos/03-form-submission.md`:

> A form = submit + processing (email, DB, script) + moderation statuses.
> "Registration / login / **password change**" — handled via `users_auth_providers`, not a separate form.

## ⚠ `forUsers` — NARROW: auth + base identity ONLY (~10 fields)

`forUsers` is the **minimal core** user schema: only the fields every user has and which the auth/identity layer needs to operate. **All other personal data lives in Account-section forms** attached to the Users module (see §"Account-section data-forms").

### Allowed `forUsers.schema` fields (whitelist)

```yaml
attributes_sets:
  - id: '@aset.forUsers'
    type_id: 6   # forUsers
    schema:
      # --- Auth (always, system flags drive login flow) ---
      email:        { type: string, isLogin: true,    rules: { pattern: "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$" } }
      password:     { type: string, isPassword: true, rules: { minLength: 8, maxLength: 128 } }
      sign_up:      { type: radioButton, isSignUp: true }   # toggle for sing_in_up flow

      # --- Base identity (rendered in user card header / profile menu / orders / receipts) ---
      first_name:   { type: string,      rules: { minLength: 1, maxLength: 50 } }
      last_name:    { type: string,      rules: { minLength: 1, maxLength: 50 } }
      phone:        { type: string,      additionalFields: { mask: "+## ### ### ####" } }
      gender:       { type: list,        listTitles: { en_US: { female: 'Female', male: 'Male', other: 'Other' } } }
      birthday:     { type: dateTime,    rules: { minDate: "1900-01-01" } }
      avatar:       { type: image }
```

**~10 fields total.** No exceptions: anything NOT in this whitelist must NOT be added to `forUsers.schema`.

### ❌ What MUST NOT be in `forUsers.schema`

| Field category | Where it goes instead |
|---|---|
| `addresses`, `address_line1/2`, `city`, `country`, `postcode` (any address-book CRUD) | **`forForms_my_data`** (Personal Info / address book in Account → My Data) |
| `pref_email_newsletter`, `pref_sms_notifications`, `pref_push_notifications`, `pref_order_updates`, `pref_new_arrivals`, `pref_sale_alerts`, newsletter frequency, etc. | **`forForms_subscriptions`** (Account → Subscriptions) |
| `consent_data_processing`, `consent_marketing`, `consent_cross_border` | **`forForms_subscriptions`** (consents are part of preferences toggle) |
| `loyalty_card_number`, `loyalty_status`, `loyalty_points`, `loyalty_total_purchases`, `loyalty_next_level_amount` | **`forForms_loyalty`** (Account → Loyalty Card) — only if the project has an editable loyalty profile form. If loyalty is read-only display → no form, data comes from a separate backend service. |
| `social_google_connected`, `social_apple_connected`, `social_facebook_connected` | **Out-of-whitelist** (OAuth flow via `users_auth_providers` with additional providers). Do not create a form for "social link toggles" — they're side-effects of the OAuth flow. |
| `saved_cards`, payment methods | **Out-of-whitelist** (`payment_accounts` table — manual admin setup or external PSP integration). Do not put in forUsers or in any form. |
| `referral_code` (the user's own permanent code) | **Out-of-whitelist** (referral programs use the `discounts` / `discount_coupons` module). The **act** of inviting a friend goes into `forForms_refer_a_friend`. |
| `bonuses_balance`, `wallet_balance` | **Out-of-whitelist** (bonus engine — read-only display in Account section). |

If inspector reports such fields → mapper routes them to the right data-form (or warns "out-of-whitelist") instead of adding to `forUsers.schema`.

## Account-section data-forms

When the project's `account/` directory contains **interactive sections with real `<form>` / `onSubmit` / inputs**, each section becomes a dedicated data-form. The form is attached to the **Users module** via `form_module_config` (`module_id: 9`) so the admin sees and configures it in the Users module's forms list.

### Section → form mapping (typical Next.js shop)

> ⚠ **Stack-specific patterns.** The `*.tsx` component-name patterns in the tables below assume a React / Next.js project. For other stacks the inspector substitutes the file convention and parses analogous signals:
> - **Vue** → `*.vue` SFCs (template + `<form>` / `v-model` / `@submit`); section names follow PascalCase identically (`MyDataSection.vue`).
> - **Angular** → `*.component.ts` + `*.component.html`; sections are typically `my-data.component.ts`.
> - **Svelte / SolidJS** → `*.svelte` / `*.tsx` with framework-specific form bindings.
>
> The **mapping table** below (section → form identifier → form type → notes) is universal — the `my_data` / `subscriptions` / `loyalty` / `feedback` form identifiers are OneEntry-side conventions, not React-side. Only the source-signal column ("Account section component") is stack-specific. Replace the file extension and pattern matcher for non-React stacks; keep the form identifiers as is.

Inspector walks `src/app/pages/account/**/*Section.tsx` (or `src/views/account/**` / `src/components/account/**` depending on convention; for Vue/Angular projects — the analogous glob). For each section with form signals:

| Account section component | Form identifier | type | processing_type | Notes |
|---|---|---|---|---|
| `MyDataSection.tsx` / `EditProfile*.tsx` / `AddressBook*.tsx` | `my_data` | `data` | `db` | Personal Info + address book. Inputs: first_name, last_name, phone, gender, birthday, **addresses (json — array of address objects)**, default_address_id. |
| `SubscriptionsSection.tsx` / `PreferencesForm.tsx` / `ConsentDialog.tsx` | `subscriptions` | `data` | `db` | Newsletter / SMS / Push toggles, frequency, GDPR consents. Inputs: pref_email_newsletter, pref_sms, pref_push, pref_order_updates, pref_new_arrivals, pref_sale_alerts, newsletter_frequency (list), consent_marketing, consent_data_processing. |
| `LoyaltySection.tsx` / `LoyaltyProfileForm.tsx` | `loyalty` | `data` | `db` | **Only if the section contains an editable form.** If it's purely a card display + points balance → skip (no form). Inputs (when present): loyalty_card_number, preferred_store (list), preferred_communication (list). |
| `ServiceMaintenanceSection.tsx` | `service_request` | `data` | `db` or `email` | Already covered. Inputs: category (list), description (text), attachments (groupOfImages). |
| `FeedbackSection.tsx` | `feedback` | `data` | `db` | Already covered. Inputs: rating, category (list), order_id (optional), message (text), attachments. |
| `ReferSection.tsx` / `ReferFriendForm.tsx` | `refer_a_friend` | `data` | `email` | Already covered. Inputs: friend_email, message (text). |

### Read-only Account sections — NO form

These sections **only display** data fetched from APIs. They do NOT produce form submissions and therefore do NOT generate a `forForms_*` set:

- `HistorySection.tsx` / `MyOrdersSection.tsx` → fetches `/api/content/orders/me` — read-only.
- `WishlistSection.tsx` → uses `user_activity_events` (out-of-whitelist) — read-only display.
- `WaitingListSection.tsx` → similar (notify-back-in-stock submissions go into a separate `notify_back_in_stock` form on the PDP, not here).
- `LoyaltyCard.tsx` (display widget) → read-only.
- `BonusesSection.tsx` → read-only balance + transactions.

If inspector flags one of these as a "form" by mistake (e.g. it contains an `<input>` for a search filter) → mapper REJECTS via the same `has_form_signals + signin` rule used elsewhere (need `<form>`, `onSubmit`, `useForm`, or ≥2 inputs that aren't just filter widgets).

### Attaching Account-section forms to the Users module

For **every** Account-section form, mapper MUST emit a `form_module_config` row binding the form to the Users module (`module_id: 9`). Without it the admin won't see the form in the Users module screen and the data won't appear in the user card.

```yaml
tables:
  form_module_config:
    - module_id: 9
      form_id: '@form.signin'          # already covered by signin invariant
      is_global: true
      is_closed: false
      is_moderate: false
      view_only_user_data: false
      comment_only_user_data: false
      is_rating: false

    - module_id: 9
      form_id: '@form.my_data'         # Account → My Data
      is_global: true
      is_closed: false
      is_moderate: false
      view_only_user_data: false
      comment_only_user_data: false
      is_rating: false

    - module_id: 9
      form_id: '@form.subscriptions'   # Account → Subscriptions
      is_global: true
      is_closed: false
      is_moderate: false
      view_only_user_data: false
      comment_only_user_data: false
      is_rating: false

    # ... same for loyalty / service_request / feedback / refer_a_friend if present
```

⚠ **Composite UNIQUE `(module_id, form_id)`** is enforced — see `.claude/agents/blueprint-builder.md` Step 13.5 dedupe rules.

## ⚠ `forForms_checkout` — NARROW: order-specific fields ONLY

Checkout is **one form** of type `order` (do NOT split into address/payment/confirmation — that's a UI wizard concern). The form's schema contains **only fields specific to one order**, NOT user-profile fields that already live in `forForms_my_data` or `forUsers`.

### Allowed `forForms_checkout.schema` fields (whitelist)

```yaml
attributes_sets:
  - id: '@aset.forForms_checkout'
    type_id: 7
    schema:
      # --- Delivery for THIS order ---
      delivery_method:        { type: list, listTitles: { en_US: { courier: 'Courier', pickup: 'Pickup', post: 'Post' } } }
      delivery_instructions:  { type: text, rules: { maxLength: 500 } }
      delivery_slot:          { type: dateTime }                     # if the project supports timed delivery

      # --- Payment for THIS order ---
      payment_method:         { type: list, listTitles: { en_US: { card: 'Card', cash: 'Cash on delivery', apple_pay: 'Apple Pay', google_pay: 'Google Pay' } } }
      card_number:            { type: string, rules: { pattern: "^[0-9]{13,19}$" } }       # only if on-site payment (NOT redirect to PSP)
      card_holder:            { type: string }
      card_expiry:            { type: string, rules: { pattern: "^(0[1-9]|1[0-2])/([0-9]{2})$" } }
      card_cvv:               { type: string, rules: { minLength: 3, maxLength: 4 } }

      # --- Order extras ---
      promo_code:             { type: string }                                                # promo applied to THIS order
      agreed_terms:           { type: radioButton }                                            # T&C checkbox
      save_address:           { type: radioButton }                                            # "save shipping address to my profile"
      gift_wrap:              { type: radioButton }                                            # only if the project offers gift wrap
      order_notes:            { type: text, rules: { maxLength: 1000 } }                      # customer notes for the order
```

**~10–13 fields.** Exact list depends on project features (gift wrap, timed delivery, on-site card capture vs PSP redirect).

### ❌ What MUST NOT be in `forForms_checkout.schema`

| Field | Why | Where it actually lives |
|---|---|---|
| `email`, `phone`, `full_name`, `first_name`, `last_name` | They identify the **user**, not the order | **`forUsers`** (base identity) — frontend reads from `users.attributes_sets` |
| `address_line1`, `address_line2`, `city`, `country`, `postcode` | They are user **addresses** — multi-address management | **`forForms_my_data.schema.addresses`** (json array) — frontend lets user pick an address at checkout |
| `default_address_id` / `selected_address_id` | UI state, not blueprint data | Not modeled in blueprint — frontend transient state. The picked address is copied into `orders_storage` row when the order is created. |

**Frontend behaviour:** on the checkout page the frontend renders address & contact pickers populated from `users.attributes_sets` + the `my_data` form. The user can pick an existing address or open the "edit profile" flow inline (which submits to `form_data` via the `my_data` form). The `checkout` form itself **never re-asks** for email/phone/full_name/address fields.

### Guest checkout — two acceptable patterns

Different projects handle guest checkout differently. Mapper picks ONE pattern based on inspector signals:

**Pattern A — Inline optional fields in checkout** (simpler, default for small shops):

If the project supports guest checkout AND inspector finds no separate guest checkout flow → leave `forForms_checkout` as defined above and add the following **optional** fields, marked clearly that they are only filled by guests:

```yaml
forForms_checkout.schema:
  # ... (all order-specific fields above)

  # --- Guest contact + address (only filled when user is not logged in) ---
  guest_email:           { type: string, rules: { pattern: "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$" } }
  guest_full_name:       { type: string }
  guest_phone:           { type: string }
  guest_address_line1:   { type: string }
  guest_address_line2:   { type: string }
  guest_city:            { type: string }
  guest_postcode:        { type: string }
  guest_country:         { type: list }
```

The `guest_*` prefix signals to admins (and to any blueprint consumer) that these are NOT a duplicate of user-profile fields — they're fallback for non-logged-in checkout. Frontend leaves them empty for logged-in users.

**Pattern B — Separate `forForms_checkout_guest` set** (only when inspector finds a dedicated guest checkout page like `app/guest-checkout/page.tsx`):

```yaml
attributes_sets:
  - id: '@aset.forForms_checkout_guest'
    type_id: 7
    schema:
      email:          { type: string, rules: { pattern: "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$" } }
      full_name:      { type: string }
      phone:          { type: string }
      address_line1:  { type: string }
      address_line2:  { type: string }
      city:           { type: string }
      postcode:       { type: string }
      country:        { type: list }
      # ... same delivery/payment/extras as forForms_checkout
```

**Default decision:** Pattern A. Pick Pattern B only when inspector explicitly returns a `guest-checkout` route/page.

## ⚠ `forUserGroups` — emit ONLY when the project uses groups for logic (revised 2026-06-03)

**DEFAULT: DO NOT emit `forUserGroups`.** When groups exist only as auth-role buckets (`user` / `guest` / `admin`), every `user_groups` row stays with `attribute_set_id: null` and `forUserGroups` is **not** added to `attributes_sets`. The previous "always emit empty `{}` to satisfy the FK" practice was incorrect — the FK is nullable; emitting an empty set just creates a confusing empty "For user groups" panel in the admin UI.

**Emit `forUserGroups` only when the project signals that groups carry business logic.** Then mapper emits fields:

### Trigger signals (inspector must look for)

Inspector greps the project for any of these signals:

```bash
grep -rE "userGroup|user_role|loyaltyTier|membership|tier|customer_segment|wholesale" src/
grep -rE "default_discount|tier_discount|group_discount" src/
grep -rE "allowed_payment|allowed_delivery|vip[_-]?status|b2b" src/
grep -rE "group\.permissions|role\.permissions" src/
```

If at least one match in real source (not just node_modules) → emit fields in `forUserGroups.schema`:

```yaml
attributes_sets:
  - id: '@aset.forUserGroups'
    type_id: 8
    schema:
      # --- Pricing / discounts at the group level (typical wholesale / VIP) ---
      default_discount:        { type: real, rules: { minValue: 0, maxValue: 100 } }     # percentage
      vip_status:              { type: list, listTitles: { en_US: { none: 'None', silver: 'Silver', gold: 'Gold', platinum: 'Platinum' } } }

      # --- Permissions for ordering / checkout ---
      allowed_payment_methods: { type: json }                                            # array of payment_method ids the group can use
      allowed_delivery_methods:{ type: json }
      min_order_amount:        { type: real, rules: { minValue: 0 } }
      max_credit_limit:        { type: real, rules: { minValue: 0 } }                    # B2B credit

      # --- Free-form group config (anything project-specific) ---
      group_meta:              { type: json }
```

⚠ Only emit fields the project **actually uses**. Don't pre-emptively add `vip_status` if there's zero VIP logic in code — keep `forUserGroups` empty.

### Rule when no signals found

**Omit `forUserGroups` from `attributes_sets` entirely.** Do NOT emit an empty `schema: {}` entry. Every `user_groups` row keeps `attribute_set_id: null`.

```yaml
# attributes_sets: { ... }   # no forUserGroups entry here
user_groups:
  - id: '@ug.user'
    identifier: 'user'
    # NO attribute_set key — attribute_set_id remains null
    localize_infos: { en_US: { title: 'Registered Users' } }
    is_visible: true
```

Then mapper records in warnings: `forUserGroups_omitted: no group-level business logic detected. attribute_set NOT created — user_groups.attribute_set_id remains null. If you later add VIP/wholesale logic — add fields here.`

### ❌ Hard rule — `guest` is preseeded, blueprint MUST NOT emit it

`user_groups (id=1, identifier='guest', attribute_set_id=null)` is preseeded by migration `1745835025671-set-default-user-group.ts` with `ON CONFLICT DO NOTHING`. The blueprint **MUST NOT** emit a `user_groups` row with `identifier='guest'`.

If it does, blueprint-loader's `setval(seq, MAX(id)+1)` pre-alignment prevents a primary-key collision but produces a **duplicate "Guest"** row (e.g., id=3) that is visible in the admin UI as a second group with the same name.

All FK references to guest must use the literal `user_group_id: 1` or the `guest_preseeded` marker — never an `@ug.guest` token.

Same rule for `admin` (created by `seed:admins`, not by blueprint).

## ❌ What is NOT a form (anti-patterns — DO NOT create as forms)

| Anti-pattern | What it actually is | Where it goes |
|---|---|---|
| `profile_edit` (separate form) | One specific Account section → `my_data` | `forForms_my_data` (renamed and unified) |
| `change_password` (separate form) | A `users_auth_providers` endpoint / `PUT /users/:id/password` | the `password` field in `forUsers` (`isPassword: true`) + the auth provider |
| `address_book` (separate form) | Part of My Data (address CRUD lives there) | `addresses` field (`type: json`) inside `forForms_my_data.schema` |
| `payment_methods` (separate form) | Out-of-whitelist (`payment_accounts` table + PSP) | manual admin setup |
| `consents` (separate form) | Part of `subscriptions` (consents = preference toggles) | `consent_*` fields in `forForms_subscriptions.schema` |
| `social_connections` (separate form) | OAuth flow side-effect | additional providers in `users_auth_providers` |
| `loyalty_card_request` (separate form) | If editable → covered by `loyalty`; if not → no form | `forForms_loyalty` OR nothing |
| `promo_code` (separate form) | A FIELD inside `checkout` (the order form) | `promo_code` field in `forForms_checkout.schema` |
| `email_confirmation`, `phone_otp` | OTP / verification flow, not a blueprint form | handled by auth provider or out-of-whitelist |

⚠ **If inspector finds a UI component for one of these** — mapper still does NOT create them as separate forms; it routes the fields to the right home per the table above.

## Forms — ONLY real submissions (full whitelist)

Create a form **only if** the code physically contains a `<form>` / `onSubmit` / `useForm` / ≥2 inputs in an identifiable component.

### Form whitelist for a typical e-commerce project

| identifier | type | processing_type | Source signal | Bound to module |
|---|---|---|---|---|
| **`signin`** | `sing_in_up` | `db` | LoginModal / RegisterModal (or always) | Users (id=9) |
| **`checkout`** | `order` | `db` | DeliveryPage + PaymentPage merged | Orders (via `orders_storage.form_id`) |
| **`my_data`** | `data` | `db` | MyDataSection.tsx with `<form>` / inputs for first_name/phone/address | Users (id=9) |
| **`subscriptions`** | `data` | `db` | SubscriptionsSection.tsx with toggles / inputs | Users (id=9) |
| **`loyalty`** | `data` | `db` | LoyaltySection.tsx **with an editable form** (skip if read-only display) | Users (id=9) |
| **`service_request`** | `data` | `db` or `email` | ServiceMaintenanceSection.tsx | Users (id=9) |
| **`feedback`** | `data` | `db` | FeedbackSection.tsx with textarea | Users (id=9) (feedback is per-user) |
| **`refer_a_friend`** | `data` | `email` | ReferSection.tsx with friend email input | Users (id=9) |
| **`review_rating`** / **`review_feedback`** | `rating` / `data` | `db` | WriteReviewModal.tsx with rating + body | **Catalog (id=3)** — product-scoped form |
| **`contact`** | `data` | `email` | Real ContactForm (NOT info page) | Users (id=9) when authenticated; otherwise Forms (id=2) fallback |
| **`newsletter`** | `data` | `db` or `script` | Footer with email subscribe | Forms (id=2) fallback (not user-specific) |
| **`reserve_in_store`** | `data` | `email` or `db` | ReserveInStoreModal | **Catalog (id=3)** — per-product form |
| **`notify_back_in_stock`** | `data` | `db` | NotifyBackInStock* / WaitingList with email | **Catalog (id=3)** — per-product form |
| **`comments`** | `data` | `db` | CommentsSection under product/article | **Pages (id=4)** when on a CMS page; **Catalog (id=3)** when on a product |

**Typically 8–12 forms total** in an e-commerce project (signin + checkout + 4–6 account forms + 2–4 other forms).

⚠ **`FormType` enum (verified):** `order` | `sing_in_up` (legacy typo) | `collection` | `data` | `rating`. The `identifier` is project-specific, `type` is one of these 5.

### ⚠ Checkout = ONE form, not several

Anti-pattern: splitting checkout into `checkout_address` + `checkout_payment` + `checkout_confirmation` as separate forms.

In OneEntry **checkout = one order = one form of type `order`** with all order-specific fields (and `guest_*` fallback if Pattern A). The frontend may render it as a multi-step wizard — UI concern, not blueprint structure.

⚠ `type='order'` (NOT `type='data'`) — this is a distinct form type in `forms_type_enum` that the loader interprets as "this form creates an `orders_storage` record via `form_module_config`".

## How the mapper decides "form, attribute, or skip"

```python
def categorize_account_section(component_path, component_content, has_form_signals):
    """
    Decides whether an Account-section component generates a data-form
    attached to the Users module, edits `forUsers` attributes, or is read-only.
    """
    if not has_form_signals(component_content):
        return ('skip', 'read-only display — no form')

    name = component_path.lower()

    if 'mydata' in name or 'editprofile' in name or 'addressbook' in name:
        return ('form', 'my_data')              # → forForms_my_data + form_module_config(9)
    if 'subscription' in name or 'preference' in name or 'consent' in name:
        return ('form', 'subscriptions')        # → forForms_subscriptions + fmc(9)
    if 'loyalty' in name:
        return ('form', 'loyalty')              # → forForms_loyalty + fmc(9)
    if 'service' in name and 'maintenance' in name:
        return ('form', 'service_request')      # → forForms_service_request + fmc(9)
    if 'feedback' in name:
        return ('form', 'feedback')             # → forForms_feedback + fmc(9)
    if 'refer' in name and 'friend' in name:
        return ('form', 'refer_a_friend')       # → forForms_refer_a_friend + fmc(9)

    # Read-only sections — explicit skip
    if any(s in name for s in ('history', 'myorders', 'wishlist', 'waitinglist', 'bonuses', 'loyaltycard')):
        return ('skip', 'read-only display')

    # Unknown account section with form signals → warn and create as 'data' form bound to Users
    return ('form', f'account_{slugify(name)}')


def should_create_form(form_id, project_files):
    if form_id == 'signin':
        return True                              # invariant
    source = find_form_source(form_id, project_files)
    return bool(source and has_form_signals(source.content))
```

## After import — warnings format

The mapper records what it did and what it deliberately did NOT do:

```yaml
warnings:
  - 'forUsers_narrow: emitted ~10 fields (auth + base identity). Extended profile data routed to Account-section data-forms.'
  - 'account_section_forms: emitted forForms_my_data, forForms_subscriptions, forForms_loyalty (each attached to Users module via form_module_config).'
  - 'forForms_checkout_narrow: emitted ~12 fields (delivery + payment + extras). User-profile fields (email/phone/full_name/addresses) NOT duplicated — taken from forUsers + forForms_my_data at checkout time.'
  - 'guest_checkout_pattern_A: emitted guest_* fallback fields in forForms_checkout (no dedicated guest checkout page detected).'
  - 'forUserGroups_empty: kept empty schema (no group-level business logic signals found).'
  - 'skipped_forms: subscriptions_pref → merged into forForms_subscriptions; address_book → addresses field in forForms_my_data; promo_code → field in forForms_checkout.'
```

## Validator — new rule snapshot

- **S42 (forUsers anti-pattern "too many fields")** — RE-ACTIVATED with a different threshold. Now **WARNING** if `forUsers.schema` has >15 fields (extended profile data should be in account-section forms). **ERROR** if any of these specific fields are present in `forUsers.schema`: `addresses`, `address_line1`, `loyalty_*`, `pref_*`, `consent_*`, `social_*_connected`, `saved_cards`, `referral_code`, `bonuses_balance`.
- **S43 (account-section data-forms reminder)** — INFO if any of `MyDataSection`, `SubscriptionsSection`, `LoyaltySection` are mentioned by inspector but the corresponding `forForms_*` is missing.
- **S49 (form-as-attribute anti-pattern)** — kept: WARNING if blueprint contains forms `profile_edit` / `change_password` / `address_book` / `payment_methods` / `subscriptions_pref` / `consents` / `loyalty_card_request` / `social_connections` / `promo_code` — these are now anti-patterns (renamed `my_data`/`subscriptions`/etc).
- **S51 (forForms_checkout pollution)** — NEW. WARNING if `forForms_checkout.schema` contains any of `email`, `phone`, `full_name`, `first_name`, `last_name`, `address_line1`, `address_line2`, `city`, `country`, `postcode` (without `guest_` prefix). Those duplicate `forUsers` / `forForms_my_data` and must be removed or renamed to `guest_*`.
- **S52 (form_module_config coverage)** — NEW. WARNING if a form whose identifier is in {`signin`, `my_data`, `subscriptions`, `loyalty`, `service_request`, `feedback`, `refer_a_friend`} exists in `tables.forms` but has no row in `tables.form_module_config` with `module_id: 9`.
