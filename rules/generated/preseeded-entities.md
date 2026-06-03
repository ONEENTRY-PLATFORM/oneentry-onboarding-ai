# Preseeded entities — what already exists in any fresh OneEntry Platform instance

> **This file is auto-generated** via `agents_datasets/scripts/gen-rules.py`. Do not edit by hand.
>
> Generation date: 2026-06-02.
>
> Source of truth: `INSERT INTO <whitelist_table>` in `cms/src/seeds/*.ts`.

## Rule

In any freshly installed OneEntry Platform instance, certain records in whitelist tables **already exist** via TypeORM migrations. The blueprint **must not** try to insert them again — 23505 will follow.

Mapper and builder must **not generate** preseeded records. If the user application has an analogous entity — use the existing numeric id directly (without a token) in the FK reference.

## Registry of preseeded records in whitelist tables

| Table | Source | Columns -> values |
|---|---|---|
| `form_module_config` | `1755499198642-seed-forms-refactoring.ts` | `module_id=4`, `form_id=${formId}`, `entity_identifiers='${JSON.stringify(
        entityIdentifiers` |
| `templates` | `1880400000000-seed-dynamic-block-templates.ts` | `identifier=$1`, `general_type_id=$2`, `attribute_set_id=$3`, `title=$4`, `attributes_sets='{}'::json` |
| `user_group_permissions_mn` | `1755499198641-seed-user-permissions-add-endpoints.ts` | `group_id=${GUEST_USER_GROUP_ID}`, `permission_id=${permData[0].id}` |
| `user_group_permissions_mn` | `1870795700000-seed-frequently-ordered-block-type.ts` | `id=DEFAULT`, `group_id=1`, `permission_id=$1` |
| `user_group_permissions_mn` | `1765780000001-seed-user-permissions2.ts` | `group_id=${GUEST_USER_GROUP_ID}`, `permission_id=${permissionData[0].id}` |
| `user_group_permissions_mn` | `1765790000000-seed-user-permissions-orders-preview.ts` | `group_id=${GUEST_USER_GROUP_ID}`, `permission_id=${permData[0].id}` |
| `user_group_permissions_mn` | `1765780000002-seed-user-permissions2.ts` | `group_id=${GUEST_USER_GROUP_ID}`, `permission_id=${permissionData[0].id}` |
| `user_groups` | `1745835025671-set-default-user-group.ts` | `id=1`, `identifier='guest'`, `localize_infos='{"en_US":{"title":"Guest"}}'` |
| `user_permissions` | `1755499198641-seed-user-permissions-add-endpoints.ts` | `localize_infos='{"en_US":{"title":"${item.title}"}}'`, `path='${item.path}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1870795700001-seed-subscriptions.ts` | `localize_infos='{"en_US":{"title":"Subscription management"}}'`, `path='/api/content/subscriptions'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":0` |
| `user_permissions` | `1870795700001-seed-subscriptions.ts` | `localize_infos='{"en_US":{"title":"Active subscriptions"}}'`, `path='/api/content/subscriptions/active'`, `rules='{"permissions":{"readAllRule":1`, `section="readRestrictionRule":0` |
| `user_permissions` | `1774429295863-seed-refund-request-permissions.ts` | `localize_infos='{"en_US":{"title":"Refund requests for the order"}}'`, `path='/api/content/orders/{id}/refund'`, `rules='{"permissions":{"readAllRule":1`, `section="readRestrictionRule":0` |
| `user_permissions` | `1870795700000-seed-frequently-ordered-block-type.ts` | `id=DEFAULT`, `localize_infos='{"en_US":{"title":"Getting frequently ordered products"}}'`, `path='/api/content/blocks/{marker}/products/{productId}/frequently-ordered'`, `section='blocks'`, `rules='{"permissions":{"readAllRule":0` |
| `user_permissions` | `1765780000001-seed-user-permissions2.ts` | `localize_infos='{"en_US":{"title":"${
          permission.title
        }"}}'`, `path='${permission.path}'`, `rules='{"permissions":${JSON.stringify(
        permission.rules`, `section=` |
