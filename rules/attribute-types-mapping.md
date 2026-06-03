# Attribute types mapping — 19 OneEntry types and recognition heuristics

> **⚠ Universality note.** Examples below may reference fashion-shop terms (clothing / shoes / bags / women / men) — they are **illustrative**. The **rules themselves are universal**: substitute the vocabulary of YOUR project type when applying them — e-commerce shop, restaurant (`menu-item/dish/cuisine`), beauty salon (`service/master/treatment`), hotel (`room/suite/amenity`), EdTech (`course/lesson`), corporate site (`page/department/team`), personal cabinet (`section/setting`), SaaS (`plan/feature/seat`). The blueprint pipeline treats all of them the same way.

> **This file is a self-contained mirror of OneEntry Platform rules.** Agents use only this file.
>
> The data is synchronized with the OneEntry Platform `AttributeType` enum and `SchemaItem` interface (maintainer keeps this file in sync with the CMS source).

## ⚠️ Critical rule: we use the enum VALUES, not the constant names

```ts
export enum AttributeType {
  string = 'string',
  text = 'text',
  textWithHeader = 'textWithHeader',
  integer = 'integer',
  real = 'real',
  float = 'float',
  dateTime = 'dateTime',
  date = 'date',
  time = 'time',
  file = 'file',
  image = 'image',
  groupOfImages = 'groupOfImages',
  flag = 'radioButton',          // ⚠ name `flag`, value 'radioButton'
  list = 'list',
  button = 'button',
  entity = 'entity',
  spam = 'spam',
  json = 'json',
  timeInterval = 'timeInterval',
}
```

In the blueprint JSON, `schema.<attr>.type` is **strictly the string value**:
- ✅ `"type": "radioButton"` (for a boolean flag)
- ❌ `"type": "flag"`

19 allowed `type` values:
```
string, text, textWithHeader, integer, real, float,
dateTime, date, time, file, image, groupOfImages,
radioButton, list, button, entity, spam, json, timeInterval
```

## SchemaItem structure (minimum and maximum)

Minimum:
```json
{
  "type": "string",
  "localizeInfos": { "en_US": { "title": "Title" } },
  "position": 1,
  "identifier": "title"
}
```

Full (`attributes-sets.interface.ts:23-55`):
```ts
type SchemaItem = {
  type: AttributeType;
  rules?: JSON;                  // validation rules (regex, etc.)
  localizeInfos: SchemaItemLocalizeInfos;  // required, at least 1 lang
  position?: number;
  identifier?: number | string;
  isPrice?: boolean;             // exactly 1 in a product attribute_set
  isSku?: boolean;               // exactly 1 in a product attribute_set
  isCurrency?: boolean;          // exactly 1
  isTaxRate?: boolean;
  isPassword?: boolean;          // exactly 1 in a signup/login form
  isLogin?: boolean;             // exactly 1 in a signup/login form
  isSignUp?: boolean;            // exactly 1 in a signup/login form
  isNotificationEmail?: boolean;
  isNotificationPhonePush?: boolean;
  isNotificationPhoneSMS?: boolean;
  isVisible?: boolean;
  additionalFields?: Record<string, any>;  // jsonb for everything else
  isProductPreview?: boolean;    // for image, exactly 1 in a product attribute_set
  isCompress?: boolean;          // for image
  isIcon?: boolean;              // for image
  isRatingValue?: boolean;       // for real
  id?: number;
  listTitles?: Record<lang, Array<{value:string,title:string,position?:number,extended?:any}>>;
                                 // for list / radioButton — MUST be an array
  multiselect?: boolean;         // for list — true = multi-value, default single
  moduleIdentifier?: string;     // for entity
  listType?: 'flat' | 'nested';  // ONLY for type='entity' — frontend rejects 'single'/'multiple'
  previewTemplateId?: number;
  intervals: any[];              // for timeInterval
  initialValue?: any;
  splitPrice?: boolean;
  splitParts?: number[];
  splitUnit?: 'number' | 'percent';
};
```

`SchemaItemLocalizeInfos` = `Record<lang, { title: string; mask?: string; maskPlaceholder?: string }>`.

