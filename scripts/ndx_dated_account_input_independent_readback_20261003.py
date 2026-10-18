"""Read saved account inputs independently; never import assemblers or engines."""
import argparse
import hashlib
import json
import math
import os
from fractions import Fraction
from pathlib import Path

ROOT=Path(__file__).resolve().parents[1]
SOURCE=Path(__file__).resolve()
LOADED_SHA=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
CORE=ROOT/'backtest/ndx_dated_account_input_research.py'
CORE_SHA='319c80d23dad7e50eacb219206c5a5a3dd58bee41dc51b69e424a84f3c5b360e'
OWNER=ROOT/'scripts/ndx_dated_account_inputs_20261003.py'
OWNER_SHA='67ae96e5d71053606a9cfc28694af193cb92449ca02671aada755a3e2395c5ee'
INPUT_FLAGS=('account_executed','fit_performed','source_bytes_authenticated','split_evidence_authenticated','historical_identity_verified','provider_binding_verified','point_in_time_verified','promotion_allowed','legal_training_input_admitted','execution_authorized','untouched_holdout','future_independent_oos','corporate_action_completeness_verified','dividend_cash_flows_modelled','total_return_modelled')

def require(ok,message):
    if not ok:raise ValueError(message)

def encode(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(blob):return hashlib.sha256(blob).hexdigest()
def exact(a,b,message):require(encode(a)==encode(b),message)
def read(reference,sources):
    require(set(reference)=={'path','sha256'},'Exact external reference')
    path=reference['path'];blob=Path(path).read_bytes();h=sha(blob)
    require(h==reference['sha256'] and (path not in sources or sources[path]==h),'External bytes/source conflict')
    sources[path]=h
    def pairs(items):
        out={}
        for k,v in items:require(k not in out,'Duplicate JSON key');out[k]=v
        return out
    return json.loads(blob,object_pairs_hook=pairs)

def pointer(value,path):
    require(type(path) is str and path.startswith('/'),'JSON pointer')
    for part in path[1:].split('/'):
        part=part.replace('~1','/').replace('~0','~')
        value=value[int(part)] if isinstance(value,list) else value[part]
    return value

def inspect(document,parents):
    inputs=document['inputs'];task=pointer(parents['preparation'],document['task_reference']['json_pointer'])
    exact(inputs['original_task'],task,'Original numerical task');fit=parents['raw']['fitted']
    exact(inputs['original_fit_result'],fit,'Original returned weights')
    exact(inputs['original_candidate_coordinates'],task['numerical_identity']['selected'],'Original coordinates')
    require(inputs['schema']=='DATED_CONDITIONAL_ACCOUNT_INPUTS_V1','New input schema')
    for key in INPUT_FLAGS:require(inputs[key] is False,'Input authority '+key)
    calendar=parents['channels']['calendar253'][126:]
    require(len(calendar)==127 and calendar[0]=='2026-03-20' and calendar[1]=='2026-03-23' and calendar[-1]=='2026-09-21','Explicit evaluation calendar')
    exact(inputs['calendar'],calendar,'127 calendar');require(type(inputs['valuation_point_count']) is int and inputs['valuation_point_count']==127 and type(inputs['return_interval_count']) is int and inputs['return_interval_count']==126,'Dimensions')
    selected=task['numerical_identity']['selected'];original=[r['original_control_security'] for r in parents['control']['rows']]
    exact(inputs['original_incumbent_definition'],original,'Unchanged ordered original8')
    candidate_rows={r['coordinate']['security_id']:(i,r) for i,r in enumerate(parents['channels']['rows'])}
    control_rows={r['original_control_security']['security_id']:(i,r) for i,r in enumerate(parents['control']['rows'])}
    union=set(selected)|set(control_rows)
    aliases={sid:'SID_'+sid[len('security:'):].replace(':','_').upper() for sid in sorted(union)}
    require(len(set(aliases.values()))==len(union),'Unique engine aliases')
    exact(inputs['engine_security_keys'],aliases,'Original SID alias map')
    cells=0;events=0
    for role in ('candidate','incumbent'):
        account=inputs[role];coordinates=selected if role=='candidate' else {r['security_id']:r for r in original}
        order=sorted(selected) if role=='candidate' else [r['security_id'] for r in original]
        weights={s:fit['targets'][s]['target_weight'] if role=='candidate' else coordinates[s]['target_weight'] for s in order}
        exact(account['original_security_order'],order,'Account SID order')
        exact(account['original_ticker_by_security'],{s:coordinates[s]['ticker'] for s in order},'Actual tickers')
        exact(account['engine_ticker_by_security'],{s:aliases[s] for s in order},'Alias tickers')
        expected_schedule=[dict(decision_date=calendar[0],execution_date=calendar[1],targets={s:dict(ticker=aliases[s],issuer_id=coordinates[s]['issuer_id'],target_weight=weights[s]) for s in order})]
        exact(account['schedule'],expected_schedule,'Close nextOpen schedule, original weights')
        exact(account['risk_chains_by_decision'],{calendar[0]:{s:coordinates[s]['risk_chain'] for s in order}},'Original risk labels')
        risk={k:v for k,v in task['numerical_identity']['parameters'].items() if k not in ('fit_days','shrinkage_intensity','turnover_anchor_strength')}
        exact(account['risk_parameters'],risk,'All original risk constraints')
        require(account['split_application_order']=='BEFORE_OPEN_MARK_AND_EXECUTION_BY_FROZEN_ENGINE;PENDING_BASKET_CANCELLED_ON_SPLIT','Split order')
        require(account['engine_weight_semantics']==('FROZEN_CANDIDATE_NORMALIZES_POSITIVE_TARGET_WEIGHTS' if role=='candidate' else 'CONTROL_RESTORES_ORIGINAL_WEIGHTS_AFTER_POSITIVE_TARGET_NORMALIZATION'),'Engine weight semantics')
        matrices={field:dict(index=calendar,columns=[aliases[s] for s in order],data=[[] for _ in calendar]) for field in ('open','close')}
        actions=[]
        for sid in order:
            if sid in selected:
                index,row=candidate_rows[sid];reference=dict(document['input_references']['channels'],json_pointer=f'/rows/{index}/channel')
            else:
                index,row=control_rows[sid];reference=dict(document['input_references']['control'],json_pointer=f'/rows/{index}/channel')
            channel=row['channel']
            if sid in selected and sid in control_rows:exact(channel,control_rows[sid][1]['channel'],'Shared candidate/control channel')
            exact(account['complete_channels_preserved'][sid],channel,'Saved full channel')
            evidence=[]
            for i,quote in enumerate(channel['quote_rows'][126:]):
                require(quote['session']==calendar[i],'Every quote date');record=dict(session=calendar[i])
                for field in ('open','close'):
                    rational=Fraction(quote['nominal_'+field+'_exact']);number=float(rational)
                    require(rational>0 and math.isfinite(number),'Positive nominal conversion')
                    matrices[field]['data'][i].append(number);cells+=1
                    record[field]=dict(exact=str(rational),value=number,float_hex=number.hex(),source_reference=reference,json_pointer=reference['json_pointer']+f'/quote_rows/{126+i}/nominal_{field}_exact')
                evidence.append(record)
            exact(account['exact_quote_conversion_evidence'][sid],evidence,'Every exact/float/hex/source quote')
            bound=[]
            for policy in channel['event_policies']:
                if not calendar[0]<policy['session']<=calendar[-1]:continue
                matches=[(i,r) for i,r in enumerate(parents['registry']['events']) if r['ticker']==channel['ticker'] and r['first_adjusted_trading_date']==policy['session']]
                require(len(matches)==1,'Unique recorded split');i,r=matches[0]
                exact([r['new_shares'],r['old_shares']],[policy['numerator'],policy['denominator']],'Split ratio')
                action=dict(security_id=sid,session=policy['session'],new_shares=r['new_shares'],old_shares=r['old_shares'],source_url=r['source_url'],evidence_sha256=r['raw_sha256'])
                actions.append(action);events+=1
                bound.append(dict(event=action,policy_reference=dict(document['input_references']['registry'],json_pointer=f'/events/{i}')))
            exact(account['split_evidence_preserved'][sid],bound,'Full split bindings')
        exact(account['matrices'],matrices,'Complete engine matrices');exact(account['corporate_actions'],actions,'Original SID split actions')
        for key,value in dict(initial_cash_usd=25000,minimum_cash_buffer_usd=100,transaction_cost_bps=10,valuation_end_date=calendar[-1],external_cashflows=[],identity_events=[],initial_holdings={},initial_point_included=True,weights_normalized=False,nominal_prices_adjusted_again=False,risk_observation_gates_orders=role=='candidate',candidate_normalization_required_by_engine=role=='candidate').items():exact(account[key],value,'Account contract '+key)
        nonpositive=[s for s in order if weights[s]==0]
        exact(account['engine_input_compatibility'],dict(status='BLOCKED_NONPOSITIVE_TARGET' if nonpositive else 'REQUIRES_FROZEN_VALIDATION',nonpositive_target_security_ids=nonpositive),'No zero target dropped')
        exact(account['engine_dispatch_blockers'],['FROZEN_ENGINE_REQUIRES_STRICTLY_POSITIVE_TARGET_WEIGHTS'] if nonpositive else [],'Dispatch blockers')
        require(account['engine_input_status']==('BLOCKED_ZERO_TARGET_WEIGHT' if nonpositive else 'STRUCTURALLY_ASSEMBLED_CONDITIONAL_INPUT'),'Input compatibility status')
        require(account['role']==role,'Account role')
        for key in INPUT_FLAGS:require(account[key] is False,'No account permission')
    norm=inputs['candidate_engine_normalization_evidence'];order=list(selected);weights={s:float(fit['targets'][s]['target_weight']) for s in order};total=sum(weights[s] for s in order)
    exact(norm['ordered_security_ids'],order,'Normalizer order');exact(norm['float_total'],total,'Original float summation')
    exact(norm['original_weights'],{s:fit['targets'][s]['target_weight'] for s in order},'Original saved weights')
    exact(norm['effective_weights'],{s:weights[s]/total for s in order} if all(w>0 for w in weights.values()) else None,'Frozen effective candidate weights')
    require(norm['control_weights_normalized'] is False,'Control normalization forbidden')
    exact(norm['normalizer_source_reference'],document['input_references']['normalizer'],'Frozen normalizer source')
    require(norm['semantics']=='SAME_FLOAT_SUM_AND_DIVISION_AS_FROZEN_NORMALISE_TARGETS;NOT_AN_ENGINE_EXECUTION' and norm['blocked_nonpositive'] is any(w<=0 for w in weights.values()),'Normalizer input semantics')
    exact(document['original_provenance_and_missing'],parents['channels']['original_provenance_and_missing'],'Complete101 provenance')
    exact(document['preserved_evidence_sidecars'],parents['channels']['preserved_evidence_sidecars'],'All7 evidence layers')
    return dict(quote_value_count=cells,split_event_count=events,candidate_security_count=len(selected),incumbent_security_count=8,calendar_count=127)

def run(inputs_reference,publication_reference):
    require(sha(SOURCE.read_bytes())==LOADED_SHA,'Loaded reader source drift')
    require(type(OWNER_SHA) is str and sha(OWNER.read_bytes())==OWNER_SHA,'Reviewed producer pin pending/drift')
    require(sha(CORE.read_bytes())==CORE_SHA,'Reviewed core drift')
    sources={str(SOURCE):LOADED_SHA,str(OWNER):OWNER_SHA,str(CORE):CORE_SHA}
    document=read(inputs_reference,sources);publication=read(publication_reference,sources)
    require(document['schema']=='DATED_ACCOUNT_INPUT_DOCUMENT_V1' and publication['schema']=='DATED_ACCOUNT_INPUT_PUBLICATION_V1' and publication['status']=='PUBLISHED_CONDITIONAL_INPUT_NOT_EXECUTED','Published inputs')
    exact(publication['inputs_reference'],inputs_reference,'External publication anchor');exact(publication['source_hashes'],document['source_hashes'],'Publisher source map')
    for path,h in document['source_hashes'].items():
        require(path not in sources or sources[path]==h,'Source conflict');require(sha(Path(path).read_bytes())==h,'Direct saved source bytes');sources[path]=h
    parents={}
    for role in ('preparation','channels','control','registry'):parents[role]=read(document['input_references'][role],sources)
    report=read(document['independent_readback_reference'],sources);parents['raw']=read(report['raw_reference'],sources)
    require(report['status']=='PASSED' and report['attempt_outcome'] in ('RISK_PASSED','RISK_FAILED'),'Independent returned task')
    exact(document['saved_readback'],report,'Preserved fit audit')
    counts=inspect(document,parents)
    folder=Path(inputs_reference['path']).parent;require({p.name for p in folder.iterdir()}=={'started.json','inputs.json','publication.json'},'Unique complete input namespace')
    result=dict(schema='DATED_ACCOUNT_INPUT_INDEPENDENT_READBACK_V1',status='PASS',inputs_reference=inputs_reference,publication_reference=publication_reference,reader_sha256=sources[str(SOURCE)],source_hashes=sources,**counts,producer_called=False,fit_performed=False,account_executed=False,old_raw_audit_repeated=False,point_in_time_verified=False,promotion_allowed=False)
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Final source drift')
    output=folder/'independent_readback.json';blob=encode(result)
    with output.open('xb') as f:f.write(blob);f.flush();os.fsync(f.fileno())
    require(output.read_bytes()==blob,'Durable independent result')
    for path,h in sources.items():require(sha(Path(path).read_bytes())==h,'Post-publication source drift')
    return dict(path=str(output),sha256=sha(blob))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--inputs-path',required=True);parser.add_argument('--inputs-sha',required=True);parser.add_argument('--publication-sha',required=True);args=parser.parse_args()
    print(json.dumps(run(dict(path=str(Path(args.inputs_path).resolve()),sha256=args.inputs_sha),dict(path=str(Path(args.inputs_path).resolve().with_name('publication.json')),sha256=args.publication_sha))))
