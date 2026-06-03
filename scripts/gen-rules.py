#!/usr/bin/env python3
"""
gen-rules.py — auto-generator of rules for blueprint agents from the OneEntry Platform sources.

⚠ MAINTAINER-ONLY SCRIPT. This file lives in `agents_datasets/scripts/` and is run
exclusively by the maintainer of `agents_datasets/` from the msvc monorepo, where
the sibling `cms/` repo is present. It is NEVER executed in shop environments
where `agents_datasets/` is consumed by AI agents (no `cms/` sources exist there).
All `cms/src/...` paths in the comments below refer to the maintainer's local
`cms/` checkout; they are documentation for the human maintainer, not runtime
references for any agent.

Usage (maintainer only, requires access to a OneEntry Platform source tree):
    cd "<path-to-agents_datasets>"
    python3 scripts/gen-rules.py [--cms-path /abs/path/to/cms-source]

By default looks for cms in ../cms (from agents_datasets/scripts/ this resolves to ../../cms — relative to the msvc repo).

What it regenerates:
- rules/whitelist-tables.md      <- list of ALLOWED_TABLES + FK + NOT NULL columns per-table
- rules/table-columns.md         <- registry of all columns per-table (for S27)
- rules/unique-constraints.md    <- composite UNIQUE keys (for S21)
- rules/preseeded-entities.md    <- INSERTs in seed migrations across whitelist tables (for S20)

After running:
    git diff agents_datasets/rules/   # inspect changes
    git add agents_datasets/rules/
    git commit -m "regenerate rules from cms <date>"
    git push
"""

import re
import sys
import argparse
from pathlib import Path
from datetime import date
from collections import defaultdict

# ============== CONFIGURATION ==============

# Whitelist of tables (source: cms/src/modules/import/sevices/blueprint/blueprint-loader.service.ts)
# IMPORTANT: 24 tables. Extended with user_permissions/user_group_permissions_mn/
# collections/collection_rows — previously these settings required manual post-import,
# now the loader supports upsert by natural-key (see NATURAL_KEYS, SKIP_IF_PARENT_HAS_CHILDREN).
WHITELIST_TABLES = [
    'attributes_sets', 'templates', 'template_previews', 'pages', 'products',
    'products_pages_mn', 'blocks', 'block_pages_mn', 'block_products_mn',
    'product_blocks_mn', 'forms',
    'form_module_config',   # binding of forms to modules (Users, Catalog etc) — Data Submission
    'form_data',            # form data (submitted form records) — name with underscore (entity is @Entity({ name: 'form_data' }))
    'user_groups', 'users_auth_providers',
    'user_permissions',     # permissions (upsert by path+section, preseed reused)
    'user_group_permissions_mn',  # binding of permissions to groups (upsert by group_id+permission_id)
    'collections',          # integration_collections (FAQ/Stores/Brands, upsert by identifier)
    'collection_rows',      # collection rows (skip-if-parent-has-children)
    'product_statuses', 'order_statuses', 'orders_storage',
    'orders_storage_payment_accounts', 'product_relations_templates',
    # Extended whitelist (2026-06-02): previously out-of-whitelist tables now
    # loadable directly via blueprint (no orchestrator round-trip needed).
    'slides', 'menus', 'menu_pages_mn', 'menu_custom_items_mn',
    'discounts', 'discount_conditions', 'discount_coupons',
    'payment_status_map', 'page_errors',
    'filters', 'filter_items_mn',
    'payment_accounts',
]

