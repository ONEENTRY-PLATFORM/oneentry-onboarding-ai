# Attribute validators — user-input fields MUST have rules

> **⚠ Universality note.** Examples below may reference fashion-shop terms (clothing / shoes / bags / women / men) — they are **illustrative**. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop, restaurant (`menu-item/dish/cuisine`), beauty salon (`service/master/treatment`), hotel (`room/suite/amenity`), EdTech (`course/lesson`), corporate site (`page/department/team`), personal cabinet (`section/setting`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **Hand-written, project-agnostic.** Source of truth for `schema.<key>.rules` and `schema.<key>.additionalFields` on every OneEntry attribute set. Used by code-inspector, entity-mapper, post-mapper-fixer, blueprint-validator.

## 🚨 CORE RULE

**Every attribute that accepts data entered by an end-user in the application MUST have validators AND UX hints.** "User-input" means the value originates from a form/input rendered in the storefront app (signin, signup, my_data, checkout, checkout_guest, feedback, refer_a_friend, review, reserve_in_store, subscriptions, etc.). Validators and hints are two complementary jsonb columns on every `SchemaItem`:

- `rules: { ... }` — declarative **constraints** (`pattern`, `minLength`, `maxLength`, `minValue`, `maxValue`, `minDate`, `maxDate`, `required`) consumed by the OneEntry storefront SDK. Block submission when violated.
- `validators: { <lang>: { ... } }` — **admin-side** validators read by `StringFieldsParameters.js:227-465`, `TextFieldsParameters.js:231-372`, `NumberFieldsParameters.js`, `DateFieldsParameters.js`. The admin **does NOT read `rules` directly** — it reads `validators[lang]`. Without them, the admin form accepts any input. Auto-generated from `rules` by `post-mapper-fixer.py::normalize_attribute_schema_shape` for every attribute_set (no longer limited to forForms_*/forUsers).
- `additionalFields: { ... }` — **UX hints** that guide the user while they're typing. NOT validation — purely presentation. **Required for every user-input attribute**, not optional.

### `rules` → `validators[lang]` mapping (auto)

| `rules` key | `validators[lang]` key |
|---|---|
| `minLength` / `maxLength` (on `string`, `textarea`, `text`) | `stringInspectionValidator: {stringMin, stringMax, stringLength:0}` |
| `pattern` (regex on `string`, `textarea`, `text`) | `regExpValidator: {patternValue, invert:false, flags:[]}` |
| `minValue` / `maxValue` (on `integer`, `real`) | `checkForNumberValidator: {integerOnly, minValue, maxValue}` |
| `required: true` (any type) | `requiredValidator: {strict: true}` (emitted via `emit_admin_validators_per_lang`) |

⚠ Mapper agents may emit only `rules` — the post-mapper-fixer derives the
matching `validators[lang]` block automatically. Hand-written `validators`
take precedence; auto-generation only fills missing keys.

### What goes into `additionalFields`

| Key | Purpose | Examples |
|---|---|---|
| `placeholder` | Ghost text shown inside the empty input — a short example of the expected value. **Must be present on every user-input string/text/number/date attribute.** | `placeholder: '+1 555 123 4567'`, `placeholder: 'jane.doe@example.com'`, `placeholder: 'MM/YY'`, `placeholder: '4111 1111 1111 1111'` |
| `helperText` | Permanent hint shown below the input — explains what the field is for, the format, or any non-obvious constraint. **Required when `rules` are non-trivial** (regex pattern, min/max, required consent, etc.) so the user understands WHY their input was rejected. | `helperText: 'We will send order updates to this email.'`, `helperText: 'Minimum 8 characters, mix of letters and numbers.'`, `helperText: 'Visible on the front of your card, 16 digits.'` |
| `mask` | Input mask that auto-formats while typing. Use for phone, card number, card expiry, CVV, postcodes — anywhere the user types a fixed-width / fixed-shape value. `#` = digit, `A` = letter. | `mask: '+## ### ### ####'` (phone), `mask: '#### #### #### ####'` (card), `mask: '##/##'` (expiry), `mask: '####'` (CVV) |
| `prefix` / `suffix` | Static text glued to the left/right of the input. Common for currency, units, percent. | `prefix: '$'` (price), `suffix: 'kg'` (weight), `suffix: '%'` (discount), `prefix: '@'` (handle) |
| `step` | Numeric increment for `<input type="number">`. | `step: 0.01` (price), `step: 1` (quantity) |
| `tooltip` | Hover/long-press tooltip with extended explanation (when `helperText` would be too long inline). | `tooltip: 'Postcode format depends on your country. Examples: US 90210, UK SW1A 1AA.'` |
| `autoComplete` | HTML `autocomplete` attribute hint to the browser (`email`, `tel`, `cc-number`, `street-address`, `postal-code`, `name`, etc.). Lets the browser offer saved values. | `autoComplete: 'cc-number'`, `autoComplete: 'street-address'` |
| `inputType` | Override the input element type when different from the OneEntry attribute type (e.g. render a `string` attribute as `<input type="tel">` or `type="email"`). | `inputType: 'tel'`, `inputType: 'email'`, `inputType: 'url'` |

### Why both are needed

Without `additionalFields.placeholder` / `helperText`:
- The user sees a blank box labelled only "Phone" or "Address line 1" — no example of what to type → bounce rate spikes on signup/checkout.
- When their input is rejected by `rules.pattern`, they have no hint about the expected format → frustration loop.
- Mobile users get the generic keyboard instead of a phone/email/numeric one (without `autoComplete`/`inputType`).

Without `rules`:
- The admin UI shows raw input boxes with no help text.
- The storefront SDK doesn't reject obviously broken data (e.g. an empty `email`, a 200-character `first_name`, a `card_cvv: "abc"`).
- Server-side validation falls back to bare `class-validator` decorators on DTOs, which often have no per-field constraints for jsonb attribute schemas.

**No exception** for "system" fields, "internal" fields, or "MVP-stage" fields. If a real user types into it — it gets BOTH `rules` AND `additionalFields`.

## Scope: which attribute sets are user-input

| Attribute set | User-input? | Why |
|---|---|---|
| `forUsers` | ✅ YES | profile editing in storefront (my_data form + signup) |
| `forForms_signin` | ✅ YES | login + signup |
| `forForms_checkout` / `forForms_checkout_guest` | ✅ YES | order placement |
| `forForms_my_data` / `forForms_subscriptions` / `forForms_feedback` / `forForms_refer_a_friend` / `forForms_review` / `forForms_reserve_in_store` / `forForms_service_request` | ✅ YES | account-section data-forms |
| `forUserGroups` | ❌ NO | admin-only configuration |
| `forAdmins` | ❌ NO | admin profile editing in admin UI (separate validation layer) |
| `forProducts_*` | ⚠ MIXED | admin-input in CMS admin (price/sku/title), but ALSO consumed by storefront SDK validators (e.g. price > 0). Apply numeric-range + string-length validators where obvious. |
| `forPages` | ⚠ MIXED | admin-input (meta_title/meta_description/canonical). Apply length validators only. |
| `forBlocks_*` | ⚠ MIXED | admin-input (title/subtitle/cta_url). Apply length + URL pattern validators. |
| `forBlocks_*` (system/computed) | ❌ NO | when admin doesn't directly type — skip |

## Canonical validator table (apply by attribute `identifier`)

Format: identifier → `{ rules?, additionalFields? }`. Apply ON TOP of whatever the inspector/mapper emitted (don't strip existing keys — merge).

### Identity / auth fields
```yaml
email:
  rules:            { pattern: '^[^@\s]+@[^@\s]+\.[^@\s]+$', maxLength: 254 }
  additionalFields: { placeholder: 'jane.doe@example.com', helperText: "We'll send order updates to this email.", autoComplete: 'email', inputType: 'email' }
password:
  rules:            { minLength: 8, maxLength: 128 }
  additionalFields: { helperText: 'Minimum 8 characters.', autoComplete: 'new-password', inputType: 'password' }
phone:
  rules:            {}
  additionalFields: { mask: '+## ### ### ####', placeholder: '+1 555 123 4567', helperText: 'We may call about your order.', autoComplete: 'tel', inputType: 'tel' }
first_name:
  rules:            { minLength: 1, maxLength: 50 }
  additionalFields: { placeholder: 'Jane', autoComplete: 'given-name' }
last_name:
  rules:            { minLength: 1, maxLength: 50 }
  additionalFields: { placeholder: 'Doe', autoComplete: 'family-name' }
full_name:
  rules:            { minLength: 2, maxLength: 100 }
  additionalFields: { placeholder: 'Jane Doe', autoComplete: 'name' }
middle_name:
  rules:            { maxLength: 50 }
  additionalFields: { placeholder: 'Optional', autoComplete: 'additional-name' }
nickname:
  rules:            { minLength: 2, maxLength: 50 }
  additionalFields: { placeholder: 'How should we call you?', autoComplete: 'nickname' }
username:
  rules:            { pattern: '^[a-zA-Z0-9_-]{3,30}$' }
  additionalFields: { placeholder: 'Letters, digits, underscores', helperText: '3-30 chars; a-z, 0-9, _ and -.', autoComplete: 'username' }
birthday:
  rules:            { minDate: '1900-01-01' }
  additionalFields: { placeholder: 'YYYY-MM-DD', helperText: "We'll send you a birthday discount.", autoComplete: 'bday' }
date_of_birth:
  rules:            { minDate: '1900-01-01' }
  additionalFields: { placeholder: 'YYYY-MM-DD', autoComplete: 'bday' }
```

### Address fields
```yaml
address_line1:
  rules:            { minLength: 1, maxLength: 200 }
  additionalFields: { placeholder: '123 Main St', helperText: 'Street and house number.', autoComplete: 'address-line1' }
address_line2:
  rules:            { maxLength: 200 }
  additionalFields: { placeholder: 'Apt 4B (optional)', autoComplete: 'address-line2' }
city:
  rules:            { minLength: 1, maxLength: 100 }
  additionalFields: { placeholder: 'San Francisco', autoComplete: 'address-level2' }
state:
  rules:            { maxLength: 100 }
  additionalFields: { placeholder: 'California', autoComplete: 'address-level1' }
country:
  rules:            { minLength: 2, maxLength: 60 }
  additionalFields: { placeholder: 'United States', autoComplete: 'country-name' }
postcode:
  rules:            { minLength: 3, maxLength: 12 }
  additionalFields: { placeholder: '94103', helperText: 'Postcode / ZIP.', autoComplete: 'postal-code' }
zip:
  rules:            { minLength: 3, maxLength: 12 }
  additionalFields: { placeholder: '94103', autoComplete: 'postal-code' }
zip_code:
  rules:            { minLength: 3, maxLength: 12 }
  additionalFields: { placeholder: '94103', autoComplete: 'postal-code' }
```

### Order / checkout fields
```yaml
card_number:
  rules:            { pattern: '^[0-9]{13,19}$' }
  additionalFields: { mask: '#### #### #### ####', placeholder: '4111 1111 1111 1111', helperText: '16 digits on the front of your card.', autoComplete: 'cc-number', inputType: 'tel' }
card_name:
  rules:            { minLength: 2, maxLength: 100 }
  additionalFields: { placeholder: 'JANE DOE', helperText: 'Name as printed on the card.', autoComplete: 'cc-name' }
card_expiry:
  rules:            { pattern: '^(0[1-9]|1[0-2])\/[0-9]{2}$' }
  additionalFields: { mask: '##/##', placeholder: 'MM/YY', helperText: 'Month and year of expiry.', autoComplete: 'cc-exp', inputType: 'tel' }
card_cvv:
  rules:            { pattern: '^[0-9]{3,4}$' }
  additionalFields: { mask: '####', placeholder: '123', helperText: '3-4 digits on the back of your card.', autoComplete: 'cc-csc', inputType: 'tel' }
promo_code:
  rules:            { maxLength: 50 }
  additionalFields: { placeholder: 'WELCOME10', helperText: 'Optional promotional code.' }
coupon_code:
  rules:            { maxLength: 50 }
  additionalFields: { placeholder: 'WELCOME10', helperText: 'Optional coupon code.' }
voucher_code:
  rules:            { maxLength: 50 }
  additionalFields: { placeholder: 'GIFT100', helperText: 'Optional gift voucher code.' }
delivery_instructions:
  rules:            { maxLength: 500 }
  additionalFields: { placeholder: 'Ring the doorbell, leave at door, etc.', helperText: 'Up to 500 characters.' }
delivery_notes:
  rules:            { maxLength: 500 }
  additionalFields: { placeholder: 'Anything the courier should know.' }
order_notes:
  rules:            { maxLength: 500 }
  additionalFields: { placeholder: 'Anything else?' }
```

### Free-text content fields
```yaml
title:
  rules:            { minLength: 1, maxLength: 200 }
  additionalFields: { placeholder: 'Short title' }
subtitle:
  rules:            { maxLength: 300 }
  additionalFields: { placeholder: 'Supporting line' }
description:
  rules:            { maxLength: 5000 }
  additionalFields: { placeholder: 'Tell customers more...', helperText: 'Up to 5000 characters.' }
short_description:
  rules:            { maxLength: 500 }
  additionalFields: { placeholder: 'One-paragraph summary.' }
message:
  rules:            { minLength: 1, maxLength: 2000 }
  additionalFields: { placeholder: 'Type your message here...' }
notes:
  rules:            { maxLength: 2000 }
  additionalFields: { placeholder: 'Optional notes.' }
question:
  rules:            { minLength: 5, maxLength: 500 }
  additionalFields: { placeholder: 'What would you like to ask?' }
answer:
  rules:            { minLength: 1, maxLength: 5000 }
  additionalFields: { placeholder: 'Detailed answer.' }
comment:
  rules:            { maxLength: 2000 }
  additionalFields: { placeholder: 'Add a comment.' }
feedback:
  rules:            { minLength: 5, maxLength: 2000 }
  additionalFields: { placeholder: "Tell us what you think.", helperText: 'Up to 2000 characters.' }
review_text:
  rules:            { minLength: 5, maxLength: 2000 }
  additionalFields: { placeholder: 'Tell others why you like it...', helperText: '5-2000 characters.' }
review_title:
  rules:            { minLength: 2, maxLength: 200 }
  additionalFields: { placeholder: 'Great product!' }
```

### Numeric fields
```yaml
price:
  rules:            { minValue: 0, maxValue: 9999999 }
  additionalFields: { placeholder: '99.99', prefix: '$', step: 0.01, inputType: 'number' }
old_price:
  rules:            { minValue: 0, maxValue: 9999999 }
  additionalFields: { placeholder: '129.00', prefix: '$', step: 0.01, inputType: 'number' }
quantity:
  rules:            { minValue: 0, maxValue: 9999 }
  additionalFields: { placeholder: '1', step: 1, inputType: 'number' }
rating:
  rules:            { minValue: 0, maxValue: 5 }
  additionalFields: { helperText: 'From 0 to 5 stars.', step: 0.5, inputType: 'number' }
weight:
  rules:            { minValue: 0 }
  additionalFields: { placeholder: '0.50', suffix: 'kg', step: 0.01, inputType: 'number' }
height:
  rules:            { minValue: 0 }
  additionalFields: { placeholder: '10', suffix: 'cm', step: 0.1, inputType: 'number' }
width:
  rules:            { minValue: 0 }
  additionalFields: { placeholder: '10', suffix: 'cm', step: 0.1, inputType: 'number' }
depth:
  rules:            { minValue: 0 }
  additionalFields: { placeholder: '10', suffix: 'cm', step: 0.1, inputType: 'number' }
```

### Catalog metadata fields
```yaml
sku:
  rules:            { pattern: '^[a-zA-Z0-9_-]+$', minLength: 1, maxLength: 50 }
  additionalFields: { placeholder: 'MEN-SHIRT-001', helperText: 'Letters, digits, dashes, underscores.' }
slug:
  rules:            { pattern: '^[a-z0-9-]+$', minLength: 1, maxLength: 100 }
  additionalFields: { placeholder: 'product-name', helperText: 'Lowercase letters, digits, hyphens.' }
barcode:
  rules:            { pattern: '^[0-9]+$', minLength: 8, maxLength: 14 }
  additionalFields: { placeholder: '0123456789012', helperText: 'EAN-13 / UPC barcode.' }
```

### Marketing / referral fields
```yaml
friend_email:
  rules:            { pattern: '^[^@\s]+@[^@\s]+\.[^@\s]+$' }
  additionalFields: { placeholder: 'friend@example.com', autoComplete: 'email', inputType: 'email' }
friend_emails:
  rules:            { pattern: '^[^@\s]+@[^@\s]+\.[^@\s]+$' }
  additionalFields: { placeholder: 'friend1@example.com, friend2@example.com', helperText: 'Comma-separated for multiple recipients.', autoComplete: 'email' }
referral_code:
  rules:            { pattern: '^[A-Z0-9]{4,16}$' }
  additionalFields: { placeholder: 'JANE2024', helperText: '4-16 uppercase letters and digits.' }
```

### URL / SEO fields
```yaml
cta_url:
  rules:            { pattern: '^(https?:\/\/|\/)[^\s]+$', maxLength: 500 }
  additionalFields: { placeholder: 'https://example.com  OR  /sale', helperText: 'Absolute URL (https://...) or relative path (/...).', autoComplete: 'url', inputType: 'url' }
canonical:
  rules:            { pattern: '^https?:\/\/[^\s]+$', maxLength: 500 }
  additionalFields: { placeholder: 'https://example.com/page', helperText: 'Canonical URL for SEO.', autoComplete: 'url', inputType: 'url' }
website:
  rules:            { pattern: '^https?:\/\/[^\s]+$', maxLength: 500 }
  additionalFields: { placeholder: 'https://example.com', autoComplete: 'url', inputType: 'url' }
meta_title:
  rules:            { maxLength: 70 }
  additionalFields: { placeholder: 'Page title for search engines', helperText: 'Up to 70 characters (truncated in Google).' }
meta_description:
  rules:            { maxLength: 160 }
  additionalFields: { placeholder: 'Short page description shown in search results.', helperText: 'Up to 160 characters.' }
seo_title:
  rules:            { maxLength: 70 }
  additionalFields: { placeholder: 'SEO title', helperText: 'Up to 70 characters.' }
seo_description:
  rules:            { maxLength: 160 }
  additionalFields: { placeholder: 'SEO meta description.', helperText: 'Up to 160 characters.' }
og_title:
  rules:            { maxLength: 70 }
  additionalFields: { placeholder: 'Open Graph title (social shares).', helperText: 'Up to 70 characters.' }
og_description:
  rules:            { maxLength: 200 }
  additionalFields: { placeholder: 'Open Graph description (social shares).', helperText: 'Up to 200 characters.' }
```

### Consents / agreements (radioButton)
```yaml
agreed_terms:
  rules:            { required: true }
  additionalFields: { helperText: 'You must accept Terms of Service to continue.' }
consent_marketing:
  rules:            {}
  additionalFields: { helperText: "Optional — we'll send promotional emails." }
consent_data_processing:
  rules:            { required: true }
  additionalFields: { helperText: 'Required to process your order (GDPR).' }
consent_cross_border:
  rules:            {}
  additionalFields: { helperText: 'Allow us to transfer your data internationally.' }
```

## Merge semantics (post-mapper-fixer.py::enrich_attribute_validators)

For each attribute set in `mapped.attributes_sets`:

```python
for attr_key, attr in (aset.get('schema') or {}).items():
    ident = attr.get('identifier') or attr_key
    rule_template = ATTR_VALIDATORS.get(ident)
    if not rule_template:
        continue
    # Merge `rules`
    if 'rules' in rule_template:
        existing_rules = attr.setdefault('rules', {})
        for k, v in rule_template['rules'].items():
            existing_rules.setdefault(k, v)   # don't overwrite hand-set rules
    # Merge `additionalFields`
    if 'additionalFields' in rule_template:
        existing_addl = attr.setdefault('additionalFields', {})
        for k, v in rule_template['additionalFields'].items():
            existing_addl.setdefault(k, v)
```

Idempotent. Never overwrites hand-set values — only fills in missing keys.

## Inspector responsibility

Inspector continues to record raw signal — what fields exist in the project's forms, with what JS-level validations (Zod schemas, react-hook-form rules, `pattern=` HTML attrs). When inspector finds project-specific constraints stricter than the canonical table → record them in `inspector.notes.attribute_constraints.<set>.<identifier>` and mapper applies the project-specific values on top of the canonical defaults.

## Validator coverage check (blueprint-validator)

New check **S63 — Validator coverage**: for each attribute set marked `user-input` (forUsers / forForms_*), count `attrs_total` vs `attrs_with_validators` (sum of `rules` keys + `additionalFields` keys). If coverage < 80% for an entire set → WARN. If a known-critical field (`email`, `phone`, `password`, `card_*`, `birthday`, `postcode`, `address_line1`, `city`, `country`) is missing validators → ERROR.

## Cross-references

- `agents_datasets/rules/users-architecture.md` §"Allowed forUsers.schema fields" — has inline validator examples.
- `agents_datasets/rules/products-architecture.md` §"Allowed forProducts schema" — has minValue / minLength examples.
- `agents_datasets/agents/entity-mapper.md` Step 1.5 — invokes enrich_attribute_validators.
- `agents_datasets/scripts/post-mapper-fixer.py::ATTR_VALIDATORS` — runtime constant.
- `agents_datasets/rules/coverage-checklist.md` §3.X — validator coverage check.
