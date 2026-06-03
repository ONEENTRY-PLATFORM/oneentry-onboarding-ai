<!-- audit: 5/5 (2026-05-22) endpoints[GET /api/content/users/me/cart, PUT /api/content/users/me/cart, POST /api/content/users/me/cart/items, DELETE /api/content/users/me/cart/items/:productId, GET /api/content/users/me/wishlist, PUT /api/content/users/me/wishlist, POST /api/content/users/me/wishlist/items, DELETE /api/content/users/me/wishlist/items/:productId, POST /api/content/user-activity/track, GET /api/content/blocks/:marker/trending, GET /api/content/blocks/:marker/recently-viewed, GET /api/content/blocks/:marker/repeat-purchase, GET /api/content/blocks/:marker/personal-recommendations, GET /api/content/blocks/:marker/cart-complement, GET /api/content/blocks/:marker/cart-similar, GET /api/content/blocks/:marker/wishlist-similar], fields[user_activity_events.event_type (UserActivityEventType: product_view/page_view/category_view/search/product_add_to_cart/product_remove_from_cart/product_add_to_wishlist/product_remove_from_wishlist/product_purchase/product_rating), user_activity_events.user_id, user_activity_events.guest_id (uuid v4 from the X-Guest-Id header), user_activity_events.payload jsonb, cart_items.user_id/product_id/qty/added_at (BIGSERIAL id, UNIQUE(user_id, product_id), FK CASCADE), wishlist_items.user_id/product_id/added_at (BIGSERIAL id, UNIQUE(user_id, product_id), FK CASCADE)], queues[BULL_QUEUES.userActivity='user-activity' with @Processor classes: FlushActivityBufferConsumer (flush-activity-buffer), TrendingConsumer (recompute-trending), CleanupOldActivityConsumer (cleanup-old-activity), RecommendationConsumer (recompute-recommendations), SegmentsRecomputeConsumer (recompute-segments), DormantReactivationConsumer (dormant-reactivation), RefreshPurchaseHistoryConsumer (refresh-user-purchase-history)], ws[no direct channels in the user-activity module], fk[user_activity_events.user_id->users.id (CASCADE), product_id->products.id (CASCADE), page_id->pages.id (CASCADE); cart_items.user_id->users.id (CASCADE), cart_items.product_id->products.id (CASCADE); wishlist_items.user_id->users.id (CASCADE), wishlist_items.product_id->products.id (CASCADE); guest rows in user_activity_events (guest_id IS NOT NULL, user_id IS NULL) are removed only by a cleanup cron] -->

# 18. User activity: cart, wishlist, events

## Purpose

Unlike other OneEntry modules, `user-activity` serves the **client side (storefront)**, not the admin panel. It covers:

- Cart of an authenticated user / guest.
- Wishlist (favorites).
- Recently viewed (view history) — in a Redis ZSet.
- Activity event journal (`product_view`, `search`, `product_purchase`) for analytics and trending.
- Recommendation blocks (trending, recently-viewed, repeat-purchase, personal-recommendations, cart-complement, cart-similar, wishlist-similar) — served by `content-blocks` controller, fed by user-activity consumers.

Scenarios:
1. A guest without login opens a product → `IssueGuestIdInterceptor` issues an `X-Guest-Id` → `UserActivityAutoTrackingInterceptor` records a `product_view` in the Redis buffer.
2. The guest adds the product to the cart → `POST /users/me/cart/items` → Redis key `cart:guest:<uuid>` (TTL 30 days).
3. The guest signs up → the cart migrates from Redis into normalized rows in `cart_items` (one row per `(user_id, product_id)`).
4. The user removes a product from the wishlist → `DELETE /users/me/wishlist/items/:productId` → row deleted from `wishlist_items` and `ProductRemoveFromWishlist` event emitted into the activity buffer.

**IMPORTANT:** this module has **no admin endpoints** in the usual sense (no `admin-*.controller.ts`). The whole API is content (storefront-side), under `UserCommonGuard` which lets both authenticated users and guests through.

> **MIGRATION NOTE (2026-05-22):** the previous design stored cart and wishlist inside `users.system_attributes_sets jsonb` (`{[lang]: {cart, wishlist}}`) plus a dedicated system attribute set with `identifier='user_activity_set'`. That model was removed: migration `1870797500000-create-cart-and-wishlist-items-tables.ts` introduced the normalized `cart_items` / `wishlist_items` tables, and migration `1870797500001-drop-user-activity-system-attribute-set.ts` dropped `users.system_attribute_set_id`, `users.system_attributes_sets`, and the `attributes_sets` row with identifier `user_activity_set`. Cart and wishlist are now **language-agnostic** (no `langCode` anywhere).

