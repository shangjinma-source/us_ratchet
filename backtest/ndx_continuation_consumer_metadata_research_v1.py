"""Pure continuation metadata and public-input associations, without IO.

The pair and consumer views must first be checked against independent host
anchors. This contract selects no algorithms and verifies no file bytes. IO
callers reconstruct entire wrappers, STARTs and closures separately.
"""
from copy import deepcopy
from backtest import ndx_compact_history_runtime_registration_research_v1 as references
from backtest import ndx_continuation_consumer_role_registry_research_v1 as consumer_registry


REFERENCE_KERNEL_SHA256 = 'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23'
CONSUMER_REGISTRY_KERNEL_SHA256 = '184479c5e0e6412265e00cc875af1f7902e4f500dc984ca2aaaf3251bc8c433b'
SCHEMA = 'CONTINUATION_CONSUMER_METADATA_ASSOCIATIONS_V1'
ADAPTERS = {
    'capture_publisher': 'CONTINUATION_CAPTURE_PUBLISHER_V1',
    'capture_independent_reader': 'CONTINUATION_CAPTURE_INDEPENDENT_READER_V1',
    'observation_writer': 'CONTINUATION_OBSERVATION_WRITER_V1',
    'observation_independent_reader': 'CONTINUATION_OBSERVATION_INDEPENDENT_READER_V1',
    'gap_publisher': 'CONTINUATION_GAP_PUBLISHER_V1',
    'gap_independent_reader': 'CONTINUATION_GAP_INDEPENDENT_READER_V1',
}
METADATA_KEYS = ('continuation_adapter_schema', 'consumer_role',
    'implementation_pair_binding_reference', 'consumer_role_registry_reference',
    'ancestry_contract_reference', 'shared_ancestry_verifier_reference',
    'consumer_registry_core_reference', 'consumer_metadata_contract_reference')
REGISTERED_DEPENDENCY_ROLES = {
    'capture_publisher': ('capture_core', 'parent_view', 'legacy_view', 'compact_helpers', 'scoped', 'base'),
    'observation_writer': ('payload_core', 'parent_view', 'compact_helpers', 'capture_checker', 'csv_reader'),
    'gap_publisher': ('gap_core', 'parent_view', 'legacy_view', 'compact_helpers', 'prefix_core', 'scoped', 'base', 'capture_checker'),
}
PRODUCER_FOR_READER = {'capture_independent_reader': 'capture_publisher',
    'observation_independent_reader': 'observation_writer', 'gap_independent_reader': 'gap_publisher'}
OBSERVATION_READER_START_SCHEMA = 'PROSPECTIVE_OBSERVATION_CONTINUATION_READER_STARTED_V1'
OBSERVATION_BUSINESS_ADAPTER = 'REGISTERED_PROSPECTIVE_OBSERVATION_WRITER_V5'
NAMESPACE_FILES = {
    'capture_publisher': ('started.json', 'QQQ.csv', 'SPY.csv', 'New_York.tzif', 'capture.json', 'publication.json'),
    'capture_independent_reader': ('started.json', 'independent_readback.json'),
    'observation_writer': ('started.json', 'observation_payload.json', 'receipt.json'),
    'observation_independent_reader': ('started.json', 'observation_payload.json', 'receipt.json', 'reader_started.json', 'independent_readback.json'),
    'gap_publisher': ('started.json', 'history.json', 'publication.json', 'QQQ.accounted_prefix.csv', 'SPY.accounted_prefix.csv', 'QQQ.prefix_evidence.json', 'SPY.prefix_evidence.json'),
    'gap_independent_reader': ('started.json', 'independent_readback.json'),
}
FLAGS = dict(references.FLAGS, file_bytes_verified=False, full_wrapper_verified=False,
    append_algorithm_called=False, source_claims_select_io=False,
    implementation_pair_approval_authenticated=False)
require = references.require


def _same(left, right, message):
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


