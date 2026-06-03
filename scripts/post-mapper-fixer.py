#!/usr/bin/env python3
"""
post-mapper-fixer.py — deterministic fix of mapped.yaml after the entity-mapper agent.

Guarantees structural rules independently of the LLM mapper:
  1. isVisible:true on every schema-item.
  2. 404 page (general_type_id=3) if NotFoundPage exists in the project.
  3. hub/catalog page titles from shared/title-derivations.json for nulls.
  4. block titles — extracted from component source files (h1/h2/SECTION_TITLES).
     Falls back to block_default_titles from the shared JSON.
  5. user user_group is always created if there are auth-providers and it is missing.
  6. orders_storage.form_id -> form with type='order' (not signin).

Idempotent. Safe to re-run.

Usage:
    python3 post-mapper-fixer.py <mapped.yaml> <project_root>

======================================================================
VERTICAL ASSUMPTIONS — read this when applying to non-fashion projects
======================================================================

This script contains several dictionaries and heuristics whose CONTENT is
populated for the fashion-retail reference project (new-shop-nextjs). The
ALGORITHMS are universal; only the vocabulary is vertical-specific. Adding
entries is non-destructive; removing or replacing entries may break the
fashion reference but enables better support for other verticals.

Vertical-specific knobs (extend per project; do NOT remove without a
replacement for the fashion reference):

  * SPLIT_CATEGORIES (≈L186-217) — fashion-shop category splits
      ('clothing' / 'shoes' / 'bags' / 'accessories') with their
      category-specific attribute names. Used by split_forProducts_by_category()
      to break a common forProducts into per-segment attribute sets. For other
      verticals, define an analogous dict (hotel: rooms/suites/villas;
      restaurant: starters/mains/desserts/drinks; LMS: tracks; real-estate:
      property categories). Until extended, non-fashion projects keep a
      single forProducts (no split) — graceful fallback, not a crash.

  * detect_category_by_pages() — uses ('clothing', 'shoes', 'bags',
      'accessories') page-name substrings. Returns None for unknown pages
      (graceful fallback).

  * Page-role detection heuristics (~L4619-4721) — last-resort fallbacks for
      the reference fashion-shop project ('WomenCatalog' -> 'women',
      'MenShoesPage' -> 'men-shoes'). Already disclaimed inline. Inspector's
      role detector (rules/block-page-binding.md §5) is the universal path;
      this heuristic only fires when inspector left no signal.

  * SKU-prefix → page-identifier mapping (~L4829-4866) — derives page
      bindings from product SKU prefix ('wc-1' -> women-clothing). Universal
      pattern (multi-vertical example "main-courses" -> "mc-" already in
      comments); the dictionary is built dynamically from the project's
      actual pages.

  * shared/title-derivations.json — hub_titles, composite_catalog,
      block_default_titles. Vertical defaults documented in that file's
      _comment. Extend per project; never remove fashion entries while
      the fashion reference is in active use.

  * Permissions seed (~L739) — comment marks the canonical permission set
      as "fashion / general e-commerce shop" defaults. Other verticals
      typically reuse the same set (it covers Catalog / Pages / Users /
      Orders / Forms read paths) — extension is rarely needed.

OneEntry-side constants are NOT vertical-specific and must not be changed:
module_id (preseed modules 1..18), general_type_id (STABLE 3/4/17/21),
attribute_type_id (1..11), schema-id contract ('<type>_id<N>'), the 24-table
whitelist, and form-purpose -> module_id mapping (.claude/agents/entity-mapper.md
Step 9.9). See rules/oneentry-invariants.md §1-19 for the authoritative
list of OneEntry invariants.
"""
import sys, os, re, json, yaml
from pathlib import Path


SCRIPT_DIR = Path(__file__).parent
TITLE_DERIVATIONS_JSON = SCRIPT_DIR / 'shared' / 'title-derivations.json'


def load_title_derivations():
    if not TITLE_DERIVATIONS_JSON.exists():
        return {'hub_titles': {}, 'block_default_titles': {}}
    return json.loads(TITLE_DERIVATIONS_JSON.read_text())


def read_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def write_yaml(data, path):
    with open(path, 'w') as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def derive_page_title(identifier, hub_titles, composite=None):
    """Hub/catalog page title.

    Rules:
      1. Exact match in hub_titles  -> hub_titles[identifier].
      2. Composite '{gender}-{leaf}' (women-accessories, men-shoes, kids-clothing...)
         -> "<Gender's> <Leaf>" using composite.gender_possessive[gender]
            and hub_titles[leaf] (e.g. women-accessories -> "Women's Accessories").
         This is a §18 exception: composite title is built deterministically from
         two atomic, project-agnostic tokens (gender + category), it is NOT a
         Title-Case translation of the identifier.
      3. Generic composite '<x>-<leaf>' where leaf alone is in hub_titles
         (and prefix is not a known gender) -> hub_titles[leaf].
      4. None — let the mapper leave null + warning per §18.
    """
    if identifier in hub_titles:
        return hub_titles[identifier]
    parts = identifier.split('-')
    composite = composite or {}
    genders = set(composite.get('genders') or [])
    gender_possessive = composite.get('gender_possessive') or {}
    if len(parts) >= 2:
        head, tail = parts[0], '-'.join(parts[1:])
        # 2. {gender}-{leaf}
        if head in genders and tail in hub_titles:
            possessive = gender_possessive.get(head) or hub_titles.get(head) or head.title()
            return f"{possessive} {hub_titles[tail]}"
        # 3. fallback: leaf only
        if parts[-1] in hub_titles:
            return hub_titles[parts[-1]]
    return None


def find_component_file(project_root, component_name_or_path):
    """Find a component .tsx file. Accepts either a class name or a relative path."""
    project_root = Path(project_root)
    # If it is already a path
    p = project_root / component_name_or_path
    if p.exists():
        return p
    # Class name — search
    for src in ('src/app/components', 'src/components', 'components', 'app/components'):
        for ext in ('tsx', 'jsx', 'ts'):
            cand = project_root / src / f'{component_name_or_path}.{ext}'
            if cand.exists():
                return cand
    # Full fallback
    for ext in ('tsx', 'jsx'):
        results = list(project_root.rglob(f'{component_name_or_path}.{ext}'))
        results = [r for r in results if 'node_modules' not in str(r) and '.next' not in str(r)]
        if results:
            return results[0]
    return None


def parse_section_titles(project_root):
    """Extract SECTION_TITLES.<key>.title from data/sectionTitles.ts."""
    titles = {}
    for cand in Path(project_root).rglob('sectionTitles.ts'):
        if 'node_modules' in str(cand) or '.next' in str(cand):
            continue
        try:
            text = cand.read_text()
        except Exception:
            continue
        for m in re.finditer(r"(\w+)\s*:\s*\{[^}]*?title\s*:\s*['\"]([^'\"]+)['\"]", text):
            titles[m.group(1)] = m.group(2)
    return titles


def extract_block_title(component_file, section_titles):
    """Return a title or None from <h1>/<h2>/{SECTION_TITLES.X.title} in the component file."""
    if not component_file or not component_file.exists():
        return None
    text = component_file.read_text()

    # 1. SECTION_TITLES.X.title
    m = re.search(r'<h[12][^>]*>\s*\{[^}]*?SECTION_TITLES\.(\w+)\.title[^}]*?\}\s*</h[12]>', text)
    if m:
        key = m.group(1)
        if key in section_titles:
            return section_titles[key]

    # 2. <h2>Literal text</h2>
    m = re.search(r'<h[12][^>]*>\s*([A-Z][^<{}\n]{2,80})\s*</h[12]>', text)
    if m:
        title = m.group(1).strip()
        # HTML entities: &apos; -> '
        title = title.replace('&apos;', "'").replace('&amp;', '&')
        return title

    # 3. title prop literal: title="X" / title={'X'}
    m = re.search(r'title\s*=\s*[\'"]([A-Z][^\'"]{2,80})[\'"]', text)
    if m:
        return m.group(1).strip()

    return None


def fix_block_titles(blocks, project_root, section_titles, block_defaults, languages):
    """Fill null/missing/identifier-equal block titles from component source files."""
    fixes = []
    for b in blocks:
        ident = b.get('identifier', '?')

        # Check whether a fix is needed: null OR equals identifier (mapper didn't find it)
        li = b.setdefault('localize_infos', {})
        needs_fix = False
        for lang in languages:
            lang_info = li.get(lang, {}) or {}
            cur = lang_info.get('title')
            if not cur or cur == ident:
                needs_fix = True
                break
        if not needs_fix:
            continue

        derived = None
        # 1. From the block's source file
        source_components = b.get('source_components') or []
        if source_components:
            comp_file = find_component_file(project_root, source_components[0])
            if comp_file:
                derived = extract_block_title(comp_file, section_titles)
                source = f'{comp_file.name}'
        # 2. From block_default_titles (fallback)
        if not derived and ident in block_defaults:
            derived = block_defaults[ident]
            source = 'block_default_titles'

        if not derived:
            continue

        # Apply to all languages where title is null or title==identifier
        for lang in languages:
            lang_info = li.setdefault(lang, {})
            cur = lang_info.get('title')
            if not cur or cur == ident:
                lang_info['title'] = derived
        fixes.append(f"block '{ident}' title -> '{derived}' (from {source})")
    return fixes


# Split of forProducts attributes by category (clothing/shoes/bags/accessories).
# `shared` attributes go into all 4 sets; category-specific ones — only into their own.
# The list is based on e-commerce conventions; unclassified attributes go to shared.
PRODUCT_CATEGORY_ATTRS = {
    'shared': {
        'sku', 'price', 'currency', 'brand', 'brand_country', 'description', 'cover',
        'gallery', 'colors', 'sizes', 'material', 'material_origin', 'material_finish',
        'season', 'style', 'in_stock', 'is_new', 'is_featured', 'label', 'badge',
        'rating', 'rating_count', 'product_details', 'product_model', 'specs',
        'recommended_id', 'special_offers_id',
    },
    'clothing': {
        'clothing_type', 'collar', 'fit', 'hood', 'lining_material', 'neckline',
        'pockets', 'silhouette', 'sleeve',
    },
    'shoes': {
        'shoe_type', 'shoe_height', 'heel_height', 'heel_width', 'heel_counter',
        'insole_material', 'sole_construction', 'sole_material', 'sole_thickness',
        'sole_type', 'stitch_type', 'technologies', 'toe_shape', 'upper_material',
        'width', 'shaft_volume',
    },
    'bags': {
        'bag_size', 'bag_type', 'closure_type', 'frame', 'outer_material', 'strap_width',
    },
    'accessories': {
        'accessory_type',
    },
}


def detect_product_category(product):
    """Detect a product's category by pages: women-clothing -> clothing, men-shoes -> shoes."""
    pages = product.get('pages') or []
    if not pages:
        return None
    page = pages[0]
    for cat in ('clothing', 'shoes', 'bags', 'accessories'):
        if cat in page:
            return cat
    return None


def split_for_products_by_category(data, languages):
    """Split a common forProducts into forProducts_clothing/shoes/bags/accessories.

    Idempotent: if already split (no forProducts, but forProducts_* exist), no-op.
    """
    fixes = []
    asets = data.get('attributes_sets') or []
    products = data.get('products') or []
    if not products:
        return fixes

    # Find forProducts
    fp_idx = next((i for i, a in enumerate(asets) if a.get('identifier') == 'forProducts'), None)
    if fp_idx is None:
        return fixes  # already split or not present at all

    fp = asets[fp_idx]
    schema = fp.get('schema') or {}
    fp_id_token = fp.get('id', '@aset.forProducts')

    # Determine which categories are actually used (have products)
    used_cats = set()
    for p in products:
        cat = detect_product_category(p)
        if cat:
            used_cats.add(cat)
    if not used_cats:
        return fixes

    # Build new sets
    new_asets = []
    shared_attrs = PRODUCT_CATEGORY_ATTRS['shared']
    type_id = fp.get('type_id', 1)
    for cat in sorted(used_cats):
        cat_attrs = PRODUCT_CATEGORY_ATTRS.get(cat, set())
        # shared + cat-specific + any unknown fields (go into the shared bucket)
        all_keys = (set(schema.keys()) & (shared_attrs | cat_attrs)) | (
            set(schema.keys()) - shared_attrs - set().union(*PRODUCT_CATEGORY_ATTRS.values())
        )
        cat_schema = {k: schema[k] for k in all_keys if k in schema}
        # Renumber positions
        for pos, key in enumerate(sorted(cat_schema.keys()), start=1):
            cat_schema[key] = {**cat_schema[key], 'position': pos, 'isVisible': True}
        new_aset = {
            'id': f'@aset.forProducts_{cat}',
            'identifier': f'forProducts_{cat}',
            'type_id': type_id,
            'title': f"Products — {cat.capitalize()}",
            'schema': cat_schema,
        }
        new_asets.append(new_aset)

    # Drop the old forProducts, add the new ones
    asets.pop(fp_idx)
    asets.extend(new_asets)
    data['attributes_sets'] = asets

    # Rebind each product to its own set + remove irrelevant attributes
    rebound = 0
    for p in products:
        cat = detect_product_category(p)
        if not cat:
            continue
        target_aset = f'forProducts_{cat}'
        if p.get('attribute_set') == target_aset:
            continue
        p['attribute_set'] = target_aset
        # Clean attributes_sets.<lang>.<key> from attributes belonging to other categories
        new_aset = next((a for a in new_asets if a['identifier'] == target_aset), None)
        if new_aset:
            allowed = set((new_aset.get('schema') or {}).keys())
            for lang in languages:
                vals = (p.get('attributes_sets') or {}).get(lang) or {}
                p.setdefault('attributes_sets', {})[lang] = {
                    k: v for k, v in vals.items() if k in allowed
                }
        rebound += 1

    fixes.append(
        f"forProducts split: {len(new_asets)} category-specific sets "
        f"({', '.join(sorted(used_cats))}), {rebound} products reassigned"
    )
    return fixes


# Pattern mapping for project data files -> collection identifier in OneEntry.
# Picks the first matching file, parses the JS/TS export as JSON.
COLLECTION_PATTERNS = [
    ('faq', ['*faq*.ts', '*faq*.tsx', '*faq*.json']),
    ('stores', ['*store*.ts', '*store*.tsx', '*stores*.json']),
    ('brands', ['*brand*.ts', '*brand*.tsx', '*brands*.json']),
]


def _extract_balanced_array(text, start_idx):
    """From the position of the first '[' extract the substring up to the matching ']'.

    Tracks nested [], {} and string literals ' " ` to avoid catching ] inside them.
    """
    if start_idx >= len(text) or text[start_idx] != '[':
        return None
    depth_sq = 0
    depth_cu = 0
    i = start_idx
    in_str = None  # opening quote character or None
    escape = False
    while i < len(text):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", '`'):
                in_str = ch
            elif ch == '[':
                depth_sq += 1
            elif ch == ']':
                depth_sq -= 1
                if depth_sq == 0:
                    return text[start_idx:i + 1]
            elif ch == '{':
                depth_cu += 1
            elif ch == '}':
                depth_cu -= 1
        i += 1
    return None


def _extract_balanced_object(text, start_idx):
    """From the position of the first '{' extract the substring up to the matching '}'.

    Used for single-object exports like `export const X = { ... };` so we can
    wrap the result into a 1-element array for downstream consumers.
    """
    if start_idx >= len(text) or text[start_idx] != '{':
        return None
    depth_sq = 0
    depth_cu = 0
    i = start_idx
    in_str = None
    escape = False
    while i < len(text):
        ch = text[i]
        if in_str:
            if escape:
                escape = False
            elif ch == '\\':
                escape = True
            elif ch == in_str:
                in_str = None
        else:
            if ch in ('"', "'", '`'):
                in_str = ch
            elif ch == '{':
                depth_cu += 1
            elif ch == '}':
                depth_cu -= 1
                if depth_cu == 0:
                    return text[start_idx:i + 1]
            elif ch == '[':
                depth_sq += 1
            elif ch == ']':
                depth_sq -= 1
        i += 1
    return None


_TS_SYMBOL_TABLE_CACHE = {}


def _build_ts_symbol_table(text_clean):
    """Detect simple `const X = { key: 'url' }` declarations and `import X from 'path'`
    statements inside a TS/JS source file. Returns a flat dict:
      { 'I.womenFashion': 'https://...', 'heroSlide1': 'TODO_UPLOAD:./img/hero1.png' }

    Universal — works for any project that uses local URL-maps or static asset
    imports (Next.js, Vite, CRA). Without this, `image: I.womenFashion` is stored
    verbatim as a filename and the admin file-viewer 404s.
    """
    table = {}
    # 1. import X from './path/file.ext' (default import) — non-resolvable from
    #    pipeline so emit TODO_UPLOAD placeholder.
    for m in re.finditer(
        r"import\s+(\w+)\s+from\s+['\"]([^'\"]+)['\"]",
        text_clean,
    ):
        name, path = m.group(1), m.group(2)
        # Only treat as asset if path looks like a file (has extension)
        if re.search(r'\.(png|jpe?g|gif|svg|webp|avif|ico)$', path, re.IGNORECASE):
            table[name] = f'TODO_UPLOAD:{path}'
    # 2. import { a, b } from './assets' — named imports from index file.
    for m in re.finditer(
        r"import\s*\{\s*([^}]+)\}\s*from\s*['\"]([^'\"]+)['\"]",
        text_clean,
    ):
        names = [n.strip().split(' as ')[-1].strip() for n in m.group(1).split(',') if n.strip()]
        for n in names:
            table.setdefault(n, f'TODO_UPLOAD:{m.group(2)}#{n}')
    # 3. const I = { key: 'url', key2: 'url2' }; — URL-map declarations.
    for m in re.finditer(
        r"const\s+(\w+)\s*(?::\s*\w[\w<>,\s\[\]]*)?\s*=\s*\{([^{}]*?)\}\s*;",
        text_clean,
        re.DOTALL,
    ):
        outer, body = m.group(1), m.group(2)
        for kv in re.finditer(
            r"(\w+)\s*:\s*['\"`]([^'\"`]+)['\"`]",
            body,
        ):
            key, val = kv.group(1), kv.group(2)
            table[f'{outer}.{key}'] = val
            table[key] = val  # also expose unqualified
    return table


def _resolve_ts_expr(value, symbols):
    """Resolve `I.womenFashion` / `heroSlide1.src` to a literal URL or TODO_UPLOAD
    marker using the symbol table. Returns resolved value or original."""
    if not isinstance(value, str):
        return value
    v = value.strip()
    # Accept bare identifier (X), member access (X.Y), or .src/.default suffix.
    m = re.fullmatch(r'([A-Za-z_]\w*)(?:\.(\w+))?(?:\.(?:src|default))?', v)
    if not m:
        return value
    head, tail = m.group(1), m.group(2)
    candidates = []
    if tail:
        candidates.append(f'{head}.{tail}')
    candidates.append(head)
    if tail:
        candidates.append(tail)
    for c in candidates:
        if c in symbols:
            return symbols[c]
    return value


def _resolve_expressions_recursively(obj, symbols):
    """Walk a parsed JSON-like structure and resolve any TS expression tokens
    in string leaves. Idempotent."""
    if isinstance(obj, dict):
        return {k: _resolve_expressions_recursively(v, symbols) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_resolve_expressions_recursively(v, symbols) for v in obj]
    if isinstance(obj, str):
        return _resolve_ts_expr(obj, symbols)
    return obj


def parse_data_file(file_path):
    """Parse a TS/JS/JSON file containing a list of objects. Returns list[dict] or [].

    Supports:
      export const X[: Type[]]? = [{...},{...}];
      export const X[: Type[]]? = {...};        (single object — wrapped into [obj])
      const X[: Type[]]? = [{...}]; export default X;
      module.exports = [{...}];
    Resolves TS expressions like `I.foo` / `heroSlide1.src` to actual URLs from
    the file's symbol table; non-resolvable image imports become
    `TODO_UPLOAD:<path>` so the admin shows a placeholder hint.

    Uses balanced bracket matching to correctly handle nested structures
    (arrays inside objects, hours: [...], etc.).
    """
    try:
        text = Path(file_path).read_text()
    except Exception:
        return []
    if file_path.suffix == '.json':
        try:
            return json.loads(text)
        except Exception:
            return []

    # NB: do not strip // comments — the regex would break URLs inside strings
    # (https:// -> empty, unterminated strings). /* */ block comments are removed —
    # they almost never appear inside strings.
    text_clean = re.sub(r'/\*[\s\S]*?\*/', '', text)

    # Build symbol table once per file (cached for repeated parse calls).
    sym_key = str(file_path)
    if sym_key in _TS_SYMBOL_TABLE_CACHE:
        symbols = _TS_SYMBOL_TABLE_CACHE[sym_key]
    else:
        symbols = _build_ts_symbol_table(text_clean)
        _TS_SYMBOL_TABLE_CACHE[sym_key] = symbols

    # Find the start position of the array OR single object
    arr_patterns = [
        r'export\s+(?:default\s+)?const\s+\w+(?:\s*:\s*[\w\[\]<>,\s]+)?\s*=\s*\[',
        r'const\s+\w+(?:\s*:\s*[\w\[\]<>,\s]+)?\s*=\s*\[',
        r'module\.exports\s*=\s*\[',
    ]
    arr_src = None
    for pat in arr_patterns:
        m = re.search(pat, text_clean)
        if m:
            # Position of the first '[' — last char of the matched substring
            arr_src = _extract_balanced_array(text_clean, m.end() - 1)
            if arr_src:
                break

    # Fallback: single-object export (banners, promo config, footer links, etc.)
    if not arr_src:
        obj_patterns = [
            r'export\s+(?:default\s+)?const\s+\w+(?:\s*:\s*[\w\[\]<>,\s]+)?\s*=\s*\{',
            r'const\s+\w+(?:\s*:\s*[\w\[\]<>,\s]+)?\s*=\s*\{',
            r'module\.exports\s*=\s*\{',
        ]
        for pat in obj_patterns:
            m = re.search(pat, text_clean)
            if m:
                obj_src = _extract_balanced_object(text_clean, m.end() - 1)
                if obj_src:
                    arr_src = '[' + obj_src + ']'
                    break

    if not arr_src:
        return []

    # Convert JS literals to JSON
    js = arr_src
    # keys: word: -> "word":  (only if not inside a string — simple heuristic below)
    js = re.sub(r'([{,]\s*)(\w+)\s*:', r'\1"\2":', js)

    def _convert_quoted(match, quote):
        inner = match.group(1)
        # Since the opening quote character is no longer special in a JSON string
        # (it is now wrapped in "), remove the escape from it.
        inner = inner.replace('\\' + quote, quote)
        # Escape " and \n inside
        inner = inner.replace('\\', '\\\\').replace('"', '\\"').replace('\n', '\\n')
        # But \\ -> \  back, since we already escaped; otherwise it would become \\\\
        # Simple strategy: original \x escapes are not supported.
        return '"' + inner + '"'

    # 'string with \'apostrophe\'' -> "string with 'apostrophe'"
    js = re.sub(r"'((?:[^'\\]|\\.)*)'",
                lambda m: _convert_quoted(m, "'"), js)
    # backticks to double quotes (for template literals without interpolation)
    js = re.sub(r"`((?:[^`\\]|\\.)*)`",
                lambda m: _convert_quoted(m, '`'), js)
    # trailing commas
    js = re.sub(r',\s*([\]}])', r'\1', js)
    try:
        parsed = json.loads(js)
        return _resolve_expressions_recursively(parsed, symbols) if symbols else parsed
    except Exception:
        # JSON conversion can fail on edge cases (nested apostrophes inside
        # converted strings, TS-specific syntax, etc.). Fall back to the
        # robust state-machine-based object parser used for products / slides.
        try:
            arr_body = arr_src.lstrip()
            if arr_body.startswith('['):
                arr_body = arr_body[1:]
            if arr_body.endswith(']'):
                arr_body = arr_body[:-1]
            out = []
            for obj_body in _split_product_objects(arr_body):
                parsed = _parse_object_top_level(obj_body)
                if parsed:
                    out.append(parsed)
            return _resolve_expressions_recursively(out, symbols) if symbols else out
        except Exception:
            return []


def _sync_top_level_collections_to_tables(data):
    """Force-sync top-level `collections`/`collection_rows` into `tables.*`.

    The blueprint-builder reads ONLY `tables.collections` / `tables.collection_rows`.
    Top-level keys persist for pipeline tooling but never reach the loader.
    Sync at the END of `generate_collections` to make sure every row written to
    top-level mirrors into `tables.*`.

    Idempotent — duplicate identifiers / rows are skipped via natural keys.
    Universal — applies to every project type that emits collections.
    """
    fixes = []
    top_colls = data.get('collections') or []
    top_rows = data.get('collection_rows') or []
    if not top_colls and not top_rows:
        return fixes
    tables = data.setdefault('tables', {})
    tbl_colls = tables.setdefault('collections', [])
    tbl_rows = tables.setdefault('collection_rows', [])
    tbl_coll_idents = {c.get('identifier') for c in tbl_colls}
    added_colls = 0
    for c in top_colls:
        if c.get('identifier') and c.get('identifier') not in tbl_coll_idents:
            tbl_colls.append(c)
            tbl_coll_idents.add(c.get('identifier'))
            added_colls += 1
    # Build a broad natural key from form_data — for FAQ rows the question is
    # the natural key; for stores it's id/address; for any other shape we fall
    # back to the JSON-string of form_data (worst case dedup is correct).
    def _row_key(r):
        fd = r.get('form_data') or {}
        nk = (fd.get('id') or fd.get('identifier') or fd.get('question')
              or fd.get('title') or fd.get('name'))
        if not nk:
            import json as _json
            nk = _json.dumps(fd, sort_keys=True)[:200]
        return (r.get('collection_id'), r.get('lang_code'), nk)

    tbl_row_keys = {_row_key(r) for r in tbl_rows}
    added_rows = 0
    for r in top_rows:
        key = _row_key(r)
        if key not in tbl_row_keys:
            tbl_rows.append(r)
            tbl_row_keys.add(key)
            added_rows += 1
    if added_colls:
        fixes.append(f"tables.collections: +{added_colls} synced from top-level")
    if added_rows:
        fixes.append(f"tables.collection_rows: +{added_rows} synced from top-level")
    return fixes


def generate_collections(data, project_root, languages):
    """Generate collections + collection_rows for FAQ/Stores/Brands.

    Loader does upsert for collections (natural-key=identifier) and
    skip-if-parent-has-children for collection_rows — repeated import is safe.
    """
    fixes = []
    existing_colls = data.get('collections') or []
    existing_idents = {c.get('identifier') for c in existing_colls}
    new_colls = []
    new_rows = []
    primary_lang = languages[0] if languages else 'en_US'

    for ident, patterns in COLLECTION_PATTERNS:
        if ident in existing_idents:
            continue
        # Find the data file
        data_file = None
        for pat in patterns:
            for f in Path(project_root).rglob(pat):
                if ('node_modules' in str(f) or '.next' in str(f)
                        or 'storybook-static' in str(f) or '/dist/' in str(f)):
                    continue
                data_file = f
                break
            if data_file:
                break
        if not data_file:
            continue  # no data in the project — collection is not needed

        # Create the collection even if data does not parse — admin will fill in rows
        new_colls.append({
            'id': f'@coll.{ident}',
            'identifier': ident,
            'localize_infos': {primary_lang: {'title': ident.capitalize()}},
        })

        rows_data = parse_data_file(data_file)
        if not rows_data:
            continue  # collection created, admin will fill rows manually

        for row in rows_data:
            new_rows.append({
                'collection_id': f'@coll.{ident}',
                'lang_code': primary_lang,
                'form_data': row if isinstance(row, dict) else {'value': row},
            })

    # The blueprint-builder reads `tables.collections` / `tables.collection_rows`
    # — NOT the top-level lists. Without merging into `tables.*` the rows never
    # reach the loader (verified gap: 10/29 source rows → 3/29 in DB). Merge
    # into both places: top-level for back-compat, `tables.*` for actual import.
    tables = data.setdefault('tables', {})
    if new_colls:
        data['collections'] = existing_colls + new_colls
        tables_colls = tables.setdefault('collections', [])
        existing_tables_idents = {c.get('identifier') for c in tables_colls}
        for c in new_colls:
            if c.get('identifier') not in existing_tables_idents:
                tables_colls.append(c)
        fixes.append(f"+ collections: {len(new_colls)} ({', '.join(c['identifier'] for c in new_colls)})")
    if new_rows:
        existing_rows = data.get('collection_rows') or []
        data['collection_rows'] = existing_rows + new_rows
        tables_rows = tables.setdefault('collection_rows', [])
        existing_keys = {
            (r.get('collection_id'), r.get('lang_code'),
             (r.get('form_data') or {}).get('identifier'))
            for r in tables_rows
        }
        for r in new_rows:
            key = (r.get('collection_id'), r.get('lang_code'),
                   (r.get('form_data') or {}).get('identifier'))
            if key not in existing_keys:
                tables_rows.append(r)
                existing_keys.add(key)
        fixes.append(f"+ collection_rows: {len(new_rows)} rows")

    # Sync any top-level entries (existing + new) into `tables.*` so the
    # builder picks them up — without this step, collection_rows never reach
    # the loader (verified gap: tables.collection_rows = 3 vs top-level = 10).
    fixes.extend(_sync_top_level_collections_to_tables(data))

    return fixes


# Standard permissions for a registered user in a fashion / general e-commerce shop.
# Loader does upsert by (path, section) — preseed rows are reused.
#
# Rule semantics (per the `UserPermission` entity's `rules` JSONB column):
#   readAllRule          — 0 = unrestricted read, 1 = restricted by owner, False = no read
#   readRestrictionRule  — 1 = read only owner records (used together with readAllRule=0/1)
#   addRule              — True = allow POST, False = forbid
#   changeRule           — True = allow PATCH/PUT (only on own records when readRestrictionRule=1)
#   deleteRule           — True = allow DELETE
#
# Convention helpers
_READ_ONLY  = {'readAllRule': 0, 'readRestrictionRule': 1,
               'addRule': False, 'changeRule': False, 'deleteRule': False}
_READ_WRITE = {'readAllRule': 0, 'readRestrictionRule': 1,
               'addRule': True,  'changeRule': True,  'deleteRule': True}
_WRITE_ONLY = {'readAllRule': False, 'readRestrictionRule': 1,
               'addRule': True,  'changeRule': False, 'deleteRule': False}
_READ_AND_ADD = {'readAllRule': 0, 'readRestrictionRule': 1,
                 'addRule': True,  'changeRule': False, 'deleteRule': False}
_READ_AND_UPDATE = {'readAllRule': 0, 'readRestrictionRule': 1,
                    'addRule': False, 'changeRule': True,  'deleteRule': False}

