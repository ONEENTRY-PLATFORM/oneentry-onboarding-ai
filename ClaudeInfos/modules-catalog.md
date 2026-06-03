# `cms/` module catalog

Module reference by domain. Each module may have multiple variants for different audiences: `admin-`, `developer-`, `content-`, `base-`. The app routes in `cms/` are assembled from 4 root modules:

| Root | File | What it serves |
|---|---|---|
| `BaseAppModule` | `cms/src/base.app.module.ts` | Shared layer, used as a parent |
| `AdminAppModule` | `cms/src/admin.app.module.ts` | Admin panel API `/api/admin/*` |
| `DeveloperAppModule` | `cms/src/developer.app.module.ts` | Developer API `/api/developer/*` |
| `ContentAppModule` | `cms/src/content.app.module.ts` | Public/content API `/api/content/*` |

For more on audiences see [`patterns-controllers.md`](./patterns-controllers.md).

In the "Controllers" column the abbreviations are: `A` = admin, `D` = developer, `C` = content, `B` = base (common), `_` = module-only (no audience prefix).

In the "Queues" column — the Bull queue name into which the module publishes or from which it consumes.

---

## Content

### `pages`

- **Files:** `cms/src/modules/pages/`
- **Entities:** `PageEntity`
- **Controllers:** `admin-pages.controller.ts` (A), `developer-pages.controller.ts` (D), `content-pages.controller.ts` (C), `base-pages.controller.ts` (B)
- **Services:** `AdminPagesService`, `DeveloperPagesService`, etc. (see `services/`)
- **Modules:** `pages.module.ts`, `developer.pages.module.ts`, `content.pages.module.ts`
- **CRDT:** page editing goes through `SyncSocketGateway` (port `WS_SYNC_SERVER_PORT`, default 3007).

### `blocks`

- **Entities:** `BlockEntity`, `BlockPageEntity`, `BlockProductsEntity`, `ProductBlocksEntity`
- **Controllers:** A/D/C/B. The content controller (`content-blocks.controller.ts`) hosts the recommendation block endpoints (each gated by a seeded `user_permissions` row, see seeds `1870797100000`..`1870797700000`):
  - `GET /:marker/trending`
  - `GET /:marker/recently-viewed`
  - `GET /:marker/repeat-purchase`
  - `GET /:marker/personal-recommendations`
  - `GET /:marker/cart-complement`
  - `GET /:marker/cart-similar`
  - `GET /:marker/wishlist-similar`

  Data is fed by `user-activity` consumers; for an unauthenticated guest without enough signal the endpoints return `200 OK { items: [], total: 0 }`.
- **Modules:** `blocks.module.ts`, `content.blocks.module.ts`, `developer.blocks.module.ts`
- **Queues:** `BULL_QUEUES.indexData`, `BULL_QUEUES.findBlockProductRelations`

### `templates`

- **Entities:** `TemplateEntity`
- **Controllers:** A/C/B
- **Modules:** `templates.module.ts`, `content.templates.module.ts`

### `template-previews`

- **Entities:** `TemplatePreviewsEntity`
- **Controllers:** A/C/B
- **Modules:** `template-previews.module.ts`, `content.template-previews.module.ts`

### `menus`

- **Entities:** `MenuEntity`, `MenuPageEntity`, `MenuCustomItemEntity`
- **Controllers:** A/C/B. `admin-menus.controller.ts` exposes CRUD for custom items: `POST /api/admin/menus/:id/custom-items`, `PUT /api/admin/menus/:id/custom-items/:itemId`, `DELETE /api/admin/menus/:id/custom-items/:itemId`, `PUT /api/admin/menus/:id/custom-items/:itemId/position` — guarded by `AdminAuthGuard` + `@GrantByPermission(AdminPermissionsEnum['menu.items.add' \| 'menu.update' \| 'menu.items.remove' \| 'menu.items.changePositions'])`. The three CRUD endpoints (`POST` / `PUT` / `DELETE`) are journaled via `@Journalable(MENU_CUSTOM_ITEM_*)`; the position endpoint is not journaled (drag-drop noise). `content-menus.controller.ts` returns the menu as a **tree** (pages + custom items merged by lexorank under `parent_id`; the tree assembly lives in `base-menus.service.ts` and is inherited by `content-menus.service.ts`).
- **Modules:** `menus.module.ts`, `content-menus.module.ts`
- **Custom items:** see `MenuCustomItemEntity` (table `menu_custom_items_mn`) — free-form `{ value, localizeInfos }` items with polymorphic `parent_id` (no FK; can point at `pages.id` or another `menu_custom_items_mn.id`). Newly created items land at the visual bottom via `CommonPositionService` lexorank (`object_category_id = menuId`).

