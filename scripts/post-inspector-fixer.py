#!/usr/bin/env python3
"""
post-inspector-fixer.py — deterministic fix of inspector.yaml after the code-inspector agent.

PURPOSE: eliminate typical inspector bugs that later break the mapper:
  1. title-mapping bug: title taken from a neighboring component (e.g. WomenCollection
     with title="Sale" instead of the real "New Arrivals" from its own file).
  2. null titles on blocks — try to extract from h2/h1/SECTION_TITLES in the source file.
  3. Inline blocks inside pages — recently_viewed/wishlist/similar, if present in code.

Runs AFTER the code-inspector agent and BEFORE the entity-mapper.

Usage:
    python3 post-inspector-fixer.py <inspector.yaml> <project_root>

Example:
    python3 post-inspector-fixer.py \\
        <output_dir>/<project>.inspector.yaml \\
        <path-to-project-root>
"""
import sys, os, re, yaml, json
from pathlib import Path


def read_yaml(path):
    with open(path) as f:
        return yaml.safe_load(f) or {}


def write_yaml(data, path):
    with open(path, 'w') as f:
        yaml.dump(data, f, allow_unicode=True, sort_keys=False, default_flow_style=False)


def find_component_file(project_root, component_name):
    """Find the .tsx file of a component by its name."""
    for ext in ('tsx', 'jsx', 'ts', 'js'):
        for src in ('src', 'app', '.'):
            cand = Path(project_root) / src / 'app' / 'components' / f'{component_name}.{ext}'
            if cand.exists():
                return cand
            cand = Path(project_root) / src / 'components' / f'{component_name}.{ext}'
            if cand.exists():
                return cand
    # broad fallback
    for p in Path(project_root).rglob(f'{component_name}.tsx'):
        if 'node_modules' not in str(p):
            return p
    return None


def parse_section_titles(project_root):
    """Extract SECTION_TITLES.<key>.title from data/sectionTitles.ts."""
    titles = {}
    candidates = list(Path(project_root).rglob('sectionTitles.ts')) + \
                 list(Path(project_root).rglob('sectionTitles.tsx'))
    for cand in candidates:
        if 'node_modules' in str(cand):
            continue
        try:
            text = cand.read_text()
        except Exception:
            continue
        # Simple heuristic: key: { title: 'X', ... }
        for m in re.finditer(r"(\w+)\s*:\s*\{[^}]*?title\s*:\s*['\"]([^'\"]+)['\"]", text):
            titles[m.group(1)] = m.group(2)
    return titles


def extract_title_from_component(component_file, section_titles):
    """Extract title from <h1>/<h2> or {SECTION_TITLES.X.title}."""
    if not component_file or not component_file.exists():
        return None, None
    text = component_file.read_text()

    # 1. <h2>{SECTION_TITLES.newArrivals.title}</h2>
    m = re.search(r'<h[12][^>]*>\s*\{[^}]*?SECTION_TITLES\.(\w+)\.title[^}]*?\}\s*</h[12]>', text)
    if m:
        key = m.group(1)
        if key in section_titles:
            return section_titles[key], f'{component_file.name}:SECTION_TITLES.{key}'

    # 2. <h2>Literal Text</h2>
    m = re.search(r'<h[12][^>]*>\s*([A-Z][^<{}\n]{2,50})\s*</h[12]>', text)
    if m:
        title = m.group(1).strip()
        # Decode HTML entities (&apos; -> ', &amp; -> &, &quot; -> ")
        title = (title.replace('&apos;', "'").replace('&amp;', '&')
                      .replace('&quot;', '"').replace('&#39;', "'"))
        if title and not title.startswith('{'):
            return title, f'{component_file.name}:<h2>{title}</h2>'

    return None, 'NOT_FOUND'


def detect_inline_blocks(project_root):
    """Find inline blocks in pages (recently_viewed, wishlist, similar)."""
    inline = []
    pages_dir = Path(project_root) / 'src' / 'app' / 'pages'
    if not pages_dir.exists():
        return inline
    for f in pages_dir.rglob('*.tsx'):
        if 'node_modules' in str(f):
            continue
        try:
            text = f.read_text()
        except Exception:
            continue
        text_lower = text.lower()
        rel = str(f.relative_to(project_root))

        # recently_viewed: Redux + .map in JSX
        if ('recentlyviewed' in text_lower and 'state.recentlyviewed' in text_lower
                and '.map(' in text and 'recently' in text_lower):
            inline.append({
                'identifier': 'recently_viewed',
                'kind': 'recently_viewed',
                'inline': True,
                'source_components': [rel],
                'binding': 'product_page',
                'kind_evidence': [
                    f'{rel}: state.recentlyViewed.items + .map(allRecentlyViewed...)',
                    'detected by post-inspector-fixer.py'
                ],
            })

        # wishlist inline
        if 'wishlist' in text_lower and 'state.wishlist' in text_lower and '.map(' in text:
            inline.append({
                'identifier': 'wishlist_similar',
                'kind': 'wishlist_similar',
                'inline': True,
                'source_components': [rel],
                'binding': 'favorites',
                'kind_evidence': [f'{rel}: state.wishlist.items'],
            })

    return inline


