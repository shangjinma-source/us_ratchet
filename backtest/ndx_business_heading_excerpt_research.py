"""Strict DOM heading boundaries for research 10-K business evidence."""
import hashlib
import re

from lxml import html

START = re.compile(r'ITEM\s+1\s*[.\-:]?\s*BUSINESS', re.IGNORECASE)
END = re.compile(r'ITEM\s+1A\s*[.\-:]?\s*RISK\s+FACTORS', re.IGNORECASE)
BLOCKS = {'div', 'p', 'h1', 'h2', 'h3', 'h4'}


def extract_business_heading_excerpt(raw):
    """Accept one actual sibling heading pair, never a prose cross-reference.

    This deliberately narrow extractor rejects unsupported document layouts.
    It does not infer a risk chain, publication date, or source authenticity.
    """
    if type(raw) is not bytes or not raw:
        raise ValueError('Explicit nonempty raw HTML bytes required')
    document = html.fromstring(raw)
    for node in list(document.iter()):
        name = node.tag.rsplit('}', 1)[-1].rsplit(':', 1)[-1].lower() if isinstance(node.tag, str) else ''
        if name in ('script', 'style', 'head', 'hidden', 'resources') and node.getparent() is not None:
            node.getparent().remove(node)
    starts, ends = [], []
    for node in document.iter():
        if node.tag not in BLOCKS:
            continue
        # A table of contents is not a report body section; link-only nodes
        # also cannot establish the required heading boundary.
        if any(parent.tag in ('table', 'a') for parent in node.iterancestors()) or node.xpath('.//a[@href]'):
            continue
        text = ' '.join(node.text_content().split())
        if START.fullmatch(text):
            starts.append(node)
        elif END.fullmatch(text):
            ends.append(node)
    # Nested wrappers around the same heading are not independent headings.
    starts = [node for node in starts if not any(parent in starts for parent in node.iterancestors())]
    ends = [node for node in ends if not any(parent in ends for parent in node.iterancestors())]
    if len(starts) != 1 or len(ends) != 1 or starts[0].getparent() is not ends[0].getparent():
        raise ValueError('One unambiguous same-parent business/risk heading pair required')
    siblings = list(starts[0].getparent())
    first, last = siblings.index(starts[0]), siblings.index(ends[0])
    if last <= first:
        raise ValueError('Risk heading must follow business heading')
    fragments = [' '.join((node.text_content() + ' ' + (node.tail or '')).split())
                 for node in siblings[first:last]]
    text = '\n'.join(fragment for fragment in fragments if fragment)
    if len(text) < 200:
        raise ValueError('Substantive bounded business text required')
    return dict(schema='ndx_business_heading_excerpt_research_v1', section_text=text,
        section_text_sha256=hashlib.sha256(text.encode('utf8')).hexdigest(),
        raw_html_sha256=hashlib.sha256(raw).hexdigest(), section_text_characters=len(text),
        boundary_method='UNIQUE_SIBLING_DOM_ITEM1_ITEM1A_COMPLETE_HEADING_TEXT',
        start_sibling_offset=first, end_sibling_offset=last,
        risk_chain_assigned=False, publication_date_inferred=False,
        source_authenticity_verified=False, point_in_time_verified=False, promotion_allowed=False)
