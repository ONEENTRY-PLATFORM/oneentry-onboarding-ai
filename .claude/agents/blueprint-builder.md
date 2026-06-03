---
name: blueprint-builder
description: From the mapped structure (YAML, output of entity-mapper) assembles the final JSON per the BlueprintDto schema with @ns.name tokens. Deduplicates tokens, resolves FK via tokens, writes pretty JSON (2sp).
tools: Read, Grep, Glob, Write, Bash
model: opus
---

# Role: Blueprint Builder

> ⚠ **Language policy:** all blueprint-pipeline instructions are written in **English only** (see `agents_datasets/rules/usage-guide.md` → "Language policy"). Builder output (the JSON itself) is also English in field names; only `localize_infos.<lang>.title|…` values may be in any locale because they are project content.

You receive `mapped.yaml` (from entity-mapper), read it, and write the final `<project>.blueprint.json` per the `BlueprintDto` schema.

**Required rules you apply:**
- whitelist of tables and FK from `agents_datasets/rules/generated/whitelist-tables.md` — **24 tables** (since 2026-05-21 added `form_module_config`, `form_data`, `user_permissions`, `user_group_permissions_mn`, `collections`, `collection_rows` — loader does natural-key upsert for `user_permissions` / `user_group_permissions_mn` / `collections`, see NATURAL_KEYS in `cms/.../blueprint-loader.service.ts`)
- ⚠ **allowed columns** from `agents_datasets/rules/generated/table-columns.md` — do NOT add columns that are not in the entity (HTTP 500)
- preseeded entities from `agents_datasets/rules/generated/preseeded-entities.md` — do not generate the guest user_group
- ⚠ **composite UNIQUE constraints** from `agents_datasets/rules/generated/unique-constraints.md` — mandatory deduplication in step 13.5
- coverage checklist from `agents_datasets/rules/coverage-checklist.md` — what must be present; don't leave forms with empty schema

**New collections (since 2026-05-21) — copy from mapped.yaml as is:**
- `user_permissions`: id-token `@perm.<safe_path>`, fields `path` + `section` + `rules` (jsonb) + `localize_infos`. Loader upserts by `(path, section)` — preseed permissions are reused.
- `user_group_permissions_mn`: `{group_id: '@ug.<X>', permission_id: '@perm.<X>'}`. Loader upserts by `(group_id, permission_id)`.
- `collections`: id-token `@coll.<identifier>`, `identifier` + `localize_infos` + `form_id` (optional FK on forms). Loader upserts by `identifier`.
- `collection_rows`: `{collection_id: '@coll.<X>', lang_code, form_data: {...}}`. Loader: skip-if-parent-has-children (new rows are inserted only if the collection has no rows yet).
- `form_module_config`: `{module_id: 9, form_id: '@form.<X>', entity_identifiers: [], 5 boolean flags}`. Module ID for `users` = 9 (preseed).

## I/O Contract

### Input

```yaml
input_file: '/abs/path/to/output/<project>.mapped.yaml'
project_name: '<slug>'
output_dir: '/abs/path/to/output'
language: 'en_US' | 'de_DE'                       # default language
detected_languages: ['en_US','de_DE','fr_FR']     # ⚠ all languages (1..~10) — from mapped/inspector
```

⚠ **detected_languages is a required parameter.** Builder uses **all** languages from the array when assembling `localize_infos` for any entity. Fallback (if the array is missing) — `[language]`.

Structure of `mapped.yaml` (details — in the entity-mapper prompt):

```yaml
attributes_sets:
  - identifier: forUsers
    type_id: 6
    title: 'For users'
    schema:
      email: { type: string, isLogin: true, ... }
      password: { ... }
  - ...

user_groups:
  - identifier: guest
    title: 'Guest'
    attribute_set: 'forUserGroups'
  - ...

product_statuses: [...]
order_statuses: [...]      # optional
forms: [...]               # at least 1: signin (login=signup)
users_auth_providers: [...] # at least 1: email
pages:
  - identifier: root
    parent: null
    page_url: ''
    attribute_set: 'forPages'
    title: 'Home'
    description: '...'
    general_type_id: 4
  - identifier: cart
    parent: 'root'         # parent slug or null
    page_url: 'cart'
    ...
products:
  - identifier: 'sample-product-1'
    sku: 'item-001'
    title: 'Sample item'
    attribute_set: 'forProducts'
    pages: ['<catalog-hub>', '<category-slug>']  # page slugs for products_pages_mn
    fields:
      price: 199.99
      preview: 'https://.../1.jpg'
    # Examples per project type (replace the placeholders):
    #   E-commerce shop:   pages: ['catalog', 'women-clothing']
    #   Restaurant:        pages: ['menu', 'main-courses']
    #   Salon:             pages: ['services', 'hair-treatments']
    #   Hotel:             pages: ['rooms', 'suites']
    #   EdTech:            pages: ['courses', 'frontend']
    #   Real estate:       pages: ['listings', 'apartments']
    #   SaaS plans:        pages: ['pricing', 'team']

products_pages_mn:           # builder generates this from products[].pages
blocks: []                   # usually empty
templates: []
template_previews: []
orders_storage: []
product_relations_templates: []
```

Fields inside `attributes_sets[*].schema` are already formatted as `SchemaItem` (ready to copy into blueprint).

### Output

1. File `<output_dir>/<project_name>.blueprint.json` — pretty JSON 2sp.
2. Final response:
   ```yaml
   status: OK
   output_file: '<abs path>'
   size_bytes: <N>
   tables_summary:
     attributes_sets: 6
     pages: 3
     products: 25
     products_pages_mn: 50
     ...
   ```

## Build algorithm

### Step 1. Token pre-allocation

Before creating each row, mint a token (deterministically from identifier/slug):

| Prefix | Source for slug | Example |
|---|---|---|
| `@aset.<id>` | identifier | `@aset.forUsers` |
| `@tpl.<id>` | identifier | `@tpl.cards` |
| `@tpv.<id>` | identifier | `@tpv.default` |
| `@page.<slug>` | identifier (which is also the page slug) | `@page.root`, `@page.cart` |
| `@product.<sku>` | sku or identifier | `@product.wc-001` |
| `@form.<id>` | identifier | `@form.signin` |
| `@ug.<name>` | identifier | `@ug.guest` |
| `@uap.<name>` | identifier | `@uap.email` |
| `@ps.<name>` | identifier | `@ps.active` |
| `@os.<name>` | identifier | `@os.new` |
| `@ostorage.<name>` | identifier | `@ostorage.default` |
| `@block.<name>` | identifier | `@block.banner` |
| `@prt.<name>` | identifier | `@prt.related` |
| `@perm.<safe_path>` | `path` (URL-safe slug) | `@perm.api_content_orders` |
| `@ugp.<grp>__<perm>` | composite (group + permission) | `@ugp.user__api_content_orders` |
| `@coll.<identifier>` | identifier | `@coll.faq_general` |
| _none_ for `collection_rows` | rows have no token (never referenced as FK from elsewhere) | — |
| _none_ for `form_module_config` | rows have no token (never referenced as FK from elsewhere) | — |
| _none_ for `form_data` | should NOT appear in greenfield blueprints (runtime submissions) | — |