# Known entity paths for each whitelist table (relative to cms/src/modules)
ENTITY_PATHS = {
    'attributes_sets': 'attributes-sets/entities/attributes-set.entity.ts',
    'templates': 'templates/entities/template.entity.ts',
    'template_previews': 'template-previews/entities/template-previews.entity.ts',
    'pages': 'pages/entities/page.entity.ts',
    'products': 'products/entities/product.entity.ts',
    'products_pages_mn': 'products/entities/product-page.entity.ts',
    'blocks': 'blocks/entities/block.entity.ts',
    'block_pages_mn': 'blocks/entities/block-page.entity.ts',
    'block_products_mn': 'blocks/entities/block-products.entity.ts',
    'product_blocks_mn': 'blocks/entities/product-blocks.entity.ts',
    'forms': 'forms/entities/form.entity.ts',
    'user_groups': 'user-groups/entities/user-group.entity.ts',
    'users_auth_providers': 'users/entities/users-auth-provider.entity.ts',
    'product_statuses': 'product-status/entities/product-status.entity.ts',
    'order_statuses': 'orders/entities/order-status.entity.ts',
    'orders_storage': 'orders/entities/order-storage.entity.ts',
    'orders_storage_payment_accounts': 'orders/entities/order-storage-payment-account.entity.ts',
    'product_relations_templates': 'products/entities/product-relations-template.entity.ts',
    'form_module_config': 'forms/entities/form-module-config.entity.ts',
    'user_permissions': 'user-permissions/entities/user-permission.entity.ts',
    'user_group_permissions_mn': 'user-permissions/entities/user-group-permission-mn.entity.ts',
    'collections': 'collections/entities/collection.entity.ts',
    'collection_rows': 'collections/entities/collection-row.entity.ts',
    # 2026-06-02 extended whitelist
    'slides': 'slides/entities/slide.entity.ts',
    'menus': 'menus/entities/menu.entity.ts',
    'menu_pages_mn': 'menus/entities/menu-page.entity.ts',
    'menu_custom_items_mn': 'menus/entities/menu-custom-item.entity.ts',
    'discounts': 'discounts/entities/discount.entity.ts',
    'discount_conditions': 'discounts/entities/discount-condition.entity.ts',
    'discount_coupons': 'discounts/entities/discount-coupon.entity.ts',
    'payment_status_map': 'payments/entities/payment-status-map.entity.ts',
    'page_errors': 'page-errors/entities/page-error.entity.ts',
    'filters': 'filters/entities/filter.entity.ts',
    'filter_items_mn': 'filters/entities/filter-item.entity.ts',
    'payment_accounts': 'payments/entities/payment-account.entity.ts',
    # form_data — submissions storage; entity FormDataEntity (name: 'form_data' snake_case)
    'form_data': 'form-data/entities/form-data.entity.ts',
}

# Base columns from BaseAbstractEntity (inherited by all entities)
BASE_COLUMNS = {'id', 'created_date', 'updated_date', 'version', 'identifier'}
# Extras from BaseAttributeSetsAbstractEntity
ATTR_SETS_COLUMNS = {'attributes_sets', 'attribute_set_id'}

# Which entities extend BaseAttributeSetsAbstractEntity (have attributes_sets/attribute_set_id columns).
# WARNING: this list is built via grep `extends BaseAttributeSetsAbstractEntity` over cms/src/modules/.
# When a new entity with this extends is added — it MUST be added here.
# Before 2026-05-20 `templates` was missing from this set -> table-columns.md emitted an incorrect
# column list for templates -> builder tried to put attribute_set_id -> validator
# treated it as ERROR S27 -> pipeline could not produce a valid blueprint.
ATTR_SETS_EXTENDED = {
    'pages', 'products', 'blocks', 'forms', 'user_groups',
    'templates',     # <- added 2026-05-20: actually extends BaseAttributeSetsAbstractEntity
}

# Entities extending typeorm `BaseEntity` directly (NOT our BaseAbstractEntity).
# They only have id (PrimaryGeneratedColumn) + explicit columns. No identifier/created_date/updated_date/version.
NO_BASE_ABSTRACT = {
    'products_pages_mn',
    'block_pages_mn',
    'block_products_mn',
    'product_blocks_mn',
    'orders_storage_payment_accounts',
    'user_permissions',         # extends BaseEntity, no identifier/version/dates
    'user_group_permissions_mn',  # extends BaseEntity
    'collection_rows',          # extends BaseEntity
    'form_module_config',       # extends BaseEntity (no identifier column)
    'form_data',                # extends BaseEntity (only id + explicit columns)
}

# Extra columns that the auto-parser misses (for example, camelCase in the DB).
# Loader works with these columns exactly in this form — they cannot be converted.
EXTRA_COLUMNS = {
    # products_pages_mn — the only mn-table with camelCase in the DB (TypeORM does not convert
    # because @Column({ nullable: true }) has no explicit name:).
    'products_pages_mn': {'pageId', 'productId'},
}

# Columns that MUST be excluded from auto-generation (auto-parser finds them, but they
# should not appear in the blueprint — for example, if they are synonyms for already-included ones).
EXCLUDE_COLUMNS = {
    # snake_case versions that the auto-parser produced from camelCase entity fields, while the DB stores them in camelCase.
    'products_pages_mn': {'page_id', 'product_id'},
}

# ============== PARSERS ==============

