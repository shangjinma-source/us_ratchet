"""Independent saved-only Fraction replay; never imports a producer/account kernel."""
from pathlib import Path
from fractions import Fraction as F
from copy import deepcopy
import hashlib
import ast
import json

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'data/cache/research/first_period_incumbent_cash_flow_paths_20261003_v2'
PINS={'accounts.json':'7a9514dbe38b30196302453d833d31552ab3da62bd3fabc142e7c75e6a606d8a','publication.json':'9ce38205f97506b300a6fada34652308a87cd3f882a350d8336ad646b3412204'}
PRODUCER=ROOT/'scripts/ndx_first_period_incumbent_cash_flow_paths_v2_20261003.py'
PRODUCER_SHA='3052f58c22f2d9bcd9824dc25286eb034a1c910535fabc69e8087733263815e2'
SOURCE=Path(__file__).resolve()
LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/first_period_incumbent_cash_flow_independent_readback_20261003_v2'
CHECKS=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
FALSE=('orders_executed','point_in_time_verified','promotion_allowed','dividends_modelled','corporate_actions_modelled','fx_modelled','formal_dual_benchmark_admission','old_accounts_reexecuted','original_target_weights_modified','risk_is_order_gate','full_transitive_source_closure_reverified')

def check(ok, message):
    if not ok: raise AssertionError(message)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def rat(x): return {'numerator':str(x.numerator),'denominator':str(x.denominator)}
def value(cash,holdings,prices): return cash+sum((q*F(prices[s]) for s,q in holdings.items()),F(0))
def field(record,key,expected):
    actual=record[key]
    check(F(actual)==expected if isinstance(expected,F) else enc(actual)==enc(expected),'Mismatch '+key)

def risk(holdings,prices,metadata,parameters):
    vals={s:q*F(prices[s]) for s,q in sorted(holdings.items()) if q>0}; total=sum(vals.values(),F(0))
    common=dict(risk_is_order_gate=False,target_slot_count=len(holdings),zero_share_security_ids=sorted(s for s,q in holdings.items() if q==0),positive_holding_count=len(vals))
    if not total: return dict(common,checks={'ALL_CASH':False},all_passed=False,weights={},effective_n=None,risk_chain_weights={})
    w={s:x/total for s,x in vals.items()}; ranked=sorted(w.values(),reverse=True); chains={}
    for s,x in w.items():
        k=metadata[s]['risk_chain']; chains[k]=chains.get(k,F(0))+x
    neff=1/sum((x*x for x in w.values()),F(0)); p={k:F(v) for k,v in parameters.items()}; eps=F(1,10**9)
    tests=[ranked[0]<=p['max_single_weight']+eps,ranked[-1]>=p['min_single_weight']-eps,
           sum(ranked[:3])<=p['top_weight_cap']+eps,neff>=p['minimum_effective_n_ratio']*len(w)-eps,max(chains.values())<=p['risk_chain_top1_cap']+eps]
    return dict(common,checks=dict(zip(CHECKS,tests)),all_passed=all(tests),weights={s:rat(x) for s,x in w.items()},effective_n=rat(neff),risk_chain_weights={s:rat(x) for s,x in chains.items()})

PARENTS={'candidates': ('data/cache/research/first_period_cash_buy_hold_account_20261002_v1/accounts.json', '4112089be89d196405da8df2e1a6266eb7ad95baad992b0759e28c7c8800c792'), 'candidate_publication': ('data/cache/research/first_period_cash_buy_hold_account_20261002_v1/publication.json', 'd841df9120aead6a9cc8c0e6d003c5e4d48beed380d31fbe0d69daa032145ec9'), 'contract': ('DYNAMIC_FIRST_CASH_INCUMBENT_COMPLETION_CONTRACT_20261003.md', '5f1e59267e063a4bd5b336cd6f8b68b2a3817d918576931f666a91cea76b0c8a'), 'inputs': ('data/cache/research/first_period_standard_cash_inputs_20261002_v1/inputs.json', 'f583f6e55efeb78f0fc1c761bb2027076274012c30a7dda528ef6dee1a3004ee'), 'input_publication': ('data/cache/research/first_period_standard_cash_inputs_20261002_v1/publication.json', '304303cd9e53cb92723d4fd463f58934f3506339a2f8170ffef9cd9f258e6d47'), 'nominal': ('data/cache/research/incumbent_price_source_probe_20260912_v1/nominal_control_20260912.json', '53d2beb410c37393df266dd6709621dec27822b1b50db5d0623415b2d4ad8ac1'), 'policy': ('backtest/ndx_dynamic_frozen_incumbent_control.py', '537908ef0447b1e4e7104afdd2008d4d3d04b60f820bfaab33562dc7114f54e6'), 'execution_policy': ('backtest/ndx_dynamic_frozen_execution_research.py', '69d2bf761eac32edd8c39a9fdbffed300ba7cb4740771fbd008b4f09b204813b'), 'core': ('backtest/ndx_incumbent_cash_flow_research.py', 'e905dfaa2962e0bc52f32115093cea782ae39072b5723e07519b254762203c6e')}