### `markers`

- **Entities:** `MarkerEntity`
- **Controllers:** A/C/B
- **Modules:** `markers.module.ts`, `content.markers.module.ts`

### `page-errors`

- **Entities:** `PageErrorEntity`
- **Controllers:** `page-errors.controller.ts` (shared)
- **Modules:** `page-errors.module.ts`

### `sitemap`

- **Entities:** none (reads from `pages`)
- **Controllers:** `sitemap.controller.ts` (inside `sitemap.module.ts`)
- **Modules:** `sitemap.module.ts` (only for generating XML on the content API)

---

## Catalog

### `products`

- **Entities:** `ProductEntity`, `ProductPageEntity`, `ProductRelationsTemplateEntity`
- **Controllers:** A/D/C/B + `product-relation-template.controller.ts`
- **Services:** `AdminProductsService`, `ProductPageService`, `ProductRelationsTemplateService`, `ProductElasticService`
- **Modules:** `products.module.ts`, `content.products.module.ts`, `developer.products.module.ts`
- **Consumers:** `RelationsProductsConsumer` (queue `relations-products`), `BlockProductsConsumer` (queue `block-products`), `ProductElasticConsumer` (queue `BULL_QUEUES.productElastic`)
- **Queues:** `indexData`, `findProductRelations`, `findBlockProductRelations`, `files`, `events`, `productElastic`
- **CRDT:** product editing goes through `SyncSocketGateway`.

### `product-status`

- **Entities:** `ProductStatusEntity`
- **Controllers:** A/D/C/B
- **Modules:** `product-status.module.ts`, `content-product-status.module.ts`, `developer-product-status.module.ts`
- **Consumer:** `ProductStatusesConsumer` (queue `product-statuses`) — `@Process('set-default-status')`. File `cms/src/modules/products/consumers/product-statuses.consumer.ts` (sic — it lives under `products/`, not `product-status/`).

### `import`

- **Entities:** `CatalogImportTemplateEntity`, `CatalogImportHistoryEntity`
- **Controllers:** `admin-import.controller.ts`, `catalog-import-template.controller.ts`
- **Modules:** `import.module.ts`
- **Transport:** RabbitMQ exchange `exchange-import`, queue `queue-import` → Python `import-backend`.

---

## Attributes and indexing

### `attributes-sets`

- **Entities:** `AttributesSetEntity`, `AttributeSetTypeEntity`
- **Controllers:** `admin-attributes-sets.controller.ts` (A), `developer-attributes-sets.controller.ts` (D), `content-attributes-sets.controller.ts` (C), `base-atribute-sets.controller.ts` (B, typo in the name — `atribute`)
- **Services:** `AdminAttributesSetsService`, `BaseAttributesSetsService` (with `isThereWhoUsingMe`), `AttributeSetTypeService`, `CopyAttributesSetValuesService`
- **Consumer:** `AttributesSetsConsumer` (queue `attributes-sets`) — `@Process('update-changing')`, `@Process('copy-values')`. WS channel `attributesSetsChanging`.
- **Modules:** `attributes-sets.module.ts`, `content.attributes-sets.module.ts`, `developer.attributes-sets.module.ts`

### `index-attributes-sets`

