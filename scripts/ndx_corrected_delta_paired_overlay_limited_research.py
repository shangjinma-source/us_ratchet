"""Merge audited paired repairs with explicit, unresolved 26-file historical gaps."""
import argparse
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_corrected_delta_paired_overlay_limited_research as merger
from backtest import ndx_exact_price_cache_drift_research as drift
from backtest import ndx_joint_weight_runner as encoding
from scripts.ndx_joint_weight_verify import _restore
from scripts.ndx_base_three_cell_window_delta_research import publish

PLAN=ROOT/'data/cache/research/delta_three_cell_paired_trace_20260912_v2/plan.json'
PLAN_SHA='fb2e514516123efe67dffb92821410ce2eb52d3e757494c4dfaf517c7ea9b330'
AUDIT=ROOT/'data/cache/research/delta_paired_snapshot_20260912_v1/limited_drift_independent_audit_20260919.json'
AUDIT_SHA='34e395c008db8b91b8cdc5075af864ba80e216780d523362bc1e402dc292633b'
GAP_PATH=str((ROOT/'config/ndx_cardinality_discovery_v1.yaml').resolve())
GAP_EXPECTED_SHA='1f85b1d848c5a884290b9a8edc89efd4a9d8520c271ad9581c33c3601e72d78e'
LOADED={str(path):hashlib.sha256(path.read_bytes()).hexdigest() for path in (
    Path(__file__).resolve(),drift.SOURCE,Path(merger.__file__).resolve(),Path(merger.digest.__code__.co_filename).resolve(),
    Path(encoding.__file__).resolve(),Path(_restore.__code__.co_filename).resolve(),Path(publish.__code__.co_filename).resolve())}


def verify_gap_observations(observations):
    if type(observations) is not list or not observations:raise ValueError('Explicit historical loader gap observation required')
    for gap in observations:
        if (gap['path']!=GAP_PATH or gap['expected_historical_sha256']!=GAP_EXPECTED_SHA or
            gap['original_pointer_preserved'] is not True or gap['used_as_current_numerical_input'] is not False):
            raise ValueError('Exact original historical loader gap required')
        path=Path(GAP_PATH)
        if not path.exists():actual=None
        elif path.is_file():actual=hashlib.sha256(path.read_bytes()).hexdigest()
        else:raise ValueError('Historical gap path exists but is not a regular file')
        if (actual!=gap['observed_current_sha256'] or gap['status']!=('UNAVAILABLE' if actual is None else 'HISTORICAL_SOURCE_DRIFT')):
            raise ValueError('Historical loader gap observation drifted')


