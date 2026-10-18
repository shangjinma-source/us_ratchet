"""Independent typed-matrix and Decimal risk readback; never invokes a fitter."""
import argparse
from copy import deepcopy
from datetime import datetime
from decimal import Decimal,localcontext
import hashlib
import json
import math
from pathlib import Path
import sys
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_root_price_archive_contract_research as archive
BASE=ROOT/'data/cache/research/corrected_frontier_cutoff_archive_20260919_v1'
EXECUTION=BASE/'20230403_first_non_equal_refit.json'
EXECUTION_SHA='4d6846dfe7283716985ac663ff42a7409320c53c51e28b4b694af71e33231df0'
QUEUE=BASE/'20230403_queue.json';QUEUE_SHA='8958f310aca0263e4e88eb124a09cda70a312ac50345203d4c22c63605963f90'
CONTEXT_SHA='e270220f666c835bd21e80099ddba3e8a6b8531e296af2764f578de4ed14c9a2'
CONTEXT=ROOT/'data/cache/research/ndx_joint_weight_runs_v3'/CONTEXT_SHA/'context.json'
CORRECTIONS=(('GOOG','2022-07-18',0.,-.025335378898117544),('GOOGL','2022-07-18',0.,-.024580059928059006),('FTNT','2022-06-23',0.,.019968386675822902))
LOADED={str(p):archive.drift.file_sha(p) for p in (Path(__file__).resolve(),archive.SOURCE,archive.drift.SOURCE)}
PARAMETERS=('fit_days','shrinkage_intensity','turnover_anchor_strength','max_single_weight','min_single_weight','top_weight_cap','minimum_effective_n_ratio','risk_chain_top1_cap')


def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,separators=(',',':'),ensure_ascii=False,allow_nan=False).encode()).hexdigest()
def decode(value):
    if not isinstance(value,dict):return value
    if set(value)=={'float_hex'}:
        number=float.fromhex(value['float_hex'])
        if not math.isfinite(number):raise ValueError('Nonfinite encoded input')
        return number
    if set(value)=={'timestamp'}:return value['timestamp']
    if set(value)=={'mapping'}:return {k:decode(v) for k,v in value['mapping'].items()}
    if set(value)=={'items','sequence_type'} and value['sequence_type']=='list':return [decode(v) for v in value['items']]
    raise ValueError('Unsupported typed coordinate')
def positive(v):
    if type(v) not in (int,float) or not math.isfinite(v) or v<0:raise ValueError('Finite nonboolean nonnegative value required')
    return Decimal(str(v))


def risk_checks(fitted,selected,parameters):
    if (set(fitted['targets'])!=set(selected) or fitted['previous_target_weights']!={}
        or any(type(fitted[k]) not in (int,float) or fitted[k]!=0 for k in ('effective_anchor_strength','surviving_anchor_mass'))
        or set(fitted['anchor_by_security'])!=set(selected)
        or any(type(w) not in (int,float) or w!=0 for w in fitted['anchor_by_security'].values())):raise ValueError('Zero-anchor and selected denominator differ')
    weights={}
    for sid,row in fitted['targets'].items():
        if row['ticker']!=selected[sid]['ticker'] or row['issuer_id']!=selected[sid]['issuer_id']:raise ValueError('Target identity differs')
        weights[sid]=positive(row['target_weight'])
    with localcontext() as context:
        context.prec=50;tolerance=Decimal('1e-9');total=sum(weights.values());ordered=sorted(weights.values(),reverse=True);chains={}
        if abs(total-1)>tolerance:raise ValueError('Weight sum differs')
        for sid,w in weights.items():
            chain=selected[sid]['risk_chain'];chains[chain]=chains.get(chain,Decimal(0))+w
        effective=1/sum(w*w for w in weights.values())
        checks=dict(MAX_SINGLE_WEIGHT=ordered[0]<=positive(parameters['max_single_weight'])+tolerance,
            MIN_SINGLE_WEIGHT=ordered[-1]>=positive(parameters['min_single_weight'])-tolerance,
            SECURITY_TOP3_WEIGHT=sum(ordered[:3])<=positive(parameters['top_weight_cap'])+tolerance,
            MINIMUM_EFFECTIVE_N=effective>=len(weights)*positive(parameters['minimum_effective_n_ratio'])-tolerance,
            RISK_CHAIN_TOP1_WEIGHT=max(chains.values())<=positive(parameters['risk_chain_top1_cap'])+tolerance)
    if digest(checks)!=digest(fitted['declared_constraint_checks']) or fitted['declared_constraints_passed'] is not all(checks.values()):raise ValueError('Independent five risks differ')
    return dict(checks=checks,weight_sum=str(total),effective_n=str(effective),risk_chain_weights={k:str(v) for k,v in chains.items()},tolerance='1e-9')


