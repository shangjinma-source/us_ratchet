"""NVDA conditional associated-release sensitivity; never certified event timing."""
import argparse,json
from copy import deepcopy
from datetime import datetime, timezone
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
from zoneinfo import ZoneInfo
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.research.run_news_early_three_arm_v1 import transform as mrna_transform, SID as MRNA_SID
from scripts.research.run_news_context_three_arm_v1 import quote_in_source
from scripts.research.run_news_preopen_execution_probe_v1 import eligible,opening_metrics
from backtest.historical_dividend_next_open_book_research import run_next_open_book
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
SID='research:security:nvda'
QUALITY='ASSUMED_ASSOCIATED_RELEASE_AVAILABILITY_SENSITIVITY_ONLY'
BASE='tmp/recent_continuous_baseline_20261026_v7/'


def transform(target,held_initial,target_initial,answer,arm):
    # Apply the unchanged one-security mapping without mutating its MRNA module.
    mapped=mrna_transform({MRNA_SID:target.get(SID,0)},held_initial,target_initial,answer,arm)
    result=deepcopy(target);result[SID]=mapped[MRNA_SID];return result


def validate(root,contract_path,answer_path,review_path):
    root=Path(root);pins={}
    def raw(path):
        path=Path(path);path=path if path.is_absolute() else root/path
        data=path.read_bytes();pins[str(path)]=sha256(data).hexdigest();return data
    def read(path):return json.loads(raw(path))
    frozen=read(contract_path);folder=Path(contract_path).parent;answer=read(answer_path);review=read(review_path)
    if sha256(raw(contract_path)).hexdigest()!='901ddd09fb1200db09039109f641352db9cf81df4ec900bc68b5e1d3830fb628':raise ValueError('FIXED_CONTRACT_CHANGED')
    required={'semantic_pass':True,'action_evidence_contiguous_pass':True,'development_replay_permitted':True,'production_authorized':False,'automatic_adoption_authorized':False,'condition_explicit':True}
    if any(review.get(k) is not v for k,v in required.items()) or review.get('condition_quality')!=QUALITY:raise ValueError('CONDITIONAL_REVIEW_REQUIRED')
    reviewed={}
    for path,digest in review['source_hashes'].items():
        if sha256(raw(path)).hexdigest()!=digest:raise ValueError('REVIEWED_SOURCE_CHANGED')
        reviewed[str((root/path).resolve())]=digest
    for path in (contract_path,answer_path,folder/'public_input.json',Path(__file__).resolve(),BASE+'book.json',BASE+'execution_inputs.json'):
        if reviewed.get(str((root/path).resolve()))!=sha256(raw(path)).hexdigest():raise ValueError(('EXECUTION_REVIEW_BINDING_REQUIRED',str(path)))
    if frozen.get('schema')!='FROZEN_CONDITIONAL_NVDA_TWO_MECHANISM_V1' or frozen.get('quality')!=QUALITY:raise ValueError('CONDITION_REQUIRED')
    c=read(folder/'source_contract.json');record=read(folder/'public_input.json');receipt=read(folder/'run1/receipt.json')
    if sha256(raw(folder/'source_contract.json')).hexdigest()!=frozen['source_contract_sha256']:raise ValueError('SOURCE_CONTRACT_CHANGED')
    if c['quality']!=QUALITY or c['public_available_at'] is not None or c['assumed_availability_upper_utc']!='2023-11-22T12:00:00Z' or c['initial_account_close']!='2023-11-21':raise ValueError('ASSUMPTION_CHANGED')
    for path,digest in c['source_hashes'].items():
        if sha256(raw(path)).hexdigest()!=digest:raise ValueError('SOURCE_CHANGED')
    if sha256(raw(folder/'public_input.json')).hexdigest()!=frozen['input_sha256'] or sha256(raw(folder/'prompt_template.txt')).hexdigest()!=frozen['prompt_sha256']:raise ValueError('INPUT_CHANGED')
    prompt=(root/folder/'prompt_template.txt').read_text(encoding='utf-8')+json.dumps(record,ensure_ascii=False)
    if sha256(prompt.encode()).hexdigest()!=frozen['full_prompt_sha256'] or receipt['prompt_sha256']!=frozen['full_prompt_sha256']:raise ValueError('FULL_PROMPT_CHANGED')
    if receipt.get('status')!='PENDING_INDEPENDENT_SEMANTIC_REVIEW' or receipt.get('production_authorized') is not False:raise ValueError('MODEL_RECEIPT_NOT_ADMITTED')
    if receipt['contract_sha256']!=sha256(raw(contract_path)).hexdigest() or receipt['answer_sha256']!=sha256(raw(answer_path)).hexdigest() or receipt['input_sha256']!=frozen['input_sha256']:raise ValueError('RECEIPT_CHANGED')
    if sha256(raw(frozen['execution_source_path'])).hexdigest()!=frozen['runner_sha256']:raise ValueError('MODEL_SOURCE_CHANGED')
    if read(folder/'run1/raw_answer.json')!=answer:raise ValueError('RAW_ANSWER_CHANGED')
    sources={s['id']:s for s in record['sources']}
    if len(sources)!=2 or set(sources)!=set(c['source_ids']):raise ValueError('SOURCE_DOMAIN_CHANGED')
    for item in c['sources']:
        s=sources[item['id']]
        if sha256(s['text'].encode()).hexdigest()!=item['text_sha256'] or s['text_sha256']!=item['text_sha256']:raise ValueError('TEXT_CHANGED')
    if answer['source_id']!=c['event_id']:raise ValueError('ANSWER_SOURCE_CHANGED')
    for section in ('shared_facts','A_direct','B_signal'):
        items=answer[section] if section=='shared_facts' else answer[section]['evidence']
        if not items:raise ValueError('EMPTY_EVIDENCE')
        for item in items:
            sid=item.get('source_id');quote=item.get('exact_quote') if section=='shared_facts' else item.get('quote')
            if sid not in sources or not quote_in_source(quote,sources[sid]['text']):raise ValueError('QUOTE_NOT_IN_SOURCE')
    for arm in ('A','B'):transform({SID:7},7,7,answer,arm)
    c['replay_admission']={'condition_quality':QUALITY,'actual_first_publication_verified':False,'independent_semantic_review':True}
    return c,answer,pins