PARENTS.update(prior_source=('scripts/ndx_first_period_incumbent_cash_flow_paths_20261003.py','35c9eb96ea0712a785670ad18892ef747aea4e22617a672862cdb0d2413b5265'),prior_started=('data/cache/research/first_period_incumbent_cash_flow_paths_20261003_v1/started.json','e63dfdf2278cc56d7cc6b43a1e496bfc5405ae3023fe3baccf66890bcbec0305'),prior_failure=('data/cache/research/first_period_incumbent_cash_flow_paths_20261003_v1/failure.json','3fe30f582a3c64a1ed9d668a1e30ecd872b0f0189435358bcf0ec614c51d24d6'))

def prior_evidence(refs,docs):
    raw=docs[refs['prior_source']['path']]
    check(sha(raw)==refs['prior_source']['sha256'],'Failed source exact bytes')
    failed=docs[refs['prior_failure']['path']]; oldstart=docs[refs['prior_started']['path']]
    exact(failed,dict(error='Exact original107 calendar',retry_allowed=False,status='FAILED_DO_NOT_CONSUME'),'Preserved original failure')
    check(oldstart['retry_allowed'] is False,'Original no retry')
    original={r['path']:r['sha256'] for role,r in refs.items() if not role.startswith('prior_')}
    original[refs['prior_source']['path']]=refs['prior_source']['sha256']
    exact(oldstart['source_hashes'],original,'Failed source context')
    tree=ast.parse(raw)
    functions={n.name:n for n in tree.body if isinstance(n,ast.FunctionDef)}
    body=functions['assemble'].body
    first=next(i for i,n in enumerate(body) if isinstance(n,ast.For))
    calls=[(i,n) for i,statement in enumerate(body) for n in ast.walk(statement) if isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='validate_candidates']
    check(len(calls)==1 and calls[0][0]<first,'Validation before first simulation loop')
    check(not any(isinstance(n,ast.Call) and isinstance(n.func,ast.Name) and n.func.id=='simulate' for statement in body[:first] for n in ast.walk(statement)),'No prior simulation dispatch in source')
    messages=[n for n in ast.walk(functions['validate_candidates']) if isinstance(n,ast.Constant) and n.value=='Exact original107 calendar']
    check(len(messages)==1,'Single failure location')
    calendar=docs[refs['nominal']['path']]['original_fixed_schedule']['calendar']
    check(not(len(calendar)==107 and calendar[0]=='2023-03-31' and calendar[-1]=='2023-09-01'),'Original calendar failed')
    return dict(prior_source_reference=refs['prior_source'],prior_started_reference=refs['prior_started'],prior_failure_reference=refs['prior_failure'],original_failure=failed,original_full_calendar_count=len(calendar),failure_function='validate_candidates',failure_message_line=messages[0].lineno,assemble_validation_call_line=calls[0][1].lineno,first_simulation_loop_line=body[first].lineno,inference_basis='HARD_SOURCE_CONTROL_FLOW_PLUS_EXACT_PREVALIDATION_FAILURE_AND_NO_ACCOUNT_ARTIFACT',prior_attempt_pre_dispatch_failure_only=True,prior_account_artifact_present=False,prior_runtime_execution_trace_available=False,old_failed_namespace_modified=False)

