<!-- audit: 5/5 (2026-05-13) endpoints[POST /files, GET /files, DELETE /files, POST /files/editor], fields[products.file_upload_value jsonb (Record<string,any>), AttributeType.image/file/groupOfImages, value jsonb {filename, downloadLink, previewLink, defaultPreview}, ActionTypes (PERMISSIONS/FILES/IMAGE_RESIZE/FILE_REMOVE/FOLDERS/FOLDER_CREATE/FOLDER_REMOVE/FOLDER_RENAME/FILE_RENAME)], queues[BULL_QUEUES.files='files' + jobs delete/copy in FilesConsumer; BULL_QUEUES.preview='preview' + jobs refresh-previews/refresh-preview/attribute-set-preview in PreviewConsumer], ws[no direct channels in file-upload], fk[none — links via jsonb pointers to S3 URLs] -->

# 15. File upload: S3/Minio, previews, deletion, copying

## Purpose

Anything involving **binary files** in OneEntry — from a regular product image upload to a deferred image import from Excel. Scenarios:

- Admin uploads a news banner → `POST /files` through the block editor UI.
- Product deletion → product files (`files/project/product/<id>/`) follow, via the Bull `files` queue.
- Page duplication → files are copied into the new folder (the `copy` job).
- Editing a preview template → recalculate all linked previews via Bull `preview`.
- Excel import with a "cover as URL" column → the Python backend stores the URL in `products.file_upload_value jsonb`, and cms picks it up later.

**No dedicated entities.** Files live in S3/Minio (or locally when `S3_ENABLED=false`). Metadata sits inside jsonb fields of consumer entities: `attributes_sets`, `localize_infos.htmlContent` (for the editor), `products.file_upload_value`.

## Entities and dependency hierarchy

```
S3/Minio                            — external storage (or fs: files/project/<type>/<id>/ when S3_ENABLED=false)
  ↑ S3-key shaped like files/project/<type>/<id>/<filename>
attributes_sets (jsonb)            — { [lang]: { [marker]: { filename, downloadLink, previewLink?, defaultPreview? } } }
localize_infos.htmlContent         — embedded text with <img src="..."> pointing to an S3 link
products.file_upload_value (jsonb) — deferred import upload (see below)
template_previews.proportions      — describes preview formats (horizontal/vertical/square)
```

| Table | Base class | Connection to file-upload |
|---|---|---|
| `attributes_sets` | `BaseAbstractEntity` | Attribute values of type `image` / `file` / `groupOfImages` are stored on `schema` consumers |
| `products` | `BaseAttributeSetsAbstractEntity` | `file_upload_value jsonb` — deferred pipeline for imports (`product.entity.ts:177`) |
| `template_previews` | `BaseAbstractEntity` | `proportions jsonb` defines which previews to regenerate (see 11) |

**No FKs to S3.** The connection is jsonb pointers (`filename` ↔ S3 key), which lets the backend change (S3 → Minio → fs) without migrations.

## Related `AttributeType`s (file-flavored)

In the `attributes_sets.schema[k].type` schema, the valid "file" values come from `cms/src/modules/index-attributes-sets/types/attribute-types.enum.ts`:

| `AttributeType` | What it stores in jsonb |
|---|---|
| `image` | A single picture: `{ filename, downloadLink, previewLink?: {<marker>: [thumb, preview]}, defaultPreview?, size?, params? }` |
| `file` | A single file of arbitrary type: `{ filename, downloadLink, contentType, size? }` |
| `groupOfImages` | An array of `image` objects |

Additional special flags in `SchemaItem` (see `agents_datasets/ClaudeInfos/examples/10-extend-attribute-set.md`):
- `isProductPreview` — this attribute is used as the product card cover.
- `isIcon` — category/section icon.
- `isCompress: true` — `FileCompressorService` will compress the picture before upload.
- `previewTemplateId` — id of a `template_previews` (see 11) row: which proportions to regenerate.

## Full jsonb with data

### Product image (cover)

`products.attributes_sets`:

```json
{
  "en_US": {
    "cover": {
      "filename": "files/project/product/57/coffee-arabica-hero.jpg",
      "downloadLink": "https://s3.eu-west-1.amazonaws.com/oneentry-cms/files/project/product/57/coffee-arabica-hero.jpg",
      "previewLink": {
        "type_id3": ["https://.../57/coffee-arabica-hero_thumb.jpg", "https://.../57/coffee-arabica-hero_preview.jpg"]
      },
      "defaultPreview": "horizontal",
      "size": 184320,
      "params": { "width": 1920, "height": 1080 }
    }
  }
}
```

