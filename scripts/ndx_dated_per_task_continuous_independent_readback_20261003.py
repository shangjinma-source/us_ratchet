"""Independent candidate-only Fraction oracle. Shared original8 is never rerun."""
import argparse
from copy import deepcopy
from decimal import Context,Decimal,localcontext
from fractions import Fraction as F
import hashlib,json,os
from pathlib import Path

SOURCE=Path(__file__).resolve();ROOT=SOURCE.parents[1];LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PRODUCER=ROOT/'scripts/ndx_dated_per_task_continuous_20261003.py';PRODUCER_SHA='d6ece8c31eefd25ec019b1acbb0f9d5a8b25403e2b0065f56b5c03acd5584464'
INPUT_READER=ROOT/'scripts/ndx_dated_account_input_independent_readback_20261003.py';INPUT_READER_SHA='688685ffffad650b30647cf2be5205aacf819b1aed5215867b0d4c565ed22295'
BASE=ROOT/'data/cache/research/dated_per_task_continuous_weight_diagnostic_20261003_v1'
INPUT_ROOT=ROOT/'data/cache/research/dated_account_inputs_20261003_v1'
FIRST='89d4f76f1ca92a9d3c3541b3f796f03d0d821977da1cd720c58d455a470c56b3'
CONTROL=dict(path=str(ROOT/'data/cache/research/dated_continuous_weight_diagnostic_20261003_v1/diagnostic.json'),sha256='bb81bc97c9bb5564afeab9eed4a1421e40fe5274ae29807ce9994bd7b70b8c7f')
CONTROL_PUB=dict(path=str(ROOT/'data/cache/research/dated_continuous_weight_diagnostic_20261003_v1/publication.json'),sha256='ad10068b3b2efa98ce13cdef62c52d096c085680343078a8c429daf5225144d8')
CONTROL_AUDIT=dict(path=str(ROOT/'DYNAMIC_DATED_CONTINUOUS_INDEPENDENT_READBACK_20261003.json'),sha256='3dca84ea418360f1c039c437614c0887966c665cdfbf4c5c0c99484659d42057')
FALSE=('account_executed','fit_performed','raw_prices_decoded','old_audit_repeated','point_in_time_verified','promotion_allowed','formal_cohort_verified','future_independent_oos','untouched_holdout','full_transitive_source_closure_reverified','integer_shares_computed','fund_account_computed','control_diagnostic_recomputed','integer_rejection_overridden','weights_normalized')
TRACK_FALSE=('formal_cohort_verified','point_in_time_verified','promotion_allowed','future_independent_oos','untouched_holdout','accounting_conservation_verified','dividends_included','corporate_actions_complete','weights_refitted','weights_normalized','daily_rebalancing_performed')
def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b,msg):require(enc(a)==enc(b),msg)
def canonical(v):require(type(v) is str and len(v)==64 and all(c in '0123456789abcdef' for c in v),'Canonical SHA/ID')
def ratio(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def display(v):
    with localcontext(Context(prec=80)):return str(Decimal(v.numerator)/Decimal(v.denominator))
def check_ref(r):
    require(type(r) is dict and set(r)=={'path','sha256'} and type(r['path']) is str and r['path'],'External ref');canonical(r['sha256'])
def merge(s,p,h):canonical(h);require(p not in s or s[p]==h,'Source conflict');s[p]=h
def read(r,sources):
    check_ref(r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'External bytes');merge(sources,r['path'],r['sha256'])
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON');out[k]=v
        return out
    def invalid(v):raise ValueError('Nonfinite JSON')
    return json.loads(b,object_pairs_hook=pairs,parse_constant=invalid)
def guard(sources):
    s=dict(sources)
    for p,h in ((SOURCE,LOADED_SHA),(PRODUCER,PRODUCER_SHA),(INPUT_READER,INPUT_READER_SHA)):merge(s,str(p),h)
    for p,h in s.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)

