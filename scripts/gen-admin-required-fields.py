#!/usr/bin/env python3
"""gen-admin-required-fields.py — parse class-validator decorators from cms
DTOs and emit a JSON manifest of admin-required fields per whitelist table.

The validator (validate-blueprint.py) consumes the manifest and auto-generates
checks for every required / enum / numeric / date-string constraint. This
removes the manual guesswork — if a cms DTO requires a field, the manifest
captures it, and the validator flags every blueprint row that omits it.

Output: `rules/generated/admin-required-fields.json` (consumed by validator)

Usage:
    python3 gen-admin-required-fields.py --cms <path>
"""
import argparse
import json
import re
import sys
from pathlib import Path


# DTO class name → whitelist table mapping. Extend when new tables join the
# whitelist. Naming convention: CreateXDto / XDto / UpdateXDto → "x".
DTO_TO_TABLE = {
    'CreatePageDto':              'pages',
    'PageDto':                    'pages',
    'CreateProductDto':           'products',
    'ProductDto':                 'products',
    'CreateBlockDto':             'blocks',
    'BlockDto':                   'blocks',
    'CreateFormDto':              'forms',
    'FormDto':                    'forms',
    'CreateAttributesSetDto':     'attributes_sets',
    'AttributesSetDto':           'attributes_sets',
    'CreateUserGroupDto':         'user_groups',
    'UserGroupDto':               'user_groups',
    'CreateTemplateDto':          'templates',
    'TemplateDto':                'templates',
    'CreateMenuDto':              'menus',
    'MenuDto':                    'menus',
    'CreateFilterDto':            'filters',
    'FilterDto':                  'filters',
    'CreateSlideDto':             'slides',
    'SlideDto':                   'slides',
    'CreateDiscountDto':          'discounts',
    'DiscountDto':                'discounts',
    'DiscountValueConfigDto':     'discounts.discount_value',  # nested
    'CreatePageErrorDto':         'page_errors',
    'PageErrorDto':               'page_errors',
    'PaymentStatusMapDto':        'payment_status_map',
    'CreateOrderStatusDto':       'order_statuses',
    'OrderStatusDto':             'order_statuses',
    'CreateOrdersStorageDto':     'orders_storage',
    'OrdersStorageDto':           'orders_storage',
    'ProductStatusDto':           'product_statuses',
    'CreateProductStatusDto':     'product_statuses',
    'CreateDiscountCouponDto':    'discount_coupons',
    'DiscountCouponDto':          'discount_coupons',
    'CreateCollectionDto':        'collections',
    'CollectionDto':              'collections',
    'TemplatePreviewDto':         'template_previews',
    'CreateTemplatePreviewDto':   'template_previews',
}


# Map class-validator decorator → manifest key
VALIDATOR_RE = re.compile(
    r'@(IsNotEmpty|IsString|IsNumber|IsInt|IsBoolean|IsDateString|IsEnum|'
    r'IsArray|IsObject|IsUUID|IsEmail|IsUrl|MinLength|MaxLength|Min|Max|'
    r'IsOptional|IsDate)\s*(?:\(([^)]*)\))?',
)


# Snake-case conversion: orderStorageId → order_storage_id
CAMEL_RE = re.compile(r'(?<!^)(?=[A-Z])')


def to_snake(name: str) -> str:
    return CAMEL_RE.sub('_', name).lower()


def extract_dto_fields(dto_path: Path) -> list[dict]:
    """Parse a *.dto.ts file and return list of {class, field, validators}."""
    text = dto_path.read_text(errors='replace')
    out: list[dict] = []

    # Find class declarations
    class_blocks = re.split(r'(?=export\s+class\s+\w+Dto)', text)
    for block in class_blocks:
        m = re.search(r'export\s+class\s+(\w+Dto)', block)
        if not m:
            continue
        cls_name = m.group(1)
        if cls_name not in DTO_TO_TABLE:
            continue

        # For each property: collect preceding decorators
        for prop_m in re.finditer(
            r'((?:@\w+\s*(?:\([^)]*\))?\s*)+)\s*([\w_]+)\??\s*:\s*([^;\n]+)[;\n]',
            block,
        ):
            decorators_block = prop_m.group(1)
            field = prop_m.group(2)
            ts_type = prop_m.group(3).strip()
            # Skip arrow-functions or weird matches
            if field in ('class', 'constructor', 'function') or '=>' in ts_type:
                continue

            validators: dict = {}
            optional = '@IsOptional' in decorators_block
            for vm in VALIDATOR_RE.finditer(decorators_block):
                name = vm.group(1)
                arg = (vm.group(2) or '').strip()
                if name == 'IsOptional':
                    continue
                key = name.lower().replace('is', '', 1)
                if name == 'IsEnum':
                    validators['enum'] = arg
                elif name in ('MinLength', 'Min'):
                    validators['min'] = arg
                elif name in ('MaxLength', 'Max'):
                    validators['max'] = arg
                else:
                    validators[key] = True

            required = ('@IsNotEmpty' in decorators_block) or (
                validators and not optional and ts_type and not ts_type.endswith('?')
            )
            if not validators and not required:
                continue
            out.append({
                'class': cls_name,
                'table': DTO_TO_TABLE[cls_name],
                'field': to_snake(field),
                'field_camel': field,
                'required': required,
                'validators': validators,
            })
    return out


def build_manifest(cms_path: Path) -> dict:
    """Walk every *.dto.ts in cms/src/modules and assemble the manifest."""
    manifest: dict = {}
    dto_files = list(cms_path.glob('src/modules/**/dto/*.dto.ts'))
    for f in dto_files:
        for entry in extract_dto_fields(f):
            tbl = entry['table']
            manifest.setdefault(tbl, {'fields': {}, 'sources': set()})
            manifest[tbl]['sources'].add(str(f.relative_to(cms_path)))
            # Merge — last one wins for the same field, but mark required if ANY DTO requires.
            ex = manifest[tbl]['fields'].get(entry['field'], {})
            ex['required'] = ex.get('required', False) or entry['required']
            ex.setdefault('validators', {}).update(entry['validators'])
            manifest[tbl]['fields'][entry['field']] = ex
    # Sets → sorted lists for JSON
    for tbl in manifest:
        manifest[tbl]['sources'] = sorted(manifest[tbl]['sources'])
    return manifest


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--cms', required=True, help='path to cms repo root')
    parser.add_argument('--out', default=None,
                        help='output JSON path (default: rules/generated/admin-required-fields.json)')
    args = parser.parse_args()

    cms = Path(args.cms)
    if not (cms / 'src' / 'modules').exists():
        print(f'ERROR: not a cms repo: {cms}', file=sys.stderr)
        return 1

    out_path = Path(args.out) if args.out else (
        Path(__file__).resolve().parent.parent / 'rules' / 'generated' / 'admin-required-fields.json'
    )
    manifest = build_manifest(cms)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(json.dumps(manifest, indent=2, ensure_ascii=False))

    total_required = sum(
        1
        for tbl in manifest.values()
        for f in tbl['fields'].values()
        if f.get('required')
    )
    print(f'manifest written: {out_path}')
    print(f'  tables: {len(manifest)}')
    print(f'  required fields: {total_required}')
    for tbl, info in sorted(manifest.items()):
        req = sum(1 for f in info['fields'].values() if f.get('required'))
        print(f'    {tbl}: {len(info["fields"])} fields, {req} required')
    return 0


if __name__ == '__main__':
    sys.exit(main())
