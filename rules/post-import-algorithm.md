# Post-import orchestration — Algorithm details

> **Companion file** to `post-import-orchestration.md` (overview / contract / report format live there). This file holds the per-step algorithm only — long enough to deserve its own file under the Claude Code 40k context-cost threshold.

> **⚠ Universality note.** Steps below are vertical-agnostic (e-commerce / restaurant / salon / hotel / EdTech / corporate / personal cabinet / SaaS) — substitute domain vocabulary as needed.

## Algorithm

### Step 1. Read blueprint + mapped warnings

From `mapped.yaml.warnings`, extract `out-of-whitelist:` markers:

```python
import yaml
mapped = yaml.safe_load(open(mapped_yaml_path))
oow_tasks = []
for w in (mapped.get('warnings') or []):
    if 'out-of-whitelist:' in w:
        oow_tasks.append(parse_oow_warning(w))
```

Also from the blueprint — extract the list of data forms (for form_module_config) and user_groups (for permissions).

### Step 1.5 — Build identifier → ID maps for downstream steps

After the loader call (Step 5 of the parent pipeline), the orchestrator needs to translate string identifiers (`women-clothing`, `signin`, `forProducts`, `user`) into numeric DB IDs to attach things via REST.

⚠ The CMS does NOT expose a uniform `GET /<table>/marker/:marker` endpoint that returns `{id}`:
- `GET /api/admin/attributes-sets/marker/:marker` exists but throws `MethodNotAllowedException` (`admin-attributes-sets.controller.ts:440-445`).
- `GET /api/admin/pages/marker/:marker` does NOT exist.
- `GET /api/admin/products/marker/:marker` does NOT exist.
- `GET /api/admin/forms/marker/:marker` — check per project (see `admin-forms.controller.ts`).

**Preferred approach — use the loader's `registry`.** `BlueprintImportResultDto` returns:
```ts
{ status: 'success', dry_run: boolean, inserted: Record<table, count>,
  registry: Record<token, id>, warnings: string[] }
```
The `registry` is exactly the token → numeric-id map (entries like `"@page.women" → 17`, `"@form.signin" → 4`). Capture it at the end of Step 5 and split it back into per-namespace maps:

```python
loader_result = blueprint_post_response.json()
registry = loader_result.get('registry', {})

def split(prefix: str) -> dict[str, int]:
    return {
        tok[len(prefix):]: rid
        for tok, rid in registry.items() if tok.startswith(prefix)
    }

pages_by_identifier    = split('@page.')
forms_by_identifier    = split('@form.')
attribute_sets_index   = split('@aset.')
user_groups_index      = split('@ug.')
products_by_identifier = split('@product.')
# ... add other namespaces as needed (see token-namespaces convention in entity-mapper.md / oneentry-invariants.md §8)
```

**Fallback — when the orchestrator runs independently of the loader call** (the loader response is unavailable):

```python
def fetch_index(path: str) -> dict[str, int]:
    """Return identifier -> id map by walking the CRUD list endpoint."""
    r = requests.get(
        f"{target_cms_api_url}/{path}",
        headers={'Authorization': f'Bearer {target_cms_jwt}'},
        params={'limit': 1000},
    )
    if r.status_code != 200:
        return {}
    payload = r.json()
    # List response shape varies per controller. Verified examples:
    # - `/attributes-sets`: ItemsWithTotal<T> = { items: T[], total: number }
    #   (standard `ItemsWithTotal<T> = { items: T[]; total: number }` shape).
    # - Other admin lists may return a bare array or { data, count, ... } depending on
    #   @nestjsx/crud-typeorm `serialize` config. Probe all 3 shapes.
    if isinstance(payload, list):
        rows = payload
    elif isinstance(payload, dict):
        rows = payload.get('items') or payload.get('data') or []
    else:
        rows = []
    return {
        row['identifier']: row['id']
        for row in rows
        if isinstance(row, dict) and 'identifier' in row and 'id' in row
    }

# Verified endpoints with a plain @Get() list method (admin):
# - /attributes-sets (ItemsWithTotal — `admin-attributes-sets.controller.ts:109`)
# - /user-groups, /forms, /markers, /menus, /integration-collections — each module
#   has @Controller(...) + @Get() but the wrapper shape is per-controller. Always
#   probe `items` / `data` / bare-array via the helper above.
# NOT verified to have a marker→id mapping endpoint: /pages, /products.
# For pages walk the tree via GET /pages/root + GET /pages/:id/children.
```