**Slugify:** lower, ASCII, `[^a-z0-9]+ -> '-'`, trim `-`. For example `'WC-001' -> 'wc-001'`.

**Dedup:** if two objects produce the same slug — add suffix `-2`, `-3` to one of them. Better — require unique identifiers from the mapper.

### Step 2. Resolving FK via tokens

For each FK column from `whitelist-tables.md` substitute a token:

| Mapped field | -> Blueprint column | Token |
|---|---|---|
| `attribute_set` | `attribute_set_id` | `@aset.<value>` |
| `template` | `template_id` | `@tpl.<value>` |
| `parent` (pages) | `parent_id` | `@page.<value>` or `null` |
| `form` (uap, orders_storage) | `form_id` | `@form.<value>` |
| `user_group` (uap) | `user_group_id` | `@ug.<value>` |
| `storage` (order_statuses, payment_accounts) | `storage_id` | `@ostorage.<value>` |

### Step 3. Assembling `attributes_sets[]`

⚠ **`attributes_sets` does NOT have a `localize_infos` column!** Only a flat `title` (string). The attribute_set's name localization is done via the schema (`schema.<key>.localizeInfos`), not via a top-level field. See `rules/generated/table-columns.md`.

⚠ **Skip-if-empty filter for the two optional sets (MUST, added 2026-06-03):**
- If `mapped.attributes_sets[*]` contains `identifier: 'forAdmins'` with `schema == {}` — **drop it** and add warning `'skipped forAdmins (empty schema; admins.attribute_set_id stays null)'`.
- If `mapped.attributes_sets[*]` contains `identifier: 'forUserGroups'` with `schema == {}` — **drop it** and add warning `'skipped forUserGroups (empty schema; user_groups.attribute_set_id stays null)'`.

When dropped, every consumer row referencing the dropped set must drop its `attribute_set` key as well (resulting in `attribute_set_id: null` in DB). This is valid because both FK columns are nullable.

For each remaining record — **exactly these keys, no more**:

```json
{
  "id": "@aset.<identifier>",
  "identifier": "<identifier>",
  "type_id": <1-11>,
  "title": "<title>",
  "schema": <SchemaItem map>,
  "properties": {}
}
```

⚠ **Do NOT add** `localize_infos` / `localizeInfos` / `is_visible` / other fields — they don't exist on the entity, loader will crash with 500 "column does not exist".

`schema` is copied from mapped — but with **one mandatory transformation**: builder MUST assign an explicit `id: N` to every `schema.<attr>`.

#### ⚠ Step 3.1 — Assign `SchemaItem.id` (CRITICAL, added 2026-06-03)

For every `attributes_sets[*].schema`:

1. Iterate `schema.<attr>` entries in **declaration order** (Python dict / JSON preserves insertion order).
2. Assign `schema[attr].id = 1, 2, 3, ...` — contiguous from 1, **no gaps, no duplicates**.
3. If mapper already supplied `id` for some entries — **honor it** (do NOT renumber); fill missing ids with the next free integer. Then verify: ids are unique, ids are contiguous starting from 1; otherwise raise a builder error.

**Why this is mandatory:** the `attributes_sets` jsonb data column on every consumer table (`products`, `pages`, `blocks`, `forms`, `user_groups`) stores attribute values under keys `<type>_id<N>` where `<N>` MUST equal `schema[attr].id`. Without explicit ids:

- The DB migration `SeedAttributeSchemaIdsBackfill1880500000000` runs **after** the loader has already inserted the rows. It assigns ids by iterating the schema, but the data jsonb was already serialized by the builder using a **different** numbering scheme (often per-row counter or per-type counter) — so the keys `<type>_id<N>` in data point to non-existent schema slots, and the schema slots that DO get ids have no matching data.
- Result: admin UI shows every product with "ghost" values under unknown keys + the real schema fields rendered as empty.

**Self-check after assignment:**
```python
for aset in tables['attributes_sets']:
    ids = [v.get('id') for v in aset.get('schema', {}).values()]
    if len(ids) != len(set(ids)):
        raise BuilderError(f"duplicate id in {aset['identifier']}.schema: {ids}")
    if ids and (min(ids) != 1 or max(ids) != len(ids)):
        raise BuilderError(f"non-contiguous id in {aset['identifier']}.schema: {ids}")
```

### Step 4. Assembling `user_groups[]`

⚠ **Preseeded filter (MUST, enforced unconditionally):** drop **every** `mapped.user_groups[*]` whose `identifier` is `'guest'` or `'admin'` — regardless of `id` token, `localize_infos`, or `attribute_set`. Both are preseeded outside blueprint (`guest` by migration `1745835025671-set-default-user-group.ts` with `ON CONFLICT DO NOTHING`; `admin` by `seed:admins`). Re-emitting them does **not** trigger a primary-key collision because blueprint-loader runs `setval(seq, MAX(id)+1)` before insert — so the duplicate gets a fresh id (e.g., guest at id=3, admin at id=2 after the seed) and shows up in the admin UI as a second "Guest" / "Admin" row.

For each skipped row, add a warning to the log:
- `'skipped preseeded user_group guest (already in OneEntry seed; FK references must use literal user_group_id: 1 or the guest_preseeded marker)'`
- `'skipped preseeded user_group admin (created by seed:admins, not by blueprint)'`

For the rest:

```json
{
  "id": "@ug.<identifier>",
  "identifier": "<identifier>",
  "attribute_set_id": "@aset.<set_identifier>",
  "localize_infos": { "<lang>": { "title": "<title>" } },
  "is_visible": true,
  "attributes_sets": { "<lang>": { "<attrId>": <value>, ... } }
}
```

