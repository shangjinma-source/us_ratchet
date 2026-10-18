"""Fixed-source, prepare-only business review pack. No risk decisions or apply calls.

Source hashes establish local saved-byte consistency, never SEC/clock/PIT authority.
The caller cannot choose source paths, manifests, checksums or permission booleans.
"""
from pathlib import Path
from html.parser import HTMLParser
from collections import Counter
from copy import deepcopy
import ast
import csv
import hashlib
import json
import os

import yaml

ROOT = Path(__file__).resolve().parents[1]
CONTRACT_PATH = ROOT / 'research_contracts/ndx_business_review_prepare_sources_20261009_v1.json'
CONTRACT_SHA256 = '619ac926847773f903186e9ed83f53d4581ea27a360076e71d0f6c0ad938c982'
SCHEMA = 'PREPARE_ONLY_BUSINESS_RISK_REVIEW_PACK_V1'
MAX_FILE_BYTES = 32_000_000
MAX_TOTAL_BYTES = 256_000_000
FALSE_FIELDS = ('accepted', 'risk_assigned', 'accepted_review_created', 'registry_apply_called',
    'source_authenticity_verified', 'point_in_time_verified', 'available_at_inferred',
    'promotion_allowed', 'identity_interval_verified', 'provider_binding_verified',
    'legal_training_input_admitted', 'http_performed', 'prices_or_returns_read')
PLAN = 'tmp/ten_business_review_prepare_plan_20261009_v1/plan.json'
COVER = 'tmp/existing_eleven_sec_cover_assembly_20261009_v1/assembly.json'
IDENTITY = 'data/cache/candidate_pools/ndx_taxonomy_v2/security_identity.csv'


def _require(value, message):
    if not value:
        raise ValueError(message)


def _sha(raw):
    return hashlib.sha256(raw).hexdigest()


def _encoded(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False).encode('utf8')


def _exact(actual, expected, message):
    _require(_encoded(actual) == _encoded(expected), message)


def _json(raw):
    def pairs(items):
        result = {}
        for key, value in items:
            _require(key not in result, 'Duplicate JSON key')
            result[key] = value
        return result
    def constant(value):
        raise ValueError('Nonfinite JSON: ' + value)
    return json.loads(raw, object_pairs_hook=pairs, parse_constant=constant)


def _safe(path):
    path = Path(path)
    _require(path.is_absolute(), 'Absolute fixed source required')
    for parent in (path, *path.parents):
        _require(not parent.is_symlink(), 'Symlink source forbidden')
    _require(path.is_file() and path.stat().st_size <= MAX_FILE_BYTES, 'Missing/oversize fixed source')
    return path


def _inventory(folder):
    _require(folder.is_dir() and not folder.is_symlink(), 'Fixed namespace missing/link')
    names = []
    for path in folder.rglob('*'):
        _require(not path.is_symlink(), 'Namespace symlink forbidden')
        if path.is_file():
            names.append(path.relative_to(folder).as_posix())
    return sorted(names)


