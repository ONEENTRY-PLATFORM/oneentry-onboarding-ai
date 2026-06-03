# Pattern: splitting controllers by audience

In `cms/` every module with a public surface is split into several controllers per audience. This isn't cosmetics — it means different guards, different DTOs, different services.

---

## 1. Audiences and file prefixes

For a module `X` the typical trio (plus variants) is:

| File prefix | Audience | Purpose |
|---|---|---|
| `admin-X.controller.ts` | OneEntry admin panel | CRUD for administrators, protected by `AdminAuthGuard` + `@GrantByPermission(...)` |
| `developer-X.controller.ts` | Developer API (external integrators) | Extended API for module developers |
| `content-X.controller.ts` | End clients (storefront / public) | Read-only public API, more restricted |
| `base-X.controller.ts` | Shared parent | Often an abstract class that admin/content/developer extend (but it sometimes shows up as a standalone controller in the code as well) |
| `X.controller.ts` without a prefix | Module-only | Not tied to an audience (e.g. `general-types.controller.ts`, `index-attribute.controller.ts`, `journal.controller.ts`, `auth.controller.ts`, `settings.controller.ts`) |

The HTTP path prefix inside each group is the same (e.g. all three variants of `blocks.controller.ts` declare `@Controller('blocks')`), and the **global prefix** `/api/admin` / `/api/content` / `/api/developer` is set via `app.setGlobalPrefix(API_TYPE)` in `cms/src/main.ts:105` and `:118`, depending on the env variables `API_TYPE` and `API_DEVELOPER_TYPE`. Values are in the `ApiTypes` enum (`cms/src/shared/types/api-types.ts`): `ADMIN = '/api/admin'`, `CONTENT = '/api/content'`. The developer prefix comes from env as the string `/api/developer`.

In other words, **the same class** `@Controller('blocks')` will sit on different URLs depending on which root app module (`AdminAppModule` / `ContentAppModule` / `DeveloperAppModule`) it is registered in.

### Root module summary

| Root | File | API |
|---|---|---|
| `AdminAppModule` | `cms/src/admin.app.module.ts` | `/api/admin/*` |
| `ContentAppModule` | `cms/src/content.app.module.ts` | `/api/content/*` |
| `DeveloperAppModule` | `cms/src/developer.app.module.ts` | `/api/developer/*` |
| `BaseAppModule` | `cms/src/base.app.module.ts` | Shared, imported by the others |

In main.ts a single process can run admin + developer at the same time (two NestApplications on different ports), or one of admin/content depending on the `API_TYPE` env.

---

## 2. Protection: AdminAuthGuard + @GrantByPermission

### `AdminAuthGuard`

File: `cms/src/modules/admins/services/admin-auth.guard.ts`.

What it does:
1. If the request header has `x-internal-request: true` — passes through (for internal inter-service calls).
2. Extracts `Authorization: Bearer <token>` via `extractAccessTokenFromHeader`.
3. Verifies the JWT with the `JWT_SECRET`.
4. Finds the session: `findOne(AdminSessionEntity, { userId: payload.id, accessToken: token })`.
5. Checks `expiredDate`.
6. Puts the payload in `request['user']`.

### `@GrantByPermission`

File: `cms/src/modules/auth/decorators/grant-by-permission.decorator.ts`.

```ts
export const GrantByPermission = (permission: keyof ActionPermissions) =>
  applyDecorators(UseGuards(AdminAuthGuard, PermissionGuard(permission)));
```

A composite decorator: applies both `AdminAuthGuard` and `PermissionGuard(permission)` at once. Usage:

```ts
@Post()
@GrantByPermission(AdminPermissionsEnum['blocks.create'])
async createBlock(...) {}
```

### `PermissionGuard`

File: `cms/src/modules/auth/guards/permission.guard.ts`.

A mixin function: builds a `PermissionGuardMixin` that, for a concrete `permission`, takes `request.user.id`, runs `SELECT permissions FROM admins WHERE id = $1` and checks `permissions?.[permission]`. So permissions live in `admins.permissions jsonb` (see `AdminEntity.permissions`).

---

## 3. AdminPermissionsEnum — full list

File: `cms/src/modules/admins/types/admin-permissions-enum.ts`. The complete current list (grouped as in the enum):

