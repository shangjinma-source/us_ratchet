"""Hard-sealed 111-account reuse plus independent numerical audit of ten new rows."""
import argparse
from copy import deepcopy
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_historical_cross_k_accounts_independent_audit_20260923 as independent

SOURCE = Path(__file__).resolve()
BASE = independent.BASE / 'historical_cross_k_candidate_accounts_20260923_v1'
SEED = dict(path=str(BASE / 'completed_111_independent_audit.json'),
            sha256='9500b2e5bdbbf52a5b61503bbfe378e11c7096df52672b3f103bdf1a04501849')
FIT = dict(path=str(independent.BASE / 'historical_fourteen_cross_k_20260923_v1/completed_5001_independent_audit.json'),
           sha256='41f9be6511c1f21ddc8267f92f25db0a5c051620b48847c18bb97ca9aeb0fbfa')
INDEX = dict(path=str(BASE / 'tasks/index_ab66904de99fdf434cfa588f97ea54ea96956ecdb0c07f93e9b1eff40298255c.json'),
             sha256='931a12a52e9b2b95e054b684289f7b4faff6afc31d63558ea1943829dc971dce')
READER_SHA = '52bf9f7934605d9768bb71e0de18080bd9edcbff225f61f333f366f52e64a39d'
LOADED = dict(independent.LOADED)
independent.archive.merge(LOADED, {str(SOURCE): independent.hashlib.sha256(SOURCE.read_bytes()).hexdigest()})


def equal(left, right):
    return independent.exact(left, right)


def validate_prefix(seed, previous, current, fit, fit_index):
    if (seed['schema'] != 'HISTORICAL_CROSS_K_ACCOUNT_PREFIX_INDEPENDENT_AUDIT_V1'
            or type(seed['completed_account_task_count']) is not int
            or seed['completed_account_task_count'] != 111 or len(seed['details']) != 111
            or seed['raw_marker_result_chain_verified'] is not True
            or current['finalized_after_full_source_verification'] is not True
            or type(current['completed_account_task_count']) is not int
            or current['completed_account_task_count'] != 121 or len(current['entries']) != 121
            or previous['completed_account_task_count'] != 111 or len(previous['entries']) != 111
            or not equal(previous['entries'], current['entries'][:111])):
        raise ValueError('Exact sealed 111 prefix and finalized 121 denominator required')
    if (fit['schema'] != 'HISTORICAL_CROSS_K_COMPLETED_PREFIX_INDEPENDENT_AUDIT_V1'
            or fit['completed_new_count'] != 5001 or len(fit['details']) != 5001
            or fit['complete_marker_raw_checkpoint_chain_verified'] is not True
            or fit_index['completed_new_count'] != 5001 or len(fit_index['entries']) != 5001
            or fit_index['finalized_after_full_source_verification'] is not True):
        raise ValueError('Exact sealed 5001 independently audited fit authority required')
    if any(document['plan_reference'] != independent.PLAN for document in (seed, previous, current, fit, fit_index)):
        raise ValueError('Historical plan differs')
    if current['fit_prefix_audit_reference'] != FIT or previous['fit_prefix_audit_reference'] != seed['fit_prefix_audit_reference']:
        raise ValueError('Fit authority differs')
    identifiers = [row['task_id'] for row in fit['details']]
    if (len(set(identifiers)) != 5001 or identifiers != [row['task_id'] for row in fit_index['entries']]
            or [entry['task_id'] for entry in current['entries']] != identifiers[:121]
            or [detail['task_id'] for detail in seed['details']] != identifiers[:111]):
        raise ValueError('Unique ordered fit/account task linkage differs')
    for detail, entry in zip(seed['details'], previous['entries'], strict=True):
        for key in ('result_reference', 'raw_reference'):
            if detail[key] != entry[key]:
                raise ValueError('Sealed account detail and prefix artifact differ')
    for name, reference in (('shared_control_reference', independent.CONTROL),
                            ('shared_comparison_reference', independent.COMPARISON),
                            ('external_completed_account_reference', independent.EXTERNAL)):
        if seed[name] != reference:
            raise ValueError('Sealed benchmark or external authority differs')


def exact_closure(current, previous, previous_reference, auth_sources):
    required = dict(previous['historical_expected_source_hashes'])
    independent.archive.merge(required, {previous_reference['path']: previous_reference['sha256']})
    independent.archive.merge(required, auth_sources)
    for entry in current['entries'][111:]:
        for key in ('started_reference', 'raw_reference', 'result_reference'):
            reference = entry[key]
            if reference:
                independent.archive.merge(required, {reference['path']: reference['sha256']})
    if not equal(required, current['historical_expected_source_hashes']):
        raise ValueError('Incremental index has missing or unexplained source closure')


