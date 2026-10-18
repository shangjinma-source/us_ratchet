"""One source-bound historical non-GOOG recovery; never run a fitter."""
from copy import deepcopy
import hashlib
import json
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from backtest import ndx_saved_fractional_window_research as recovery
from scripts import ndx_non_equal_base_runner as runner

SELF=Path(__file__).resolve()
LOADED=hashlib.sha256(SELF.read_bytes()).hexdigest()


def run():
    sources={str(SELF):LOADED}
    def read(path,sha):
        path=Path(path).resolve();raw=path.read_bytes()
        if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('Bound source differs')
        sources[str(path)]=sha
        return json.loads(raw)
    directory=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1'
    inventory=read(directory/'saved_dependency_count_20260912.json','dadcc73e981d56d2b867f4cabd02db2d093f81709799a2428e20681ba268ad69')
    path=Path(inventory['checkpoint_field_samples']['NON_EQUAL_BASE']['path'])
    checkpoint=read(path,inventory['source_hashes'][str(path)])
    context=read(path.parent/'context.json',checkpoint['context_sha256'])
    task=checkpoint['task']
    if 'GOOG' in task['tickers'].split(';') or task not in context['tasks']:
        raise ValueError('Bound non-GOOG member required')
    coordinate={k:task[k] for k in ('source_batch','universe_track','selection_date')}
    prepared=runner.preparation.prepare_non_equal_base_date(**coordinate)
    if task not in prepared['tasks'] or prepared['training_semantics']!=context['training_semantics']:
        raise ValueError('Original full prepared-input binding differs')
    for mapping in (prepared['source_hashes'],context['source_hashes'],runner._LOADED):
        for p,h in mapping.items():
            if p in sources and sources[p]!=h:raise ValueError('Source conflict')
            sources[p]=h
    runner._verify_sources(sources)
    saved=runner._read_checkpoint(path,checkpoint['context_sha256'],task,context['numerical_sources'])
    arguments=dict(task=task,inputs=prepared['inputs'],engine='non_equal_fractional_v1',
                   runtime=context['runtime'],source_hashes=sources)
    old=recovery.verify_original(arguments=arguments,saved=saved)
    evidence=read(directory/'root_return_semantics_review_20260912.json','a0cfca247b790779de4abdfa8ce4d284214cf4405e35e1fb38233f018db6c02b')
    error,=[r for r in evidence['known_split_day_return_errors'] if r['ticker']=='GOOG' and r['session']=='2022-07-18']
    revised=deepcopy(arguments)
    if revised['inputs']['returns'].loc[error['session'],'GOOG']!=error['legacy_root_return']:
        raise ValueError('Original correction cell differs')
    revised['inputs']['returns'].loc[error['session'],'GOOG']=error['provider_split_adjusted_price_return']
    eq=recovery.equivalence.compare_candidate_numerical_inputs(left=arguments,right=revised)
    if eq['changed_dependency_fields']!=['incumbent_forward_returns']:
        raise ValueError('Complete candidate fit/forward dependency must remain equivalent')
    new=recovery.recover(arguments=revised,saved=saved)
    allowed={'paired_return_p50_vs_incumbent','paired_return_p10_vs_incumbent',
             'paired_drawdown_cost_p50_vs_incumbent','paired_drawdown_cost_p90_vs_incumbent'}
    for a,b in zip(old['windows'],new['windows']):
        if any(a[k]!=b[k] for k in a if not k.startswith('incumbent_')):
            raise ValueError('Candidate/target/cost sequence changed')
    changed=[k for k in old['metrics'] if old['metrics'][k]!=new['metrics'][k]]
    if not set(changed)<=allowed:raise ValueError('Unexpected changed output')
    sources.update(old['source_hashes']);sources.update(new['source_hashes'])
    runner._verify_sources(sources)
    return dict(schema='ndx_saved_fractional_window_probe_v1',task=task,source_hashes=sources,
        correction=error,original=old,corrected=new,changed_metrics=changed,
        compared_metric_count=len(old['metrics']),original_max_absolute_error=max(abs(v-saved['result'][k]) for k,v in old['metrics'].items()),
        original_absolute_tolerance=recovery.TOLERANCE,dependency_fields_changed=eq['changed_dependency_fields'],
        fitter_called=False,projection_called=False,whole_lot_called=False,
        saved_checkpoint_modified=False,point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    result=run();path=ROOT/'data/cache/research/root_return_semantics_probe_20260912_v1/non_equal_single_window_recovery_20260912.json'
    raw=(json.dumps(result,indent=2,sort_keys=True)+'\n').encode()
    with path.open('xb') as stream:stream.write(raw)
    runner._verify_sources(result['source_hashes'])
    print(json.dumps(dict(path=str(path),sha256=hashlib.sha256(raw).hexdigest(),windows=len(result['original']['windows']),
        original_error=result['original_max_absolute_error'],changed=result['changed_metrics'])))
