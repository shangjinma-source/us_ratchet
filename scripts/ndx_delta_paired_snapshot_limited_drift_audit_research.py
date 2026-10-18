"""All-614 typed scalar audit with the exact, still-unresolved 26-file drift."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
from types import FunctionType
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_exact_price_cache_drift_research as drift
from scripts import ndx_delta_paired_snapshot_full_independent_audit as strict
SOURCE=Path(__file__).resolve()
LOADED={str(p):hashlib.sha256(p.read_bytes()).hexdigest() for p in (SOURCE,Path(strict.__file__).resolve(),drift.SOURCE,Path(strict.scalar.__file__).resolve())}
INDEX=ROOT/'data/cache/research/delta_paired_snapshot_20260912_v1/tasks/index_a1a78475e53cb9b2339f839f72f3310ce4c4c1c871406ef384f183d0c599e1b4.json'
INDEX_SHA='6c27c7be1a31d94bbf6052d5c24f58b185abfff04ab0275fc485214dcd66da8c'


def check_config_observations(gaps):
    for gap in gaps:
        if drift.file_sha(gap['path'])!=gap['observed_current_sha256']:
            raise ValueError('Declared historical config observation changed')


def audit_limited(*,index_path,index_sha256):
    if str(Path(index_path).resolve())!=str(INDEX) or index_sha256!=INDEX_SHA:
        raise ValueError('Only the externally diagnosed complete614 index is authorized')
    contract=drift.load_contract()
    def bounded_verify(sources,gaps):
        for p,h in LOADED.items():
            if drift.file_sha(p)!=h:raise ValueError('Loaded audit source changed')
        drift.verify_expected_sources(sources,contract)
        check_config_observations(gaps)
    # Only verification is replaced privately; all strict task/target/scalar
    # assertions run unchanged, and the original function/global stay intact.
    globals_copy=dict(strict.audit_complete.__globals__,verify_sources_and_gaps=bounded_verify)
    audit=FunctionType(strict.audit_complete.__code__,globals_copy,strict.audit_complete.__name__,strict.audit_complete.__defaults__,strict.audit_complete.__closure__)
    original=audit(index_path,index_sha256)
    expected=original.pop('source_hashes')
    for p,h in LOADED.items():
        if p in expected and expected[p]!=h:raise ValueError('Conflicting audit source identity')
        expected[p]=h
    verification=drift.verify_expected_sources(expected,contract)
    if len(verification['historical_gap_observations'])!=26:
        raise ValueError('Complete recorded 26-file gap set required')
    check_config_observations([row['gap'] for row in original['tasks']])
    original.update(schema='ndx_delta_paired_snapshot_limited_drift_independent_audit_v1',
        verified_source_hashes=verification['verified_source_hashes'],historical_expected_source_hashes=expected,
        historical_price_cache_gap_observations=verification['historical_gap_observations'],
        historical_full_source_closure_verified=False,strict_no_gap_audit_passed=False,
        complete_task_lineage_verified=True,all_windows_independently_recomputed=True,
        nominal_execution_independently_replayed=False,
        numerical_scope='HARD_TYPED_INPUTS_ALL614_OLD_FULL_RESULT_MATCH_AND_FRACTIONAL_SCALARS_WITH_EXACT_PRICE_CACHE_GAPS',
        exception_authority=dict(path=str(drift.REPORT),sha256=drift.REPORT_SHA),
        original_historical_provenance_verified=False,point_in_time_verified=False,promotion_allowed=False)
    return original


def publish_limited(output,report):
    if report['schema']!='ndx_delta_paired_snapshot_limited_drift_independent_audit_v1':raise ValueError('Limited audit schema required')
    contract=drift.load_contract()
    def verify():
        result=drift.verify_expected_sources(report['historical_expected_source_hashes'],contract)
        if result['verified_source_hashes']!=report['verified_source_hashes'] or result['historical_gap_observations']!=report['historical_price_cache_gap_observations']:
            raise ValueError('Audit source partition changed')
        check_config_observations([row['gap'] for row in report['tasks']])
    verify()
    with Path(output).open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True);stream.write('\n')
    verify()
    return dict(path=str(Path(output).resolve()),sha256=drift.file_sha(output))


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--index-path',required=True);parser.add_argument('--index-sha256',required=True);parser.add_argument('--output',required=True)
    args=parser.parse_args()
    if Path(args.output).exists():raise FileExistsError('Limited audit already exists')
    report=audit_limited(index_path=args.index_path,index_sha256=args.index_sha256)
    print(json.dumps(publish_limited(args.output,report)))
