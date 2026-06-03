<!-- audit: 5/5 (2026-05-13) endpoints[POST /payments/accounts, PUT /payments/accounts/:id, DELETE /payments/accounts/:id, POST /payments/accounts/:id/stripe/auth, PUT /payments/sessions/:id, GET /payments/refund/:id, PUT /payments/refund/:id, PUT /payments/status-maps], fields[payment_accounts.type (STRIPE/YOOKASSA/MIDTRANS/CUSTOM), payment_accounts.settings jsonb, payment_accounts.test_settings jsonb, payment_accounts.is_visible, payment_accounts.test_mode, payment_sessions.status (waiting/completed/canceled/expired), payment_sessions.type (session/intent), payment_refunds.status (pending/succeeded/failed/cancelled), payment_status_map.status_map jsonb, payment_stages.status (planned/completed)], queues[BULL_QUEUES.events + BULL_CONSUMERS.refund='refund' (refund job via shared events queue)], ws[no direct channels in admin-payments], fk[payment_sessions.order_id->orders.id (SET NULL), payment_sessions.subscription_id->user_subscriptions.id (SET NULL), payment_sessions.payment_account_id->payment_accounts.id (SET NULL), payment_refunds.payment_session_id->payment_sessions.id, payment_refunds.order_refund_id->order_refunds.id, payment_status_map.order_storage_id->orders_storage.id] -->

# 12. Payments and refunds: Stripe / YooKassa / Midtrans / Custom

## Purpose

OneEntry separates "**who accepts money**" from "**how it accepts**". The same online store can:

- Accept payments via **Stripe** (cards) for international customers.
- Via **YooKassa** for Russia.
- Via **Midtrans** for Indonesia (gopay, qris, virtual accounts).
- Via **Custom** (offline payment, cash to courier, corporate invoice).

And all four options live in the same `payment_accounts` table, with payment sessions in `payment_sessions`. Orders and subscriptions **don't know** about providers — the link is via FK.

Scenarios:
1. Creating a new Stripe payment account in the admin.
2. The user clicks "Pay" in the storefront → a `payment_session` is created with a provider link.
3. The provider sends a webhook → cms updates the session status.
4. The order moves to the status from `payment_status_map` (e.g., `waiting` payment → `payment_waiting` order).
5. The user requests a refund → `payment_refund` + Bull job `refund`.

## Entities and dependency hierarchy

```
orders_storage                    — multitenant: restaurant / branch / marketplace vendor
  ↑ order_storage_id
payment_status_map                — "session status → order status" mapping per orders_storage
                                  — each orders_storage has its own set of statuses and mapping

payment_accounts                  — provider (Stripe/YooKassa/Midtrans/Custom)
                                  — settings, test_settings — secrets, test_mode
  ↑ payment_account_id
payment_sessions                  — a specific payment attempt, linked to an order OR subscription
                                  — status, amount, session_id (provider's id), payment_url
  ↑ payment_session_id
payment_refunds                   — partial/full refunds
                                  — order_refund_id → orders/order_refunds (business-logic side)

payment_stages                    — payment stages on an order (prepayment + balance)
                                  — session_id (FK on the current active session)

payment_param_items               — custom account parameters (for UI)
```

| Table | Base class | Key fields |
|---|---|---|
| `payment_accounts` | `BaseAbstractEntity` | `identifier` UNIQUE, `type` (enum), `is_visible`, `test_mode`, `settings jsonb`, `test_settings jsonb`, `localize_infos` |
| `payment_sessions` | `BaseAbstractEntity` | `type` (`session`/`intent`), `order_id` (FK SET NULL), `subscription_id` (FK SET NULL), `payment_account_id` (FK SET NULL), `status`, `amount`, `session_id`, `payment_url`, `client_secret` |
| `payment_refunds` | own PK | `identifier`, `amount`, `payment_session_id` (FK), `order_refund_id` (FK), `status` |
| `payment_stages` | own PK | `order_id`, `product_id`, `marker`, `position`, `title`, `value`, `status` (`planned`/`completed`), `session_id` |
| `payment_status_map` | `BaseAbstractEntity` | `status_map jsonb`, `order_storage_id` |
| `payment_param_items` | `BaseAbstractEntity` | Account parameters in the UI |

