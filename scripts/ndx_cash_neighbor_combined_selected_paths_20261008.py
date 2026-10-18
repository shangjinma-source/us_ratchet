"""Create-only selected candidate paths. Future anchors block all actual execution.

Authenticate one complete paired JSON stream before any account dispatch. Never
reselect, evaluate risk, or run an incumbent/zero-trade control.
"""
import argparse,hashlib,json,os,shutil,types
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];SOURCE=Path(__file__).resolve();LOADED=hashlib.sha256(SOURCE.read_bytes()).hexdigest()
OUTPUT=ROOT/'data/cache/research/cash_neighbor_combined_selected_paths_20261008_v1'
SEL=ROOT/'data/cache/research/cash_neighbor_combined_selection_20261008_v3'
BOUND={
 'selection':('E:\\Git\\us_ratchet\\data\\cache\\research\\cash_neighbor_combined_selection_20261008_v3\\index.json', '4c0622b20d56ca52fd5473a45613b874020e3dcd7faeeb06011851bf4541b995'),'selection_publication':('E:\\Git\\us_ratchet\\data\\cache\\research\\cash_neighbor_combined_selection_20261008_v3\\publication.json', '3ab8cbbe81224da7223a389698a2b364451854a4301a2b93ec2105c67c47aea1'),
 'selection_audit':('E:\\Git\\us_ratchet\\data\\cache\\research\\cash_neighbor_combined_selection_independent_readback_20261008_v2\\independent_readback.json', 'ead90f58d2f1a218db872c381b4d2f103bf1f968f93c5affb048b787d35d19a2'),
 'selection_reader':('E:\\Git\\us_ratchet\\scripts\\ndx_cash_neighbor_combined_selection_independent_readback_v2_20261008.py', 'df04270fee0f0af2f2c558781f7e2de56109a6cb4d74e0ba015308b339f3aca8'),
 'paired':(str(ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/accounts.json'),'7d5df8f295657497f3919aa3458dff31f0c175a40f391eb6b37ac9e5b7512d6f'),
 'paired_publication':(str(ROOT/'data/cache/research/old_holding_topup_paired_account_20261002_v1/publication.json'),'fb9db1ac77fffec7ec90141a7b431b3f34fb4bac0329deb07245c85b22325e7e'),
 'preparation':(str(ROOT/'data/cache/research/cash_topup_neighbor_preparation_20261003_v1/preparation.json'),'04cf54101f56303cc656e60079f1434661845da6e13c6c7d23305f3e9f1dde2b'),
 'request_core':(str(ROOT/'backtest/ndx_cash_neighbor_combined_selected_path_requests_research.py'),'62f6a671f54e54d250cadb2422d753dad8f0f03da8f250e73a580344f9c56d16'),
 'account_core':(str(ROOT/'backtest/ndx_cash_flow_return_accounting_research.py'),'ba4924f8f34ded1163d1b746faed236e968306004f2f15b559642cd4275f9417'),
 'stream_core':(str(ROOT/'backtest/ndx_research_json_rows_stream.py'),'b1a2ae63c68476dc952abf53bdd081e7f08cab3052ddc6fca5b61bd32091b86c')}
MIN_FREE_BYTES=5*1024**3
FLAGS=dict.fromkeys(('risk_recomputed','selection_reexecuted','controls_executed','orders_executed','point_in_time_verified','promotion_allowed','fresh_oos_claimed','economic_winner_selected','independent_account_readback_passed','full_transitive_source_closure_reverified'),False)

def require(ok,msg):
    if not ok:raise ValueError(msg)
def enc(v):return json.dumps(v,sort_keys=True,separators=(',',':'),allow_nan=False).encode()
def sha(b):return hashlib.sha256(b).hexdigest()
def exact(a,b):require(enc(a)==enc(b),'Exact saved evidence mismatch')
def ref(p,h):return dict(path=str(p),sha256=h)
def valid(r):require(type(r)is dict and set(r)=={'path','sha256'} and type(r['path'])is str and type(r['sha256'])is str and len(r['sha256'])==64 and all(c in '0123456789abcdef'for c in r['sha256']),'Pending or invalid anchor');return r
def merge(s,r):valid(r);require(r['path']not in s or s[r['path']]==r['sha256'],'Conflicting source');s[r['path']]=r['sha256']
def read(r,s):
    merge(s,r);b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Consumed source SHA');return json.loads(b)
def save(p,v):
    b=enc(v)
    with p.open('xb')as f:f.write(b);f.flush();os.fsync(f.fileno())
    require(p.read_bytes()==b,'Durable saved bytes');return ref(p,sha(b))
def guard(s):
    require(sha(SOURCE.read_bytes())==LOADED,'Loaded wrapper drift')
    for p,h in s.items():require(sha(Path(p).read_bytes())==h,'Source drift '+p)
def module(r):
    b=Path(r['path']).read_bytes();require(sha(b)==r['sha256'],'Immediate private module SHA');m=types.ModuleType('_private_'+Path(r['path']).stem);exec(compile(b,r['path'],'exec'),m.__dict__);return m

def validate_parents(d,r):
    i,p,a=d['selection'],d['selection_publication'],d['selection_audit']
    require(i['schema']=='CASH_NEIGHBOR_COMBINED_STREAM_SELECTION_INDEX_V1' and i['status']=='COMPLETE_DECLARED_UNION_SELECTION','Complete selection only')
    require(p['schema']=='CASH_NEIGHBOR_COMBINED_STREAM_SELECTION_PUBLICATION_V1' and p['status']=='PUBLISHED_COMPLETE_DECLARED_UNION_SELECTION','Final selection receipt')
    require(a['schema']=='CASH_NEIGHBOR_COMBINED_SELECTION_INDEPENDENT_READBACK_V1' and a['status']=='PASS','Independent selection')
    exact(p['index_reference'],r['selection']);exact(a['index_reference'],r['selection']);exact(a['publication_reference'],r['selection_publication']);exact(a['reader_sha256'],r['selection_reader']['sha256']);exact(p['source_hashes'],i['source_hashes'])
    for v in (i,a):
        require(type(v['scenario_count'])is int and v['scenario_count']==40 and type(v['total_candidate_count'])is int and v['total_candidate_count']==304305,'Complete candidate denominator')
        for flag in ('risk_recomputed','account_executed','point_in_time_verified','promotion_allowed'):require(v[flag]is False,'Parent authority')
    require(a['complete_saved_score_order_independently_verified']is True,'Saved order audited')
    require(len(i['cases'])==len(a['cases'])==len(d['preparation']['rows'])==40,'Full forty rows')
    ids=[]
    for n,(case,audit,prep)in enumerate(zip(i['cases'],a['cases'],d['preparation']['rows'])):
        require(type(case['scenario_index'])is int and case['scenario_index']==n,'Original case position');exact(audit['scenario_index'],n);exact(case['scenario_id'],audit['scenario_id']);exact(case['scenario_id'],prep['scenario_id']);exact(case['status'],audit['status']);ids.append(case['scenario_id'])
    require(len(set(ids))==40,'Unique scenarios')
    for role in ('paired','paired_publication','preparation'):
        exact(i['input_references'][role],r[role])
    exact(d['paired_publication']['account_reference'],r['paired'])
    return ids

def prepare_requests(d,r,sources,cores):
    index=d['selection'];requests=[];coordinates=set()
    with Path(r['paired']['path']).open('rb')as f:
        stream=cores['stream_core'].JsonRowsStream(f)
        for n,token in enumerate(stream):
            require(n<40 and token['row_index']==n,'Complete original paired order');entry=index['cases'][n];folder=SEL/f'scenario-{n:02d}'
            require({p.name for p in folder.iterdir()}=={'started.json','ledger.jsonl','selection.json','publication.json'},'Exact successful selection case')
            local={};sr=entry['selection_reference'];pr=entry['publication_reference'];exact(sr['path'],str(folder/'selection.json'));exact(pr['path'],str(folder/'publication.json'))
            selected=read(sr,local);pub=read(pr,local);exact(pub['selection_reference'],sr);exact(selected['ledger_reference'],entry['ledger_reference']);exact(pub['ledger_reference'],entry['ledger_reference']);require(selected['requires_final_publication']is True and pub['requires_final_publication']is True,'Final index authorizes case')
            require(selected['schema']=='CASH_NEIGHBOR_SOURCE_BOUND_CASE_SELECTION_V1','Case selection schema');exact(selected['scenario_index'],n);exact(selected['selection']['scenario_id'],entry['scenario_id']);exact(selected['selection']['status'],entry['status'])
            cr=d['preparation']['rows'][n]['contract_reference'];require(index['source_hashes'].get(cr['path'])==cr['sha256'],'Bound scenario contract');prepared=read(cr,local)
            case=dict(prepared=prepared,selection=selected['selection'],old_paired_row=token['value'],selection_reference=dict(sr,json_pointer='/selection'),selection_audit_reference=dict(r['selection_audit'],json_pointer=f'/cases/{n}'),old_paired_reference=dict(r['paired'],json_pointer=f'/rows/{n}'))
            request=cores['request_core'].prepare_case(case,n);exact(request['scenario_id'],entry['scenario_id']);row=prepared['contract']['original_input_row'];e=row['cash_event'];coordinates.add((row['lane'],e['decision_date'],e['execution_date'],e['amount_usd']));guard(local)
            out=OUTPUT/f'scenario-{n:02d}';out.mkdir(exist_ok=False);rr=save(out/'request.json',dict(request=request,paired_row_byte_reference=dict(source_reference=r['paired'],byte_start=token['byte_start'],byte_stop=token['byte_stop'],row_sha256=token['sha256']),source_hashes=local,**FLAGS));requests.append(dict(scenario_index=n,scenario_id=request['scenario_id'],status=request['status'],request_reference=rr))
        summary=stream.summary
    require(len(requests)==40 and summary['complete_document_consumed']is True,'Whole paired EOF before dispatch');exact(summary['sha256'],r['paired']['sha256']);exact(summary['metadata']['source_hashes'],d['paired_publication']['source_hashes']);require(summary['metadata']['schema']=='OLD_HOLDING_TOPUP_PAIRED_PRICE_ONLY_ACCOUNT_V1','Paired source schema')
    core=cores['request_core'];require(coordinates=={(lane,day,execution,amount)for lane in core.LANES for day,execution,_ in core.CLOCKS for amount in ('1000','10000')},'Exact forty coordinates');guard(sources)
    return requests,summary

def verify_account(account,request,core):
    require(type(account)is dict and account['schema']=='BUY_ONLY_OPEN_CASH_FLOW_TWR_ACCOUNTING_V1','Returned account schema')
    args=request['accounting_request'];rows=account['rows'];require(len(rows)==len(args['sessions']),'Whole path rows');expected=request['expected_first_trade']
    for j,(row,session)in enumerate(zip(rows,args['sessions'])):
        exact(row['session'],session['session']);exact(row['holdings_after'],expected['proposed_holdings']);exact(row['buy_shares'],session['buy_shares']);require(core.number(row['cash_after_usd'])==core.number(expected['cash_after_usd']),'Saved cash after');require(core.number(row['cash_injection_usd'])==core.number(session['cash_injection_usd']),'Single saved flow');require(core.number(row['fees_usd'])==(core.number(expected['fees_usd'])if j==0 else 0),'Single fee')
    for key in ('gross_buy_usd','fees_usd','cash_after_usd'):require(core.number(rows[0][key])==core.number(expected[key]),'First saved plan reconciliation')
    for flag in ('dividends_modelled','corporate_actions_modelled','orders_executed','point_in_time_verified','promotion_allowed'):require(account[flag]is False,'Accounting authority')

def execute_requests(requests,sources,cores):
    completed=[];attempted=[];unresolved=[];failure=None
    for pos,entry in enumerate(requests):
        invoked=False;started=rawref=post=None
        try:
            guard(sources);local={};request_doc=read(entry['request_reference'],local);request=request_doc['request'];exact(request['scenario_id'],entry['scenario_id']);exact(request['scenario_index'],entry['scenario_index']);exact(request['status'],entry['status']);require(type(entry['scenario_index'])is int and entry['scenario_index']==pos,'Exact dispatch position');guard(request_doc['source_hashes']);guard(local)
            if entry['status']!='NEW_PATH_REQUIRED':
                require(entry['status']in ('REUSE_EXISTING_PAIRED_PATH','NO_FEASIBLE_IN_DECLARED_UNION') and request['accounting_request']is None,'No hidden dispatch');completed.append(dict(entry,outcome=entry['status'],candidate_reference=request['reused_candidate_path_reference'],control_reference=request['control_path_reference']));continue
            free=shutil.disk_usage(OUTPUT).free;require(type(free)is int and free>=MIN_FREE_BYTES,'RESOURCE_STOP_BEFORE_DISPATCH')
            folder=OUTPUT/f'scenario-{entry["scenario_index"]:02d}';require({p.name for p in folder.iterdir()}=={'request.json'},'Exclusive attempt, no retry')
            started=save(folder/'started.json',dict(schema='CASH_NEIGHBOR_SELECTED_PATH_STARTED_V1',request_reference=entry['request_reference'],source_hashes=sources,control_execution_allowed=False,**FLAGS))
            guard(sources);invoked=True;attempted.append(entry['scenario_id']);account=None;error=None
            try:account=cores['account_core'].account_path(**request['accounting_request'])
            except Exception as e:error=dict(type=type(e).__name__,message=str(e))
            rawref=save(folder/'raw.json',dict(schema='CASH_NEIGHBOR_SELECTED_PATH_RAW_V1',request_reference=entry['request_reference'],started_reference=started,account=account,error=error,account_call_attempt_count=1,returned_account_count=int(account is not None),**FLAGS))
            validation=None
            try:
                guard(sources);guard(local);guard(request_doc['source_hashes']);require(error is None,'Account exception');verify_account(account,request,cores['request_core'])
            except Exception as e:validation=dict(type=type(e).__name__,message=str(e))
            post=save(folder/'postcheck.json',dict(schema='CASH_NEIGHBOR_SELECTED_PATH_POSTCHECK_V1',outcome='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK'if validation is None else ('ACCOUNT_EXCEPTION'if error else 'VALIDATION_FAILURE'),raw_reference=rawref,started_reference=started,validation_error=validation,**FLAGS))
            require(validation is None,'Saved account failure');require({p.name for p in folder.iterdir()}=={'request.json','started.json','raw.json','postcheck.json'},'Exact attempt files');guard(sources)
            completed.append(dict(entry,outcome='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK',raw_reference=rawref,postcheck_reference=post,control_reference=request['control_path_reference']))
        except Exception as e:
            failure=dict(scenario_id=entry['scenario_id'],scenario_index=entry['scenario_index'],dispatch_invoked=invoked,error_type=type(e).__name__,error=str(e),started_reference=started,raw_reference=rawref,postcheck_reference=post)
            if invoked:unresolved.append(entry['scenario_id'])
            break
    done={r['scenario_id']for r in completed};remaining=[r['scenario_id']for r in requests if r['scenario_id']not in done and r['scenario_id']not in unresolved]
    return dict(schema='CASH_NEIGHBOR_SELECTED_PATHS_RESULT_V1',status='COMPLETE_PENDING_INDEPENDENT_READBACK'if failure is None else 'STOPPED_NO_RETRY',scenario_count=40,completed_rows=completed,attempted_scenario_ids=attempted,unresolved_scenario_ids=unresolved,undispatched_scenario_ids=remaining,failure=failure,**FLAGS)

def verify_saved_outputs(requests,result):
    byid={row['scenario_id']:row for row in result['completed_rows']}
    for entry in requests:
        folder=OUTPUT/f'scenario-{entry["scenario_index"]:02d}';r=entry['request_reference'];require(sha(Path(r['path']).read_bytes())==r['sha256'],'Saved request final bytes')
        row=byid[entry['scenario_id']];expected={'request.json'}
        if row['outcome']=='ACCOUNT_SAVED_PENDING_INDEPENDENT_READBACK':
            expected|={'started.json','raw.json','postcheck.json'}
            for key in ('raw_reference','postcheck_reference'):
                q=row[key];require(sha(Path(q['path']).read_bytes())==q['sha256'],'Saved account final bytes')
            post=json.loads(Path(row['postcheck_reference']['path']).read_bytes());q=post['started_reference'];require(sha(Path(q['path']).read_bytes())==q['sha256'],'Saved attempt final bytes')
        require({p.name for p in folder.iterdir()}==expected,'Final case namespace')


def run(*,execute=False):
    require(execute is True,'Explicit execute');require(not OUTPUT.exists(),'Create-only, no retry');r={k:valid(ref(*v))for k,v in BOUND.items()};sources={str(SOURCE):LOADED};d={};cores={}
    for k,v in r.items():
        if k=='paired':continue
        if k.endswith('_core'):merge(sources,v);cores[k]=module(v)
        elif k=='selection_reader':merge(sources,v)
        else:d[k]=read(v,sources)
    guard(sources);ids=validate_parents(d,r);require(not (SEL/'failure.json').exists() and not (Path(r['selection_audit']['path']).parent/'failure.json').exists(),'Failed selection blocked')
    OUTPUT.mkdir(parents=True,exist_ok=False);result=None
    try:
        save(OUTPUT/'started.json',dict(schema='CASH_NEIGHBOR_SELECTED_PATHS_STARTED_V1',input_references=r,source_hashes=sources,scenario_ids=ids,minimum_free_bytes=MIN_FREE_BYTES,paired_authenticated_once_at_eof=True,**FLAGS))
        requests,summary=prepare_requests(d,r,sources,cores);result=execute_requests(requests,sources,cores);result.update(input_references=r,source_hashes=sources,paired_stream_summary=summary)
        rr=save(OUTPUT/'result.json',result);guard(sources)
        if result['failure']is not None:save(OUTPUT/'failure.json',dict(status='STOPPED_NO_RETRY',result_reference=rr,failure=result['failure'],**FLAGS));return rr
        verify_saved_outputs(requests,result);pr=save(OUTPUT/'publication.json',dict(schema='CASH_NEIGHBOR_SELECTED_PATHS_PUBLICATION_V1',status='PUBLISHED_PENDING_INDEPENDENT_READBACK',result_reference=rr,source_hashes=sources,**FLAGS));guard(sources);verify_saved_outputs(requests,result);require({p.name for p in OUTPUT.iterdir()}=={'started.json','result.json','publication.json'}|{f'scenario-{i:02d}'for i in range(40)},'Exact final namespace');require(sha(Path(rr['path']).read_bytes())==rr['sha256'] and sha(Path(pr['path']).read_bytes())==pr['sha256'],'Final saved bytes');return rr
    except BaseException as e:
        if not (OUTPUT/'failure.json').exists():save(OUTPUT/'failure.json',dict(status='FAILED_DO_NOT_CONSUME',error_type=type(e).__name__,error=str(e),partial_result=result,undispatched_scenario_ids=ids if result is None else result['undispatched_scenario_ids'],unresolved_scenario_ids=[] if result is None else result['unresolved_scenario_ids'],account_dispatch_started=bool(result and result['attempted_scenario_ids']),retry_allowed=False,**FLAGS))
        raise

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--execute',action='store_true');print(json.dumps(run(execute=p.parse_args().execute)))

