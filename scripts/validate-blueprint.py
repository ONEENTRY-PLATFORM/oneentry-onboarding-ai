#!/usr/bin/env python3
"""validate-blueprint.py — pre-load completeness checker for OneEntry blueprints.

Catches the kind of gaps that silently produce an "empty admin" after a
successful HTTP 200 import — missing slides, unbound menus, dropped tables,
unresolvable @tokens, missing validators, orphan forms.

Each check has a stable code (CHK-NNN) so consumers can suppress individual
checks. Exit codes:
    0  all checks pass (no ERRORs; WARNs OK)
    1  user error (file not found / bad JSON)
    2  one or more ERROR-level checks failed

Usage:
    python3 validate-blueprint.py <blueprint.json> [--mapped <mapped.yaml>] [--strict]
"""
import argparse
import json
import re
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    yaml = None  # mapped.yaml comparison becomes optional


# Severity levels
ERR = 'ERR'
WARN = 'WARN'
INFO = 'INFO'


class Report:
    def __init__(self) -> None:
        self.issues: list[tuple[str, str, str]] = []  # (severity, code, message)

    def add(self, severity: str, code: str, message: str) -> None:
        self.issues.append((severity, code, message))

    def err(self, code: str, message: str) -> None:
        self.add(ERR, code, message)

    def warn(self, code: str, message: str) -> None:
        self.add(WARN, code, message)

    def info(self, code: str, message: str) -> None:
        self.add(INFO, code, message)

    @property
    def errors(self) -> int:
        return sum(1 for s, *_ in self.issues if s == ERR)

    @property
    def warnings(self) -> int:
        return sum(1 for s, *_ in self.issues if s == WARN)


# ---------- individual checks ----------

def _tables(bp: dict) -> dict:
    t = bp.get('tables') or {}
    return t if isinstance(t, dict) else {}


def chk_post_import_coverage(bp: dict, mapped: dict | None, r: Report) -> None:
    """CHK-001 — every `post_import_*` array in mapped.yaml has a matching
    `tables.<x>[]` of equal-or-greater size in the blueprint. Catches the
    case where the builder drops a category of data."""
    if not mapped:
        return
    sidecar_to_tables = {
        'post_import_slides': ['slides'],
        'post_import_menus': ['menus'],
        'post_import_discounts': ['discounts'],
        'post_import_payment_status_maps': ['payment_status_map'],
        'post_import_page_errors': ['page_errors'],
        'post_import_filters': ['filters'],
    }
    tbls = _tables(bp)
    for side, targets in sidecar_to_tables.items():
        side_rows = mapped.get(side) or []
        if not side_rows:
            continue
        for t in targets:
            n_blueprint = len(tbls.get(t) or [])
            if n_blueprint < len(side_rows):
                r.err('CHK-001', (
                    f"{side}[{len(side_rows)}] in mapped.yaml but only "
                    f"{n_blueprint} rows in blueprint.tables.{t} — builder "
                    f'dropped data'
                ))


def chk_guest_user_group(bp: dict, r: Report) -> None:
    """CHK-002 — `guest` user_group MUST be in the blueprint, otherwise the
    storefront cannot resolve anonymous sessions after a clean DB."""
    ugs = _tables(bp).get('user_groups') or []
    if not any((u.get('identifier') == 'guest') for u in ugs):
        r.err('CHK-002', 'user_groups missing the `guest` row — '
                         'storefront anonymous sessions will fail')