def enc(value):return json.dumps(value,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(left,right,message):check(enc(left)==enc(right),message)

def inspect_saved(account,publication,started,refs,docs,account_reference):
    check(account['schema']=='FIRST_PERIOD_INCUMBENT_TWO_PATHS_EIGHT_SCENARIOS_V2','New V2 account schema')
    check(publication['schema']=='FIRST_PERIOD_INCUMBENT_CASH_FLOW_PATHS_PUBLICATION_V2' and publication['status']=='PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS','V2 publication')
    exact(publication['account_reference'],account_reference,'Account publication link')
    prior=prior_evidence(refs,docs)
    for obj in (account,publication):
        check(obj['prior_attempt_pre_dispatch_failure_only'] is True,'Pre-dispatch inference preserved')
        exact(obj['prior_attempt_evidence'],prior,'Prior attempt evidence')
    exact(started['prior_attempt_evidence'],prior,'Started prior attempt evidence')
    sources=account['source_hashes']
    exact(publication['source_hashes'],sources,'Publication sources')
    exact(started['source_hashes'],sources,'Started sources');check(started['retry_allowed'] is False,'No retry')
    exact(account['input_references'],refs,'Exact input roles')
    for key in ('first_close_plan_does_not_use_open_cash_injection','initial_plan_quotes_expand_empty_baseline_prices_only','future_decisions_use_counterfactual_own_state','candidate_uses_execution_open_control_uses_prior_close'):
        check(account[key] is True,'Explicit path policy '+key)
    check(account['information_set_equivalence_verified'] is False,'Different decision information')
    check(account['flow_policy']=='FLOW_NOT_AVAILABLE_TO_PRIOR_CLOSE_PLAN','No advance cash')
    def pointer(reference):
        check(reference['path'] in docs and sources.get(reference['path'])==reference['sha256'],'Pointer source')
        out=docs[reference['path']]
        for key in reference['json_pointer'].split('/')[1:]:
            key=key.replace('~1','/').replace('~0','~')
            out=out[int(key)] if isinstance(out,list) else out[key]
        return out
    inp=docs[refs['inputs']['path']]; nominal=docs[refs['nominal']['path']]
    ipub=docs[refs['input_publication']['path']]
    check(ipub['input_reference']==refs['inputs'] and ipub['source_hashes']==inp['source_hashes'],'Input receipt')
    check(account['parent_input_sources_preserved_not_reaudited']==inp['source_hashes'],'Parent source preservation')
    metadata=deepcopy(nominal); del metadata['execution']
    for obj in metadata['nominal_quotes']['by_ticker'].values(): del obj['rows']
    check(account['parent_nominal_metadata']==metadata,'Metadata')
    for obj in (account,publication):
        for key in FALSE: check(obj[key] is False,key)
    check(type(account['path_count']) is int and account['path_count']==2 and type(account['scenario_count']) is int and account['scenario_count']==8 and len(account['paths'])==2,'Path count')
    calendar=[d for d in nominal['original_fixed_schedule']['calendar'] if '2023-03-31'<=d<='2023-09-01']
    check(len(calendar)==107 and calendar[0]=='2023-03-31' and calendar[-1]=='2023-09-01','Scoped original calendar, never all nominal dates')
    candidates=docs[refs['candidates']['path']]
    check(candidates['observed_calendar']==calendar and len(candidates['rows'])==8,'Candidate saved8 metadata')
    cp=docs[refs['candidate_publication']['path']]
    check(cp['account_reference']==refs['candidates'] and cp['source_hashes']==candidates['source_hashes'] and cp['status']=='PUBLISHED_CONDITIONAL_PRICE_ONLY_PATHS','Candidate publication')
    mapped={}; expected_main={r['scenario_id']:r for r in inp['rows'] }
    check(len(expected_main)==8 and len(account['scenario_mappings'])==8,'Mapping denominator')
    for row in account['scenario_mappings']:
        original=pointer(row['input_reference']); check(original==row['original_input_row']==expected_main[row['scenario_id']],'Mapping source')
        check(row['scenario_id'] not in mapped,'Duplicate scenario'); mapped[row['scenario_id']]=row
        check(row['path_id']==original['cash_event']['decision_date']+'|'+original['cash_event']['amount_usd'],'Mapping key')
        check(row['candidate_account_reexecuted'] is False,'No candidate replay')
        candidate=pointer(row['candidate_account_reference'])
        check(candidate['scenario_id']==row['scenario_id'] and candidate['input_row']==original and candidate['input_reference']==row['input_reference'],'Candidate exact source mapping')
        ca=candidate['accounting_inputs'];check(ca['initial']==dict(session='2023-03-31',cash_usd=original['starting_cash_usd'],holdings={},close_prices={}),'Candidate initial empty')
        check([r['session'] for r in ca['sessions']]==calendar[1:],'Candidate full source calendar')
        check(F(ca['transaction_cost_bps'])==F(original['transaction_cost_bps']),'Candidate fee')
        check(all(F(r['cash_injection_usd'])==F(original['cash_event']['amount_usd'] if k==0 else '0') for k,r in enumerate(ca['sessions'])),'Candidate identical flow clock')
    check({r['path_id'] for r in account['paths']}=={'2023-03-31|1000','2023-03-31|10000'},'Both explicit cash amounts')
    check({(r['lane'],r['cash_event']['amount_usd']) for r in expected_main.values()}=={(lane,amount) for lane in ('RETURN','BAD_TAIL','DRAWDOWN','LEGACY_TARGET_DISTANCE') for amount in ('1000','10000')},'Full four lanes and two amounts')
    counts=dict(paths=0,daily=0,decisions=0,executions=0,trades=0,rejected=0,filled=0,quote_references=0,mappings=8)
    for path in account['paths']:
        counts['paths']+=1
        check(path['same_original_first_decision_shares_verified'] is True and path['old_float_monetary_bitwise_equivalence_claimed'] is False,'Saved first plan boundary')
        for key in FALSE: check(path[key] is False,key)
        prepared=path['prepared']; a=path['account']; c=prepared['core_inputs']; initial=c['initial']; sessions=c['sessions']; schedule=c['schedule']
        members=[x['original_input_row'] for x in mapped.values() if x['path_id']==path['path_id']]
        check(initial['session']=='2023-03-31' and initial['holdings']=={} and F(initial['cash_usd'])==25000 and len(initial['close_prices'])==8,'Empty funded initial state, quotes only')
        check(len(sessions)==106 and len(schedule)==6 and sessions[0]['session']=='2023-04-03','First path 106 sessions and six decisions')
        check(len(members)==4 and len({r['lane'] for r in members})==4,'Four lane mapping')
        baseline=pointer(prepared['baseline_reference']); check(initial['holdings']==baseline['shares'] and initial['cash_usd']==str(baseline['cash_usd']),'Baseline')
        for member in members:
            check(member['holdings']==initial['holdings'] and member['starting_cash_usd']==initial['cash_usd'] and member['original_inventory_row']['baseline']==baseline,'Same initial state')
            check(member['cash_event']['amount_usd']==sessions[0]['cash_injection_usd'] and member['cash_event']['execution_date']==sessions[0]['session'],'Same flow')
            for key in ('risk_parameters','transaction_cost_bps','minimum_cash_buffer_usd'): check(member[key]==c[key],'Member contract')
        calendar=[d for d in nominal['original_fixed_schedule']['calendar'] if initial['session']<=d<='2023-09-01']
        check([initial['session']]+[r['session'] for r in sessions]==calendar,'Full observed calendar')
        check(all(r['cash_injection_usd']=='0' for r in sessions[1:]),'One flow only')
        evidence=prepared['quote_evidence']; expected_quotes=[(initial['session'],'close',initial['close_prices'])]
        for row in sessions: expected_quotes.extend([(row['session'],'open',row['open_prices']),(row['session'],'close',row['close_prices'])])
        check(len(evidence)==len(expected_quotes),'Quote denominator')
        for ev,(day,kind,marks) in zip(evidence,expected_quotes):
            check(ev['session']==day and ev['field']==kind and set(ev['quotes'])==set(marks),'Quote domain')
            for sid,quote in ev['quotes'].items():
                raw=pointer(quote['reference']); check(type(raw) is float and str(raw)==quote['literal']==marks[sid],'Float literal preserved')
                source_quote=pointer(dict(quote['reference'],json_pointer=quote['reference']['json_pointer'].rsplit('/',1)[0]))
                check(source_quote['session']==day and source_quote['ticker']==c['securities'][sid]['ticker'] and source_quote['currency']=='USD','Quote attribution')
                counts['quote_references']+=1
        fixed=nominal['original_fixed_schedule']; first=fixed['schedule'][0]['targets']
        check(c['fixed_weights']=={s:str(v['target_weight']) for s,v in first.items()},'Original weights')
        for sid,security in c['securities'].items():
            check(security==dict(ticker=first[sid]['ticker'],issuer_id=first[sid]['issuer_id'],risk_chain=fixed['risk_chains_by_decision'][initial['session']][sid]),'Security coordinates')
        selected=[r for r in fixed['schedule'] if initial['session']<=r['decision_date'] and r['execution_date']<='2023-09-01']
        check(schedule==[{k:r[k] for k in ('decision_date','execution_date')} for r in selected],'Original schedule')
        check(len(prepared['schedule_evidence'])==len(selected),'Schedule evidence count')
        for ev,entry in zip(prepared['schedule_evidence'],selected):
            check(ev['source_row']==pointer(ev['reference'])==entry,'Schedule pointer')
            check(ev['risk_labels']==pointer(ev['risk_reference'])=={s:v['risk_chain'] for s,v in c['securities'].items()} and ev['risk_observation_date']==entry['decision_date'],'Risk source')
        check(prepared['initial_saved_decision']==pointer(prepared['initial_saved_decision_reference']),'Saved first decision')
        for key in ('initial','sessions','schedule','securities','risk_parameters','transaction_cost_bps','minimum_cash_buffer_usd'): check(a[key]==c[key],'Account inputs '+key)
        check(a['original_fixed_weights']==c['fixed_weights'] and a['weights_normalized'] is False,'Weights unchanged')
        for key in ('open_replan_performed','orders_executed','point_in_time_verified','promotion_allowed','risk_is_order_gate','old_experiments_executed','negative_cash_allowed'): check(a[key] is False,key)
        rate=F(c['transaction_cost_bps'])/10000; buffer=F(c['minimum_cash_buffer_usd']); weights={s:F(w) for s,w in c['fixed_weights'].items()}
        cash=F(initial['cash_usd']); holdings=dict(initial['holdings']); prev=value(cash,holdings,initial['close_prices']); first_equity=prev
        wealth=F(1); fees_total=F(0); flows_total=F(0); reductions_total=0; di=ei=ti=0
        check(enc(a['initial_risk'])==enc(risk(holdings,initial['close_prices'],c['securities'],c['risk_parameters'])),'Initial risk')
        def project(wanted,prices):
            delta={s:wanted.get(s,0)-holdings.get(s,0) for s in sorted(set(wanted)|set(holdings))}
            buy=sum((q*F(prices[s]) for s,q in delta.items() if q>0),F(0)); sell=sum((-q*F(prices[s]) for s,q in delta.items() if q<0),F(0))
            fee=(buy+sell)*rate; return cash-buy+sell-fee,buy,sell,fee,delta
        def freeze(day,prices):
            nonlocal di,reductions_total
            if day not in {r['decision_date'] for r in schedule}: return None
            d=a['decisions'][di]; di+=1; investable=value(cash,holdings,prices)-buffer
            original={s:(investable*w)//F(prices[s]) for s,w in sorted(weights.items())}; wanted=dict(original); moves=[]
            def valid():
                rem=project(wanted,prices)[0]; return rem>=0 and rem>=buffer-F(1,10**8)
            def decrement(eligible,stage):
                nonlocal reductions_total
                sid=max(eligible,key=lambda s:(F(prices[s]),s)); q=wanted[sid]; wanted[sid]-=1; reductions_total+=1
                moves.append(dict(stage=stage,security_id=sid,before_shares=q,after_shares=q-1))
            while min(wanted.values())>=1 and not valid():
                choices=[s for s,q in wanted.items() if q>1]
                if not choices: break
                decrement(choices,'DYNAMIC_FIRST_STAGE_KEEP_ONE')
            fallback=not valid()
            if fallback:
                wanted=dict(original)
                while not valid():
                    choices=[s for s,q in wanted.items() if q>0]; check(bool(choices),'Unexpected NO_PLAN in actual artifact')
                    decrement(choices,'CONTROL_FINANCIAL_PROJECTION_ALLOW_ZERO')
            check(d['status']=='FROZEN' and d['shares_before']==holdings and d['original_floor_shares']==original and d['desired_shares']==wanted,'Frozen plan')
            check(d['reductions']==moves and d['projection_used'] is fallback,'Two-stage trace')
            for k,x in [('cash_before_usd',cash),('investable_before_future_flow_usd',investable)]: field(d,k,x)
            rem,buy,sell,fee,delta=project(wanted,prices)
            for k,x in [('projected_cash_usd',rem),('projected_buy_usd',buy),('projected_sell_usd',sell),('projected_fees_usd',fee)]: field(d,k,x)
            check(d['delta']==delta and enc(d['risk'])==enc(risk(wanted,prices,c['securities'],c['risk_parameters'])),'Frozen risk/delta')
            check({s:F(v) for s,v in d['prices'].items()}=={s:F(v) for s,v in prices.items()} and d['original_fixed_weights']==c['fixed_weights'] and d['future_open_flow_included_in_plan'] is False and d['risk_is_order_gate'] is False,'Plan semantics')
            check(d['decision_date']==day and d['execution_date']==next(r['execution_date'] for r in schedule if r['decision_date']==day),'Plan clock')
            return wanted,delta,day
        pending=freeze(initial['session'],initial['close_prices'])
        check(a['decisions'][0]['desired_shares']==prepared['initial_saved_decision']['desired_shares'] and a['decisions'][0]['delta']==prepared['initial_saved_decision']['delta'],'Initial old frozen quantities')
        check(len(a['daily'])==len(sessions),'Daily count'); previous_day=initial['session']
        for row,daily in zip(sessions,a['daily']):
            opens=row['open_prices']; closes=row['close_prices']; day=row['session']; old_cash=cash; old_holdings=dict(holdings); flow=F(row['cash_injection_usd'])
            open_old=value(cash,holdings,opens); cash+=flow; open_funded=open_old+flow; actualfee=F(0); actualdelta={}; status='NO_FROZEN_ORDER'
            if pending:
                wanted,delta,decision=pending; rem,buy,sell,fee,nowdelta=project(wanted,opens); check(nowdelta==delta,'Frozen delta stays fixed')
                failure=[]
                if rem<0: failure.append('NONNEGATIVE_CASH')
                if rem<buffer-F(1,10**8): failure.append('CASH_BUFFER')
                status='REJECTED' if failure else 'FILLED'; e=a['executions'][ei]; ei+=1
                check(e['session']==day and e['decision_date']==decision and e['status']==status and e['failure_reasons']==failure,'Atomic status')
                check(e['frozen_delta']==delta and e['desired_shares']==wanted and e['shares_before']==holdings and {s:F(v) for s,v in e['prices'].items()}=={s:F(v) for s,v in opens.items()},'Frozen execution')
                for k,x in [('cash_before_flow_usd',old_cash),('cash_injection_usd',flow),('cash_before_trade_usd',cash),('projected_cash_usd',rem),('projected_buy_usd',buy),('projected_sell_usd',sell),('projected_fees_usd',fee)]: field(e,k,x)
                check(enc(e['desired_risk'])==enc(risk(wanted,opens,c['securities'],c['risk_parameters'])) and e['risk_is_order_gate'] is False,'Open desired risk')
                if not failure:
                    cash=rem; holdings=dict(wanted); actualfee=fee; actualdelta=dict(delta)
                    for sid,q in delta.items():
                        if q:
                            trade=a['trades'][ti]; ti+=1
                            check(trade['session']==day and trade['security_id']==sid and trade['signed_share_delta']==q and trade['external_cash_flow'] is False,'Trade')
                            field(trade,'price_usd',F(opens[sid])); field(trade,'fee_usd',abs(q)*F(opens[sid])*rate)
                field(e,'cash_after_usd',cash); field(e,'actual_fees_usd',actualfee)
                check(e['shares_after']==holdings and enc(e['actual_risk'])==enc(risk(holdings,opens,c['securities'],c['risk_parameters'])),'Actual risk/holdings')
                counts[status.lower()]+=1; pending=None
            close=value(cash,holdings,closes); overnight=open_old/prev; after=close/open_funded; wealth*=overnight*after
            for k,x in [('previous_close_equity_usd',prev),('pre_flow_open_equity_usd',open_old),('post_flow_pre_fee_open_equity_usd',open_funded),('cash_injection_usd',flow),('cash_before_usd',old_cash),('cash_after_usd',cash),('fees_usd',actualfee),('close_equity_usd',close),('overnight_pnl_usd',open_old-prev),('cash_flow_adjusted_pnl_usd',close-prev-flow)]: field(daily,k,x)
            for k,x in [('overnight_return',overnight-1),('after_flow_return',after-1),('session_twr',overnight*after-1),('cumulative_twr',wealth-1)]: check(daily[k]==rat(x),k)
            check(daily['session']==day and daily['previous_close_session']==previous_day and daily['holdings_before']==old_holdings and daily['holdings_after']==holdings and daily['signed_share_delta']==actualdelta and daily['execution_status']==status,'Daily state')
            check(enc(daily['risk'])==enc(risk(holdings,closes,c['securities'],c['risk_parameters'])),'Daily risk')
            flows_total+=flow; fees_total+=actualfee; prev=close; previous_day=day; pending=freeze(day,closes)
        check(di==len(a['decisions']) and ei==len(a['executions']) and ti==len(a['trades']) and pending is None,'Evidence denominators')
        for k,x in [('initial_equity_usd',first_equity),('terminal_equity_usd',prev),('total_cash_injection_usd',flows_total),('total_fees_usd',fees_total),('net_dollar_pnl_excluding_injections_usd',prev-first_equity-flows_total)]: field(a,k,x)
        check(a['chained_twr']==rat(wealth-1) and a['original_weight_sum']==rat(sum(weights.values())) and a['reduction_count']==reductions_total,'Final account')
        counts['daily']+=len(sessions); counts['decisions']+=di; counts['executions']+=ei; counts['trades']+=ti
    check(counts['daily']==212 and counts['decisions']==12,'Actual bounded denominator')
    return counts

def readback(*,execute=False):
    check(execute is True,'Explicit readback')
    check(all(type(h) is str and len(h)==64 for h in (*PINS.values(),PRODUCER_SHA)), 'Future actual anchors pending')
    check(not OUTPUT.exists(),'No retry/overwrite')
    sources={str(SOURCE):LOADED,str(PRODUCER):PRODUCER_SHA}
    def read(reference):
        check(set(reference)=={'path','sha256'},'Exact external reference')
        blob=Path(reference['path']).read_bytes();check(sha(blob)==reference['sha256'],'Consumed saved bytes')
        check(reference['path'] not in sources or sources[reference['path']]==reference['sha256'],'Source conflict')
        sources[reference['path']]=reference['sha256'];return blob
    refs={role:dict(path=str(ROOT/path),sha256=h) for role,(path,h) in PARENTS.items()}
    docs={r['path']:json.loads(read(r)) if role in ('inputs','input_publication','nominal','candidates','candidate_publication','prior_started','prior_failure') else read(r) for role,r in refs.items()}
    check({p.name for p in Path(refs['prior_started']['path']).parent.iterdir()}=={'started.json','failure.json'},'Failed namespace remains exact')
    ar=dict(path=str(DIR/'accounts.json'),sha256=PINS['accounts.json']);pr=dict(path=str(DIR/'publication.json'),sha256=PINS['publication.json'])
    account=json.loads(read(ar));publication=json.loads(read(pr))
    check({p.name for p in DIR.iterdir()}=={'accounts.json','publication.json','started.json'},'Successful namespace exact')
    start_blob=(DIR/'started.json').read_bytes();sources[str(DIR/'started.json')]=sha(start_blob);started=json.loads(start_blob)
    expected={str(PRODUCER):PRODUCER_SHA,**{r['path']:r['sha256'] for r in refs.values()}}
    exact(account['source_hashes'],expected,'Twelve inputs plus producer, no claimed extra sources')
    def guard():
        for path,h in sources.items():check(sha(Path(path).read_bytes())==h,'Source drift')
    guard();counts=inspect_saved(account,publication,started,refs,docs,ar);guard()
    report=dict(schema='FIRST_PERIOD_INCUMBENT_CASH_FLOW_INDEPENDENT_READBACK_V1',status='PASS',accounts_reference=ar,publication_reference=pr,reader_sha256=LOADED,source_hashes=sources,counts=counts,started_bytes_externally_anchored=False,candidate_accounts_reexecuted=False,candidate_check_scope='EIGHT_SAVED_INPUT_FLOW_CALENDAR_MAPPINGS_ONLY',production_functions_called=False,old_experiments_reexecuted=False,formal_admission=False,point_in_time_verified=False,promotion_allowed=False)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    def save(path,value):
        import os
        blob=enc(value)
        with path.open('xb') as stream:stream.write(blob);stream.flush();os.fsync(stream.fileno())
        check(path.read_bytes()==blob,'Saved report bytes')
        return dict(path=str(path),sha256=sha(blob))
    try:
        answer=save(OUTPUT/'independent_readback.json',report);guard()
        check({p.name for p in OUTPUT.iterdir()}=={'independent_readback.json'},'Exact readback namespace')
        return answer
    except Exception as failure:
        save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error=str(failure),retry_allowed=False));raise

if __name__=='__main__':
    import argparse
    parser=argparse.ArgumentParser();parser.add_argument('--execute',action='store_true');args=parser.parse_args()
    print(json.dumps(readback(execute=args.execute)))
