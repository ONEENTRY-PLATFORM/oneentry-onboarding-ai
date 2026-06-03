#!/usr/bin/env python3
"""build-blueprint.py — deterministic OneEntry blueprint assembler.

Reads `mapped.yaml` produced by the mapper + post-mapper-fixer, copies the
known whitelist tables into `blueprint.json::tables`, filters out unknown
columns (using rules/generated/table-columns.md as source of truth), dedupes
composite-UNIQUE tables, and writes the JSON.

This replaces the previous AI-driven blueprint-builder agent that was prone
to silently dropping tables it didn't know about — a deterministic script
cannot drift.

Usage:
    python3 build-blueprint.py <mapped.yaml> <blueprint.json> [--rules-dir DIR]

Exit codes:
    0  success
    1  user error (file not found, bad YAML)
    2  shape/data error (unresolvable refs, etc.)
"""
import argparse
import json
import os
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print('ERROR: pyyaml is required. Install with `pip install pyyaml`.', file=sys.stderr)
    sys.exit(1)


# Sources of truth — built from rules/generated/* which gen-rules.py keeps in
# sync with the cms entity layer. Loaded lazily from the rules dir; falls
# back to the canonical msvc/agents_datasets when none is passed.
_DEFAULT_RULES_DIR = Path(__file__).resolve().parent.parent / 'rules' / 'generated'


def _parse_columns_md(path: Path) -> dict[str, set[str]]:
    """Parse rules/generated/table-columns.md → {table: set(columns)}."""
    out: dict[str, set[str]] = {}
    if not path.exists():
        return out
    text = path.read_text()
    # ### `table_name`\nColumns: `col1`, `col2`, ...
    for m in re.finditer(
        r'^### `(\w+)`\s*\n\s*\n\s*Columns:\s*((?:`\w+`(?:,\s*)?)+)',
        text,
        re.MULTILINE,
    ):
        table = m.group(1)
        cols = set(re.findall(r'`(\w+)`', m.group(2)))
        out[table] = cols
    # Inherited columns from BaseAbstractEntity / BaseAttributeSetsAbstractEntity
    base_cols = {'id', 'created_date', 'updated_date', 'version', 'identifier'}
    aset_inherited = base_cols | {'attributes_sets', 'attribute_set_id'}
    aset_tables = {'pages', 'blocks', 'forms', 'user_groups', 'products', 'slides',
                   'templates', 'discounts'}
    # Columns gen-rules.py misses because they use `@Column({ unique: true })`
    # without an explicit `name:` (TypeORM uses property name as DB column).
    # Tracked here as a fallback supplement. Universal — these columns are
    # required by NOT NULL constraints across every project.
    forced_extras = {
        'page_errors':         {'code'},
        'discount_coupons':    {'code', 'is_used', 'is_reusable', 'used_at', 'order_id'},
        'menu_pages_mn':       {'is_pinned', 'page_id', 'menu_id', 'parent_id'},
        'menu_custom_items_mn':{'menu_id', 'parent_id', 'value', 'localize_infos'},
        'slides':              {'block_id', 'parent_id', 'is_visible', 'time', 'time_interval'},
        'filter_items_mn':     {'filter_id', 'object_type', 'object_id', 'attribute_value_id',
                                'value_text', 'parent_id', 'range_from', 'range_to'},
        'payment_status_map':  {'order_storage_id', 'status_map'},
        'discount_conditions': {'discount_id', 'condition_type', 'entity_ids', 'value'},
        'discounts':           {'type', 'condition_logic', 'discount_value', 'exclusions',
                                'gifts', 'gifts_replace_cart_items', 'user_groups',
                                'user_exclusions', 'start_date', 'end_date',
                                'selected_attribute_markers'},
        'menus':               {'localize_infos'},
        'filters':             {'localize_infos', 'scope_types'},
        'order_statuses':      {'storage_id', 'is_default', 'localize_infos'},
        'orders_storage_payment_accounts': {'payment_account_id'},
    }
    for t in out:
        out[t] |= base_cols
        if t in aset_tables:
            out[t] |= aset_inherited
        if t in forced_extras:
            out[t] |= forced_extras[t]
    return out