def inspect_context(context,queue,result):
    encoded=context['prepared_inputs']
    if set(encoded)!={'returns','nominal_prices','universe','contract','incumbent_weights','target_returns'} or digest(encoded)!=queue['input_binding']['original_typed_inputs_sha256']:raise ValueError('Whole six-input binding differs')
    returns=decode(encoded['returns']['payload']);universe=decode(encoded['universe']['payload']);parameters=decode(encoded['contract']['payload'])
    dates=[datetime.fromisoformat(d).date().isoformat() for d in returns['index']]
    if dates!=sorted(set(dates)) or any(d+'T00:00:00'!=raw for d,raw in zip(dates,returns['index'])):raise ValueError('Canonical complete daily matrix required')
    if parameters['fit_days']!=126 or {k:parameters[k] for k in PARAMETERS}!=queue['fit_parameters']:raise ValueError('Original fit contract differs')
    selected=result['candidate']['selected'];names=result['candidate']['task']['tickers'].split(';')
    rows=[dict(zip(universe['columns'],values)) for values in zip(*universe['column_values'])]
    actual={r['security_id']:{k:r[k] for k in ('ticker','issuer_id','risk_chain')} for r in rows if r['ticker'] in names}
    if digest(actual)!=digest(selected) or len(actual)!=len(names) or len({r['issuer_id'] for r in actual.values()})!=len(names):raise ValueError('Typed security/issuer/risk coordinates differ')
    corrected=deepcopy(encoded);locations=[]
    for ticker,date,old,new in CORRECTIONS:
        column=returns['columns'].index(ticker);position=dates.index(date)
        cell=corrected['returns']['payload']['mapping']['column_values']['items'][column]['items'][position]
        if set(cell)!={'float_hex'} or cell['float_hex']!=old.hex():raise ValueError('Exact original split cell differs')
        cell['float_hex']=new.hex();locations.append(dict(ticker=ticker,date=date,old=old,new=new))
    if digest(corrected)!=queue['input_binding']['corrected_typed_inputs_sha256'] or digest(locations)!=digest(queue['input_binding']['corrections']):raise ValueError('Exact full typed three-cell correction differs')
    cutoff=queue['historical_cutoff'];fit=result['refit'];days=[d for d in dates if d<=cutoff][-126:]
    if len(days)!=126 or days[-1]!=cutoff or dates[-1]!=cutoff:raise ValueError('Exact historical 126 row matrix required')
    names=[selected[s]['ticker'] for s in sorted(selected)];positions=[dates.index(d) for d in days]
    payload=dict(dates=days,tickers=names,returns=[[returns['column_values'][returns['columns'].index(t)][i] for t in names] for i in positions])
    if any(c['date']>=days[0] for c in locations):raise ValueError('This first diagnostic requires corrections strictly before fitted matrix')
    if fit['fit_start']!=days[0] or fit['fit_end']!=days[-1] or fit['cutoff']!=cutoff or type(fit['fit_row_count']) is not int or fit['fit_row_count']!=126 or fit['fit_data_sha256']!=digest(payload):raise ValueError('Saved fitted matrix differs')
    if digest(fit['declared_parameters'])!=digest({k:parameters[k] for k in PARAMETERS if k!='fit_days'}) or fit['weight_spec']!=result['candidate']['task']['weight_spec']:raise ValueError('Saved parameter/weight specification differs')
    if fit['risk_chains_by_security']!={s:r['risk_chain'] for s,r in selected.items()}:raise ValueError('Risk identity map differs')
    return dict(fit_start=days[0],fit_end=days[-1],fit_row_count=126,fit_data_sha256=digest(payload),selected=selected,
                correction_dates_outside_latest_fit=True,corrections=locations,decimal_risks=risk_checks(fit,selected,parameters))


