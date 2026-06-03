<!-- audit: 5/5 (2026-05-13) endpoints[POST /subscriptions, PUT /subscriptions/:id, DELETE /subscriptions/:id, GET /subscriptions/user/:id, GET /subscriptions/:id, GET /subscriptions/marker-validation/:marker], fields[subscriptions.product_ids jsonb (number[]), subscriptions.period_in_days, user_subscriptions.status (PENDING/ACTIVE/CANCELED/UNPAID/PAST_DUE/INCOMPLETE/INCOMPLETE_EXPIRED), user_subscriptions.stripe_subscription (uniq), user_subscriptions.midtrans_subscription_id (uniq), user_subscriptions.due_date, user_subscriptions.lang_code, stripe_customers.customer (uniq text), midtrans_customers UNIQUE (user_id, payment_account_id), midtrans_customers.saved_token_id], queues[BULL_QUEUES.events + BULL_CONSUMERS.refund='refund'/mailing='mailing' (via the shared events queue)], ws[no direct ws in subscriptions], fk[user_subscriptions.user_id->users.id (SET NULL), subscription_id->subscriptions.id (CASCADE), payment_account_id->payment_accounts.id (SET NULL), stripe_customer_id->stripe_customers.id, midtrans_customer_id->midtrans_customers.id (SET NULL); subscriptions.payment_account_id->payment_accounts.id; payment_sessions.subscription_id->user_subscriptions.id (SET NULL); midtrans_customers.user_id->users.id (CASCADE)] -->

# 17. Subscriptions and billing: Stripe + Midtrans

## Purpose

A subscription is a **recurring payment** for access to a set of products/services. Scenarios:

- SaaS service: "Pro account at $9.90/month".
- Coffee subscription: "Freshly roasted coffee shipped every two weeks".
- Premium content access: "PDF magazine via subscription".
- Multi-product access: "12 online courses in one subscription".

OneEntry supports **two subscription providers**:
1. **Stripe** (carded, off-session, recurring via Stripe Subscriptions API).
2. **Midtrans** (Indonesia, primarily uses `saved_token_id` for repeat charges).

Refunds and actual payments go through the **same shared `payments` module** (see [12-payments-and-refunds.md](./12-payments-and-refunds.md)). Subscriptions **do not have** their own payments table — they reuse `payment_sessions` with `type='intent'` and `subscription_id`.

## Entities and dependency hierarchy

```
products                          — products included in a subscription (id array)
payment_accounts                  — provider (Stripe / Midtrans)
                                    settings.{secretKey,webhookSecret} see file 12
  ↑ payment_account_id
subscriptions                     — subscription plan: products, period, identifier
                                    product_ids jsonb (number[])
                                    period_in_days (default 30)
  ↑ subscription_id (CASCADE)
user_subscriptions                — a specific subscription of a specific user
                                    status (UserSubscriptionStatus)
                                    due_date, lang_code
                                    stripe_subscription / midtrans_subscription_id (unique per provider)

stripe_customers                  — customer record at Stripe (1:1 with users)
                                    customer (text uniq — Stripe customer id)
midtrans_customers                — saved token at Midtrans (per user, per payment_account)
                                    saved_token_id, card_masked
                                    UNIQUE(user_id, payment_account_id)

payment_sessions.subscription_id  — every subscription payment = a new session
                                    (see file 12, type='intent')
```

| Table | Base class | Key fields |
|---|---|---|
| `subscriptions` | own PK | `identifier` indexed, `localize_infos jsonb`, `product_ids jsonb (number[])`, `period_in_days`, `payment_account_id` (FK) |
| `user_subscriptions` | own PK | `user_id` (FK SET NULL), `subscription_id` (FK CASCADE), `payment_account_id` (FK SET NULL), `stripe_subscription` (uniq), `midtrans_subscription_id` (uniq), `stripe_customer_id` (FK), `midtrans_customer_id` (FK SET NULL), `status` (enum), `due_date`, `lang_code` |
| `stripe_customers` | own PK | `customer` (text uniq), `user_id` (uniq FK) |
| `midtrans_customers` | own PK | UNIQUE `(user_id, payment_account_id)`, `saved_token_id`, `card_masked` |