## Full type table

| Type (value) | When to apply (code pattern) | Extra schema fields | Heuristic example |
|---|---|---|---|
| `string` | string ≤ 255, no newlines: `name`, `title`, `code` | `rules` (regex) | a `string` field in a TS type, length unspecified or ≤ 255 |
| `text` | multi-line text, `description`, `bio` | — | a `string` field with rich/multiline signals (textarea, markdown) |
| `textWithHeader` | rich-text with a header (CMS block) | — | rarely used; an explicit hint in the code "content block" |
| `integer` | whole number: `count`, `qty`, `stock` | `rules` (min/max) | a `number` without a decimal point in samples |
| `real` or `float` | fractional number: `weight`, `rating`, `price` (without isPrice) | `isRatingValue` for ratings | `number` with a decimal point; `price`/`cost`/`amount` → `real` + `isPrice: true` |
| `dateTime` | ISO string `YYYY-MM-DDTHH:MM:SS` | — | `Date`, `createdAt`, `publishedAt` |
| `date` | `YYYY-MM-DD` | — | `birthday`, `releaseDate` |
| `time` | `HH:MM` or `HH:MM:SS` | — | rare in e-commerce |
| `file` | arbitrary document (pdf, doc) | — | a `string` URL ending in a non-image extension |
| `image` | single image URL | `isProductPreview`, `isCompress`, `isIcon` | fields `image`, `cover`, `imageUrl`, `thumbnail` |
| `groupOfImages` | array of URLs | — | fields `gallery`, `images: string[]` |
| `radioButton` | boolean flag (`isFeatured`, `isOnSale`) | — | a `boolean` field |
| `list` | array of objects with fixed options | `listTitles[lang]: [{value,title,position}]` (ARRAY, NOT dict), `multiselect: true` for multi | `colors: [{hex,name}]`, `sizes: ['S','M','L']`, tags |
| `button` | UI button in a template | — | rare, code hint (template block) |
| `entity` | reference to another entity | `moduleIdentifier` (identifier of the target attribute_set) | `categoryId`, `brandId` referring to a reference table |
| `spam` | anti-spam form field (honeypot) | — | a form field named `spam`/`honeypot` |
| `json` | arbitrary JSON that cannot be parsed | — | `metadata`, `extra`, `payload` |
| `timeInterval` | schedule / delivery intervals / working hours | `intervals: [{from,to,days?}]`, `initialValue` | `'09:00-18:00'` regex, `{from,to}` object |

## Recognition heuristics (apply in order)

Apply sequentially, stop at the first match:

### 1. By field name (name contains ⇒ type + flags)

| Name pattern | Type | Extra flag |
|---|---|---|
| `price`, `cost`, `amount` | `real` | `isPrice: true` |
| `currency`, `currencyCode` | `string` | `isCurrency: true` |
| `sku`, `article`, `code` (as a unique product identifier) | `string` | `isSku: true` |
| `taxRate`, `vat` | `real` | `isTaxRate: true` |
| `email` (in a form) | `string` | `isLogin: true` |
| `password` (in a form) | `string` | `isPassword: true` |
| `signUp`, `register` (boolean in a form) | `radioButton` | `isSignUp: true` |
| `phone`, `mobile` | `string` | `additionalFields: { mask: '+7 (###) ###-##-##' }` |
| `image`, `cover`, `imageUrl`, `thumbnail`, `photo` (single) | `image` | for the main product image — `isProductPreview: true` (one per attribute_set) |
| `gallery`, `images` (array) | `groupOfImages` | — |
| `description`, `bio`, `content`, `summary`, `text` (long) | `text` | — |
| `title`, `name`, `label` | `string` | — |
| `rating` | `real` | `isRatingValue: true` |
| `is*`, `has*` (boolean) | `radioButton` | — |
| `*At`, `*Date` (timestamp) | `dateTime` | — |
| `metadata`, `extra`, `payload`, `config` | `json` | — |

### 2. By value type (if the name does not help)

