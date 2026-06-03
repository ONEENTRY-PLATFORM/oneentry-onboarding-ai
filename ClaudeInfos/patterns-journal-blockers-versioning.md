# Patterns: Journal, blockers, versioning

Three closely related mechanisms that sit on top of ordinary CRUD operations. All three are universal: they work for any entity without any special code in its service.

---

## 1. Journal (admin action audit)

### 1.1. Concept

An admin's action on an entity → an automatic row in `journal_records`:
- who (`admin`),
- when (`created_at`),
- what (`action: CREATE/UPDATE/DELETE`, `delta jsonb`),
- which module (`module_name`),
- which ID (`entity_id`),
- the result (`result: SUCCESS/FAILURE`, `error`),
- the business event (`journaling_event`).

### 1.2. Where it is defined

| Part | File |
|---|---|
| Decorator | `cms/src/modules/journal/decorators/journalable.decorator.ts` |
| Interceptor (admin) | `cms/src/modules/journal/journal.interceptor.ts` |
| Interceptor (developer base) | `cms/src/modules/journal/developer-journal.interceptor.ts` |
| Service | `cms/src/modules/journal/jounal.service.ts` (sic — the filename is misspelled and kept as-is) |
| Entity | `cms/src/modules/journal/entities/journal-record.entity.ts` |
| Event enum | `cms/src/modules/journal/types/journaling-events.ts` (131 values as of 2026-05-29, including the 11 new `MENU_CUSTOM_ITEM_*` and `FILTER_*` events added in the 2026-05 wave) |
| Module enum | `cms/src/modules/journal/types/module-name-enum.ts` |
| Controller | `cms/src/modules/journal/journal.controller.ts` |

### 1.3. How to use it

```ts
@Post()
@GrantByPermission(AdminPermissionsEnum['blocks.create'])
@Journalable(JournalingEvents.BLOCK_CREATED)
async createBlock(@Body() dto: CreateBlockDto) {
  return this.adminBlocksService.create(dto);
}
```

The `@Journalable(...)` decorator attaches a `'journaling-event'` metadata key to the method. The interceptor (`DeveloperJournalInterceptor` / `JournalInterceptor`) is applied globally in the corresponding app module and works like this:

1. **On every request** it increments the `api-counter-key` counter in Redis (`API_COUNTER_KEY` from `cms/src/config/constants.ts:134`, with a 2-day window).
2. **GET requests** → `next.handle()`, not journaled (`developer-journal.interceptor.ts:75-77`).
3. It reads the `'journaling-event'` metadata. If it is absent → `next.handle()`.
4. From the controller class name (`AdminBlocksController` → `'ADMINBLOCKS'`) plus `ModuleNameEnum['ADMINBLOCKS'] = 'BLOCK'` it derives `moduleName`.
5. After the method runs, it writes a row via `journalService` with `delta` (request body), `action` (`POST=CREATE`, `PUT/PATCH=UPDATE`, `DELETE=DELETE`), `result` (`SUCCESS`/`FAILURE`), `error`.

### 1.4. Adding a new event

1. Open `cms/src/modules/journal/types/journaling-events.ts`.
2. Add a value to the enum (e.g. `EVENT_X_CREATED = 'eventXCreated'`).
3. If `ModuleNameEnum` doesn't yet know about your controller — add an entry to `module-name-enum.ts`:
   ```ts
   ADMINEVENTX = 'EVENT_X',  // ← key = controller name without 'Controller', uppercase
   ```
4. Use `@Journalable(JournalingEvents.EVENT_X_CREATED)` on the method.

### 1.5. What this means for AI

- **Do not write your own audit table.** The journal already exists.
- Put `@Journalable` on every mutating method in an admin controller. If no event fits — add one to the enum; don't skip.
- GET methods are intentionally not journaled.
- Requests coming from other microservices (`x-internal-request: true`) bypass the guard, but **are still** journaled (the interceptor sits above the guard).

---

## 2. Blockers

There is **no real mutex-based locking** in `cms/`. Everything called a "blocker" is an advisory signal over WebSocket. That means: the code relies on clients cooperating (the frontend respects the signal and locks the UI), not on a hard guarantee.

