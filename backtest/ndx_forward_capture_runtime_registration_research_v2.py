"""Pure V5-chain capture registration; distinct from the frozen V1 contract.

Trusted host runtime, six dependencies and research root are separate inputs.
This plan authenticates no files, parent format, suffix inventory or clocks.
"""
from copy import deepcopy
import re
from backtest import ndx_compact_history_runtime_registration_research_v1 as references

SCHEMA = 'FORWARD_CAPTURE_RUNTIME_REGISTRATION_V2'
PLAN_SCHEMA = 'FORWARD_CAPTURE_RUNTIME_PLAN_V2'
REFERENCE_KERNEL_SHA256 = 'd0d9241b737e41a1339bb5c3fe9ef0418c99bd4b8db5856c2e603b5e641f3b23'
PARENT_ROLES = ('reference', 'publication_reference', 'readback_reference', 'reader_reference')
DEPENDENCY_ROLES = ('capture_core', 'parent_view', 'legacy_view', 'compact_helpers', 'scoped', 'base')
FLAGS = dict(references.FLAGS, network_capture_performed=False, old_calendar_mutated=False)


def prepare_forward_capture_runtime(*, registration, registration_reference,
        runtime_reference, dependency_references, research_root):
    """Return detached create-only bindings without consuming saved evidence."""
    claims = {}
    references.reference(registration_reference, claims)
    references.reference(runtime_reference, claims)
    references.reference_roles(dependency_references, DEPENDENCY_ROLES, claims)
    root = references.canonical_path(research_root)
    references.require(type(registration) is dict and set(registration) == {
        'schema', 'runtime_reference', 'dependency_references', 'parent', 'output_directory', *FLAGS},
        'Exact forward capture V2 registration fields')
    references.require(registration['schema'] == SCHEMA, 'Forward capture V2 registration version')
    for flag in FLAGS:
        references.require(registration[flag] is False, 'Strict false authority flag ' + flag)
    references.require(registration['runtime_reference'] == runtime_reference, 'Host runtime binding')
    references.require(registration['dependency_references'] == dependency_references, 'Host dependency bindings')
    references.reference_roles(registration['parent'], PARENT_ROLES, claims)
    output = references.canonical_path(registration['output_directory'])
    references.require(output.parent == root and output != root, 'Direct child of trusted research root')
    references.require(re.fullmatch(r'[a-z][a-z0-9_]{2,119}', output.name) is not None,
        'Explicit stable output namespace')
    for item in claims.values():
        source = references.canonical_path(item['path'])
        references.require(source != output and output not in source.parents, 'Output aliases input namespace')
    return dict(schema=PLAN_SCHEMA, registration_reference=deepcopy(registration_reference),
        runtime_reference=deepcopy(runtime_reference), dependency_references=deepcopy(dependency_references),
        parent=deepcopy(registration['parent']), output_directory=str(output),
        source_reference_claims={item['path']: item['sha256'] for item in claims.values()},
        create_only=True, automatic_retry_allowed=False, registration_bytes_verified=False,
        source_bytes_verified=False, output_namespace_verified=False, parent_schema_verified=False,
        capture_reads_host_configured_local_caches_only=True, **FLAGS)
