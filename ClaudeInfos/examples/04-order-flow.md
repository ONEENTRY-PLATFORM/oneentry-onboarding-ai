<!--
audit: 5/5 (2026-05-13)
endpoints[
  POST /orders-storage,
  PUT /orders-storage/:id,
  PUT /orders-storage/:id/orders/:orderId/change-status,
  POST /orders-storage/:id/order-statuses,
  PUT /orders-storage/:id/order-statuses/:statusId,
  DELETE /orders-storage/:id/orders/:orderId
]
fields[
  orders.storage_id,
  orders.status_id,
  orders.payment_account_id,
  orders.form_data jsonb,
  orders.discount_config jsonb,
  orders.payment_strategy,
  orders.lang_code,
  order_products.product_id+order_id unique,
  order_statuses.is_default,
  orders_storage.form_id,
  orders_storage.price_expiration
]
queues[BULL_CONSUMERS.changeOrderStatus (job name 'change-order-status' in the events queue)]
ws[admin-orders-storage: 'orders-storage' delete]
fk[
  orders.storage_id->orders_storage.id CASCADE,
  orders.status_id->order_statuses.id SET NULL,
  orders.payment_account_id->payment_accounts.id SET NULL,
  order_products.order_id->orders.id CASCADE
]
-->

# 04. Order: cart → checkout → payment → delivery → fulfillment

## Purpose

Any "paid order" business process:
- **E-commerce order**: cart → checkout → online payment → packing → shipping → delivery.
- **Restaurant order**: "received → cooking → ready → handed out".
- **Service booking**: "booked → confirmed → completed".
- **Subscription**: recurring order (`payment_strategy`).
- **Refund request**: `order_refund_request` → `order_refund`.

OneEntry separates:
- **`orders_storage`** — an "order slot" with its own set of statuses, checkout form, attached payment accounts. One project — multiple storages ("Retail", "Wholesale", "Restaurant").
- **`orders`** — a specific order.
- **`order_statuses`** — status dictionary **per storage** (each storage has its own set).
- **`order_products`** — products in the order with a fixed price.

## Entities and dependency hierarchy

```
forms                          — checkout form (payer/recipient/delivery fields)
  ↑ form_id (nullable)
orders_storage                 — order storage: localize_infos, form_id, general_type_id, price_expiration
  ↑ storage_id (CASCADE)
  ├── orders                   — specific order (storage_id, status_id, user_id, form_data, currency, payment_strategy)
  │   ↑ order_id (CASCADE)
  │   ├── order_products       — products in the order (product_id, quantity, price snapshot, is_gift)
  │   ├── orders_history       — status transition log
  │   └── order_refund(_request) — refund
  ├── order_statuses           — statuses (storage_id, identifier, is_default, position)
  └── orders_storage_payment_accounts_mn — M:N storage ↔ payment accounts

payment_accounts (separate module) ← payment_account_id (SET NULL)
users (separate table)             ← user_id (SET NULL)
products                            ← order_products.product_id (no formal FK on ProductEntity, but the index exists)
```

| Table | Base class | Key fields |
|---|---|---|
| `orders_storage` | `BaseAbstractEntity` | `localize_infos`, `form_id` (checkout form), `general_type_id`, `selected_attribute_markers`, `price_expiration` (`'10m'` price-lock window), CASCADE with orders |
| `orders` | — | Does NOT inherit `BaseAttributeSetsAbstractEntity` — orders have no attribute_set. `storage_id` (FK CASCADE), `user_id` (SET NULL), `status_id` (SET NULL), `payment_account_id` (SET NULL), `currency`, `lang_code`, `form_data` (jsonb with checkout data), `import_id`, `payment_strategy` enum, `discount_config` jsonb, `created_date` |
| `order_products` | — | `product_id` (index, no FK to products), `order_id` (FK CASCADE), `quantity`, `price` numeric(15,2), `is_gift` boolean, unique `(product_id, order_id, is_gift)` |
| `order_statuses` | `BaseAbstractEntity` | `localize_infos`, `is_default` (one per storage), `storage_id` (FK CASCADE), `position_id` |
| `orders_history` | `BaseEntity` | history feed, `order_id`, status/field changes |

