"""Fixed-host, read-only conditional77 source binding; never a qualified cash plan.

Only the pinned independent arithmetic inspector is executed. Original IO readers,
producers, account loaders, optimizers and network clients are never imported.
"""
from copy import deepcopy
from decimal import Decimal
from fractions import Fraction
from io import BytesIO
from pathlib import Path
import ast
import gzip
import hashlib
import json
import math
import re
import stat
import sys
import types


_ROOT = Path(__file__).resolve().parents[1]
_DESIGN = _ROOT / 'tmp/joint_full_conditional_source_adapter_design_20261009_v1'
_MEMO = _ROOT / 'tmp/joint_full_conditional_inspector_adaptation_memo_20261009_v1'
_HOST_FILES = (
    (_DESIGN / 'manifest_v2.json', 'c86276f6cc51f7d6f590c4c46e5044638f0e8d9b5bee26473c9fe8f586534789'),
    (_DESIGN / 'FIXED_HOST_CATALOGUE.json', '7d529cf138b75e5c3478478feb6e7ee8c860619a8e30accd0896ffd624f4b8ce'),
    (_DESIGN / 'CONTRACT.json', '7716af33d029ae3bb245eaeb8446b995e087e0251a856ce75faf77f788ccc3e3'),
    (_DESIGN / 'CATALOGUE_SUPPLEMENT.json', 'ba750de67b5d0a4fb17c0bf80816448c9a77af7bb58877964d514e2294ce73a7'),
    (_MEMO / 'manifest.json', 'ba4f70fa0149c436026b8ab0909e93a5ecc169a614d449f575d7896b9f7d4b82'),
    (_MEMO / 'ADAPTATION.md', '34537113d5d6b3c0707a79cd42e63e9c9635bc3718b421535a1ed14baafd772a'),
    (_MEMO / 'INSPECTOR_INTERFACE.json', '26e36671d7c9c3344b10d8f17c4a4a1ca406d21f105da8bdd8e30622c6fc2fa2'),
    (_MEMO / 'IMPORT_SURFACE.json', 'cbffacc4c04d0aa9e03bf61c64ff1457f65d0bd063080213de926e4639634917'),
)
_NUMBER = re.compile(r'-?(?:0|[1-9][0-9]*)(?:\.[0-9]+)?(?:[eE][+-]?[0-9]+)?')
_MAX_JSON = 40 * 1024 * 1024
_MAX_RAW = 32 * 1024 * 1024
_INSPECTOR_SHA = '7670ff8bdd39bc713463c1e15eda72b5988ff7e321b5bb02f567d8ea51aa313c'
_SIDECARS = ('original_evidence_and_projection', 'incremental_evidence_and_projection',
             'v3_incremental_evidence_and_projection', 'v4_incremental_evidence_and_projection',
             'v5_incremental_evidence_and_projection', 'v6_incremental_evidence_and_projection',
             'bulk_incremental_evidence_and_projection')
_SOURCE_IDS = ('HOST_BINDING', 'PIT_MEMBERSHIP', 'IDENTITY_AND_ACTIONS', 'RISK_AND_LIQUIDITY',
               'CAUSAL_MATRIX', 'PRIOR_BOOK', 'CASH_EVENT', 'PRICE_CONTEXT', 'POLICY', 'DUAL_BENCHMARKS')


def _require(ok, message):
    if not ok:
        raise ValueError(message)


def _sha(blob):
    return hashlib.sha256(blob).hexdigest()


def _encoded(value):
    return json.dumps(value, sort_keys=True, separators=(',', ':'), allow_nan=False).encode()


def _exact(left, right, label):
    _require(_encoded(left) == _encoded(right), label)


def _pairs(items):
    out = {}
    for key, value in items:
        _require(key not in out, 'Duplicate JSON key')
        out[key] = value
    return out


def _reject_constant(value):
    raise ValueError('Nonfinite JSON: ' + value)


def _pointer_key(key):
    return key.replace('~', '~0').replace('/', '~1')