class _FixedSources:
    def __init__(self):
        self.contract_raw = _safe(CONTRACT_PATH).read_bytes()
        _require(_sha(self.contract_raw) == CONTRACT_SHA256, 'Fixed contract SHA mismatch')
        self.contract = _json(self.contract_raw)
        _exact(sorted(self.contract), sorted(('schema', 'scope', 'bindings', 'namespace_inventories',
            'root_review_roles', 'expected_ticker_order', 'source_authenticity_verified',
            'point_in_time_verified', 'promotion_allowed', 'accepted_review_created')), 'Contract shape')
        _require(self.contract['schema'] == 'BUSINESS_REVIEW_PREPARE_FIXED_SOURCE_CONTRACT_V1', 'Contract schema')
        for field in ('source_authenticity_verified', 'point_in_time_verified', 'promotion_allowed', 'accepted_review_created'):
            _require(self.contract[field] is False, 'Contract authority forbidden')
        bindings = self.contract['bindings']
        _require(type(bindings) is dict and 0 < len(bindings) <= 512, 'Bounded fixed roster')
        self.raw = {}
        self.paths = {}
        total = 0
        self.check_inventory()
        for relative, digest in bindings.items():
            _require(type(relative) is str and not Path(relative).is_absolute() and '..' not in relative.split('/'), 'Fixed relative source')
            _require(type(digest) is str and len(digest) == 64 and all(c in '0123456789abcdef' for c in digest), 'Source SHA syntax')
            path = _safe(ROOT / relative)
            raw = path.read_bytes()
            total += len(raw)
            _require(total <= MAX_TOTAL_BYTES, 'Total source resource bound')
            _require(_sha(raw) == digest, 'Fixed source SHA mismatch: ' + relative)
            self.raw[relative] = raw
            key = os.path.normcase(os.path.abspath(path))
            _require(key not in self.paths, 'Fixed source alias')
            self.paths[key] = relative

    def check_inventory(self):
        for relative, expected in self.contract['namespace_inventories'].items():
            _require(not Path(relative).is_absolute() and '..' not in relative.split('/'), 'Fixed namespace path')
            _exact(_inventory(ROOT / relative), expected, 'Fixed namespace inventory drift: ' + relative)

    def final_guard(self):
        _require(_safe(CONTRACT_PATH).read_bytes() == self.contract_raw, 'Contract changed during read')
        for relative, digest in self.contract['bindings'].items():
            _require(_sha(_safe(ROOT / relative).read_bytes()) == digest, 'Final fixed source drift: ' + relative)
        self.check_inventory()

    def document(self, relative):
        _require(relative in self.raw, 'Source not in closed roster')
        return _json(self.raw[relative])

    def reference(self, relative):
        _require(relative in self.raw, 'Reference not in closed roster')
        return dict(path=str(ROOT / relative), sha256=self.contract['bindings'][relative])

    def follow(self, reference):
        # Reference comparison only: this method never performs IO.
        _require(type(reference) is dict and set(reference) == {'path', 'sha256'}, 'Closed reference shape')
        _require(type(reference['path']) is str and Path(reference['path']).is_absolute(), 'Absolute reference')
        key = os.path.normcase(os.path.abspath(reference['path']))
        _require(key in self.paths, 'Unknown reference, no IO allowed')
        relative = self.paths[key]
        _require(reference['sha256'] == self.contract['bindings'][relative], 'Reference SHA role mismatch')
        return self.raw[relative]


def _canonical(path):
    return '/' + '/'.join(part if part in ('html', 'body', 'head') or '[' in part else part + '[1]'
        for part in path.split('/') if part)


def _text(node):
    return ' '.join(' '.join(node['pieces']).split())


class _OriginalHTML(HTMLParser):
    """Independent original tag hierarchy and raw offsets, no producer/parser imports."""
    VOID = {'area', 'base', 'br', 'col', 'embed', 'hr', 'img', 'input', 'link', 'meta', 'param', 'source', 'track', 'wbr'}

    def __init__(self, raw):
        super().__init__(convert_charrefs=True)
        self.source = raw.decode('utf8')
        self.stack = []
        self.nodes = {}
        self.counts = Counter()
        self.lines = [0] + [i + 1 for i, c in enumerate(self.source) if c == '\n']
        self.feed(self.source)
        self.close()
        _require(not self.stack, 'Original HTML stack incomplete')

    def node(self, path):
        _require(_canonical(path) in self.nodes, 'Original DOM pointer missing')
        return self.nodes[_canonical(path)]

    def position(self):
        line, column = self.getpos()
        return self.lines[line - 1] + column

    def handle_starttag(self, tag, attrs):
        _require(len(self.stack) < 256 and len(self.nodes) < 250_000, 'Original HTML resource bound')
        parent = self.stack[-1] if self.stack else None
        counts = parent['counts'] if parent else self.counts
        counts[tag] += 1
        part = tag if tag in ('html', 'head', 'body') else f'{tag}[{counts[tag]}]'
        path = (parent['path'] if parent else '') + '/' + part
        _require(path not in self.nodes, 'Original DOM duplicate')
        node = dict(path=path, tag=tag, parent=parent, children=[], counts=Counter(), pieces=[],
            attrs=dict(attrs), start=self.position())
        node['start_tag_stop'] = node['start'] + len(self.get_starttag_text())
        self.nodes[path] = node
        if parent:
            parent['children'].append(node)
        if tag in self.VOID:
            node['stop'] = node['start_tag_stop']
        else:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in self.VOID:
            node = self.stack.pop()
            node['stop'] = node['start_tag_stop']

    def handle_endtag(self, tag):
        if tag in self.VOID:
            return
        _require(self.stack and self.stack[-1]['tag'] == tag, 'Original HTML mismatched tag')
        node = self.stack.pop()
        node['stop'] = self.source.index('>', self.position()) + 1

    def handle_data(self, data):
        for node in self.stack:
            node['pieces'].append(data)

    def byte_start(self, node):
        return len(self.source[:node['start']].encode('utf8'))

    def byte_stop(self, node):
        return len(self.source[:node['stop']].encode('utf8'))


