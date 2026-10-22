"""Externalize a corrected Blogger XML without changing its template or cascade.

Usage:
  python3 tools/build_blogger_release.py theme-item.fixed.xml OUTPUT_DIR \\
    --base-url https://cdn.jsdelivr.net/gh/HG-oh/kr-inside-styles@COMMIT/assets/releases/v1

Accepts the original Blogger export or the corrected self-contained XML. For an
original export, the known common component fixes are applied from common_test.css
before extraction; all source corrections are recorded in release-audit.json.
Assets contain no deployment URL; they can be committed before the final XML is
built against a pinned commit. This command only writes local files, never publishes.
"""
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
import re
import xml.etree.ElementTree as ET
from urllib.parse import urlsplit
from xml.sax.saxutils import escape

ROOT = Path(__file__).resolve().parents[1]
ASSETS = ROOT / 'assets' / 'releases' / 'v1'
EXPRESSION = re.compile(r'\$\(([^)]+)\)')
SKIN = re.compile(r"(<b:skin\b[^>]*><!\[CDATA\[)(.*?)(\]\]></b:skin>)", re.S)
COMMON = re.compile(r"<style id='kr-inside-common-style' type='text/css'><!\[CDATA\[\n(.*?)\n\]\]></style>", re.S)
SCRIPT = re.compile(r"<script type='text/javascript'>\s*//<!\[CDATA\[\n((?:(?!</script>).)*?)\n[ \t]*//\]\]>\s*</script>", re.S)
BLOGGER = '{http://www.google.com/2005/gml/b}'


def sha256(content: str) -> str:
    return hashlib.sha256(content.encode('utf-8')).hexdigest()


def replace_once(source: str, before: str, after: str) -> str:
    if source.count(before) != 1:
        raise ValueError('Expected exactly one source occurrence: ' + before[:100])
    return source.replace(before, after, 1)


def unique_match(pattern: re.Pattern, source: str, description: str) -> re.Match:
    found = list(pattern.finditer(source))
    if len(found) != 1:
        raise ValueError(f'Expected one {description}, found {len(found)}')
    return found[0]


def rule_ranges(css: str) -> list[tuple[int, int, int]]:
    """Return top-level (prelude start, opening brace, end) ignoring strings/comments.

    The start includes leading whitespace/comments, allowing a byte-exact split.
    Semicolon at-rules are supported. Nested blocks retain their original bytes.
    """
    result = []
    depth = 0
    start = 0
    opening = None
    quote = None
    comment = False
    i = 0
    while i < len(css):
        char = css[i]
        if comment:
            if css[i:i + 2] == '*/':
                comment = False
                i += 2
                continue
        elif quote:
            if char == '\\':
                i += 2
                continue
            if char == quote:
                quote = None
        elif css[i:i + 2] == '/*':
            comment = True
            i += 2
            continue
        elif char in "\"'":
            quote = char
        elif char == '\\':
            i += 2
            continue
        elif char == '{':
            if depth == 0:
                opening = i
            depth += 1
        elif char == '}':
            depth -= 1
            if depth < 0:
                raise ValueError('Unmatched CSS closing brace')
            if depth == 0:
                result.append((start, opening, i + 1))
                start = i + 1
        elif char == ';' and depth == 0:
            start = i + 1
        i += 1
    if depth or quote or comment:
        raise ValueError('Unterminated CSS block, string, or comment')
    return result


def split_skin(skin: str) -> tuple[str, str, str, str]:
    marker = '/*-- Google Fonts --*/'
    if skin.count(marker) != 1:
        raise ValueError('Missing unique static skin boundary')
    offset = skin.index(marker)
    metadata, css = skin[:offset], skin[offset:]
    dynamic_rules = []
    for start, opening, end in rule_ranges(css):
        prelude = re.sub(r'/\*.*?\*/', '', css[start:opening], flags=re.S).strip()
        if '$(' in prelude:
            if not prelude.startswith('@media'):
                raise ValueError('Unexpected Blogger expression in CSS selector/at-rule')
            dynamic_rules.append((start, end))
    if len(dynamic_rules) != 1:
        raise ValueError(f'Expected one variable-dependent media rule, found {len(dynamic_rules)}')
    start, end = dynamic_rules[0]
    dynamic = css[start:end]
    if not re.search(r'@media\s*\(max-width:\s*\$\(row\.width \+ 50px\)\)', dynamic):
        raise ValueError('Unexpected dynamic breakpoint')
    return metadata, css[:start], dynamic, css[end:]