def parse_entity_columns(entity_path: Path) -> dict:
    """Parse an entity file, return a dict with columns and metadata."""
    if not entity_path.exists():
        return {'columns': set(), 'unique': [], 'not_null': set(), 'fks': {}}

    raw_text = entity_path.read_text(encoding='utf-8')

    # WARNING: strip comments before parsing — otherwise commented-out @Column / @JoinColumn
    # mistakenly end up in the column registry (typical bug: name: 'capture_mode' was in a
    # // @Column block and the regex captured it -> table-columns.md contained a column
    # that does not exist in the real DB -> blueprint failed with HTTP 500 on import).
    text = re.sub(r'/\*.*?\*/', '', raw_text, flags=re.DOTALL)      # block comments
    text = re.sub(r'(?m)^\s*//.*$', '', text)                       # line comments

    # Columns: find all @Column(..., name: 'xxx') and fields WITHOUT name (name = property name -> snake_case)
    columns = set()

    # 1. @Column(...{name: 'col_name'}) — explicit name
    for m in re.finditer(r"@Column\([^)]*name:\s*['\"]([a-z_]+)['\"]", text):
        columns.add(m.group(1))
    # 2. @JoinColumn({ name: 'col_name' }) — for FK via ManyToOne
    for m in re.finditer(r"@JoinColumn\([^)]*name:\s*['\"]([a-z_]+)['\"]", text):
        columns.add(m.group(1))
    # 3. @Column({...}) without name -> name from the following property (camelCase -> snake_case)
    # Simple heuristic: find @Column(...without name)\n property_name:
    for m in re.finditer(
        r"@Column\([^)]*\)\s*\n\s*([a-zA-Z]+)\s*[:?]",
        text
    ):
        prop = m.group(1)
        # camelCase -> snake_case
        snake = re.sub(r'(?<!^)(?=[A-Z])', '_', prop).lower()
        # Only if no preceding @JoinColumn/name
        columns.add(snake)

    # Also — public property name: type without @Column but inside an entity class (rare, skipped)

    # NOT NULL: nullable: false explicit OR nullable: true is absent
    not_null = set()
    # 1. @Column({... name: 'xxx' ..., nullable: false ...})  — explicit name
    for m in re.finditer(
        r"@Column\(([^)]+)\)",
        text, re.DOTALL
    ):
        block = m.group(1)
        name_m = re.search(r"name:\s*['\"]([a-z_]+)['\"]", block)
        if not name_m:
            continue
        col = name_m.group(1)
        if 'nullable: false' in block:
            not_null.add(col)
        # If nullable is not mentioned — typeorm defaults to true (nullable), but if there is a default value — usually not null
        elif 'nullable:' not in block and 'default:' not in block:
            # Often this is not null by default
            pass
    # 2. @Column({...nullable: false...}) without explicit `name:` -> derive from property name
    # (same camelCase -> snake_case heuristic as in columns extraction).
    # Covers entities where TypeORM derives column name from the property — e.g.
    # `user_permissions.path` / `user_permissions.section`, where @Column has
    # nullable: false but no explicit name: key. Historically the parser missed
    # these and the generated whitelist-tables.md under-reported NOT NULL.
    for m in re.finditer(
        r"@Column\(([^)]*)\)\s*\n\s*([a-zA-Z]+)\s*[:?]",
        text, re.DOTALL,
    ):
        block = m.group(1)
        prop = m.group(2)
        if 'nullable: false' not in block:
            continue
        # Skip if there is an explicit `name:` in the block — that case is handled above.
        if re.search(r"name:\s*['\"][a-z_]+['\"]", block):
            continue
        snake = re.sub(r'(?<!^)(?=[A-Z])', '_', prop).lower()
        not_null.add(snake)

    # UNIQUE: @Unique(['col1', 'col2'])
    unique = []
    for m in re.finditer(r"@Unique\(\[\s*([^\]]+)\s*\]\)", text):
        cols = re.findall(r"['\"]([a-zA-Z_]+)['\"]", m.group(1))
        # camelCase -> snake_case (TypeORM converts)
        cols_db = [re.sub(r'(?<!^)(?=[A-Z])', '_', c).lower() for c in cols]
        unique.append(cols_db)

    # UNIQUE INDEX: @Index(['col1', 'col2'], { unique: true })
    # Эта форма используется у user_group_permissions_mn (group_id, permission_id)
    # вместо @Unique. Семантически идентично UNIQUE constraint'у — нарушение
    # даёт PG error 23505, поэтому validator S21 должен видеть оба варианта.
    for m in re.finditer(
        r"@Index\(\s*\[\s*([^\]]+)\s*\]\s*,\s*\{[^}]*unique:\s*true[^}]*\}\s*\)",
        text,
    ):
        cols = re.findall(r"['\"]([a-zA-Z_]+)['\"]", m.group(1))
        cols_db = [re.sub(r'(?<!^)(?=[A-Z])', '_', c).lower() for c in cols]
        unique.append(cols_db)

    # FK: @ManyToOne + @JoinColumn name
    fks = {}
    for m in re.finditer(
        r"@JoinColumn\(\{[^}]*name:\s*['\"]([a-z_]+)['\"]",
        text
    ):
        col = m.group(1)
        # FK target is hard to determine — left for manual annotation in whitelist-tables.md
        fks[col] = '?'

    return {'columns': columns, 'unique': unique, 'not_null': not_null, 'fks': fks}


