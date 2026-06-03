<!-- audit: 5/5 (2026-05-13) endpoints[POST /modules, PUT /modules/:id, DELETE /modules/:id, POST /modules/create, POST /modules/:id/deploy, POST /modules/:id/suspend, POST /modules/:id/resume, GET /modules/:id/state, GET /modules/:id/logs, PUT /modules/:name/config], fields[modules.type (SYSTEM/CUSTOM), modules.config jsonb (Record<string,any>), modules.used_templates jsonb (number[], select:false), modules.task_id (uuid from the provisioner), modules.last_checked_status, modules.last_status_update_time, modules.status_transition (DEPLOYING/SUSPENDING/UNSUSPENDING/DELETING), modules.icon, modules.is_visible], queues[no dedicated Bull queues — deploy goes through the external cms_provisioner by task_id], ws[no direct channels in admin-modules; transition statuses are refreshed via cron polling of the provisioner], fk[module_general_types_mn M2M (module_id, general_type_id), module_attribute_set_types_mn M2M (module_id, attribute_set_type_id); FormModuleConfigEntity OneToMany (CASCADE)] -->

# 19. Third-party modules (CMS "plugins")

## Purpose

A "module" in OneEntry is an **admin panel section**: "Catalog", "Orders", "Users", "Subscriptions", "Menus", and so on. System modules (`type=SYSTEM`) are created by seed migrations and cannot be removed. Custom ones (`type=CUSTOM`) are uploaded through `POST /modules/create` (multipart), deployed by the external `cms_provisioner`, and can be suspended/resumed/deleted.

Scenarios:

- "Connect a CRM integration plugin" → upload the .zip via `POST /modules/create` → `taskId` from the provisioner → poll the status through `GET /modules/:id/state`.
- "Pause a plugin for debugging" → `POST /modules/:id/suspend` → `statusTransition='suspending'` → after the provisioner responds, the plugin container stops.
- "Bind the module to a new `general_type`" → `PUT /modules/:name/config` updates `module_general_types_mn`.
- "Hide a module from the admin menu without deleting it" → `PUT /modules/:id/change-visibility`.

## Entities and dependency hierarchy

```
general_types                       — types of content entities (catalog_page, common_page, ...)
attribute_set_types                 — attribute set types (forProducts, forPages, ...)
forms                               — forms the module can use

modules                             — module (admin section)
                                      type: SYSTEM | CUSTOM
                                      config jsonb, used_templates jsonb (number[])
                                      task_id (uuid from the provisioner), status_transition

module_general_types_mn             — M2M: module ↔ general_type
module_attribute_set_types_mn       — M2M: module ↔ attribute_set_type
form_module_config                  — config of a specific form for a specific module (CASCADE)
```

| Table | Base class | Key fields |
|---|---|---|
| `modules` | `BaseAbstractEntity` | `identifier`, `is_visible`, `type` (enum), `localize_infos`, `icon`, `config jsonb`, `used_templates jsonb` (`select:false`), `task_id`, `last_checked_status`, `last_status_update_time`, `status_transition` (enum) |
| `module_general_types_mn` | M2M | `(module_id, general_type_id)` |
| `module_attribute_set_types_mn` | M2M | `(module_id, attribute_set_type_id)` |
| `form_module_config` | OneToMany | `module_id` (CASCADE), form configuration inside the module |

### `ModuleType` (`cms/src/modules/modules/types/module-type.enum.ts`)

```ts
ModuleType.SYSTEM = 'system'   // out of the box, via seed (id=1..N)
ModuleType.CUSTOM = 'custom'   // uploaded plugin via POST /modules/create
```

### `StatusTransition` (`cms/src/modules/modules/types/status-transition.enum.ts`)

```ts
StatusTransition.DEPLOYING    = 'deploying'      // container deploy via the provisioner
StatusTransition.SUSPENDING   = 'suspending'     // container suspension
StatusTransition.UNSUSPENDING = 'unsuspending'   // resume
StatusTransition.DELETING     = 'deleting'       // container deletion
```

This is a **UI indicator** for long-running operations: while the module hasn't reached idle (`transition=null`), the frontend shows a spinner "module is being processed".

## Related `general_types` and `attribute_sets`

The module **does NOT extend `BaseAttributeSetsAbstractEntity`** — a module has no customizable attributes through an `attribute_set`. Localization is limited to `localize_infos.title` for the admin menu item.

But the module is **M2M-linked** with `general_types` and `attribute_set_types`: "this module serves pages of type `catalog_page` and attribute sets of type `forProducts`".

## Full jsonb with data

### `modules` (system "Catalog" module)

```json
{
  "id": 1,
  "identifier": "catalog",
  "type": "system",
  "isVisible": true,
  "localizeInfos": {
    "en_US": { "title": "Catalog" }
  },
  "icon": "mdi mdi-package-variant",
  "config": {
    "rowsPerPage": 50,
    "productsPerRow": 4,
    "defaultSortBy": "createdDate",
    "defaultSortOrder": "DESC"
  },
  "taskId": null,
  "lastCheckedStatus": null,
  "lastStatusUpdateTime": null,
  "statusTransition": null,
  "positionId": 12
}
```