def build(*,parent_path,parent_sha256,index_path,index_sha256,audit_path,audit_sha256):
    if Path(audit_path).resolve()!=AUDIT or audit_sha256!=AUDIT_SHA:
        raise ValueError('Hard independently completed 614 limited audit required')
    sources={};gap_observations=[];contract=drift.load_contract()
    def include(mapping):
        for path,sha in mapping.items():
            path=str(Path(path).resolve())
            if path in sources and sources[path]!=sha:raise ValueError('Conflicting source SHA')
            sources[path]=sha
    def read(path,sha):
        include({str(Path(path).resolve()):sha});raw=Path(path).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External artifact SHA differs')
        return json.loads(raw)
    def verify():
        drift.verify_expected_sources(sources,contract)
        verify_gap_observations(gap_observations)
    include(LOADED)
    plan=read(PLAN,PLAN_SHA);parent=read(parent_path,parent_sha256);index=read(index_path,index_sha256);audit=read(audit_path,audit_sha256)
    if (index['schema']!='ndx_delta_paired_snapshot_completion_index_v1' or index['status']!='COMPLETE' or
        index['planned']!=614 or len(index['completed'])!=614 or index['finalization']['status']!='COMPLETE' or
        index['finalization']['planned']!=614 or index['finalization']['completed']!=614 or
        index['finalization']['source_closure_verified'] is not True):raise ValueError('Entire 614 finalized COMPLETE index required')
    if (audit['schema']!='ndx_delta_paired_snapshot_limited_drift_independent_audit_v1' or audit['planned']!=614 or audit['completed']!=614 or
        audit['verified_source_hashes'].get(str(Path(index_path).resolve()))!=index_sha256 or
        any(audit[flag] is not True for flag in ('complete_task_lineage_verified','all_windows_independently_recomputed','no_fitter_or_evaluator_called')) or
        any(audit[flag] is not False for flag in ('original_historical_provenance_verified','point_in_time_verified','promotion_allowed','historical_full_source_closure_verified','strict_no_gap_audit_passed'))):
        raise ValueError('Independent limited complete 614 task/window audit required')
    audit_partition=drift.verify_expected_sources(audit['historical_expected_source_hashes'],contract)
    if (audit_partition['verified_source_hashes']!=audit['verified_source_hashes'] or
        audit_partition['historical_gap_observations']!=audit['historical_price_cache_gap_observations'] or
        len(audit_partition['historical_gap_observations'])!=26):
        raise ValueError('Limited audit source partition differs')
    manifest=read(index['manifest']['path'],index['manifest']['sha256'])
    original_rows=[row for day in plan['dates'] for row in day['tasks']]
    audited={row['new_job_id']:row for row in audit['tasks']}
    if (len(audit['tasks'])!=614 or len(audited)!=614 or
        {key:row['task'] for key,row in audited.items()}!={row['new_job_id']:row['task'] for row in original_rows}):
        raise ValueError('Independent audit task denominator or identities differ')
    for row in audited.values():
        variants=row['variants']
        if len(variants)!=2 or {v['variant'] for v in variants}!={'original','corrected'}:
            raise ValueError('Both independent scalar variants required')
        for variant in variants:
            if type(variant['window_count']) is not int or variant['window_count']<=0:
                raise ValueError('Positive independently checked window count required')
            if any(type(variant[key]) not in (int,float) or not math.isfinite(variant[key]) or not 0<=variant[key]<=1e-12 for key in ('paired_error','window_error')):
                raise ValueError('Independent scalar error exceeds exact audit tolerance')
    if (manifest['schema']!='ndx_delta_paired_snapshot_manifest_v1' or manifest['tasks']!=original_rows or
        manifest['parent_plan_path']!=str(PLAN) or manifest['parent_plan_sha256']!=PLAN_SHA or manifest['planned']!=614 or
        manifest['corrections']!=plan['errors'] or
        index['finalization']['manifest_path']!=index['manifest']['path'] or index['finalization']['manifest_sha256']!=index['manifest']['sha256']):
        raise ValueError('Final snapshot and hard original plan differ')
    for value in (plan,manifest,index['finalization']):include(value['source_hashes'])
    if parent['schema']=='ndx_corrected_base_overlay_limited_drift_v3':
        parent_expected=dict(parent['historical_expected_source_hashes'])
        for path,sha in parent['verified_source_hashes'].items():
            if path in parent_expected and parent_expected[path]!=sha:raise ValueError('Conflicting BASE parent source partition')
            parent_expected[path]=sha
        partition=drift.verify_expected_sources(parent_expected,contract)
        if (partition['verified_source_hashes']!=parent['verified_source_hashes'] or
            partition['historical_gap_observations']!=parent['historical_price_cache_gap_observations'] or
            parent['historical_full_source_closure_verified'] is not False):
            raise ValueError('Limited BASE parent source partition differs')
        include(parent['historical_expected_source_hashes']);include(parent['verified_source_hashes'])
    else:include(parent['source_hashes'])
    include(audit['historical_expected_source_hashes']);include(audit['verified_source_hashes'])
    gap_observations=list({json.dumps(gap,sort_keys=True):gap for observation in plan['historical_context_gap_observations'].values()
        for gap in observation['gaps']}.values())
    include(index['finalization']['additional_provenance_hashes'])
    for document in (index,index['finalization'],manifest):
        if any(document[flag] is not False for flag in ('original_historical_provenance_verified','point_in_time_verified','promotion_allowed')):
            raise ValueError('Historical gap/PIT limitation changed')
    if parent['records_sha256']!=merger.digest(parent['records']):raise ValueError('Parent record digest differs')
    date=parent['coordinate']['selection_date'];date_rows=[row for row in original_rows if row['task']['selection_date']==date]
    if not date_rows:raise ValueError('Parent date has no planned paired-only subset')
    rows={row['new_job_id']:row for row in original_rows}
    if len(rows)!=614:raise ValueError('Duplicate planned task identifier')
    for row in original_rows:
        if sources.get(row['context_path'])!=row['context_sha256'] or sources.get(row['checkpoint_path'])!=row['checkpoint_sha256']:
            raise ValueError('Original context/checkpoint absent from complete source closure')
    verify();seen=set();replacements=[];parent_by_job={record['task']['job_id']:record for record in parent['records']}
    for entry in index['completed']:
        value=read(entry['path'],entry['sha256']);identifier=value['new_job_id']
        if identifier not in rows or identifier in seen:raise ValueError('Unknown or duplicate completed task')
        seen.add(identifier);row=rows[identifier];result=value['result']
        if (value['schema']!='ndx_delta_paired_snapshot_task_v1' or value['original']!=row or
            value['manifest_path']!=index['manifest']['path'] or value['manifest_sha256']!=index['manifest']['sha256'] or
            any(value[flag] is not False for flag in ('original_historical_provenance_verified','point_in_time_verified','promotion_allowed')) or
            result['schema']!='ndx_delta_paired_trace_recovery_research_v2' or
            result['original_full_result_exact'] is not True or
            any(result[flag] is not False for flag in ('original_historical_provenance_verified','point_in_time_verified','promotion_allowed')) or
            result['historical_loader_provenance_gaps']!=plan['historical_context_gap_observations'][row['context_path']]['gaps'] or
            result['context_path']!=row['context_path'] or result['context_sha256']!=row['context_sha256'] or
            result['checkpoint_path']!=row['checkpoint_path'] or result['checkpoint_sha256']!=row['checkpoint_sha256']):
            raise ValueError('Completed task original input lineage differs')
        original=read(row['checkpoint_path'],row['checkpoint_sha256']);context=read(row['context_path'],row['context_sha256'])
        digest=original.pop('checkpoint_sha256')
        if (digest!=encoding._sha(original) or original['context_sha256']!=encoding._sha(context) or original['status']!='EVALUATED' or
            original['task']!=row['task'] or encoding._normalize(result['original_result'])!=original['result']):
            raise ValueError('Complete original DELTA result is not exact to external checkpoint')
        if (set(result['original_result'])!=set(result['result']) or
            {k:v for k,v in result['original_result'].items() if k not in merger.PAIRED_KEYS}!=
            {k:v for k,v in result['result'].items() if k not in merger.PAIRED_KEYS}):
            raise ValueError('Completed DELTA task altered fields outside paired four')
        if row['task']['selection_date']==date:
            old=parent_by_job[row['task']['job_id']]
            if (old['task']!=row['task'] or old['origin']!='DELTA' or
                old['lineage']['original_checkpoint_path']!=row['checkpoint_path'] or
                old['lineage']['original_checkpoint_sha256']!=row['checkpoint_sha256']):raise ValueError('Parent original DELTA lineage differs')
            replacements.append(dict(task=row['task'],original_result=result['original_result'],result=result['result'],
                reconstruction_scope=result['reconstruction_scope'],historical_loader_provenance_gaps=result['historical_loader_provenance_gaps'],
                original_historical_provenance_verified=result['original_historical_provenance_verified'],
                point_in_time_verified=result['point_in_time_verified'],promotion_allowed=result['promotion_allowed'],
                lineage=dict(checkpoint_path=entry['path'],checkpoint_sha256=entry['sha256'],complete_index_path=str(Path(index_path).resolve()),
                    complete_index_sha256=index_sha256,independent_audit_path=str(Path(audit_path).resolve()),independent_audit_sha256=audit_sha256)))
        del value,result,original,context
    if seen!=set(rows):raise ValueError('Incomplete entire 614 lineage denominator')
    output=merger.extend_delta_paired_overlay(parent=parent,replacements=replacements,expected_tasks=[row['task'] for row in date_rows])
    partition=drift.verify_expected_sources(sources,contract)
    if len(partition['historical_gap_observations'])!=26:raise ValueError('Exact 26 historical price gaps required')
    output.pop('source_hashes',None)
    output.update(schema='ndx_corrected_delta_paired_overlay_limited_drift_v2',
        historical_expected_source_hashes=sources,verified_source_hashes=partition['verified_source_hashes'],
        historical_price_cache_gap_observations=partition['historical_gap_observations'],
        historical_full_source_closure_verified=False,strict_no_gap_audit_passed=False,
        input_artifact_binding_verified=True,parent_overlay_path=str(Path(parent_path).resolve()),
        parent_overlay_sha256=parent_sha256,global_delta_paired_queue_completed=614,
        numerical_audit_scope='COMPLETE_614_TASK_LINEAGE_AND_ALL_WINDOWS_INDEPENDENTLY_RECOMPUTED',
        historical_loader_gap_observations=gap_observations,
        checkpoint_documents_cached=False)
    verify();return output