def inspect_candidate(track,inputs,input_reference):
    a=inputs['candidate'];cal=inputs['calendar'];order=a['original_security_order'];targets=a['schedule'][0]['targets']
    require(len(cal)==127 and cal==sorted(set(cal)) and cal[0]=='2026-03-20' and cal[1]=='2026-03-23' and cal[-1]=='2026-09-21','Exact127 calendar')
    require(len(order)==len(set(order)) and set(order)==set(targets)==set(inputs['original_fit_result']['targets']),'Full original support inclzero')
    weights={s:F(str(targets[s]['target_weight'])) for s in order};require(all(w>=0 for w in weights.values()) and sum(weights.values())>0,'Nonnegative original weight mass')
    exact({s:targets[s]['target_weight'] for s in order},{s:t['target_weight'] for s,t in inputs['original_fit_result']['targets'].items()},'Raw target weights unchanged')
    require(type(a['transaction_cost_bps']) is int and a['transaction_cost_bps']==10 and a['weights_normalized'] is False and a['nominal_prices_adjusted_again'] is False,'Original fractional policy')
    positions=[dict(security_id=s,ticker=a['original_ticker_by_security'][s],issuer_id=targets[s]['issuer_id'],target_weight=targets[s]['target_weight']) for s in order]
    events=[];by={}
    for s in order:
        qs=a['exact_quote_conversion_evidence'][s];require([q['session'] for q in qs]==cal,'All exact quote dates')
        for q in qs:
            for f in ('open','close'):
                v=F(q[f]['exact']);require(v>0 and type(q[f]['value']) is float and float(v)==q[f]['value'] and q[f]['value'].hex()==q[f]['float_hex'],'Bound exact-to-float evidence')
        for binding in a['split_evidence_preserved'][s]:
            e=binding['event'];require(e['security_id']==s and e['session'] in cal and (s,e['session']) not in by,'Unique action SID/date')
            for k in ('new_shares','old_shares'):require(type(e[k]) is int and e[k]>0,'Integer ratio')
            by[(s,e['session'])]=F(e['new_shares'],e['old_shares']);events.append(dict(security_id=s,effective_session=e['session'],numerator=str(e['new_shares']),denominator=str(e['old_shares']),source_reference=deepcopy(binding['policy_reference']),original_event_preserved=deepcopy(e)))
    exact([e['original_event_preserved'] for e in events],a['corporate_actions'],'Complete action list')
    path=[];values=[]
    for i,d in enumerate(cal):
        rows=[];total=F(0)
        for s in order:
            quantity=F(0)
            if i:
                quantity=weights[s]/F(a['exact_quote_conversion_evidence'][s][1]['open']['exact'])
                # Entry-day action is before the purchase, never applied again.
                for (sid,event_day),factor in by.items():
                    if sid==s and cal[1]<event_day<=d:quantity*=factor
            close=F(a['exact_quote_conversion_evidence'][s][i]['close']['exact']);gross=quantity*close;net=gross*F(999,1000);total+=net
            row=dict(security_id=s,fractional_quantity=ratio(quantity),contribution_before_cost=ratio(gross),contribution_after_cost=ratio(net))
            if i:row.update(nominal_close_exact=ratio(close),split_ratio_before_purchase_or_mark=ratio(by.get((s,d),F(1))),entry_purchase=i==1)
            rows.append(row)
        value=total if i else F(1);values.append(value);path.append(dict(session=d,normalized_value=ratio(value),normalized_value_display=display(value),role='FIXED_FRACTIONAL_HOLDINGS_CLOSE_MARK' if i else 'INITIAL_REFERENCE_ONE_NOT_INVESTED_ACCOUNT',security_rows=rows))
    # Independent all ordered pairs establishes maxdrawdown, including initial1.
    dd=max(F(0),max(1-values[j]/values[i] for i in range(127) for j in range(i,127)))
    peak=values[0];pi=0;worst=F(0);pair=(0,0)
    for j,v in enumerate(values):
        if v>peak:peak=v;pi=j
        if 1-v/peak>worst:worst=1-v/peak;pair=(pi,j)
    require(worst==dd,'Independent drawdown definitions agree')
    expected=dict(schema='DATED_FIXED_FRACTIONAL_WEIGHT_DIAGNOSTIC_V1',calendar=deepcopy(cal),positions_preserved=positions,split_events_preserved=events,source_references_preserved=dict(inputs=dict(input_reference,json_pointer='/inputs/candidate'),complete_original_track_preserved=deepcopy(a)),transaction_cost_bps_preserved=10,weight_sum_exact=ratio(sum(weights.values())),scalar_encoding='FLOAT_TO_STR_THEN_EXACT_DECIMAL_FRACTION;EXACT_RATIONAL_QUOTES',role='frozen_target_weight_daily_return_comparability',cost_policy='ONCE_MULTIPLICATIVE_ONE_MINUS_COST_ON_ALL_POST_ENTRY_VALUES_NOT_DAILY_FEE',path=path,interval_count=126,cumulative_return_exact=ratio(values[-1]-1),annualized_return_exact=ratio(values[-1]**2-1),annualization_exponent_exact=ratio(F(2)),max_drawdown_exact=ratio(dd),drawdown_peak_index=pair[0],drawdown_trough_index=pair[1],drawdown_peak_session=cal[pair[0]],drawdown_trough_session=cal[pair[1]],evaluation_interval_previously_used_for_fitting=True,**dict.fromkeys(TRACK_FALSE,False))
    exact(track,expected,'Complete independent candidate path/metadata/metrics')
    return dict(point_count=127,security_point_count=127*len(order),split_event_count=len(events),zero_weight_count=sum(w==0 for w in weights.values()),return_exact=ratio(values[-1]-1),annualized_return_exact=ratio(values[-1]**2-1),maximum_drawdown_exact=ratio(dd))