Creation order:
1. Create `forms` (opt.) for checkout — see [03-form-submission.md](./03-form-submission.md).
2. Create `orders_storage` via `POST /orders-storage` (with `formId`, `generalTypeId` = id of `order`, `localizeInfos`).
3. Create a set of `order_statuses` via `POST /orders-storage/:id/order-statuses` (new, waiting, ready, delivered, cancelled). **One status** must be `is_default=true`.
4. (Opt.) Attach payment accounts via the separate `payments` endpoint.
5. Storefront / admin creates an order — an `orders` record with `storage_id`, `status_id` (defaults to `is_default`), `user_id`, `form_data` (populated from the checkout form).

## Related `general_types` and `attribute_sets`

- `general_types.type = 'order'` (id=21, from migration `1744702199257-update-general-types.ts`).
- `AttributesSetType.forOrders` — order attributes. **Note:** `OrderEntity` itself has NO `attribute_set_id`/`attributes_sets` (it does not inherit `BaseAttributeSetsAbstractEntity`). Order attributes are stored via **`form_data`** (fields filled at checkout) — this is `FormDataLangType`, not `attributes_sets`. If you need arbitrary additional order fields — add them through the checkout form schema, not through attribute_set.

## Full jsonb with data

### Order storage "Retail"

```json
{
  "id": 1,
  "identifier": "retail",
  "formId": 31,
  "generalTypeId": 21,
  "selectedAttributeMarkers": "customer_name,total",
  "priceExpiration": "10m",
  "localizeInfos": {
    "en_US": { "title": "Retail orders" }
  }
}
```

### Order statuses for the storage

```json
[
  { "id": 11, "identifier": "new",       "storageId": 1, "isDefault": true,  "localizeInfos": { "en_US": { "title": "New" } } },
  { "id": 12, "identifier": "paid",      "storageId": 1, "isDefault": false, "localizeInfos": { "en_US": { "title": "Paid" } } },
  { "id": 13, "identifier": "assembled", "storageId": 1, "isDefault": false, "localizeInfos": { "en_US": { "title": "Assembled" } } },
  { "id": 14, "identifier": "shipped",   "storageId": 1, "isDefault": false, "localizeInfos": { "en_US": { "title": "Shipped" } } },
  { "id": 15, "identifier": "delivered", "storageId": 1, "isDefault": false, "localizeInfos": { "en_US": { "title": "Delivered" } } },
  { "id": 16, "identifier": "cancelled", "storageId": 1, "isDefault": false, "localizeInfos": { "en_US": { "title": "Cancelled" } } }
]
```

### Order