- Array of primitives with repeating values (`['S','M','L']`, tags) → `list` with `multiselect: true` (if source is an array of selected values) or default single. `listTitles[lang]` is an ARRAY of `{value,title,position}` — never a dict.
- Array of objects `[{hex,name},…]` or `[{value,label},…]` → `list` with `listTitles` built from the objects.
- Array of image URLs → `groupOfImages`.
- An object with a known structure `{from:'09:00',to:'18:00'}` or regex `^\d{2}:\d{2}-\d{2}:\d{2}$` → `timeInterval`.
- Boolean → `radioButton`.
- ISO string `YYYY-MM-DDT*` → `dateTime`.
- An arbitrary object that cannot be parsed → `json`.

### 3. Relationships between entities

- A `*Id` field (e.g. `categoryId`, `brandId`) referring to `data/<other>.ts` or a static reference table → `entity` + `moduleIdentifier: '<target attribute_set identifier>'`.
- If the reference is a short enum in the code, **turn it into a `list` with `listTitles`** rather than making a separate entity.

## Detailed examples

### Product colors (`colors: [{hex,name}]`)

Source:
```ts
const colors = [
  { hex: '#000000', name: 'Black' },
  { hex: '#FFFFFF', name: 'White' },
];
```

Schema item:
```json
{
  "type": "list",
  "listTitles": {
    "en_US": [
      { "value": "#000000", "title": "Black", "position": 1 },
      { "value": "#FFFFFF", "title": "White", "position": 2 }
    ]
  },
  "localizeInfos": { "en_US": { "title": "Color" } },
  "position": 5,
  "identifier": "color"
}
```

⚠ **`listTitles[lang]` MUST be an ARRAY of `{value, title, position}`** — NOT
a dict `{"#000000": "Black"}`. Frontend `ListFieldsParameters.js:109` does
`Array.isArray(options[lang])`; dict form resolves to `langOptions=[]` and
the admin shows "Not selected" for any saved value.

### Clothing sizes (array of primitives, multi-select)

Source:
```ts
const sizes = ['XS','S','M','L','XL'];
```

Schema item:
```json
{
  "type": "list",
  "multiselect": true,
  "listTitles": {
    "en_US": [
      { "value": "XS", "title": "XS", "position": 1 },
      { "value": "S",  "title": "S",  "position": 2 },
      { "value": "M",  "title": "M",  "position": 3 },
      { "value": "L",  "title": "L",  "position": 4 },
      { "value": "XL", "title": "XL", "position": 5 }
    ]
  },
  "localizeInfos": { "en_US": { "title": "Size" } },
  "position": 6,
  "identifier": "size"
}
```

⚠ For multi-select use `"multiselect": true` (boolean) — NOT
`"listType": "multiple"`. The values `'single'` / `'multiple'` are NOT
accepted by the admin; `listType` is reserved for entity-list type with
values `'flat'` / `'nested'` only.

### Store working hours

Source:
```ts
const businessHours = { from: '09:00', to: '21:00', days: ['mon','tue','wed','thu','fri','sat'] };
```

Schema item:
```json
{
  "type": "timeInterval",
  "intervals": [{ "from": "09:00", "to": "21:00", "days": ["mon","tue","wed","thu","fri","sat"] }],
  "initialValue": null,
  "localizeInfos": { "en_US": { "title": "Business hours" } },
  "position": 1,
  "identifier": "business_hours"
}
```

### Product price

Source: `price: 199.99`.

Schema item:
```json
{
  "type": "real",
  "isPrice": true,
  "localizeInfos": { "en_US": { "title": "Price" } },
  "position": 2,
  "identifier": "price"
}
```

### Product image (main)

Source: `imageUrl: 'https://.../product.jpg'`.

Schema item:
```json
{
  "type": "image",
  "isProductPreview": true,
  "isCompress": true,
  "localizeInfos": { "en_US": { "title": "Main image" } },
  "position": 3,
  "identifier": "preview"
}
```

### Product SKU

Source: `sku: 'WC-001'`.

Schema item:
```json
{
  "type": "string",
  "isSku": true,
  "localizeInfos": { "en_US": { "title": "SKU" } },
  "position": 1,
  "identifier": "sku"
}
```

### Email field in a login form

