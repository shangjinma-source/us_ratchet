"""Consume one externally reviewed complete corrected date and its independent diff."""
import argparse,hashlib,json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_corrected_complete_date_frontier_research as core
from scripts import ndx_selected_date_overlay_research as reader
from scripts import ndx_selected_date_overlay_diff_research as independent_diff
SOURCE=Path(__file__).resolve()
LOADED={str(SOURCE):reader.drift.file_sha(SOURCE),**core.LOADED,**reader.LOADED,**independent_diff.LOADED}


def validate_diff(report,*,date,complete_path,complete_sha256,parent,complete):
    if (report.get('schema')!='SELECTED_COMPLETE_DATE_INDEPENDENT_ORDERED_DIFF_V1' or report.get('date')!=date
        or report.get('output_path')!=str(Path(complete_path).resolve()) or report.get('output_sha256')!=complete_sha256
        or report.get('source_hashes',{}).get(str(Path(complete_path).resolve()))!=complete_sha256):raise ValueError('Exact independently diff-audited output required')
    expected=dict(original_count=parent['original_count'],selected_replaced=parent['pending_count'],unrelated_records_exact=parent['available_count'])
    if any(type(report.get(k)) is not int or report[k]!=v for k,v in expected.items()):raise ValueError('Full diff denominator differs')
    if any(report.get(k) is not True for k in ('whole_date_task_map_verified','ordered_full_record_diff_verified','full_new_results_match_external_checkpoints','output_source_partitions_reverified')):raise ValueError('Full independent date audit required')
    if any(report.get(k) is not False for k in ('numerical_recomputation_performed','merger_called','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed','selection_performed','training_performed')):raise ValueError('Diff scope differs')
    if complete.get('input_artifact_binding_verified') is not True:raise ValueError('Source-bound complete reader artifact required')
    if any(report['source_hashes'].get(p)!=h for p,h in independent_diff.LOADED.items()):raise ValueError('Independent full-diff loaded sources omitted')


def verify(report):
    expected=report['historical_expected_source_hashes']
    if any(expected.get(p)!=h or report['verified_source_hashes'].get(p)!=h for p,h in LOADED.items()):raise ValueError('Required loaded consumer source omitted')
    partition=reader.drift.verify_expected_sources(expected,reader.drift.load_contract())
    if partition['verified_source_hashes']!=report['verified_source_hashes'] or partition['historical_gap_observations']!=report['historical_price_cache_gap_observations']:raise ValueError('Consumer source partition differs')
    for key in ('historical_full_source_closure_verified','point_in_time_verified','promotion_allowed','selection_performed','training_performed','execution_performed','full_ndx_pool_coverage_verified'):
        if report.get(key) is not False:raise ValueError('Unsupported consumer scope upgrade')
    reader.independent.verify_gaps(report['historical_loader_gap_observations'])


def build(*,date,complete_path,complete_sha256,diff_path,diff_sha256):
    sources=dict(LOADED)
    def include(mapping):
        for p,h in mapping.items():
            p=str(Path(p).resolve())
            if p in sources and sources[p]!=h:raise ValueError('Conflicting source')
            sources[p]=h
    def read(path,digest):
        path=Path(path).resolve();raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=digest:raise ValueError('External reviewed artifact differs')
        include({str(path):digest});return json.loads(raw)
    inventory=read(reader.INVENTORY,reader.INVENTORY_SHA)
    matches=[r for r in inventory['dates'] if r['date']==date.replace('-','')]
    if len(matches)!=1:raise ValueError('Exactly one bound original date required')
    descriptor=matches[0];parent=read(descriptor['overlay_path'],descriptor['overlay_sha256'])
    complete=read(complete_path,complete_sha256);audit=read(diff_path,diff_sha256)
    if (complete['parent_overlay_path']!=descriptor['overlay_path'] or complete['parent_overlay_sha256']!=descriptor['overlay_sha256']
        or complete['coordinate']['selection_date']!=date):raise ValueError('Complete output linked to wrong original date')
    validate_diff(audit,date=date,complete_path=complete_path,complete_sha256=complete_sha256,parent=parent,complete=complete)
    reader.verify(complete)
    include(complete['historical_expected_source_hashes']);include(complete['verified_source_hashes']);include(audit['source_hashes'])
    refs=[(p,h) for p,h in sources.items() if Path(p).name=='equal_base_'+date.replace('-','')+'_20260911.json']
    if len(refs)!=1:raise ValueError('Unique original equal training semantics source required')
    original_equal=read(*refs[0])
    if original_equal['coordinate']!=parent['coordinate']:raise ValueError('Original training date differs')
    delta_contracts={};contexts={}
    for record in parent['records']:
        if record['origin']!='DELTA':continue
        lineage=record['lineage'];checkpoint_path=lineage['original_checkpoint_path']
        if sources.get(checkpoint_path)!=lineage['original_checkpoint_sha256']:raise ValueError('Original DELTA checkpoint source not bound')
        context_path=str(Path(checkpoint_path).parent/'context.json')
        if context_path not in sources:raise ValueError('Original DELTA context source not bound')
        if context_path not in contexts:
            context=read(context_path,sources[context_path])
            contexts[context_path]=(reader.independent.scalar.decode(context['prepared_inputs']['contract']['payload']),{core.digest(t) for t in context['tasks']})
        contract,tasks=contexts[context_path]
        if core.digest(record['task']) not in tasks:raise ValueError('Original DELTA task absent from bound context')
        delta_contracts[record['task']['job_id']]=contract
    result=core.analyze_complete_corrected_date(complete_overlay=complete,original_parent=parent,original_training_semantics=original_equal['training_semantics'],delta_contracts=delta_contracts)
    include(result.pop('source_hashes'))
    partition=reader.drift.verify_expected_sources(sources,reader.drift.load_contract())
    semantics=dict(schema='CORRECTED_COMPLETE_COHORT_NUMERICAL_COORDINATE_V1',original_training_contract_sha256=result['original_training_contract_reference_sha256'],
        corrected_records_sha256=complete['records_sha256'],correction_signatures=sorted({r['correction_signature'] for r in complete['records']}),
        complete_overlay_path=str(Path(complete_path).resolve()),complete_overlay_sha256=complete_sha256)
    result.update(input_artifact_binding_verified=True,original_source_hashes_verified_here=False,
        corrected_numerical_coordinate=semantics,corrected_numerical_coordinate_sha256=core.digest(semantics),
        complete_date_artifact=dict(path=str(Path(complete_path).resolve()),sha256=complete_sha256),independent_full_diff_artifact=dict(path=str(Path(diff_path).resolve()),sha256=diff_sha256),
        historical_expected_source_hashes=sources,verified_source_hashes=partition['verified_source_hashes'],historical_price_cache_gap_observations=partition['historical_gap_observations'],
        historical_loader_gap_observations=complete['historical_loader_gap_observations'],saved_non20_fields_independently_recomputed=False,binary_float_ledger_hash_independently_verified=False)
    verify(result);return result


def publish(path,report):
    verify(report)
    saved=reader.publish(path,report)
    verify(report);return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for key in ('date','complete-path','complete-sha256','diff-path','diff-sha256','output'):parser.add_argument('--'+key,required=True)
    args=vars(parser.parse_args());output=args.pop('output');print(json.dumps(publish(output,build(**args))))
