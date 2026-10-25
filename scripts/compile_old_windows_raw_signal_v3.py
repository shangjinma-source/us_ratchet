"""Recompile 31 conditional domains from fixed source routes; zero searches."""
import hashlib,json,sys
from copy import deepcopy
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest.return_priority_monthly_training_inputs import compile_monthly_training_window

def main():
    pins={}
    def document(path):
        b=(ROOT/path).read_bytes();pins[path]=hashlib.sha256(b).hexdigest();d=json.loads(b)
        for p,h in d.get('source_hashes',{}).items():
            actual=hashlib.sha256((ROOT/p).read_bytes()).hexdigest()
            if actual!=h:raise ValueError('SOURCE_CHANGED:'+p)
            if p in pins and pins[p]!=h:raise ValueError('PIN_CONFLICT:'+p)
            pins[p]=h
        return d
    basepath='tmp/old_window_source_reuse_20261026/unified_raw_compilation_v2.json'
    earlypath='tmp/old_window_source_reuse_20261026/early_raw_routes_v2.json'
    bridgepath='tmp/early_identity_bridge_20261026/review.json'
    eligibilitypath='tmp/old_window_regular_way_20261026/review.json'
    base=document(basepath);early=document(earlypath);bridges=document(bridgepath)
    eligibility=document(eligibilitypath)
    pins['scripts/compile_old_windows_raw_signal_v3.py']=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
    by_day={w['decision_cutoff']:w for w in early['windows']}
    identity_bridges={(i['decision_date'],row['ticker']):(i,row) for row in bridges['rows'] for i in row['decision_identity']}
    windows=[]
    for previous in base['windows']:
        out=deepcopy(previous);day=out['decision_date'];is_early=day in by_day
        if is_early:
            prepared=by_day[day];candidates=deepcopy(prepared['candidates']);out['blockers']=[]
            for c in candidates:
                if 'IDENTITY_NOT_AVAILABLE_BY_CUTOFF' in c['blockers']:
                    bridge=identity_bridges.get((day,c['ticker']))
                    if bridge and (bridge[0]['security_id'],bridge[0]['issuer_id'])==(c['security_id'],c['issuer_id']):
                        c['retrospective_identity_bridge']=bridge[1]
                        c['source_references'].append(bridgepath)
                        c['blockers'].remove('IDENTITY_NOT_AVAILABLE_BY_CUTOFF')
                if c['status']!='EXCLUDED_TRAINING_RULE':c['status']='BLOCKED' if c['blockers'] else 'READY_CONDITIONAL'
                out['blockers'] += [c['ticker']+':'+blocker for blocker in c['blockers']]
            exclusions={c['ticker']:dict(reason='INSUFFICIENT_253_SESSION_PREDECISION_HISTORY',known_asof=day,source_references=[eligibilitypath]) for c in candidates if c['status']=='EXCLUDED_TRAINING_RULE'}
            out.update(candidates=candidates,training_dates=prepared['training_dates'],
                admission=dict(status='REVIEWED_CONDITIONAL',decision_date=day,members=out['members'],
                    training_exclusions=exclusions,source_references=[earlypath,bridgepath,eligibilitypath]),
                previous_blockers=previous['blockers'])
        for c in out.get('candidates',[]):
            c['source_available_by_cutoff']=c.get('identity_available_by_cutoff')
            c['mapping_retrospective']=bool(c.get('retrospective_identity_bridge'))
            c['sec_acceptance_timestamp']=None
        if not out['blockers']:
            arguments=compile_monthly_training_window(window=dict(decision_cutoff=day,training_dates=out['training_dates'],candidates=out['candidates']),source_hashes=pins,admission=out['admission'])
            if not is_early and arguments!=previous['compiled_search_arguments']:raise ValueError('LATER_ARGUMENTS_CHANGED:'+day)
            out.update(compiled_search_arguments=arguments,status='PURE_COMPILED_CONDITIONAL_NOT_EXECUTION_ADMITTED')
        else:out.update(compiled_search_arguments=None,status='BLOCKED')
        windows.append(out)
    for p,h in pins.items():
        if hashlib.sha256((ROOT/p).read_bytes()).hexdigest()!=h:raise ValueError('SOURCE_CHANGED_DURING_RUN:'+p)
    result=dict(schema='OLD_WINDOWS_UNIFIED_RAW_COMPILATION_V3',windows=windows,source_hashes=pins,
        window_count=len(windows),pure_compiled_windows=sum(w['compiled_search_arguments'] is not None for w in windows),
        search_calls=0,economic_runs=0,execution_authorized=False,membership_pit_certified=False,
        short_history_exclusions=[r for r in eligibility['rows'] if r['status']=='EXCLUDED_SHORT_REGULAR_HISTORY'],
        limitations=base['limitations'][:-1]+[
            'Early windows use exact-overlap raw segments and explicit nominal calibration. June extensions are not new independent daily anchors.',
            'Retrospective identity bridges preserve original availability false or unknown; signed dates are not SEC acceptance timestamps.',
            'Uncertain HONA membership remains outside the known domain and has its separate lawful short-history exclusion.'])
    target=ROOT/'tmp/old_window_source_reuse_20261026/unified_raw_compilation_v3.json'
    target.write_text(json.dumps(result,indent=2),encoding='utf-8')
    print(json.dumps({k:result[k] for k in ('window_count','pure_compiled_windows','search_calls','economic_runs')}))

if __name__=='__main__':main()