def chk_slider_blocks_have_slides(bp: dict, r: Report) -> None:
    """CHK-003 — every visible block on a `forBlocks_slider` attribute_set
    MUST have ≥1 row in slides that references it via block_id."""
    tbls = _tables(bp)
    slider_aset_ids = set()
    for a in (tbls.get('attributes_sets') or []):
        ident = a.get('identifier') or ''
        if ident == 'forBlocks_slider' or 'slider' in ident.lower():
            slider_aset_ids.add(a.get('id'))
    slider_block_tokens = set()
    for b in (tbls.get('blocks') or []):
        if b.get('attribute_set_id') in slider_aset_ids and b.get('is_visible', True):
            slider_block_tokens.add(b.get('id'))
    if not slider_block_tokens:
        return
    slide_block_refs = {s.get('block_id') for s in (tbls.get('slides') or [])}
    for tok in slider_block_tokens:
        if tok not in slide_block_refs:
            r.warn('CHK-003', f'slider block {tok!r} has no slides — admin '
                              f'will show an empty carousel')


def chk_menus_have_pages(bp: dict, r: Report) -> None:
    """CHK-004 — every menu MUST have ≥1 menu_pages_mn binding."""
    tbls = _tables(bp)
    menus = tbls.get('menus') or []
    if not menus:
        return
    mp_refs = {m.get('menu_id') for m in (tbls.get('menu_pages_mn') or [])}
    mc_refs = {m.get('menu_id') for m in (tbls.get('menu_custom_items_mn') or [])}
    for m in menus:
        tok = m.get('id')
        if tok not in mp_refs and tok not in mc_refs:
            r.warn('CHK-004', f"menu {m.get('identifier')!r} has no pages or "
                              f'custom items — admin will show an empty menu')


def chk_discounts_have_triggers(bp: dict, r: Report) -> None:
    """CHK-005 — every discount must have ≥1 discount_conditions row OR
    ≥1 discount_coupons row, otherwise it can never apply."""
    tbls = _tables(bp)
    discounts = tbls.get('discounts') or []
    if not discounts:
        return
    cond_refs = {d.get('discount_id') for d in (tbls.get('discount_conditions') or [])}
    coup_refs = {d.get('discount_id') for d in (tbls.get('discount_coupons') or [])}
    for d in discounts:
        tok = d.get('id')
        if tok not in cond_refs and tok not in coup_refs:
            r.warn('CHK-005', f"discount {d.get('identifier')!r} has no "
                              f'conditions or coupons — will never trigger')


def chk_payment_status_map_complete(bp: dict, r: Report) -> None:
    """CHK-006 — every payment_status_map row must have a non-null
    order_storage_id (FK token) and at least one status_map entry."""
    for psm in (_tables(bp).get('payment_status_map') or []):
        if not psm.get('order_storage_id'):
            r.err('CHK-006', 'payment_status_map row missing order_storage_id')
        if not psm.get('status_map'):
            r.warn('CHK-006', 'payment_status_map row has empty status_map')


def chk_page_errors_have_pages(bp: dict, r: Report) -> None:
    """CHK-007 — every page_errors row must reference a page."""
    for pe in (_tables(bp).get('page_errors') or []):
        if not pe.get('page_id'):
            r.err('CHK-007', f"page_errors code={pe.get('code')} missing page_id")


def chk_tokens_resolvable(bp: dict, r: Report) -> None:
    """CHK-008 — every `@ns.name` token referenced in any FK column must
    appear as an `id` in some row of the same table family."""
    tbls = _tables(bp)
    # Build map: token -> known
    known: set[str] = set()
    for rows in tbls.values():
        for row in rows:
            tid = row.get('id')
            if isinstance(tid, str) and tid.startswith('@'):
                known.add(tid)
    # Scan for unresolved refs. Token grammar matches @ns.name where `name`
    # is a page identifier / block identifier / etc — these may contain dashes
    # (`about-us`, `info-faq`), underscores, dots — anything that's safe to
    # use as a URL slug or SQL identifier fragment.
    token_re = re.compile(r'^@[\w.\-]+$')
    unresolved: dict[str, list[str]] = {}
    for tname, rows in tbls.items():
        for row in rows:
            for k, v in row.items():
                if k == 'id':
                    continue
                if isinstance(v, str) and token_re.match(v) and v not in known:
                    unresolved.setdefault(v, []).append(f'{tname}.{k}')
    for tok, where in unresolved.items():
        r.err('CHK-008',
              f"unresolved token {tok!r} referenced at {', '.join(where[:3])}"
              + ('…' if len(where) > 3 else ''))