def find_seed_inserts(seeds_dir: Path, whitelist: list) -> dict:
    """Parse seed files for INSERTs into whitelist tables."""
    if not seeds_dir.exists():
        return {}
    inserts = defaultdict(list)
    for sf in seeds_dir.glob('*.ts'):
        text = sf.read_text(encoding='utf-8', errors='ignore')
        for tbl in whitelist:
            for m in re.finditer(
                rf"INSERT INTO\s+{tbl}\s*\(([^)]+)\)\s*VALUES\s*\(([^)]+)\)",
                text, re.IGNORECASE
            ):
                cols = [c.strip() for c in m.group(1).split(',')]
                vals = [v.strip() for v in m.group(2).split(',')]
                inserts[tbl].append({
                    'source': sf.name,
                    'columns': cols,
                    'values': vals,
                })
    return dict(inserts)


# ============== GENERATORS ==============

def gen_table_columns_md(parsed: dict) -> str:
    today = date.today().isoformat()
    out = [
        '# Table columns — registry of allowed columns for each whitelist table',
        '',
        '> **This file is auto-generated** via `agents_datasets/scripts/gen-rules.py`. Do not edit by hand — changes will be overwritten on the next regeneration.',
        '>',
        f'> Generation date: {today}.',
        '>',
        '> Source of truth: `cms/src/modules/{*}/entities/*.entity.ts`.',
        '',
        '## Why this file exists',
        '',
        'The OneEntry loader performs a direct `INSERT INTO <table> (col1, col2, ...) VALUES (...)`. If a blueprint row references **a column that does not exist in the entity**, the loader fails with **HTTP 500** error `column "X" of relation "Y" does not exist`.',
        '',
        '**Builder MUST** use **only columns from the registry** for each row. **Validator S27** checks this automatically.',
        '',
        '## Inherited columns',
        '',
        'Most tables extend `BaseAbstractEntity` (or `BaseAttributeSetsAbstractEntity`). Inherited columns are **present everywhere**:',
        '',
        '**`BaseAbstractEntity`:** `id`, `created_date`, `updated_date`, `version`, `identifier`',
        '',
        '**`BaseAttributeSetsAbstractEntity`** (extends `BaseAbstractEntity`): + `attributes_sets` (jsonb), `attribute_set_id` (int)',
        '',
        '## Column registry per-table',
        '',
    ]
    for tbl in WHITELIST_TABLES:
        info = parsed.get(tbl, {'columns': set()})
        # mn-tables (NO_BASE_ABSTRACT) extend typeorm BaseEntity -> only 'id' + explicit columns.
        # Other tables extend our BaseAbstractEntity -> + BASE_COLUMNS (id, identifier, timestamps, version).
        if tbl in NO_BASE_ABSTRACT:
            cols_set = info['columns'] | {'id'}
        else:
            cols_set = info['columns'] | BASE_COLUMNS | (ATTR_SETS_COLUMNS if tbl in ATTR_SETS_EXTENDED else set())
        # Overrides: add EXTRA, remove EXCLUDE
        cols_set |= EXTRA_COLUMNS.get(tbl, set())
        cols_set -= EXCLUDE_COLUMNS.get(tbl, set())
        cols = sorted(cols_set)
        out.append(f'### `{tbl}`')
        out.append('')
        out.append(f'Columns: {", ".join(f"`{c}`" for c in cols)}')
        if not info['columns']:
            out.append('')
            out.append('WARNING: **Entity not found** — check the path in `gen-rules.py`')
        out.append('')

    # Separate section: which tables have/lack localize_infos (typical source of bugs)
    has_localize = sorted(t for t, info in parsed.items() if 'localize_infos' in info.get('columns', set()))
    no_localize = sorted(t for t in WHITELIST_TABLES if t not in has_localize)
    out.extend([
        '## Which tables have `localize_infos`',
        '',
        f'**PRESENT:** {", ".join(f"`{t}`" for t in has_localize) if has_localize else "_none_"}',
        '',
        f'**ABSENT:** {", ".join(f"`{t}`" for t in no_localize) if no_localize else "_none_"}',
        '',
        'WARNING: if the builder put `localize_infos` into a table from the "ABSENT" list — HTTP 500 will follow. Most common mistakes:',
        '- `attributes_sets` with `localize_infos` — it only has a flat `title` (string). Name localization is done via `schema.<key>.localizeInfos` inside schema fields.',
        '- `templates`, `template_previews`, `product_relations_templates` — also only a flat `title` or `name`.',
        '- mn-tables — no localization at all.',
        '',
        '## What the builder must do',
        '',
        '1. For each row use **only columns from the corresponding registry section**.',
        '2. Do not add `localize_infos` to `attributes_sets` / `templates` / `template_previews` / `product_relations_templates`.',
        '3. Do not add `is_visible` or other fields if they are not in the entity.',
        '',
        '## What the validator (S27) must do',
        '',
        '```python',
        'import re',
        'allowed = {}',
        "text = open('agents_datasets/rules/table-columns.md').read()",
        'for m in re.finditer(r"### `([a-z_]+)`\\n\\nColumns: ([^\\n]+)", text):',
        '    table = m.group(1)',
        '    cols = re.findall(r"`([a-z_]+)`", m.group(2))',
        '    allowed[table] = set(cols)',
        '',
        'for tname, rows in tables.items():',
        '    if tname not in allowed: continue',
        '    for i, row in enumerate(rows):',
        '        extra = set(row.keys()) - allowed[tname]',
        '        if extra:',
        '            errors.append(f"S27: {tname}[{i}] uses unknown columns {sorted(extra)}. "',
        '                          f"Will fail with HTTP 500. See rules/table-columns.md")',
        '```',
        '',
        'S27 is an **ERROR**, not a warning, because the blueprint fails with HTTP 500.',
    ])
    return '\n'.join(out) + '\n'