def _check_segment(parser, segment):
    parent = parser.node(segment['parent_xpath'])
    begin, end = segment['child_index_start'], segment['child_index_stop_exclusive']
    _require(type(begin) is int and type(end) is int and 0 <= begin < end <= len(parent['children']), 'Segment integer bounds')
    nodes = parent['children'][begin:end]
    _require(len(nodes) == len(segment['included_children']), 'Complete segment child count')
    for index, (node, declared) in enumerate(zip(nodes, segment['included_children']), begin):
        _require(node['path'] == _canonical(declared['dom_xpath']) and index == declared['child_index'], 'Complete child pointer/order')
        text = _text(node)
        _require(len(text) == declared['normalized_characters'] and _sha(text.encode()) == declared['normalized_sha256'], 'Complete child text')
    return nodes, '\n'.join(_text(node) for node in nodes if _text(node)).encode('utf8')


def _check_direct(inputs, artifact, parser, raw):
    if 'all_included_sibling_ranges' in artifact:
        body = parser.node(artifact['source_parent_xpath'])
        begin, end = artifact['sibling_index_start'], artifact['sibling_index_stop']
        nodes = body['children'][begin:end]
        _require(len(nodes) == len(artifact['all_included_sibling_ranges']), 'Complete direct interval')
        for node, declared in zip(nodes, artifact['all_included_sibling_ranges']):
            _require(node['path'] == _canonical(declared['dom_xpath']), 'Original child pointer')
            _require(_sha(_text(node).encode()) == declared['normalized_sha256'] and len(_text(node)) == declared['normalized_characters'], 'Original child full text')
        start, stop = parser.node(artifact['start_dom_xpath']), parser.node(artifact['stop_exclusive_dom_xpath'])
        _require(_text(start) == artifact['start_heading_text'] and _text(stop) == artifact['stop_heading_text'], 'Actual original heading')
    else:
        _require(len(artifact['complete_range_segments']) == 1, 'Same-parent single interval')
        nodes, _ = _check_segment(parser, artifact['complete_range_segments'][0])
        start, stop = parser.node(artifact['start_heading']['dom_xpath']), parser.node(artifact['stop_exclusive_heading']['dom_xpath'])
        _require(_text(start) == artifact['start_heading']['text'] and _text(stop) == artifact['stop_exclusive_heading']['text'], 'Actual heading text')
        begin, end = parser.byte_start(start), parser.byte_start(stop)
        _require(begin == artifact['original_raw_byte_start'] and end == artifact['original_raw_byte_stop_exclusive'], 'Original raw interval bounds')
        _require(inputs.follow(artifact['original_interval_reference']) == raw[begin:end], 'Whole original raw interval bytes')
    _require(start['parent'] is stop['parent'] and nodes and nodes[0] is start, 'Actual same-parent boundary')
    body = start['parent']
    _require(body['children'][body['children'].index(start) + len(nodes)] is stop, 'Complete children through next heading')
    saved = inputs.follow(artifact['normalized_text_reference'])
    expected = '\n'.join(_text(node) for node in nodes if _text(node)).encode()
    _require(saved == expected and len(saved.decode('utf8')) == artifact['normalized_characters' if 'normalized_characters' in artifact else 'section_text_characters'], 'Whole direct section text')
    return len(nodes)