def build():
    sources=dict(LOADED)
    def read(p,h):
        p=str(Path(p).resolve());raw=Path(p).read_bytes()
        if hashlib.sha256(raw).hexdigest()!=h:raise ValueError('Externally bound bytes differ')
        archive.merge(sources,{p:h});return json.loads(raw)
    execution=read(EXECUTION,EXECUTION_SHA);queue=read(QUEUE,QUEUE_SHA);context=read(CONTEXT,CONTEXT_SHA)
    if execution['queue']!=dict(path=str(QUEUE),sha256=QUEUE_SHA) or queue['context']!=dict(path=str(CONTEXT),sha256=CONTEXT_SHA):raise ValueError('Hard queue/context linkage differs')
    result=execution['result'];fitted=result['refit'];job=execution['job_id'];candidate,=[r for r in queue['candidates'] if r['task']['job_id']==job]
    if digest(candidate)!=digest(result['candidate']) or result['queue_sha256']!=digest(queue) or result['job_id']!=job or result['status']!='FITTED_FIVE_RISKS_PASSED':raise ValueError('One reviewed complete task required')
    started=read(execution['started_attempt']['path'],execution['started_attempt']['sha256'])
    if started['job_id']!=job or started['queue']!=execution['queue'] or started['output']!=str(EXECUTION) or started['status']!='STARTED_NOT_COMPLETED' or started['runner_source_hashes']!=execution['runner_source_hashes']:raise ValueError('Started one-shot attempt binding differs')
    for document in (queue,result):
        archive.merge(sources,document['historical_expected_source_hashes'])
        if archive.verify_expected_sources(document['historical_expected_source_hashes'],archive.load_contract())!=document['archive_resolution']:raise ValueError('Full archive source partition differs')
    archive.merge(sources,execution['runner_source_hashes']);archive.merge(sources,fitted['source_hashes'])
    for doc,fields in ((execution,('selection_performed','point_in_time_verified','promotion_allowed')),(result,('checkpoint_weights_used','selection_performed','historical_full_source_closure_verified','point_in_time_verified','promotion_allowed','whole_lot_execution_performed','forward_oos_evaluation_performed'))):
        if any(doc[k] is not False for k in fields):raise ValueError('Research scope upgraded')
    if type(result['new_cutoff_fit_attempt_count']) is not int or result['new_cutoff_fit_attempt_count']!=1 or context['runtime']!=queue['original_runtime']:raise ValueError('Original runtime/single attempt differs')
    checked=archive.verify_expected_sources(sources,archive.load_contract());details=inspect_context(context,queue,result)
    if digest(details['decimal_risks']['checks'])!=digest(result['independently_recomputed_five_checks']):raise ValueError('Saved adapter checks differ')
    checked=archive.verify_expected_sources(sources,archive.load_contract())
    return dict(schema='FIRST_CUTOFF_REFIT_INDEPENDENT_TYPED_DECIMAL_AUDIT_V1',execution=dict(path=str(EXECUTION),sha256=EXECUTION_SHA),
        queue=dict(path=str(QUEUE),sha256=QUEUE_SHA),job_id=job,details=details,historical_expected_source_hashes=sources,archive_resolution=checked,
        fitter_called=False,fitter_optimality_independently_proved=False,performance_or_dual_benchmark_pass_claimed=False,
        nominal_execution_revalidated=False,point_in_time_verified=False,promotion_allowed=False)


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('--output',required=True);args=parser.parse_args();value=build()
    with Path(args.output).open('x',encoding='utf8') as f:json.dump(value,f,sort_keys=True,indent=2,allow_nan=False);f.write('\n')
    archive.verify_expected_sources(value['historical_expected_source_hashes'],archive.load_contract())
    print(json.dumps(dict(path=str(Path(args.output).resolve()),sha256=archive.drift.file_sha(args.output),details=value['details'])))