`used_templates` is not shown (`select:false` — not returned in the general `GET /modules`, only in `GET /modules/:name` via an explicit `addSelect`).

### `modules` (custom CRM integration module mid-deploy)

```json
{
  "id": 47,
  "identifier": "amocrm-integration",
  "type": "custom",
  "isVisible": false,
  "localizeInfos": {
    "en_US": { "title": "amoCRM Integration" }
  },
  "icon": "mdi mdi-account-network",
  "config": {
    "apiUrl": "https://example.amocrm.com/api/v4/",
    "syncIntervalMinutes": 15,
    "pipelineId": 7732461,
    "leadStatusMap": {
      "new_order": 142823,
      "paid": 142824,
      "shipped": 142825
    }
  },
  "usedTemplates": [],
  "taskId": "62c1b917-8956-4832-a241-c45ed1ba8921",
  "lastCheckedStatus": "Deploying",
  "lastStatusUpdateTime": "2026-05-13T10:23:41.000Z",
  "statusTransition": "deploying",
  "positionId": 47
}
```

### `modules` (system "Subscriptions" module created by seed)

From `cms/src/seeds/1870795700001-seed-subscriptions.ts`:

```json
{
  "id": 17,
  "identifier": "subscriptions",
  "type": "system",
  "isVisible": true,
  "localizeInfos": {
    "en_US": { "title": "Subscriptions" }
  },
  "icon": "i-subscriptions",
  "config": {},
  "usedTemplates": []
}
```

### `module_general_types_mn` (M2M rows)

```json
[
  { "moduleId": 1, "generalTypeId": 2 },
  { "moduleId": 1, "generalTypeId": 4 },
  { "moduleId": 17, "generalTypeId": null }
]
```

The catalog module serves `general_types.id=2,4` (`catalog_page`, `product`). Subscriptions are not bound to any specific general_type (they are a dedicated entity).

### `modules.config` — arbitrary jsonb

A free-form `Record<string, any>` — each module defines its own shape. Examples:

- **Catalog:** `{ rowsPerPage, productsPerRow, defaultSortBy, defaultSortOrder }`.
- **Orders:** `{ defaultStorageId, autoCloseAfterDays, lowStockThreshold }`.
- **Forms:** `{ captchaProvider, captchaSiteKey, maxAttachmentSizeMb }`.
- **CRM plugin:** `{ apiUrl, syncIntervalMinutes, pipelineId, leadStatusMap }`.

This is the place for **UI/behavior settings of the module** — NOT for credentials (see the antipattern).

## Admin API (`@Controller('modules')`)

### CRUD

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/modules` | — | List of all modules |
| `GET` | `/modules/:name` | — | Get by `identifier` |
| `GET` | `/modules/types` | — | List of `ModuleType` |
| `GET` | `/modules/:id/user-permissions` | — | List of the module's permissions for the current user |
| `POST` | `/modules` | `settings.modules.create` | Create a module |
| `PUT` | `/modules/:id` | `settings.modules.update` | Update (`localizeInfos`, `icon`, `isVisible`, bindings) |
| `PUT` | `/modules/:name/config` | `settings.modules.update` | Update ONLY the `config jsonb` |
| `DELETE` | `/modules/:id` | `settings.modules.delete` | Delete (for custom — via the provisioner) |
| `PUT` | `/modules/:id/change-visibility` | `settings.modules.switching` | Show/hide in the menu |
| `PUT` | `/modules/:id/position` | `settings.modules.changePositions` | Order in the menu |
| `GET` | `/modules/marker-validation/:marker` | — | `identifier` uniqueness |

### Custom modules (deploy/suspend)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/modules/create` | `settings.modules.upload` | Upload a plugin .zip (multipart). Creates `modules.type='custom'` + sets `taskId` |
| `POST` | `/modules/:id/deploy` | `settings.modules.update` | Deploy the plugin container. `statusTransition='deploying'` until completion |
| `POST` | `/modules/:id/suspend` | `settings.modules.update` | Suspend (container stopped, data preserved). `statusTransition='suspending'` |
| `POST` | `/modules/:id/resume` | `settings.modules.update` | Resume from suspension. `statusTransition='unsuspending'` |
| `GET` | `/modules/:id/state` | — | Poll the provisioner by `taskId`, refresh `last_checked_status` |
| `GET` | `/modules/:id/logs?...` | — | Plugin container logs (proxied through the provisioner) |

```http
POST /modules/create
Content-Type: multipart/form-data

file=@amocrm-integration-v1.2.3.zip
identifier=amocrm-integration
```

After the upload:
1. A `modules` row is created with `type='custom'`, `isVisible=false`.
2. `task_id` ← UUID from the provisioner.
3. `statusTransition='deploying'`.
4. The frontend periodically calls `GET /modules/47/state` → `last_checked_status` / `last_status_update_time` get refreshed.
5. When the deploy completes → `statusTransition` is reset to null, `isVisible=true`.

## Behind the scenes

### Cms_provisioner — external service