USER_PERMISSIONS_TEMPLATE = [
    # --- Content navigation: pages ---
    {'path': '/api/content/pages',                        'section': 'pages',   'rule': _READ_ONLY},
    {'path': '/api/content/pages/{id}',                   'section': 'pages',   'rule': _READ_ONLY},
    {'path': '/api/content/pages/root',                   'section': 'pages',   'rule': _READ_ONLY},
    {'path': '/api/content/pages/url/{url}',              'section': 'pages',   'rule': _READ_ONLY},
    {'path': '/api/content/pages/{url}/children',         'section': 'pages',   'rule': _READ_ONLY},
    {'path': '/api/content/pages/{url}/blocks',           'section': 'pages',   'rule': _READ_ONLY},
    {'path': '/api/content/pages/{url}/config',           'section': 'pages',   'rule': _READ_ONLY},
    {'path': '/api/content/pages/{url}/forms',            'section': 'pages',   'rule': _READ_ONLY},
    {'path': '/api/content/pages/quick/search',           'section': 'pages',   'rule': _READ_ONLY},

    # --- Menus (header/footer/mega) ---
    {'path': '/api/content/menus/marker/{marker}',        'section': 'menus',   'rule': _READ_ONLY},

    # --- Catalog (products) ---
    {'path': '/api/content/products',                          'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/{id}',                     'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/all',                      'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/all/counts',               'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/empty-page',               'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/ids',                      'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/page/url/{url}',           'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/page/url/{url}/counts',    'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/page/{id}',                'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/page/{id}/counts',         'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/page/{url}/prices',        'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/quick/search',             'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/{id}/blocks',              'section': 'products', 'rule': _READ_ONLY},
    {'path': '/api/content/products/{id}/related',             'section': 'products', 'rule': _READ_ONLY},

    # --- Product statuses (in_stock / out_of_stock labels) ---
    {'path': '/api/content/product-statuses',                  'section': 'product-statuses', 'rule': _READ_ONLY},
    {'path': '/api/content/product-statuses/marker/{marker}',  'section': 'product-statuses', 'rule': _READ_ONLY},

    # --- Blocks (block metadata + recommendation endpoints) ---
    {'path': '/api/content/blocks',                                       'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/marker/{marker}',                       'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/quick/search',                          'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/products',                     'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/slides',                       'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/trending',                     'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/recently-viewed',              'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/repeat-purchase',              'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/personal-recommendations',     'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/cart-complement',              'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/cart-similar',                 'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/wishlist-similar',             'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/similar-products',             'section': 'blocks', 'rule': _READ_ONLY},
    {'path': '/api/content/blocks/{marker}/products/{productId}/frequently-ordered', 'section': 'blocks', 'rule': _READ_ONLY},

    # --- Attribute sets (for filter/card metadata rendering) ---
    {'path': '/api/content/attributes-sets',                                    'section': 'attributes-sets', 'rule': _READ_ONLY},
    {'path': '/api/content/attributes-sets/marker/{marker}',                    'section': 'attributes-sets', 'rule': _READ_ONLY},
    {'path': '/api/content/attributes-sets/{marker}/attributes',                'section': 'attributes-sets', 'rule': _READ_ONLY},
    {'path': '/api/content/attributes-sets/{marker}/attributes/{attributeMarker}', 'section': 'attributes-sets', 'rule': _READ_ONLY},

    # --- Filters (catalog facets) ---
    {'path': '/api/content/filters/marker/{marker}',      'section': 'filters', 'rule': _READ_ONLY},

    # --- Templates (block/page rendering) ---
    {'path': '/api/content/templates',                    'section': 'templates', 'rule': _READ_ONLY},
    {'path': '/api/content/templates/all',                'section': 'templates', 'rule': _READ_ONLY},
    {'path': '/api/content/templates/marker/{marker}',    'section': 'templates', 'rule': _READ_ONLY},
    {'path': '/api/content/template-previews',                'section': 'template-previews', 'rule': _READ_ONLY},
    {'path': '/api/content/template-previews/marker/{marker}','section': 'template-previews', 'rule': _READ_ONLY},

    # --- Forms (schema read + submission) ---
    {'path': '/api/content/forms',                       'section': 'forms',     'rule': _READ_ONLY},
    {'path': '/api/content/forms/marker/{marker}',       'section': 'forms',     'rule': _READ_ONLY},
    {'path': '/api/content/form-data',                   'section': 'form-data', 'rule': _WRITE_ONLY},
    {'path': '/api/content/form-data/{id}',              'section': 'form-data', 'rule': _READ_ONLY},
    {'path': '/api/content/form-data/marker/{marker}',   'section': 'form-data', 'rule': _READ_ONLY},
    {'path': '/api/content/form-data/{id}/update-status','section': 'form-data', 'rule': _WRITE_ONLY},

    # --- Auth providers (sign-up / sign-in / refresh / activate / change-password) ---
    {'path': '/api/content/users-auth-providers',                                          'section': 'users-auth-providers', 'rule': _READ_ONLY},
    {'path': '/api/content/users-auth-providers/marker/{marker}',                          'section': 'users-auth-providers', 'rule': _READ_ONLY},
    {'path': '/api/content/users-auth-providers/marker/{marker}/users/sign-up',            'section': 'users-auth-providers', 'rule': _WRITE_ONLY},
    {'path': '/api/content/users-auth-providers/marker/{marker}/users/auth',               'section': 'users-auth-providers', 'rule': _WRITE_ONLY},
    {'path': '/api/content/users-auth-providers/marker/{marker}/users/refresh',            'section': 'users-auth-providers', 'rule': _WRITE_ONLY},
    {'path': '/api/content/users-auth-providers/marker/{marker}/users/logout',             'section': 'users-auth-providers', 'rule': _WRITE_ONLY},
    {'path': '/api/content/users-auth-providers/marker/{marker}/users/activate',           'section': 'users-auth-providers', 'rule': _WRITE_ONLY},
    {'path': '/api/content/users-auth-providers/marker/{marker}/users/check-code',         'section': 'users-auth-providers', 'rule': _WRITE_ONLY},
    {'path': '/api/content/users-auth-providers/marker/{marker}/users/generate-code',      'section': 'users-auth-providers', 'rule': _WRITE_ONLY},
    {'path': '/api/content/users-auth-providers/marker/{marker}/users/change-password',    'section': 'users-auth-providers', 'rule': _WRITE_ONLY},

    # --- Own profile + cart + wishlist + fcm ---
    {'path': '/api/content/users/me',                              'section': 'users', 'rule': _READ_AND_UPDATE},
    {'path': '/api/content/users/me/cart',                         'section': 'users', 'rule': _READ_WRITE},
    {'path': '/api/content/users/me/cart/items',                   'section': 'users', 'rule': _READ_WRITE},
    {'path': '/api/content/users/me/cart/items/{productId}',       'section': 'users', 'rule': _READ_WRITE},
    {'path': '/api/content/users/me/wishlist',                     'section': 'users', 'rule': _READ_WRITE},
    {'path': '/api/content/users/me/wishlist/items',               'section': 'users', 'rule': _READ_WRITE},
    {'path': '/api/content/users/me/wishlist/items/{productId}',   'section': 'users', 'rule': _READ_WRITE},
    {'path': '/api/content/users/me/fcm-token/{token}',            'section': 'users', 'rule': _WRITE_ONLY},

    # --- User groups (read membership info — optional) ---
    {'path': '/api/content/user-groups/marker/{marker}',  'section': 'user-groups', 'rule': _READ_ONLY},
    {'path': '/api/content/user-groups/root',             'section': 'user-groups', 'rule': _READ_ONLY},

    # --- Orders (read own + create via orders-storage) ---
    {'path': '/api/content/orders',                                           'section': 'orders',          'rule': _READ_AND_ADD},
    {'path': '/api/content/orders/{id}',                                      'section': 'orders',          'rule': _READ_ONLY},
    {'path': '/api/content/orders/{id}/refund',                               'section': 'orders',          'rule': _WRITE_ONLY},
    {'path': '/api/content/orders-storage',                                   'section': 'orders-storage',  'rule': _READ_ONLY},
    {'path': '/api/content/orders-storage/marker/{marker}',                   'section': 'orders-storage',  'rule': _READ_ONLY},
    {'path': '/api/content/orders-storage/marker/{marker}/orders',            'section': 'orders-storage',  'rule': _READ_AND_ADD},
    {'path': '/api/content/orders-storage/marker/{marker}/orders/{id}',       'section': 'orders-storage',  'rule': _READ_AND_UPDATE},
    {'path': '/api/content/orders-storage/orders/preview',                    'section': 'orders-storage',  'rule': _WRITE_ONLY},

    # --- Payments (sessions + connected) ---
    {'path': '/api/content/payments/accounts',                'section': 'payments', 'rule': _READ_ONLY},
    {'path': '/api/content/payments/accounts/{id}',           'section': 'payments', 'rule': _READ_ONLY},
    {'path': '/api/content/payments/connected',               'section': 'payments', 'rule': _READ_ONLY},
    {'path': '/api/content/payments/sessions',                'section': 'payments', 'rule': _READ_AND_ADD},
    {'path': '/api/content/payments/sessions/{id}',           'section': 'payments', 'rule': _READ_ONLY},
    {'path': '/api/content/payments/sessions/order/{id}',     'section': 'payments', 'rule': _READ_ONLY},

    # --- Collections (FAQ, Stores, Brands, etc.) ---
    {'path': '/api/content/integration-collections',                                  'section': 'integration-collections', 'rule': _READ_ONLY},
    {'path': '/api/content/integration-collections/{id}',                             'section': 'integration-collections', 'rule': _READ_ONLY},
    {'path': '/api/content/integration-collections/{id}/rows',                        'section': 'integration-collections', 'rule': _READ_ONLY},
    {'path': '/api/content/integration-collections/marker-validation/{marker}',       'section': 'integration-collections', 'rule': _READ_ONLY},
    {'path': '/api/content/integration-collections/marker/{marker}/rows',             'section': 'integration-collections', 'rule': _READ_ONLY},
    {'path': '/api/content/integration-collections/marker/{marker}/rows/{id}',        'section': 'integration-collections', 'rule': _READ_ONLY},

    # --- Subscriptions (newsletter / event-based) ---
    {'path': '/api/content/subscriptions',                                    'section': 'subscriptions', 'rule': _READ_ONLY},
    {'path': '/api/content/subscriptions/active',                             'section': 'subscriptions', 'rule': _READ_ONLY},
    {'path': '/api/content/events/forms/subscribe/marker/{marker}',           'section': 'events',        'rule': _WRITE_ONLY},
    {'path': '/api/content/events/forms/unsubscribe/marker/{marker}',         'section': 'events',        'rule': _WRITE_ONLY},
    {'path': '/api/content/events/forms/subscriptions',                       'section': 'events',        'rule': _READ_ONLY},
    {'path': '/api/content/events/subscribe/marker/{marker}',                 'section': 'events',        'rule': _WRITE_ONLY},
    {'path': '/api/content/events/unsubscribe/marker/{marker}',               'section': 'events',        'rule': _WRITE_ONLY},
    {'path': '/api/content/events/subscriptions',                             'section': 'events',        'rule': _READ_ONLY},

    # --- General types (block type meta) ---
    {'path': '/api/content/general-types',                'section': 'general-types', 'rule': _READ_ONLY},

    # --- Locales (multi-language selector) ---
    {'path': '/api/content/locales/active/all',           'section': 'locales',           'rule': _READ_ONLY},

    # --- Global settings (storefront config) ---
    {'path': '/api/content/settings-general',             'section': 'settings-general',  'rule': _READ_ONLY},
    {'path': '/api/content/immutable-settings',           'section': 'immutable-settings','rule': _READ_ONLY},

    # --- Files (uploaded images / docs visible to customers) ---
    {'path': '/api/content/files',                        'section': 'files',             'rule': _READ_ONLY},

    # --- System (captcha validation when forms have CAPTCHA) ---
    {'path': '/api/content/system/captcha/validate',      'section': 'system',            'rule': _WRITE_ONLY},
]


# 5 fixed payment-status keys per `PaymentStatusMapDto`.
PAYMENT_STATUS_KEYS = ('waiting', 'partial', 'completed', 'canceled', 'expired')

# Keyword heuristics mapping each payment status key to candidate order-status
# identifiers (in priority order). Matching is case-insensitive substring.
# Order convention: payment waits → order is just created; payment partial →
# order is being processed; payment completed → order is also "paid/processing";
# payment canceled or expired → order is cancelled.
PAYMENT_TO_ORDER_HEURISTIC = {
    'waiting':   ('new', 'pending', 'created', 'awaiting'),
    'partial':   ('processing', 'in_progress', 'progress', 'paying', 'partial'),
    # `completed` payment means the customer has paid in full → the order is
    # ready to fulfil ("done"). If `done` is not present, fall back to `paid` /
    # `completed` / `processing` / `confirmed`.
    'completed': ('done', 'completed', 'paid', 'confirmed', 'processing'),
    'canceled':  ('cancelled', 'canceled', 'cancel'),
    'expired':   ('expired', 'cancelled', 'canceled'),
}


def _pick_order_status(payment_key, available_status_idents):
    """Return the best-matching order_status identifier for `payment_key`, or None."""
    if not available_status_idents:
        return None
    lowered = [(s, s.lower()) for s in available_status_idents]
    for kw in PAYMENT_TO_ORDER_HEURISTIC.get(payment_key, ()):
        kw_l = kw.lower()
        for original, low in lowered:
            if low == kw_l:
                return original
        for original, low in lowered:
            if kw_l in low or low in kw_l:
                return original
    return None


# File-name / route-segment patterns that signal an order or booking subsystem.
# Universal across project types:
#   - e-commerce:  cart, checkout, order, payment
#   - restaurant:  reservation, booking, delivery
#   - salon:       appointment, booking
#   - SaaS:        subscription, plan, billing
# Any of these → orders_storage is needed.
_ORDER_SIGNAL_BASENAMES = (
    'cart', 'checkout', 'order', 'orders',
    'payment', 'payments', 'checkoutconfig',
    'reservation', 'reservations', 'booking', 'bookings',
    'appointment', 'appointments', 'reserve',
    'subscription', 'subscriptions', 'billing',
)


def _has_checkout_signals(project_root):
    """Return True if the source has any order / cart / booking / subscription evidence.

    Universal across stacks: Next.js (`app/checkout/page.tsx`), Vue/Nuxt
    (`pages/checkout.vue`), React (`pages/Cart.jsx`), Angular
    (`booking.component.ts`), etc. Checks file basenames (case-insensitive)
    rather than full paths.
    """
    project_root = Path(project_root) if project_root else None
    if project_root is None or not project_root.exists():
        return False
    skip_dirs = {'node_modules', '.next', '.git', 'dist', 'build', '.turbo',
                 '.cache', '.svelte-kit', '.output', '.parcel-cache',
                 'storybook-static', 'playwright-report'}
    for path in project_root.rglob('*'):
        if not path.is_file():
            continue
        if any(part in skip_dirs or part.startswith('.') for part in path.relative_to(project_root).parts):
            continue
        if path.suffix not in ('.ts', '.tsx', '.js', '.jsx', '.vue', '.svelte', '.mjs'):
            continue
        # Strip the suffix and check against the basename pool.
        stem = path.stem.lower().replace('-', '').replace('_', '')
        if any(sig in stem for sig in _ORDER_SIGNAL_BASENAMES):
            return True
    return False


def ensure_orders_subsystem(data, project_root, languages):
    """Safety net for orders_storage + standard order_statuses.

    If `mapped` does not declare any orders_storage / order_statuses but the
    project clearly has a checkout flow (cart page, PaymentPage, checkoutConfig),
    emit the standard 1 storage + 4 statuses. Without this, the downstream
    `generate_payment_status_maps()` cannot build the admin payment-status
    mapping.

    Idempotent: no-op when `orders_storage` is already non-empty.
    """
    fixes = []
    if data.get('orders_storage'):
        return fixes
    if not _has_checkout_signals(project_root):
        return fixes

    primary_lang = languages[0] if languages else 'en_US'

    # Pick an "order" form if mapper produced one; otherwise fall back to signin.
    forms = data.get('forms') or []
    order_form_ident = next(
        (f.get('identifier') for f in forms if f.get('type') == 'order'),
        None,
    )
    fallback_form_ident = order_form_ident or next(
        (f.get('identifier') for f in forms
         if f.get('type') in ('sing_in_up', 'signin') or f.get('identifier') == 'signin'),
        'signin',
    )

    data['orders_storage'] = [{
        'identifier':           'default',
        'general_type_marker':  'order',
        'general_type_id':      21,  # STABLE — `update-general-types.ts:20`
        'form':                 fallback_form_ident,
        'price_expiration':     '10m',
        'localize_infos':       {primary_lang: {'title': 'Default storage'}},
    }]
    data['order_statuses'] = [
        {'identifier': 'new',        'storage': 'default', 'is_default': True,
         'localize_infos': {primary_lang: {'title': 'New'}}},
        {'identifier': 'processing', 'storage': 'default', 'is_default': False,
         'localize_infos': {primary_lang: {'title': 'Processing'}}},
        {'identifier': 'done',       'storage': 'default', 'is_default': False,
         'localize_infos': {primary_lang: {'title': 'Done'}}},
        {'identifier': 'cancelled',  'storage': 'default', 'is_default': False,
         'localize_infos': {primary_lang: {'title': 'Cancelled'}}},
    ]

    fixes.append(
        "+ orders_storage 'default' (general_type_id=21 'order') + 4 standard "
        "order_statuses (new/processing/done/cancelled) — SAFETY NET (mapper "
        "skipped the orders subsystem despite checkout signals)"
    )
    warnings_list = data.setdefault('warnings', [])
    warnings_list.append(
        "orders_storage was generated by post-mapper-fixer safety net — "
        "mapper should emit it explicitly (see standard-entities.md → "
        "'orders_storage + order_statuses')."
    )
    return fixes


def generate_payment_status_maps(data):
    """Build `mapped.post_import_payment_status_maps[]` — one task per orders_storage.

    The post-import-orchestrator (Step 9) executes `PUT /api/admin/payments/status-maps`
    for each entry. Idempotent: if the task list is already present, no-op.
    """
    fixes = []
    if data.get('post_import_payment_status_maps'):
        return fixes  # idempotent — already populated by a prior run

    storages = data.get('orders_storage') or []
    statuses = data.get('order_statuses') or []
    if not storages or not statuses:
        return fixes  # no storages or no order_statuses — nothing to map

    tasks = []
    for storage in storages:
        storage_ident = storage.get('identifier')
        if not storage_ident:
            continue
        storage_token = storage.get('id') or f'@storage.{storage_ident}'
        # Order statuses belonging to this storage (by storage_id / order_storage / storage token)
        ours = []
        for st in statuses:
            st_storage = st.get('storage_id') or st.get('order_storage') or st.get('storage')
            if st_storage in (storage_token, storage_ident):
                ours.append(st.get('identifier'))
        ours = [i for i in ours if i]
        if not ours:
            continue
        status_map = {}
        for payment_key in PAYMENT_STATUS_KEYS:
            matched = _pick_order_status(payment_key, ours)
            if matched:
                status_map[payment_key] = matched
        if not status_map:
            continue
        tasks.append({
            'orders_storage':           storage_ident,
            'orders_storage_token':     storage_token,
            'status_map':               status_map,
        })

    if tasks:
        data['post_import_payment_status_maps'] = tasks
        total_pairs = sum(len(t['status_map']) for t in tasks)
        fixes.append(
            f"+ post_import_payment_status_maps: {len(tasks)} storages, "
            f"{total_pairs} payment-status <-> order-status pairs"
        )
        warnings_list = data.setdefault('warnings', [])
        warnings_list.append(
            f"out-of-whitelist-needs-post-import: {len(tasks)} payment_status_maps "
            f"(for {', '.join(t['orders_storage'] for t in tasks)}). Created via "
            f"PUT /api/admin/payments/status-maps after blueprint import "
            f"(see post-import-orchestration.md Step 9)."
        )

    return fixes


# Anti-pattern keys that must NOT land in product attributes_sets (live elsewhere).
_PRODUCT_FIELD_BLOCKLIST = {
    'salePrice', 'sale_price', 'discountPrice', 'discount_price',
    'originalPrice', 'original_price',
    'colorImages', 'color_images', 'colorStock', 'color_stock',
    'sizeStock', 'size_stock',
    'reviews', 'review',  # nested user-generated content — out of catalog scope
    'galleryImages', 'productDetails', 'specs',  # heavy nested objects/arrays — TODO: separate handler
}

# camelCase -> snake_case for OneEntry identifiers.
_CAMEL_RE = re.compile(r'([A-Z])')


def _camel_to_snake(name):
    return _CAMEL_RE.sub(lambda m: '_' + m.group(1).lower(), name).lstrip('_')


def _strip_dollar(v):
    """`'$45.50'` → `45.5`, `'89'` → 89, other strings pass through."""
    if isinstance(v, str) and v.startswith('$'):
        try:
            return float(v[1:].replace(',', ''))
        except ValueError:
            return v
    return v


def _find_balanced(text, open_ch, close_ch, start_pos):
    """Return index AFTER the matching close_ch starting from text[start_pos]==open_ch.

    Respects nesting and skips contents of quoted strings.
    """
    if text[start_pos] != open_ch:
        return -1
    depth = 0
    i = start_pos
    n = len(text)
    while i < n:
        ch = text[i]
        if ch in ("'", '"'):
            quote = ch
            i += 1
            while i < n:
                if text[i] == '\\':
                    i += 2
                    continue
                if text[i] == quote:
                    i += 1
                    break
                i += 1
            continue
        if ch == open_ch:
            depth += 1
        elif ch == close_ch:
            depth -= 1
            if depth == 0:
                return i + 1
        i += 1
    return -1


def _split_product_objects(arr_body):
    """Yield each `{...}` product-object substring from an array body.

    Skips nested `{...}` inside the object (e.g. specs[{label,value}]).
    """
    n = len(arr_body)
    i = 0
    while i < n:
        if arr_body[i] != '{':
            i += 1
            continue
        end = _find_balanced(arr_body, '{', '}', i)
        if end < 0:
            return
        yield arr_body[i:end]
        i = end


_KEY_RE = re.compile(r"\s*([A-Za-z_][A-Za-z0-9_]*)\s*:\s*", re.DOTALL)


def _parse_object_top_level(obj_body):
    """Parse `{ ... }` and return dict of scalar / string-array top-level fields.

    Skips nested objects, arrays of objects, and unparseable values. obj_body
    is the substring including the outer braces.
    """
    if obj_body.startswith('{'):
        body = obj_body[1:-1]
    else:
        body = obj_body
    result = {}
    pos = 0
    n = len(body)
    while pos < n:
        # Skip whitespace, comments, commas
        while pos < n and body[pos] in ' \t\n\r,':
            pos += 1
        if pos < n and body[pos:pos+2] == '//':
            nl = body.find('\n', pos)
            pos = nl + 1 if nl >= 0 else n
            continue
        if pos < n and body[pos:pos+2] == '/*':
            end = body.find('*/', pos)
            pos = end + 2 if end >= 0 else n
            continue
        m = _KEY_RE.match(body, pos)
        if not m:
            break
        key = m.group(1)
        vstart = m.end()
        if vstart >= n:
            break
        ch = body[vstart]
        if ch == '{':
            end = _find_balanced(body, '{', '}', vstart)
            pos = end if end > 0 else n
            continue  # nested object — skip
        if ch == '[':
            end = _find_balanced(body, '[', ']', vstart)
            if end < 0:
                break
            inner = body[vstart+1:end-1].strip()
            if inner.startswith('{'):
                pos = end
                continue  # array of objects — skip
            items = []
            ipos = 0
            in_n = len(inner)
            bad = False
            while ipos < in_n:
                while ipos < in_n and inner[ipos] in ' \t\n\r,':
                    ipos += 1
                if ipos >= in_n:
                    break
                ich = inner[ipos]
                if ich in ("'", '"'):
                    quote = ich
                    iend = ipos + 1
                    while iend < in_n:
                        if inner[iend] == '\\':
                            iend += 2
                            continue
                        if inner[iend] == quote:
                            break
                        iend += 1
                    items.append(inner[ipos+1:iend])
                    ipos = iend + 1
                elif ich in '-0123456789':
                    iend = ipos
                    while iend < in_n and inner[iend] not in ' \t\n\r,':
                        iend += 1
                    try:
                        items.append(float(inner[ipos:iend]))
                    except ValueError:
                        bad = True
                        break
                    ipos = iend
                else:
                    bad = True
                    break
            if not bad:
                result[key] = items
            pos = end
            continue
        if ch in ("'", '"'):
            quote = ch
            iend = vstart + 1
            while iend < n:
                if body[iend] == '\\':
                    iend += 2
                    continue
                if body[iend] == quote:
                    break
                iend += 1
            result[key] = body[vstart+1:iend]
            pos = iend + 1
            continue
        # number / true / false / null / identifier expression
        iend = vstart
        while iend < n and body[iend] not in ',}\n':
            iend += 1
        raw = body[vstart:iend].strip()
        if raw == 'true':
            result[key] = True
        elif raw == 'false':
            result[key] = False
        elif raw == 'null':
            result[key] = None
        else:
            try:
                if '.' in raw and any(c.isdigit() for c in raw):
                    # Heuristic: only treat as float if at least one digit, otherwise
                    # `heroSlide1.src` would parse to a (wrong) float.
                    raise ValueError
                if '.' in raw:
                    result[key] = float(raw)
                else:
                    result[key] = int(raw)
            except ValueError:
                # Non-string identifier expression (e.g. `heroSlide1.src`, imported
                # asset). Record as a string placeholder so downstream still sees
                # the field; admin can replace the asset path later.
                if raw and re.fullmatch(r'[A-Za-z_$][\w$.\[\]'']*', raw):
                    result[key] = raw
        pos = iend
    return result


_PRODUCT_ARR_HEADER_RE = re.compile(
    r"export\s+const\s+[A-Z_][A-Z0-9_]*\s*:\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*)?(?:\[\s*\])\s*=\s*\[",
    re.MULTILINE,
)


def _parse_product_files(project_root):
    """Walk product-data files, return list of dicts: one per product object.

    Each dict carries `_source_file` for downstream routing.
    """
    project_root = Path(project_root)
    products = []
    seen_files = set()
    for glob in _PRODUCT_DATA_GLOBS:
        for path in sorted(project_root.glob(glob)):
            if path in seen_files or not path.is_file():
                continue
            seen_files.add(path)
            try:
                text = path.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            # Find each `export const SOMETHING: ...[] = [` array
            for m in _PRODUCT_ARR_HEADER_RE.finditer(text):
                bracket_pos = text.rfind('[', 0, m.end())
                if bracket_pos < 0:
                    continue
                arr_end = _find_balanced(text, '[', ']', bracket_pos)
                if arr_end < 0:
                    continue
                arr_body = text[bracket_pos+1:arr_end-1]
                for obj_body in _split_product_objects(arr_body):
                    parsed = _parse_object_top_level(obj_body)
                    # Heuristic: a product object must have a string `id` like 'wc-1'
                    pid = parsed.get('id')
                    if not isinstance(pid, str) or not re.fullmatch(r'[a-z]+-[0-9a-z\-]+', pid):
                        continue
                    # Filter out non-product entries that share the `id`-pattern:
                    # filter chips (only `label`+`chip`), stores (`address`/`mapUrl`),
                    # special-offer bundles (`originalPrice`+`bundlePrice` only),
                    # navigation records, etc. A real product carries a `price`
                    # field (the universal e-commerce signal).
                    if 'price' not in parsed:
                        continue
                    parsed['_source_file'] = str(path.relative_to(project_root))
                    products.append(parsed)
    return products


# Identifier aliases — keys in source -> identifier used in attribute_set schema.
_ATTRIBUTE_KEY_ALIASES = {
    'name':           'title',
    'image':          'preview',
    # camelCase -> snake_case happens before this map
    'gallery_images': 'gallery',
    'in_stock':       'in_stock',
}


def _route_product_keys(raw):
    """Convert raw source-key/value dict to {attribute_identifier: value} dict.

    Filters out anti-pattern keys, renames camelCase → snake_case + applies aliases,
    and parses `$N.NN` price strings into floats.
    """
    out = {}
    for k, v in raw.items():
        if k.startswith('_'):
            continue
        if k in _PRODUCT_FIELD_BLOCKLIST:
            continue
        snake = _camel_to_snake(k)
        if snake in _PRODUCT_FIELD_BLOCKLIST:
            continue
        ident = _ATTRIBUTE_KEY_ALIASES.get(snake, snake)
        if ident in ('id',):
            continue
        if ident == 'price':
            v = _strip_dollar(v)
        out[ident] = v
    return out


def _canonical_key(key):
    """Universal canonical normalization for attribute key matching.
    `galleryImages`, `Gallery Images`, `GALLERY_IMAGES`, `gallery-images` → all
    become `gallery_images`. See rules/mapper-source-extraction.md §1.5.1.
    """
    import re as _re
    if not isinstance(key, str):
        return ''
    # Split camelCase only when a lowercase/digit precedes an uppercase letter
    # ("galleryImages" → "gallery_Images"). Avoids splitting ALL_CAPS strings.
    s = _re.sub(r'([a-z0-9])([A-Z])', r'\1_\2', key)
    # Also split ABBRevWord: HTTPRequest → HTTP_Request
    s = _re.sub(r'([A-Z]+)([A-Z][a-z])', r'\1_\2', s)
    s = _re.sub(r'[-\s\.]+', '_', s)
    s = s.lower().strip('_')
    s = _re.sub(r'_+', '_', s)
    return s


_UNIVERSAL_SYNONYMS = {
    # concept → canonical schema identifier hint (only the absolutely universal cases)
    'id': 'sku', 'code': 'sku', 'slug': 'sku', 'key': 'sku', 'uid': 'sku',
    'name': 'title', 'label': 'title', 'caption': 'title', 'heading': 'title',
    'desc': 'description', 'details': 'description', 'body': 'description',
    'content': 'description', 'about': 'description', 'info': 'description',
    'cost': 'price', 'amount': 'price',
    'img': 'image', 'photo': 'image', 'picture': 'image',
    'thumbnail': 'preview', 'cover': 'preview', 'preview_image': 'preview',
    'photos': 'gallery', 'pictures': 'gallery', 'media': 'gallery',
    'images': 'gallery', 'gallery_images': 'gallery',
    'link': 'href', 'url': 'href', 'route': 'href',
}


def _match_source_to_schema(src_key, schema_ids):
    """Step 1.5.2 — token-set comparison. Returns matching schema identifier
    or None. Pure-structural, vertical-agnostic.
    Priority: exact > universal-synonym > schema-subset-of-source > etc.
    """
    if not isinstance(src_key, str):
        return None
    src_c = _canonical_key(src_key)
    # 0. Universal synonym hint — rewrite src to canonical concept first
    src_aliased = _UNIVERSAL_SYNONYMS.get(src_c, src_c)
    schema_canon = {sid: _canonical_key(sid) for sid in schema_ids}
    # 1. Exact match
    for sid, sc in schema_canon.items():
        if sc == src_aliased or sc == src_c:
            return sid
    # 2. Plural normalization (strip trailing s/es/ies on each token)
    def _depluralize(tokens):
        out = []
        for t in tokens:
            if t.endswith('ies') and len(t) > 3:
                out.append(t[:-3] + 'y')
            elif t.endswith('es') and len(t) > 2:
                out.append(t[:-2])
            elif t.endswith('s') and len(t) > 1:
                out.append(t[:-1])
            else:
                out.append(t)
        return tuple(out)
    src_tokens = tuple(src_c.split('_'))
    src_tokens_dp = _depluralize(src_tokens)
    for sid, sc in schema_canon.items():
        sc_tokens = tuple(sc.split('_'))
        if _depluralize(sc_tokens) == src_tokens_dp:
            return sid
    # 3. Schema ⊆ source — schema identifier is a subset of source
    candidates = []
    for sid, sc in schema_canon.items():
        sc_tokens = set(sc.split('_'))
        if sc_tokens and sc_tokens.issubset(set(src_tokens)):
            candidates.append((sid, len(sc_tokens)))
    if candidates:
        # 4. Disambiguation — longer schema id wins (more specific)
        candidates.sort(key=lambda x: -x[1])
        return candidates[0][0]
    # 5. Source ⊆ schema
    candidates = []
    for sid, sc in schema_canon.items():
        sc_tokens = set(sc.split('_'))
        if set(src_tokens).issubset(sc_tokens) and src_tokens:
            candidates.append((sid, -len(sc_tokens)))
    if candidates:
        candidates.sort(key=lambda x: x[1])
        return candidates[0][0]
    # 6. Single-word substring (for short keys)
    if len(src_tokens) == 1:
        for sid, sc in schema_canon.items():
            sc_tokens = sc.split('_')
            if len(sc_tokens) == 1 and (src_c in sc or sc in src_c):
                return sid
    return None


def _parse_all_arrays_in_file(file_path):
    """Parse ALL `export const X = [...]` arrays in a TS/JS file and merge
    their contents into one flat list. Many real projects split products
    across multiple exports per category (MEN_BELTS_PRODUCTS,
    MEN_WALLETS_PRODUCTS, …). `parse_data_file` returns only the first
    array — this helper sweeps the whole file.
    """
    import re as _re
    try:
        text = Path(file_path).read_text()
    except Exception:
        return []
    text_clean = _re.sub(r'/\*[\s\S]*?\*/', '', text)
    sym_key = str(file_path)
    if sym_key in _TS_SYMBOL_TABLE_CACHE:
        symbols = _TS_SYMBOL_TABLE_CACHE[sym_key]
    else:
        symbols = _build_ts_symbol_table(text_clean)
        _TS_SYMBOL_TABLE_CACHE[sym_key] = symbols
    out = []
    # Find every export const X = [
    for m in _re.finditer(
        r'export\s+(?:default\s+)?const\s+(\w+)(?:\s*:\s*[\w\[\]<>,\s|]+)?\s*=\s*\[',
        text_clean,
    ):
        arr_src = _extract_balanced_array(text_clean, m.end() - 1)
        if not arr_src:
            continue
        arr_body = arr_src.lstrip()
        if arr_body.startswith('['):
            arr_body = arr_body[1:]
        if arr_body.endswith(']'):
            arr_body = arr_body[:-1]
        try:
            for obj_body in _split_product_objects(arr_body):
                parsed = _parse_object_top_level(obj_body)
                if parsed:
                    out.append(parsed)
        except Exception:
            continue
    if symbols and out:
        out = _resolve_expressions_recursively(out, symbols)
    return out


def _discover_data_files(project_root):
    """Recursive discovery of all source data files in a project. Returns a
    list of (file_path, parsed_content) tuples where parsed_content is either
    a list of dicts or a dict (keyed by id).
    Path-agnostic, multi-extension, multi-format.
    """
    import json as _json
    from pathlib import Path as _Path
    root = _Path(project_root)
    if not root.exists():
        return []
    out = []
    EXTS = {'.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs', '.json'}
    REJECT_DIRS = {'node_modules', '.next', 'dist', 'build', '.git',
                   '__tests__', '__mocks__', '.cache', 'coverage'}
    for f in root.rglob('*'):
        if not f.is_file() or f.suffix not in EXTS:
            continue
        if any(part in REJECT_DIRS for part in f.parts):
            continue
        # Skip configs/tests
        if f.name in ('package.json', 'tsconfig.json', '.eslintrc.json'):
            continue
        if '.spec.' in f.name or '.test.' in f.name:
            continue
        try:
            if f.suffix == '.json':
                content = _json.loads(f.read_text())
                if isinstance(content, (list, dict)) and content:
                    out.append((f, content))
                continue
            # Use multi-export parser — many TS files split products across
            # several `export const X = [...]` arrays (one per category).
            parsed = _parse_all_arrays_in_file(f)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                if len(parsed) >= 1:
                    out.append((f, parsed))
                continue
            # Fallback: single-array / single-object form
            parsed = parse_data_file(f)
            if isinstance(parsed, list) and parsed and isinstance(parsed[0], dict):
                if len(parsed) >= 1:
                    out.append((f, parsed))
        except Exception:
            continue
    return out