def _strict_views(blob, *, with_tokens=False, native_compatibility=True):
    """L preserves exact values and tokens; C exists only for frozen JSON semantics."""
    _require(type(blob) is bytes and len(blob) <= _MAX_JSON, 'JSON byte bound')
    text = blob.decode('utf-8', errors='strict')
    fidelity = json.loads(text, parse_float=Decimal, object_pairs_hook=_pairs,
                          parse_constant=_reject_constant)
    compatibility = (json.loads(text, object_pairs_hook=_pairs, parse_constant=_reject_constant)
                     if native_compatibility else fidelity)
    tokens = []
    if with_tokens:
        pos = byte_pos = 0
        while pos < len(text):
            ch = text[pos]
            if ch == '"':
                _, end = json.decoder.scanstring(text, pos + 1, True)
                byte_pos += len(text[pos:end].encode('utf-8'))
                pos = end
            elif ch == '-' or ch.isdigit():
                match = _NUMBER.match(text, pos)
                _require(match is not None, 'Number token')
                lexeme = match.group()
                tokens.append(dict(original_lexeme=lexeme, utf8_byte_start=byte_pos,
                                   utf8_byte_stop=byte_pos + len(lexeme)))
                pos = match.end()
                byte_pos += len(lexeme)
            else:
                byte_pos += len(ch.encode('utf-8'))
                pos += 1
    token_index = {}
    token_position = 0

    def walk(left, right, pointer, depth):
        nonlocal token_position
        _require(depth <= 128, 'JSON depth bound')
        if type(left) is dict:
            _require(type(right) is dict and list(left) == list(right), 'L/C keys')
            for key in left:
                walk(left[key], right[key], pointer + '/' + _pointer_key(key), depth + 1)
        elif type(left) is list:
            _require(type(right) is list and len(left) == len(right), 'L/C array')
            for i, value in enumerate(left):
                walk(value, right[i], pointer + '/' + str(i), depth + 1)
        elif type(left) in (int, Decimal):
            if native_compatibility:
                _require(type(right) in (int, float) and (type(right) is int or math.isfinite(right)),
                         'Nonfinite compatibility number')
            if type(left) is Decimal:
                _require(left.is_finite(), 'Nonfinite exact number')
            if with_tokens:
                _require(token_position < len(tokens), 'Missing numeric token')
                token = tokens[token_position]
                token_position += 1
                _require(Decimal(token['original_lexeme']) == left, 'L/token number mismatch')
                token_index[pointer] = dict(token, original_json_type='number')
        else:
            _require(type(left) is type(right) and left == right, 'L/C scalar')

    walk(fidelity, compatibility, '', 0)
    _require(not with_tokens or token_position == len(tokens), 'Extra numeric token')
    return fidelity, compatibility if native_compatibility else None, token_index


def _raw_fidelity(raw):
    """Raw provider numbers never need a binary-float compatibility view."""
    _require(type(raw) is bytes and 0 < len(raw) <= _MAX_RAW, 'Raw byte bound')
    decoded = raw
    if raw.startswith(b'\x1f\x8b'):
        with gzip.GzipFile(fileobj=BytesIO(raw)) as stream:
            decoded = stream.read(_MAX_RAW + 1)
    _require(len(decoded) <= _MAX_RAW, 'Decoded raw byte bound')
    left, _, tokens = _strict_views(decoded, with_tokens=True, native_compatibility=False)
    return left, tokens, _sha(decoded)


def _json_fidelity(value):
    if type(value) is Decimal:
        return str(value)
    if type(value) is dict:
        return {k: _json_fidelity(v) for k, v in value.items()}
    if type(value) is list:
        return [_json_fidelity(v) for v in value]
    return value


def _number_descriptor(row, field, pointer, token_index):
    present = field in row
    value = row.get(field)
    leaf = pointer + '/' + _pointer_key(field) if present else None
    token = token_index.get(leaf)
    return dict(parent_json_pointer=pointer, field_name=field, present=present, json_pointer=leaf,
                original_json_type=('absent' if not present else 'null' if value is None else
                                    'number' if type(value) in (int, Decimal) else 'string' if type(value) is str else 'invalid'),
                original_lexeme=token['original_lexeme'] if token else None,
                original_value=token['original_lexeme'] if token else _json_fidelity(value),
                exact_fraction=str(Fraction(value)) if type(value) in (int, Decimal) else None,
                status=row.get('status'), blocking_reasons=deepcopy(row.get('reasons', [])),
                available_at=None, availability_verified=False)