def gen_unique_constraints_md(parsed: dict) -> str:
    today = date.today().isoformat()
    out = [
        '# UNIQUE constraints — registry and deduplication rules',
        '',
        '> **This file is auto-generated** via `agents_datasets/scripts/gen-rules.py`. Do not edit by hand.',
        '>',
        f'> Generation date: {today}.',
        '>',
        '> Source of truth: the `@Unique([...])` decorator in `cms/src/modules/{*}/entities/*.entity.ts`.',
        '',
        '## Why this file exists',
        '',
        'A PostgreSQL UNIQUE constraint fires on INSERT when attempting to insert a second row with the same key. The loader treats this as 23505 -> the entire import is rolled back.',
        '',
        '**Builder MUST deduplicate** rows before writing JSON using these keys. **Validator S21** checks for duplicates.',
        '',
        '## Simple UNIQUE (single column)',
        '',
        '| Table | UNIQUE |',
        '|---|---|',
    ]
    composite_rows = []
    for tbl in WHITELIST_TABLES:
        info = parsed.get(tbl, {})
        for u in info.get('unique', []):
            if len(u) == 1:
                out.append(f'| `{tbl}` | `({u[0]})` |')
            else:
                composite_rows.append((tbl, u))

    out.extend([
        '',
        '## Composite UNIQUE (multiple columns) — WARNING: CRITICAL',
        '',
        'These tables are garbage traps for the builder. Deduplicate by the UNIQUE key, not by the full row contents.',
        '',
        '| Table | UNIQUE key |',
        '|---|---|',
    ])
    for tbl, u in composite_rows:
        out.append(f'| `{tbl}` | `({", ".join(u)})` |')

    out.extend([
        '',
        '## Deduplication algorithm (for builder, step 13.5)',
        '',
        '```python',
        'DEDUPE_RULES = [',
    ])
    for tbl, u in composite_rows:
        out.append(f"    ('{tbl}', {tuple(u)!r}),")
    out.extend([
        ']',
        '',
        'def dedupe_by_unique_key(rows, unique_keys, table_name, warnings):',
        '    seen = {}',
        '    for row in rows:',
        '        key = tuple(row.get(k) for k in unique_keys)',
        '        if key in seen:',
        '            warnings.append(f"{table_name}: dropped duplicate by UNIQUE{unique_keys}={key}")',
        '            continue',
        '        seen[key] = row',
        '    return list(seen.values())',
        '',
        'for tname, ukey in DEDUPE_RULES:',
        '    if tname in blueprint["tables"]:',
        '        blueprint["tables"][tname] = dedupe_by_unique_key(',
        '            blueprint["tables"][tname], ukey, tname, warnings',
        '        )',
        '```',
        '',
        '## Drop semantics (important to understand)',
        '',
        'When the builder drops a duplicate — this is an **intentional** loss of binding information. For example, if mapped says:',
        '',
        '```yaml',
        'blocks:',
        '  - identifier: related_products',
        '    product_page_bindings:',
        "      - { product: 'product-a', page: 'category-x' }",
        "      - { product: 'product-a', page: 'category-y' }",
        '```',
        '',
        'After dedup, `block_products_mn` will contain **one** row `(product_id=@product.product-a, block_id=@block.related_products, page_id=@page.category-x)` — the second page will be lost as `page_id`. This is **fine**: the UNIQUE constraint in the DB says the same binding cannot exist twice. Logically: if a block is bound to product `product-a`, it is shown on ALL pages of that product (the frontend decides). The example uses generic identifiers (`product-a`, `category-x/y`); any vertical applies — substitute with real project identifiers (`wc-1`/`women-clothing` for a fashion shop, `pizza-1`/`mains` for a restaurant, `room-101`/`suites` for a hotel).',
        '',
        'If specific pages matter — better use `block_pages_mn` (block-to-page binding) + `block_products_mn` without page_id (block-to-product binding).',
        '',
        '## What the validator (S21) must do',
        '',
        'For each table in the composite UNIQUE registry — check key uniqueness:',
        '',
        '```python',
        'def check_composite_unique(rows, unique_keys, table_name, errors):',
        '    seen = {}',
        '    for i, row in enumerate(rows):',
        '        key = tuple(row.get(k) for k in unique_keys)',
        '        if key in seen:',
        '            errors.append(',
        '                f"S21: {table_name}[{i}] violates UNIQUE{unique_keys}={key} "',
        '                f"(first occurrence at idx {seen[key]})"',
        '            )',
        '        else:',
        '            seen[key] = i',
        '```',
        '',
        'This must be an **ERROR**, not a warning — otherwise the loader will fail on 23505 100% of the time.',
        '',
        '## Not in the registry (but worth checking)',
        '',
        '- `users_auth_providers` — no explicit UNIQUE in the entity, but in practice the loader may complain when there are two email providers. If there is only one in the blueprint — fine.',
        '- `pages.identifier`, `products.identifier` — NOT unique (only @Index). Duplicate identifiers are allowed but considered bad practice.',
    ])
    return '\n'.join(out) + '\n'


