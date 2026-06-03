# Patterns: Bull queues and WebSocket channels

In `cms/` background jobs run through Bull (Redis-based), inter-service messaging is RabbitMQ, real-time with the frontend goes through socket.io (Nest WebSockets gateways), and y-websocket handles CRDT.

---

## 1. Bull queues — full list

Registered in `cms/src/config/constants.ts:23-40` via `BULL_QUEUES`. Queue names (enum values):

| Key in `BULL_QUEUES` | Queue name | Consumer (class) | Consumer file | Purpose |
|---|---|---|---|---|
| `events` | `events` | `EventsProcessor` | `modules/events/consumers/events.consumer.ts` | Sending push/email/WS/workflows notifications |
| `indexData` | `index-data` | `IndexDataConsumer` | `modules/index-attributes-sets/consumers/index-data.consumer.ts` | Indexing attribute values for search |
| `findProductRelations` | `relations-products` | `RelationsProductsConsumer` | `modules/products/consumers/relations-products.consumer.ts` | Finding related products |
| `findBlockProductRelations` | `block-products` | `BlockProductsConsumer` | `modules/products/consumers/block-products.consumer.ts` | Finding products for a block |
| `productStatuses` | `product-statuses` | `ProductStatusesConsumer` | `modules/products/consumers/product-statuses.consumer.ts` | Setting the default product status |
| `files` | `files` | `FilesConsumer` | `modules/file-upload/consumers/files.consumer.ts` | Deleting / copying files in S3/Minio |
| `preview` | `preview` | `PreviewConsumer` | `modules/file-upload/consumers/preview.consumer.ts` | Generating previews of uploaded files |
| `system` | `system` | `SystemConsumer` | `shared/consumers/system.consumer.ts` | System jobs for the admin API |
| `systemDev` | `system-dev` | `DeveloperSystemConsumer` | `shared/consumers/developer-system.consumer.ts` | System jobs for the developer API |
| `systemContent` | `system-content` | `ContentSystemConsumer` | `shared/consumers/content-system.consumer.ts` | System jobs for the content API (sync swagger files) |
| `workflows` | `workflows` | `EventsNode` | `modules/events/nodes/events.node.ts` | Workflows engine node |
| `productElastic` | `product-elastic` | `ProductElasticConsumer` | `modules/products/consumers/product-elastic.consumer.ts` | Building / updating the Elasticsearch product index |
| `userActivity` | `user-activity` | `FlushActivityBufferConsumer`, `TrendingConsumer`, `CleanupOldActivityConsumer`, `RecommendationConsumer`, `SegmentsRecomputeConsumer`, `DormantReactivationConsumer`, `RefreshPurchaseHistoryConsumer` | `modules/user-activity/consumers/*.consumer.ts` | Activity buffer flush, trending / recommendations / segments recompute, cleanup |
| `contentApiErrors` | `content-api-errors` | `ContentApiErrorConsumer` | `modules/journal/consumers/content-api-error.consumer.ts` | Persists 4xx/5xx errors of the public Content API into `content_api_errors` (async, fire-and-forget from the global `ContentApiErrorLoggerFilter` exception filter). Backpressure: drops new jobs once `getWaitingCount() > 1000`. |

An additional `attributes-sets` queue is registered directly in `cms/src/modules/attributes-sets/attributes-sets.module.ts:26` (not via the `BULL_QUEUES` constant — this is the exception):

| Queue name | Consumer | File | Purpose |
|---|---|---|---|
| `attributes-sets` | `AttributesSetsConsumer` | `modules/attributes-sets/consumers/attributes-sets.consumer.ts` | Updating attribute set schemas and copying values across languages |

---

## 2. `@Process(...)` methods in consumers

The exact job names for `queue.add('<name>', payload)`. List from `grep -rn "@Process(" cms/src`:

### `attributes-sets`
- `@Process('update-changing')` — updates the attribute set on every consumer table (see [`data-model-core.md §3`](./data-model-core.md#3-dynamic-consumer-table-whitelist-via-information_schema)).
- `@Process('copy-values')` — copies attribute values from `sourceLang` to `targetLangs`.

### `events`
Names come from the `BULL_CONSUMERS` enum (`cms/src/config/constants.ts:39`):
- `@Process(BULL_CONSUMERS.changeProductAttribute)` (`'change-product-attribute'`)
- `@Process(BULL_CONSUMERS.changeProductStatus)` (`'change-product-status'`)
- `@Process(BULL_CONSUMERS.signUp)` (`'sign-up'`)
- `@Process(BULL_CONSUMERS.sendCode)` (`'send-user'` — sic, in the code sendCode → 'send-user')
- `@Process(BULL_CONSUMERS.changePassword)` (`'change-password'`)
- `@Process(BULL_CONSUMERS.changeOrderStatus)` (`'change-order-status'`)
- `@Process(BULL_CONSUMERS.changeUserFormData)` (`'change-user-form-data'`)
- `@Process(BULL_CONSUMERS.submitFormData)` (`'submit-form-data'`)
- `@Process(BULL_CONSUMERS.mailing)` (`'mailing'`)
- `@Process(BULL_CONSUMERS.refund)` (`'refund'`)
- `@Process(BULL_CONSUMERS.discountStart)` (`'discount-start'`)
- `@Process(BULL_CONSUMERS.discountEnd)` (`'discount-end'`)
- `@Process(BULL_CONSUMERS.bonusAccrual)` (`'bonus-accrual'`)
- `@Process(BULL_CONSUMERS.bonusExpiration)` (`'bonus-expiration'`)

### `workflows`
- `@Process(BULL_CONSUMERS.workflows)` (`'workflows'`) — `EventsNode`.

### `files`
- `@Process('delete')`
- `@Process('copy')`

### `preview`
- Three `@Process({ ... })` entries with complex config (see `preview.consumer.ts:56`, `:73`, `:144`).

### `index-data`
- `@Process('index')` — indexing of a single attribute set / products / pages.
- `@Process('index-all')` — re-indexing everything.

### `block-products`
- `@Process('find')`
- `@Process('findAll')`

### `product-elastic`
- `@Process('build-product-index')`
- `@Process('update-product-index')`

### `product-statuses`
- `@Process('set-default-status')`

### `relations-products`
- `@Process('find')`

### `system-content`
- `@Process('sync-swagger-files')`

### `system-dev`
- `@Process('upload-user-module')`

### `system`
- `@Process('clean-users')`
- `@Process('delete-certs')`
- `@Process('calculate-ratings')`
- `@Process('sync-storage')`

### `content-api-errors`
- `@Processor(BULL_QUEUES.contentApiErrors)` on `ContentApiErrorConsumer`.
- `@Process(CONTENT_API_ERROR_JOB_NAME)` (`'log-error'`, defined in `modules/journal/types/content-api-error-job.type.ts`) — single handler that creates the `content_api_errors` row.
- `@OnQueueFailed({ name: CONTENT_API_ERROR_JOB_NAME })` — logs the failure but never throws (jobs that fail with the entity-write step go to `removeOnFail: 50`).

### `user-activity`
All consumers live in `cms/src/modules/user-activity/consumers/` and are decorated `@Processor(BULL_QUEUES.userActivity)`. Job names come from `BULL_CONSUMERS` (`cms/src/config/constants.ts:40-70`):
- `@Process(BULL_CONSUMERS.flushActivityBuffer)` (`'flush-activity-buffer'`) — `FlushActivityBufferConsumer`. Bull repeat-job (`USER_ACTIVITY_FLUSH_INTERVAL_MS`, default 30000ms). Drains the `activity:buffer` Redis list in batches of 1000 via LRANGE + LTRIM, **pre-filters orphan `user_id`** (rows referencing a deleted user — would otherwise produce FK 23503 on the whole batch), then bulk INSERTs into `user_activity_events`.
- `@Process(BULL_CONSUMERS.recomputeTrending)` (`'recompute-trending'`) — `TrendingConsumer`.
- `@Process(BULL_CONSUMERS.cleanupOldActivity)` (`'cleanup-old-activity'`) — `CleanupOldActivityConsumer`.
- `@Process(BULL_CONSUMERS.recomputeRecommendations)` (`'recompute-recommendations'`) — `RecommendationConsumer`.
- `@Process(BULL_CONSUMERS.recomputeSegments)` (`'recompute-segments'`) — `SegmentsRecomputeConsumer`.
- `@Process(BULL_CONSUMERS.dormantReactivation)` (`'dormant-reactivation'`) — `DormantReactivationConsumer`.
- `@Process(BULL_CONSUMERS.refreshUserPurchaseHistory)` (`'refresh-user-purchase-history'`) — `RefreshPurchaseHistoryConsumer`.

---

## 3. Auto-emitting WS notifications from Bull hooks

Most consumers in the admin/developer API wire `socketService.sendSocketNotification(...)` into the Bull hooks:

```ts
@OnQueueActive()
public onActive(job: Job) {
  this.socketService.sendSocketNotification(
    { jobId: job.id, aId: job.data?.aId },
    'start',
    'attributesSetsChanging',     // ← WS channel
  );
}

@OnQueueCompleted()
public onFinish(job: Job) {
  this.socketService.sendSocketNotification(
    { jobId: job.id, aId: job.data?.aId },
    'finish',
    'attributesSetsChanging',
  );
}

@OnQueueFailed()
@OnQueueError()
public onError(job: Job) {
  this.socketService.sendSocketNotification(
    job.failedReason,
    'error',
    'attributesSetsChanging',
  );
}
```

This means: **new `@Process(...)` handlers on the consumer automatically inherit WS notification emission** — all that's needed is that the payload contain `aId` (or whichever field) and that the hooks are wired.

The default channel for `sendSocketNotification` is `'indexProducts'` (see `developer-socket.gateway.ts:67`). For any other channel — pass it explicitly.

---

## 4. WebSocket gateways

All Socket.IO servers live inside `cms/src/modules/socket/`. The internal CRDT server is separate.

### 4.1. `DeveloperSocketGateway`

File: `cms/src/modules/socket/developer-socket.gateway.ts`.

- Runs on the same ports as the developer API.
- Authentication: JWT via `auth.token` from the socket handshake (`handleConnection`), secret `JWT_SECRET`.
- Method **`sendSocketNotification(payload, action, channel = 'indexProducts')`** (`:64`) — emits `server.emit(channel, { payload, action })`. This is the main entry point for every Bull consumer.
- Method **`sendMessage(payload, entity, action)`** (`:39`) — emits on the `msgToClient` channel + publishes to Redis pub/sub if this is the developer instance.
- The `msgToClient` channel — a generic notification with `{ entity, action }`.

**`@SubscribeMessage` channels (what the gateway listens to):**
- `'indexProducts'` (`@deprecated`) — start product indexing.
- `'indexPages'` (`@deprecated`) — start page indexing.
- `'indexProductsStop'` (`@deprecated`).
- `'indexDataStop'` — stop indexing.
- `'relationsProducts'` — start the related-products search.
- `'checkIndexProducts'` — query how many indexing jobs are active.
- `'changePosition'` — broadcast a position change to other clients.
- `'import'` — broadcast that the import has started.
- `'attributeChangingValue'` — broadcast that an attribute value is being edited (used as an **advisory user blocker**: the frontend catches it and locks the field for other admins; see [`patterns-journal-blockers-versioning.md`](./patterns-journal-blockers-versioning.md)).
- `'ping'` — measure latency.

### 4.2. `AdminSocketGateway`

File: `cms/src/modules/socket/admin-socket.gateway.ts`. Extends `DeveloperSocketGateway`.

- Adds a hook on `SharedRedisService.setMessageHandler` — listens to messages from a Redis channel written by the developer gateway. Upon receiving `{ channel, payload }` it does `server.emit(channel, payload)`. So the admin and developer APIs synchronize through Redis pub/sub.
- Everything else is inherited.

### 4.3. `ContentSocketGateway`

File: `cms/src/modules/socket/content-socket.gateway.ts`.

- Path: `/api/content/ws`.
- Authentication: via `UsersAuthProviderEntity` (pulling `tokenSecretKey` from `config`) + checking `UserSessionEntity` by `userId + accessToken + deviceFingerprint`.
- Guests (`X-Guest-Id`) — kept in a separate map.
- Does not provide `@SubscribeMessage` methods in the visible code (the gateway is open for connection but message handling is not implemented in the file itself).

### 4.4. `SyncSocketGateway` (CRDT)

File: `cms/src/modules/socket/sync-socket.gateway.ts`.

- A dedicated WebSocket server on port `WS_SYNC_SERVER_PORT` (default `3007`).
- Implemented via `y-websocket/bin/utils.setupWSConnection` and `ws` (not socket.io).
- Used only for products and pages (see the root `CLAUDE.md` on CRDT) — the frontend connects via `WebsocketProvider`.
- This means: `products` and `pages` do not have a full-fledged `PUT /:id` for replacing the whole object — changes go to YJS docs, and parallel writes to the DB happen on the CMS side.

### 4.5. `WorkflowsGateway`

File: `cms/src/modules/workflows/workflows.gateway.ts`.

- `@SubscribeMessage('subscribe')` / `@SubscribeMessage('unsubscribe')` — managing subscriptions to workflow events.

---

## 5. All WS channels (emit side) that the frontend sees

The list is based on grepping `socketService.sendSocketNotification(...)` and `server.emit(...)`:

| Channel | Where it is emitted | Meaning |
|---|---|---|
| `attributesSetsChanging` | `attributes-sets.consumer.ts:28/37/47/211/268` | Hooks for `update-changing` / `copy-values`. On the frontend → system blocker for the set. |
| `indexProducts` | `developer-socket.gateway.ts:67/120` | Default channel for `sendSocketNotification`. Product indexing progress. |
| `indexData` | `index-data.consumer.ts:37` | Indexing progress (overall). |
| `indexHealth` | `index-data.consumer.ts:176` | Index health (health metrics). |
| `blockProducts` | `block-products.consumer.ts:31/36/46` | Progress of the block-products search. |
| `msgToClient` | `developer-socket.gateway.ts:40/76` | Generic message to the frontend with `{ entity, action }`. |
| `changePosition` | `developer-socket.gateway.ts:129` | Broadcast about position change (between admins). |
| `import` | `developer-socket.gateway.ts:137` | Broadcast about the start of a catalog import. |
| `attributeChangingValue` | `developer-socket.gateway.ts:148` | Advisory blocker for an attribute field between admins. |
| `ping` | `developer-socket.gateway.ts:154` | Ping response. |
| `system` | `auth.controller.ts:160` (via `sendSocketNotification({}, 'logout', 'system')`) | A "log out" command (e.g. on forced admin logout). |

The full list of emits can be obtained with: `grep -rn "sendSocketNotification\|server\.emit" cms/src --include="*.ts"`.

---

## 6. RabbitMQ — brief

Constants in `cms/src/config/constants.ts:5-21`:

```ts
RABBITMQ_QUEUES = {
  queueSubscribe: 'queue-subscribe',
  exchange: 'queue-exchange',
  queueImport: 'queue-import',
}

RABBITMQ_EXCHANGES = {
  exchangeMessage: 'exchange-message',
  exchangeImport: 'exchange-import',
}

RABBITMQ_ROUTING_KEYS = {
  messageKey: 'message-key',
  notificationKey: 'notification-key',
  websocket: 'websocket',
  reloadFirebaseAdmin: 'reload-firebase-admin',
}
```

- **`exchange-message`** + key `notification-key` — sending push/email to `notice-service`.
- **`exchange-message`** + key `websocket` — sending a WS notification through notice-service (?) — verify in `notice-service` if needed.
- **`exchange-message`** + key `reload-firebase-admin` — reload Firebase credentials.
- **`exchange-import`** + queue `queue-import` — catalog import → `import-backend`.

RabbitMQ modules: `rabbitmq-publisher.module.ts`, `rabbitmq-consumer.module.ts`, `rabbitmq-content.consumer.module.ts` (`cms/src/modules/rabbitmq/`).

---

## 7. What this means for AI

- **A new background task** → pick an existing queue that fits (`events`, `system`, `index-data`) and add `@Process('your-name')` to the consumer. If the payload contains `aId` — auto-emission of `attributesSetsChanging` already works.
- **Notifying the frontend** → inject `AdminSocketGateway` (admin) or `DeveloperSocketGateway` (developer) → `sendSocketNotification(payload, action, channel)`. If the channel is well-known (see the table above), the frontend already listens. If it's a new channel — discuss with the UI side and add a handler in `AppInformer.js` (frontend).
- **Don't create a new queue** for a single task. If the task doesn't fit any existing one — discuss with the user.
- **The CRDT queue** (`y-websocket`) — never confuse it with the regular `WebSocketGateway`.
- **RabbitMQ is for inter-service communication.** Bull is for the CMS's internal background work.

---

## Related documents

- [`patterns-journal-blockers-versioning.md`](./patterns-journal-blockers-versioning.md) — how WS channels are used as "system blockers".
- [`data-model-core.md`](./data-model-core.md) — why `update-changing` walks `information_schema`.
- [`modules-catalog.md`](./modules-catalog.md) — which module registers which queue.
