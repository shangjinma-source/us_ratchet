"""Independent completed-prefix scalar/Decimal audit, never optimizer or snapshot restore."""
import argparse
from copy import deepcopy
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts import ndx_selected_snapshot_first_two_audit_20260919 as first
drift,scalar,ledger=first.drift,first.scalar,first.ledger
FOLDER=first.FOLDER
MANIFEST=FOLDER/'manifest.json'
MANIFEST_SHA='beb22a53d179a725e359272273b14c8fc6ed6fe669e0fac574c0a4ff5f45fb9e'
SEED=FOLDER/'first_two_independent_audit_20260919.json'
SEED_SHA='e722bf066d64a9de6dff174af54876459265767d32456eb78ee17e725cbc30c1'
CORRECTIONS=(('GOOG','2022-07-18',0.,-.025335378898117544),('GOOGL','2022-07-18',0.,-.024580059928059006),('FTNT','2022-06-23',0.,.019968386675822902))
SCOPE='EXTERNAL_SHA_LINEAGE_PLUS_TWENTY_METRICS_WINDOWS_AND_DECIMAL_CLOSE_ACCOUNTING'
LOADED={str(p):drift.file_sha(p) for p in (Path(__file__).resolve(),Path(first.__file__).resolve(),drift.SOURCE,Path(scalar.__file__).resolve(),Path(ledger.__file__).resolve())}


def digest(value):
    return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()


def exact(a,b):
    return digest(a)==digest(b)


def require_false(value,keys):
    if any(value.get(key) is not False for key in keys):raise ValueError('Unsupported scope flag upgrade')


def check_index(index,manifest,seed_ids):
    reference=dict(path=str(MANIFEST),sha256=MANIFEST_SHA)
    n=len(index['completed']);planned=len(manifest['tasks']);final=index.get('finalization')
    if (index['schema']!='ndx_selected_delta_exact_gap_completion_index_v1' or index['manifest']!=reference
        or type(index['planned']) is not int or index['planned']!=planned or not 2<=n<=planned
        or type(final) is not dict or final.get('schema')!='ndx_selected_delta_exact_gap_finalization_v1'
        or type(final.get('completed')) is not int or final['completed']!=n
        or type(final.get('planned')) is not int or final['planned']!=planned):
        raise ValueError('Complete finalized index denominator required')
    status='COMPLETE' if n==planned else 'PARTIAL'
    if index['status']!=status or final['status']!=status or final['immutable_numerical_source_closure_verified'] is not True:
        raise ValueError('Finalization status differs')
    for value in (index,final):require_false(value,('historical_full_source_closure_verified','original_historical_provenance_verified','point_in_time_verified','promotion_allowed'))
    pairs=[(e['path'],e['sha256']) for e in index['completed']]
    if len(set(pairs))!=n:raise ValueError('Duplicate completed artifact')
    ids=[r['new_job_id'] for r in manifest['tasks'][:n]]
    if not set(seed_ids)<=set(ids):raise ValueError('Original independently checked seed omitted')
    return ids