def gen_preseeded_md(seed_inserts: dict) -> str:
    today = date.today().isoformat()
    out = [
        '# Preseeded entities — what already exists in any fresh OneEntry Platform instance',
        '',
        '> **This file is auto-generated** via `agents_datasets/scripts/gen-rules.py`. Do not edit by hand.',
        '>',
        f'> Generation date: {today}.',
        '>',
        '> Source of truth: `INSERT INTO <whitelist_table>` in `cms/src/seeds/*.ts`.',
        '',
        '## Rule',
        '',
        'In any freshly installed OneEntry Platform instance, certain records in whitelist tables **already exist** via TypeORM migrations. The blueprint **must not** try to insert them again — 23505 will follow.',
        '',
        'Mapper and builder must **not generate** preseeded records. If the user application has an analogous entity — use the existing numeric id directly (without a token) in the FK reference.',
        '',
        '## Registry of preseeded records in whitelist tables',
        '',
    ]
    if not seed_inserts:
        out.append('_No INSERTs into whitelist tables found in `cms/src/seeds/`._')
        out.append('')
    else:
        out.append('| Table | Source | Columns -> values |')
        out.append('|---|---|---|')
        for tbl, items in sorted(seed_inserts.items()):
            for item in items:
                cv = ', '.join(f"`{c}={v}`" for c, v in zip(item['columns'], item['values']))
                out.append(f"| `{tbl}` | `{item['source']}` | {cv} |")

        out.append('')
        out.append('## How to reference a preseeded record')
        out.append('')
        out.append('If the application needs a reference to a preseeded record (for example, the guest user_group):')
        out.append('')
        out.append('WRONG (will create a duplicate -> 23505):')
        out.append('```yaml')
        out.append('user_groups:')
        out.append('  - identifier: guest    # already preseeded!')
        out.append('```')
        out.append('')
        out.append('CORRECT — specify the **numeric id directly** in the FK field:')
        out.append('```json')
        out.append('"users_auth_providers": [{')
        out.append('  "user_group_id": 1     // <- numeric id of preseeded guest')
        out.append('}]')
        out.append('```')

    out.extend([
        '',
        '## What we DO NOT generate in mapper / builder',
        '',
    ])
    for tbl, items in sorted(seed_inserts.items()):
        for item in items:
            id_idx = next((i for i, c in enumerate(item['columns']) if c == 'identifier'), None)
            if id_idx is not None and id_idx < len(item['values']):
                ident = item['values'][id_idx].strip("'\"")
                out.append(f'- `{tbl}` with identifier `{ident}` — **never**.')

    out.extend([
        '',
        '## Why the loader CANNOT do identifier-lookup',
        '',
        'From `cms/src/modules/import/sevices/blueprint/blueprint-loader.service.ts`:',
        '- The loader expects that **every** reference via `@token` has a corresponding row with `id: @token` in the blueprint.',
        '- If the row is missing -> error `Unresolved token references` (S4).',
        '- The loader **does not** issue a DB query like `SELECT id FROM user_groups WHERE identifier=\'guest\'`.',
        '',
        'Therefore the only way to reference a preseeded record is **a numeric id directly** in the FK field. The loader sees a number (not a string with `@`), skips resolution, passes it as-is to INSERT. PostgreSQL FK constraint checks existence -> finds the preseeded record -> import succeeds.',
        '',
        '## What the validator (S20) must do',
        '',
        '```python',
        'preseeded_identifiers = {',
        '    # From this file: { table_name: [identifiers...] }',
        '}',
        'for table_name, idents in preseeded_identifiers.items():',
        '    rows = tables.get(table_name, [])',
        '    for i, row in enumerate(rows):',
        '        if row.get("identifier") in idents:',
        '            errors.append(',
        '                f"S20: {table_name}[{i}] has identifier \'{row[\'identifier\']}\' "',
        '                f"which is already preseeded in OneEntry Platform. "',
        '                f"Use literal id (number) in FK references instead."',
        '            )',
        '```',
    ])

    return '\n'.join(out) + '\n'


