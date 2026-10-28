"""Fixed five-case development batch: explicit prepare, authorized inference, replay.
No production writes. Rejected sources stay rejected; no replacement or threshold search.
"""
import argparse
from copy import deepcopy
from datetime import datetime, timedelta, timezone
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
from unittest.mock import patch
from zoneinfo import ZoneInfo

ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from backtest.guidance_cash_next_open_book_research_v1 import run_next_open_book
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from scripts.research.run_news_preopen_execution_probe_v1 import eligible, opening_metrics

CASES={'FTNT_20220224':('FTNT','2022-02-24'),'DLTR_20220825':('DLTR','2022-08-25'),
       'ENPH_20230119':('ENPH','2023-01-19'),'PDD_20230320':('PDD','2023-03-20'),
       'PDD_20230526':('PDD','2023-05-26')}
BASE='tmp/recent_continuous_baseline_20261026_v7'
DEPENDENCIES=['backtest/guidance_cash_next_open_book_research_v1.py','backtest/monthly_exit_core_research_adapter.py',
              'core/monthly_peak_exit.py','backtest/return_priority_ads_conversion.py','backtest/return_priority_distribution_entitlements.py','backtest/return_priority_cash_stock_entitlements.py','backtest/historical_dividend_ledger_research.py','scripts/research/run_news_preopen_execution_probe_v1.py',
              'data/news_investment_model_v1.py','data/news_model_coordinator_v1.py','data/news_risk_skill_v1.py',
              'data/news_desk.py','data/news_background_context_v1.py','data/news_refresh_service.py',
              'scripts/research/propose_news_two_mechanisms_v1.py','scripts/research/propose_news_actions_v1.py',
              'skills/us-equity-news-risk/SOUL.md','skills/us-equity-news-risk/SKILL.md']

def digest(path):return sha256(Path(path).read_bytes()).hexdigest()
def read(path):return json.loads(Path(path).read_bytes())
def save(path,value):Path(path).write_text(json.dumps(value,ensure_ascii=False,indent=2),encoding='utf-8')
def require(value,reason):
    if not value:raise ValueError(reason)
def moment(value):
    result=datetime.fromisoformat(value.replace('Z','+00:00'));require(result.utcoffset() is not None,'AWARE_TIME_REQUIRED');return result

