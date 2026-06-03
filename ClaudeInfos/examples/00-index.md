# `agents_datasets/ClaudeInfos/examples/` — practical examples of OneEntry entity usage

This folder complements [`use-cases.md`](../use-cases.md). `use-cases.md` answers "what to use", these files answer "**how exactly, what jsonb to put, which admin endpoint to hit, what happens in Bull/WS/Journal**".

Each file is one scenario with real data structure (5-10 attributes in `attribute_set`, localization in 2 languages), real endpoints from `admin-*.controller.ts`, real Bull jobs from `BULL_QUEUES`/`BULL_CONSUMERS`. **All names are grep-validated** against `cms/src/`.

Focus is **admin API** for backend development. UI/storefront/developer/content API are not described.

## File map

| # | File | Scenario | Highlights |
|---|---|---|---|
| 01 | [`01-catalog-product.md`](./01-catalog-product.md) | Product catalog (e-commerce, marketplace, B2B) | `products` + `pages` (`catalog_page`) + Bull `product-elastic` + y-websocket CRDT |
| 02 | [`02-content-page.md`](./02-content-page.md) | Content page: blog, news, landings, vacancies | `pages` (`common_page`) + `blocks` + `block_pages_mn` + `templates` |
| 03 | [`03-form-submission.md`](./03-form-submission.md) | Submission form: contact, registration, application, rating | `forms` + `form_data` + Bull `submit-form-data` → events |
| 04 | [`04-order-flow.md`](./04-order-flow.md) | Order: cart → checkout → payment → delivery | `orders_storage` + `orders` + `order_products` + `order_statuses` + Bull `change-order-status` |
| 05 | [`05-discount-promo.md`](./05-discount-promo.md) | Discounts, coupons, bonuses, personal promotions | `discounts` (3 types) + `discount_conditions` + `discount_coupons` + Bull `discountStart/discountEnd/bonusAccrual/bonusExpiration` |
| 06 | [`06-event-notification.md`](./06-event-notification.md) | Email/push/WS/workflow on trigger | `events` + Bull `events` (12+ consumers) + RabbitMQ `exchange-message`/`message-key` → `notice-service` |
| 07 | [`07-import-catalog.md`](./07-import-catalog.md) | Catalog/users/orders import from Excel/CSV/XML/JSON/SQL | `/import/from-blueprint` + `catalog_import_history` + RabbitMQ `exchange-import`/`websocket` ← `import-backend` |
| 08 | [`08-users-and-groups.md`](./08-users-and-groups.md) | End users, groups, permissions for storefront | `users` + `user_groups` + `user_groups_mn` + `user_permissions` + Bull `change-user-attribute` |
| 09 | [`09-collections.md`](./09-collections.md) | Simple dictionaries: FAQ, cities, contacts, partners | `collections` + `collection_rows` (no Bull, no WS, no attribute_set) |
| 10 | [`10-extend-attribute-set.md`](./10-extend-attribute-set.md) | The main one — extending `attribute_set` (add field without migration) | `PUT /attributes-sets/:id/schema` + Bull `'attributes-sets'` + WS `attributesSetsChanging` + `information_schema` whitelist |
| 11 | [`11-templates-and-previews.md`](./11-templates-and-previews.md) | Templates and previews for displaying products/pages/blocks | `templates` + `template_previews` (`proportions jsonb`) + Bull `preview` (`refresh-preview`, `attribute-set-preview`) |
| 12 | [`12-payments-and-refunds.md`](./12-payments-and-refunds.md) | Payment accounts, payment sessions, refunds, status mapping | `payment_accounts` (Stripe/YooKassa/Midtrans/Custom) + `payment_sessions` + `payment_refunds` + `payment_stages` + `payment_status_map` |
| 13 | [`13-menus-and-markers.md`](./13-menus-and-markers.md) | Site menus and universal markers | `menus` + `menu_pages_mn` (hierarchy via `parent_id`) + `MarkerEntity` vs schema markers (`isPrice`, `isSku`, ...) |
| 14 | [`14-locales-and-i18n.md`](./14-locales-and-i18n.md) | UI locales, language dictionary, usage tracking | `LocaleEntity` (`locales`) vs `LanguageEntity` (`languages`) vs `LocalesUsageEntity` (`content_locales_usage`) + `TrackLocaleUsageInterceptor` |
| 15 | [`15-file-upload-pipeline.md`](./15-file-upload-pipeline.md) | Upload/delete/copy files to S3/Minio + previews | `POST /files` + Bull `files` (`delete`/`copy`) + Bull `preview` (`refresh-preview`/`attribute-set-preview`) + `file_upload_value jsonb` |
| 16 | [`16-index-attributes-search.md`](./16-index-attributes-search.md) | Denormalized attribute index for filters and search | `index_attributes` + `index_attribute_data` + Bull `index-data` (`index`/`index-all`) + WS `indexData`/`indexHealth` + EventEmitter2 `product.price-updated` |
| 17 | [`17-subscriptions-billing.md`](./17-subscriptions-billing.md) | Subscriptions and billing via Stripe/Midtrans | `subscriptions` + `user_subscriptions` (`UserSubscriptionStatus`) + `stripe_customers` + `midtrans_customers` + `payment_sessions.subscription_id` |
| 18 | [`18-user-activity-cart-wishlist.md`](./18-user-activity-cart-wishlist.md) | User activity: cart, wishlist, recently viewed, recommendation blocks, activity events | `cart_items` + `wishlist_items` (normalized, FK CASCADE) + `user_activity_events` + Redis (`cart:guest:*` TTL 30d, `wishlist:guest:*` TTL 90d) + Bull `user-activity` (7 implemented consumers) + `X-Guest-Id` header for guests |
| 19 | [`19-third-party-modules.md`](./19-third-party-modules.md) | Third-party modules as "plugins": upload, deploy, suspend/resume | `modules` (`type=CUSTOM`) + M2M `module_general_types_mn`/`module_attribute_set_types_mn` + `task_id` + `statusTransition` + `cms_provisioner` |

## How to read

1. **Start with [`10-extend-attribute-set.md`](./10-extend-attribute-set.md)** if you're not familiar with the attribute model — it's the foundation.
2. **Open `[NN]-*.md` that matches the task** — it has a full jsonb example, admin endpoints, what happens in Bull/WS, the antipattern.
3. **Cross-reference [`../use-cases.md`](../use-cases.md)** if your scenario isn't in the top 10.
4. **Cross-reference [`../entities-catalog.md`](../entities-catalog.md)** if you need entity class details (100+ entities).

## Zero hallucination principle

At the top of each file is the comment `<!-- audit: 5/5 (YYYY-MM-DD) endpoints[...], fields[...], queues[...], ws[...], fk[...] -->`. This means 5 names from the text (endpoint, field, queue, WS channel, FK) are confirmed by grep against the OneEntry Platform source. If anything changes — re-audit.

When working with these files **still verify with grep** before use — the repository moves, the doc may lag. Check command:

```bash
grep -rn "<name>" "<path-to-oneentry-platform-source>" --include="*.ts"
```

## What is NOT described

- Admin UI and frontend (`cms_frontend/`).
- Developer / content / public API (only admin).
- Internals of `notice-service` (only upstream connection via RabbitMQ).
- Internals of `import-backend` (only connection via `exchange-import`).
- Legacy repos.

See the root `CLAUDE.md` and `agents_datasets/ClaudeInfos/00-index.md` for general context.
