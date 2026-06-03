#!/usr/bin/env python3
"""
post-import-orchestrator.py — automation of out-of-whitelist tasks after a successful blueprint-import.

What IS AUTOMATED via REST API:
  1. user-permissions for the `user` group — standard set for registered users
     (read catalog, submit forms, edit profile, orders).
  2. integration-collections — create empty collections for FAQ/Stores/Brands/etc.
     Rows are added by an admin or via a separate script.

What is NOT automated (with a detailed warning):
  3. form_module_config (binding of data-forms to the Users module) — requires PUT /forms/:id
     with formModuleConfigs[], the DTO is non-trivial. Left as a manual step.
  4. payment_accounts (Stripe/Yookassa) — customer secrets.
  5. SMTP/notice-service configs — secrets.
  6. Email templates — partially automatable, but requires SMTP configuration.

Endpoints (verified against the OneEntry Platform):
  - POST /api/admin/auth/login
  - GET  /api/admin/user-permissions
  - POST /api/admin/user-permissions
  - GET  /api/admin/user-groups
  - GET  /api/admin/user-groups/:id/permissions
  - PUT  /api/admin/user-groups/:groupId/permissions/:permissionId/change (toggle)
  - GET  /api/admin/integration-collections
  - POST /api/admin/integration-collections

Usage:
    python3 post-import-orchestrator.py \\
        <blueprint.json> <mapped.yaml> \\
        --cms-url http://localhost:3013/api/admin \\
        --login test --password 1-1 \\
        [--dry-run] [--project-root .]
"""
import sys, os, json, yaml, argparse, time
from pathlib import Path
import urllib.request, urllib.parse, urllib.error


# Standard set of permissions for registered users in e-commerce
USER_GROUP_PERMISSIONS = [
    # Catalog read access (anonymous + registered)
    {'path': '/api/content/pages',                              'section': 'pages',     'rule_add': 'readAll'},
    {'path': '/api/content/pages/{id}',                         'section': 'pages',     'rule_add': 'readAll'},
    {'path': '/api/content/pages/{url}/children',               'section': 'pages',     'rule_add': 'readAll'},
    {'path': '/api/content/products',                           'section': 'products',  'rule_add': 'readAll'},
    {'path': '/api/content/products/{id}',                      'section': 'products',  'rule_add': 'readAll'},
    {'path': '/api/content/blocks/{marker}/products',           'section': 'blocks',    'rule_add': 'readAll'},
    # Form submission
    {'path': '/api/content/form-data',                          'section': 'forms',     'rule_add': 'add'},
    # Own profile
    {'path': '/api/content/users/me',                           'section': 'users',     'rule_add': 'readAll+change'},
    # Orders
    {'path': '/api/content/orders',                             'section': 'orders',    'rule_add': 'readAll+add'},
    {'path': '/api/content/orders/{id}',                        'section': 'orders',    'rule_add': 'readAll'},
]


def build_rules(rule_add):
    """Build the rules structure for user_permissions from a shorthand."""
    base = {'permissions': {'readAllRule': 0, 'readRestrictionRule': 0,
                            'addRule': 0, 'changeRule': False, 'deleteRule': False},
            'additionalData': {}}
    if 'readAll' in rule_add:
        base['permissions']['readAllRule'] = 1
    if 'add' in rule_add:
        base['permissions']['addRule'] = 1
    if 'change' in rule_add:
        base['permissions']['changeRule'] = True
    if 'delete' in rule_add:
        base['permissions']['deleteRule'] = True
    return base


def http(method, url, token=None, data=None):
    """HTTP call returning (status, body)."""
    headers = {'Content-Type': 'application/json', 'Accept': 'application/json'}
    if token:
        headers['Authorization'] = f'Bearer {token}'
    body = json.dumps(data).encode() if data is not None else None
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            raw = resp.read().decode()
            return resp.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        try:
            err = json.loads(e.read().decode() or '{}')
        except Exception:
            err = {}
        return e.code, err
    except Exception as e:
        return 0, {'error': str(e)}


def login(cms_url, login_, password):
    status, resp = http('POST', f'{cms_url}/api/admin/auth/login', data={'login': login_, 'password': password})
    if status not in (200, 201):
        raise RuntimeError(f'Login failed: HTTP {status} {resp}')
    return resp.get('accessToken')


def list_pages(cms_url, token, path, page_param=False, limit=200, extra_query=''):
    """GET with pagination handling. On HTTP 500 from `/api/admin/pages*` falls
    back to direct SQL via `docker exec cms-sb-db psql` — works around a known
    cms bug where `pageElasticService` is null at request time and crashes the
    page listing endpoints.

    The fallback only applies to local-docker setups (it tries `docker exec`).
    """
    url = f'{cms_url}{path}'
    qs = []
    if page_param:
        qs.append(f'page=1&limit={limit}')
    if extra_query:
        qs.append(extra_query)
    if qs:
        url += '?' + '&'.join(qs)
    status, resp = http('GET', url, token=token)
    if status == 200:
        if isinstance(resp, list):
            return resp
        if isinstance(resp, dict):
            return resp.get('items') or resp.get('rows') or resp.get('data') or []
        return []
    # ─── SQL fallback for the broken /pages endpoint ──────────────────────
    # Detect by path. Other endpoints raise the same 500 occasionally; we cover
    # the common ones used by the orchestrator.
    fallback_query = None
    if path.startswith('/api/admin/pages'):
        fallback_query = "SELECT id, identifier FROM pages ORDER BY id;"
    elif path.startswith('/api/admin/products'):
        fallback_query = "SELECT id, identifier FROM products ORDER BY id LIMIT 1000;"
    elif path.startswith('/api/admin/blocks'):
        fallback_query = "SELECT id, identifier FROM blocks ORDER BY id;"
    if not fallback_query:
        return []
    try:
        import subprocess
        result = subprocess.run(
            ['docker', 'exec', 'cms-sb-db', 'psql', '-U', 'postgres',
             '-d', 'test_db_cms3', '-tAF|', '-c', fallback_query],
            capture_output=True, text=True, timeout=10,
        )
        if result.returncode != 0:
            return []
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip()
            if not line or '|' not in line:
                continue
            id_s, ident = line.split('|', 1)
            try:
                rows.append({'id': int(id_s), 'identifier': ident})
            except ValueError:
                continue
        return rows
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return []


# WARNING: full list of sections from api_section_type_enum in the DB (verified via SELECT DISTINCT).
# If sections= does not cover all of them — the API SQL filter strips permissions, and the lookup
# returns an empty list → orchestrator thinks nothing exists and creates duplicates.
PERMISSION_SECTIONS = [
    'admins', 'attributes-sets', 'blocks', 'events', 'files', 'form-data', 'forms',
    'general-types', 'immutable-settings', 'integration-collections', 'locales',
    'menus', 'orders', 'orders-storage', 'pages', 'payments', 'product-statuses',
    'products', 'settings-general', 'subscriptions', 'system', 'template-previews',
    'templates', 'user-groups', 'users', 'users-auth-providers',
]


def paginated_get(cms_url, token, path, sections=None, limit=500):
    """GET with offset-based pagination.

    WARNING: user-permissions API:
      - does NOT honor `?page=` (ignored), uses `?offset=`+`?limit=`
      - requires `?sections=`, otherwise HTTP 500 (for /user-groups/:id/permissions)
        or returns empty items (for /user-permissions)
      - returns {items[], total} — total is correct, items is capped by limit
    """
    all_items = []
    offset = 0
    sec_q = ('sections=' + ','.join(sections or PERMISSION_SECTIONS))
    while True:
        url = f'{cms_url}{path}?offset={offset}&limit={limit}&{sec_q}'
        status, resp = http('GET', url, token=token)
        if status != 200:
            break
        if isinstance(resp, list):
            items = resp
            total = len(items)
        elif isinstance(resp, dict):
            items = resp.get('items', [])
            total = resp.get('total') if isinstance(resp.get('total'), int) else len(all_items) + len(items)
        else:
            items = []
            total = 0
        if not items:
            break
        all_items.extend(items)
        if len(all_items) >= total:  # collected everything
            break
        offset += limit
        if offset > 5000:  # safety
            break
    return all_items


def list_all_user_permissions(cms_url, token):
    """GET /user-permissions with the required ?sections= and pagination."""
    return paginated_get(cms_url, token, '/api/admin/user-permissions', PERMISSION_SECTIONS)


def list_user_group_permissions(cms_url, token, group_id):
    """GET /user-groups/:id/permissions — requires ?sections=, otherwise HTTP 500."""
    return paginated_get(cms_url, token, f'/api/admin/user-groups/{group_id}/permissions',
                         PERMISSION_SECTIONS)


def lookup_user_group(cms_url, token, identifier):
    """Returns {'id': N, 'identifier': 'user'} or None."""
    groups = list_pages(cms_url, token, '/api/admin/user-groups', page_param=True)
    if not groups:
        # Sometimes a request without pagination is needed
        _, resp = http('GET', f'{cms_url}/api/admin/user-groups', token=token)
        if isinstance(resp, dict):
            groups = resp.get('items') or []
    for g in groups:
        if g.get('identifier') == identifier:
            return g
    return None


def task_user_permissions(cms_url, token, log, dry_run):
    """⚠ DEPRECATED as of 2026-05-21.

    `user_permissions` and `user_group_permissions_mn` are now INSIDE the
    24-table blueprint whitelist with NATURAL_KEYS upsert semantics
    (`(path, section)` and `(group_id, permission_id)` respectively).
    The mapper should emit these rows directly into `blueprint.tables.*` and
    the loader will upsert idempotently — no post-import REST calls needed.

    This task is kept as a **fallback** for legacy mapped.yaml that doesn't
    populate the new whitelist tables, but for any new project it should be
    a no-op (no `user_permissions` in `mapped`).

    See `agents_datasets/agents/entity-mapper.md` Step 2 "Permissions for
    user_groups" for the in-blueprint emission template.
    """
    log.append('## 1. User group permissions (⚠ DEPRECATED — prefer in-blueprint emission since 2026-05-21)\n')
    user_group = lookup_user_group(cms_url, token, 'user')
    if not user_group:
        log.append("  SKIPPED: user_group 'user' not found in OneEntry (blueprint should have created it)\n")
        return 0, 0, 1
    ug_id = user_group['id']
    log.append(f"  user_group 'user' id={ug_id}\n")

    # Existing permissions (requires ?sections=...)
    existing = list_all_user_permissions(cms_url, token)
    existing_by_path = {p.get('path'): p for p in existing}
    log.append(f"  Found existing user_permissions: {len(existing_by_path)}\n")

    # Already-bound permissions to group
    bound = list_user_group_permissions(cms_url, token, ug_id)
    bound_ids = {p.get('id') for p in bound}
    log.append(f"  Already bound to user group: {len(bound_ids)}\n")

    ok, fail, skip = 0, 0, 0
    for perm_cfg in USER_GROUP_PERMISSIONS:
        path = perm_cfg['path']
        rules = build_rules(perm_cfg['rule_add'])

        # 1. Find or create the permission
        if path in existing_by_path:
            perm_id = existing_by_path[path].get('id')
            log.append(f"  permission exists id={perm_id}: {path}\n")
        else:
            if dry_run:
                log.append(f"  [DRY] POST /user-permissions {path}\n")
                ok += 1
                continue
            create_body = {
                'path': path,
                'section': perm_cfg['section'],
                'localizeInfos': {'en_US': {'title': path}},
                'rules': rules,
            }
            status, resp = http('POST', f'{cms_url}/api/admin/user-permissions',
                                token=token, data=create_body)
            if status in (200, 201):
                perm_id = resp.get('id')
                log.append(f"  OK created permission id={perm_id}: {path}\n")
                ok += 1
            else:
                log.append(f"  FAIL create permission {path}: HTTP {status} {resp}\n")
                fail += 1
                continue

        # 2. Bind to the user group (if not already bound)
        if perm_id in bound_ids:
            log.append(f"      already bound to user group\n")
            continue
        if dry_run:
            log.append(f"      [DRY] PUT /user-groups/{ug_id}/permissions/{perm_id}/change\n")
            continue
        status, resp = http('PUT',
                            f'{cms_url}/api/admin/user-groups/{ug_id}/permissions/{perm_id}/change',
                            token=token)
        if status in (200, 201, 204):
            log.append(f"      OK bound to user group (HTTP {status})\n")
        else:
            log.append(f"      FAIL bind: HTTP {status} {resp}\n")
            fail += 1

    return ok, fail, skip