def chk_validators_emitted(bp: dict, r: Report) -> None:
    """CHK-009 — every input-form attribute_set (`forForms_*` or `forUsers`)
    must have validators[lang] on each user-input field. Pipeline auto-derives
    them from `rules`; absence means the form will accept anything."""
    asets = _tables(bp).get('attributes_sets') or []
    for a in asets:
        ident = a.get('identifier') or ''
        if not (ident.startswith('forForms_') or ident == 'forUsers'):
            continue
        sch = a.get('schema') or {}
        if not isinstance(sch, dict):
            continue
        for k, item in sch.items():
            if not isinstance(item, dict):
                continue
            atype = item.get('type')
            if atype not in ('string', 'text', 'textarea', 'integer', 'real'):
                continue
            if not item.get('validators'):
                r.warn('CHK-009',
                       f"{ident}.{k} ({atype}) has no validators[lang] — "
                       f"admin form won't enforce rules")
                break  # one warning per set is enough


def chk_listTitles_array(bp: dict, r: Report) -> None:
    """CHK-010 — `listTitles[lang]` must be ARRAY of {value,title}, not dict.
    Frontend `ListFieldsParameters.js:109` checks Array.isArray — dict form
    silently produces an empty dropdown."""
    asets = _tables(bp).get('attributes_sets') or []
    for a in asets:
        ident = a.get('identifier') or ''
        sch = a.get('schema') or {}
        if not isinstance(sch, dict):
            continue
        for k, item in sch.items():
            if not isinstance(item, dict):
                continue
            lt = item.get('listTitles')
            if not isinstance(lt, dict):
                continue
            for lang, lmap in lt.items():
                if isinstance(lmap, dict):
                    r.err('CHK-010', f"{ident}.{k}.listTitles[{lang}] is a "
                                     f"dict — must be an ARRAY")
                    break


def chk_forms_bound(bp: dict, r: Report) -> None:
    """CHK-011 — every form must have a form_module_config row."""
    tbls = _tables(bp)
    forms = tbls.get('forms') or []
    bindings = {fmc.get('form_id') for fmc in (tbls.get('form_module_config') or [])}
    for f in forms:
        tok = f.get('id')
        if tok not in bindings:
            r.warn('CHK-011', f"form {f.get('identifier')!r} has no "
                              f"form_module_config binding")


def chk_pages_hierarchy(bp: dict, r: Report) -> None:
    """CHK-013 — every page except `root` must have a `parent_id`. Without
    parent_id pages render as a flat list in admin → categories aren't
    nested → products bound to them aren't reachable. Caught in user's
    "товаров вообще нет" complaint where products existed but were hidden."""
    import re as _re
    pages = _tables(bp).get('pages') or []
    page_errors = _tables(bp).get('page_errors') or []
    # Any page referenced by an HTTP error code (404/500/503/…) is a
    # top-level error-handler page by definition; the admin tree intentionally
    # sits them at root. Build the exemption set from data, not a hard list.
    error_page_ids = set()
    for pe in page_errors:
        pid = pe.get('page_id') or pe.get('page')
        if pid:
            error_page_ids.add(pid if isinstance(pid, str) else str(pid))
    # Universal error-page-identifier pattern (covers `not-found`, `404`,
    # `offline`, `maintenance`, `server-error`, `forbidden`, …).
    error_ident_rx = _re.compile(
        r'^(root|404|403|500|503|not.?found|page.?not.?found|error|server.?error|'
        r'offline|maintenance|forbidden|unauthorized|access.?denied)$',
        _re.IGNORECASE,
    )
    for p in pages:
        ident = p.get('identifier') or ''
        if not ident:
            continue
        if error_ident_rx.match(ident):
            continue
        # Cross-check the page_errors → page_id table
        page_token = p.get('id') or f"@page.{ident}"
        if page_token in error_page_ids:
            continue
        if not p.get('parent_id'):
            r.err('CHK-013', f"page {ident!r} has no parent_id — will not "
                             f"appear nested in admin catalog tree")


