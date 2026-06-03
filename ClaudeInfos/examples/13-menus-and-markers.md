<!-- audit: 5/5 (2026-05-13) endpoints[POST /menus, PUT /menus/:id, DELETE /menus/:id, PUT /menus/:id/page/:pageId/position, GET /menus/:id/included, POST /markers, PUT /markers/:id, DELETE /markers/:id], fields[menus.localize_infos jsonb, menu_pages_mn.is_pinned, menu_pages_mn.parent_id (hierarchy), menu_pages_mn.page_id, menu_pages_mn.menu_id, menu_pages_mn.position_id, markers.marker (uniq, indexed), markers.name, markers.localize_infos jsonb], queues[none], ws[none], fk[menu_pages_mn.page_id->pages.id (CASCADE, orphanedRowAction:'delete'), menu_pages_mn.menu_id->menus.id (CASCADE, orphanedRowAction:'delete'), menu_pages_mn.position_id->positions.id; markers have no FK to other entities] -->

# 13. Site menus and universal markers

## Purpose

Two independent scenarios that historically live in neighboring modules:

**Menus (`menus`)** — collections of links to pages used for UI navigation: main site menu, footer, mobile sidebar, brand menu in the admin panel. Supports **hierarchy** (dropdown submenus) via `parent_id`.

**Markers (`markers`)** — a universal dictionary of tags with localized titles. **Don't confuse** with schema markers on attributes (`isPrice`, `isSku` in `attributes_sets.schema[k]`) — these are different mechanisms (see below).

Scenarios:
- Create the main site menu: `POST /menus` → add pages via `POST /menus/:id/...` (returns the updated menu with bindings).
- Build a hierarchical menu "About > Team / History / Contacts": pages are added with `parentId` pointing to the parent `menu_pages_mn.id`.
- Change the order of pages in a menu: `PUT /menus/:id/page/:pageId/position`.
- Create a `markers` tag dictionary for UI use ("new", "hit", "sale") — the rendering of a specific marker in a template is bound via jsonb pointers or passed in `attributes_sets`.

## Entities and dependency hierarchy

```
pages                            — pages
  ↑ page_id (CASCADE)
menu_pages_mn                    — menu ↔ page link
                                   is_pinned, parent_id (hierarchy)
                                   position_id (order)
  ↑ menu_id (CASCADE)
menus                            — menu (main / footer / etc.)
                                   localize_infos jsonb, identifier UNIQUE

markers                          — tag dictionary (independent of menus)
                                   marker (text UNIQUE indexed), name, localize_infos
```

| Table | Base class | Key fields |
|---|---|---|
| `menus` | `BaseAbstractEntity` | `identifier` UNIQUE, `localize_infos jsonb (CommonLocalizeInfos)`, `menuPages` (OneToMany CASCADE) |
| `menu_pages_mn` | `BaseEntity` (own PK) | `is_pinned` (boolean), `page_id` (FK CASCADE), `menu_id` (FK CASCADE), `position_id` (FK), `parent_id` (nullable — hierarchy) |
| `markers` | `BaseAbstractEntity` | `name` (string), `marker` (UNIQUE indexed), `localize_infos jsonb` |

## Full jsonb with data

### `menus` (main site menu)

```json
{
  "id": 1,
  "identifier": "main-menu",
  "localizeInfos": {
    "en_US": { "title": "Main menu" }
  }
}
```

### `menu_pages_mn` (page bindings)

```json
[
  { "id": 100, "menuId": 1, "pageId": 5,  "parentId": null, "isPinned": true,  "positionId": 100 },
  { "id": 101, "menuId": 1, "pageId": 12, "parentId": null, "isPinned": false, "positionId": 101 },
  { "id": 102, "menuId": 1, "pageId": 13, "parentId": 101,  "isPinned": false, "positionId": 102 },
  { "id": 103, "menuId": 1, "pageId": 14, "parentId": 101,  "isPinned": false, "positionId": 103 },
  { "id": 104, "menuId": 1, "pageId": 20, "parentId": null, "isPinned": false, "positionId": 104 }
]
```

Here:
- Page 5 is a root item, **pinned** (`isPinned=true`).
- Page 12 is the root "About" item.
- Pages 13, 14 are submenus under 12 (`parent_id=101`).
- Page 20 is a root item.

Hierarchy lives in **`parent_id`** on `menu_pages_mn`, not on `pages`. This means the same page can be a sub-item in different menus under different parents.

### `markers` (tag dictionary)

```json
[
  {
    "id": 1,
    "marker": "new",
    "name": "New",
    "localizeInfos": {
      "en_US": { "title": "New" }
    }
  },
  {
    "id": 2,
    "marker": "sale",
    "name": "Sale",
    "localizeInfos": {
      "en_US": { "title": "Sale" }
    }
  },
  {
    "id": 3,
    "marker": "best-seller",
    "name": "Best seller",
    "localizeInfos": {
      "en_US": { "title": "Best seller" }
    }
  }
]
```

