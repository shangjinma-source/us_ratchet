"""Inspect a host-selected implementation pair without IO or approval claims.

The host must select the binding path AND digest independently of daily input.
Neither implementation embeds its peer or this binding's digest. This module
checks declarations only; the IO host must verify every referenced byte string.
"""
from copy import deepcopy

from backtest import ndx_compact_history_runtime_registration_research_v1 as references

REFERENCE_KERNEL_SHA256 = "d0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23"
SCHEMA = "COMPACT_IMPLEMENTATION_PAIR_BINDING_V1"
VIEW_SCHEMA = "COMPACT_IMPLEMENTATION_PAIR_BOUND_VIEW_V1"
FAMILY = "NDX_RESEARCH_COMPACT_ACTUAL_V4"
PROTOCOL = "HOST_BOUND_COMPACT_IMPLEMENTATION_PAIR_V1"
ROLE = "IMMUTABLE_IMPLEMENTATION_PAIR_DECLARATION_NOT_AUTHORITY"
PUBLISHER_DEPENDENCY_ROLES = ("history_core", "parent_view", "legacy_view",
    "compact_helpers", "capture_checker", "observation_reader", "csv_reader",
    "independent_prefix")
READER_DEPENDENCY_ROLES = ("history_reconstructor", "legacy_history_reconstructor",
    "parent_view", "legacy_view", "compact_helpers", "capture_checker",
    "observation_reader", "csv_reader", "independent_prefix",
    "independent_gap_reconstructor")
DEPENDENCY_ROLES = {"publisher": PUBLISHER_DEPENDENCY_ROLES,
    "independent_reader": READER_DEPENDENCY_ROLES}
MAX_LEGACY_BINDINGS = 128
FLAGS = dict(references.FLAGS, binding_bytes_verified=False,
    peer_source_bytes_verified=False, contract_source_bytes_verified=False,
    root_approval_authenticated=False, filesystem_verified=False,
    implementation_pair_approval_authenticated=False)
require = references.require


def inspect_pair_binding(*, binding, binding_reference, host_binding_reference,
        self_role, self_reference, expected_contract_reference,
        expected_algorithm_dependencies, approved_legacy_binding_references=()):
    """Return detached declarations matching separately supplied host anchors.

    A caller controlling the host anchor can select another pair. Structural
    agreement cannot establish Root approval, authenticity, or filesystem state.
    The legacy list is flat and host-selected; it never discovers trusted peers.
    """
    claims = {}

    def ref(value):
        path = references.canonical_path(value.get("path") if type(value) is dict else None)
        key = str(path).casefold()
        require(key not in claims or claims[key] == value, "No path spelling aliases")
        references.reference(value, claims)
        return key, value["sha256"]

    require(type(self_role) is str and self_role in DEPENDENCY_ROLES, "Exact self role")
    host_identity = ref(host_binding_reference)
    ref(binding_reference)
    require(binding_reference == host_binding_reference, "Independently selected host binding")
    contract_identity = ref(expected_contract_reference)
    ref(self_reference)
    require(type(expected_algorithm_dependencies) is dict and
        set(expected_algorithm_dependencies) == set(DEPENDENCY_ROLES), "Exact algorithm pair roles")
    for role, roles in DEPENDENCY_ROLES.items():
        dependencies = expected_algorithm_dependencies[role]
        require(type(dependencies) is dict and set(dependencies) == set(roles),
            "Complete closed algorithm dependencies " + role)
        for value in dependencies.values():
            ref(value)
    require(type(approved_legacy_binding_references) in (tuple, list) and
        len(approved_legacy_binding_references) <= MAX_LEGACY_BINDINGS, "Bounded flat host legacy list")
    legacy_identities = [ref(value) for value in approved_legacy_binding_references]
    require(len({item[0] for item in legacy_identities}) == len(legacy_identities) and
        len({item[1] for item in legacy_identities}) == len(legacy_identities), "Unique legacy bindings")
    keys = {"schema", "family", "protocol", "role", "publisher_reference",
        "independent_reader_reference", "contract_reference", "publisher_dependency_references",
        "reader_dependency_references", "approved_legacy_binding_references", *FLAGS}
    require(type(binding) is dict and set(binding) == keys, "Exact binding fields")
    for key, expected in (("schema", SCHEMA), ("family", FAMILY),
            ("protocol", PROTOCOL), ("role", ROLE)):
        require(type(binding[key]) is str and binding[key] == expected, "Binding " + key)
    for key in FLAGS:
        require(binding[key] is False, "Strict false " + key)
    publisher_identity = ref(binding["publisher_reference"])
    reader_identity = ref(binding["independent_reader_reference"])
    ref(binding["contract_reference"])
    require(binding["contract_reference"] == expected_contract_reference, "Host contract binding")
    for role, field in (("publisher", "publisher_dependency_references"),
            ("independent_reader", "reader_dependency_references")):
        require(binding[field] == expected_algorithm_dependencies[role], "Host algorithm bindings " + role)
    require(type(binding["approved_legacy_binding_references"]) is list and
        binding["approved_legacy_binding_references"] == list(approved_legacy_binding_references),
        "Host-selected legacy bindings only")
    role_field = "publisher_reference" if self_role == "publisher" else "independent_reader_reference"
    require(self_reference == binding[role_field], "Self matches exact pair role")
    special = [host_identity, contract_identity, publisher_identity, reader_identity, *legacy_identities]
    require(len({item[0] for item in special}) == len(special) and
        len({item[1] for item in special}) == len(special), "Distinct binding, contract, peers and predecessors")
    for dependencies in expected_algorithm_dependencies.values():
        for value in dependencies.values():
            identity = ref(value)
            require(all(identity[0] != item[0] and identity[1] != item[1] for item in special),
                "Algorithm cannot depend on pair, binding or predecessor bytes")
    return deepcopy(dict(schema=VIEW_SCHEMA, family=FAMILY, protocol=PROTOCOL,
        binding_reference=host_binding_reference, contract_reference=expected_contract_reference,
        publisher_reference=binding["publisher_reference"],
        independent_reader_reference=binding["independent_reader_reference"],
        algorithm_dependency_references=expected_algorithm_dependencies,
        approved_legacy_binding_references=list(approved_legacy_binding_references),
        self_role=self_role, self_reference=self_reference,
        source_reference_claims={value["path"]: value["sha256"] for value in claims.values()},
        **FLAGS))
