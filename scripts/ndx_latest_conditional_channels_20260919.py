"""Bounded arithmetic over 101 observed channels; no fitted or admitted universe."""
import argparse,copy,hashlib,json,os,sys,tempfile
from fractions import Fraction
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT))
from backtest import ndx_conditional_channel_input_research as kernel
from backtest import ndx_current_receipt_quote_guard_research as capture
from backtest import ndx_simple_split_quote_guard_research as matcher
from backtest import ndx_simple_split_quote_guard_v2_research as denominator
from backtest import ndx_post_action_interval_research as interval
from backtest import ndx_root_price_archive_contract_research as archive
from scripts import ndx_latest_all_ndx_conditional_manifest_20260919 as universe
BASE=ROOT/'data/cache/research'
MANIFEST=BASE/'latest_all_ndx_conditional_manifest_20260919_v1/manifest.json'
MANIFEST_SHA='be842f56db29f989af87885079c8807334089b36334c4c8c743d9ab2c33007e2'
REGISTRY=BASE/'standard_split_exact_gap_20260919_v1/registry_readback.json'
REGISTRY_SHA='61c1a7a07f1a3ad65d3fffac43e8a8b4494c58c67192d93808333073f711c32e'
ADDITIONS=BASE/'current_mstr_pdf_split_20260919_v1/three_split_facts.json'
ADDITIONS_SHA='e02e164554cb56f2aaed60b89e8adc3f059144bb350e88d7206e2fe74dbd401c'
KERNEL_SHA='68595f10bde6d917682d8543ebd081462f0df90b0e330f606ca1ac9a2c596804'
FALSE=('point_in_time_verified','promotion_allowed','legal_training_input_admitted','fit_performed','security_identity_verified','execution_authorized','complete_corporate_action_history_verified')
LOADED={str(Path(m.__file__).resolve()):hashlib.sha256(Path(m.__file__).read_bytes()).hexdigest() for m in (kernel,capture,matcher,denominator,interval,archive,universe)}
LOADED[str(Path(__file__).resolve())]=hashlib.sha256(Path(__file__).read_bytes()).hexdigest()
for module in (capture.gap,capture.nominal):
    LOADED[str(Path(module.__file__).resolve())]=hashlib.sha256(Path(module.__file__).read_bytes()).hexdigest()

def digest(value):return hashlib.sha256(json.dumps(value,sort_keys=True,allow_nan=False,separators=(',',':')).encode()).hexdigest()
def read(path,sha,sources):
    path=Path(path).resolve();raw=path.read_bytes()
    if hashlib.sha256(raw).hexdigest()!=sha:raise ValueError('External SHA differs')
    archive.merge(sources,{str(path):sha});return json.loads(raw,object_pairs_hook=universe.unique)
def inherit(value,sources):
    for key in ('source_hashes','historical_expected_source_hashes'):
        if key in value:archive.merge(sources,value[key])
def verify_sources(sources):
    archive.merge(dict(sources),LOADED)
    if LOADED[str(Path(kernel.__file__).resolve())]!=KERNEL_SHA:raise ValueError('Frozen kernel differs')
    return archive.verify_expected_sources(sources,archive.load_contract())