- **Entities:** `IndexAttributeEntity`, `IndexAttributeDataEntity`, `IndexAttributeTypeEntity`
- **Controller:** `index-attribute.controller.ts`
- **Service:** `IndexDataService` (dynamic pass over `information_schema` for indexing).
- **Consumer:** `IndexDataConsumer` (queue `index-data`) — `@Process('index')`, `@Process('index-all')`. WS channels `indexProducts`, `indexHealth`.

### `general-types`

- **Entities:** `GeneralTypeEntity`
- **Controller:** `general-types.controller.ts`
- **Modules:** `general-types.module.ts`

### `modules`

- **Entities:** `ModuleEntity`
- **Controllers:** A/D/C/B
- **Modules:** `modules.module.ts`, `content-modules.module.ts`, `developer-modules.module.ts`

---

## Filters

### `filters`

- **Entities:** `FilterEntity`, `FilterItemEntity`, `FilterCustomItemEntity`
- **Controllers:**
  - `admin-filters.controller.ts` (A) — extends `ContentFiltersController`. Full CRUD over filters / items / custom items + batch `POST /api/admin/filters/:id/items` + drag-drop position + `GET /api/admin/filters/marker-validation/:marker` (uniqueness check). Journaled via `@Journalable`. **Note:** the inherited `GET /api/admin/filters/marker/:marker` is intentionally **blocked** — the admin override (`@ApiExcludeEndpoint` + `throw new MethodNotAllowedException()`) returns 405 so the public path is not reachable from the admin app.
  - `content-filters.controller.ts` (C) — single public `GET /api/content/filters/marker/:marker?langCode=` (anonymous, no `user_permissions` gate); returns items as a tree, with custom items merged in and an extra response-discriminator value `custom`.
  - `base-filters.controller.ts` (B).
- **Services:** `BaseFiltersService` (read path — `getAllDataQuery` issues two SQL branches, admin (flat) and content (with LEFT JOINs to `pages` / `products` / `admins` / `attributes_sets` / `discounts` / `payment_accounts` / `positions` for polymorphic resolution); see `cms/.claude/docs/filters.md` for the full join map) ← `ContentFiltersService` ← `AdminFiltersService` (mutations).
- **Modules:** `filters.module.ts`, `content-filters.module.ts`. The admin module pulls in `CommonPositionModule` (lexorank), the admin socket, and `locales-usage`.
- **Companion endpoint:** `GET /api/admin/index-attributes/unique-values` — DISTINCT values for the attribute picker (scalar + JSON-list strategies in `IndexAttributeValuesService`).
- **Migrations / seeds:**
  - `1880200200000-create-filters-tables.ts` — base tables.
  - `1880200300000-add-attribute-identifier-to-filter-items.ts` — `attribute_identifier` column for direct schema lookup (legacy items keep `NULL` and fall back to a heuristic resolver).
  - `1880200200002-seed-filter-permissions.ts` — two-part seed: (1) grants the 6 new `filter.*` permissions to every admin who already has `menu.create` (convention: "права на меню → права на фильтры"), via `jsonb_set` per key (dotted-path syntax with `{filter.create}` braces because the key itself contains a dot, otherwise jsonb would treat it as a path); (2) **only for the root admin (id=1)**, appends `'filters'` into `permissions->'admins.modules'` via `jsonb_insert`, idempotent through `NOT (permissions->'admins.modules' @> '["filters"]'::jsonb)`. `down()` removes both. Note: regular admins do NOT get the module appended automatically — they have the `filter.*` boolean keys, but the nav entry only shows up for root or for anyone an admin manually adds it for.
  - `1880200200003-seed-add-module-filter.ts` — registers the **Filters** module in the `modules` table itself: `INSERT INTO modules (id=18, identifier='filters', localize_infos={en_US:{title:"Filters"}}, icon='i-filters', is_visible=true)`, then creates a matching row in `positions` (`object_type='module'`, lexorank tail) and updates `modules.position_id`. Wraps work in `DISABLE/ENABLE TRIGGER check_total_rows_trigger`. **Note:** the existence guard checks `WHERE identifier = 'fillters'` (sic — typo with double `l`); the actual INSERT uses `'filters'`, so the guard never matches — left as-is in the source.
