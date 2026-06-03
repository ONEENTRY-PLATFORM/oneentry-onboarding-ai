<!-- audit: 5/5 (2026-05-13) endpoints[POST /locales, PUT /locales/:id, PUT /locales/:code/set-active, DELETE /locales/:code (delete by code, not by id!), GET /languages, POST /languages], fields[locales.code (uniq, en_US format), locales.short_code (en), locales.is_active, locales.native_name (native title), locales.image (emoji), languages.code (dictionary of all languages), content_locales_usage.entity, content_locales_usage.entity_id, content_locales_usage.content_language], queues[none], ws[none], fk[no formal FKs; LocalesUsageEntity.contentLanguage logically corresponds to LocaleEntity.code] -->

# 14. Locales and languages: active UI locales, dictionary, usage tracking

## Purpose

OneEntry separates three localization concepts that are easy to confuse:

1. **`LocaleEntity` (`locales`)** — **active UI locales**: which languages are currently available in the admin panel and storefront.
2. **`LanguageEntity` (`languages`)** — **a dictionary of every language in the world**: used when adding a new locale as a source of `code`/`name`.
3. **`LocalesUsageEntity` (`content_locales_usage`)** — **"which locale is used where" tracking**: filled in automatically by `TrackLocaleUsageInterceptor`.

Scenarios:
- Enable a new UI language (for example, `bn_BD`): `POST /languages` (if not yet in the dictionary) → `POST /locales` → `PUT /locales/:id/set-active`.
- Remove a language: `DELETE /locales/:code` (by `code`, not by `id`!) → `TrackLocaleDeletionEventInterceptor` cleans `content_locales_usage`.
- Find out "which entities already have translations into `bn_BD`": `SELECT * FROM content_locales_usage WHERE content_language = 'bn_BD'`.

## Entities and dependency hierarchy

```
languages                    — dictionary of ALL languages in the world
                               (id, name, code)
locales                      — ACTIVE UI locales
                               (code uniq en_US, short_code en, name, native_name, is_active, image)
content_locales_usage        — tracking of which locale is used where
                               (entity, entity_id, content_language)
                               filled in by TrackLocaleUsageInterceptor
```

**There are no formal FKs between them.** The link is logical:
- `locales.code` (e.g. `'en_US'`) is the value that lands in `localize_infos` jsonb across every entity.
- `content_locales_usage.contentLanguage` — the same value, used for tracking.
- `languages` is used only as a reference dictionary when creating a new `locales` row.

| Table | Base class | Key fields |
|---|---|---|
| `locales` | `BaseEntity` | `code` (UNIQUE, `'en_US'`), `short_code` (`'en'`), `name` (English), `native_name` (English), `is_active` (boolean), `image` (emoji/url), `position_id` |
| `languages` | `BaseEntity` | `name`, `code` — simple dictionary, no localization, no position |
| `content_locales_usage` | own PK | `entity` (varchar), `entity_id` (int), `content_language` (varchar 30) |

### Which entities are tracked (EntitiesWithLocalesEnum)

`cms/src/modules/locales-usage/types/entities-with-locales.enum.ts`:

```ts
'admin attributes-sets' → 'attributes-sets'
'adminmenus'            → 'menus'
'adminblocks'           → 'blocks'
'adminforms'            → 'forms'
'adminmodules'          → 'modules'
'adminpages'            → 'pages'
'adminproducts'         → 'products'
'admintemplates'        → 'templates'
```

So on 8 entity types `TrackLocaleUsageInterceptor` catches `localize_infos` updates and writes the corresponding row into `content_locales_usage`.

## Full jsonb with data

### `locales` (active locale)

```json
{
  "id": 1,
  "code": "en_US",
  "shortCode": "en",
  "name": "English",
  "nativeName": "English",
  "isActive": true,
  "image": "🇺🇸",
  "positionId": 1
}
```

```json
{
  "id": 2,
  "code": "de_DE",
  "shortCode": "de",
  "name": "German",
  "nativeName": "Deutsch",
  "isActive": true,
  "image": "🇩🇪",
  "positionId": 2
}
```

```json
{
  "id": 7,
  "code": "bn_BD",
  "shortCode": "bn",
  "name": "Bengali",
  "nativeName": "বাংলা",
  "isActive": false,
  "image": "🇧🇩",
  "positionId": 7
}
```

The `bn_BD` locale has been created but is `isActive=false` — it isn't shown in the language switcher yet. Activation: `PUT /locales/7/set-active`.

### `languages` (dictionary)

```json
[
  { "id": 1,  "code": "en", "name": "English" },
  { "id": 2,  "code": "de", "name": "German" },
  { "id": 3,  "code": "fr", "name": "French" },
  { "id": 4,  "code": "bn", "name": "Bengali" },
  { "id": 5,  "code": "id", "name": "Indonesian" },
  { "id": 6,  "code": "zh", "name": "Chinese" }
]
```

A simple dictionary of all world languages. **This is NOT a list of active locales** — it's a list of "what exists in general".

### `content_locales_usage` (tracking)

```json
[
  { "id": 1, "entity": "products",        "entityId": 57, "contentLanguage": "en_US" },
  { "id": 2, "entity": "products",        "entityId": 57, "contentLanguage": "de_DE" },
  { "id": 3, "entity": "pages",           "entityId": 12, "contentLanguage": "en_US" },
  { "id": 4, "entity": "attributes-sets", "entityId": 9,  "contentLanguage": "en_US" },
  { "id": 5, "entity": "attributes-sets", "entityId": 9,  "contentLanguage": "de_DE" }
]
```

