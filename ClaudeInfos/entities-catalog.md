# `cms/` entity catalog

A reference for every entity class under `cms/src/**/*.entity.ts` (at the time of writing: 100+ module entity files under `cms/src/modules/**/entities/` + 3 abstract ones under `cms/src/shared/entities/`). Grouped by domain, not alphabetically: search by meaning.

The table columns for each entity:
- **Class** — class name (use this to grep).
- **File** — path relative to the repo (`cms/src/...`).
- **Table** — SQL table name.
- **Extends** — parent class (`AS` = `BaseAttributeSetsAbstractEntity`, `B` = `BaseAbstractEntity`, `BE` = typeorm's `BaseEntity`, `—` = its own `@PrimaryGeneratedColumn`).
- **Purpose** — one-line description.

> If you need details on a specific entity — open its file. This document is an index.

---

## Abstract bases

| Class | File | Purpose |
|---|---|---|
| `BaseAbstractEntity` | `shared/entities/base-abstract.entity.ts` | Base: `id`, `createdDate`, `updatedDate`, `version`, `identifier` |
| `BaseAttributeSetsAbstractEntity` | `shared/entities/base-attribute-sets.abstract.entity.ts` | + `attributesSets jsonb`, `attributeSetId` |
| `BasePositionAbstractEntity` | `shared/entities/base-position.abstract.entity.ts` | `@deprectated` (sic). Empty class, not used by any entity |

See [`data-model-core.md`](./data-model-core.md) for details.

---

## Content: pages, blocks, templates, menus

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `PageEntity` | `modules/pages/entities/page.entity.ts` | `pages` | AS | CMS page (content / catalog / error page) |
| `BlockEntity` | `modules/blocks/entities/block.entity.ts` | `blocks` | AS | Section block on a page or linked to a product |
| `BlockPageEntity` | `modules/blocks/entities/block-page.entity.ts` | `block_pages_mn` | BE | M2M: block ↔ page, +`is_nested`, +position |
| `BlockProductsEntity` | `modules/blocks/entities/block-products.entity.ts` | `block_products_mn` | BE | M2M: block ↔ specific products (for recommendation blocks) |
| `ProductBlocksEntity` | `modules/blocks/entities/product-blocks.entity.ts` | `product_blocks_mn` | BE | M2M: product ↔ the blocks of that product (reverse link) |
| `MenuEntity` | `modules/menus/entities/menu.entity.ts` | `menus` | B | A menu (e.g. the site's main menu) |
| `MenuPageEntity` | `modules/menus/entities/menu-page.entity.ts` | `menu_pages_mn` | BE | M2M: page ↔ menu, +`is_pinned`, +position |
| `MenuCustomItemEntity` | `modules/menus/entities/menu-custom-item.entity.ts` | `menu_custom_items_mn` | B | Custom ("free-form") menu item: localized title + `value` (URL/anchor/mailto/tel/relative path). `parentId` is polymorphic (no FK) — points at `pages.id` or another `menu_custom_items_mn.id`. Migrations `1880200000000` + `1880200100000`. |
| `TemplateEntity` | `modules/templates/entities/template.entity.ts` | `templates` | AS | Output template (page, product, block); type via `general_type_id` |
| `TemplatePreviewsEntity` | `modules/template-previews/entities/template-previews.entity.ts` | `template_previews` | B | Preview template with proportions (horizontal/vertical/square) |
| `MarkerEntity` | `modules/markers/entities/marker.entity.ts` | `markers` | B | A marker/tag (unique text identifier with localization) |
| `PageErrorEntity` | `modules/page-errors/entities/page-error.entity.ts` | `page_errors` | BE | Map of HTTP error codes to handler pages |

---

## Product catalog

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `ProductEntity` | `modules/products/entities/product.entity.ts` | `products` | AS | A product (any catalog entity) |
| `ProductPageEntity` | `modules/products/entities/product-page.entity.ts` | `products_pages_mn` | BE | M2M: product ↔ page (category) |
| `ProductStatusEntity` | `modules/product-status/entities/product-status.entity.ts` | `product_statuses` | B | A product status (e.g. `published`, `draft`) |
| `ProductRelationsTemplateEntity` | `modules/products/entities/product-relations-template.entity.ts` | `product_relations_templates` | B | Condition template for searching related/similar products |

---

## Attribute sets and indexing

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `AttributesSetEntity` | `modules/attributes-sets/entities/attributes-set.entity.ts` | `attributes_sets` | B | The attribute set itself: `schema jsonb`, `properties jsonb`, `type_id`, position |
| `AttributeSetTypeEntity` | `modules/attributes-sets/entities/attribute-set-type.entity.ts` | `attribute_set_types` | BE | Set type (`forProducts`, `forPages`, etc.) |
| `IndexAttributeEntity` | `modules/index-attributes-sets/entities/index-attribute.entity.ts` | `index_attributes` | B | Registry of indexed attributes: `tableName`, `identifier`, `typeId` |
| `IndexAttributeDataEntity` | `modules/index-attributes-sets/entities/index-attribute-data.entity.ts` | `index_attribute_data` | B | Denormalized values: (dataId, tableName, attributeId, langCode) → value |
| `IndexAttributeTypeEntity` | `modules/index-attributes-sets/entities/index-attribute-type.entity.ts` | `index_attribute_types` | BE | Indexed-attribute type (`AttributeType`) |
| `GeneralTypeEntity` | `modules/general-types/general-types.entity.ts` | `general_types` | BE | Enum-style table of types (`common_page`, `product_block`, `frequently_ordered_block`, …) |
| `ModuleEntity` | `modules/modules/entities/module.entity.ts` | `modules` | B | A module (system/custom). M2M with `general_types` and `attribute_set_types` |

---

## Collections

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `CollectionEntity` | `modules/collections/entities/collection.entity.ts` | `collections` | B | Collection container with `form_id` (optional) |
| `CollectionRowEntity` | `modules/collections/entities/collection-row.entity.ts` | `collection_rows` | BE | A row: `form_data jsonb`, generic ref to an entity via `entityType + entityId` |

---

## Filters (named picker / list of polymorphic items)

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `FilterEntity` | `modules/filters/entities/filter.entity.ts` | `filters` | B | A named filter (by `identifier`, UNIQUE). `localizeInfos` for the title and `scopeTypes jsonb` — the soft-constraint set of allowed `object_type` values |
| `FilterItemEntity` | `modules/filters/entities/filter-item.entity.ts` | `filter_items_mn` | BE | Polymorphic item: `(object_type, object_id)` pair, **no FK** — orphan items are filtered out in the SQL query via LEFT JOIN. `object_type` ∈ `page` / `product` / `admin` / `attribute` / `discount` / `personal-discount` / `bonus` / `payment-method` (`FilterScopeType`). For `attribute` items the column trio (`attributeValueId`, `attributeIdentifier`, `valueText`) carries the value. `parentId` is also polymorphic (no FK). Ordered via `positionId` → `PositionEntity`. **No UNIQUE on `(filter_id, object_type, object_id)`** — the same object can be attached to one filter multiple times; deduplication, if needed, is the service layer's job |
| `FilterCustomItemEntity` | `modules/filters/entities/filter-custom-item.entity.ts` | `filter_custom_items_mn` | BE | Free-form ("external") item: localized title + scalar `value` (URL/identifier/text). Shares the lexorank pool with `filter_items_mn` per filter |

> Detailed reference: [`cms/.claude/docs/filters.md`](../../cms/.claude/docs/filters.md) — single-query SQL hydration in `BaseFiltersService.getAllDataQuery`, attribute display resolver, drag-drop pipeline, and the companion `/api/admin/index-attributes/unique-values` endpoint.

---

## Forms

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `FormEntity` | `modules/forms/entities/form.entity.ts` | `forms` | AS | A form: `processingType` (db/email/script), `type: FormType`, attribute_set with fields |
| `FormDataEntity` | `modules/form-data/entities/form-data.entity.ts` | `form_data` | BE | Submitted form data: `form_data jsonb`, `user_identifier`, `entity_identifier`, `status`, `ip` |
| `FormModuleConfigEntity` | `modules/forms/entities/form-module-config.entity.ts` | `form_module_config` | BE | Configuration of the module ↔ form binding |
| `FormModuleMnEntity` | `modules/forms/entities/form-module-mn.entity.ts` | `form_modules_mn` | BE | Binding of a form instance to a specific receiver entity |
| `FormPageEntity` | `modules/forms/entities/form-page.entity.ts` | `form_pages_mn` | BE | **`@deprecated`** M2M: form ↔ page |

---

## Orders and payments

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `OrderEntity` | `modules/orders/entities/order.entity.ts` | `orders` | — | An order: `storage_id`, `user_id`, `status_id`, `payment_account_id`, `form_data jsonb`, `payment_strategy` |
| `OrderProductEntity` | `modules/orders/entities/order-product.entity.ts` | `order_products` | — | A product in an order, unique (productId, orderId, isGift) |
| `OrderStatusEntity` | `modules/orders/entities/order-status.entity.ts` | `order_statuses` | B | An order status within a storage |
| `OrderStorageEntity` | `modules/orders/entities/order-storage.entity.ts` | `orders_storage` | B | Order storage (multi-tenancy: restaurants/branches), tied to `general_type` + `form_id` |
| `OrderStoragePaymentAccountEntity` | `modules/orders/entities/order-storage-payment-account.entity.ts` | `orders_storage_payment_accounts` | — | M2M: storage ↔ payment account |
| `OrdersHistoryEntity` | `modules/orders/entities/orders-history.entity.ts` | `orders_history` | BE | Order history entry (types: `products` / `status` / `refund`) |
| `OrderRefundEntity` | `modules/orders/entities/order-refund.entity.ts` | `order_refunds` | — | Order refund |
| `OrderRefundRequestEntity` | `modules/orders/entities/order-refund-request.entity.ts` | `order_refund_requests` | — | Refund request (from the user side) |
| `PaymentAccountEntity` | `modules/payments/entities/payment-account.entity.ts` | `payment_accounts` | B | Payment provider configuration |
| `PaymentSessionEntity` | `modules/payments/entities/payment-session.entity.ts` | `payment_sessions` | B | Payment session (payment attempt), tied to an order or subscription |
| `PaymentRefundEntity` | `modules/payments/entities/payment-refund.entity.ts` | `payment_refunds` | — | Refund on the payment provider side |
| `PaymentStageEntity` | `modules/payments/entities/payment-stage.entity.ts` | `payment_stages` | — | Stages of a multi-step payment |
| `PaymentStatusMapEntity` | `modules/payments/entities/payment-status-map.entity.ts` | `payment_status_map` | B | Mapping of provider statuses to internal ones (per `order_storage_id`) |
| `PaymentParamItemEntity` | `modules/payments/entities/payment-param-item.entity.ts` | `payment_param_items` | BE | Parameters/attributes of a payment_account |

---

## Discounts and bonuses

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `DiscountEntity` | `modules/discounts/entities/discount.entity.ts` | `discounts` | AS | Discount/bonus/personal discount; `type: DiscountType` |
| `DiscountConditionEntity` | `modules/discounts/entities/discount-condition.entity.ts` | `discount_conditions` | BE | Activation conditions (by `DiscountConditionType`) |
| `DiscountCouponEntity` | `modules/discounts/entities/discount-coupon.entity.ts` | `discount_coupons` | BE | Coupons: a single discount can map to N coupons |
| `DiscountBonusEventEntity` | `modules/discounts/entities/discount-bonus-event.entity.ts` | `discount_bonus_events` | BE | Bonus accrual configuration (1:1 with a BONUS-type discount) |
| `DiscountBonusBalanceEntity` | `modules/discounts/entities/discount-bonus-balance.entity.ts` | `discount_bonus_balance` | BE | A user's bonus balance |
| `DiscountBonusTransactionEntity` | `modules/discounts/entities/discount-bonus-transaction.entity.ts` | `discount_bonus_transaction` | BE | Bonus movements (ACCRUAL/USAGE/REDUCE/EXPIRATION/REVERSAL_*) |
| `DiscountBonusUsageDetailEntity` | `modules/discounts/entities/discount-bonus-usage-detail.entity.ts` | `discount_bonus_usage_detail` | BE | Detail of a specific USAGE transaction |
| `DiscountSettingsEntity` | `modules/discounts/entities/discount-settings.entity.ts` | `discount_settings` | B | Global discount settings (`allowStacking`, `maxDiscountValue`, gift refund policy) |

---

## Users and admins

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `AdminEntity` | `modules/admins/entities/admin.entity.ts` | `admins` | AS | An admin: `login`, `email`, `passwordHash`, `permissions jsonb`, `selectedLanguage`, `isDeveloper` |
| `UpdatedPermissionsLogEntity` | `modules/admins/entities/updated-permissions-log.entity.ts` | `updated_permissions_log` | BE | Simple permission-change log (`adminId`) |
| `AdminSessionEntity` | `modules/auth/entities/admin-session.entity.ts` | `admin_sessions` | BE | Active admin session |
| `RefreshTokenEntity` | `modules/auth/entities/refresh-token.entity.ts` | `refresh_tokens` | BE | Refresh token for a user/admin |
| `UserEntity` | `modules/users/entities/user.entity.ts` | `users` | B (+ manual `attribute_set_id` and `attributes_sets`) | An end user of the site |
| `UserActionEntity` | `modules/users/entities/user-action.entity.ts` | `user_actions` | — | User action log (`UserActionType`) |
| `UserCodeEntity` | `modules/users/entities/user-code.entity.ts` | `user_codes` | BE | Activation/recovery codes for a user |
| `UserSessionEntity` | `modules/users/entities/user-session.entity.ts` | `user_sessions` | BE | Active user session (+ device fingerprint) |
| `UsersAuthProviderEntity` | `modules/users/entities/users-auth-provider.entity.ts` | `users_auth_providers` | B | Auth provider (email / phone / OAuth / etc.) with localization and `config` |
| `UserGroupEntity` | `modules/user-groups/entities/user-group.entity.ts` | `user_groups` | AS | A user group (hierarchy: parent_id/depth/category_path) |
| `UserGroupMnEntity` | `modules/user-groups/entities/user-group-mn.entity.ts` | `user_groups_mn` | BE | M2M: user ↔ group |
| `UserPermissionEntity` | `modules/user-permissions/entities/user-permission.entity.ts` | `user_permissions` | BE | Permission for non-admins (typed as `APISectionTypeEnum`) |
| `UserGroupPermissionMnEntity` | `modules/user-permissions/entities/user-group-permission-mn.entity.ts` | `user_group_permissions_mn` | BE | M2M: group ↔ permission |

---

## Localization

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `LocaleEntity` | `modules/locales/entities/locale.entity.ts` | `locales` | BE | Active interface locales (`code: en_US`, `shortCode: en`, `isActive`) |
| `LanguageEntity` | `modules/multilanguage/entities/language.entity.ts` | `languages` | BE | Simple language reference (`name`, `code`) |
| `LocalesUsageEntity` | `modules/locales-usage/entities/locales-usage.entity.ts` | `content_locales_usage` | — | Tracking "which locales are used where" |

---

## Subscriptions (billing)

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `SubscriptionEntity` | `modules/subscriptions/entities/subscription.entity.ts` | `subscriptions` | — | A subscription plan |
| `UserSubscriptionEntity` | `modules/subscriptions/entities/user-subscription.entity.ts` | `user_subscriptions` | — | A specific user subscription with `UserSubscriptionStatus` |
| `MidtransCustomerEntity` | `modules/subscriptions/entities/midtrans-customer.entity.ts` | `midtrans_customers` | — | External Midtrans customer id |
| `StripeCustomerEntity` | `modules/subscriptions/entities/stripe-customer.entity.ts` | `stripe_customers` | — | External Stripe customer id |

---

## Events and notifications

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `EventEntity` | `modules/events/entities/event.entity.ts` | `events` | AS | Event configuration: `type: EventType`, `actions jsonb` (isPush/isEmail/isWS/isWorkflows), `mailing jsonb` |
| `EventSubscriptionEntity` | `modules/events/entities/event-subscription.entity.ts` | `event_subscription` | — | Subscription user ↔ event ↔ product |
| `EventEmailSettingsEntity` | `modules/events/entities/event-email-settings.entity.ts` | `event_email_settings` | — | Sender for email mailings |
| `FirebaseCredentialsEntity` | `modules/events/entities/firebase-credentials.entity.ts` | `firebase_credentials` | — | Firebase private key for push |

---

## Journal and versions

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `JournalRecordEntity` | `modules/journal/entities/journal-record.entity.ts` | `journal_records` | BE | Audit row: `module_name`, `entity_id`, `delta jsonb`, `action`, `journaling_event`, `result`, `admin` |
| `ContentApiErrorEntity` | `modules/journal/entities/content-api-error.entity.ts` | `content_api_errors` | BE | Content API 4xx/5xx error log. Written async via Bull queue `content-api-errors` by a global exception filter; surfaced by the "Content API errors" Journal tab. `bigint` PK, 4 indices (`created_at DESC`, `status_code`, `path`, composite `(method, path)`). `request_query` jsonb, sanitized; `error_stack` only for 5xx. Migration `1880100000000`. |
| `EntityVersionEntity` | `modules/entity-versions/entities/entity-version.entity.ts` | `entity_versions` | BE | Entity version snapshot: `entity_name`, `entity_id`, `version`, `action`, `data jsonb`, `admin_id` |

---

## Catalog import

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `CatalogImportTemplateEntity` | `modules/import/entities/catalog-import-template.entity.ts` | `catalog_import_templates` | B | Import template (mapping of Excel/CSV columns ↔ attributes) |
| `CatalogImportHistoryEntity` | `modules/import/entities/catalog-import-history.entity.ts` | `catalog_import_history` | — | Import log (`ImportType`) |

---

## User activity

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `UserActivityEventEntity` | `modules/user-activity/entities/user-activity-event.entity.ts` | `user_activity_events` | — | Activity event (product/category view, add-to-cart, search, rating, purchase). BIGSERIAL id. Guest or user |
| `CartItemEntity` | `modules/user-activity/entities/cart-item.entity.ts` | `cart_items` | — | One row per `(userId, productId)` cart position. `qty`, `addedAt`. BIGSERIAL id, `UNIQUE(user_id, product_id)`, FK CASCADE on `users.id` and `products.id`. Language-agnostic |
| `WishlistItemEntity` | `modules/user-activity/entities/wishlist-item.entity.ts` | `wishlist_items` | — | One row per `(userId, productId)` wishlist position. No `qty`. BIGSERIAL id, `UNIQUE(user_id, product_id)`, FK CASCADE on `users.id` and `products.id`. Language-agnostic |
| `UserRecommendationEntity` | `modules/user-activity/entities/user-recommendation.entity.ts` | `user_recommendations` | — | Per-user precomputed recommendations populated by `RecommendationConsumer` |
| `UserSegmentEntity` | `modules/user-activity/entities/user-segment.entity.ts` | `user_segments` | — | RFM segments per user (populated by `SegmentsRecomputeConsumer`) |
| `TriggeredCommunicationLogEntity` | `modules/user-activity/entities/triggered-communication-log.entity.ts` | `triggered_communication_logs` | — | Log of cart-abandonment / repeat-purchase / dormant-reactivation notifications dispatched to `notice-service` |

---

## Positions (sort)

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `PositionEntity` | `modules/position/entities/position.entity.ts` | `positions` | — | Generic object position in sort order: `objectType + objectId`, `position` (lexorank), `isLocked` |

---

## System / service

| Class | File | Table | Extends | Purpose |
|---|---|---|---|---|
| `SystemEntity` | `modules/system/entities/system.entity.ts` | `system` | BE | System settings (`langInterface`) |
| `AppCertEntity` | `modules/system/entities/app-cert.entity.ts` | `app_certs` | BE | Certificates for admin apps |
| `AppTokenEntity` | `modules/system/entities/app-token.entity.ts` | `app_tokens` | BE | App tokens (content API) |
| `BackupEntity` | `modules/backups/backup.entity.ts` | `backups` | BE | Entity backup (`type: BackupEntityType`, `entityId`, `data jsonb`) |
| `ImmutableSettingsEntity` | `modules/immutable-settings/entities/immutable-settings.entity.ts` | `immutable_settings` | BE | Hard limits (`maxRequestsCountForAdmin`, `availableDiskSpace`, `maxEntityVersion`) |
| `UsageImmutableSettingsEntity` | `modules/immutable-settings/entities/usage-immutable-settings.entity.ts` | `usage_immutable_settings` | — | Current usage (to compare against limits) |
| `SettingsGeneralEntity` | `modules/settings-general/entities/settings-general.entity.ts` | `settings_general` | B | General app settings (data jsonb) |
| `WorkflowsStorageEntity` | `modules/workflows/core/entities/workflows-storage.entity.ts` | `workflows_storage` | BE | Key/value storage for workflows (arbitrary process state) |

---

## Completeness check

The list above is compiled from a glob over `cms/src/**/*.entity.ts` (sorted): 100+ module entity files under `cms/src/modules/**/entities/` (106 as of 2026-05-29) + 3 abstract ones under `cms/src/shared/entities/`. If you suspect an entity is missing — `find cms/src -name "*.entity.ts" -type f | sort`. The 2026-05-22 cart/wishlist refactor added `CartItemEntity`, `WishlistItemEntity`, `UserRecommendationEntity`, `UserSegmentEntity`, `TriggeredCommunicationLogEntity` under `modules/user-activity/entities/`. The 2026-05-26/29 wave added the **Filters** module (`FilterEntity`, `FilterItemEntity`, `FilterCustomItemEntity`), `MenuCustomItemEntity` under `modules/menus/entities/`, and `ContentApiErrorEntity` under `modules/journal/entities/`.

### Known code "oddities" (recorded here so AI doesn't try to "fix" them)

- `BasePositionAbstractEntity` is marked `@deprectated` (typo in the code, left as-is). Used by no entity.
- The file `cms/src/modules/journal/jounal.service.ts` has a misspelled name (`jounal` instead of `journal`). It is imported under that path — do not rename.
- `BlockEntity.blockProducts` is typed through `ProductBlocksEntity` and `BlockEntity.productBlocks` is typed through `BlockProductsEntity` — the relation names are swapped relative to the types. **This is the actual state of the code, not a bug.**
- `FormPageEntity` is `@deprecated`.
- `BackupEntity` doesn't use `BaseAbstractEntity` (no version/identifier) but its own minimal set.

### "orphan?" marker (potentially unused)

Based on grep through problem cases, `BasePositionAbstractEntity` is the only obvious orphan. The rest of the entities are imported in their respective modules. For a robust check use: `grep -rn "<EntityName>" cms/src --include="*.ts" -l | wc -l` — should be > 1 (the file itself + consumers).

---

## Related documents

- [`data-model-core.md`](./data-model-core.md) — base abstract classes and jsonb structures.
- [`modules-catalog.md`](./modules-catalog.md) — which modules use which entities.
- [`use-cases.md`](./use-cases.md) — which tasks are solved by which entity set.
