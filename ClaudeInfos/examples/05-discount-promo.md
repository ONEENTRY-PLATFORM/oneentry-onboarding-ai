<!-- audit: 5/5 (2026-05-13) endpoints[POST /discounts, PUT /discounts/:id, POST /discounts/:id/coupons, POST /discounts/:id/coupons/generate, POST /discounts/bonus-balance/adjust, PUT /discounts/settings], fields[discounts.type, discounts.discount_value jsonb, discounts.user_groups jsonb, discount_coupons.code unique, discount_bonus_balance.user_id unique], queues[BULL_CONSUMERS.discountStart/discountEnd/bonusExpiration via cron service], ws[admin-discounts: 'discounts' create/update/delete], fk[discount_coupons.discount_id->discounts.id CASCADE, discount_conditions.discount_id->discounts.id CASCADE, discount_bonus_balance.user_id->users.id CASCADE] -->

# 05. Discounts, coupons, bonus programs

## Purpose

Any promotional mechanism:
- **Seasonal discount**: "-20% on summer collection from Jun 1 to Aug 31".
- **Coupons**: single-use / reusable codes (`SUMMER2024`, `WELCOME10`).
- **Gift with purchase**: "buy a coffee maker — get 200g of coffee free".
- **Personal discount for a group**: "-12% for the Wholesale group" (see [08-users-and-groups.md](./08-users-and-groups.md)).
- **Bonus program**: "5% of order amount to bonus balance + expires in 90 days".
- **Discount by min cart amount / by user LTV / by birthday**.

OneEntry distinguishes three types within a single `discounts` table:
- `DISCOUNT` — regular discount / promo.
- `PERSONAL_DISCOUNT` — discount for specific groups/users.
- `BONUS` — awarding/redeeming bonuses.

## Entities and dependency hierarchy

```
discount_settings        — global settings of the discounts module (1 row)
discounts                — head entity: type, period, application conditions, value config
  ↑ discount_id (CASCADE)
discount_conditions      — activation conditions (min cart, specific product, user attribute)
discount_coupons         — coupon codes (single-use / reusable)
discount_bonus_events    — trigger event config for type=BONUS (when to accrue)
discount_bonus_balance   — bonus balance of a specific user (user_id UNIQUE)
discount_bonus_transaction — history of movements (accrued / spent / expired)
discount_bonus_usage_detail — details of bonus usage in an order
```

| Table | Base class | Key fields |
|---|---|---|
| `discounts` | `BaseAttributeSetsAbstractEntity` | `type` enum (`DISCOUNT/BONUS/PERSONAL_DISCOUNT`), `start_date`, `end_date`, `condition_logic` (`AND`/`OR`), `discount_value` jsonb (type, value, applicability), `exclusions` jsonb, `gifts` jsonb, `gifts_replace_cart_items`, `user_groups` jsonb, `user_exclusions` jsonb, `position_id` (application priority) |
| `discount_conditions` | `BaseEntity` | `discount_id` (FK CASCADE), `condition_type` enum, `entity_ids` jsonb, `value` jsonb |
| `discount_coupons` | `BaseEntity` | `discount_id`, `code` (unique), `used_at`, `is_used`, `is_reusable`, `order_id`, composite index `(discount_id, is_used)` |
| `discount_bonus_balance` | `BaseEntity` | `user_id` UNIQUE (FK CASCADE), `balance` numeric(14,2) |

Order:
1. If bonuses are used — `PUT /discounts/settings` to set `bonusExpirationDays`, etc.
2. `POST /discounts` — create a discount (`type`, `localizeInfos`, `startDate`, `endDate`, `discountValue`, `conditions`, optionally `userGroups`, `gifts`).
3. (If a coupon is needed) `POST /discounts/:id/coupons` — manual code, or `POST /discounts/:id/coupons/generate` — bulk generation.

## Related `general_types` and `attribute_sets`

- `general_types.type = 'discount'` — link to the `discounts` module.
- `AttributesSetType.forDiscounts` — discount attributes (e.g., `banner_image` discount banner, `landing_url` link to the promo page, `terms_text` promo rules).
- **Application conditions** are stored in normalized `discount_conditions` (not in attribute_set) because conditions are structural (you need SQL to check `MIN_CART_AMOUNT`, `USER_LTV`), and attribute_set is for content fields.

`DiscountConditionType` enum (`cms/src/modules/discounts/types/discount.type.ts:12-21`):
- `PRODUCT`, `CATEGORY` — discount on specific products/categories.
- `ATTRIBUTE` — discount on products with attribute X (e.g., `material='wool'`).
- `PRODUCT_IN_CART`, `CATEGORY_IN_CART` — product/category must be in the cart.
- `MIN_CART_AMOUNT` — minimum cart amount.
- `USER_LTV`, `USER_ATTRIBUTE` — conditions on the buyer.