- **Detailed reference:** [`cms/.claude/docs/filters.md`](../../cms/.claude/docs/filters.md) — every JOIN, every drag-drop edge case, the attribute display resolver. Read first for any filter-listing / filter-item / filter-position task.

---

## Collections

### `collections`

- **Entities:** `CollectionEntity`, `CollectionRowEntity`
- **Controllers:** A/D/C/B
- **Modules:** `collections.module.ts`, `content-collections.module.ts`, `developer-collections.module.ts`

---

## Forms

### `forms`

- **Entities:** `FormEntity`, `FormPageEntity` (deprecated), `FormModuleConfigEntity`, `FormModuleMnEntity`
- **Controllers:** A/C/B
- **Modules:** `forms.module.ts`, `content-forms.module.ts`

### `form-data`

- **Entities:** `FormDataEntity`
- **Controllers:** A/C/B
- **Modules:** `form-data.module.ts`, `content.form-data.module.ts`

---

## Orders and payments

### `orders`

- **Entities:** `OrderEntity`, `OrderProductEntity`, `OrderStatusEntity`, `OrderStorageEntity`, `OrderStoragePaymentAccountEntity`, `OrdersHistoryEntity`, `OrderRefundEntity`, `OrderRefundRequestEntity`
- **Controllers:** `admin-order.controller.ts`, `admin-orders-storage.controller.ts`, `base-order.controller.ts`, `base-orders-storage.controller.ts`, `content-order.controller.ts`, `content-orders-storage.controller.ts`
- **Modules:** `orders.module.ts`, `content-orders.module.ts`

### `payments`

- **Entities:** `PaymentAccountEntity`, `PaymentSessionEntity`, `PaymentRefundEntity`, `PaymentStageEntity`, `PaymentStatusMapEntity`, `PaymentParamItemEntity`
- **Controllers:** A/C/B
- **Services:** `PaymentRefundService` (uses `BULL_QUEUES.events`)
- **Modules:** `payments.module.ts`, `content-payments.module.ts`

### `discounts`

- **Entities:** `DiscountEntity`, `DiscountConditionEntity`, `DiscountCouponEntity`, `DiscountBonusEventEntity`, `DiscountBonusBalanceEntity`, `DiscountBonusTransactionEntity`, `DiscountBonusUsageDetailEntity`, `DiscountSettingsEntity`
- **Controllers:** A/D/C/B
- **Modules:** `discounts.module.ts`, `content-discounts.module.ts`, `developer-discounts.module.ts`

### `subscriptions`

- **Entities:** `SubscriptionEntity`, `UserSubscriptionEntity`, `StripeCustomerEntity`, `MidtransCustomerEntity`
- **Controllers:** A/C/B
- **Modules:** `subscriptions.module.ts`, `content.subscriptions.module.ts`

---

## Users and admins

### `admins`

- **Entities:** `AdminEntity`, `UpdatedPermissionsLogEntity`
- **Controllers:** `admins-controller.ts` (no audience prefix — shared admin), `base-admins.controller.ts`, `content-admins.controller.ts`, `developer-admins.controller.ts`
- **Services:** `AdminsService`, `BaseAdminsService`, `DeveloperAdminsService`, `ContentAdminsService`, `PermissionsUpdatesCheckingService`
- **Guard:** `AdminAuthGuard` (see `services/admin-auth.guard.ts`)
- **Modules:** `admins.module.ts`, `content.admins.module.ts`, `developer-admins.module.ts`

### `auth`

- **Entities:** `AdminSessionEntity`, `RefreshTokenEntity`
- **Controllers:** `auth.controller.ts`, `developer-auth.controller.ts`
- **Modules:** `auth.module.ts`, `developer-auth.module.ts`

### `users`

- **Entities:** `UserEntity`, `UserActionEntity`, `UserCodeEntity`, `UserSessionEntity`, `UsersAuthProviderEntity`
- **Controllers:** A/C/B + sub-folder `users-auth-providers/` (admin/content/base)
- **Modules:** `users.module.ts`, `content.users.module.ts`

### `user-groups`