Also resolve the default language ONCE here so downstream steps (markers, menus,
collections, filters) can build `localizeInfos` fallbacks without re-computing it:

```python
# Convention: mapped.detected_languages is written by entity-mapper Step 7
# (see entity-mapper.md). First language wins; fall back to en_US.
detected_langs = mapped.get('detected_languages') or []
default_lang = detected_langs[0] if detected_langs else 'en_US'
```

### Step 2. form_module_config — attach data forms to Users

⚠ **As of 2026-05-21, `form_module_config` is IN the 24-table whitelist** (`blueprint-loader.service.ts:35`). Prefer including `form_module_config` rows directly in the blueprint JSON over post-import REST. The orchestrator step below remains as a fallback for legacy projects only.

There is NO simple `POST /api/admin/forms/module-config` endpoint in `admin-forms.controller.ts` (verified — only `PUT /module-config/:configId/position` and `POST /module-config/init-position` exist). Standalone form-module-config rows can be created only via:
- Blueprint loader (recommended — whitelist table).
- OneEntry Platform UI → Forms module → "attach to entity".
- Internal service method `AdminFormModuleConfigService.create(configDto)` / `.addManyModuleForms(...)` (verified against the service layer), but it is NOT exposed as a public REST endpoint.

If the blueprint already contains `form_module_config` rows, **skip this step entirely**. If it does not and you really need to bind data-forms to the Users module post-hoc, do it via OneEntry Platform UI.

```python
# DEPRECATED — prefer including form_module_config in the blueprint itself.
# Kept as a documented manual fallback. Logs each data-form as a manual task.
for form in blueprint['tables'].get('forms', []):
    if form.get('type') != 'data':
        continue
    if form.get('identifier') in ('signin', 'checkout', 'review'):
        continue
    if any(c.get('form_id') == f"@form.{form['identifier']}"
           for c in blueprint['tables'].get('form_module_config', [])):
        continue   # already attached via blueprint
    final_report.manual_tasks.append(
        f"Form '{form['identifier']}' (type=data) — attach to Users module via "
        f"OneEntry Platform UI → Forms → '{form['identifier']}' → Module Config (no public POST endpoint)."
    )
    log_task('form_module_config', form['identifier'], 'MANUAL')
```

### Step 3. user-permissions for the user group

⚠ **As of 2026-05-21, `user_permissions` and `user_group_permissions_mn` are IN the 24-table whitelist** (`blueprint-loader.service.ts:39-40`). The loader has natural-key upsert (`blueprint-loader.service.ts:51-57`) so preseeded permissions are reused, not duplicated. Prefer including these rows directly in the blueprint.

The REST endpoints below remain available (`@Controller('user-permissions')` in `admin-user-permissions.controller.ts`), but for new projects the blueprint route is simpler and idempotent.

A typical set of permissions for registered users in e-commerce:

```python
# Verified against `APISectionTypeEnum` and the user-permissions seed migrations.
#
# `section` values must be from APISectionTypeEnum: admins, attributes-sets, locales, blocks, files,
#   forms, form-data, events, general-types, menus, orders-storage, orders, pages, products,
#   product-statuses, payments, system, templates, template-previews, users, users-auth-providers,
#   integration-collections, user-groups, settings-general, immutable-settings, sitemap, discounts.
#
# `rules` shape (from seeds — full 5-permission map + additionalData object):
#   { "permissions": { "readAllRule": 0|1, "readRestrictionRule": 0|1,
#                      "addRule": 0|1|false|true, "changeRule": false|true,
#                      "deleteRule": false|true },
#     "additionalData": {} }
def perm_rules(read_all=0, read_restricted=0, add=False, change=False, delete=False):
    return {
        'permissions': {
            'readAllRule':         read_all,
            'readRestrictionRule': read_restricted,
            'addRule':             add,
            'changeRule':          change,
            'deleteRule':          delete,
        },
        'additionalData': {},
    }

USER_PERMISSIONS_TEMPLATE = [
    # Catalog reads
    {'path': '/api/content/pages',                        'section': 'pages',     'rules': perm_rules(read_all=1)},
    {'path': '/api/content/pages/{id}',                   'section': 'pages',     'rules': perm_rules(read_all=1)},
    {'path': '/api/content/products',                     'section': 'products',  'rules': perm_rules(read_all=1)},
    {'path': '/api/content/products/{id}',                'section': 'products',  'rules': perm_rules(read_all=1)},
    {'path': '/api/content/blocks/{marker}/products',     'section': 'blocks',    'rules': perm_rules(read_all=1)},

    # Form submissions go to form-data; section is 'form-data', NOT 'forms'
    {'path': '/api/content/form-data',                    'section': 'form-data', 'rules': perm_rules(add=True)},

    # Own profile
    {'path': '/api/content/users/me',                     'section': 'users',     'rules': perm_rules(read_all=1, change=True)},

    # Orders
    {'path': '/api/content/orders',                       'section': 'orders',    'rules': perm_rules(read_all=1, add=True)},
    {'path': '/api/content/orders/{id}',                  'section': 'orders',    'rules': perm_rules(read_all=1)},
]

# Find the user group id
user_group = lookup_user_group_by_identifier('user')

# Real flow (verified):
# 1. Create the permission row(s):
#    POST /api/admin/user-permissions  (body = CreateUserPermissionDto[]  — BATCH ARRAY)
#    Body fields per item (from UserPermissionEntity): { localizeInfos, section: APISectionTypeEnum,
#                                                         path: string, rules: Record<string, any> }
#    There is NO `identifier` field on UserPermissionEntity (it doesn't extend BaseAbstractEntity).
#    There is NO group_id / user_group_id field on the DTO.
#
# 2. Bind each created permission to a user_group via the user-groups endpoint:
#    PUT /api/admin/user-groups/:groupId/permissions/:permissionId/change
#    (admin-user-groups.controller.ts:699 — `changeGroupPermission()` is a TOGGLE:
#     creates the binding if absent, removes it if present. Read state via
#     GET /api/admin/user-groups before toggling so you don't undo an existing bind.)
#
# 3. Alternative shortcut — copy ALL permissions from another group:
#    POST /api/admin/user-groups/:sourceGroupId/permissions/copy-to/:destGroupId
#    (admin-user-groups.controller.ts:747 — merges, skipping duplicates)

# Step A — create permissions in batch
created = requests.post(
    f"{target_cms_api_url}/user-permissions",
    headers={'Authorization': f'Bearer {target_cms_jwt}'},
    json=[
        {
            'localizeInfos': { default_lang: { 'title': perm.get('title') or perm['path'] } },
            'section':       perm['section'],
            'path':          perm['path'],
            'rules':         perm['rules'],
        }
        for perm in USER_PERMISSIONS_TEMPLATE
    ],
).json()

# Step B — bind each permission id to the user_group (toggle endpoint — check existing state first)
already_bound = fetch_existing_bindings(user_group['id'])   # GET group permissions
for p in created:
    if p['id'] in already_bound:
        continue
    requests.put(
        f"{target_cms_api_url}/user-groups/{user_group['id']}/permissions/{p['id']}/change",
        headers={'Authorization': f'Bearer {target_cms_jwt}'},
    )
    log_task('user_permission', p['path'], 'OK')
```

### Step 4. integration-collections (FAQ / Stores / Brands / etc)

⚠ **As of 2026-05-21, `collections` and `collection_rows` are IN the 24-table whitelist** (`blueprint-loader.service.ts:41-42`). Prefer including them in the blueprint directly. The REST `@Controller('integration-collections')` (`admin-collections.controller.ts`) is still exposed, but for new pipelines it's simpler to let the mapper emit `collections` + `collection_rows` rows and let the loader create them.

The legacy post-import step below remains for cases where the inspector found FAQ/Stores/Brands data files but the mapper did not emit collection rows (e.g. when the data structure is too dynamic to embed as static rows).

From `mapped.yaml.warnings`, extract out-of-whitelist markers like `'out-of-whitelist: detected N FAQ entries — should be collections'`. From the inspector — extract the real data:

⚠ Verified `CreateCollectionDto` has ONLY two fields:
- `identifier: string` (with `@Matches(markerPattern)` — must start with a letter; `^[A-Za-z]+[a-zA-Z0-9_-]*$`)
- `localizeInfos: CommonLocalizeInfos` (REQUIRED, non-empty)