## Related `general_types` and `attribute_sets`

`payment_accounts` does NOT inherit `BaseAttributeSetsAbstractEntity` — a payment account has no customizable attributes via `attribute_set`. Localization is only the name (`localize_infos.title`) for the UI.

Custom UI parameters for account configuration live separately — in `payment_param_items` (linked to `payment_account_id`).

## Full jsonb with data

### `payment_accounts` (Stripe account)

```json
{
  "id": 1,
  "identifier": "stripe-eu",
  "type": "stripe",
  "isVisible": true,
  "testMode": false,
  "localizeInfos": {
    "en_US": { "title": "Stripe (Europe)" }
  },
  "settings": {
    "publishableKey": "<pk_live_...>",
    "secretKey": "<sk_live_...>",
    "webhookSecret": "<whsec_...>",
    "automaticTaxEnabled": true,
    "successUrl": "https://shop.example.com/checkout/success",
    "cancelUrl": "https://shop.example.com/checkout/cancel"
  },
  "testSettings": {
    "publishableKey": "<pk_test_...>",
    "secretKey": "<sk_test_...>",
    "webhookSecret": "<whsec_...>"
  }
}
```

> **WARNING:** real `sk_live_*`, `whsec_*`, `pk_live_*` in DB jsonb fields are **live Stripe credentials**. In the admin panel they're returned only in masked form; in this example values are wrapped as `<...>` to emphasize they're placeholders.

### `payment_accounts` (Midtrans account)

```json
{
  "id": 2,
  "identifier": "midtrans-id",
  "type": "midtrans",
  "isVisible": true,
  "testMode": true,
  "localizeInfos": {
    "en_US": { "title": "Midtrans (Indonesia)" }
  },
  "settings": {
    "serverKey": "<hidden>",
    "successUrl": "https://shop.example.com/midtrans/success",
    "cancelUrl": "https://shop.example.com/midtrans/cancel",
    "paymentMethods": ["gopay", "qris", "bca_va", "shopeepay"],
    "sessionTimeout": 3600
  },
  "testSettings": {
    "serverKey": "<hidden>",
    "paymentMethods": ["gopay", "qris"]
  }
}
```

Full list of allowed Midtrans `paymentMethods` — `MIDTRANS_VALID_PAYMENT_METHODS` in `cms/src/modules/payments/types/payments.ts`. The default (`DEFAULT_MIDTRANS_ENABLED_PAYMENTS`) is `['gopay', 'qris']`.

### `payment_sessions` (order payment)

```json
{
  "id": 9012,
  "type": "session",
  "orderId": 4571,
  "subscriptionId": null,
  "paymentAccountId": 1,
  "status": "completed",
  "amount": 4350.00,
  "sessionId": "cs_live_a1b2c3d4...",
  "paymentUrl": "https://checkout.stripe.com/c/pay/cs_live_a1b2c3d4...",
  "successUrl": "https://shop.example.com/checkout/success",
  "cancelUrl": "https://shop.example.com/checkout/cancel",
  "clientSecret": "<hidden>",
  "createdDate": "2026-05-13T11:24:18.000Z"
}
```

`sessionId` is the provider's id (`cs_live_…` from Stripe, `order_id` from Midtrans, payment `id` from YooKassa). cms stores it in one column regardless of the provider.

### `payment_sessions` (subscription payment)

```json
{
  "id": 9013,
  "type": "intent",
  "orderId": null,
  "subscriptionId": 173,
  "paymentAccountId": 1,
  "status": "waiting",
  "amount": 990.00,
  "sessionId": "sub_a1b2c3d4...",
  "paymentUrl": null,
  "clientSecret": "<hidden>",
  "createdDate": "2026-05-13T11:30:00.000Z"
}
```

A subscription session is `type=intent` (off-session payment), `subscription_id` instead of `order_id`. See [17-subscriptions-billing.md](./17-subscriptions-billing.md).

### `payment_refunds`

```json
{
  "id": 1764,
  "identifier": "re_3OTaXY2eZvKYlo2C1aBcDeFg",
  "amount": 1500.00,
  "status": "succeeded",
  "createdDate": "2026-05-14T10:12:33.000Z"
}
```