def validate_links(task_id,docs,refs):
    d,p,started,inp,pub,audit,control=map(docs.__getitem__,('diagnostic','publication','started','inputs','input_publication','input_readback','control_audit'))
    require(d['schema']=='SOURCE_BOUND_DATED_PER_TASK_CONTINUOUS_DIAGNOSTIC_V1' and p['schema']=='DATED_PER_TASK_CONTINUOUS_PUBLICATION_V1' and p['status']=='PUBLISHED_CANDIDATE_DIAGNOSTIC_WITH_IMMUTABLE_CONTROL_REFERENCE','New published candidate only')
    exact(p['diagnostic_reference'],refs['diagnostic'],'Publication target');exact(p['source_hashes'],d['source_hashes'],'Diagnostic sources');require(d['source_hashes'][str(PRODUCER)]==PRODUCER_SHA,'Actual producer source')
    require(started['schema']=='DATED_PER_TASK_CONTINUOUS_STARTED_V1' and started['task_id']==task_id and type(started['planned_candidate_core_call_count']) is int and started['planned_candidate_core_call_count']==1 and type(started['planned_control_core_call_count']) is int and started['planned_control_core_call_count']==0,'Started scope')
    expectedrefs=dict(inputs=refs['inputs'],readback=refs['input_readback'],publication=refs['input_publication']);exact(d['input_references'],expectedrefs,'Explicit inputs');exact(started['input_references'],expectedrefs,'Started input linkage');exact(started['source_hashes'],d['source_hashes'],'Started sources')
    require(inp['schema']=='DATED_ACCOUNT_INPUT_DOCUMENT_V1' and pub['status']=='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED','Audited input publication');exact(pub['inputs_reference'],refs['inputs'],'Input bytes');exact(pub['source_hashes'],inp['source_hashes'],'Input sources')
    require(audit['schema']=='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1' and audit['status']=='PASS' and audit['reader_sha256']==INPUT_READER_SHA,'Independent input audit');exact(audit['inputs_reference'],refs['inputs'],'Audit input');exact(audit['publication_reference'],refs['input_publication'],'Audit receipt')
    task=inp['inputs']['original_task'];require(task['numerical_task_id']==task_id==sha(enc(task['numerical_identity'])) and task['numerical_identity']['cutoff']=='2026-03-20','Dated numeric identity');exact(d['original_task_preserved'],task,'Full task preserved')
    exact(d['immutable_control_reference'],dict(CONTROL,json_pointer='/tracks/incumbent'),'Immutable control pointer');exact(d['immutable_control_publication_reference'],CONTROL_PUB,'Control pub');exact(d['immutable_control_readback_reference'],CONTROL_AUDIT,'Existing control audit');exact(started['immutable_control_reference'],CONTROL,'Started control')
    require(control['schema']=='DATED_CONTINUOUS_INDEPENDENT_READBACK_V1' and control['status']=='PASS','Saved original8 independent result');exact(control['diagnostic_reference'],CONTROL,'Control audit target');exact(control['publication_reference'],CONTROL_PUB,'Control audit receipt')
    saved_control=docs['control_document']['tracks']['incumbent'];exact(saved_control['calendar'],inp['inputs']['calendar'],'Control calendar unchanged')
    original=saved_control['source_references_preserved']['complete_original_track_preserved'];current=inp['inputs']['incumbent']
    for key in ('matrices','schedule','risk_chains_by_decision','corporate_actions','initial_cash_usd','minimum_cash_buffer_usd','transaction_cost_bps','valuation_end_date','external_cashflows','initial_holdings','risk_parameters','original_security_order','original_ticker_by_security'):exact(current[key],original[key],'Same immutable control contract '+key)
    require(task['numerical_identity']['requested_previous_target_weights'] is None,'Original None prior')
    for key,expected in [('original_input_limitations',inp['inputs']['limitations']),('original_provenance_and_missing',inp['original_provenance_and_missing']),('preserved_evidence_sidecars',inp['preserved_evidence_sidecars'])]:exact(d[key],expected,'Complete evidence '+key)
    require(type(d['candidate_core_call_count']) is int and d['candidate_core_call_count']==1 and type(d['control_core_call_count']) is int and d['control_core_call_count']==0,'Only one candidate computation')
    for obj in (d,p,started):
        for k in FALSE:require(obj[k] is False,'No output authority upgrade')
    for obj in (inp,pub,audit,control):
        for k in ('point_in_time_verified','promotion_allowed','account_executed','fit_performed'):require(obj[k] is False,'No input authority')
    require(d['integer_account_status_consumed'] is False and d['integer_execution_or_rejection_inferred'] is False and d['evaluation_interval_previously_used_for_fitting'] is True,'Separate diagnostic role')