There is NO `attribute_set_id` field. `CollectionEntity` has a `formId: number | null` (`collection.entity.ts:49`) that links to a form (which in turn carries an `attribute_set_id`) — the schema for collection rows comes from that form's attribute_set, not directly from the collection. To attach a form, update the collection row after creation (or include `form_id` in the blueprint row).

```python
COLLECTION_PATTERNS = {
    'faq':          {'inspector_signal': 'faqitem',     'data_file': 'src/app/data/faqData.ts'},
    'stores':       {'inspector_signal': 'store',       'data_file': 'src/app/data/storesData.ts'},
    'brands':       {'inspector_signal': 'brand',       'data_file': 'src/app/data/brands.ts'},
    'partners':     {'inspector_signal': 'partner',     'data_file': 'src/app/data/partners.ts'},
    'testimonials': {'inspector_signal': 'testimonial', 'data_file': 'src/app/data/testimonials.ts'},
}

for coll_name, cfg in COLLECTION_PATTERNS.items():
    if cfg['inspector_signal'] not in inspector_text.lower():
        continue

    # 1. Ensure the backing form (with its forForms_<name> attribute_set) was already created
    #    by the blueprint loader. If not, this is a manual-task case — the post-import
    #    orchestrator does NOT create attribute_sets via REST (no clean public endpoint
    #    that captures the full SchemaItem map for arbitrary fields).
    form_id = forms_by_identifier.get(f'collection_{coll_name}')      # form created in blueprint
    if form_id is None:
        final_report.manual_tasks.append(
            f"Integration collection '{coll_name}': missing backing form. "
            f"Create `forms[].identifier='collection_{coll_name}'` + its `forForms_collection_{coll_name}` "
            f"attribute_set in the blueprint, then re-run."
        )
        continue

    # 2. Create the collection itself. CreateCollectionDto has only {identifier, localizeInfos}.
    coll = requests.post(
        f"{target_cms_api_url}/integration-collections",
        headers={'Authorization': f'Bearer {target_cms_jwt}'},
        json={
            'identifier':    coll_name,
            'localizeInfos': { default_lang: { 'title': '' } },
        },
    ).json()
    coll_id = coll['id']

    # 3. Bind the form via PUT. UpdateCollectionDto has ALL 3 fields REQUIRED:
    #    {formId, identifier, localizeInfos} (verified — `update-collection.dto.ts`).
    requests.put(
        f"{target_cms_api_url}/integration-collections/{coll_id}",
        headers={'Authorization': f'Bearer {target_cms_jwt}'},
        json={
            'formId':        form_id,
            'identifier':    coll['identifier'],     # re-send the same identifier
            'localizeInfos': coll['localizeInfos'],  # re-send the same localizeInfos
        },
    )

    # 4. Insert rows. Verified endpoint: POST /api/admin/integration-collections/marker/:marker/rows
    #    (base-collections.controller.ts:344) with query `langCode` and body CreateCollectionRowDto:
    #    { entityType?: string, entityId?: number, formIdentifier: string (markerPattern, REQUIRED),
    #      formData: FormDataLangType }
    #    FormDataLangType = { <lang>: [{ marker, type, value }, ...] }
    rows = parse_data_file(cfg['data_file'])
    for row in rows:
        requests.post(
            f"{target_cms_api_url}/integration-collections/marker/{coll_name}/rows",
            headers={'Authorization': f'Bearer {target_cms_jwt}'},
            params={'langCode': default_lang},
            json={
                'formIdentifier': f'collection_{coll_name}',
                'formData': row['formData'],     # {<lang>: [{marker, type, value}, ...]}
            },
        )
    log_task('integration_collection', coll_name, f'{len(rows)} rows')
```

### Step 5. markers (if present in the inspector)

If the inspector found tags/labels on products (not product attributes, but a separate entity like `Tag`/`Marker`/`Label`).

⚠ Verified `MarkerEntity` extends `BaseAbstractEntity` (gives `id` + `identifier`) and adds its own fields:
- `name: string`
- `marker: string` (unique — this is the marker-string used in lookups, distinct from `identifier`)
- `localizeInfos: CommonLocalizeInfos` (camelCase, NOT `localize_infos`)

There is NO `type` field on `MarkerEntity`. `CreateMarkerDto extends MarkerEntity` — body shape matches the entity columns above.

