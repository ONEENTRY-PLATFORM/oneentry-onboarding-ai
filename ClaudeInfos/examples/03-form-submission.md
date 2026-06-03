<!-- audit: 5/5 (2026-05-13) endpoints[POST /forms, PUT /forms/:id, POST /form-data/marker/:marker, PUT /form-data/:id/update-status, DELETE /form-data/:id], fields[forms.processing_type, forms.type, form_data.form_module_id, form_data.status, form_data.fingerprint], queues[events queue + submit-form-data consumer], ws[admin-forms.controller: 'forms' create/update, 'form' delete; form-data: none], fk[form_data.form_module_id->forms_modules_mn.id CASCADE] -->

# 03. Form: receiving submissions, vacancy applications, registration

## Purpose

Any form a user fills out and submits:
- **"Contact me"** / contacts / price request.
- **Vacancy application** (CV, file attachment).
- **Registration / login / password change** (via `users_auth_providers`).
- **Review / comment / product rating** (`FormType.RATING`).
- **Order via cart** (`FormType.ORDER` — payer/recipient/delivery fields).

OneEntry distinguishes **`forms`** (field description + processing rules) and **`form_data`** (specific submissions to one form). These are two different tables. `forms` is the dictionary, `form_data` is the stream of submissions.

If data only needs to be **stored in the admin as a table** — that's not a form, that's [09-collections.md](./09-collections.md). A form is needed when there's submit + processing (email, DB, script) + moderation statuses.

## Entities and dependency hierarchy

```
forms                  — form description: type, processing_type, localization, attribute_set
  ↑ form_id
form_module_configs    — settings for how the form interacts with a specific module
                         (e.g., order form ↔ orders_storage; review form ↔ products)
  ↑ form_module_config_id
forms_modules_mn       — specific "slots" for the form (order id, product id)
  ↑ form_module_id (CASCADE)
form_data              — each submitted entry
```

| Table | Base class | Key fields |
|---|---|---|
| `forms` | `BaseAttributeSetsAbstractEntity` | `processing_type` enum (`db`/`email`/`script`), `type` enum (`order`/`sing_in_up`/`collection`/`data`/`rating`), `template_id`, `selected_attribute_markers`, `localize_infos: FormLocalizeInfos` |
| `form_data` | `BaseEntity` | `form_identifier`, `time`, `form_data` jsonb (`FormDataLangType`), `user_identifier`, `entity_identifier`, `parent_id` (for threads), `ip`, `fingerprint`, `is_user_admin`, `status` enum (`sent/banned/deleted/moderation/approved`), `form_module_id` (FK CASCADE) |
| `form_module_configs` | — | link between form and module (`OrderStorageEntity`, `ProductEntity`, etc.) — which attribute_set to apply, what to write into `entity_identifier` |
| `forms_modules_mn` | — | M:N form ↔ specific module instance (e.g., review form ↔ product 42) |

Creation order:
1. Create `attribute_set` of type `forBlocks` (a form inherits from `BaseAttributeSetsAbstractEntity`, but semantically its fields are block-fields). The schema defines the form fields themselves (name, email, message, attached file).
2. Create `form` via `POST /forms`, specifying `processingType`, `type`, `attributeSetId`, `localizeInfos`.
3. (Opt.) Link the form to a module via `form_module_config` — e.g., so the order form creates an entry in the target `orders_storage`.
4. Storefront submits data via `POST /content/form-data/...` or admin creates a manual entry via `POST /form-data/marker/:marker` (see below).

## Related `general_types` and `attribute_sets`

- `general_types.type = 'form'` (id=11) — linked to the `forms` module via `module_general_types_mn`.
- `AttributesSetType.forBlock` (= `'forBlocks'`) — form fields are described in `attribute_set` via `schema`. Each schema item is a future form field: `{type: 'string'|'text'|'list'|'file'|'image'|'radioButton'|'json'|..., identifier: 'email', isNotificationEmail: true, ...}`.
- Special flags in `SchemaItem`: `isPassword`, `isLogin`, `isSignUp`, `isNotificationEmail`, `isNotificationPhoneSMS`, `isNotificationPhonePush` — mark system fields (e.g., sender `email` for email processing).

## Full jsonb with data

### Form "Contact us"