def validate_static_css(css: str) -> None:
    if '$(' in css or re.search(r'<(?:b|data|Variable|Group)\b', css):
        raise ValueError('Unresolved Blogger content in external CSS')
    rule_ranges(css)
    # Moving a relative URL to a different origin would change its meaning.
    for match in re.finditer(r'url\(\s*[\"\']?([^\s\"\')]+)', css):
        url = match.group(1)
        if not url.startswith(('https://', 'http://', '//', 'data:')):
            raise ValueError('Relative CSS URL needs an explicit migration: ' + url)


def prepare_source(original: str) -> tuple[str, list[str]]:
    """Apply only the established corrections when input is the original export."""
    original_link = "<link href='https://hg-oh.github.io/kr-inside-styles/common_test.css' rel='stylesheet' type='text/css'/>"
    if original_link not in original:
        if not COMMON.search(original):
            raise ValueError('Input must be the original Blogger export or corrected self-contained XML')
        return original, []
    css = (ROOT / 'common_test.css').read_text(encoding='utf-8')
    css = replace_once(css, ':root:not([data-theme="light"]):hover .faq-item,\n[data-theme="dark"]:hover .faq-item {\n    border-color: #4b5563;\n}', '''html[data-theme="dark"] .faq-item:hover,
html.dark-mode:not([data-theme="light"]) .faq-item:hover {
    border-color: #4b5563;
}
@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) .faq-item:hover { border-color: #4b5563; }
}''')
    css = replace_once(css, ':root:not([data-theme="light"]) .faq-item[open] summary,\n[data-theme="dark"] .faq-item[open] summary {\n    color: #bfdbfe;\n}', '''html[data-theme="dark"] .faq-item[open] summary,
html.dark-mode:not([data-theme="light"]) .faq-item[open] summary {
    color: #bfdbfe;
}
@media (prefers-color-scheme: dark) {
    :root:not([data-theme="light"]) .faq-item[open] summary { color: #bfdbfe; }
}''')
    css = css.replace('.dark-mode:root {', '.dark-mode:root:not([data-theme="light"]) {')
    css = css.replace('.dark-mode body {', '.dark-mode:root:not([data-theme="light"]) body {')
    # Keep reduced-motion timing overrides global, but preserve layout transforms.
    css = replace_once(css, '    transform: none !important;\n', '')
    motion_end = '    scroll-behavior: auto !important;\n  }\n}'
    css = replace_once(css, motion_end, motion_end[:-1] + '  :is(.faq-item, .card, .product-card, .product-dark-mode-toggle, .toc-dark-mode-toggle):hover {\n    transform: none !important;\n  }\n}')
    css = replace_once(css, '(prefers-contrast: high)', '(prefers-contrast: more)')
    css = '/* KR-Inside shared components: review-v1; source: common_test.css. */\n' + css
    candidate = original
    original_link = "<link href='https://hg-oh.github.io/kr-inside-styles/common_test.css' rel='stylesheet' type='text/css'/>"
    if ']]>' in css:
        raise ValueError('Unsafe CDATA boundary in CSS')
    candidate = replace_once(candidate, original_link, "<style id='kr-inside-common-style' type='text/css'><![CDATA[\n" + css + "\n]]></style>")
    candidate = replace_once(candidate, '//dnjs.cloudflare.com', '//cdnjs.cloudflare.com')
    # Keep Blogger variables and variable-dependent breakpoints inside b:skin.
    automatic = re.search(r'/\* ===== 자동 다크 모드 통합 스타일 ===== \*/\s*@media \(prefers-color-scheme: dark\) \{.*?\n\}', candidate, re.S)
    if not automatic:
        raise ValueError('Missing automatic theme dark-mode block')
    corrected = replace_once(automatic.group(), ':root {', ':root:not([data-theme="light"]) {')
    corrected = corrected.replace('.main-logo img {', ':root:not([data-theme="light"]) .main-logo img {')
    corrected = corrected.replace('#292027', '$(body.darkmode.bg)').replace('#5477eb', '$(main.color)')
    candidate = replace_once(candidate, automatic.group(), corrected)
    return candidate, [
        'embed corrected common_test.css temporarily before release extraction',
        'correct explicit-light FAQ text and hover conditions',
        'make component dark-mode selectors respect explicit light mode',
        'preserve layout transforms while reducing hover animation',
        'replace prefers-contrast high with standard more value',
        'correct cdnjs DNS prefetch spelling',
        'guard automatic theme dark mode against explicit light mode',
        'use Blogger background/accent variables in automatic dark mode',
    ]