def _parse_unique_constraints_md(path: Path) -> dict[str, list[list[str]]]:
    """Parse rules/generated/unique-constraints.md → {table: [[cols...], ...]}.

    Each table can have multiple composite-UNIQUE constraints. Builder must
    dedup rows by EVERY one of them, otherwise the loader fails with 23505.
    """
    out: dict[str, list[list[str]]] = {}
    if not path.exists():
        return out
    text = path.read_text()
    # Looks for: ### `table` ... UNIQUE (col1, col2, ...)
    cur_table = None
    for line in text.splitlines():
        m = re.match(r'^### `(\w+)`', line)
        if m:
            cur_table = m.group(1)
            continue
        if cur_table:
            mu = re.search(r'UNIQUE\s*\(\s*([\w,\s_]+)\s*\)', line)
            if mu:
                cols = [c.strip() for c in mu.group(1).split(',') if c.strip()]
                if cols:
                    out.setdefault(cur_table, []).append(cols)
    return out


# Source tables in mapped.yaml that are emitted at the TOP level (not inside
# `tables.*`). The builder hoists them up.
TOP_LEVEL_TABLES = {
    'attributes_sets', 'templates', 'template_previews',
    'pages', 'products', 'products_pages_mn',
    'blocks', 'block_pages_mn', 'block_products_mn', 'product_blocks_mn',
    'forms', 'form_module_config', 'form_data',
    'user_groups', 'users_auth_providers', 'user_permissions',
    'user_group_permissions_mn',
    'collections', 'collection_rows',
    'product_statuses', 'order_statuses', 'orders_storage',
    'orders_storage_payment_accounts', 'product_relations_templates',
    # Extended whitelist (2026-06-02)
    'slides', 'menus', 'menu_pages_mn', 'menu_custom_items_mn',
    'discounts', 'discount_conditions', 'discount_coupons',
    'payment_status_map', 'page_errors',
    'filters', 'filter_items_mn',
    'payment_accounts',
}


def _dedupe_rows(rows: list[dict], key_cols: list[str]) -> tuple[list[dict], int]:
    """Drop rows whose composite-key already appeared. Idempotent."""
    seen: set[tuple] = set()
    out: list[dict] = []
    dropped = 0
    for row in rows:
        try:
            k = tuple(row.get(c) for c in key_cols)
        except TypeError:
            out.append(row)
            continue
        # If any key column is missing or None, skip dedup for this row —
        # the loader will validate NOT NULL at insert time.
        if any(v is None for v in k):
            out.append(row)
            continue
        if k in seen:
            dropped += 1
            continue
        seen.add(k)
        out.append(row)
    return out, dropped


def _filter_columns(row: dict, allowed: set[str]) -> dict:
    """Keep only allowed columns. Strips builder-internal helpers like
    `attribute_set` (semantic identifier) — those don't map to DB columns."""
    return {k: v for k, v in row.items() if k in allowed}


def _normalize_aset_token(row: dict) -> None:
    """Convert mapper's semantic FK names (`form: 'checkout'`, `page: 'about'`,
    `attribute_set: 'forUsers'`) into loader-expected `<x>_id: '@<ns>.<ident>'`
    tokens. Universal across project verticals."""
    # Safe-to-rewrite semantic→FK mappings. `parent` and `template` are
    # ambiguous (different namespaces depending on table), so they are
    # handled via the table-specific lookup at the bottom.
    sem_to_fk = {
        'attribute_set': ('attribute_set_id', 'aset'),
        'form':          ('form_id',          'form'),
        'block':         ('block_id',         'block'),
        'menu':          ('menu_id',          'menu'),
        'filter':        ('filter_id',        'filter'),
        'discount':      ('discount_id',      'discount'),
        'orders_storage':('order_storage_id', 'ostorage'),
        'user_group':    ('user_group_id',    'ug'),
    }
    for sem, (fk, ns) in sem_to_fk.items():
        if sem in row and fk not in row:
            v = row.pop(sem)
            if isinstance(v, str) and v:
                row[fk] = v if v.startswith('@') else f'@{ns}.{v}'


