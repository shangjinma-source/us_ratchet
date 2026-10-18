"""Pure actual/gap parent-edge planning with optional host consumer roles.

This module never loads a path, invokes a publisher, or calculates a history.
An accepted envelope is a structural association, not authenticated evidence.
"""
from copy import deepcopy
from backtest import ndx_compact_ancestry_contract_research_v1 as legacy_contract
from backtest import ndx_continuation_consumer_metadata_research_v1 as consumer_metadata


SCHEMA = 'COMPACT_ANCESTRY_WORK_ITEMS_V2'
LEGACY_CONTRACT_SHA256 = '1f50f4d5a893c163149bf69593880f73a1387293ee04b2ab9c0fcbb58090fc5e'
REFERENCE_KERNEL_SHA256 = legacy_contract.REFERENCE_KERNEL_SHA256
PARENT_ROLES = legacy_contract.PARENT_ROLES
OBSERVATION_ROLES = legacy_contract.OBSERVATION_ROLES
TERMINAL_SCHEMA = legacy_contract.TERMINAL_SCHEMA
ACTUAL_SCHEMA = legacy_contract.ACTUAL_SCHEMA
GAP_SCHEMA = legacy_contract.GAP_SCHEMA
MAX_PARENT_NODES = legacy_contract.MAX_PARENT_NODES
FLAGS = dict(legacy_contract.FLAGS)
require = legacy_contract.require
reference = legacy_contract.reference
references = legacy_contract.references
_path_key = legacy_contract._path_key
_same = legacy_contract._same


def classify_parent_edge(envelope, *, bound_pair, legacy_implementations=(),
        consumer_registry_view=None, consumer_registry_core_reference=None,
        metadata_contract_reference=None, registered_gap_dependency_references=None):
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
    consumer_fields = ('continuation_adapter_schema', 'consumer_role')
    has_consumer = any(key in value for value in (document, publication, readback) for key in consumer_fields)
    provenance_fields = ('consumer_role_registry_reference', 'consumer_registry_core_reference',
        'consumer_metadata_contract_reference')
    has_provenance = any(key in value for value in (document, publication, readback) for key in provenance_fields)
    has_metadata = any(key in value for value in (document, publication, readback)
        for key in consumer_metadata.METADATA_KEYS)
    consumer_input_fields = ('consumer_role_registry', 'consumer_registry_core',
        'consumer_metadata_contract', 'shared_ancestry_verifier')
    has_consumer_inputs = any(key in inputs for key in consumer_input_fields)
    if has_consumer:
        require(parent_schema == GAP_SCHEMA, 'Continuation parent role requires genuine gap V5')
        context = dict(bound_pair=bound_pair, consumer_registry_view=consumer_registry_view,
            consumer_registry_core_reference=consumer_registry_core_reference,
            metadata_contract_reference=metadata_contract_reference)
        for value, role in ((document, 'gap_publisher'), (publication, 'gap_publisher'),
                (readback, 'gap_independent_reader')):
            consumer_metadata.inspect_consumer_metadata(value, expected_role=role, **context)
        consumer_metadata.inspect_producer_input_references(inputs, consumer_role='gap_publisher',
            registered_dependency_references=registered_gap_dependency_references, **context)
        _same(current['reader_reference'], consumer_registry_view['consumer_references']['gap_independent_reader'],
            'Host continuation gap reader role')
        implementation = 'HOST_BOUND_CONTINUATION_GAP_PAIR'
    elif has_pair:
        require(parent_schema == ACTUAL_SCHEMA, 'Pair contract supports genuine actual V4 only')
        require(consumer_registry_view is None or has_provenance,
            'Current host consumer family requires compact provenance')
        require(not has_consumer_inputs or has_provenance,
            'Compact consumer inputs require complete outer provenance')
        require('shared_ancestry_verifier' not in inputs, 'Compact is not a consumer input role')
        require(not any('shared_ancestry_verifier_reference' in value
            for value in (document, publication, readback)), 'Compact uses three provenance fields, not a consumer header')
        for value in (document, publication, readback):
            _same(value.get(pair_fields[0]), pair_reference, 'Artifact binding cannot select host binding')
            _same(value.get(pair_fields[1]), contract_reference, 'Exact host contract role')
        _same(inputs.get('runtime'), reference(bound_pair['publisher_reference']), 'Host publisher role')
        _same(current['reader_reference'], reference(bound_pair['independent_reader_reference']), 'Host independent reader role')
        _same(inputs.get('dependencies'), bound_pair['algorithm_dependency_references']['publisher'], 'Host publisher algorithm roles')
        if has_provenance:
            # Compact publishers retain their B roles. Optional C provenance
            # never makes an actual artifact one of the six consumer roles.
            context = dict(bound_pair=bound_pair, consumer_registry_view=consumer_registry_view,
                consumer_registry_core_reference=consumer_registry_core_reference,
                metadata_contract_reference=metadata_contract_reference)
            expected = consumer_metadata.expected_consumer_metadata(consumer_role='gap_publisher', **context)
            for value in (document, publication, readback):
                _same({key: value.get(key) for key in provenance_fields},
                    {key: expected[key] for key in provenance_fields}, 'Exact compact consumer provenance')
            _same({key: inputs.get(key) for key in ('consumer_role_registry',
                    'consumer_registry_core', 'consumer_metadata_contract')},
                dict(consumer_role_registry=expected['consumer_role_registry_reference'],
                    consumer_registry_core=expected['consumer_registry_core_reference'],
                    consumer_metadata_contract=expected['consumer_metadata_contract_reference']),
                'Exact compact public consumer provenance')
        implementation = 'HOST_BOUND_CURRENT_PAIR'
    else:
        require(not has_metadata, 'Partial consumer metadata requires a host-bound implementation')
        require(not any(key in inputs for key in (*consumer_input_fields,
            'implementation_pair_binding', 'ancestry_contract')), 'Partial continuation public inputs cannot select legacy roles')
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


def inspect_ancestry_graph(root_refs, verified_envelopes, *, bound_pair, legacy_implementations=(),
        consumer_registry_view=None, consumer_registry_core_reference=None,
        metadata_contract_reference=None, registered_gap_dependency_references=None):
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
        item = classify_parent_edge(envelope, bound_pair=bound_pair, legacy_implementations=legacy_implementations,
            consumer_registry_view=consumer_registry_view,
            consumer_registry_core_reference=consumer_registry_core_reference,
            metadata_contract_reference=metadata_contract_reference,
            registered_gap_dependency_references=registered_gap_dependency_references)
        items.append(item)
        if item['kind'] == 'terminal':
            break
        current = item['prior_references']
    return dict(schema=SCHEMA, root_references=references(root_refs, PARENT_ROLES),
        work_items=deepcopy(list(reversed(items))), parent_node_count=len(items),
        global_node_limit=MAX_PARENT_NODES, shared_metadata_only=True,
        append_algorithm_called=False, file_bytes_read=False, **FLAGS)
