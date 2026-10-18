"""Pure V5 gap-run registration; host bindings confer no IO authority.

The registration binds a real V3/V4/V5 parent and capture by four immutable refs
each. Schema compatibility, bytes, clocks and prior-attempt inventory still
require the separate runtime and independent reader.
"""
from copy import deepcopy
import re
from backtest import ndx_compact_history_runtime_registration_research_v1 as references

SCHEMA = 'PROSPECTIVE_GAP_RUNTIME_REGISTRATION_V1'
PLAN_SCHEMA = 'PROSPECTIVE_GAP_RUNTIME_PLAN_V1'
REFERENCE_KERNEL_SHA256 = 'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23'
ANCHOR_ROLES = ('reference', 'publication_reference', 'readback_reference', 'reader_reference')
DEPENDENCY_ROLES = ('gap_core', 'parent_view', 'legacy_view', 'compact_helpers',
    'prefix_core', 'scoped', 'base', 'capture_checker')
FLAGS = dict(references.FLAGS, network_capture_performed=False, old_calendar_mutated=False,
    production_generator_authorized=False, seal_status_event_created=False)


def prepare_gap_runtime(*, registration, registration_reference,
        runtime_reference, dependency_references, research_root):
    """Return detached create-only bindings, never verified gap history.

    The caller supplies trusted host runtime/dependency references separately;
    registration claims cannot choose or replace those trusted bindings.
    """
    claims = {}
    references.reference(registration_reference, claims)
    references.reference(runtime_reference, claims)
    references.reference_roles(dependency_references, DEPENDENCY_ROLES, claims)
    root = references.canonical_path(research_root)
    references.require(type(registration) is dict and set(registration) == {
        'schema', 'runtime_reference', 'dependency_references', 'parent', 'capture',
        'output_directory', *FLAGS}, 'Exact gap registration fields')
    references.require(registration['schema'] == SCHEMA, 'Gap registration version')
    for flag in FLAGS:
        references.require(registration[flag] is False, 'Strict false authority flag ' + flag)
    references.require(registration['runtime_reference'] == runtime_reference, 'Host runtime binding')
    references.require(registration['dependency_references'] == dependency_references,
        'Host dependency bindings')
    for role in ('parent', 'capture'):
        references.reference_roles(registration[role], ANCHOR_ROLES, claims)
    output = references.canonical_path(registration['output_directory'])
    references.require(output.parent == root and output != root, 'Direct child of trusted research root')
    references.require(re.fullmatch(r'[a-z][a-z0-9_]{2,119}', output.name) is not None,
        'Explicit stable output namespace')
    for item in claims.values():
        source = references.canonical_path(item['path'])
        references.require(source != output and output not in source.parents,
            'Output aliases input namespace')
    return dict(schema=PLAN_SCHEMA, registration_reference=deepcopy(registration_reference),
        runtime_reference=deepcopy(runtime_reference), dependency_references=deepcopy(dependency_references),
        parent=deepcopy(registration['parent']), capture=deepcopy(registration['capture']),
        output_directory=str(output), source_reference_claims={
            item['path']: item['sha256'] for item in claims.values()},
        create_only=True, automatic_retry_allowed=False, registration_bytes_verified=False,
        source_bytes_verified=False, output_namespace_verified=False,
        parent_capture_schema_verified=False, prefix_artifact_bytes_verified=False, timing_classification_verified=False, **FLAGS)
