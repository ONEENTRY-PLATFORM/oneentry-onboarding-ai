# Use cases — "If you need X, use Y"

This is the main entry-point file for picking up a task. When the user comes in with a description of a new feature (a bookstore, a vacancy catalog, a blog, a contact form, birthday discounts), we open this file first and look for the case **closest in meaning**. Only when nothing fits do we move on to [`when-not-to-create-tables.md`](./when-not-to-create-tables.md), and only as a last resort do we invent a new entity.

Every case here is grounded in real code in `cms/src/`. Entity, module, and enum names are the same as in the repo.

> **AI rule:** do not propose a new table if the task fits one of the cases below. Use the existing data model.

---

## Case catalog (briefly)

| # | If you need | Use |
|---|---|---|
| 1 | A product catalog | `products` + `attribute_set forProducts` + `general_types.product` |
| 2 | A content page (news, blog, article, "About us") | `pages` (`general_type=common_page`) + `blocks` |
| 3 | A catalog page / category | `pages` (`general_type=catalog_page`) + `config: jsonb` |
| 4 | A custom field on a product / page / admin / user group | Extend the `attribute_set` (see [data-model-core](./data-model-core.md)) |
| 5 | A list of similar records (FAQ, cities, reviews) | `collections` + `collection_rows` (+ optional `form_id`) |
| 6 | Receiving form input (application, registration, contact form) | `forms` + `form_data` |
| 7 | A site menu (with optional free-form items) | `menus` + `menu_pages_mn` (M2M page↔menu) + `menu_custom_items_mn` (custom items) |
| 8 | A page / product template | `templates` + `general_type_id` |
| 9 | A preview template | `template_previews` |
| 10 | Push / email / webhook on an event | `events` + Bull queue `events` + RabbitMQ → `notice-service` |
| 11 | A user subscription to an event | `event_subscription` |
| 12 | An order | `orders` + `orders_storage` + `order_statuses` + `order_products` |
| 13 | Order storage (multi-tenancy for orders) | `orders_storage` (linked to `general_type` and a form) |
| 14 | A discount / promo code / coupon / bonuses | `discounts` + `discount_coupons` + `discount_conditions` + `discount_bonus_*` |
| 15 | A payment session / refund | `payment_sessions` + `payment_accounts` + `payment_refunds` |
| 16 | User groups and their attributes | `user_groups` (with attribute_set) + `user_groups_mn` |
| 17 | Permissions for non-admin users | `user_permissions` + `user_group_permissions_mn` |
| 18 | Markers (tags for attributes / sections) | `markers` |
| 19 | Locales and languages | `locales` + `language` + `localize_infos` (jsonb on entities) |
| 20 | File upload / previews | `file-upload` + Bull `files` / `preview` (S3/Minio) |
| 21 | Attribute indexing for search | `index_attributes` + `index_attribute_data` + Bull `index-data` |
| 22 | Catalog import from Excel / CSV / JSON | `catalog_import_templates` + `catalog_import_history` + RabbitMQ `queue-import` → `import-backend` |
| 23 | A subscription / billing (Stripe / Midtrans) | `subscriptions` + `user_subscriptions` + `stripe_customers` / `midtrans_customers` |
| 24 | User activity (views, cart, wishlist, recently viewed) | `cart_items` + `wishlist_items` + `user_activity_events` + Bull `user-activity` + Redis (guest cart/wishlist) |
| 25 | An audit of admin actions | The `@Journalable` decorator (NOT your own table) |
| 26 | Entity version history (rollback) | `entity_versions` (universal) |
| 27 | A real-time notification to admins (background task finished, indexing, etc.) | `AdminSocketGateway.sendSocketNotification` + Bull `@OnQueueActive/Completed/Failed` |
| 28 | CRDT collaborative editing (product / page) | `SyncSocketGateway` (port `WS_SYNC_SERVER_PORT=3007`) + yjs |
| 29 | Custom module / entity settings (arbitrary jsonb) | `properties / config / custom_settings: jsonb` (see below) |
| 30 | Blocks (generic page/product sections) | `blocks` + `block_pages_mn` / `block_products_mn` / `product_blocks_mn` + `custom_settings jsonb` |
| 31 | An uploaded third-party module (developer API) | `modules` (`general_types_mn` + `attribute_set_types_mn`) |
| 32 | A named picker / curated list of mixed entities (a "facet", "saved selection") | `filters` + `filter_items_mn` (polymorphic by `object_type`) + `filter_custom_items_mn` (free-form) |