Each row says "the entity `entity:entityId` has a translation for `contentLanguage`". Filled in automatically by the interceptor on `PUT /products/57` with an update to `localize_infos.en_US.title`.

### `localize_infos` (typical use of `locales.code`)

`products.localize_infos` (or any other entity):

```json
{
  "en_US": { "title": "Ethiopia Yirgacheffe Coffee", "description": "..." },
  "de_DE": { "title": "Äthiopischer Yirgacheffe Kaffee", "description": "..." },
  "bn_BD": { "title": "ইথিওপিয়া ইয়ারগাচেফে কফি", "description": "..." }
}
```

Here `en_US`, `de_DE`, `bn_BD` are values from `locales.code`. The jsonb structure is **self-expanding**: adding a new locale = just a new key in `localize_infos`, no migrations required.

## Admin API

### `@Controller('locales')`

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/locales` | `settings.locales.create` | Create a new locale (`code`, `shortCode`, `name`, `nativeName`) |
| `GET` | `/locales?offset=&limit=` | — | List (with pagination) |
| `GET` | `/locales/:id` | — | Details by id |
| `GET` | `/locales/check-existence/:code` | — | Check whether a locale with that `code` exists |
| `PUT` | `/locales/:code/set-active` | `settings.locales.switching` | Activate/deactivate (by `code`!) |
| `PUT` | `/locales/:id` | `settings.locales.update` | Update (by `id`) |
| `DELETE` | `/locales/:code` | `settings.locales.delete` | Delete (by `code`!) — `TrackLocaleDeletionEventInterceptor` clears usage |
| `PUT` | `/locales/:id/position` | `settings.locales.changePositions` | Order |

> **Note:** `set-active` and `DELETE` operate **by `code`**, while `PUT /:id` and `/:id/position` operate **by `id`**. This is a historical quirk.

### `@Controller('languages')`

| Method | Path | Purpose |
|---|---|---|
| `GET` | `/languages` | Dictionary list |
| `GET` | `/languages/:id` | Single language |
| `POST` | `/languages` | Add a language to the dictionary |

```http
POST /locales

{
  "code": "bn_BD",
  "shortCode": "bn",
  "name": "Bengali",
  "nativeName": "বাংলা",
  "image": "🇧🇩"
}
```

```http
PUT /locales/bn_BD/set-active
```

After activation, the admin panel and storefront start showing the `bn_BD` language switcher.

## Behind the scenes

### `TrackLocaleUsageInterceptor`

`cms/src/modules/locales-usage/interceptors/track-locale-usage.interceptor.ts:17` — a global interceptor that on every successful admin request with a `localize_infos` update:
1. Resolves the entity name from the controller (`AdminProductsController` → `'products'` via `EntitiesWithLocalesEnum`).
2. Extracts `entityId` from the path params (`:id`).
3. Extracts the used `langCode` keys from `body.localizeInfos`.
4. Upserts into `content_locales_usage` by `(entity, entity_id, content_language)`.

### `TrackLocaleDeletionEventInterceptor`

Listens for `DELETE /locales/:code` and cleans up every `content_locales_usage` row with `content_language = :code`. This is **not an FK CASCADE** — it's explicit interceptor logic.

### Bull / WS

**Not used.** Locales are static configuration; there are no background jobs.

### Journal

`JournalingEvents.LANGUAGE_CREATED/UPDATED` — for the `multilanguage` module. For `locales` — `LOCALE_CREATED/UPDATED/DELETED` (if present in the enum).

### Permissions

`settings.locales.{create, update, delete, switching, changePositions}` in `AdminPermissionsEnum`.

## Cross-references

- [01-catalog-product.md](./01-catalog-product.md) — `products.localize_infos` uses `locales.code` as the key.
- [02-content-page.md](./02-content-page.md) — `pages.localize_infos`, `pages.attributes_sets[lang]`.
- [06-event-notification.md](./06-event-notification.md) — `events.localize_infos.template/subject/push` per language.
- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — `attributes_sets.schema[k].localizeInfos` per language.
- `agents_datasets/ClaudeInfos/data-model-core.md` — the generic `{ [lang]: { ... } }` jsonb shape.

## Antipatterns

**"To add a new language I'll ALTER TABLE products ADD COLUMN title_bn_bd."** Don't:

1. This requires a migration and deploy for every new language — incompatible with runtime locale additions.
2. You end up with dozens of columns and exploding indexes.
3. The `localize_infos jsonb` structure already expands without migrations.

The right approach:
1. `POST /locales` creates a new locale (`bn_BD`).
2. `PUT /locales/bn_BD/set-active` activates it.
3. On the next `PUT /products/:id` the admin just adds `localizeInfos.bn_BD.title = '...'` — jsonb accepts it.

**"I'll build a single `translations (entity, entity_id, lang, field, value)` table."** Classic EAV antipattern:

1. JOINs on every "give me product in en_US with all fields" query.
2. No way to validate structure (schema lives in one place, translations in another).
3. `localize_infos jsonb` already exists natively — PostgreSQL indexes jsonb and merges through CRDT.

**"`LocaleEntity` and `LanguageEntity` are the same thing, I'll keep one table."** Don't:

1. `LocaleEntity` represents **active locales of the project** (with `is_active`, `position`, `image`).
2. `LanguageEntity` is a **universal dictionary of all world languages** (used as a UI source when creating a locale).
3. Merging them breaks the "dictionary vs active configuration" split and leads to semantic soup.