def _pin_valid(reference):
    _require(type(reference) is dict and type(reference.get('path')) is str and
             Path(reference['path']).is_absolute() and type(reference.get('sha256')) is str and
             re.fullmatch('[0-9a-f]{64}', reference['sha256']) is not None, 'Pending or malformed host pin')


def _regular_path(path, *, directory=False):
    path = Path(path)
    _require(path.is_absolute() and path == Path(str(path.absolute())), 'Absolute host path')
    for part in (path, *path.parents):
        info = part.lstat()
        _require(not stat.S_ISLNK(info.st_mode) and not (getattr(info, 'st_file_attributes', 0) & 1024),
                 'Symlink/reparse host path')
    mode = path.lstat().st_mode
    _require(stat.S_ISDIR(mode) if directory else stat.S_ISREG(mode), 'Host file type')


def _namespace_snapshot(path):
    _regular_path(path, directory=True)
    records = []
    for file in sorted(Path(path).iterdir(), key=lambda p: p.name):
        _regular_path(file)
        records.append(dict(name=file.name, type='regular_file', reparse_point=False))
    return records


class _ReadSession:
    def __init__(self, catalogue):
        self.catalogue = catalogue
        self.sources = {}
        self.namespaces = {}

    def take_reference(self, reference):
        _pin_valid(reference)
        path = reference['path']
        _regular_path(path)
        blob = Path(path).read_bytes()
        _require(_sha(blob) == reference['sha256'], 'Source bytes changed: ' + path)
        if path in self.sources:
            _require(self.sources[path] == reference['sha256'], 'Conflicting host pins')
        self.sources[path] = reference['sha256']
        return blob

    def take(self, role):
        _require(role in self.catalogue['roles'], 'Unknown host role before IO')
        return self.take_reference(self.catalogue['roles'][role]['reference'])

    def document(self, role, *, with_tokens=False):
        views = _strict_views(self.take(role), with_tokens=with_tokens)
        expected = self.catalogue['roles'][role]['reference'].get('schema')
        if expected is not None:
            _require(type(views[1]) is dict and views[1].get('schema') == expected, 'Source schema: ' + role)
        return views

    def bind_namespace(self, path, expected):
        observed = _namespace_snapshot(path)
        _exact(observed, expected, 'Exact host namespace: ' + str(path))
        self.namespaces[str(path)] = deepcopy(expected)

    def guard(self):
        # Internal snapshots are never returned by reference.
        for path, expected in self.sources.items():
            _regular_path(path)
            _require(_sha(Path(path).read_bytes()) == expected, 'Final source drift: ' + path)
        for path, expected in self.namespaces.items():
            _exact(_namespace_snapshot(path), expected, 'Final namespace drift: ' + path)


def _bootstrap(include_saved_dual_benchmarks):
    _require(type(include_saved_dual_benchmarks) is bool, 'Explicit optional benchmark bool')
    # Validate the entire fixed anchor table before any artifact stat/open.
    for path, sha in _HOST_FILES:
        _pin_valid(dict(path=str(path), sha256=sha))
    session = _ReadSession(dict(roles={}))
    host = {}
    for path, sha in _HOST_FILES:
        blob = session.take_reference(dict(path=str(path), sha256=sha))
        if path.suffix == '.json':
            host[path.name] = _strict_views(blob)[1]
    catalogue = host['FIXED_HOST_CATALOGUE.json']
    contract = host['CONTRACT.json']
    supplement = host['CATALOGUE_SUPPLEMENT.json']
    _require(len(catalogue['roles']) == 291 and len(catalogue['channel_order']) == 77, 'Fixed catalogue shape')
    pins = {}
    for item in catalogue['roles'].values():
        reference = item['reference']
        _pin_valid(reference)
        old = pins.setdefault(reference['path'], reference['sha256'])
        _require(old == reference['sha256'], 'Conflicting catalogue pin')
    _exact([r['requirement_id'] for r in contract['source_checks']], list(_SOURCE_IDS), 'Ten source obligations')
    session.catalogue = catalogue
    for item in catalogue['namespaces'].values():
        if item['profile'].startswith('CORE'):
            expected = [dict(name=n, type='regular_file', reparse_point=False)
                        for n in item['expected_direct_regular_files']]
            session.bind_namespace(item['path'], expected)
    raw_ns = supplement['raw_capture_namespace']
    session.bind_namespace(raw_ns['path'], raw_ns['expected_direct_entries'])
    return session, catalogue, contract, supplement