---

## Detailed cases

### 1. Product catalog (shop, assortment, books, electronics, ...)

- **Entity:** `ProductEntity` (`cms/src/modules/products/entities/product.entity.ts`, table `products`).
- **Type:** `GeneralType.Product` in `general_types`.
- **Product attributes (name, price, description, images, SKU):** through an `attribute_set` of type `forProducts`. Schema markers on attributes: `isPrice`, `isSku`, `isCurrency`, `isProductPreview`, `isIcon`, `isTaxRate`, `isRatingValue` (see `SchemaItem` in [data-model-core](./data-model-core.md#23-the-attribute-set-schema-metadata)).
- **Category binding (to a page):** through the M2M `products_pages_mn` (`ProductPageEntity`).
- **Display template:** `template_id` → `templates` (+ `short_desc_template_id`).
- **Status:** `status_id` → `product_statuses` (module `product-status`).
- **Import from an external system:** the `import_id` column in `products` (for re-matching), module `import`.
- **Product-to-product relations (related/similar):** `product_relations_templates` + Bull queue `relations-products`.

**Do not create:** a dedicated `books` / `vacancies` / `cars` table. All of these are `products` with different `attribute_set_id`. The difference lies in the set's schema and the values in `attributes_sets`.

### 2. Content pages (news, blog, "About us", articles, landings)

- **Entity:** `PageEntity` (`cms/src/modules/pages/entities/page.entity.ts`, table `pages`).
- **Type:** `GeneralType.CommonPage` (`'common_page'`).
- **Localized text:** `localize_infos jsonb` with shape `{ [lang]: { title, plainContent, htmlContent, menuTitle } }` (see `PageLocalizeInfos`).
- **Page contents (modules / sections):** **blocks** (see case 30), linked through `block_pages_mn` (`BlockPageEntity`). The `isNested` field determines whether the block is also attached to all nested products.
- **Hierarchy (categories → subcategories):** `parent_id` + `depth` + `category_path`.
- **URL:** `page_url` (unique, indexed).

**Do not create:** an `articles` / `blog_posts` / `news` table. These are `pages` with `common_page` or a variant with its own `attribute_set` tailored to the field set you need (for example, a blog could use an `attribute_set` with attributes `author`, `tags`, `cover`).

### 3. Catalog / category pages with filtering and a subset of products

- **Entity:** `PageEntity`, `GeneralType.CatalogPage` (`'catalog_page'`).
- **Output settings (rowsPerPage, productsPerRow):** the `config jsonb` column on `pages` (see `PageEntity.config: Record<string, number>`).
- **Product binding:** via `products_pages_mn` (`ProductPageEntity`).

### 4. A custom field on an existing entity

If the task is "we need to add a field X to a product", "give the admin a phone field", "give the page a custom JSON" — **do not add a SQL column**. Extend the `attribute_set`:

- Find or create the set you need (`attributes_sets`, `type` = matching `AttributesSetType`).
- Add a new `SchemaItem` to its `schema` (jsonb) with the right `type` (`string`, `text`, `integer`, `list`, `image`, ...).
- All consumer tables will pick up the attribute automatically through the Bull job `attributes-sets:update-changing` (see [`patterns-queues-and-ws.md`](./patterns-queues-and-ws.md)).

This only works if the entity has an `attribute_set_id` column — see the list of such entities in [data-model-core §1](./data-model-core.md#1-base-abstract-entities).

### 5. A list of similar records (FAQ, cities, countries, brands, reviews)

- **Entity:** `CollectionEntity` (`cms/src/modules/collections/entities/collection.entity.ts`, table `collections`).
- **Items:** `CollectionRowEntity` (table `collection_rows`), storing `form_data jsonb` with shape `{ [lang]: [{ marker, type, value }, ...] }`.
- **Form binding for the input/edit UI:** `form_id` on `collections`.
- **Link to another entity (e.g. a review attached to a product):** `entity_type` (varchar) + `entity_id` (int) on `collection_rows` — a generic reference.

**Do not create:** an `faq` / `cities` / `countries` table. All of these are one collection (`collections.identifier='faq'`) and its rows.

### 6. Receiving form input (application, registration, contact form, vote)

- **Entity:** `FormEntity` (`cms/src/modules/forms/entities/form.entity.ts`, table `forms`). Form metadata — name, type, processing method.
- **Form type:** `FormType` (`'data'`, `'order'`, `'sing_in_up'`, `'collection'`, `'rating'`).
- **Processing method:** `FormProcessingType` (`'db'`, `'email'`, `'script'`).
- **Form fields:** through an `attribute_set` of type `forBlock` (a form extends `BaseAttributeSetsAbstractEntity`).
- **Submitted data:** `FormDataEntity` (`form_data` table, `cms/src/modules/form-data/entities/form-data.entity.ts`). Fields: `form_identifier`, `form_data jsonb`, `user_identifier`, `entity_identifier`, `status` (`FormDataStatusType`), `ip`, `fingerprint`.

**Do not create:** `contact_requests` / `vacancy_applications` tables. Create a form with the right `attribute_set` and read `form_data` by `form_identifier`.

### 7. Site menu

- **Entity:** `MenuEntity` (`menus` table).
- **Page binding:** `MenuPageEntity` (M2M `menu_pages_mn`), with order via `position_id` and the `is_pinned` flag.
- **Free-form (custom) items — external URL, anchor, mailto, tel, relative path:** `MenuCustomItemEntity` (`menu_custom_items_mn`). Localized `localizeInfos`, scalar `value`, polymorphic `parent_id` (no FK — may point at `pages.id` or another `menu_custom_items_mn.id`). Ordered via the same lexorank pool as menu pages (`object_category_id = menuId`).
- **Content API output:** `GET /api/content/menus/marker/:marker` returns a **tree** that interleaves `menu_pages_mn` rows and `menu_custom_items_mn` rows by lexorank under `parent_id`. Newly created custom items land at the visual bottom.

**Do not create:** an `external_menu_links` / `custom_nav_items` table — that's exactly what `menu_custom_items_mn` is for.

**Example:** [examples/13-menus-and-markers.md](./examples/13-menus-and-markers.md)

### 8. Page / product / block template

- **Entity:** `TemplateEntity` (`templates`).
- **Applicability is defined via `general_type`:** a template references `general_types` (`forCatalogPages`, `forCommonPages`, etc. — concrete values are in `general-types.enum.ts` + seeds).
- **Usage:** `template_id` on `pages` / `products` / `blocks`.
- Has its own `attribute_set` (extends `BaseAttributeSetsAbstractEntity`).

**Example:** [examples/11-templates-and-previews.md](./examples/11-templates-and-previews.md)

### 9. Preview template

- `TemplatePreviewsEntity` (`template_previews`). Separate from regular templates, linked to an attribute via `previewTemplateId` (see `SchemaItem.previewTemplateId`).

**Example:** [examples/11-templates-and-previews.md](./examples/11-templates-and-previews.md)

### 10. Push / email / WS / webhook on an event

- **Entity:** `EventEntity` (`events` table). Fields:
  - `type: EventType` (`'attribute'` / `'status'`),
  - `actions jsonb`: `{ isPush, isWebsocket, isEmail, isWorkflows }`,
  - `mailing jsonb`: frequency and conditions,
  - linked to `modules`, `user_groups`, `payment_accounts`.
- **Worker:** `EventsProcessor` (`cms/src/modules/events/consumers/events.consumer.ts`), Bull queue `BULL_QUEUES.events`. Handles: `changeProductAttribute`, `changeProductStatus`, `signUp`, `sendCode`, `changePassword`, `changeOrderStatus`, `changeUserFormData`, `submitFormData`, `mailing`, `refund`, `discountStart`, `discountEnd`, `bonusAccrual`, `bonusExpiration` (names from `BULL_CONSUMERS` in `cms/src/config/constants.ts`).
- **Push/email delivery:** via RabbitMQ exchange `exchange-message` → the separate `notice-service` (out of scope of this document).
- **Email server configuration:** `EventEmailSettingsEntity` (`event_email_settings`).
- **Firebase credentials:** `FirebaseCredentialsEntity` (`firebase_credentials`).

### 11. User subscription to an event

- `EventSubscriptionEntity` (`event_subscription`). Links user ↔ event ↔ product. Used for "notify me when the product is back / the price changes".

**Example:** [examples/06-event-notification.md § User subscription to an event](./examples/06-event-notification.md#user-subscription-to-an-event-event_subscription)

### 12. Order

- **Entity:** `OrderEntity` (`orders`). Does NOT extend `BaseAbstractEntity` — an order has its own set of fields.
- **Order form data (name, address, phone):** `form_data jsonb` with shape `FormDataLangType`.
- **Products:** `OrderProductEntity` (`order_products`), unique `(productId, orderId, isGift)`.
- **Change history:** `OrdersHistoryEntity` (`orders_history`).
- **Status:** `status_id` → `OrderStatusEntity` (`order_statuses`).
- **Refund:** `OrderRefundEntity` (`order_refunds`), `OrderRefundRequestEntity` (`order_refund_requests`).
- **Payment strategy:** `payment_strategy` (`OrderPaymentStrategy`).

### 13. Order storage (multi-tenancy: restaurants / branches / order types)

- **Entity:** `OrderStorageEntity` (`orders_storage`).
- **Form binding:** `form_id` (the form used for entering order data).
- **Payment account binding:** M2M `OrderStoragePaymentAccountEntity`.
- **Type:** `general_type_id` (via `general_types`).
- **Storage-specific order statuses:** OneToMany `order_statuses`.

### 14. Discounts, coupons, bonuses

- **Entity:** `DiscountEntity` (`discounts`). Has an `attribute_set` (`forDiscounts`). Type: `DiscountType` (`DISCOUNT` / `BONUS` / `PERSONAL_DISCOUNT`).
- **Applicability conditions:** `DiscountConditionEntity` (`discount_conditions`), condition types — `DiscountConditionType` (`PRODUCT`, `CATEGORY`, `ATTRIBUTE`, `PRODUCT_IN_CART`, `CATEGORY_IN_CART`, `MIN_CART_AMOUNT`, `USER_LTV`, `USER_ATTRIBUTE`).
- **Coupons:** `DiscountCouponEntity` (`discount_coupons`).
- **Bonuses (loyalty program):**
  - `DiscountBonusBalanceEntity` (`discount_bonus_balance`) — the user's balance,
  - `DiscountBonusTransactionEntity` (`discount_bonus_transaction`) — movements,
  - `DiscountBonusEventEntity` (`discount_bonus_events`) — accrual configuration,
  - `DiscountBonusUsageDetailEntity` (`discount_bonus_usage_detail`).
- **Global settings:** `DiscountSettingsEntity` (`discount_settings`).

### 15. Payments and refunds

- `PaymentAccountEntity` (`payment_accounts`) — payment provider configuration (Stripe, YooKassa, etc.).
- `PaymentSessionEntity` (`payment_sessions`) — a specific payment attempt, tied to an order or subscription.
- `PaymentRefundEntity` (`payment_refunds`) — refunds.
- `PaymentStageEntity` (`payment_stages`), `PaymentStatusMapEntity` (`payment_status_map`), `PaymentParamItemEntity` (`payment_param_items`) — service tables.

**Example:** [examples/12-payments-and-refunds.md](./examples/12-payments-and-refunds.md)

### 16. User groups

- **Entity:** `UserGroupEntity` (`user_groups`), has an `attribute_set` (`forUserGroups`).
- **Hierarchy:** `parent_id`, `depth`, `category_path` — same as for pages.
- **User binding:** M2M `UserGroupMnEntity` (`user_groups_mn`).
- **System guests group:** id = `GUEST_USER_GROUP_ID` (= 1) from `cms/src/config/constants.ts`.

### 17. Permissions for non-admin users

- `UserPermissionEntity` (`user_permissions`) — the list of available actions.
- `UserGroupPermissionMnEntity` (`user_group_permissions_mn`) — M2M group ↔ permission.

**Do not confuse** with `AdminPermissionsEnum` (that one is for admins, see [`patterns-controllers.md`](./patterns-controllers.md)).

### 18. Markers (tags)

- `MarkerEntity` (`markers`). A lightweight entity: `name`, `marker` (unique, indexed), `localizeInfos`.
- Used for tagging attributes / sections in the UI.

**Example:** [examples/13-menus-and-markers.md](./examples/13-menus-and-markers.md)

### 19. Locales and languages

- `LocaleEntity` (`locales`) — a specific active interface locale. Fields: `code` (`en_US`), `shortCode` (`en`), `name`, `nativeName`, `isActive`, `position`.
- `LanguageEntity` (`languages`) — language reference (`name`, `code`). These are different tables and different modules (`locales` / `multilanguage`).
- In code, localized text is stored in `localize_infos jsonb` on the entity with shape `{ [code]: { title, ... } }`.
- `LocalesUsageEntity` (`locales-usage` module, `content_locales_usage` table) — a separate accounting of which locales are used where.

**Example:** [examples/14-locales-and-i18n.md](./examples/14-locales-and-i18n.md)

### 20. Files

- The `file-upload` module. Upload / delete / copy via the `files` and `preview` Bull queues (`cms/src/modules/file-upload/consumers/files.consumer.ts`, `preview.consumer.ts`).
- File-typed attributes in the schema: `image`, `file`, `groupOfImages` (see `AttributeType`).
- When importing file values — deferred download via the `file_upload_value jsonb` column on `products`.

**Example:** [examples/15-file-upload-pipeline.md](./examples/15-file-upload-pipeline.md)

### 21. Attribute-based search (indexing)

- `IndexAttributeEntity` (`index_attributes`) — the registry of indexed attributes: `tableName` (`IndexTableType`), `identifier`, `typeId`, `additionalInfo / additionalFields jsonb`.
- `IndexAttributeDataEntity` (`index_attribute_data`) — denormalized "row from (id) consumer-table × attribute × language × value" table. Unique index on `(dataId, attributeId, tableName, identifier, langCode)`. Flags `isPrice`, `isSku`, `isCurrency`, `isProductPreview`, `isIcon`, `isTaxRate` — for fast "get all SKUs for products with this set" lookups.
- **Bull queue:** `index-data`, consumer `IndexDataConsumer` (`@Process('index')`, `@Process('index-all')` in `cms/src/modules/index-attributes-sets/consumers/index-data.consumer.ts`).
- **WebSocket progress notifications:** channels `indexProducts` / `indexHealth` via `socketService.sendSocketNotification`.

**Example:** [examples/16-index-attributes-search.md](./examples/16-index-attributes-search.md)

### 22. Catalog import

- `CatalogImportTemplateEntity` (`catalog_import_templates`) — templates (mapping of Excel/CSV columns ↔ attributes).
- `CatalogImportHistoryEntity` (`catalog_import_history`) — import log.
- **Transport:** RabbitMQ exchange `exchange-import`, queue `queue-import`, the queue name is in `cms/src/config/constants.ts` (`RABBITMQ_QUEUES.queueImport`; routing keys are in `RABBITMQ_ROUTING_KEYS`).
- **Receiver:** Python service `import-backend` (out of scope of this document).

### 23. Subscriptions / billing

- `SubscriptionEntity` (`subscriptions`) — a subscription plan.
- `UserSubscriptionEntity` (`user_subscriptions`) — a specific user subscription.
- `StripeCustomerEntity` (`stripe_customers`), `MidtransCustomerEntity` (`midtrans_customers`) — external provider customer ids.

**Example:** [examples/17-subscriptions-billing.md](./examples/17-subscriptions-billing.md)

### 24. User activity (views, recently viewed, cart, wishlist)

- **Activity events entity:** `UserActivityEventEntity` (`user_activity_events`). Shape: `userId | guestId`, `productId | pageId`, `eventType`, `createdAt`.
- **Event type:** `UserActivityEventType` — `product_view`, `page_view`, `category_view`, `search`, `product_add_to_cart`, `product_remove_from_cart`, `product_add_to_wishlist`, `product_remove_from_wishlist`, `product_purchase`, `product_rating`.
- **Bull queue:** `user-activity` with **implemented** consumers — `FlushActivityBufferConsumer` (`flush-activity-buffer`), `TrendingConsumer` (`recompute-trending`), `CleanupOldActivityConsumer` (`cleanup-old-activity`), `RecommendationConsumer` (`recompute-recommendations`), `SegmentsRecomputeConsumer` (`recompute-segments`), `DormantReactivationConsumer` (`dormant-reactivation`), `RefreshPurchaseHistoryConsumer` (`refresh-user-purchase-history`). All names live in `BULL_CONSUMERS` (`cms/src/config/constants.ts`).
- **Cart and wishlist for authenticated users — dedicated normalized tables:** `CartItemEntity` (`cart_items` — `userId`, `productId`, `qty`, `addedAt`, BIGSERIAL id, `UNIQUE(user_id, product_id)`) and `WishlistItemEntity` (`wishlist_items` — same shape minus `qty`). FK `ON DELETE CASCADE` on `users.id` and `products.id`. **Language-agnostic** (no `langCode`). Introduced by migration `1870797500000-create-cart-and-wishlist-items-tables.ts`. The legacy `users.system_attributes_sets` storage was removed by migration `1870797500001-drop-user-activity-system-attribute-set.ts` (2026-05-22).
- **Guest carts/wishlists:** `GuestCartStorageService` / `GuestWishlistStorageService` — keyed by `guestId` (a UUID from the `X-Guest-Id` header). Redis keys `cart:guest:<uuid>` (TTL 30 days) and `wishlist:guest:<uuid>` (TTL 90 days), constants in `cms/src/modules/user-activity/types/guest-storage-config.ts`.

**Example:** [examples/18-user-activity-cart-wishlist.md](./examples/18-user-activity-cart-wishlist.md)

### 25. Admin action audit

- **Do NOT create your own table.** Use the `@Journalable(JournalingEvents.X)` decorator on the controller method. The interceptor (`JournalInterceptor` in `cms/src/modules/journal/journal.interceptor.ts`, which extends `DeveloperJournalInterceptor`) automatically writes a row into `journal_records` (`JournalRecordEntity`).
- **If the right `JournalingEvents` value is missing** — add it in `cms/src/modules/journal/types/journaling-events.ts` and in `ModuleNameEnum` (if there's no `<ControllerName>Controller → MODULE_NAME` mapping yet).

**Example:** [patterns-journal-blockers-versioning.md](./patterns-journal-blockers-versioning.md)

### 26. Version history (rollback)

- **Entity:** `EntityVersionEntity` (`entity_versions`). A universal table: `entity_name`, `entity_id`, `version`, `action`, `data jsonb`, `admin_id`. Unique (entityName, entityId, version).
- Triggers / the snapshot service — `cms/src/modules/entity-versions/`. The snapshot is built from `information_schema` — there's no entity registry you have to maintain by hand.

**Example:** [patterns-journal-blockers-versioning.md](./patterns-journal-blockers-versioning.md)

### 27. Real-time notification to the admin panel

If a background task (Bull) needs to tell the admin panel "started / progress / finished":

- **Bull hooks**: `@OnQueueActive` / `@OnQueueCompleted` / `@OnQueueFailed` / `@OnQueueError` on the consumer — internally they call `socketService.sendSocketNotification(payload, action, channel)`. The channel is a string like `'indexProducts'`, `'attributesSetsChanging'`, `'blockProducts'`, `'indexHealth'`.
- **Direct call from a service**: inject `AdminSocketGateway` (for the admin API) or `DeveloperSocketGateway` (for the developer API), method `sendSocketNotification`.

For details — see [`patterns-queues-and-ws.md`](./patterns-queues-and-ws.md).

### 28. CRDT collaborative editing

- `SyncSocketGateway` (`cms/src/modules/socket/sync-socket.gateway.ts`) brings up a dedicated WebSocket server on `WS_SYNC_SERVER_PORT` (default 3007) via `y-websocket/bin/utils.setupWSConnection`.
- Within the CMS scope it is used only for **products** and **pages** (the frontend connects with `WebsocketProvider` clients).
- This means `products` does not have a full-fledged `PUT /admin/:id` for replacing the whole object — changes go into YJS docs, and the DB backup is written in parallel.

**Example:** [patterns-queues-and-ws.md § CRDT](./patterns-queues-and-ws.md)

### 29. Arbitrary jsonb for settings / config

If you need to store "free-form" settings on an entity and don't want to introduce a table — use one of the existing jsonb column patterns:

- `attributes_sets.properties` (jsonb) — extra properties for the attribute set.
- `pages.config` (jsonb `Record<string, number>`) — catalog page output settings.
- `modules.config` (jsonb `Record<string, any>`) — module settings.
- `blocks.custom_settings` (jsonb `BlockCustomSettings`) — settings for a specific block (slider, sortType, conditions).
- `forms.localizeInfos` (jsonb `FormLocalizeInfos`) — form descriptions with translations and success/error messages.
- `users.state` (jsonb `Record<string, any>`) — the user's client-side state.

If nothing among the existing slots fits — consider whether it is better to add an attribute (of type `json`) to an `attribute_set`.

### 30. Blocks (generic sections for pages/products)

- **Entity:** `BlockEntity` (`blocks`). Has an `attribute_set` (`forBlocks`).
- **Type:** `GeneralType.CommonBlock` / `ProductBlock` / `SimilarProductsBlock` / `FrequentlyOrderedBlock` / `SliderBlock` / `TrendingBlock` / `RecentlyViewedBlock` / `RepeatPurchaseBlock` / `PersonalRecommendationsBlock` / `CartComplementBlock` / `CartSimilarBlock` / `WishlistSimilarBlock` (full list — see [data-model-core §4](./data-model-core.md#4-general_types--entity-types)).
- **Page binding:** `block_pages_mn` (`BlockPageEntity`), the `is_nested` flag determines inheritance to child products.
- **Product binding:**
  - `block_products_mn` (`BlockProductsEntity`) — a specific block, specific products (for blocks like "recommendations"),
  - `product_blocks_mn` (`ProductBlocksEntity`) — the reverse link product → blocks displayed on this product.
- **Custom settings:** `custom_settings jsonb` (`BlockCustomSettings`):
  - `productConfig` (per language: `quantity`, `sortType: BlockSortType`, `sortOrder`),
  - `condition` (product filters for the block),
  - `similarProductRules`,
  - `frequentlyOrderedConfig` (for the "frequently ordered together" block: `timeWindow: 'day' | 'week' | 'month' | 'quarter'`, `limit`, `minimumCoOrders`, `fallbackToPopular`),
  - `sliderDelay`, `sliderDelayType`.
- **Recommendation block endpoints** (`content-blocks.controller.ts`, all under `UserCommonGuard`):
  - `GET /api/content/blocks/:marker/trending`
  - `GET /api/content/blocks/:marker/recently-viewed`
  - `GET /api/content/blocks/:marker/repeat-purchase`
  - `GET /api/content/blocks/:marker/personal-recommendations`
  - `GET /api/content/blocks/:marker/cart-complement`
  - `GET /api/content/blocks/:marker/cart-similar`
  - `GET /api/content/blocks/:marker/wishlist-similar`

  For an unauthenticated guest without enough signal, these endpoints return `200 OK { items: [], total: 0 }` (not `401`) so the storefront can render an empty section gracefully. Backed by the consumers in `cms/src/modules/user-activity/consumers/` (see [examples/18](./examples/18-user-activity-cart-wishlist.md)).

**Do not create:** a separate table for a "slider block" or a "trending block". These are `BlockEntity` rows with the matching `general_type_id`. If you need a **new block class** with fundamentally different behavior — add a value to the `GeneralType` enum + a seed in `general_types`, not a separate table.

### 31. Third-party modules ("plugins" in the CMS)

- **Entity:** `ModuleEntity` (`modules`). Type: `ModuleType` (`SYSTEM` / `CUSTOM`).
- **Binding to general types:** M2M `module_general_types_mn` — which `general_types` this module serves.
- **Binding to attribute set types:** M2M `module_attribute_set_types_mn`.
- **Deploy state:** `task_id`, `last_checked_status`, `status_transition` (the `StatusTransition` enum).
- **Module config:** `config jsonb`, `used_templates` (jsonb id array).

**Example:** [examples/19-third-party-modules.md](./examples/19-third-party-modules.md)

### 32. Named picker / curated list of mixed entities (a "facet" / "saved selection")

If the task is: "admin needs to assemble a named list of pages and products with custom ordering", "give the storefront a configurable left-side filter widget", "let me bundle a set of attribute values for the catalog page" — **use the Filters module**, not a fresh table.

- **Head entity:** `FilterEntity` (`filters` table). `identifier` (UNIQUE — public marker), `localizeInfos`, `scopeTypes jsonb` — the soft-constraint set of allowed `object_type` values; switching the scope does NOT delete out-of-scope items (UI badges them).
- **Polymorphic items:** `FilterItemEntity` (`filter_items_mn`) — a `(object_type, object_id)` pair, **no FK** (orphan items are filtered out in the SQL via LEFT JOIN). `object_type` is one of `FilterScopeType`: `page` / `product` / `admin` / `attribute` / `discount` / `personal-discount` / `bonus` / `payment-method`. For `attribute` items the trio `attributeValueId` / `attributeIdentifier` / `valueText` carries the value (the new `attribute_identifier` column lands schema lookups directly; legacy NULL rows fall back to a heuristic resolver).
- **Gotcha — no uniqueness on `(filter_id, object_type, object_id)`:** the table has no UNIQUE constraint on the polymorphic triple, so the same object can be attached to one filter twice. If your task is "add object once, idempotently" or "list items distinct by source entity", do the deduplication in the service layer (e.g. `WHERE NOT EXISTS` on insert, or `GROUP BY` on read) — the DB will not enforce it for you.
- **Free-form items:** `FilterCustomItemEntity` (`filter_custom_items_mn`) — localized title + scalar `value` (URL / identifier / text). Shares one lexorank pool with `filter_items_mn` per filter.
- **Ordering:** lexorank in the `positions` table via `CommonPositionService` (`object_category_id = filterId`). Both filter items and custom items live in the same lexorank pool.
- **Reads:** `BaseFiltersService.getAllDataQuery` — two SQL branches (admin flat / content with polymorphic resolution via LEFT JOINs to `pages` / `products` / `admins` / `attributes_sets` / `discounts` / `payment_accounts` / `positions`). No N+1. Full join map in [`cms/.claude/docs/filters.md`](../../cms/.claude/docs/filters.md).
- **Public endpoint (anonymous, no `user_permissions` gate):** `GET /api/content/filters/marker/:marker?langCode=`.
- **Admin endpoints:** `admin-filters.controller.ts` (extends `ContentFiltersController`) — full CRUD, batch `POST /api/admin/filters/:id/items`, drag-drop position, `GET /api/admin/filters/marker-validation/:marker` (uniqueness check). Journaled. The inherited public `GET /api/admin/filters/marker/:marker` is intentionally blocked (405 `MethodNotAllowedException`).
- **Companion:** `GET /api/admin/index-attributes/unique-values` — DISTINCT values for the attribute picker (`IndexAttributeValuesService`).

**Detailed reference:** [`cms/.claude/docs/filters.md`](../../cms/.claude/docs/filters.md) — every JOIN, every drag-drop edge case, the attribute display resolver. Read first for any filter-listing / filter-item / filter-position task.

**Do not create:** a `saved_selections` / `facet_definitions` / `custom_lists` table — that's what Filters are.

### 33. Logging public Content API errors (admin "Content API errors" tab)

- **Do NOT log inline** in business code. There is a global exception filter on the content app — `shared/exception-filters/content-api-error-logger.filter.ts` — that catches every 4xx/5xx and publishes a sanitized job to the `content-api-errors` Bull queue.
- **Persistence:** `ContentApiErrorEntity` (`content_api_errors` table, `bigint` PK). Indices: `created_at DESC`, `status_code`, `path`, composite `(method, path)`.
- **Consumer:** `consumers/content-api-error.consumer.ts` — writes the row without blocking the request path. `error_stack` is stored only for 5xx; bodies and query are sanitized via `utils/sanitize-request-body.util.ts` and truncated to fit caps (path 500, body 2KB, stack 8KB).
- **Admin UI tab:** `controllers/admin-content-api-errors.controller.ts` (`AdminContentApiErrorsService`) — list / detail / cleanup.
- **Sibling Journal subsystems** added in the same wave: `admin-content-api-stats.controller.ts` + `ContentApiStatsService` (request counts/timings aggregated per route and period from `content-api-period.enum.ts`, with the route list supplied by `ContentApiRoutesRegistryService` — which on `onModuleInit` reads the static `src/modules/journal/content-routes.generated.json` via `fs.readFileSync`; the legacy `scripts/generate-content-routes.ts` that originally produced that JSON was deleted in develop, so the file is now a checked-in snapshot rather than build-time output), and `admin-journal-traffic.controller.ts` + `AdminJournalTrafficService` (traffic dashboard backed by `PrometheusQueryService`).

**Do not create:** a `content_error_logs` / `api_5xx_log` table by hand — the filter + queue + entity above is the system for it.

---

## What to do if no case fit

1. Check [`when-not-to-create-tables.md`](./when-not-to-create-tables.md) — it lists "instead of a new table, do this".
2. If you still need a new entity — open [`entities-catalog.md`](./entities-catalog.md) and [`modules-catalog.md`](./modules-catalog.md) and make sure there really isn't a similar one.
3. If you're sure — discuss the structure with the user through the analyst; don't just do it.