def _host_context(bound_pair, consumer_registry_view, consumer_registry_core_reference, metadata_contract_reference):
    require(type(bound_pair) is dict and bound_pair.get('schema') == 'COMPACT_IMPLEMENTATION_PAIR_BOUND_VIEW_V1'
        and bound_pair.get('family') == consumer_registry.FAMILY
        and bound_pair.get('protocol') == 'HOST_BOUND_COMPACT_IMPLEMENTATION_PAIR_V1', 'Previously inspected host pair view')
    require(type(consumer_registry_view) is dict and consumer_registry_view.get('schema') == consumer_registry.VIEW_SCHEMA
        and consumer_registry_view.get('family') == consumer_registry.FAMILY
        and consumer_registry_view.get('protocol') == consumer_registry.PROTOCOL, 'Previously inspected host consumer view')
    claims = {}
    for item in (bound_pair['binding_reference'], bound_pair['contract_reference'],
            bound_pair['publisher_reference'], bound_pair['independent_reader_reference'],
            consumer_registry_view['registry_reference'], consumer_registry_core_reference, metadata_contract_reference):
        references.reference(item, claims)
    require(consumer_registry_core_reference['sha256'] == CONSUMER_REGISTRY_KERNEL_SHA256, 'Fixed consumer registry kernel')
    _same(consumer_registry_view['implementation_pair_binding_reference'], bound_pair['binding_reference'], 'Same independently bound pair')
    _same(consumer_registry_view['ancestry_contract_reference'], bound_pair['contract_reference'], 'Same independently bound ancestry contract')
    consumers = consumer_registry_view['consumer_references']
    require(type(consumers) is dict and set(consumers) == set(ADAPTERS), 'Closed six previously inspected consumer roles')
    for item in consumers.values():
        references.reference(item, claims)
    return claims


def expected_consumer_metadata(*, consumer_role, bound_pair, consumer_registry_view,
        consumer_registry_core_reference, metadata_contract_reference):
    """Return exactly eight code-fixed metadata fields; no business dispatch IO."""
    require(type(consumer_role) is str and consumer_role in ADAPTERS, 'Code-fixed consumer role')
    _host_context(bound_pair, consumer_registry_view, consumer_registry_core_reference, metadata_contract_reference)
    return deepcopy(dict(continuation_adapter_schema=ADAPTERS[consumer_role], consumer_role=consumer_role,
        implementation_pair_binding_reference=bound_pair['binding_reference'],
        consumer_role_registry_reference=consumer_registry_view['registry_reference'],
        ancestry_contract_reference=bound_pair['contract_reference'],
        shared_ancestry_verifier_reference=bound_pair['independent_reader_reference'],
        consumer_registry_core_reference=consumer_registry_core_reference,
        consumer_metadata_contract_reference=metadata_contract_reference))


def inspect_consumer_metadata(value, *, expected_role, **host_context):
    """Check mandatory header fields; other wrapper fields remain IO obligations.

    A complete wrapper can be supplied without stripping metadata or changing
    its original schema. Unexpected wrapper fields are not authorized here.
    """
    expected = expected_consumer_metadata(consumer_role=expected_role, **host_context)
    require(type(value) is dict and all(key in value for key in METADATA_KEYS), 'Complete continuation metadata')
    _same({key: value[key] for key in METADATA_KEYS}, expected, 'Exact independently selected consumer metadata')
    return deepcopy(dict(schema=SCHEMA, metadata=expected,
        implementation_reference=host_context['consumer_registry_view']['consumer_references'][expected_role],
        namespace_files=list(NAMESPACE_FILES[expected_role]), **FLAGS))


def continuation_input_references(*, registered_dependency_references, consumer_role, **host_context):
    """Keep the original business dependency map and add separate host refs."""
    require(type(consumer_role) is str and consumer_role in REGISTERED_DEPENDENCY_ROLES, 'Producer public input role')
    require(type(registered_dependency_references) is dict and
        set(registered_dependency_references) == set(REGISTERED_DEPENDENCY_ROLES[consumer_role]), 'Original registered business dependency roles')
    claims = {}
    for value in registered_dependency_references.values():
        references.reference(value, claims)
    metadata = expected_consumer_metadata(consumer_role=consumer_role, **host_context)
    return deepcopy(dict(registration_dependency_references=registered_dependency_references,
        implementation_pair_binding=metadata['implementation_pair_binding_reference'],
        consumer_role_registry=metadata['consumer_role_registry_reference'], ancestry_contract=metadata['ancestry_contract_reference'],
        shared_ancestry_verifier=metadata['shared_ancestry_verifier_reference'],
        consumer_registry_core=metadata['consumer_registry_core_reference'],
        consumer_metadata_contract=metadata['consumer_metadata_contract_reference']))


def inspect_producer_input_references(value, *, consumer_role, registered_dependency_references, **host_context):
    """Associate runtime and original registration map; hosts close all fields."""
    expected = continuation_input_references(registered_dependency_references=registered_dependency_references,
        consumer_role=consumer_role, **host_context)
    require(type(value) is dict, 'Producer common input object')
    _same(value.get('dependencies'), registered_dependency_references, 'Unchanged registered business algorithms')
    _same(value.get('runtime'), host_context['consumer_registry_view']['consumer_references'][consumer_role], 'Known consumer runtime role')
    _same({key: value.get(key) for key in expected}, expected, 'Separate continuation input references')
    return deepcopy(expected)
