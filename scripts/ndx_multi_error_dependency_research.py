"""Classify saved records against three evidenced cells, without economic evaluation."""
from collections import Counter
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from scripts.ndx_joint_weight_verify import _restore_input

SELF=Path(__file__).resolve(); LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()


def run():
    sources={str(SELF):LOADED}
    def read(path,expected):
        path=Path(path).resolve(); raw=path.read_bytes(); sha=hashlib.sha256(raw).hexdigest()
        if sha!=expected or str(path) in sources and sources[str(path)]!=sha:raise ValueError('Source conflict/drift')
        sources[str(path)]=sha
        return json.loads(raw)
    directory=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1'
    prior=read(directory/'saved_dependency_count_20260912.json','dadcc73e981d56d2b867f4cabd02db2d093f81709799a2428e20681ba268ad69')
    old=read(directory/'root_return_semantics_review_20260912.json','a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b')
    extra=read(ROOT/'data/cache/research/legacy_pool_additional_split_probe_20260912_v1/report.json','64e6c86a9ad8045dcb925990c04a7d00c8480cdec2e922ef215e9ed839acd850')
    for document in (old,extra):
        for path,sha in document['source_hashes'].items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Evidence source changed')
            sources[path]=sha
    goog,=[e for e in old['known_split_day_return_errors'] if e['ticker']=='GOOG' and e['session']=='2022-07-18']
    errors=[dict(ticker='GOOG',session=goog['session'],old=goog['legacy_root_return'],new=goog['provider_split_adjusted_price_return'])]
    errors += [dict(ticker=e['ticker'],session=e['session'],old=e['old_root_return'],new=e['provider_split_only_price_return']) for e in extra['observed_split_events']]
    if {(e['ticker'],e['session']) for e in errors}!={('GOOG','2022-07-18'),('GOOGL','2022-07-18'),('FTNT','2022-06-23')} or len(errors)!=3:raise ValueError('Exact three errors required')
    masks={}
    for location in old['actual_window_error_locations']:
        context_sha=location['context_sha256']
        path,=[p for p,h in old['source_hashes'].items() if h==context_sha and Path(p).name=='context.json']
        context=read(path,context_sha)
        inputs={k:_restore_input(v) for k,v in context['prepared_inputs'].items()}
        returns=inputs['returns'];contract=inputs['contract'];window=contract['window_days'];fit=contract['fit_days']
        starts=list(range(fit,len(returns)-window+1,contract['step_days']))
        rows=[]
        for error in errors:
            if returns.loc[error['session'],error['ticker']]!=error['old']:raise ValueError('Context original cell differs')
            position=returns.index.get_loc(error['session'])
            rows.append(dict(**error,in_fit=any(s-fit<=position<s for s in starts),
                in_forward=any(s<=position<s+window for s in starts),
                incumbent_positive=inputs['incumbent_weights'].get(error['ticker'],0)>0))
        masks[location['coordinate']['selection_date']]=rows
    inventory=read(ROOT/'data/cache/research/dynamic_frozen_v2/combined_summary_inventory_20260912.json','baa74f6447e4663ac13a0b4174ad0fa0cf0d799ce3d35a735c9f25379e24ca09')
    buckets={};counter=Counter(); seen=set()
    def add(date,origin,tickers,spec,locator):
        combo=tickers.split(';') if isinstance(tickers,str) else tickers
        selected=[e['ticker'] for e in masks[date] if e['ticker'] in combo and (e['in_forward'] or spec!='equal_weight' and e['in_fit'])]
        benchmark=any(e['incumbent_positive'] and e['in_forward'] for e in masks[date])
        category='SELECTED_INPUT_CHANGED' if selected else 'PAIRED_ONLY_NO_REFIT' if benchmark else 'NO_DEPENDENCY'
        key='|'.join((date,origin,category))
        buckets.setdefault(key,[]).append(locator)
        counter['|'.join((origin,category))]+=1
    for descriptor in inventory['summaries']:
        date=descriptor['coordinate']['selection_date'];summary=read(descriptor['path'],descriptor['sha256'])
        path,=[p for p in summary['source_hashes'] if Path(p).name.startswith('equal_base_')]
        equal=read(path,summary['source_hashes'][path])
        for index,row in enumerate(equal['evaluation']['records']):
            # Exact saved report row index plus content-addressed report identifies each equal record.
            add(date,'EQUAL_WEIGHT_BASE',row['tickers'],row['weight_spec'],dict(report_path=path,row_index=index,tickers=row['tickers']))
        for path,sha in summary['source_hashes'].items():
            if path in seen or Path(path).name=='context.json':continue
            if 'ndx_non_equal_base_fractional_v1' not in path and 'ndx_joint_weight_runs_v3' not in path:continue
            seen.add(path);checkpoint=read(path,sha);task=checkpoint['task']
            if checkpoint['status']!='EVALUATED' or prior['source_hashes'].get(path)!=sha:raise ValueError('Verified saved checkpoint differs')
            origin='NON_EQUAL_BASE' if 'ndx_non_equal_base_fractional_v1' in path else 'DELTA'
            add(task['selection_date'],origin,task['tickers'],task['weight_spec'],
                dict(checkpoint_path=path,checkpoint_sha256=sha,task=task))
    if sum(counter.values())!=351255 or len(masks)!=15:raise ValueError('Incomplete denominator')
    for descriptor in inventory['summaries']:
        date=descriptor['coordinate']['selection_date']
        for origin,counts in descriptor['counts'].items():
            if sum(len(rows) for key,rows in buckets.items() if key.startswith(date+'|'+origin+'|'))!=counts['observed']:raise ValueError('Date/origin denominator differs')
    for path,sha in sources.items():
        if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=sha:raise ValueError('Final source drift')
    return dict(schema='ndx_three_cell_saved_dependency_v1',source_hashes=sources,errors=errors,
        masks_by_date=masks,counts=dict(counter),buckets=buckets,
        bucket_content_sha256={key:hashlib.sha256(json.dumps(rows,sort_keys=True,separators=(',',':')).encode()).hexdigest() for key,rows in buckets.items()},
        record_count=sum(counter.values()),assumption='ONLY_THREE_EXPLICIT_RETURN_CELLS_CHANGE_OTHER_INPUTS_IDENTICAL',
        affected_fit_can_propagate_via_anchor_and_turnover=True,all_provider_errors_repaired=False,
        training_performed=False,economic_metrics_recomputed=False,checkpoint_reuse_authorized=False,promotion_allowed=False)


if __name__=='__main__':
    result=run();path=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/three_cell_saved_dependency_20260912.json'
    raw=(json.dumps(result,sort_keys=True,indent=2)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw)
    for source,sha in result['source_hashes'].items():
        if hashlib.sha256(Path(source).read_bytes()).hexdigest()!=sha:raise ValueError('Source drift after save')
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),counts=result['counts'])))