- **Entities:** `UserGroupEntity`, `UserGroupMnEntity`
- **Controllers:** A/C/B
- **Modules:** `user-groups.module.ts`, `content-user-groups.module.ts`

### `user-permissions`

- **Entities:** `UserPermissionEntity`, `UserGroupPermissionMnEntity`
- **Controllers:** A/B + content via `content-user-permissions.module.ts`
- **Modules:** `user-permissions.module.ts`, `content-user-permissions.module.ts`

### `user-activity`

- **Entities:** `UserActivityEventEntity`, `CartItemEntity`, `WishlistItemEntity`, `UserRecommendationEntity`, `UserSegmentEntity`, `TriggeredCommunicationLogEntity`
- **Controllers:**
  - `content-cart.controller.ts` (`/api/content/users/me/cart` — lives in `modules/users/controllers/`, depends on `CartService` from this module)
  - `content-wishlist.controller.ts` (`/api/content/users/me/wishlist` — same setup)
  - `content-user-activity.controller.ts` (`/api/content/user-activity/track`)
- **Services:** `UserActivityService`, `CartService`, `WishlistService`, `GuestCartStorageService`, `GuestWishlistStorageService`, `CartWishlistEventEmitterService`, `RecommendationEngineService`, `RecommendationSignalsCollectorService`, `UserSegmentsService`, `NoticePublisherService`
- **Modules:** `user-activity.module.ts`, `content.user-activity.module.ts`
- **Queue:** Bull `BULL_QUEUES.userActivity = 'user-activity'`. **Implemented consumers** in `cms/src/modules/user-activity/consumers/`:
  - `FlushActivityBufferConsumer` — `@Process(BULL_CONSUMERS.flushActivityBuffer)`
  - `TrendingConsumer` — `@Process(BULL_CONSUMERS.recomputeTrending)`
  - `CleanupOldActivityConsumer` — `@Process(BULL_CONSUMERS.cleanupOldActivity)`
  - `RecommendationConsumer` — `@Process(BULL_CONSUMERS.recomputeRecommendations)`
  - `SegmentsRecomputeConsumer` — `@Process(BULL_CONSUMERS.recomputeSegments)`
  - `DormantReactivationConsumer` — `@Process(BULL_CONSUMERS.dormantReactivation)`
  - `RefreshPurchaseHistoryConsumer` — `@Process(BULL_CONSUMERS.refreshUserPurchaseHistory)`

  Job names come from `BULL_CONSUMERS` (`cms/src/config/constants.ts:40-70`).

---

## Events and notifications

### `events`

- **Entities:** `EventEntity`, `EventSubscriptionEntity`, `EventEmailSettingsEntity`, `FirebaseCredentialsEntity`
- **Controllers:** `admin-events.controller.ts`, `content-events.controller.ts`, `settings.controller.ts`
- **Consumer:** `EventsProcessor` (`events/consumers/events.consumer.ts`, queue `BULL_QUEUES.events`) — handlers `change-product-attribute`, `change-product-status`, `sign-up`, `send-user`, `change-password`, `change-order-status`, `change-user-form-data`, `submit-form-data`, `mailing`, `refund`, `discount-start`, `discount-end`, `bonus-accrual`, `bonus-expiration`.
- **Workflows node:** consumer in `events/nodes/events.node.ts` (queue `BULL_QUEUES.workflows`) — `@Process(BULL_CONSUMERS.workflows)`.
- **Transport:** RabbitMQ `exchange-message` → the separate `notice-service`.
- **Modules:** `events.module.ts`, `content-events.module.ts`

---

## Journal and versions

### `journal`

- **Entities:** `JournalRecordEntity`, `ContentApiErrorEntity`
- **Controllers:**
  - `journal.controller.ts` — base journal API (records list, get one, etc.).
  - `controllers/admin-content-api-errors.controller.ts` — admin tab "Content API errors" (list/detail/cleanup over `content_api_errors`).
  - `controllers/admin-content-api-stats.controller.ts` — request volume & timings aggregated per route/period (`content-api-period.enum.ts`).
  - `controllers/admin-journal-traffic.controller.ts` — traffic metrics tab; queries Prometheus via `PrometheusQueryService`.