def chk_discount_dates(bp: dict, r: Report) -> None:
    """CHK-014 — admin discount editor blocks "Save" if start_date / end_date
    are missing ("Data is not valid — saving is disabled"). DB columns are
    nullable but admin UX requires them."""
    for d in (_tables(bp).get('discounts') or []):
        ident = d.get('identifier')
        if not d.get('start_date'):
            r.err('CHK-014', f"discount {ident!r} missing start_date — "
                             f"admin save button will be disabled")
        if not d.get('end_date'):
            r.err('CHK-014', f"discount {ident!r} missing end_date — "
                             f"admin save button will be disabled")


def chk_unique_identifiers(bp: dict, r: Report) -> None:
    """CHK-015 — duplicate identifier in tables where it must be UNIQUE.
    `user_groups`/`menus`/`filters`/`discounts`/`collections`/`pages` all
    have implicit identifier uniqueness in admin (even when DB allows dups)."""
    for table in ('user_groups', 'menus', 'filters', 'discounts',
                  'collections', 'pages'):
        rows = _tables(bp).get(table) or []
        seen: dict[str, int] = {}
        for row in rows:
            ident = row.get('identifier')
            if not ident:
                continue
            seen[ident] = seen.get(ident, 0) + 1
        for ident, n in seen.items():
            if n > 1:
                r.err('CHK-015', f"{table}: identifier {ident!r} appears "
                                  f"{n} times — admin shows duplicates")


def chk_payment_status_map_identifier(bp: dict, r: Report) -> None:
    """CHK-016 — payment_status_map.identifier must be non-empty so admin can
    pick the provider in /payments/statuses/N/config dropdown."""
    for psm in (_tables(bp).get('payment_status_map') or []):
        if not (psm.get('identifier') or '').strip():
            r.err('CHK-016', 'payment_status_map row has empty identifier — '
                              'admin "Statuses Config" cannot list it')


def chk_discount_value_complete(bp: dict, r: Report) -> None:
    """CHK-017 — discount.discount_value must have discountType + applicability
    + value. cms DiscountValueConfigDto requires them. Without these admin
    shows 'Тип не выбран' and blocks save."""
    for d in (_tables(bp).get('discounts') or []):
        dv = d.get('discount_value') or {}
        ident = d.get('identifier')
        if 'discountType' not in dv:
            r.err('CHK-017', f"discount {ident!r} discount_value missing "
                              f"discountType — admin save disabled")
        if 'applicability' not in dv:
            r.err('CHK-017', f"discount {ident!r} discount_value missing "
                              f"applicability (TO_ORDER/TO_PRODUCT/...)")
        if 'value' not in dv:
            r.err('CHK-017', f"discount {ident!r} discount_value missing "
                              f"value (numeric amount/percent)")


def chk_no_rating_in_non_review_forms(bp: dict, r: Report) -> None:
    """CHK-018 — `rating` field must not appear in any forForms_* schema
    except forForms_review_rating. Otherwise feedback/contact forms render
    a star UI which is semantically wrong."""
    asets = _tables(bp).get('attributes_sets') or []
    for a in asets:
        ident = a.get('identifier') or ''
        if not ident.startswith('forForms_') or ident == 'forForms_review_rating':
            continue
        sch = a.get('schema') or {}
        if not isinstance(sch, dict):
            continue
        for k, item in sch.items():
            if not isinstance(item, dict):
                continue
            if item.get('identifier') == 'rating' or item.get('type') == 'rating':
                r.err('CHK-018', f"{ident} has `rating` attribute — "
                                  f"should be split into forForms_review_rating")
                break


