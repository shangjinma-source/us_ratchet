"""Corrected full-date economic competition with explicit archived source resolution."""
import argparse
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_corrected_complete_date_frontier_research as core
from backtest import ndx_root_price_archive_contract_research as archive
from scripts import ndx_selected_date_archive_overlay_research as reader
from scripts import ndx_selected_date_archive_diff_research as independent_diff

SOURCE=Path(__file__).resolve()
LOADED={str(SOURCE):archive.drift.file_sha(SOURCE)}
for mapping in (core.LOADED,reader.LOADED,independent_diff.LOADED):archive.merge(LOADED,mapping)
FLAGS=('historical_full_source_closure_verified','point_in_time_verified','promotion_allowed','selection_performed',
       'training_performed','execution_performed','full_ndx_pool_coverage_verified','original_live_price_paths_verified',
       'original_strict_source_verification_passed','historical_minimum_single_weight_verified')


def validate_diff(report,*,date,complete_path,complete_sha256,parent,complete):
    path=str(Path(complete_path).resolve())
    if (report.get('schema')!=independent_diff.SCHEMA or report.get('date')!=date
        or report.get('output_path')!=path or report.get('output_sha256')!=complete_sha256
        or report.get('historical_expected_source_hashes',{}).get(path)!=complete_sha256):
        raise ValueError('Exact independently audited archive output required')
    expected=dict(original_count=parent['original_count'],selected_replaced=parent['pending_count'],unrelated_records_exact=parent['available_count'])
    if any(type(report.get(k)) is not int or report[k]!=v for k,v in expected.items()):raise ValueError('Full date diff denominator differs')
    if any(report.get(k) is not True for k in ('whole_date_task_map_verified','ordered_full_record_diff_verified','full_new_results_match_external_checkpoints','output_source_partitions_reverified')):
        raise ValueError('Complete independent ordered diff required')
    reader.independent.require_false(report,independent_diff.FLAGS)
    if complete.get('input_artifact_binding_verified') is not True or complete.get('source_resolution_schema')!=reader.RESOLUTION_SCHEMA:
        raise ValueError('Source-bound archive complete date required')
    if any(report['historical_expected_source_hashes'].get(p)!=h for p,h in independent_diff.LOADED.items()):
        raise ValueError('Independent diff code closure omitted')


def verify(report):
    if (report.get('schema')!='CORRECTED_COMPLETE_DATE_CROSS_K_FRONTIER_V1'
        or report.get('source_resolution_schema')!=reader.RESOLUTION_SCHEMA
        or 'verified_source_hashes' in report or 'historical_price_cache_gap_observations' in report):
        raise ValueError('Explicit new archive resolution required')
    reader.independent.require_false(report,FLAGS)
    sources=report['historical_expected_source_hashes']
    if any(sources.get(p)!=h for p,h in LOADED.items()):raise ValueError('Loaded frontier source missing')
    checked=archive.verify_expected_sources(sources,archive.load_contract())
    if not reader.independent.exact(checked,report['archive_resolution']):raise ValueError('Archive partition differs')
    if len(checked['archive_resolutions'])!=85 or len(checked['historical_gap_observations'])!=26:raise ValueError('Exact archive denominator required')
    reader.independent.verify_gaps(report['historical_loader_gap_observations'])


