"""Extend the sealed 101-account inventory without re-auditing its ledgers."""
import argparse
from copy import deepcopy
from pathlib import Path
import json
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from scripts import ndx_historical_cross_k_economic_summary_20260923 as base

SEED = dict(path=str(base.AUDIT.parent / 'economic_summary_101.json'),
            sha256='1dd13d6bfabe6a5d69ede5e0b4dd0436fc29d40d1495dad1fc1855dabc4dc24c')
SOURCE = Path(__file__).resolve()
LOADED = dict(base.LOADED, **{str(SOURCE): base.sha(SOURCE)})
AUTHORIZED_AUDITS = {
    str(base.AUDIT.parent / 'completed_111_independent_audit.json'):
        ('9500b2e5bdbbf52a5b61503bbfe378e11c7096df52672b3f103bdf1a04501849', 111),
}


def same(left, right):
    return base.canonical(left) == base.canonical(right)


def validate_extension(seed, previous, audit, index):
    """Require a monotone extension of the independently authenticated prefix."""
    count = audit['completed_account_task_count']
    if (type(count) is not int or not 101 < count <= 31827
            or audit['schema'] != 'HISTORICAL_CROSS_K_ACCOUNT_PREFIX_INDEPENDENT_AUDIT_V1'
            or audit['raw_marker_result_chain_verified'] is not True
            or index['finalized_after_full_source_verification'] is not True
            or type(index['completed_account_task_count']) is not int
            or index['completed_account_task_count'] != count
            or len(audit['details']) != count or len(index['entries']) != count):
        raise ValueError('Complete independently audited extension required')
    if (seed['completed_account_count'] != 101 or len(seed['rows']) != 101
            or not same(seed['audit_reference'], dict(path=str(base.AUDIT), sha256=base.AUDIT_SHA))
            or not same(audit['details'][:101], previous['details'])):
        raise ValueError('Sealed 101-account prefix differs')
    for key in ('plan_reference', 'shared_control_reference', 'shared_comparison_reference',
                'external_completed_account_reference'):
        if not same(audit[key], previous[key]):
            raise ValueError('Historical scope or shared reference differs')
    for key in ('engine_called', 'fit_performed', 'point_in_time_verified',
                'promotion_allowed', 'formal_dual_benchmark_admission', 'external_account_imported'):
        if audit[key] is not False:
            raise ValueError('Independent audit boundary upgraded')
    identifiers = [detail['task_id'] for detail in audit['details']]
    if (len(set(identifiers)) != count
            or identifiers != [entry['task_id'] for entry in index['entries']]
            or identifiers[:101] != [row['task_id'] for row in seed['rows']]
            or not same(index['plan_reference'], audit['plan_reference'])
            or not same(index['fit_prefix_audit_reference'], audit['fit_prefix_audit_reference'])):
        raise ValueError('Complete ordered task linkage required')
    for entry, detail in zip(index['entries'], audit['details'], strict=True):
        for key in ('result_reference', 'raw_reference'):
            if not same(entry[key], detail[key]):
                raise ValueError('Index and independent result linkage differs')
    return count


def build(audit_path, audit_sha256):
    authority = AUTHORIZED_AUDITS.get(str(Path(audit_path).resolve()))
    if authority is None or audit_sha256 != authority[0]:
        raise ValueError('Externally reviewed independent audit authority required')
    sources = dict(LOADED)
    seed = base.read(SEED, sources)
    previous = base.read(seed['audit_reference'], sources)
    reference = dict(path=str(Path(audit_path).resolve()), sha256=audit_sha256)
    audit = base.read(reference, sources)
    index = base.read(audit['index_reference'], sources)
    count = validate_extension(seed, previous, audit, index)
    if count != authority[1]:
        raise ValueError('Externally reviewed account denominator differs')
    contract = base.archive.load_contract()
    for document in (seed, audit):
        if not same(base.archive.verify_expected_sources(document['historical_expected_source_hashes'], contract), document['archive_resolution']):
            raise ValueError('Authenticated source partition differs')
        base.archive.merge(sources, document['historical_expected_source_hashes'])
    if any(audit['historical_expected_source_hashes'].get(path) != checksum
           for path, checksum in index['historical_expected_source_hashes'].items()):
        raise ValueError('Final index source missing from independent audit')
    rows = deepcopy(seed['rows'])
    for entry, detail in zip(index['entries'][101:], audit['details'][101:], strict=True):
        saved = base.read(detail['result_reference'], sources)
        raw = base.read(detail['raw_reference'], sources) if detail['raw_reference'] else None
        base.read(entry['started_reference'], sources)
        if not same(saved['started_reference'], entry['started_reference']):
            raise ValueError('New account marker linkage differs')
        if any(audit['historical_expected_source_hashes'].get(path) != checksum
               for path, checksum in saved['historical_expected_source_hashes'].items()):
            raise ValueError('New account closure missing from independent audit')
        rows.append(base.summarize_detail(detail, saved, raw))
    result = base.aggregate(rows, count)
    return dict(result, schema='HISTORICAL_CROSS_K_INCREMENTAL_ECONOMIC_SUMMARY_V1',
                seed_summary_reference=SEED, reused_summary_row_count=101,
                newly_summarized_row_count=count - 101, audit_reference=reference,
                index_reference=audit['index_reference'], plan_reference=audit['plan_reference'],
                summarized_new_account_count=count, unsummarized_new_account_count=31827-count,
                historical_plan_canonical_task_count=31828, new_historical_fit_task_count=31827,
                shared_control_reference=audit['shared_control_reference'],
                shared_comparison_reference=audit['shared_comparison_reference'],
                external_mechanical_account_reference=audit['external_completed_account_reference'],
                scope=seed['scope'], nav_currency_policy=seed['nav_currency_policy'],
                historical_expected_source_hashes=sources,
                archive_resolution=base.archive.verify_expected_sources(sources, contract))


def publish_verified(path, value):
    reference = value['audit_reference']
    if not same(value, build(reference['path'], reference['sha256'])):
        raise ValueError('Complete incremental inventory differs')
    saved = base.publish(path, value)
    if not same(base.archive.verify_expected_sources(value['historical_expected_source_hashes'], base.archive.load_contract()), value['archive_resolution']):
        raise ValueError('Source partition changed after publication')
    return saved


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--audit-path', required=True)
    parser.add_argument('--audit-sha256', required=True)
    parser.add_argument('--output', required=True)
    arguments = parser.parse_args()
    print(json.dumps(publish_verified(arguments.output, build(arguments.audit_path, arguments.audit_sha256))))