Schema item (within the attribute_set schema of the login=signup form):
```json
{
  "type": "string",
  "isLogin": true,
  "rules": { "pattern": "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$" },
  "localizeInfos": { "en_US": { "title": "Email" } },
  "position": 1,
  "identifier": "email"
}
```

### Password in a form

Schema item:
```json
{
  "type": "string",
  "isPassword": true,
  "rules": { "minLength": 6 },
  "localizeInfos": { "en_US": { "title": "Password" } },
  "position": 2,
  "identifier": "password"
}
```

### "Is registration" flag in a form (login=signup)

Schema item:
```json
{
  "type": "radioButton",
  "isSignUp": true,
  "localizeInfos": { "en_US": { "title": "Sign Up" } },
  "position": 3,
  "identifier": "sign_up"
}
```

### text (multi-line rich text)

Source: `description: "A long product description with line breaks."`.

Value structure — `AttributeTextType[]` (an array of objects, usually with 1 element): `{htmlValue, plainValue, mdValue, params: {isImageCompressed, editorMode}}`.

Schema item:
```json
{
  "type": "text",
  "localizeInfos": { "en_US": { "title": "Description" } },
  "position": 5,
  "identifier": "description"
}
```

### textWithHeader (a CMS content block with a header)

Value structure — `AttributeTextWithHeaderType[]`: `{header, htmlValue, plainValue, mdValue, params}` (see `attribute-value.type.ts:144-183`). The `header` field is the section name/title, separate from the body.

Schema item:
```json
{
  "type": "textWithHeader",
  "localizeInfos": { "en_US": { "title": "Content section" } },
  "position": 1,
  "identifier": "section"
}
```

### integer (whole number — quantity, stock)

Source: `stock: 42`.

Schema item:
```json
{
  "type": "integer",
  "rules": { "minValue": 0 },
  "localizeInfos": { "en_US": { "title": "Stock quantity" } },
  "position": 7,
  "identifier": "stock"
}
```

### dateTime (full date + time)

Value structure — `AttributeDateTimeType`: `{fullDate, formattedValue, formatString}` (see `attribute-value.type.ts:6-27`).

- `fullDate`: ISO `'2024-05-07T21:02:00.000Z'`
- `formattedValue`: `'08-05-2024 00:02'` (formatted according to `formatString`)
- `formatString`: `'DD-MM-YYYY HH:mm'`

Schema item:
```json
{
  "type": "dateTime",
  "localizeInfos": { "en_US": { "title": "Published at" } },
  "position": 8,
  "identifier": "published_at"
}
```

### date (date only, no time)

Schema item:
```json
{
  "type": "date",
  "rules": { "minDate": "1900-01-01", "maxDate": "2030-12-31" },
  "localizeInfos": { "en_US": { "title": "Birthday" } },
  "position": 4,
  "identifier": "dob"
}
```

### time (time only)

Schema item:
```json
{
  "type": "time",
  "localizeInfos": { "en_US": { "title": "Opening time" } },
  "position": 2,
  "identifier": "opening_time"
}
```

### file (arbitrary document — pdf, doc, zip)

Value structure — `AttributeFileType`: `{filename, downloadLink, size, contentType?}` (see `attribute-value.type.ts:29-59`).

Schema item:
```json
{
  "type": "file",
  "additionalFields": { "allowedExtensions": ["pdf", "doc", "docx"], "maxSize": 5242880 },
  "localizeInfos": { "en_US": { "title": "CV / Resume" } },
  "position": 9,
  "identifier": "cv_file"
}
```

### groupOfImages (gallery — multiple images)

Source: `gallery: ['url1.jpg', 'url2.jpg', 'url3.jpg']`.

Value structure — array of `AttributeImageType[]`: `[{filename, downloadLink, previewLink, size, params: {isImageCompressed}, contentType}]` (see `attribute-value.type.ts:61-108`).

Schema item:
```json
{
  "type": "groupOfImages",
  "isCompress": true,
  "localizeInfos": { "en_US": { "title": "Gallery" } },
  "position": 4,
  "identifier": "gallery"
}
```

### button (UI button in a template)

Used rarely — in template/block schemas when a declarative button with text and a link is needed. The exact serialization is provided through `additionalFields`.