def gen_whitelist_tables_md(parsed: dict) -> str:
    today = date.today().isoformat()
    count = len(WHITELIST_TABLES)
    out = [
        f'# Whitelist tables — {count} tables for Blueprint',
        '',
        '> **This file is partially auto-generated** via `agents_datasets/scripts/gen-rules.py`. The table list and NOT NULL columns are regenerated. FK descriptions and text comments may be edited manually (see hand-written sections below).',
        '>',
        f'> Generation date: {today}.',
        '',
        f'## {count} allowed tables',
        '',
        '```',
    ]
    out.extend(WHITELIST_TABLES)
    out.append('```')
    out.append('')
    out.append('## NOT NULL columns (without default) per-table')
    out.append('')
    out.append('Extracted from `@Column(..., nullable: false, ...)` without `default:` in the entity.')
    out.append('')

    for tbl in WHITELIST_TABLES:
        info = parsed.get(tbl, {})
        nn = info.get('not_null', set())
        out.append(f'### `{tbl}`')
        if nn:
            out.append('NOT NULL: ' + ', '.join(f'`{c}`' for c in sorted(nn)))
        else:
            out.append('NOT NULL: _(no explicit not-null without default)_')
        out.append('')

    out.append('## Hard FKs (hand-written section — maintain on changes)')
    out.append('')
    out.append('Source: `cms/src/modules/import/sevices/blueprint/fk-graph.ts`. This section is **not regenerated automatically** — update by hand if the FK map changes.')
    out.append('')
    out.append('```')
    out.append('templates:                       attribute_set_id -> attributes_sets')
    out.append('pages:                           attribute_set_id, template_id, parent_id (self)')
    out.append('blocks:                          attribute_set_id, template_id')
    out.append('products:                        attribute_set_id, template_id, status_id')
    out.append('products_pages_mn:               pageId, productId          <- camelCase!')
    out.append('block_pages_mn:                  page_id, block_id')
    out.append('block_products_mn:               product_id, block_id, page_id')
    out.append('product_blocks_mn:               product_id, block_id')
    out.append('forms:                           attribute_set_id, template_id')
    out.append('user_groups:                     attribute_set_id, parent_id (self)')
    out.append('users_auth_providers:            user_group_id, form_id')
    out.append('orders_storage:                  form_id')
    out.append('order_statuses:                  storage_id')
    out.append('orders_storage_payment_accounts: storage_id, payment_account_id')
    out.append('# Added 2026-05-21 — six new whitelist tables:')
    out.append('form_module_config:              form_id, module_id')
    out.append('form_data:                       form_module_id -> form_modules_mn (junction of forms↔modules; NOT directly to forms)')
    out.append('user_permissions:                (no outgoing FK; binds to user_groups via user_group_permissions_mn)')
    out.append('user_group_permissions_mn:       group_id -> user_groups, permission_id -> user_permissions')
    out.append('collections:                     form_id -> forms (optional, onDelete: SET NULL)')
    out.append('collection_rows:                 collection_id -> collections (SKIP_IF_PARENT_HAS_CHILDREN policy on re-import)')
    out.append('```')
    return '\n'.join(out) + '\n'


