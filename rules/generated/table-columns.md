# Table columns — registry of allowed columns for each whitelist table

> **This file is auto-generated** via `agents_datasets/scripts/gen-rules.py`. Do not edit by hand — changes will be overwritten on the next regeneration.
>
> Generation date: 2026-06-02.
>
> Source of truth: `cms/src/modules/{*}/entities/*.entity.ts`.

## Why this file exists

The OneEntry loader performs a direct `INSERT INTO <table> (col1, col2, ...) VALUES (...)`. If a blueprint row references **a column that does not exist in the entity**, the loader fails with **HTTP 500** error `column "X" of relation "Y" does not exist`.

**Builder MUST** use **only columns from the registry** for each row. **Validator S27** checks this automatically.

## Inherited columns

Most tables extend `BaseAbstractEntity` (or `BaseAttributeSetsAbstractEntity`). Inherited columns are **present everywhere**:

**`BaseAbstractEntity`:** `id`, `created_date`, `updated_date`, `version`, `identifier`

**`BaseAttributeSetsAbstractEntity`** (extends `BaseAbstractEntity`): + `attributes_sets` (jsonb), `attribute_set_id` (int)

## Column registry per-table

### `attributes_sets`

Columns: `created_date`, `hash`, `id`, `identifier`, `is_visible`, `position_id`, `properties`, `schema`, `title`, `type_id`, `updated_date`, `version`

### `templates`

Columns: `attribute_set_id`, `attributes_sets`, `created_date`, `general_type_id`, `id`, `identifier`, `position_id`, `title`, `updated_date`, `version`

### `template_previews`

Columns: `created_date`, `id`, `identifier`, `position_id`, `proportions`, `title`, `updated_date`, `version`

### `pages`

Columns: `attribute_set_id`, `attributes_sets`, `category_path`, `children_count`, `config`, `created_date`, `depth`, `general_type_id`, `id`, `identifier`, `is_edit`, `is_visible`, `localize_infos`, `page_url`, `parent_id`, `position_id`, `rating`, `show_children`, `template_id`, `updated_date`, `user_edit_id`, `version`

### `products`

Columns: `attribute_key_value`, `attribute_schema_hash`, `attribute_set_id`, `attributes_sets`, `created_date`, `file_upload_value`, `id`, `identifier`, `import_id`, `is_edit`, `is_visible`, `localize_infos`, `rating`, `short_desc_template_id`, `status_id`, `template_id`, `updated_date`, `user_edit_id`, `version`

### `products_pages_mn`

Columns: `category_path`, `id`, `pageId`, `position_id`, `productId`

### `blocks`

Columns: `attribute_set_id`, `attributes_sets`, `created_date`, `custom_settings`, `general_type_id`, `id`, `identifier`, `is_visible`, `localize_infos`, `product_page_urls`, `template_id`, `updated_date`, `version`

### `block_pages_mn`

Columns: `block_id`, `id`, `is_nested`, `page_id`, `position_id`

### `block_products_mn`

Columns: `block_id`, `deleted`, `id`, `is_locked`, `page_id`, `position_id`, `product_id`

### `product_blocks_mn`

Columns: `block_id`, `id`, `is_visible`, `lang_code`, `position_id`, `product_id`

### `forms`

Columns: `attribute_set_id`, `attributes_sets`, `created_date`, `id`, `identifier`, `localize_infos`, `processing_type`, `selected_attribute_markers`, `template_id`, `type`, `updated_date`, `version`

### `form_module_config`

Columns: `allow_half_ratings`, `allow_rerating`, `comment_only_user_data`, `entity_identifiers`, `form_id`, `id`, `is_anonymous`, `is_closed`, `is_global`, `is_moderate`, `is_rating`, `max_rating_scale`, `module_id`, `rating_calculation`, `view_only_user_data`

### `form_data`

Columns: `entity_identifier`, `fingerprint`, `form_data`, `form_identifier`, `form_module_id`, `id`, `ip`, `is_user_admin`, `parent_id`, `status`, `time`, `user_identifier`

### `user_groups`

Columns: `attribute_set_id`, `attributes_sets`, `children_count`, `created_date`, `depth`, `id`, `identifier`, `is_visible`, `localize_infos`, `parent_id`, `show_children`, `updated_date`, `version`

### `users_auth_providers`

Columns: `config`, `created_date`, `form_id`, `id`, `identifier`, `is_active`, `is_check_code`, `localize_infos`, `type`, `updated_date`, `user_group_id`, `version`

### `user_permissions`

Columns: `id`, `localize_infos`, `path`, `rules`, `section`

### `user_group_permissions_mn`

Columns: `group_id`, `id`, `permission_id`

### `collections`

Columns: `created_date`, `form_id`, `id`, `identifier`, `localize_infos`, `selected_attribute_markers`, `updated_date`, `version`

### `collection_rows`

Columns: `collection_id`, `entity_id`, `entity_type`, `form_data`, `id`, `lang_code`

### `product_statuses`

Columns: `created_date`, `id`, `identifier`, `is_default`, `localize_infos`, `position_id`, `updated_date`, `version`

### `order_statuses`