This repo **has no** Bull queues or WS channels for modules. Long-running operations are delegated to the external `cms_provisioner` service (a separate repo in the monorepo, see the root `CLAUDE.md`).

The cms ↔ provisioner link:
- cms sends a command (deploy / suspend / resume / delete) → receives a `taskId`.
- The provisioner handles it asynchronously and updates the container status.
- cms polls `GET /modules/:id/state` (triggered from the admin frontend) → reads the status by `taskId` from the provisioner → updates `last_checked_status` and `last_status_update_time`.

### `usedTemplates` and `select:false`

`modules.used_templates` (`jsonb number[]`) lists the ids of templates (see [11-templates-and-previews.md](./11-templates-and-previews.md)) used by this module. The field is marked `select:false` — NOT returned in the regular `GET /modules` (to keep the response small), only on explicit request through `addSelect('module.usedTemplates')`.

It is used so that in the template admin UI you can show "this template is used by module X" (preventing template deletion if a module needs it).

### Form binding (`FormModuleConfigEntity`)

`form_module_config` is the config of a specific form for a specific module. It links to `modules` through `OneToMany(... { onDelete: 'CASCADE', cascade: true })` — deleting a module cascades and removes all its form bindings.

Used when a module (for example, "Submissions") provides forms of a specific kind: which fields, in which order, which validations apply.

### Seeds for system modules

System modules are created by seed migrations. Example from `cms/src/seeds/1870795700001-seed-subscriptions.ts`:

```sql
INSERT INTO modules (
  id, "localize_infos", identifier,
  "is_visible", "is_active", type,
  icon, "used_templates"
) VALUES (
  17,
  '{"en_US":{"title":"Subscriptions"}}',
  'subscriptions',
  true, true, 'system',
  'i-subscriptions',
  DEFAULT
)
```

The seed also adds permissions to `admin_permissions` for the new module (`subscriptions.create`, `.update`, `.delete`).

### Journal

`JournalingEvents.MODULE_*` (if present in `journaling-events.ts`) write to the `journal_records` audit log. Before adding a new module to production, it's worth adding event names to the enum.

### Permissions

`settings.modules.{create, update, delete, switching, changePositions, upload}` in `AdminPermissionsEnum`.

## Cross-references

- [02-content-page.md](./02-content-page.md) — `general_types` (catalog_page / common_page / blog / vacancy) are bound to a module through `module_general_types_mn`.
- [03-form-submission.md](./03-form-submission.md) — `FormModuleConfigEntity` connects a form to a module.
- [06-event-notification.md](./06-event-notification.md) — `events.module_id` → the module defines which triggers are available (for example, the `products` module has the `change-product-attribute` trigger).
- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — `attribute_set_types` (forProducts, forPages, ...) are bound to a module through `module_attribute_set_types_mn`.
- [11-templates-and-previews.md](./11-templates-and-previews.md) — `modules.used_templates jsonb` points to `templates.id`.
- [17-subscriptions-billing.md](./17-subscriptions-billing.md) — `modules.id=17` (`identifier='subscriptions'`) is created by the seed.
- `cms_provisioner/` (root `CLAUDE.md`) — the external service for deploying CUSTOM modules.

## Antipatterns

**"To add a new 'Couriers' admin section, I'll create a `couriers` table + a `couriers.controller.ts` controller without a module."** Don't:

1. Without a record in `modules` there are no permissions — `AdminAuthGuard` lets nobody through, no admin sees the section in the menu.
2. Without `module_general_types_mn` you can't link to `general_types` (e.g. courier pages).
3. Journaling and cross-links in the admin panel are all tied to `module_id` on `events`, `journal_records`, `attribute_sets`. Without a module the section becomes an "island".

The right approach: create a seed migration like `1900000000000-seed-couriers.ts`:
1. `INSERT INTO modules (identifier, type, localize_infos, icon, ...) VALUES ('couriers', 'system', ...)`.
2. `INSERT INTO admin_permissions (...) VALUES (...)` for `couriers.create/update/delete`.
3. (Optional) M2M `module_general_types_mn` with `general_types.id=...`.

**"I'll store an amoCRM secret token in `modules.config.token`."** Don't:

1. `config jsonb` is returned by `GET /modules/:name` to any authenticated admin without special masking.
2. The `settings.modules.update` permission is broader than `settings.payments.accounts.update` — more people have access to credentials.
3. The history of `config` changes through the journal makes the leak visible.

The right approach: provider credentials belong in `payment_accounts.settings` (masked, see [12](./12-payments-and-refunds.md)) or in a dedicated encrypted table. `modules.config` should contain **only UI/behavior settings** (sync interval, defaults, mapping).

**"I'll upload the plugin .zip straight to S3 and run it as a Node.js child process."** Don't:

1. Security: foreign code in the cms process context is a path to a compromised system.
2. Resource isolation — a child process shares memory/CPU with cms.
3. Plugin logs and metrics are not isolated from cms.

The right approach: `cms_provisioner` deploys the plugin into a **separate container** with its own network environment and resource limits. cms only talks to it through an API. See also `CLAUDE.md` (repo root) section "Active repos".