```json
{
  "id": 24,
  "identifier": "contact-us",
  "type": "data",
  "processingType": "email",
  "templateId": 9,
  "selectedAttributeMarkers": "name,email,message",
  "localizeInfos": {
    "en_US": {
      "title": "Contact us",
      "systemTitle": "Contacts",
      "successMessage": "Thanks! We'll get back within a day.",
      "unsuccessMessage": "Something went wrong."
    }
  },
  "attributeSetId": 33,
  "attributesSets": {
    "en_US": {
      "header": "Drop a request",
      "subheader": "We'll call back within an hour during business hours",
      "submit_button_label": "Send",
      "consent_text": "I consent to personal data processing"
    }
  }
}
```

Related `attribute_set.schema` (5 fields, describe what to show in the form):

```json
{
  "name":    { "type": "string",     "identifier": "name",    "position": 1, "localizeInfos": { "en_US": { "title": "Name" } } },
  "email":   { "type": "string",     "identifier": "email",   "position": 2, "isNotificationEmail": true, "localizeInfos": { "en_US": { "title": "Email" } } },
  "phone":   { "type": "string",     "identifier": "phone",   "position": 3, "isNotificationPhoneSMS": true, "localizeInfos": { "en_US": { "title": "Phone", "mask": "+1 (___) ___-____" } } },
  "message": { "type": "text",       "identifier": "message", "position": 4, "localizeInfos": { "en_US": { "title": "Message" } } },
  "consent": { "type": "radioButton","identifier": "consent", "position": 5, "localizeInfos": { "en_US": { "title": "Consent" } } }
}
```

### `form_data` record (one submission)

```json
{
  "id": 5012,
  "formIdentifier": "contact-us",
  "time": "2026-05-13T14:22:11.512Z",
  "userIdentifier": "anonymous",
  "entityIdentifier": "page-contacts",
  "parentId": null,
  "ip": "203.0.113.42",
  "fingerprint": "fp-7c9a2e",
  "isUserAdmin": false,
  "status": "moderation",
  "formModuleId": null,
  "formData": {
    "en_US": [
      { "marker": "name",    "type": "string",      "value": "John Doe" },
      { "marker": "email",   "type": "string",      "value": "john@example.com" },
      { "marker": "phone",   "type": "string",      "value": "+1 (415) 000-0000" },
      { "marker": "message", "type": "text",
        "value": [{
          "htmlValue": "<p>Need a wholesale price list.</p>",
          "plainValue": "Need a wholesale price list.",
          "mdValue": "Need a wholesale price list.",
          "params": { "isImageCompressed": true, "editorMode": "html" }
        }]
      },
      { "marker": "consent", "type": "radioButton", "value": true },
      { "marker": "cv_file", "type": "file",
        "value": {
          "filename": "files/project/form-data/5012/cv.pdf",
          "downloadLink": "https://cdn.example/cloud-static/files/project/form-data/5012/cv.pdf",
          "size": 89234,
          "contentType": "application/pdf"
        }
      }
    ]
  }
}
```

## Admin API

### Forms (`@Controller('forms')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `POST` | `/forms` | `forms.create` | Create a form |
| `PUT` | `/forms/:id` | `forms.update` | Update |
| `DELETE` | `/forms/:id` | `forms.delete` | Delete |
| `GET` | `/forms` / `/forms/:id` | — | Fetch |
| `GET` | `/forms/marker-validation/:marker` | — | `identifier` uniqueness check |
| `PUT` | `/forms/module-config/:configId/position` | — | Reorder forms attached to a module |
| `POST` | `/forms/module-config/init-position` | — | Initialize `position` for all configs |

```http
POST /forms

{
  "identifier": "contact-us",
  "type": "data",
  "processingType": "email",
  "attributeSetId": 33,
  "localizeInfos": {
    "en_US": { "title": "Contact us", "systemTitle": "Contacts", "successMessage": "Thanks!", "unsuccessMessage": "Error" }
  }
}
```

### Form data (`@Controller('form-data')`)

| Method | Path | Permission | Purpose |
|---|---|---|---|
| `GET` | `/form-data` | — | List of all submissions (paginated) |
| `POST` | `/form-data/marker/:marker` | — | Search submissions of one form with filters (by `status`, `entityIdentifier`, `dateFrom/dateTo`, `parentId`) |
| `PUT` | `/form-data/:id/update-status` | `forms.data.update` | Change status (moderation → approved/banned) |
| `DELETE` | `/form-data/:id` | `forms.data.delete` | Delete one submission |
| `DELETE` | `/form-data` | `forms.data.delete` | Batch delete |
| `GET` | `/form-data/count/:marker` | — | Counts per form |