`DiscountValueType` enum:
- `NONE` — no numeric discount (gift only).
- `PERCENTAGE` — percentage.
- `FIXED_AMOUNT` — fixed amount off.
- `FIXED_PRICE` — re-price to fixed value.

`DiscountValueApplicability`: `TO_PRODUCT` or `TO_ORDER`.

## Full jsonb with data

### Discount "-20% in summer on items tagged summer" + coupon `SUMMER2026`

```json
{
  "id": 17,
  "identifier": "summer-2026",
  "type": "DISCOUNT",
  "startDate": "2026-06-01T00:00:00.000Z",
  "endDate":   "2026-08-31T23:59:59.000Z",
  "conditionLogic": "AND",
  "discountValue": {
    "discountType": "PERCENTAGE",
    "value": 20,
    "maxAmount": 5000,
    "applicability": "TO_PRODUCT"
  },
  "exclusions": [{ "id": "category-clearance", "isNested": true }],
  "gifts": [],
  "giftsReplaceCartItems": false,
  "userGroups": null,
  "userExclusions": [],
  "selectedAttributeMarkers": "banner_image",
  "positionId": 8801,
  "localizeInfos": {
    "en_US": { "title": "Summer sale -20%" }
  },
  "attributeSetId": 31,
  "attributesSets": {
    "en_US": {
      "banner_image": {
        "filename": "files/project/discount/17/banner.jpg",
        "downloadLink": "https://cdn.example/cloud-static/files/project/discount/17/banner.jpg",
        "previewLink": "https://cdn.example/cloud-static/files/project/discount/17/banner-preview.jpg",
        "size": 312088,
        "params": { "isImageCompressed": true },
        "contentType": "image/jpeg"
      },
      "landing_url": "/promo/summer-2026",
      "terms_text": {
        "htmlValue": "<p>Discount is not combinable with other promos.</p>",
        "plainValue": "Discount is not combinable with other promos.",
        "mdValue": "Discount is not combinable with other promos.",
        "params": { "isImageCompressed": true, "editorMode": "html" }
      },
      "is_visible_on_homepage": true,
      "priority_badge_color": { "title": "Red", "value": "red", "extended": { "type": "string", "value": "#dc2626" } }
    }
  },
  "conditions": [
    {
      "id": 401,
      "discountId": 17,
      "conditionType": "MIN_CART_AMOUNT",
      "value": { "amount": 3000 }
    },
    {
      "id": 402,
      "discountId": 17,
      "conditionType": "ATTRIBUTE",
      "entityIds": [{ "id": "tag", "isNested": false }],
      "value": { "tag": "summer" }
    }
  ]
}
```

### Coupon

```json
{
  "id": 5512,
  "discountId": 17,
  "code": "SUMMER2026",
  "isUsed": false,
  "isReusable": true,
  "usedAt": null,
  "orderId": null
}
```

### Bonus program (type=BONUS) + user balance

```json
{
  "id": 19,
  "identifier": "bonus-program",
  "type": "BONUS",
  "startDate": null,
  "endDate":   null,
  "discountValue": { "discountType": "PERCENTAGE", "value": 5, "applicability": "TO_ORDER" },
  "localizeInfos": {
    "en_US": { "title": "5% cashback bonuses" }
  },
  "bonusEvent": {
    "id": 71,
    "triggerEvent": "ORDER_PAID",
    "bonusExpirationDays": 90
  }
}
```

```json
{
  "id": 1102,
  "userId": 42,
  "balance": "1500.00",
  "createdAt": "2026-04-01T10:00:00.000Z",
  "updatedAt": "2026-05-13T14:22:00.000Z"
}
```

## Admin API (`@Controller('discounts')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `PUT` | `/discounts/settings` | — | Update global `discount_settings` (default bonuses, periods) |
| `POST` | `/discounts` | `discounts.create` | Create discount |
| `PUT` | `/discounts/:id` | `discounts.update` | Update |
| `DELETE` | `/discounts/:id` | `discounts.delete` | Delete |
| `PUT` | `/discounts/:id/position` | `discounts.updatePriority` | Change priority (`position`) — application order when discounts overlap |
| `POST` | `/discounts/:id/coupons` | — | Add coupon manually |
| `POST` | `/discounts/:id/coupons/generate` | — | Bulk generate N coupons (length, mask, template) |
| `DELETE` | `/discounts/:id/coupons/:couponId` | — | Delete one coupon |
| `DELETE` | `/discounts/:id/coupons` | — | Delete all coupons of a discount (batch) |
| `POST` | `/discounts/bonus-balance/adjust` | — | Manual adjustment of a user's bonus balance |