def _reference(catalogue, role, pointer=None):
    source = catalogue['roles'][role]['reference']
    out = dict(path=source['path'], sha256=source['sha256'])
    if pointer is not None:
        out['json_pointer'] = pointer
    return out


def _pure_inspector(session):
    reference = session.catalogue['roles']['pure_inspector.history_v2']['reference']
    _require(reference['sha256'] == _INSPECTOR_SHA, 'Pinned independent inspector')
    blob = session.take('pure_inspector.history_v2')
    tree = ast.parse(blob.decode('utf-8'))
    allowed = {'copy', 'datetime', 'decimal', 'fractions', 'io', 'zoneinfo', 'gzip', 'hashlib', 'json', 'math'}
    for node in tree.body:
        _require(isinstance(node, (ast.Import, ast.ImportFrom, ast.Assign, ast.FunctionDef, ast.Expr)), 'Pure source top level')
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            names = [a.name for a in node.names] if isinstance(node, ast.Import) else [node.module]
            _require(all(n in allowed for n in names), 'Pure source imports')
        elif isinstance(node, ast.Expr):
            _require(isinstance(node.value, ast.Constant) and type(node.value.value) is str, 'Pure top-level expression')
        elif isinstance(node, ast.Assign):
            _require(all(isinstance(n.func, ast.Name) and n.func.id == 'dict'
                         for n in ast.walk(node.value) if isinstance(n, ast.Call)), 'Pure top-level calls')
    # Standard runtime initialization is explicitly outside zero-artifact-IO claims.
    # Reject repository shadowing of the ordinary stdlib dependency surface.
    for name in allowed:
        module = __import__(name)
        origin = getattr(module, '__file__', None)
        if origin is not None:
            _require(not Path(origin).resolve().is_relative_to(_ROOT), 'Stdlib shadowing')
    module = types.ModuleType('_fixed_conditional_price_inspector_7670')
    module.__file__ = reference['path']
    exec(compile(blob, reference['path'], 'exec'), module.__dict__)
    return module


def _issuer_coefficients(coordinates):
    multiplicity = {}
    for row in coordinates:
        issuer = row['issuer_id']
        multiplicity[issuer] = multiplicity.get(issuer, 0) + 1
    coefficients = [1]
    for issuer in sorted(multiplicity):
        new = coefficients + [0]
        for k, coefficient in enumerate(coefficients):
            new[k + 1] += multiplicity[issuer] * coefficient
        coefficients = new
    return dict(issuer_class_counts=multiplicity,
                per_k=[dict(k=k, conditional_support_count=str(coefficients[k]))
                       for k in range(1, len(coefficients))],
                k_above_issuer_count=dict(first_k=len(coefficients), count='0', proof='ONE_CLASS_PER_ISSUER'),
                qualified_denominator=None, supports_enumerated=False)