def deep_extract_attributes_from_source(data, project_root, languages):
    """Deterministic deep extraction — guarantees every source attribute
    matchable via Step 1.5 algorithm gets emitted into `attributes_sets[lang]`.

    Independent of (and runs after) the LLM mapper, so the result is
    reproducible: same source files + same schemas → always the same blueprint.

    Universal: path-agnostic file discovery + vertical-agnostic key matching.
    """
    fixes = []
    if not project_root:
        return fixes
    lang = languages[0] if languages else 'en_US'
    products = data.get('products') or []
    blocks = data.get('blocks') or []
    asets = {a.get('identifier'): a for a in (data.get('attributes_sets') or [])
             if a.get('identifier')}
    if not (products or blocks) or not asets:
        return fixes

    # Discover all data files once
    discovered = _discover_data_files(project_root)
    if not discovered:
        return fixes

    # Build identifier → source row index across all discovered files.
    # Universal: we index by FOUR independent keys so any of them can match
    # a downstream block/product identifier:
    #   1. The row's explicit `id` / `sku` / `slug` / `code` / `identifier`
    #      / `key` field (typical for product/menu-item arrays).
    #   2. The Record outer key when source is `Record<key, dict>` (typical
    #      for grouped catalogs / mega menus / category dicts).
    #   3. The exported constant name slugified (e.g. `DISCOUNT_BANNER` →
    #      `discount_banner`) for single-object exports without an id field
    #      (typical for hero/banner/site-config singletons).
    #   4. The file stem slugified (e.g. `banners.ts` → `banners`) as a
    #      last-resort fallback.
    src_by_id = {}
    for _path, content in discovered:
        stem_slug = _canonical_key(_path.stem)
        # 1. Find ALL exported const names in this file (we use them as
        #    fallback identifiers for single-object exports that don't carry
        #    an `id` field). Regex-only — no body parsing — so it's robust
        #    against TS strings with apostrophes etc.
        try:
            text = _path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            text = ''
        const_names = [m.group(1) for m in re.finditer(
            r'export\s+(?:default\s+)?const\s+([A-Z_][\w]*)\s*[=:]', text
        )]
        # 2. Index by file stem (banners.ts → 'banners') for single-dict
        #    exports — when the file holds ONE top-level object the stem is
        #    often the most natural lookup key. If the dict is actually a
        #    Record<key, dict> (2+ keys, all values dicts) then iterate INTO
        #    it so each inner key becomes its own indexed entry.
        if isinstance(content, list) and len(content) == 1 and isinstance(content[0], dict):
            top = content[0]
            inner_dicts = [(k, v) for k, v in top.items() if isinstance(v, dict)]
            is_record_of_dicts = len(inner_dicts) >= 2 and len(inner_dicts) == len(top)
            if is_record_of_dicts:
                # Treat as Record — iterate each (key → child) pair
                for k, v in inner_dicts:
                    src_by_id.setdefault(k, v)
                    ck = _canonical_key(k)
                    if ck and ck != k:
                        src_by_id.setdefault(ck, v)
            else:
                # Single content object — key by stem + const name(s)
                src_by_id.setdefault(stem_slug, top)
                for cn in const_names:
                    src_by_id.setdefault(_canonical_key(cn), top)
        # 3. Index by every row's own id field (typical for product arrays).
        #    For each candidate key we store BOTH the original (raw) form
        #    and its canonicalized snake_case form — that way downstream
        #    block-identifier matching works regardless of source style
        #    (camelCase `newArrivals` ↔ snake_case `new_arrivals`).
        def _put(key, value):
            if not isinstance(key, str) or not key:
                return
            src_by_id.setdefault(key, value)
            ck = _canonical_key(key)
            if ck and ck != key:
                src_by_id.setdefault(ck, value)
        if isinstance(content, list):
            for item in content:
                if not isinstance(item, dict):
                    continue
                for k in ('id', 'sku', 'slug', 'code', 'identifier', 'key'):
                    v = item.get(k)
                    if isinstance(v, str) and v:
                        _put(v, item)
                        break
        elif isinstance(content, dict):
            for k, v in content.items():
                if isinstance(v, dict):
                    _put(k, v)
                    if 'id' not in v:
                        v['id'] = k

    def _flatten_specs(item):
        """Flatten specs/attributes/features array into top-level keys.
        Source: [{label:'Material', value:'Leather'}] → {Material: 'Leather'}.
        Returns a new dict merged with item's own keys (specs values win when
        conflict — they're more authoritative metadata)."""
        out = dict(item)
        for nested_key in ('specs', 'attributes', 'features', 'properties', 'details'):
            arr = item.get(nested_key)
            if not isinstance(arr, list):
                continue
            for entry in arr:
                if not isinstance(entry, dict):
                    continue
                label = entry.get('label') or entry.get('name') or entry.get('key')
                value = entry.get('value') or entry.get('val')
                if label and value is not None:
                    out.setdefault(label, value)
        return out

    SKIP_KEYS = {'id', 'sku', '_id', '__typename', 'version', 'createdAt',
                 'updatedAt', 'lastModified', 'reviews', 'relatedProducts',
                 'options', 'specs', 'attributes', 'features', 'properties',
                 'details'}

    def _enrich_entity(entity, aset):
        """Match source-row keys to schema identifiers and emit into entity's
        attributes_sets[lang]. Returns count of filled fields."""
        ident = entity.get('identifier')
        if not ident:
            return 0
        # Try direct lookup, then canonical (camelCase/snake/Title → canonical)
        src = src_by_id.get(ident)
        if not src:
            src = src_by_id.get(_canonical_key(ident))
        # Try plural↔singular and common synonyms
        if not src:
            canon = _canonical_key(ident)
            variants = {canon}
            if canon.endswith('s'):  variants.add(canon[:-1])
            else:                    variants.add(canon + 's')
            if canon.endswith('y'):  variants.add(canon[:-1] + 'ies')
            for v in variants:
                if v in src_by_id:
                    src = src_by_id[v]
                    break
        # Token-overlap match — block identifier may have extra/missing tokens
        # (e.g. block `discount_banner` ↔ source `DISCOUNT_BANNER`,
        # block `hero_slider` ↔ source `HERO_SLIDES`).
        if not src:
            canon = _canonical_key(ident)
            tokens = set(canon.split('_'))
            best = (0, None)
            for k, v in src_by_id.items():
                if not isinstance(v, dict):
                    continue
                kt = set(k.split('_'))
                overlap = len(tokens & kt)
                if overlap >= max(1, len(tokens) - 1) and overlap > best[0]:
                    best = (overlap, v)
            src = best[1]
        # Transitive component → import → data lookup. Universal across
        # stacks: many real projects name their COMPONENT after the block
        # but the actual data lives in a separately-named export
        # (e.g. component `MenCollection` imports `SECTION_TITLES.bestSellers`).
        # We find the component file by name-fuzzy match, scan its imports,
        # pick the first matching dict key from any imported data file.
        if not src and discovered:
            canon = _canonical_key(ident)
            # 1. Find component file by stem similarity
            comp_paths = []
            for path, _ in discovered:
                if _canonical_key(path.stem) == canon:
                    comp_paths.append(path)
            # Also look for non-data component files (often outside `data/`)
            try:
                from pathlib import Path as _P
                root = _P(project_root)
                for path in root.rglob('*'):
                    if not path.is_file():
                        continue
                    if path.suffix not in ('.tsx', '.jsx'):
                        continue
                    if _canonical_key(path.stem) == canon:
                        comp_paths.append(path)
                        break
            except Exception:
                pass
            # 2. Scan the component's imports for data files and use their dicts
            for cp in comp_paths[:3]:
                try:
                    ctext = cp.read_text(encoding='utf-8', errors='ignore')
                except OSError:
                    continue
                import_idents = []
                for m in re.finditer(
                    r"import\s*\{([^}]+)\}\s*from\s*['\"][^'\"]+['\"]",
                    ctext,
                ):
                    for name in m.group(1).split(','):
                        name = name.strip().split(' as ')[0].strip()
                        if name:
                            import_idents.append(name)
                # Score every src_by_id entry by which imports reference it
                for imp in import_idents:
                    cs = _canonical_key(imp)
                    if cs in src_by_id and isinstance(src_by_id[cs], dict):
                        src = src_by_id[cs]
                        break
                if src:
                    break
        if not src:
            return 0
        schema = (aset or {}).get('schema') or {}
        # Build {identifier → (innerId, type)} — mirror logic in
        # transform_attribute_data_to_admin_shape._schema_id_map.
        schema_meta = {}
        schema_idents = []
        for idx, (_k, item) in enumerate(schema.items(), start=1):
            if not isinstance(item, dict):
                continue
            sid = item.get('identifier')
            atype = item.get('type')
            inner_id = item.get('id') if item.get('id') is not None else idx
            if sid:
                schema_idents.append(sid)
                if atype:
                    schema_meta[sid] = (int(inner_id), atype)
        src_flat = _flatten_specs(src)
        attrs = entity.setdefault('attributes_sets', None)
        if not isinstance(attrs, dict):
            attrs = {}
            entity['attributes_sets'] = attrs
        lang_data = attrs.get(lang)
        if not isinstance(lang_data, dict):
            lang_data = {}
            attrs[lang] = lang_data
        filled = 0
        for src_key, src_value in src_flat.items():
            if src_key in SKIP_KEYS:
                continue
            schema_id = _match_source_to_schema(src_key, schema_idents)
            if not schema_id:
                continue
            # Check BOTH semantic and shaped (<type>_id<N>) forms. The mapper
            # may have already populated either one.
            meta = schema_meta.get(schema_id)
            shaped_key = f"{meta[1]}_id{meta[0]}" if meta else None
            existing_sem = lang_data.get(schema_id)
            existing_shp = lang_data.get(shaped_key) if shaped_key else None
            non_empty = lambda v: v not in (None, '', [], {})
            if non_empty(existing_sem) or non_empty(existing_shp):
                continue
            # Write under the SHAPED key directly when type metadata is known —
            # avoids transform_attribute_data_to_admin_shape silently dropping
            # the value when both keys coexist (it prefers the shaped one).
            target_key = shaped_key or schema_id
            lang_data[target_key] = src_value
            filled += 1
        return filled

    products_enriched = 0
    blocks_enriched = 0
    total_fields = 0
    for p in products:
        aset_ident = p.get('attribute_set')
        aset = asets.get(aset_ident) if aset_ident else None
        if not aset:
            continue
        n = _enrich_entity(p, aset)
        if n:
            products_enriched += 1
            total_fields += n
    for b in blocks:
        aset_ident = b.get('attribute_set')
        aset = asets.get(aset_ident) if aset_ident else None
        if not aset:
            continue
        n = _enrich_entity(b, aset)
        if n:
            blocks_enriched += 1
            total_fields += n

    if total_fields:
        fixes.append(
            f"+ deep-extract: {total_fields} attribute values from source "
            f"({products_enriched} products, {blocks_enriched} blocks) — "
            f"deterministic Step-1.5 token matching"
        )
    return fixes


def enrich_product_data(data, project_root, languages):
    """Safety net: ensure every product in source ends up in `mapped.products[]`
    with FULL `attributes_sets` populated, and that the matching forProducts_*
    attribute_set's `schema` is extended to cover every observed attribute with
    `type: list` + populated `listTitles` for categorical strings.

    Runs even when the mapper produced a sample-only product set. Idempotent.
    """
    fixes = []
    if not project_root or not Path(project_root).exists():
        return fixes
    primary_lang = languages[0] if languages else 'en_US'

    source_products = _parse_product_files(project_root)
    if not source_products:
        return fixes

    # Index existing mapped products by identifier.
    mapped_products = data.setdefault('products', [])
    by_ident = {p.get('identifier'): p for p in mapped_products if p.get('identifier')}

    # Index existing attribute_sets by identifier.
    asets = data.setdefault('attributes_sets', [])
    aset_by_ident = {a.get('identifier'): a for a in asets if a.get('identifier')}

    # Pick a default forProducts set name when none is decided yet.
    default_aset = None
    for cand in ('forProducts', 'forProducts_default'):
        if cand in aset_by_ident:
            default_aset = cand
            break
    if default_aset is None and asets:
        for a in asets:
            ident = a.get('identifier') or ''
            if ident.startswith('forProducts'):
                default_aset = ident
                break
    default_aset = default_aset or 'forProducts'

    def pick_aset_for_source_file(src_file):
        low = src_file.lower()
        for kind in ('clothing', 'shoes', 'bags', 'accessories'):
            if kind in low and f'forProducts_{kind}' in aset_by_ident:
                return f'forProducts_{kind}'
        return default_aset

    # ─── Add missing products / enrich attributes_sets ───────────────────────
    added = enriched = 0
    # Accumulate per-aset attribute observations: { aset: { ident: set(values) } }
    observed = {}
    # Per-aset: detected arrays-of-strings (-> type:list with multi-select)
    array_attrs = {}

    for sp in source_products:
        ident = sp.get('id')
        aset_ident = pick_aset_for_source_file(sp.get('_source_file', ''))
        attrs = _route_product_keys(sp)

        # Track per-aset observations for schema enrichment.
        obs = observed.setdefault(aset_ident, {})
        arrs = array_attrs.setdefault(aset_ident, set())
        for k, v in attrs.items():
            if isinstance(v, list):
                arrs.add(k)
                for item in v:
                    if isinstance(item, str) and item:
                        obs.setdefault(k, set()).add(item)
            elif isinstance(v, str) and v:
                obs.setdefault(k, set()).add(v)

        existing = by_ident.get(ident)
        if existing is None:
            # Add the missing product.
            new_prod = {
                'identifier':       ident,
                'attribute_set':    aset_ident,
                'localize_infos':   {primary_lang: {'title': attrs.get('title') or ident}},
                'attributes_sets':  {primary_lang: attrs},
                'is_visible':       True,
            }
            mapped_products.append(new_prod)
            by_ident[ident] = new_prod
            added += 1
        else:
            # Enrich attributes_sets with missing keys.
            ex_attrs_sets = existing.setdefault('attributes_sets', {})
            ex_lang = ex_attrs_sets.setdefault(primary_lang, {})
            changed = False
            for k, v in attrs.items():
                if k not in ex_lang or ex_lang.get(k) in (None, '', []):
                    ex_lang[k] = v
                    changed = True
            if changed:
                enriched += 1

    if added:
        fixes.append(f"+ products: {added} added from source (mapper undersampled)")
    if enriched:
        fixes.append(f"products: {enriched} existing entries got missing attribute values")

    # ─── Enrich schemas with missing attributes / list-typed enums ──────────
    # `SCALAR_LIST_HINT`: identifiers whose values are *known* to form a closed
    # enum across catalogs in this project type. The list intentionally spans
    # multiple verticals — only the ones actually OBSERVED in the source contribute
    # to `observed` (so unrelated hints are no-ops). Add more identifiers as new
    # verticals appear; do NOT remove them — universality is the goal.
    SCALAR_LIST_HINT = {
        # Fashion / apparel
        'clothing_type', 'season', 'material', 'style', 'fit', 'collar',
        'neckline', 'sleeve', 'hood', 'pockets', 'silhouette',
        'lining_material', 'material_origin', 'material_finish',
        'brand_country', 'badge', 'label', 'brand',
        # Shoes
        'shoe_type', 'upper_material', 'sole', 'sole_material',
        'insole_material', 'closure', 'closure_type', 'width',
        # Bags / accessories
        'bag_type', 'bag_size', 'frame', 'inner_pockets', 'outer_pockets',
        'accessory_type',
        # Restaurant / food delivery
        'dish_type', 'cuisine', 'spiciness',
        # Beauty salon / clinic / barbershop
        'service_type', 'service_category', 'category',
        # Hotel / coworking
        'room_type', 'amenities',
        # EdTech / courses
        'course_level', 'language', 'format', 'difficulty',
        # Real estate
        'property_type',
        # SaaS plans
        'billing_cycle', 'features',
        # Universal commerce attributes
        'color', 'size', 'gender', 'age_group',
    }
    schema_extended = 0
    list_promoted = 0
    list_titles_grown = 0
    for aset_ident, obs in observed.items():
        aset = aset_by_ident.get(aset_ident)
        if aset is None:
            continue
        schema = aset.setdefault('schema', {})
        pos_max = max(
            (int(it.get('position') or 0) for it in schema.values() if isinstance(it, dict)),
            default=0,
        )
        for attr_ident, values in obs.items():
            is_array_attr = attr_ident in (array_attrs.get(aset_ident) or set())
            should_be_list = is_array_attr or attr_ident in SCALAR_LIST_HINT
            item = schema.get(attr_ident)
            if item is None:
                pos_max += 1
                new_item = {
                    'identifier':   attr_ident,
                    'position':     pos_max,
                    'isVisible':    True,
                    'localizeInfos': {primary_lang: {'title': attr_ident.replace('_', ' ').title()}},
                }
                if should_be_list:
                    new_item['type'] = 'list'
                    new_item['listType'] = 'multiple' if is_array_attr else 'single'
                    new_item['listTitles'] = {primary_lang: [
                        {'value': v, 'title': v, 'position': i + 1}
                        for i, v in enumerate(sorted(values))
                    ]}
                else:
                    new_item['type'] = 'string'
                schema[attr_ident] = new_item
                schema_extended += 1
                continue
            if not isinstance(item, dict):
                continue
            # Promote string -> list if we now know the value set is enum-like.
            if item.get('type') == 'string' and should_be_list:
                item['type'] = 'list'
                item['listType'] = 'multiple' if is_array_attr else 'single'
                item.setdefault('listTitles', {})
                list_promoted += 1
            # Extend listTitles with all observed values.
            # listTitles[lang] is canonically an ARRAY of {value,title,position}
            # (see attribute-shapes-reference.md). Support legacy dict form
            # transparently — convert to array on first touch.
            if item.get('type') == 'list':
                lt_root = item.setdefault('listTitles', {})
                lt_lang = lt_root.get(primary_lang)
                if isinstance(lt_lang, dict):
                    lt_lang = [
                        {'value': k, 'title': v, 'position': i + 1}
                        for i, (k, v) in enumerate(lt_lang.items())
                    ]
                    lt_root[primary_lang] = lt_lang
                elif not isinstance(lt_lang, list):
                    lt_lang = []
                    lt_root[primary_lang] = lt_lang
                existing_values = {(it.get('value') if isinstance(it, dict) else None) for it in lt_lang}
                grew = False
                for v in values:
                    if v not in existing_values:
                        lt_lang.append({'value': v, 'title': v, 'position': len(lt_lang) + 1})
                        existing_values.add(v)
                        grew = True
                if grew:
                    list_titles_grown += 1

    if schema_extended:
        fixes.append(f"schemas: +{schema_extended} attributes added from observed source data")
    if list_promoted:
        fixes.append(f"schemas: promoted {list_promoted} string→list (enum-like categorical fields)")
    if list_titles_grown:
        fixes.append(f"schemas: extended listTitles on {list_titles_grown} list attributes")

    return fixes


# Directories that typically hold catalog/menu/services data across stacks.
# Universal: e-commerce products, restaurant menus, salon services, real-estate
# listings, course catalogs, etc. — all map to OneEntry "products" table.
_DATA_LIKE_DIRS = (
    'data', 'datasets', 'fixtures', 'mock', 'mocks', 'seeds',
    'catalog', 'menu', 'menus', 'items', 'products', 'services',
    'dishes', 'goods', 'inventory',
)

# Patterns considered "catalog source files" across any stack.
_PRODUCT_DATA_GLOBS = tuple(
    pattern
    for d in _DATA_LIKE_DIRS
    for pattern in (
        f'**/{d}/*.ts',  f'**/{d}/*.js',  f'**/{d}/*.tsx', f'**/{d}/*.jsx',
        f'**/{d}/*.mjs', f'**/{d}/*.cjs',
        f'**/{d}/*.json', f'**/{d}/*.yaml', f'**/{d}/*.yml',
    )
)

# Regex for a single product object body. Matches `id: 'xx'` then anywhere `price: NUMBER`
# and `salePrice: NUMBER` (in any order). Numbers may be string-quoted ('$45.50') or numeric (45.5).
_PRICE_RE = re.compile(
    r"id\s*:\s*['\"]([a-zA-Z0-9_\-]+)['\"][^}]*?"
    r"price\s*:\s*['\"]?\$?([0-9.]+)['\"]?[^}]*?"
    r"salePrice\s*:\s*['\"]?\$?([0-9.]+)['\"]?",
    re.DOTALL,
)

# Coupon-constant pattern. Captures key + label + pct from
# `KEY: { label: 'X% off', pct: X }` or `KEY: { pct: X, label: 'X% off' }`.
_COUPON_RECORD_RE = re.compile(
    r"([A-Z][A-Z0-9_]{2,})\s*:\s*\{"
    r"(?:[^{}]*?label\s*:\s*['\"]([^'\"]+)['\"][^{}]*?pct\s*:\s*([0-9.]+)"
    r"|[^{}]*?pct\s*:\s*([0-9.]+)[^{}]*?label\s*:\s*['\"]([^'\"]+)['\"])"
    r"[^{}]*\}",
    re.DOTALL,
)


def _scan_product_sales(project_root):
    """Walk product-data files and emit (slug, pct) tuples for every salePrice<price pair.

    Returns dict pct -> sorted list of unique product slugs.
    """
    project_root = Path(project_root)
    by_pct = {}
    seen_files = set()
    for glob in _PRODUCT_DATA_GLOBS:
        for path in project_root.glob(glob):
            if path in seen_files or not path.is_file():
                continue
            seen_files.add(path)
            try:
                text = path.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            for match in _PRICE_RE.finditer(text):
                slug = match.group(1)
                try:
                    price = float(match.group(2))
                    sale_price = float(match.group(3))
                except ValueError:
                    continue
                if price <= 0 or sale_price <= 0 or sale_price >= price:
                    continue
                pct = int(round((price - sale_price) / price * 100))
                if pct <= 0 or pct >= 100:
                    continue
                by_pct.setdefault(pct, set()).add(slug)
    return {pct: sorted(slugs) for pct, slugs in by_pct.items()}


_COUPON_CONST_RE = re.compile(
    r"(?:export\s+(?:const|let|var)\s+)?"
    r"([A-Z][A-Z0-9_]*(?:COUPON|PROMO|PROMOTION|DISCOUNT|VOUCHER)[A-Z0-9_]*)"
    r"\s*(?::[^=]*)?=\s*\{",
)


def _scan_coupons(project_root):
    """Walk source for coupon-shaped Record constants and emit list of {code,pct,label}.

    Universal: matches `*COUPON*` / `*PROMO*` / `*DISCOUNT*` / `*VOUCHER*` constants
    in any file under the project. Skips node_modules, build outputs and dot-dirs.
    """
    project_root = Path(project_root)
    coupons = []
    seen_codes = set()
    skip_dirs = {'node_modules', '.next', '.git', 'dist', 'build', '.turbo',
                 '.cache', '.svelte-kit', '.output', '.parcel-cache'}
    for path in project_root.rglob('*'):
        if not path.is_file():
            continue
        if any(part in skip_dirs or part.startswith('.') for part in path.relative_to(project_root).parts):
            continue
        if path.suffix not in ('.ts', '.js', '.tsx', '.jsx', '.mjs', '.cjs', '.json'):
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        if not _COUPON_CONST_RE.search(text):
            continue
        for match in _COUPON_RECORD_RE.finditer(text):
            code = match.group(1)
            if code in seen_codes:
                continue
            label = match.group(2) or match.group(5) or ''
            pct_str = match.group(3) or match.group(4) or ''
            try:
                pct = int(round(float(pct_str)))
            except ValueError:
                continue
            if pct <= 0 or pct >= 100:
                continue
            seen_codes.add(code)
            coupons.append({'code': code, 'pct': pct, 'label': label or f'{pct}% off'})
    return coupons


def generate_post_import_discounts(data, project_root, languages):
    """Safety-net: build `mapped.post_import_discounts[]` if the mapper left it empty.

    The mapper SHOULD do this from `inspector.notes.discounts.extracted`. If the
    inspector forgot to populate `notes.discounts` (regression observed across
    catalog projects), we re-scan source-of-truth files directly: grouped
    salePrice buckets → `sale_<pct>_off`, CHECKOUT_COUPONS-shaped
    records → `coupon_<code>`. Idempotent: if `post_import_discounts` already
    contains entries, no-op.
    """
    fixes = []
    if data.get('post_import_discounts'):
        return fixes
    if not project_root or not Path(project_root).exists():
        return fixes

    primary_lang = languages[0] if languages else 'en_US'
    out = []

    # A. Product-level sales — group by percent bucket.
    by_pct = _scan_product_sales(project_root)
    for pct, slugs in sorted(by_pct.items()):
        if not slugs:
            continue
        out.append({
            'identifier':     f'sale_{pct}_off',
            'type':           'DISCOUNT',
            'localize_infos': {primary_lang: {'title': f'-{pct}% off'}},
            'discount_value': {
                'type':           'PERCENTAGE',
                'applicability':  'TO_PRODUCT',
                'value':          pct,
            },
            'condition_logic': 'OR',
            'conditions':      [{'type': 'PRODUCT', 'value_slug': s} for s in slugs],
            'is_active':       True,
        })

    # B. Coupon-based discounts — one per code.
    for c in _scan_coupons(project_root):
        out.append({
            'identifier':     f"coupon_{c['code'].lower()}",
            'type':           'DISCOUNT',
            'localize_infos': {primary_lang: {'title': f"{c['code']} — {c['label']}"}},
            'discount_value': {
                'type':           'PERCENTAGE',
                'applicability':  'TO_ORDER',
                'value':          c['pct'],
            },
            'coupons':   [{'code': c['code']}],
            'is_active': True,
        })

    if not out:
        return fixes

    data['post_import_discounts'] = out
    n_sales   = sum(1 for d in out if d['identifier'].startswith('sale_'))
    n_coupons = sum(1 for d in out if d['identifier'].startswith('coupon_'))
    fixes.append(
        f"+ post_import_discounts: {len(out)} entries "
        f"({n_sales} percent-bucket sales + {n_coupons} coupon codes) "
        f"— SAFETY NET (inspector did not emit notes.discounts.extracted)"
    )
    warnings_list = data.setdefault('warnings', [])
    warnings_list.append(
        f"out-of-whitelist-needs-post-import: discounts ({n_sales}+{n_coupons}). "
        f"Will be created via REST after import (POST /api/admin/discounts). "
        f"Generated by post-mapper-fixer safety net — inspector should emit "
        f"notes.discounts.extracted instead (see code-inspector Step 8.7)."
    )
    return fixes


_SLIDE_ARR_HEADER_RE = re.compile(
    r"export\s+const\s+[A-Z_][A-Z0-9_]*\s*:\s*(?:[A-Za-z_][A-Za-z0-9_]*\s*)?\[\s*\]\s*=\s*\[",
    re.MULTILINE,
)

# Slide-shaped const name hints (any framework / language). Matched
# case-insensitively against the constant identifier.
_SLIDE_NAME_HINTS = ('slide', 'slider', 'carousel', 'hero')


def _scan_slides(project_root):
    """Walk source for slide-shaped arrays and emit [{image, headline, …}, …].

    Universal heuristic: any `export const NAME: Type[] = [...]` whose NAME
    contains `slide`/`carousel`/`hero` (case-insensitive). Skips build / vendor
    directories. Items must carry an `image`/`imageUrl`/`src` field to count.
    """
    project_root = Path(project_root)
    slides = []
    skip_dirs = {'node_modules', '.next', '.git', 'dist', 'build', '.turbo',
                 '.cache', '.svelte-kit', '.output', '.parcel-cache'}

    for path in project_root.rglob('*'):
        if not path.is_file():
            continue
        if any(part in skip_dirs or part.startswith('.') for part in path.relative_to(project_root).parts):
            continue
        if path.suffix not in ('.ts', '.js', '.tsx', '.jsx', '.mjs', '.cjs'):
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        for m in _SLIDE_ARR_HEADER_RE.finditer(text):
            header = text[m.start():m.end()]
            # The const name lives between "const " and the next colon/=.
            name_match = re.search(r'const\s+([A-Z_][A-Z0-9_]*)', header)
            if not name_match:
                continue
            cname = name_match.group(1).lower()
            if not any(h in cname for h in _SLIDE_NAME_HINTS):
                continue
            bracket_pos = text.rfind('[', 0, m.end())
            if bracket_pos < 0:
                continue
            arr_end = _find_balanced(text, '[', ']', bracket_pos)
            if arr_end < 0:
                continue
            arr_body = text[bracket_pos+1:arr_end-1]
            for obj_body in _split_product_objects(arr_body):
                parsed = _parse_object_top_level(obj_body)
                if not (parsed.get('image') or parsed.get('imageUrl') or parsed.get('src')):
                    continue
                parsed['_source_file'] = str(path.relative_to(project_root))
                slides.append(parsed)
    return slides


def _find_data_files_for_block(block, project_root, limit=8):
    """Return ALL candidate source files for a block (preferred order first).
    Same heuristic as `_find_data_file_for_block` but exposes the full list so
    the caller can pick the file that actually yields the most slide rows.
    Universal across projects — used by `fill_slides_for_all_slider_blocks`.
    """
    if not project_root:
        return []
    project_root = Path(project_root)
    explicit = block.get('source_data_file')
    out = []
    if explicit:
        cand = project_root / explicit
        if cand.is_file():
            out.append(cand)
    raw_ident = (block.get('identifier') or '').lower()
    name_hints = {raw_ident.replace('-', '').replace('_', '')}
    def _add_plural_variants(t):
        """English plural/singular variants — universal, vertical-agnostic."""
        name_hints.add(t)
        if t.endswith('ies') and len(t) > 3:
            name_hints.add(t[:-3] + 'y')        # categories → category
        elif t.endswith('es') and len(t) > 2:
            name_hints.add(t[:-2])              # boxes → box
            name_hints.add(t[:-1])              # services → service
        elif t.endswith('s') and len(t) > 1:
            name_hints.add(t[:-1])              # items → item
        if t.endswith('y') and len(t) > 1:
            name_hints.add(t[:-1] + 'ies')      # category → categories
        else:
            name_hints.add(t + 's')             # item → items
            name_hints.add(t + 'es')            # box → boxes
    for token in re.split(r'[-_]+', raw_ident):
        if token and len(token) >= 3:
            _add_plural_variants(token)
    src_comps = block.get('source_components') or []
    for sc in src_comps:
        if isinstance(sc, str):
            stem = sc.lower().replace('-', '').replace('_', '').replace('/', '')
            name_hints.add(stem)
    skip_dirs = {'node_modules', '.next', '.git', 'dist', 'build', '.turbo',
                 '.cache', '.svelte-kit', '.output', '.parcel-cache',
                 'stories', 'storybook-static', '__tests__', 'tests', 'test',
                 'e2e', 'playwright-report', '_doc', 'docs', 'pages-docs'}
    preferred = []
    fallback = []
    for path in project_root.rglob('*'):
        if not path.is_file():
            continue
        parts = path.relative_to(project_root).parts
        if any(part in skip_dirs or part.startswith('.') for part in parts):
            continue
        if path.suffix not in ('.ts', '.tsx', '.js', '.jsx', '.mjs'):
            continue
        if path.stem.endswith(('.stories', '.story', '.test', '.spec')):
            continue
        stem = path.stem.lower().replace('-', '').replace('_', '')
        # Score by number of distinct hints found in stem — more overlap wins
        score = sum(1 for h in name_hints if h and h in stem)
        if score == 0:
            continue
        is_in_data_dir = any(d in parts for d in _DATA_LIKE_DIRS)
        bucket = preferred if is_in_data_dir else fallback
        bucket.append((-score, len(stem), path))
    preferred.sort()
    fallback.sort()
    out.extend(p for _, _, p in preferred)
    out.extend(p for _, _, p in fallback)
    # Dedupe while preserving order
    seen = set()
    dedup = []
    for p in out:
        if p in seen:
            continue
        seen.add(p)
        dedup.append(p)
        if len(dedup) >= limit:
            break
    return dedup


def _find_data_file_for_block(block, project_root):
    """Find a source data file for a block by matching the block's identifier
    or source_components against typical file-name patterns. Returns Path|None.

    Universal: works across stacks and project types.
    """
    if not project_root:
        return None
    project_root = Path(project_root)
    explicit = block.get('source_data_file')
    if explicit:
        cand = project_root / explicit
        if cand.is_file():
            return cand
    raw_ident = (block.get('identifier') or '').lower()
    # Use both compact (no separators) AND individual word tokens so that
    # `category_section` matches `categories.ts` via the `categor` stem.
    name_hints = {raw_ident.replace('-', '').replace('_', '')}
    for token in re.split(r'[-_]+', raw_ident):
        if token and len(token) >= 3:
            name_hints.add(token)
            # Strip plural `s` so `categories` ↔ `category`
            if token.endswith('s'):
                name_hints.add(token[:-1])
            else:
                name_hints.add(token + 's')
    src_comps = block.get('source_components') or []
    for sc in src_comps:
        if isinstance(sc, str):
            stem = sc.lower().replace('-', '').replace('_', '').replace('/', '')
            name_hints.add(stem)
    skip_dirs = {'node_modules', '.next', '.git', 'dist', 'build', '.turbo',
                 '.cache', '.svelte-kit', '.output', '.parcel-cache',
                 # Stories / tests / docs are not real data sources for blocks
                 'stories', 'storybook-static', '__tests__', 'tests', 'test',
                 'e2e', 'playwright-report', '_doc', 'docs', 'pages-docs'}
    # Prefer files inside data-like directories first.
    preferred = []
    fallback = []
    for path in project_root.rglob('*'):
        if not path.is_file():
            continue
        parts = path.relative_to(project_root).parts
        if any(part in skip_dirs or part.startswith('.') for part in parts):
            continue
        if path.suffix not in ('.ts', '.tsx', '.js', '.jsx', '.mjs'):
            continue
        if path.stem.endswith(('.stories', '.story', '.test', '.spec')):
            continue
        stem = path.stem.lower().replace('-', '').replace('_', '')
        if not any(h and h in stem for h in name_hints):
            continue
        is_in_data_dir = any(d in parts for d in _DATA_LIKE_DIRS)
        if is_in_data_dir:
            preferred.append(path)
        else:
            fallback.append(path)
    return (preferred[0] if preferred else (fallback[0] if fallback else None))


def _has_slide_fields(parsed):
    return any(parsed.get(k) for k in ('image', 'imageUrl', 'src',
                                        'headline', 'title', 'label',
                                        'eyebrow', 'name'))


def _extract_all_slide_objects(text, max_slides=24):
    """Walk any number of nested arrays / objects in the source text and return
    every `{image?, title?, ...}`-shaped object. Handles flat `export const X
    = [{...}]`, nested `Record<group, T[]>`, and Record-of-Records structures.
    """
    out = []
    pos = 0
    n = len(text)
    # Find every `{ ... }` top-level object in the file (greedy), parse it,
    # and keep ones that look slide-shaped. We avoid double-counting nested
    # objects by skipping the entire matched object's span.
    while pos < n and len(out) < max_slides:
        ch = text[pos]
        if ch != '{':
            pos += 1
            continue
        end = _find_balanced(text, '{', '}', pos)
        if end < 0:
            break
        body = text[pos:end]
        parsed = _parse_object_top_level(body)
        if _has_slide_fields(parsed):
            out.append(parsed)
            pos = end  # skip whole matched object
        else:
            pos += 1  # may contain nested slide-shaped objects
    return out


def _parse_slides_from_data_file(path):
    """Parse `export const X[: T[]]? = [{...}, ...]` from `path`, returning a
    list of slide-shaped objects (those carrying `image/imageUrl/src/headline/
    title/label/eyebrow/name`). Falls back to a whole-file walk if no top-level
    array is detected (handles `Record<group, T[]>` shapes like MEGA_DATA /
    TREND_BLOCKS_CATALOG).

    Resolves TS expressions (e.g. `I.womenFashion` → actual URL) via the file
    symbol table — same mechanism as `parse_data_file`.
    """
    if not path or not path.is_file():
        return []
    try:
        text = path.read_text(encoding='utf-8', errors='ignore')
    except OSError:
        return []
    text_clean = re.sub(r'/\*[\s\S]*?\*/', '', text)
    sym_key = str(path)
    if sym_key in _TS_SYMBOL_TABLE_CACHE:
        symbols = _TS_SYMBOL_TABLE_CACHE[sym_key]
    else:
        symbols = _build_ts_symbol_table(text_clean)
        _TS_SYMBOL_TABLE_CACHE[sym_key] = symbols
    out = []
    for m in _PRODUCT_ARR_HEADER_RE.finditer(text_clean):
        bracket_pos = text_clean.rfind('[', 0, m.end())
        if bracket_pos < 0:
            continue
        arr_end = _find_balanced(text_clean, '[', ']', bracket_pos)
        if arr_end < 0:
            continue
        arr_body = text_clean[bracket_pos+1:arr_end-1]
        chunk_slides = []
        for obj_body in _split_product_objects(arr_body):
            parsed = _parse_object_top_level(obj_body)
            if _has_slide_fields(parsed):
                chunk_slides.append(parsed)
        if chunk_slides:
            out.extend(chunk_slides)
            break  # take the first matching array per file
    if not out:
        # Fallback: walk every `{...}` literal in the file (catches nested
        # Record<group, T[]> structures: MEGA_DATA, TREND_BLOCKS_CATALOG, etc.)
        out = _extract_all_slide_objects(text_clean)
    if symbols and out:
        out = _resolve_expressions_recursively(out, symbols)
    return out


# Field names that universally indicate a slide's "parent group" / "tab" /
# "section". A flat slide array with any of these fields on its items is a
# hierarchical structure that needs to be lifted into parent+child slides.
# Order matters — more-specific names are tried first when multiple match.
_GROUP_FIELD_HINTS = (
    'parent_id', 'parentId', 'parent_identifier', 'parentIdentifier',
    'parent', 'parentLabel', 'parent_label',
    'chip', 'tab', 'section', 'category', 'group', 'groupName',
    'group_name', 'categoryName', 'category_name', 'tag',
)


def _slugify_for_identifier(text):
    """Convert arbitrary label to a stable, safe slide identifier.
    'Lounge & Underwear' → 'lounge_underwear'.
    """
    import re as _re
    if not isinstance(text, str) or not text.strip():
        return ''
    s = text.strip().lower()
    s = _re.sub(r'[^a-z0-9]+', '_', s)
    s = s.strip('_')
    return s or 'group'