```python
for marker_data in inspector.get('markers', []):
    response = requests.post(
        f"{target_cms_api_url}/markers",
        headers={'Authorization': f'Bearer {target_cms_jwt}'},
        json={
            'identifier':    marker_data['identifier'],
            'marker':        marker_data.get('marker') or marker_data['identifier'],   # unique marker key — defaults to identifier
            'name':          marker_data.get('name') or marker_data['identifier'],
            'localizeInfos': marker_data['localize_infos'] or {                        # required non-empty (IsLocalizeInfos)
                default_lang: { 'title': '' },
            },
        },
    )
    log_task('marker', marker_data['identifier'], response.status_code)
```

### Step 6. menus

If there is header/footer navigation.

⚠ Verified `CreateMenuDto`: `{ identifier: string, localizeInfos: CommonLocalizeInfos, pagesIds: number[], pinnedIds?: number[], isPinned?: boolean }`. **Page IDs go directly in the create body** via `pagesIds` — there is no need for separate per-page calls.

Verified endpoints:
- `POST /api/admin/menus` — create + attach pages in one call (`admin-menus.controller.ts:178`).
- `PUT /api/admin/menus/:id/page/:pageId/position` — change the lexorank of an already-attached page (`:274`), NOT for primary binding.
- There is NO `POST /api/admin/menu-pages-mn` controller; the mn-table is managed inside the menus service.

```python
for menu_name, pages in inspector.get('menus', {}).items():
    # Resolve page identifiers → numeric IDs.
    # There is NO `GET /api/admin/pages/marker/:marker` (verified — no such endpoint in admin-pages.controller.ts).
    # Use the inspector's pre-built page-identifier→id map (the orchestrator captures it after Step 5 loader)
    # or walk the full tree via `GET /api/admin/pages/catalog` + client-side filter.
    pages_ids = [pages_by_identifier.get(p) for p in pages]
    pages_ids = [pid for pid in pages_ids if pid is not None]
    if not pages_ids:
        log_task('menu', menu_name, 'SKIPPED — no resolvable page IDs')
        continue

    resp = requests.post(
        f"{target_cms_api_url}/menus",
        headers={'Authorization': f'Bearer {target_cms_jwt}'},
        json={
            'identifier':    menu_name,
            'localizeInfos': { default_lang: { 'title': '' } },     # admin sets the title later
            'pagesIds':      pages_ids,
        },
    )
    log_task('menu', menu_name, f"{len(pages_ids)} pages — HTTP {resp.status_code}")
```

### Step 7. filters (catalog facets)

Source of truth: `agents_datasets/rules/filters-setup.md` (runtime model + index pipeline summarised inline there).

