"""Independent saved-only Fraction replay; never imports a producer/account kernel."""
from pathlib import Path
from fractions import Fraction as F
from copy import deepcopy
import hashlib
import json

ROOT=Path(__file__).resolve().parents[1]
DIR=ROOT/'data/cache/research/incumbent_cash_flow_paths_20261002_v1'
PINS={'accounts.json':'d1ac38ebe7674756d67cdc390938a6dffbe0d4f45c25e7b10726fab5642dc36a',
      'publication.json':'2abc2d2bbe9e03e6f7c84f11f6c9c9a422d81624a291c9494349c58950ede1bd'}
CHECKS=('MAX_SINGLE_WEIGHT','MIN_SINGLE_WEIGHT','SECURITY_TOP3_WEIGHT','MINIMUM_EFFECTIVE_N','RISK_CHAIN_TOP1_WEIGHT')
FALSE=('orders_executed','point_in_time_verified','promotion_allowed','dividends_modelled','corporate_actions_modelled','fx_modelled','formal_dual_benchmark_admission','old_accounts_reexecuted','original_target_weights_modified','risk_is_order_gate','full_transitive_source_closure_reverified')

def check(ok, message):
    if not ok: raise AssertionError(message)

def sha(raw): return hashlib.sha256(raw).hexdigest()
def rat(x): return {'numerator':str(x.numerator),'denominator':str(x.denominator)}
def value(cash,holdings,prices): return cash+sum((q*F(prices[s]) for s,q in holdings.items()),F(0))
def field(record,key,expected):
    actual=record[key]
    check(F(actual)==expected if isinstance(expected,F) else actual==expected,'Mismatch '+key)

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