## Entities and dependency hierarchy

```
users                            — authenticated profile
  ↑ user_id (FK CASCADE)        — guest = userId NULL, guestId IS NOT NULL
products                         — for product_view / add_to_cart
  ↑ product_id (FK CASCADE)
pages                            — for page_view / category_view
  ↑ page_id (FK CASCADE)

cart_items                       — normalized cart rows (BIGSERIAL, UNIQUE(user_id, product_id))
wishlist_items                   — normalized wishlist rows (BIGSERIAL, UNIQUE(user_id, product_id))
user_activity_events             — event journal (BIGSERIAL, 5 indexes)

Redis cart:guest:<uuid>          — guest cart (TTL 30 days)
Redis wishlist:guest:<uuid>      — guest wishlist (TTL 90 days)
Redis activity:{u:|g:}:{type}    — recently viewed / trending (Sorted Set + List buffer)
Redis activity:buffer            — buffer of events pending DB write (drained by FlushActivityBufferConsumer)
```

| Table / store | Where | Key fields |
|---|---|---|
| `cart_items` | Postgres | `userId`, `productId`, `qty (int, CHECK > 0)`, `addedAt timestamptz`. BIGSERIAL PK. `UNIQUE(user_id, product_id)`. FK CASCADE on `users.id` and `products.id`. No `lang_code`. Index `idx_cart_user(user_id)`. |
| `wishlist_items` | Postgres | `userId`, `productId`, `addedAt timestamptz`. BIGSERIAL PK. `UNIQUE(user_id, product_id)`. FK CASCADE on `users.id` and `products.id`. No `qty`, no `lang_code`. Index `idx_wish_user(user_id)`. |
| `user_activity_events` | Postgres | `userId \| guestId`, `eventType`, `productId \| pageId \| categoryId`, `payload jsonb`, `createdAt`. BIGSERIAL PK, 5 composite indexes on `(*, createdAt)`. |
| `cart:guest:<uuid>` | Redis | TTL 30 days (`GUEST_CART_TTL_DAYS=30`). Stores `CartItem[]` for the guest. Hard limit `CART_MAX_ITEMS=500`. |
| `wishlist:guest:<uuid>` | Redis | TTL 90 days (`GUEST_WISHLIST_TTL_DAYS=90`). Stores `WishlistItem[]` for the guest. Hard limit `WISHLIST_MAX_ITEMS=500`. |
| `activity:{u:<id>|g:<uuid>}:{event_type}` | Redis | Sorted Set + List, for fast "recently viewed" reads. |
| `activity:buffer` | Redis | Buffer of records not yet flushed into `user_activity_events`. Drained by `FlushActivityBufferConsumer` every `USER_ACTIVITY_FLUSH_INTERVAL_MS` (default 30 sec). |

All constants (TTLs, key prefixes, item limits, UUID regex) live in `cms/src/modules/user-activity/types/guest-storage-config.ts`.

## Guest identification: `X-Guest-Id` header (primary)

A guest is identified by the **HTTP `X-Guest-Id` header** (uuid v4). See `cms/src/shared/interceptors/issue-guest-id.interceptor.ts`:

```ts
const GUEST_HEADER = 'x-guest-id';
const GUEST_COOKIE_NAME = 'oe_guest_id';
```

On the first request:
1. If `req.headers['x-guest-id']` contains a valid uuid v4, it is used.
2. Otherwise `userActivityService.issueGuestId()` creates a new one.
3. **The header is added to `req`** (so downstream interceptors can use it), `res.setHeader('X-Guest-Id', guestId)` is set (the client receives it in the response) and **additionally** the cookie `oe_guest_id` is written (`maxAge=90 days`, `sameSite=lax`, `secure=true`).

**Primary identifier — the header.** The cookie is secondary (a convenience for clients that can submit it automatically on the next request).

For authenticated users (when `req.user.id` exists) the interceptor **does nothing** — they don't need a guestId.

## Full jsonb / row examples

### `user_activity_events` (product view by an authenticated user)

```json
{
  "id": "1234567890",
  "userId": 42,
  "guestId": null,
  "eventType": "product_view",
  "productId": 57,
  "pageId": null,
  "categoryId": 12,
  "payload": {
    "source": "card-related-block",
    "blockId": 99,
    "abVariant": "B"
  },
  "createdAt": "2026-05-22T11:24:18.000Z"
}
```