Schema item:
```json
{
  "type": "button",
  "additionalFields": { "href": "/checkout", "variant": "primary" },
  "localizeInfos": { "en_US": { "title": "Checkout button" } },
  "position": 10,
  "identifier": "cta_checkout"
}
```

### entity (reference to another entity)

Used when an attribute field is a reference to a record in another attribute_set (or module). `moduleIdentifier` points to the target attribute_set by identifier.

Source: `brandId: 12` references the `brands` reference (attribute_set with identifier `forBrands`).

Schema item:
```json
{
  "type": "entity",
  "moduleIdentifier": "forBrands",
  "listType": "single",
  "localizeInfos": { "en_US": { "title": "Brand" } },
  "position": 6,
  "identifier": "brand"
}
```

⚠ An `entity` attribute requires the target attribute_set to exist in the blueprint (or in the DB from presets). If the reference is a simple code enum — use `list` with `listTitles`, not `entity`.

### spam (anti-spam / honeypot)

A hidden form field that a real user does not fill in — if a non-empty value arrives, the submission is rejected. Not shown in the UI.

Schema item:
```json
{
  "type": "spam",
  "isVisible": false,
  "localizeInfos": { "en_US": { "title": "Honeypot" } },
  "position": 99,
  "identifier": "honeypot"
}
```

### json (arbitrary object that does not parse into structured types)

Source: `metadata: { source: 'imported', batch_id: 'B-001', flags: ['featured','new'] }`.

Schema item:
```json
{
  "type": "json",
  "localizeInfos": { "en_US": { "title": "Metadata" } },
  "position": 20,
  "identifier": "metadata"
}
```

`json` is a fallback for cases when the mapper is uncertain. Prefer breaking it down into separate fields (`source: string`, `batch_id: string`, `flags: list`) instead of stuffing everything into one `json`.

## Data shape — what goes into `attributes_sets[lang][<type>_id<N>]`

When an attribute is filled with a value, the data side has its own per-type
shape. The data key is `<type>_id<innerId>` (e.g. `list_id3`, `image_id7`),
NOT the semantic identifier. Below is what each renderer in
`cms_frontend/.../shared/Custom/Attributes/Parameters/` expects.

| Type | Value shape | Renderer evidence |
|---|---|---|
| `string`, `textarea` | bare string `"text"` | `StringFieldsParameters.js:78` |
| `text` | `{htmlValue:"…", plainValue:"…", mdValue:"…", params:{editorMode:"HTML"}}` | `TextFieldsParameters.js:99,822-823` |
| `integer`, `real` | string `"123.45"` (NOT number) | `NumberFieldsParameters.js:68-70` (`.trim()` on string-only path) |
| `list` (single or multi) | `[{value:"X"}, {value:"Y"}]` (array of `{value}` objects) | `ListFieldsParameters.js:101-102,137,150` |
| `radioButton` | `{value:"X"}` (object, NOT bare string; NOT empty string) | `RadioButtonFieldsParameters.js:34,44,56` |
| `image`, `groupOfImages` | `[{filename, downloadLink, previewLink:{"1":[origUrl, previewUrl]}}]` — note `previewLink` values are **tuples `[url, url]`** | `ImageFieldsParameters/ImageFieldsParameters.js:59,98,113` |
| `button` | `{value, href}` (object) | `ButtonFieldsParameters.js` |
| `date`, `dateTime`, `time` | `{fullDate:"ISO", formattedValue, formatString}` (NOT bare string) | `DateFieldsParameters.js:550` |
| `file` | array similar to image, `[{filename, downloadLink, size?}]` | `FileFieldsParameters.js:329` |

**Backfill defaults** (for schema keys absent from source data — admin needs a
shape to render an empty control):

| Type | Default |
|---|---|
| `list` / `image` / `groupOfImages` / `file` | `[]` |
| `string` / `textarea` | `""` |
| `text` | `{htmlValue:"", plainValue:"", mdValue:"", params:{editorMode:"HTML"}}` |
| `button` | `{}` |
| `integer` / `real` / `date` / `dateTime` / `time` / `radioButton` | omit the key entirely (admin treats absence as "not set") |