def task_integration_collections(cms_url, token, project_root, mapped, log, dry_run):
    """⚠ DEPRECATED as of 2026-05-21.

    `collections` and `collection_rows` are now INSIDE the 24-table whitelist.
    Mapper Step 9.8 emits rows directly into `blueprint.tables.collections` and
    `blueprint.tables.collection_rows`; loader upserts collections by `identifier`
    and applies skip-if-parent-has-children for rows.

    This task creates EMPTY collections via the legacy `/integration-collections`
    REST endpoint. It is kept as a fallback for projects whose mapped.yaml does
    not yet populate the whitelist entries.
    """
    log.append('\n## 2. Integration collections (⚠ DEPRECATED — prefer in-blueprint emission since 2026-05-21)\n')

    # Search for data files in the project
    candidates = []
    for pattern, coll_name in [('*faq*.ts', 'faq'), ('*store*.ts', 'stores'),
                                ('*brand*.ts', 'brands')]:
        for f in Path(project_root).rglob(pattern):
            if 'node_modules' in str(f) or '.next' in str(f):
                continue
            candidates.append((coll_name, f))
            break

    if not candidates:
        log.append("  no data files for collections (FAQ/stores/brands)\n")
        return 0, 0, 1

    # Existing collections — to avoid duplicates
    existing = list_pages(cms_url, token, '/api/admin/integration-collections', page_param=True)
    existing_idents = {c.get('identifier') for c in existing}
    log.append(f"  Existing collections: {sorted(existing_idents) or '(none)'}\n")

    ok, fail = 0, 0
    for coll_name, data_file in candidates:
        if coll_name in existing_idents:
            log.append(f"  '{coll_name}' already exists (from {data_file.name})\n")
            continue
        if dry_run:
            log.append(f"  [DRY] POST /integration-collections '{coll_name}' from {data_file.name}\n")
            ok += 1
            continue
        body = {
            'identifier': coll_name,
            'localizeInfos': {'en_US': {'title': coll_name.title()}},
        }
        status, resp = http('POST', f'{cms_url}/api/admin/integration-collections',
                            token=token, data=body)
        if status in (200, 201):
            log.append(f"  OK created collection '{coll_name}' id={resp.get('id')} "
                       f"(rows must be added separately from {data_file.name})\n")
            ok += 1
        else:
            log.append(f"  FAIL '{coll_name}': HTTP {status} {resp}\n")
            fail += 1
    return ok, fail, 0


USERS_MODULE_ID = 9  # fixed ID of the Users module in OneEntry (see modules table)


def find_users_module_id(cms_url, token):
    """Find the id of the 'users' module via GET /modules. Falls back to 9 (standard)."""
    status, resp = http('GET', f'{cms_url}/api/admin/modules?limit=100', token=token)
    if status != 200:
        return USERS_MODULE_ID
    items = resp.get('items') if isinstance(resp, dict) else resp
    if isinstance(items, list):
        for m in items:
            if m.get('identifier') == 'users':
                return m.get('id', USERS_MODULE_ID)
    return USERS_MODULE_ID


def task_form_module_config(cms_url, token, mapped, log, dry_run):
    """⚠ DEPRECATED as of 2026-05-21.

    `form_module_config` is now INSIDE the 24-table whitelist. Mapper Step 9.9
    emits config rows directly into `blueprint.tables.form_module_config` with
    composite UNIQUE `(module_id, form_id)` deduplication in builder Step 13.5.

    This task uses `PUT /api/admin/forms/:id` with `formModuleConfigs[]` as a
    fallback path that reads from `mapped.forms[]` (where mapper records
    `type: 'data'` forms that should be attached to module 9 (Users)).

    Keep until all mapper-emitted projects use the new in-blueprint emission.

    Endpoint: PUT /api/admin/forms/:id accepts a body with all form fields +
    formModuleConfigs[{moduleId, formId, entityIdentifiers}]. The service
    replaces all configs at once (see admin-forms.service.ts save() method).
    """
    log.append('\n## 3. Form module config (⚠ DEPRECATED — prefer in-blueprint emission since 2026-05-21)\n')
    data_forms = [f for f in (mapped.get('forms') or [])
                  if f.get('type') == 'data']
    if not data_forms:
        log.append("  no data-forms to bind\n")
        return 0, 0, 0

    users_module_id = find_users_module_id(cms_url, token)
    log.append(f"  Users module id: {users_module_id}\n")

    ok, fail, skip = 0, 0, 0
    for f_meta in data_forms:
        ident = f_meta.get('identifier')
        # Fetch the full form via GET (needed for PUT — service expects a full DTO)
        status, all_forms = http('GET', f'{cms_url}/api/admin/forms?limit=200', token=token)
        if status != 200:
            log.append(f"  FAIL GET /forms failed: HTTP {status}\n")
            fail += 1
            continue
        items = all_forms.get('items') if isinstance(all_forms, dict) else all_forms
        target = next((x for x in (items or []) if x.get('identifier') == ident), None)
        if not target:
            log.append(f"  form '{ident}' not found in CMS\n")
            skip += 1
            continue
        form_id = target.get('id')

        # Fetch full form data (for PUT)
        status, full_form = http('GET', f'{cms_url}/api/admin/forms/{form_id}', token=token)
        if status != 200:
            log.append(f"  FAIL GET /forms/{form_id} failed: HTTP {status}\n")
            fail += 1
            continue

        # Idempotency: check existing config
        existing = full_form.get('formModuleConfigs') or []
        already_bound = any(c.get('moduleId') == users_module_id for c in existing)
        if already_bound:
            log.append(f"  form '{ident}' already bound to Users module\n")
            skip += 1
            continue

        if dry_run:
            log.append(f"  [dry-run] PUT /forms/{form_id} formModuleConfigs+=Users\n")
            ok += 1
            continue

        # Add a new module config alongside existing ones
        new_configs = list(existing) + [{
            'moduleId': users_module_id,
            'formId': form_id,
            'entityIdentifiers': [],
        }]
        payload = dict(full_form)
        payload['formModuleConfigs'] = new_configs

        status, resp = http('PUT', f'{cms_url}/api/admin/forms/{form_id}', token=token, data=payload)
        if status == 200:
            log.append(f"  OK '{ident}' (id={form_id}) -> Users module\n")
            ok += 1
        else:
            log.append(f"  FAIL PUT /forms/{form_id} HTTP {status}: {resp}\n")
            fail += 1

    return ok, fail, skip


def task_post_import_payment_status_maps(cms_url, token, mapped, log, dry_run):
    """Set payment-status <-> order-status mapping per orders_storage.

    Reads `mapped.post_import_payment_status_maps[]` (built by
    post-mapper-fixer.py::generate_payment_status_maps). For each task:
      1. Resolve orders_storage identifier -> orders_storage_id via GET /orders-storage.
      2. PUT /payments/status-maps with `{orderStorageId, statusMap}`.
    """
    log.append('\n## 5. Payment status maps (post-import)\n')

    tasks = (mapped or {}).get('post_import_payment_status_maps') or []
    if not tasks:
        log.append('  no `post_import_payment_status_maps[]` tasks — skip\n')
        return 0, 0, 1

    # Resolve orders_storage identifier -> id via REST
    existing_storages = list_pages(cms_url, token, '/api/admin/orders-storage', page_param=True, limit=200)
    ident_to_storage_id = {s.get('identifier'): s.get('id') for s in existing_storages if s.get('identifier')}

    ok, fail, skip = 0, 0, 0
    for task in tasks:
        storage_ident = task.get('orders_storage')
        status_map = task.get('status_map') or {}
        if not storage_ident or not status_map:
            log.append(f"  SKIP malformed task: {task}\n")
            skip += 1
            continue
        storage_id = ident_to_storage_id.get(storage_ident)
        if not storage_id:
            log.append(f"  FAIL orders_storage '{storage_ident}' not found in CMS — skip\n")
            fail += 1
            continue
        body = {'orderStorageId': storage_id, 'statusMap': status_map}
        if dry_run:
            log.append(f"  [DRY] PUT /payments/status-maps storage='{storage_ident}' "
                       f"(id={storage_id}) statusMap={status_map}\n")
            ok += 1
            continue
        status, resp = http('PUT', f'{cms_url}/api/admin/payments/status-maps',
                            token=token, data=body)
        # PUT /status-maps returns 200 OK (NestJS default for PUT, no @HttpCode override
        # in admin-payments.controller.ts:215). Accept 201 too as defensive fallback for
        # potential future endpoint upgrades.
        if status in (200, 201):
            log.append(f"  OK status-map for storage='{storage_ident}' (id={storage_id}): "
                       f"{len(status_map)} pairs\n")
            ok += 1
        else:
            log.append(f"  FAIL status-map for '{storage_ident}': HTTP {status} {resp}\n")
            fail += 1

    return ok, fail, skip


def task_post_import_slides(cms_url, token, mapped, log, dry_run):
    """Create slides for slider_block blocks.

    Reads `mapped.post_import_slides[]` (built by post-mapper-fixer). The
    `slides` table is **OUT** of the blueprint whitelist (verified at
    the OneEntry Platform blueprint loader (verified against `BlueprintLoaderService.ALLOWED_TABLES`)).
    Each task is sent to `POST /api/admin/slides`:
        body = {blockId, attributesSets, isVisible}

    Idempotent: rebuilds existing slides per `block_id` first; if the count
    already matches the task list — skip; otherwise upsert by position.
    """
    log.append('\n## 6.5 Slider block slides (post-import)\n')
    tasks = (mapped or {}).get('post_import_slides') or []
    if not tasks:
        log.append('  no `post_import_slides[]` tasks — skip\n')
        return 0, 0, 1

    existing_blocks = list_pages(cms_url, token, '/api/admin/blocks', page_param=True, limit=500)
    ident_to_block_id = {b.get('identifier'): b.get('id') for b in existing_blocks if b.get('identifier')}
    # For each block, look up its attribute_set_id — slides inherit it via
    # `attributeSetId` so the admin slide-editor renders the correct fields.
    block_ident_to_aset_id = {}
    for b in existing_blocks:
        ident = b.get('identifier')
        aset_id = b.get('attributeSetId') or b.get('attribute_set_id')
        if ident and aset_id:
            block_ident_to_aset_id[ident] = aset_id

    # Two emission shapes are accepted:
    #
    #   A. NESTED (entity-mapper / agents/entity-mapper.md format):
    #      post_import_slides:
    #        - block_identifier: hero
    #          source_data_file: src/app/data/heroSlides.ts
    #          slides: [{eyebrow, headline, subtext, image, cta, href, ...}, ...]
    #
    #   B. FLAT (post-mapper-fixer.generate_post_import_slides safety net):
    #      post_import_slides:
    #        - block_identifier: hero
    #          position: 1
    #          attributes_sets: {en_US: {title, subtitle, image, cta_label, cta_url}}
    #
    # We normalize both into flat per-slide tasks. The NESTED form's per-slide
    # dicts use source field names (headline/subtext/cta/href/eyebrow/image)
    # which we route to OneEntry attribute identifiers (title/subtitle/cta_label/
    # cta_url/eyebrow/image) — same routing as post-mapper-fixer._attr_payload.
    PRIMARY_LANG = 'en_US'

    def _from_nested_slide(s, idx):
        title = s.get('headline') or s.get('title') or ''
        subtitle = s.get('subtext') or s.get('subtitle') or ''
        image = s.get('image') or s.get('imageUrl') or ''
        cta_label = s.get('cta') or s.get('cta_label') or s.get('button') or ''
        cta_url = s.get('href') or s.get('cta_url') or s.get('link') or ''
        eyebrow = s.get('eyebrow') or ''
        attrs = {}
        if title:     attrs['title']     = title
        if subtitle:  attrs['subtitle']  = subtitle
        if image:     attrs['image']     = image
        if cta_label: attrs['cta_label'] = cta_label
        if cta_url:   attrs['cta_url']   = cta_url
        if eyebrow:   attrs['eyebrow']   = eyebrow
        return {
            'position':        idx,
            'is_visible':      True,
            'attributes_sets': {PRIMARY_LANG: attrs},
        }

    flat_tasks = []
    for t in tasks:
        block_ident = t.get('block_identifier') or t.get('block') or '?'
        nested = t.get('slides')
        if isinstance(nested, list) and nested:
            for idx, s in enumerate(nested, start=1):
                ft = _from_nested_slide(s, idx)
                ft['block_identifier'] = block_ident
                flat_tasks.append(ft)
        else:
            # Already flat — pass through.
            flat_tasks.append(t)

    ok, fail, skip = 0, 0, 0
    by_block = {}
    for t in flat_tasks:
        by_block.setdefault(t.get('block_identifier'), []).append(t)

    for block_ident, block_tasks in by_block.items():
        block_id = ident_to_block_id.get(block_ident)
        if not block_id:
            log.append(f"  FAIL block '{block_ident}' not found — cannot create {len(block_tasks)} slide(s)\n")
            fail += len(block_tasks)
            continue

        # GET existing slides for this block to decide skip vs create. The
        # admin-slides controller returns a paginated wrapper `{items: [...],
        # total, ...}` rather than a bare array (verified — `admin-slides.
        # controller.ts:63-69`). Unwrap `items` so the idempotency guard works.
        status, raw = http('GET', f'{cms_url}/api/admin/slides?blockId={block_id}', token=token)
        if isinstance(raw, dict) and isinstance(raw.get('items'), list):
            existing_count = len(raw['items'])
        elif isinstance(raw, list):
            existing_count = len(raw)
        else:
            existing_count = 0
        if existing_count >= len(block_tasks):
            log.append(f"  SKIP block '{block_ident}': already has {existing_count} slide(s) "
                       f"(task list = {len(block_tasks)})\n")
            skip += len(block_tasks)
            continue

        for t in block_tasks:
            body = {
                'blockId':        block_id,
                'attributesSets': t.get('attributes_sets') or {},
                'isVisible':      bool(t.get('is_visible', True)),
            }
            # Inherit the slider block's attribute_set so the admin slide-editor
            # knows which fields to render. Without this `attributeSetId` is
            # null and admin UI shows "No attribute set" — empty edit screen.
            inherited_aset = block_ident_to_aset_id.get(block_ident)
            if inherited_aset:
                body['attributeSetId'] = inherited_aset
            if dry_run:
                log.append(f"  [DRY] POST /slides block='{block_ident}' (id={block_id}) "
                           f"pos={t.get('position')} attrs={list((body['attributesSets'].get('en_US') or {}).keys())}\n")
                ok += 1
                continue
            status, resp = http('POST', f'{cms_url}/api/admin/slides', token=token, data=body)
            if status in (200, 201):
                slide_id = resp.get('id') if isinstance(resp, dict) else '?'
                log.append(f"  OK slide pos={t.get('position')} for '{block_ident}' (slide_id={slide_id})\n")
                ok += 1
            else:
                log.append(f"  FAIL POST /slides for '{block_ident}' pos={t.get('position')}: "
                           f"HTTP {status} {resp}\n")
                fail += 1

    return ok, fail, skip


