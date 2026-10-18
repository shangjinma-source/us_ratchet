"""Pure host-selected consumer roles, independent of the compact pair binding.

The registry binds implementation bytes after all sources are frozen. It never
chooses append algorithms, grants authority, reads files or invokes a consumer.
The host supplies its expected registry hash independently of daily artifacts.
"""
from copy import deepcopy
from backtest import ndx_compact_history_runtime_registration_research_v1 as references


REFERENCE_KERNEL_SHA256 = 'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23'
SCHEMA = 'COMPACT_CONTINUATION_CONSUMER_ROLE_REGISTRY_V1'
VIEW_SCHEMA = 'COMPACT_CONTINUATION_CONSUMER_ROLE_VIEW_V1'
FAMILY = 'NDX_RESEARCH_COMPACT_ACTUAL_V4'
PROTOCOL = 'HOST_BOUND_CONTINUATION_CONSUMER_ROLES_V1'
ROLE = 'IMPLEMENTATION_ROLE_DECLARATIONS_NOT_AUTHORITY'
CONSUMER_ROLES = ('capture_publisher', 'capture_independent_reader', 'observation_writer',
    'observation_independent_reader', 'gap_publisher', 'gap_independent_reader')
FLAGS = dict(references.FLAGS, registry_bytes_verified=False, consumer_source_bytes_verified=False,
    implementation_pair_approval_authenticated=False, root_approval_authenticated=False,
    filesystem_verified=False, full_transitive_source_closure_reverified=False)
require = references.require


def inspect_consumer_roles(*, registry, registry_reference, host_registry_reference,
        bound_pair, self_role=None, self_reference=None):
    """Return exact detached roles associated with an already host-bound pair.

    ``bound_pair`` is produced by the separately validated pair-binding kernel.
    This function checks associations, not pair or registry byte authenticity.
    It cannot establish human approval if the caller controls the host inputs.
    Consumer schema/adapter dispatch remains fixed in each IO implementation;
    registry data cannot supply code, callbacks, schemas or algorithm overrides.
    """
    claims = {}

    def ref(value):
        path = references.canonical_path(value.get('path') if type(value) is dict else None)
        key = str(path).casefold()
        require(key not in claims or claims[key] == value, 'No path spelling aliases')
        references.reference(value, claims)
        return key, value['sha256']

    host = ref(host_registry_reference)
    ref(registry_reference)
    require(registry_reference == host_registry_reference, 'Independent host registry selection')
    require(type(bound_pair) is dict and bound_pair.get('schema') == 'COMPACT_IMPLEMENTATION_PAIR_BOUND_VIEW_V1'
        and bound_pair.get('family') == FAMILY
        and bound_pair.get('protocol') == 'HOST_BOUND_COMPACT_IMPLEMENTATION_PAIR_V1',
        'Explicit previously inspected pair view')
    pair = ref(bound_pair.get('binding_reference'))
    contract = ref(bound_pair.get('contract_reference'))
    publisher = ref(bound_pair.get('publisher_reference'))
    reader = ref(bound_pair.get('independent_reader_reference'))
    keys = {'schema', 'family', 'protocol', 'role', 'implementation_pair_binding_reference',
        'ancestry_contract_reference', 'consumer_references', *FLAGS}
    require(type(registry) is dict and set(registry) == keys, 'Exact consumer registry fields')
    for key, expected in (('schema', SCHEMA), ('family', FAMILY), ('protocol', PROTOCOL), ('role', ROLE)):
        require(type(registry[key]) is str and registry[key] == expected, 'Consumer registry ' + key)
    for key in FLAGS:
        require(registry[key] is False, 'Strict false ' + key)
    ref(registry['implementation_pair_binding_reference'])
    ref(registry['ancestry_contract_reference'])
    require(registry['implementation_pair_binding_reference'] == bound_pair['binding_reference'], 'Same host-selected pair binding')
    require(registry['ancestry_contract_reference'] == bound_pair['contract_reference'], 'Same host-selected ancestry contract')
    consumers = registry['consumer_references']
    require(type(consumers) is dict and set(consumers) == set(CONSUMER_ROLES), 'Closed six consumer roles')
    identities = [host, pair, contract, publisher, reader]
    identities.extend(ref(consumers[role]) for role in CONSUMER_ROLES)
    require(len({item[0] for item in identities}) == len(identities)
        and len({item[1] for item in identities}) == len(identities), 'Distinct registry, pair, contract and implementation roles')
    require((self_role is None) == (self_reference is None), 'Complete optional consumer self association')
    if self_role is not None:
        require(type(self_role) is str and self_role in CONSUMER_ROLES, 'Known consumer self role')
        ref(self_reference)
        require(self_reference == consumers[self_role], 'Exact consumer self role')
    # An implementation-role file must not masquerade as a fixed algorithm.
    # Algorithms retain their separately reviewed pair bindings and cannot be
    # changed, added or selected by this registry.
    algorithms = bound_pair.get('algorithm_dependency_references')
    require(type(algorithms) is dict and set(algorithms) == {'publisher', 'independent_reader'}, 'Pair algorithm role maps')
    for dependencies in algorithms.values():
        require(type(dependencies) is dict and dependencies, 'Previously bound algorithm dependencies')
        for value in dependencies.values():
            identity = ref(value)
            require(all(identity[0] != item[0] and identity[1] != item[1] for item in identities),
                'Consumer registry cannot replace a fixed algorithm role')
    return deepcopy(dict(schema=VIEW_SCHEMA, family=FAMILY, protocol=PROTOCOL,
        registry_reference=host_registry_reference,
        implementation_pair_binding_reference=bound_pair['binding_reference'],
        ancestry_contract_reference=bound_pair['contract_reference'], consumer_references=consumers,
        self_role=self_role, self_reference=self_reference,
        source_reference_claims={value['path']: value['sha256'] for value in claims.values()},
        consumer_schema_dispatch_selected_by_registry=False, append_algorithm_called=False,
        **FLAGS))