The blueprint pipeline (`post-mapper-fixer.py::transform_attribute_data_to_admin_shape`)
applies these transforms automatically — but mapper agents should generate
data in the correct shape from the start so the transform is a no-op.

## Attribute identifiers (snake_case)

- ASCII, latin, no whitespace, no Cyrillic.
- Predictable: `title`, `description`, `price`, `sku`, `color`, `size`, `images`, `preview`, `email`, `password`, `sign_up`, `business_hours`, `weight`.
- Unique within a single `schema`.

## ⚠ SchemaItem `id` — explicit, unique, contiguous (CRITICAL, added 2026-06-03)

Every `SchemaItem` in `schema.<attr>` **MUST** carry an explicit numeric `id`:

```json
"title":       { "id": 1,  "type": "string",         "identifier": "title",       "position": 1,  "localizeInfos": { ... } },
"sku":         { "id": 2,  "type": "string",         "identifier": "sku",         "position": 2,  "localizeInfos": { ... } },
"price":       { "id": 3,  "type": "real",           "identifier": "price",       "position": 3,  "localizeInfos": { ... }, "isPrice": true },
"gallery":     { "id": 4,  "type": "groupOfImages",  "identifier": "gallery",     "position": 4,  "localizeInfos": { ... } },
"description": { "id": 5,  "type": "text",           "identifier": "description", "position": 5,  "localizeInfos": { ... } }
```

**Rules:**
1. `id` is assigned by the **builder** when assembling `attributes_sets[]` (NOT by the mapper). Mapper outputs schema without `id`; builder fills `id: 1, 2, 3, ...` in declaration order of `schema.<attr>` keys (which Python dict / JSON preserves).
2. `id` values are **unique within a single `schema`** and **contiguous from 1** (no gaps, no duplicates).
3. **Never** emit a schema where two attributes have the same `id` — this corrupts the `attributes_sets` jsonb (two value-keys `<type>_id<N>` collide; one wins, the other is dropped).
4. **Never** rely on the `SeedAttributeSchemaIdsBackfill1880500000000` migration to assign `id` post-hoc. The backfill runs on whatever order the loader inserts the schema, but the `attributes_sets` jsonb values are already serialized with their own `<type>_id<N>` keys — if those keys don't match the backfilled ids, the admin UI shows empty fields and stray "ghost" values under unknown keys.

## ⚠ `attributes_sets` jsonb — key format contract (MUST follow)

The data jsonb column `attributes_sets` on `products` / `pages` / `blocks` / `forms` / `user_groups` stores per-language attribute values:

```json
{
  "<lang>": {
    "<type>_id<N>": <value>
  }
}
```

**`<type>` and `<N>` MUST be derived from the referenced `schema`:**
- `<type>` = `schema[attr].type` (e.g. `string`, `real`, `list`, `text`, `groupOfImages`).
- `<N>` = `schema[attr].id` (the numeric id assigned in the schema, see rule above).

⚠ **The mapper / builder MUST NOT** generate `<type>_id<N>` keys by counting their own emission order. Every key MUST resolve back to a specific `schema[attr]` by `(type, id)`. If the schema has `title` at `id=1` (type=string), the only correct data key is `string_id1`. Emitting `string_id12` for `title` (because builder happened to write it twelfth) is a bug — admin UI will not find this key in schema and show it under an "unknown" group, while the real schema `string_id1` stays empty.

**Coverage rule:** for every key in `schema.<attr>`, the mapper SHOULD emit a corresponding `<type>_id<N>` entry in the data jsonb — even if the value is empty. Use the per-type defaults from "Default values" above. This way the admin UI always renders the full attribute panel; missing entries surface as "no value set" by default rather than silently disappearing.

## Edge cases

- **Empty `schema = {}`** is allowed only for technical attribute_sets with no fields (for example, for admin without custom properties).
- **Flag duplication** (`isPrice` on two attributes) → the loader does not block this, but it is a business error. The builder is required to validate.
- **`additionalFields`** — where to put everything that does not fit standard fields: regex, min/max, validation masks, units, etc.
