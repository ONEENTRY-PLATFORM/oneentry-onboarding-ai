<!-- audit: 5/5 (2026-05-13) endpoints[POST /events, PUT /events/:id, DELETE /events/:id], fields[events.type, events.actions jsonb {isPush,isWebsocket,isEmail,isWorkflows}, events.whom, events.mailing jsonb, events.discount_event_type, events.product_attribute_set_id], queues[BULL_QUEUES.events + consumers: changeProductAttribute/changeProductStatus/signUp/sendCode/changePassword/changeOrderStatus/submitFormData/mailing/refund/discountStart/discountEnd/bonusAccrual/bonusExpiration], ws[admin-events: 'event' broadcast in exchange-message; inside cms — admin-socket for admins], fk[events.module_id->modules.id, events.user_group_id->user_groups.id] -->

# 06. Event → notification (email / push / WebSocket / workflow)

## Purpose

"When something happens — notify" trigger:
- **Product price changed** → email to subscribers / push to the mobile app.
- **Order moved to status "Ready for pickup"** → SMS + email to the customer.
- **New review on a product** → email to the admin + websocket notification in the admin panel.
- **Customer birthday** → email with a coupon.
- **Discount ending soon** → push "3 days left".
- **Registration / password change / code request** → system email.

OneEntry is structured as three tiers:
1. **CMS** — the `events` table stores the configuration (what triggers, who to send to, what to send).
2. **Bull queue `events`** + `EventsProcessor` — inside cms it processes domain triggers (`change-product-attribute`, `change-order-status`, ...) and for each matching event builds a `NotificationDataType`.
3. **RabbitMQ → `notice-service`** — the built message is published to `RABBITMQ_EXCHANGES.exchangeMessage` (`'exchange-message'`) with routing key `RABBITMQ_ROUTING_KEYS.messageKey` (`'message-key'`). `notice-service` listens to the exchange and delivers: email (`@nestjs-modules/mailer`), push (Firebase Admin / APN), WebSocket.

## Entities and dependency hierarchy

```
modules                      — module dictionary (products, orders, users, forms, discounts)
  ↑ module_id
events                       — event config: trigger + recipients + actions + localization
  ↑ user_group_id
user_groups                  — target recipient group (for WhomType.USER_GROUP)
                             — payment_accounts FK (for PaymentEvent)
event_subscriptions          — subscriptions of specific users/devices to specific events
event_email_settings         — SMTP mailing settings
firebase_credentials         — service account for pushes
```

| Table | Base class | Key fields |
|---|---|---|
| `events` | `BaseAttributeSetsAbstractEntity` | `name`, `type` enum (`attribute`/`status`), `attribute`, `product_status`, `module_id`, `user_group_id`, `whom` enum (`all`/`subs`/`user_group`), `actions` jsonb (`{isPush,isWebsocket,isEmail,isWorkflows}`), `conditions` enum (`CompareCondition`), `extra_condition` jsonb (`{type:'eq|ne|mth|lth', value}`), `mailing` jsonb (`{conditions, period, scheduleAttr, origin, ndays}`), `users` jsonb (`UsersEvent`), `forms` jsonb (`FormsEvent`), `payments` jsonb (`PaymentEvent`), `discount_event_type` enum, `discounts` jsonb (`DiscountEventConfig`), `type_schedule` enum, `localize_infos` (`{title, template, subject, push}`), `product_attribute_set_id`, `form_type` enum, `form_identifier`, `form_email_field_identifier`, `orders_storage`, `order_status` |
| `event_subscriptions` | `BaseEntity` | userId, eventId, fcmToken (for push) |
| `event_email_settings` | `BaseEntity` | smtp config |

## Related `general_types` and `attribute_sets`