def audit():
    docs={}
    def load(path,digest):
        path=Path(path); raw=path.read_bytes(); check(sha(raw)==digest,'Byte binding '+str(path)); doc=json.loads(raw); docs[str(path)]=doc; return doc
    account=load(DIR/'accounts.json',PINS['accounts.json']); publication=load(DIR/'publication.json',PINS['publication.json'])
    check({p.name for p in DIR.iterdir()}=={'accounts.json','publication.json','started.json'},'Namespace')
    sources=account['source_hashes']
    for path,digest in sources.items(): check(sha(Path(path).read_bytes())==digest,'Direct source '+path)
    check(publication['source_hashes']==sources,'Publication source map')
    check(publication['account_reference']=={'path':str(DIR/'accounts.json'),'sha256':PINS['accounts.json']},'Publication account')
    check(publication['status']=='PUBLISHED_CONDITIONAL_SAME_FLOW_INCUMBENT_PATHS','Publication state')
    started=json.loads((DIR/'started.json').read_bytes()); check(started['source_hashes']==sources and started['retry_allowed'] is False,'Started')
    refs=account['input_references']
    for ref in refs.values():
        check(sources[ref['path']]==ref['sha256'],'Input source map')
        if ref['path'].endswith('.json'): load(ref['path'],ref['sha256'])
    def pointer(ref):
        check(ref['path'] in docs and sources.get(ref['path'])==ref['sha256'],'Pointer provenance')
        out=docs[ref['path']]
        for key in ref['json_pointer'].split('/')[1:]:
            key=key.replace('~1','/').replace('~0','~'); out=out[int(key)] if isinstance(out,list) else out[key]
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
    check(account['path_count']==10 and account['scenario_count']==40 and len(account['paths'])==10,'Path count')
    mapped={}; expected_main={r['scenario_id']:r for r in inp['rows'] if r['branch_role']=='MAIN_LANE'}
    check(len(expected_main)==40 and len(account['scenario_mappings'])==40,'Mapping denominator')
    for row in account['scenario_mappings']:
        original=pointer(row['input_reference']); check(original==row['original_input_row']==expected_main[row['scenario_id']],'Mapping source')
        check(row['scenario_id'] not in mapped,'Duplicate scenario'); mapped[row['scenario_id']]=row
        check(row['path_id']==original['cash_event']['decision_date']+'|'+original['cash_event']['amount_usd'],'Mapping key')
    counts=dict(paths=0,daily=0,decisions=0,executions=0,trades=0,rejected=0,filled=0,quote_references=0,mappings=40)
    for path in account['paths']:
        counts['paths']+=1
        for key in FALSE: check(path[key] is False,key)
        prepared=path['prepared']; a=path['account']; c=prepared['core_inputs']; initial=c['initial']; sessions=c['sessions']; schedule=c['schedule']
        members=[x['original_input_row'] for x in mapped.values() if x['path_id']==path['path_id']]
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
        check(a['initial_risk']==risk(holdings,initial['close_prices'],c['securities'],c['risk_parameters']),'Initial risk')
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
            check(d['delta']==delta and d['risk']==risk(wanted,prices,c['securities'],c['risk_parameters']),'Frozen risk/delta')
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
                check(e['desired_risk']==risk(wanted,opens,c['securities'],c['risk_parameters']) and e['risk_is_order_gate'] is False,'Open desired risk')
                if not failure:
                    cash=rem; holdings=dict(wanted); actualfee=fee; actualdelta=dict(delta)
                    for sid,q in delta.items():
                        if q:
                            trade=a['trades'][ti]; ti+=1
                            check(trade['session']==day and trade['security_id']==sid and trade['signed_share_delta']==q and trade['external_cash_flow'] is False,'Trade')
                            field(trade,'price_usd',F(opens[sid])); field(trade,'fee_usd',abs(q)*F(opens[sid])*rate)
                field(e,'cash_after_usd',cash); field(e,'actual_fees_usd',actualfee)
                check(e['shares_after']==holdings and e['actual_risk']==risk(holdings,opens,c['securities'],c['risk_parameters']),'Actual risk/holdings')
                counts[status.lower()]+=1; pending=None
            close=value(cash,holdings,closes); overnight=open_old/prev; after=close/open_funded; wealth*=overnight*after
            for k,x in [('previous_close_equity_usd',prev),('pre_flow_open_equity_usd',open_old),('post_flow_pre_fee_open_equity_usd',open_funded),('cash_injection_usd',flow),('cash_before_usd',old_cash),('cash_after_usd',cash),('fees_usd',actualfee),('close_equity_usd',close),('overnight_pnl_usd',open_old-prev),('cash_flow_adjusted_pnl_usd',close-prev-flow)]: field(daily,k,x)
            for k,x in [('overnight_return',overnight-1),('after_flow_return',after-1),('session_twr',overnight*after-1),('cumulative_twr',wealth-1)]: check(daily[k]==rat(x),k)
            check(daily['session']==day and daily['previous_close_session']==previous_day and daily['holdings_before']==old_holdings and daily['holdings_after']==holdings and daily['signed_share_delta']==actualdelta and daily['execution_status']==status,'Daily state')
            check(daily['risk']==risk(holdings,closes,c['securities'],c['risk_parameters']),'Daily risk')
            flows_total+=flow; fees_total+=actualfee; prev=close; previous_day=day; pending=freeze(day,closes)
        check(di==len(a['decisions']) and ei==len(a['executions']) and ti==len(a['trades']) and pending is None,'Evidence denominators')
        for k,x in [('initial_equity_usd',first_equity),('terminal_equity_usd',prev),('total_cash_injection_usd',flows_total),('total_fees_usd',fees_total),('net_dollar_pnl_excluding_injections_usd',prev-first_equity-flows_total)]: field(a,k,x)
        check(a['chained_twr']==rat(wealth-1) and a['original_weight_sum']==rat(sum(weights.values())) and a['reduction_count']==reductions_total,'Final account')
        counts['daily']+=len(sessions); counts['decisions']+=di; counts['executions']+=ei; counts['trades']+=ti
    check(counts['daily']==442 and counts['decisions']==30,'Actual bounded denominator')
    for path,digest in sources.items(): check(sha(Path(path).read_bytes())==digest,'End source guard')
    for name,digest in PINS.items(): check(sha((DIR/name).read_bytes())==digest,'End artifact guard')
    return dict(status='PASS_INDEPENDENT_SAVED_FRACTION_READBACK',counts=counts,direct_source_count=len(sources),accounts_sha256=PINS['accounts.json'],publication_sha256=PINS['publication.json'],production_functions_called=False,old_experiments_reexecuted=False,formal_admission=False)

if __name__=='__main__': print(json.dumps(audit(),indent=2))