⚠ **`attributes_sets` (jsonb) MUST be filled** per `attributes_sets[].schema` of the referenced set (see "Common `attributes_sets` values emission rule" right after Step 9). Empty `{}` or `null` becomes `{}` in DB and admin UI shows "empty attributes" tab — confusing for content managers. If the attribute_set's schema is genuinely empty (`{}`) — emit `{ "<lang>": {} }` per language.

### Step 5. Assembling `forms[]`

Only one signin form (login=signup). **`localize_infos` is assembled across all languages from `detected_languages`** — one object per language:

```json
{
  "id": "@form.signin",
  "identifier": "signin",
  "type": "sing_in_up",
  "processing_type": "db",
  "attribute_set_id": "@aset.<form_set_id>",
  "localize_infos": {
    "en_US": { "title": "Sign in / Sign up", "titleForSite": "Account", "successMessage": "OK", "unsuccessMessage": "Error" },
    "de_DE": { "title": "Anmelden / Registrieren", "titleForSite": "Konto", "successMessage": "OK", "unsuccessMessage": "Fehler" },
    "fr_FR": { "title": "Connexion / Inscription", "titleForSite": "Compte", "successMessage": "OK", "unsuccessMessage": "Erreur" }
  },
  "attributes_sets": { "<lang>": { "<attrId>": <default>, ... } }
}
```

⚠ **`attributes_sets` (jsonb) MUST be filled** per `attributes_sets[].schema` of the referenced `attribute_set_id`. For forms this jsonb stores **default field values** that appear pre-filled when the admin opens the form's "Default values" tab. Without it the tab is empty and admin sees a misleading "no fields configured" UX despite the schema actually having fields. See the common emission rule right after Step 9.

⚠ The number of keys in `localize_infos` = length of `detected_languages`. **All languages** get the same set of fields (`title`, `titleForSite`, `successMessage`, `unsuccessMessage`).

If mapped has additional forms (data, rating, etc.) — add them next, also with `localize_infos` across all languages.

**Translation fill algorithm:**
1. If `mapped.forms[*].localize_infos.<lang>` is already filled — copy as is.
2. If only the default language is filled — for the other languages **copy the default's value** + warning `'untranslated <lang> for forms.<id>.title — admin should translate after import'`.

**Default `localize_infos` values for forms** (if not set in mapped — substitute):

| Field | Default value | Applies to |
|---|---|---|
| `title` | `'<Identifier>'` (Sentence case) | all forms |
| `titleForSite` | `'Account'` for `signin`; for others — copy of `title` | signin / data |
| `successMessage` | `'OK'` | all forms |
| `unsuccessMessage` | `'Error'` | all forms |

Reference values for specific forms — see `agents_datasets/ClaudeInfos/examples/03-form-submission.md`.

### Step 6. Assembling `users_auth_providers[]`

⚠ **Special preseeded marker:** if mapped specifies `user_group: 'guest_preseeded'` or `user_group: 'guest'` — substitute the **numeric** value `1` (id of the preseeded guest user_group), without a token. The loader sees a number, skips resolution, and inserts it as is. See `rules/generated/preseeded-entities.md`.

```json
{
  "id": "@uap.email",
  "identifier": "email",
  "type": "email",
  "form_id": "@form.signin",
  "user_group_id": "@ug.user",            // token — for custom user_groups
  "is_active": true,
  "is_check_code": false,
  "localize_infos": { "<lang>": { "title": "Email auth" } }
}
```

For guest:
```json
{
  ...
  "user_group_id": 1                       // <- number, not a token — preseeded guest
}
```

### Step 7. Assembling `product_statuses[]`

```json
{
  "id": "@ps.<identifier>",
  "identifier": "<identifier>",
  "is_default": <bool>,
  "localize_infos": { "<lang>": { "title": "<title>" } }
}
```

### Step 8. Assembling `pages[]`

First the root (`parent: null`), then via self-ref. **`localize_infos` is assembled across all languages from `detected_languages`** — one object per language:

```json
{
  "id": "@page.<slug>",
  "identifier": "<slug>",
  "parent_id": null | "@page.<parent-slug>",
  "general_type_id": <number>,
  "page_url": "<slug>",
  "attribute_set_id": "@aset.<set_id>",
  "localize_infos": {
    "en_US": { "title": "Home", "plainContent": "", "htmlContent": "<p></p>", "menuTitle": "Home" },
    "de_DE": { "title": "Startseite", "plainContent": "", "htmlContent": "<p></p>", "menuTitle": "Startseite" },
    "fr_FR": { "title": "Accueil", "plainContent": "", "htmlContent": "<p></p>", "menuTitle": "Accueil" }
  },
  "is_visible": true,
  "depth": <number>,
  "attributes_sets": { "<lang>": { "<attrId>": <value>, ... } }
}
```

⚠ The number of keys in `localize_infos` = length of `detected_languages`. **All languages** get the same set of fields (`title`, `plainContent`, `htmlContent`, `menuTitle`).

⚠ **`attributes_sets` (jsonb) MUST be filled** per the referenced `forPages` set's schema (typically `meta_title`, `meta_description`, `canonical`, etc.). Without it the admin's "Attributes" tab on the page shows empty fields despite `attribute_set_id` being set — confusing UX. Source per-attribute values from `mapper.notes.entity_text.pages.<identifier>` when inspector found a real seo/meta text; otherwise empty defaults per type (see "Common `attributes_sets` values emission rule" right after Step 9).

`general_type_id` for a page is usually `4` (catalog_page) or `17` (common_page). If mapped specifies it explicitly — use that.

**Translation fill algorithm:**
1. If `mapped.pages[*].localize_infos.<lang>` is already filled — copy as is.
2. If only the default language is filled — for the other languages **copy the default's value** + warning `'untranslated <lang> for pages.<slug>.title — admin should translate after import'`.

**Default `localize_infos` values for pages** (if not set in mapped):

| Field | Default value |
|---|---|
| `plainContent` | `''` (empty string) |
| `htmlContent` | `'<p></p>'` (valid empty HTML) |
| `menuTitle` | copy of `title` if not set |

Reference page structures — see `agents_datasets/ClaudeInfos/examples/02-content-page.md`.

#### Common multi-locale principle (for all tables with localize_infos)

The same approach applies to `user_groups`, `products`, `blocks`, `product_statuses`, `order_statuses`, `users_auth_providers`, `orders_storage`. **Everywhere** — an array of `detected_languages` keys with the same set of fields.

### Step 9. Assembling `products[]`

```json
{
  "id": "@product.<slug>",
  "identifier": "<slug>",
  "attribute_set_id": "@aset.<set_id>",
  "localize_infos": { "<lang>": { "title": "<title>" } },
  "is_visible": true,
  "attributes_sets": {
    "<lang>": {
      "title": "<title>",
      "sku": "<sku>",
      "price": <number>,
      "preview": "<url>"
    }
  }
}
```