def _original_associations(session, catalogue, supplement):
    docs = {}
    fidelity = {}
    number_tokens = {}
    for role, assertion in supplement['preserved_original_assertions'].items():
        left, compat, tokens = session.document(role, with_tokens=(role == 'pool.0'))
        _exact(sorted(compat), assertion['top_level_exact_keys'], 'Original keys ' + role)
        _exact(compat.get('source_hashes'), assertion['source_hashes_declaration'], 'Original declaration ' + role)
        _exact(compat.get('input_references'), assertion['input_references_declaration'], 'Original inputs ' + role)
        docs[role] = compat
        fidelity[role] = left
        if tokens:
            number_tokens[role] = tokens
    panel = docs['pool.0']['panel']
    index = docs['history.0']
    coordinates = panel['universe']['data']
    # Frame orientation is read from the original split-table column names.
    names = panel['universe']['columns']
    coordinates = [dict(zip(names, row)) for row in coordinates]
    _require(len(coordinates) == 77 and len({r['security_id'] for r in coordinates}) == 77 and
             len({r['issuer_id'] for r in coordinates}) == 76, '77/76 original full pool')
    _require(len(index['rows']) == 77, 'All77 index rows')
    _exact(panel['observed_provenance_and_missing'], index['original_provenance_and_missing'], 'All original provenance')
    _require(len(panel['observed_provenance_and_missing']) == 101, '101 provenance denominator')
    outer = dict(inventory_reference=_reference(catalogue, 'pool.0', '/panel/universe'),
                 security_count=77, issuer_count=76, observed_provenance_count=101,
                 preserved_sidecar_references={k: _reference(catalogue, 'pool.0', '/' + k) for k in _SIDECARS})
    _exact(index['outer_inventory_contract'], outer, 'Independent outer contract')
    _exact(index['preserved_evidence_sidecars'], {k: docs['pool.0'][k] for k in _SIDECARS}, 'All seven sidecars')
    _require(index['new_independent_numeric_readback_completed'] is False and
             index['status'] == 'PUBLISHED_CONDITIONAL_NUMBERS_PENDING_INDEPENDENT_READBACK', 'Original pending preserved')
    audit = docs['history.2']
    _require(audit['status'] == 'PASS' and audit['independent_arithmetic_readback_completed'] is True and
             len(audit['rows']) == 77, 'Separate saved arithmetic audit')
    _exact(audit['index_reference'], _reference(catalogue, 'history.0'), 'Audit index')
    _exact(audit['publication_reference'], _reference(catalogue, 'history.1'), 'Audit publication')
    _exact(audit['inspector_reference'], _reference(catalogue, 'pure_inspector.history_v2'), 'Audit inspector')
    _exact(docs['history.1']['index_reference'], _reference(catalogue, 'history.0'), 'History publication')
    _exact(docs['pool.1']['panel_reference'], _reference(catalogue, 'pool.0'), 'Panel publication')
    requirements = docs['requirements.0']['requirements']
    _exact(index['reference_calendar'], requirements['reference_calendar'], 'Original requirements calendar')
    _exact(requirements['universe'], coordinates, 'Requirements whole77')
    _exact(requirements['observed_provenance_and_missing'], panel['observed_provenance_and_missing'], 'Requirements all101')
    _exact(docs['requirements.0']['projection_evidence']['complete_panel_sidecars'],
           index['preserved_evidence_sidecars'], 'Requirements seven sidecars')
    for i, row in enumerate(index['rows']):
        _exact(row['coordinate'], coordinates[i], 'Whole ordered coordinate')
        _exact(row['coordinate'], catalogue['channel_order'][i]['coordinate'], 'Host coordinate order')
        _exact(row['channel_reference'], _reference(catalogue, f'channel.{i:03d}.reference'), 'Index channel host role')
        _exact(audit['rows'][i]['coordinate'], row['coordinate'], 'Audit coordinate')
        _exact(audit['rows'][i]['channel_reference'], row['channel_reference'], 'Audit channel')
    return docs, fidelity, coordinates, outer, number_tokens


def _policy(session, contract):
    left, value, _ = session.document('policy.original')
    execution = value['execution_contract']
    params = execution['parameters']
    expected = {'initial_cash_usd': Fraction(25000), 'max_single_weight': Fraction(9, 20),
                'min_single_weight': Fraction(1, 20), 'top_weight_cap': Fraction(4, 5),
                'minimum_effective_n_ratio': Fraction(7, 10), 'risk_chain_top1_cap': Fraction(11, 20),
                'minimum_cash_buffer_usd': Fraction(100), 'transaction_cost_bps': Fraction(10)}
    for key, number in expected.items():
        _require(Fraction(left['execution_contract']['parameters'][key]) == number, 'Original policy parameter ' + key)
    _require(execution['cash_flow_role'] == 'ZERO_FLOW_BASELINE' and
             value['scope'] == contract['fixed_policy']['source_scope'], 'Original policy scope')
    return dict(source_reference=_reference(session.catalogue, 'policy.original'),
                original_document=_json_fidelity(left), parameter_scope='RESEARCH_REFERENCE_ONLY',
                mathematical_tolerance='1/1000000000', cash_event=None, formal_policy_authorized=False)