```json
{
  "id": 1024,
  "identifier": "order-1024",
  "storageId": 1,
  "userId": 42,
  "statusId": 12,
  "paymentAccountId": 3,
  "currency": "USD",
  "langCode": "en_US",
  "paymentStrategy": "once",
  "importId": null,
  "createdDate": "2026-05-13T14:00:00.000Z",
  "discountConfig": {
    "appliedDiscounts": [
      { "discountId": 17, "couponCode": "SUMMER2026", "value": 290, "applicability": "TO_PRODUCT" }
    ],
    "bonusUsed": 100
  },
  "formData": {
    "en_US": [
      { "marker": "customer_name",    "type": "string", "value": "John Doe" },
      { "marker": "customer_email",   "type": "string", "value": "john@example.com" },
      { "marker": "customer_phone",   "type": "string", "value": "+1 415 000-0000" },
      { "marker": "delivery_address", "type": "text",
        "value": [{
          "htmlValue": "<p>San Francisco, Market St 1, apt 12</p>",
          "plainValue": "San Francisco, Market St 1, apt 12",
          "mdValue": "San Francisco, Market St 1, apt 12",
          "params": { "isImageCompressed": true, "editorMode": "html" }
        }]
      },
      { "marker": "delivery_method", "type": "list",
        "value": { "title": "Courier", "value": "courier", "extended": { "type": "string", "value": "courier" } }
      },
      { "marker": "delivery_date", "type": "dateTime",
        "value": { "fullDate": "2026-05-15T14:00:00.000Z", "formattedValue": "15-05-2026 14:00", "formatString": "DD-MM-YYYY HH:mm" }
      },
      { "marker": "needs_receipt", "type": "radioButton", "value": true }
    ]
  },
  "orderProducts": [
    { "id": 5001, "orderId": 1024, "productId": 1234, "quantity": 2, "price": "1450.00", "isGift": false },
    { "id": 5002, "orderId": 1024, "productId": 8801, "quantity": 1, "price": "0.00",    "isGift": true  }
  ]
}
```

Note:
- `order_products.price` is a **snapshot of the price at order creation time**, not the current product price. The product price may change after the order, but the order keeps the locked value.
- `is_gift: true` — gift line (from `gifts` discount, see [05-discount-promo.md](./05-discount-promo.md)). Price `0.00`. Unique `(product_id, order_id, is_gift)` allows having both a regular and a gift copy of the same product.
- The order has **no** `attributes_sets` of its own. All checkout "extra fields" — in `form_data`.

## Admin API

### Storages (`@Controller('orders-storage')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/orders-storage` | `orders.storage.create` | Create a storage |
| `PUT` | `/orders-storage/:id` | `orders.storage.update` | Update (`formId`, `localizeInfos`, etc.) |
| `DELETE` | `/orders-storage/:id` | `orders.storage.delete` | Delete (orders are cascade-deleted!) |
| `POST` | `/orders-storage/:id/order-statuses` | `orders.storage.order-status.create` | Create a status |
| `PUT` | `/orders-storage/:id/order-statuses/:statusId` | `orders.storage.order-status.update` | Update |
| `PUT` | `/orders-storage/:id/order-statuses/:statusId/position` | `orders.storage.order-status.changePositions` | Reorder statuses |
| `PUT` | `/orders-storage/:id/orders/:orderId/change-status` | `orders.storage.order-status.update` | Change a specific order's status |
| `DELETE` | `/orders-storage/:id/orders/:orderId` | `orders.storage.order.delete` | Delete an order |
| `DELETE` | `/orders-storage/:id/orders` | — | Batch order deletion |

```http
POST /orders-storage

{
  "identifier": "retail",
  "formId": 31,
  "generalTypeId": 21,
  "localizeInfos": { "en_US": { "title": "Retail orders" } }
}
```

```http
POST /orders-storage/1/order-statuses

{
  "identifier": "paid",
  "isDefault": false,
  "localizeInfos": { "en_US": { "title": "Paid" } }
}
```

```http
PUT /orders-storage/1/orders/1024/change-status

{
  "statusIdentifier": "assembled"
}
```

After this, `base-order.service.ts` pushes a job to the `events` queue:
```ts
this.eventsQueue.add(BULL_CONSUMERS.changeOrderStatus, { orderId, newStatusId, oldStatusId, ... });
```

### Orders (`@Controller('orders')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/orders/refund-requests` | — | Refund request (creates `order_refund_request`) |

The list of orders / order details mostly go through the `orders-storage` controller. Refunds are managed by a separate endpoint.

## Behind the scenes