### `UserSubscriptionStatus` (7 values)

```ts
PENDING            = 'pending'             // created, waiting for the first payment
ACTIVE             = 'active'              // active, paid, period running
CANCELED           = 'canceled'            // canceled by the user, not renewed
UNPAID             = 'unpaid'              // period elapsed, payment did not go through
PAST_DUE           = 'past_due'            // payment failed, provider retries
INCOMPLETE         = 'incomplete'          // provider initialized but first payment not confirmed
INCOMPLETE_EXPIRED = 'incomplete_expired'  // first payment never went through
```

These statuses map directly to Stripe Subscription statuses — that's intentional, to avoid mapping back and forth.

## Related `general_types` and `attribute_sets`

`subscriptions` **does NOT extend `BaseAttributeSetsAbstractEntity`** — a subscription plan has no customizable attributes through an `attribute_set`. Localization is limited to `localize_infos.title`/`description` for UI display. If you need custom plan fields (e.g. "access level", "device count"), put them into `product_ids` ⊂ `products`, and those attributes live on the products.

## Full jsonb with data

### `subscriptions` (plan)

```json
{
  "id": 5,
  "identifier": "premium-monthly",
  "localizeInfos": {
    "en_US": {
      "title": "Premium access (monthly)",
      "description": "Access to all content, ad-free, HD downloads."
    }
  },
  "productIds": [301, 302, 305],
  "periodInDays": 30,
  "paymentAccountId": 1,
  "createdDate": "2026-01-15T09:00:00.000Z",
  "updatedDate": "2026-04-20T14:30:00.000Z"
}
```

**`productIds` is the array of product ids** included in the subscription. The same product can belong to multiple subscriptions (e.g. "article access" in both Standard and Premium).

### `subscriptions` (multi-product, coffee by subscription)

```json
{
  "id": 6,
  "identifier": "coffee-bi-weekly",
  "localizeInfos": {
    "en_US": { "title": "Coffee subscription (bi-weekly)" }
  },
  "productIds": [57, 92, 105],
  "periodInDays": 14,
  "paymentAccountId": 2
}
```

### `user_subscriptions` (Stripe user, active)

```json
{
  "id": 173,
  "userId": 42,
  "subscriptionId": 5,
  "paymentAccountId": 1,
  "stripeSubscription": "sub_1OabcdEfghIJklmNop",
  "stripeCustomerId": 28,
  "midtransSubscriptionId": null,
  "midtransCustomerId": null,
  "status": "active",
  "dueData": "2026-06-13T09:00:00.000Z",
  "langCode": "en_US",
  "createdDate": "2026-05-13T09:00:00.000Z",
  "updatedDate": "2026-05-13T09:01:23.000Z"
}
```

### `user_subscriptions` (Midtrans user, pending)

```json
{
  "id": 174,
  "userId": 43,
  "subscriptionId": 6,
  "paymentAccountId": 2,
  "stripeSubscription": null,
  "stripeCustomerId": null,
  "midtransSubscriptionId": "MTSUB-2026-05-13-17a2",
  "midtransCustomerId": 14,
  "status": "pending",
  "dueData": "2026-05-27T09:00:00.000Z",
  "langCode": "en_US"
}
```

### `stripe_customers`

```json
{
  "id": 28,
  "customer": "cus_OabcdEfghIJklmNop",
  "userId": 42,
  "createdAt": "2026-05-13T08:59:55.000Z"
}
```

`customer` is the Stripe Customer ID (`cus_…`). UNIQUE: exactly one row per user, and exactly one per Stripe Customer.

### `midtrans_customers`

```json
{
  "id": 14,
  "userId": 43,
  "paymentAccountId": 2,
  "savedTokenId": "<midtrans_saved_token_id>",
  "cardMasked": "4811-11**-****-1114",
  "createdAt": "2026-05-13T09:00:10.000Z"
}
```

UNIQUE `(user_id, payment_account_id)` — a user may have several saved cards **across different payment accounts** (e.g. separate cards per branch), but only one within a single account.