def chk_template_previews_title(bp: dict, r: Report) -> None:
    """CHK-019 — template_previews.title must be non-empty (rendered in
    /settings tab as Name column)."""
    for tp in (_tables(bp).get('template_previews') or []):
        if not (tp.get('title') or '').strip():
            r.warn('CHK-019', f"template_preview {tp.get('identifier')!r} "
                              f"has empty title")


def chk_orphan_form_asets(bp: dict, r: Report) -> None:
    """CHK-020 — every `forForms_X` aset must have a corresponding form with
    identifier=X. Otherwise aset is dead weight in admin."""
    asets = _tables(bp).get('attributes_sets') or []
    form_idents = {f.get('identifier') for f in (_tables(bp).get('forms') or [])}
    for a in asets:
        ident = a.get('identifier') or ''
        if not ident.startswith('forForms_'):
            continue
        form_name = ident[len('forForms_'):]
        if form_name not in form_idents:
            r.warn('CHK-020', f"aset {ident!r} has no matching form "
                              f"`{form_name}` — orphan schema")


def chk_block_aset_data_filled(bp: dict, r: Report) -> None:
    """CHK-021 — every visible block with a non-empty attribute_set schema
    should have data in its attributes_sets. Empty data on a 6-field schema
    is the "block looks empty in admin" complaint."""
    asets = {a.get('id'): a for a in (_tables(bp).get('attributes_sets') or [])}
    for b in (_tables(bp).get('blocks') or []):
        aset_ref = b.get('attribute_set_id')
        aset = asets.get(aset_ref)
        if not aset:
            continue
        sch = aset.get('schema') or {}
        if not isinstance(sch, dict) or not sch:
            continue
        attrs = (b.get('attributes_sets') or {})
        any_lang_has_data = any(
            isinstance(v, dict) and any(v.values()) for v in attrs.values()
        )
        if not any_lang_has_data:
            r.warn('CHK-021', f"block {b.get('identifier')!r} has "
                              f"{len(sch)}-field schema but empty data")


def chk_slider_block_nested(bp: dict, r: Report) -> None:
    """CHK-022 — for slider blocks that semantically expect nested sub-items
    (`category_grid`, `mega_menu`), slides.parent_id should be used. If all
    slides for such a block are flat (no parent_id), the admin can't show the
    expected drill-down."""
    asets = {a.get('id'): a for a in (_tables(bp).get('attributes_sets') or [])}
    nested_aset_idents = {'forBlocks_category_grid', 'forBlocks_mega_menu'}
    for b in (_tables(bp).get('blocks') or []):
        aset = asets.get(b.get('attribute_set_id'))
        if not aset or aset.get('identifier') not in nested_aset_idents:
            continue
        slides = [s for s in (_tables(bp).get('slides') or [])
                  if s.get('block_id') == b.get('id')]
        if slides and not any(s.get('parent_id') for s in slides):
            r.info('CHK-022', f"block {b.get('identifier')!r} ({aset.get('identifier')}) "
                              f"has {len(slides)} flat slides; consider nested "
                              f"parent_id for sub-categories")