Filters are out-of-whitelist (the loader can't create rows in `filters` / `filter_items_mn`). They MUST be created here via REST API after the blueprint has been loaded, so that catalog pages render facet UI.

```python
# Step 7.1 — Read task list from the mapper
filter_tasks = mapped.get('post_import_filters', [])

# Step 7.2 — Fallback: if the mapper didn't emit tasks but catalog pages exist,
# build a default task per page using FACET_CANDIDATE heuristic from filters-setup.md §4.
# (See is_facet_candidate() — based on attribute name + type, NOT a schema flag.)
if not filter_tasks:
    for page in blueprint['tables'].get('pages', []):
        if page.get('general_type_id') != 4:                # 4 = catalog_page
            continue
        for_products = next(
            (a for a in blueprint['tables']['attributes_sets']
             if a.get('identifier') == 'forProducts'),
            None,
        )
        if not for_products:
            continue
        attr_idents = [
            name for name, attr in for_products.get('schema', {}).items()
            if is_facet_candidate(name, attr.get('type'), attr.get('listTitles'))
        ]
        if not attr_idents:
            log_task('filters', page['identifier'], 'SKIPPED — no facet-candidate attributes')
            continue
        filter_tasks.append({
            'identifier':                page['identifier'],            # marker == identifier
            'scope_types':               ['product', 'attribute'],
            'page_identifier':           page['identifier'],
            'attribute_set_identifier':  'forProducts',
            'attribute_identifiers':     attr_idents,
            'direct_items':              [],
            'localize_infos':            None,                          # admin sets later
        })

# Step 7.3 — `attribute_sets_index` is already built in Step 1.5
# (from loader.registry["@aset.*"] map, or via GET /attributes-sets CRUD walk).
# `GET /api/admin/attributes-sets/marker/:marker` exists but throws
# MethodNotAllowedException (line 440 of admin-attributes-sets.controller.ts) — DO NOT use.
#
# For direct items of type page/product/discount/payment-method, there are no
# corresponding `/marker/:marker` endpoints; the orchestrator logs a manual task
# instead of attempting to resolve them automatically.

# Step 7.4 — For each task: create filter + add items
for task in filter_tasks:
    # Idempotency via marker-validation endpoint (returns false if identifier already taken)
    valid = requests.get(
        f"{target_cms_api_url}/filters/marker-validation/{task['identifier']}",
        headers={'Authorization': f'Bearer {target_cms_jwt}'},
    ).json().get('valid', True)
    if not valid:
        log_task('filter', task['identifier'], 'SKIPPED — already exists')
        continue

    # `default_lang` was resolved once in Step 1.5 (read from mapped.detected_languages).
    # Create filter (camelCase body — verified against CreateFilterDto; returns HTTP 200 + FilterEntity)
    create_resp = requests.post(
        f"{target_cms_api_url}/filters",
        headers={'Authorization': f'Bearer {target_cms_jwt}'},
        json={
            'identifier':    task['identifier'],
            'localizeInfos': task.get('localize_infos') or {
                # No Title-Case hallucination — leave the title empty and let admin fill it via OneEntry Platform UI.
                default_lang: { 'title': '' },
            },
            'scopeTypes':    task.get('scope_types') or ['product', 'attribute'],
        },
    )
    # NestJS @Post() returns HTTP 201 Created by default (no @HttpCode override on the handler).
    # @ApiResponse(200) is just Swagger metadata. Always accept BOTH 200 and 201.
    if create_resp.status_code not in (200, 201):
        log_task('filter', task['identifier'], f"FAILED — HTTP {create_resp.status_code} {create_resp.text[:200]}")
        continue
    filter_id = create_resp.json().get('id')
    if not filter_id:
        log_task('filter', task['identifier'], 'FAILED — no id in response body')
        continue

    # Build items batch (camelCase, real DTO: AddFilterItemRecordDto)
    aset_ident = task.get('attribute_set_identifier') or 'forProducts'
    aset_id = attribute_sets_index.get(aset_ident)
    # Group items by (attribute_set_id, attribute_identifier) — the replace endpoint is
    # narrow: ONE call per pair, atomically replacing items of that ONE attribute.
    items_by_attr = {}  # attr_ident -> list[AddFilterItemRecordDto]
    total_items = 0
    if aset_id is None:
        log_task('filter_items', task['identifier'],
                 f"SKIPPED — attribute_set '{aset_ident}' not found in GET /attributes-sets index")
    else:
        # The mapper may emit `attribute_identifiers` either as a list of bare strings
        # (simple "expose facet" case) OR as a list of rich dicts that carry per-item
        # data (value-text for string facets, attributeValueId for list/radio facets,
        # isRange/rangeFrom/rangeTo for numeric facets, allowedProductStatusIds for
        # sale-conditional facets). Support both shapes here so the orchestrator
        # forwards every field the mapper produced — silently dropping them would
        # break range/list/sale facets at runtime. See filters-setup.md §7.2 for
        # the full AddFilterItemRecordDto contract.
        for entry in task.get('attribute_identifiers', []):
            if isinstance(entry, str):
                attr_ident = entry
                extras = {}
            else:
                attr_ident = entry['identifier']
                extras = entry  # dict with optional valueText / attributeValueId / isRange / rangeFrom / rangeTo / allowedProductStatusIds
            item = {
                'objectType':          'attribute',         # always 'attribute' for schema-driven items
                'objectId':            aset_id,             # parent attribute_set id, REQUIRED int
                'attributeIdentifier': attr_ident,          # schema key inside that set
            }
            # Optional value selectors — pass through only if the mapper provided them.
            if 'valueText' in extras and extras['valueText'] is not None:
                item['valueText'] = extras['valueText']          # string facets ('color' = 'red')
            if 'attributeValueId' in extras and extras['attributeValueId'] is not None:
                item['attributeValueId'] = extras['attributeValueId']  # list / radioButton facets
            # Range facets (numeric attributes only — integer/real/float).
            if extras.get('isRange'):
                item['isRange']   = True
                item['rangeFrom'] = extras.get('rangeFrom')
                item['rangeTo']   = extras.get('rangeTo')
            # Sale-conditional facets (item appears only when product is in given statuses).
            if extras.get('allowedProductStatusIds'):
                item['allowedProductStatusIds'] = extras['allowedProductStatusIds']
            items_by_attr.setdefault(attr_ident, []).append(item)
            total_items += 1

    # Direct items (page/product/discount/payment-method/admin/bonus) — NOT auto-resolved.
    # There are no admin endpoints to look up these entities by identifier (verified against
    # admin-pages/admin-products controllers — no `/marker/:marker` or equivalent).
    # Log them as manual tasks; admin attaches via OneEntry Platform UI → Filters → <filter> → Add item.
    for direct in task.get('direct_items', []) or []:
        final_report.manual_tasks.append(
            f"Filter '{task['identifier']}': attach direct item {direct} via OneEntry Platform UI "
            f"(no admin REST endpoint to resolve {direct.get('object_type')} by identifier)."
        )
        log_task('filter_direct_item', task['identifier'], f"MANUAL — {direct}")

    # ⚠ PREFER PUT /items/attribute/replace over POST /items for idempotency.
    # `filter_items_mn` has NO UNIQUE constraint — POST /items always inserts new rows.
    # The atomic-replace endpoint deletes all existing attribute items for the given
    # (attributeSetId, attributeIdentifier) pair, then inserts the new list.
    # Real DTO (verified against replace-attribute-filter-items.dto.ts):
    #   { attributeSetId: int, attributeIdentifier: str, items: AddFilterItemRecordDto[] }
    # Response is FilterItemEntity[] — the array of newly saved items.
    # Issue one PUT per attribute (narrow per-attribute semantics).
    for attr_ident, items_payload in items_by_attr.items():
        items_resp = requests.put(
            f"{target_cms_api_url}/filters/{filter_id}/items/attribute/replace",
            headers={'Authorization': f'Bearer {target_cms_jwt}'},
            json={
                'attributeSetId':      aset_id,        # REQUIRED int
                'attributeIdentifier': attr_ident,     # REQUIRED string, ≤255
                'items':               items_payload,  # AddFilterItemRecordDto[]
            },
        )
        log_task('filter_items', f"{task['identifier']}/{attr_ident}",
                 f"{len(items_payload)} items — HTTP {items_resp.status_code} (replace, idempotent per attribute)")

    log_task('filter', task['identifier'], f"created (id={filter_id}) with {total_items} items across {len(items_by_attr)} attribute(s)")
```

**What it accomplishes:**
- One filter per catalog page → storefront calls `GET /api/content/filters/marker/<identifier>` and receives populated facets.
- Items reference attributes by `(objectType='attribute', objectId=<attribute_set_id>, attributeIdentifier=<schema_key>)` — verified against `AddFilterItemRecordDto`.
- All attributes are already in `index_attribute_data` (the `'index-data'` Bull consumer auto-populated them when the loader wrote `attributes_sets` rows in Step 5). No "isFilter" flag — indexing is universal.

**Edge cases:**
- No catalog pages → skip entirely.
- `forProducts` has zero facet-candidate attributes (description-only catalog, etc.) → SKIPPED with manual hint ("review the catalog attributes, decide which to expose as facets in OneEntry Platform UI → Filters").
- Filter identifier already exists (idempotent re-run) → SKIPPED via `/filters/marker-validation/:marker`.
- Inspector did not capture the panel label → `localizeInfos.<lang>.title = ''` and emit manual-task hint ("set filter title in OneEntry Platform UI → Filters → <identifier>"). NO Title-Case hallucination.
- Attribute_set ID lookup fails (e.g. forProducts wasn't created because the project had no products) → SKIPPED with hint.

### Step 8. orphan blocks — attach to fallback pages

After all the above, walk the blueprint and find `blocks` rows that have **no entries** in `block_pages_mn`, `block_products_mn`, OR `product_blocks_mn`. These won't render anywhere.

```python
orphan_blocks = []
for block in blueprint['tables'].get('blocks', []):
    block_token = f"@block.{block['identifier']}"
    attached = (
        any(m.get('block_id') == block_token for m in blueprint['tables'].get('block_pages_mn', [])) or
        any(m.get('block_id') == block_token for m in blueprint['tables'].get('block_products_mn', [])) or
        any(m.get('block_id') == block_token for m in blueprint['tables'].get('product_blocks_mn', []))
    )
    if not attached:
        orphan_blocks.append(block)

# DO NOT auto-attach to random pages — the post-import orchestrator just LOGS them
# as a manual task. Auto-attaching is dangerous (admin sees content surfacing where
# they didn't expect).
for ob in orphan_blocks:
    final_report.manual_tasks.append(
        f"orphan block '{ob['identifier']}' (general_type_id={ob.get('general_type_id')}) — "
        f"attach it to the relevant page(s)/product(s) via OneEntry Platform UI → Pages/Products → Blocks tab. "
        f"Likely scope: " + suggest_scope_for_block(ob)
    )
    log_task('block', ob['identifier'], 'ORPHAN — manual task added')

def suggest_scope_for_block(block):
    """Heuristic suggestion of where the block likely belongs."""
    ident = block.get('identifier', '').lower()
    if 'related' in ident or 'similar' in ident or 'cross_sell' in ident or 'bought_together' in ident:
        return 'product_page (every product detail page)'
    if 'review' in ident:
        return 'product_page (every product detail page)'
    if 'recently_viewed' in ident or 'recommendation' in ident or 'for_you' in ident:
        return 'home + account pages'
    if 'special_offers' in ident or 'sale' in ident or 'promo' in ident:
        return 'home + sale page'
    if 'faq' in ident:
        return 'about / help / product pages'
    return 'unknown — admin decides'
```

### Step 8.4 Slides for `slider_block` (post-import `slides[]`)

**Trigger:** `mapped.post_import_slides[]` is non-empty (populated by `post-mapper-fixer.generate_post_import_slides()` when the project has both a `slider_block` block and a `heroSlides.ts`-style source file).

**Why post-import:** the `slides` table is **NOT** in the blueprint loader whitelist. The `slider_block` itself IS created via the blueprint (with `general_type_id=25`, marker `slider_block`), but its child `slides[]` are inserted post-import.

**REST contract** (verified against the OneEntry Platform `admin-slides.controller`):
```http
POST   /api/admin/slides            body=CreateSlideDto {blockId, attributesSets, isVisible}
GET    /api/admin/slides?blockId=<id>
```

`task_post_import_slides()` resolves `block_identifier` → `block_id` via GET `/api/admin/blocks`, then GETs existing slides for that block (idempotency — if `existing_count >= len(tasks)`, the whole block-task is skipped). Otherwise it POSTs each task one-by-one.

Required admin permission: `slides.create` — preseeded.

See `rules/block-types.md` "Slides for `slider_block`" for the full table schema and DTO contract.

### Step 8.5 Error pages (`page_errors`) — bind HTTP codes to error pages

**Trigger:** `mapped.post_import_page_errors[]` is non-empty (populated by post-mapper-fixer when the project ships `app/not-found.tsx` / `app/error.tsx`).

**Why post-import:** the `page_errors` table is **NOT** in the blueprint loader whitelist. Even though the underlying `pages` row (with `general_type_id=3` = `error_page`, STABLE — see `rules/dynamic-ids.md`) IS created by the blueprint, the link `HTTP code → page` has to be inserted post-import.

**REST contract** (verified against the OneEntry Platform `page-errors.controller`):
```http
POST /api/admin/page-errors                       body={code: 404}      -> returns {id}
PUT  /api/admin/page-errors/:id/set-error-page    body={pageId: <pageId>}
```

`task_post_import_page_errors()` first GETs `/api/admin/page-errors` to find rows that already exist (idempotency), then POSTs missing codes, then PUTs `set-error-page` for each. The `offline` page is intentionally **skipped** — it has no HTTP code (it is a PWA service-worker fallback, not an HTTP error).

Required admin permissions: `pages.errorStatus.create`, `pages.settings.update` — both preseeded in admin RBAC.

### Step 9. payment_accounts — DO NOT automate

```python
if has_checkout_in_blueprint(blueprint):
    log_task('payment_accounts', 'SKIPPED', 'Manual setup required (Stripe/Yookassa secrets)')
    final_report.manual_tasks.append(
        "Settings → Payment Accounts → Add → Stripe/Yookassa/Custom → enter API keys + webhook URL. "
        "After creation: Settings → Order Storages → default → choose payment_account."
    )
```