def replay(inputs, book, action, published='2023-11-22T12:00:00Z', initial_date='2023-11-21', target_transform=None):
    if action not in ('NO_CHANGE','BLOCK_NEW_BUYS','EXIT','HALF_TARGET'):
        raise ValueError('UNKNOWN_ACTION')
    assembled=inputs['assembled']; all_days=assembled['session_dates']
    expected={'2023-11-21':['2023-11-21','2023-11-22','2023-11-24','2023-11-27']}
    if initial_date not in expected: raise ValueError('FIXED_CASE_REQUIRED')
    index=all_days.index(initial_date); days=all_days[index:index+4]
    if days!=expected[initial_date]: raise ValueError('FIXED_SESSIONS_CHANGED')
    audit=dict(zip(all_days[:-1],book['provider_audit']))
    initial=next(r for r in book['daily_ledger'] if r['date']==days[0])
    if any(Fraction(str(initial.get(k,0))) for k in ('receivable','dividend_receivable','nontradable_entitlement_value')) or initial.get('distribution_rights') or initial.get('merger_entitlements'):
        raise ValueError('INITIAL_RIGHTS_UNSUPPORTED')
    for key in ('actions','provider_actions','cash_stock_merger_events','distribution_events'):
        if any(days[0]<e.get('date',e.get('effective_date',''))<=days[-1] for e in assembled.get(key) or []): raise ValueError('LOCAL_ACTION_UNSUPPORTED')
    if any(days[0]<=w['decision_date']<days[-1] for w in assembled['monthly_inputs']): raise ValueError('MONTH_RESET_FORBIDDEN')
    if any(days[0]<e['ex_date']<=days[-1] for e in inputs.get('dividend_events',[])): raise ValueError('LOCAL_DIVIDEND_UNSUPPORTED')
    risk=MonthlyExitCoreResearchAdapter(); risk.state=deepcopy(audit[all_days[index-1]]['risk_overlay']['state']); risk.last_day=risk.state['session_date']
    ceiling=deepcopy(audit[days[0]]['monthly_ceiling']); epoch=audit[days[0]]['target_decision_date']; trace=[]; sid=SID
    def provider(*,decision_date,active_date,state):
        target,diag=risk.apply(day=decision_date,month=epoch,target=deepcopy(ceiling),closes={s:assembled['close_prices'][s][decision_date] for s in ceiling})
        original=deepcopy(target)
        # Risk uses only the preceding close. News can arrive AFTER that close,
        # provided processing completes BEFORE this actual execution opening.
        opening=datetime.fromisoformat(active_date+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York')).isoformat()
        enabled=eligible(published,opening) and active_date in days[1:3]
        if enabled:
            if action=='EXIT': target[sid]=0
            elif action=='BLOCK_NEW_BUYS': target[sid]=min(target.get(sid,0),state['shares'].get(sid,0))
            elif action=='HALF_TARGET': target[sid]=target.get(sid,0)//2
        if enabled and target_transform is not None:
            target=target_transform(deepcopy(original),deepcopy(state))
            if any(type(v) is not int or v<0 or v>original.get(k,0) for k,v in target.items()): raise ValueError('OVERLAY_EXCEEDS_RISK_TARGET')
        orders=[]
        for s in sorted(set(state['shares'])|set(target)):
            delta=target.get(s,0)-state['shares'].get(s,0)
            if delta: orders.append(dict(id='preopen:'+active_date+':'+s,security_id=s,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),decision_date=decision_date,active_date=active_date,decision_mark=assembled['close_prices'][s][decision_date]))
        trace.append(dict(risk_asof_close=decision_date,assumed_availability_upper_utc=published,processing_seconds=120,execution_open=opening,news_active=enabled,original_target=original,target=deepcopy(target),risk=diag,orders=deepcopy(orders)))
        return dict(status='READY',orders=orders)
    result=run_next_open_book(session_dates=days,ohlc=inputs['ohlc'],initial_cash=initial['cash'],initial_shares=initial['shares'],fee_bps='0',slippage_bps='5',order_provider=provider)
    if result['status']!='COMPLETE': raise ValueError(result.get('reason'))
    return dict(book=result,trace=trace)