def _saved_benchmarks(session, catalogue):
    """Only saved identity/audit association; never raw NAV/FX/TSM reconstruction."""
    try:
        for item in catalogue['namespaces'].values():
            if item['profile'] == 'OPTIONAL_SAVED_DUAL_NUMBERS':
                session.bind_namespace(item['path'], [dict(name=n, type='regular_file', reparse_point=False)
                                       for n in item['expected_direct_regular_files']])
        optional_roles = [role for role, item in catalogue['roles'].items()
                          if item['profile'] == 'OPTIONAL_SAVED_DUAL_NUMBERS']
        # START/alignment and fixed supporting roles must be byte-guarded too;
        # namespace names alone do not protect their contents.
        for role in optional_roles:
            session.take(role)
        docs = {}
        facts = {}
        for group in ('incumbent_training', 'target_training'):
            for role in sorted(k for k in catalogue['roles'] if k.startswith(group + '.')):
                left, compat, tokens = session.document(role, with_tokens=True)
                docs[role] = compat
                facts[role] = dict(reference=_reference(catalogue, role), original_document=_json_fidelity(left),
                                   original_numeric_tokens=tokens)
        incumbent = docs['incumbent_training.0']
        audit = docs['incumbent_training.2']
        _require(audit['status'] == 'PASS', 'Saved incumbent audit')
        _exact(audit['inputs_reference'], _reference(catalogue, 'incumbent_training.0'), 'Incumbent evidence ref')
        _exact(audit['publication_reference'], _reference(catalogue, 'incumbent_training.1'), 'Incumbent publication ref')
        scoring = incumbent['scoring_inputs']
        _require(len(scoring['decisions']) == 6 and all(len(d['windows']) == 13 for d in scoring['decisions']), 'Incumbent all78')
        target = docs['target_training.1']
        target_audit = docs['target_training.3']
        _require(target_audit['status'] == 'PASS', 'Saved target audit')
        _exact(target_audit['index_reference'], _reference(catalogue, 'target_training.0'), 'Target audit index')
        _exact(target_audit['publication_reference'], _reference(catalogue, 'target_training.2'), 'Target audit publication')
        _require(len(target['modes']) == 2 and all(len(m['decisions']) == 6 and
                 all(len(d['windows']) == 13 for d in m['decisions']) for m in target['modes']), 'Target two full78 modes')
        return dict(status='SAVED_NUMBER_AND_EXISTING_AUDIT_ASSOCIATION_ONLY_NOT_NEW_RAW_REPLAY',
                    documents=facts, fresh_raw_reconstruction='SOURCE_BLOCKED',
                    fixed_optional_roles_read=optional_roles,
                    benchmark_qualified=False, formal_comparison_allowed=False, not_a_candidate_pool=True)
    except (ValueError, KeyError, TypeError, OSError, UnicodeError) as exc:
        return dict(status='SOURCE_BLOCKED', reason=str(exc), fresh_raw_reconstruction='SOURCE_BLOCKED',
                    benchmark_qualified=False, formal_comparison_allowed=False, partial_proof_claimed=False)