## Admin API (`@Controller('subscriptions')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/subscriptions/user/:id` | — | Active subscriptions of a specific user (`user_subscriptions` JOIN `subscriptions`) |
| `GET` | `/subscriptions/:id` | — | Plan details |
| `POST` | `/subscriptions` | `subscriptions.create` | Create a plan |
| `PUT` | `/subscriptions/:id` | `subscriptions.update` | Update a plan |
| `DELETE` | `/subscriptions/:id` | `subscriptions.delete` | Delete a plan (CASCADE → user_subscriptions are deleted) |
| `GET` | `/subscriptions/marker-validation/:marker` | — | `identifier` uniqueness check |

Plus from `BaseSubscriptionController` — `GET /subscriptions` (shared list).

```http
POST /subscriptions

{
  "identifier": "premium-monthly",
  "localizeInfos": {
    "en_US": { "title": "Premium access (monthly)" }
  },
  "productIds": [301, 302, 305],
  "periodInDays": 30,
  "paymentAccountId": 1
}
```

### Restrictions on changes when active subscriptions exist

If a plan has `user_subscriptions` with `status='active'`, `PUT /subscriptions/:id` cannot change:
- `identifier` (marker) — would break the link with the provider.
- `paymentAccountId` — the provider is already attached to its sub_id.
- `periodInDays` — would break `due_date` calculation.

The guard lives in `AdminSubscriptionsService` (`admin-subscriptions.service.ts:69-86`).

## Behind the scenes

### Subscription lifecycle

1. **Plan created** in the admin panel via `POST /subscriptions`.
2. **User subscribes** on the storefront → `payment_sessions` is created with `type='intent'`, `subscription_id=null`, `payment_account_id=<plan.paymentAccountId>`.
3. Request goes to the provider:
   - **Stripe:** `StripeService.createSubscription(customer, priceId)` → `sub_…` id.
   - **Midtrans:** `MidtransService.createSubscription(...)` using `saved_token_id`.
4. A `user_subscriptions` row is created with `status='pending'`, `stripe_subscription`/`midtrans_subscription_id` populated.
5. The provider's webhook (`/api/content/payments/webhook`) → `payment_sessions.status='completed'` + `user_subscriptions.status='active'`.
6. When `period_in_days` elapses, the provider performs an off-session charge → a new `payment_sessions` for the same `user_subscriptions`.
7. If the charge fails → `status='past_due'` → retries → `status='unpaid'` or `canceled`.

### Bull queue `events` (shared notifications mechanism)

Subscriptions **don't have their own Bull queue** — they use the shared `BULL_QUEUES.events`:

| Job | When |
|---|---|
| `'mailing'` (`BULL_CONSUMERS.mailing`) | Recurring reminders "3 days until charge", "subscription successfully renewed". Triggered by events (`events.type='attribute'` or `'status'`) from 06. |
| `'refund'` (`BULL_CONSUMERS.refund`) | After `PUT /payments/refund/:id` (a refund on a subscription session). |

### Services

| Service | What it does |
|---|---|
| `AdminSubscriptionsService` | Plan CRUD, validation of change restrictions when active subscriptions exist |
| `BaseSubscriptionService` | Shared logic for admin + content |
| `ContentSubscriptionsService` | Storefront subscription API (the user sees and cancels their subscriptions) |
| `SubscriptionPriceSyncService` | Syncs product prices with the provider (Stripe Price API) — if the plan has `productIds=[301]` and the price of product 301 changes, the Stripe Price needs to be updated |
| `StripeService` (from payments module) | `createCustomer`, `createSubscription`, `cancelSubscription`, `refund` |
| `MidtransService` (from payments module) | `createSubscription` with `saved_token_id`, `chargeSubscription`, `cancelSubscription` |

### Connection to payments

```
user_subscriptions.id ─── payment_sessions.subscription_id (SET NULL)
                          payment_sessions.type = 'intent'
                          payment_sessions.amount = <price>
                          payment_sessions.status = waiting/completed/canceled/expired
                              ↓
                          payment_refunds.payment_session_id
```

**The same** `payment_refunds` mechanism works for one-off orders and subscriptions alike. There is no dedicated `subscription_refunds` (see the antipattern).