# Table-specific semantic-FK mappings — applied AFTER the generic ones.
# Used for fields where the namespace depends on the table (e.g. `parent`
# means @page.X on pages but @menu_page.X on menu_pages_mn — different
# entity, different table).
TABLE_SPECIFIC_SEM_FK = {
    'pages': {
        'parent':   ('parent_id',  'page'),
        'template': ('template_id', 'tpl'),
    },
    'products': {
        'template': ('template_id', 'tpl'),
        'status':   ('status_id',   'ps'),
    },
    'blocks': {
        'template': ('template_id', 'tpl'),
    },
    'forms': {
        'template': ('template_id', 'tpl'),
    },
    'user_groups': {
        'parent':   ('parent_id',  'ug'),
    },
    'order_statuses': {
        'storage':  ('storage_id', 'ostorage'),
    },
    # mn / junction tables — semantic identifiers → camelCase FK tokens.
    # NB column names are camelCase (`pageId`, `productId`) not snake_case.
    'products_pages_mn': {
        'product':  ('productId', 'product'),
        'page':     ('pageId',    'page'),
    },
    'block_pages_mn': {
        'block':    ('block_id', 'block'),
        'page':     ('page_id',  'page'),
    },
    'block_products_mn': {
        'block':    ('block_id',   'block'),
        'product':  ('product_id', 'product'),
        'page':     ('page_id',    'page'),
    },
    'product_blocks_mn': {
        'block':    ('block_id',   'block'),
        'product':  ('product_id', 'product'),
    },
    'user_group_permissions_mn': {
        'group':       ('group_id',      'ug'),
        'user_group':  ('group_id',      'ug'),
        'permission':  ('permission_id', 'perm'),
    },
}


def _normalize_table_specific(table: str, row: dict) -> None:
    """Apply table-specific semantic→FK rewriting that the generic
    `_normalize_aset_token` cannot infer."""
    mapping = TABLE_SPECIFIC_SEM_FK.get(table)
    if not mapping:
        return
    for sem, (fk, ns) in mapping.items():
        if sem in row and fk not in row:
            v = row.pop(sem)
            if isinstance(v, str) and v:
                row[fk] = v if v.startswith('@') else f'@{ns}.{v}'


# Tables whose rows are typically referenced by `@<ns>.<identifier>` tokens
# from FK columns of other tables. If a row in one of these tables has an
# `identifier` but no `id` field, the builder auto-generates an id token
# (`@<ns>.<identifier>`) so the loader's TokenRegistry can resolve cross-table
# refs.
ID_TOKEN_NAMESPACES = {
    'attributes_sets': 'aset',
    'templates': 'tpl',
    'pages': 'page',
    'blocks': 'block',
    'products': 'product',
    'forms': 'form',
    'user_groups': 'ug',
    'product_statuses': 'ps',
    'order_statuses': 'ostatus',
    'orders_storage': 'storage',     # mapper FKs reference @storage.X
    'collections': 'coll',            # mapper FKs reference @coll.X
    'menus': 'menu',
    'filters': 'filter',
    'discounts': 'discount',
    'product_relations_templates': 'prt',
    'template_previews': 'tpreview',
    'payment_accounts': 'pacct',
}


def _ensure_title_from_localize(row: dict, primary_lang: str = 'en_US') -> None:
    """If `title` (varchar) column is empty/missing AND the row carries
    `localize_infos[lang].title`, derive title from it. Some cms DTOs
    require `title` (attributes_sets, templates, template_previews) but
    mapper only emits `localize_infos`."""
    if row.get('title'):
        return
    li = row.get('localize_infos') or {}
    if not isinstance(li, dict):
        return
    lang_block = li.get(primary_lang) or next(
        (v for v in li.values() if isinstance(v, dict)), {}
    )
    title = (lang_block or {}).get('title')
    if title:
        row['title'] = title


def _ensure_id_token(table: str, row: dict) -> None:
    """Add `id: '@<ns>.<identifier>'` if missing and the table has a known
    namespace AND the row carries an identifier. Also normalize legacy
    namespaces emitted by older mapper revisions to the current canonical
    set (e.g. `@storage.X` → `@storage.X`)."""
    ns = ID_TOKEN_NAMESPACES.get(table)
    if ns is None:
        return
    # Normalize legacy namespace on existing id (mapper drift).
    current_id = row.get('id')
    if isinstance(current_id, str) and current_id.startswith('@'):
        # Split @ns.rest
        rest = current_id[1:].split('.', 1)
        if len(rest) == 2 and rest[0] != ns:
            # Replace only if the row carries identifier matching the rest
            ident = row.get('identifier')
            if ident and rest[1] == ident:
                row['id'] = f'@{ns}.{ident}'
        return
    if current_id is None:
        ident = row.get('identifier')
        if ident:
            row['id'] = f'@{ns}.{ident}'