Columns: `created_date`, `id`, `identifier`, `is_default`, `localize_infos`, `position_id`, `storage_id`, `updated_date`, `version`

### `orders_storage`

Columns: `created_date`, `form_id`, `general_type_id`, `id`, `identifier`, `localize_infos`, `price_expiration`, `selected_attribute_markers`, `updated_date`, `version`

### `orders_storage_payment_accounts`

Columns: `id`, `payment_account_id`, `storage_id`

### `product_relations_templates`

Columns: `conditions`, `created_date`, `id`, `identifier`, `is_active`, `name`, `updated_date`, `version`

### `slides`

Columns: `block_id`, `created_date`, `id`, `identifier`, `is_visible`, `parent_id`, `position_id`, `time_interval`, `updated_date`, `version`

### `menus`

Columns: `created_date`, `id`, `identifier`, `localize_infos`, `updated_date`, `version`

### `menu_pages_mn`

Columns: `created_date`, `id`, `identifier`, `is_pinned`, `menu_id`, `page_id`, `parent_id`, `position_id`, `updated_date`, `version`

### `menu_custom_items_mn`

Columns: `created_date`, `id`, `identifier`, `localize_infos`, `menu_id`, `parent_id`, `position_id`, `updated_date`, `value`, `version`

### `discounts`

Columns: `condition_logic`, `created_date`, `discount_value`, `end_date`, `exclusions`, `gifts`, `gifts_replace_cart_items`, `id`, `identifier`, `localize_infos`, `position_id`, `selected_attribute_markers`, `start_date`, `type`, `updated_date`, `user_exclusions`, `user_groups`, `version`

### `discount_conditions`

Columns: `condition_type`, `created_date`, `discount_id`, `entity_ids`, `id`, `identifier`, `updated_date`, `value`, `version`

### `discount_coupons`

Columns: `code`, `created_date`, `discount_id`, `id`, `identifier`, `is_reusable`, `is_used`, `order_id`, `updated_date`, `used_at`, `version`

### `payment_status_map`

Columns: `created_date`, `id`, `identifier`, `order_storage_id`, `status_map`, `updated_date`, `version`

### `page_errors`

Columns: `created_date`, `id`, `identifier`, `page_id`, `updated_date`, `version`

### `filters`

Columns: `created_date`, `id`, `identifier`, `localize_infos`, `updated_date`, `version`

### `filter_items_mn`

Columns: `allowed_product_status_ids`, `attribute_identifier`, `attribute_value_id`, `created_date`, `filter_id`, `id`, `identifier`, `is_range`, `object_id`, `object_type`, `parent_id`, `position_id`, `range_from`, `range_to`, `updated_date`, `value_text`, `version`

### `payment_accounts`

Columns: `created_date`, `id`, `identifier`, `is_visible`, `localize_infos`, `settings`, `test_mode`, `test_settings`, `type`, `updated_date`, `version`

## Which tables have `localize_infos`

**PRESENT:** `blocks`, `collections`, `discounts`, `filters`, `forms`, `menu_custom_items_mn`, `menus`, `order_statuses`, `orders_storage`, `pages`, `payment_accounts`, `product_statuses`, `products`, `user_groups`, `user_permissions`, `users_auth_providers`

**ABSENT:** `attributes_sets`, `block_pages_mn`, `block_products_mn`, `collection_rows`, `discount_conditions`, `discount_coupons`, `filter_items_mn`, `form_data`, `form_module_config`, `menu_pages_mn`, `orders_storage_payment_accounts`, `page_errors`, `payment_status_map`, `product_blocks_mn`, `product_relations_templates`, `products_pages_mn`, `slides`, `template_previews`, `templates`, `user_group_permissions_mn`

WARNING: if the builder put `localize_infos` into a table from the "ABSENT" list — HTTP 500 will follow. Most common mistakes:
- `attributes_sets` with `localize_infos` — it only has a flat `title` (string). Name localization is done via `schema.<key>.localizeInfos` inside schema fields.
- `templates`, `template_previews`, `product_relations_templates` — also only a flat `title` or `name`.
- mn-tables — no localization at all.

## What the builder must do

1. For each row use **only columns from the corresponding registry section**.
2. Do not add `localize_infos` to `attributes_sets` / `templates` / `template_previews` / `product_relations_templates`.
3. Do not add `is_visible` or other fields if they are not in the entity.

## What the validator (S27) must do

```python
import re
allowed = {}
text = open('agents_datasets/rules/table-columns.md').read()
for m in re.finditer(r"### `([a-z_]+)`\n\nColumns: ([^\n]+)", text):
    table = m.group(1)
    cols = re.findall(r"`([a-z_]+)`", m.group(2))
    allowed[table] = set(cols)

for tname, rows in tables.items():
    if tname not in allowed: continue
    for i, row in enumerate(rows):
        extra = set(row.keys()) - allowed[tname]
        if extra:
            errors.append(f"S27: {tname}[{i}] uses unknown columns {sorted(extra)}. "
                          f"Will fail with HTTP 500. See rules/table-columns.md")
```

S27 is an **ERROR**, not a warning, because the blueprint fails with HTTP 500.