def audit_task(value,row,context,checkpoint,manifest):
    result=value['result'];task=row['task']
    if (value['schema']!='ndx_selected_delta_exact_gap_task_v1' or value['new_job_id']!=row['new_job_id']
        or not exact(value['original'],row) or value['manifest_path']!=str(MANIFEST) or value['manifest_sha256']!=MANIFEST_SHA
        or not any(exact(task,x) for x in context['tasks']) or not exact(result['original_task'],task)):
        raise ValueError('Actual complete task/context/manifest binding differs')
    require_false(value,('historical_full_source_closure_verified','original_historical_provenance_verified','point_in_time_verified','promotion_allowed','non20_risk_projection_fields_independently_recomputed'))
    if value['saved_result_revalidation_scope']!=SCOPE:raise ValueError('Unsupported restored scope label')
    require_false(result,('original_result_reproduced','window_fit_reuse_performed','old_window_targets_available','original_historical_provenance_verified','point_in_time_verified','promotion_allowed','selection_performed','no_fit_reuse'))
    if (result['schema']!='ndx_delta_selected_input_research_v1' or type(result['old_input_numerical_evaluation_count']) is not int
        or result['old_input_numerical_evaluation_count']!=0 or type(result['new_input_numerical_evaluation_count']) is not int
        or result['new_input_numerical_evaluation_count']!=1 or result['exact_three_return_cells_only'] is not True
        or result['nominal_execution_semantics']!='ORIGINAL_V3_UNCHANGED'
        or result['reconstruction_scope']!='NEW_INPUT_FULL_V3_WITH_HISTORICAL_LOADER_PROVENANCE_GAP'
        or result['actual_runtime_matches_original_context'] is not True
        or not exact(result['observed_runtime'],row['runtime']) or not exact(context['runtime'],row['runtime'])):
        raise ValueError('Numerical execution provenance differs')
    known=manifest['completed_probe']
    if value['mode']=='EXTERNAL_FIRST_PROBE_IMPORTED_WITHOUT_NEW_FIT':
        if dict(path=value['imported_probe_path'],sha256=value['imported_probe_sha256'],new_job_id=value['new_job_id'])!=known:
            raise ValueError('Imported probe identity differs')
    elif value['mode']!='ONE_NEW_INPUT_FULL_V3_EVALUATION_NO_OLD_WINDOW_REUSE' or value['new_job_id']==known['new_job_id']:
        raise ValueError('Unexpected task execution mode')
    for kind in ('context','checkpoint'):
        if result[kind+'_path']!=row[kind+'_path'] or result[kind+'_sha256']!=row[kind+'_sha256']:
            raise ValueError('Actual original input coordinate differs')
    payload=dict(checkpoint);signature=payload.pop('checkpoint_sha256')
    if (digest(payload)!=signature or checkpoint['context_sha256']!=digest(context) or checkpoint['status']!='EVALUATED'
        or not exact(checkpoint['task'],task) or result['original_result_lineage_sha256']!=digest(checkpoint['result'])):
        raise ValueError('Original checkpoint typed lineage differs')
    encoded=context['prepared_inputs'];changed=deepcopy(encoded)
    inputs={k:scalar.decode(v['payload']) for k,v in encoded.items()}
    ret=inputs['returns'];calendar=ret['index'];returns=dict(zip(ret['columns'],ret['column_values']));c=inputs['contract']
    for ticker,date,old,new in CORRECTIONS:
        column=ret['columns'].index(ticker);pos=calendar.index(date)
        if type(returns[ticker][pos]) is not float or returns[ticker][pos]!=old:raise ValueError('Original three correction cells differ')
        cell=changed['returns']['payload']['mapping']['column_values']['items'][column]['items'][pos]
        if set(cell)!={'float_hex'} or float.fromhex(cell['float_hex'])!=old:raise ValueError('Typed original correction differs')
        cell['float_hex']=new.hex();returns[ticker][pos]=new
    old_digest,new_digest=digest(encoded),digest(changed)
    if (value['input_digests']!=dict(original=old_digest,corrected=new_digest)
        or result['original_input_sha256']!=old_digest or result['new_input_sha256']!=new_digest):
        raise ValueError('Exact typed input or three-cell correction digest differs')
    windows=result['historical_window_weights'];starts=list(range(c['fit_days'],len(calendar)-c['window_days']+1,c['step_days']))
    tickers=task['tickers'].split(';');prior=None
    if not starts or len(starts)!=len(windows) or len(starts)!=len(result['new_windows']) or type(result['new_fitted_window_count']) is not int or result['new_fitted_window_count']!=len(starts):
        raise ValueError('All actual fitted windows required')
    anchored=task['weight_spec']=='constrained_fixed_shrinkage_turnover_anchor'
    for start,weight,forward in zip(starts,windows,result['new_windows']):
        if (weight['tickers']!=tickers or set(weight['weights'])!=set(tickers)
            or any(type(x) not in (int,float) or not math.isfinite(x) or x<=0 for x in weight['weights'].values())
            or (weight['fit_start'],weight['fit_end'],weight['fit_row_count'])!=(calendar[start-c['fit_days']],calendar[start-1],c['fit_days'])
            or not exact(weight['anchor_weights'],prior if anchored else None)
            or type(weight['turnover_anchor_strength']) not in (int,float)
            or weight['turnover_anchor_strength']!=(c['turnover_anchor_strength'] if anchored else 0.)
            or (forward['start'],forward['end'])!=(calendar[start],calendar[start+c['window_days']-1])):
            raise ValueError('Saved window identity/date/anchor differs')
        prior=weight['weights']
    rows,metrics=scalar.economics(returns,inputs['target_returns']['column_values'][0],inputs['incumbent_weights'],c,windows)
    errors=first.compare(metrics,result['result'],1e-12)
    window_errors=[max(first.compare(a,b,1e-12).values()) for a,b in zip(rows,result['new_windows'])]
    panel=inputs['nominal_prices'];begin=calendar[starts[0]];end=calendar[starts[-1]+c['window_days']-1]
    positions=[i for i,date in enumerate(panel['index']) if begin<=date<=end]
    prices={t:[panel['column_values'][panel['columns'].index(t)][i] for i in positions] for t in tickers}
    universe=dict(zip(inputs['universe']['columns'],inputs['universe']['column_values']))
    chains={t:universe['risk_chain'][universe['ticker'].index(t)] for t in tickers}
    account=ledger.account(dates=[panel['index'][i] for i in positions],prices=prices,
        schedule={calendar[start]:w['weights'] for start,w in zip(starts,windows)},risk_chains=chains,contract=c)
    accounting_errors=first.compare(account['summary'],result['result'],1e-8)
    gaps=result['historical_loader_provenance_gaps']
    verify_gaps(gaps)
    return dict(new_job_id=row['new_job_id'],task=task,mode=value['mode'],window_count=len(rows),
        independent_three_cell_input_sha256=new_digest,scalar_max_error=max(errors.values()),
        all_windows_max_error=max(window_errors),legacy_close_max_error=max(accounting_errors.values()),
        checked_metric_fields=sorted(metrics),checked_legacy_close_fields=sorted(account['summary']),
        legacy_close_summary=account['summary'],historical_loader_provenance_gaps=gaps,
        saved_non20_fields_independently_recomputed=False,binary_float_ledger_hash_independently_verified=False)