def build(source_path: Path, output_dir: Path, base_url: str) -> dict:
    base_url = base_url.rstrip('/')
    parsed = urlsplit(base_url)
    if parsed.scheme != 'https' or not parsed.netloc or parsed.query or parsed.fragment:
        raise ValueError('--base-url must be an absolute HTTPS directory URL without a query/fragment')
    original_input = source_path.read_bytes().decode('utf-8')
    original_tree = ET.fromstring(original_input)
    source, source_corrections = prepare_source(original_input)
    ET.fromstring(source)
    skin_match = unique_match(SKIN, source, 'b:skin')
    common_match = unique_match(COMMON, source, 'corrected common style')
    metadata, prefix, dynamic, suffix = split_skin(skin_match.group(2))
    if '--kr-blogger-' in source:
        raise ValueError('Source already contains release bridge properties')

    expressions = list(dict.fromkeys(EXPRESSION.findall(prefix + suffix)))
    bridges = {expression: f'--kr-blogger-{index:02d}' for index, expression in enumerate(expressions, 1)}
    def externalize(css: str) -> str:
        return EXPRESSION.sub(lambda match: 'var(' + bridges[match.group(1)] + ')', css)
    def restore(css: str) -> str:
        for expression, name in bridges.items():
            css = css.replace('var(' + name + ')', '$(' + expression + ')')
        return css
    external_prefix, external_suffix = externalize(prefix), externalize(suffix)
    if restore(external_prefix) != prefix or restore(external_suffix) != suffix:
        raise ValueError('CSS expression substitution is not reversible')
    # Include the original attribution in each stylesheet as well as in b:skin.
    notice = re.match(r'/\*.*?\*/', metadata, re.S)
    if not notice:
        raise ValueError('Original theme copyright/attribution notice missing')
    header = notice.group() + '\n/* KR-Inside shared theme release v1; generated by tools/build_blogger_release.py. */\n'
    assets = {
        'common.css': common_match.group(1),
        'typify-base.css': header + external_prefix,
        'typify-responsive.css': header + external_suffix,
    }
    for name, css in assets.items():
        validate_static_css(css)

    bridge_css = '\n/* Blogger resolves these values per blog; keep them in b:skin. */\n:root {\n'
    bridge_css += ''.join(f'  {name}: $({expression});\n' for expression, name in bridges.items())
    bridge_css += '}\n'
    inline_skin = metadata + bridge_css + dynamic + '\n'
    def url(filename: str) -> str:
        return base_url + '/' + filename
    def attr(value: str) -> str:
        return escape(value, {"'": '&apos;', '"': '&quot;'})
    def link(filename: str) -> str:
        return "<link href='" + attr(url(filename)) + "' rel='stylesheet' type='text/css'/>"

    changes = []
    def change(before: str, after: str) -> None:
        nonlocal candidate
        candidate = replace_once(candidate, before, after)
        changes.append((before, after))
    candidate = source
    change(common_match.group(), link('common.css'))
    replacement_skin = (link('typify-base.css') + '\n' + skin_match.group(1) + inline_skin
                        + skin_match.group(3) + '\n' + link('typify-responsive.css'))
    change(skin_match.group(), replacement_skin)
    script_audit = []
    blocks = list(SCRIPT.finditer(source))
    for marker, filename in [('/*! Custom - Theia Sticky Sidebar', 'typify-plugins.js'),
                             ('function _0x46b6', 'typify-runtime.js')]:
        found = [match for match in blocks if match.group(1).startswith(marker)]
        if len(found) != 1:
            raise ValueError('Missing unique original static script: ' + marker)
        block = found[0]
        payload = block.group(1)
        if '<b:' in payload or '<data:' in payload:
            raise ValueError('Dynamic Blogger script cannot be externalized')
        assets[filename] = payload
        tag = "<script src='" + attr(url(filename)) + "' type='text/javascript'></script>"
        change(block.group(), tag)
        script_audit.append({'filename': filename, 'source_character_offset': block.start(),
                             'sha256': sha256(payload), 'payload_unchanged': True,
                             'execution': 'synchronous, original document position'})
    if [item['source_character_offset'] for item in script_audit] != sorted(item['source_character_offset'] for item in script_audit):
        raise ValueError('Unexpected original script order')

    candidate_tree = ET.fromstring(candidate)
    restored = candidate
    for before, after in reversed(changes):
        restored = replace_once(restored, after, before)
    if restored != source:
        raise ValueError('Unexpected edits outside the audited transformations')
    for tag in ('widget', 'template-skin'):
        before = [ET.tostring(node) for node in original_tree.iter(BLOGGER + tag)]
        after = [ET.tostring(node) for node in candidate_tree.iter(BLOGGER + tag)]
        if before != after:
            raise ValueError('Blogger ' + tag + ' content changed')
    # The template declares XHTML as its default namespace. Literal iter('script')
    # would silently find zero nodes and skip all execution-order checks.
    old_scripts = list(original_tree.iter('{http://www.w3.org/1999/xhtml}script'))
    new_scripts = list(candidate_tree.iter('{http://www.w3.org/1999/xhtml}script'))
    if len(old_scripts) < len(script_audit):
        raise ValueError('Expected XHTML script nodes were not found')
    if len(old_scripts) != len(new_scripts):
        raise ValueError('XML script count changed')
    external_script_names = ('typify-plugins.js', 'typify-runtime.js')
    script_positions = {}
    for index, (before, after) in enumerate(zip(old_scripts, new_scripts)):
        name = next((name for name in external_script_names if after.get('src') == url(name)), None)
        if name:
            if any(key in after.attrib for key in ('async', 'defer')):
                raise ValueError('Script execution semantics changed')
            if after.attrib != {'src': url(name), 'type': 'text/javascript'}:
                raise ValueError('Unexpected external script attributes')
            script_positions[name] = index
        elif ET.tostring(before) != ET.tostring(after):
            raise ValueError(f'Unrelated XML script at position {index} changed')

    if set(script_positions) != set(external_script_names):
        raise ValueError('External scripts missing from the XML script sequence')

    ASSETS.mkdir(parents=True, exist_ok=True)
    output_dir.mkdir(parents=True, exist_ok=True)
    for filename, content in assets.items():
        (ASSETS / filename).write_text(content, encoding='utf-8')
    output_path = output_dir / 'theme-item.lightweight.xml'
    output_path.write_text(candidate, encoding='utf-8')
    manifest = {
        'release': 'v1', 'base_url': base_url,
        'status': 'locally built; remote availability must be verified before installing XML',
        'source': {'filename': source_path.name, 'bytes': len(original_input.encode('utf-8')), 'sha256': sha256(original_input)},
        'corrected_intermediate': {'bytes': len(source.encode('utf-8')), 'sha256': sha256(source), 'corrections_applied': source_corrections},
        'xml': {'filename': output_path.name, 'bytes': len(candidate.encode('utf-8')), 'sha256': sha256(candidate)},
        'xml_reduction_percent': round(100 * (1 - len(candidate.encode('utf-8')) / len(original_input.encode('utf-8'))), 2),
        'assets': {filename: {'bytes': len(content.encode('utf-8')), 'sha256': sha256(content), 'url': url(filename)}
                   for filename, content in assets.items()},
    }
    audit = {
        'source_sha256': sha256(original_input), 'corrected_intermediate_sha256': sha256(source),
        'output_sha256': sha256(candidate),
        'source_corrections_before_extraction': source_corrections,
        'inverse_transform_reconstructs_corrected_source_exactly': restored == source,
        'only_xml_transformations': ['inline common CSS to stylesheet link',
                                    'static b:skin CSS to two stylesheet links around dynamic breakpoint',
                                    'two original static script payloads to synchronous external script tags'],
        'css_cascade_order': ['common.css', 'typify-base.css', 'b:skin dynamic breakpoint', 'typify-responsive.css'],
        'variable_definitions_preserved': len(re.findall(r'<Variable\b', metadata)),
        'widgets_preserved': len(list(original_tree.iter(BLOGGER + 'widget'))),
        'template_skin_preserved_exactly': True,
        'xml_script_nodes_preserved': len(old_scripts),
        'dynamic_and_third_party_scripts_preserved_exactly': True,
        'external_script_node_positions_zero_based': script_positions,
        'static_scripts': script_audit,
        'skin_segments': {key: {'bytes': len(value.encode('utf-8')), 'sha256': sha256(value)}
                          for key, value in [('metadata', metadata), ('static_prefix_original', prefix),
                                             ('dynamic_media_original', dynamic), ('static_suffix_original', suffix)]},
        'skin_source_reconstruction_exact': metadata + restore(external_prefix) + dynamic + restore(external_suffix) == skin_match.group(2),
        'blogger_expression_bridges': bridges,
        'external_css_has_unresolved_blogger_expressions': False,
        'fontface_rules_preserved': len(re.findall(r'@font-face\b', prefix + suffix)),
        'original_css_relative_url_changes': False,
        'publication_performed': False,
    }
    (output_dir / 'release-manifest.json').write_text(json.dumps(manifest, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    (output_dir / 'release-audit.json').write_text(json.dumps(audit, indent=2, ensure_ascii=False) + '\n', encoding='utf-8')
    return manifest


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('source_xml', type=Path)
    parser.add_argument('output_dir', type=Path)
    parser.add_argument('--base-url', required=True, help='Published, preferably commit-pinned HTTPS asset directory')
    args = parser.parse_args()
    print(json.dumps(build(args.source_xml, args.output_dir, args.base_url), indent=2, ensure_ascii=False))


if __name__ == '__main__':
    main()