### 2.1. System blocker (advisory via Bull hooks → WS)

**What it is:** while a heavy background task (e.g. `attributes-sets:update-changing`) is running on the server, every admin session receives a WS signal and locks the corresponding UI controls.

**How it is implemented:**

1. A Bull consumer (e.g. `AttributesSetsConsumer`) has the `@OnQueueActive` / `@OnQueueCompleted` / `@OnQueueFailed` / `@OnQueueError` hooks (`cms/src/modules/attributes-sets/consumers/attributes-sets.consumer.ts:26-52`).
2. Inside the hook: `socketService.sendSocketNotification({ jobId, aId }, action, 'attributesSetsChanging')`.
3. The frontend (in `cms_frontend/`, outside the scope of this document) listens to the `attributesSetsChanging` channel and pushes `aId` into its redux blockers store. Then the UI buttons / inputs for this attribute set are disabled for every admin. The server is unaware of UI locking — it only emits signals.

**Which queues support this:**
- `attributes-sets` (channel `attributesSetsChanging`)
- `index-data` (channels `indexData`, `indexHealth`)
- `relations-products` (channel `indexProducts` — the default for `sendSocketNotification`)
- `block-products` (channel `blockProducts`)
- and others — wherever hooks call `sendSocketNotification`.

**A Bull job inherits this behavior for free:** if you put `aId` (or an equivalent) into `job.data`, the hooks auto-emit the signal. See [`patterns-queues-and-ws.md §3`](./patterns-queues-and-ws.md#3-auto-emitting-ws-notifications-from-bull-hooks).

### 2.2. User blocker (advisory: "X is editing field Y right now")

**What it is:** when an admin starts typing into an attribute field, other admins see that the field is busy and cannot edit it at the same time. TTL ~5 seconds (on the frontend).

**How it is implemented:**

- Frontend (in `cms_frontend/`, outside the scope of this document): a HOC wrapping attribute fields catches `keyUp` and emits a message on the `attributeChangingValue` WS channel. TBD: the exact HOC name — verify in the frontend repo if needed.
- Server: `DeveloperSocketGateway.attributeChangingValue` (`developer-socket.gateway.ts:143-149`) receives it and calls `this.server.except(client.id).emit('attributeChangingValue', payload)` — i.e. it broadcasts to everyone EXCEPT the sender.
- Other frontends receive the channel, show "X is editing", and lock the field for 5 seconds.

**This is NOT a mutex.** If the frontend crashes between keyUps — the block expires by TTL and the field becomes available. If two admins hit "Save" at the same time — both saves happen, the DB resolves the conflict (last-write-wins).

### 2.3. What is NOT a blocker (commonly confused)

`products` has the columns `isPositionLocked`, the methods `manageSortLocking`, `removeWithLocked`. **This is pinning a product's position in sort order**, not edit blocking:

- `PositionEntity.isLocked` (`cms/src/modules/position/entities/position.entity.ts:65`) + `lockedPosition` (the numeric pinned position).
- `AdminProductsController` (`cms/src/modules/products/controllers/admin-products.controller.ts:526`) — the `manageSortLocking(positionId, index)` method pins a product at a position while others are reordered.
- `removeWithLocked(...)` — deletes a product while shifting the pinning of its neighbors.

If you receive a task "block this product from being edited" — that is a **different** mechanism, and it is NOT in the code. Clarify with the user.

### 2.4. What this means for AI

- **Don't try to introduce a distributed mutex.** The CMS doesn't have one, and there's no code for it. If the task requires a guaranteed mutex — discuss it separately with the user.
- **WebSocket signals are advisory.** They give UX, not consistency. Final correctness is enforced at the DB level (constraints, transactions, optimistic version in `BaseAbstractEntity.version`).
- **`isPositionLocked` is NOT an edit lock.** It is about sort order.

---

## 3. Versioning (entity_versions)

### 3.1. Concept

Any change to an entity (insert/update/delete) → a snapshot in `entity_versions`. Universal mechanism — works for every table that has an `attributes_sets` column (or is explicitly hooked via a trigger).

### 3.2. Where it is defined

| Part | File |
|---|---|
| Entity | `cms/src/modules/entity-versions/entities/entity-version.entity.ts` |
| Service | `cms/src/modules/entity-versions/entity-version.service.ts` |
| Controller | `cms/src/modules/entity-versions/controllers/admin-entity-versions.controller.ts` |
| Migrations (creating triggers and cleanup) | `cms/src/migrations/1870796200002-create-entity-versioning.ts`, `1870796200003-create-entity-versioning.ts`, `1870796400000-entity-versions-cleanup-on-delete.ts` |

### 3.3. How it works

**`EntityVersionEntity`** (the `entity_versions` table):
- `entity_name` (varchar, indexed) — the SQL table name.
- `entity_id` (int) — the object ID.
- `version` (int) — version number (also present in `BaseAbstractEntity.version`).
- `action` (varchar(10)) — `'INSERT' / 'UPDATE' / 'DELETE'`.
- `data` (jsonb) — row snapshot.
- `admin_id` (int, nullable) — who did it.
- `created_date` (timestamptz).
- Unique composite index `(entity_name, entity_id, version)`.

**Triggers on consumer tables:** the migration `1870796200002-create-entity-versioning.ts:96` walks through `information_schema` and attaches a trigger to every table that has an `attributes_sets` column. On INSERT/UPDATE/DELETE the trigger writes a row into `entity_versions` with a JSON snapshot of `OLD` or `NEW`.

In other words, **versioning hooks itself into all consumer tables automatically** — mirroring the dynamic-whitelist pattern from [`data-model-core.md §3`](./data-model-core.md#3-dynamic-consumer-table-whitelist-via-information_schema).

### 3.4. Restoring a version

`EntityVersionService.restoreVersion(entityName, entityId, version)` (`entity-version.service.ts:51`):

1. Finds the row in `entity_versions`.
2. Pulls the column types for the table from `information_schema.columns`.
3. Builds `UPDATE <table> SET <col>=$<n> ... WHERE id=$1` with explicit typing for ARRAY columns (PostgreSQL).
4. Applies it.

So restoration **also** works universally — no hardcoded field list.

### 3.5. Versioning limits

`ImmutableSettingsEntity.maxEntityVersion` (`cms/src/modules/immutable-settings/entities/immutable-settings.entity.ts:18`) sets the per-entity version limit. Older versions must be pruned (triggers / cron — see the relevant migrations).

### 3.6. What this means for AI

- **Don't write your own `<entity>_history` table.** `entity_versions` already covers it.
- A new entity with `attributes_sets` is automatically versioned. If the entity has NO `attributes_sets` — there is no versioning (no trigger is installed).
- If you need rollback for a complex structure with many-to-many relations — `entity_versions` only snapshots the row itself. Relations (M2M tables) are a separate story.

---

## 4. How Journal / Blockers / Versions relate

These three mechanisms run in parallel and do not conflict:

| What | Where it lives | When it fires |
|---|---|---|
| Journal | `journal_records` | On every mutating HTTP request decorated with `@Journalable` |
| Versions | `entity_versions` | On every SQL INSERT/UPDATE/DELETE on a consumer table (trigger) |
| Blockers | WS channels (no persistence) | While a Bull job is running, or while a user-blocker TTL is active |

To put it differently:
- **Journal** = "what the admin tried to do through the API".
- **Versions** = "what actually happened in the DB".
- **Blockers** = "UI flags for other sessions to keep them out".

These three sources may diverge (for example, a direct UPDATE from a migration leaves no row in journal but creates a version). When investigating incidents, take both into account.

---

## Related documents

- [`patterns-controllers.md`](./patterns-controllers.md) — how `@Journalable` combines with `@GrantByPermission`.
- [`patterns-queues-and-ws.md`](./patterns-queues-and-ws.md) — WS channels for blockers.
- [`data-model-core.md`](./data-model-core.md) — `information_schema` (the shared mechanism behind versioning).