def build():
    if LOADED[str(Path(independent.__file__).resolve())] != READER_SHA:
        raise ValueError('Frozen independent inspector source differs')
    archive = independent.archive
    sources = dict(LOADED)
    seed = independent.read(SEED, sources)
    previous = independent.read(seed['index_reference'], sources)
    current = independent.read(INDEX, sources)
    fit = independent.read(FIT, sources)
    fit_index = independent.read(fit['index_reference'], sources)
    validate_prefix(seed, previous, current, fit, fit_index)
    contract = archive.load_contract()
    for document in (seed, fit):
        archive.merge(sources, document['historical_expected_source_hashes'])
    # One union byte verification; numerical work below is exclusively new rows.
    archive.merge(sources, current['historical_expected_source_hashes'])
    archive.verify_expected_sources(sources, contract)
    for document in (seed, previous, current, fit, fit_index):
        expected = independent.prefix.partition_subset(document['historical_expected_source_hashes'], contract)
        if not equal(expected, document['archive_resolution']):
            raise ValueError('Frozen source partition differs')
    plan = independent.read(independent.PLAN, sources)
    inputs = independent.read(independent.INPUT, sources)
    auth_sources = independent.runner_loaded_sources()
    for reference, document in ((independent.PLAN, plan), (independent.INPUT, inputs), (FIT, fit)):
        independent.read(reference, auth_sources)
        archive.merge(auth_sources, document['historical_expected_source_hashes'])
    independent.read(fit['index_reference'], auth_sources)
    queue = [dict(task_id=entry['task_id'], fit_checkpoint_reference=entry['result_reference'], detail=detail)
             for entry, detail in zip(fit_index['entries'], fit['details'], strict=True)]
    required = dict(auth_sources)
    independent.validate_index(current, queue, required)
    if Path(INDEX['path']).name != 'index_' + independent.digest(current) + '.json':
        raise ValueError('Final index digest address differs')
    exact_closure(current, previous, seed['index_reference'], auth_sources)
    if any(current['historical_expected_source_hashes'].get(path) != checksum for path, checksum in auth_sources.items()):
        raise ValueError('New fit authority missing from index')
    comparison = independent.read(independent.COMPARISON, sources)
    control = independent.read(independent.CONTROL, sources)
    if comparison['account_references']['incumbent'] != independent.CONTROL or comparison['account_references']['candidate'] != independent.EXTERNAL:
        raise ValueError('Shared comparison identity differs')
    nav_reference = comparison['nav_reference']
    nav_bytes = Path(nav_reference['path']).read_bytes()
    if independent.hashlib.sha256(nav_bytes).hexdigest() != nav_reference['sha256']:
        raise ValueError('Shared NAV bytes changed')
    archive.merge(sources, {nav_reference['path']: nav_reference['sha256']})
    tasks = {row['task_id']: dict(row['task'], task_id=row['task_id']) for row in plan['tasks']}
    results = deepcopy(seed['details'])
    for entry, row in zip(current['entries'][111:], queue[111:121], strict=True):
        documents = {kind: independent.read(entry[kind + '_reference'], sources)
                     if entry[kind + '_reference'] else None for kind in ('started', 'raw', 'result')}
        saved = documents['result']
        if saved['fit_prefix_audit_reference'] != FIT or saved['fit_checkpoint_reference'] != row['fit_checkpoint_reference']:
            raise ValueError('New account exact fit authority differs')
        checkpoint = independent.read(row['fit_checkpoint_reference'], sources)
        if not equal(checkpoint['task'], tasks[entry['task_id']]) or checkpoint['fit_performed'] is not True:
            raise ValueError('New account historical fit task differs')
        results.append(independent.inspect_entry(entry, documents, tasks[entry['task_id']], checkpoint['result'],
            row['detail'], FIT, auth_sources, inputs, plan['numerical_source_hashes'], control['execution'], nav_bytes.decode('utf-8-sig')))
    result = dict(schema='HISTORICAL_CROSS_K_ACCOUNT_PREFIX_INCREMENTAL_INDEPENDENT_AUDIT_V1',
        seed_audit_reference=SEED, index_reference=INDEX, fit_prefix_audit_reference=FIT, plan_reference=independent.PLAN,
        shared_control_reference=independent.CONTROL, shared_comparison_reference=independent.COMPARISON,
        external_completed_account_reference=independent.EXTERNAL, external_account_imported=False,
        audited_fit_task_count=5001, completed_account_task_count=121, pending_account_task_count=4880,
        reused_independent_account_count=111, newly_independently_audited_account_count=10,
        old_account_numerical_audit_repeated=False, old_fit_numerical_audit_repeated=False,
        skipped_risk_count=sum(row['status']=='SKIPPED_RISK' for row in results),
        executed_account_count=sum(row['status']!='SKIPPED_RISK' for row in results), details=results,
        raw_marker_result_chain_verified=True, write_order_independently_attested=False,
        producer_called=False, runner_called=False, engine_called=False, formal_dual_benchmark_admission=False,
        source_reuse_basis='HARD_EXTERNAL_AUDIT_SHA_EXACT_PREFIX_AND_FULL_BYTE_CLOSURE',
        historical_expected_source_hashes=sources, archive_resolution=archive.verify_expected_sources(sources, contract),
        **dict.fromkeys(independent.FALSE, False))
    return result


def publish_verified(path, value):
    # Repeat only the bounded ten-row independent audit, never the old 111 or 5001.
    if not equal(value, build()):
        raise ValueError('Incremental independent report rebuild differs')
    reference = independent.publish(path, value)
    if not equal(value['archive_resolution'], independent.archive.verify_expected_sources(
            value['historical_expected_source_hashes'], independent.archive.load_contract())):
        raise ValueError('Source drift after publication')
    return reference


def build_and_publish(path):
    """No external payload: build once, seal sources, publish and read back."""
    value = build()
    archive = independent.archive
    if not equal(value['archive_resolution'], archive.verify_expected_sources(
            value['historical_expected_source_hashes'], archive.load_contract())):
        raise ValueError('Source drift before publication')
    reference = independent.publish(path, value)
    readback_sources = {}
    if not equal(value, independent.read(reference, readback_sources)):
        raise ValueError('Published incremental report readback differs')
    if not equal(value['archive_resolution'], archive.verify_expected_sources(
            value['historical_expected_source_hashes'], archive.load_contract())):
        raise ValueError('Source drift after publication')
    return reference


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    print(json.dumps(build_and_publish(arguments.output)))