def _lift_groups_into_parents(slides, languages):
    """If a flat slide list has a universal "group" field on every item,
    promote distinct group values to PARENT slides and link every original
    slide to its parent via `parent_identifier`.

    Universal — works for any vertical: category grids, "Shop by occasion",
    Mega menu sections, multi-tab carousels, etc. Recognised group fields are
    listed in `_GROUP_FIELD_HINTS`.

    Returns (parents, children) — parents come first so they're imported
    before children resolve `parent_identifier`. If no group field is detected
    the input is returned as-is (children=slides, parents=[]).
    """
    if not slides:
        return [], slides
    # 1. Find the first group field present on (almost) all items
    group_field = None
    for hint in _GROUP_FIELD_HINTS:
        present = sum(1 for s in slides if isinstance(s, dict) and s.get(hint))
        if present >= max(2, len(slides) // 2):
            group_field = hint
            break
    if not group_field:
        return [], slides
    # 2. Collect distinct group values, preserving first-seen order
    primary_lang = languages[0] if languages else 'en_US'
    parents = []
    parents_by_value = {}
    children = []
    for s in slides:
        if not isinstance(s, dict):
            continue
        group_val = s.get(group_field)
        if not isinstance(group_val, str) or not group_val.strip():
            children.append(s)
            continue
        parent_ident = parents_by_value.get(group_val)
        if not parent_ident:
            parent_ident = _slugify_for_identifier(group_val)
            # Disambiguate identifier collisions across different labels
            base = parent_ident
            n = 1
            while any(p['identifier'] == parent_ident for p in parents):
                n += 1
                parent_ident = f"{base}_{n}"
            parents_by_value[group_val] = parent_ident
            parents.append({
                'identifier': parent_ident,
                'image': s.get('_parent_image') or '',  # parent typically has no own image
                'title': group_val,
                'attributes_sets': {primary_lang: {'title': group_val}},
            })
        # Attach child to its parent
        child = dict(s)
        child['parent_identifier'] = parent_ident
        # Drop the consumed group field — it has been lifted into the parent
        child.pop(group_field, None)
        children.append(child)
    return parents, children


def fill_slides_for_all_slider_blocks(data, project_root, languages):
    """Universal: walk every slider_block in `blocks[]`, find its source data
    file (heuristic by identifier + source_components + explicit field), and
    emit `post_import_slides[]` entries.

    Idempotent — only emits when no entries exist for a given block_identifier.
    """
    fixes = []
    if not project_root or not Path(project_root).exists():
        return fixes
    blocks = data.get('blocks') or []
    slider_blocks = [
        b for b in blocks
        if (b.get('general_type_marker') == 'slider_block'
            or b.get('general_type_id') == 25
            or b.get('block_type') in ('slider', 'slider_block', 'carousel'))
    ]
    if not slider_blocks:
        return fixes
    tasks = data.setdefault('post_import_slides', [])
    # Count existing entries per block — we REPLACE rather than skip when the
    # source clearly has more slides than the mapper captured (the LLM mapper
    # often samples only 1-2 slides per block and the rest get lost).
    from collections import Counter
    existing_by_block = Counter(
        t.get('block_identifier') for t in tasks if t.get('block_identifier')
    )
    primary_lang = languages[0] if languages else 'en_US'

    # Pull the attribute-set id off the slider block so generated slide rows
    # inherit it (admin renderer needs the schema to render fields). Without
    # this, slides import with `attribute_set_id: null` and the admin shows
    # empty rows under each slider.
    def _aset_for(block):
        return (block.get('attribute_set')
                or (block.get('attributes_sets_data') or {}).get('identifier'))

    added_blocks = 0
    added_slides = 0
    replaced_blocks = 0
    for b in slider_blocks:
        ident = b.get('identifier')
        if not ident:
            continue
        candidates = _find_data_files_for_block(b, project_root)
        # Pick the candidate file that yields the most slide-shaped objects.
        # Ties broken in candidate order (`_find_data_files_for_block` already
        # prefers data-dir files, higher overlap, shorter stem).
        best = (None, [])
        for cand in candidates:
            ps = _parse_slides_from_data_file(cand)
            if len(ps) > len(best[1]):
                best = (cand, ps)
        src_file, parsed_slides = best
        if not src_file or not parsed_slides:
            continue
        existing_n = existing_by_block.get(ident, 0)
        # Universal completeness rule: if the source clearly carries more
        # slides than the mapper produced — replace. Otherwise leave the
        # mapper's entries in place (they may contain hand-curated copy).
        if existing_n >= len(parsed_slides):
            continue
        if existing_n > 0:
            # Drop the under-populated entries for this block before re-emit
            tasks[:] = [t for t in tasks if t.get('block_identifier') != ident]
            replaced_blocks += 1
        aset_ident = _aset_for(b)
        # Universal: if source items carry a "group" field (chip/category/
        # section/tab/parent/…), lift the groups into PARENT slides and link
        # original items as children. Without this, hierarchical category
        # grids / multi-tab carousels arrive flat in admin (the user sees
        # only the top-level tabs but no nested cards). See
        # rules/slider-blocks-extraction.md §3.
        parents, children = _lift_groups_into_parents(parsed_slides, languages)

        def _emit_flat(slide, position, parent_ident=None, is_parent=False):
            title    = slide.get('title') or slide.get('headline') or slide.get('label') or ''
            image    = slide.get('image') or slide.get('imageUrl') or slide.get('src') or ''
            subtitle = slide.get('subtitle') or slide.get('subtext') or ''
            cta_lbl  = slide.get('cta_label') or slide.get('cta') or slide.get('button') or ''
            cta_url  = slide.get('cta_url') or slide.get('href') or slide.get('link') or ''
            eyebrow  = slide.get('eyebrow') or ''
            attrs = {}
            if title:     attrs['title']     = title
            if subtitle:  attrs['subtitle']  = subtitle
            if image:     attrs['image']     = image
            if cta_lbl:   attrs['cta_label'] = cta_lbl
            if cta_url:   attrs['cta_url']   = cta_url
            if eyebrow:   attrs['eyebrow']   = eyebrow
            entry = {
                'block_identifier': ident,
                'position':         position,
                'is_visible':       True,
                'attributes_sets':  {primary_lang: attrs},
            }
            if aset_ident:
                entry['attribute_set'] = aset_ident
            # Stable per-slide identifier — preferred from source.id/slug/etc.
            sid = (slide.get('identifier') or slide.get('id') or slide.get('slug')
                   or slide.get('key') or _slugify_for_identifier(title))
            if sid:
                entry['identifier'] = str(sid)
            if parent_ident:
                entry['parent_identifier'] = parent_ident
            entry['source_file'] = str(src_file.relative_to(Path(project_root)))
            if is_parent:
                entry['is_parent'] = True
            tasks.append(entry)
            return 1

        pos = 1
        # Parents first — children below resolve `parent_identifier` against
        # the parent's `identifier` field.
        for p in parents:
            added_slides += _emit_flat(p, pos, is_parent=True)
            pos += 1
        for c in children:
            added_slides += _emit_flat(
                c, pos, parent_ident=c.get('parent_identifier'),
            )
            pos += 1
        added_blocks += 1
    if added_blocks:
        replaced_note = f"; {replaced_blocks} replaced mapper-sampled stubs" if replaced_blocks else ''
        fixes.append(
            f"+ slider slides for {added_blocks} block(s) "
            f"({added_slides} slide records, parent+child hierarchy preserved)"
            f"{replaced_note}"
        )
    return fixes


def generate_default_template_previews(data, languages):
    """Emit standard `template_previews` (slot proportions for slider blocks).

    OneEntry's slider_block UI lets admins assign a preview template (16:9,
    1:1, etc.) controlling crop ratio. The blueprint never includes any by
    default → admin can't choose any template → slider editor shows "No
    preview templates" warning. Emit two universal defaults:
      - `hero_slide` (16:9, wide hero — universal across web)
      - `card_square` (1:1, gallery / category tile — universal)

    Idempotent. Goes into `tables.template_previews` so the loader picks it up.
    """
    fixes = []
    primary_lang = languages[0] if languages else 'en_US'
    tables = data.setdefault('tables', {})
    tpvs = tables.setdefault('template_previews', [])
    existing_idents = {t.get('identifier') for t in tpvs if t.get('identifier')}

    DEFAULTS = [
        {
            'id':           '@tpv.hero_slide',
            'identifier':   'hero_slide',
            'title':        'Hero slide (16:9)',
            'proportions':  {'width': 16, 'height': 9},
        },
        {
            'id':           '@tpv.card_square',
            'identifier':   'card_square',
            'title':        'Square card (1:1)',
            'proportions':  {'width': 1, 'height': 1},
        },
    ]
    added = 0
    for tpv in DEFAULTS:
        if tpv['identifier'] in existing_idents:
            continue
        tpvs.append(tpv)
        existing_idents.add(tpv['identifier'])
        added += 1
    if added:
        fixes.append(
            f"+ template_previews: {added} universal defaults "
            f"(hero_slide 16:9, card_square 1:1) — needed for slider_block UI"
        )
    return fixes


def generate_post_import_slides(data, project_root, languages):
    """Build `mapped.post_import_slides[]` for slider_block blocks.

    Slides are OUT of the blueprint whitelist (loader does NOT accept `slides`
    rows — verified at the OneEntry Platform 
    blueprint-loader.service.ts:24-49`). Each slide is created post-import via
    `POST /api/admin/slides` (controller the OneEntry Platform 
    admin-slides.controller.ts:42`).

    Mapping:
      slide.image / imageUrl  -> attributes_sets[lang].image
      slide.headline / title  -> attributes_sets[lang].title
      slide.eyebrow           -> attributes_sets[lang].eyebrow
      slide.subtext / subtitle-> attributes_sets[lang].subtitle
      slide.cta / cta_label   -> attributes_sets[lang].cta_label
      slide.href / cta_url    -> attributes_sets[lang].cta_url

    Idempotent: if `post_import_slides[]` already populated — no-op.
    """
    fixes = []
    if data.get('post_import_slides'):
        return fixes
    if not project_root or not Path(project_root).exists():
        return fixes

    blocks = data.get('blocks') or []
    slider_blocks = [
        b for b in blocks
        if (b.get('general_type_marker') == 'slider_block'
            or b.get('block_type') in ('slider', 'slider_block', 'carousel'))
    ]
    if not slider_blocks:
        return fixes

    parsed_slides = _scan_slides(project_root)
    if not parsed_slides:
        return fixes

    primary_lang = languages[0] if languages else 'en_US'

    def _attr_payload(slide):
        title = slide.get('headline') or slide.get('title') or ''
        subtitle = slide.get('subtext') or slide.get('subtitle') or ''
        image = slide.get('image') or slide.get('imageUrl') or ''
        cta_label = slide.get('cta') or slide.get('cta_label') or slide.get('button') or ''
        cta_url = slide.get('href') or slide.get('cta_url') or slide.get('link') or ''
        eyebrow = slide.get('eyebrow') or ''
        out = {}
        if title:     out['title']     = title
        if subtitle:  out['subtitle']  = subtitle
        if image:     out['image']     = image
        if cta_label: out['cta_label'] = cta_label
        if cta_url:   out['cta_url']   = cta_url
        if eyebrow:   out['eyebrow']   = eyebrow
        return out

    # Distribute slides across slider blocks. Default policy: attach all parsed
    # slides to the first slider block — typical projects only have ONE slider
    # (the home hero). Additional sliders would need explicit hints in source.
    target_block = slider_blocks[0]
    target_ident = target_block.get('identifier') or '(unknown)'

    tasks = []
    for idx, slide in enumerate(parsed_slides, start=1):
        attrs = _attr_payload(slide)
        if not attrs:
            continue
        tasks.append({
            'block_identifier': target_ident,
            'position':         idx,
            'is_visible':       True,
            'attributes_sets':  {primary_lang: attrs},
            'source_file':      slide.get('_source_file', ''),
        })

    if not tasks:
        return fixes

    data['post_import_slides'] = tasks
    fixes.append(
        f"+ post_import_slides: {len(tasks)} slides for block '{target_ident}' "
        f"(source: {tasks[0].get('source_file')})"
    )
    warnings_list = data.setdefault('warnings', [])
    warnings_list.append(
        f"out-of-whitelist-needs-post-import: {len(tasks)} slides for slider_block "
        f"'{target_ident}'. Created via POST /api/admin/slides after import "
        f"(rules/post-import-orchestration.md Step 8.6)."
    )
    return fixes


# ─── Universal duplicate-schema-slot detector ──────────────────────────────
# Pairs of attribute identifiers that represent the same semantic slot. Keep
# the first (canonical) and remove the second; data-loader writes into the
# canonical key only. Applies across all project verticals.
_SEMANTIC_DUPLICATE_SLOTS = (
    ('preview',  'cover'),    # both = main product image; canonical = `preview`
    ('preview',  'image'),
    ('gallery',  'images'),
    ('gallery',  'gallery_images'),
    ('sizes',    'size'),     # plural list canonical, singular is duplicate
    ('colors',   'color'),
    ('materials', 'material'),  # only when both present, otherwise keep what exists
    ('tags',     'tag'),
)


def dedupe_semantic_slots(data):
    """Remove duplicate semantic-slot attributes from each attribute_set.

    Universal across project types. When two identifiers represent the same
    concept (cover/preview, size/sizes), the duplicate is removed from
    `schema` AND from each product's `attributes_sets[lang]`. The canonical
    field's value is preserved (or filled from the duplicate if canonical
    is empty).
    """
    fixes = []
    asets = data.get('attributes_sets') or []
    removed_schema = 0
    backfilled = 0
    for aset in asets:
        schema = aset.get('schema') or {}
        for canonical, duplicate in _SEMANTIC_DUPLICATE_SLOTS:
            if canonical in schema and duplicate in schema:
                schema.pop(duplicate, None)
                removed_schema += 1
    # Clean products attributes_sets entries.
    for p in (data.get('products') or []):
        attrs_sets = p.get('attributes_sets') or {}
        for lang, attrs in (attrs_sets.items() if isinstance(attrs_sets, dict) else []):
            if not isinstance(attrs, dict):
                continue
            for canonical, duplicate in _SEMANTIC_DUPLICATE_SLOTS:
                if duplicate in attrs:
                    if canonical not in attrs or not attrs.get(canonical):
                        attrs[canonical] = attrs[duplicate]
                        backfilled += 1
                    attrs.pop(duplicate, None)
    if removed_schema:
        fixes.append(f"schemas: removed {removed_schema} duplicate semantic slots (preview/cover, sizes/size, …)")
    if backfilled:
        fixes.append(f"products: backfilled {backfilled} canonical-slot values from duplicates")
    return fixes


def autogenerate_skus(data):
    """For products in an attribute_set that has an `isSku=true` attribute, ensure
    every product has a non-empty SKU. Auto-derive from `identifier` when missing.

    Universal: every catalog has SKU-like product identifiers across verticals.
    """
    fixes = []
    asets = data.get('attributes_sets') or []
    aset_sku_key = {}
    for aset in asets:
        ident = aset.get('identifier')
        if not ident:
            continue
        for k, v in (aset.get('schema') or {}).items():
            if isinstance(v, dict) and v.get('isSku') is True:
                aset_sku_key[ident] = k
                break
    if not aset_sku_key:
        return fixes
    filled = 0
    for p in (data.get('products') or []):
        aset_ident = p.get('attribute_set')
        sku_key = aset_sku_key.get(aset_ident)
        if not sku_key:
            continue
        attrs_sets = p.setdefault('attributes_sets', {})
        for lang_attrs in attrs_sets.values() if isinstance(attrs_sets, dict) else []:
            if isinstance(lang_attrs, dict) and not lang_attrs.get(sku_key):
                lang_attrs[sku_key] = p.get('identifier') or ''
                filled += 1
    if filled:
        fixes.append(f"products: auto-filled {filled} empty SKU values from product identifier")
    return fixes


def cleanup_empty_json_attrs(data):
    """Remove `type: json` attributes whose value is unused across every product
    in their attribute_set. These are usually leftover schema entries (`specs`,
    `product_details`) that mapper added but never populated.

    Universal: applies to any catalog vertical.
    """
    fixes = []
    asets = data.get('attributes_sets') or []
    products = data.get('products') or []
    products_by_aset = {}
    for p in products:
        products_by_aset.setdefault(p.get('attribute_set'), []).append(p)
    removed = 0
    for aset in asets:
        aset_ident = aset.get('identifier')
        schema = aset.get('schema') or {}
        for attr_key in list(schema.keys()):
            v = schema.get(attr_key)
            if not isinstance(v, dict) or v.get('type') != 'json':
                continue
            usages = 0
            for p in products_by_aset.get(aset_ident, []):
                attrs_sets = p.get('attributes_sets') or {}
                for lang_attrs in attrs_sets.values() if isinstance(attrs_sets, dict) else []:
                    if isinstance(lang_attrs, dict) and lang_attrs.get(attr_key) not in (None, '', {}, []):
                        usages += 1
                        break
            if usages == 0:
                schema.pop(attr_key)
                removed += 1
    if removed:
        fixes.append(f"schemas: removed {removed} unused `type:json` attributes (specs/product_details/…)")
    return fixes


def split_review_form_into_rating_and_data(data, languages):
    """If the project has a `review` form with mixed rating + text fields, split
    it into TWO forms:
      - `review_rating` (type='rating') — for the star/numeric score
      - `review_feedback` (type='data') — for the text body + author + photos

    OneEntry treats `rating` and `data` as different processing pipelines:
      - `rating` forms aggregate scores into product-level rating
      - `data` forms accumulate user-submitted records (free-form content)

    A single form with type='rating' that ALSO has text fields cannot do both
    pipelines simultaneously. Universal across project types (every B2C project
    with reviews has the same split need: shop, hotel, salon, restaurant).

    Idempotent: no-op if `review_rating` + `review_feedback` already exist.
    """
    fixes = []
    forms = data.get('forms') or []
    review = next((f for f in forms if f.get('identifier') == 'review'), None)
    has_rating = any(f.get('identifier') == 'review_rating' for f in forms)
    has_feedback = any(f.get('identifier') == 'review_feedback' for f in forms)
    if has_rating and has_feedback:
        return fixes
    # If `review` form isn't there but the project still needs review
    # functionality (forBlocks_reviews block typically exists in B2C catalogs),
    # synthesize empty review_rating + review_feedback forms with default schemas.
    asets = data.get('attributes_sets') or []
    has_review_block = any((a.get('identifier') or '') == 'forBlocks_reviews' for a in asets)
    if not review and has_review_block:
        if not has_rating:
            forms.append({
                'identifier': 'review_rating',
                'type': 'rating',
                'processing_type': 'main',
                'localize_infos': {(languages[0] if languages else 'en_US'):
                                   {'title': 'Product Rating'}},
                'attribute_set': 'forForms_review_rating',
            })
            asets.append({
                'id': '@aset.forForms_review_rating',
                'identifier': 'forForms_review_rating',
                'type_id': 7,
                'title': 'For Review Rating Form',
                'localize_infos': {(languages[0] if languages else 'en_US'):
                                   {'title': 'For Review Rating'}},
                'schema': {
                    'rating': {
                        'id': 1, 'type': 'integer', 'identifier': 'rating',
                        'isRatingValue': True, 'position': 1, 'isVisible': True,
                        'localizeInfos': {(languages[0] if languages else 'en_US'):
                                          {'title': 'Rating'}},
                        'rules': {'minValue': 1, 'maxValue': 5},
                    },
                },
            })
        if not has_feedback:
            forms.append({
                'identifier': 'review_feedback',
                'type': 'data',
                'processing_type': 'main',
                'localize_infos': {(languages[0] if languages else 'en_US'):
                                   {'title': 'Product Review Text'}},
                'attribute_set': 'forForms_review_feedback',
            })
            asets.append({
                'id': '@aset.forForms_review_feedback',
                'identifier': 'forForms_review_feedback',
                'type_id': 7,
                'title': 'For Review Feedback Form',
                'localize_infos': {(languages[0] if languages else 'en_US'):
                                   {'title': 'For Review Feedback'}},
                'schema': {
                    'review_text': {
                        'id': 1, 'type': 'text', 'identifier': 'review_text',
                        'position': 1, 'isVisible': True,
                        'localizeInfos': {(languages[0] if languages else 'en_US'):
                                          {'title': 'Review'}},
                        'additionalFields': {
                            'placeholder': 'Share your experience with this product…',
                            'helperText': 'Up to 5000 characters.',
                        },
                        'rules': {'maxLength': 5000},
                    },
                    'photos': {
                        'id': 2, 'type': 'groupOfImages', 'identifier': 'photos',
                        'position': 2, 'isVisible': True, 'isCompress': True,
                        'localizeInfos': {(languages[0] if languages else 'en_US'):
                                          {'title': 'Photos'}},
                    },
                },
            })
        data['forms'] = forms
        data['attributes_sets'] = asets
        fixes.append("+ synthesized review_rating + review_feedback forms "
                     "(forBlocks_reviews present but no `review` source form)")
        return fixes
    if not review:
        return fixes
    review_aset = next((a for a in asets if a.get('identifier') == 'forForms_review'), None)
    if not review_aset:
        return fixes
    schema = review_aset.get('schema') or {}
    # Identify rating-related vs free-text attributes
    rating_idents = {'rating', 'stars', 'score', 'grade'}
    rating_attrs, text_attrs = {}, {}
    primary_lang = languages[0] if languages else 'en_US'
    for k, item in schema.items():
        if not isinstance(item, dict):
            continue
        ident = (item.get('identifier') or '').lower()
        if ident in rating_idents or item.get('type') in ('real', 'integer', 'float'):
            rating_attrs[k] = item
        else:
            text_attrs[k] = item
    if not rating_attrs or not text_attrs:
        # No mixed shape — leave as is
        return fixes
    # Create two new attribute_sets
    rating_aset_ident = 'forForms_review_rating'
    feedback_aset_ident = 'forForms_review_feedback'
    new_rating_set = {
        'id':         '@aset.forForms_review_rating',
        'identifier': rating_aset_ident,
        'type_id':    7,  # forForms
        'title':      'For Forms (review rating)',
        'schema':     rating_attrs,
        'localize_infos': {primary_lang: {'title': 'Review rating'}},
    }
    new_feedback_set = {
        'id':         '@aset.forForms_review_feedback',
        'identifier': feedback_aset_ident,
        'type_id':    7,
        'title':      'For Forms (review feedback)',
        'schema':     text_attrs,
        'localize_infos': {primary_lang: {'title': 'Review feedback'}},
    }
    asets.append(new_rating_set)
    asets.append(new_feedback_set)
    # Replace `review` form with two
    data['forms'] = [f for f in forms if f.get('identifier') != 'review']
    data['forms'].append({
        'id':           '@form.review_rating',
        'identifier':   'review_rating',
        'type':         'rating',
        'attribute_set': rating_aset_ident,
        'processing_type': review.get('processing_type') or 'db',
        'localize_infos': {primary_lang: {'title': 'Product rating'}},
    })
    data['forms'].append({
        'id':           '@form.review_feedback',
        'identifier':   'review_feedback',
        'type':         'data',
        'attribute_set': feedback_aset_ident,
        'processing_type': review.get('processing_type') or 'db',
        'localize_infos': {primary_lang: {'title': 'Customer review'}},
    })
    # Remove the now-split review aset
    data['attributes_sets'] = [a for a in asets if a.get('identifier') != 'forForms_review']
    # Also drop form_module_config for the merged 'review' if present
    fmc = data.get('form_module_config') or []
    data['form_module_config'] = [c for c in fmc if c.get('form') != 'review']
    fixes.append(
        f"forms: split 'review' (mixed rating+text, anti-pattern) into "
        f"'review_rating' (type=rating, {len(rating_attrs)} attrs) + "
        f"'review_feedback' (type=data, {len(text_attrs)} attrs)"
    )
    return fixes


def merge_subscriptions_form_into_user(data, languages):
    """Move `forForms_subscriptions` boolean preference fields into `forUsers`.

    Subscriptions / newsletter / preference forms are an anti-pattern in
    OneEntry: Forms accumulate submission records, but a user's *current*
    preferences belong on the user entity itself. Drop the subscriptions form
    + its attribute_set, lift `pref_*` fields onto `forUsers.schema` as
    radioButton attributes.

    Universal across project types — B2C apps commonly have this preference
    pattern (e-commerce / SaaS / fintech / EdTech / etc.).
    """
    fixes = []
    primary_lang = languages[0] if languages else 'en_US'
    forms = data.get('forms') or []
    sub_form = next((f for f in forms if f.get('identifier') == 'subscriptions'), None)
    if not sub_form:
        return fixes
    asets = data.get('attributes_sets') or []
    sub_aset = next((a for a in asets if a.get('identifier') == 'forForms_subscriptions'), None)
    users_aset = next((a for a in asets if a.get('identifier') == 'forUsers'), None)
    if not sub_aset or not users_aset:
        return fixes
    sub_schema = sub_aset.get('schema') or {}
    users_schema = users_aset.setdefault('schema', {})
    max_pos = max(
        (int(it.get('position') or 0) for it in users_schema.values() if isinstance(it, dict)),
        default=0,
    )
    lifted = 0
    for k, v in sub_schema.items():
        if not isinstance(v, dict):
            continue
        if k in users_schema:
            continue
        max_pos += 1
        new_item = dict(v)
        new_item['position'] = max_pos
        users_schema[k] = new_item
        lifted += 1
    # Remove the subscriptions form + its aset + module-config binding.
    # Filter form_module_config in BOTH top-level and tables.* shapes —
    # mapper emits the top-level form, post-mapper migrate_post_import_to_tables
    # may have already mirrored it into tables.form_module_config with the
    # @token form_id field.
    data['forms'] = [f for f in forms if f.get('identifier') != 'subscriptions']
    data['attributes_sets'] = [a for a in asets if a.get('identifier') != 'forForms_subscriptions']

    def _is_subscriptions_binding(c):
        if c.get('form') == 'subscriptions':
            return True
        fid = c.get('form_id') or ''
        return isinstance(fid, str) and fid == '@form.subscriptions'

    fmc_top = data.get('form_module_config') or []
    data['form_module_config'] = [c for c in fmc_top if not _is_subscriptions_binding(c)]
    tables = data.get('tables') or {}
    if 'form_module_config' in tables:
        tables['form_module_config'] = [c for c in tables['form_module_config']
                                         if not _is_subscriptions_binding(c)]
    fixes.append(
        f"forms: removed `subscriptions` form (anti-pattern); lifted {lifted} "
        f"pref_* fields into forUsers schema (universal B2C preferences live "
        f"on user, not on a form)"
    )
    return fixes


def dedupe_error_pages(data):
    """Collapse duplicate error-page rows. mapper emits `not-found` (page_url=404)
    AND post-mapper-fixer adds `404` (page_url=404) — keep the canonical one
    (matching HTTP code identifier: '404'/'500'/'offline').

    Universal across project types.
    """
    fixes = []
    pages = data.get('pages') or []
    # Group error-pages by page_url. Keep the one whose identifier matches the URL.
    by_url = {}
    for p in pages:
        if p.get('general_type_id') != 3:
            continue
        url = (p.get('page_url') or p.get('identifier') or '').strip()
        by_url.setdefault(url, []).append(p)
    removed_idents = []
    for url, group in by_url.items():
        if len(group) <= 1:
            continue
        canonical = next((p for p in group if p.get('identifier') == url), group[0])
        for p in group:
            if p is canonical:
                continue
            ident = p.get('identifier')
            pages.remove(p)
            removed_idents.append(ident)
    if removed_idents:
        # Also rewrite any references (post_import_page_errors, links) to use canonical.
        psk_tasks = data.get('post_import_page_errors') or []
        canonicals = {url: (next((p for p in g if p.get('identifier') == url), g[0])).get('identifier')
                      for url, g in by_url.items() if len(g) >= 1}
        for t in psk_tasks:
            page_ident = t.get('page_identifier')
            for url, canon in canonicals.items():
                if page_ident == url or page_ident in removed_idents:
                    t['page_identifier'] = canon
                    break
        data['pages'] = pages
        fixes.append(
            f"pages: removed {len(removed_idents)} duplicate error-page rows "
            f"({', '.join(removed_idents)}); error_page rows are canonicalized by page_url"
        )
    return fixes


# ─── Universal block-values filler ─────────────────────────────────────────

_BLOCK_SOURCE_FILE_HINTS = {
    # Substrings (case-insensitive) of source filenames that typically carry
    # the data for a block of the given block-identifier hint. Universal —
    # the mapping is heuristic and additive; new project types can add
    # entries without breaking existing ones.
    'promo':            ('promo', 'promoblocks', 'banner', 'specialoffers'),
    'faq':              ('faq', 'faqdata', 'questions'),
    'discount_banner':  ('banners', 'discount', 'sale'),
    'category_section': ('categories', 'category'),
    'trend_blocks':     ('trend', 'trending', 'newarrivals', 'bestsellers'),
    'bundles':          ('specialoffers', 'bundles', 'combos'),
    'special_offers':   ('specialoffers', 'bundles'),
    'reviews':          ('reviews', 'testimonials'),
    'hero':             ('heroslides', 'hero'),
}


def _detect_block_source_file(block, project_root):
    """Return Path to the source file that carries this block's content, if any.

    Looks at three signals (in priority):
      1. `block.source_data_file` explicitly set by the mapper.
      2. Heuristic match on block identifier vs source file basename.
    Returns None if no file found.
    """
    explicit = block.get('source_data_file')
    if explicit:
        cand = Path(project_root) / explicit
        if cand.is_file():
            return cand
    ident = (block.get('identifier') or '').lower()
    hints = _BLOCK_SOURCE_FILE_HINTS.get(ident)
    if not hints:
        for k, v in _BLOCK_SOURCE_FILE_HINTS.items():
            if k in ident:
                hints = v
                break
    if not hints:
        return None
    project_root = Path(project_root)
    skip_dirs = {'node_modules', '.next', '.git', 'dist', 'build', '.turbo'}
    for path in project_root.rglob('*'):
        if not path.is_file():
            continue
        if any(part in skip_dirs or part.startswith('.') for part in path.relative_to(project_root).parts):
            continue
        if path.suffix not in ('.ts', '.tsx', '.js', '.jsx', '.mjs'):
            continue
        stem = path.stem.lower().replace('-', '').replace('_', '')
        if any(h in stem for h in hints):
            return path
    return None


def fill_block_attribute_values(data, project_root, languages):
    """For each block, look up its source file and copy scalar / image / URL
    values into `block.attributes_sets[lang][attr]`.

    Universal: for any block where the attribute_set schema declares
    `title/subtitle/image/cta_label/cta_url/eyebrow/description` etc., we try
    to fill them with concrete text/URL extracted from the source data file.
    No-op when no source file is found.
    """
    fixes = []
    if not project_root or not Path(project_root).exists():
        return fixes
    primary_lang = languages[0] if languages else 'en_US'
    blocks = data.get('blocks') or []
    asets = data.get('attributes_sets') or []
    aset_by_ident = {a.get('identifier'): a for a in asets if a.get('identifier')}

    filled_blocks = 0
    for block in blocks:
        attrs_sets = block.get('attributes_sets') or {}
        lang_attrs = attrs_sets.get(primary_lang) if isinstance(attrs_sets, dict) else None
        # Used to skip when ANY value present, but that was wrong — `fill_empty_block_titles`
        # sets `title` early, leaving image/cta/eyebrow still empty. Process every block;
        # only individual missing fields get filled (logic at the bottom of the loop body).
        src_file = _detect_block_source_file(block, project_root)
        if not src_file:
            continue
        # Pull first plausible string / array-of-strings value pair from source.
        try:
            text = src_file.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        # Find first `export const X[: Type[]]? = [` and parse the first object.
        m = _PRODUCT_ARR_HEADER_RE.search(text)
        if not m:
            continue
        bracket_pos = text.rfind('[', 0, m.end())
        if bracket_pos < 0:
            continue
        arr_end = _find_balanced(text, '[', ']', bracket_pos)
        if arr_end < 0:
            continue
        arr_body = text[bracket_pos+1:arr_end-1]
        first_obj = next(iter(_split_product_objects(arr_body)), None)
        if not first_obj:
            continue
        parsed = _parse_object_top_level(first_obj)
        # Route the parsed source fields onto the block attribute identifiers.
        title = parsed.get('title') or parsed.get('headline') or parsed.get('label') or ''
        subtitle = parsed.get('subtitle') or parsed.get('subtext') or parsed.get('description') or parsed.get('discountText') or ''
        image = parsed.get('image') or parsed.get('imageUrl') or parsed.get('cover') or ''
        cta_label = parsed.get('cta') or parsed.get('cta_label') or parsed.get('button') or ''
        cta_url = parsed.get('href') or parsed.get('cta_url') or parsed.get('link') or ''
        eyebrow = parsed.get('eyebrow') or parsed.get('badge') or ''
        new_attrs = {}
        for k, v in (('title', title), ('subtitle', subtitle), ('image', image),
                     ('cta_label', cta_label), ('cta_url', cta_url),
                     ('eyebrow', eyebrow), ('description', subtitle)):
            if not v:
                continue
            # Only emit attributes that the block's aset schema actually declares.
            aset_ident = block.get('attribute_set')
            schema = (aset_by_ident.get(aset_ident) or {}).get('schema') or {}
            if k in schema:
                new_attrs[k] = v
        if new_attrs:
            existing = block.setdefault('attributes_sets', {}).setdefault(primary_lang, {})
            # Per-field check: only fill MISSING values, never overwrite admin-edited content
            for k, v in new_attrs.items():
                if not existing.get(k):
                    existing[k] = v
            filled_blocks += 1
    if filled_blocks:
        fixes.append(f"blocks: filled attribute_set values for {filled_blocks} blocks from source data files")
    return fixes


# ─── Universal menu items filler ───────────────────────────────────────────

_MENU_CONFIG_PATTERNS = (
    'headerconfig', 'footerconfig', 'navconfig', 'menuconfig',
    'header.config', 'footer.config',
    'navigation', 'navlinks', 'sitemap',
)


def _scan_menu_configs(project_root):
    """Return dict {menu_name: [{label, href}, ...]} parsed from project source.

    Looks for files whose basename matches the menu-config hints. For each
    matching file, finds top-level `Record`/`object`/`array` literals and
    extracts `{label, href}` pairs recursively. Universal across stacks.
    """
    project_root = Path(project_root)
    result = {}
    skip_dirs = {'node_modules', '.next', '.git', 'dist', 'build', '.turbo'}
    for path in project_root.rglob('*'):
        if not path.is_file():
            continue
        if any(part in skip_dirs or part.startswith('.') for part in path.relative_to(project_root).parts):
            continue
        if path.suffix not in ('.ts', '.tsx', '.js', '.jsx', '.mjs'):
            continue
        stem = path.stem.lower().replace('-', '').replace('_', '')
        menu_kind = None
        if any(p in stem for p in _MENU_CONFIG_PATTERNS):
            if 'header' in stem or 'nav' in stem or 'sitemap' in stem:
                menu_kind = 'header'
            elif 'footer' in stem:
                menu_kind = 'footer'
        if menu_kind is None:
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        # Extract all `{label: '...', href: '...'}` pairs.
        items = []
        for m in re.finditer(
            r"\{[^{}]*?(?:label|name|title)\s*:\s*['\"]([^'\"]+)['\"][^{}]*?(?:href|url|link|path)\s*:\s*['\"]([^'\"]+)['\"][^{}]*?\}",
            text, re.DOTALL,
        ):
            items.append({'label': m.group(1), 'href': m.group(2)})
        # Also catch reverse order (href first, then label).
        for m in re.finditer(
            r"\{[^{}]*?(?:href|url|link|path)\s*:\s*['\"]([^'\"]+)['\"][^{}]*?(?:label|name|title)\s*:\s*['\"]([^'\"]+)['\"][^{}]*?\}",
            text, re.DOTALL,
        ):
            items.append({'label': m.group(2), 'href': m.group(1)})
        if items:
            existing = result.setdefault(menu_kind, [])
            seen = {(i['label'], i['href']) for i in existing}
            for it in items:
                key = (it['label'], it['href'])
                if key not in seen:
                    existing.append(it)
                    seen.add(key)
    return result


def fill_header_menu_from_pages(data, languages):
    """Populate `post_import_menus[header].items[]` from existing pages when no
    explicit header items were found in source configs.

    Universal: any TOP-LEVEL page (parent_id is None or `@page.root` or `root`)
    that is NOT an error_page is a navigation candidate — derived purely from
    the page tree, with NO project-specific identifier whitelist. This works
    equally for e-commerce (women/men/sale), restaurants (menu/reservations),
    salons (services/booking), hotels (rooms/packages), SaaS (pricing/docs),
    corporate sites (about/team/careers).

    Idempotent: only adds if header has 0 pages.
    """
    fixes = []
    primary_lang = languages[0] if languages else 'en_US'
    tasks = data.get('post_import_menus') or []
    header = next((t for t in tasks if t.get('identifier') == 'header'), None)
    if not header:
        header = {
            'identifier': 'header',
            'localize_infos': {primary_lang: {'title': 'Header'}},
            'pages':        [],
            'custom_items': [],
        }
        tasks.append(header)
        data['post_import_menus'] = tasks
    if header.get('items') or header.get('pages'):
        return fixes  # already populated

    pages = data.get('pages') or []

    # A "top-level" page = parent is root or unspecified.
    def _is_top_level(p):
        parent = p.get('parent_id') or p.get('parent')
        return parent in (None, '', 'root', '@page.root')

    candidates = []
    seen = set()
    for p in pages:
        ident = (p.get('identifier') or '').lower()
        if not ident or ident in seen:
            continue
        if ident == 'root':
            continue
        if p.get('general_type_id') == 3:  # error page → never in nav
            continue
        if not _is_top_level(p):
            continue
        candidates.append((ident, p.get('localize_infos', {})))
        seen.add(ident)
    added = 0
    for slug, li in candidates:
        title = ''
        for lang_block in (li or {}).values() if isinstance(li, dict) else []:
            if isinstance(lang_block, dict) and lang_block.get('menuTitle'):
                title = lang_block['menuTitle']
                break
            if isinstance(lang_block, dict) and lang_block.get('title'):
                title = lang_block['title']
                break
        if not title:
            title = slug.title()
        header.setdefault('items', []).append({
            'page_slug':      slug,
            'localize_infos': {primary_lang: {'title': title}},
        })
        added += 1
    if added:
        fixes.append(
            f"+ header menu: {added} top-level navigation pages added from page tree "
            f"(universal nav-slug recognition)"
        )
    return fixes


def normalize_synthetic_asset_paths(data):
    """Replace synthetic `/assets/<name>.png`-style strings with a TODO marker
    that prompts the admin to upload the real asset.

    Universal: any project with build-time asset imports (Next.js, Vite, CRA,
    Webpack) gives the parser a JS identifier (e.g. `heroSlide1.src`) that
    the slide-attrs filler converts via convention. Better to leave a clear
    placeholder than to ship a 404-ing fake URL.
    """
    fixes = []
    fake_re = re.compile(r'^/assets/[^/]+\.(?:png|jpg|jpeg|gif|webp|svg)$', re.IGNORECASE)
    touched = 0
    for entries in (
        data.get('post_import_slides') or [],
        data.get('blocks') or [],
    ):
        for entry in entries:
            slides = entry.get('slides') if isinstance(entry, dict) else None
            iterables = []
            if isinstance(slides, list):
                iterables.extend(slides)
            attrs_sets = entry.get('attributes_sets') if isinstance(entry, dict) else None
            if isinstance(attrs_sets, dict):
                for lang_attrs in attrs_sets.values():
                    if isinstance(lang_attrs, dict):
                        iterables.append(lang_attrs)
            for item in iterables:
                if not isinstance(item, dict):
                    continue
                for k, v in list(item.items()):
                    if isinstance(v, str) and fake_re.match(v):
                        item[k] = (
                            f'TODO_UPLOAD:{v.split("/")[-1]}'
                        )
                        touched += 1
    if touched:
        fixes.append(
            f"assets: replaced {touched} synthetic `/assets/*` paths with "
            f"`TODO_UPLOAD:...` markers (admin should upload real image)"
        )
    return fixes


# OneEntry locales table contains only `en_US` as active by default. Any other
# `en_*` regional variant (en_GB / en_AU / en_CA) is INACTIVE → loader silently
# drops jsonb keys matching inactive locales (data ends up `{}` in DB). Same
# for de_AT (vs de_DE), es_MX (vs es_ES), pt_BR (vs pt_PT), etc.
# Map every regional variant the inspector might pick up onto the closest
# always-active code. Universal across project types.
_LOCALE_NORMALIZATION = {
    'en_GB': 'en_US', 'en_AU': 'en_US', 'en_CA': 'en_US', 'en_NZ': 'en_US',
    'en_IE': 'en_US', 'en_ZA': 'en_US', 'en_IN': 'en_US', 'en_SG': 'en_US',
    'de_AT': 'de_DE', 'de_CH': 'de_DE',
    'es_MX': 'es_ES', 'es_AR': 'es_ES', 'es_CO': 'es_ES', 'es_CL': 'es_ES',
    'pt_BR': 'pt_PT',
    'fr_BE': 'fr_FR', 'fr_CA': 'fr_FR', 'fr_CH': 'fr_FR',
    'it_CH': 'it_IT',
    'zh_CN': 'zh_ZH', 'zh_TW': 'zh_ZH', 'zh_HK': 'zh_ZH',
}


def _normalize_locale_codes_in_object(obj, fixes_counter):
    """Recursively walk a YAML/JSON object and rename regional locale keys to
    base codes (en_GB → en_US, de_AT → de_DE, etc.). Mutates in-place.
    """
    if isinstance(obj, dict):
        for k in list(obj.keys()):
            v = obj[k]
            new_k = _LOCALE_NORMALIZATION.get(k, k)
            if new_k != k:
                # Merge into base if base already exists, otherwise rename
                if new_k in obj and isinstance(obj.get(new_k), dict) and isinstance(v, dict):
                    obj[new_k].update(v)
                else:
                    obj[new_k] = v
                del obj[k]
                fixes_counter[0] += 1
                _normalize_locale_codes_in_object(obj.get(new_k), fixes_counter)
            else:
                _normalize_locale_codes_in_object(v, fixes_counter)
    elif isinstance(obj, list):
        for item in obj:
            _normalize_locale_codes_in_object(item, fixes_counter)


def normalize_locale_codes(data):
    """Rename inactive regional locale codes (en_GB, de_AT, …) to base codes
    (en_US, de_DE, …) throughout the mapped data.

    Why: cms `locales` table activates only base codes by default. Any other
    regional variant present in blueprint jsonb columns gets silently dropped
    by the loader → entities load as `attributes_sets={}`. Universal — applies
    to every project type that uses regional locale conventions in source.
    """
    fixes = []
    counter = [0]
    # Top-level keys
    if isinstance(data.get('language'), str):
        old = data['language']
        new = _LOCALE_NORMALIZATION.get(old, old)
        if new != old:
            data['language'] = new
            counter[0] += 1
    if isinstance(data.get('detected_languages'), list):
        seen = set()
        new_list = []
        for lang in data['detected_languages']:
            nlang = _LOCALE_NORMALIZATION.get(lang, lang)
            if nlang not in seen:
                new_list.append(nlang)
                seen.add(nlang)
                if nlang != lang:
                    counter[0] += 1
        data['detected_languages'] = new_list
    # Deep walk
    _normalize_locale_codes_in_object(data, counter)
    if counter[0]:
        fixes.append(
            f"locales: normalized {counter[0]} regional codes "
            f"(en_GB→en_US, de_AT→de_DE, …) — cms `locales` activates base codes only"
        )
    return fixes


def emit_admin_validators_per_lang(data, languages):
    """Add `validators[lang].requiredValidator` (and analogous) to every
    user-input attribute. The admin form-validation pipeline reads
    `validators[lang]` exclusively; if absent, no client-side validation fires
    in the admin UI (`requiredValidator` / `booleanValidator` /
    `comparisonValidator` / `defaultValueValidator` shape). `rules` and
    `additionalFields` (placeholder / helperText) remain in place for the
    storefront SDK side — they are NOT read by the admin renderer.

    Universal across project types — applies to any form-based input (signin,
    checkout, booking, contact, subscription, review).
    """
    fixes = []
    asets = data.get('attributes_sets') or []
    primary_lang = languages[0] if languages else 'en_US'
    added = 0
    for aset in asets:
        ident = aset.get('identifier') or ''
        # Only forForms_* and forUsers carry user-input attributes
        if not (ident.startswith('forForms_') or ident == 'forUsers'):
            continue
        schema = aset.get('schema') or {}
        for key, item in schema.items():
            if not isinstance(item, dict):
                continue
            if item.get('validators'):
                continue  # already populated
            rules = item.get('rules') or {}
            attr_ident = item.get('identifier') or ''
            attr_type = item.get('type')

            validators_block = {}
            # requiredValidator — fires for any non-empty value requirement
            # On forUsers + forForms_*, a field is "required" unless rules
            # explicitly mark it optional. Currently `rules.required` is rarely
            # set; treat email/password/login/phone + isLogin/isPassword as
            # required by convention.
            is_required = (
                rules.get('required') is True
                or item.get('isLogin') is True
                or item.get('isPassword') is True
                or item.get('isSignUp') is True
                or attr_ident in (
                    'email', 'password', 'login', 'phone',
                    'first_name', 'last_name', 'full_name',
                    'agreed_terms', 'consent',
                )
            )
            if is_required:
                validators_block['requiredValidator'] = {'strict': True}

            # booleanValidator — for radioButton (true/false toggle)
            if attr_type == 'radioButton':
                validators_block['booleanValidator'] = {
                    'trueValue': True,
                    'falseValue': False,
                }

            if not validators_block:
                continue
            item['validators'] = {primary_lang: validators_block}
            added += 1
    if added:
        fixes.append(
            f"+ validators[lang]: emitted requiredValidator/booleanValidator "
            f"for {added} user-input attributes (admin form validation contract)"
        )
    return fixes


# Canonical schema for any slider-type attribute_set. The admin UI shows the
# slide editor with these fields; without them the data jsonb (image / title /
# subtitle / cta_*) has no place to render. Universal — every project type
# with sliders/carousels needs the same slide-card UI.
_SLIDER_CANONICAL_SCHEMA_ITEMS = [
    {'identifier': 'image',     'type': 'image',  'title': 'Image'},
    {'identifier': 'title',     'type': 'string', 'title': 'Title'},
    {'identifier': 'subtitle',  'type': 'string', 'title': 'Subtitle'},
    {'identifier': 'eyebrow',   'type': 'string', 'title': 'Eyebrow / Label'},
    {'identifier': 'cta_label', 'type': 'string', 'title': 'CTA label'},
    {'identifier': 'cta_url',   'type': 'string', 'title': 'CTA URL'},
]


def ensure_slider_block_schemas(data, languages):
    """Every block with `general_type_id == 25` (slider_block) holds slides in
    a child `slides` table; each slide inherits the block's `attribute_set_id`.
    The slide-editor admin UI renders a card with `image / title / subtitle /
    eyebrow / cta_label / cta_url` — but ONLY if the attribute_set's schema
    declares those identifiers. Many mappers emit a slider attribute_set with
    only `title` (or empty), leaving every slide's image / cta invisible in the
    admin UI.

    Fix: for every attribute_set bound to ANY slider_block, ensure the schema
    contains all canonical slide attributes. Idempotent — pre-existing items
    with the same identifier are preserved.

    Universal across project types — sliders exist in any vertical (hero
    carousel for e-commerce / restaurant / hotel / SaaS landing / corporate).
    """
    fixes = []
    primary_lang = languages[0] if languages else 'en_US'
    blocks = data.get('blocks') or []
    asets = data.get('attributes_sets') or []
    aset_by_ident = {a.get('identifier'): a for a in asets if a.get('identifier')}

    # Collect attribute_set identifiers used by slider blocks.
    slider_aset_idents = set()
    for b in blocks:
        if b.get('general_type_id') != 25:
            continue
        ai = b.get('attribute_set')
        if ai:
            slider_aset_idents.add(ai)

    added_per_set = {}
    for ai in slider_aset_idents:
        aset = aset_by_ident.get(ai)
        if aset is None:
            continue
        if not isinstance(aset.get('schema'), dict):
            aset['schema'] = {}
        schema = aset['schema']
        # Index existing identifiers
        existing_idents = {
            (item or {}).get('identifier'): k for k, item in schema.items()
            if isinstance(item, dict)
        }
        pos_max = max(
            (int((item or {}).get('position') or 0) for item in schema.values()
             if isinstance(item, dict)),
            default=0,
        )
        added = 0
        for canon in _SLIDER_CANONICAL_SCHEMA_ITEMS:
            if canon['identifier'] in existing_idents:
                continue
            pos_max += 1
            new_key = canon['identifier']
            schema[new_key] = {
                'identifier':    canon['identifier'],
                'type':          canon['type'],
                'position':      pos_max,
                'isVisible':     True,
                'localizeInfos': {primary_lang: {'title': canon['title']}},
            }
            added += 1
        if added:
            added_per_set[ai] = added
    if added_per_set:
        summary = ', '.join(f'{k}(+{v})' for k, v in added_per_set.items())
        fixes.append(
            f"slider schemas: ensured canonical slide fields (image/title/"
            f"subtitle/eyebrow/cta_label/cta_url) on {summary}"
        )
    return fixes


def generate_default_payment_accounts(data):
    """Emit a `default` payment_account so admin /payments/statuses/N/config
    page has at least one account to render. payment_accounts is in the
    blueprint whitelist (extended 2026-06-02) — we do NOT link the account
    to orders_storage via orders_storage_payment_accounts (per user policy:
    "не подключать"); admin links manually if needed.

    Universal — every project that has the `orders` subsystem needs at least
    one payment_account row even if no real payment provider configured yet.
    """
    fixes = []
    pa = data.setdefault('payment_accounts', [])
    if any((a.get('identifier') == 'default') for a in pa):
        return fixes
    pa.append({
        'id': '@pacct.default',
        'identifier': 'default',
        'type': 'test',
        'is_visible': True,
        'test_mode': True,
        'test_settings': {},
        'settings': {},
        'localize_infos': {'en_US': {'title': 'Default Payment Account'}},
    })
    fixes.append("+ payment_accounts: 1 default account (not linked to storage)")
    return fixes


def generate_default_templates(data):
    """Emit the universal set of `templates` rows if mapper omitted them.

    Universal across project verticals — every project needs render templates
    for at least product / page / block / form. Without them, admin shows an
    empty "Choose template" dropdown for the bound entity. The set mirrors
    cms preseeded `general_types` (verified via SQL):
      - product   (general_type_id=5)
      - page      (general_type_id=4 hub / =17 catalog)
      - block     (general_type_id=18 common / =8 product_block)
      - form      (general_type_id=7)

    Idempotent — skip identifiers already present.
    """
    fixes = []
    templates = data.get('templates') or []
    existing = {t.get('identifier') for t in templates}
    # general_type_id values verified against cms preseeded `general_types`
    # table (see rules/generated/preseeded-entities.md).
    DEFAULTS = [
        ('product_default',       1,  'Product Default'),
        ('common_page_default',   17, 'Common Page Default'),
        ('catalog_page_default',  4,  'Catalog Page Default'),
        ('common_block_default',  18, 'Common Block Default'),
        ('product_block_default', 10, 'Product Block Default'),
        ('form_default',          11, 'Form Default'),
    ]
    added = 0
    corrected = 0
    canonical_gtid = {ident: gtid for ident, gtid, _ in DEFAULTS}
    # Correct legacy general_type_id values on already-present templates.
    # Mapper used to emit gtid=7 for forms but cms general_types has form=11;
    # similar drift for product (=1 not 5), product_block (=10 not 8).
    for t in templates:
        ident = t.get('identifier')
        if ident in canonical_gtid and t.get('general_type_id') != canonical_gtid[ident]:
            t['general_type_id'] = canonical_gtid[ident]
            corrected += 1
    for ident, gtid, title in DEFAULTS:
        if ident in existing:
            continue
        templates.append({
            'id': f'@tpl.{ident}',
            'identifier': ident,
            'general_type_id': gtid,
            'title': title,
            'attributes_sets': {},
        })
        added += 1
    if corrected:
        fixes.append(f"templates: corrected general_type_id on {corrected} legacy rows")
    if added:
        data['templates'] = templates
        fixes.append(f"+ templates: {added} universal defaults (product/page/block/form)")
    return fixes


def generate_default_product_relations_templates(data):
    """Auto-generate the standard `product_relations_templates` set so the admin
    `Product links` tab is functional out of the box.

    `product_relations_templates` IS in the 24-table blueprint whitelist —
    so emitting into `tables.product_relations_templates` ensures admin sees
    them straight after import, without orchestrator round-trip.

    Universal across project verticals — relations are domain-agnostic:
      - `similar`     — same category, ±30% price
      - `cross_sell`  — same category, complementary
      - `upsell`      — same category, >120% price
      - `recommended` — generic recommendations (no strict logic)
      - `variants`    — only if products share a parent attribute (model/group/parent_sku)

    Idempotent — skip identifiers already present in `tables.product_relations_templates`.
    No-op if there are no products (corporate / personal-cabinet projects).
    """
    fixes = []
    products = data.get('products') or []
    if not products:
        return fixes
    asets = data.get('attributes_sets') or []
    # Pick a "category-like" attribute identifier present in any forProducts_* schema.
    # Universal candidates — first hit wins, ordered by domain frequency.
    category_field = None
    for cand in ('category', 'clothing_type', 'shoe_type', 'bag_type', 'accessory_type',
                 'dish_type', 'service_type', 'room_type', 'course_type', 'product_type'):
        for a in asets:
            if not (a.get('identifier') or '').startswith('forProducts'):
                continue
            if cand in (a.get('schema') or {}):
                category_field = cand
                break
        if category_field:
            break
    # Pick a variants-grouping attribute if any product schema has it
    variants_field = None
    for cand in ('product_model', 'parent_sku', 'product_group_id', 'model', 'variant_group'):
        for a in asets:
            if not (a.get('identifier') or '').startswith('forProducts'):
                continue
            if cand in (a.get('schema') or {}):
                variants_field = cand
                break
        if variants_field:
            break

    tables = data.setdefault('tables', {})
    existing = tables.setdefault('product_relations_templates', [])
    existing_idents = {(r.get('identifier') or '') for r in existing}

    templates = []
    if category_field:
        if 'similar' not in existing_idents:
            templates.append({
                'id': '@prt.similar',
                'identifier': 'similar',
                'name': 'Similar Products',
                'is_active': True,
                'conditions': [
                    {'field': category_field, 'operator': 'eq', 'value': f'{{self.{category_field}}}'},
                    {'field': 'price', 'operator': 'between',
                     'value': ['{self.price * 0.7}', '{self.price * 1.3}']},
                    {'field': 'sku', 'operator': 'neq', 'value': '{self.sku}'},
                ],
            })
        if 'cross_sell' not in existing_idents:
            templates.append({
                'id': '@prt.cross_sell',
                'identifier': 'cross_sell',
                'name': 'Cross-sell (complementary)',
                'is_active': True,
                'conditions': [
                    {'field': category_field, 'operator': 'neq', 'value': f'{{self.{category_field}}}'},
                    {'field': 'sku', 'operator': 'neq', 'value': '{self.sku}'},
                ],
            })
        if 'upsell' not in existing_idents:
            templates.append({
                'id': '@prt.upsell',
                'identifier': 'upsell',
                'name': 'Upsell (premium options)',
                'is_active': True,
                'conditions': [
                    {'field': category_field, 'operator': 'eq', 'value': f'{{self.{category_field}}}'},
                    {'field': 'price', 'operator': 'gt', 'value': '{self.price * 1.2}'},
                    {'field': 'sku', 'operator': 'neq', 'value': '{self.sku}'},
                ],
            })
    if 'recommended' not in existing_idents:
        templates.append({
            'id': '@prt.recommended',
            'identifier': 'recommended',
            'name': 'Recommended (general)',
            'is_active': True,
            'conditions': [
                {'field': 'sku', 'operator': 'neq', 'value': '{self.sku}'},
            ],
        })
    if variants_field and 'variants' not in existing_idents:
        templates.append({
            'id': '@prt.variants',
            'identifier': 'variants',
            'name': 'Product Variants',
            'is_active': True,
            'conditions': [
                {'field': variants_field, 'operator': 'eq', 'value': f'{{self.{variants_field}}}'},
                {'field': 'sku', 'operator': 'neq', 'value': '{self.sku}'},
            ],
        })

    if templates:
        existing.extend(templates)
        tables['product_relations_templates'] = existing
        idents = ', '.join(t['identifier'] for t in templates)
        fixes.append(
            f"+ product_relations_templates: {len(templates)} default templates ({idents})"
        )
    return fixes


def _slug_from_url(url):
    """Derive a stable menu_custom_items_mn.identifier from a URL.
    Universal: works for social profiles, mailto, tel, generic external links.
    """
    import re as _re
    s = _re.sub(r'^https?://(?:www\.)?', '', url or '')
    s = _re.sub(r'[^a-zA-Z0-9]+', '-', s).strip('-').lower()
    return s[:60] or 'external'


def migrate_post_import_to_tables(data):
    """Migrate `post_import_*` arrays into `tables.*` so the blueprint loader
    creates everything itself — no orchestrator round-trip needed.

    Whitelist extended on 2026-06-02 to cover slides / menus / menu_pages_mn /
    menu_custom_items_mn / discounts / discount_conditions / discount_coupons /
    payment_status_map / page_errors / filters / filter_items_mn. This function
    reshapes mapper-emitted `post_import_*` sidecars into the canonical
    `tables.<name>[]` form with `@token` FK resolution.

    Idempotent — dedupes rows by identifier / natural-key before appending.
    Universal across project verticals — operates purely on data shape.
    """
    fixes = []
    fixes_unresolved_menu = []
    tables = data.setdefault('tables', {})

    # Clean-slate per post_import_* group so re-running the fixer produces a
    # deterministic output (no stale rows from a previous run leak through).
    # We only purge the groups that are about to be regenerated; tables coming
    # from sources other than post_import_* (e.g. user-edited overlays) are
    # left intact because their post_import_* sidecar is absent.
    purge_map = {
        'post_import_slides': ['slides'],
        'post_import_menus': ['menus', 'menu_pages_mn', 'menu_custom_items_mn'],
        'post_import_discounts': ['discounts', 'discount_conditions', 'discount_coupons'],
        'post_import_payment_status_maps': ['payment_status_map'],
        'post_import_page_errors': ['page_errors'],
        'post_import_filters': ['filters', 'filter_items_mn'],
    }
    for sidecar, target_tables in purge_map.items():
        if data.get(sidecar):
            for t in target_tables:
                if t in tables:
                    tables[t] = []

    def _push(table, rows, key='identifier'):
        """Append unique rows by `key` (or natural-key tuple)."""
        existing = tables.setdefault(table, [])
        seen = set()
        for r in existing:
            if isinstance(key, str):
                seen.add(r.get(key))
            else:
                seen.add(tuple(r.get(k) for k in key))
        added = 0
        for r in rows:
            if isinstance(key, str):
                k = r.get(key)
                if k is None or k in seen:
                    continue
                seen.add(k)
            else:
                k = tuple(r.get(kk) for kk in key)
                if k in seen:
                    continue
                seen.add(k)
            existing.append(r)
            added += 1
        return added

    # --- post_import_slides → tables.slides ---
    slides_src = data.get('post_import_slides') or []
    if slides_src:
        # First pass: build (block_identifier, slide_identifier) → @slide.X
        # token map so child slides can resolve `parent_identifier` against a
        # stable token. Hierarchical slides (parent+children from
        # `_lift_groups_into_parents`) need this — otherwise a child's
        # `parent_id` would point at an `@slide.X_Y` index suffix that nothing
        # in the same block matches.
        slide_token = {}
        # Track per-block position so identifier-based slides keep a stable
        # global suffix when their identifier is missing.
        per_block_idx = {}
        for i, s in enumerate(slides_src):
            bi = s.get('block_identifier') or ''
            sid = s.get('identifier')
            if sid:
                key = (bi, sid)
                slide_token[key] = f'@slide.{bi}_{sid}' if bi else f'@slide.{sid}'
            per_block_idx[bi] = per_block_idx.get(bi, 0) + 1
            # Always register fallback index too, for parent_identifier resolution
            # by index (rare, but supported).
            fb_key = (bi, str(per_block_idx[bi]))
            slide_token.setdefault(fb_key, f'@slide.{bi}_{per_block_idx[bi]}' if bi else f'@slide.idx_{i}')

        rows = []
        per_block_idx_emit = {}
        for i, s in enumerate(slides_src):
            bi = s.get('block_identifier') or ''
            ai = s.get('attribute_set')
            sid = s.get('identifier')
            per_block_idx_emit[bi] = per_block_idx_emit.get(bi, 0) + 1
            # Stable token: prefer source identifier, fall back to per-block idx
            if sid:
                token = f'@slide.{bi}_{sid}' if bi else f'@slide.{sid}'
            else:
                token = f'@slide.{bi}_{per_block_idx_emit[bi]}' if bi else f'@slide.idx_{i}'
            row = {
                'id': token,
                'block_id': f'@block.{bi}' if bi else None,
                'is_visible': s.get('is_visible', True),
                'identifier': sid or '',
                'attributes_sets': s.get('attributes_sets') or {},
            }
            if ai:
                row['attribute_set_id'] = f'@aset.{ai}'
            parent_ref = s.get('parent_identifier')
            if parent_ref:
                # Try (same block, parent ident); fall back to global lookup.
                key = (bi, parent_ref)
                row['parent_id'] = slide_token.get(key, f'@slide.{bi}_{parent_ref}' if bi else f'@slide.{parent_ref}')
            rows.append(row)
        n = _push('slides', rows, key='id')
        if n:
            parent_n = sum(1 for r in rows if not r.get('parent_id'))
            child_n  = sum(1 for r in rows if r.get('parent_id'))
            extra = f" ({parent_n} top-level, {child_n} nested)" if child_n else ''
            fixes.append(f"+ tables.slides: {n} rows from post_import_slides{extra}")

    # --- post_import_menus → tables.menus + tables.menu_pages_mn + tables.menu_custom_items_mn ---
    # Two routing rules per item:
    #   1. External URL (`http://`, `https://`, or contains `://`) → goes
    #      into `menu_custom_items_mn` with the URL stored in `url`. Loader
    #      cannot resolve `@page.https://...` and rejects with 400.
    #   2. Page slug → `menu_pages_mn` with `@page.<slug>` token. If the
    #      target page doesn't exist in the blueprint, also try the slug
    #      WITHOUT a common prefix (e.g. mapper sometimes emits
    #      `info-about-us` while the actual page is `about-us`).
    menus_src = data.get('post_import_menus') or []
    if menus_src:
        # Build set of known page identifiers for resolution.
        known_pages = {p.get('identifier') for p in (data.get('pages') or []) if p.get('identifier')}
        menu_rows = []
        mn_rows = []
        ci_rows = []  # menu_custom_items_mn
        # Track per-menu identifier → @<ns>.<token> for parent_id resolution.
        # Hierarchical sources emit `parent_identifier` referring to a sibling
        # entry within the same menu; we must turn that into the correct id
        # token (@mp.X for menu_pages_mn or @mci.X for menu_custom_items_mn).
        mn_token = {}   # (menu, ident) → @mp.<menu>_<ident>
        ci_token = {}   # (menu, ident) → @mci.<menu>_<ident>
        unresolved_parent_refs = []
        for m in menus_src:
            mi = m.get('identifier')
            if not mi:
                continue
            menu_rows.append({
                'id': f'@menu.{mi}',
                'identifier': mi,
                'localize_infos': m.get('localize_infos') or {},
            })
            # Concatenate items + custom_items so item-order positions are
            # deterministic across both kinds. Pre-walk to register every
            # entry's stable token, then re-walk to emit FK refs.
            all_entries = []
            for item in (m.get('items') or []):
                all_entries.append(('item', item))
            for item in (m.get('custom_items') or []):
                all_entries.append(('custom', item))
            # Pre-pass: register tokens for parent resolution.
            #
            # IMPORTANT — universal cms semantic:
            # `menu_pages_mn.parent_id` and `menu_custom_items_mn.parent_id`
            # both reference a **page.id** (not the row's own id in the join
            # table). The admin update path (`base-menus.service.ts:328-345`)
            # computes `parent_id` by walking `pages.parentId` and matching
            # against page ids already in the menu. The cms fk-graph.ts
            # technically declares self-FK on those columns, but the actual
            # functional contract is "parent_id = parent PAGE id".
            #
            # So for parent_id we must emit `@page.<parent_slug>`. For custom
            # items that nest under another custom item (no real page), we
            # fall back to `@mci.<menu>_<key>` (polymorphic — same column
            # accepts a menu_custom_items_mn.id in that case).
            for kind, item in all_entries:
                idents = []
                if item.get('identifier'):
                    idents.append(item['identifier'])
                if item.get('page_slug'):
                    idents.append(item['page_slug'])
                for ident in idents:
                    # Always remember whether the entry is page-backed so
                    # children that reference this entry pick the correct
                    # token namespace.
                    if kind == 'item':
                        # menu_pages_mn entries are always page-backed
                        slug = item.get('page_slug') or ident
                        mn_token[(mi, ident)] = f'@page.{slug}'
                    else:
                        # Pure custom item (no page) — use the row's own id
                        ci_token[(mi, ident)] = f'@mci.{mi}_{ident}'

            def _resolve_parent(parent_ident):
                """parent_identifier resolution.
                Returns the FK token for `parent_id`:
                  • If parent is a page-backed menu entry → @page.<slug>
                  • If parent is a pure custom item       → @mci.<menu>_<id>
                Universal — handles mixed hierarchies (page parent + custom-
                item parent within the same menu).
                """
                if not parent_ident:
                    return None
                key = (mi, parent_ident)
                if key in mn_token:
                    return mn_token[key]
                if key in ci_token:
                    return ci_token[key]
                return None

            for item in (m.get('items') or []):
                ident = item.get('identifier')
                slug = (item.get('page_slug') or '').strip()
                url = (item.get('url') or item.get('href') or '').strip()
                if not url and ('://' in slug or slug.startswith('http')):
                    url = slug
                    slug = ''
                if url:
                    if ':--' in url and '://' not in url:
                        url = url.replace(':--', '://', 1)
                    ci_rows.append({
                        'id':         f'@mci.{mi}_{ident}' if ident else None,
                        'menu_id':    f'@menu.{mi}',
                        'identifier': ident or _slug_from_url(url),
                        'value':      url,
                        'localize_infos': item.get('localize_infos') or {},
                        'parent_id':  _resolve_parent(item.get('parent_identifier')),
                    })
                    continue
                if not slug:
                    continue
                resolved_slug = None
                if slug in known_pages:
                    resolved_slug = slug
                else:
                    for prefix in ('info-', 'page-', 'footer-', 'header-'):
                        if slug.startswith(prefix):
                            stripped = slug[len(prefix):]
                            if stripped in known_pages:
                                resolved_slug = stripped
                                break
                if resolved_slug is None:
                    fixes_unresolved_menu.append(f'{mi}:{slug}')
                    continue
                parent_ref = item.get('parent_identifier') or item.get('parent_slug')
                parent_tok = _resolve_parent(parent_ref)
                if parent_ref and parent_tok is None:
                    unresolved_parent_refs.append(f'{mi}:{ident or slug}→{parent_ref}')
                # Universal: cms admin builds menu hierarchy by walking
                # `pages.parentId`. A menu_pages_mn entry can only be nested
                # under a parent that is ALSO a page. If the parent is a
                # custom item (`@mci.X`) → demote this entry to custom item
                # too (it gets the page URL, parent stays the custom-item
                # group). Otherwise the admin shows it flat anyway and the
                # blueprint validator (CHK-024) flags the mismatch.
                if isinstance(parent_tok, str) and parent_tok.startswith('@mci.'):
                    page_row = next((p for p in (data.get('pages') or [])
                                     if p.get('identifier') == resolved_slug), {})
                    href = '/' + resolved_slug.replace('-', '/')
                    li = item.get('localize_infos') or (page_row.get('localize_infos') or {})
                    ci_rows.append({
                        'id':             f'@mci.{mi}_{ident or resolved_slug}',
                        'menu_id':        f'@menu.{mi}',
                        'identifier':     ident or resolved_slug,
                        'value':          href,
                        'localize_infos': li,
                        'parent_id':      parent_tok,
                    })
                    continue
                row_id_key = ident or resolved_slug
                row = {
                    'id':        f'@mp.{mi}_{row_id_key}',
                    'menu_id':   f'@menu.{mi}',
                    'page_id':   f'@page.{resolved_slug}',
                    'is_pinned': item.get('is_pinned', False),
                    'parent_id': parent_tok,
                }
                mn_rows.append(row)
            # Pure custom_items (typically grouping nodes with no URL)
            for item in (m.get('custom_items') or []):
                ident = item.get('identifier')
                value = (item.get('value') or '').strip()
                if ':--' in value and '://' not in value:
                    value = value.replace(':--', '://', 1)
                parent_tok = _resolve_parent(item.get('parent_identifier'))
                if item.get('parent_identifier') and parent_tok is None:
                    unresolved_parent_refs.append(f'{mi}:{ident}→{item.get("parent_identifier")}')
                ci_rows.append({
                    'id':         f'@mci.{mi}_{ident}' if ident else None,
                    'menu_id':    f'@menu.{mi}',
                    'identifier': ident or _slug_from_url(value) or 'group',
                    'value':      value,
                    'localize_infos': item.get('localize_infos') or {},
                    'parent_id':  parent_tok,
                })
        n1 = _push('menus', menu_rows, key='id')
        # Dedupe key: prefer `id` (stable) when present; fall back to
        # natural-key for legacy entries without id tokens.
        n2 = _push('menu_pages_mn', mn_rows, key='id') if any(r.get('id') for r in mn_rows) \
             else _push('menu_pages_mn', mn_rows, key=('menu_id', 'page_id'))
        n3 = _push('menu_custom_items_mn', ci_rows, key='id') if any(r.get('id') for r in ci_rows) \
             else _push('menu_custom_items_mn', ci_rows, key=('menu_id', 'identifier'))
        if n1 or n2 or n3:
            nested = sum(1 for r in mn_rows + ci_rows if r.get('parent_id'))
            extra = f" ({nested} with parent_id)" if nested else ''
            fixes.append(
                f"+ tables.menus: {n1} menus, {n2} menu_pages_mn, {n3} menu_custom_items_mn{extra}"
            )
        if fixes_unresolved_menu:
            fixes.append(
                f"menu page slugs not resolvable, dropped: "
                f"{len(fixes_unresolved_menu)} ({', '.join(fixes_unresolved_menu[:5])}…)"
            )
        if unresolved_parent_refs:
            fixes.append(
                f"menu parent_identifier unresolved (will become top-level): "
                f"{len(unresolved_parent_refs)}: {', '.join(unresolved_parent_refs[:5])}"
            )

    # --- post_import_discounts → tables.discounts + discount_conditions + discount_coupons ---
    discounts_src = data.get('post_import_discounts') or []
    if discounts_src:
        d_rows = []
        cond_rows = []
        coup_rows = []
        for d in discounts_src:
            di = d.get('identifier')
            if not di:
                continue
            # Admin UI requires non-null start_date / end_date to enable
            # "Save". Default: today → today + 1 year. Universal — any
            # discount needs a validity window.
            import datetime as _dt
            today = _dt.date.today()
            default_start = d.get('start_date') or today.isoformat() + 'T00:00:00.000Z'
            default_end = d.get('end_date') or (
                today.replace(year=today.year + 1).isoformat() + 'T23:59:59.999Z'
            )
            # CMS DTO `DiscountValueConfigDto` requires `discountType` (NOT
            # `type`) + `applicability` + `value`. Mapper often emits the
            # legacy `type` key — normalize it. Without this admin shows
            # "Тип не выбран" and blocks save.
            dv = dict(d.get('discount_value') or {})
            if 'discountType' not in dv and 'type' in dv:
                dv['discountType'] = dv.pop('type')
            dv.setdefault('discountType', 'PERCENTAGE')
            dv.setdefault('applicability', 'TO_ORDER')
            dv.setdefault('value', 0)
            d_rows.append({
                'id': f'@discount.{di}',
                'identifier': di,
                'type': d.get('type', 'DISCOUNT'),
                'localize_infos': d.get('localize_infos') or {},
                'discount_value': dv,
                'condition_logic': d.get('condition_logic', 'OR'),
                'start_date': default_start,
                'end_date': default_end,
                'exclusions': d.get('exclusions'),
                'gifts': d.get('gifts'),
                'user_groups': d.get('user_groups'),
                'user_exclusions': d.get('user_exclusions'),
            })
            for cond in (d.get('conditions') or []):
                cond_rows.append({
                    'discount_id': f'@discount.{di}',
                    'condition_type': cond.get('condition_type', 'MIN_CART_AMOUNT'),
                    'entity_ids': cond.get('entity_ids') or [],
                    'value': cond.get('value') or {},
                })
            for coup in (d.get('coupons') or []):
                coup_rows.append({
                    'discount_id': f'@discount.{di}',
                    'code': coup.get('code'),
                    'is_reusable': coup.get('is_reusable', False),
                })
        n1 = _push('discounts', d_rows, key='id')
        # discount_conditions has no natural key — push all (loader has no
        # unique constraint, idempotency relies on truncate before reimport).
        n2 = len(cond_rows)
        if n2:
            tables.setdefault('discount_conditions', []).extend(cond_rows)
        n3 = _push('discount_coupons', coup_rows, key=('discount_id', 'code'))
        if n1 or n2 or n3:
            fixes.append(
                f"+ tables.discounts: {n1} discounts, {n2} conditions, {n3} coupons"
            )

    # --- post_import_payment_status_maps → tables.payment_status_map ---
    psm_src = data.get('post_import_payment_status_maps') or []
    if psm_src:
        rows = []
        for psm in psm_src:
            tok = psm.get('orders_storage_token') or (
                f'@storage.{psm.get("orders_storage")}' if psm.get('orders_storage') else None)
            # Normalize legacy namespaces emitted by the mapper to the
            # canonical `@storage.` used by the loader's TokenRegistry.
            # `@os.` actually names order_statuses in builder-blueprint.md
            # convention (NOT orders_storage), but older mapper revisions
            # confused the two — rewrite when seen on a storage FK.
            if isinstance(tok, str):
                for legacy in ('@ostorage.', '@os.'):
                    if tok.startswith(legacy):
                        tok = '@storage.' + tok[len(legacy):]
                        break
            # admin requires non-empty identifier for provider selection.
            # Fallback chain: explicit identifier → provider name → 'default'.
            ident = (psm.get('identifier') or psm.get('provider') or 'default').strip() or 'default'
            rows.append({
                'order_storage_id': tok,
                'identifier': ident,
                'status_map': psm.get('status_map') or {},
            })
        n = _push('payment_status_map', rows, key=('order_storage_id', 'identifier'))
        if n:
            fixes.append(f"+ tables.payment_status_map: {n} rows")

    # --- post_import_page_errors → tables.page_errors ---
    pe_src = data.get('post_import_page_errors') or []
    if pe_src:
        rows = []
        for pe in pe_src:
            pi = pe.get('page_identifier')
            code = pe.get('code') or pe.get('http_code')
            if code is None:
                continue
            rows.append({
                'code': int(code),
                'page_id': f'@page.{pi}' if pi else None,
            })
        n = _push('page_errors', rows, key='code')
        if n:
            fixes.append(f"+ tables.page_errors: {n} rows")

    # --- post_import_filters → tables.filters + tables.filter_items_mn ---
    filters_src = data.get('post_import_filters') or []
    if filters_src:
        f_rows = []
        fi_rows = []
        for f in filters_src:
            fi = f.get('identifier')
            if not fi:
                continue
            f_rows.append({
                'id': f'@filter.{fi}',
                'identifier': fi,
                'localize_infos': f.get('localize_infos') or {},
                'scope_types': f.get('scope_types') or [],
            })
            # filter items: one per attribute_identifier (object_type='attribute')
            for ident in (f.get('attribute_identifiers') or []):
                fi_rows.append({
                    'filter_id': f'@filter.{fi}',
                    'object_type': 'attribute',
                    'object_id': 0,  # admin re-resolves by value_text
                    'value_text': ident,
                })
            # direct_items (page/product/discount) if mapper emitted any
            for it in (f.get('direct_items') or []):
                fi_rows.append({
                    'filter_id': f'@filter.{fi}',
                    'object_type': it.get('object_type'),
                    'object_id': it.get('object_id', 0),
                    'value_text': it.get('value_text') or '',
                })
        n1 = _push('filters', f_rows, key='id')
        # filter_items has no stable natural key — push all
        n2 = len(fi_rows)
        if n2:
            tables.setdefault('filter_items_mn', []).extend(fi_rows)
        if n1 or n2:
            fixes.append(f"+ tables.filters: {n1} filters, {n2} filter_items")

    return fixes


def fill_block_pages_mn_from_source(data, project_root):
    """Universally derive `block_pages_mn` from source files via TRANSITIVE
    import resolution (not just direct import).

    Algorithm:
      1. Resolve each block identifier → React component file name
         (snake_case → PascalCase, e.g. `hero_slider` → `HeroSlider.tsx`).
      2. Build a component import graph: for every `*.tsx` in
         `src/app/components/`, parse `import … from '…/<Component>'` lines
         to compute the set of child components each one references.
      3. For each page file, BFS up to depth 4 starting from direct imports
         to collect ALL transitively-reachable components.
      4. For every block whose component appears in a page's reachable set,
         add a `block_pages_mn` row.
      5. Special-case binding rules:
         - ProductDetailPage transitive components → bind to ALL `forProducts_*`
           category pages (the dynamic route renders for every product),
         - Header/Footer transitive components → not bound (global chrome),
         - Catalog wrappers (CatalogTemplate, AccessoriesCatalog, ShoesCatalog)
           → propagate to their catalog leaf pages.

    Page-identifier derivation:
      HomePage → root, WomenCatalogPage → women, MenShoesPage → men-shoes,
      NewArrivalsPage → new, NotFoundPage → 404, …

    Universal across Next.js / CRA / Vite projects with the standard
    `src/app/components/` + `pages/` convention. Idempotent.
    """
    fixes = []
    if not project_root:
        return fixes
    from pathlib import Path as _Path
    root = _Path(project_root)
    if not root.exists():
        return fixes
    blocks = data.get('blocks') or []
    pages_idents = {p.get('identifier') for p in (data.get('pages') or []) if p.get('identifier')}
    if not blocks or not pages_idents:
        return fixes
    comp_dirs = [
        root / 'src' / 'app' / 'components',
        root / 'src' / 'components',
        root / 'app' / 'components',
    ]
    page_files = []
    for pat in ('src/app/pages/*.tsx', 'src/pages/*.tsx', 'src/app/**/page.tsx'):
        page_files.extend(root.glob(pat))
    if not page_files:
        return fixes

    def _pascal(s):
        return ''.join(part.capitalize() for part in s.split('_'))

    # 1. Index every component file (.tsx) by its PascalCase name
    component_files = {}  # name → Path
    for cd in comp_dirs:
        if not cd.exists():
            continue
        for f in cd.rglob('*.tsx'):
            component_files[f.stem] = f

    # 2. Compute import graph: for each component, set of child component names
    #    referenced via `from '...components/X'` or `from './X'` patterns.
    IMPORT_RE = re.compile(
        r"""import\s+(?:[\w*{}\s,]+\s+from\s+)?['"]([^'"]+)['"]""",
        re.MULTILINE,
    )
    def _extract_imports(file_path):
        try:
            text = file_path.read_text()
        except (OSError, UnicodeDecodeError):
            return set()
        out = set()
        for m in IMPORT_RE.finditer(text):
            path = m.group(1)
            # Last segment is the imported file/component name
            last = path.split('/')[-1]
            if last and last[0].isupper() and last in component_files:
                out.add(last)
        return out

    import_graph = {name: _extract_imports(path) for name, path in component_files.items()}

    # 3. BFS expansion to depth 4
    def _reachable(seed_names, max_depth=4):
        visited = set()
        frontier = set(seed_names)
        depth = 0
        while frontier and depth < max_depth:
            new_frontier = set()
            for name in frontier:
                if name in visited:
                    continue
                visited.add(name)
                new_frontier |= import_graph.get(name, set()) - visited
            frontier = new_frontier
            depth += 1
        return visited

    # Always-skip components — global chrome, layout, utility
    SKIP = {
        'Header', 'Footer', 'HeaderMegaMenu', 'HeaderMobileDrawer',
        'MiniCart', 'CheckoutStepper', 'LoginModal', 'Providers',
        'ProductCard', 'ProductCardSkeleton', 'ColorSwatch',
        'ImageWithFallback', 'MobileFilterPanel', 'MobileFilterBody',
        'CatalogMobileSort', 'CatalogListProductCard', 'FormField',
        'SizeDropdown', 'QtyControl', 'RadioCard', 'NoFilterResults',
        'JsonLd', 'ErrorBoundary', 'HomeScrollNotify',
    }

    # PAGE_ALIASES is a fallback dictionary for project-specific filename →
    # identifier mappings (filenames are NOT universal — different projects
    # name their landing/cart/error pages differently). The CANONICAL source
    # of truth is `mapped.yaml::pages[]` itself — `_page_ident` first tries
    # to match the file's role to a registered page; the alias dict is a
    # last-resort heuristic for the reference fashion-shop project. For
    # restaurant / hotel / EdTech / SaaS projects this dict is typically
    # ignored (their file names don't match) and the kebab-case fallback
    # picks up the slack.
    PAGE_ALIASES = {
        'Home': 'root', 'Landing': 'root', 'Index': 'root', 'Root': 'root',
        'NotFound': '404', 'Error': '500', 'ServerError': '500',
        'Offline': 'offline', 'Maintenance': 'offline',
        # Reference (fashion-shop) only — feel free to ignore for other projects.
        'WomenCatalog': 'women', 'MenCatalog': 'men',
        'NewArrivals': 'new', 'Sale': 'sale', 'Cart': 'cart',
        'Favorites': 'favorites', 'Account': 'account',
        'StoreLocations': 'stores',
        'Confirmation': 'checkout-confirmation',
        'Delivery': 'checkout-delivery', 'Payment': 'checkout-payment',
        'FilterSystemDownload': None, 'Info': None,
    }

    # Build a map of mapper-emitted pages: page_url + identifier → identifier.
    # This is the PRIMARY lookup — alias dict is fallback only.
    pages_by_url = {}
    pages_by_ident_lower = {}
    for p in (data.get('pages') or []):
        ident = p.get('identifier')
        url = (p.get('page_url') or '').strip()
        if not ident:
            continue
        pages_by_ident_lower[ident.lower()] = ident
        if url:
            pages_by_url[url] = ident

    def _page_ident(stem):
        bare = stem[:-4] if stem.endswith('Page') else stem
        # 1) project alias hit
        if bare in PAGE_ALIASES:
            return PAGE_ALIASES[bare]
        # 2) try kebab-case → match against registered pages by url or ident
        kebab = re.sub(r'(?<!^)(?=[A-Z])', '-', bare).lower()
        if kebab in pages_by_url:
            return pages_by_url[kebab]
        if kebab in pages_by_ident_lower:
            return pages_by_ident_lower[kebab]
        # 3) try snake_case
        snake = re.sub(r'(?<!^)(?=[A-Z])', '_', bare).lower()
        if snake in pages_by_ident_lower:
            return pages_by_ident_lower[snake]
        return kebab  # last-resort fallback (may warn-but-bind)

    # Page → all transitively reachable components
    page_to_components = {}
    product_detail_components = set()
    for pf in page_files:
        seed = _extract_imports(pf)
        # Direct imports declared from `./pages/X` could also be sub-pages.
        reachable = _reachable(seed, max_depth=4) - SKIP
        if pf.stem == 'ProductDetailPage':
            product_detail_components = reachable
            continue  # handled separately
        page_ident = _page_ident(pf.stem)
        if not page_ident:
            continue
        page_to_components[page_ident] = reachable

    # 4. Bind blocks to pages
    block_pages_mn = data.setdefault('block_pages_mn', [])
    existing = {(r.get('block'), r.get('page')) for r in block_pages_mn
                if r.get('block') and r.get('page')}
    added = 0
    block_by_pascal = {_pascal(b.get('identifier') or ''): b.get('identifier')
                       for b in blocks if b.get('identifier')}

    for page_ident, components in page_to_components.items():
        if page_ident not in pages_idents:
            continue
        for comp in components:
            blk_ident = block_by_pascal.get(comp)
            if not blk_ident:
                continue
            key = (blk_ident, page_ident)
            if key in existing:
                continue
            block_pages_mn.append({'block': blk_ident, 'page': page_ident})
            existing.add(key)
            added += 1

    # 5. ProductDetailPage transitive components → bind to all catalog leaves
    #    (every product page reuses the same set of detail-page blocks).
    if product_detail_components:
        catalog_leaves = [
            p.get('identifier') for p in (data.get('pages') or [])
            if p.get('identifier') and (p.get('general_type_id') in (4, 17))
            and p.get('identifier') not in ('root',)
        ]
        for comp in product_detail_components:
            blk_ident = block_by_pascal.get(comp)
            if not blk_ident:
                continue
            for page_ident in catalog_leaves:
                if page_ident not in pages_idents:
                    continue
                key = (blk_ident, page_ident)
                if key in existing:
                    continue
                block_pages_mn.append({'block': blk_ident, 'page': page_ident})
                existing.add(key)
                added += 1

    if added:
        fixes.append(f"+ block_pages_mn: {added} block↔page bindings "
                     f"auto-derived from source (transitive depth-4 scan)")
    return fixes


def fill_products_pages_mn(data, project_root):
    """Auto-bind every product to its category page based on identifier prefix.

    Most catalog projects encode the category in the product identifier (e.g.
    `wc-1` = women-clothing, `mc-7` = men-clothing, `sale-3` = sale). Without
    `products_pages_mn` rows the storefront catalog renders empty pages —
    products exist but no page knows about them.

    Universal heuristic — works for any vertical:
      1. Take every page with `general_type_id=4` (catalog_page).
      2. Build a prefix→page map from page identifier (e.g. `women-clothing` → wc-).
      3. Match every product identifier to a page by longest-prefix.
      4. Append a `products_pages_mn` row per match.

    Idempotent: only adds rows that don't already exist.
    """
    fixes = []
    products = data.get('products') or []
    pages = data.get('pages') or []
    if not products or not pages:
        return fixes
    # Build a prefix → page-identifier map. Common patterns observed across
    # verticals: `women-clothing` (e-commerce), `main-courses` (restaurant),
    # `hair-treatments` (salon), `frontend-courses` (EdTech).
    # Use the FIRST 2 chars of each catalog page identifier as the prefix key.
    catalog_pages = [p for p in pages
                     if p.get('general_type_id') in (4, '4')
                     and p.get('identifier')]
    page_prefixes = {}
    for p in catalog_pages:
        ident = p['identifier']
        # Derive a 2-char product-identifier prefix from page slug. For
        # "women-clothing" → "wc"; "men-shoes" → "ms"; "main-courses" → "mc".
        words = re.split(r'[-_]+', ident)
        if len(words) >= 2:
            prefix = (words[0][0] + words[1][0]).lower()
        elif words:
            prefix = words[0][:2].lower()
        else:
            continue
        # Multiple pages may resolve to the same prefix; keep the most specific
        # by longer identifier length (women-clothing > women).
        cur = page_prefixes.get(prefix)
        if cur is None or len(ident) > len(cur):
            page_prefixes[prefix] = ident

    existing = data.setdefault('products_pages_mn', [])
    existing_keys = {(r.get('product'), r.get('page')) for r in existing}
    added = 0
    for prod in products:
        pid = prod.get('identifier')
        if not pid:
            continue
        parts = pid.split('-')
        # Try 2-char prefix first ("wc", "ms"), then word prefix ("sale")
        prefix = parts[0][:2].lower() if parts and len(parts[0]) >= 2 else None
        page_ident = page_prefixes.get(prefix)
        if not page_ident and parts:
            # Fall back: try the whole first word as a page identifier match.
            for p_ident in (cp['identifier'] for cp in catalog_pages):
                if p_ident == parts[0].lower():
                    page_ident = p_ident
                    break
        if not page_ident:
            continue
        key = (pid, page_ident)
        if key in existing_keys:
            continue
        existing.append({'product': pid, 'page': page_ident})
        existing_keys.add(key)
        added += 1
    if added:
        fixes.append(
            f"+ products_pages_mn: {added} product↔page bindings auto-derived "
            f"from identifier prefixes (catalog populated)"
        )
    return fixes


def check_slider_blocks_have_slides(data):
    """S66 invariant check — every static slider_block (gtid=25) that is
    visible AND bound to a page MUST have slides emitted.

    Adds a warning entry per non-conformant block. Universal across project
    types — server-populated sliders (gtids 26-32) are exempt.
    """
    fixes = []
    blocks = data.get('blocks') or []
    if not blocks:
        return fixes
    block_bindings = {b.get('identifier') for b in (data.get('block_pages_mn') or [])
                      if b.get('block')}
    slides_tasks = {(t.get('block_identifier') or t.get('block'))
                    for t in (data.get('post_import_slides') or [])}
    skip_markers = set((data.get('notes', {}) or {}).get('skip_slides') or [])
    warnings_list = data.setdefault('warnings', [])
    flagged = 0
    for b in blocks:
        # Only static slider_block (25). Server-populated sliders are exempt.
        if b.get('general_type_id') != 25:
            continue
        if b.get('is_visible') is False:
            continue
        ident = b.get('identifier')
        if not ident or ident in skip_markers:
            continue
        # Must be bound to a page (block_pages_mn check) AND have slides
        if ident not in block_bindings:
            continue
        if ident not in slides_tasks:
            warnings_list.append(
                f"S66 slider_block '{ident}' is visible + page-bound but has "
                f"NO slides — admin will render an empty carousel. Either "
                f"provide source slide data or add to "
                f"`mapped.notes.skip_slides: [{ident!r}]`."
            )
            flagged += 1
    if flagged:
        fixes.append(f"S66: flagged {flagged} slider_block(s) without slides")
    return fixes


def check_visible_collections_have_rows(data):
    """S67 invariant — every visible collection (referenced by a page or block
    or matching a top-level page URL) MUST have ≥ 1 collection_row.

    Universal across project types.
    """
    fixes = []
    tables = data.get('tables') or {}
    colls = tables.get('collections') or data.get('collections') or []
    rows = tables.get('collection_rows') or data.get('collection_rows') or []
    if not colls:
        return fixes
    rows_per_coll = {}
    for r in rows:
        cid = r.get('collection_id')
        rows_per_coll[cid] = rows_per_coll.get(cid, 0) + 1
    # Build the "visible" set: collection identifier matches any page identifier
    page_idents = {p.get('identifier') for p in (data.get('pages') or [])
                   if p.get('identifier')}
    warnings_list = data.setdefault('warnings', [])
    flagged = 0
    for c in colls:
        ident = c.get('identifier')
        coll_id = c.get('id') or f'@coll.{ident}'
        # Visible? — identifier matches a page slug
        visible = ident in page_idents or any(
            ident in (p.get('identifier') or '') for p in (data.get('pages') or [])
        )
        if not visible:
            continue
        n = rows_per_coll.get(coll_id, 0)
        if n == 0:
            warnings_list.append(
                f"S67 collection '{ident}' is referenced by a page but has "
                f"0 rows — admin will render an empty list (silent broken UX)."
            )
            flagged += 1
    if flagged:
        fixes.append(f"S67: flagged {flagged} visible collection(s) with 0 rows")
    return fixes


def bind_offline_page_to_error_code(data, languages):
    """Bind standard HTTP error codes to existing error pages:
      - 404 → page with identifier `404` / `not-found` / `not_found`
      - 500 → page with identifier `500` / `error` / `server-error`
      - 503 → page with identifier `offline` / `503` / `maintenance`

    Universal: every web project ships a 404 page, most ship 500/503 too.
    Without these bindings the cms storefront cannot resolve which page to
    render for each HTTP error code. Idempotent.
    """
    fixes = []
    pages = data.get('pages') or []
    page_idents = {p.get('identifier') for p in pages if p.get('identifier')}
    tasks = data.setdefault('post_import_page_errors', [])
    existing_codes = set()
    for t in tasks:
        code = t.get('code') or t.get('http_code')
        if code is not None:
            existing_codes.add(int(code))
    # Map HTTP code → list of candidate page identifiers (first hit wins).
    CODE_BINDINGS = [
        (404, ['404', 'not-found', 'not_found', 'notfound']),
        (500, ['500', 'error', 'server-error', 'internal_error', '5xx']),
        (503, ['offline', '503', 'maintenance', 'unavailable']),
    ]
    added = 0
    for code, candidates in CODE_BINDINGS:
        if code in existing_codes:
            continue
        target = next((c for c in candidates if c in page_idents), None)
        if not target:
            continue
        tasks.append({'http_code': code, 'page_identifier': target})
        existing_codes.add(code)
        added += 1
    if added:
        fixes.append(f"+ post_import_page_errors: bound {added} standard HTTP codes "
                     f"({', '.join(str(c) for c, _ in CODE_BINDINGS if c in existing_codes)})")
    return fixes


def normalize_page_urls(data):
    """Strip `/` from every `pages[].page_url`. In OneEntry, `page_url` is a
    single URL segment (the hierarchy is reconstructed via `parent_id`). Mapper
    sometimes emits Next.js-style multi-segment paths (`download/filter-system`,
    `product/[id]`) — convert to the last segment.

    Universal: every project that uses file-system-based routing will hit this.
    """
    fixes = []
    n = 0
    for p in (data.get('pages') or []):
        url = p.get('page_url')
        if not isinstance(url, str) or '/' not in url:
            continue
        new_url = url.rstrip('/').split('/')[-1].strip('[]') or url.replace('/', '-')
        p['page_url'] = new_url
        n += 1
    if n:
        fixes.append(f"pages: normalized {n} page_url values (stripped '/' to single-segment)")
    return fixes


_DISCOUNT_LIKE_FIELDS_ON_USERGROUP = (
    'default_discount', 'group_discount', 'tier_discount',
    'discount_percent', 'discount_value', 'discount',
    'bonus_percent', 'cashback_percent', 'cashback',
)


def strip_discount_fields_from_usergroup(data):
    """Remove discount-shaped attributes from `forUserGroups` schema.

    OneEntry has a dedicated `Discounts` module that handles all promotion
    rules. Putting `default_discount` / `tier_discount` on the user-group
    attribute_set creates a UX trap: content admins try to set discounts in
    two places, and one of them silently has no storefront effect. Strip them
    in the mapped layer so the admin sees the Discounts module as the single
    source of truth.

    Universal — applies to any project type.
    """
    fixes = []
    asets = data.get('attributes_sets') or []
    removed = 0
    for aset in asets:
        if aset.get('identifier') != 'forUserGroups':
            continue
        schema = aset.get('schema') or {}
        for key in list(schema.keys()):
            ident = schema[key].get('identifier') if isinstance(schema[key], dict) else None
            check_name = (ident or key).lower().replace('-', '_')
            if any(d in check_name for d in _DISCOUNT_LIKE_FIELDS_ON_USERGROUP):
                schema.pop(key)
                removed += 1
    if removed:
        fixes.append(
            f"forUserGroups: removed {removed} discount-shaped attrs "
            f"(discounts live in the Discounts module, not on user_groups)"
        )
    return fixes


def fill_empty_block_titles(data, languages):
    """For any block whose `attributes_sets[lang]` has an empty `title`, fill it
    from the block identifier (snake_case → Title Case). Better than blank.

    Universal across project types — every empty block in admin UI looks broken.
    """
    fixes = []
    primary_lang = languages[0] if languages else 'en_US'
    filled = 0
    for b in (data.get('blocks') or []):
        attrs_sets = b.setdefault('attributes_sets', {})
        lang_attrs = attrs_sets.setdefault(primary_lang, {})
        if lang_attrs.get('title'):
            continue
        ident = b.get('identifier') or ''
        if not ident:
            continue
        title = ident.replace('_', ' ').replace('-', ' ').strip().title()
        lang_attrs['title'] = title
        filled += 1
    if filled:
        fixes.append(
            f"blocks: filled empty title for {filled} blocks with derived "
            f"snake_case→Title Case from identifier"
        )
    return fixes


def _extract_all_exported_values(text):
    """Yield (var_name, value) for every `export const NAME = …;` in a TS/JS
    file body. Handles nested Records / arrays of arbitrary depth.

    Returns Python-native values (`dict` / `list` / `str` / `int` / `bool`).
    Universal — no project-specific assumptions.
    """
    import json as _json
    text_clean = re.sub(r'/\*[\s\S]*?\*/', '', text)
    pattern = re.compile(
        r'export\s+(?:default\s+)?const\s+([A-Z_a-z][\w]*)'
        r'(?:\s*:\s*[\w\[\]<>,\s|]+)?\s*=\s*([{\[])'
    )
    for m in pattern.finditer(text_clean):
        name = m.group(1)
        opener = m.group(2)
        if opener == '[':
            body = _extract_balanced_array(text_clean, m.end() - 1)
        else:
            body_inner = _extract_balanced_object(text_clean, m.end() - 1)
            body = body_inner if body_inner else None
        if not body:
            continue
        js = body
        # keys: word: -> "word":   (don't touch URLs / identifiers inside strings)
        js = re.sub(r'([{\[,]\s*)(\w+)\s*:', r'\1"\2":', js)
        js = re.sub(r"'((?:[^'\\]|\\.)*)'",
                    lambda mm: '"' + mm.group(1).replace('\\\'', '\'')
                                          .replace('\\', '\\\\').replace('"', '\\"')
                                          .replace('\n', '\\n') + '"', js)
        js = re.sub(r"`((?:[^`\\]|\\.)*)`",
                    lambda mm: '"' + mm.group(1).replace('\\', '\\\\').replace('"', '\\"')
                                          .replace('\n', '\\n') + '"', js)
        js = re.sub(r',\s*([\]}])', r'\1', js)
        try:
            value = _json.loads(js)
        except Exception:
            continue
        yield name, value


# Universal: identifier-fragments that suggest a navigation source file.
_NAV_FILE_HINTS = (
    'header', 'footer', 'menu', 'menus', 'nav', 'navigation',
    'sitemap', 'mega', 'categories', 'category', 'sections',
)
# Universal: keys whose VALUE in a typed Record/dict semantically represents
# a child group at the next nesting level. Order = priority.
_NAV_GROUPING_KEYS = (
    'items', 'children', 'subitems', 'sub_items', 'subcategories',
    'sub_categories', 'links', 'chips', 'sections', 'columns',
    'cards', 'nodes',
)


def _max_nesting_depth(value, depth=0):
    """Universal: maximum depth of nested containers in `value`.
    Flat string-array → depth 1; Record<G, T[]> → 2; Record<G, Record<S, T[]>>
    → 3; etc. Used to gate the menu scanner: anything shallower than depth 2
    is just a list of choices, not a navigation tree.
    """
    if isinstance(value, dict) and value:
        return 1 + max((_max_nesting_depth(v, depth + 1) for v in value.values()), default=0)
    if isinstance(value, list) and value:
        return 1 + max((_max_nesting_depth(v, depth + 1) for v in value
                        if isinstance(v, (dict, list))), default=0)
    return 0


def _looks_like_nav_tree(value, depth=0, max_depth=6):
    """Heuristic: does `value` look like a hierarchical navigation tree?
    Returns int score (0 if not, higher = more menu-like).

    Recognises three universal shapes simultaneously:
      • Record<key, {…children…}>     — top-level grouping by record key
      • Record<key, Array<…children…>> — nav tabs with arrays of items
      • Array<{label, href, children?}> — flat or nested item arrays
    Uses presence of label/href/title/items keys + nesting depth as signal.
    Refuses bare flat string arrays (HEADER_LANGUAGES = ['EN', 'DE', …]) and
    single-record-of-strings; both routinely show up in source but aren't
    navigation.
    """
    if depth > max_depth:
        return 0
    # Universal gate: require at least 2 levels of nesting to qualify as a tree
    if depth == 0 and _max_nesting_depth(value) < 2:
        return 0
    if isinstance(value, dict):
        score = 0
        if len(value) >= 2:
            score += 1
        for v in value.values():
            score += _looks_like_nav_tree(v, depth + 1, max_depth)
        for k in ('label', 'title', 'name', 'href', 'url', 'path', 'link', 'page'):
            if k in value:
                score += 1
                break
        return score
    if isinstance(value, list) and value:
        score = 0
        for it in value[:8]:
            if isinstance(it, (dict, list)):
                score += _looks_like_nav_tree(it, depth + 1, max_depth)
            elif isinstance(it, str) and len(it) <= 80:
                score += 1  # bare-string children (e.g. items: ['Pants', 'Jeans'])
        return score
    return 0


def _slugify_for_menu(text):
    """Universal slugifier — preserves identifier stability across runs."""
    import re as _re
    if not isinstance(text, str) or not text.strip():
        return ''
    s = text.strip().lower()
    s = _re.sub(r"['\"`’]", '', s)
    s = _re.sub(r'[^a-z0-9]+', '_', s)
    s = s.strip('_')
    return s or 'item'


def _walk_nav_tree(value, parent_ident, primary_lang, depth=0, out=None,
                   prefix='', max_depth=6):
    """Recursively flatten a hierarchical nav structure into a list of
    `{identifier, label, href?, parent_identifier}` records. Universal —
    handles dict-of-dicts, dict-of-arrays, and array-of-{label, href, items}
    shapes interchangeably.

    Each emitted record carries a STABLE identifier derived from the
    label/key path so re-runs over the same source produce the same tree.
    """
    if out is None:
        out = []
    if depth > max_depth:
        return out
    if isinstance(value, dict):
        # 1. Pure record `Record<key, child>` — each key is a category label.
        # Skip if dict looks like a single item (has its own label/href).
        own_label = value.get('label') or value.get('title') or value.get('name')
        own_href = value.get('href') or value.get('url') or value.get('path') or value.get('link')
        children_keys = [k for k, v in value.items()
                         if k not in ('label', 'title', 'name', 'href', 'url',
                                      'path', 'link', 'icon', 'image',
                                      'is_pinned', 'pinned')]
        if own_label or own_href:
            ident = _slugify_for_menu(f'{prefix}{own_label or own_href or "node"}')
            entry = {
                'identifier':      ident,
                'parent_identifier': parent_ident or None,
                'label':           own_label or own_href,
                'href':            own_href or '',
                'localize_infos':  {primary_lang: {'title': own_label or own_href or ''}},
            }
            out.append(entry)
            # Recurse into a `items`/`children`/... grouping key
            for gk in _NAV_GROUPING_KEYS:
                if isinstance(value.get(gk), (list, dict)):
                    _walk_nav_tree(value[gk], ident, primary_lang,
                                   depth + 1, out, prefix=f'{ident}_',
                                   max_depth=max_depth)
            return out
        # 2. Pure record — each key becomes a parent of its value subtree
        for k in children_keys:
            v = value[k]
            if not isinstance(k, str):
                continue
            key_ident = _slugify_for_menu(f'{prefix}{k}')
            label = k if k.isupper() or any(c.isalpha() for c in k) else str(k)
            out.append({
                'identifier':        key_ident,
                'parent_identifier': parent_ident or None,
                'label':             label,
                'href':              '',  # pure grouping node
                'localize_infos':    {primary_lang: {'title': label.replace('_', ' ').title()}},
            })
            _walk_nav_tree(v, key_ident, primary_lang,
                           depth + 1, out, prefix=f'{key_ident}_',
                           max_depth=max_depth)
        return out
    if isinstance(value, list):
        # 3. Array of items — each item is either dict, list, or string leaf
        for it in value:
            if isinstance(it, dict):
                _walk_nav_tree(it, parent_ident, primary_lang,
                               depth + 1, out, prefix=prefix,
                               max_depth=max_depth)
            elif isinstance(it, list):
                _walk_nav_tree(it, parent_ident, primary_lang,
                               depth + 1, out, prefix=prefix,
                               max_depth=max_depth)
            elif isinstance(it, str) and it.strip():
                leaf_ident = _slugify_for_menu(f'{prefix}{it}')
                out.append({
                    'identifier':        leaf_ident,
                    'parent_identifier': parent_ident or None,
                    'label':             it,
                    'href':              '',
                    'localize_infos':    {primary_lang: {'title': it}},
                })
        return out
    return out


def _scan_hierarchical_menus(project_root, primary_lang):
    """Detect data files that export a hierarchical navigation structure and
    flatten them into the universal `[{identifier, parent_identifier, label,
    href}, …]` form ready for `post_import_menus`.

    Universal: works for any vertical (catalog, hospitality, education) and
    any nesting depth (Gender → Subcat → Section → Item, or Region → Country
    → City → Branch, or Year → Course → Module → Lesson).

    Returns dict {menu_kind: [items]} where menu_kind is `header` or `footer`
    inferred from filename (default: `header` if neither hint matches).
    """
    if not project_root:
        return {}
    root = Path(project_root)
    if not root.exists():
        return {}
    skip_dirs = {'node_modules', '.next', '.git', 'dist', 'build', '.turbo',
                 '.cache', '__tests__', 'stories', 'storybook-static'}
    result = {}
    for path in root.rglob('*'):
        if not path.is_file() or path.suffix not in ('.ts', '.tsx', '.js', '.jsx', '.mjs', '.cjs'):
            continue
        if any(part in skip_dirs or part.startswith('.')
               for part in path.relative_to(root).parts):
            continue
        stem = path.stem.lower().replace('-', '').replace('_', '')
        if not any(h in stem for h in _NAV_FILE_HINTS):
            continue
        try:
            text = path.read_text(encoding='utf-8', errors='ignore')
        except OSError:
            continue
        # Find the deepest / most-menu-like exported structure
        best = (0, None, None)  # (score, name, value)
        for name, value in _extract_all_exported_values(text):
            score = _looks_like_nav_tree(value)
            if score > best[0]:
                best = (score, name, value)
        if best[0] < 4:
            continue
        # Decide menu_kind by filename
        menu_kind = 'header'
        if 'footer' in stem:
            menu_kind = 'footer'
        # Walk into a flat list with parent_identifier chain
        items = _walk_nav_tree(best[2], None, primary_lang)
        if not items:
            continue
        bucket = result.setdefault(menu_kind, [])
        # Dedupe by identifier (some sources have repeated leaves under
        # different parents — we preserve the first occurrence).
        seen = {i.get('identifier') for i in bucket}
        for it in items:
            if it.get('identifier') in seen:
                continue
            seen.add(it.get('identifier'))
            bucket.append(it)
    return result


def fill_post_import_menus(data, project_root, languages):
    """Build / extend `mapped.post_import_menus[]` with items parsed from
    `headerConfig.ts` / `footerConfig.ts`-style source files.

    Idempotent: only adds items that are missing in the existing task list.
    Universal across project types — any nav-config file shaped as
    `Record<group, Link[]>` is processed.
    """
    fixes = []
    if not project_root or not Path(project_root).exists():
        return fixes
    primary_lang = languages[0] if languages else 'en_US'

    # Phase 1: try hierarchical scan first (universal — handles arbitrarily
    # nested Record<G, Record<S, T[]>> shapes). Falls back to the flat
    # `_scan_menu_configs` if nothing structural matches.
    hier = _scan_hierarchical_menus(project_root, primary_lang)
    parsed_flat = _scan_menu_configs(project_root)
    if not hier and not parsed_flat:
        return fixes

    tasks = data.setdefault('post_import_menus', [])
    by_ident = {t.get('identifier'): t for t in tasks if t.get('identifier')}
    added_items = 0

    # Phase 1: HIERARCHICAL menus — record each item with its parent chain.
    for menu_kind, items in hier.items():
        task = by_ident.get(menu_kind)
        if task is None:
            task = {
                'identifier':     menu_kind,
                'localize_infos': {primary_lang: {'title': menu_kind.title()}},
                'items':          [],
                'custom_items':   [],
            }
            tasks.append(task)
            by_ident[menu_kind] = task
        # Existing identifiers — avoid duplicate emission on re-runs
        seen_idents = {i.get('identifier') for i in (task.get('items') or [])}
        seen_idents.update(c.get('identifier') for c in (task.get('custom_items') or []))
        for item in items:
            ident = item.get('identifier')
            if not ident or ident in seen_idents:
                continue
            seen_idents.add(ident)
            href = (item.get('href') or '').strip()
            label = item.get('label') or ident
            parent_ident = item.get('parent_identifier')
            # Choose the right table:
            #   • Non-empty internal href → menu_pages_mn (resolves to a page slug)
            #   • Otherwise (external URL OR no link)   → menu_custom_items_mn
            slug = href.lstrip('/').replace('/', '-') if (href and '://' not in href) else None
            if slug:
                entry = {
                    'identifier':        ident,
                    'parent_identifier': parent_ident,
                    'page_slug':         slug,
                    'localize_infos':    {primary_lang: {'title': label}},
                }
                task.setdefault('items', []).append(entry)
            else:
                entry = {
                    'identifier':        ident,
                    'parent_identifier': parent_ident,
                    'value':             href,
                    'localize_infos':    {primary_lang: {'title': label}},
                }
                task.setdefault('custom_items', []).append(entry)
            added_items += 1

    # Phase 2: FLAT fallback for menus that the hierarchical scan didn't catch
    # (regex-extracted `{label, href}` literals from header/footer configs).
    for menu_kind, items in parsed_flat.items():
        task = by_ident.get(menu_kind)
        if task is None:
            task = {
                'identifier':     menu_kind,
                'localize_infos': {primary_lang: {'title': menu_kind.title()}},
                'items':          [],
                'custom_items':   [],
            }
            tasks.append(task)
            by_ident[menu_kind] = task
        seen_hrefs = {p.get('page_slug') for p in (task.get('items') or [])}
        seen_hrefs.update(c.get('value') for c in (task.get('custom_items') or []))
        seen_labels = {(p.get('localize_infos') or {}).get(primary_lang, {}).get('title')
                       for p in (task.get('items') or []) + (task.get('custom_items') or [])}
        for item in items:
            href = item['href']
            label = item['label']
            slug = href.lstrip('/').replace('/', '-') or None
            if (slug in seen_hrefs and slug) or label in seen_labels:
                continue
            if slug:
                task.setdefault('items', []).append({
                    'page_slug':      slug,
                    'localize_infos': {primary_lang: {'title': label}},
                })
            else:
                task.setdefault('custom_items', []).append({
                    'value':          href,
                    'localize_infos': {primary_lang: {'title': label}},
                })
            seen_hrefs.add(slug); seen_labels.add(label)
            added_items += 1
    if added_items:
        hier_n = sum(len(v) for v in hier.values())
        fixes.append(
            f"+ menu items: {added_items} navigation entries added "
            f"({hier_n} hierarchical + {added_items - hier_n} flat) "
            f"from nav-source scan"
        )
    return fixes


def generate_user_permissions(data, languages):
    """Generate user_permissions + user_group_permissions_mn for the user group.

    Idempotent: if user_permissions are already present in mapped — no-op.
    Loader does upsert by (path, section), so preseed duplicates will not appear.
    """
    fixes = []
    user_groups = data.get('user_groups') or []
    if not any(ug.get('identifier') == 'user' for ug in user_groups):
        return fixes  # no user group — nothing to bind

    existing_perms = data.get('user_permissions') or []
    existing_paths = {p.get('path') for p in existing_perms}
    perms_to_add = []
    for p in USER_PERMISSIONS_TEMPLATE:
        if p['path'] in existing_paths:
            continue
        # localize_infos: {en_US: {title: "Read pages", ...}}
        lang_titles = {lang: {'title': p['path']} for lang in languages}
        perms_to_add.append({
            'id': '@perm.' + p['path'].replace('/', '_').replace('{', '').replace('}', ''),
            'path': p['path'],
            'section': p['section'],
            'rules': {'permissions': p['rule'], 'additionalData': {}},
            'localize_infos': lang_titles,
        })
    if perms_to_add:
        data['user_permissions'] = existing_perms + perms_to_add
        fixes.append(f"+ user_permissions: {len(perms_to_add)} permissions for the user group")

    # user_group_permissions_mn (binding to the user group)
    existing_mn = data.get('user_group_permissions_mn') or []
    existing_keys = {
        (m.get('group_id') or m.get('group'),
         m.get('permission_id') or m.get('permission'))
        for m in existing_mn
    }
    mn_to_add = []
    for p in USER_PERMISSIONS_TEMPLATE:
        token_perm = '@perm.' + p['path'].replace('/', '_').replace('{', '').replace('}', '')
        # Compare using the same tokens we write — otherwise the fixer
        # would not see existing entries and would duplicate them on each run.
        key = ('@ug.user', token_perm)
        if key in existing_keys:
            continue
        mn_to_add.append({
            'group_id': '@ug.user',
            'permission_id': token_perm,
        })
    if mn_to_add:
        data['user_group_permissions_mn'] = existing_mn + mn_to_add
        fixes.append(f"+ user_group_permissions_mn: {len(mn_to_add)} bindings to the user group")

    return fixes


def strip_rating_from_non_review_forms(data):
    """Remove `rating` attribute from any `forForms_X` schema where X is not
    `review_rating`. Mapper sometimes carries a `rating: int` field into
    forms like `feedback` / `service_request` — admin then shows a rating
    star UI on a contact form, which is wrong.

    Universal — applies regardless of project vertical (rating is the
    ProductReview concern, isolated to forForms_review_rating).
    """
    fixes = []
    stripped = 0
    for a in (data.get('attributes_sets') or []):
        ident = a.get('identifier') or ''
        if not ident.startswith('forForms_'):
            continue
        if ident == 'forForms_review_rating':
            continue
        sch = a.get('schema') or {}
        if not isinstance(sch, dict):
            continue
        keys_to_drop = []
        for k, item in sch.items():
            if not isinstance(item, dict):
                continue
            if item.get('identifier') == 'rating' or item.get('type') == 'rating':
                keys_to_drop.append(k)
        for k in keys_to_drop:
            del sch[k]
            stripped += 1
    if stripped:
        fixes.append(f"stripped {stripped} `rating` attrs from non-review forms")
    return fixes


def normalize_attribute_schema_shape(data, languages):
    """Final-stage transform of every attribute_set's `schema` so the SCHEMA
    side is admin-ready before blueprint-build.

    Fixes (all verified against `cms_frontend/.../shared/Custom/Attributes/Parameters/`
    and `cms_frontend/.../settings/`):

    1. **listTitles dict → array** — frontend (`ListFieldsParameters.js:109`,
       `ListEntityOptions.js:441`, `ListEntityParameters.js:65`,
       `AttributeWithValueViewer.js:246`, `FormsDataTable.js:642`) reads
       `Array.isArray(options[lang])`; dict `{Sport:"Sport"}` resolves to
       `langOptions=[]` → "Not selected" for every list value.
       Convert to `[{value, title, position}]`.

    2. **listType cleanup** — frontend `ListEntityOptions.js:27-30` only knows
       `flat`/`nested`. Schema sometimes emits `single`/`multiple`. Convert:
         - `'multiple'` → drop `listType`, set `multiselect: true`
         - `'single'` → drop `listType` entirely (default behavior)

    3. **rules → validators[lang]** — frontend never reads `rules.{minLength,
       maxLength, pattern, minValue, maxValue}` directly. Validators must be
       in `validators[lang].{stringInspectionValidator, regExpValidator,
       checkForNumberValidator, requiredValidator}`. Generate from `rules`.

    Universal — applies to every attribute_set regardless of vertical.
    Idempotent — already-array listTitles, already-emitted validators
    are preserved.
    """
    fixes = []
    primary_lang = languages[0] if languages else 'en_US'
    asets = data.get('attributes_sets') or []
    fixed_listTitles = 0
    fixed_listType = 0
    emitted_validators = 0
    for aset in asets:
        sch = aset.get('schema') or {}
        if not isinstance(sch, dict) or not sch:
            continue
        for _k, item in sch.items():
            if not isinstance(item, dict):
                continue
            atype = item.get('type')

            # 1. listTitles dict → array
            lt = item.get('listTitles')
            if isinstance(lt, dict):
                new_lt = {}
                changed = False
                for lang, lmap in lt.items():
                    if isinstance(lmap, list):
                        new_lt[lang] = lmap
                    elif isinstance(lmap, dict):
                        new_lt[lang] = [
                            {'value': v, 'title': t, 'position': i + 1}
                            for i, (v, t) in enumerate(lmap.items())
                        ]
                        changed = True
                    else:
                        new_lt[lang] = []
                if changed:
                    item['listTitles'] = new_lt
                    fixed_listTitles += 1

            # 2. listType: 'single'/'multiple' → multiselect
            ltype = item.get('listType')
            if atype in ('list', 'radioButton') and ltype in ('single', 'multiple'):
                if ltype == 'multiple':
                    item['multiselect'] = True
                # 'single' is the default — no flag needed.
                # Keep `listType` ONLY when it carries semantic meaning for the
                # admin entity-list editor: `flat` / `nested`.
                del item['listType']
                fixed_listType += 1

            # 3. rules → validators[lang]
            rules = item.get('rules') or {}
            if rules:
                validators = item.setdefault('validators', {}) or {}
                v_lang = validators.setdefault(primary_lang, {}) or {}
                # Only emit if validators[lang] doesn't already have this key
                # (preserves any hand-crafted validators).
                generated = False
                if atype in ('string', 'textarea', 'text'):
                    smin = rules.get('minLength')
                    smax = rules.get('maxLength')
                    if (smin or smax) and 'stringInspectionValidator' not in v_lang:
                        v_lang['stringInspectionValidator'] = {
                            'stringMin': int(smin or 0),
                            'stringMax': int(smax or 0),
                            'stringLength': 0,
                        }
                        generated = True
                    if rules.get('pattern') and 'regExpValidator' not in v_lang:
                        v_lang['regExpValidator'] = {
                            'patternValue': rules['pattern'],
                            'invert': False,
                            'flags': [],
                        }
                        generated = True
                if atype in ('integer', 'real') and 'checkForNumberValidator' not in v_lang:
                    minv = rules.get('minValue')
                    maxv = rules.get('maxValue')
                    if minv is not None or maxv is not None:
                        v_lang['checkForNumberValidator'] = {
                            'integerOnly': atype == 'integer',
                            'minValue': float(minv) if minv is not None else 0,
                            'maxValue': float(maxv) if maxv is not None else 0,
                        }
                        generated = True
                if generated:
                    item['validators'] = validators
                    emitted_validators += 1

            # 3b. Default validators for input-form attributes with NO rules.
            # Frontend `StringFieldsParameters.js:227` and friends iterate
            # `validators[lang]` — completely absent block makes them treat
            # the field as "no validation", which is fine for OPTIONAL fields
            # but leaves Validator S70/CHK-009 flagging them. We emit a
            # minimal {requiredValidator: {strict: false}} so the admin shows
            # the field as optional rather than "unconfigured".
            aset_ident = (aset or {}).get('identifier') or ''
            is_input_set = aset_ident.startswith('forForms_') or aset_ident == 'forUsers'
            if is_input_set and atype in ('string', 'textarea', 'text', 'integer', 'real'):
                validators = item.setdefault('validators', {}) or {}
                v_lang = validators.setdefault(primary_lang, {}) or {}
                if not v_lang:
                    v_lang['requiredValidator'] = {'strict': False}
                    item['validators'] = validators
                    emitted_validators += 1
    if fixed_listTitles:
        fixes.append(f"schema listTitles: dict→array on {fixed_listTitles} attributes")
    if fixed_listType:
        fixes.append(f"schema listType: single/multiple cleanup on {fixed_listType} attributes")
    if emitted_validators:
        fixes.append(f"schema validators[lang]: emitted from rules for {emitted_validators} attributes")
    return fixes


def transform_attribute_data_to_admin_shape(data, languages):
    """Final-stage transform of every entity's `attributes_sets[lang]` data so
    that the blueprint embeds **admin-ready** values — no post-import SQL
    needed to align keys or fix shapes.

    For each entity that has `attribute_set` field (products, blocks, pages,
    forms, user_groups, slides, plus `post_import_slides[].attributes_sets`):
      1. RENAME semantic keys (`title`, `brand`, `colors`) → schema keys
         `<type>_id<innerId>` (e.g. `string_id1`, `list_id3`, `image_id7`).
         Done by walking the matching `attributes_sets[].schema` and looking
         up `identifier` field.
      2. NORMALIZE per-type shape:
         - `string` / `textarea` → string
         - `text` → `{htmlValue, plainValue, mdValue, params:{editorMode:"HTML"}}`
         - `integer` / `real`    → string (admin parses with parseFloat)
         - `list`                → `[{value: X}]` or `[{value:a},{value:b}]`
         - `image` / `groupOfImages` → `[{filename, downloadLink, previewLink}]`
         - `radioButton`         → non-empty string OR drop key
         - `button`              → object `{value, href}`
      3. BACKFILL missing schema keys with type-appropriate empty defaults so
         the admin form renderers receive a valid (empty) shape instead of
         `undefined` (which crashes some renderers).

    Universal across project verticals.
    Idempotent — values already in `<type>_id<N>` form are preserved.
    Frontend renderer file citations:
      - TextFieldsParameters.js:99,822-823 (text editor shape)
      - ListFieldsParameters.js:137,162-165 (list[].value)
      - ImageFieldsParameters/ImageFieldsParameters.js:59,98 (image array)
      - NumberFieldsParameters.js:68-70 (number→string for trim())
      - RadioButtonFieldsParameters.js:34,44,56 (option.value)
    """
    fixes = []
    primary_lang = languages[0] if languages else 'en_US'
    asets = data.get('attributes_sets') or []
    aset_by_ident = {a.get('identifier'): a for a in asets if a.get('identifier')}

    renamed = 0
    shaped = 0
    backfilled = 0
    text_wrapped = 0

    def _schema_id_map(aset):
        """Build identifier → (innerId, type) lookup from an attribute_set's schema.

        Important: in mapped.yaml schema entries usually do NOT carry an `id`
        field — CMS BlueprintLoaderService assigns `id` sequentially in
        Python-dict insertion order when normalizing to `attributeN` keys
        (verified via DB introspection on `attributes_sets.schema::jsonb`).
        We mirror that algorithm so `<type>_id<N>` keys we write here match
        what the admin renderers will look up after import.
        """
        out = {}
        sch = (aset or {}).get('schema') or {}
        for idx, (_k, item) in enumerate(sch.items(), start=1):
            if not isinstance(item, dict):
                continue
            ident = item.get('identifier')
            atype = item.get('type')
            inner_id = item.get('id')
            if inner_id is None:
                inner_id = idx
            if ident and atype:
                out[ident] = (int(inner_id), atype)
        return out

    def _normalize_value(value, atype):
        """Apply per-type shape rules. Returns (new_value, was_modified)."""
        if atype == 'list':
            if isinstance(value, list):
                # already a list — check if items are bare strings vs {value}
                new = []
                modified = False
                for it in value:
                    if isinstance(it, dict) and 'value' in it:
                        new.append(it)
                    elif isinstance(it, str) and it:
                        new.append({'value': it})
                        modified = True
                    elif it is not None:
                        new.append({'value': str(it)})
                        modified = True
                return new, modified
            if isinstance(value, str) and value:
                return [{'value': value}], True
            return [], True
        if atype in ('image', 'groupOfImages'):
            # Frontend ImageFieldsParameters.js:98,113 reads
            # `Object.values(item.previewLink).map(p => <img src={p[1]} />)` —
            # previewLink VALUES must be [origUrl, previewUrl] tuples, NOT
            # bare strings. Backend canonical: cms/.../upload-result.dto.ts:40
            # `previewLink?: Record<string, [string, string]>`.
            def _wrap_preview(link):
                return [link, link] if isinstance(link, str) else link
            if isinstance(value, list):
                new = []
                modified = False
                for it in value:
                    if isinstance(it, dict) and 'filename' in it:
                        it = dict(it)
                        # ensure previewLink is dict with tuple values
                        pl = it.get('previewLink')
                        if not isinstance(pl, dict):
                            it['previewLink'] = {'1': _wrap_preview(it.get('downloadLink') or it.get('filename'))}
                            modified = True
                        else:
                            # rewrap any bare-string values
                            new_pl = {k: _wrap_preview(v) if isinstance(v, str) else v for k, v in pl.items()}
                            if new_pl != pl:
                                it['previewLink'] = new_pl
                                modified = True
                        if 'downloadLink' not in it:
                            it['downloadLink'] = it.get('filename')
                            modified = True
                        new.append(it)
                    elif isinstance(it, str) and it:
                        new.append({
                            'filename': it,
                            'downloadLink': it,
                            'previewLink': {'1': [it, it]},
                        })
                        modified = True
                return new, modified
            if isinstance(value, str) and value:
                return [{
                    'filename': value,
                    'downloadLink': value,
                    'previewLink': {'1': [value, value]},
                }], True
            return [], True
        if atype in ('integer', 'real'):
            if isinstance(value, (int, float)):
                return str(value), True
            if value is None:
                return None, False  # leave absent
            return value, False
        if atype == 'text':
            if isinstance(value, dict) and 'htmlValue' in value:
                return value, False
            if isinstance(value, str):
                return {
                    'htmlValue': value,
                    'plainValue': value,
                    'mdValue': value,
                    'params': {'editorMode': 'HTML'},
                }, True
            return {
                'htmlValue': '', 'plainValue': '', 'mdValue': '',
                'params': {'editorMode': 'HTML'},
            }, True
        if atype == 'radioButton':
            # Frontend RadioButtonFieldsParameters.js:34,44,56 reads
            # `state?.value` to find the selected option. Data shape must be
            # `{value: "X"}` — bare string makes `state?.value === undefined`.
            if isinstance(value, str):
                if value == '':
                    return None, True  # drop empty
                return {'value': value}, True
            if isinstance(value, dict) and 'value' in value:
                return value, False
            return None, True
        if atype == 'button':
            if isinstance(value, dict):
                return value, False
            return {}, True
        if atype in ('date', 'dateTime', 'time'):
            # Frontend DateFieldsParameters.js:550 reads `state?.fullDate`.
            # Bare ISO string makes the form show empty. Wrap into the canonical
            # date-picker shape.
            if isinstance(value, str):
                if not value:
                    return None, True  # drop empty
                fmt = '%H:%M' if atype == 'time' else ('%Y-%m-%d' if atype == 'date' else '%Y-%m-%dT%H:%M')
                return {
                    'fullDate': value,
                    'formattedValue': value,
                    'formatString': fmt,
                }, True
            if isinstance(value, dict) and 'fullDate' in value:
                return value, False
            return value, False
        # string / textarea / other — keep as-is
        return value, False

    def _type_default(atype):
        if atype in ('list', 'image', 'groupOfImages'):
            return []
        if atype == 'string':
            return ''
        if atype == 'text':
            return {
                'htmlValue': '', 'plainValue': '', 'mdValue': '',
                'params': {'editorMode': 'HTML'},
            }
        if atype == 'button':
            return {}
        # integer / real / dateTime / date / time / radioButton — skip (admin
        # handles missing key as unset; setting "" or 0 hides "unset" state).
        return None

    def _process_entity(entity, aset_ident_field='attribute_set'):
        nonlocal renamed, shaped, backfilled, text_wrapped
        if not isinstance(entity, dict):
            return
        aset_ident = entity.get(aset_ident_field)
        if not aset_ident:
            return
        aset = aset_by_ident.get(aset_ident)
        if not aset:
            return
        schema = (aset or {}).get('schema') or {}
        if not schema:
            return
        schema_map = _schema_id_map(aset)
        attrs = entity.setdefault('attributes_sets', {}) or {}
        # Use langs ACTUALLY present in entity data (locale-collapse may have
        # converted en_GB → en_US after primary_lang was captured).
        entity_langs = list(attrs.keys()) or list(languages or ['en_US'])
        for lang in entity_langs:
            lang_data = attrs.setdefault(lang, {}) or {}
            if not isinstance(lang_data, dict):
                lang_data = {}
                attrs[lang] = lang_data
            # 1. RENAME semantic → schema keys
            keys_snapshot = list(lang_data.keys())
            for k in keys_snapshot:
                if k in schema_map:
                    inner_id, atype = schema_map[k]
                    new_key = f'{atype}_id{inner_id}'
                    if new_key in lang_data:
                        # already populated under new key — keep new, drop old
                        del lang_data[k]
                    else:
                        lang_data[new_key] = lang_data.pop(k)
                        renamed += 1
            # 2. NORMALIZE shape for keys matching <type>_id<N>
            for k in list(lang_data.keys()):
                m = re.match(r'^([a-zA-Z]+)_id(\d+)$', k)
                if not m:
                    continue
                atype = m.group(1)
                new_v, modified = _normalize_value(lang_data[k], atype)
                if modified:
                    shaped += 1
                    if atype == 'text':
                        text_wrapped += 1
                if new_v is None and atype in ('radioButton',):
                    del lang_data[k]
                else:
                    lang_data[k] = new_v
            # 3. BACKFILL missing schema keys with type defaults
            for ident, (inner_id, atype) in schema_map.items():
                ekey = f'{atype}_id{inner_id}'
                if ekey not in lang_data:
                    dflt = _type_default(atype)
                    if dflt is not None:
                        lang_data[ekey] = dflt
                        backfilled += 1
            attrs[lang] = lang_data
        entity['attributes_sets'] = attrs

    # Apply to every list of attribute-bearing entities in mapped.yaml
    for coll_key in ('products', 'blocks', 'pages', 'forms', 'user_groups'):
        for ent in (data.get(coll_key) or []):
            _process_entity(ent, 'attribute_set')

    # post_import_slides[] inherit attribute_set from parent block (slider block).
    # Resolve block_identifier → block.attribute_set, then attach to slide before
    # running the same transform pipeline.
    block_by_ident = {b.get('identifier'): b for b in (data.get('blocks') or []) if b.get('identifier')}
    for s in (data.get('post_import_slides') or []):
        bi = s.get('block_identifier')
        parent = block_by_ident.get(bi)
        if parent and parent.get('attribute_set'):
            s['attribute_set'] = parent['attribute_set']
            _process_entity(s, 'attribute_set')

    # Drop orphan semantic keys that didn't match any schema identifier (so
    # they didn't get renamed). They survive as dead data otherwise. Apply
    # ONLY for entities we touched.
    schema_key_pattern = re.compile(r'^[a-zA-Z]+_id\d+$')
    def _drop_orphans(entity, aset_ident_field='attribute_set'):
        nonlocal renamed
        aset_ident = entity.get(aset_ident_field) if isinstance(entity, dict) else None
        if not aset_ident:
            return
        aset = aset_by_ident.get(aset_ident)
        if not aset or not (aset.get('schema') or {}):
            return
        attrs = entity.get('attributes_sets') or {}
        for lang, lang_data in list(attrs.items()):
            if not isinstance(lang_data, dict):
                continue
            for k in list(lang_data.keys()):
                if not schema_key_pattern.match(k):
                    del lang_data[k]
    for coll_key in ('products', 'blocks', 'pages', 'forms', 'user_groups'):
        for ent in (data.get(coll_key) or []):
            _drop_orphans(ent, 'attribute_set')
    for s in (data.get('post_import_slides') or []):
        _drop_orphans(s, 'attribute_set')

    if renamed or shaped or backfilled or text_wrapped:
        fixes.append(
            f"attribute data: renamed {renamed} keys (semantic→<type>_id<N>), "
            f"shaped {shaped} values, backfilled {backfilled} missing keys, "
            f"text-wrapped {text_wrapped}"
        )
    return fixes


def fix_mapped(mapped_path, project_root, languages=None):
    if languages is None:
        languages = ['en_US']
    # Normalize the `languages` parameter itself BEFORE any fix function
    # consumes it (en_GB → en_US, de_AT → de_DE, …). Otherwise functions like
    # `emit_admin_validators_per_lang` add data under a key that the cms loader
    # will silently drop because the regional locale isn't activated.
    languages = [_LOCALE_NORMALIZATION.get(lang, lang) for lang in languages]
    # Deduplicate preserving order
    seen = set()
    languages = [lang for lang in languages if not (lang in seen or seen.add(lang))]
    data = read_yaml(mapped_path)
    fixes = []

    derivations = load_title_derivations()
    hub_titles = derivations['hub_titles']
    composite_catalog = derivations.get('composite_catalog', {})
    block_defaults = derivations.get('block_default_titles', {})
    section_titles = parse_section_titles(project_root)

    # === Fix 1: isVisible:true ===
    count = 0
    for aset in (data.get('attributes_sets') or []):
        for k, item in (aset.get('schema') or {}).items():
            if not isinstance(item, dict):
                continue
            if item.get('isVisible') is not True:
                item['isVisible'] = True
                count += 1
    if count:
        fixes.append(f"isVisible:true added to {count} schema-items")

    # === Fix 2: Error pages (404, 500, offline) ===
    # Next.js conventions:
    #   app/not-found.tsx       -> HTTP 404 page
    #   app/error.tsx           -> HTTP 500 segment-error page
    #   app/global-error.tsx    -> HTTP 500 root-error page
    #   app/offline/page.tsx    -> offline fallback (PWA), bound to no HTTP code
    #   app/checkout/error.tsx  -> nested 500 — represented by the same 500 row
    # All map to `general_type_id=3` ('error_page', STABLE — verified in
    # the OneEntry Platform general_types snapshot).
    pages = data.get('pages') or []
    existing_idents = {p.get('identifier') for p in pages}
    project_path = Path(project_root) if project_root else None
    error_page_signals = []

    def _exists(rel):
        return project_path and (project_path / rel).exists()

    def _rglob_first(pattern):
        if not project_path:
            return False
        for _ in project_path.rglob(pattern):
            return True
        return False

    # 404 (HTTP code 404)
    if (_exists('app/not-found.tsx') or _rglob_first('not-found.tsx')
            or _rglob_first('NotFoundPage.tsx')):
        error_page_signals.append({
            'identifier':  '404',
            'http_code':   404,
            'title':       hub_titles.get('404', 'Page Not Found'),
            'menu_title':  '404',
        })

    # 500 (HTTP code 500). Multiple `error.tsx` files collapse to one entry.
    if (_exists('app/error.tsx') or _exists('app/global-error.tsx')
            or _rglob_first('error.tsx')):
        error_page_signals.append({
            'identifier':  '500',
            'http_code':   500,
            'title':       hub_titles.get('500', 'Something went wrong'),
            'menu_title':  '500',
        })

    # Offline (no HTTP code — page is bound to PWA SW only).
    if (_exists('app/offline/page.tsx') or _rglob_first('offline/page.tsx')
            or _rglob_first('OfflinePage.tsx')):
        error_page_signals.append({
            'identifier':  'offline',
            'http_code':   None,
            'title':       hub_titles.get('offline', 'No Internet Connection'),
            'menu_title':  'Offline',
        })

    added_error_pages = []
    for sig in error_page_signals:
        if sig['identifier'] in existing_idents:
            continue
        page = {
            'identifier':       sig['identifier'],
            'parent':           None,
            'page_url':         sig['identifier'],
            'attribute_set':    'forPages',
            'template':         'common_page_default',
            'general_type_marker': 'error_page',
            'general_type_id':  3,
            'localize_infos': {
                lang: {'title': sig['title'], 'menuTitle': sig['menu_title']}
                for lang in languages
            },
        }
        pages.append(page)
        added_error_pages.append(sig)
        existing_idents.add(sig['identifier'])
        fixes.append(f"+ page '{sig['identifier']}' (general_type_id=3 error_page)")
    if added_error_pages:
        data['pages'] = pages

    # ─── post-import page_errors binding (Code→Page) ────────────────────────
    # `page_errors` is OUT of the blueprint whitelist (loader does not accept
    # this table). The orchestrator creates rows via REST after import:
    #   POST /api/admin/page-errors  body={code: 404}
    #   PUT  /api/admin/page-errors/:id/set-error-page  body={pageId: <404page>}
    if added_error_pages or any(p.get('general_type_id') == 3 for p in pages):
        psk_tasks = data.get('post_import_page_errors') or []
        # Idempotency: rebuild from current page entries that have an http code.
        if not psk_tasks:
            for p in pages:
                ident = p.get('identifier')
                if p.get('general_type_id') != 3 or ident == 'offline':
                    continue
                try:
                    code = int(ident)
                except (TypeError, ValueError):
                    continue
                if not (400 <= code <= 599):
                    continue
                psk_tasks.append({
                    'http_code':       code,
                    'page_identifier': ident,
                })
            if psk_tasks:
                data['post_import_page_errors'] = psk_tasks
                fixes.append(
                    f"+ post_import_page_errors: {len(psk_tasks)} binding(s) "
                    f"({', '.join(str(t['http_code']) for t in psk_tasks)})"
                )

    # === Fix 3: hub/catalog page titles ===
    page_title_fixed = 0
    for p in (data.get('pages') or []):
        ident = p.get('identifier', '')
        derived = derive_page_title(ident, hub_titles, composite_catalog)
        if not derived:
            continue
        li = p.setdefault('localize_infos', {})
        for lang in languages:
            lang_info = li.setdefault(lang, {})
            if not lang_info.get('title'):
                lang_info['title'] = derived
                page_title_fixed += 1
    if page_title_fixed:
        fixes.append(f"hub/catalog page titles for {page_title_fixed} entries")

    # === Fix 3.5: promote catalog-hub pages to general_type_id=4 ===
    # Universal cms invariant: a page that has any catalog_page descendant
    # (recursively) must itself be `catalog_page` (general_type_id=4) — not
    # `common_page` (=17). The cms admin catalog filter only walks ONE level
    # deep (`developer-pages.controller.ts::getTableData2`: `EXISTS pages
    # WHERE parent_id=p.id AND type='catalog_page'`). So intermediate hub
    # pages (`women`, `men`, `electronics`, `services`, `cuisine`, …) whose
    # DIRECT children are themselves common-page hubs get hidden by the
    # admin tree — the user clicks into Catalog and sees an empty branch.
    #
    # Universal across verticals — e-commerce gender hubs, restaurant
    # cuisine hubs, education faculty hubs, hotel property-type hubs,
    # SaaS pricing-tier hubs all need this promotion.
    pages_local = data.get('pages') or []
    by_ident = {p.get('identifier'): p for p in pages_local if p.get('identifier')}
    def _resolve_parent_ident(parent_ref):
        if not parent_ref:
            return None
        if isinstance(parent_ref, str):
            return parent_ref.replace('@page.', '')
        return None
    children_of = {}
    for p in pages_local:
        pi = _resolve_parent_ident(p.get('parent') or p.get('parent_id'))
        if pi:
            children_of.setdefault(pi, []).append(p.get('identifier'))
    def _has_catalog_descendant(ident, _seen=None):
        if _seen is None:
            _seen = set()
        if ident in _seen:
            return False
        _seen.add(ident)
        for c_ident in children_of.get(ident, []):
            child = by_ident.get(c_ident)
            if not child:
                continue
            if child.get('general_type_id') == 4 or child.get('general_type_marker') == 'catalog_page':
                return True
            if _has_catalog_descendant(c_ident, _seen):
                return True
        return False
    promoted = 0
    for p in pages_local:
        ident = p.get('identifier')
        if not ident:
            continue
        # Already catalog → skip
        gtid = p.get('general_type_id')
        marker = p.get('general_type_marker')
        if gtid == 4 or marker == 'catalog_page':
            continue
        # Exempt utility/error/root pages — never catalog
        if ident in ('root', '', 'cart', 'checkout', 'favorites', 'account',
                     'wishlist', '404', '500', '503', 'offline', 'error',
                     'not-found'):
            continue
        if gtid == 3 or marker == 'error_page':
            continue
        # Demote condition: only promote when this page has catalog descendants
        if _has_catalog_descendant(ident):
            p['general_type_id'] = 4
            p['general_type_marker'] = 'catalog_page'
            promoted += 1
    if promoted:
        fixes.append(
            f"promoted {promoted} hub page(s) to catalog_page (general_type_id=4) "
            f"— required for cms admin catalog tree to surface the branch"
        )

    # === Fix 4: block titles ===
    block_fixes = fix_block_titles(data.get('blocks') or [], project_root,
                                    section_titles, block_defaults, languages)
    fixes.extend(block_fixes)

    # === Fix 5: user user_group is mandatory ===
    auth_providers = data.get('users_auth_providers') or []
    user_groups = data.get('user_groups') or []
    has_user_auth = any(p.get('type') in ('email', 'google', 'apple', 'facebook')
                       for p in auth_providers)
    ug_idents = {ug.get('identifier') for ug in user_groups}
    if has_user_auth and 'user' not in ug_idents:
        user_groups.append({
            'id': '@ug.user',
            'identifier': 'user',
            'attribute_set': 'forUserGroups',
            'localize_infos': {lang: {'title': 'Registered Users'} for lang in languages},
            'is_visible': True,
        })
        fixes.append("+ user_group 'user' (auth-providers found)")
        # Update references in auth-providers from user_preseeded -> user
        for p in auth_providers:
            if p.get('user_group') in (None, '', 'user_preseeded'):
                p['user_group'] = 'user'

    # === Fix 5.5: guest user_group is mandatory (storefront anonymous sessions) ===
    # Standard cms seed `1745835025671-set-default-user-group.ts` creates `guest`
    # with id=1, but after `TRUNCATE ... RESTART IDENTITY` the seed flag in the
    # `migrations` table prevents re-run. Including `guest` in the blueprint
    # makes it part of every clean import — no manual SQL required.
    if 'guest' not in ug_idents:
        user_groups.append({
            'id': '@ug.guest',
            'identifier': 'guest',
            'attribute_set': 'forUserGroups',
            'localize_infos': {lang: {'title': 'Guest'} for lang in languages},
            'is_visible': True,
        })
        fixes.append("+ user_group 'guest' (storefront anonymous sessions)")
    data['user_groups'] = user_groups

    # === Fix 6: orders_storage.form -> order ===
    forms = data.get('forms') or []
    order_forms = [f for f in forms if f.get('type') == 'order']
    if order_forms:
        order_ident = order_forms[0].get('identifier')
        for s in (data.get('orders_storage') or []):
            cur = s.get('form')
            if cur != order_ident:
                fixes.append(f"orders_storage.form: '{cur}' -> '{order_ident}'")
                s['form'] = order_ident

    # === Fix 6.1.5: orders_storage + standard order_statuses safety net ===
    # If the mapper skipped the orders subsystem but the project shows clear
    # cart/checkout signals — emit it deterministically so payment_status_map
    # has something to bind to.
    ord_fixes = ensure_orders_subsystem(data, project_root, languages)
    fixes.extend(ord_fixes)

    # === Fix 6.2: post-import payment_status_map task list ===
    # PaymentStatusMap is admin-config (PUT /api/admin/payments/status-maps) —
    # not representable in blueprint tables. We auto-build a mapping per
    # orders_storage by keyword-matching order_status identifiers against the
    # 5 fixed payment-status keys (`PaymentStatusMapDto`).
    psm_fixes = generate_payment_status_maps(data)
    fixes.extend(psm_fixes)

    # === Fix 6.2.1: post-import discounts safety net ===
    # Mapper SHOULD populate `post_import_discounts[]` from
    # `inspector.notes.discounts.extracted`. If the inspector failed to emit
    # `notes.discounts`, scan product/coupon source files directly so the admin
    # Discounts page is not left empty.
    disc_fixes = generate_post_import_discounts(data, project_root, languages)
    fixes.extend(disc_fixes)

    # === Fix 6.2.2: products + schema attribute enrichment safety net ===
    # If the mapper sampled only a few products (regression observed across
    # catalog projects, with very few attributes per product) — scan source
    # product files and fill every product's attributes_sets + extend
    # forProducts_* schemas with the full union of observed list values.
    prod_fixes = enrich_product_data(data, project_root, languages)
    fixes.extend(prod_fixes)

    # === Fix 6.2.2.5: deterministic deep extraction (Step 1.5 in Python) ===
    # Independent of the LLM mapper. Guarantees that for every source data row
    # whose identifier matches a product/block, ALL source keys that satisfy
    # rules/mapper-source-extraction.md §1.5 get emitted into attributes_sets.
    # Path-agnostic discovery + vertical-agnostic token-set matching.
    deep_fixes = deep_extract_attributes_from_source(data, project_root, languages)
    fixes.extend(deep_fixes)

    # === Fix 6.2.3: slides for slider_block (post-import) ===
    # `slides` table is OUT of the blueprint whitelist. We build a task list
    # for the orchestrator to POST /api/admin/slides after blueprint upload.
    slide_fixes = generate_post_import_slides(data, project_root, languages)
    fixes.extend(slide_fixes)

    # === Fix 6.2.4: dedupe semantic slots in schemas (cover/preview, sizes/size, …) ===
    fixes.extend(dedupe_semantic_slots(data))

    # === Fix 6.2.5: auto-generate empty SKU values from product identifier ===
    fixes.extend(autogenerate_skus(data))

    # === Fix 6.2.6: remove unused `type:json` attributes (specs/product_details/…) ===
    fixes.extend(cleanup_empty_json_attrs(data))

    # === Fix 6.2.7: merge `subscriptions` form into forUsers preferences ===
    fixes.extend(merge_subscriptions_form_into_user(data, languages))

    # === Fix 6.2.7b: split mixed `review` form into rating + feedback forms ===
    fixes.extend(split_review_form_into_rating_and_data(data, languages))

    # === Fix 6.2.8: dedupe error pages (404/not-found, 500/error pairs) ===
    fixes.extend(dedupe_error_pages(data))

    # === Fix 6.2.9: fill block attribute values from source data files ===
    fixes.extend(fill_block_attribute_values(data, project_root, languages))

    # === Fix 6.2.10: build post_import_menus[] from header/footer source configs ===
    fixes.extend(fill_post_import_menus(data, project_root, languages))

    # === Fix 6.2.11: fallback header menu from page tree (when source config lacks one) ===
    fixes.extend(fill_header_menu_from_pages(data, languages))

    # === Fix 6.2.12: replace synthetic /assets/*.png placeholders with TODO_UPLOAD markers ===
    fixes.extend(normalize_synthetic_asset_paths(data))

    # === Fix 6.2.13: fill empty block titles with identifier-derived defaults ===
    fixes.extend(fill_empty_block_titles(data, languages))

    # === Fix 6.2.14: strip discount-shaped fields from forUserGroups ===
    # (discounts/coupons/bonuses belong in the Discounts module, NOT user_groups)
    fixes.extend(strip_discount_fields_from_usergroup(data))

    # === Fix 6.2.14.5: normalize locale codes (en_GB → en_US, de_AT → de_DE) ===
    # MUST run before any other fix that produces new lang-keyed objects.
    fixes.extend(normalize_locale_codes(data))

    # === Fix 6.2.14.6: emit validators[lang] for user-input attributes ===
    # admin form validation reads validators[lang].*; rules/additionalFields
    # alone are not sufficient.
    fixes.extend(emit_admin_validators_per_lang(data, languages))

    # === Fix 6.2.14.7: bind `offline` page to HTTP 503 (Service Unavailable) ===
    fixes.extend(bind_offline_page_to_error_code(data, languages))

    # === Fix 6.2.14.7b: ensure slider attribute_set schemas contain canonical slide fields ===
    fixes.extend(ensure_slider_block_schemas(data, languages))

    # === Fix 6.2.14.7c: auto-bind products to category pages (products_pages_mn) ===
    fixes.extend(fill_products_pages_mn(data, project_root))
    fixes.extend(fill_block_pages_mn_from_source(data, project_root))

    # === Fix 6.2.14.8: S66 — flag visible slider_blocks without slides ===
    fixes.extend(check_slider_blocks_have_slides(data))

    # === Fix 6.2.14.9: S67 — flag visible collections with 0 rows ===
    fixes.extend(check_visible_collections_have_rows(data))

    # === Fix 6.2.15: normalize page_urls — strip `/` for single-segment URLs ===
    fixes.extend(normalize_page_urls(data))

    # === Fix 6.2.16: emit slides for EVERY slider_block (not just hero) ===
    # Walks all slider_block instances and finds matching source data files
    # (category_section→categories.ts, trend_blocks→trendBlocks.ts, …).
    fixes.extend(fill_slides_for_all_slider_blocks(data, project_root, languages))

    # === Fix 6.2.17: emit default template_previews (hero_slide 16:9, square 1:1) ===
    # Without these, slider_block UI cannot assign a preview-template to a
    # slide and admin sees "No preview templates" warning.
    fixes.extend(generate_default_template_previews(data, languages))

    # === Fix 6.3: forProducts -> split into category-specific sets ===
    split_fixes = split_for_products_by_category(data, languages)
    fixes.extend(split_fixes)

    # === Fix 6.5: products — remove top-level sku/fields (not products columns) ===
    # Whitelist of products columns: id, identifier, attribute_set_id, attributes_sets,
    # localize_infos, is_visible, is_edit, rating, status_id, template_id,
    # short_desc_template_id, import_id, ... (see rules/generated/table-columns.md).
    # The mapper sometimes places SKU/fields at the top level — this breaks INSERT.
    PRODUCT_TOP_LEVEL_OK = {
        'id', 'identifier', 'attribute_set', 'template', 'status', 'pages',
        'localize_infos', 'attributes_sets', 'is_visible', 'is_edit', 'rating',
    }
    products_fixed = 0
    for p in (data.get('products') or []):
        # 1. Move `fields` -> `attributes_sets` with a language wrapper
        if 'fields' in p and 'attributes_sets' not in p:
            fields = p.pop('fields')
            if isinstance(fields, dict):
                # If fields is flat — wrap it in {primary_lang: {...}}
                primary_lang = languages[0] if languages else 'en_US'
                p['attributes_sets'] = {primary_lang: fields}
            products_fixed += 1
        # 2. Drop unknown top-level keys (sku, currency, brand, etc.)
        for k in list(p.keys()):
            if k not in PRODUCT_TOP_LEVEL_OK:
                p.pop(k)
    if products_fixed:
        fixes.append(f"products: renamed fields->attributes_sets + cleaned top-level fields for {products_fixed} products")

    # === Fix 6.8: integration collections (FAQ/Stores/Brands) ===
    coll_fixes = generate_collections(data, project_root, languages)
    fixes.extend(coll_fixes)

    # === Fix 6.7: user_permissions + user_group_permissions_mn for the 'user' group ===
    # Loader does upsert by (path, section) — preseed permissions are reused,
    # new ones are INSERTed. See blueprint-loader.service.ts NATURAL_KEYS.
    perm_fixes = generate_user_permissions(data, languages)
    fixes.extend(perm_fixes)

    # === Fix 7: form_module_config — bind every form to its module ===
    # Module ids (preseeded in OneEntry): users=9, forms=2, orders=12,
    # subscriptions=17. Mapping rules — by form.type:
    #   order              → orders
    #   sing_in_up/signin  → users  (auth, not stored as form_data)
    #   data               → users  (profile/cabinet data forms)
    #   subscription       → subscriptions
    #   rating/review/feedback → forms (generic form viewer)
    # Universal across project verticals — any form without a binding will be
    # invisible in admin, breaking the "Module forms" tab.
    MODULE_IDS = {'users': 9, 'forms': 2, 'orders': 12, 'subscriptions': 17}
    TYPE_TO_MODULE = {
        'data':         'users',
        'order':        'orders',
        'sing_in_up':   'users',
        'signin':       'users',
        'login':        'users',
        'signup':       'users',
        'subscription': 'subscriptions',
        'rating':       'forms',
        'review':       'forms',
        'feedback':     'forms',
    }
    # Per-identifier overrides (when type alone is ambiguous):
    # `review_feedback` is conceptually a review form even though its `type`
    # is `data` (mapper marker for free-text fields). Same for any future
    # `*_rating` / `*_review` / `*_feedback` split-derived forms.
    FORM_IDENT_OVERRIDES = {
        'review_rating':   'forms',
        'review_feedback': 'forms',
    }
    fmc_list = data.get('form_module_config') or []
    existing_form_idents = {fmc.get('form') for fmc in fmc_list}
    added_fmc = 0
    user_scoped = 0
    # Re-fetch forms here — earlier `split_review_form_into_rating_and_data`
    # and `merge_subscriptions_form_into_user` reassign `data['forms']` to a
    # new list, so the local `forms` captured at the top of `fix_mapped` is
    # stale and missing the split-derived review_rating / review_feedback.
    forms = data.get('forms') or []
    for f in forms:
        ident = f.get('identifier')
        if not ident or ident in existing_form_idents:
            continue
        module = FORM_IDENT_OVERRIDES.get(ident) or \
                 TYPE_TO_MODULE.get(f.get('type'), 'forms')
        mid = MODULE_IDS.get(module)
        if mid is None:
            continue
        # Universal rule: forms bound to the USERS module store per-user
        # data (profile, address, my-orders, my-bonuses, …). Each authenticated
        # user fills the form for themselves and should only see their own
        # entries. Two `form_module_config` flags express this:
        #   - is_global=true            → form appears for ALL users in the
        #     module automatically (no explicit per-user entity list needed).
        #   - view_only_user_data=true  → each user sees only their own
        #     submitted data, not other users' submissions.
        # Without these flags admin must check them by hand on every per-user
        # form. Auth forms (sing_in_up/login/signup) are still bound to the
        # users module but are NOT data-capture forms — exclude them.
        is_user_data_form = (
            module == 'users'
            and (f.get('type') == 'data'
                 or ident.startswith(('profile', 'my_', 'my-', 'account')))
        )
        fmc_list.append({
            'module_id': mid,
            'form': ident,  # builder converts to form_id via @form.X
            'entity_identifiers': [],
            'is_global':              bool(is_user_data_form),
            'is_closed':              False,
            'is_moderate':            False,
            'view_only_user_data':    bool(is_user_data_form),
            'comment_only_user_data': False,
        })
        added_fmc += 1
        if is_user_data_form:
            user_scoped += 1
    if added_fmc:
        data['form_module_config'] = fmc_list
        suffix = (f" ({user_scoped} user-scoped → is_global+view_only_user_data)"
                  if user_scoped else '')
        fixes.append(f"+ form_module_config: {added_fmc} forms bound by type → module{suffix}")

    # === Fix 7.1: enforce user-scope flags on PRE-EXISTING form_module_config ===
    # The mapper occasionally pre-emits form_module_config rows for `data`-type
    # forms bound to the users module (id=9) but leaves is_global/
    # view_only_user_data at false. Patch them so storefront actually shows
    # the form to every authenticated user and scopes their view to own data.
    forms_by_ident = {f.get('identifier'): f for f in (data.get('forms') or [])
                      if f.get('identifier')}
    USERS_MODULE_ID = MODULE_IDS['users']
    patched = 0
    for fmc in data.get('form_module_config') or []:
        if fmc.get('module_id') != USERS_MODULE_ID:
            continue
        fident = fmc.get('form')
        form = forms_by_ident.get(fident)
        if not form:
            continue
        if form.get('type') != 'data' and not (fident or '').startswith(
            ('profile', 'my_', 'my-', 'account')
        ):
            continue
        changed = False
        if not fmc.get('is_global'):
            fmc['is_global'] = True
            changed = True
        if not fmc.get('view_only_user_data'):
            fmc['view_only_user_data'] = True
            changed = True
        if changed:
            patched += 1
    if patched:
        fixes.append(
            f"+ form_module_config: enforced user-scope flags on {patched} pre-existing rows "
            f"(users-module data forms: is_global+view_only_user_data=true)"
        )

    # === Fix 7.5: cleanup orphan form_module_config entries ===
    # After all form mutations (split_review, merge_subscriptions, add data
    # bindings), drop any form_module_config row whose form_id token refers
    # to a form that no longer exists. Without this the loader fails with
    # 'Unresolved token references'.
    known_form_idents = {f.get('identifier') for f in (data.get('forms') or [])
                          if f.get('identifier')}
    def _fmc_form_ident(c):
        if c.get('form'):
            return c['form']
        fid = c.get('form_id') or ''
        if isinstance(fid, str) and fid.startswith('@form.'):
            return fid[len('@form.'):]
        return None
    dropped_fmc = 0
    for container in ('form_module_config',):
        rows = data.get(container) or []
        cleaned = [c for c in rows
                   if _fmc_form_ident(c) in known_form_idents]
        dropped_fmc += len(rows) - len(cleaned)
        data[container] = cleaned
    tables = data.get('tables') or {}
    if 'form_module_config' in tables:
        rows = tables['form_module_config'] or []
        cleaned = [c for c in rows
                   if _fmc_form_ident(c) in known_form_idents]
        dropped_fmc += len(rows) - len(cleaned)
        tables['form_module_config'] = cleaned
    if dropped_fmc:
        fixes.append(f"form_module_config: dropped {dropped_fmc} orphan rows "
                     f"(referenced removed/merged forms)")

    # === Fix 8: validators for user-input attributes ===
    # Per rules/attribute-validators.md: every attribute that accepts user input
    # MUST have rules / additionalFields. Apply canonical table by identifier.
    validator_fixes = enrich_attribute_validators(data)
    fixes.extend(validator_fixes)

    # === Fix 8.3: migrate post_import_* arrays into tables.* ===
    # After cms whitelist extension (2026-06-02), these tables are loadable via
    # blueprint directly — orchestrator round-trip no longer needed for them.
    fixes.extend(migrate_post_import_to_tables(data))

    # === Fix 8.4: default product_relations_templates ===
    # `product_relations_templates` IS in the 24-whitelist → emitting them into
    # `tables.product_relations_templates` makes them available right after
    # blueprint import, no orchestrator needed.
    fixes.extend(generate_default_templates(data))
    fixes.extend(generate_default_payment_accounts(data))
    fixes.extend(generate_default_product_relations_templates(data))

    # === Fix 8.5: normalize attribute_set SCHEMA shape ===
    # Convert listTitles dict → array, drop invalid listType values, generate
    # validators[lang] from rules. Must run BEFORE data-shape transform so
    # type detection downstream sees the final schema.
    # Strip stray `rating` field from non-review forms BEFORE shape normalize.
    fixes.extend(strip_rating_from_non_review_forms(data))
    fixes.extend(normalize_attribute_schema_shape(data, languages))

    # === Fix 9 (FINAL): transform attribute data to admin-ready shape ===
    # Renames semantic keys → <type>_id<innerId>, normalizes per-type shapes,
    # backfills missing keys with type-defaults — so the blueprint embeds
    # admin-ready values and no post-import SQL is needed.
    # MUST run LAST — after schemas are finalized and after enrichment.
    fixes.extend(transform_attribute_data_to_admin_shape(data, languages))

    write_yaml(data, mapped_path)
    return fixes


# Canonical validators by attribute `identifier`. Source of truth:
# `agents_datasets/rules/attribute-validators.md` §"Canonical validator table".
# Keep in sync with that file.
ATTR_VALIDATORS = {
    # --- Identity / auth ---
    'email': {
        'rules': {'pattern': r'^[^@\s]+@[^@\s]+\.[^@\s]+$', 'maxLength': 254},
        'additionalFields': {'placeholder': 'jane.doe@example.com',
                             'helperText': "We'll send order updates to this email.",
                             'autoComplete': 'email', 'inputType': 'email'},
    },
    'password': {
        'rules': {'minLength': 8, 'maxLength': 128},
        'additionalFields': {'helperText': 'Minimum 8 characters.',
                             'autoComplete': 'new-password', 'inputType': 'password'},
    },
    'phone': {
        'additionalFields': {'mask': '+## ### ### ####', 'placeholder': '+1 555 123 4567',
                             'helperText': 'We may call about your order.',
                             'autoComplete': 'tel', 'inputType': 'tel'},
    },
    'first_name':   {'rules': {'minLength': 1, 'maxLength': 50},
                     'additionalFields': {'placeholder': 'Jane', 'autoComplete': 'given-name'}},
    'last_name':    {'rules': {'minLength': 1, 'maxLength': 50},
                     'additionalFields': {'placeholder': 'Doe', 'autoComplete': 'family-name'}},
    'full_name':    {'rules': {'minLength': 2, 'maxLength': 100},
                     'additionalFields': {'placeholder': 'Jane Doe', 'autoComplete': 'name'}},
    'middle_name':  {'rules': {'maxLength': 50},
                     'additionalFields': {'placeholder': 'Optional', 'autoComplete': 'additional-name'}},
    'nickname':     {'rules': {'minLength': 2, 'maxLength': 50},
                     'additionalFields': {'placeholder': 'How should we call you?', 'autoComplete': 'nickname'}},
    'username':     {'rules': {'pattern': r'^[a-zA-Z0-9_-]{3,30}$'},
                     'additionalFields': {'placeholder': 'Letters, digits, underscores',
                                          'helperText': '3-30 chars; a-z, 0-9, _ and -.',
                                          'autoComplete': 'username'}},
    'birthday':     {'rules': {'minDate': '1900-01-01'},
                     'additionalFields': {'placeholder': 'YYYY-MM-DD',
                                          'helperText': "We'll send you a birthday discount.",
                                          'autoComplete': 'bday'}},
    'date_of_birth':{'rules': {'minDate': '1900-01-01'},
                     'additionalFields': {'placeholder': 'YYYY-MM-DD', 'autoComplete': 'bday'}},

    # --- Address ---
    'address_line1':{'rules': {'minLength': 1, 'maxLength': 200},
                     'additionalFields': {'placeholder': '123 Main St',
                                          'helperText': 'Street and house number.',
                                          'autoComplete': 'address-line1'}},
    'address_line2':{'rules': {'maxLength': 200},
                     'additionalFields': {'placeholder': 'Apt 4B (optional)',
                                          'autoComplete': 'address-line2'}},
    'city':         {'rules': {'minLength': 1, 'maxLength': 100},
                     'additionalFields': {'placeholder': 'San Francisco', 'autoComplete': 'address-level2'}},
    'state':        {'rules': {'maxLength': 100},
                     'additionalFields': {'placeholder': 'California', 'autoComplete': 'address-level1'}},
    'country':      {'rules': {'minLength': 2, 'maxLength': 60},
                     'additionalFields': {'placeholder': 'United States', 'autoComplete': 'country-name'}},
    'postcode':     {'rules': {'minLength': 3, 'maxLength': 12},
                     'additionalFields': {'placeholder': '94103', 'helperText': 'Postcode / ZIP.',
                                          'autoComplete': 'postal-code'}},
    'zip':          {'rules': {'minLength': 3, 'maxLength': 12},
                     'additionalFields': {'placeholder': '94103', 'autoComplete': 'postal-code'}},
    'zip_code':     {'rules': {'minLength': 3, 'maxLength': 12},
                     'additionalFields': {'placeholder': '94103', 'autoComplete': 'postal-code'}},

    # --- Order / checkout ---
    'card_number':  {'rules': {'pattern': r'^[0-9]{13,19}$'},
                     'additionalFields': {'mask': '#### #### #### ####',
                                          'placeholder': '4111 1111 1111 1111',
                                          'helperText': '16 digits on the front of your card.',
                                          'autoComplete': 'cc-number', 'inputType': 'tel'}},
    'card_name':    {'rules': {'minLength': 2, 'maxLength': 100},
                     'additionalFields': {'placeholder': 'JANE DOE',
                                          'helperText': 'Name as printed on the card.',
                                          'autoComplete': 'cc-name'}},
    'card_expiry':  {'rules': {'pattern': r'^(0[1-9]|1[0-2])\/[0-9]{2}$'},
                     'additionalFields': {'mask': '##/##', 'placeholder': 'MM/YY',
                                          'helperText': 'Month and year of expiry.',
                                          'autoComplete': 'cc-exp', 'inputType': 'tel'}},
    'card_cvv':     {'rules': {'pattern': r'^[0-9]{3,4}$'},
                     'additionalFields': {'mask': '####', 'placeholder': '123',
                                          'helperText': '3-4 digits on the back of your card.',
                                          'autoComplete': 'cc-csc', 'inputType': 'tel'}},
    'promo_code':   {'rules': {'maxLength': 50},
                     'additionalFields': {'placeholder': 'WELCOME10', 'helperText': 'Optional promotional code.'}},
    'coupon_code':  {'rules': {'maxLength': 50},
                     'additionalFields': {'placeholder': 'WELCOME10', 'helperText': 'Optional coupon code.'}},
    'voucher_code': {'rules': {'maxLength': 50},
                     'additionalFields': {'placeholder': 'GIFT100', 'helperText': 'Optional gift voucher code.'}},
    'delivery_instructions': {'rules': {'maxLength': 500},
                              'additionalFields': {'placeholder': 'Ring the doorbell, leave at door, etc.',
                                                   'helperText': 'Up to 500 characters.'}},
    'delivery_notes':{'rules': {'maxLength': 500},
                      'additionalFields': {'placeholder': 'Anything the courier should know.'}},
    'order_notes':  {'rules': {'maxLength': 500},
                     'additionalFields': {'placeholder': 'Anything else?'}},

    # --- Free-text content ---
    'title':        {'rules': {'minLength': 1, 'maxLength': 200},
                     'additionalFields': {'placeholder': 'Short title'}},
    'subtitle':     {'rules': {'maxLength': 300},
                     'additionalFields': {'placeholder': 'Supporting line'}},
    'description':  {'rules': {'maxLength': 5000},
                     'additionalFields': {'placeholder': 'Tell customers more...',
                                          'helperText': 'Up to 5000 characters.'}},
    'short_description': {'rules': {'maxLength': 500},
                          'additionalFields': {'placeholder': 'One-paragraph summary.'}},
    'message':      {'rules': {'minLength': 1, 'maxLength': 2000},
                     'additionalFields': {'placeholder': 'Type your message here...'}},
    'notes':        {'rules': {'maxLength': 2000},
                     'additionalFields': {'placeholder': 'Optional notes.'}},
    'question':     {'rules': {'minLength': 5, 'maxLength': 500},
                     'additionalFields': {'placeholder': 'What would you like to ask?'}},
    'answer':       {'rules': {'minLength': 1, 'maxLength': 5000},
                     'additionalFields': {'placeholder': 'Detailed answer.'}},
    'comment':      {'rules': {'maxLength': 2000},
                     'additionalFields': {'placeholder': 'Add a comment.'}},
    'feedback':     {'rules': {'minLength': 5, 'maxLength': 2000},
                     'additionalFields': {'placeholder': 'Tell us what you think.',
                                          'helperText': 'Up to 2000 characters.'}},
    'review_text':  {'rules': {'minLength': 5, 'maxLength': 2000},
                     'additionalFields': {'placeholder': 'Tell others why you like it...',
                                          'helperText': '5-2000 characters.'}},
    'review_title': {'rules': {'minLength': 2, 'maxLength': 200},
                     'additionalFields': {'placeholder': 'Great product!'}},

    # --- Numeric ---
    'price':        {'rules': {'minValue': 0, 'maxValue': 9999999},
                     'additionalFields': {'placeholder': '99.99', 'prefix': '$', 'step': 0.01,
                                          'inputType': 'number'}},
    'old_price':    {'rules': {'minValue': 0, 'maxValue': 9999999},
                     'additionalFields': {'placeholder': '129.00', 'prefix': '$', 'step': 0.01,
                                          'inputType': 'number'}},
    'quantity':     {'rules': {'minValue': 0, 'maxValue': 9999},
                     'additionalFields': {'placeholder': '1', 'step': 1, 'inputType': 'number'}},
    'rating':       {'rules': {'minValue': 0, 'maxValue': 5},
                     'additionalFields': {'helperText': 'From 0 to 5 stars.', 'step': 0.5,
                                          'inputType': 'number'}},
    'weight':       {'rules': {'minValue': 0},
                     'additionalFields': {'placeholder': '0.50', 'suffix': 'kg', 'step': 0.01,
                                          'inputType': 'number'}},
    'height':       {'rules': {'minValue': 0},
                     'additionalFields': {'placeholder': '10', 'suffix': 'cm', 'step': 0.1,
                                          'inputType': 'number'}},
    'width':        {'rules': {'minValue': 0},
                     'additionalFields': {'placeholder': '10', 'suffix': 'cm', 'step': 0.1,
                                          'inputType': 'number'}},
    'depth':        {'rules': {'minValue': 0},
                     'additionalFields': {'placeholder': '10', 'suffix': 'cm', 'step': 0.1,
                                          'inputType': 'number'}},

    # --- Catalog metadata ---
    'sku':          {'rules': {'pattern': r'^[a-zA-Z0-9_-]+$', 'minLength': 1, 'maxLength': 50},
                     'additionalFields': {'placeholder': 'MEN-SHIRT-001',
                                          'helperText': 'Letters, digits, dashes, underscores.'}},
    'slug':         {'rules': {'pattern': r'^[a-z0-9-]+$', 'minLength': 1, 'maxLength': 100},
                     'additionalFields': {'placeholder': 'product-name',
                                          'helperText': 'Lowercase letters, digits, hyphens.'}},
    'barcode':      {'rules': {'pattern': r'^[0-9]+$', 'minLength': 8, 'maxLength': 14},
                     'additionalFields': {'placeholder': '0123456789012',
                                          'helperText': 'EAN-13 / UPC barcode.'}},

    # --- Marketing / referral ---
    'friend_email': {'rules': {'pattern': r'^[^@\s]+@[^@\s]+\.[^@\s]+$'},
                     'additionalFields': {'placeholder': 'friend@example.com',
                                          'autoComplete': 'email', 'inputType': 'email'}},
    'friend_emails':{'rules': {'pattern': r'^[^@\s]+@[^@\s]+\.[^@\s]+$'},
                     'additionalFields': {'placeholder': 'friend1@example.com, friend2@example.com',
                                          'helperText': 'Comma-separated for multiple recipients.',
                                          'autoComplete': 'email'}},
    'referral_code':{'rules': {'pattern': r'^[A-Z0-9]{4,16}$'},
                     'additionalFields': {'placeholder': 'JANE2024',
                                          'helperText': '4-16 uppercase letters and digits.'}},

    # --- URL / SEO ---
    'cta_url':      {'rules': {'pattern': r'^(https?:\/\/|\/)[^\s]+$', 'maxLength': 500},
                     'additionalFields': {'placeholder': 'https://example.com  OR  /sale',
                                          'helperText': 'Absolute URL (https://...) or relative path (/...).',
                                          'autoComplete': 'url', 'inputType': 'url'}},
    'canonical':    {'rules': {'pattern': r'^https?:\/\/[^\s]+$', 'maxLength': 500},
                     'additionalFields': {'placeholder': 'https://example.com/page',
                                          'helperText': 'Canonical URL for SEO.',
                                          'autoComplete': 'url', 'inputType': 'url'}},
    'website':      {'rules': {'pattern': r'^https?:\/\/[^\s]+$', 'maxLength': 500},
                     'additionalFields': {'placeholder': 'https://example.com',
                                          'autoComplete': 'url', 'inputType': 'url'}},
    'meta_title':   {'rules': {'maxLength': 70},
                     'additionalFields': {'placeholder': 'Page title for search engines',
                                          'helperText': 'Up to 70 characters (truncated in Google).'}},
    'meta_description': {'rules': {'maxLength': 160},
                         'additionalFields': {'placeholder': 'Short page description shown in search results.',
                                              'helperText': 'Up to 160 characters.'}},
    'seo_title':    {'rules': {'maxLength': 70},
                     'additionalFields': {'placeholder': 'SEO title', 'helperText': 'Up to 70 characters.'}},
    'seo_description':{'rules': {'maxLength': 160},
                       'additionalFields': {'placeholder': 'SEO meta description.',
                                            'helperText': 'Up to 160 characters.'}},
    'og_title':     {'rules': {'maxLength': 70},
                     'additionalFields': {'placeholder': 'Open Graph title (social shares).',
                                          'helperText': 'Up to 70 characters.'}},
    'og_description':{'rules': {'maxLength': 200},
                      'additionalFields': {'placeholder': 'Open Graph description (social shares).',
                                           'helperText': 'Up to 200 characters.'}},

    # --- Consents ---
    'agreed_terms': {'rules': {'required': True},
                     'additionalFields': {'helperText': 'You must accept Terms of Service to continue.'}},
    'consent_marketing': {'additionalFields': {'helperText': "Optional — we'll send promotional emails."}},
    'consent_data_processing': {'rules': {'required': True},
                                'additionalFields': {'helperText': 'Required to process your order (GDPR).'}},
    'consent_cross_border': {'additionalFields': {'helperText': 'Allow us to transfer your data internationally.'}},
}


def enrich_attribute_validators(data):
    """Merge canonical validators into every attribute set schema by identifier.

    Idempotent: NEVER overwrites hand-set keys — only fills missing keys via setdefault.
    See `agents_datasets/rules/attribute-validators.md`.
    """
    fixes = []
    sets = data.get('attributes_sets') or []
    touched_sets = 0
    touched_attrs = 0

    for aset in sets:
        schema = aset.get('schema') or {}
        if not schema:
            continue
        per_set_touched = 0
        for attr_key, attr in schema.items():
            if not isinstance(attr, dict):
                continue
            ident = attr.get('identifier') or attr_key
            template = ATTR_VALIDATORS.get(ident)
            if not template:
                continue
            # Merge `rules` (set-default semantics, never overwrite)
            if 'rules' in template:
                existing_rules = attr.setdefault('rules', {})
                if not isinstance(existing_rules, dict):
                    existing_rules = {}
                    attr['rules'] = existing_rules
                for k, v in template['rules'].items():
                    if k not in existing_rules:
                        existing_rules[k] = v
                        per_set_touched += 1
            # Merge `additionalFields`
            if 'additionalFields' in template:
                existing_addl = attr.setdefault('additionalFields', {})
                if not isinstance(existing_addl, dict):
                    existing_addl = {}
                    attr['additionalFields'] = existing_addl
                for k, v in template['additionalFields'].items():
                    if k not in existing_addl:
                        existing_addl[k] = v
                        per_set_touched += 1
        if per_set_touched:
            touched_sets += 1
            touched_attrs += per_set_touched
    if touched_sets:
        fixes.append(
            f"+ validators: enriched {touched_attrs} rule/additionalField entries across {touched_sets} attribute sets"
        )
    return fixes


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    mapped_path = sys.argv[1]
    project_root = sys.argv[2]

    if not os.path.exists(mapped_path):
        print(f"ERROR: mapped.yaml not found: {mapped_path}")
        sys.exit(1)

    inspector_path = mapped_path.replace('.mapped.yaml', '.inspector.yaml')
    languages = ['en_US']
    if os.path.exists(inspector_path):
        try:
            ins = read_yaml(inspector_path)
            languages = ins.get('detected_languages') or [ins.get('language', 'en_US')]
        except Exception:
            pass

    print(f"Fixing {mapped_path} (languages: {languages})")
    fixes = fix_mapped(mapped_path, project_root, languages)
    print(f"\nApplied {len(fixes)} fixes:")
    for f in fixes:
        print(f"  - {f}")
    if not fixes:
        print("  (no fixes needed)")


if __name__ == '__main__':
    main()