- **Services:** `JournalService` (file `jounal.service.ts`, sic — typo), `AdminContentApiErrorsService`, `ContentApiStatsService`, `AdminJournalTrafficService`, `ContentApiRoutesRegistryService` (on `onModuleInit` reads the static `src/modules/journal/content-routes.generated.json` via `fs.readFileSync` and exposes the route list to other journal services; the legacy `scripts/generate-content-routes.ts` that produced that JSON was removed in develop, so the JSON is now a checked-in snapshot, not regenerated at build time), `JournalCleanupService`, `PrometheusQueryService`.
- **Consumers:** `consumers/content-api-error.consumer.ts` — `@Process(...)` on Bull queue `content-api-errors`; persists error records produced by the global exception filter without blocking the request path.
- **Exception filter:** `shared/exception-filters/content-api-error-logger.filter.ts` — global filter on the content app that publishes a sanitized job onto the `content-api-errors` queue for every 4xx/5xx.
- **Utils:** `utils/sanitize-request-body.util.ts` — redacts secrets / truncates payloads before they hit the queue.
- **Decorator:** `@Journalable(JournalingEvents)` — `decorators/journalable.decorator.ts`
- **Interceptor:** `JournalInterceptor` (admin), `DeveloperJournalInterceptor` (developer)
- **Modules:** `journal.module.ts`, `developer-journal.module.ts`

### `entity-versions`

- **Entities:** `EntityVersionEntity`
- **Controller:** `admin-entity-versions.controller.ts`
- **Service:** `EntityVersionService` (snapshot via `information_schema`)
- **Modules:** `entity-versions.module.ts`

---

## Localization

### `locales`

- **Entities:** `LocaleEntity`
- **Controllers:** A/C/B
- **Modules:** `locales.module.ts`, `content-locales.module.ts`

### `multilanguage`

- **Entities:** `LanguageEntity`
- **Controllers:** none (or internal)
- **Modules:** `multilanguage.module.ts`

### `locales-usage`

- **Entities:** `LocalesUsageEntity`
- **Modules:** `locales-usage.module.ts`

---

## Files and export

### `file-upload`

- **Controllers:** `admin-file-upload.controller.ts`, `base-file-upload.controller.ts`, `content-file-upload.controller.ts`, `files-editor.controller.ts`
- **Consumers:** `FilesConsumer` (queue `files`) — `@Process('delete')`, `@Process('copy')`. `PreviewConsumer` (queue `preview`) — three `@Process({ ... })`.
- **Modules:** `file-upload.module.ts`, `content.file-upload.module.ts`

### `export`

- **Controller:** `admin-export.controller.ts`
- **Modules:** `export.module.ts`
- Uses AdminPermissions: `export.users`, `export.orders`, `export.payments`.

---

## Sockets

### `socket`

- **Gateways (`cms/src/modules/socket/`):**
  - `DeveloperSocketGateway` (`developer-socket.gateway.ts`) — the primary one, with the `sendSocketNotification(payload, action, channel)` method. `@SubscribeMessage('indexProducts'|'indexPages'|'indexProductsStop'|'indexDataStop'|'relationsProducts'|'checkIndexProducts'|'changePosition'|'import'|'attributeChangingValue'|'ping')`.
  - `AdminSocketGateway` extends `DeveloperSocketGateway` — listens to `SharedRedisService` for cross-API notifications.
  - `ContentSocketGateway` — a separate `/api/content/ws` path, for authorized users by userSession.
  - `SyncSocketGateway` — a separate WS server on `WS_SYNC_SERVER_PORT` via `y-websocket/bin/utils.setupWSConnection` (used only for products and pages).
- **Service:** `SharedRedisService` — pub/sub between the admin and developer gateways.
- **Modules:** `admin-socket.module.ts`, `developer-socket.module.ts`, `content-socket.module.ts`

---

## Workflows

### `workflows`

- **Entities:** `WorkflowsStorageEntity`
- **Gateway:** `workflows.gateway.ts` — `@SubscribeMessage('subscribe')`, `@SubscribeMessage('unsubscribe')`
- **Modules:** `workflows.module.ts`