def chk_catalog_hub_pages(bp: dict, r: Report) -> None:
    """CHK-025 — any page that has a `catalog_page` descendant (at any depth)
    must itself be `catalog_page` (general_type_id=4). cms admin catalog list
    walks only ONE level deep when looking for catalog descendants, so any
    `common_page` (=17) hub whose direct children are themselves common-page
    hubs gets hidden. See rules/oneentry-invariants.md §8.5."""
    pages = _tables(bp).get('pages') or []
    by_id_or_ident = {}
    for p in pages:
        if p.get('id'):
            by_id_or_ident[p['id']] = p
        if p.get('identifier'):
            by_id_or_ident[p['identifier']] = p
    children_of = {}
    for p in pages:
        parent = p.get('parent_id')
        if isinstance(parent, str):
            parent = parent.replace('@page.', '')
        if parent:
            children_of.setdefault(parent, []).append(p)
    def _has_catalog_descendant(ident, seen=None):
        if seen is None:
            seen = set()
        if ident in seen:
            return False
        seen.add(ident)
        for c in children_of.get(ident, []):
            if c.get('general_type_id') == 4 or c.get('general_type_marker') == 'catalog_page':
                return True
            ci = c.get('identifier')
            if ci and _has_catalog_descendant(ci, seen):
                return True
        return False
    EXEMPT = {'root', '', 'cart', 'checkout', 'favorites', 'account',
              'wishlist', 'profile', '404', '500', '503', 'offline',
              'error', 'not-found', 'login', 'signup', 'forgot-password'}
    for p in pages:
        ident = p.get('identifier') or ''
        if not ident or ident in EXEMPT:
            continue
        gtid = p.get('general_type_id')
        if gtid == 4 or p.get('general_type_marker') == 'catalog_page':
            continue
        if gtid == 3:
            continue
        if _has_catalog_descendant(ident):
            r.err('CHK-025', f"page {ident!r} has catalog_page descendants but "
                             f"is general_type_id={gtid} (not 4) — cms admin "
                             f"catalog tree will hide its branch")


def chk_menu_parent_id_namespace(bp: dict, r: Report) -> None:
    """CHK-024 — menu_pages_mn.parent_id and menu_custom_items_mn.parent_id
    MUST reference a page token (`@page.X`), not a join-table token. The cms
    admin reads `parentId` as a page id when building the nested menu tree
    (cms_frontend/views/menu/MenuManagement.js:75). Using `@mp.X` / `@mci.X`
    silently breaks the hierarchy — see rules/menus-setup.md §3.0."""
    for table in ('menu_pages_mn', 'menu_custom_items_mn'):
        for row in (_tables(bp).get(table) or []):
            pid = row.get('parent_id')
            if not isinstance(pid, str) or not pid.startswith('@'):
                continue
            if pid.startswith('@page.'):
                continue
            # menu_custom_items_mn may legitimately nest under another
            # custom item — `@mci.X` is acceptable there ONLY when the
            # parent is purely a grouping node (no page).
            if table == 'menu_custom_items_mn' and pid.startswith('@mci.'):
                continue
            r.err('CHK-024', f"{table} row references parent_id={pid!r}; "
                             f"cms admin expects a page token (@page.X) — "
                             f"using @mp./@mci. tokens for menu_pages_mn.parent_id "
                             f"silently flattens the admin tree")


def chk_user_data_form_flags(bp: dict, r: Report) -> None:
    """CHK-023 — form_module_config rows bound to the Users module (module_id=9)
    for data-capture forms (`type=data`, or identifier prefixed with
    `profile_`/`my_`/`account_`) must enable BOTH `is_global=true` AND
    `view_only_user_data=true`. Without these flags the storefront cannot
    render the form per-user and users see each other's submissions —
    a privacy + UX bug. See rules/standard-entities.md §"Per-user data-form
    flags"."""
    USERS_MODULE_ID = 9
    forms_by_token = {}
    for f in (_tables(bp).get('forms') or []):
        tok = f.get('id') or (f"@form.{f['identifier']}" if f.get('identifier') else None)
        if tok:
            forms_by_token[tok] = f
    for fmc in (_tables(bp).get('form_module_config') or []):
        if fmc.get('module_id') != USERS_MODULE_ID:
            continue
        fid = fmc.get('form_id') or (f"@form.{fmc['form']}" if fmc.get('form') else None)
        form = forms_by_token.get(fid) if fid else None
        ident = (form or {}).get('identifier') or (fid or '').replace('@form.', '')
        is_data_form = (form and form.get('type') == 'data') or \
                       ident.startswith(('profile', 'my_', 'my-', 'account'))
        if not is_data_form:
            continue
        if not fmc.get('is_global') or not fmc.get('view_only_user_data'):
            r.err('CHK-023',
                  f"form_module_config for {ident!r} (users module, type=data) "
                  f"must set is_global=true AND view_only_user_data=true "
                  f"(got is_global={fmc.get('is_global')!r}, "
                  f"view_only_user_data={fmc.get('view_only_user_data')!r})")