| `user_permissions` | `1765790000000-seed-user-permissions-orders-preview.ts` | `localize_infos='{"en_US":{"title":"Preview an order in the order repository"}}'`, `path='/api/content/orders-storage/orders/preview'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":0` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=1`, `localize_infos='{"en_US":{"title":"Retrieving all top-level objects on the page (parentId = null` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=2`, `localize_infos='{"en_US":{"title":"Retrieving all page objects containing product information in the form of an array"}}'`, `path='/api/content/pages'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=3`, `localize_infos='{"en_US":{"title":"Retrieving a single page object containing information about forms`, `path=blocks`, `rules=menus attached to the page"}}'`, `section='/api/content/pages/{id}'` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=4`, `localize_infos='{"en_US":{"title":"Retrieving child pages with product information in the form of an array"}}'`, `path='/api/content/pages/{url}/children'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=5`, `localize_infos='{"en_US":{"title":"Retrieving a single page object with information about forms`, `path=blocks`, `rules=menus attached to the page by URL"}}'`, `section='/api/content/pages/url/{url}'` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=6`, `localize_infos='{"en_US":{"title":"Retrieving ContentPageFormDto objects for an associated form by URL"}}'`, `path='/api/content/pages/{url}/forms'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=7`, `localize_infos='{"en_US":{"title":"Retrieving ContentPageBlockDto objects for a related block by URL"}}'`, `path='/api/content/pages/{url}/blocks'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=8`, `localize_infos='{"en_US":{"title":"Retrieving settings for the page"}}'`, `path='/api/content/pages/{url}/config'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=9`, `localize_infos='{"en_US":{"title":"Fast search for limited output page objects"}}'`, `path='/api/content/pages/quick/search'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=10`, `localize_infos='{"en_US":{"title":"Getting all form objects"}}'`, `path='/api/content/forms'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=11`, `localize_infos='{"en_US":{"title":"Getting a single form object by marker"}}'`, `path='/api/content/forms/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=12`, `localize_infos='{"en_US":{"title":"Obtaining similar products (based on the conditions in the block` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=13`, `localize_infos='{"en_US":{"title":"Retrieving products from categories associated with a block"}}'`, `path='/api/content/blocks/{marker}/products'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=14`, `localize_infos='{"en_US":{"title":"Retrieving all block objects"}}'`, `path='/api/content/blocks'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=15`, `localize_infos='{"en_US":{"title":"Getting a single block object by its marker"}}'`, `path='/api/content/blocks/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=16`, `localize_infos='{"en_US":{"title":"Fast search for limited output block objects"}}'`, `path='/api/content/blocks/quick/search'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=17`, `localize_infos='{"en_US":{"title":"Searching for all product objects with pagination and filtering. (POST` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=18`, `localize_infos='{"en_US":{"title":"Searching for all product objects with pagination`, `path=which do not have a category."}}'`, `rules='/api/content/products/empty-page'`, `section='{"permissions":{"readAllRule":0` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=19`, `localize_infos='{"en_US":{"title":"Searching for all product objects with pagination for the selected category. (POST` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=20`, `localize_infos='{"en_US":{"title":"Searching for information on products and prices for the selected category"}}'`, `path='/api/content/products/page/{url}/prices'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=21`, `localize_infos='{"en_US":{"title":"Searching for all product objects with pagination for the selected category (based on its URL` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=22`, `localize_infos='{"en_US":{"title":"Searching for all related product objects"}}'`, `path='/api/content/products/{id}/related'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=23`, `localize_infos='{"en_US":{"title":"Fetching multiple items by id"}}'`, `path='/api/content/products/ids'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=24`, `localize_infos='{"en_US":{"title":"Receiving one unit of goods"}}'`, `path='/api/content/products/{id}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=25`, `localize_infos='{"en_US":{"title":"Retrieving ContentPageBlockDto objects by product identifier"}}'`, `path='/api/content/products/{id}/blocks'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=26`, `localize_infos='{"en_US":{"title":"Fast search for product page objects with limited output"}}'`, `path='/api/content/products/quick/search'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=27`, `localize_infos='{"en_US":{"title":"Searching for all objects with the status of \\"goods\\""}}'`, `path='/api/content/product-statuses'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=28`, `localize_infos='{"en_US":{"title":"Search for an item status object by its textual identifier (marker` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=29`, `localize_infos='{"en_US":{"title":"Checking the existence of a text identifier (marker` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=30`, `localize_infos='{"en_US":{"title":"Retrieving all user objects - admins. (POST` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=31`, `localize_infos='{"en_US":{"title":"Retrieving all objects of attribute sets."}}'`, `path='/api/content/attributes-sets'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=32`, `localize_infos='{"en_US":{"title":"Retrieving all attributes with data from the attribute set"}}'`, `path='/api/content/attributes-sets/{marker}/attributes'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=33`, `localize_infos='{"en_US":{"title":"Retrieving a single attribute with data from a set of attributes"}}'`, `path='/api/content/attributes-sets/{marker}/attributes/{attributeMarker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=34`, `localize_infos='{"en_US":{"title":"Retrieving a single object from a set of attributes by a marker"}}'`, `path='/api/content/attributes-sets/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=35`, `localize_infos='{"en_US":{"title":"Creating a data storage information object"}}'`, `path='/api/content/form-data'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=36`, `localize_infos='{"en_US":{"title":"Searching data form by text identifier (marker` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=37`, `localize_infos='{"en_US":{"title":"Searching for all active language localization objects (available for use` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=38`, `localize_infos='{"en_US":{"title":"Retrieving all template objects with filtering by types"}}'`, `path='/api/content/templates'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=39`, `localize_infos='{"en_US":{"title":"Retrieving all template objects grouped by types"}}'`, `path='/api/content/templates/all'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=40`, `localize_infos='{"en_US":{"title":"Retrieving a single template object by marker"}}'`, `path='/api/content/templates/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=41`, `localize_infos='{"en_US":{"title":"Getting all types"}}'`, `path='/api/content/general-types'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=42`, `localize_infos='{"en_US":{"title":"Retrieving all template objects"}}'`, `path='/api/content/template-previews'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=43`, `localize_infos='{"en_US":{"title":"Retrieving a single template object by marker"}}'`, `path='/api/content/template-previews/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=44`, `localize_infos='{"en_US":{"title":"File upload"}}'`, `path='/api/content/files'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=45`, `localize_infos='{"en_US":{"title":"Returns all subscriptions to products"}}'`, `path='/api/content/events/subscriptions'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=46`, `localize_infos='{"en_US":{"title":"Subscription to an event on a product"}}'`, `path='/api/content/events/subscribe/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=47`, `localize_infos='{"en_US":{"title":"Event unsubscription on the item"}}'`, `path='/api/content/events/unsubscribe/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=48`, `localize_infos='{"en_US":{"title":"Obtaining data of an authorized user"}}'`, `path='/api/content/users/me'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=49`, `localize_infos='{"en_US":{"title":"Adds FCM token for sending Push notifications"}}'`, `path='/api/content/users/me/fcm-token/{token}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=50`, `localize_infos='{"en_US":{"title":"User registration (❗️For providers with user activation`, `path=the activation code is sent through the corresponding user notification method` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=51`, `localize_infos='{"en_US":{"title":"Obtaining the activation code for the user"}}'`, `path='/api/content/users-auth-providers/marker/{marker}/users/generate-code'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=52`, `localize_infos='{"en_US":{"title":"User activation code verification"}}'`, `path='/api/content/users-auth-providers/marker/{marker}/users/check-code'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=53`, `localize_infos='{"en_US":{"title":"User activation"}}'`, `path='/api/content/users-auth-providers/marker/{marker}/users/activate'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=54`, `localize_infos='{"en_US":{"title":"User authentication"}}'`, `path='/api/content/users-auth-providers/marker/{marker}/users/auth'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=55`, `localize_infos='{"en_US":{"title":"User token update"}}'`, `path='/api/content/users-auth-providers/marker/{marker}/users/refresh'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=56`, `localize_infos='{"en_US":{"title":"User logout"}}'`, `path='/api/content/users-auth-providers/marker/{marker}/users/logout'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=57`, `localize_infos='{"en_US":{"title":"User password change (only for tariffs with account activation and Activation feature enabled` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=58`, `localize_infos='{"en_US":{"title":"Retrieving all authentication provider objects"}}'`, `path='/api/content/users-auth-providers'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=59`, `localize_infos='{"en_US":{"title":"Retrieving a single authentication provider object by token"}}'`, `path='/api/content/users-auth-providers/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=60`, `localize_infos='{"en_US":{"title":"Retrieving all user group objects from the top level (parentId = null` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=61`, `localize_infos='{"en_US":{"title":"Retrieving all user group objects"}}'`, `path='/api/content/user-groups'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=62`, `localize_infos='{"en_US":{"title":"Retrieving a single user group object"}}'`, `path='/api/content/user-groups/{id}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=63`, `localize_infos='{"en_US":{"title":"Obtaining user subgroups"}}'`, `path='/api/content/user-groups/marker/{marker}/children'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=64`, `localize_infos='{"en_US":{"title":"Retrieving a single user group object"}}'`, `path='/api/content/user-groups/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=65`, `localize_infos='{"en_US":{"title":"Retrieving pages included in the menu by marker"}}'`, `path='/api/content/menus/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=66`, `localize_infos='{"en_US":{"title":"Emulating a 404 error"}}'`, `path='/api/content/system/test404'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=67`, `localize_infos='{"en_US":{"title":"Emulating a 500 error"}}'`, `path='/api/content/system/test500'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=68`, `localize_infos='{"en_US":{"title":"Obtaining the number of API calls"}}'`, `path='/api/content/system/api-stat'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=69`, `localize_infos='{"en_US":{"title":"Google ReCaptcha verification"}}'`, `path='/api/content/system/captcha/validate'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=70`, `localize_infos='{"en_US":{"title":"Stripe webhook"}}'`, `path='/api/content/payments/webhook/stripe'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=71`, `localize_infos='{"en_US":{"title":"Payment session creation"}}'`, `path='/api/content/payments/sessions'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=72`, `localize_infos='{"en_US":{"title":"Retrieving a single payment session object by its identifier"}}'`, `path='/api/content/payments/sessions/{id}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=73`, `localize_infos='{"en_US":{"title":"Retrieving a single payment session object by order ID"}}'`, `path='/api/content/payments/sessions/order/{id}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=74`, `localize_infos='{"en_US":{"title":"Payment settings retrieval"}}'`, `path='/api/content/payments/connected'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=75`, `localize_infos='{"en_US":{"title":"Getting all payment accounts as an array"}}'`, `path='/api/content/payments/accounts'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=76`, `localize_infos='{"en_US":{"title":"Retrieving a single object of a payment account by its identifier"}}'`, `path='/api/content/payments/accounts/{id}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=77`, `localize_infos='{"en_US":{"title":"Obtaining application settings"}}'`, `path='/api/content/settings-general'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=78`, `localize_infos='{"en_US":{"title":"Sure`, `path=please provide the text you would like me to translate into English using technical style and terminology"}}'`, `rules='/api/content/immutable-settings'`, `section='{"permissions":{"readAllRule":0` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=79`, `localize_infos='{"en_US":{"title":"Getting all collections"}}'`, `path='/api/content/integration-collections'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=80`, `localize_infos='{"en_US":{"title":"Retrieving a single object from a collection"}}'`, `path='/api/content/integration-collections/{id}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=81`, `localize_infos='{"en_US":{"title":"Retrieving all records belonging to a collection"}}'`, `path='/api/content/integration-collections/{id}/rows'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=82`, `localize_infos='{"en_US":{"title":"Checking the existence of a text identifier (marker` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=83`, `localize_infos='{"en_US":{"title":"Retrieving all records belonging to a collection"}}'`, `path='/api/content/integration-collections/marker/{marker}/rows'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=84`, `localize_infos='{"en_US":{"title":"Updating a record in a collection"}}'`, `path='/api/content/integration-collections/marker/{marker}/rows/{id}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=85`, `localize_infos='{"en_US":{"title":"Creating an order in the order repository"}}'`, `path='/api/content/orders-storage/marker/{marker}/orders'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=86`, `localize_infos='{"en_US":{"title":"Order modification in the order repository"}}'`, `path='/api/content/orders-storage/marker/{marker}/orders/{id}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=87`, `localize_infos='{"en_US":{"title":"Retrieving all objects from the orders repository"}}'`, `path='/api/content/orders-storage'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1748328604654-seed-user-permissions.ts` | `id=88`, `localize_infos='{"en_US":{"title":"Retrieving a single order storage object by marker"}}'`, `path='/api/content/orders-storage/marker/{marker}'`, `rules='{"permissions":{"readAllRule":0`, `section="readRestrictionRule":1` |
| `user_permissions` | `1765780000002-seed-user-permissions2.ts` | `localize_infos='{"en_US":{"title":"${
          permission.title
        }"}}'`, `path='${permission.path}'`, `rules='{"permissions":${JSON.stringify(
        permission.rules`, `section=` |

## How to reference a preseeded record

If the application needs a reference to a preseeded record (for example, the guest user_group):

WRONG (will create a duplicate -> 23505):
```yaml
user_groups:
  - identifier: guest    # already preseeded!
```

CORRECT — specify the **numeric id directly** in the FK field:
```json
"users_auth_providers": [{
  "user_group_id": 1     // <- numeric id of preseeded guest
}]
```

## What we DO NOT generate in mapper / builder

- `templates` with identifier `$1` — **never**.
- `user_groups` with identifier `guest` — **never**.

## Why the loader CANNOT do identifier-lookup

From `cms/src/modules/import/sevices/blueprint/blueprint-loader.service.ts`:
- The loader expects that **every** reference via `@token` has a corresponding row with `id: @token` in the blueprint.
- If the row is missing -> error `Unresolved token references` (S4).
- The loader **does not** issue a DB query like `SELECT id FROM user_groups WHERE identifier='guest'`.

Therefore the only way to reference a preseeded record is **a numeric id directly** in the FK field. The loader sees a number (not a string with `@`), skips resolution, passes it as-is to INSERT. PostgreSQL FK constraint checks existence -> finds the preseeded record -> import succeeds.

## What the validator (S20) must do

```python
preseeded_identifiers = {
    # From this file: { table_name: [identifiers...] }
}
for table_name, idents in preseeded_identifiers.items():
    rows = tables.get(table_name, [])
    for i, row in enumerate(rows):
        if row.get("identifier") in idents:
            errors.append(
                f"S20: {table_name}[{i}] has identifier '{row['identifier']}' "
                f"which is already preseeded in OneEntry Platform. "
                f"Use literal id (number) in FK references instead."
            )
```