def exclusive_publish(path,value):
    path=Path(path);path.parent.mkdir(parents=True,exist_ok=True)
    fd,name=tempfile.mkstemp(prefix='.'+path.name+'.',dir=path.parent)
    try:
        with os.fdopen(fd,'wb') as handle:
            handle.write(json.dumps(value,sort_keys=True,allow_nan=False,indent=2).encode());handle.flush();os.fsync(handle.fileno())
        os.link(name,path)
    finally:Path(name).unlink(missing_ok=True)
    return dict(path=str(path.resolve()),sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def event_policy(ticker,decoded,request,events,post=None):
    if post is not None:
        floor=interval.SUPPORTED[ticker][0]
        if post['first_post_action_session']!=floor:raise ValueError('Hard post-action floor differs')
        observed=json.loads(decoded)['chart']['result'][0].get('events',{}).get('splits',{})
        policies=[]
        for key,e in observed.items():
            day=kernel._session(e['date'])
            if key!=str(e['date']) or day>floor:raise ValueError('Later/invalid post-action event')
            ratio=Fraction(str(kernel._number(e['numerator'])))/Fraction(str(kernel._number(e['denominator'])))
            policies.append(dict(session=day,numerator=ratio.numerator,denominator=ratio.denominator,kind='BEFORE_PARTITION_UNMODELLED'))
        if floor not in [e['session'] for e in policies]:raise ValueError('Boundary event absent')
    else:
        matches=matcher.match_returned_events(decoded=decoded,ticker=ticker,specific_events=events,blocked_tickers={'CMCSA','TRI','LCID','LRCX','HON','EXC','WDC','ILMN','AZN','SIRI'})
        denominator.validate_known_event_denominator(ticker=ticker,matches=matches,events=events,request=request)
        policies=[dict(session=e['first_adjusted_trading_date'],numerator=int(e['numerator']),denominator=int(e['denominator']),kind='ORDINARY_SPLIT') for e in matches]
    return sorted(policies,key=lambda x:x['session'])

def load_prepared():
    sources=dict(LOADED);manifest=read(MANIFEST,MANIFEST_SHA,sources);inherit(manifest,sources)
    old=read(REGISTRY,REGISTRY_SHA,sources);extra=read(ADDITIONS,ADDITIONS_SHA,sources)
    inherit(old,sources);inherit(extra,sources)
    events=copy.deepcopy(old['events'])+[dict(e,simple_split_guard_eligible=True) for e in extra['events']]
    if len(events)!=28 or len({(e['ticker'],e['first_adjusted_trading_date']) for e in events})!=28:raise ValueError('Unique 28-event registry required')
    eligible=[e for e in events if e['simple_split_guard_eligible'] is True]
    if len(eligible)!=26:raise ValueError('26 eligible specific events required')
    calendar=manifest['observed_reference_calendar'][-127:];tasks=[];arguments={}
    for row in manifest['rows']:
        ticker=row['ticker'];task=dict(ticker=ticker,manifest_row_sha256=digest(row),mode='CALCULATE',reason=None)
        if row['price_status']=='BLOCKED_NO_CONDITIONAL_PRICE_REFERENCE':task.update(mode='BLOCKED',reason='NO_CONDITIONAL_PRICE_REFERENCE')
        elif not row['coverage']['windows']['latest_fit_adjacent_prices']['date_coverage_complete']:task.update(mode='BLOCKED',reason='INSUFFICIENT_127_ADJACENT_PRICES')
        if task['mode']=='CALCULATE':
            ref=row['conditional_quote_reference']['artifact_reference'];quote=read(ref['path'],ref['sha256'],sources);inherit(quote,sources)
            post=row['price_status']=='CONDITIONAL_POST_ACTION_REFERENCE';result=quote['result']
            rawref=quote['raw_decoding_evidence'] if post else quote
            decoded,receipt,request,evidence=capture.load_capture(ticker=ticker,raw_path=rawref['raw_path'],raw_sha256=rawref['raw_sha256'],sources=sources)
            floor=None;boundary=None
            if post:
                boundary=quote['original_interval_plan_row']['proposed_interval'];floor=interval.SUPPORTED[ticker][0]
                if boundary['ticker']!=ticker or boundary['first_post_action_session']!=floor:raise ValueError('Bound interval differs')
                rows=[dict(r,split_factor=r['factor'],split_factor_numerator=r['factor_numerator'],split_factor_denominator=r['factor_denominator'],later_split_effective_sessions=r['returned_later_split_like_events']) for r in result['rows']]
            else:
                rows=result['reconstruction']['rows'];floor=result.get('regular_way_floor')
                if ticker in capture.PARTITION_REQUIRED and floor is None:raise ValueError('Regular partition required')
            policy=event_policy(ticker,decoded,request,eligible,boundary)
            args=dict(ticker=ticker,raw_bytes=decoded,quote_rows=rows,calendar=calendar,cutoff=universe.CUTOFF,exclude_on_or_after=receipt['completed_training_excludes_dates_on_or_after'],event_policy=policy,regular_floor=floor)
            task.update(quote_reference=ref,raw_reference=dict(path=rawref['raw_path'],sha256=rawref['raw_sha256']),event_policy=policy,regular_floor=floor,
                input_sha256=digest(dict(args,raw_bytes_sha256=hashlib.sha256(args['raw_bytes']).hexdigest(),raw_bytes=None)))
            arguments[ticker]=args
        tasks.append(task)
    if len(tasks)!=101 or len({t['ticker'] for t in tasks})!=101 or len(arguments)!=96:raise ValueError('Full 101/96/5 denominator differs')
    partition=verify_sources(sources)
    plan=dict(schema='LATEST_CONDITIONAL_CHANNEL_PLAN_V1',manifest_reference=dict(path=str(MANIFEST),sha256=MANIFEST_SHA),cutoff=universe.CUTOFF,planned=101,numerical_channels=96,blocked_channels=5,tasks=tasks,historical_expected_source_hashes=sources,archive_resolution=partition,**dict.fromkeys(FALSE,False))
    return plan,arguments

def calculate(task,args,plan_sha):
    result=None if task['mode']=='BLOCKED' else kernel.build_channel_input(**args)
    return dict(schema='LATEST_CONDITIONAL_CHANNEL_TASK_V1',plan_sha256=plan_sha,task=task,status='BLOCKED' if result is None else 'CONDITIONAL_NUMERIC_RESULT',result=result,**dict.fromkeys(FALSE,False))

def scan_orphans(folder,entries):
    allowed={Path(e['path']).name for e in entries}|{e['ticker']+'.started.json' for e in entries}
    for path in Path(folder).glob('*.json'):
        if path.name not in allowed and not path.name.startswith('index_'):raise ValueError('Unindexed started/result refuses automatic retry')

def execute(plan_path,plan_sha,folder,*,max_new,index_path=None,index_sha=None):
    if type(max_new) is not int or not 0<=max_new<=101:raise ValueError('Explicit bounded budget 0..101 required')
    sources={};saved=read(plan_path,plan_sha,sources);plan,args=load_prepared()
    if digest(saved)!=digest(plan):raise ValueError('Plan must reproduce complete hard source preparation')
    archive.merge(sources,plan['historical_expected_source_hashes']);folder=Path(folder).resolve();folder.mkdir(parents=True,exist_ok=True)
    entries=[]
    if (index_path is None)!=(index_sha is None):raise ValueError('External index path and SHA required together')
    if index_path is not None:
        index=read(index_path,index_sha,sources);entries=index['entries']
        expected=index_value(entries,plan_sha,folder)
        if digest(index)!=digest(expected):raise ValueError('Exact recovery schema/count/status required')
    if len(entries)>101 or [e['ticker'] for e in entries]!=[t['ticker'] for t in plan['tasks'][:len(entries)]]:raise ValueError('Completed ordered prefix required')
    scan_orphans(folder,entries)
    for entry,task in zip(entries,plan['tasks']):
        if entry['path']!=str(folder/(task['ticker']+'.json')):raise ValueError('Saved result address differs')
        marker=read(folder/(task['ticker']+'.started.json'),entry['started_sha256'],sources)
        if digest(marker)!=digest(dict(schema='LATEST_CHANNEL_ATTEMPT_V1',plan_sha256=plan_sha,task=task,attempt_count=1)):raise ValueError('Original exclusive attempt differs')
        if digest(read(entry['path'],entry['sha256'],sources))!=digest(calculate(task,args.get(task['ticker']),plan_sha)):raise ValueError('Saved result fails raw arithmetic reconstruction')
    verify_sources(sources)
    pending=plan['tasks'][len(entries):len(entries)+max_new]
    for position,task in enumerate(pending):
        ticker=task['ticker'];marker=exclusive_publish(folder/(ticker+'.started.json'),dict(schema='LATEST_CHANNEL_ATTEMPT_V1',plan_sha256=plan_sha,task=task,attempt_count=1))
        archive.merge(sources,{marker['path']:marker['sha256']})
        if task['mode']=='CALCULATE':
            refs=[task['quote_reference'],task['raw_reference']]
            rawfolder=Path(task['raw_reference']['path']).parent
            refs += [dict(path=str(rawfolder/(ticker+suffix)),sha256=sources[str(rawfolder/(ticker+suffix))]) for suffix in ('.receipt.json','.started.json','.decoded.json')]
            for ref in refs:
                if hashlib.sha256(Path(ref['path']).read_bytes()).hexdigest()!=ref['sha256']:raise ValueError('Actual task source changed')
        value=calculate(task,args.get(ticker),plan_sha)
        # Refuse publication if the exclusive attempt or any numerical source changed.
        for path,h in dict(LOADED,**{marker['path']:marker['sha256']}).items():
            if hashlib.sha256(Path(path).read_bytes()).hexdigest()!=h:raise ValueError('Loaded source/attempt changed')
        ref=exclusive_publish(folder/(ticker+'.json'),value);archive.merge(sources,{ref['path']:ref['sha256']})
        entries.append(dict(ticker=ticker,**ref,started_sha256=marker['sha256']))
        if position==len(pending)-1:verify_sources(sources)
        index=index_value(entries,plan_sha,folder);output=exclusive_publish(folder/('index_'+digest(index)+'.json'),index)
        if position==len(pending)-1:verify_sources(sources)
        print(json.dumps(output),flush=True)
    verify_sources(sources)
    return index_value(entries,plan_sha,folder)

def index_value(entries,plan_sha,folder):
    return dict(schema='LATEST_CHANNEL_INDEX_V1',plan_sha256=plan_sha,output_directory=str(folder),planned=101,completed=len(entries),status='COMPLETE' if len(entries)==101 else 'PARTIAL',entries=entries,**dict.fromkeys(FALSE,False))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--plan',required=True);p.add_argument('--execute',action='store_true');p.add_argument('--plan-sha');p.add_argument('--folder');p.add_argument('--max-new',type=int,default=0);p.add_argument('--index');p.add_argument('--index-sha');a=p.parse_args()
    if a.execute:
        if not a.plan_sha or not a.folder:p.error('Execution requires --plan-sha and --folder')
        print(json.dumps(execute(a.plan,a.plan_sha,a.folder,max_new=a.max_new,index_path=a.index,index_sha=a.index_sha)))
    else:
        plan,_=load_prepared();ref=exclusive_publish(a.plan,plan);verify_sources(plan['historical_expected_source_hashes']);print(json.dumps(ref))