### `workflows-api`

- External API for workflows.
- **Modules:** `workflows-api.module.ts`

---

## Positions

### `position`

- **Entities:** `PositionEntity`
- **Modules:** `position.module.ts`, `common-position.module.ts`, `developer.position.module.ts`

---

## Backups and system settings

### `backups`

- **Entities:** `BackupEntity`
- **Modules:** `backups.module.ts`

### `system`

- **Entities:** `SystemEntity`, `AppCertEntity`, `AppTokenEntity`
- **Controllers:** `admin-system.controller.ts`, `content-system.controller.ts`
- **Consumers:** `SystemConsumer` (queue `system`) — `@Process('clean-users'|'delete-certs'|'calculate-ratings'|'sync-storage')`. `DeveloperSystemConsumer` (queue `system-dev`) — `@Process('upload-user-module')`. `ContentSystemConsumer` (queue `system-content`) — `@Process('sync-swagger-files')`.
- **Modules:** `system.module.ts`, `content-system.module.ts`

### `settings-general`

- **Entities:** `SettingsGeneralEntity`
- **Controller:** `admin-settings-general.controller.ts`
- **Modules:** `admin-settings-general.module.ts`, `content-settings-general.module.ts`

### `immutable-settings`

- **Entities:** `ImmutableSettingsEntity`, `UsageImmutableSettingsEntity`
- **Controller:** `admin-immutable-settings.controller.ts`
- **Modules:** `admin-immutable-settings.module.ts`, `content-immutable-settings.module.ts`

### `health`

- Healthcheck endpoint. File: `health.module.ts`.

### `rabbitmq`

- **Modules:** `rabbitmq-publisher.module.ts`, `rabbitmq-consumer.module.ts`, `rabbitmq-content.consumer.module.ts`
- Uses `nestjs-plus` + `amqplib` (see the root `CLAUDE.md`).

---

## Shared

| Folder | What |
|---|---|
| `cms/src/shared/entities/` | `BaseAbstractEntity`, `BaseAttributeSetsAbstractEntity`, `BasePositionAbstractEntity` |
| `cms/src/shared/decorators/` | `IsLocalizeInfos`, and others |
| `cms/src/shared/guards/` | General-purpose guards |
| `cms/src/shared/interceptors/` | Base interceptors |
| `cms/src/shared/exception-filters/` | Global filters |
| `cms/src/shared/consumers/` | `SystemConsumer`, `DeveloperSystemConsumer`, `ContentSystemConsumer` |
| `cms/src/shared/services/` | Shared services |
| `cms/src/shared/utils.ts` | Utilities (`typeormTransaction`, `extractAccessTokenFromHeader`, etc.) |
| `cms/src/shared/types/` | `common.types.ts` with `LocalizeInfo`, `CommonLocalizeInfos`, `AttributesSetsTables`, `PositionRelationTypes`, etc. |
| `cms/src/shared/shared.module.ts` | Base shared module |
| `cms/src/shared/developer.shared.module.ts` | Shared for developer API |
| `cms/src/shared/als.shared.module.ts` | AsyncLocalStorage |

---

## Completeness of the list

The list above is built from every `*.module.ts` under `cms/src/modules/` (as of 2026-05-29: 97 module files under `cms/src/modules/` plus 8 top-level — `base.app.module.ts`, `admin.app.module.ts`, `developer.app.module.ts`, `content.app.module.ts` in `cms/src/`, plus `shared.module.ts`, `developer.shared.module.ts`, `als.shared.module.ts` in `cms/src/shared/`, = 105 module files total across `cms/src/`). If a module is missing — `find cms/src -name "*.module.ts" -type f`.

---

## Related documents

- [`patterns-controllers.md`](./patterns-controllers.md) — splitting admin/developer/content.
- [`patterns-queues-and-ws.md`](./patterns-queues-and-ws.md) — Bull queues and WS channels.
- [`entities-catalog.md`](./entities-catalog.md) — all entities.