def build(*,date,complete_path,complete_sha256,diff_path,diff_sha256):
    sources=dict(LOADED)
    def read(path,sha):
        path=Path(path).resolve();raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External artifact SHA differs')
        archive.merge(sources,{str(path):sha});return json.loads(raw)
    inventory=read(reader.INVENTORY,reader.INVENTORY_SHA)
    descriptor,=[r for r in inventory['dates'] if r['date']==date.replace('-','')]
    parent=read(descriptor['overlay_path'],descriptor['overlay_sha256'])
    complete=read(complete_path,complete_sha256);audit=read(diff_path,diff_sha256)
    if (complete['parent_overlay_path']!=descriptor['overlay_path'] or complete['parent_overlay_sha256']!=descriptor['overlay_sha256']
        or complete['coordinate']['selection_date']!=date):raise ValueError('Complete date parent differs')
    validate_diff(audit,date=date,complete_path=complete_path,complete_sha256=complete_sha256,parent=parent,complete=complete)
    reader.verify(complete);independent_diff.verify(audit)
    archive.merge(sources,complete['historical_expected_source_hashes']);archive.merge(sources,audit['historical_expected_source_hashes'])
    contract=archive.load_contract();archive.verify_expected_sources(sources,contract)
    refs=[(p,h) for p,h in sources.items() if Path(p).name=='equal_base_'+date.replace('-','')+'_20260911.json']
    if len(refs)!=1:raise ValueError('One bound original equal semantics artifact required')
    equal=read(*refs[0])
    if equal['coordinate']!=parent['coordinate']:raise ValueError('Original semantics date differs')
    delta_contracts={};contexts={}
    for record in parent['records']:
        if record['origin']!='DELTA':continue
        lineage=record['lineage'];checkpoint_path=lineage['original_checkpoint_path']
        if sources.get(checkpoint_path)!=lineage['original_checkpoint_sha256']:raise ValueError('Original DELTA checkpoint not bound')
        context_path=str(Path(checkpoint_path).parent/'context.json')
        if context_path not in sources:raise ValueError('Original DELTA context not bound')
        if context_path not in contexts:
            context=read(context_path,sources[context_path])
            contexts[context_path]=(reader.independent.scalar.decode(context['prepared_inputs']['contract']['payload']),{core.digest(t) for t in context['tasks']})
        parameters,tasks=contexts[context_path]
        if core.digest(record['task']) not in tasks:raise ValueError('Original DELTA task absent')
        delta_contracts[record['task']['job_id']]=parameters
    result=core.analyze_complete_corrected_date(complete_overlay=complete,original_parent=parent,original_training_semantics=equal['training_semantics'],delta_contracts=delta_contracts)
    archive.merge(sources,result.pop('source_hashes'))
    coordinate=dict(schema='CORRECTED_COMPLETE_COHORT_NUMERICAL_COORDINATE_V1',original_training_contract_sha256=result['original_training_contract_reference_sha256'],
        corrected_records_sha256=complete['records_sha256'],correction_signatures=sorted({r['correction_signature'] for r in complete['records']}),
        complete_overlay_path=str(Path(complete_path).resolve()),complete_overlay_sha256=complete_sha256)
    result.update(source_resolution_schema=reader.RESOLUTION_SCHEMA,archive_resolution=archive.verify_expected_sources(sources,contract),
        historical_expected_source_hashes=sources,input_artifact_binding_verified=True,original_source_hashes_verified_here=False,
        corrected_numerical_coordinate=coordinate,corrected_numerical_coordinate_sha256=core.digest(coordinate),
        complete_date_artifact=dict(path=str(Path(complete_path).resolve()),sha256=complete_sha256),
        independent_full_diff_artifact=dict(path=str(Path(diff_path).resolve()),sha256=diff_sha256),
        historical_loader_gap_observations=complete['historical_loader_gap_observations'],
        original_live_price_paths_verified=False,original_strict_source_verification_passed=False,historical_minimum_single_weight_verified=False,
        saved_non20_fields_independently_recomputed=False,binary_float_ledger_hash_independently_verified=False)
    reader.verify(complete);independent_diff.verify(audit);verify(result)
    return result


def publish(path,result):
    verify(result);saved=reader.publish(path,result);verify(result);return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('date','complete-path','complete-sha256','diff-path','diff-sha256','output'):parser.add_argument('--'+name,required=True)
    args=vars(parser.parse_args());output=args.pop('output');print(json.dumps(publish(output,build(**args))))