```http
POST /discounts

{
  "identifier": "summer-2026",
  "type": "DISCOUNT",
  "startDate": "2026-06-01T00:00:00.000Z",
  "endDate":   "2026-08-31T23:59:59.000Z",
  "conditionLogic": "AND",
  "discountValue": {
    "discountType": "PERCENTAGE",
    "value": 20,
    "maxAmount": 5000,
    "applicability": "TO_PRODUCT"
  },
  "attributeSetId": 31,
  "localizeInfos": { "en_US": { "title": "Summer sale -20%" } },
  "conditions": [
    { "conditionType": "MIN_CART_AMOUNT", "value": { "amount": 3000 } },
    { "conditionType": "ATTRIBUTE", "entityIds": [{ "id": "tag" }], "value": { "tag": "summer" } }
  ]
}
```

```http
POST /discounts/17/coupons/generate

{
  "count": 500,
  "codeLength": 8,
  "prefix": "SUMMER",
  "isReusable": false
}
```

```http
POST /discounts/bonus-balance/adjust

{
  "userId": 42,
  "delta": 500,
  "reason": "Compensation for delayed delivery of order #1024"
}
```

## Behind the scenes

- **Bull consumers (via cron service, not a queue per se):** `DiscountCronService` (`cms/src/modules/discounts/services/discount-cron.service.ts`) periodically checks discounts and pushes jobs:
  - `BULL_CONSUMERS.discountStart` (`'discount-start'`) — when `startDate` arrives, the discount activates (notification mailout to subscribers via `events`).
  - `BULL_CONSUMERS.discountEnd` (`'discount-end'`) — `endDate` passed, the discount deactivates.
  - `BULL_CONSUMERS.bonusExpiration` (`'bonus-expiration'`) — bonus expiration after `bonusExpirationDays`.
  - `BULL_CONSUMERS.bonusAccrual` (`'bonus-accrual'`) — bonus accrual on order payment.
  These consumers are job names in the `events` queue (`BULL_QUEUES.events = 'events'`), not separate queues.
- **WS.** On discount CRUD `admin-discounts.controller.ts` sends `socketService.sendMessage(payload, 'discounts', 'create' | 'update' | 'delete')` — open admin tabs refresh the list. No broadcasts on coupon/bonus events.
- **Journal** — `DISCOUNT_CREATED, DISCOUNT_UPDATED, DISCOUNT_DELETED`.
- **Permissions** — `discounts.{create,update,delete,updatePriority}`.
- **`position`** of the discount — fractional-ranking string (same as product positions). When several discounts overlap on one product, the one with higher (or lower — depending on direction) `position` applies.
- **`discount_settings`** — singleton record (one row per project), `PUT /discounts/settings`. Stores defaults: `bonusExpirationDays`, `bonusExpirationDate`, gift refund policies (`GiftRefundPolicy`).
- **Link to order:** when an order is paid, [04-order-flow.md](./04-order-flow.md) triggers discount application (`discount_bonus_usage_detail` records details), and `bonusAccrual` accrues bonuses.

## Links to other files

- [01-catalog-product.md](./01-catalog-product.md) — `DiscountConditionType.PRODUCT`/`CATEGORY`/`ATTRIBUTE` references products and their attributes.
- [04-order-flow.md](./04-order-flow.md) — an order applies the discount (records `coupon_id`, runs `bonusAccrual`).
- [06-event-notification.md](./06-event-notification.md) — `discountStart`/`discountEnd` can trigger subscriber mailouts.
- [08-users-and-groups.md](./08-users-and-groups.md) — `userGroups: EntityIdentifier[]` references `user_groups.id` for `PERSONAL_DISCOUNT`.

## Antipattern

**"Let's add a `products.discount_percent` column and always compute the discounted price right there."** Don't. It breaks the audit trail, doesn't work with different discount types (coupon / group / min amount), and prevents simultaneously applying two promos to one product. Correct way:

1. Create a `discount` (`type='DISCOUNT'`, `discountValue.discountType='PERCENTAGE'`, `value=20`).
2. Attach conditions — `discount_conditions` (on category, on product attribute).
3. Storefront on cart-add calls `/content/discounts/calculate` (or equivalent), which iterates over all active `discounts`, checks conditions, applies by `position`-priority, and returns the final price + list of applied discounts.

**"Let's add a `users.bonus_points` field."** Don't. The bonus balance is `discount_bonus_balance` (a separate table with history via `discount_bonus_transaction`). Otherwise the "when accrued / expired / spent" audit is lost.

**"Coupons are just `markers`."** No. `markers` is a project-wide dictionary of text labels, while `discount_coupons` is a table with a unique code, link to the discount, usage history, and FK to the order. Don't confuse them.
