<!-- audit: 5/5 (2026-05-22) endpoints[PUT /users/:id, POST /users/search, POST /user-groups, PUT /user-groups/:groupId/permissions/:permissionId/change], fields[users.attribute_set_id, users.attributes_sets, user_groups.parent_id, user_groups_mn.user_id/group_id], queues[index-data via IndexTableType.USER_GROUPS, change-user-attribute consumer], ws[socketService.sendMessage 'userGroup' 'create'], fk[user_groups_mn.user_id->users.id CASCADE, user_groups_mn.group_id->user_groups.id CASCADE, user_group_permission_mn] -->

# 08. Users, groups, permissions

## Purpose

Any OneEntry project that has a "personal account" / B2B accounts / customers with different rights:
- **End users** (`users`) — those logged into the storefront / mobile app / personal account.
- **Groups** (`user_groups`) — VIPs, wholesalers, employees, guests, by city/region. Hierarchy via `parent_id`.
- **End-user permissions** (`user_permissions`) — who has access to which `/content/*` section. **Don't confuse with `admins` / `AdminPermissionsEnum`** — those are different rights systems.

If the task is "make admin roles" — this is **not** the right place; that's `admins` + `AdminPermissionsEnum`. If the task is "wholesalers see a special price list" — this is the place, via `user_groups` + `user_permissions` + (opt.) group `attribute_set`.

## Entities and dependency hierarchy

```
user_permissions   — dictionary: one permission = one section/path + rules
                       ↑ permission_id
user_group_permission_mn   — M:N groups↔permissions
                       ↓ group_id
user_groups        — user groups with hierarchy (parent_id)
                       ↑ group_id
user_groups_mn     — M:N users↔groups (CASCADE on both sides)
                       ↓ user_id
users              — end users + form_data + attribute_set
                       ↑ user_id (FK CASCADE)
cart_items / wishlist_items   — normalized cart/wishlist (see examples/18)
```

| Table | Base class | Key fields |
|---|---|---|
| `users` | `BaseAbstractEntity` (with manually added `attribute_set_id`) | `password_hash`, `is_active`, `is_deleted`, `auth_provider_id`, `form_data` (jsonb), `state` (jsonb), `notification_data` (jsonb), `locale`, `import_id`, `rating` (jsonb), `attributes_sets`, `deleted_at` |
| `user_groups` | `BaseAttributeSetsAbstractEntity` (full `attribute_set`) | `parent_id`, `localize_infos`, `is_visible`, `depth`, `attribute_set_id`, `attributes_sets` |
| `user_groups_mn` | `BaseEntity` | `user_id`, `group_id`, unique pair |
| `user_permissions` | `BaseEntity` | `localize_infos`, `section` (enum `APISectionTypeEnum`), `path`, `rules` (json — `permissions` + `additionalData`) |
| `user_group_permission_mn` | `BaseEntity` | `group_id`, `permission_id`, CASCADE |

FK (`@JoinColumn` confirmed):
- `user_groups_mn.user_id -> users.id` (CASCADE)
- `user_groups_mn.group_id -> user_groups.id` (CASCADE)
- `user_group_permission_mn.group_id -> user_groups.id` (CASCADE)
- `user_group_permission_mn.permission_id -> user_permissions.id` (CASCADE)
- `users.auth_provider_id -> users_auth_providers.id`

Creation order on a clean DB:
1. `user_permissions` are created via seed (factory permissions for sections `pages`, `products`, `forms`, `orders`, ...).
2. `user_groups` is created (at minimum `Guest` — `GUEST_USER_GROUP_ID = 1`).
3. Permissions are attached to groups via `PUT /user-groups/:groupId/permissions/:permissionId/change`.
4. User registration via `/auth/sign-up` (see `users-auth-providers`) — they automatically land in the guest group.
5. Admin via `PUT /users/:id` changes their `groupIds`, `notificationData`, `formData`, etc.

## Related `general_types` and `attribute_sets`

- **`AttributesSetType.forUsers`** — user attributes (e.g., `birthDate`, `loyalty_level`, `avatar`, `vat_number`).
- **`AttributesSetType.forUserGroups`** — group attributes (e.g., `discount_percent` of the "Wholesalers" group, `delivery_zone` of the "Moscow" group).

> Cart and wishlist used to live inside `users.system_attributes_sets` (per-language jsonb). After the 2026-05-22 refactor they moved to dedicated normalized tables `cart_items` / `wishlist_items` (FK CASCADE on `users.id` and `products.id`, `UNIQUE(user_id, product_id)`, language-agnostic). The end user manages them through content endpoints under `/users/me/cart` and `/users/me/wishlist`. **Admin / developer API have no endpoints for cart/wishlist** — these are user-state, not admin-state. See [examples/18](./18-user-activity-cart-wishlist.md).