## Admin API

### `@Controller('menus')`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/menus` | — | List of menus |
| `GET` | `/menus/:id` | — | Menu details (with `menuPages`) |
| `GET` | `/menus/:id/included` | — | Only pages that ARE already included in the menu (for UI) |
| `POST` | `/menus` | `menu.create` | Create menu |
| `PUT` | `/menus/:id` | `menu.update` | Update (including page bindings) |
| `DELETE` | `/menus/:id` | `menu.delete` | Delete (CASCADE → menu_pages_mn) |
| `PUT` | `/menus/:id/page/:pageId/position` | `menu.items.changePositions` | Change page position in a menu |
| `GET` | `/menus/marker-validation/:marker` | — | Uniqueness check for `identifier` |
| `GET` | `/menus/marker/:marker` | — | Lookup by `identifier` |

### `@Controller('markers')`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/markers?offset=&limit=` | — | List |
| `GET` | `/markers/:id` | — | Details |
| `POST` | `/markers` | `markers.create` | Create |
| `PUT` | `/markers/:id` | `markers.update` | Update |
| `DELETE` | `/markers/:id` | `markers.delete` | Delete |
| `GET` | `/markers/marker/:marker` | — | Lookup by the `marker` field |

```http
POST /menus

{
  "identifier": "main-menu",
  "localizeInfos": {
    "en_US": { "title": "Main menu" }
  },
  "menuPages": [
    { "pageId": 5,  "parentId": null, "isPinned": true,  "positionId": 100 },
    { "pageId": 12, "parentId": null, "isPinned": false, "positionId": 101 }
  ]
}
```

## Cross-references

- [02-content-page.md](./02-content-page.md) — `pages.id` ← `menu_pages_mn.page_id`. Deleting a page cascades and removes it from every menu.
- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — **schema markers** (`isPrice`, `isSku`, etc.) in `attributes_sets.schema[k]`. This is a different mechanism — not to be confused with `MarkerEntity`.
- [16-index-attributes-search.md](./16-index-attributes-search.md) — `index_attribute_data.is_price/is_sku/is_currency` — reflections of schema markers on indexed rows. Also unrelated to the `markers` table.

## `MarkerEntity` vs schema markers — the key distinction

Two different mechanisms with similar names, constantly confused:

| Entity | Where it lives | What it is |
|---|---|---|
| **`MarkerEntity` (table `markers`)** | Its own table | **Tag dictionary** for UI. Universal — can be referenced from anywhere by `marker` (varchar). |
| **Schema markers** (`isPrice`, `isSku`, `isCurrency`, `isProductPreview`, `isIcon`, `isTaxRate`, `isRatingValue`, etc.) | `attributes_sets.schema[k]` jsonb | **Boolean flags on an attribute within a set.** They tag the role of the attribute for UI/business logic (this attribute is a price, that one is a SKU, etc.). |

Schema-marker example (from 10):

```json
"price": {
  "type": "real",
  "isPrice": true,           // schema marker
  "identifier": "price"
}
```

And separately — a `markers` row:
```json
{ "id": 1, "marker": "new", "name": "New" }
```

They are **completely unrelated**: the first means "this attribute has the role `price`", the second means "the reference tag `new` exists".

## Antipatterns

**"Each menu layout deserves its own table (`main_menu`, `footer_menu`, `mobile_menu`)."** Don't:

1. They are different rows in `menus` with different `identifier` values. One universal mechanism.
2. Page linkage goes through a single `menu_pages_mn`.
3. If tomorrow a "brand menu in admin" appears — don't create a table, just `POST /menus { identifier: 'admin-brand-menu' }`.

The right approach: use `identifier` to distinguish menu roles.

**"I'll put hierarchy in `pages.parent_page_id` to avoid `menu_pages_mn.parent_id`."** Don't:

1. The same page may live in different menus under **different parents** (main menu → "About → Team", but in the footer just "Team").
2. `pages.parent_id` is already used for catalog hierarchy (see [01](./01-catalog-product.md), [02](./02-content-page.md)), not for UI menus.
3. The hierarchy in `menu_pages_mn.parent_id` is **hierarchy within that specific menu**, isolated from other contexts.

**"I'll use `MarkerEntity.marker` as the attribute type in a schema."** Don't — `attributes_sets.schema[k]` already has its own `type` field (`AttributeType` enum). `MarkerEntity` is a **separate dictionary for the UI**, and its rows must not be confused with attribute types. Schema markers (`isPrice`, etc.) are **boolean flags**, whereas `MarkerEntity` rows are **table rows**. Different in nature.