### Webhook handling

The webhook from Stripe / Midtrans hits `POST /api/content/payments/webhook` (excluded from `AdminAuthGuard` via `URL_EXEMPTS`). Inside:
1. Signature verification (`stripe-signature` header against `payment_accounts.settings.webhookSecret`).
2. If `event.type === 'invoice.payment_succeeded'`:
   - Find `user_subscriptions` by `stripeSubscription`.
   - Create `payment_sessions` with `subscription_id`, `status='completed'`.
   - Update `due_date = now + period_in_days`.
3. If `'invoice.payment_failed'` → `status='past_due'`.
4. If `'customer.subscription.deleted'` → `status='canceled'`.

### Sensitive credentials

`payment_accounts.settings.secretKey`, `webhookSecret`, `publishableKey` for Stripe; `serverKey` for Midtrans — all of this **is already covered in [12-payments-and-refunds.md](./12-payments-and-refunds.md)**. Credentials are not duplicated in this document — subscriptions use the existing `payment_account_id`.

### Journal

In `cms/src/modules/journal/types/journaling-events.ts` there are **no** subscription-specific events (as of 2026-05-13). Plan create/update/delete are written as regular admin-endpoint operations, but not tagged with a specific `JournalingEvents.SUBSCRIPTION_*`. If needed — add entries to the enum.

### Permissions

`subscriptions.{create, update, delete}` in `AdminPermissionsEnum`. Provisioned through the seed `cms/src/seeds/1870795700001-seed-subscriptions.ts` (which also creates `modules.id=17` for subscriptions — see [19-third-party-modules.md](./19-third-party-modules.md)).

## Cross-references

- [04-order-flow.md](./04-order-flow.md) — one-off orders use `payment_sessions.order_id`; subscriptions use `payment_sessions.subscription_id`. A single payment mechanism.
- [08-users-and-groups.md](./08-users-and-groups.md) — `users.id` ← `user_subscriptions.user_id`. Subscription↔group link: a user with an active subscription can automatically be granted a `user_group_id` (via `events.type='attribute'`).
- [12-payments-and-refunds.md](./12-payments-and-refunds.md) — **the canonical document for payment mechanics**. Subscription refunds = `payment_refunds.payment_session_id` on a session with `subscription_id`.
- [06-event-notification.md](./06-event-notification.md) — billing reminders and cancellation notices go through the `events` Bull queue, consumer `mailing`.
- [19-third-party-modules.md](./19-third-party-modules.md) — `modules.id=17` (`identifier='subscriptions'`) added via the seed.

## Antipatterns

**"I'll create a separate `subscription_payments` table for subscription charges."** Don't:

1. **The webhook is the same** — both an order and a subscription get `invoice.payment_succeeded` from Stripe. The handling logic overlaps by 90%.
2. **Refunds are the same** — `payment_refunds` already links to any session via `payment_session_id`.
3. **Status mapping is the same** — `payment_status_map` for `orders_storage` and a duplicate for subscriptions would be redundant.
4. **The admin UI** would have to be written in two places.

The right approach: **`payment_sessions` with `subscription_id` instead of `order_id`** — one universal mechanism for one-off and recurring payments. See file 12.

**"I'll add a `current_subscription_id` column to `users`."** Don't:

1. A user may have **multiple simultaneous subscriptions** (e.g. on different product groups) — one column can't hold them.
2. Subscription history (canceled, expired) is lost.
3. Cascade rules (`SET NULL` on plan deletion) break.

The right approach: `user_subscriptions` — many-to-one with `users`, history preserved through the `status` enum.

**"I'll stash Stripe `sk_live_*` into `subscriptions.settings`."** Don't:

1. Provider credentials are an **attribute of the payment account**, not the plan. A single account serves many plans.
2. They currently live in `payment_accounts.settings` (masked in the API) — one storage location, one rotation flow.
3. Duplicating them into `subscriptions.settings` would require updating N rows on every key rotation.

The right approach: `subscriptions.payment_account_id → payment_accounts.id`. Credentials live in one place, in `payment_accounts.settings` (see file 12).