def _check_ccep(inputs, manifest, parser, raw):
    total = 0
    for declared in manifest['sections']:
        section = _json(inputs.follow(declared['reference']))
        expected_pages = [p for pair in section['original_printed_page_ranges'] for p in range(pair['start'], pair['end'] + 1)]
        _exact([p['printed_page'] for p in section['page_occurrences']], expected_pages, 'All original page occurrences/order')
        parts = []
        for entry in section['page_occurrences']:
            node = parser.node(entry['body_page_xpath'])
            begin, end = parser.byte_start(node), parser.byte_stop(node)
            _require(begin == entry['raw_byte_start'] and end == entry['raw_byte_stop_exclusive'], 'Whole page byte bounds')
            _require(inputs.follow(entry['raw_page_reference']) == raw[begin:end], 'Whole original page raw bytes')
            text = _text(node).encode()
            _require(inputs.follow(entry['normalized_page_text_reference']) == text, 'Whole original page text')
            _require(entry['original_printed_page_marker'] in text.decode() and len(text.decode()) == entry['normalized_characters'], 'Printed page identity')
            parts.append(text)
            total += 1
        for endpoint in section['original_endpoint_links']:
            anchor, target = parser.node(endpoint['anchor_xpath']), parser.node(endpoint['target_dom_xpath'])
            _require(anchor['attrs']['href'] == endpoint['original_href'] and target['attrs']['id'] == endpoint['original_href'][1:], 'Original endpoint href')
            _require(_text(anchor) == endpoint['printed_page_label'], 'Original endpoint printed page')
        _require(inputs.follow(section['section_assembly_reference']) == b'\n\n'.join(parts), 'Whole section page assembly')
    _require(total == 43 and len(manifest['sections']) == 4, 'Complete43 referenced pages')
    return total


def _check_fer(inputs, artifact, parser, raw):
    _require(len(artifact['segments']) == 27 and artifact['assembled_raw_contiguous_interval_claimed'] is False, 'Explicit27 segmented source roles')
    parts, included = [], set()
    for index, reference in enumerate(artifact['segments']):
        segment = _json(inputs.follow(reference['reference']))
        _require(segment['segment_index'] == index, 'Segment order')
        nodes, text = _check_segment(parser, segment['complete_range_segment'])
        begin, end = parser.byte_start(nodes[0]), parser.byte_stop(nodes[-1])
        _require(begin == segment['raw_byte_start'] and end == segment['raw_byte_stop_exclusive'], 'Segment raw byte bounds')
        _require(inputs.follow(segment['original_raw_fragment_reference']) == raw[begin:end], 'Complete segment raw bytes')
        _require(inputs.follow(segment['normalized_text_reference']) == text, 'Complete segment full text')
        included.update(node['path'] for node in nodes)
        parts.append(text)
    _require(len(included) == 1155 and inputs.follow(artifact['assembled_text_reference']) == b'\n\n'.join(parts), 'All1155/wholeFER assembly')
    exclusions = _json(inputs.follow(artifact['exclusion_reference']))
    _require(len(exclusions['excluded_page_wrappers']) == 54 and len(exclusions['outside4b_logical_boundary_nodes']) == 6, 'Exclusion source roles')
    for entry in exclusions['excluded_page_wrappers']:
        node = parser.node(entry['excluded_dom_xpath'])
        _require(_text(node) == entry['complete_normalized_text'], 'Excluded wrapper original text')
        _require(_sha(raw[parser.byte_start(node):parser.byte_stop(node)]) == entry['complete_raw_outer_element_sha256'], 'Excluded wrapper original bytes')
        _require(node['path'] not in included, 'Exclusion/inclusion conflict')
    for entry in exclusions['outside4b_logical_boundary_nodes']:
        node = parser.node(entry['dom_xpath'])
        _require(node['path'] not in included and _text(node) == entry['normalized_text'] and entry['business_content_may_be_present'] is True, 'Next4C remains business scope, not footer')
    return len(included)