def verify_gaps(gaps):
    for gap in gaps:
        if (gap['original_pointer_preserved'] is not True or gap['used_as_current_numerical_input'] is not False
            or drift.file_sha(gap['path'])!=gap['observed_current_sha256']):raise ValueError('Historical config gap observation differs')


def verify_report(report):
    required=dict(LOADED,**{str(MANIFEST):MANIFEST_SHA,str(SEED):SEED_SHA})
    if any(report['historical_expected_source_hashes'].get(p)!=h or report['verified_source_hashes'].get(p)!=h for p,h in required.items()):
        raise ValueError('Audit omitted loaded source or hard manifest/seed')
    require_false(report,('optimizer_or_original_simulator_called','historical_full_source_closure_verified',
        'saved_non20_fields_independently_recomputed','binary_float_ledger_hash_independently_verified','point_in_time_verified','promotion_allowed'))
    checked=drift.verify_expected_sources(report['historical_expected_source_hashes'],drift.load_contract())
    if checked['verified_source_hashes']!=report['verified_source_hashes'] or checked['historical_gap_observations']!=report['historical_price_cache_gap_observations']:
        raise ValueError('Audit source partition changed')
    for row in report['tasks']:verify_gaps(row['historical_loader_provenance_gaps'])


def build(index_path,index_sha256):
    sources=dict(LOADED)
    def include(mapping):
        for p,h in mapping.items():
            p=str(Path(p).resolve())
            if p in sources and sources[p]!=h:raise ValueError('Conflicting source')
            sources[p]=h
    def read(p,h):
        p=str(Path(p).resolve());raw=Path(p).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('External SHA differs')
        include({p:h});return json.loads(raw)
    manifest=read(MANIFEST,MANIFEST_SHA);seed=read(SEED,SEED_SHA);index=read(index_path,index_sha256)
    ids=check_index(index,manifest,[r['new_job_id'] for r in seed['tasks']])
    final=index['finalization'];contract=drift.load_contract()
    checked=drift.verify_expected_sources(final['historical_expected_source_hashes'],contract)
    if (checked['verified_source_hashes']!=final['verified_source_hashes'] or checked['historical_gap_observations']!=final['historical_price_cache_gap_observations'] or len(checked['historical_gap_observations'])!=26):
        raise ValueError('Finalized exact26 source partition differs')
    include(final['historical_expected_source_hashes']);include(final['additional_provenance_hashes'])
    for p,h in manifest['historical_expected_source_hashes'].items():
        if sources.get(p)!=h:raise ValueError('Manifest source omitted from finalization')
    parent=read(drift.SELECTED_PLAN,drift.SELECTED_PLAN_SHA)
    for observation in parent['historical_context_gap_observations'].values():verify_gaps(observation['gaps'])
    planned={r['new_job_id']:r for r in manifest['tasks']}
    reports=[]
    drift.verify_expected_sources(sources,contract)
    for identifier,entry in zip(ids,index['completed']):
        value=read(entry['path'],entry['sha256']);row=planned[identifier]
        if value['new_job_id']!=identifier:raise ValueError('Completed queue is not full ordered plan prefix')
        if Path(entry['path']).resolve()!=FOLDER/'tasks'/(identifier+'.json'):raise ValueError('Completed task file coordinate differs')
        context=read(row['context_path'],row['context_sha256']);checkpoint=read(row['checkpoint_path'],row['checkpoint_sha256'])
        expected_gap=parent['historical_context_gap_observations'][row['context_path']]
        if expected_gap!=dict(context_sha256=row['context_sha256'],gaps=value['result']['historical_loader_provenance_gaps']):raise ValueError('Hard original gap metadata differs')
        reports.append(audit_task(value,row,context,checkpoint,manifest))
    verified=drift.verify_expected_sources(sources,contract)
    report=dict(schema='SELECTED_COMPLETED_QUEUE_INDEPENDENT_SCALAR_DECIMAL_AUDIT_V1',planned=len(manifest['tasks']),
        completed=len(reports),status=index['status'],tasks=reports,completed_queue_all_tasks_audited=True,
        verified_source_hashes=verified['verified_source_hashes'],historical_expected_source_hashes=sources,
        historical_price_cache_gap_observations=verified['historical_gap_observations'],
        optimizer_or_original_simulator_called=False,historical_full_source_closure_verified=False,
        saved_non20_fields_independently_recomputed=False,binary_float_ledger_hash_independently_verified=False,
        nominal_quote_authenticity_verified=False,dynamic_next_open_execution_validated=False,
        point_in_time_verified=False,promotion_allowed=False)
    verify_report(report)
    return report


if __name__=='__main__':
    parser=argparse.ArgumentParser()
    for name in ('index-path','index-sha256','output'):parser.add_argument('--'+name,required=True)
    args=parser.parse_args();report=build(args.index_path,args.index_sha256)
    with Path(args.output).open('x',encoding='utf8') as stream:json.dump(report,stream,indent=2,sort_keys=True,allow_nan=False);stream.write('\n')
    verify_report(report)
    print(json.dumps(dict(path=str(Path(args.output).resolve()),sha256=drift.file_sha(args.output),completed=report['completed'])))