# ============== MAIN ==============

def main():
    parser = argparse.ArgumentParser(description='Regenerate blueprint-agent rules from cms entities')
    script_dir = Path(__file__).resolve().parent
    default_cms = (script_dir.parent.parent / 'cms').resolve()
    parser.add_argument(
        '--cms-path',
        default=str(default_cms),
        help=f'Absolute path to cms folder (default: {default_cms})',
    )
    parser.add_argument(
        '--rules-dir',
        default=str(script_dir.parent / 'rules' / 'generated'),
        help='Output dir for auto-generated rules (default: rules/generated/). Do NOT confuse with rules/ — that one holds hand-written files (coverage-checklist, oneentry-invariants, standard-entities + manual extensions).',
    )
    parser.add_argument('--dry-run', action='store_true', help='Print to stdout, don\'t write files')
    args = parser.parse_args()

    cms_path = Path(args.cms_path)
    if not cms_path.exists():
        print(f"ERROR: cms folder not found: {cms_path}", file=sys.stderr)
        print("Pass --cms-path /abs/path/to/cms", file=sys.stderr)
        sys.exit(1)

    modules_dir = cms_path / 'src' / 'modules'
    seeds_dir = cms_path / 'src' / 'seeds'

    print(f"Reading cms from: {cms_path}")
    print(f"Modules dir:      {modules_dir}")
    print(f"Seeds dir:        {seeds_dir}")
    print()

    # Parse entity for each whitelist table
    parsed = {}
    for tbl in WHITELIST_TABLES:
        if tbl not in ENTITY_PATHS:
            # WARNING: table is in WHITELIST_TABLES but lacks an associated entity file
            # (for example, `form-data` — path not yet provided). Skip with a warning
            # to avoid KeyError. This is a "configuration bug", not a data bug.
            print(f"  WARNING {tbl}: NO entity path in ENTITY_PATHS — skipped")
            parsed[tbl] = {'columns': set(), 'unique': [], 'not_null': set(), 'fks': {}}
            continue
        ent_path = modules_dir / ENTITY_PATHS[tbl]
        info = parse_entity_columns(ent_path)
        parsed[tbl] = info
        status = 'OK' if info['columns'] else 'NOT FOUND'
        print(f"  {status} {tbl}: {len(info['columns'])} cols, {len(info['unique'])} unique, {len(info['not_null'])} not-null")

    # Parse seeds for preseeded INSERTs
    seed_inserts = find_seed_inserts(seeds_dir, WHITELIST_TABLES)
    print(f"\n  Preseeded INSERTs: {sum(len(v) for v in seed_inserts.values())} rows in {len(seed_inserts)} tables")

    # Generate 4 files
    rules_dir = Path(args.rules_dir)
    files_to_write = {
        'table-columns.md': gen_table_columns_md(parsed),
        'unique-constraints.md': gen_unique_constraints_md(parsed),
        'preseeded-entities.md': gen_preseeded_md(seed_inserts),
        'whitelist-tables.md': gen_whitelist_tables_md(parsed),
    }

    print()
    if args.dry_run:
        for name, content in files_to_write.items():
            print(f"\n{'=' * 60}\n{name}\n{'=' * 60}\n{content[:500]}...")
    else:
        rules_dir.mkdir(parents=True, exist_ok=True)
        for name, content in files_to_write.items():
            target = rules_dir / name
            old = target.read_text() if target.exists() else ''
            if old == content:
                print(f"  = {name} (no changes)")
            else:
                target.write_text(content)
                print(f"  + {name} (updated)")
        print()
        print("Done. Review changes:")
        print(f"  git diff {rules_dir}")
        print(f"  git add  {rules_dir}")
        print(f"  git commit -m 'regenerate rules from cms'")


if __name__ == '__main__':
    main()