- `general_types` is not used directly for `events` (the trigger isn't a "content entity"), but `events` inherits `BaseAttributeSetsAbstractEntity` → it has an `attribute_set` for content fields (e.g., notification banner).
- **Email/push template** is stored in `localize_infos.template` / `localize_infos.push` / `localize_infos.subject` per language. Contains placeholders like `{{product.title}}`, `{{user.email}}` — `EventsProcessor` substitutes them via `valueToPlaceholders` before publishing to RabbitMQ.

## Full jsonb with data

### Event "Product price dropped"

```json
{
  "id": 11,
  "identifier": "price-drop-notification",
  "name": "Product price drop",
  "type": "attribute",
  "attribute": "price",
  "productStatus": null,
  "conditions": "less",
  "extraCondition": null,
  "moduleId": 1,
  "userGroupId": null,
  "productAttributeSetId": 9,
  "whom": "subs",
  "typeSchedule": "every_time",
  "actions": {
    "isPush": true,
    "isWebsocket": false,
    "isEmail": true,
    "isWorkflows": false
  },
  "sentEmailCounter": 142,
  "localizeInfos": {
    "en_US": {
      "title": "Price drop",
      "subject": "{{product.title}} is now cheaper",
      "template": "<p>Hi {{user.firstName}}!</p><p>{{product.title}} is now {{product.price}} USD (was {{product.priceOld}}).</p>",
      "push": "{{product.title}} -{{product.discountPercent}}%"
    }
  },
  "attributeSetId": 51,
  "attributesSets": {
    "en_US": {
      "is_active": true,
      "send_window_start": { "fullDate": "2026-01-01T08:00:00.000Z", "formattedValue": "08:00", "formatString": "HH:mm" },
      "send_window_end":   { "fullDate": "2026-01-01T22:00:00.000Z", "formattedValue": "22:00", "formatString": "HH:mm" }
    }
  }
}
```

### Event "Order assembled" (on order status change)

```json
{
  "id": 12,
  "identifier": "order-ready",
  "name": "Order assembled and ready for pickup",
  "type": "status",
  "ordersStorage": 1,
  "orderStatus": "ready",
  "whom": "all",
  "typeSchedule": "every_time",
  "actions": { "isPush": true, "isWebsocket": false, "isEmail": true, "isWorkflows": false },
  "localizeInfos": {
    "en_US": {
      "title": "Order ready",
      "subject": "Order #{{order.number}} is ready for pickup",
      "template": "<p>{{user.firstName}}, order #{{order.number}} is waiting at {{order.pickupAddress}}.</p>"
    }
  }
}
```

### Event "Discount ending soon"

```json
{
  "id": 13,
  "identifier": "discount-ending-soon",
  "name": "Discount ending soon",
  "discountEventType": "discount_end",
  "discounts": {
    "daysBefore": 3,
    "dailyReminders": true,
    "notificationTime": "2026-06-01T09:00:00.000Z"
  },
  "whom": "subs",
  "actions": { "isPush": true, "isWebsocket": false, "isEmail": true, "isWorkflows": false },
  "localizeInfos": {
    "en_US": {
      "title": "Discount ending soon",
      "subject": "{{discount.daysLeft}} days left for \"{{discount.title}}\"",
      "template": "<p>Hurry! \"{{discount.title}}\" is valid for {{discount.daysLeft}} more days.</p>",
      "push": "{{discount.title}} — {{discount.daysLeft}} days left"
    }
  }
}
```

## Admin API (`@Controller('events')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/events` | `events.create` | Create an event |
| `PUT` | `/events/:id` | `events.update` | Update |
| `DELETE` | `/events/:id` | `events.delete` | Delete |

Plus a separate `SettingsController` for firebase/email (with permissions `events.setupFirebase`, `events.emailSettings`).

```http
POST /events

{
  "identifier": "price-drop-notification",
  "name": "Product price drop",
  "type": "attribute",
  "attribute": "price",
  "conditions": "less",
  "productAttributeSetId": 9,
  "moduleId": 1,
  "whom": "subs",
  "typeSchedule": "every_time",
  "actions": { "isPush": true, "isWebsocket": false, "isEmail": true, "isWorkflows": false },
  "localizeInfos": {
    "en_US": { "title": "Price drop", "subject": "{{product.title}} is now cheaper!", "template": "...", "push": "..." }
  }
}
```

## Behind the scenes

### Bull queue `events`

The queue is `BULL_QUEUES.events = 'events'`. **All** triggers in cms go through this one queue, differing by `job.name`. `EventsProcessor` (`cms/src/modules/events/consumers/events.consumer.ts`) handles:

| `BULL_CONSUMERS.*` | Job name | What triggers it |
|---|---|---|
| `changeProductAttribute` | `'change-product-attribute'` | Product attribute value change (`price`, `in_stock`, etc.) |
| `changeProductStatus` | `'change-product-status'` | Product `status_id` change |
| `signUp` | `'sign-up'` | User registration |
| `sendCode` | `'send-user'` | OTP request / password recovery |
| `changePassword` | `'change-password'` | Password change |
| `changeOrderStatus` | `'change-order-status'` | Order status change |
| `changeUserFormData` | `'change-user-form-data'` | `users.form_data` change |
| `submitFormData` | `'submit-form-data'` | Any form submit — see [03-form-submission.md](./03-form-submission.md) |
| `mailing` | `'mailing'` | Recurring scheduled mailout (`event.mailing.period`) |
| `refund` | `'refund'` | Order refund |
| `discountStart` | `'discount-start'` | Discount started — see [05-discount-promo.md](./05-discount-promo.md) |
| `discountEnd` | `'discount-end'` | Discount ended (+ daily reminders via `discounts.daysBefore`) |
| `bonusAccrual` | `'bonus-accrual'` | Bonus accrual |
| `bonusExpiration` | `'bonus-expiration'` | Bonus expiration |

Inside the consumer:
1. Find all `events` with a matching trigger (`type`, `attribute`, `moduleId`, `productAttributeSetId`, etc.).
2. For each, collect the recipient list by `whom` + `event_subscriptions`.
3. Substitute placeholders into `template` / `subject` / `push` (`valueToPlaceholders` in `admin-events.service.ts:1442`).
4. Publish `MessageDto` to RabbitMQ.

### RabbitMQ

```ts
// admin-events.service.ts:1432-1438
await this.rabbitProducerService.publishMessage(
  RABBITMQ_EXCHANGES.exchangeMessage,  // 'exchange-message'
  RABBITMQ_ROUTING_KEYS.messageKey,    // 'message-key'
  { msg: data },
);
```

- **`exchange-message`** — exchange that `notice-service` subscribes to. cms is the producer.
- **`message-key`** — ordinary transactional messages (email/push to a single user).
- **`notification-key`** — bulk mailings (`RABBITMQ_ROUTING_KEYS.notificationKey`).
- **`websocket`** — separate routing key for realtime messages to the admin frontend via `rabbitmq-admin.consumer.service.ts`.
- **`reload-firebase-admin`** — service: tells `notice-service` that credentials were updated.

`notice-service` is a separate NestJS microservice (see `notice-service/`), it:
- Listens to `exchange-message` via `@golevelup/nestjs-rabbitmq` (`@RabbitSubscribe`).
- On `isEmail=true` sends via the mailer.
- On `isPush=true` goes to Firebase Admin / APN.
- On `isWebsocket=true` sends a socket message via `rabbitmq-admin.consumer.service.ts:92` (`client.emit(payload.id, ...)`).

### WS inside cms

For **admin** notifications (e.g., "new submission came in") there's a second path: `RABBITMQ_ROUTING_KEYS.websocket` → `rabbitmq-admin.consumer.service.ts` → `AdminSocketGateway` → specific admin tab. This is not a user WS, but a service one for the admin UI.

### Journal

`EVENT_CREATED, EVENT_UPDATED, EVENT_DELETED`. **Each sent email/push is NOT journaled** in `journal_entries` (that would be a DDoS on the table) — for mailout audit there's the `events.sent_email_counter` counter.

### Permissions

`events.{get,create,update,delete,setupFirebase,emailSettings}`.

## Links to other files

- [01-catalog-product.md](./01-catalog-product.md) — event `type='attribute'` listens to product attribute changes.
- [03-form-submission.md](./03-form-submission.md) — form submit triggers the `submit-form-data` consumer, which finds related `events` and sends notifications.
- [04-order-flow.md](./04-order-flow.md) — `order_status` change via the `change-order-status` consumer.
- [05-discount-promo.md](./05-discount-promo.md) — `discountStart`/`discountEnd`/`bonusAccrual`/`bonusExpiration` consumers.
- [08-users-and-groups.md](./08-users-and-groups.md) — `events.user_group_id` for targeted mailout to a group.

## Antipattern

**"I'll put the trigger right in `admin-products.controller.ts` — after `PUT /products/:id` I'll send an email to subscribers."** Don't:

1. It blocks the HTTP response (SMTP call is synchronous).
2. It doesn't scale (if there are 100 subscribers and 100 products changed).
3. It isn't journaled and can't be configured by an admin without a release.
4. It doesn't use `notice-service`, which already handles push/email/APN with retry.

Correct way:
1. Create an `event` in the admin via `POST /events` with trigger `type='attribute'`, `attribute='price'`, `conditions='less'`, `productAttributeSetId=9`.
2. On the product side — change the attribute as usual. CMS itself calls `eventsQueue.add('change-product-attribute', {productId, ...})`.
3. `EventsProcessor` finds subscribers, builds the payload, publishes to RabbitMQ.
4. `notice-service` delivers.

Between steps 2 and 4 — the standard OneEntry pipeline, no custom code in the controller.

**"I'll make a separate `email_logs` table."** Don't — for the send counter there's `events.sent_email_counter`. If you need detailed delivery logs — that's the `notice-service`'s responsibility, not cms's.

## User subscription to an event (`event_subscription`)

Sometimes a user wants to receive notifications **about a specific product** — e.g., "tell me when iPhone X is back in stock" or "notify me when the price of this coffee drops below 1000 rubles". This is **`event_subscription`**, a separate entity from `events`.

### Entity

`EventSubscriptionEntity` (`event_subscription` table) — `cms/src/modules/events/entities/event-subscription.entity.ts`:

| Field | Description |
|---|---|
| `id` | PK |
| `user_id` | FK → `users.id` (CASCADE) — who is subscribed |
| `event_id` | FK → `events.id` (CASCADE) — to which event |
| `event_marker` | text marker of the event (for quick lookup without a JOIN) |
| `product_id` | FK → `products.id` (CASCADE) — specific product |
| `locale` | preferred notification language (nullable) |
| `threshold` | threshold value (e.g., price ≤ X) — `float`, nullable |

### Storefront API (NOT admin)

```http
POST /api/content/events/subscribe/marker/:marker
Body: { productId: number, locale?: string, threshold?: number }

DELETE /api/content/events/unsubscribe/marker/:marker
Body: { productId: number }
```

Controller — `cms/src/modules/events/controllers/content-events.controller.ts:121` (`subscribe`), `:163` (`unsubscribe`). Service — `content-events.service.ts`.

### How it's used in `EventsProcessor`

When the event fires (`change-product-attribute`, `change-product-status`, ...) the consumer finds recipients considering:
- `event.whom === 'subs'` (subscribers only).
- `event_subscription.product_id === productId` (only those subscribed to this product).
- `event_subscription.threshold` (if set) — comparison with the current attribute value.

So `event_subscription` is a **recipient filter** when `whom='subs'`, not a separate delivery mechanism. The notification itself goes through the same pipeline: `events` Bull queue → RabbitMQ → `notice-service`.

### Example jsonb row

```json
{
  "id": 412,
  "userId": 42,
  "eventId": 11,
  "eventMarker": "price-drop-notification",
  "locale": "en_US",
  "threshold": 1000.00
}
```

User 42 subscribes to the "price drop" event (id=11) for a specific product (`product_id` via `JoinColumn`), wants `en_US`, and it fires only when the price drops below 1000.

### Antipattern

**"I'll create a separate `product_subscribers (user_id, product_id, threshold)` table."** Don't — it's **`event_subscription`** with a `productId` link. One generic mechanism: the user subscribes to an event linked to a product. If tomorrow we add "price-drop subscription by category" — it'll be `event_subscription` with `category_id` (once the field is added), not a new table.
