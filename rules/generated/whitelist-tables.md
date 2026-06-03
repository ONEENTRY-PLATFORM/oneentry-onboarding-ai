# Whitelist tables — 36 tables for Blueprint

> **This file is partially auto-generated** via `agents_datasets/scripts/gen-rules.py`. The table list and NOT NULL columns are regenerated. FK descriptions and text comments may be edited manually (see hand-written sections below).
>
> Generation date: 2026-06-02.

## 36 allowed tables

```
attributes_sets
templates
template_previews
pages
products
products_pages_mn
blocks
block_pages_mn
block_products_mn
product_blocks_mn
forms
form_module_config
form_data
user_groups
users_auth_providers
user_permissions
user_group_permissions_mn
collections
collection_rows
product_statuses
order_statuses
orders_storage
orders_storage_payment_accounts
product_relations_templates
slides
menus
menu_pages_mn
menu_custom_items_mn
discounts
discount_conditions
discount_coupons
payment_status_map
page_errors
filters
filter_items_mn
payment_accounts
```

## NOT NULL columns (without default) per-table

Extracted from `@Column(..., nullable: false, ...)` without `default:` in the entity.

### `attributes_sets`
NOT NULL: `type_id`

### `templates`
NOT NULL: _(no explicit not-null without default)_

### `template_previews`
NOT NULL: _(no explicit not-null without default)_

### `pages`
NOT NULL: `rating`

### `products`
NOT NULL: `rating`

### `products_pages_mn`
NOT NULL: `position_id`

### `blocks`
NOT NULL: `general_type_id`

### `block_pages_mn`
NOT NULL: `position_id`

### `block_products_mn`
NOT NULL: `deleted`, `position_id`

### `product_blocks_mn`
NOT NULL: `lang_code`, `position_id`

### `forms`
NOT NULL: _(no explicit not-null without default)_

### `form_module_config`
NOT NULL: `form_id`

### `form_data`
NOT NULL: _(no explicit not-null without default)_

### `user_groups`
NOT NULL: _(no explicit not-null without default)_

### `users_auth_providers`
NOT NULL: `type`

### `user_permissions`
NOT NULL: `localize_infos`, `path`, `section`

### `user_group_permissions_mn`
NOT NULL: `group_id`, `permission_id`

### `collections`
NOT NULL: _(no explicit not-null without default)_

### `collection_rows`
NOT NULL: `collection_id`

### `product_statuses`
NOT NULL: _(no explicit not-null without default)_

### `order_statuses`
NOT NULL: `storage_id`

### `orders_storage`
NOT NULL: `general_type_id`

### `orders_storage_payment_accounts`
NOT NULL: `payment_account_id`, `storage_id`

### `product_relations_templates`
NOT NULL: `name`

### `slides`
NOT NULL: `block_id`

### `menus`
NOT NULL: _(no explicit not-null without default)_

### `menu_pages_mn`
NOT NULL: `menu_id`, `page_id`, `position_id`

### `menu_custom_items_mn`
NOT NULL: `menu_id`

### `discounts`
NOT NULL: _(no explicit not-null without default)_

### `discount_conditions`
NOT NULL: _(no explicit not-null without default)_

### `discount_coupons`
NOT NULL: _(no explicit not-null without default)_

### `payment_status_map`
NOT NULL: `order_storage_id`

### `page_errors`
NOT NULL: _(no explicit not-null without default)_

### `filters`
NOT NULL: _(no explicit not-null without default)_

### `filter_items_mn`
NOT NULL: `filter_id`, `is_range`, `object_id`

### `payment_accounts`
NOT NULL: _(no explicit not-null without default)_

## Hard FKs (hand-written section — maintain on changes)

Source: `cms/src/modules/import/sevices/blueprint/fk-graph.ts`. This section is **not regenerated automatically** — update by hand if the FK map changes.

```
templates:                       attribute_set_id -> attributes_sets
pages:                           attribute_set_id, template_id, parent_id (self)
blocks:                          attribute_set_id, template_id
products:                        attribute_set_id, template_id, status_id
products_pages_mn:               pageId, productId          <- camelCase!
block_pages_mn:                  page_id, block_id
block_products_mn:               product_id, block_id, page_id
product_blocks_mn:               product_id, block_id
forms:                           attribute_set_id, template_id
user_groups:                     attribute_set_id, parent_id (self)
users_auth_providers:            user_group_id, form_id
orders_storage:                  form_id
order_statuses:                  storage_id
orders_storage_payment_accounts: storage_id, payment_account_id
# Added 2026-05-21 — six new whitelist tables:
form_module_config:              form_id, module_id
form_data:                       form_module_id -> form_modules_mn (junction of forms↔modules; NOT directly to forms)
user_permissions:                (no outgoing FK; binds to user_groups via user_group_permissions_mn)
user_group_permissions_mn:       group_id -> user_groups, permission_id -> user_permissions
collections:                     form_id -> forms (optional, onDelete: SET NULL)
collection_rows:                 collection_id -> collections (SKIP_IF_PARENT_HAS_CHILDREN policy on re-import)
```