def _template_columns(inputs):
    syntax = ast.parse(inputs.raw['data/ndx_taxonomy_review.py'])
    assignments = [node for node in syntax.body if isinstance(node, ast.Assign) and any(isinstance(t, ast.Name) and t.id == 'REVIEW_TEMPLATE_COLUMNS' for t in node.targets)]
    _require(len(assignments) == 1, 'Existing template declaration')
    columns = ast.literal_eval(assignments[0].value)
    _require(type(columns) is list and len(columns) == len(set(columns)) and all(type(c) is str for c in columns), 'Existing template columns')
    return columns


def prepare_reviewpack():
    """Read only the fixed local roster and independently reconstruct all complete facts."""
    inputs = _FixedSources()
    plan, cover = inputs.document(PLAN), inputs.document(COVER)
    _exact([row['ticker'] for row in plan['rows']], inputs.contract['expected_ticker_order'], 'All10 issuer order')
    columns = _template_columns(inputs)
    taxonomy = yaml.safe_load(inputs.raw['config/candidate_taxonomy_v2.yaml'])
    _require(taxonomy['taxonomy_id'] == 'us_growth_risk_chain_taxonomy_v2', 'Original controlled taxonomy')
    identity_rows = list(csv.DictReader(inputs.raw[IDENTITY].decode('utf-8-sig').splitlines()))
    rows, counts = [], dict(direct_section_children=0, ccep_page_occurrences=0, fer_content_children=0)
    for row in plan['rows']:
        ticker = row['ticker']
        original = next(r for r in cover['rows'] if r['ticker'] == ticker)
        _exact(row['original_identity_candidates'], original['original_identity_matches'], 'Original identity candidates')
        _exact(row['filing_declaration'], original['original_filing'], 'Original filing/date declaration')
        for candidate in row['original_identity_candidates']:
            reference = candidate['reference']
            _require(reference['sha256'] == inputs.contract['bindings'][IDENTITY], 'Identity source SHA')
            _exact(identity_rows[reference['csv_data_row_index']], candidate['row'], 'Original identity CSV row')
        _require(row['source_available_at_utc'] is None and row['risk_chain'] is None and row['status'] == 'pending_review', 'Pending only source facts')
        parser = _OriginalHTML(inputs.follow(row['raw_reference']))
        raw = inputs.follow(row['raw_reference'])
        manifest = _json(inputs.follow(row['raw_manifest_reference']))
        _require(manifest['content_sha256'] == _sha(raw) and manifest['fetched_at'] == row['local_fetched_at_as_manifest_declared'], 'Original local capture declaration')
        evidence = row['business_evidence']
        if evidence is None:
            _require(ticker == 'TRI' and row['local_attachment_reference'] is None, 'OnlyTRI cover-only blocker')
        else:
            artifact = _json(inputs.follow(row['full_business_fact_reference']))
            if ticker == 'CCEP':
                complete = inputs.document('tmp/ccep_item4_complete_referenced_pages_20261009_v1/manifest.json')
                counts['ccep_page_occurrences'] = _check_ccep(inputs, complete, parser, raw)
            elif ticker == 'FER':
                counts['fer_content_children'] = _check_fer(inputs, artifact, parser, raw)
                _require(len(row['original_identity_candidates']) == 2, 'BothFER identity candidates required')
                _exact(artifact['original_identity_candidates'], row['original_identity_candidates'], 'FER no identity selection')
            else:
                counts['direct_section_children'] += _check_direct(inputs, artifact, parser, raw)
            parts = []
            for node in evidence['complete_original_nodes']:
                text = _text(parser.node(node['raw_dom_xpath']))
                _require(text == node['complete_node_text'] and _sha(text.encode()) == node['complete_node_text_sha256'], 'Actual source business node')
                parts.append(text)
            separator = ast.literal_eval(evidence['quote_join_rule'])
            _require(separator in (' ', '\n'), 'Known quote normalization')
            quote = separator.join(parts)
            _require(quote == evidence['exact_quote_text'] and _sha(quote.encode()) == evidence['exact_quote_sha256'], 'Exact source quote')
            for reference_key, begin_key, end_key in [('exact_saved_text_reference', 'saved_text_codepoint_start', 'saved_text_codepoint_stop'), ('full_assembled_text_reference', 'full_text_codepoint_start', 'full_text_codepoint_stop')]:
                full = inputs.follow(evidence[reference_key]).decode('utf8')
                begin, end = evidence[begin_key], evidence[end_key]
                _require(type(begin) is int and type(end) is int and 0 <= begin < end <= len(full) and full[begin:end] == quote, 'Quote full text offsets')
        template = dict.fromkeys(columns, '')
        template.update(evidence_id='conditional-full-business:' + row['cik'] + ':' + row['filing_declaration']['accession_number'],
            issuer_id=row['issuer_id'], ticker=ticker, risk_chain=None, status='pending_review',
            evidence_source_type='sec_filing_business_description', evidence_source='Saved complete business facts, pending independent risk review',
            accession_number=row['filing_declaration']['accession_number'],
            evidence_locator=row['filing_declaration']['document_url'],
            evidence_excerpt=evidence['exact_quote_text'] if evidence else '',
            notes='No approval, risk or PIT authority. Identity candidates retained; security/effective/available fields intentionally unassigned.')
        # Local capture after selection is a diagnostic, not proof the filing was
        # unpublished then. The existing policy uses evidence publication date.
        capture_diagnostic = 'LOCAL_RAW_FETCH_POSTDATES_ORIGINAL_SELECTION_2026_07_13'
        blockers = [item for item in row['blockers'] if item != capture_diagnostic]
        rows.append(dict(template=template, original_identity_candidates=deepcopy(row['original_identity_candidates']),
            identity_resolution_status='AMBIGUOUS_TWO_CANDIDATES_NO_SELECTION' if ticker == 'FER' else 'ORIGINAL_CANDIDATE_ONLY_NO_INTERVAL_APPROVAL',
            original_filing_declaration=deepcopy(row['filing_declaration']), original_source_available_date_as_declared=row['filing_declaration']['source_available_date'],
            local_fetched_at_as_declared=row['local_fetched_at_as_manifest_declared'], source_available_at_utc=None,
            timing_declarations=dict(official_filing_date_as_declared=row['filing_declaration']['filing_date'],
                official_acceptance_datetime_as_declared=row['filing_declaration']['acceptance_datetime'],
                local_capture_datetime_as_declared=row['local_fetched_at_as_manifest_declared'],
                actual_risk_review_datetime=None, official_publication_time_independently_verified=False),
            timing_policy='evidence_available_date <= selection_date; no historical backfill. Later local capture alone does not establish prior nonpublication. Official accession/submission publication evidence plus unchanged original may support its actual interval, never earlier business regimes.',
            full_business_fact_reference=deepcopy(row['full_business_fact_reference']),
            complete_business_evidence=deepcopy(evidence), blockers=blockers,
            timing_diagnostics=[capture_diagnostic],
            **dict.fromkeys(FALSE_FIELDS, False)))
    _exact(counts, dict(direct_section_children=960, ccep_page_occurrences=43, fer_content_children=1155), 'Whole fixed evidence coverage')
    inputs.final_guard()
    return dict(schema=SCHEMA, status='PENDING_REVIEW_ONLY', taxonomy_id=taxonomy['taxonomy_id'],
        controlled_taxonomy_reference=inputs.reference('config/candidate_taxonomy_v2.yaml'),
        existing_template_source_reference=inputs.reference('data/ndx_taxonomy_review.py'), template_columns=columns,
        fixed_source_contract_reference=dict(path=str(CONTRACT_PATH), sha256=CONTRACT_SHA256),
        source_prepare_plan_reference=inputs.reference(PLAN), independently_reconstructed_counts=counts,
        root_review_references=[inputs.reference(p) for p in inputs.contract['root_review_roles']],
        rows=rows, source_hashes=dict(inputs.contract['bindings']),
        source_claim_semantics='Fixed local saved bytes reverified; not source/clock/PIT authentication',
        full_transitive_source_authentication_performed=False, **dict.fromkeys(FALSE_FIELDS, False))


def validate_reviewpack(value):
    """Rebuild from fixed originals; reject missing/extra/reordered/privileged caller data."""
    expected = prepare_reviewpack()
    _exact(value, expected, 'Reviewpack differs from complete fixed pending originals')
    return deepcopy(expected)
