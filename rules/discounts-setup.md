# Discounts — universal setup rules for any OneEntry project

> **⚠ Universality note.** Examples below may reference fashion-shop terms (clothing / shoes / bags / women / men) — they are **illustrative**. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop, restaurant (`menu-item/dish/cuisine`), beauty salon (`service/master/treatment`), hotel (`room/suite/amenity`), EdTech (`course/lesson`), corporate site (`page/department/team`), personal cabinet (`section/setting`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **Hand-written, project-agnostic, grep-verified against the OneEntry Discounts module.** Source of truth for how discounts work in OneEntry and how the blueprint pipeline must treat them. Used by code-inspector, entity-mapper, post-import-orchestrator, blueprint-validator.

## 1. TL;DR — how discounts work in OneEntry

1. **Two main tables, all out of the 24-table blueprint whitelist**:

   | Table | Role |
   |---|---|
   | `discounts` | A discount/promotion (`identifier`, `type`, `localizeInfos`, `discountValue`, `conditions[]`, `startDate`/`endDate`). |
   | `discount_coupons` | Coupon codes attached to a discount (auto-generated via `/discounts/:id/coupons/generate` or user-defined). |

2. **Discount value model** — verified against the CreateDiscountDto contract:
   - `type` enum: `DISCOUNT` (regular % / amount off), `BONUS` (cashback / loyalty points), `PERSONAL_DISCOUNT` (user-specific).
   - `discountValue.discountType` enum: `NONE` / `PERCENTAGE` / `FIXED_AMOUNT` / `FIXED_PRICE`. ⚠ **Field name is `discountType`, NOT `type`** — admin UI (`DiscountsValueSettings.js`) reads `discountValue.discountType` and shows an empty "Choose discount type" dropdown if you send `type`.
   - `discountValue.applicability` enum: `TO_PRODUCT` / `TO_ORDER`.
   - `discountValue.value: number` — the % (e.g. `10` = 10%) or amount in product currency.

3. **Conditions model** — array of `{ type, value, ... }` with logical operator:
   - `conditionLogic` enum: `AND` / `OR` between condition items.
   - `condition.type` enum: `PRODUCT`, `CATEGORY`, `ATTRIBUTE`, `PRODUCT_IN_CART`, `CATEGORY_IN_CART`, `MIN_CART_AMOUNT`, `USER_LTV`, `USER_ATTRIBUTE`.

4. **Discounts are NOT representable in the blueprint** — `discounts` / `discount_coupons` are not in the 24-table whitelist of the blueprint-loader. The blueprint pipeline therefore:
   - Inspector detects discount signals (`salePrice`/`oldPrice`/`originalPrice` patterns in product data, `% off` literals in banners, `CHECKOUT_COUPONS`/`promoCode` constants).
   - Mapper emits `mapped.post_import_discounts[]` — task list to create after blueprint upload.
   - Post-import-orchestrator reads it and POSTs via REST against `/api/admin/discounts*` endpoints.
   - Validator checks that the task list is non-empty when discount signals exist (S62).

---

## 2. What the blueprint pipeline MUST do

### 2.1 Inspector — detect discount signals

Look at the project for any of:

| Signal kind | Examples | Maps to |
|---|---|---|
| **Product-level price pair** | `salePrice`, `oldPrice`, `originalPrice`, `discountPrice` fields in product data files | `type=DISCOUNT`, `discountValue.discountType=PERCENTAGE`, `applicability=TO_PRODUCT`, `value=computed_pct`, `conditions=[{type:PRODUCT, value:product_id}]` |
| **Coupon constants** | `CHECKOUT_COUPONS`, `PROMO_CODES`, `COUPON_CODES` records `{ CODE: { pct: N } }` | `type=DISCOUNT`, one row per coupon code with `discount_coupons[]` rows |
| **Static banner literals** | `"Up to 70% off"`, `"SALE"`, `"% off"` in `banners.ts`/`seoData.ts` | **Marketing copy** — NOT discount entities. Do NOT emit a discount task per banner sentence. |
| **Badge constants** | `badge: '-50%'`, `badge: 'SALE'` in product catalog | **Already routed** to `tags: type=list` per `products-architecture.md`. Do NOT duplicate as discount entity. |

Emit in `inspector.yaml`:
```yaml
notes:
  discounts:
    present: true
    signals:
      - { kind: product_sale, source: src/app/data/productCatalog.ts:296, evidence: "price: 289.00, salePrice: 144.50, badge: '-50%'", computed_pct: 50, products: ['wc-1', 'ws-3'] }
      - { kind: coupon,       source: src/app/data/checkoutConfig.ts:4,   code: ONEENTRY10, pct: 10, label: '10% off' }
      - { kind: coupon,       source: src/app/data/checkoutConfig.ts:5,   code: SAVE10,     pct: 10, label: '10% off' }
      - { kind: coupon,       source: src/app/data/checkoutConfig.ts:6,   code: ONEENTRY20, pct: 20, label: '20% off' }
      - { kind: coupon,       source: src/app/data/checkoutConfig.ts:7,   code: SUMMER15,   pct: 15, label: '15% off' }
      - { kind: coupon,       source: src/app/data/checkoutConfig.ts:8,   code: WELCOME25,  pct: 25, label: '25% off' }
    extracted:
      product_sales:
        - { products: ['wc-1', 'ws-3'], pct: 50 }
        - { products: ['wc-2'],         pct: 40 }
        - { products: ['ws-1', 'wb-2'], pct: 30 }
      coupons:
        - { code: ONEENTRY10, pct: 10 }
        - { code: SAVE10,     pct: 10 }
        - { code: ONEENTRY20, pct: 20 }
        - { code: SUMMER15,   pct: 15 }
        - { code: WELCOME25,  pct: 25 }
```

### 2.2 Mapper — build `post_import_discounts[]` task list

See `entity-mapper.md` Step 9.11. Goal: take inspector's extracted discount data and write `mapped.post_import_discounts[]` — one task per discount entity that should be created after import.

---

## 3. Mapper task structure (`mapped.post_import_discounts[]`)

```yaml
post_import_discounts:

  # --- Product-level sale discounts (grouped by % to avoid 100+ entities) ---
  - identifier: sale_50_off
    type: DISCOUNT
    localize_infos:
      en_US: { title: '-50% off — flash sale' }
    discount_value:
      type: PERCENTAGE
      applicability: TO_PRODUCT
      value: 50
    condition_logic: OR
    conditions:
      - { type: PRODUCT, value_slug: 'wc-1' }
      - { type: PRODUCT, value_slug: 'ws-3' }
    is_active: true

  - identifier: sale_40_off
    type: DISCOUNT
    localize_infos:
      en_US: { title: '-40% off' }
    discount_value:
      type: PERCENTAGE
      applicability: TO_PRODUCT
      value: 40
    conditions:
      - { type: PRODUCT, value_slug: 'wc-2' }

  # --- Coupon-based discounts (one per CHECKOUT_COUPONS entry) ---
  - identifier: coupon_oneentry10
    type: DISCOUNT
    localize_infos:
      en_US: { title: 'ONEENTRY10 — 10% off' }
    discount_value:
      type: PERCENTAGE
      applicability: TO_ORDER
      value: 10
    coupons:
      - { code: ONEENTRY10, usage_limit: null }

  - identifier: coupon_save10
    type: DISCOUNT
    localize_infos:
      en_US: { title: 'SAVE10 — 10% off' }
    discount_value: { type: PERCENTAGE, applicability: TO_ORDER, value: 10 }
    coupons: [{ code: SAVE10 }]

  - identifier: coupon_oneentry20
    type: DISCOUNT
    localize_infos:
      en_US: { title: 'ONEENTRY20 — 20% off' }
    discount_value: { type: PERCENTAGE, applicability: TO_ORDER, value: 20 }
    coupons: [{ code: ONEENTRY20 }]

  - identifier: coupon_summer15
    type: DISCOUNT
    localize_infos:
      en_US: { title: 'SUMMER15 — 15% off' }
    discount_value: { type: PERCENTAGE, applicability: TO_ORDER, value: 15 }
    coupons: [{ code: SUMMER15 }]

  - identifier: coupon_welcome25
    type: DISCOUNT
    localize_infos:
      en_US: { title: 'WELCOME25 — 25% off' }
    discount_value: { type: PERCENTAGE, applicability: TO_ORDER, value: 25 }
    coupons: [{ code: WELCOME25 }]
```

**Key fields:**
- `identifier`: discount marker, must be URL-safe slug (`[a-z0-9_-]+`). UNIQUE constraint on `discounts.identifier` — orchestrator must check existence before POST.
- `type`: one of `DISCOUNT` (default for retail %), `BONUS` (loyalty points), `PERSONAL_DISCOUNT` (single-user / VIP).
- `discount_value.type`: one of `PERCENTAGE`, `FIXED_AMOUNT`, `FIXED_PRICE`, `NONE`.
- `discount_value.applicability`: `TO_PRODUCT` (% off per matching item) vs `TO_ORDER` (% off total cart).
- `conditions[].type`: see enum in §1.
- `conditions[].value_slug`: blueprint product/category slug; orchestrator resolves slug → DB id before POST.
- `coupons[]`: array of `{ code, usage_limit?, valid_from?, valid_to? }` — POSTed via `/discounts/:id/coupons` after the discount is created.

### 3.1 Discount grouping strategy

When inspector finds 100+ products with `salePrice`, do NOT emit 100 discounts. Group by percent:

```
discount_50_off → conditions: OR(product=wc-1, product=ws-3, product=...)
discount_40_off → conditions: OR(product=wc-2, ...)
discount_30_off → conditions: OR(product=ws-1, ...)
```

One discount entity per unique percent across all products. Maximum 5-7 discount entities for a typical shop (5, 10, 15, 20, 25, 30, 40, 50 % buckets).

---

## 4. Inspector extraction heuristics

### 4.1 Product `salePrice` pattern

Typical shape:
```ts
export const products = [
  { id: 'wc-1', price: 289.00, salePrice: 144.50, badge: '-50%' },
  { id: 'wc-2', price: 199.00, salePrice: 119.40, badge: '-40%' },
  ...
];
```

Inspector should:
1. For each product with `salePrice` field — compute `pct = round((price - salePrice) / price * 100)`.
2. Group products by `pct` value.
3. Emit one `product_sales` group per unique `pct`.

### 4.2 Coupon constants pattern

Typical shape:
```ts
export const CHECKOUT_COUPONS = {
  ONEENTRY10: { label: '10% off', pct: 10 },
  SAVE10:     { label: '10% off', pct: 10 },
};
```

Inspector should:
1. Walk `*.ts` files in `src/data/` / `src/app/data/` for `*COUPON*` / `*PROMO*` exports.
2. Read each key + pct into `coupons[]` array.
3. If two coupons share the same pct → STILL emit as separate discounts (they're different codes with potentially different usage limits).

### 4.3 Banner / hero copy

Static marketing text like "Up to 70% off summer sale" in `banners.ts` / `seoData.ts` is **NOT** a discount entity — it's display content that lives in page/block `attributes_sets`. Inspector should record it as `kind: marketing_copy` and mapper should ignore for discount emission.

### 4.4 Badge constants

`badge: '-50%'` / `badge: 'SALE'` patterns on individual products are **already routed** to the consolidated `tags: type=list` attribute (see `products-architecture.md` "Consolidate marketing flags"). Do NOT also emit them as discount entities — the discount entity is created from `salePrice` (the actual % calculation), not from the badge label.

---

## 5. Anti-patterns

| Anti-pattern | Correct |
|---|---|
| Adding `sale_price` / `discount_amount` / `discount_percent` to `forProducts_*.schema` as attributes | Emit `post_import_discounts[]` task; product retains `price: real` only |
| Emitting 100 separate discount entities for 100 products on sale | Group by unique percent — one discount per percent bucket with OR-conditions over product ids |
| Putting promo code values inside `forForms_checkout.schema` as a `list` enum | The list of valid codes is dynamic and admin-managed. Frontend should fetch valid codes from `GET /api/content/discounts/coupons/validate?code=XXX`. Form retains a `promo_code: { type: string }` free-text input. |
| Emitting a discount per banner sentence (`"Up to 70% off"`) | Banner copy is marketing content for hero blocks, not a discount entity. Only emit when there's an actual `salePrice` or `CHECKOUT_COUPONS` entry. |
| Setting `discountValue.value: 0.50` for 50% off | `discountValue.value` is the percent itself (`50`), not the multiplier. Use `50` not `0.50`. |
| Hard-coding numeric category/product ids in `conditions[].value` | Use `conditions[].value_slug: '<blueprint identifier>'`; orchestrator resolves slug → id at POST time. |

---

## 6. Real REST API contract

### 6.1 Create discount

`CreateDiscountDto` accepts the full discount definition in one call. ⚠ **Condition shape is `{conditionType, entityIds, value?}`** — NOT the older `{type, value}` form. `entityIds` is an array of `EntityIdentifier` objects `{id: number|string, isNested?: bool}` (verified against the OneEntry Platform `DiscountConditionDto`).

```
POST /api/admin/discounts
Authorization: Bearer <token>
Content-Type: application/json

{
  "identifier": "sale_50_off",
  "type": "DISCOUNT",
  "localizeInfos": { "en_US": { "title": "-50% off flash sale" } },
  "discountValue": {
    "discountType": "PERCENTAGE",
    "applicability": "TO_PRODUCT",
    "value": 50
  },
  "conditionLogic": "OR",
  "conditions": [
    { "conditionType": "PRODUCT",          "entityIds": [{"id": 12}, {"id": 18}] },
    { "conditionType": "CATEGORY",         "entityIds": [{"id": 47, "isNested": true}] },
    { "conditionType": "MIN_CART_AMOUNT",  "value":     {"amount": 1000} },
    { "conditionType": "USER_LTV",         "value":     {"amount": 5000} }
  ],
  "userGroups": [],
  "exclusions": [],
  "gifts": [],
  "giftsReplaceCartItems": false,
  "startDate": null,
  "endDate": null
}
```

Returns `{ id, identifier, ... }`. Permission: `AdminPermissionsEnum['discount.create']`.

Condition-type matrix (verified against the OneEntry Platform `DiscountConditionType` enum + `discount-condition.validator`):

| `conditionType` | Carries `entityIds` | Carries `value` | Notes |
|---|---|---|---|
| `PRODUCT` | yes — product ids | no | one product per `EntityIdentifier` |
| `PRODUCT_IN_CART` | yes — product ids | no | cart-driven |
| `CATEGORY` | yes — page (category) ids | no | use `isNested: true` for subtree |
| `CATEGORY_IN_CART` | yes — page (category) ids | no | cart-driven |
| `ATTRIBUTE` | yes — attribute ids | yes — attribute value to match | both required |
| `USER_ATTRIBUTE` | yes — user-attr ids | yes — value to match | profile-based |
| `MIN_CART_AMOUNT` | no | yes — `{amount: number}` | currency-scoped |
| `USER_LTV` | no | yes — `{amount: number}` | lifetime-value gate |

### 6.2 Create coupons for a discount

`CreateDiscountCouponDto` accepts ONLY `{code}` (verified against the OneEntry Platform). The previous "doc fiction" `usageLimit` field does not exist; per-coupon usage limits are configured manually in the admin UI after creation.

```
POST /api/admin/discounts/:id/coupons
{ "code": "ONEENTRY10" }
```

Or auto-generate N coupons via the `GenerateDiscountCouponDto` mask syntax (verified against the OneEntry Platform):
```
POST /api/admin/discounts/:id/coupons/generate
{
  "mask":     "SALE-AAAA9",     // A=random A-Z letter, 9=random 0-9 digit
  "quantity": 100                // 1..MAX_GENERATE_SIZE per request
}
```

The mask must contain at least `COUPON_CONSTANTS.MASK_MIN_VARIABLE_CHARS` placeholder symbols. Escape literal `A`/`9` with `\A`/`\9`. The earlier wording "`count`/`prefix`/`length`" was doc fiction — not a real endpoint contract.

### 6.3 Update / delete

- `PUT /api/admin/discounts/:id` — update with same DTO shape.
- `DELETE /api/admin/discounts/:id` — delete (cascade deletes coupons).
- `PUT /api/admin/discounts/:id/position` — change priority (lexorank).

### 6.4 Idempotency before creating

1. `GET /api/admin/discounts` → list existing discounts (returns `{ items, total }`).
2. If `identifier` already exists in `items[]` → skip create, reuse `id`. Optionally PUT to update.
3. For coupons under a discount — fetch via `GET /api/admin/discounts/:id/coupons`, dedupe by `code`.
4. Optional: `GET /api/admin/discounts/marker-validation/:marker` returns 200/409 for collision pre-check.

### 6.5 Discount settings (separate endpoint)

Global discount-engine settings (stacking, max bonus, gift policy) live in a singleton:
```
GET /api/admin/discounts/settings
PUT /api/admin/discounts/settings
```

Post-import-orchestrator should **NOT** modify this — leave defaults unless inspector finds explicit `stacking: true` / `maxDiscount: N` signals in the project.

### 6.6 Required admin permissions

- `discount.create`
- `discount.update`
- `discount.delete`
- `discount.coupon.create`
- `discount.coupon.delete`

All seeded in the CMS admin-rights seed migrations (preseeded). Orchestrator does NOT need to grant them — admin user must have them by definition.

### 6.7 What CANNOT be auto-resolved

- `bonusEvent` (cashback rules) — requires explicit project decision (when to award bonus points). Inspector cannot infer this from frontend data; admin configures manually after import.
- `attributesSets` / `attributeSetId` on discount itself — for advanced attribute-based conditions; default to none, admin sets up later.
- Personalized discounts (`type=PERSONAL_DISCOUNT`) targeted at specific users — requires user ids which are not part of blueprint; manual setup.
- `selectedAttributeMarkers` (display string of attributes in admin UI) — auto-fill is risky; leave empty.

---

## 7. End-to-end pipeline example

1. **Inspector** finds `salePrice` in `productCatalog.ts` (100+ products) + `CHECKOUT_COUPONS` (5 codes) + banner text "Up to 70% off" → emits `inspector.yaml.notes.discounts.signals/extracted`.
2. **Mapper** groups product sales by percent (5-7 buckets) + one entity per coupon → writes `mapped.post_import_discounts[]`. Emits warning `out-of-whitelist-needs-post-import: N discounts …`. Does NOT mutate `forProducts_*.schema` with `sale_price` field (that's the trigger of an anti-pattern).
3. **Builder** ignores `post_import_discounts[]` (lives at the mapped-level meta, not inside blueprint tables).
4. **Validator** S62 — INFO when inspector recorded discount signals but mapper didn't emit `post_import_discounts[]`.
5. **Loader** uploads blueprint via `POST /api/admin/import/from-blueprint` (discounts untouched — products exist now).
6. **Post-import-orchestrator** reads `mapped.post_import_discounts[]`. For each task: resolve `conditions[].value_slug → product_id` via lookup → POST discount → POST coupons → idempotency check.

---

## 8. Cross-references

- `agents_datasets/rules/products-architecture.md` — why `sale_price` must NOT live in `forProducts_*.schema`.
- `agents_datasets/rules/menus-setup.md` — analogous post-import pattern (out-of-whitelist + REST).
- `agents_datasets/agents/entity-mapper.md` Step 9.11 — emission of `post_import_discounts[]`.
- `agents_datasets/agents/code-inspector.md` Step 5.8 — discount signals detection.
- `agents_datasets/scripts/post-import-orchestrator.py` — `task_post_import_discounts`.