## Full jsonb with data

### User — B2B customer

```json
{
  "id": 42,
  "identifier": "ivanov",
  "isActive": true,
  "isDeleted": false,
  "authProviderId": 1,
  "locale": "en_US",
  "formData": {
    "en_US": [
      { "marker": "login",    "type": "string", "value": "ivanov" },
      { "marker": "f-name",   "type": "string", "value": "John" },
      { "marker": "l-name",   "type": "string", "value": "Doe" },
      { "marker": "password", "type": "string", "value": "<hashed>" }
    ]
  },
  "notificationData": {
    "email": "john@example.com",
    "phonePush": ["fcm-token-android-1"],
    "phoneSMS": "+1 415 000-0000"
  },
  "state": { "lastViewedProductId": 1234, "onboarding": "done" },
  "rating": { "value": 4.5, "like": 10, "dislike": 2, "method": "average" },
  "attributeSetId": 26,
  "attributesSets": {
    "en_US": {
      "birth_date": {
        "fullDate": "1990-03-15T00:00:00.000Z",
        "formattedValue": "15-03-1990",
        "formatString": "DD-MM-YYYY"
      },
      "avatar": {
        "filename": "files/project/users/42/avatar.png",
        "downloadLink": "https://cdn.example/cloud-static/files/project/users/42/avatar.png",
        "previewLink": "https://cdn.example/cloud-static/files/project/users/42/avatar-preview.png",
        "size": 18402,
        "params": { "isImageCompressed": true },
        "contentType": "image/png"
      },
      "loyalty_level": { "title": "Silver", "value": "silver", "extended": { "type": "string", "value": "silver" } },
      "vat_number": "7701234567",
      "consent_marketing": true
    }
  }
}
```

Cart / wishlist are stored separately — see [examples/18](./18-user-activity-cart-wishlist.md).

### Group "Wholesalers"

```json
{
  "id": 5,
  "identifier": "wholesale",
  "parentId": null,
  "depth": 0,
  "isVisible": true,
  "showChildren": true,
  "localizeInfos": {
    "en_US": { "title": "Wholesale" }
  },
  "attributeSetId": 17,
  "attributesSets": {
    "en_US": {
      "discount_percent": 12,
      "min_order_amount": 50000,
      "personal_manager": "Jane Smith",
      "is_post_payment_allowed": true
    }
  }
}
```

### End-user permission

```json
{
  "id": 12,
  "section": "products",
  "path": "/content/products",
  "localizeInfos": { "en_US": { "title": "Products catalog" } },
  "rules": {
    "permissions": {
      "readAllRule": 1,
      "readRestrictionRule": 0,
      "readNestedRule": 1,
      "addRule": 0,
      "changeRule": 0,
      "deleteRule": 0
    },
    "additionalData": {
      "blocks": { "identifiers": [], "isExclude": false, "isInclude": false }
    }
  }
}
```

## Admin API

### Users (`@Controller('users')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/users` | `users.get` | Paginated list |
| `GET` | `/users/:id` | `users.get` | Single user |
| `PUT` | `/users/:id` | `users.update` | Update (`UpdateFromAdminUserDto`) — `isActive`, `isArchived`, `authProviderId`, `notificationData`, `groups` |
| `DELETE` | `/users/:id` | `users.delete` | Soft delete (`deleted_at`) |
| `POST` | `/users/search` | — | Advanced search with `stateFilters` + `identifiers` (logins) |
| `POST` | `/users/check-login-existence` | — | Does the login exist |
| `POST` | `/users/all` | — | Filtered list |
| `GET` | `/users/actions` | — | User action history (`user_actions`) |

```http
PUT /users/42

{
  "isActive": true,
  "isArchived": false,
  "authProviderId": 1,
  "notificationData": { "email": "john@example.com", "phonePush": [], "phoneSMS": "+14150000000" },
  "groups": [1, 5]
}
```