def chk_admin_required_fields_manifest(bp: dict, r: Report,
                                        rules_dir: Path | None = None) -> None:
    """CHK-100 — read `rules/generated/admin-required-fields.json` and verify
    every required field is populated on every row of the matching whitelist
    table. Manifest is auto-generated from cms DTO decorators by
    `gen-admin-required-fields.py`.

    Decouples validator from manual guessing — when cms changes its DTOs,
    re-run `gen-admin-required-fields.py` and the validator picks up the
    new requirements automatically.
    """
    if rules_dir is None:
        rules_dir = Path(__file__).resolve().parent.parent / 'rules' / 'generated'
    manifest_path = rules_dir / 'admin-required-fields.json'
    if not manifest_path.exists():
        r.warn('CHK-100', f'manifest not found at {manifest_path} — run '
                          f'gen-admin-required-fields.py to enable this check')
        return
    try:
        manifest = json.loads(manifest_path.read_text())
    except (json.JSONDecodeError, OSError) as exc:
        r.warn('CHK-100', f'failed to load manifest: {exc}')
        return

    tbls = _tables(bp)
    for tname, info in manifest.items():
        fields = info.get('fields') or {}
        required = [f for f, meta in fields.items() if meta.get('required')]
        if not required:
            continue
        # Nested manifest key (e.g. `discounts.discount_value`) → look up the
        # parent table and the nested key.
        if '.' in tname:
            parent, nested = tname.split('.', 1)
            rows = tbls.get(parent) or []
            for row in rows:
                nested_obj = row.get(nested) or {}
                for f in required:
                    # Manifest uses snake_case; nested DTOs often store camelCase.
                    camel = re.sub(r'_([a-z])', lambda m: m.group(1).upper(), f)
                    if not nested_obj.get(f) and not nested_obj.get(camel):
                        r.err('CHK-100',
                              f"{parent}[{row.get('identifier')!r}].{nested}.{f} "
                              f"required by cms DTO but missing")
            continue
        rows = tbls.get(tname) or []
        for row in rows:
            for f in required:
                camel = re.sub(r'_([a-z])', lambda m: m.group(1).upper(), f)
                if row.get(f) in (None, '', []) and row.get(camel) in (None, '', []):
                    ident = row.get('identifier') or row.get('id') or '<unknown>'
                    r.err('CHK-100',
                          f"{tname}[{ident!r}].{f} required by cms DTO but missing")


def chk_invalid_listType(bp: dict, r: Report) -> None:
    """CHK-012 — listType allowed values are `flat`/`nested` only (for
    entity-typed). `single`/`multiple` rejected — use `multiselect: true`."""
    asets = _tables(bp).get('attributes_sets') or []
    for a in asets:
        sch = a.get('schema') or {}
        if not isinstance(sch, dict):
            continue
        for k, item in sch.items():
            if isinstance(item, dict) and item.get('listType') in ('single', 'multiple'):
                r.warn('CHK-012',
                       f"{a.get('identifier')}.{k}.listType="
                       f"{item['listType']!r} is invalid — use multiselect")
                break