def publish_verified(path,value):
    if Path(path).exists():raise FileExistsError('Existing DELTA overlay must be verified, not replaced')
    contract=drift.load_contract()
    def verify():
        if value['schema']!='ndx_corrected_delta_paired_overlay_limited_drift_v2' or value['historical_full_source_closure_verified'] is not False:
            raise ValueError('Explicit limited overlay required')
        required=dict(LOADED,**{str(AUDIT):AUDIT_SHA})
        if any(value['verified_source_hashes'].get(path)!=sha or value['historical_expected_source_hashes'].get(path)!=sha for path,sha in required.items()):
            raise ValueError('Publication must retain loaded sources and hard independent audit')
        partition=drift.verify_expected_sources(value['historical_expected_source_hashes'],contract)
        if (partition['verified_source_hashes']!=value['verified_source_hashes'] or
            partition['historical_gap_observations']!=value['historical_price_cache_gap_observations']):
            raise ValueError('Publication source partition differs')
        verify_gap_observations(value['historical_loader_gap_observations'])
    verify();saved=publish(path,value);verify()
    return saved


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__)
    for name in ('parent-path','parent-sha256','index-path','index-sha256','audit-path','audit-sha256','output'):parser.add_argument('--'+name,required=True)
    options=vars(parser.parse_args());output=options.pop('output');value=build(**options)
    print(json.dumps(dict(**publish_verified(output,value),added=value['delta_paired_added'],pending=value['pending_count'])))
