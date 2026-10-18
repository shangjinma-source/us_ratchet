"""Pure parent-edge planning; hosts verify bytes, metadata and replay arithmetic.

This module never loads a path, invokes a publisher, or calculates a history.
An accepted envelope is a structural association, not authenticated evidence.
"""
from copy import deepcopy
from backtest import ndx_compact_history_runtime_registration_research_v1 as reference_kernel


SCHEMA = 'COMPACT_ANCESTRY_WORK_ITEMS_V1'
REFERENCE_KERNEL_SHA256 = 'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23'
PARENT_ROLES = ('reference', 'publication_reference', 'readback_reference', 'reader_reference')
OBSERVATION_ROLES = ('payload_reference', 'receipt_reference', 'audit_reference', 'reader_reference')
TERMINAL_SCHEMA = 'PROSPECTIVE_GAP_EXTENSION_HISTORY_V3'
ACTUAL_SCHEMA = 'PROSPECTIVE_OBSERVATION_PARENT_HISTORY_V4'
GAP_SCHEMA = 'PROSPECTIVE_GAP_EXTENSION_HISTORY_V5'
MAX_PARENT_NODES = 128
FLAGS = dict.fromkeys(('source_authenticity_verified', 'clock_authenticity_verified',
    'filesystem_attempt_inventory_authenticated', 'point_in_time_verified',
    'full_transitive_source_closure_reverified', 'future_independent_oos',
    'promotion_allowed', 'live_mutation_allowed'), False)


def require(condition, message):
    if not condition:
        raise ValueError(message)


def reference(value):
    require(type(value) is dict and set(value) == {'path', 'sha256'}, 'Exact immutable reference')
    path, digest = value['path'], value['sha256']
    reference_kernel.canonical_path(path)
    require(type(digest) is str and len(digest) == 64 and
        set(digest) <= set('0123456789abcdef'), 'Bound immutable SHA')
    return deepcopy(value)


def references(value, roles):
    require(type(value) is dict and set(value) == set(roles), 'Exact reference roles')
    result = {role: reference(value[role]) for role in roles}
    require(len({_path_key(item) for item in result.values()}) == len(result), 'Distinct reference role paths')
    return result


def _path_key(item):
    return str(reference_kernel.canonical_path(item['path'])).casefold()


def _same(left, right, message):
    # Equality alone accepts False == 0, so recursively retain JSON value types.
    require(type(left) is type(right), message)
    if type(left) is dict:
        require(set(left) == set(right), message)
        for key in left:
            _same(left[key], right[key], message)
    elif type(left) in (list, tuple):
        require(len(left) == len(right), message)
        for first, second in zip(left, right):
            _same(first, second, message)
    else:
        require(left == right, message)