```http
PUT /form-data/5012/update-status

{
  "status": "approved"
}
```

Allowed statuses — `FormDataStatusType`: `sent`, `banned`, `deleted`, `moderation`, `approved`.

```http
POST /form-data/marker/contact-us?langCode=en_US&page=1&limit=20

{
  "status": ["moderation"],
  "dateFrom": "2026-05-01",
  "dateTo": "2026-05-13",
  "entityIdentifier": "page-contacts"
}
```

## Behind the scenes

- **Bull queue `events` + consumer `submit-form-data`** — every time `BaseFormDataService.create` saves a new submission, it pushes a job:
  ```ts
  this.eventsQueue.add(BULL_CONSUMERS.submitFormData, formData);
  // 'submit-form-data' — see cms/src/config/constants.ts:49
  ```
  The job finds `events` subscribed to this form marker and pushes notifications via [06-event-notification.md](./06-event-notification.md) — e.g., an email to the admin about a new submission.
- **Bull consumer `change-form-attribute`** — reacts to changes in the form's `attribute_set` schema (type `forBlocks` used by the form). Recomputes `selected_attribute_markers` and indexes.
- **WS.** On changes to the **form itself** `admin-forms.controller.ts` sends `sendMessage(payload, 'forms', 'create' | 'update')` and `'form', 'delete'` — the frontend updates the form list in open tabs. On submission (`form_data`), WS events are **not** emitted; the admin tab with the submission log sees new records via periodic polling or manual refresh, not via broadcast.
- **Journal** — `FORM_CREATED, FORM_UPDATED, FORM_DELETED, FORM_DATA_CREATED, FORM_DATA_UPDATED, FORM_DATA_DELETED`. `POST /form-data/marker/:marker` has `@Journalable(FORM_DATA_CREATED)` (in base-form-data, double-check via re-query if it matters).
- **`processing_type='email'`** — the `submit-form-data` consumer extracts addresses from `attribute_set` (fields with `isNotificationEmail`) and sends mail via `notice-service` (RabbitMQ via `RABBITMQ_ROUTING_KEYS.notificationKey = 'notification-key'`).
- **`processing_type='script'`** — POST to an external URL from the form config.
- **`processing_type='db'`** — just an entry in `form_data`, no side effects.

## Links to other files

- [02-content-page.md](./02-content-page.md) — a form is inserted into a page via a block of type `general_type='form'` (`block_pages_mn`).
- [04-order-flow.md](./04-order-flow.md) — `FormType.ORDER` form is used on checkout, its data lands in `order` + `form_data` with a reference to `orders_storage`.
- [06-event-notification.md](./06-event-notification.md) — what happens after submit: `events` trigger → email/push.
- [09-collections.md](./09-collections.md) — `collections.form_id` references a form; the collection uses the same schema for its rows.
- [08-users-and-groups.md](./08-users-and-groups.md) — `FormType.SIGN_IN_UP` form is linked to `users_auth_provider` for login/registration.

## processing_type variations

`forms.processing_type` — enum (`cms/src/modules/forms/forms.interface.ts`, `FormProcessingType`) with three values: `'db'`, `'email'`, `'script'`. Determines what the `submit-form-data` consumer does after saving `form_data`.

### `'db'` — data only into form_data

The simplest mode. Storefront submits → record in `form_data` → event in Bull `events` (for journaling / WS, no side effects). No emails, no HTTP calls. All examples above — `'db'` (this is the default).

When to choose: internal tools, requests the admin processes by hand, reviews with moderation.

### `'email'` — data is sent via email through notice-service

The `submit-form-data` consumer extracts from `attribute_set` all fields with the flag `isNotificationEmail: true` (these are recipient addresses), and from `form_data.formData` — the email body. Delivery goes via RabbitMQ → notice-service → SMTP/SES.

Minimal form:

```json
POST /forms
{
  "identifier": "contact-us",
  "type": "data",
  "processingType": "email",
  "attributeSetId": 33,
  "localizeInfos": {
    "en_US": { "title": "Contact us", "systemTitle": "Contacts", "successMessage": "Thanks!", "unsuccessMessage": "Error" }
  }
}
```

Related `attribute_set.schema` — must contain **at least one field with `isNotificationEmail: true`**:

```json
{
  "to_email": {
    "type": "string",
    "identifier": "to_email",
    "position": 1,
    "isNotificationEmail": true,
    "initialValue": "support@example.com",
    "localizeInfos": { "en_US": { "title": "Recipient email" } }
  },
  "from_name": { "type": "string", "identifier": "from_name", "position": 2, "localizeInfos": { "en_US": { "title": "Your name" } } },
  "from_email": { "type": "string", "identifier": "from_email", "position": 3, "rules": { "pattern": "^[^@\\s]+@[^@\\s]+\\.[^@\\s]+$" }, "localizeInfos": { "en_US": { "title": "Your email" } } },
  "message": { "type": "text", "identifier": "message", "position": 4, "localizeInfos": { "en_US": { "title": "Message" } } }
}
```

Email template fields (`letterTitle`, `letterBody`) and addresses are stored in `EmailSettings` / `ProcessingEmail` — these are `additionalFields` / `attributesSets` of the form record. Exact `ProcessingEmail` shape:

```ts
// cms/src/modules/forms/forms.interface.ts:45-49
export type ProcessingEmail = {
  addresses: string[];      // where to send
  letterTitle: string;      // email subject
  letterBody: string;       // body template (with {{marker}} interpolation)
};
```

⚠ `forms` is in whitelist 18, but the `ProcessingEmail` setup (addresses + template) is **not loaded by the blueprint loader** — it's usually done in the admin after import (Forms module → form → "Processing" tab). The blueprint can only contain the basic form fields (`processing_type: 'email'`) and the attribute_set with an `isNotificationEmail` field, the rest is a manual step.

### `'script'` — payload goes to a webhook/script

The `submit-form-data` consumer makes a POST to an external URL with the JSON body `form_data.formData`. This is integration with CRM / Zapier / your own backend that should accept the submission.

```json
POST /forms
{
  "identifier": "demo-request",
  "type": "data",
  "processingType": "script",
  "attributeSetId": 41,
  "localizeInfos": {
    "en_US": { "title": "Request a demo", "successMessage": "Thanks, we'll call back", "unsuccessMessage": "Error" }
  }
}
```

Related `ProcessingScript` setting:

```ts
// cms/src/modules/forms/forms.interface.ts:51-53
export type ProcessingScript = {
  url: string;              // where to POST
};
```

Example payload that notice-service / consumer will send to `url`:

```json
{
  "formIdentifier": "demo-request",
  "time": "2026-05-13T14:22:11.512Z",
  "formData": {
    "en_US": [
      { "marker": "name",    "type": "string", "value": "John Doe" },
      { "marker": "email",   "type": "string", "value": "john@acme.com" },
      { "marker": "company", "type": "string", "value": "Acme Inc." }
    ]
  }
}
```

⚠ Same as for `'email'`: `processing_type: 'script'` is set via blueprint, but `url` is stored in the form's admin settings and usually is **not** populated via blueprint. The user must enter the URL manually after import.

### Summary for mapper / builder

| If the code has | → pick `processing_type` |
|---|---|
| A simple "submit a request" form, admin reads in the admin panel | `'db'` |
| Contact form, feedback, vacancy application — send to department email | `'email'` (+ `isNotificationEmail` field in attribute_set) |
| Integration with external CRM/Zapier/HubSpot | `'script'` (admin adds the URL manually) |

⚠ Mapper defaults to `'db'`. If the project has a component with an explicit email-sending marker (mailto: link, `sendgrid`/`nodemailer` import in the backend form handler, "send to" field in the UI) — pick `'email'`. If a webhook URL is found for the form — `'script'`. Document the reason in `mapped.yaml` under `warnings:`.

## Antipattern

**"Let's just save the submission directly into a new `contact_requests` table."** Don't. OneEntry already has the whole pipeline: `forms` (schema) + `form_data` (record) + `events` (trigger) + `submit-form-data` consumer (processing):

1. Create an `attribute_set` with the schema (`name`, `email`, `message`).
2. Create a `form` (`processingType: 'email'`, `attributeSetId: <above>`).
3. Storefront submits `POST /content/form-data/...`.
4. Admin sees all submissions in `GET /form-data`, can set statuses, ban, export.

**When a form does NOT fit:** if the data is a module entity (order, product, page), not just a "submission". Then a form is a **transport** (`FormType.ORDER` for checkout), and the data lands in `orders`/`pages`/`products` via `form_module_config`.
