# Menus — universal setup rules for any OneEntry project

> **⚠ Universality note.** Examples below frequently use fashion-shop terms (clothing / shoes / bags / women / men) because that is the reference test project. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop (`product/sku/brand/category`), restaurant (`menu-item/dish/cuisine/section`), beauty salon (`service/master/treatment/duration`), hotel (`room/suite/amenity`), EdTech (`course/lesson/level`), corporate site (`page/department/team`), personal cabinet (`section/setting/subscription`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **Hand-written, project-agnostic, grep-verified against the OneEntry menus module.** Source of truth for how menus work in OneEntry and how the blueprint pipeline must treat them. Used by code-inspector, entity-mapper, post-import-orchestrator, blueprint-validator.

## 1. TL;DR — how menus work in OneEntry

1. **Three tables, all out of the 24-table blueprint whitelist**:

   | Table | Role |
   |---|---|
   | `menus` | A menu (e.g. "Header navigation") — `identifier`, `localize_infos`. |
   | `menu_pages_mn` | M2M page ↔ menu — `menu_id`, `page_id`, `parent_id?`, `position_id`, `is_pinned`. Hierarchy via `parent_id`. |
   | `menu_custom_items_mn` | Custom (free-form) items — external URL / anchor / mailto / tel / relative path. `menu_id`, `value`, `localize_infos`, `position_id`. The `parent_id` column exists in the entity for storage of legacy hierarchies but is NOT exposed by `CreateMenuCustomItemDto` — custom items are created at root level. |

2. **Sort order = lexorank in the `positions` table** via `CommonPositionService` (`object_category_id = menu_id`). Menu pages and custom items share the **same** lexorank pool per menu — items interleave seamlessly.

3. **Content API output is a tree** (`GET /api/content/menus/marker/:marker`) — `base-menus.service.ts` merges pages + custom items by `parent_id` and lexorank. Storefront uses this single endpoint.

4. **Menus are NOT representable in the blueprint** — `menus` / `menu_pages_mn` / `menu_custom_items_mn` are not in the 24-table whitelist of the blueprint-loader. The blueprint pipeline therefore:
   - Inspector detects menu signals (Header/Footer components, MEGA_DATA/FOOTER_LINKS data files).
   - Mapper emits `mapped.post_import_menus[]` — task list to create after blueprint upload.
   - Post-import-orchestrator reads it and POSTs via REST against `/api/admin/menus*` endpoints.
   - Validator checks that the task list is non-empty when menu signals exist (S61).

---

## 2. What the blueprint pipeline MUST do

### 2.1 Inspector — detect menu signals

Look at the project for any of:
- Components: `Header*`, `Footer*`, `*Menu*`, `*Nav*`, `MobileDrawer*`, `MegaMenu*`.
- Data files: `headerConfig.*`, `footerConfig.*`, `MEGA_DATA`, `SUB_CATEGORIES`, `FOOTER_LINKS`, `headerLinks`, `navItems`, `mainMenu`, `topNav`.
- Page-routing constants exporting an array of `{ title, href, children? }`-shaped records.

Emit in `inspector.yaml`:
```yaml
notes:
  menus:
    present: true
    signals:
      - { kind: component, name: Header, path: src/app/components/Header.tsx }
      - { kind: data,      name: MEGA_DATA, path: src/app/data/categories.ts:8 }
      - { kind: data,      name: FOOTER_LINKS, path: src/app/data/footerConfig.ts }
    extracted:
      header_items:
        - { title: "Women's", href: "/women", children: [{ title: "Clothing", href: "/women/clothing" }, ...] }
        - { title: "Men's",   href: "/men",   children: [...] }
      footer_items:
        - { title: "About us", href: "/about-us" }
        - { title: "Contact",  href: "/contact" }
```

The `extracted.*` blocks are the practical input for the mapper — they preserve hierarchy.

### 2.2 Mapper — build `post_import_menus[]` task list

See `entity-mapper.md` Step 9.7. Goal: take inspector's extracted menu data and write `mapped.post_import_menus[]` — one task per menu that should be created after import. Also emit `out-of-whitelist-needs-post-import: N menus …` warning.

---

## 3. Mapper task structure (`mapped.post_import_menus[]`)

```yaml
post_import_menus:
  - identifier: header              # menu marker (URL-safe slug); UNIQUE constraint on creation
    localize_infos:
      en_US: { title: "Main Menu" }
    items:                          # menu_pages_mn rows — link existing blueprint pages
      - { page_slug: women,    parent_slug: null,  position: 1, is_pinned: false }
      - { page_slug: men,      parent_slug: null,  position: 2, is_pinned: false }
      - { page_slug: women-clothing, parent_slug: women, position: 1, is_pinned: false }
      - { page_slug: women-shoes,    parent_slug: women, position: 2, is_pinned: false }
      - { page_slug: sale,     parent_slug: null,  position: 3, is_pinned: false }
    custom_items:                   # menu_custom_items_mn rows — free-form URLs/anchors
      - identifier: contact-us
        value: "mailto:hello@example.com"
        localize_infos: { en_US: { title: "Contact us" } }
        parent_slug: null
        position: 4
  - identifier: footer
    localize_infos:
      en_US: { title: "Footer" }
    items:
      - { page_slug: about-us,   parent_slug: null, position: 1 }
      - { page_slug: faq,        parent_slug: null, position: 2 }
      - { page_slug: contact,    parent_slug: null, position: 3 }
    custom_items: []
```

**Key fields:**
- `identifier`: menu marker, must be URL-safe slug (`[a-z0-9-]+`). UNIQUE constraint on `menus.identifier`.
- `items[].page_slug`: must match an `identifier` of a row in `blueprint.tables.pages[]`. Migrator resolves `page_slug → @page.<slug>` token; loader resolves the token to the page id.
- `items[].parent_slug` OR `items[].parent_identifier`: REFERENCE to another item in the same menu. Used to compute `menu_pages_mn.parent_id` — see §3.0 below for the **mandatory token-namespace contract**.
- `custom_items[].parent_identifier`: same mechanism for grouping/external-URL items.
- `position` *(advisory only)*: position-id is auto-assigned per menu via lexorank in the `positions` table; array order in `items[]` determines the initial order.

### 3.0 menu_pages_mn.parent_id — universal token contract

> Universal rule, applies to every OneEntry project. Misuse breaks the admin menu tree and the storefront `GET /api/content/menus/marker/:marker` response (both rely on the same hierarchy semantics).

`menu_pages_mn.parent_id` and `menu_custom_items_mn.parent_id` are **not self-FK in the functional sense**. The cms `fk-graph.ts` registers them as self-FK for topo-sorting, but the actual semantic — enforced by `base-menus.service.ts:update()` and read by `cms_frontend/views/menu/MenuManagement.js` — is:

**`menu_pages_mn.parent_id` references `pages.id` of the parent page** (not the parent's `menu_pages_mn.id`).

Why: the admin menu UI builds the hierarchy by walking `pages.parentId` (`MenuManagement.js:75` — `allPages.filter((page) => page.parentId === pageId)`). The same page tree must be mirrored inside the menu: every child's `menu_pages_mn.parent_id` equals the parent's `pages.id`. The cms update service computes this automatically when an admin edits the menu — but the blueprint loader has no such logic and trusts whatever token you emit. So you MUST emit a page token.

| Field | Required token | Resolves to |
|---|---|---|
| `menu_pages_mn.page_id` | `@page.<slug>` | `pages.id` of THIS entry |
| `menu_pages_mn.parent_id` | `@page.<parent_slug>` | `pages.id` of PARENT page (must also be in the menu) |
| `menu_custom_items_mn.parent_id` | `@page.<parent_slug>` *(typical)* OR `@mci.<menu>_<id>` *(when nested under another custom item)* | `pages.id` *or* `menu_custom_items_mn.id` — polymorphic |

Example — universal Women / Men hierarchical menu, vertical-agnostic:

```yaml
# Blueprint emits (post-mapper-fixer.py does this automatically):
tables:
  menu_pages_mn:
    - { id: '@mp.header_women',           menu_id: '@menu.header', page_id: '@page.women',           parent_id: null }
    - { id: '@mp.header_women-clothing',  menu_id: '@menu.header', page_id: '@page.women-clothing',  parent_id: '@page.women' }
    - { id: '@mp.header_women-shoes',     menu_id: '@menu.header', page_id: '@page.women-shoes',     parent_id: '@page.women' }
    - { id: '@mp.header_men',             menu_id: '@menu.header', page_id: '@page.men',             parent_id: null }
    - { id: '@mp.header_men-clothing',    menu_id: '@menu.header', page_id: '@page.men-clothing',    parent_id: '@page.men' }
```

Universal across verticals — same rule for restaurant menus (Cuisine → Course → Dish), hotel navigation (Property type → Amenity), EdTech (Faculty → Program → Module → Lesson), corporate sites (Department → Team → Page), SaaS (Section → Subsection).

**Common mistake to avoid:** emitting `parent_id: '@mp.<menu>_<key>'` (the join row's own token) "works" in the loader (TokenRegistry is a flat string→int map and the integer ends up in the DB), but the admin reads it as `pageId = X` → no page with id X → flat list. The data is silently wrong.

Pre-condition for `parent_id` to actually render nested in admin:
1. The PARENT page must also have a `menu_pages_mn` entry in the same menu (otherwise the admin loop `allPages.filter(p => p.parentId === pageId)` finds nothing).
2. The PARENT page itself must have a correct `pages.parent_id` (the page tree, not the menu tree).

`post-mapper-fixer.py::migrate_post_import_to_tables` enforces this contract automatically via `mn_token[(menu, key)] = '@page.<slug>'`.

### 3.1 Hierarchical menus from Record-of-Record sources

Many real projects express navigation as deeply nested records:

```ts
// Universal pattern: outer dict by top-tab, inner dict by sub-category,
// arrays of items at the leaves. Same shape across e-commerce
// (gender → subcat → section), restaurants (cuisine → course → dish),
// hotels (property type → amenity group → amenity), education
// (faculty → program → module → lesson).
export const MEGA_DATA = {
  women: {
    clothing: [
      { title: 'CLOTHING', items: ['Pants & Shorts', 'Jeans', …] },
      { title: 'SEASONAL TRENDS', items: [...] },
    ],
    shoes: [...]
  },
  men: { … },
};
```

`post-mapper-fixer.py::_scan_hierarchical_menus` recursively walks any such
structure and emits one `post_import_menus[].items[]` (or `custom_items[]`)
row per node, with `parent_identifier` set to the slugified path. The dict
keys (`women`, `men`, `clothing`, …) become parent rows with empty `value`
(grouping nodes); the leaf strings or `{label, href}` records become
clickable rows.

Pre-conditions for the scanner to fire:
1. File stem matches `_NAV_FILE_HINTS` (`header*`/`footer*`/`menu*`/`nav*`/
   `sitemap*`/`mega*`/`categor*`/`section*`).
2. Largest exported value has a `_max_nesting_depth ≥ 2` — bare string arrays
   like `HEADER_LANGUAGES = ['EN', 'DE', …]` and flat record-of-strings are
   ignored (they aren't menus).

Result for the example above: `women` (group) → `women_clothing` (group) →
`women_clothing_clothing` (group) → `pants_shorts`, `jeans`, … (leaves);
plus the parallel `men` subtree.

---

## 4. Inspector extraction heuristics

### 4.1 MEGA_DATA / categories.ts pattern

Typical shape:
```ts
export const MEGA_DATA = {
  women: { clothing: [{ title: 'CLOTHING', items: [...] }, ...], shoes: [...] },
  men:   { clothing: [...], shoes: [...] },
};
```

Inspector should:
1. Read keys of the top-level object → root menu items (`women`, `men`).
2. Match each root to an existing page slug (`women`, `men`).
3. Read nested keys → sub-menu items, match to composite catalog slugs (`women-clothing`, `women-shoes`).

### 4.2 FOOTER_LINKS / footerConfig.ts pattern

Typical shape:
```ts
export const FOOTER_LINKS = [
  { title: 'About us', href: '/about-us' },
  { title: 'FAQ',      href: '/faq' },
  { title: 'Contact',  href: '/contact' },
];
```

Inspector should:
1. Read each entry as a flat menu item.
2. Match `href` (strip leading `/`) to existing page slug.
3. If no matching page exists → emit as `custom_items[].value: '<href>'`.

### 4.3 Header components walk

If extraction from data is impossible (e.g. menu items are hard-coded inline JSX), inspector should at minimum record component paths and emit `extracted: {}` empty so the mapper knows it's an "admin-to-fill" case.

---

## 5. Anti-patterns

| Anti-pattern | Correct |
|---|---|
| Writing rows into `menus` / `menu_pages_mn` / `menu_custom_items_mn` inside `blueprint.tables.*` | Emit `mapped.post_import_menus[]` + `out-of-whitelist-needs-post-import:` warning |
| Adding a `menus` column to `attributes_sets.schema` | The data model is structural (`menus` + `menu_pages_mn`), not jsonb-on-page |
| Putting menu items as separate `pages` with `general_type_id=17` and a synthetic `page_url` | Pages already exist in blueprint — menus only **reference** them |
| Treating `menuTitle` field on a page as menu definition | `menuTitle` is the display text inside a future menu, **not** a menu by itself |

---

## 6. Real REST API contract

### 6.1 Create menu (with page-items in one call)

`CreateMenuDto` uses **camelCase** field names and accepts the full list of
page-items in `pagesIds`. There is **NO separate `POST /:id/pages` endpoint**
for adding page-items — all pages are passed up-front.

```
POST /api/admin/menus
Authorization: Bearer <token>
Content-Type: application/json

{
  "identifier": "header",
  "localizeInfos": { "en_US": { "title": "Main Menu" } },
  "pagesIds": [12, 18, 25, 30, 31],
  "pinnedIds": [],
  "isPinned": false
}
```
- Returns `{ id, identifier, ... }`. `id` is the integer PK used in subsequent calls.
- All pages from `pagesIds` are linked in one transaction; positions are auto-assigned (lexorank).
- Permission: `AdminPermissionsEnum['menu.create']`.

### 6.2 Add pages to existing menu (PUT, not POST)

To add new pages to an existing menu — use `PUT /api/admin/menus/:id` with
`UpdateMenuDto` (which also accepts `pagesIds`). Pass the **full merged list**
(existing ∪ new); the service reconciles by id.

```
PUT /api/admin/menus/<menu_id>
{ "pagesIds": [12, 18, 25, 30, 31, 42] }   // 42 is the new one
```

To reorder a single existing item by lexorank: `PUT /api/admin/menus/:id/page/:pageId/position`.

⚠ **There is no `POST /api/admin/menus/:id/pages` endpoint.** Earlier docs
incorrectly mentioned it — code never had it. Verified against
`admin-menus.controller.ts` (2026-05-31 cms HEAD).

- Permission: `AdminPermissionsEnum['menu.update']` for PUT; `menu.items.changePositions` for the position endpoint.

### 6.3 Add custom item (external URL / anchor / mailto)

`CreateMenuCustomItemDto` accepts **only** `localizeInfos` + `value`. It does
NOT accept `parent_id` or `identifier` — class-validator whitelist rejects
unknown keys. Hierarchy/identification for custom items is not supported by
the create DTO; they get an auto-generated id and live at root level.

```
POST /api/admin/menus/<menu_id>/custom-items
{
  "value": "https://example.com",
  "localizeInfos": { "en_US": { "title": "External link" } }
}
```
- Permission: `AdminPermissionsEnum['menu.items.add']`.

### 6.4 Idempotency before creating
1. `GET /api/admin/menus` → list existing menus.
2. If `identifier` already exists → skip create, reuse `id`. Use `PUT` (6.2) to add missing pages.
3. For `custom_items[]` — fetch existing custom items via `GET /api/admin/menus/:id`, dedupe by `value`.

### 6.5 Required admin permissions
- `menu.create`
- `menu.update`
- `menu.delete`
- `menu.items.add`
- `menu.items.remove`
- `menu.items.changePositions`

All seeded in the CMS admin-rights seed migrations (preseeded). Orchestrator does NOT need to grant them — admin user must have them by definition.

### 6.6 What CANNOT be auto-resolved
- Per-menu page ordering / hierarchy beyond what `pagesIds: number[]` natural order provides — current orchestrator does **not** call any per-item position endpoint. Admin must reorder in OneEntry Platform UI if precise control is needed (see "Note on orphan fields" in §3).
- Pinning (`is_pinned` per page / top-level `pinned_slugs`) — current orchestrator does **not** call the pin endpoint. Admin pins items manually in the UI.
- Multi-language menu titles when inspector saw only one language — orchestrator copies the default into other languages and emits a warning.

---

## 7. End-to-end pipeline example

1. **Inspector** finds `Header.tsx` + `MEGA_DATA` + `FOOTER_LINKS` → emits `inspector.yaml.notes.menus.extracted.header_items/footer_items`.
2. **Mapper** copies the signals into `mapped.post_import_menus[]` — one entry per logical menu (header / footer / sidebar). Emits warning `out-of-whitelist-needs-post-import: N menus …`. Does NOT mutate `pages.localize_infos.menuTitle` (that's the displayed text within a future menu — orthogonal to menu existence).
3. **Builder** ignores `post_import_menus[]` (lives at the mapped-level meta, not inside blueprint tables).
4. **Validator** S61 — INFO when inspector recorded menu signals but mapper didn't emit `post_import_menus[]`.
5. **Loader** uploads blueprint via `POST /api/admin/import/from-blueprint` (menus untouched — pages exist now).
6. **Post-import-orchestrator Step 8** reads `mapped.post_import_menus[]`. For each task: create menu → add page-items → add custom-items, with idempotency check.

---

## 8. Cross-references

- OneEntry menus module — entity / DTOs / controllers (admin + content + base); REST contract is reproduced inline in §3 (`POST/PUT /api/admin/menus`, items endpoints).
- Tree assembly (`buildTree`) — performed by the base menus service; storefront receives the assembled tree via `GET /api/content/menus/marker/:marker`.
- `entity-mapper.md` Step 9.7 — emission of `post_import_menus[]`.
- `post-import-orchestration.md` Step 8 — orchestrator algorithm.
- `agents_datasets/ClaudeInfos/use-cases.md` case 7 — Site menu entity reference.
- `agents_datasets/ClaudeInfos/entities-catalog.md` — `MenuEntity` / `MenuPageEntity` / `MenuCustomItemEntity`.