`@Journalable(USER_UPDATED)`. The `groups` type — `number[]` (field `groupIds` in the Swagger doc, but in the DTO it's `groups`).

### Groups (`@Controller('user-groups')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/user-groups` | `userGroups.create` | Create |
| `PUT` | `/user-groups/:id` | `userGroups.update` | Update |
| `DELETE` | `/user-groups/:id` | `userGroups.delete` | Delete |
| `PUT` | `/user-groups/:id/change-visibility` | `userGroups.update` | Toggle `is_visible` |
| `GET` | `/user-groups/root` | — | All top-level groups |
| `GET` | `/user-groups/:id/children` | — | Child groups |
| `GET` | `/user-groups/:id/permissions` | — | What permissions a group has |
| `POST` | `/user-groups/find-permissions` | — | Aggregated permission list for an array of `groupIds` |
| `PUT` | `/user-groups/:groupId/permissions/:permissionId/change` | `userPermissions.update` | **Toggle** a permission's binding to the group |

```http
POST /user-groups

{
  "identifier": "wholesale",
  "parentId": null,
  "version": 0,
  "localizeInfos": {
    "en_US": { "title": "Wholesale" }
  }
}
```

On group creation the code calls `socketService.sendMessage(payload, 'userGroup', 'create')` (WS event for the admin frontend) and pushes a job to the `index-data` queue (`tableName: IndexTableType.USER_GROUPS`) — this re-indexes group attribute values for filtering (see `agents_datasets/ClaudeInfos/patterns-queues-and-ws.md`).

### Permissions (`@Controller('user-permissions')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/user-permissions` | `userPermissions.create` | Create |
| `PUT` | `/user-permissions/:id` | `userPermissions.update` | Update |
| `DELETE` | `/user-permissions/:id` | `userPermissions.delete` | Delete |

Normally the admin doesn't create new `user_permissions` — they are seeded on first start. The admin's job is to attach existing permissions to groups (see `PUT /:groupId/permissions/:permissionId/change` above).

## Behind the scenes

- **Bull queue `index-data`** — after `POST /user-groups` a job `'index'` is queued with `{ deletion: false, aId: null, tableName: USER_GROUPS }` (see `admin-user-groups.controller.ts:441`). This rebuilds the group attribute value index — needed for attribute filtering in `GET /user-groups`.
- **Bull consumer `change-user-attribute`** — reacts to schema changes of `attribute_set` (type `forUsers`). When the admin adds a new field to the users' set via [10-extend-attribute-set.md](./10-extend-attribute-set.md) — this consumer recalculates values for all `users` with the matching `attribute_set_id`.
- **WebSocket channel `userGroup` / event `create`** — `AdminSocketGateway.sendMessage` sends the frontend a `{status, payload}` payload to refresh the group list in open tabs.
- **Journal** — `USER_CREATED, USER_ACTIVATED, USER_UPDATED, USER_DELETED, USER_PASSWORD_CHANGED, USER_GROUP_CREATED, USER_GROUP_UPDATED, USER_GROUP_DELETED, USER_PERMISSION_*, USER_AUTH_PROVIDER_*`.
- **`GUEST_USER_GROUP_ID = 1`** — constant in `cms/src/config/constants.ts`. Any freshly registered or unauthenticated guest belongs to this group. Checked in `AuthGuard` for content endpoints.
- **Cart / wishlist** are NOT edited via the admin API. There are no `admin-cart.controller.ts` / `admin-wishlist.controller.ts`. Cart and wishlist rows live in `cart_items` / `wishlist_items` and are managed exclusively by content endpoints `/users/me/cart` and `/users/me/wishlist` (end-user case, not admin). See [examples/18](./18-user-activity-cart-wishlist.md).

## Links to other files

- [10-extend-attribute-set.md](./10-extend-attribute-set.md) — how to extend `forUsers` / `forUserGroups` attributes. A schema change recalculates values for all `users` via the `change-user-attribute` job.
- [03-form-submission.md](./03-form-submission.md) — user `formData` comes from the registration form (`form_identifier` is specified in `users_auth_providers`).
- [04-order-flow.md](./04-order-flow.md) — `orders.user_id` references `users.id`. The order is visible in `user.orders` (`OneToMany`).
- [09-collections.md](./09-collections.md) — a collection can be attached to a user via `entity_type='users'`.

## Antipattern

**"Let's add a `users.is_vip BOOLEAN` column."** Don't. `users` already has a full `attribute_set_id`. If you need to "tag VIP customers":

1. Open the user attribute set (`AttributesSetType.forUsers`).
2. Add to `schema` the attribute `is_vip` with `type: 'radioButton'` (this is the `AttributeType.flag` enum value, see `cms/src/modules/index-attributes-sets/types/attribute-types.enum.ts:14`).
3. The `PUT /attributes-sets/:id/schema` PATCH updates the schema **and** starts the Bull job `change-user-attribute`, which recalculates values for all users.
4. Frontend gets the attribute via `GET /users/:id` (or `/me` for the user themselves).

Same logic for anything you'd want to add as a column: `loyalty_level`, `vat_number`, `birth_date`, `avatar` — these are attributes, not columns. See [10-extend-attribute-set.md](./10-extend-attribute-set.md).

**When a column IS justified:** only when the field is needed for filtering in SQL `WHERE` on millions of rows or for a unique index (`login`, `email`) — and in that case it already exists in `users` (`password_hash`, `auth_provider_id`, `import_id`, `is_active`).