def task_align_attribute_keys(cms_url, token, mapped, log, dry_run):
    """Align JSON keys in `attributes_sets` jsonb columns to the admin-UI
    contract: `<type>_id<id>` (e.g. `string_id1`, `list_id3`, `real_id5`).

    The blueprint-builder auto-numbers schema keys to `attribute1`, `attribute2`,
    … (so the UI's `EditSingleAttribute.js:492` URL works), but the admin's
    *value-renderer* (`ShowAttributesFields.js`) looks up data via
    `page.attributesSets[lang][<type>_id<id>]` — a different key shape! Both
    rename steps are required:

      1. data-key was semantic (e.g. `sku`) → bring to schema key (`attribute1`)
      2. then immediately rename `attribute1` → `string_id1` (using schema's
         `type` + `id` fields) so the UI's value-lookup works.

    Step 1 (semantic→attribute<N>) is done by walking schema's `identifier`
    field; step 2 (attribute<N>→<type>_id<id>) is done by reading `type`+`id`.
    Steps run together. Without this, every entity in the admin UI appears
    empty (Type/Marker labels visible, value fields blank).

    Local-docker-only — uses `docker exec`. Universal across project types.
    """
    log.append('\n## 7.5 Align attribute_set keys (data ↔ admin-UI lookup)\n')
    if dry_run:
        log.append('  [DRY] would run docker exec psql to rename data keys\n')
        return 0, 0, 1

    # The single SQL block performs BOTH renames per attribute_set in one pass:
    # first semantic→attributeN (idempotent — only fires if old key still
    # present), then attributeN→<type>_id<id>.
    # The expression below performs BOTH renames in one CASE:
    #   - if data has the semantic key (e.g. `sku`) → rename to ui_key
    #   - else if data has the schema-key (e.g. `attribute1`) → rename to ui_key
    #   - else leave as-is
    sql = r"""
DO $$
DECLARE
  aset_rec   RECORD;
  schema_obj jsonb;
  k          text;
  ident      text;
  type_v     text;
  id_v       int;
  ui_key     text;
  cnt        int;
  total      int := 0;
BEGIN
  FOR aset_rec IN SELECT id, identifier, schema::jsonb AS schema_j FROM attributes_sets LOOP
    schema_obj := aset_rec.schema_j;
    FOR k IN SELECT jsonb_object_keys(schema_obj) LOOP
      ident    := COALESCE(schema_obj->k->>'identifier', '');
      type_v   := schema_obj->k->>'type';
      id_v     := (schema_obj->k->>'id')::int;
      IF type_v IS NULL OR id_v IS NULL THEN CONTINUE; END IF;
      ui_key   := type_v || '_id' || id_v;

      UPDATE products SET attributes_sets = COALESCE((
        SELECT jsonb_object_agg(lang_k,
          CASE WHEN lang_v ? k     THEN (lang_v - k)     || jsonb_build_object(ui_key, lang_v->k)
               WHEN ident <> '' AND lang_v ? ident
                                   THEN (lang_v - ident) || jsonb_build_object(ui_key, lang_v->ident)
               ELSE lang_v END
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      ), attributes_sets::jsonb)::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      GET DIAGNOSTICS cnt = ROW_COUNT; total := total + cnt;

      UPDATE pages SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          CASE WHEN lang_v ? k     THEN (lang_v - k)     || jsonb_build_object(ui_key, lang_v->k)
               WHEN ident <> '' AND lang_v ? ident
                                   THEN (lang_v - ident) || jsonb_build_object(ui_key, lang_v->ident)
               ELSE lang_v END
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id;
      GET DIAGNOSTICS cnt = ROW_COUNT; total := total + cnt;

      UPDATE blocks SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          CASE WHEN lang_v ? k     THEN (lang_v - k)     || jsonb_build_object(ui_key, lang_v->k)
               WHEN ident <> '' AND lang_v ? ident
                                   THEN (lang_v - ident) || jsonb_build_object(ui_key, lang_v->ident)
               ELSE lang_v END
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id;
      GET DIAGNOSTICS cnt = ROW_COUNT; total := total + cnt;

      UPDATE forms SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          CASE WHEN lang_v ? k     THEN (lang_v - k)     || jsonb_build_object(ui_key, lang_v->k)
               WHEN ident <> '' AND lang_v ? ident
                                   THEN (lang_v - ident) || jsonb_build_object(ui_key, lang_v->ident)
               ELSE lang_v END
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id;
      GET DIAGNOSTICS cnt = ROW_COUNT; total := total + cnt;

      UPDATE user_groups SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          CASE WHEN lang_v ? k     THEN (lang_v - k)     || jsonb_build_object(ui_key, lang_v->k)
               WHEN ident <> '' AND lang_v ? ident
                                   THEN (lang_v - ident) || jsonb_build_object(ui_key, lang_v->ident)
               ELSE lang_v END
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id;
      GET DIAGNOSTICS cnt = ROW_COUNT; total := total + cnt;

      UPDATE slides SET attributes_sets = COALESCE((
        SELECT jsonb_object_agg(lang_k,
          CASE WHEN lang_v ? k     THEN (lang_v - k)     || jsonb_build_object(ui_key, lang_v->k)
               WHEN ident <> '' AND lang_v ? ident
                                   THEN (lang_v - ident) || jsonb_build_object(ui_key, lang_v->ident)
               ELSE lang_v END
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      ), attributes_sets::jsonb)::jsonb WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      GET DIAGNOSTICS cnt = ROW_COUNT; total := total + cnt;
    END LOOP;
  END LOOP;

  -- ─── PASS 2: convert list-typed values to admin-UI shape ────────────
  -- Frontend `ListFieldsParameters.js` expects state as ARRAY of objects
  -- (each with a `value` property). Plain strings / plain arrays of strings
  -- fail `Array.isArray(state) && state[0].value` check → dropdown empty.
  -- Convert:
  --   "X"               → [{"value": "X"}]    (single-select list)
  --   ["a","b"]         → [{"value":"a"},{"value":"b"}]    (multi-select list)
  -- Idempotent: skip if value is already array-of-objects.
  FOR aset_rec IN SELECT id, identifier, schema::jsonb AS schema_j FROM attributes_sets LOOP
    schema_obj := aset_rec.schema_j;
    FOR k IN SELECT jsonb_object_keys(schema_obj) LOOP
      type_v := schema_obj->k->>'type';
      id_v   := (schema_obj->k->>'id')::int;
      IF type_v <> 'list' OR id_v IS NULL THEN CONTINUE; END IF;
      ui_key := type_v || '_id' || id_v;

      -- products
      UPDATE products SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          CASE
            WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'string'
                 AND (lang_v->>ui_key) <> ''
              THEN lang_v - ui_key || jsonb_build_object(ui_key,
                                       jsonb_build_array(jsonb_build_object('value', lang_v->>ui_key)))
            WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'array'
                 AND jsonb_array_length(lang_v->ui_key) > 0
                 AND jsonb_typeof(lang_v->ui_key->0) = 'string'
              THEN lang_v - ui_key || jsonb_build_object(ui_key,
                       (SELECT jsonb_agg(jsonb_build_object('value', elem))
                        FROM jsonb_array_elements_text(lang_v->ui_key) elem))
            ELSE lang_v END
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      GET DIAGNOSTICS cnt = ROW_COUNT; total := total + cnt;

      -- blocks
      UPDATE blocks SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          CASE
            WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'string'
                 AND (lang_v->>ui_key) <> ''
              THEN lang_v - ui_key || jsonb_build_object(ui_key,
                                       jsonb_build_array(jsonb_build_object('value', lang_v->>ui_key)))
            WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'array'
                 AND jsonb_array_length(lang_v->ui_key) > 0
                 AND jsonb_typeof(lang_v->ui_key->0) = 'string'
              THEN lang_v - ui_key || jsonb_build_object(ui_key,
                       (SELECT jsonb_agg(jsonb_build_object('value', elem))
                        FROM jsonb_array_elements_text(lang_v->ui_key) elem))
            ELSE lang_v END
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;

      -- slides (jsonb column)
      UPDATE slides SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          CASE
            WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'string'
                 AND (lang_v->>ui_key) <> ''
              THEN lang_v - ui_key || jsonb_build_object(ui_key,
                                       jsonb_build_array(jsonb_build_object('value', lang_v->>ui_key)))
            WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'array'
                 AND jsonb_array_length(lang_v->ui_key) > 0
                 AND jsonb_typeof(lang_v->ui_key->0) = 'string'
              THEN lang_v - ui_key || jsonb_build_object(ui_key,
                       (SELECT jsonb_agg(jsonb_build_object('value', elem))
                        FROM jsonb_array_elements_text(lang_v->ui_key) elem))
            ELSE lang_v END
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::jsonb WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
    END LOOP;
  END LOOP;

  -- ─── PASS 3: type-specific shape corrections per AttributeType ──────
  --   image:        string URL → array `[{filename, downloadLink, previewLink}]`
  --   real/integer/float: number → string (NumberFieldsParameters.value expects string)
  --   radioButton:  empty string "" → drop key (RadioButtonFieldsParameters expects {value})
  --   list:         empty string "" → drop key (was added by alignment but no value)
  -- Each entity loop is idempotent (checks current jsonb_typeof before mutating).
  FOR aset_rec IN SELECT id, identifier, schema::jsonb AS schema_j FROM attributes_sets LOOP
    schema_obj := aset_rec.schema_j;
    FOR k IN SELECT jsonb_object_keys(schema_obj) LOOP
      type_v := schema_obj->k->>'type';
      id_v   := (schema_obj->k->>'id')::int;
      IF id_v IS NULL THEN CONTINUE; END IF;
      ui_key := type_v || '_id' || id_v;

      IF type_v = 'image' THEN
        -- products
        UPDATE products SET attributes_sets = (
          SELECT jsonb_object_agg(lang_k,
            CASE WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'string'
                      AND (lang_v->>ui_key) <> ''
                 THEN lang_v - ui_key || jsonb_build_object(ui_key,
                        jsonb_build_array(jsonb_build_object(
                          'filename',    split_part(lang_v->>ui_key, '/', -1),
                          'downloadLink', lang_v->>ui_key,
                          'previewLink', jsonb_build_object('1', lang_v->>ui_key))))
                 ELSE lang_v END
          ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
        )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
        GET DIAGNOSTICS cnt = ROW_COUNT; total := total + cnt;
        UPDATE blocks SET attributes_sets = (
          SELECT jsonb_object_agg(lang_k,
            CASE WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'string'
                      AND (lang_v->>ui_key) <> ''
                 THEN lang_v - ui_key || jsonb_build_object(ui_key,
                        jsonb_build_array(jsonb_build_object(
                          'filename',    split_part(lang_v->>ui_key, '/', -1),
                          'downloadLink', lang_v->>ui_key,
                          'previewLink', jsonb_build_object('1', lang_v->>ui_key))))
                 ELSE lang_v END
          ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
        )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
        UPDATE slides SET attributes_sets = (
          SELECT jsonb_object_agg(lang_k,
            CASE WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'string'
                      AND (lang_v->>ui_key) <> ''
                 THEN lang_v - ui_key || jsonb_build_object(ui_key,
                        jsonb_build_array(jsonb_build_object(
                          'filename',    split_part(lang_v->>ui_key, '/', -1),
                          'downloadLink', lang_v->>ui_key,
                          'previewLink', jsonb_build_object('1', lang_v->>ui_key))))
                 ELSE lang_v END
          ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
        )::jsonb WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      ELSIF type_v IN ('real', 'integer', 'float') THEN
        -- Number → string (renderer uses input.value.trim())
        UPDATE products SET attributes_sets = (
          SELECT jsonb_object_agg(lang_k,
            CASE WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'number'
                 THEN lang_v - ui_key || jsonb_build_object(ui_key, (lang_v->>ui_key))
                 ELSE lang_v END
          ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
        )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
        UPDATE blocks SET attributes_sets = (
          SELECT jsonb_object_agg(lang_k,
            CASE WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'number'
                 THEN lang_v - ui_key || jsonb_build_object(ui_key, (lang_v->>ui_key))
                 ELSE lang_v END
          ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
        )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      ELSIF type_v IN ('radioButton', 'list') THEN
        -- empty string → drop key entirely (admin shows "not selected")
        UPDATE products SET attributes_sets = (
          SELECT jsonb_object_agg(lang_k,
            CASE WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'string'
                      AND (lang_v->>ui_key) = ''
                 THEN lang_v - ui_key
                 ELSE lang_v END
          ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
        )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
        UPDATE forms SET attributes_sets = (
          SELECT jsonb_object_agg(lang_k,
            CASE WHEN lang_v ? ui_key AND jsonb_typeof(lang_v->ui_key) = 'string'
                      AND (lang_v->>ui_key) = ''
                 THEN lang_v - ui_key
                 ELSE lang_v END
          ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
        )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      END IF;
    END LOOP;
  END LOOP;

  -- ─── PASS 4: clean orphan keys (data keys without a matching schema entry) ──
  -- Walk each entity, for each lang block, drop keys whose `<type>_id<id>`
  -- does not correspond to any schema attribute. Prevents `materials`/`title`
  -- string-keyed leftovers from confusing admin renderer + storage.
  DECLARE
    orphan_dropped int := 0;
  BEGIN
    -- Build a temp table of all valid <ui_key> per attribute_set_id
    CREATE TEMP TABLE IF NOT EXISTS _valid_keys (aset_id int, vkey text) ON COMMIT DROP;
    DELETE FROM _valid_keys;
    INSERT INTO _valid_keys (aset_id, vkey)
    SELECT a.id, (a.schema::jsonb->kk->>'type') || '_id' || ((a.schema::jsonb->kk->>'id')::int)
    FROM attributes_sets a, jsonb_object_keys(a.schema::jsonb) AS kk
    WHERE (a.schema::jsonb->kk->>'id') IS NOT NULL;

    FOR aset_rec IN SELECT id FROM attributes_sets LOOP
      -- products
      UPDATE products SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          (SELECT COALESCE(jsonb_object_agg(inner_k, inner_v), '{}'::jsonb)
           FROM jsonb_each(lang_v) AS t2(inner_k, inner_v)
           WHERE inner_k IN (SELECT vkey FROM _valid_keys WHERE aset_id = aset_rec.id))
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      GET DIAGNOSTICS cnt = ROW_COUNT; orphan_dropped := orphan_dropped + cnt;
      -- blocks
      UPDATE blocks SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          (SELECT COALESCE(jsonb_object_agg(inner_k, inner_v), '{}'::jsonb)
           FROM jsonb_each(lang_v) AS t2(inner_k, inner_v)
           WHERE inner_k IN (SELECT vkey FROM _valid_keys WHERE aset_id = aset_rec.id))
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      -- pages
      UPDATE pages SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          (SELECT COALESCE(jsonb_object_agg(inner_k, inner_v), '{}'::jsonb)
           FROM jsonb_each(lang_v) AS t2(inner_k, inner_v)
           WHERE inner_k IN (SELECT vkey FROM _valid_keys WHERE aset_id = aset_rec.id))
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      -- forms
      UPDATE forms SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          (SELECT COALESCE(jsonb_object_agg(inner_k, inner_v), '{}'::jsonb)
           FROM jsonb_each(lang_v) AS t2(inner_k, inner_v)
           WHERE inner_k IN (SELECT vkey FROM _valid_keys WHERE aset_id = aset_rec.id))
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      -- user_groups
      UPDATE user_groups SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          (SELECT COALESCE(jsonb_object_agg(inner_k, inner_v), '{}'::jsonb)
           FROM jsonb_each(lang_v) AS t2(inner_k, inner_v)
           WHERE inner_k IN (SELECT vkey FROM _valid_keys WHERE aset_id = aset_rec.id))
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::json WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
      -- slides
      UPDATE slides SET attributes_sets = (
        SELECT jsonb_object_agg(lang_k,
          (SELECT COALESCE(jsonb_object_agg(inner_k, inner_v), '{}'::jsonb)
           FROM jsonb_each(lang_v) AS t2(inner_k, inner_v)
           WHERE inner_k IN (SELECT vkey FROM _valid_keys WHERE aset_id = aset_rec.id))
        ) FROM jsonb_each(attributes_sets::jsonb) AS t(lang_k, lang_v)
      )::jsonb WHERE attribute_set_id = aset_rec.id AND attributes_sets::jsonb <> '{}'::jsonb;
    END LOOP;
    RAISE NOTICE 'PASS 4 orphans cleaned: % rows touched', orphan_dropped;
  END;

  RAISE NOTICE 'TOTAL_RENAMED=%', total;
END$$;
"""

    try:
        import subprocess
        result = subprocess.run(
            ['docker', 'exec', 'cms-sb-db', 'psql', '-U', 'postgres',
             '-d', 'test_db_cms3', '-c', sql],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log.append(f"  FAIL psql exit {result.returncode}: {result.stderr[:400]}\n")
            return 0, 1, 0
        # Parse TOTAL_RENAMED notice
        renamed = '?'
        for line in (result.stderr or '').splitlines():
            if 'TOTAL_RENAMED=' in line:
                renamed = line.split('TOTAL_RENAMED=', 1)[1].split(' ', 1)[0].strip()
        log.append(f"  OK renamed {renamed} rows across products/pages/blocks/forms/user_groups/slides\n")
        return 1, 0, 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.append(f"  SKIP: docker exec not available ({type(e).__name__})\n")
        return 0, 0, 1


def task_normalize_attribute_value_shapes(cms_url, token, mapped, log, dry_run):
    """Enforce per-type data-value shapes across every attribute-bearing table.

    Runs AFTER task_align_attribute_keys (keys now follow `<type>_id<N>`).
    Schema-driven — discovers consumer tables dynamically via information_schema.
    Universal across project verticals.

    Fixes (each idempotent):
      - integer/real keys stored as JSON number  →  string ("123.45")
      - image/groupOfImages keys stored as ""    →  empty array []
      - list keys stored as bare string "x"      →  [{"value":"x"}]
      - list keys stored as null                 →  []
      - radioButton keys stored as ""            →  key dropped (admin treats
        missing as unset; "" breaks the boolean validator)
      - button keys stored as non-object         →  {}
      - dateTime keys stored as ""               →  key dropped

    Frontend renderer evidence:
      - cms_frontend/.../ImageFieldsParameters.js:59,98 — iterates item.downloadLink
        / item.previewLink; string value crashes
      - cms_frontend/.../NumberFieldsParameters.js:68-70 — eventValue.trim() requires
        string; bare number bypasses validation
      - cms_frontend/.../ListFieldsParameters.js:18 — expects [{value:X}]
    """
    log.append('\n## 7.6 Normalize attribute value shapes (per-type guarantees)\n')
    if dry_run:
        log.append('  DRY-RUN — skipping\n')
        return 0, 0, 0
    sql = r"""
DO $$
DECLARE
  consumer_table text;
  aset_rec record;
  schema_rec record;
  fixed_int int := 0;
  fixed_real int := 0;
  fixed_img int := 0;
  fixed_list int := 0;
  fixed_radio int := 0;
  fixed_btn int := 0;
  fixed_dt int := 0;
BEGIN
  FOR consumer_table IN
    SELECT DISTINCT table_name FROM information_schema.columns
    WHERE column_name = 'attribute_set_id' AND table_schema = 'public'
      AND table_name IN (SELECT t.table_name FROM information_schema.columns t
                         WHERE t.column_name='attributes_sets' AND t.table_schema='public')
      AND table_name <> 'admins'
  LOOP
    FOR aset_rec IN
      SELECT id, schema::jsonb AS schema_j FROM attributes_sets
      WHERE schema::jsonb <> '{}'::jsonb
    LOOP
      FOR schema_rec IN
        SELECT kk AS skey,
               (aset_rec.schema_j->kk->>'type') AS atype,
               (aset_rec.schema_j->kk->>'identifier') AS aident,
               (aset_rec.schema_j->kk->>'id')::int AS aid
        FROM jsonb_object_keys(aset_rec.schema_j) AS kk
        WHERE (aset_rec.schema_j->kk->>'id') IS NOT NULL
      LOOP
        IF schema_rec.atype IN ('integer','real') THEN
          EXECUTE format($q$
            UPDATE %I SET attributes_sets = (
              SELECT jsonb_object_agg(lang_k,
                CASE WHEN jsonb_typeof(lang_v->%L) = 'number'
                     THEN jsonb_set(lang_v, ARRAY[%L], to_jsonb((lang_v->>%L)))
                     ELSE lang_v END)
              FROM jsonb_each(attributes_sets::jsonb) AS jl(lang_k, lang_v)
            )::%s WHERE attribute_set_id = $1;
          $q$, consumer_table,
              schema_rec.atype || '_id' || schema_rec.aid,
              schema_rec.atype || '_id' || schema_rec.aid,
              schema_rec.atype || '_id' || schema_rec.aid,
              CASE WHEN consumer_table='slides' THEN 'jsonb' ELSE 'json' END)
          USING aset_rec.id;
          GET DIAGNOSTICS fixed_int = ROW_COUNT;
          IF schema_rec.atype = 'real' THEN fixed_real := fixed_real + fixed_int; END IF;
        ELSIF schema_rec.atype IN ('image','groupOfImages') THEN
          EXECUTE format($q$
            UPDATE %I SET attributes_sets = (
              SELECT jsonb_object_agg(lang_k,
                CASE WHEN (lang_v ? %L) AND jsonb_typeof(lang_v->%L) <> 'array'
                     THEN jsonb_set(lang_v, ARRAY[%L], '[]'::jsonb)
                     ELSE lang_v END)
              FROM jsonb_each(attributes_sets::jsonb) AS jl(lang_k, lang_v)
            )::%s WHERE attribute_set_id = $1;
          $q$, consumer_table,
              schema_rec.atype || '_id' || schema_rec.aid,
              schema_rec.atype || '_id' || schema_rec.aid,
              schema_rec.atype || '_id' || schema_rec.aid,
              CASE WHEN consumer_table='slides' THEN 'jsonb' ELSE 'json' END)
          USING aset_rec.id;
          GET DIAGNOSTICS fixed_img = ROW_COUNT;
        ELSIF schema_rec.atype = 'list' THEN
          EXECUTE format($q$
            UPDATE %I SET attributes_sets = (
              SELECT jsonb_object_agg(lang_k,
                CASE WHEN (lang_v ? %L) AND jsonb_typeof(lang_v->%L) <> 'array'
                     THEN jsonb_set(lang_v, ARRAY[%L],
                       CASE WHEN jsonb_typeof(lang_v->%L) = 'string'
                              AND length(lang_v->>%L) > 0
                            THEN jsonb_build_array(jsonb_build_object('value', lang_v->>%L))
                            ELSE '[]'::jsonb END)
                     ELSE lang_v END)
              FROM jsonb_each(attributes_sets::jsonb) AS jl(lang_k, lang_v)
            )::%s WHERE attribute_set_id = $1;
          $q$, consumer_table,
              'list_id' || schema_rec.aid, 'list_id' || schema_rec.aid,
              'list_id' || schema_rec.aid, 'list_id' || schema_rec.aid,
              'list_id' || schema_rec.aid, 'list_id' || schema_rec.aid,
              CASE WHEN consumer_table='slides' THEN 'jsonb' ELSE 'json' END)
          USING aset_rec.id;
          GET DIAGNOSTICS fixed_list = ROW_COUNT;
        ELSIF schema_rec.atype = 'radioButton' THEN
          EXECUTE format($q$
            UPDATE %I SET attributes_sets = (
              SELECT jsonb_object_agg(lang_k,
                CASE WHEN (lang_v->>%L) = '' THEN lang_v - %L ELSE lang_v END)
              FROM jsonb_each(attributes_sets::jsonb) AS jl(lang_k, lang_v)
            )::%s WHERE attribute_set_id = $1;
          $q$, consumer_table,
              'radioButton_id' || schema_rec.aid, 'radioButton_id' || schema_rec.aid,
              CASE WHEN consumer_table='slides' THEN 'jsonb' ELSE 'json' END)
          USING aset_rec.id;
          GET DIAGNOSTICS fixed_radio = ROW_COUNT;
        ELSIF schema_rec.atype = 'button' THEN
          EXECUTE format($q$
            UPDATE %I SET attributes_sets = (
              SELECT jsonb_object_agg(lang_k,
                CASE WHEN (lang_v ? %L) AND jsonb_typeof(lang_v->%L) <> 'object'
                     THEN jsonb_set(lang_v, ARRAY[%L], '{}'::jsonb)
                     ELSE lang_v END)
              FROM jsonb_each(attributes_sets::jsonb) AS jl(lang_k, lang_v)
            )::%s WHERE attribute_set_id = $1;
          $q$, consumer_table,
              'button_id' || schema_rec.aid, 'button_id' || schema_rec.aid,
              'button_id' || schema_rec.aid,
              CASE WHEN consumer_table='slides' THEN 'jsonb' ELSE 'json' END)
          USING aset_rec.id;
          GET DIAGNOSTICS fixed_btn = ROW_COUNT;
        ELSIF schema_rec.atype IN ('dateTime','date','time') THEN
          EXECUTE format($q$
            UPDATE %I SET attributes_sets = (
              SELECT jsonb_object_agg(lang_k,
                CASE WHEN (lang_v->>%L) = '' THEN lang_v - %L ELSE lang_v END)
              FROM jsonb_each(attributes_sets::jsonb) AS jl(lang_k, lang_v)
            )::%s WHERE attribute_set_id = $1;
          $q$, consumer_table,
              schema_rec.atype || '_id' || schema_rec.aid,
              schema_rec.atype || '_id' || schema_rec.aid,
              CASE WHEN consumer_table='slides' THEN 'jsonb' ELSE 'json' END)
          USING aset_rec.id;
          GET DIAGNOSTICS fixed_dt = ROW_COUNT;
        END IF;
      END LOOP;
    END LOOP;
  END LOOP;
  RAISE NOTICE 'shape fixes: int+real=%, img=%, list=%, radio=%, btn=%, dt=%',
    fixed_int + fixed_real, fixed_img, fixed_list, fixed_radio, fixed_btn, fixed_dt;
END $$;
"""
    import subprocess
    try:
        result = subprocess.run(
            ['docker', 'exec', 'cms-sb-db', 'psql', '-U', 'postgres', '-d', 'test_db_cms3', '-c', sql],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log.append(f'  FAIL psql exit {result.returncode}: {result.stderr[:800]}\n')
            return 0, 1, 0
        log.append('  OK shape normalization applied\n')
        if 'NOTICE' in (result.stderr or ''):
            log.append(f'  {result.stderr.strip().splitlines()[-1]}\n')
        return 1, 0, 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.append(f'  SKIP: docker exec not available ({type(e).__name__})\n')
        return 0, 0, 1


def task_ensure_standard_user_groups(cms_url, token, mapped, log, dry_run):
    """B7 — Ensure the standard `guest` user_group exists.

    CMS ships a TypeORM seed (1745835025671-set-default-user-group.ts) that
    inserts `guest` (id=1). The seed is recorded in the `migrations` table —
    so after `TRUNCATE user_groups RESTART IDENTITY CASCADE` (typical reset
    during pipeline development) the seed will NOT re-run because TypeORM
    thinks it's already applied. Without `guest` the storefront cannot resolve
    anonymous cart/session bindings.

    Universal — `guest` is required for every OneEntry project regardless of
    vertical (e-commerce, restaurant, hotel, SaaS — all storefronts need an
    anonymous group).

    Idempotent — uses WHERE NOT EXISTS by identifier (no unique constraint
    on `user_groups.identifier` exists, hence we cannot use ON CONFLICT).
    """
    log.append('\n## 8.7 Standard user_groups (guest)\n')
    if dry_run:
        log.append('  DRY-RUN — skipping\n')
        return 0, 0, 0
    sql = r"""
INSERT INTO user_groups (identifier, localize_infos)
SELECT 'guest', '{"en_US":{"title":"Guest"}}'::jsonb
WHERE NOT EXISTS (SELECT 1 FROM user_groups WHERE identifier = 'guest');
"""
    import subprocess
    try:
        result = subprocess.run(
            ['docker', 'exec', 'cms-sb-db', 'psql', '-U', 'postgres', '-d', 'test_db_cms3', '-c', sql],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode != 0:
            log.append(f'  FAIL psql exit {result.returncode}: {result.stderr[:600]}\n')
            return 0, 1, 0
        inserted = '0 1' in (result.stdout or '')
        log.append(f'  OK guest user_group {"inserted" if inserted else "already present"}\n')
        return 1, 0, 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.append(f'  SKIP: docker exec not available ({type(e).__name__})\n')
        return 0, 0, 1


def task_wrap_text_values_in_editor_shape(cms_url, token, mapped, log, dry_run):
    """B5 — Wrap plain-string `text`-type values into the admin editor shape.

    Frontend renderer evidence:
      cms_frontend/.../TextFieldsParameters.js:99,822-823 destructures
      `{htmlValue, plainValue, mdValue, params:{editorMode}}` from the value.
      A plain string makes all three fields `undefined` → empty editor.

    Required shape:
      { "htmlValue": "<str>", "plainValue": "<str>", "mdValue": "<str>",
        "params": {"editorMode": "HTML"} }

    Universal — applies to any project that fills `text`-type attributes
    (descriptions / about / long-form copy / bio / details). Idempotent —
    objects with `htmlValue` key are left alone.
    """
    log.append('\n## 8.5 Wrap text values into editor shape\n')
    if dry_run:
        log.append('  DRY-RUN — skipping\n')
        return 0, 0, 0
    sql = r"""
DO $$
DECLARE
  consumer_table text;
  aset_rec record;
  schema_rec record;
  wrapped int := 0;
BEGIN
  FOR consumer_table IN
    SELECT DISTINCT table_name FROM information_schema.columns
    WHERE column_name = 'attribute_set_id' AND table_schema = 'public'
      AND table_name IN (SELECT t.table_name FROM information_schema.columns t
                         WHERE t.column_name='attributes_sets' AND t.table_schema='public')
      AND table_name <> 'admins'
  LOOP
    FOR aset_rec IN
      SELECT id, schema::jsonb AS schema_j FROM attributes_sets
      WHERE schema::jsonb <> '{}'::jsonb
    LOOP
      FOR schema_rec IN
        SELECT (aset_rec.schema_j->kk->>'id')::int AS aid
        FROM jsonb_object_keys(aset_rec.schema_j) AS kk
        WHERE (aset_rec.schema_j->kk->>'type') = 'text'
          AND (aset_rec.schema_j->kk->>'id') IS NOT NULL
      LOOP
        EXECUTE format($q$
          UPDATE %I SET attributes_sets = (
            SELECT jsonb_object_agg(lang_k,
              CASE WHEN jsonb_typeof(lang_v->%L) = 'string'
                   THEN jsonb_set(lang_v, ARRAY[%L],
                     jsonb_build_object(
                       'htmlValue', lang_v->>%L,
                       'plainValue', lang_v->>%L,
                       'mdValue', lang_v->>%L,
                       'params', jsonb_build_object('editorMode', 'HTML')))
                   ELSE lang_v END)
            FROM jsonb_each(attributes_sets::jsonb) AS jl(lang_k, lang_v)
          )::%s WHERE attribute_set_id = $1;
        $q$, consumer_table,
            'text_id' || schema_rec.aid,
            'text_id' || schema_rec.aid,
            'text_id' || schema_rec.aid,
            'text_id' || schema_rec.aid,
            'text_id' || schema_rec.aid,
            CASE WHEN consumer_table='slides' THEN 'jsonb' ELSE 'json' END)
        USING aset_rec.id;
        GET DIAGNOSTICS wrapped = ROW_COUNT;
      END LOOP;
    END LOOP;
  END LOOP;
  RAISE NOTICE 'text wrap pass complete';
END $$;
"""
    import subprocess
    try:
        result = subprocess.run(
            ['docker', 'exec', 'cms-sb-db', 'psql', '-U', 'postgres', '-d', 'test_db_cms3', '-c', sql],
            capture_output=True, text=True, timeout=120,
        )
        if result.returncode != 0:
            log.append(f'  FAIL psql exit {result.returncode}: {result.stderr[:600]}\n')
            return 0, 1, 0
        log.append('  OK text wrap applied\n')
        return 1, 0, 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.append(f'  SKIP: docker exec not available ({type(e).__name__})\n')
        return 0, 0, 1


def task_backfill_missing_attribute_keys(cms_url, token, mapped, log, dry_run):
    """B6 — Insert type-appropriate empty defaults for schema keys missing from data.

    Audit confirmed: ~32% of expected cells are missing (1184 / 3700).
    Without defaults, admin renderers receive `undefined` and either crash or
    show stale state from previous entity (React useState quirk).

    Defaults inserted ONLY for keys absent from data:
      list / image / groupOfImages         → []
      string                                → ""
      text                                  → editor-shape with empty fields
      button                                → {}
    Skipped (no sensible default, admin handles missing key as unset):
      integer / real / dateTime / date / time / radioButton

    Universal — schema-introspecting across all consumer tables.
    Idempotent — only inserts when key is absent.
    """
    log.append('\n## 8.6 Backfill missing attribute keys with type-defaults\n')
    if dry_run:
        log.append('  DRY-RUN — skipping\n')
        return 0, 0, 0
    sql = r"""
DO $$
DECLARE
  consumer_table text;
  aset_rec record;
  schema_rec record;
  default_jsonb jsonb;
  ekey text;
  filled int := 0;
BEGIN
  FOR consumer_table IN
    SELECT DISTINCT table_name FROM information_schema.columns
    WHERE column_name = 'attribute_set_id' AND table_schema = 'public'
      AND table_name IN (SELECT t.table_name FROM information_schema.columns t
                         WHERE t.column_name='attributes_sets' AND t.table_schema='public')
      AND table_name <> 'admins'
  LOOP
    FOR aset_rec IN
      SELECT id, schema::jsonb AS schema_j FROM attributes_sets
      WHERE schema::jsonb <> '{}'::jsonb
    LOOP
      FOR schema_rec IN
        SELECT (aset_rec.schema_j->kk->>'type') AS atype,
               (aset_rec.schema_j->kk->>'id')::int AS aid
        FROM jsonb_object_keys(aset_rec.schema_j) AS kk
        WHERE (aset_rec.schema_j->kk->>'id') IS NOT NULL
      LOOP
        ekey := schema_rec.atype || '_id' || schema_rec.aid;
        default_jsonb := CASE schema_rec.atype
          WHEN 'list'          THEN '[]'::jsonb
          WHEN 'image'         THEN '[]'::jsonb
          WHEN 'groupOfImages' THEN '[]'::jsonb
          WHEN 'string'        THEN '""'::jsonb
          WHEN 'text'          THEN '{"htmlValue":"","plainValue":"","mdValue":"","params":{"editorMode":"HTML"}}'::jsonb
          WHEN 'button'        THEN '{}'::jsonb
          ELSE NULL
        END;
        IF default_jsonb IS NULL THEN CONTINUE; END IF;
        EXECUTE format($q$
          UPDATE %I SET attributes_sets = (
            SELECT jsonb_object_agg(lang_k,
              CASE WHEN (lang_v ? %L) THEN lang_v
                   ELSE jsonb_set(lang_v, ARRAY[%L], %L::jsonb) END)
            FROM jsonb_each(attributes_sets::jsonb) AS jl(lang_k, lang_v)
          )::%s WHERE attribute_set_id = $1;
        $q$, consumer_table, ekey, ekey, default_jsonb::text,
            CASE WHEN consumer_table='slides' THEN 'jsonb' ELSE 'json' END)
        USING aset_rec.id;
        GET DIAGNOSTICS filled = ROW_COUNT;
      END LOOP;
    END LOOP;
  END LOOP;
  RAISE NOTICE 'backfill pass complete';
END $$;
"""
    import subprocess
    try:
        result = subprocess.run(
            ['docker', 'exec', 'cms-sb-db', 'psql', '-U', 'postgres', '-d', 'test_db_cms3', '-c', sql],
            capture_output=True, text=True, timeout=180,
        )
        if result.returncode != 0:
            log.append(f'  FAIL psql exit {result.returncode}: {result.stderr[:600]}\n')
            return 0, 1, 0
        log.append('  OK backfill applied\n')
        return 1, 0, 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.append(f'  SKIP: docker exec not available ({type(e).__name__})\n')
        return 0, 0, 1


def task_seed_default_discount_conditions(cms_url, token, mapped, log, dry_run):
    """B1 — Every discount must have ≥1 row in discount_conditions, otherwise
    the discount evaluator treats it as un-triggerable.

    Universal across project verticals. Reads `discounts.discount_value->>'applicability'`:
      - TO_ORDER  → MIN_CART_AMOUNT, value={amount:0}   (applies to any cart)
      - TO_PRODUCT → MIN_CART_AMOUNT, value={amount:0}  (placeholder — projects
        that need PRODUCT-/CATEGORY-specific targeting should override via
        explicit blueprint emission; this fallback keeps the discount active)

    Idempotent — only seeds when `discount_conditions` for the discount is empty.
    """
    log.append('\n## 8.1 Default discount_conditions seeding\n')
    if dry_run:
        log.append('  DRY-RUN — skipping\n')
        return 0, 0, 0
    sql = r"""
DO $$
DECLARE
  d_rec record;
  app_kind text;
  seeded int := 0;
BEGIN
  FOR d_rec IN
    SELECT d.id, d.discount_value FROM discounts d
    WHERE NOT EXISTS (SELECT 1 FROM discount_conditions WHERE discount_id = d.id)
  LOOP
    app_kind := COALESCE(d_rec.discount_value->>'applicability', 'TO_ORDER');
    -- Universal fallback: minimum cart amount = 0 (always satisfied).
    -- For TO_PRODUCT discounts the project should override with a CATEGORY/PRODUCT
    -- condition via blueprint emission; this row keeps the discount evaluable.
    INSERT INTO discount_conditions (discount_id, condition_type, entity_ids, value)
    VALUES (d_rec.id, 'MIN_CART_AMOUNT'::discount_condition_type_enum, '[]'::jsonb,
            jsonb_build_object('amount', 0));
    seeded := seeded + 1;
  END LOOP;
  RAISE NOTICE 'seeded % default discount_conditions rows', seeded;
END $$;
"""
    import subprocess
    try:
        result = subprocess.run(
            ['docker', 'exec', 'cms-sb-db', 'psql', '-U', 'postgres', '-d', 'test_db_cms3', '-c', sql],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.append(f'  FAIL psql exit {result.returncode}: {result.stderr[:600]}\n')
            return 0, 1, 0
        log.append(f'  OK discount conditions seeded\n')
        for line in (result.stderr or '').strip().splitlines()[-3:]:
            if 'NOTICE' in line: log.append(f'  {line.strip()}\n')
        return 1, 0, 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.append(f'  SKIP: docker exec not available ({type(e).__name__})\n')
        return 0, 0, 1


def task_bind_orphan_forms_to_modules(cms_url, token, mapped, log, dry_run):
    """B2 — Every form must be bound to a module via form_module_config.

    Universal — drives binding from `forms.type` (universal enum across verticals):
      order        → module 'orders'        (storefront checkout submit)
      signin/login → module 'users'         (auth)
      subscription → module 'subscriptions' (newsletter / event)
      rating/review→ module 'forms'         (generic form-data viewer)
      data         → module 'forms'         (generic)
      DEFAULT      → module 'forms'

    Idempotent — only binds forms that have NO form_module_config row.
    """
    log.append('\n## 8.2 Orphan forms — module binding\n')
    if dry_run:
        log.append('  DRY-RUN — skipping\n')
        return 0, 0, 0
    sql = r"""
DO $$
DECLARE
  f_rec record;
  mod_ident text;
  mod_id int;
  bound int := 0;
BEGIN
  FOR f_rec IN
    SELECT f.id, f.type::text AS ftype FROM forms f
    WHERE NOT EXISTS (SELECT 1 FROM form_module_config WHERE form_id = f.id)
  LOOP
    mod_ident := CASE f_rec.ftype
      WHEN 'order'        THEN 'orders'
      WHEN 'signin'       THEN 'users'
      WHEN 'login'        THEN 'users'
      WHEN 'subscription' THEN 'subscriptions'
      WHEN 'rating'       THEN 'forms'
      WHEN 'review'       THEN 'forms'
      WHEN 'data'         THEN 'forms'
      ELSE 'forms'
    END;
    SELECT id INTO mod_id FROM modules WHERE identifier = mod_ident LIMIT 1;
    IF mod_id IS NULL THEN
      SELECT id INTO mod_id FROM modules WHERE identifier = 'forms' LIMIT 1;
    END IF;
    IF mod_id IS NULL THEN
      RAISE NOTICE 'no fallback module for form id=%', f_rec.id;
      CONTINUE;
    END IF;
    INSERT INTO form_module_config
      (module_id, form_id, entity_identifiers, is_global, is_closed,
       is_moderate, view_only_user_data, comment_only_user_data)
    VALUES (mod_id, f_rec.id, '[]'::json, false, false, false, false, false)
    ON CONFLICT (module_id, form_id) DO NOTHING;
    bound := bound + 1;
  END LOOP;
  RAISE NOTICE 'bound % orphan forms to modules', bound;
END $$;
"""
    import subprocess
    try:
        result = subprocess.run(
            ['docker', 'exec', 'cms-sb-db', 'psql', '-U', 'postgres', '-d', 'test_db_cms3', '-c', sql],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.append(f'  FAIL psql exit {result.returncode}: {result.stderr[:600]}\n')
            return 0, 1, 0
        log.append('  OK forms bound\n')
        for line in (result.stderr or '').strip().splitlines()[-3:]:
            if 'NOTICE' in line: log.append(f'  {line.strip()}\n')
        return 1, 0, 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.append(f'  SKIP: docker exec not available ({type(e).__name__})\n')
        return 0, 0, 1


def task_merge_duplicate_collections(cms_url, token, mapped, log, dry_run):
    """B3 — Merge `X` + `X_list` / `X_data` / `X_items` duplicate-collection pairs.

    Universal — when the mapper emits both a "logical" and a "raw" collection for
    the same payload (e.g. `stores` (visible, 0 rows) + `stores_list` (hidden,
    10 rows)), the visible one would show empty on storefront. Detection rule:
      pair (X, X+suffix) where suffix ∈ {_list, _data, _items, _all}
    Action: move every collection_rows row from twin → X, then DELETE twin.

    Idempotent — only acts on pairs where X has 0 rows AND twin has ≥1 row.
    """
    log.append('\n## 8.3 Merge duplicate collections (X / X_list / X_data / X_items)\n')
    if dry_run:
        log.append('  DRY-RUN — skipping\n')
        return 0, 0, 0
    sql = r"""
DO $$
DECLARE
  base_rec record;
  twin_rec record;
  suffix text;
  merged int := 0;
BEGIN
  FOR base_rec IN
    SELECT c.id, c.identifier FROM collections c
    WHERE NOT EXISTS (SELECT 1 FROM collection_rows WHERE collection_id = c.id)
  LOOP
    FOREACH suffix IN ARRAY ARRAY['_list','_data','_items','_all'] LOOP
      SELECT t.id, (SELECT COUNT(*) FROM collection_rows WHERE collection_id=t.id) AS rows
      INTO twin_rec
      FROM collections t WHERE t.identifier = base_rec.identifier || suffix LIMIT 1;
      IF twin_rec.id IS NOT NULL AND twin_rec.rows > 0 THEN
        UPDATE collection_rows SET collection_id = base_rec.id WHERE collection_id = twin_rec.id;
        DELETE FROM collections WHERE id = twin_rec.id;
        merged := merged + 1;
        EXIT; -- one twin per base
      END IF;
    END LOOP;
  END LOOP;
  RAISE NOTICE 'merged % duplicate collection pairs', merged;
END $$;
"""
    import subprocess
    try:
        result = subprocess.run(
            ['docker', 'exec', 'cms-sb-db', 'psql', '-U', 'postgres', '-d', 'test_db_cms3', '-c', sql],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.append(f'  FAIL psql exit {result.returncode}: {result.stderr[:600]}\n')
            return 0, 1, 0
        log.append('  OK duplicate collections merged\n')
        for line in (result.stderr or '').strip().splitlines()[-3:]:
            if 'NOTICE' in line: log.append(f'  {line.strip()}\n')
        return 1, 0, 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.append(f'  SKIP: docker exec not available ({type(e).__name__})\n')
        return 0, 0, 1


def task_seed_missing_order_statuses(cms_url, token, mapped, log, dry_run):
    """B4 — Ensure the canonical 7-status order lifecycle exists.

    Universal — every OneEntry project that has `orders_storage` benefits from
    the full lifecycle: new → processing → shipped → delivered → done →
    cancelled / refunded. Without `shipped`/`delivered` integrators have no
    valid state to record "package handed to carrier" / "package received".

    Idempotent — only inserts statuses missing by `identifier`. Uses the lowest
    `orders_storage.id` if multiple exist; localize_infos are en_US-only
    canonical labels (project can rename in admin).
    """
    log.append('\n## 8.4 Order statuses — seed canonical lifecycle\n')
    if dry_run:
        log.append('  DRY-RUN — skipping\n')
        return 0, 0, 0
    canonical = [
        ('new',        'New',         1, True),
        ('processing', 'Processing',  2, False),
        ('shipped',    'Shipped',     3, False),
        ('delivered',  'Delivered',   4, False),
        ('done',       'Done',        5, False),
        ('cancelled',  'Cancelled',   6, False),
        ('refunded',   'Refunded',    7, False),
    ]
    sql_template = r"""
DO $$
DECLARE
  storage_id_v int;
  pos_id int;
  inserted_status_id int;
  inserted int := 0;
BEGIN
  SELECT id INTO storage_id_v FROM orders_storage ORDER BY id LIMIT 1;
  IF storage_id_v IS NULL THEN
    RAISE NOTICE 'no orders_storage — skipping';
    RETURN;
  END IF;
  -- {{STATUSES_SQL}}
  RAISE NOTICE 'inserted % missing order statuses', inserted;
END $$;
"""
    statuses_sql = []
    for ident, title, pos_idx, is_default in canonical:
        statuses_sql.append(f"""
  IF NOT EXISTS (SELECT 1 FROM order_statuses WHERE identifier = '{ident}') THEN
    INSERT INTO order_statuses (identifier, localize_infos, is_default, storage_id)
    VALUES ('{ident}', '{{"en_US": {{"title": "{title}"}}}}'::json,
            {str(is_default).lower()}, storage_id_v)
    RETURNING id INTO inserted_status_id;
    INSERT INTO positions (position, object_id, object_type)
    VALUES ('0|izzzzz:' || lpad({pos_idx}::text, 3, '0'), inserted_status_id, 'order-storage-order-status')
    RETURNING id INTO pos_id;
    UPDATE order_statuses SET position_id = pos_id WHERE id = inserted_status_id;
    inserted := inserted + 1;
  END IF;""")
    sql = sql_template.replace('-- {{STATUSES_SQL}}', '\n'.join(statuses_sql))
    import subprocess
    try:
        result = subprocess.run(
            ['docker', 'exec', 'cms-sb-db', 'psql', '-U', 'postgres', '-d', 'test_db_cms3', '-c', sql],
            capture_output=True, text=True, timeout=60,
        )
        if result.returncode != 0:
            log.append(f'  FAIL psql exit {result.returncode}: {result.stderr[:600]}\n')
            return 0, 1, 0
        log.append('  OK order statuses seeded\n')
        for line in (result.stderr or '').strip().splitlines()[-3:]:
            if 'NOTICE' in line: log.append(f'  {line.strip()}\n')
        return 1, 0, 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        log.append(f'  SKIP: docker exec not available ({type(e).__name__})\n')
        return 0, 0, 1


def task_post_import_page_errors(cms_url, token, mapped, log, dry_run):
    """Bind HTTP error codes to error pages.

    Reads `mapped.post_import_page_errors[]` (built by post-mapper-fixer for
    Next.js apps that ship `not-found.tsx` / `error.tsx` / similar). The
    `page_errors` table is **OUT** of the blueprint whitelist (confirmed at
    the OneEntry Platform blueprint loader (verified against `BlueprintLoaderService.ALLOWED_TABLES`)),
    so each row is created via:
      1. POST /api/admin/page-errors   body={code: 404}   -> returns {id}
      2. PUT  /api/admin/page-errors/:id/set-error-page  body={pageId: <pageId>}

    Idempotent: existing codes are looked up via GET and re-bound rather than
    POSTed twice.
    """
    log.append('\n## 6. Error pages binding (post-import)\n')
    tasks = (mapped or {}).get('post_import_page_errors') or []
    if not tasks:
        log.append('  no `post_import_page_errors[]` tasks — skip\n')
        return 0, 0, 1

    existing_pages = list_pages(cms_url, token, '/api/admin/pages', page_param=True, limit=500)
    ident_to_page_id = {p.get('identifier'): p.get('id') for p in existing_pages if p.get('identifier')}

    # GET existing page_errors to know which codes already exist.
    status, existing_errors = http('GET', f'{cms_url}/api/admin/page-errors', token=token)
    if status != 200 or not isinstance(existing_errors, list):
        existing_errors = []
    code_to_error_id = {row.get('code'): row.get('id') for row in existing_errors
                        if isinstance(row, dict)}

    ok, fail, skip = 0, 0, 0
    for t in tasks:
        code = t.get('http_code')
        page_ident = t.get('page_identifier')
        if not isinstance(code, int) or not page_ident:
            log.append(f"  SKIP malformed task: {t}\n")
            skip += 1
            continue

        page_id = ident_to_page_id.get(page_ident)
        if not page_id:
            log.append(f"  FAIL page '{page_ident}' not found in CMS — cannot bind code {code}\n")
            fail += 1
            continue

        error_id = code_to_error_id.get(code)
        if error_id is None:
            if dry_run:
                log.append(f"  [DRY] POST /page-errors body={{code:{code}}}\n")
                error_id = -1  # placeholder for dry-run binding log below
            else:
                status, resp = http('POST', f'{cms_url}/api/admin/page-errors',
                                    token=token, data={'code': code})
                if status not in (200, 201) or not isinstance(resp, dict):
                    log.append(f"  FAIL POST /page-errors code={code}: HTTP {status} {resp}\n")
                    fail += 1
                    continue
                error_id = resp.get('id')
                code_to_error_id[code] = error_id
                log.append(f"  OK code {code} created (page_errors.id={error_id})\n")

        if dry_run:
            log.append(f"  [DRY] PUT /page-errors/{error_id}/set-error-page "
                       f"body={{pageId:{page_id}}} (page='{page_ident}')\n")
            ok += 1
            continue

        status, resp = http('PUT', f'{cms_url}/api/admin/page-errors/{error_id}/set-error-page',
                            token=token, data={'pageId': page_id})
        if status in (200, 201):
            log.append(f"  OK bound code {code} -> page '{page_ident}' (id={page_id})\n")
            ok += 1
        else:
            log.append(f"  FAIL set-error-page code={code} page='{page_ident}': HTTP {status} {resp}\n")
            fail += 1

    return ok, fail, skip


def task_post_import_menus(cms_url, token, blueprint, mapped, log, dry_run):
    """Create menus + custom-items from `mapped.post_import_menus[]`.

    REST contract (verified against the OneEntry menus DTOs):
      * `POST /api/admin/menus` — body uses **camelCase** `localizeInfos` and
        accepts `pagesIds: number[]` (and optional `pinnedIds`, `isPinned`).
        ALL page items are passed in this single call — there is NO
        `POST /:id/pages` endpoint to add page items afterwards.
      * `POST /api/admin/menus/:id/custom-items` — body has ONLY `localizeInfos`
        and `value`. `parent_id` / `identifier` are NOT accepted (class-validator
        whitelist rejects unknown keys).
      * Late additions of pages to an existing menu go through `PUT /menus/:id`
        (UpdateMenuDto, which also takes `pagesIds`).

    Idempotency: if the identifier already exists we reuse it; new pages are
    added via PUT (full pagesIds list = existing ∪ requested).
    """
    log.append('\n## 4. Menus (post-import)\n')

    tasks = (mapped or {}).get('post_import_menus') or []
    if not tasks:
        log.append('  no `post_import_menus[]` tasks in mapped.yaml — skip\n')
        return 0, 0, 1

    # Build page_slug -> page_id map from the loaded blueprint (pages we just
    # uploaded). We cannot trust @page.<slug> tokens here — the loader resolved
    # them to integer ids. Re-fetch from the CMS to get the real ids.
    existing_pages = list_pages(cms_url, token, '/api/admin/pages', page_param=True, limit=500)
    slug_to_page_id = {p.get('identifier'): p.get('id') for p in existing_pages if p.get('identifier')}

    # Existing menus — for idempotency.
    existing_menus = list_pages(cms_url, token, '/api/admin/menus', page_param=True, limit=200)
    ident_to_menu = {m.get('identifier'): m for m in existing_menus if m.get('identifier')}

    ok, fail, skip = 0, 0, 0
    for task in tasks:
        ident = task.get('identifier')
        if not ident:
            log.append(f"  FAIL menu task missing identifier: {task}\n")
            fail += 1
            continue
        log.append(f"\n### Menu `{ident}`\n")

        # Resolve all page slugs upfront — we need pagesIds list for both
        # create and update flows.
        wanted_page_ids = []
        for item in (task.get('items') or []):
            slug = item.get('page_slug')
            pid = slug_to_page_id.get(slug)
            if not pid:
                log.append(f"  SKIP page slug='{slug}' — not found in pages\n")
                skip += 1
                continue
            if pid not in wanted_page_ids:
                wanted_page_ids.append(pid)

        # --- 1. Create or reuse the menu itself ---
        existing_menu = ident_to_menu.get(ident)
        if existing_menu:
            menu_id = existing_menu.get('id')
            log.append(f"  reuse menu id={menu_id} (already exists)\n")

            # Fetch full menu to know which pages are already linked,
            # then PUT with merged list if there are new ones.
            status, full = http('GET', f"{cms_url}/api/admin/menus/{menu_id}", token=token)
            existing_page_ids = []
            if status == 200 and isinstance(full, dict):
                for it in (full.get('pages') or full.get('menuPages') or []):
                    pid = it.get('pageId') or it.get('page_id') or (it.get('page') or {}).get('id')
                    if pid and pid not in existing_page_ids:
                        existing_page_ids.append(pid)
            new_pages = [pid for pid in wanted_page_ids if pid not in existing_page_ids]
            if new_pages:
                merged = existing_page_ids + new_pages
                put_body = {'pagesIds': merged}
                if dry_run:
                    log.append(f"  [DRY] PUT /menus/{menu_id} pagesIds={merged}\n")
                    ok += 1
                else:
                    status, resp = http('PUT', f'{cms_url}/api/admin/menus/{menu_id}', token=token, data=put_body)
                    if status in (200, 201):
                        log.append(f"  OK merged pagesIds (+{len(new_pages)} new)\n")
                        ok += 1
                    else:
                        log.append(f"  FAIL PUT /menus/{menu_id}: HTTP {status} {resp}\n")
                        fail += 1
            else:
                log.append("  no new pages to add\n")
                skip += 1
        else:
            # ⚠ The OneEntry Platform `base-menus.service.create` path does NOT
            # initialise `menu_pages_mn.position_id` for the menuPages cascade
            # save — POSTing /menus with a non-empty `pagesIds` array fails with
            # `null value in column page_id of relation menu_pages_mn violates
            # not-null constraint`. The `update` path (PUT /menus/:id) DOES
            # build each MenuPageEntity with explicit `positionId` via
            # `createPosition(...)`. Workaround: 2-step create — POST with empty
            # pagesIds, then PUT to add the pages.
            base_body = {
                'identifier': ident,
                'localizeInfos': task.get('localizeInfos')
                                or task.get('localize_infos')
                                or {'en_US': {'title': ident.replace('-', ' ').title()}},
                'pagesIds': [],
            }
            if dry_run:
                log.append(f"  [DRY] POST /menus identifier='{ident}' (empty); "
                           f"PUT /menus/:id pagesIds={wanted_page_ids}\n")
                ok += 1
                continue
            status, resp = http('POST', f'{cms_url}/api/admin/menus', token=token, data=base_body)
            if status not in (200, 201):
                log.append(f"  FAIL POST /menus '{ident}': HTTP {status} {resp}\n")
                fail += 1
                continue
            menu_id = resp.get('id')
            if wanted_page_ids:
                put_body = {'pagesIds': wanted_page_ids}
                status, resp = http('PUT', f'{cms_url}/api/admin/menus/{menu_id}',
                                    token=token, data=put_body)
                if status in (200, 201):
                    log.append(f"  OK created menu id={menu_id} + PUT {len(wanted_page_ids)} pages\n")
                else:
                    log.append(f"  FAIL PUT /menus/{menu_id} pagesIds: HTTP {status} {resp}\n")
                    fail += 1
                    continue
            else:
                log.append(f"  OK created menu id={menu_id} (no pages)\n")
            ok += 1

        # --- 2. Custom items (external URLs / anchors / mailto) ---
        # CreateMenuCustomItemDto accepts ONLY { localizeInfos, value }.
        # parent_id / identifier are NOT in the DTO — class-validator whitelist rejects them.
        status, existing_full = http('GET', f"{cms_url}/api/admin/menus/{menu_id}", token=token)
        existing_custom_values = set()
        if status == 200 and isinstance(existing_full, dict):
            for ci in (existing_full.get('customItems') or existing_full.get('custom_items') or []):
                v = ci.get('value')
                if v:
                    existing_custom_values.add(v)

        for ci in (task.get('custom_items') or task.get('customItems') or []):
            ci_value = ci.get('value', '')
            if not ci_value:
                log.append(f"  SKIP custom-item without value: {ci}\n")
                skip += 1
                continue
            if ci_value in existing_custom_values:
                log.append(f"  skip custom-item value='{ci_value}' — already exists\n")
                skip += 1
                continue
            body = {
                'value': ci_value,
                'localizeInfos': ci.get('localizeInfos')
                                or ci.get('localize_infos')
                                or {'en_US': {'title': ci_value}},
            }
            if dry_run:
                log.append(f"  [DRY] POST /menus/{menu_id}/custom-items value='{ci_value}'\n")
                ok += 1
                continue
            status, resp = http('POST', f'{cms_url}/api/admin/menus/{menu_id}/custom-items',
                                token=token, data=body)
            if status in (200, 201):
                log.append(f"  OK custom-item '{ci_value}' (id={resp.get('id')})\n")
                ok += 1
            else:
                log.append(f"  FAIL custom-item '{ci_value}': HTTP {status} {resp}\n")
                fail += 1

    return ok, fail, skip


def task_post_import_filters(cms_url, token, blueprint, mapped, log, dry_run):
    """Create filters + attach attribute/page/product items from
    `mapped.post_import_filters[]`.

    Status: stub — full algorithm lives in `rules/post-import-orchestration.md`
    Step 7 and `rules/filters-setup.md` §7. This function reads the tasks and
    logs them as a manual-action checklist; the actual REST loop is intentionally
    NOT yet implemented in this script because:
      1. `filter_items_mn` has no UNIQUE constraint — the orchestrator MUST use
         `PUT /filters/:id/items/attribute/replace` (idempotent atomic replace),
         not `POST /:id/items` (creates duplicates on re-run).
      2. The list of direct (`page`/`product`/`discount`/`payment-method`) items
         cannot be resolved by identifier through admin REST — those must be
         attached via the OneEntry Platform UI.

    Until the replace endpoint is wired up here, the orchestrator emits the
    task list into the report so an operator can finish setup in the UI.
    """
    log.append('\n## 5. Filters (catalog facets) — stub\n')
    tasks = (mapped or {}).get('post_import_filters') or []
    if not tasks:
        log.append('  no `post_import_filters[]` tasks in mapped.yaml — skip\n')
        return 0, 0, 1
    log.append(f'  found {len(tasks)} filter tasks — manual action required\n')
    for t in tasks:
        ident = t.get('identifier', '?')
        attrs = ', '.join(t.get('attribute_identifiers') or []) or '(none)'
        log.append(
            f"  - filter '{ident}': scope={t.get('scope_types') or ['attribute']}, "
            f"attribute_identifiers=[{attrs}] -> create via OneEntry Platform UI "
            f"OR via PUT /api/admin/filters/:id/items/attribute/replace (see rules/filters-setup.md §7.2.1)\n"
        )
    return 0, 0, len(tasks)


def task_post_import_markers(cms_url, token, mapped, log, dry_run):
    """Create markers from `mapped.post_import_markers[]`.

    Status: stub. Endpoint contract from `rules/post-import-orchestration.md`
    Step 5: `POST /api/admin/markers` with `{ identifier, localizeInfos }`. This
    function reads the list and logs it; actual implementation requires the
    project to ship a `MarkerEntity`-shape list in `mapped`, and most current
    pipelines do NOT populate `post_import_markers[]`.

    Implement the REST loop when an active project needs automated marker
    creation.
    """
    log.append('\n## 6. Markers — stub\n')
    tasks = (mapped or {}).get('post_import_markers') or []
    if not tasks:
        log.append('  no `post_import_markers[]` tasks in mapped.yaml — skip\n')
        return 0, 0, 1
    log.append(f'  found {len(tasks)} marker tasks — to be implemented; recorded as manual action\n')
    for t in tasks:
        ident = t.get('identifier', '?')
        log.append(f"  - marker '{ident}' (POST /api/admin/markers manually)\n")
    return 0, 0, len(tasks)


def task_post_import_discounts(cms_url, token, blueprint, mapped, log, dry_run):
    """Create discounts from `mapped.post_import_discounts[]`.

    Endpoint contract from `rules/discounts-setup.md` §6:
      POST /api/admin/discounts  body=CreateDiscountDto (camelCase)
      POST /api/admin/discounts/:id/coupons  body={code, usageLimit?}

    For each task:
      1. Resolve conditions[].value_slug → DB product_id via /api/admin/pages (since
         product references in the blueprint share names with their pages — orchestrator
         looks up via blueprint.tables.products[] index).
      2. Skip create if discount with the same identifier exists.
      3. POST discount → POST coupons (if any).
    """
    log.append('\n## 7. Discounts (post-import)\n')
    tasks = (mapped or {}).get('post_import_discounts') or []
    if not tasks:
        log.append('  no `post_import_discounts[]` tasks in mapped.yaml — skip\n')
        return 0, 0, 1

    # Build slug → DB id maps from blueprint registry (loader returns registry in import response, but
    # we don't have it here; fall back to GET /api/admin/products + /api/admin/pages and match by identifier).
    existing_products = list_pages(cms_url, token, '/api/admin/products', page_param=True, limit=500)
    prod_slug_to_id = {p.get('identifier'): p.get('id') for p in existing_products if p.get('identifier')}

    existing_pages = list_pages(cms_url, token, '/api/admin/pages', page_param=True, limit=500)
    page_slug_to_id = {p.get('identifier'): p.get('id') for p in existing_pages if p.get('identifier')}

    existing_discounts = list_pages(cms_url, token, '/api/admin/discounts', page_param=True, limit=200)
    existing_idents = {d.get('identifier') for d in existing_discounts if d.get('identifier')}

    ok = fail = skip = 0
    for t in tasks:
        ident = t.get('identifier')
        if not ident:
            fail += 1
            log.append(f"  FAIL discount task missing identifier: {t}\n")
            continue
        if ident in existing_idents:
            log.append(f"  SKIP discount '{ident}' — already exists\n")
            skip += 1
            continue

        # Resolve condition value_slug → DB id.
        # The real DiscountConditionDto contract (verified at
        # the OneEntry Platform `DiscountConditionDto`):
        #   {
        #     conditionType: DiscountConditionType,
        #     entityIds?: EntityIdentifier[],      // [{id: number|string, isNested?: bool}, ...]
        #     value?: Record<string, any>,         // e.g. {amount: 1000} for MIN_CART_AMOUNT
        #   }
        # The earlier shape `{type, value}` is OUTDATED — class-validator will reject.
        resolved_conditions = []
        unresolved = []
        for cond in (t.get('conditions') or []):
            ctype = cond.get('type') or cond.get('condition_type') or cond.get('conditionType')
            slug = cond.get('value_slug')
            raw_value = cond.get('value')
            built = {'conditionType': ctype}
            if ctype == 'PRODUCT':
                if isinstance(raw_value, int):
                    built['entityIds'] = [{'id': raw_value}]
                elif slug:
                    pid = prod_slug_to_id.get(slug)
                    if pid is None:
                        unresolved.append(f"PRODUCT={slug}")
                        continue
                    built['entityIds'] = [{'id': pid}]
                else:
                    continue
            elif ctype in ('CATEGORY', 'CATEGORY_IN_CART'):
                if isinstance(raw_value, int):
                    built['entityIds'] = [{'id': raw_value, 'isNested': True}]
                elif slug:
                    pid = page_slug_to_id.get(slug)
                    if pid is None:
                        unresolved.append(f"CATEGORY={slug}")
                        continue
                    built['entityIds'] = [{'id': pid, 'isNested': True}]
                else:
                    continue
            elif ctype in ('PRODUCT_IN_CART',):
                # entity-ids list of products that need to be present in the cart
                if isinstance(raw_value, list):
                    built['entityIds'] = [
                        {'id': v} if not isinstance(v, dict) else v for v in raw_value
                    ]
                elif slug:
                    pid = prod_slug_to_id.get(slug)
                    if pid is None:
                        unresolved.append(f"PRODUCT_IN_CART={slug}")
                        continue
                    built['entityIds'] = [{'id': pid}]
                else:
                    continue
            elif ctype in ('MIN_CART_AMOUNT',):
                # value-object condition (no entityIds)
                if isinstance(raw_value, dict):
                    built['value'] = raw_value
                elif isinstance(raw_value, (int, float)):
                    built['value'] = {'amount': raw_value}
                else:
                    continue
            elif ctype in ('ATTRIBUTE', 'USER_ATTRIBUTE'):
                # require both entity-id (attribute id) AND value object
                if isinstance(raw_value, dict):
                    built['value'] = raw_value
                if slug:
                    # attribute identifier passed as slug — orchestrator can't
                    # resolve attribute id without GET /attributes; punt and warn
                    unresolved.append(f"ATTRIBUTE={slug} (resolve attribute id manually)")
                    continue
            elif ctype in ('USER_LTV',):
                if isinstance(raw_value, dict):
                    built['value'] = raw_value
                elif isinstance(raw_value, (int, float)):
                    built['value'] = {'amount': raw_value}
                else:
                    continue
            else:
                # Unknown / future condition types — pass through if value object provided.
                if isinstance(raw_value, dict):
                    built['value'] = raw_value
                else:
                    continue
            resolved_conditions.append(built)

        if unresolved:
            log.append(f"  WARN discount '{ident}' — unresolved condition slugs: {unresolved} (will still POST with what resolved)\n")

        dv = t.get('discount_value') or {}
        # Default validity window: 7 days from "now" so the discount is active
        # by default. The admin can extend / shrink in the Discounts module —
        # but without an end_date the discount is treated as "no period set"
        # in the UI and the dropdown looks broken. Sources rarely declare a
        # validity period for percent-off campaigns, so 1 week is a sensible
        # default that any project type benefits from (e-commerce flash sale,
        # restaurant happy hour, salon promo, SaaS trial).
        from datetime import datetime, timedelta, timezone
        now_iso = datetime.now(timezone.utc).replace(microsecond=0).isoformat()
        end_iso = (datetime.now(timezone.utc) + timedelta(days=7)).replace(microsecond=0).isoformat()
        body = {
            'identifier':     ident,
            'type':           t.get('type', 'DISCOUNT'),
            'localizeInfos':  t.get('localize_infos') or {'en_US': {'title': ident}},
            # ⚠ DiscountValueConfigDto field name is `discountType`, NOT `type`.
            # If you send `type`, the value lands in the entity JSON verbatim
            # but the admin UI (`DiscountsValueSettings.js`) reads
            # `pageObject.discountValue.discountType` and shows an empty
            # "Choose discount type" dropdown.
            'discountValue':  {
                'discountType':   dv.get('type') or dv.get('discount_type') or dv.get('discountType', 'PERCENTAGE'),
                'applicability':  dv.get('applicability', 'TO_ORDER'),
                'value':          dv.get('value', 0),
            },
            'conditionLogic': t.get('condition_logic', 'OR'),
            'conditions':     resolved_conditions,
            'userGroups':     [],
            'exclusions':     [],
            'gifts':          [],
            'giftsReplaceCartItems': False,
            'startDate':      t.get('start_date') or now_iso,
            'endDate':        t.get('end_date') or end_iso,
        }
        if dry_run:
            log.append(f"  DRY discount '{ident}': {body}\n")
            ok += 1
            continue
        status, resp = http('POST', f'{cms_url}/api/admin/discounts', token=token, data=body)
        if status not in (200, 201):
            fail += 1
            log.append(f"  FAIL discount '{ident}': HTTP {status} {resp}\n")
            continue
        ok += 1
        new_id = resp.get('id') if isinstance(resp, dict) else None
        log.append(f"  OK discount '{ident}' created (id={new_id})\n")

        # POST coupons (if any).
        # Real CreateDiscountCouponDto accepts ONLY {code} — verified at
        # the OneEntry Platform `CreateDiscountCouponDto`. The
        # `usageLimit` field does NOT exist on the coupon DTO; if class-validator
        # whitelist is enabled it would be silently dropped. If `usage_limit` is
        # set on the task we log it but do not send it (the admin must configure
        # usage limits manually in the UI for now).
        for c in (t.get('coupons') or []):
            code = c.get('code')
            if not code or not new_id:
                continue
            cbody = {'code': code}
            if c.get('usage_limit') is not None:
                log.append(f"    NOTE coupon '{code}': usage_limit={c['usage_limit']} "
                           f"is NOT in CreateDiscountCouponDto — admin must set "
                           f"usage limit manually in admin UI.\n")
            cstatus, cresp = http('POST', f'{cms_url}/api/admin/discounts/{new_id}/coupons', token=token, data=cbody)
            if cstatus in (200, 201):
                log.append(f"    coupon '{code}' attached\n")
            else:
                log.append(f"    coupon '{code}' FAIL HTTP {cstatus} {cresp}\n")

    return ok, fail, skip


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('blueprint_json')
    parser.add_argument('mapped_yaml')
    parser.add_argument('--cms-url', required=True)
    parser.add_argument('--login', required=True)
    parser.add_argument('--password', required=True)
    parser.add_argument('--project-root', default='.')
    parser.add_argument('--dry-run', action='store_true')
    parser.add_argument('--report')
    args = parser.parse_args()

    blueprint = json.load(open(args.blueprint_json))
    mapped = yaml.safe_load(open(args.mapped_yaml))

    print(f'Logging in to {args.cms_url}...')
    token = login(args.cms_url, args.login, args.password)
    print('OK')

    log = []
    log.append(f'# Post-Import Orchestration\n')
    log.append(f'**CMS:** {args.cms_url}')
    log.append(f'**Dry-run:** {args.dry_run}\n')

    total_ok, total_fail, total_skip = 0, 0, 0

    for name, func in [
        ('user_permissions', lambda: task_user_permissions(args.cms_url, token, log, args.dry_run)),
        ('integration_collections', lambda: task_integration_collections(args.cms_url, token,
                                                                          args.project_root, mapped,
                                                                          log, args.dry_run)),
        ('form_module_config', lambda: task_form_module_config(args.cms_url, token, mapped, log, args.dry_run)),
        ('post_import_menus', lambda: task_post_import_menus(args.cms_url, token,
                                                              blueprint, mapped, log, args.dry_run)),
        ('post_import_filters', lambda: task_post_import_filters(args.cms_url, token,
                                                                  blueprint, mapped, log, args.dry_run)),
        ('post_import_markers', lambda: task_post_import_markers(args.cms_url, token, mapped, log, args.dry_run)),
        ('post_import_discounts', lambda: task_post_import_discounts(args.cms_url, token,
                                                                       blueprint, mapped, log, args.dry_run)),
        ('post_import_payment_status_maps',
         lambda: task_post_import_payment_status_maps(args.cms_url, token, mapped, log, args.dry_run)),
        ('post_import_page_errors',
         lambda: task_post_import_page_errors(args.cms_url, token, mapped, log, args.dry_run)),
        ('post_import_slides',
         lambda: task_post_import_slides(args.cms_url, token, mapped, log, args.dry_run)),
        ('align_attribute_keys',
         lambda: task_align_attribute_keys(args.cms_url, token, mapped, log, args.dry_run)),
        ('normalize_attribute_value_shapes',
         lambda: task_normalize_attribute_value_shapes(args.cms_url, token, mapped, log, args.dry_run)),
        ('ensure_standard_user_groups',
         lambda: task_ensure_standard_user_groups(args.cms_url, token, mapped, log, args.dry_run)),
        ('backfill_missing_attribute_keys',
         lambda: task_backfill_missing_attribute_keys(args.cms_url, token, mapped, log, args.dry_run)),
        ('wrap_text_values_in_editor_shape',
         lambda: task_wrap_text_values_in_editor_shape(args.cms_url, token, mapped, log, args.dry_run)),
        ('seed_default_discount_conditions',
         lambda: task_seed_default_discount_conditions(args.cms_url, token, mapped, log, args.dry_run)),
        ('bind_orphan_forms_to_modules',
         lambda: task_bind_orphan_forms_to_modules(args.cms_url, token, mapped, log, args.dry_run)),
        ('merge_duplicate_collections',
         lambda: task_merge_duplicate_collections(args.cms_url, token, mapped, log, args.dry_run)),
        ('seed_missing_order_statuses',
         lambda: task_seed_missing_order_statuses(args.cms_url, token, mapped, log, args.dry_run)),
    ]:
        try:
            ok, fail, skip = func()
            total_ok += ok
            total_fail += fail
            total_skip += skip
        except Exception as e:
            log.append(f'\n  FAIL task {name} crashed: {e}\n')
            total_fail += 1

    log.append(f'\n## Summary\n')
    log.append(f'- OK: {total_ok}')
    log.append(f'- FAIL: {total_fail}')
    log.append(f'- SKIPPED: {total_skip}\n')
    # Dynamic warning about social auth providers (if present in mapped)
    social_providers = [p for p in (mapped.get('users_auth_providers') or [])
                        if p.get('type') == 'social']
    if social_providers:
        names = ', '.join(p.get('identifier', '?') for p in social_providers)
        log.append(f'\n## 4. OAuth credentials (manual step)\n')
        log.append(f'  WARNING: social auth-providers require manual OAuth credentials setup in CMS:\n')
        for p in social_providers:
            log.append(f"    - **{p.get('identifier')}** ({p.get('type')}) — Settings → Auth Providers → {p.get('identifier')} → config:")
            log.append(f"      `client_id`, `client_secret`, `redirect_uri` (obtain from the provider console)")
        log.append('\n  Without this configuration, login via social networks will not work.\n')

    log.append('\n## Manual tasks (secrets/complex config)\n')
    log.append('- **payment_accounts**: Settings → Payment Accounts → Stripe/Yookassa API keys + webhook URL')
    log.append('- **SMTP / notice-service**: configure the email provider (if there are processing_type=email forms)')
    log.append('- **Email templates**: Settings → Email Templates → for contact/feedback')
    if social_providers:
        log.append(f'- **OAuth credentials**: {names} (see section 4 above)')
    log.append('- **DYNAMIC block ids**: if the customer\'s prod ids differ from the snapshot — change them via the OneEntry Platform UI\n')

    report_path = args.report or args.blueprint_json.replace('.blueprint.json', '.post-import.log.md')
    with open(report_path, 'w') as f:
        f.write('\n'.join(log) if log else '(empty)')
    print(f'\nReport: {report_path}')
    print(f'OK={total_ok}, FAIL={total_fail}, SKIPPED={total_skip}')

    return 0 if total_fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
