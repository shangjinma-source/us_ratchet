"""Independent saved candidate accounting. No producer/request/account invocation."""
import argparse,copy,hashlib,json,os,types
from datetime import date
from decimal import Decimal
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
PARENT=ROOT/'data/cache/research/cash_neighbor_combined_selected_paths_20261008_v1'
OUTPUT=ROOT/'data/cache/research/cash_neighbor_combined_selected_paths_independent_readback_20261008_v1'
SEL=ROOT/'data/cache/research/cash_neighbor_combined_selection_20261008_v3'
BOUND={'result':('E:\\Git\\us_ratchet\\data\\cache\\research\\cash_neighbor_combined_selected_paths_20261008_v1\\result.json', 'ad6bb89625173932ff75dac6244543c78d267563532761171d5f84d7ab33d705'),'publication':('E:\\Git\\us_ratchet\\data\\cache\\research\\cash_neighbor_combined_selected_paths_20261008_v1\\publication.json', 'f6db71240f378cf3cf93bc849163fc359aa75a24839b1c53f5822e57d66b469d'),'producer':('E:\\Git\\us_ratchet\\scripts\\ndx_cash_neighbor_combined_selected_paths_20261008.py', '1e94ef802877a17bfdc29819b8ca45659bdebaf12cf7d67eabb84fff6e9c0b9f')}
INPUT_BOUND={
 'selection':('E:\\Git\\us_ratchet\\data\\cache\\research\\cash_neighbor_combined_selection_20261008_v3\\index.json', '4c0622b20d56ca52fd5473a45613b874020e3dcd7faeeb06011851bf4541b995'),'selection_publication':('E:\\Git\\us_ratchet\\data\\cache\\research\\cash_neighbor_combined_selection_20261008_v3\\publication.json', '3ab8cbbe81224da7223a389698a2b364451854a4301a2b93ec2105c67c47aea1'),
 'selection_audit':('E:\\Git\\us_ratchet\\data\\cache\\research\\cash_neighbor_combined_selection_independent_readback_20261008_v2\\independent_readback.json', 'ead90f58d2f1a218db872c381b4d2f103bf1f968f93c5affb048b787d35d19a2'),
 'selection_reader':('E:\\Git\\us_ratchet\\scripts\\ndx_cash_neighbor_combined_selection_independent_readback_v2_20261008.py', 'df04270fee0f0af2f2c558781f7e2de56109a6cb4d74e0ba015308b339f3aca8'),
 'paired':(str(ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/accounts.json'),'7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'),
 'paired_publication':(str(ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/publication.json'),'fb9db1ac77fffec7ec90141a7b431b3f34fb4bac0329deb07245c85b22325e7e'),
 'preparation':(str(ROOT/'data/cache/research/cash_topup_neighbor_preparation_20261003_v1/preparation.json'),'04cf54101f56303cc656e60079f1434661845da6e13c6c7d23305f3e9f1dde2b'),
 'request_core':(str(ROOT/'backtest/ndx_cash_neighbor_combined_selected_path_requests_research.py'),'62f6a671f54e54d250cadb2422d753dad8f0f03da8f250e73a580344f9c56d16'),
 'account_core':(str(ROOT/'backtest/ndx_cash_flow_return_accounting_research.py'),'ba4924f8f34ded1163d1b746faed236e968306004f2f15b559642cd4275f9417'),
 'stream_core':(str(ROOT/'backtest/ndx_research_json_rows_stream.py'),'b1a2ae63c68476dc952abf53bdd081e7f08cab3052ddc6fca5b61bd32091b86c')}
FLAGS=dict.fromkeys(('risk_recomputed','selection_reexecuted','controls_executed','orders_executed','point_in_time_verified','promotion_allowed','fresh_oos_claimed','economic_winner_selected','independent_account_readback_passed','full_transitive_source_closure_reverified'),False)
ACCOUNT_FALSE=('zero_capital_inception_supported','cash_buffer_and_risk_gates_evaluated','dividends_modelled','corporate_actions_modelled','cash_interest_modelled','withdrawals_supported','exchange_session_adjacency_verified','historical_experiment_executed','orders_executed','point_in_time_verified','promotion_allowed')

def require(ok,message):
    if not ok:raise ValueError(message)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def exact(a,b):require(enc(a)==enc(b),'Exact saved evidence mismatch')
def sha(b):return hashlib.sha256(b).hexdigest()
def ref(p,h):return dict(path=str(p),sha256=h)
def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and type(r['sha256'])is str and len(r['sha256'])==64 and all(c in '0123456789abcdef'for c in r['sha256']),'Pending or invalid anchor');return r
def merge(s,r):valid(r);require(r['path']not in s or s[r['path']]==r['sha256'],'Source conflict');s[r['path']]=r['sha256']
def loads(b):
    def pairs(items):
        out={}
        for key,value in items:require(key not in out,'Duplicate JSON key');out[key]=value
        return out
    return json.loads(b,object_pairs_hook=pairs,parse_constant=lambda v:(_ for _ in ()).throw(ValueError('Nonfinite JSON')))

def read(r,s):
    merge(s,r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed source SHA');return loads(b)
def current(p,s):
    b=p.read_bytes();r=ref(p,sha(b));merge(s,r);return loads(b),r
def guard(s):
    require(sha(SOURCE.read_bytes())==LOADED,'Reader source drift')
    for p,h in s.items():require(sha(Path(p).read_bytes())==h,'Consumed source drift '+p)
def save(p,v):
    b=enc(v)
    with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Report bytes');return ref(p,sha(b))
def flags(v):
    for k in FLAGS:require(v[k]is False,'Authority '+k)
def integer(v):require(type(v)is int and 0<=v<=10**12,'Exact whole nonnegative integer');return v

def number(v):
    require(type(v)in (str,int) and len(str(v))<=256,'Exact decimal literal')
    try:d=Decimal(v)
    except Exception as error:raise ValueError('Invalid decimal')from error
    require(d.is_finite() and len(d.as_tuple().digits)<=160 and abs(d.as_tuple().exponent)<=160,'Finite bounded decimal');return Fraction(d)
def money(v):
    scale=0;den=v.denominator
    while den%2==0:den//=2;scale+=1
    fives=0
    while den%5==0:den//=5;fives+=1
    require(den==1,'Terminating money');scale=max(scale,fives);n=v.numerator*10**scale//v.denominator;sign='-'if n<0 else '';digits=str(abs(n)).rjust(scale+1,'0');text=(digits[:-scale]+'.'+digits[-scale:]).rstrip('0').rstrip('.')if scale else digits;return sign+text if n else '0'
def ratio(v):return dict(numerator=str(v.numerator),denominator=str(v.denominator))
def holdings(v):
    require(type(v)is dict,'Holdings mapping')
    for k,q in v.items():require(type(k)is str and k,'SID');integer(q)
    return dict(sorted(v.items()))
def prices(v,ids):
    require(type(v)is dict and set(v)==set(ids),'Full required price union');out={k:number(x)for k,x in v.items()};require(all(x>0 for x in out.values()),'Positive price');return out

def inspect_account(args,account,expected_trade):
    require(type(account)is dict and account['schema']=='BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1','Returned account')
    for key in ACCOUNT_FALSE:require(account[key]is False,'Account scope '+key)
    exact(account['cash_event_timing'],'AFTER_OLD_HOLDINGS_OPEN_MARK_BEFORE_BUYS_AND_FEES');exact(account['arithmetic'],'EXACT_RATIONAL_VALUES_FINITE_DECIMAL_MONEY_NO_FLOAT_INPUT');exact(account['parameter_authority'],'CALLER_SUPPLIED_SYNTHETIC_OR_EXPLICIT_SCENARIO_NOT_SOURCE_BOUND');exact(account['engineering_resource_limits_not_investment_policy'],dict(sessions=512,security_ids=256,ratio_bits=12000))
    init=args['initial'];q=holdings(init['holdings']);cash=number(init['cash_usd']);require(cash>=0,'Initial cash');marks=prices(init['close_prices'],q);initial=previous=cash+sum(q[k]*marks[k]for k in q);require(initial>0,'Positive initial equity');fee=number(args['transaction_cost_bps']);require(fee==10,'Original fee');previous_day=init['session'];factor=Fraction(1);totalflow=totalfees=Fraction(0)
    sessions=args['sessions'];require(type(sessions)is list and 1<=len(sessions)<=512 and len(account['rows'])==len(sessions),'Whole exact path')
    for n,(session,got)in enumerate(zip(sessions,account['rows'])):
        day=session['session'];require(type(day)is str and date.fromisoformat(day).isoformat()==day and day>previous_day,'Strict calendar');buy=holdings(session['buy_shares']);union=set(q)|set(buy);op=prices(session['open_prices'],union);cl=prices(session['close_prices'],union);flow=number(session['cash_injection_usd']);require(flow>=0,'No withdrawal');before=cash+sum(q[k]*op[k]for k in q);plus=before+flow;require(before>0 and plus>0,'Positive flow boundaries');gross=sum((buy[k]*op[k]for k in buy),Fraction(0));cost=gross*fee/10000;cash_next=cash+flow-gross-cost;require(cash_next>=0,'Nonnegative cash');after={k:q.get(k,0)+buy.get(k,0)for k in sorted(union)};open_after=cash_next+sum(after[k]*op[k]for k in after);close=cash_next+sum(after[k]*cl[k]for k in after);overnight=before/previous;postflow=close/plus;daily=overnight*postflow;factor*=daily
        expected=dict(previous_close_session=previous_day,session=day,previous_close_equity_usd=money(previous),pre_flow_open_equity_usd=money(before),cash_injection_usd=money(flow),post_flow_pre_fee_open_equity_usd=money(plus),post_trade_open_equity_usd=money(open_after),close_equity_usd=money(close),gross_buy_usd=money(gross),fees_usd=money(cost),cash_after_usd=money(cash_next),holdings_before=q,buy_shares=buy,holdings_after=after,overnight_pnl_usd=money(before-previous),intraday_mark_pnl_before_fees_usd=money(close-open_after),after_flow_pnl_net_fees_usd=money(close-plus),cash_flow_adjusted_pnl_usd=money(close-previous-flow),overnight_return=ratio(overnight-1),after_flow_return=ratio(postflow-1),session_twr=ratio(daily-1),cumulative_twr=ratio(factor-1));exact(got,expected)
        exact(after,expected_trade['proposed_holdings']);require(number(expected_trade['cash_after_usd'])==cash_next,'Frozen plan cash');exact(buy,expected_trade['buy_shares']if n==0 else {});require(cost==(number(expected_trade['fees_usd'])if n==0 else 0),'Frozen plan fee')
        if n==0:require(gross==number(expected_trade['gross_buy_usd']),'Frozen plan gross')
        totalflow+=flow;totalfees+=cost;previous_day=day;previous=close;cash=cash_next;q=after
    expected_final=dict(initial_equity_usd=money(initial),terminal_equity_usd=money(previous),total_cash_injection_usd=money(totalflow),total_fees_usd=money(totalfees),net_dollar_pnl_excluding_injections_usd=money(previous-initial-totalflow),chained_twr=ratio(factor-1),transaction_cost_bps=money(fee))
    for key,value in expected_final.items():exact(account[key],value)
    require(set(account)=={'schema','rows','cash_event_timing','arithmetic','parameter_authority','engineering_resource_limits_not_investment_policy'}|set(ACCOUNT_FALSE)|set(expected_final),'Exact account fields')
    return dict(daily_rows_verified=len(sessions),first_trade_reconciled=True,terminal_equity_usd=money(previous),chained_twr=ratio(factor-1),independent_saved_quote_arithmetic_verified=True)

def inspect_partition(result,ids):
    require(result['schema']=='CASH_NEIGHBOR_SELECTED_PATHS_RESULT_V1' and type(result['scenario_count'])is int and result['scenario_count']==40,'Forty schema');require(len(ids)==len(set(ids))==40,'Original forty IDs');flags(result)
    completed=result['completed_rows'];done=[v['scenario_id']for v in completed];exact(done,ids[:len(done)])
    for i,row in enumerate(completed):require(type(row['scenario_index'])is int and row['scenario_index']==i,'Completion original order')
    unresolved=result['unresolved_scenario_ids'];undispatched=result['undispatched_scenario_ids'];require(len(unresolved)<=1,'At most stopped dispatch')
    if result['failure']is None:require(result['status']=='COMPLETE_PENDING_INDEPENDENT_READBACK','Complete result');exact(done,ids);exact(unresolved,[]);exact(undispatched,[])
    else:
        require(result['status']=='STOPPED_NO_RETRY' and len(done)<40,'Stopped remains incomplete');failure=result['failure'];require(type(failure['dispatch_invoked'])is bool,'Strict dispatch flag');exact(failure['scenario_index'],len(done));exact(failure['scenario_id'],ids[len(done)]);exact(unresolved,[ids[len(done)]]if failure['dispatch_invoked']else []);exact(undispatched,ids[len(done)+len(unresolved):])
    attempted=[v['scenario_id']for v in completed if v['outcome']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK']+unresolved;exact(result['attempted_scenario_ids'],attempted)
    return dict(completed=len(done),unresolved=len(unresolved),undispatched=len(undispatched),attempted=len(attempted))

def inspect_request(request,selected,prepared,old,index,inputs,selection_reference):
    for key in ('source_bytes_authenticated','selection_reexecuted','risk_recomputed','fees_recomputed','account_executed','control_reexecuted','orders_executed','point_in_time_verified','promotion_allowed','fresh_oos_claimed','economic_winner_selected','nav_fx_equivalence_verified'):require(request[key]is False,'Request authority '+key)
    exact(request['schema'],'CASH_NEIGHBOR_SELECTED_PATH_REQUEST_V1');require(type(request['scenario_index'])is int and request['scenario_index']==index,'Request original position');exact(request['prepared_contract'],prepared);exact(request['old_paired_evidence'],old);exact(request['selection'],selected);exact(request['scenario_id'],old['scenario_id']);exact(selected['scenario_id'],old['scenario_id']);exact(request['status'],selected['status'])
    base=dict(inputs['paired'],json_pointer=f'/rows/{index}');exact(request['input_references'],dict(selection_reference=dict(selection_reference,json_pointer='/selection'),selection_audit_reference=dict(inputs['selection_audit'],json_pointer=f'/cases/{index}'),old_paired_reference=base));exact(request['control_path_reference'],dict(base,json_pointer=base['json_pointer']+'/paths/same_flow_zero_trade_control'))
    c=prepared['contract'];exact(sha(enc(c)),prepared['contract_sha256']);exact(c['original_input_row'],old['input_row']);exact(c['input_reference'],old['input_reference']);exact(c['previous_result_reference'],old['topup_context_reference']);exact(selected['contract_sha256'],prepared['contract_sha256']);j=c['original_selected_candidate_index'];integer(j);exact(j,old['topup_context']['selected_candidate_index']);point=c['old_evaluated_points'][j];require(point['saved_feasible']is True and old['selected_plan']['feasible']is True,'Known original feasible');exact(point['buy_shares'],old['selected_plan']['buy_shares']);exact(old['selected_plan_reference'],dict(c['previous_result_reference'],json_pointer=c['previous_result_reference']['json_pointer']+f'/evaluation/branches/0/evaluated_plans/{j}'))
    oldref=dict(base,json_pointer=base['json_pointer']+'/paths/candidate');exact(selected['old_selected_path'],dict(reference=oldref,scenario_id=old['scenario_id'],selected_candidate_index=j,buy_shares=old['selected_plan']['buy_shares']))
    winner=selected['selected'];require(winner is not None and winner['feasible']is True and winner['saved_plan']['feasible']is True,'Known feasible union cannot become missing cash');plan=winner['saved_plan'];exact(plan['buy_shares'],winner['buy_shares']);expected=copy.deepcopy(old['paths']['candidate']['accounting_inputs'])
    if selected['status']=='REUSE_EXISTING_PAIRED_PATH':exact(plan,old['selected_plan']);exact(selected['reused_path_reference'],oldref);exact(request['reused_candidate_path_reference'],oldref);require(request['accounting_request']is None,'Reuse cannot execute')
    else:
        require(selected['status']=='NEW_PATH_REQUIRED' and plan['buy_shares']!=old['selected_plan']['buy_shares'],'New vector needed');expected['sessions'][0]['buy_shares']=copy.deepcopy(plan['buy_shares']);exact(request['accounting_request'],expected);require(request['reused_candidate_path_reference']is None and selected['reused_path_reference']is None,'No borrowed old path')
    exact(request['expected_first_trade'],{k:plan[k]for k in ('buy_shares','proposed_holdings','gross_buy_usd','fees_usd','cash_after_usd')});require(request['candidate_decision_time_executability_verified']is False and request['nav_reference_diagnostics_allowed']is True,'Policy restrictions')
    return request

def readback(*,execute=False):
    require(execute is True,'Explicit readback');require(not OUTPUT.exists(),'Create-only no retry');r={k:valid(ref(*v))for k,v in BOUND.items()};inputs={k:valid(ref(*v))for k,v in INPUT_BOUND.items()};sources={str(SOURCE):LOADED}
    for x in list(r.values())+list(inputs.values()):
        if x!=inputs['paired']:merge(sources,x)
    guard(sources);result=read(r['result'],sources);pub=read(r['publication'],sources);exact(result['input_references'],inputs);base={r['producer']['path']:r['producer']['sha256']}
    for key,x in inputs.items():
        if key!='paired':merge(base,x)
    exact(result['source_hashes'],base);exact(pub['source_hashes'],base);require(pub['schema']=='CASH_NEIGHBOR_SELECTED_PATHS_PUBLICATION_V1' and pub['status']=='PUBLISHED_PENDING_INDEPENDENT_READBACK','Successful publication only');exact(pub['result_reference'],r['result']);flags(pub)
    selection=read(inputs['selection'],sources);selection_pub=read(inputs['selection_publication'],sources);audit=read(inputs['selection_audit'],sources);prep=read(inputs['preparation'],sources);paired_pub=read(inputs['paired_publication'],sources)
    require(selection['schema']=='CASH_NEIGHBOR_COMBINED_STREAM_SELECTION_INDEX_V1' and selection['status']=='COMPLETE_DECLARED_UNION_SELECTION','Selection status');require(audit['schema']=='CASH_NEIGHBOR_COMBINED_SELECTION_INDEPENDENT_READBACK_V1' and audit['status']=='PASS','Selection audit');exact(audit['index_reference'],inputs['selection']);exact(audit['publication_reference'],inputs['selection_publication']);exact(audit['reader_sha256'],inputs['selection_reader']['sha256']);require(selection_pub['schema']=='CASH_NEIGHBOR_COMBINED_STREAM_SELECTION_PUBLICATION_V1' and selection_pub['status']=='PUBLISHED_COMPLETE_DECLARED_UNION_SELECTION','Final selection receipt');require(audit['complete_saved_score_order_independently_verified']is True,'Audited complete choice');exact(selection_pub['index_reference'],inputs['selection']);exact(selection_pub['source_hashes'],selection['source_hashes']);exact(paired_pub['account_reference'],inputs['paired'])
    for doc in (selection,audit):
        require(type(doc['scenario_count'])is int and doc['scenario_count']==40 and type(doc['total_candidate_count'])is int and doc['total_candidate_count']==304305,'Original selection denominator')
    for doc in (selection,selection_pub,audit):
        for key in ('risk_recomputed','account_executed','point_in_time_verified','promotion_allowed'):require(doc[key]is False,'Selection limits')
    for role in ('paired','paired_publication','preparation'):exact(selection['input_references'][role],inputs[role])
    require(len(selection['cases'])==len(audit['cases'])==len(prep['rows'])==40,'Complete source row counts')
    ids=[v['scenario_id']for v in selection['cases']];counts=inspect_partition(result,ids);require(result['failure']is None,'Stopped result has no successful publication; not accepted as full account result')
    require(not (Path(inputs['selection']['path']).parent/'failure.json').exists() and not (Path(inputs['selection_audit']['path']).parent/'failure.json').exists(),'Failed parents blocked')
    expected_root={'started.json','result.json','publication.json'}|{f'scenario-{i:02d}'for i in range(40)}
    def namespace():require({p.name for p in PARENT.iterdir()}==expected_root,'Exact parent namespace')
    namespace();started,sr=current(PARENT/'started.json',sources);require(started['schema']=='CASH_NEIGHBOR_SELECTED_PATHS_STARTED_V1','Started schema');exact(started['input_references'],inputs);exact(started['source_hashes'],base);exact(started['scenario_ids'],ids);require(type(started['minimum_free_bytes'])is int and started['minimum_free_bytes']==5*1024**3 and started['paired_authenticated_once_at_eof']is True,'Resource/stream contract');flags(started)
    sb=Path(inputs['stream_core']['path']).read_bytes();require(sha(sb)==inputs['stream_core']['sha256'],'Immediate stream source');stream_module=types.ModuleType('_saved_json_stream');exec(compile(sb,inputs['stream_core']['path'],'exec'),stream_module.__dict__)
    OUTPUT.mkdir(parents=True,exist_ok=False)
    try:
        save(OUTPUT/'started.json',dict(input_references=r,original_input_references=inputs,**FLAGS));reports=[];consumed={};names={}
        with Path(inputs['paired']['path']).open('rb')as f:
            stream=stream_module.JsonRowsStream(f)
            for n,token in enumerate(stream):
                require(n<40 and token['row_index']==n,'Original forty paired rows');entry=selection['cases'][n];completed=result['completed_rows'][n];require(type(entry['scenario_index'])is int and entry['scenario_index']==n,'Selection case position');require(type(audit['cases'][n]['scenario_index'])is int and audit['cases'][n]['scenario_index']==n,'Audit case position');exact(prep['rows'][n]['scenario_id'],entry['scenario_id']);exact(entry['scenario_id'],ids[n]);exact(audit['cases'][n]['scenario_id'],ids[n]);exact(audit['cases'][n]['status'],entry['status']);folder=PARENT/f'scenario-{n:02d}';local={};rr=completed['request_reference'];exact(rr['path'],str(folder/'request.json'));doc=read(rr,local);flags(doc)
                ss=entry['selection_reference'];sp=entry['publication_reference'];selected=read(ss,local);require(type(selected['scenario_index'])is int and selected['scenario_index']==n,'Saved selection position');exact(selected['selection']['scenario_id'],entry['scenario_id']);exact(selected['selection']['status'],entry['status']);casepub=read(sp,local);exact(casepub['selection_reference'],ss);exact(casepub['ledger_reference'],entry['ledger_reference']);exact(selected['ledger_reference'],entry['ledger_reference']);require(casepub['schema']=='CASH_NEIGHBOR_SELECTION_CASE_RECEIPT_V1' and casepub['status']=='PENDING_FINAL_SOURCE_CLOSURE','Final parent authorizes pending case receipt');require(selected['schema']=='CASH_NEIGHBOR_SOURCE_BOUND_CASE_SELECTION_V1' and selected['requires_final_publication']is True and casepub['requires_final_publication']is True,'Authorized final case')
                cr=prep['rows'][n]['contract_reference'];require(selection['source_hashes'].get(cr['path'])==cr['sha256'],'Contract in source closure');contract=read(cr,local);expected_local={v['path']:v['sha256']for v in (ss,sp,cr)};exact(doc['source_hashes'],expected_local)
                exact(doc['paired_row_byte_reference'],dict(source_reference=inputs['paired'],byte_start=token['byte_start'],byte_stop=token['byte_stop'],row_sha256=token['sha256']));request=inspect_request(doc['request'],selected['selection'],contract,token['value'],n,inputs,ss);exact(completed['status'],request['status']);exact(completed['control_reference'],request['control_path_reference'])
                require(type(completed['scenario_index'])is int and completed['scenario_index']==n,'Completed position');detail=None
                if request['status']=='REUSE_EXISTING_PAIRED_PATH':
                    exact(completed['outcome'],request['status']);exact(completed['candidate_reference'],request['reused_candidate_path_reference']);allowed={'request.json'}
                else:
                    exact(completed['outcome'],'ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK');allowed={'request.json','started.json','raw.json','postcheck.json'};rawref=completed['raw_reference'];postref=completed['postcheck_reference'];exact(rawref['path'],str(folder/'raw.json'));exact(postref['path'],str(folder/'postcheck.json'));raw=read(rawref,local);post=read(postref,local);startref=raw['started_reference'];exact(startref['path'],str(folder/'started.json'));start=read(startref,local)
                    require(start['schema']=='CASH_NEIGHBOR_SELECTED_PATH_STARTED_V1' and start['control_execution_allowed']is False,'Candidate-only started');exact(start['source_hashes'],base);exact(start['request_reference'],rr);exact(raw['request_reference'],rr);exact(post['started_reference'],startref);exact(post['raw_reference'],rawref)
                    require(raw['schema']=='CASH_NEIGHBOR_SELECTED_PATH_RAW_V1' and post['schema']=='CASH_NEIGHBOR_SELECTED_PATH_POSTCHECK_V1','Attempt schemas');require(raw['error']is None and post['validation_error']is None and post['outcome']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK','No failure promoted to path');require(type(raw['account_call_attempt_count'])is int and raw['account_call_attempt_count']==1 and type(raw['returned_account_count'])is int and raw['returned_account_count']==1,'Exactly one returned account')
                    for obj in (start,raw,post):flags(obj)
                    detail=inspect_account(request['accounting_request'],raw['account'],request['expected_first_trade'])
                require({p.name for p in folder.iterdir()}==allowed,'Exact case namespace');names[str(folder)]=allowed;guard(local)
                for p,h in local.items():merge(consumed,ref(p,h))
                reports.append(dict(scenario_index=n,scenario_id=ids[n],outcome=completed['outcome'],request_reference=rr,candidate_reference=completed.get('candidate_reference'),raw_reference=completed.get('raw_reference'),control_reference=completed['control_reference'],detail=detail))
            summary=stream.summary
        require(len(reports)==40 and summary['row_count']==40 and summary['complete_document_consumed']is True,'Full paired EOF');exact(summary['sha256'],inputs['paired']['sha256']);exact(summary,result['paired_stream_summary']);exact(summary['metadata']['source_hashes'],paired_pub['source_hashes'])
        def final_guard():
            namespace();guard(sources);guard(consumed)
            for p,expected in names.items():require({x.name for x in Path(p).iterdir()}==expected,'Final immutable case files')
        final_guard();report=save(OUTPUT/'independent_readback.json',dict(schema='CASH_NEIGHBOR_SELECTED_PATHS_INDEPENDENT_READBACK_V1',status='PASS_SAVED_PATH_ARITHMETIC',result_reference=r['result'],publication_reference=r['publication'],reader_sha256=LOADED,source_hashes=sources,consumed_case_sources=consumed,paired_reference=inputs['paired'],paired_bytes_verified_once_at_eof=True,partition=counts,cases=reports,old_controls_reaudited=False,producer_called=False,request_core_called=False,account_core_called=False,started_has_separate_external_anchor=False,**FLAGS));final_guard();require({p.name for p in OUTPUT.iterdir()}=={'started.json','independent_readback.json'},'Reader exact outputs');return report
    except BaseException as e:save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(e).__name__,error=str(e),retry_allowed=False,**FLAGS));raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(readback(execute=p.parse_args().execute)))