### `user_activity_events` (search by a guest)

```json
{
  "id": "1234567891",
  "userId": null,
  "guestId": "0e6a9c1d-3e7c-4b1a-9f2b-7c3a8d1e0f4a",
  "eventType": "search",
  "productId": null,
  "pageId": null,
  "categoryId": null,
  "payload": {
    "query": "iphone case",
    "lang": "en_US",
    "resultsCount": 17
  },
  "createdAt": "2026-05-22T11:24:33.000Z"
}
```

### `user_activity_events` (purchase)

```json
{
  "id": "1234567892",
  "userId": 42,
  "guestId": null,
  "eventType": "product_purchase",
  "productId": 57,
  "pageId": null,
  "categoryId": 12,
  "payload": {
    "orderId": 4571,
    "qty": 2,
    "price": 1450.00,
    "currency": "USD"
  },
  "createdAt": "2026-05-22T12:01:55.000Z"
}
```

### `cart_items` (authenticated user, normalized rows)

```text
 id          | user_id | product_id | qty | added_at
-------------+---------+------------+-----+--------------------------
 9000000001  |   42    |     57     |  2  | 2026-05-22 11:24:18+00
 9000000002  |   42    |     92     |  1  | 2026-05-22 11:28:01+00
```

One row per `(user_id, product_id)`. No localization. Updates to `qty` are done via `INSERT ... ON CONFLICT (user_id, product_id) DO UPDATE SET qty = EXCLUDED.qty` (see `CartService.addItemForUser`).

### `wishlist_items` (authenticated user)

```text
 id          | user_id | product_id | added_at
-------------+---------+------------+--------------------------
 9000000010  |   42    |     17     | 2026-05-21 19:11:42+00
```

Idempotent inserts via `INSERT ... ON CONFLICT (user_id, product_id) DO NOTHING` (see `WishlistService.addItemForUser`). No `qty`.

### `cart:guest:<uuid>` in Redis

```json
[
  { "productId": 57, "qty": 1, "addedAt": "2026-05-22T11:24:18.000Z" }
]
```

A guest cart has **no localization** and **no DB row**. After signup, `CartService` migrates the Redis array into normalized `cart_items` rows for the new user.

## Content API (NOT admin)

`@Controller('users/me/cart')` and `@Controller('users/me/wishlist')` under `UserCommonGuard`.

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/users/me/cart` | Get the cart of the current user (or guest, by `X-Guest-Id`) |
| `PUT` | `/users/me/cart` | Full replace (empty `items=[]` = clear) |
| `POST` | `/users/me/cart/items` | Add/update an item (`qty` is the absolute value, not an increment) |
| `DELETE` | `/users/me/cart/items/:productId` | Remove an item |
| `GET` | `/users/me/wishlist` | Get the wishlist |
| `PUT` | `/users/me/wishlist` | Replace |
| `POST` | `/users/me/wishlist/items` | Add (idempotent) |
| `DELETE` | `/users/me/wishlist/items/:productId` | Remove |
| `POST` | `/user-activity/track` | Manually track an event (block_impression, A/B variant). 204 No Content. Base views are tracked automatically by `UserActivityAutoTrackingInterceptor`. |

```http
POST /api/content/users/me/cart/items
X-Guest-Id: 0e6a9c1d-3e7c-4b1a-9f2b-7c3a8d1e0f4a