def run(root,contract_path,answer_path,review_path,output):
    if datetime.now(timezone.utc)>=datetime.fromisoformat('2026-10-27T19:50:00+00:00'):raise ValueError('NEW_EXECUTION_DEADLINE_PASSED')
    root=Path(root);c,answer,pins=validate(root,contract_path,answer_path,review_path)
    base=root/'tmp/recent_continuous_baseline_20261026_v7'
    def load(name):
        raw=(base/name).read_bytes();pins[str(base/name)]=sha256(raw).hexdigest();return json.loads(raw)
    inputs=load('execution_inputs.json');book=load('book.json')
    initial=next(r for r in book['daily_ledger'] if r['date']=='2023-11-21')
    audit=dict(zip(inputs['assembled']['session_dates'][:-1],book['provider_audit']))['2023-11-21']
    h=initial['shares'].get(SID,0);q=audit['target_shares'].get(SID,0)
    if (h,q)!=(7,7):raise ValueError('FIXED_INITIAL_ANCHOR_CHANGED')
    results={}
    for arm in ('BASELINE','A','B'):
        results[arm]=replay(inputs,book,'NO_CHANGE',published=c['assumed_availability_upper_utc'],initial_date=c['initial_account_close'],target_transform=lambda target,state:transform(target,h,q,answer,arm))
    baseline=results['BASELINE']['book']['daily_ledger']
    for row in baseline:
        expected=next(r for r in book['daily_ledger'] if r['date']==row['date'])
        for k in ('cash','shares','equity','dividend_receivable'):
            if row.get(k,'0')!=expected.get(k,'0'):raise ValueError('BASELINE_NOT_EXACT')
    opening=opening_metrics(initial,inputs['ohlc'],results,'2023-11-22');summaries={}
    for arm,result in results.items():
        ledger=result['book']['daily_ledger'];start=Fraction(initial['equity']);peak=start;dd=Fraction(0)
        for row in ledger:
            value=Fraction(row['equity']);peak=max(peak,value);dd=max(dd,1-value/peak)
        fills=[x for x in result['book']['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED']
        turnover=sum(Fraction(f['price'])*f['quantity'] for f in fills)
        costs=sum(abs(Fraction(f['price'])-Fraction(inputs['ohlc'][f['security_id']][f['date']]['open']))*f['quantity']+Fraction(f['fee']) for f in fills)
        summaries[arm]=dict(local_close_return=str(Fraction(ledger[-1]['equity'])/start-1),local_close_drawdown=str(dd),terminal_delta_vs_baseline=str(Fraction(ledger[-1]['equity'])-Fraction(baseline[-1]['equity'])),fills=fills,turnover_usd=str(turnover),cost_usd=str(costs),final_cash=ledger[-1]['cash'],final_shares=ledger[-1]['shares'])
    for file in (__file__,'scripts/research/run_news_preopen_execution_probe_v1.py','scripts/research/run_news_early_three_arm_v1.py','backtest/monthly_exit_core_research_adapter.py','backtest/historical_dividend_next_open_book_research.py'):
        pins[str(file)]=sha256(Path(file).read_bytes()).hexdigest()
    summary=dict(status='FIXED_NVDA_CONDITIONAL_THREE_ARM_COMPLETE',admission=c['replay_admission'],baseline_exact=True,initial_held=h,initial_risk_target=q,opening=opening,arms=summaries,source_hashes=pins,limitations=['ASSUMED_ASSOCIATED_RELEASE_AVAILABILITY_SENSITIVITY_ONLY: CFO actual publication date/time is unverified.','Nov23 omitted by original session calendar; Nov24 is an actual session, not a guessed calendar day.','Known-outcome development sample, not holdout.','A and B same public source, but different fixed action mappings.','Positive B is neutral factor one; positive overweight not tested.','Two opens active; third expiry respects original risk; no new monthly selection.','Close-to-open gap is shared and not avoidable news profit.','No annualization or claim of preserved CAGR or improved full-strategy drawdown.'])
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    for arm,result in results.items():(output/(arm+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--contract',required=True);p.add_argument('--answer',required=True);p.add_argument('--review',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(run(a.root,a.contract,a.answer,a.review,a.output)))