def read_conditional_full_pool_sources(*, include_saved_dual_benchmarks=False):
    """Read all fixed conditional77 inputs, independently replay prices, return facts+guard."""
    session, catalogue, contract, supplement = _bootstrap(include_saved_dual_benchmarks)
    docs, fidelity, coordinates, outer, root_number_tokens = _original_associations(session, catalogue, supplement)
    f_universe = fidelity['pool.0']['panel']['universe']
    faithful_coordinates = [_json_fidelity(dict(zip(f_universe['columns'], row))) for row in f_universe['data']]
    # Consume every core fixed role, never artifact source_hashes as an IO queue.
    deferred = {f'channel.{i:03d}.{kind}' for i in range(77)
                for kind in ('reference', 'raw_reference', 'receipt_reference')}
    for role, item in catalogue['roles'].items():
        if item['profile'].startswith('CORE') and role not in deferred:
            session.take(role)
    inspector = _pure_inspector(session)
    bridge_role = 'ndx_multidecision_scoring_history_independent_readback_v2_20261003.py.BOUND.bridge'
    bridge = session.document(bridge_role)[1]
    session.bind_namespace(str(Path(_reference(catalogue, bridge_role)['path']).parent),
                           [dict(name='bridge.json', type='regular_file', reparse_point=False)])
    bridge_rows = {}
    for row in bridge['rows']:
        _require(row['ticker'] not in bridge_rows, 'Unique bridge ticker')
        bridge_rows[row['ticker']] = row
    tzif = session.take('timezone.new_york')
    index = docs['history.0']
    _exact(index['window_contract'], inspector.CONTRACT, 'Fixed six505 contract')
    _require(len(bridge_rows) == 101 and bridge['candidate_cutoff'] == '2026-09-21', 'Full original bridge101')
    channels = []
    total_cells = 0
    blocked = {}
    for i, coordinate in enumerate(coordinates):
        role = f'channel.{i:03d}.reference'
        left, saved, tokens = session.document(role, with_tokens=True)
        raw_role = f'channel.{i:03d}.raw_reference'
        receipt_role = f'channel.{i:03d}.receipt_reference'
        raw = session.take(raw_role)
        raw_left, raw_tokens, decoded_sha = _raw_fidelity(raw)
        receipt = session.document(receipt_role)[1]
        result = inspector.inspect_scoring_history_channel(
            saved_channel=saved, raw_bytes=raw, raw_reference=_reference(catalogue, raw_role),
            receipt=receipt, receipt_reference=_reference(catalogue, receipt_role),
            bridge_row=bridge_rows[coordinate['ticker']], reference_calendar=index['reference_calendar']['dates'],
            tzif_bytes=tzif, window_contract=index['window_contract'], outer_inventory_contract=outer)
        _require(result['status'] == 'PASS' and len(saved['quote_rows']) == 610 and
                 len(saved['return_rows']) == 609 and len(saved['decisions']) == 6, 'Whole610/609/6 channel replay')
        _exact(saved['raw_reference'], _reference(catalogue, raw_role), 'Saved raw host role')
        _exact(saved['receipt_reference'], _reference(catalogue, receipt_role), 'Saved receipt host role')
        _require(all(len(d['windows']) == 13 for d in saved['decisions']), 'All78 per SID')
        count = sum(w['status'] == 'BLOCKED_WINDOW' for d in saved['decisions'] for w in d['windows'])
        blocked[coordinate['ticker']] = count
        total_cells += 78
        volumes = [_number_descriptor(row, 'raw_volume', f'/quote_rows/{r}', tokens)
                   for r, row in enumerate(left['quote_rows'])]
        raw_scope_tokens = {}
        provider_quote = raw_left['chart']['result'][0]['indicators']['quote'][0]
        for quote_row in left['quote_rows']:
            raw_index = quote_row['raw_row_index']
            if raw_index is None:
                continue
            for field in ('open', 'high', 'low', 'close', 'volume'):
                pointer = f'/chart/result/0/indicators/quote/0/{field}/{raw_index}'
                token = raw_tokens.get(pointer)
                if token is not None:
                    _require(Decimal(token['original_lexeme']) == provider_quote[field][raw_index], 'Raw L/token exact number')
                    raw_scope_tokens[pointer] = dict(token, exact_fraction=str(Fraction(Decimal(token['original_lexeme']))))
        channels.append(dict(coordinate=faithful_coordinates[i], source_reference=_reference(catalogue, role),
                             raw_reference=_reference(catalogue, raw_role), receipt_reference=_reference(catalogue, receipt_role),
                             original_channel=_json_fidelity(left), original_numeric_tokens=tokens,
                             raw_required_scope_numeric_tokens=raw_scope_tokens, raw_decoded_sha256=decoded_sha,
                             raw_token_offsets='DECODED_UTF8_JSON_BYTES_NOT_COMPRESSED_FILE_OFFSETS',
                             quote_volume_presence=volumes, independent_price_arithmetic=result,
                             original_float_return_semantics='OLD_FITTER_FLOAT_BOUNDARY_NOT_EXACT_RETURN',
                             availability_verified=False))
    _require(total_cells == 6006 and blocked.get('WDC') == 51 and blocked.get('LRCX') == 27 and
             all(n == 0 for ticker, n in blocked.items() if ticker not in ('WDC', 'LRCX')), 'Full blocked window denominator')
    volume_counts = {c['coordinate']['ticker']: sum(d['present'] for d in c['quote_volume_presence']) for c in channels}
    _require(volume_counts['WDC'] == 382 and volume_counts['LRCX'] == 478 and
             all(v == 610 for k, v in volume_counts.items() if k not in ('WDC', 'LRCX')), 'Optional volume presence preserved')
    policy = _policy(session, contract)
    optional = (_saved_benchmarks(session, catalogue) if include_saved_dual_benchmarks else
                dict(status='DISABLED', benchmark_qualified=False))
    facts = dict(schema='CONDITIONAL_FULL_POOL_SOURCE_FACTS_V1',
                 status='CONDITIONAL_NUMBERS_READ_BACK_REAL_SOURCE_BLOCKED',
                 binding_scope='LOCAL_FIXED_BYTES_AND_ASSOCIATIONS_ONLY_NOT_PROVIDER_OR_PIT_AUTHENTICATION',
                 catalogue_reference=dict(path=str(_HOST_FILES[1][0]), sha256=_HOST_FILES[1][1]),
                 conditional_security_count=77, conditional_issuer_count=76, observed_provenance_count=101,
                 conditional_inventory=faithful_coordinates, original_root_numeric_tokens=root_number_tokens,
                 observed_provenance=_json_fidelity(fidelity['pool.0']['panel']['observed_provenance_and_missing']),
                 issuer_support_domain=_issuer_coefficients(coordinates), qualified_inventory=None, qualified_denominator=None,
                 channel_facts=channels, window_coverage=dict(total_sid_decision_window_cells=6006,
                    windows_per_sid=78, blocked_by_ticker=blocked, missing_slots_dropped=False, unequal_window_pooling_allowed=False),
                 matrix_layout=dict(ordered_security_ids=[c['security_id'] for c in coordinates],
                    reference_calendar=deepcopy(index['reference_calendar']),window_contract=deepcopy(index['window_contract']),
                    required_union_dates=deepcopy(channels[0]['original_channel']['calendar']),
                    per_sid_decisions_preserved_in='channel_facts/original_channel/decisions', causal_matrix_admitted=False),
                 research_policy=policy,
                 latest_volume_panel=dict(source_reference=_reference(catalogue, 'pool.0', '/panel/raw_volume'),
                    original_frame=_json_fidelity(fidelity['pool.0']['panel']['raw_volume']), historical_cohort_qualification=False),
                 saved_history_state=dict(status=index['status'], new_independent_numeric_readback_completed=False),
                 existing_arithmetic_audit=dict(reference=_reference(catalogue, 'history.2'),
                    original_document=_json_fidelity(fidelity['history.2']), new_raw_audit_repeated=False),
                 current_price_arithmetic_readback=dict(status='PASS_PRICE_RETURN_WINDOW_ARITHMETIC_ONLY',channels=77),
                 saved_dual_benchmarks=optional, source_checks=deepcopy(contract['source_checks']),
                 registration_gaps=dict(real_joint_objective='UNREGISTERED',causal_action_rule='UNREGISTERED',
                    thirteen_cohort_prior_cash='SOURCE_BLOCKED'), current_new_money=None,current_account=None,plan_rows=[],
                 permissions=dict.fromkeys(contract['flags_false'],False),
                 preserved_original_assertions=deepcopy(supplement['preserved_original_assertions']),
                 unread_transitive_claims_are_not_io_permission=True,
                 large_original_evidence_references={k:_reference(catalogue,'pool.0','/'+k) for k in _SIDECARS})
    session.guard()
    facts['consumed_source_hashes'] = deepcopy(session.sources)
    facts['namespace_snapshots'] = deepcopy(session.namespaces)
    return dict(facts=facts, final_guard=session.guard)