def fix_inspector(inspector_path, project_root):
    data = read_yaml(inspector_path)
    fixes = []

    section_titles = parse_section_titles(project_root)
    print(f"  Found {len(section_titles)} SECTION_TITLES keys")

    # === Fix 1: title-mapping for blocks ===
    blocks = data.get('blocks', []) or []
    for b in blocks:
        ident = b.get('identifier', '?')
        # If title is null or suspicious -- try extracting from the real source
        cur_title = b.get('title')
        if isinstance(cur_title, dict):
            cur_val = cur_title.get('value')
        else:
            cur_val = cur_title

        # Get source component for this block
        source_components = b.get('source_components') or []
        if not source_components:
            continue
        comp_path_or_name = source_components[0]

        # source_components may contain either a class name (HeroSlider) or a path
        if '/' in comp_path_or_name or comp_path_or_name.endswith('.tsx'):
            comp_file = Path(project_root) / comp_path_or_name
        else:
            comp_file = find_component_file(project_root, comp_path_or_name)

        if not comp_file or not comp_file.exists():
            continue

        real_title, src = extract_title_from_component(comp_file, section_titles)
        if not real_title:
            continue

        # If the block is inline OR the source-component is a *Page.tsx file
        # (page-level component containing multiple <h2> sections), the first
        # `<h2>` found by regex is unreliable — it often picks an empty-state
        # heading or a sibling block's title, not THIS block's title. Skip the
        # auto-fill entirely; trust the inspector / leave null for the mapper
        # to derive from `kind_evidence`.
        is_inline_or_page = bool(b.get('inline')) or comp_file.name.endswith('Page.tsx')
        if is_inline_or_page:
            # Optional: only override if file contains ONE h2 total — then it's
            # unambiguous and safe to use.
            try:
                txt = comp_file.read_text(encoding='utf-8', errors='ignore')
            except OSError:
                continue
            h2_count = len(re.findall(r'<h2[^>]*>', txt))
            if h2_count > 1:
                continue

        if cur_val != real_title:
            fixes.append(f"block '{ident}' title: '{cur_val}' → '{real_title}' (from {src})")
            b['title'] = {'value': real_title, 'source': src}

    # === Fix 2: inline blocks in pages ===
    existing_idents = {b.get('identifier') for b in blocks}
    for inline_block in detect_inline_blocks(project_root):
        if inline_block['identifier'] not in existing_idents:
            blocks.append(inline_block)
            fixes.append(f"+ inline block '{inline_block['identifier']}' from {inline_block['source_components'][0]}")
    data['blocks'] = blocks

    # === Fix 3: 404 page if NotFoundPage exists in the project ===
    has_notfound = any(Path(project_root).rglob(name) for name in ['NotFoundPage.tsx', 'not-found.tsx', 'not-found.jsx'])
    has_notfound = bool(list(Path(project_root).rglob('NotFoundPage.tsx')) or
                        list(Path(project_root).rglob('not-found.tsx')))
    pages = data.get('pages', []) or []
    page_idents = {p.get('identifier') for p in pages}
    if has_notfound and '404' not in page_idents and 'not-found' not in page_idents:
        pages.append({
            'identifier': '404',
            'parent': None,
            'page_url': '404',
            'general_type_id': 3,
            'title': {'value': 'Page Not Found', 'source': 'post-inspector-fixer:NotFoundPage detected'},
        })
        fixes.append("+ page '404' (NotFoundPage detected in project)")
    data['pages'] = pages

    write_yaml(data, inspector_path)
    return fixes


def main():
    if len(sys.argv) < 3:
        print(__doc__)
        sys.exit(1)
    inspector_path = sys.argv[1]
    project_root = sys.argv[2]

    if not os.path.exists(inspector_path):
        print(f"ERROR: inspector.yaml not found: {inspector_path}")
        sys.exit(1)
    if not os.path.isdir(project_root):
        print(f"ERROR: project root not a dir: {project_root}")
        sys.exit(1)

    print(f"Fixing {inspector_path}")
    fixes = fix_inspector(inspector_path, project_root)
    print(f"\nApplied {len(fixes)} fixes:")
    for f in fixes:
        print(f"  - {f}")
    if not fixes:
        print("  (no fixes needed)")


if __name__ == '__main__':
    main()