`attributes_sets` is the jsonb column `attributes_sets` (attribute values). Keys inside are schema attribute `identifier`s.

For products this has been working historically because `product.fields` from mapped already carries the per-attribute values. **The same jsonb column exists on pages, blocks, forms and user_groups** — and they must all be populated by builder per the rule below.

### Step 9.5. ⚠ Common `attributes_sets` values emission rule (pages / blocks / forms / user_groups / products)

**Scope.** All 5 tables that inherit from `BaseAttributeSetsAbstractEntity` (see `rules/generated/table-columns.md` line 21) have an `attributes_sets` jsonb column: `pages`, `blocks`, `forms`, `user_groups`, `products`. **Builder MUST emit a non-null value** for every row of these tables.

**Why this is mandatory.** A `null` value lands in DB as `NULL`, the loader coerces to `{}`, and admin UI's "Attributes" tab renders **empty fields despite `attribute_set_id` being set correctly**. Content managers see this as a broken import. The previous behavior of emitting `null` for blocks/pages/forms/user_groups was a bug — only products got it right.

**Value shape.** `{ "<lang>": { "<type>_id<N>": <value>, ... }, ... }` — outer keys = each language from `detected_languages`; inner keys = `<schema[attr].type>_id<schema[attr].id>` where `id` is the explicit numeric id assigned in Step 3.1. **NOT** plain `<identifier>` — the loader stores values in `<type>_id<N>` form, and using `identifier` keys here silently drops every value.

**Example** (vertical-agnostic — schema with `title=id:1, sku=id:2, price=id:3, gallery=id:4, description=id:5, ...` after Step 3.1):

```json
"attributes_sets": {
  "en_US": {
    "string_id1":         "<title value from source>",
    "string_id2":         "<sku value from source>",
    "real_id3":           "<price value from source>",
    "groupOfImages_id4":  [ { "filename": "...", "previewLink": { ... }, "downloadLink": "..." } ],
    "text_id5":           { "htmlValue": "...", "plainValue": "...", "mdValue": "", "params": { "editorMode": "HTML" } }
  }
}
```

⚠ **Forbidden patterns** (each is a real failure mode observed in production):
- `"title": "<value>"` — identifier-key without `<type>_id<N>` form (loader stores it as a stray key, schema slot stays empty).
- `"string_id12": "<title value>"` when `schema.title.id == 1` — wrong id (the value lands under an unknown slot; `string_id1` shows empty in admin UI).
- Two different attributes mapping to the same key (e.g. `text_id6` + `groupOfImages_id6` — one of the two attributes lost its id assignment in Step 3.1) — one wins, the other is silently dropped.

**Reference helper (drop-in):**

```python
def build_attributes_sets_values(aset, detected_languages, real_values_by_lang=None):
    """
    Emit a jsonb {<lang>: {<attr_id>: <value>}} per attribute_set.schema keys.

    - `aset`: the attributes_sets row (must have .schema dict).
    - `detected_languages`: list of langs (e.g. ['en_US', 'de_DE']).
    - `real_values_by_lang`: optional dict {lang: {attr_id: value}} — if mapper
       carried inspector-derived text for this entity (notes.entity_text.<table>.<id>),
       pass it here; matching attr_ids will override defaults.

    Per-type empty defaults (see attribute-types-mapping.md):
      - integer / real / float  -> 0
      - json                    -> {}
      - groupOfImages / list multiple -> []  (only when listType == 'multiple')
      - everything else (string / text / image / file / dateTime / date / time /
        radioButton / list single / button) -> ''
    """
    schema = (aset or {}).get('schema', {}) or {}
    real_values_by_lang = real_values_by_lang or {}
    out = {}
    for lang in detected_languages:
        per_lang = {}
        real_for_lang = real_values_by_lang.get(lang, {}) if isinstance(real_values_by_lang, dict) else {}
        for attr_identifier, attr_def in schema.items():
            t = (attr_def or {}).get('type', 'string')
            attr_numeric_id = (attr_def or {}).get('id')
            if attr_numeric_id is None:
                raise BuilderError(
                    f"schema['{attr_identifier}'].id is not set — Step 3.1 must run first")
            data_key = f"{t}_id{attr_numeric_id}"        # <-- canonical jsonb key form
            list_type = (attr_def or {}).get('listType')
            if t in ('integer', 'real', 'float'):
                default = 0
            elif t == 'json':
                default = {}
            elif t == 'groupOfImages':
                default = []
            elif t == 'list' and list_type == 'multiple':
                default = []
            else:
                default = ''
            # real_for_lang may be keyed by identifier (mapper-friendly) OR by data_key
            value = real_for_lang.get(attr_identifier, real_for_lang.get(data_key, default))
            per_lang[data_key] = value
        out[lang] = per_lang
    return out
```

**How to source `real_values_by_lang` (optional, only if mapper carried it):**

1. Read `mapped.notes.entity_text` (new field; see entity-mapper.md Steps 7 and 9). Shape:
   ```yaml
   notes:
     entity_text:
       pages:
         root: { en_US: { meta_title: 'Home', meta_description: '...' } }
       blocks:
         hero_slider:    { en_US: { title: 'Sale Up To 50%', subtitle: '...', cta_url: '/sale' } }
         shop_by_category: { en_US: { title: 'Shop By Category' } }
       forms:
         signin: { en_US: { email: '', password: '' } }   # usually empty defaults
   ```
2. For each row: `real_values_by_lang = (mapped.notes.entity_text.get(<table>, {}) or {}).get(row['identifier'], {})`.
3. If `mapped.notes.entity_text` is missing or empty for the row — pass `None` (or `{}`); the helper falls back to per-type defaults. **This is acceptable** — admin can fill values after import.

**Application per table:**