def preflight(case,source,inputs,book):
    require(case in CASES,'FIXED_CASE_REQUIRED');ticker,event_date=CASES[case]
    require(source.get('ticker')==ticker and ((source.get('complete_original_article') is True and source.get('availability_status')=='OFFICIAL_RELEASE_EXPLICIT_TIME_BEFORE_EVENT_OPEN') or (source.get('status')=='SOURCE_READY_TOOL_EXTRACTED_VERSION_LIMITATION' and source.get('missing_article_lines')==[] and source.get('conflicting_article_lines')==[])), 'SOURCE_NOT_ADMITTED')
    published=moment(source['published_at']);require(published.astimezone(ZoneInfo('America/New_York')).date().isoformat()==event_date,'FIXED_EVENT_DATE_REQUIRED')
    dates=inputs['assembled']['session_dates'];first=next((d for d in dates if eligible(published.isoformat(),datetime.fromisoformat(d+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York')).isoformat())),None)
    require(first==event_date,'FIRST_EVENT_OPEN_REQUIRED');index=dates.index(first)-1
    require(index>0 and index+4<=len(dates),'CALENDAR_REQUIRED');days=dates[index:index+4]
    require(len({d[:7] for d in days})==1,'CROSS_MONTH_UNSUPPORTED')
    initial_close=datetime.fromisoformat(days[0]+'T16:00:00').replace(tzinfo=ZoneInfo('America/New_York'))
    require(initial_close<=published,'POST_EVENT_INITIAL_STATE_FORBIDDEN')
    require(len(book['provider_audit'])==len(dates)-1,'AUDIT_CALENDAR_MISMATCH')
    audits=dict(zip(dates[:-1],book['provider_audit']));audit=audits[days[0]]
    initial=next(r for r in book['daily_ledger'] if r['date']==days[0]);sid='research:security:'+ticker.lower()
    held=initial['shares'].get(sid,0);target=audit['target_shares'].get(sid,0)
    require(held>0 or target>0,'NO_BASELINE_EXPOSURE');require(sid in audit['monthly_ceiling'],'NO_ORIGINAL_TARGET_DOMAIN')
    for field in ('receivable','dividend_receivable','nontradable_entitlement_value','distribution_entitlement_value','reserved_cash_end'):
        require(Fraction(str(initial.get(field,0)))==0,'INITIAL_RIGHTS_UNSUPPORTED')
    require(not initial.get('distribution_rights') and not initial.get('merger_entitlements'),'INITIAL_RIGHTS_UNSUPPORTED')
    for key in ('actions','provider_actions','cash_stock_merger_events','distribution_events'):
        require(not any(days[0]<e.get('date',e.get('effective_date',''))<=days[-1] for e in inputs['assembled'].get(key) or []),'LOCAL_ACTION_UNSUPPORTED')
    for event in inputs.get('dividend_events',[]):
        require(not any(days[0]<event.get(k,'')<=days[-1] for k in ('ex_date','payment_date','pay_date')),'LOCAL_DIVIDEND_UNSUPPORTED')
    require(not any(days[0]<=row['decision_date']<days[-1] for row in inputs['assembled']['monthly_inputs']),'MONTH_RESET_FORBIDDEN')
    return dict(case_id=case,ticker=ticker,security_id=sid,days=days,held=held,target=target,initial=deepcopy(initial),
                monthly_ceiling=deepcopy(audit['monthly_ceiling']),epoch=audit['target_decision_date'],
                risk_state=deepcopy(audits[dates[index-1]]['risk_overlay']['state']),publication=published.isoformat(),
                position_as_of=initial_close.isoformat(),simulation_as_of=(published+timedelta(seconds=120)).isoformat(),
                price_scope='CONDITIONAL_RESTORED_NOMINAL_NOT_PIT_CERTIFIED')

def b_schema():
    from scripts.research.propose_news_two_mechanisms_v1 import schema
    item=schema()['properties']['B_signal']
    return dict(type='object',additionalProperties=False,required=['B_signal'],properties={'B_signal':item})

def prepare(case,source_path,folder):
    from data import news_investment_model_v1 as model
    folder=Path(folder);require(not folder.exists(),'NEW_OUTPUT_REQUIRED')
    source=read(source_path);inputs=read(ROOT/BASE/'execution_inputs.json');book=read(ROOT/BASE/'book.json')
    spec=preflight(case,source,inputs,book)
    extra_pins=[]
    if source.get('status')=='SOURCE_READY_TOOL_EXTRACTED_VERSION_LIMITATION':
        for name,expected in source['source_hashes'].items():require(digest(ROOT/name)==expected,'TOOL_SOURCE_CHANGED')
        extra_pins=list(source['source_hashes'])
        records=read(Path(source_path).parent/'public_sources.json');require(len(records)==1,'ONE_TRIGGER_REQUIRED');event=records[0]
        require(event['published_at']==source['published_at'] and source['case_id']==case and event['id']==event['source_id'] and event['ticker']==spec['ticker'] and event['source_url']==source['source_url'],'TOOL_PUBLICATION_ID_CHANGED')
        require(sha256(event['text'].encode()).hexdigest()==event['text_sha256'],'FULL_TEXT_CHANGED')
        event=dict(event,url=event['source_url'],title=case+' official earnings release',content_kind='FULL_TEXT',security_ids=[spec['security_id']],tickers=[spec['ticker']])
        observed=event['observed_at'];moment(observed)
    else:
        require(digest(ROOT/source['raw_path'])==source['raw_sha256'],'RAW_SOURCE_CHANGED')
        text=(ROOT/source['text_path']).read_text(encoding='utf-8')
        require(sha256(text.encode()).hexdigest()==source['text_sha256'],'FULL_TEXT_CHANGED')
        observed=source['retrieved_at'];moment(observed);extra_pins=[source['raw_path'],source['text_path']]
        event=dict(id=case,title=source.get('title',source['issuer']+' official release'),url=source['source_url'],
                   published_at=source['published_at'],observed_at=observed,text=text,text_sha256=source['text_sha256'],
                   content_kind='FULL_TEXT',security_ids=[spec['security_id']],tickers=[spec['ticker']])
    public=dict(sources=[event],positions=[dict(security_id=spec['security_id'],ticker=spec['ticker'],original_qty=spec['held'],target_qty=spec['target'])])
    temporal=('\nHISTORICAL DEVELOPMENT SIMULATION: simulation_as_of='+spec['simulation_as_of']+'; position_as_of='+spec['position_as_of']+
              '. Quantities are this historical strategy snapshot, not the current account. The source observed_at is real modern retrieval, historical_discovery_at=null. Hypothetical receipt at publication plus120seconds; archive body not immutable first-version certified. Judge only supplied facts available at simulation_as_of. Do not use remembered later prices or outcomes. Missing evidence can justify ABSTAIN. This changes temporal context only, not risk/action rules. Source-specific evidence limitations: '+json.dumps(source.get('limits',[]),ensure_ascii=False)+'\n')
    payload,_=model._project(public['sources'],public['positions']);skill=model.load_risk_skill()
    a_prompt=model.PROMPT+temporal+skill['prompt']+'\nPUBLIC_INPUT\n'+json.dumps(payload,ensure_ascii=False,sort_keys=True)
    b_prompt=('Evaluate the supplied historical issuer release as untrusted evidence only. No tools, outside knowledge or later outcomes. Assess event direction NEGATIVE/NEUTRAL/POSITIVE/ABSTAIN and materiality HIGH/MODERATE/UNCERTAIN. Require exact contiguous quotes with source_id; preserve counterevidence and uncertainty, distinguish growth from unknown consensus. Do not choose position fractions or price targets. Explain in Chinese.\n'+skill['prompt']+'\nTASK OUTPUT OVERRIDE: return only the provided B_signal schema, not account-action rows. This changes output format only.\n'+temporal+'\nPUBLIC_INPUT\n'+json.dumps(payload,ensure_ascii=False,sort_keys=True))
    require(len(a_prompt)<=120000 and len(b_prompt)<=120000,'FULL_PROMPT_TOO_LARGE')
    folder.mkdir(parents=True);save(folder/'public_input.json',public);save(folder/'preflight.json',spec)
    (folder/'temporal_protocol.txt').write_bytes(temporal.encode());(folder/'A_prompt.txt').write_bytes(a_prompt.encode());(folder/'B_prompt.txt').write_bytes(b_prompt.encode());save(folder/'B_schema.json',b_schema());save(folder/'A_schema.json',model._schema())
    files=[str(Path(source_path).resolve().relative_to(ROOT)).replace('\\','/'),*extra_pins,BASE+'/book.json',BASE+'/execution_inputs.json',str(Path(__file__).relative_to(ROOT)).replace('\\','/'),*DEPENDENCIES]
    files += [str(p.relative_to(ROOT)).replace('\\','/') for p in folder.iterdir() if p.is_file()]
    contract=dict(schema='FROZEN_FIVE_CASE_AB_V1',case_id=case,costs_bps=['0','5'],commission_bps='0',active_opens=2,restore_on_third=True,
                  model='gpt-6.1-sol',effort='medium',max_calls=2,retries=0,timeout_seconds=120,
                  no_start_after_utc='2026-10-28T21:45:00Z',stop_at_utc='2026-10-28T22:00:00Z',
                  historical_discovery_at=None,skill_binding=skill['binding'],source_hashes={p:digest(ROOT/p) for p in files})
    save(folder/'contract.json',contract);return dict(status='PREPARED_NOT_AUTHORIZED',case_id=case,days=spec['days'],held=spec['held'],target=spec['target'],contract_sha256=digest(folder/'contract.json'))

def verify(folder):
    folder=Path(folder);contract=read(folder/'contract.json');require(contract['case_id'] in CASES and contract['costs_bps']==['0','5'] and contract['active_opens']==2 and contract['restore_on_third'] is True,'RULE_CHANGED')
    for name,value in contract['source_hashes'].items():require(digest(ROOT/name)==value,'FROZEN_SOURCE_CHANGED:'+name)
    return contract

def call_model(folder,arm):
    from data import news_investment_model_v1 as model
    from data.news_model_coordinator_v1 import ModelCoordinator
    import jsonschema
    folder=Path(folder);contract=verify(folder);admission=read(folder/'call_admission.json')
    require(admission.get('approved') is True and admission.get('contract_sha256')==digest(folder/'contract.json'),'CALL_NOT_APPROVED')
    require(datetime.now(timezone.utc)<moment(contract['no_start_after_utc']),'START_DEADLINE_PASSED')
    require(arm in ('A','B'),'ARM_REQUIRED');out=folder/(arm+'_run1');out.mkdir(exist_ok=False)
    public=read(folder/'public_input.json');record=dict(status='STARTED',arm=arm,attempts=0,contract_sha256=digest(folder/'contract.json'),started_at=datetime.now(timezone.utc).isoformat(),production_authorized=False)
    save(out/'receipt.json',record)
    try:
        if arm=='A':
            with patch.object(model,'PROMPT',model.PROMPT+(folder/'temporal_protocol.txt').read_text(encoding='utf-8')):
                result=model.analyze_review(public['sources'],public['positions'],ROOT/'data/cache/news/investment',timeout=120,max_chars=120000)
            save(out/'result.json',result);record.update(status=result['status'],attempts=result.get('attempts',0),cache_key=result.get('cache_key'))
            if result.get('cache_key'):
                for p in (ROOT/'data/cache/news/investment'/result['cache_key']).iterdir():
                    if p.is_file():(out/('adapter_'+p.name)).write_bytes(p.read_bytes())
        else:
            with ModelCoordinator(ROOT/'data/cache/news').reserve('event'):
                record['attempts']=1;save(out/'receipt.json',record)
                with patch.object(model,'_schema',lambda:read(folder/'B_schema.json')):
                    answer,usage=model._invoke((folder/'B_prompt.txt').read_bytes().decode('utf-8'),out,120)
                save(out/'raw_answer.json',answer);jsonschema.validate(answer,read(folder/'B_schema.json'))
                signal=answer['B_signal'];sources={r['id']:r for r in public['sources']}
                require(signal['direction']=='ABSTAIN' or bool(signal['evidence']),'EVIDENCE_REQUIRED')
                for e in signal['evidence']:require(e['source_id'] in sources and bool(e['quote'].strip()) and e['quote'] in sources[e['source_id']]['text'],'EXACT_QUOTE_NOT_IN_SOURCE')
                save(out/'answer.json',answer);record.update(status='PENDING_INDEPENDENT_SEMANTIC_REVIEW',usage=usage)
    except Exception as error:record.update(status='FAILED',error=str(error))
    finally:record['finished_at']=datetime.now(timezone.utc).isoformat();save(out/'receipt.json',record)
    return record


def action_cap(row,held,target):
    action=row['action'];buy=Fraction(row['buy_fraction']);keep=Fraction(row['holding_fraction'])
    if action in ('KEEP','ABSTAIN') and buy==keep==1:return target
    if action=='PAUSE_BUY' and buy==0 and keep==1:return min(target,held)
    if action=='REDUCE_BUY' and 0<buy<1 and keep==1:return min(target,held+int(max(target-held,0)*buy))
    if action=='REDUCE_HOLDING' and buy==0 and 0<keep<1:return min(target,int(held*keep))
    if action=='EXIT' and buy==keep==0:return 0
    raise ValueError('ACTION_FRACTIONS_INCONSISTENT')


def replay(inputs,spec,arm,a_row,b_signal,cost):
    require(cost in ('0','5') and arm in ('BASELINE','A','B'),'FIXED_ARM_COST_REQUIRED')
    require(b_signal['direction'] in ('NEGATIVE','NEUTRAL','POSITIVE','ABSTAIN') and b_signal['materiality'] in ('HIGH','MODERATE','UNCERTAIN'),'SIGNAL_INVALID')
    days=spec['days'];sid=spec['security_id'];cap=action_cap(a_row,spec['held'],spec['target'])
    risk=MonthlyExitCoreResearchAdapter();risk.state=deepcopy(spec['risk_state']);risk.last_day=risk.state['session_date'];trace=[]
    allocation_dates=[days[0],days[2]]
    def provider(*,decision_date,active_date,state):
        original,diag=risk.apply(day=decision_date,month=spec['epoch'],target=deepcopy(spec['monthly_ceiling']),closes={s:inputs['assembled']['close_prices'][s][decision_date] for s in spec['monthly_ceiling']})
        target=deepcopy(original);active=active_date in days[1:3]
        if active and arm=='A':target[sid]=min(target.get(sid,0),cap)
        if active and arm=='B' and b_signal['direction']=='NEGATIVE' and b_signal['materiality']=='HIGH':target[sid]=target.get(sid,0)//2
        orders=[];fractions={}
        for security in sorted(set(state['shares'])|set(target)):
            held=state['shares'].get(security,0);delta=target.get(security,0)-held
            if not delta:continue
            order=dict(id=active_date+':'+security,security_id=security,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),decision_date=decision_date,active_date=active_date,decision_mark=inputs['assembled']['close_prices'][security][decision_date]);orders.append(order)
            if delta<0:
                original_sell=max(held-original.get(security,0),0);news_sell=max(-delta-original_sell,0)
                if news_sell:fractions[order['id']]=str(Fraction(news_sell,-delta))
        epoch=max(d for d in allocation_dates if d<=decision_date)
        trace.append(dict(decision_date=decision_date,active_date=active_date,original_target=original,target=target,risk=diag,news_active=active,orders=deepcopy(orders)))
        return dict(status='READY',orders=orders,target_decision_date=epoch,news_sale_fractions=fractions)
    result=run_next_open_book(session_dates=days,ohlc=inputs['ohlc'],initial_cash=spec['initial']['cash'],initial_shares=spec['initial']['shares'],fee_bps='0',slippage_bps=cost,order_provider=provider,news_allocation_dates=allocation_dates)
    require(result['status']=='COMPLETE','LOCAL_BOOK_NOT_COMPLETE');return dict(book=result,trace=trace)


def execute(folder,output):
    folder=Path(folder);contract=verify(folder);require(datetime.now(timezone.utc)<moment(contract['no_start_after_utc']),'START_DEADLINE_PASSED');review=read(folder/'semantic_review.json')
    require(all(review.get(k) is True for k in ('semantic_pass','action_evidence_contiguous_pass','development_replay_permitted')) and review.get('production_authorized') is False,'INDEPENDENT_REVIEW_REQUIRED')
    required=[folder/'contract.json',folder/'A_run1/result.json',folder/'A_run1/receipt.json',folder/'B_run1/answer.json',folder/'B_run1/receipt.json',Path(__file__)]
    for path in required:require(review.get('source_hashes',{}).get(str(path.resolve().relative_to(ROOT)).replace('\\','/'))==digest(path),'REVIEW_BINDING_REQUIRED')
    a=read(folder/'A_run1/result.json');b=read(folder/'B_run1/answer.json')['B_signal'];spec=read(folder/'preflight.json')
    require(a['status'] in ('SUCCEEDED','CACHED') and len(a['rows'])==1 and a['rows'][0]['security_id']==spec['security_id'],'A_RESULT_NOT_ADMITTED')
    require(read(folder/'A_run1/receipt.json')['contract_sha256']==digest(folder/'contract.json') and read(folder/'B_run1/receipt.json')['contract_sha256']==digest(folder/'contract.json'),'MODEL_CONTRACT_CHANGED')
    inputs=read(ROOT/BASE/'execution_inputs.json');baseline=read(ROOT/BASE/'book.json');output=Path(output);output.mkdir(exist_ok=False);summary={}
    for cost in contract['costs_bps']:
        results={arm:replay(inputs,spec,arm,a['rows'][0],b,cost) for arm in ('BASELINE','A','B')}
        if cost=='5':
            original={r['date']:r for r in baseline['daily_ledger']}
            for row in results['BASELINE']['book']['daily_ledger']:
                for key in ('cash','shares','equity'):require(row[key]==original[row['date']][key],'BASELINE_DAILY_MISMATCH')
        final=Fraction(results['BASELINE']['book']['daily_ledger'][-1]['equity']);arms={}
        for arm,result in results.items():
            save(output/(cost+'bp_'+arm+'.json'),result);ledger=result['book']['daily_ledger'];peak=Fraction(spec['initial']['equity']);dd=Fraction(0)
            for row in ledger:equity=Fraction(row['equity']);peak=max(peak,equity);dd=max(dd,1-equity/peak)
            arms[arm]=dict(terminal_delta=str(Fraction(ledger[-1]['equity'])-final),local_return=str(Fraction(ledger[-1]['equity'])/Fraction(spec['initial']['equity'])-1),close_drawdown=str(dd),cash=ledger[-1]['cash'],shares=ledger[-1]['shares'],fills=[r for r in result['book']['order_log'] if r['event']=='ASSUMED_NEXT_OPEN_FILLED'])
        summary[cost]=dict(arms=arms,opening=opening_metrics(spec['initial'],inputs['ohlc'],results,spec['days'][1]))
    result=dict(status='COMPLETE_CONDITIONAL_DEVELOPMENT_REPLAY',case_id=contract['case_id'],days=spec['days'],costs=summary,limitations=['Known retrospective large-move sample, not holdout','Modern archive and hypothetical historical receipt; model-memory leakage possible','Three opens: two active, third recomputes original daily risk and releases news cash; no full-cycle or annualized claim','Baseline 5bp daily ledger exact; 0bp is a cost sensitivity with same initial account','Common overnight gap is not avoidable news profit'])
    save(output/'summary.json',result);return result


if __name__=='__main__':
    parser=argparse.ArgumentParser(description=__doc__);parser.add_argument('operation',choices=['prepare','model','replay']);parser.add_argument('--case',choices=CASES);parser.add_argument('--source');parser.add_argument('--folder',required=True);parser.add_argument('--arm',choices=['A','B']);parser.add_argument('--output');args=parser.parse_args()
    if args.operation=='prepare':result=prepare(args.case,args.source,Path(args.folder).resolve())
    elif args.operation=='model':result=call_model(Path(args.folder).resolve(),args.arm)
    else:result=execute(Path(args.folder).resolve(),Path(args.output).resolve())
    print(json.dumps(result,ensure_ascii=False))