- **Menu:** `menu.create / update / delete / items.add / items.remove / items.changePositions`
- **Settings / System (modules):** `settings.modules.create / update / switching / delete / changePositions / upload`
- **Settings / Attribute sets:** `settings.attributesSets.create / update / delete / switching / changePositions`; `settings.attributes.create / update / delete / changePositions`
- **Settings / Templates:** `settings.templates.create / update / delete / changePositions`; `settings.templatePreview.create / update / delete / changePositions`
- **Settings / Certificates:** `settings.certs.create / download / delete`
- **Settings / Tokens:** `settings.tokens.create / delete`
- **Settings / Locales:** `settings.locales.create / update / delete / switching / changePositions`
- **Settings / General:** `settings.general.update`
- **Admins:** `admins.create / update / updatePermissions / modules / delete / get / changePositions / totalLogout`
- **Forms:** `forms.create / update / delete / data.delete / data.update`
- **Blocks:** `blocks.create / update / delete`
- **Markers:** `markers.create / update / delete`
- **Pages:** `pages.create / update / updateBlockAndForms / delete / settings.update / copy / errorStatus.create / errorStatus.delete / changePositions / forms.changePositions / blocks.changePositions / blocks.nested.changePositions / switching / move`
- **Catalog (products):** `catalog.products.create / update / delete / switching / copy / deleteMany / updateCategories / lockPositions / changePositions / outputSettings / filterSearch / editStatus / setTemplate / createRelationTemplate / updateRelationTemplate / deleteRelationTemplate / blocks.changePositions`; `catalog.status.update / delete / create / changePositions`
- **Users (non-admin):** `users.get / create / update / delete`
- **Auth providers:** `usersAuthProvider.create / update / delete`
- **User groups:** `userGroups.get / create / update / delete`
- **Non-admin user permissions:** `userPermissions.create / update / delete`
- **Events:** `events.get / create / update / delete / setupFirebase / emailSettings`
- **Orders:** `orders.storage.create / update / delete / order.update / order.delete / order-status.create / order-status.update / order-status.delete / order-status.changePositions`
- **Payments:** `payments.settings.get / update / accounts.get / create / update / delete / refunds`
- **Workflows:** `workflows.get / update`
- **Collections:** `collections.collection.get / create / update / delete / row.get / create / update / delete`
- **Export:** `export.users / orders / payments`
- **Discounts:** `discounts.create / update / delete / updatePriority`
- **Import:** `import.data / data.createTemplate / data.deleteTemplate`
- **Subscriptions:** `subscriptions.create / update / delete`

At the end of the file there is a comment with a bundle of "currently unneeded or unused" permissions (`settings.previews.*`, `statistics.*`, `news.*`, `settings.anchorPoints.*`, `settings.languages.*`, `settings.email`, `catalog.feedback.reply`, duplicates of `users.*` and `orders.*`). These are **not used in code** — if you need them, add them back into the enum.

### `ActionPermissions`

File: `cms/src/modules/admins/types/action-permissions.ts` — the type `Record<keyof AdminPermissionsEnum, boolean>`. Stored in the `admins.permissions jsonb` column (`AdminEntity.permissions: ActionPermissions`).

---

## 4. Rules for AI

### 4.1. "Admin-only" task

If the task is "add a button to the OneEntry admin panel for copying a product":
- Touch **only** `admin-X.controller.ts` and the corresponding `AdminXService`.
- Do NOT touch `developer-X.controller.ts`, `content-X.controller.ts`, `base-X.controller.ts`, even if they sit next to it — they serve other audiences.
- Protect every new endpoint with `@GrantByPermission(AdminPermissionsEnum[...])`. If no value fits — add one to `admin-permissions-enum.ts` and seed it in the style of `1689082120053-init-db.ts` for default admin permissions (or as a separate seed — see the existing ones in `cms/src/seeds/`).

### 4.2. "Public read-only endpoint" task

- Use only `content-X.controller.ts`. Do not use `AdminAuthGuard`. End-user authentication goes through `ContentSocketGateway`-style validation of `UsersAuthProviderEntity` + `UserSessionEntity` (see `cms/src/modules/socket/content-socket.gateway.ts:33-83` as a reference).

### 4.3. "API extension for integrators" task

- Use `developer-X.controller.ts`. Often this is a "looser" endpoint without AdminAuthGuard, authenticated by `app-tokens` (`AppTokenEntity`) or by a developer-side `JWT_SECRET`.
- Don't duplicate admin/content logic — push the common parts to `BaseXService` and inherit.

### 4.4. Don't mix audiences

If you add an endpoint in `admin-blocks.controller.ts` — it will **not** automatically appear at `/api/content/blocks`. And vice versa: anything added in `content-blocks.controller.ts` is not protected by `AdminAuthGuard`. If a feature should be available both to admins and to public clients — you need **two endpoints**.

### 4.5. Internal request from another microservice

If a service (e.g. `import-backend`) calls the CMS from inside the VPC — it sends the header `x-internal-request: true`. Both `AdminAuthGuard` and `PermissionGuard` pass it through without checks (see `admin-auth.guard.ts:22-24` and `permission.guard.ts:11-13`). Do not use this header on the public surface.

---

## 5. Example (admin-blocks.controller.ts)

```ts
@Controller('blocks')
export class AdminBlocksController extends ContentBlocksController {
  ...

  @Post()
  @GrantByPermission(AdminPermissionsEnum['blocks.create'])
  @Journalable(JournalingEvents.BLOCK_CREATED)
  @ApiOperation({ summary: 'Create a block' })
  async createBlock(@Body() dto: CreateBlockDto) { ... }
}
```

You can see three of the four "standard" decorators for an admin method here:
- `@GrantByPermission(...)` — auth + permissions.
- `@Journalable(JournalingEvents.BLOCK_CREATED)` — journaling (see [`patterns-journal-blockers-versioning.md`](./patterns-journal-blockers-versioning.md)).
- `@ApiOperation / @ApiResponse / @ApiBody` — Swagger.

The fourth part — a DTO with `class-validator` (`@IsString()`, `@IsOptional()`, etc.).

### When the controller inherits

`AdminBlocksController extends ContentBlocksController` — a typical pattern: the admin variant has `super.findAll(...)` for read-only methods, plus its own write methods. So GET endpoints can live in the `content-*` parent, and `admin-*` only adds POST/PUT/DELETE with permissions.

---

## Related documents

- [`patterns-journal-blockers-versioning.md`](./patterns-journal-blockers-versioning.md) — about `@Journalable`.
- [`patterns-queues-and-ws.md`](./patterns-queues-and-ws.md) — about WebSocket channels.
- [`modules-catalog.md`](./modules-catalog.md) — which module registers which controllers.