If multiple locales were present (e.g. `de_DE` alongside `en_US`), they would normally point to **the same file** (an image typically doesn't depend on language) — that's fine, the link is simply duplicated across locale keys in jsonb.

### Image group (gallery)

```json
{
  "en_US": {
    "gallery": [
      { "filename": "files/project/product/57/gallery-1.jpg", "downloadLink": "https://.../gallery-1.jpg" },
      { "filename": "files/project/product/57/gallery-2.jpg", "downloadLink": "https://.../gallery-2.jpg" },
      { "filename": "files/project/product/57/gallery-3.jpg", "downloadLink": "https://.../gallery-3.jpg" }
    ]
  }
}
```

### Certificate file

```json
{
  "en_US": {
    "certificate": {
      "filename": "files/project/product/57/certificate-iso-9001-en.pdf",
      "downloadLink": "https://.../certificate-iso-9001-en.pdf",
      "contentType": "application/pdf",
      "size": 524288
    }
  },
  "de_DE": {
    "certificate": {
      "filename": "files/project/product/57/certificate-iso-9001-de.pdf",
      "downloadLink": "https://.../certificate-iso-9001-de.pdf",
      "contentType": "application/pdf"
    }
  }
}
```

Here, unlike the image above, **locales point to different files** — because the document has translated versions.

### `products.file_upload_value` — deferred upload from import

When `import-backend` parses Excel with a `cover_url: 'https://supplier.com/img/p57.jpg'` column, it **doesn't download the file immediately**; it puts the URL into `products.file_upload_value`:

```json
{
  "cover": {
    "type": "image",
    "value": "https://supplier.com/img/p57.jpg",
    "filename": "p57.jpg",
    "status": "pending"
  },
  "gallery": {
    "type": "groupOfImages",
    "value": [
      "https://supplier.com/img/p57-1.jpg",
      "https://supplier.com/img/p57-2.jpg"
    ],
    "status": "pending"
  }
}
```

A separate cms worker (or a repeated import run) picks up `file_upload_value`, downloads from the URL, stores into S3 through `AdminS3StorageService`, and moves the result into `attributes_sets[lang][cover]`. See `cms/src/modules/products/entities/product.entity.ts:177-178`.

## Admin API (`@Controller('files')` + `@Controller('files/editor')`)

| Method | Path | Purpose |
|---|---|---|
| `POST` | `/files?...` | Upload file(s) (`multipart/form-data`, `AnyFilesInterceptor`) → `UploadResultDto[]` |
| `GET` | `/files?filename=...` | Download (`StreamableFile`) |
| `DELETE` | `/files?filename=...` | Remove a single file from S3 |
| `POST` | `/files/editor` | File manager: rename, create/remove folders, image resize |

`POST /files/editor` accepts a `FilesEditorDto` with the `action: ActionTypes` discriminator. Full action enum — `cms/src/modules/file-upload/types/action-types.ts`:

```ts
ActionTypes.PERMISSIONS    // fetch permissions on a path
ActionTypes.FILES          // list files inside a folder
ActionTypes.IMAGE_RESIZE   // resize a single image
ActionTypes.FILE_REMOVE    // delete a file
ActionTypes.FOLDERS        // list folders
ActionTypes.FOLDER_CREATE  // create a folder
ActionTypes.FOLDER_REMOVE  // delete a folder recursively
ActionTypes.FOLDER_RENAME  // rename a folder
ActionTypes.FILE_RENAME    // rename a file
```

```http
POST /files?type=product&id=57
Content-Type: multipart/form-data

files=@coffee-arabica-hero.jpg
```

Response:
```json
[
  {
    "filename": "files/project/product/57/coffee-arabica-hero.jpg",
    "downloadLink": "https://s3.../files/project/product/57/coffee-arabica-hero.jpg",
    "size": 184320
  }
]
```

Inside `AdminFileUploadController.uploadFiles`:
1. If `process.env.FILES_UPLOADING.ANTIVIRUS_ENABLED === 'true'` → `MalwareScannerService.scan(files)`.
2. `AdminS3StorageService.uploadFiles(uploadFilesDto, files)` — puts the file into the S3 bucket under `files/project/<type>/<id>/<filename>`.
3. Returns the `UploadResultDto` array.

## Behind the scenes

### Bull queue `files` (`BULL_QUEUES.files = 'files'`)

`FilesConsumer` (`cms/src/modules/file-upload/consumers/files.consumer.ts:41`) handles two job names:

| Job | What it does |
|---|---|
| `delete` | `{ ids: number[], type: 'page' \| 'product' \| ... }` — deletes the S3 folders `files/project/<type>/<id>/`. When `S3_ENABLED=false` — `deleteFolderRecursive` locally. |
| `copy` | `{ fromId, destId, type, data }` — copies S3 objects when an entity is duplicated. `data` is scanned with `findValuesByKey('filename')` to find every S3 link in the parent jsonb. |

**Producers** (`@InjectQueue(BULL_QUEUES.files)`):
- `AdminPagesService` (`admin-pages.service.ts:70`) — `delete` on page removal.
- `AdminProductsService` (`admin-products.service.ts:64`) — `delete` on product removal.
- `AdminAttributesSetsService` (`admin-attributes-sets.service.ts:31`) — `delete` when a file-typed attribute is removed.
- `AdminTemplatePreviewService` (`admin-template-preview.service.ts:24`).
- `AdminImportService` (`admin-import.service.ts:37`).

```ts
await this.filesQueue.add('delete', { ids: [productId], type: 'product' });
```

The queue is asynchronous: HTTP `DELETE /products/:id` returns 200 instantly, while files are cleaned up in the background. If S3 is unreachable, the job retries according to the Bull policy.

### Bull queue `preview` (`BULL_QUEUES.preview = 'preview'`)

`PreviewConsumer` (`cms/src/modules/file-upload/consumers/preview.consumer.ts:34`) handles three job names (see also 11):

| Job | What it does |
|---|---|
| `refresh-previews` | Regenerate **all** previews (a background periodic job). Iterates over every `template_previews` → calls `refresh-preview` for each one. |
| `refresh-preview` | `{ type: 'template', id }` — regenerate previews for a single `template_previews.id`. Walks every `attributes_sets` whose `schema[*].previewTemplateId === id` and re-crops the images. |
| `attribute-set-preview` | `{ set, update }` — after `PUT /attributes-sets/:id/schema`: if an attribute with `previewTemplateId` was added/removed, rewrites the related `previewLink` via `PreviewImageService.updatePreviewAndSetLinks`. |

**Triggers:** changes to `template_previews.proportions`, changes to `attributes_sets.schema[k].previewTemplateId`. Concretely, the `attribute-set-preview` job is enqueued from `AdminAttributesSetsService` during `updateSchema` when `previewTemplateId` changes.

### Services

- `AdminS3StorageService` — upload/delete/copy in S3 (AWS SDK). Provides `uploadFiles`, `deleteFile`, `copyObjects`, `deletePageFolder`.
- `ContentS3StorageService` — read-only service for the content app (storefront).
- `BaseS3StorageService` — shared base.
- `MalwareScannerService` — antivirus scanner (ClamAV or similar) when `FILES_UPLOADING.ANTIVIRUS_ENABLED=true`.
- `PreviewImageService` — `sharp`-based preview generator by proportions.
- `FileCompressorService` — compression when `schema[k].isCompress=true`.
- `FilesEditorService` — implementation of the actions from `POST /files/editor` (resize, rename, folder management).

### Local fallback (without S3)

When `S3_ENABLED=false` (typical in local-development), files are written straight to the filesystem under `files/project/<type>/<id>/<filename>` relative to the cms root. `deleteFolderRecursive` cleans up locally. This makes it possible to develop without bringing up Minio.

### Journal

**File uploads/deletions are not journaled** — that would DDoS `journal_records`. The operations of the **parent entities** are journaled (`PRODUCT_UPDATED`, `PAGE_DELETED`, etc.), which makes the audit log show "when did this product's cover change".

### Permissions

Access to `POST /files` is controlled through `AdminAuthGuard` + the permission of the entity the file is being uploaded to (i.e. the right to edit a product = the right to upload files to that product). There is no dedicated `files.upload` permission.

## Cross-references

- [01-catalog-product.md](./01-catalog-product.md) — product images.
- [02-content-page.md](./02-content-page.md) — page banners/covers + the `localize_infos.htmlContent` editor.
- [07-import-catalog.md](./07-import-catalog.md) — deferred image upload from import via `file_upload_value`.
- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — adding a file-typed attribute to a schema (`AttributeType.image/file/groupOfImages`).
- [11-templates-and-previews.md](./11-templates-and-previews.md) — preview template `proportions` + the `attribute-set-preview` job.
- [16-index-attributes-search.md](./16-index-attributes-search.md) — indexing of file-attribute values (`isProductPreview` ⇒ row in `index_attribute_data`).
- `agents_datasets/ClaudeInfos/patterns-queues-and-ws.md` — general Bull-queue pattern.

## Antipatterns

**"I'll stash the file straight into `localize_infos.htmlContent` as base64."** Don't:

1. The jsonb column turns into a multi-megabyte monster → every `SELECT * FROM products` slows down.
2. Postgres jsonb indexes stop being effective.
3. The CDN can't serve the file — only cms through the app can, which cuts throughput by an order of magnitude.
4. No antivirus scan, resize, or previews are possible.
5. Impossible to copy the file when duplicating an entity through the `copy` job — base64 would move along, but `findValuesByKey('filename')` would never find it.

The right approach:
1. `POST /files?type=page&id=12` → S3, response `{ filename, downloadLink }`.
2. Store **only the link** (`<img src="https://.../files/project/page/12/cover.jpg">`) in `localize_infos[lang].htmlContent`.
3. The Bull `delete` job on page removal automatically cleans the S3 folder.

**"I'll create an `uploaded_files (id, owner_type, owner_id, filename, url)` table."** Don't — the link between a file and its owner is already expressed by the **S3 key** (`files/project/<type>/<id>/...`). That table would duplicate information that already lives in the S3 layout. And on product deletion you would have to maintain cascading deletes in two places (jsonb + the table).