def readback(task_id,publication_reference,*,execute=False):
    canonical(task_id);require(type(execute) is bool and execute and task_id!=FIRST,'Explicit new-task-only readback')
    folder=BASE/task_id;require(Path(publication_reference['path'])==folder/'publication.json' and {p.name for p in folder.iterdir()}=={'started.json','diagnostic.json','publication.json'},'New exact three-file diagnostic, no retry')
    sources={str(SOURCE):LOADED_SHA};guard(sources);p=read(publication_reference,sources);refs=dict(publication=publication_reference,diagnostic=p['diagnostic_reference']);require(Path(refs['diagnostic']['path'])==folder/'diagnostic.json','Fixed diagnostic path');d=read(refs['diagnostic'],sources)
    started_path=folder/'started.json';refs['started']=dict(path=str(started_path),sha256=d['source_hashes'].get(str(started_path),'') or sha(started_path.read_bytes()));started=read(refs['started'],sources)
    for role,key,name in [('inputs','inputs','inputs.json'),('input_readback','readback','independent_readback.json'),('input_publication','publication','publication.json')]:
        refs[role]=d['input_references'][key];require(Path(refs[role]['path'])==INPUT_ROOT/task_id/name,'Fixed task input paths')
    require({x.name for x in (INPUT_ROOT/task_id).iterdir()}=={'started.json','inputs.json','publication.json','independent_readback.json'},'Audited inputs only')
    docs=dict(publication=p,diagnostic=d,started=started)
    for role in ('inputs','input_readback','input_publication'):docs[role]=read(refs[role],sources)
    docs['control_audit']=read(CONTROL_AUDIT,sources)
    docs['control_document']=read(CONTROL,sources)
    for path,h in d['source_hashes'].items():merge(sources,path,h)
    guard(sources);validate_links(task_id,docs,refs);counts=inspect_candidate(d['candidate'],docs['inputs']['inputs'],refs['inputs']);guard(sources)
    result=dict(schema='DATED_PER_TASK_CONTINUOUS_INDEPENDENT_READBACK_V1',status='PASS',numerical_task_id=task_id,diagnostic_reference=refs['diagnostic'],publication_reference=publication_reference,inputs_reference=refs['inputs'],input_readback_reference=refs['input_readback'],started_reference=refs['started'],started_reference_role='CURRENT_BYTES_STRUCTURALLY_LINKED_TO_EXTERNALLY_ANCHORED_DIAGNOSTIC_NOT_EXTERNALLY_PINNED',immutable_control_readback_reference=CONTROL_AUDIT,counts=counts,source_hashes=sources,reader_sha256=LOADED_SHA,candidate_only_arithmetic_recomputed=True,producer_called=False,**dict.fromkeys(FALSE,False))
    require({p.name for p in folder.iterdir()}=={'started.json','diagnostic.json','publication.json'},'No concurrent reader')
    out=folder/'independent_readback.json';b=enc(result)
    with out.open('xb') as f:f.write(b);f.flush();os.fsync(f.fileno())
    guard(sources);require(out.read_bytes()==b and {p.name for p in folder.iterdir()}=={'started.json','diagnostic.json','publication.json','independent_readback.json'},'Final audit bytes and exact namespace');return dict(path=str(out),sha256=sha(b))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--task-id',required=True);parser.add_argument('--publication-sha256',required=True);parser.add_argument('--execute',action='store_true');a=parser.parse_args();print(json.dumps(readback(a.task_id,dict(path=str(BASE/a.task_id/'publication.json'),sha256=a.publication_sha256),execute=a.execute)))