- **Bull queue `events` + consumer `change-order-status`** — on status change the consumer finds subscribed `events` (`type='status'` matching `ordersStorage` + `orderStatus`) and sends notifications via RabbitMQ → `notice-service`. See [06-event-notification.md](./06-event-notification.md).
- **Bull job `BULL_CONSUMERS.refund` in the `events` queue** — refund processing (actual debit from the account). The job is enqueued in `payment-refund.service.ts:93` (`this.eventsQueue.add(BULL_CONSUMERS.refund, ...)`), processed in `events.consumer.ts:307` (`@Process(BULL_CONSUMERS.refund)`). There's no separate `refund` queue — it's a job inside the shared `events` queue.
- **Bull consumer `bonusAccrual`** — when transitioning to a status considered "paid" (by project convention), bonuses are accrued. See [05-discount-promo.md](./05-discount-promo.md).
- **WS.** On storage deletion `admin-orders-storage.controller.ts:607` sends `socketService.sendMessage(payload, 'orders-storage', 'delete')` — open admin tabs remove the storage from the list. On order status change a broadcast is **not** sent by default (can be configured via `events` with `actions.isWebsocket=true`).
- **Journal.** `ORDER_CREATED, ORDER_UPDATED, ORDER_DELETED, ORDER_STORAGE_*, ORDER_STORAGE_ORDER_STATUS_*`. **Order creation is marked `ORDER_CREATED` via an interceptor**, although in the events enumeration some are commented out (`// ORDER_STATUS_CREATED`) — comments in `journaling-events.ts` mean that order statuses are not journaled separately (they're under the general `ORDER_STORAGE_ORDER_STATUS_*`).
- **Permissions.** `orders.{get,create,update,delete,email}`, `orders.storage.{create,update,delete}`, `orders.storage.order.{update,delete}`, `orders.storage.order-status.{create,update,delete,changePositions}`.
- **`price_expiration`** on storage — how many minutes the price is locked when a product is added to the cart (`'10m'` by default). This prevents payment at "yesterday's" price.
- **`payment_strategy`** on the order — `OrderPaymentStrategy` enum, defines one-off or recurring (`once`/`recurring`/`split`).

## Links to other files

- [01-catalog-product.md](./01-catalog-product.md) — `order_products.product_id` references `products.id` (index without FK, so deleting a product doesn't cascade-delete orders).
- [03-form-submission.md](./03-form-submission.md) — `orders_storage.form_id` references the checkout form. Order fields = fields of this form.
- [05-discount-promo.md](./05-discount-promo.md) — `orders.discount_config` jsonb stores applied discounts and coupons; `bonusAccrual` awards bonuses upon payment.
- [06-event-notification.md](./06-event-notification.md) — `change-order-status` consumer triggers email/push to the client.
- [08-users-and-groups.md](./08-users-and-groups.md) — `orders.user_id` references `users.id` (SET NULL — guest's anonymous orders survive user deletion).

## Antipattern

**"Order fields — let's add them to an `attribute_set` of type `forOrders` and link it to `OrderEntity` via `attribute_set_id`."** Don't: `OrderEntity` has NO `attribute_set_id` (see `order.entity.ts:26` — `OrderEntity` does not inherit `BaseAttributeSetsAbstractEntity`). The correct way to extend order fields is via the **checkout form** (`forms.attribute_set_id` of type `forBlocks`, schema describes the fields):

1. Open the checkout form's `attribute_set`, add field `delivery_method` (`type: 'list'`).
2. The order via storefront `POST /content/orders` with the value of this field lands in `orders.form_data.en_US[]` as `{marker: 'delivery_method', type: 'list', value: {...}}`.

`AttributesSetType.forOrders` exists in the enum, but is actually used for **analytics/filtering** in the admin (`selected_attribute_markers`), not for storing values of a specific order.

**"Let's hardcode the array of statuses in project code."** Don't — statuses are created by the admin per storage. One project can have different processes (restaurant, wholesale, retail) with different statuses.

**"Store the current product price in `order_products.price` without a snapshot."** Don't — `order_products.price` is a **snapshot** of the price at order creation time. The current product price lives in `products.attributes_sets[lang].price`. If the product price changes later, that should not bleed into the historical order.