{ "productId": 57, "qty": 2 }
```

Returns a `CartResponseDto` with the cart state after the operation.

**No `langCode` query parameter.** Cart and wishlist are language-agnostic in the current model — a single product is in the cart or it isn't, regardless of which language the storefront is rendered in. (Compare with `localize_infos` which is per-language: those still apply when reading the cart product titles, but the cart membership itself does not depend on locale.)

The `X-Guest-Id` header **is required** for guests (the controller throws `400 BadRequest` if missing) and **is ignored** for authenticated users (if `req.user.id` exists, the cart is taken from `cart_items` by `user_id`; otherwise from Redis by `cart:guest:<X-Guest-Id>`).

**Auto-tracking exclusions:** the cart/wishlist URLs are listed in `CONTENT_TRACK_EXCLUDES` so that `UserActivityAutoTrackingInterceptor` doesn't double-emit events — the only source of cart/wishlist events is `CartWishlistEventEmitterService` via `CartService` / `WishlistService`.

## Recommendation block endpoints

These live in `content-blocks.controller.ts` (the `blocks` module) but are powered by the `user-activity` module's consumers and Redis aggregates. All are open to both users and guests via `UserCommonGuard`. For an unauthenticated guest without enough signal, the endpoints return `200 OK { items: [], total: 0 }` (not `401`) so the storefront can render an empty section gracefully.

| Path | Powered by | What it returns |
|---|---|---|
| `GET /api/content/blocks/:marker/trending` | `TrendingConsumer` (Redis ZSet across recent `product_view` / `product_add_to_cart`) | Most popular products in the last N hours |
| `GET /api/content/blocks/:marker/recently-viewed` | Redis ZSet `activity:{u:<id>|g:<uuid>}:product_view` | The user's / guest's own view history (top 100) |
| `GET /api/content/blocks/:marker/repeat-purchase` | `RefreshPurchaseHistoryConsumer` (purchase frequency per user) | Products the user buys regularly |
| `GET /api/content/blocks/:marker/personal-recommendations` | `RecommendationConsumer` (collaborative filtering + segment hints) | Tailored picks per user |
| `GET /api/content/blocks/:marker/cart-complement` | `RecommendationConsumer` + co-purchase graph | Items frequently bought with what's in the cart |
| `GET /api/content/blocks/:marker/cart-similar` | `RecommendationConsumer` + content similarity on cart items | Similar to items already in the cart |
| `GET /api/content/blocks/:marker/wishlist-similar` | `RecommendationConsumer` + content similarity on wishlist items | Similar to items in the wishlist |

Each endpoint is gated by a content `user_permissions` row. Block-type seeds (`1870797100000-seed-trending-block-type.ts`, `1870797200000-seed-recently-viewed-block-type.ts`, `1870797300000-seed-repeat-purchase-block-type.ts`, `1870797400000-seed-personal-recommendations-block-type.ts`, `1870797500000-seed-cart-complement-block-type.ts`, `1870797600000-seed-cart-similar-block-type.ts`, `1870797700000-seed-wishlist-similar-block-type.ts`) use the `seedBlockType` util, which registers **both** the `general_types` row (enum-driven block type) **and** the matching `user_permissions` row in a single call.

## Behind the scenes

### Bull queue `user-activity` (`BULL_QUEUES.userActivity = 'user-activity'`)

The queue is registered in `content.app.module.ts` via `BullModule.registerQueue({ name: BULL_QUEUES.userActivity })`. **All consumers below are implemented and registered as `@Processor(BULL_QUEUES.userActivity)`** (live in `cms/src/modules/user-activity/consumers/`):

| Consumer class | File | `@Process` name (= `BULL_CONSUMERS.*`) | Schedule / trigger |
|---|---|---|---|
| `FlushActivityBufferConsumer` | `flush-activity-buffer.consumer.ts` | `'flush-activity-buffer'` | Bull repeat-job every `USER_ACTIVITY_FLUSH_INTERVAL_MS` (default 30000ms). Drains `activity:buffer` in batches of `FLUSH_BATCH_SIZE = 1000` via LRANGE + LTRIM, **pre-filters orphan `user_id`** (events where the referenced user is already deleted — would otherwise produce FK 23503 on the whole batch and loop forever on retry), then bulk `INSERT` into `user_activity_events`. On INSERT failure: re-LPUSH in reverse order to restore the original head and let Bull retry. |
| `TrendingConsumer` | `trending.consumer.ts` | `'recompute-trending'` | Recomputes the trending Redis ZSet from recent `product_view` / `product_add_to_cart` events. |
| `CleanupOldActivityConsumer` | `cleanup-old-activity.consumer.ts` | `'cleanup-old-activity'` | Periodically deletes `user_activity_events` rows older than the retention window; removes stale guest rows. |
| `RecommendationConsumer` | `recommendation.consumer.ts` | `'recompute-recommendations'` | Refreshes `user_recommendations` per user (personal-recommendations / cart-complement / cart-similar / wishlist-similar). |
| `SegmentsRecomputeConsumer` | `segments-recompute.consumer.ts` | `'recompute-segments'` | RFM-style segment recompute (`user_segments`). |
| `DormantReactivationConsumer` | `dormant-reactivation.consumer.ts` | `'dormant-reactivation'` | Picks users with no recent activity, schedules a re-engagement event. |
| `RefreshPurchaseHistoryConsumer` | `refresh-purchase-history.consumer.ts` | `'refresh-user-purchase-history'` | Refreshes the per-user purchase-frequency aggregate that powers `/blocks/:marker/repeat-purchase`. |

Every `@Process(...)` name above is exported from `BULL_CONSUMERS` in `cms/src/config/constants.ts:40-70`.

### Services

| Service | What it does |
|---|---|
| `UserActivityService` | `track(eventType, ctx)` method — RPUSHes onto the Redis `activity:buffer` (hot path) + maintains the Redis ZSet `activity:{u:<id>|g:<uuid>}:{type}` for fast recently-viewed reads. Also `isValidUuidV4`, `issueGuestId`. |
| `CartService` | Cart CRUD: for authenticated users uses `cart_items` (read by `userId`; add/update via `INSERT ... ON CONFLICT (user_id, product_id) DO UPDATE`; remove via `DELETE`); for guests — Redis key `cart:guest:<uuid>` with TTL 30 days. Migrates guest cart into `cart_items` rows at signup. |
| `WishlistService` | Same shape, for the wishlist: `wishlist_items` table for users (`INSERT ... ON CONFLICT DO NOTHING` — idempotent add, `addedAt` not bumped on repeat), Redis with TTL 90 days for guests. No `qty`. |
| `GuestCartStorageService` | Low-level work with the Redis key `cart:guest:<uuid>`. `CART_MAX_ITEMS = 500` from `guest-storage-config.ts` (over-limit ⇒ 400 Bad Request). |
| `GuestWishlistStorageService` | Same, but for the wishlist: `WISHLIST_MAX_ITEMS = 500`. |
| `CartWishlistEventEmitterService` | `emitCartDiff(owner, oldItems, newItems)` — diffs the old and new lists, emits `ProductAddToCart` / `ProductRemoveFromCart` via `UserActivityService.track`. Likewise for wishlist. |
| `UserSegmentsService` | Computes RFM segments and persists into `user_segments`. Consumed by recommendations and dormant-reactivation. |
| `RecommendationEngineService` | Hybrid collaborative + content-similarity ranking; writes `user_recommendations`. |
| `NoticePublisherService` | Publishes triggered communications to `notice-service` via RabbitMQ (e.g. cart-abandonment, repeat-purchase reminders). `TriggeredCommunicationLogEntity` records the outcome. |

### Best-effort tracking

`UserActivityService.track()` wraps the entire logic in try/catch with logging — it **never** fails the HTTP response. If Redis is unreachable or the DB complains about FKs later in the flush, the event is dropped (or eventually filtered as orphan) but the user still gets a 200 OK on the main request.

### Auto-tracking interceptor

`UserActivityAutoTrackingInterceptor` is registered globally on the content app and automatically emits `product_view` / `page_view` / `category_view` on GET requests to products/pages. The cart/wishlist URLs are excluded via `CONTENT_TRACK_EXCLUDES` to avoid double emission.

### Recently viewed (Redis ZSet)

For each user/guest a Redis Sorted Set `activity:{u:<id>|g:<uuid>}:product_view` is maintained with `score=createdAt`. After a new view is written → `ZREMRANGEBYRANK 0 -RECENT_HISTORY_LIMIT-1` to keep the top 100 (`RECENT_HISTORY_LIMIT = 100`). Key TTL is 30 days (`RECENTLY_VIEWED_TTL_SECONDS`).

### Lost-update protection for authenticated users

The current design is **lock-free at the table level**: each `(user_id, product_id)` pair is its own row, and concurrent writes to different products do not contend. For the case where two tabs hit the same `(user_id, product_id)` (e.g. one adds, the other removes), the service wraps the operation in a transaction with `pg_advisory_xact_lock(userId)` and uses `INSERT ... ON CONFLICT (user_id, product_id) DO UPDATE`:

```ts
await this.dataSource.transaction(async (manager) => {
  await manager.query('SELECT pg_advisory_xact_lock($1)', [userId]);
  await manager.query(
    `INSERT INTO cart_items (user_id, product_id, qty, added_at)
       VALUES ($1, $2, $3, NOW())
       ON CONFLICT (user_id, product_id)
       DO UPDATE SET qty = EXCLUDED.qty`,
    [userId, productId, qty],
  );
});
```

The advisory lock is per-user and per-transaction, so it serializes concurrent writes from the same user across all rows without blocking anyone else. The `ON CONFLICT` clause makes the upsert atomic at the row level. This replaces the previous "load user row, mutate `users.system_attributes_sets`, save" pattern that needed `SELECT ... FOR UPDATE` on the entire `users` row.

The same shape is used by `WishlistService` with `DO NOTHING` (idempotent add — second add does not move `addedAt`).

`CART_MAX_ITEMS` is enforced **inside** the advisory-locked transaction by counting existing rows for the user and refusing the insert if the limit would be exceeded.

### Journal

**Activity is not journaled.** `user_activity_events` is its own log, separate from `journal_records`. `journal_records` captures admin actions; writing every product view there would be a DDoS.

### Permissions

Endpoints sit under `UserCommonGuard`, without `@GrantByPermission` — it's a user-facing API, not admin. Authorization simply separates "has an account" from "doesn't". Block recommendation endpoints additionally check the seeded content-`user_permissions` rows per marker.

## Demo seeds

Two demo seeds illustrate the model end-to-end and are useful when smoke-testing locally:

- `cms/src/seeds/1880000020000-...` — generates a small synthetic `user_activity_events` history for demo users (views, cart adds, purchases) so trending / recently-viewed / repeat-purchase blocks have content.
- `cms/src/seeds/1880000040000-...` — generates demo `cart_items` and `wishlist_items` rows for the same users to make the cart / wishlist UI non-empty after a fresh DB.

Run them through the usual `npm run typeorm:seed:run` flow.

## Cross-references

- [01-catalog-product.md](./01-catalog-product.md) — `product_view` is written when a product is opened.
- [04-order-flow.md](./04-order-flow.md) — `product_purchase` is written after a successful order. The cart migrates into `orders.form_data` at checkout (cart_items rows are not deleted automatically by checkout — explicit clear).
- [06-event-notification.md](./06-event-notification.md) — `product_add_to_cart` / `product_purchase` events can trigger notifications (via `event_subscription`, see the end of 06).
- [08-users-and-groups.md](./08-users-and-groups.md) — `users` no longer has `system_attributes_sets`; cart/wishlist live in their own tables (this file).
- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — regular `attributes_sets` jsonb mechanism (unrelated to cart/wishlist after the 2026-05-22 refactor).
- `agents_datasets/ClaudeInfos/data-model-core.md` — `UserEntity` now has only `attributesSets` (public profile fields).

## Antipatterns

**Anti-pattern: storing cart/wishlist as jsonb (whether on `users` or in dedicated `carts`/`wishlists` tables).** Don't go back to `users.system_attributes_sets jsonb { [lang]: { cart, wishlist } }`, and don't "compromise" with `carts (user_id, items jsonb)` / `wishlists (user_id, items jsonb)` either — the latter just moves the jsonb one level out without fixing anything. Both shapes have the same problems:

1. **Orphans on delete.** A jsonb column has no FK. When a product is deleted, every cart item referencing it stays as a dangling number inside the jsonb; you have to walk every row to clean up. The normalized `cart_items` / `wishlist_items` tables use FK `ON DELETE CASCADE` — deleted product ⇒ deleted cart rows automatically, by Postgres.
2. **Lost-update window.** The old "load row, mutate jsonb, save" approach needed pessimistic `SELECT ... FOR UPDATE` on the whole owning row; two tabs adding different products both reloaded and rewrote the same jsonb. With row-per-pair plus `ON CONFLICT`, concurrent adds of different products do not contend at all; the same product is serialized by a tiny advisory-lock window.
3. **Per-language duplication.** The old shape stored a cart per `langCode`, which made no sense for the same physical user — and required reconciliation across languages whenever the user changed their interface locale. The new shape is language-agnostic.
4. **Index-friendliness.** A jsonb cart can't be indexed by `productId` cheaply, so "find all users who have product 57 in cart" required a full scan. `cart_items.product_id` is indexable. Stick with the normalized tables that already exist — `cart_items` and `wishlist_items`.

**"Guest carts in Postgres too, to keep things simple."** Don't:

1. There are orders of magnitude more guests than users — the DB drowns in writes.
2. A guest inactive for 30 days is a dead row that has to be cleaned anyway.
3. Redis with TTL makes both problems trivial: hot guests live in memory, inactive ones expire on their own.

**"Every `product_view` goes straight into `user_activity_events` without a buffer."** Acceptable in principle, but scales poorly:

1. A catalog with 10k concurrent visitors → 10k INSERTs per second into `user_activity_events`.
2. The right approach is the Redis `activity:buffer` + `FlushActivityBufferConsumer` batching every 30 seconds (now implemented; see "Behind the scenes" above).

**The right approach:** `cart_items` + `wishlist_items` for authenticated users, Redis for guests, `user_activity_events` for the analytics log — not for the current state of the cart.