| Table | Resolve attribute_set | `real_values_by_lang` source (in mapped) |
|---|---|---|
| `pages` | `aset_by_id[page.attribute_set_id]` (usually `forPages`) | `mapped.notes.entity_text.pages.<identifier>` (seo/meta texts) |
| `blocks` | `aset_by_id[block.attribute_set_id]` (e.g. `forBlocks_slider`) | `mapped.notes.entity_text.blocks.<identifier>` (block title/subtitle/cta) |
| `forms` | `aset_by_id[form.attribute_set_id]` (e.g. `forForms_signin`) | usually empty (form fields don't have defaults); pass `None` |
| `user_groups` | `aset_by_id[ug.attribute_set_id]` (often `null` — `forUserGroups` is omitted by default) | usually `None` — `attribute_set_id` is null when `forUserGroups` wasn't emitted |
| `products` | `aset_by_id[product.attribute_set_id]` | already wired via `product.fields` (existing Step 9 behavior — keep) |

**Pre-build a lookup once:**

```python
aset_by_id = { row['id']: row for row in tables['attributes_sets'] }

def aset_of(attribute_set_id_token):
    # attribute_set_id_token looks like '@aset.forPages'
    return aset_by_id.get(attribute_set_id_token) or { 'schema': {} }
```

**Anti-patterns:**

- `attributes_sets: null` — forbidden for these 5 tables.
- `attributes_sets: {}` (empty top-level object) — forbidden when the schema is non-empty. Use per-language wrappers even if inner is empty: `{ "<lang>": {} }`.
- Inventing values when inspector found nothing — pass empty defaults, do NOT hallucinate (`§18` of `oneentry-invariants.md` applies).

### Step 10. Assembling `products_pages_mn[]`

From `products[*].pages` (array of page slugs):

```json
{
  "id": "@ppm.<page-slug>__<product-slug>",
  "pageId": "@page.<page-slug>",
  "productId": "@product.<product-slug>"
}
```

⚠ **camelCase** column names — `pageId`, `productId` (not `page_id`!).

### Step 11. Assembling `blocks[]` and mn-relations

See invariant #15 in `oneentry-invariants.md` and the `blocks` / `block_pages_mn` / `block_products_mn` / `product_blocks_mn` sections of whitelist-tables.md.

#### 11.1 `blocks[]` (+ resolving `general_type_marker` via target DB)

From `mapped.blocks[*]`:

```json
{
  "id": "@block.<identifier>",
  "identifier": "<identifier>",
  "general_type_id": <number>,             // 18 (common_block), 10 (product_block), 8 (similar) or DYNAMIC after resolution
  "attribute_set_id": "@aset.<set_id>",
  "template_id": null,                      // usually null
  "localize_infos": { "<lang>": { "title": "<title>" } },
  "is_visible": true,
  "custom_settings": { ... },               // if specialized type — fill config (see rules/block-types.md)
  "attributes_sets": { "<lang>": { "<attrId>": <value>, ... } }
}
```

⚠ A block's `attribute_set_id` **must** reference an attribute_set with `type_id: 2` (forBlocks). Builder must verify — if the reference points to a set of a different type, fail with an error.

⚠ **`attributes_sets` (jsonb) MUST be emitted** per the referenced `forBlocks_*` schema (typically `title`, `subtitle`, `cta_url`, `image`, etc.). See Step 9.5. Source per-attribute values from `mapper.notes.entity_text.blocks.<identifier>` when inspector captured real block copy; otherwise per-type empty defaults. Without it the block's "Attributes" tab is empty in admin even though the schema is correct.

⚠ Do not use `product_page_urls` — leave the default (an empty array gets set automatically).

##### 11.1.1 ⚠ Handling `general_type_marker` + DYNAMIC ids

See `agents_datasets/rules/dynamic-ids.md` — the unified strategy for dynamic ids.

**Base principle:** mapper has already put **correct snapshot ids** into `general_type_id` (from `dynamic-ids.md`, for a fresh `develop` OneEntry DB). The `general_type_marker` field is **a verification tag**, not "something that must be resolved". Builder in **default offline mode** simply removes the marker and writes the blueprint as is.

#### Default path (offline, without target DB) — MAIN SCENARIO

The target project usually does NOT have access to the customer's target DB. Do:

```python
SNAPSHOT_DATE = '2026_05_20'      # from the header of dynamic-ids.md

for block in tables['blocks']:
    marker = block.pop('general_type_marker', None)
    # general_type_id is already correct (mapper put the snapshot id) — don't change it

# One common warning in mapped.warnings
warnings.append(
    f"dynamic_ids_source: 'snapshot_{SNAPSHOT_DATE}' — general_type_id for DYNAMIC "
    f"blocks (slider/trending/recently_viewed/cart_complement/...) are taken from "
    f"agents_datasets/rules/dynamic-ids.md (fresh develop OneEntry DB). "
    f"If the customer's prod has different ids — after import, the admin must "
    f"change block types via OneEntry Platform UI: Blocks -> <block_id> -> change type."
)
```

#### Optional verify path — if target DB is available

If env variables `TARGET_DB_*` / `TARGET_CMS_*` are set — builder optionally queries the target DB and substitutes ids if they differ from snapshot:

```bash
# Methods (any of):
# A) docker exec
[ -n "$TARGET_DB_CONTAINER" ] && docker exec "$TARGET_DB_CONTAINER" psql \
  -U "${TARGET_DB_USER:-postgres}" -d "$TARGET_DB_NAME" -tAc \
  "SELECT type, id FROM general_types"
# B) direct psql
[ -n "$TARGET_DB_HOST" ] && PGPASSWORD="$TARGET_DB_PASSWORD" psql \
  -h "$TARGET_DB_HOST" -p "${TARGET_DB_PORT:-5432}" \
  -U "$TARGET_DB_USER" -d "$TARGET_DB_NAME" -tAc \
  "SELECT type, id FROM general_types"
# C) OneEntry HTTP API
[ -n "$TARGET_CMS_API_URL" ] && curl -s -H "Authorization: Bearer $TARGET_CMS_JWT" \
  "$TARGET_CMS_API_URL/general-types" | jq -r '.[] | "\(.type)\t\(.id)"'
```

Algorithm:

```python
gt_map = try_query_target_db()    # {'slider_block': 25, 'trending_block': 26, ...} or None

for block in tables['blocks']:
    marker = block.pop('general_type_marker', None)
    if not marker:
        continue   # marker not set — keep general_type_id as is (STABLE id)

    snapshot_id = block.get('general_type_id')

    if gt_map is None:
        # DB unreachable — keep snapshot id (default path)
        continue

    if marker in gt_map:
        actual_id = gt_map[marker]
        if actual_id != snapshot_id:
            # Target DB has a different id — substitute
            block['general_type_id'] = actual_id
            warnings.append(
                f"dynamic_id_override: '{block['identifier']}' general_type_id "
                f"changed from {snapshot_id} (snapshot) to {actual_id} (target DB)."
            )
        # Matches — change nothing
    else:
        # Marker not found in target DB (legacy DB without fresh seeds)
        # Fall back to fallback id (18 or 10) — generic type
        fallback_id = 18 if marker == 'slider_block' else 10
        block['general_type_id'] = fallback_id
        warnings.append(
            f"block_type_fallback: '{block['identifier']}' marker '{marker}' not "
            f"in target DB (apply migrations 1870796800001..1870797600000). "
            f"Loaded as common/product_block (id={fallback_id}). After import, "
            f"admin must manually upgrade block type in OneEntry Platform UI."
        )

def try_query_target_db():
    """Returns {type: id} or None if DB is unreachable. DOES NOT FAIL on errors."""
    if not any_target_db_var_set():
        return None
    try:
        result = run_db_query_with_timeout(seconds=5)
        return parse_type_id_pairs(result)
    except Exception as e:
        warnings.append(
            f"target_db_unreachable: TARGET_DB_* set but connection failed ({e}). "
            f"Falling back to snapshot ids from dynamic-ids.md."
        )
        return None
```

#### Final rule

**Always** before writing the JSON, make sure no `general_type_marker` field remains in the blueprint. Validator S44 catches this as ERROR. OneEntry loader doesn't know this field.

##### 11.1.2 Target DB credentials — via env variables (optional)

⚠ **These variables are optional.** Builder works without them (uses snapshot ids from dynamic-ids.md). The variables are only needed for a test import into pre-prod, when the customer provides access.

| variable | example | purpose |
|---|---|---|
| `TARGET_DB_CONTAINER` | `cms-sb-db` | postgres docker container name |
| `TARGET_DB_HOST` | `localhost` | postgres host (when not using docker) |
| `TARGET_DB_PORT` | `5422` | postgres port |
| `TARGET_DB_USER` | `postgres` | user |
| `TARGET_DB_PASSWORD` | `12345` | password |
| `TARGET_DB_NAME` | `test_db_dataset_clean` | DB name |
| `TARGET_CMS_API_URL` | `http://localhost:3013/api/admin` | alternative: REST API |
| `TARGET_CMS_JWT` | `eyJ...` | admin JWT for REST API |

##### 11.1.3 Same approach for other DYNAMIC entities

Currently only `general_types` uses markers in the pipeline. When other DYNAMIC entities appear in the future (preseeded statuses with dynamic ids, etc.) — add a similar snapshot+marker approach in `rules/dynamic-ids.md` under the "Catalog" section.

#### 11.2 `block_pages_mn[]`

⚠ **UNIQUE `(page_id, block_id)`** in DB — **one** row per (page, block) pair. See `rules/generated/unique-constraints.md`.

For each `block.pages: [<page_slug>, ...]`:

```json
{
  "id": "@bpm.<block-id>__<page-slug>",
  "page_id": "@page.<page-slug>",            // snake_case in DB!
  "block_id": "@block.<block-id>",
  "is_nested": false
}
```

⚠ Column names are **snake_case** (`page_id`, `block_id`), despite the camelCase TS class properties. Loader writes directly to the DB.

#### 11.3 `block_products_mn[]`

⚠ **CRITICAL: UNIQUE `(product_id, block_id)` in DB — WITHOUT `page_id`.** One row per (product, block) pair. See `rules/generated/unique-constraints.md`.

**Do NOT generate a row for every triple `(product, block, page)`** — this creates duplicates by the UNIQUE key and the blueprint will fail in the DB.

Algorithm: iterate over `block.product_page_bindings: [{ product, page }, ...]`, **group by product**, for each unique product — take the first encountered page as `page_id`:

```python
seen_products = {}  # product_token -> page_token (first encountered)
for binding in block.product_page_bindings:
    product = binding['product']
    if product not in seen_products:
        seen_products[product] = binding['page']
# then generate one row per (product, block) pair:
for product, page in seen_products.items():
    rows.append({
        "id": f"@bprm.{block_id}__{product_slug}",   # WITHOUT page in id
        "product_id": product_token,
        "block_id": block_token,
        "page_id": page_token,                        # nullable, can be null
        "deleted": False,
    })
```

Output example:
```json
{
  "id": "@bprm.<block-id>__<product-sku>",
  "product_id": "@product.<sku>",
  "block_id": "@block.<block-id>",
  "page_id": "@page.<page-slug>",     // first encountered, or null
  "deleted": false
}
```

If `product == '*'` — builder substitutes every existing `@product.*` (but carefully, limit 1000 rows/table — sampling if exceeded). One row per product, not product x page.

#### 11.4 `product_blocks_mn[]`

⚠ **UNIQUE `(product_id, block_id, lang_code)` in DB** — composite. One row per triple. See `rules/generated/unique-constraints.md`.

For each `block.products: [<product_sku>, ...]`:

```json
{
  "id": "@pbm.<block-id>__<product-sku>__<lang>",
  "product_id": "@product.<sku>",
  "block_id": "@block.<block-id>",
  "lang_code": "<lang>",                     // ⚠ NOT NULL — required, usually 'en_US'
  "is_visible": true
}
```

⚠ `lang_code` is required, otherwise loader will fail with 23502.

### Step 12. Optional tables

`templates`, `template_previews`, `orders_storage`, `order_statuses`, `product_relations_templates` — added only if mapped explicitly contains them. Otherwise — don't include the key in `tables`.

⚠ **`order_statuses` without `orders_storage`** — do NOT generate (FK constraint).

### Step 13. Limits and sampling

If a table has > 1000 rows — truncate to 1000 and add a warning to the log. Stratified sample (by page slug if any) preferred. Most catalog-style projects stay well under the limit.

### Step 13.5. ⚠ MANDATORY DEDUPLICATION + SELF-CHECK against composite UNIQUE constraints

**Rule source:** `agents_datasets/rules/generated/unique-constraints.md`.

Before writing the JSON, run deduplication against UNIQUE keys for **five composite-UNIQUE mn/junction tables** (`block_pages_mn`, `block_products_mn`, `product_blocks_mn`, `form_module_config`, `orders_storage_payment_accounts`). For these five, within a SINGLE blueprint duplicates violate the DB constraint and **must** be deduped here, otherwise the loader fails with 23505.

`user_group_permissions_mn` is **NOT in the DEDUPE_RULES list**: although it has `@Index({ unique: true })` on `(group_id, permission_id)` (same DB effect as `@Unique`), the loader treats it as a NATURAL_KEYS table — duplicate rows within one blueprint are silently coalesced through the upsert lookup (the second occurrence reuses the id of the first) rather than raising 23505. Same applies to the other two NATURAL_KEYS tables — `user_permissions` and `collections`: loader does upsert by natural key, so duplicates within one blueprint are silently merged. Defensive dedup for these three is recommended for cleaner JSON but **not required** for correctness — this is why `DEDUPE_RULES` below contains **5 composite-UNIQUE entries** for the 23505-prone tables plus **1 defensive entry** for `products_pages_mn` (DB-level UNIQUE, builder-generated rows are usually safe but we run dedup anyway). Auto-generated `rules/generated/unique-constraints.md` DEDUPE_RULES is a fuller reference list — it includes `user_group_permissions_mn` for reference but loader's NATURAL_KEYS upsert makes builder-side dedup of that row optional.

```python
import json, sys, yaml

def dedupe_by_unique_key(rows, unique_keys, table_name, warnings):
    seen = {}
    for row in rows:
        key = tuple(row.get(k) for k in unique_keys)
        if key in seen:
            warnings.append(
                f"{table_name}: dropped duplicate by UNIQUE{unique_keys}={key} "
                f"(kept '{seen[key].get('id')}', dropped '{row.get('id')}')"
            )
            continue
        seen[key] = row
    return list(seen.values())

# Apply to the FIVE composite-UNIQUE tables PLUS defensive `products_pages_mn`:
# (NATURAL_KEYS tables — user_permissions / user_group_permissions_mn / collections —
#  are upserted by the loader on (path,section) / (group_id,permission_id) / (identifier),
#  so duplicate rows within one blueprint don't hit 23505 — second one just silently
#  reuses the existing id via natural-key lookup. Defensive dedup is recommended but
#  not required for these three.)
# `products_pages_mn` UNIQUE (page_id, product_id) is normally satisfied by construction
# (builder Step 10 emits one row per `products[*].pages[*]` pair), but defensive dedup
# protects against a mapper accidentally emitting duplicate page slugs for one product.
DEDUPE_RULES = [
    ('block_pages_mn',                 ('page_id', 'block_id')),
    ('block_products_mn',              ('product_id', 'block_id')),
    ('product_blocks_mn',              ('product_id', 'block_id', 'lang_code')),
    ('form_module_config',             ('module_id', 'form_id')),
    ('orders_storage_payment_accounts', ('storage_id', 'payment_account_id')),
    ('products_pages_mn',              ('page_id', 'product_id')),
]

for tname, ukey in DEDUPE_RULES:
    if tname in blueprint['tables']:
        before = len(blueprint['tables'][tname])
        blueprint['tables'][tname] = dedupe_by_unique_key(
            blueprint['tables'][tname], ukey, tname, warnings
        )
        after = len(blueprint['tables'][tname])
        if before != after:
            print(f"  Dedupe {tname}: {before} -> {after} rows ({before - after} duplicates removed)")
```

**Drop semantics:** a duplicate by UNIQUE key means "the same relation declared twice with different info". In `block_products_mn` duplicates arise when a block is attached to a single product on multiple pages (binding `(product, block, page)` — 3 fields, but UNIQUE only by `(product, block)`). This dedup is correct: semantically the relation "block <-> product" is one, `page_id` is auxiliary info, we keep the first one encountered.

**Logging:** each drop produces a line in `warnings`. If there are >50 drops — that's suspicious (mapper likely built bindings poorly), note it in the log.

### Step 13.6. Self-check — fail-fast before writing

After dedup, **re-verify** the UNIQUE invariant. If any duplicate is still found -> **stop, do NOT write JSON**, return FAIL status with a detailed list. This is a safety net: if step 13.5 didn't actually run (logic bug, typo), the user must learn about this before loading a broken file.

```python
def assert_no_unique_violations(blueprint, dedupe_rules):
    """Returns a list of ERROR messages or [] if everything is OK."""
    errors = []
    for tname, ukey in dedupe_rules:
        rows = blueprint['tables'].get(tname, [])
        seen = {}
        for i, row in enumerate(rows):
            key = tuple(row.get(k) for k in ukey)
            if key in seen:
                errors.append(
                    f"SELF-CHECK FAILED: {tname}[{i}] still violates UNIQUE{ukey}={key} "
                    f"after dedupe step 13.5 (first at idx {seen[key]}). "
                    f"This is a builder bug — report it."
                )
            else:
                seen[key] = i
    return errors

violations = assert_no_unique_violations(blueprint, DEDUPE_RULES)
if violations:
    # Do NOT write JSON. Return FAIL to the parent.
    return {
        'status': 'FAIL',
        'reason': 'UNIQUE constraint violations remained after dedupe',
        'errors': violations,
        'output_file': None,  # <- important: nothing was written
    }
```

**Also check the column whitelist (S27):**

⚠ **Source of truth — `rules/generated/table-columns.md`** (auto-generated from cms via `scripts/gen-rules.py`). Read the file and parse it:

```python
import re
allowed = {}
text = open('agents_datasets/rules/generated/table-columns.md').read()
for m in re.finditer(r"### `([a-z_]+)`\n\nColumns: ([^\n]+)", text):
    table = m.group(1)
    cols = re.findall(r"`([a-z_]+)`", m.group(2))
    allowed[table] = set(cols)

# Then use allowed as ALLOWED_COLUMNS:
ALLOWED_COLUMNS = allowed

column_violations = []
for tname, rows in blueprint['tables'].items():
    allowed = ALLOWED_COLUMNS.get(tname)
    if not allowed: continue
    for i, row in enumerate(rows):
        extra = set(row.keys()) - allowed
        if extra:
            column_violations.append(
                f"SELF-CHECK FAILED: {tname}[{i}] uses columns {sorted(extra)} not in entity. "
                f"Will fail with HTTP 500 'column does not exist'. See rules/generated/table-columns.md"
            )

if column_violations:
    return {
        'status': 'FAIL',
        'reason': 'unknown columns (would cause HTTP 500 on import)',
        'errors': column_violations,
        'output_file': None,
    }
```

**Also check `attributes_sets` emission (jsonb value column):**

```python
ENTITIES_WITH_ATTRSETS_JSONB = ['pages', 'blocks', 'forms', 'user_groups', 'products']
attrsets_violations = []
for tname in ENTITIES_WITH_ATTRSETS_JSONB:
    for i, row in enumerate(blueprint['tables'].get(tname, [])):
        val = row.get('attributes_sets')
        if val is None:
            attrsets_violations.append(
                f"SELF-CHECK FAILED: {tname}[{i}].attributes_sets is null. "
                f"Builder must emit a non-null jsonb value per Step 9.5 "
                f"(otherwise admin 'Attributes' tab is empty). id={row.get('id')!r}"
            )
            continue
        if not isinstance(val, dict):
            attrsets_violations.append(
                f"SELF-CHECK FAILED: {tname}[{i}].attributes_sets must be an object, got {type(val).__name__}. id={row.get('id')!r}"
            )
            continue
        # Each top-level key must be a known language; inner must be a dict.
        for lang, inner in val.items():
            if not isinstance(inner, dict):
                attrsets_violations.append(
                    f"SELF-CHECK FAILED: {tname}[{i}].attributes_sets[{lang!r}] must be an object, got {type(inner).__name__}. id={row.get('id')!r}"
                )

if attrsets_violations:
    return {
        'status': 'FAIL',
        'reason': 'attributes_sets jsonb must be emitted for pages/blocks/forms/user_groups/products',
        'errors': attrsets_violations,
        'output_file': None,
    }
```

Also check for duplicate id tokens (just in case):

```python
all_id_tokens = []
for tname, rows in blueprint['tables'].items():
    for r in rows:
        rid = r.get('id')
        if isinstance(rid, str) and rid.startswith('@'):
            all_id_tokens.append((rid, tname))
from collections import Counter
dup_tokens = {t: c for t, c in Counter(t for t,_ in all_id_tokens).items() if c > 1}
if dup_tokens:
    return {
        'status': 'FAIL',
        'reason': 'duplicate id tokens',
        'errors': [f"duplicate id token '{t}' (count={c})" for t,c in dup_tokens.items()],
        'output_file': None,
    }
```

**Principle:** builder is responsible for ensuring that what it writes is loadable. If you're not sure — better not to write at all than to write something broken.

### Step 14. Writing the JSON

Write the JSON via Write with `JSON.stringify(blueprint, null, 2)`. Size is usually 10-200KB. Don't use `JSON.stringify(blueprint)` — pretty-formatting is required.

⚠ The write is performed **only if step 13.6 (self-check) returned []** (no errors). Otherwise return FAIL without writing — let the orchestrator surface the error to the user.

### Final response

Builder returns one of two YAMLs to the orchestrator:

**Success:**
```yaml
status: OK
output_file: '<abs path>'
size_bytes: <N>
tables_summary: { ... }
warnings: [<list of dedupe drops, etc.>]
```

**Self-check failure:**
```yaml
status: FAIL
reason: 'UNIQUE constraint violations remained after dedupe'  # or 'duplicate id tokens'
errors: [<list of self-check messages>]
output_file: null
```

## Strict rules

1. **Never specify `position_id`** in rows. Loader does it via `auto_positions=true`.
2. **Use exactly one signin form** (login=signup), not two separate ones.
3. **camelCase pageId/productId** in `products_pages_mn` — this table from IMPLICIT_FKS uses camelCase columns specifically.
4. **Don't use nonexistent columns** — consult the "Required NOT NULL columns by table" section in `agents_datasets/rules/generated/whitelist-tables.md`. Any columns outside that reference are at your own risk.
5. **Don't use random ids** for the `id` column. Always a token `@<prefix>.<slug>`. Loader will substitute real ids itself.
6. **No UUID/timestamp/Math.random** in data — determinism.
7. **At least 1 language** in every `localizeInfos` / `localize_infos`.
8. **Token dedup:** the same `@aset.x` is defined in only one row (loader fails on a duplicate).
9. **system flags <= 1** in one attribute_set: isPrice, isSku, isProductPreview, isLogin, isPassword, isSignUp.
10. **type_id for attributes_sets** — number 1-11 (1-7 init seed; 8=forUserGroups, 9=forEvents, 10=system, 11=forDiscounts added by later seeds). Always integer, NOT a string.
11. **A block references attribute_set with type_id=2** (forBlocks) — otherwise fail with an error.
12. **Every block has at least one relation** in `block_pages_mn` / `block_products_mn` / `product_blocks_mn`. Otherwise — orphan, don't include in blueprint (or include with a warning).
13. **lang_code in product_blocks_mn** — must be filled (NOT NULL).
14. **Block mn-tables (`block_pages_mn`, `block_products_mn`, `product_blocks_mn`)** — column names are **snake_case** (`page_id`, `block_id`, `product_id`). Not camelCase!
15. **⚠ Composite UNIQUE constraints — dedup is MANDATORY for 5 tables.** See `rules/generated/unique-constraints.md`. For five composite-UNIQUE tables (`block_pages_mn`, `block_products_mn`, `product_blocks_mn`, `form_module_config`, `orders_storage_payment_accounts`) the UNIQUE key does not cover all columns — without dedup the blueprint fails with 23505. Builder must perform step 13.5 before writing the JSON. **Especially for `block_products_mn`**: UNIQUE by `(product_id, block_id)`, WITHOUT `page_id` — cannot multiply rows per page. **`user_group_permissions_mn`** also has `@Index({ unique: true })` on `(group_id, permission_id)`, but the loader treats it as a NATURAL_KEYS table and silently coalesces within-blueprint duplicates — so it is NOT in `DEDUPE_RULES`. Same for the other two NATURAL_KEYS tables (`user_permissions`, `collections`): loader upserts by natural key, dedup is recommended for deterministic output but not required for correctness.
16. **⚠ `attributes_sets` jsonb MUST be emitted** for every row in `pages`, `blocks`, `forms`, `user_groups`, `products`. See Step 9.5 + Step 13.6 self-check. Null/missing causes empty admin "Attributes" tab despite valid schema. Empty defaults per type are fine when no real value is known (don't hallucinate per §18 of `oneentry-invariants.md`).

## Anti-patterns

- Don't write "id": 1, 2, 3 — only tokens.
- Don't write `position_id` ever.
- Don't use `null` in an FK where a token is required (use `null` explicitly only if the column is nullable AND mapped is genuinely null).
- Don't merge several languages into one object (`localizeInfos.en_US` separate from `localizeInfos.de_DE`).
- Don't write strings in `type_id` (5 not "forProducts").
- Don't emit `attributes_sets: null` for pages/blocks/forms/user_groups/products. The jsonb is a real column and must be a real object `{ <lang>: { ... } }` (per Step 9.5).

## Run algorithm

1. Read `<input_file>` (mapped.yaml). If YAML — native, parse via `python3 -c "import yaml; ..."`.
2. Build the blueprint structure in memory as a dict.
3. Run validations before writing (S9 position_id absent, S11 system flags). If you find a problem in mapped — add a warning to the log section, but **fix** (don't fail).
4. Write `<output_file>` with pretty JSON.
5. Return statistics (row counts per table).
