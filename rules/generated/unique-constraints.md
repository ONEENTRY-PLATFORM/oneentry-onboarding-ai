# UNIQUE constraints — registry and deduplication rules

> **This file is auto-generated** via `agents_datasets/scripts/gen-rules.py`. Do not edit by hand.
>
> Generation date: 2026-06-02.
>
> Source of truth: the `@Unique([...])` decorator in `cms/src/modules/{*}/entities/*.entity.ts`.

## Why this file exists

A PostgreSQL UNIQUE constraint fires on INSERT when attempting to insert a second row with the same key. The loader treats this as 23505 -> the entire import is rolled back.

**Builder MUST deduplicate** rows before writing JSON using these keys. **Validator S21** checks for duplicates.

## Simple UNIQUE (single column)

| Table | UNIQUE |
|---|---|
| `attributes_sets` | `(identifier)` |
| `templates` | `(identifier)` |
| `template_previews` | `(identifier)` |
| `blocks` | `(identifier)` |
| `forms` | `(identifier)` |
| `product_statuses` | `(identifier)` |
| `order_statuses` | `(identifier)` |
| `menus` | `(identifier)` |
| `discounts` | `(identifier)` |
| `filters` | `(identifier)` |
| `payment_accounts` | `(identifier)` |

## Composite UNIQUE (multiple columns) — WARNING: CRITICAL

These tables are garbage traps for the builder. Deduplicate by the UNIQUE key, not by the full row contents.

| Table | UNIQUE key |
|---|---|
| `products_pages_mn` | `(page_id, product_id)` |
| `block_pages_mn` | `(page_id, block_id)` |
| `block_products_mn` | `(product_id, block_id)` |
| `product_blocks_mn` | `(product_id, block_id, lang_code)` |
| `form_module_config` | `(module_id, form_id)` |
| `user_group_permissions_mn` | `(group_id, permission_id)` |
| `orders_storage_payment_accounts` | `(storage_id, payment_account_id)` |

## Deduplication algorithm (for builder, step 13.5)

```python
DEDUPE_RULES = [
    ('products_pages_mn', ('page_id', 'product_id')),
    ('block_pages_mn', ('page_id', 'block_id')),
    ('block_products_mn', ('product_id', 'block_id')),
    ('product_blocks_mn', ('product_id', 'block_id', 'lang_code')),
    ('form_module_config', ('module_id', 'form_id')),
    ('user_group_permissions_mn', ('group_id', 'permission_id')),
    ('orders_storage_payment_accounts', ('storage_id', 'payment_account_id')),
]

def dedupe_by_unique_key(rows, unique_keys, table_name, warnings):
    seen = {}
    for row in rows:
        key = tuple(row.get(k) for k in unique_keys)
        if key in seen:
            warnings.append(f"{table_name}: dropped duplicate by UNIQUE{unique_keys}={key}")
            continue
        seen[key] = row
    return list(seen.values())

for tname, ukey in DEDUPE_RULES:
    if tname in blueprint["tables"]:
        blueprint["tables"][tname] = dedupe_by_unique_key(
            blueprint["tables"][tname], ukey, tname, warnings
        )
```

## Drop semantics (important to understand)

When the builder drops a duplicate — this is an **intentional** loss of binding information. For example, if mapped says:

```yaml
blocks:
  - identifier: related_products
    product_page_bindings:
      - { product: 'wc-1', page: 'women-clothing' }
      - { product: 'wc-1', page: 'men-clothing' }
```

After dedup, `block_products_mn` will contain **one** row `(product_id=@product.wc-1, block_id=@block.related_products, page_id=@page.women-clothing)` — the second page will be lost as `page_id`. This is **fine**: the UNIQUE constraint in the DB says the same binding cannot exist twice. Logically: if a block is bound to product wc-1, it is shown on ALL pages of that product (the frontend decides).

If specific pages matter — better use `block_pages_mn` (block-to-page binding) + `block_products_mn` without page_id (block-to-product binding).

## What the validator (S21) must do

For each table in the composite UNIQUE registry — check key uniqueness:

```python
def check_composite_unique(rows, unique_keys, table_name, errors):
    seen = {}
    for i, row in enumerate(rows):
        key = tuple(row.get(k) for k in unique_keys)
        if key in seen:
            errors.append(
                f"S21: {table_name}[{i}] violates UNIQUE{unique_keys}={key} "
                f"(first occurrence at idx {seen[key]})"
            )
        else:
            seen[key] = i
```

This must be an **ERROR**, not a warning — otherwise the loader will fail on 23505 100% of the time.

## Not in the registry (but worth checking)

- `users_auth_providers` — no explicit UNIQUE in the entity, but in practice the loader may complain when there are two email providers. If there is only one in the blueprint — fine.
- `pages.identifier`, `products.identifier` — NOT unique (only @Index). Duplicate identifiers are allowed but considered bad practice.