CHECKS = [
    ('CHK-001 post-import coverage', chk_post_import_coverage),
    ('CHK-002 guest user_group',     lambda bp, m, r: chk_guest_user_group(bp, r)),
    ('CHK-003 slider has slides',    lambda bp, m, r: chk_slider_blocks_have_slides(bp, r)),
    ('CHK-004 menus have pages',     lambda bp, m, r: chk_menus_have_pages(bp, r)),
    ('CHK-005 discounts triggerable',lambda bp, m, r: chk_discounts_have_triggers(bp, r)),
    ('CHK-006 payment_status_map',   lambda bp, m, r: chk_payment_status_map_complete(bp, r)),
    ('CHK-007 page_errors',          lambda bp, m, r: chk_page_errors_have_pages(bp, r)),
    ('CHK-008 tokens resolvable',    lambda bp, m, r: chk_tokens_resolvable(bp, r)),
    ('CHK-009 validators emitted',   lambda bp, m, r: chk_validators_emitted(bp, r)),
    ('CHK-010 listTitles array',     lambda bp, m, r: chk_listTitles_array(bp, r)),
    ('CHK-011 forms bound',          lambda bp, m, r: chk_forms_bound(bp, r)),
    ('CHK-012 invalid listType',     lambda bp, m, r: chk_invalid_listType(bp, r)),
    ('CHK-013 pages hierarchy',      lambda bp, m, r: chk_pages_hierarchy(bp, r)),
    ('CHK-014 discount dates',       lambda bp, m, r: chk_discount_dates(bp, r)),
    ('CHK-015 unique identifiers',   lambda bp, m, r: chk_unique_identifiers(bp, r)),
    ('CHK-016 payment_status_map identifier', lambda bp, m, r: chk_payment_status_map_identifier(bp, r)),
    ('CHK-017 discount_value complete',       lambda bp, m, r: chk_discount_value_complete(bp, r)),
    ('CHK-018 rating only in review form',    lambda bp, m, r: chk_no_rating_in_non_review_forms(bp, r)),
    ('CHK-019 template_previews title',       lambda bp, m, r: chk_template_previews_title(bp, r)),
    ('CHK-020 orphan form asets',             lambda bp, m, r: chk_orphan_form_asets(bp, r)),
    ('CHK-021 block aset data filled',        lambda bp, m, r: chk_block_aset_data_filled(bp, r)),
    ('CHK-022 slider nested sub-items',       lambda bp, m, r: chk_slider_block_nested(bp, r)),
    ('CHK-023 user-data form flags',          lambda bp, m, r: chk_user_data_form_flags(bp, r)),
    ('CHK-024 menu parent_id namespace',      lambda bp, m, r: chk_menu_parent_id_namespace(bp, r)),
    ('CHK-025 catalog hub general_type_id',   lambda bp, m, r: chk_catalog_hub_pages(bp, r)),
    ('CHK-100 admin DTO required (manifest)', lambda bp, m, r: chk_admin_required_fields_manifest(bp, r)),
]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('blueprint_json')
    parser.add_argument('--mapped', help='optional path to mapped.yaml for '
                                          'coverage comparison')
    parser.add_argument('--strict', action='store_true',
                        help='exit 2 also when WARN-level issues exist')
    args = parser.parse_args()

    bp_path = Path(args.blueprint_json)
    if not bp_path.exists():
        print(f'ERROR: blueprint not found: {bp_path}', file=sys.stderr)
        return 1
    try:
        bp = json.loads(bp_path.read_text())
    except json.JSONDecodeError as e:
        print(f'ERROR: invalid JSON: {e}', file=sys.stderr)
        return 1

    mapped = None
    if args.mapped:
        if yaml is None:
            print('WARNING: pyyaml not installed — --mapped ignored', file=sys.stderr)
        else:
            mp = Path(args.mapped)
            if mp.exists():
                mapped = yaml.safe_load(mp.read_text())
            else:
                print(f'WARNING: mapped.yaml not found: {mp}', file=sys.stderr)

    report = Report()
    for name, check in CHECKS:
        try:
            check(bp, mapped, report)
        except Exception as e:
            report.warn('CHK-???', f'{name} crashed: {e}')

    # Print report
    for severity, code, msg in report.issues:
        print(f'[{severity}] {code}: {msg}')
    total = len(report.issues)
    print()
    print(f'Summary: {report.errors} ERR · {report.warnings} WARN · '
          f'{total - report.errors - report.warnings} INFO')
    if report.errors > 0:
        return 2
    if args.strict and report.warnings > 0:
        return 2
    return 0


if __name__ == '__main__':
    sys.exit(main())