def build(mapped_path: Path, rules_dir: Path) -> tuple[dict, list[str], list[str]]:
    """Return (blueprint, warnings, errors)."""
    warnings: list[str] = []
    errors: list[str] = []
    columns = _parse_columns_md(rules_dir / 'table-columns.md')
    uniques = _parse_unique_constraints_md(rules_dir / 'unique-constraints.md')
    if not columns:
        errors.append(
            f'table-columns.md not found at {rules_dir}/table-columns.md — '
            f'run scripts/gen-rules.py first.'
        )
        return {}, warnings, errors

    mapped = yaml.safe_load(mapped_path.read_text())
    if not isinstance(mapped, dict):
        errors.append('mapped.yaml root must be a mapping')
        return {}, warnings, errors

    blueprint: dict = {'tables': {}}
    seen_tables: set[str] = set()

    # Hoist top-level tables → tables.*
    for tname in TOP_LEVEL_TABLES:
        rows = mapped.get(tname)
        if isinstance(rows, list) and rows:
            blueprint['tables'].setdefault(tname, []).extend(rows)
            seen_tables.add(tname)

    # Merge nested mapped.tables.* into blueprint.tables.*
    nested = mapped.get('tables') or {}
    if isinstance(nested, dict):
        for tname, rows in nested.items():
            if not isinstance(rows, list) or not rows:
                continue
            blueprint['tables'].setdefault(tname, []).extend(rows)
            seen_tables.add(tname)

    # Auto-bind products to their default template if template_id is missing.
    # Admin shows an empty "Choose template" dropdown otherwise. The default
    # template is mapper-emitted as `product_default` (universal pattern); if
    # the project has a different default, mapper should set template_id
    # explicitly. Universal across verticals — products / dishes / services /
    # rooms / courses all need a render template.
    templates = blueprint['tables'].get('templates') or []
    product_default_token = next(
        (f"@tpl.{t['identifier']}" for t in templates
         if (t.get('identifier') or '').endswith('product_default')),
        None,
    )
    if product_default_token:
        for p in (blueprint['tables'].get('products') or []):
            if not p.get('template_id'):
                p['template_id'] = product_default_token

    # Similar auto-bind for pages and blocks → their default templates.
    page_default_token = next(
        (f"@tpl.{t['identifier']}" for t in templates
         if (t.get('identifier') or '').endswith('page_default')),
        None,
    )
    if page_default_token:
        for p in (blueprint['tables'].get('pages') or []):
            if not p.get('template_id'):
                p['template_id'] = page_default_token
    block_default_token = next(
        (f"@tpl.{t['identifier']}" for t in templates
         if (t.get('identifier') or '').endswith('block_default')),
        None,
    )
    if block_default_token:
        for b in (blueprint['tables'].get('blocks') or []):
            if not b.get('template_id'):
                b['template_id'] = block_default_token

    # Semantic dedup for form_module_config: at this stage rows may carry
    # either `form_id: '@form.X'` or `form_id: '@form.Y'` (or even legacy
    # `form: 'X'`) — composite-UNIQUE dedup by `(module_id, form_id)` runs
    # later and cannot collapse semantically-equivalent rows. Collapse here
    # by `(module_id, normalized_form_token)`.
    def _norm_form_ref(c):
        fid = c.get('form_id') or ''
        if isinstance(fid, str) and fid.startswith('@form.'):
            return fid
        if c.get('form'):
            return f"@form.{c['form']}"
        return fid
    fmc = blueprint['tables'].get('form_module_config') or []
    if fmc:
        seen = set()
        kept = []
        for c in fmc:
            k = (c.get('module_id'), _norm_form_ref(c))
            if k in seen:
                continue
            seen.add(k)
            kept.append(c)
        if len(kept) != len(fmc):
            warnings.append(f"form_module_config: collapsed {len(fmc) - len(kept)} "
                            f"semantic duplicates")
        blueprint['tables']['form_module_config'] = kept

    # Auto-link payment_accounts to the single orders_storage via
    # orders_storage_payment_accounts junction. Admin endpoint
    # /payments/statuses/N/config looks up payment_status_map by going
    # account → storage_payment_account → storage → status_map. Without the
    # junction the UI shows empty dropdowns.
    storages = blueprint['tables'].get('orders_storage') or []
    accounts = blueprint['tables'].get('payment_accounts') or []
    if len(storages) == 1 and accounts:
        store_tok = f"@storage.{storages[0].get('identifier')}"
        junction = blueprint['tables'].setdefault('orders_storage_payment_accounts', [])
        existing = {(j.get('storage_id'), j.get('payment_account_id')) for j in junction}
        for acc in accounts:
            acct_tok = acc.get('id')
            if not acct_tok:
                continue
            key = (store_tok, acct_tok)
            if key in existing:
                continue
            junction.append({
                'storage_id': store_tok,
                'payment_account_id': acct_tok,
            })

    # Auto-bind order_statuses to the single orders_storage if storage_id is
    # missing. Universal — single-storage projects are the common case; any
    # multi-storage project must emit storage_id explicitly.
    storages = blueprint['tables'].get('orders_storage') or []
    if len(storages) == 1 and storages[0].get('identifier'):
        store_tok = f'@storage.{storages[0]["identifier"]}'
        for s in (blueprint['tables'].get('order_statuses') or []):
            if not s.get('storage_id'):
                s['storage_id'] = store_tok

    # Normalize + filter columns per table; dedupe composite-UNIQUE.
    for tname in list(blueprint['tables'].keys()):
        rows = blueprint['tables'][tname]
        if tname not in columns:
            warnings.append(
                f"table '{tname}' is not in the whitelist (table-columns.md) — dropped"
            )
            del blueprint['tables'][tname]
            continue
        allowed = columns[tname]
        cleaned: list[dict] = []
        for row in rows:
            if not isinstance(row, dict):
                continue
            _ensure_id_token(tname, row)
            _normalize_aset_token(row)
            _normalize_table_specific(tname, row)
            if tname in ('attributes_sets', 'templates', 'template_previews'):
                _ensure_title_from_localize(row)
            # forms.processing_type is NOT NULL (DB default missing). Mapper
            # usually emits 'db' / 'email' / 'main'; if missing — default to 'db'.
            if tname == 'forms' and not row.get('processing_type'):
                row['processing_type'] = 'db'
            cleaned.append(_filter_columns(row, allowed))
        # Dedupe by composite-UNIQUE
        total_dropped = 0
        for ukey in (uniques.get(tname) or []):
            cleaned, dropped = _dedupe_rows(cleaned, ukey)
            total_dropped += dropped
        if total_dropped:
            warnings.append(f"{tname}: deduped {total_dropped} composite-UNIQUE duplicates")
        # Defensive dedup by `id` if present (catches LLM-side dups)
        cleaned, dropped_id = _dedupe_rows(cleaned, ['id'])
        if dropped_id:
            warnings.append(f"{tname}: deduped {dropped_id} duplicate ids")
        blueprint['tables'][tname] = cleaned

    # Final counts summary in warnings
    total_rows = sum(len(v) for v in blueprint['tables'].values())
    warnings.append(
        f'built {len(blueprint["tables"])} tables, {total_rows} rows total'
    )
    return blueprint, warnings, errors


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('mapped_yaml')
    parser.add_argument('blueprint_json')
    parser.add_argument('--rules-dir', default=str(_DEFAULT_RULES_DIR),
                        help='directory with rules/generated/*.md')
    args = parser.parse_args()

    mapped_path = Path(args.mapped_yaml)
    if not mapped_path.exists():
        print(f'ERROR: mapped.yaml not found: {mapped_path}', file=sys.stderr)
        return 1
    out_path = Path(args.blueprint_json)
    rules_dir = Path(args.rules_dir)

    blueprint, warnings, errors = build(mapped_path, rules_dir)
    if errors:
        for e in errors:
            print(f'ERROR: {e}', file=sys.stderr)
        return 2

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(blueprint, indent=2, ensure_ascii=False))

    # Warnings sidecar — same naming as the previous AI builder
    sidecar = out_path.with_suffix('.json.builder-warnings.json')
    sidecar.write_text(json.dumps({'warnings': warnings}, indent=2, ensure_ascii=False))

    print(f'Built: {out_path} ({out_path.stat().st_size} bytes)')
    print(f'Tables: {len(blueprint["tables"])}')
    print(f'Warnings: {len(warnings)} → {sidecar.name}')
    for w in warnings[-10:]:
        print(f'  {w}')
    return 0


if __name__ == '__main__':
    sys.exit(main())