With FKs: `payment_session_id = 9012`, `order_refund_id = 412` (FK on `order_refunds` from the order module). A refund can be **partial** (`amount < session.amount`).

### `payment_stages` (prepayment + balance)

```json
[
  {
    "id": 301,
    "orderId": 4571,
    "productId": 57,
    "marker": "prepayment",
    "position": 1,
    "title": "Prepayment 30%",
    "value": 1305.00,
    "status": "completed",
    "sessionId": 9012
  },
  {
    "id": 302,
    "orderId": 4571,
    "productId": 57,
    "marker": "balance",
    "position": 2,
    "title": "Balance on delivery",
    "value": 3045.00,
    "status": "planned",
    "sessionId": null
  }
]
```

`marker` is an arbitrary stage identifier. `value` is summed across all stages and must match `orders.total`. `status=planned` while unpaid, `completed` after payment.

### `payment_status_map`

```json
{
  "id": 1,
  "orderStorageId": 1,
  "statusMap": {
    "waiting": "payment_waiting",
    "completed": "paid",
    "canceled": "payment_failed",
    "expired": "payment_expired"
  }
}
```

The mapping: key is `PaymentSessionStatus`, value is the `identifier` of an `order_statuses` row in this `orders_storage`. Each `orders_storage` has its own mapping (a restaurant and an online store may name statuses differently).

## Admin API (`@Controller('payments')`)

### Accounts

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/payments/accounts` | `payments.accounts.create` | Create account |
| `PUT` | `/payments/accounts/:id` | `payments.accounts.update` | Update (including `settings`/`test_settings`) |
| `DELETE` | `/payments/accounts/:id` | `payments.accounts.delete` | Delete |
| `POST` | `/payments/accounts/:id/stripe/auth` | `payments.accounts.create` | Stripe OAuth link |
| `POST` | `/payments/accounts/:id/paypal/auth` | `payments.accounts.create` | PayPal OAuth (legacy) |
| `DELETE` | `/payments/accounts/:id/stripe` | `payments.accounts.delete` | Unlink Stripe |
| `DELETE` | `/payments/accounts/:id/paypal` | `payments.accounts.delete` | Unlink PayPal |
| `GET` | `/payments/accounts-types` | — | List of types (`PaymentAccountType` enum) |
| `GET` | `/payments/accounts-types/:type/payment-methods` | — | List of available methods for the provider (for Midtrans — `MIDTRANS_VALID_PAYMENT_METHODS`) |
| `GET` | `/payments/accounts/marker-validation/:marker` | — | `identifier` uniqueness check |

### Sessions

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `PUT` | `/payments/sessions/:id` | — | Update session status (as a reaction to a webhook or manual action) |

### Refunds

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/payments/refund/:id` | — | Refund details |
| `PUT` | `/payments/refund/:id` | `payments.refunds` | Update refund status (after provider response) |

### Status mapping

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/payments/status-maps/:id` | `payments.settings.get` | Get mapping by `orders_storage_id` |
| `PUT` | `/payments/status-maps` | `payments.settings.update` | Save mapping |

### Custom parameters

| Method | Path | Permission |
|---|---|---|
| `GET` | `/payments/payment-param-items` | `payments.settings.get` |
| `POST` | `/payments/payment-param-items` | `payments.settings.update` |
| `PUT` | `/payments/payment-param-items/:id` | `payments.settings.update` |
| `DELETE` | `/payments/payment-param-items/:id` | `payments.settings.update` |

### Example: create a Stripe account

```http
POST /payments/accounts