def classify_parent_edge(envelope, *, bound_pair, legacy_implementations=()):
    """Associate original refs and implementation roles, without IO validation.

    Legacy implementations are a separate host-fixed table, never an artifact
    allowlist. Hosts must validate all original wrapper/START fields themselves.
    """
    require(type(envelope) is dict and set(envelope) ==
        set(PARENT_ROLES) | {'document', 'publication', 'readback'}, 'Complete parent envelope')
    current = references({role: envelope[role] for role in PARENT_ROLES}, PARENT_ROLES)
    document, publication, readback = (envelope[key] for key in ('document', 'publication', 'readback'))
    require(all(type(value) is dict for value in (document, publication, readback)), 'Wrapper objects')
    history, inputs = document.get('history'), document.get('input_references')
    require(type(history) is dict and type(inputs) is dict, 'Original history and input references')
    parent_schema = history.get('schema')
    require(parent_schema in (TERMINAL_SCHEMA, ACTUAL_SCHEMA, GAP_SCHEMA), 'Known original parent schema')
    for value in (publication, readback):
        _same(value.get('history_reference'), current['reference'], 'Child history reference association')
        _same(value.get('input_references'), inputs, 'Original input association')
    _same(readback.get('publication_reference'), current['publication_reference'], 'Original publication association')
    _same(readback.get('reader_sha256'), current['reader_reference']['sha256'], 'Original reader association')
    pair_reference = reference(bound_pair['binding_reference'])
    contract_reference = reference(bound_pair['contract_reference'])
    pair_fields = ('implementation_pair_binding_reference', 'ancestry_contract_reference')
    has_pair = any(key in value for value in (document, publication, readback) for key in pair_fields)
    if has_pair:
        require(parent_schema == ACTUAL_SCHEMA, 'Pair contract supports genuine actual V4 only')
        for value in (document, publication, readback):
            _same(value.get(pair_fields[0]), pair_reference, 'Artifact binding cannot select host binding')
            _same(value.get(pair_fields[1]), contract_reference, 'Exact host contract role')
        _same(inputs.get('runtime'), reference(bound_pair['publisher_reference']), 'Host publisher role')
        _same(current['reader_reference'], reference(bound_pair['independent_reader_reference']), 'Host independent reader role')
        _same(inputs.get('dependencies'), bound_pair['algorithm_dependency_references']['publisher'], 'Host publisher algorithm roles')
        implementation = 'HOST_BOUND_CURRENT_PAIR'
    else:
        require(type(legacy_implementations) in (tuple, list) and len(legacy_implementations) <= MAX_PARENT_NODES,
            'Bounded host legacy implementation table')
        matched = []
        for item in legacy_implementations:
            keys = {'parent_schema', 'input_role', 'implementation_reference', 'reader_reference'}
            require(type(item) is dict and item.get('parent_schema') in
                (TERMINAL_SCHEMA, ACTUAL_SCHEMA, GAP_SCHEMA), 'Host legacy parent schema')
            if item['parent_schema'] == TERMINAL_SCHEMA:
                keys.add('terminal_reference')
            require(set(item) == keys and item['input_role'] in ('runtime', 'pure'), 'Exact host legacy role')
            runtime, reader = reference(item['implementation_reference']), reference(item['reader_reference'])
            terminal_matches = item['parent_schema'] != TERMINAL_SCHEMA or reference(item['terminal_reference']) == current['reference']
            if item['parent_schema'] == parent_schema and inputs.get(item['input_role']) == runtime and current['reader_reference'] == reader and terminal_matches:
                matched.append(item)
        require(len(matched) == 1, 'Exactly one known host legacy implementation')
        implementation = 'HOST_FIXED_LEGACY_IMPLEMENTATION'
    if parent_schema == TERMINAL_SCHEMA:
        kind, prior, observation, capture = 'terminal', None, None, None
    else:
        kind = 'actual' if parent_schema == ACTUAL_SCHEMA else 'gap'
        prior = references(history.get('parent_references'), PARENT_ROLES)
        _same(inputs.get('parent'), prior, 'True original parent association')
        if kind == 'actual':
            observation = references(history.get('observation_references'), OBSERVATION_ROLES)
            _same(inputs.get('observation'), observation, 'True original observation association')
            capture = None
        else:
            capture = references(history.get('capture_references'), PARENT_ROLES)
            _same(inputs.get('capture'), capture, 'True original capture association')
            observation = None
    return dict(kind=kind, parent_schema=parent_schema, child_references=current,
        prior_references=prior, observation_references=observation, capture_references=capture,
        implementation_role=implementation, binding_reference=pair_reference,
        contract_reference=contract_reference, metadata_verification_scope='EDGE_ASSOCIATIONS_ONLY_HOST_MUST_VERIFY_COMPLETE_WRAPPERS_START_AND_BYTES',
        whole_history_arithmetic_replay_required=kind != 'terminal', **FLAGS)


def inspect_ancestry_graph(root_refs, verified_envelopes, *, bound_pair, legacy_implementations=()):
    """Plan one original parent chain with a single global depth/cycle budget.

    ``verified_envelopes`` maps exact (path, SHA) tuples to host-read envelopes.
    Its name is a host obligation; this pure function cannot verify file bytes.
    Returned items run oldest first so hosts can replay every edge separately.
    """
    current = references(root_refs, PARENT_ROLES)
    require(type(verified_envelopes) is dict, 'Host envelope map')
    visited, paths, items = set(), {}, []
    while True:
        key = (current['reference']['path'], current['reference']['sha256'])
        identity = (_path_key(current['reference']), key[1])
        require(identity not in visited and len(visited) < MAX_PARENT_NODES, 'Global actual/gap cycle or depth')
        require(identity[0] not in paths, 'Conflicting repeated parent path')
        visited.add(identity)
        paths[identity[0]] = identity[1]
        require(key in verified_envelopes, 'Missing original parent envelope')
        envelope = verified_envelopes[key]
        require(type(envelope) is dict, 'Original envelope object')
        _same({role: envelope.get(role) for role in PARENT_ROLES}, current, 'All four original parent references')
        item = classify_parent_edge(envelope, bound_pair=bound_pair, legacy_implementations=legacy_implementations)
        items.append(item)
        if item['kind'] == 'terminal':
            break
        current = item['prior_references']
    return dict(schema=SCHEMA, root_references=references(root_refs, PARENT_ROLES),
        work_items=deepcopy(list(reversed(items))), parent_node_count=len(items),
        global_node_limit=MAX_PARENT_NODES, shared_metadata_only=True,
        append_algorithm_called=False, file_bytes_read=False, **FLAGS)