{
  "identifier": "stripe-eu",
  "type": "stripe",
  "isVisible": true,
  "testMode": false,
  "localizeInfos": {
    "en_US": { "title": "Stripe (Europe)" }
  },
  "settings": {
    "publishableKey": "<pk_live_…>",
    "secretKey": "<sk_live_…>",
    "webhookSecret": "<whsec_…>",
    "successUrl": "https://shop.example.com/checkout/success",
    "cancelUrl": "https://shop.example.com/checkout/cancel"
  },
  "testSettings": { "publishableKey": "<pk_test_…>", "secretKey": "<sk_test_…>" }
}
```

## Behind the scenes

### Bull queue `events` (shared mechanism)

Unlike `index-data`, `files`, `preview` — payments has **no dedicated Bull queue**. All async actions go through the shared `BULL_QUEUES.events` queue:

| `BULL_CONSUMERS.*` | Job name | What triggers it |
|---|---|---|
| `refund` | `'refund'` | After `PUT /payments/refund/:id` with status `succeeded` → `EventsProcessor` finds events with `type='attribute'`/`type='status'` and matching conditions, sends notifications (see 06) |

Inside `EventsProcessor.refund(job)`:
1. Find related `events` for the `payments` module.
2. Substitute placeholders (`{{order.number}}`, `{{refund.amount}}`).
3. Publish to RabbitMQ → `notice-service` delivers email/push.

### Stripe / Midtrans services

Provider-specific services live in `cms/src/modules/payments/services/`:
- `StripeService` — creates `Stripe.Checkout.Session` / `Stripe.PaymentIntent`, verifies webhooks via `webhookSecret`.
- `MidtransService` — `Midtrans.Snap.createTransaction`, validates notifications by `signature_key`.

They're injected into `AdminPaymentsService` based on `payment_accounts.type` — which implementation to use.

### Webhook reception

Storefront endpoint `/api/content/payments/webhook` (see `URL_EXEMPTS` in `cms/src/config/constants.ts`) receives the provider callback. Inside:
1. Signature verification via `webhookSecret` (Stripe) / `signature_key` (Midtrans).
2. Lookup of `payment_sessions.session_id` by the id from the webhook.
3. Update `status` → if `completed` → emit a job to the `events` Bull queue with the matching trigger (`change-order-status` → `orders.status_id` is changed per `payment_status_map`).

The webhook route is excluded from `AdminAuthGuard` via `URL_EXEMPTS` — there's no auth there, only the provider's signature.

### Journal

`JournalingEvents.PAYMENT_ACCOUNT_CREATED / PAYMENT_ACCOUNT_UPDATED / PAYMENT_ACCOUNT_DELETED`, `PAYMENT_SESSION_CREATED / PAYMENT_SESSION_UPDATED / PAYMENT_SESSION_DELETED`. See `cms/src/modules/journal/types/journaling-events.ts:103-108`.

### Permissions

`payments.accounts.{create, update, delete}`, `payments.settings.{get, update}`, `payments.refunds`. Full list — `AdminPermissionsEnum`.

## Links to other files

- [04-order-flow.md](./04-order-flow.md) — `orders.id` ← `payment_sessions.order_id`. Status mapping via `payment_status_map.statusMap`. Refunds — via `order_refunds.id` ← `payment_refunds.order_refund_id`.
- [06-event-notification.md](./06-event-notification.md) — Bull `events` consumer `refund` sends a notification on refund.
- [17-subscriptions-billing.md](./17-subscriptions-billing.md) — `user_subscriptions.id` ← `payment_sessions.subscription_id`. **Subscription refunds use the same `payment_refunds`** — there's no separate `subscription_refunds` table.
- `agents_datasets/ClaudeInfos/patterns-controllers.md` — `admin-*.controller.ts` + `@GrantByPermission` pattern.

## Antipattern

**"I'll add a `stripe_session_id` column to `orders`."** Don't:

1. That ties the orders table to a specific provider — if we add YooKassa tomorrow, we'll need another `yookassa_session_id` column, and so on.
2. Searching by `payments` will require JOINs from different columns — slow and inflexible.
3. The history of provider switches on the order is lost — `stripe_session_id` gets overwritten.
4. Refunds across different providers turn into a zoo of ad-hoc logic.

Correct way:

1. `payment_sessions` stores a **universal** `session_id` (string) — independent of the provider.
2. `payment_sessions.payment_account_id` indicates which account (=provider) was used.
3. **One order → many `payment_sessions`** (if the previous one expired or was cancelled) — history is preserved.
4. All refunds go through `payment_refunds.payment_session_id`. One mechanism for all providers and for subscriptions.

**"I'll make a separate `subscription_payments` table for subscription payments."** Don't — it's the **same `payment_sessions`** with `type='intent'` and `subscription_id` instead of `order_id`. Otherwise you'd have to duplicate webhook logic, status mapping, refunds. See file 17.
