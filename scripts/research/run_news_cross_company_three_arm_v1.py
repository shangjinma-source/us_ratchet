"""Fixed APP/NVDA date-label development cases; no inference or network."""
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
CASES = {
    'APP_20251105': dict(security_id='security:0001751008:03831W108', days=['2025-11-05','2025-11-06','2025-11-07','2025-11-10'], held=2, target=2),
    'NVDA_20241120': dict(security_id='security:0001045810:67066G104', days=['2024-11-20','2024-11-21','2024-11-22','2024-11-25'], held=85, target=85),
}
QUALITY = 'DATE_ONLY_CONSERVATIVE_GLOBAL_BOUND_CONDITIONAL'
BASE = 'tmp/old_continuous_baseline_20261026_v9/'
BASE_PINS = {'book.json':'dbb9556fe946dd36a0fdfa6c1b204f32048d2c716784686628ac3bcae36b6a93', 'execution_inputs.json':'b777b58c23b1f36ee30463e926c170e1983b844b96b8e2a2cb27b6b4f11d2672'}
DEPENDENCIES = ['scripts/research/run_news_early_three_arm_v1.py','scripts/research/run_news_context_three_arm_v1.py','scripts/research/run_news_preopen_execution_probe_v1.py','backtest/monthly_exit_core_research_adapter.py','backtest/historical_dividend_next_open_book_research.py']
DEPENDENCIES += ['core/monthly_peak_exit.py','backtest/return_priority_ads_conversion.py','backtest/return_priority_distribution_entitlements.py','backtest/return_priority_cash_stock_entitlements.py']
CONTRACT_PINS = {'APP_20251105':'5ba5e2e76c626549746bd5753cbf456dcdd381f3693a84d6cdb4b4bc59a39cc7', 'NVDA_20241120':'76653dfa2531d7056146adf65bce6450a81903bb75cd2d0b06f58d89fabb2608'}


def validate(root, contract_path, answer_path, review_path):
    root=Path(root).resolve(); pins={}
    def raw(path):
        path=(root/Path(path)).resolve(); value=path.read_bytes()
        pins[str(path)]=sha256(value).hexdigest(); return value
    def read(path): return json.loads(raw(path))
    frozen=read(contract_path); case=frozen.get('case_id'); folder=Path(contract_path).parent
    if case not in CASES or sha256(raw(contract_path)).hexdigest()!=CONTRACT_PINS[case]: raise ValueError('FROZEN_CONTRACT_CHANGED')
    spec=CASES[case]; execution=frozen['execution']; source=read(folder/'source_contract.json')
    if frozen['quality']!=QUALITY or source['quality']!=QUALITY: raise ValueError('CONDITION_REQUIRED')
    if frozen['security_id']!=spec['security_id'] or execution['session_dates']!=spec['days']: raise ValueError('FIXED_DOMAIN_CHANGED')
    if (execution['active_execution_opens'],execution['release_at_execution_open_index'],execution['processing_seconds'],execution['fee_bps'],execution['slippage_bps'])!=(2,3,120,'0','5'): raise ValueError('EXECUTION_RULE_CHANGED')
    if source['public_available_at'] is not None or source['initial_account_close']!=spec['days'][0] or source['availability_upper_utc']!=spec['days'][1]+'T12:00:00Z': raise ValueError('CLOCK_CHANGED')
    for owner in (source,frozen):
        for path,digest in owner['source_hashes'].items():
            if sha256(raw(path)).hexdigest()!=digest: raise ValueError('SOURCE_CHANGED')
    for filename,key in [('source_contract.json','source_contract_sha256'),('public_input.json','input_sha256'),('prompt_template.txt','prompt_sha256')]:
        if sha256(raw(folder/filename)).hexdigest()!=frozen[key]: raise ValueError('FROZEN_INPUT_CHANGED')
    record=read(folder/'public_input.json'); answer=read(answer_path); receipt=read(folder/'run1/receipt.json'); review=read(review_path)
    prompt=(root/folder/'prompt_template.txt').read_text(encoding='utf-8')+json.dumps(record,ensure_ascii=False)
    if sha256(prompt.encode()).hexdigest()!=frozen['full_prompt_sha256'] or receipt['prompt_sha256']!=frozen['full_prompt_sha256']: raise ValueError('FULL_PROMPT_CHANGED')
    if receipt.get('status')!='PENDING_INDEPENDENT_SEMANTIC_REVIEW' or receipt.get('production_authorized') is not False: raise ValueError('MODEL_RECEIPT_REQUIRED')
    for key,value in [('contract_sha256',CONTRACT_PINS[case]),('input_sha256',frozen['input_sha256']),('answer_sha256',sha256(raw(answer_path)).hexdigest())]:
        if receipt.get(key)!=value: raise ValueError('MODEL_RECEIPT_BINDING')
    if sha256(raw(frozen['execution_source_path'])).hexdigest()!=frozen['runner_sha256']: raise ValueError('MODEL_SOURCE_CHANGED')
    if read(folder/'run1/raw_answer.json')!=answer: raise ValueError('RAW_ANSWER_CHANGED')
    if sha256(record['text'].encode()).hexdigest()!=source['full_text_sha256'] or record['text_sha256']!=source['full_text_sha256'] or answer['source_id']!=source['event_id'] or record['id']!=source['event_id']: raise ValueError('TEXT_IDENTITY_CHANGED')
    for section in ('shared_facts','A_direct','B_signal'):
        items=answer[section] if section=='shared_facts' else answer[section]['evidence']
        if not items: raise ValueError('EVIDENCE_REQUIRED')
        for item in items:
            quote=item.get('exact_quote') if section=='shared_facts' else item.get('quote')
            if item.get('source_id')!=record['id'] or not quote_in_source(quote,record['text']): raise ValueError('QUOTE_NOT_IN_SOURCE')
    required={'semantic_pass':True,'action_evidence_contiguous_pass':True,'development_replay_permitted':True,'production_authorized':False,'automatic_adoption_authorized':False,'condition_explicit':True}
    if any(review.get(k) is not v for k,v in required.items()) or review.get('condition_quality')!=QUALITY: raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
    reviewed={}
    for path,digest in review['source_hashes'].items():
        if sha256(raw(path)).hexdigest()!=digest: raise ValueError('REVIEWED_SOURCE_CHANGED')
        reviewed[str((root/path).resolve())]=digest
    required_paths=[contract_path,answer_path,folder/'public_input.json',folder/'source_contract.json',folder/'run1/receipt.json',frozen['execution_source_path'],Path(__file__).resolve(),BASE+'book.json',BASE+'execution_inputs.json',*DEPENDENCIES]
    for path in required_paths:
        if reviewed.get(str((root/path).resolve()))!=sha256(raw(path)).hexdigest(): raise ValueError(('REVIEW_BINDING_REQUIRED',str(path)))
    for filename,digest in BASE_PINS.items():
        if sha256(raw(BASE+filename)).hexdigest()!=digest: raise ValueError('BASELINE_CHANGED')
    for arm in ('A','B'): transform({spec['security_id']:spec['target']},spec['held'],spec['target'],answer,arm,security_id=spec['security_id'])
    return frozen,source,answer,pins


def transform(target, held_initial, target_initial, answer, arm, *, security_id):
    # Reuse the frozen arithmetic via a local one-key projection, not module globals.
    mapped=mrna_transform({MRNA_SID:target.get(security_id,0)},held_initial,target_initial,answer,arm)
    result=deepcopy(target);result[security_id]=mapped[MRNA_SID];return result


def replay(inputs, book, *, case_id, published, target_transform=None):
    if case_id not in CASES: raise ValueError('FIXED_CASE_REQUIRED')
    spec=CASES[case_id]; initial_date=spec['days'][0]
    assembled=inputs['assembled']; all_days=assembled['session_dates']
    index=all_days.index(initial_date); days=all_days[index:index+4]
    if days != spec['days'] or index == 0: raise ValueError('FIXED_SESSIONS_CHANGED')
    if len(book['provider_audit']) != len(all_days)-1: raise ValueError('AUDIT_CALENDAR_MISMATCH')
    audit=dict(zip(all_days[:-1],book['provider_audit']))
    initial=next(r for r in book['daily_ledger'] if r['date']==days[0])
    if any(Fraction(str(initial.get(k,0))) for k in ('receivable','dividend_receivable','nontradable_entitlement_value','distribution_entitlement_value','reserved_cash_end')) or initial.get('distribution_rights') or initial.get('merger_entitlements'):
        raise ValueError('INITIAL_RIGHTS_UNSUPPORTED')
    for key in ('actions','provider_actions','cash_stock_merger_events','distribution_events'):
        if any(days[0]<e.get('date',e.get('effective_date',''))<=days[-1] for e in assembled.get(key) or []): raise ValueError('LOCAL_ACTION_UNSUPPORTED')
    if any(days[0]<=w['decision_date']<days[-1] for w in assembled['monthly_inputs']): raise ValueError('MONTH_RESET_FORBIDDEN')
    if any(days[0]<e['ex_date']<=days[-1] for e in inputs.get('dividend_events',[])): raise ValueError('LOCAL_DIVIDEND_UNSUPPORTED')
    if any(days[0]<e.get('payment_date',e.get('pay_date',''))<=days[-1] for e in inputs.get('dividend_events',[])): raise ValueError('LOCAL_DIVIDEND_PAYMENT_UNSUPPORTED')
    risk=MonthlyExitCoreResearchAdapter(); risk.state=deepcopy(audit[all_days[index-1]]['risk_overlay']['state']); risk.last_day=risk.state['session_date']
    ceiling=deepcopy(audit[days[0]]['monthly_ceiling']); epoch=audit[days[0]]['target_decision_date']; trace=[]; sid=spec['security_id']
    def provider(*,decision_date,active_date,state):
        target,diag=risk.apply(day=decision_date,month=epoch,target=deepcopy(ceiling),closes={s:assembled['close_prices'][s][decision_date] for s in ceiling})
        original=deepcopy(target)
        # Risk uses only the preceding close. News can arrive AFTER that close,
        # provided processing completes BEFORE this actual execution opening.
        opening=datetime.fromisoformat(active_date+'T09:30:00').replace(tzinfo=ZoneInfo('America/New_York')).isoformat()
        enabled=eligible(published,opening) and active_date in days[1:3]
        if enabled and target_transform is not None:
            target=target_transform(deepcopy(original),deepcopy(state))
            if set(target)!=set(original) or any(type(v) is not int or v<0 or v>original[k] for k,v in target.items()): raise ValueError('OVERLAY_EXCEEDS_RISK_TARGET')
        orders=[]
        for s in sorted(set(state['shares'])|set(target)):
            delta=target.get(s,0)-state['shares'].get(s,0)
            if delta: orders.append(dict(id='preopen:'+active_date+':'+s,security_id=s,side='BUY' if delta>0 else 'SELL',quantity=abs(delta),decision_date=decision_date,active_date=active_date,decision_mark=assembled['close_prices'][s][decision_date]))
        trace.append(dict(security_id=sid,risk_asof_close=decision_date,assumed_availability_upper_utc=published,processing_seconds=120,execution_open=opening,news_active=enabled,original_target=original,target=deepcopy(target),risk=diag,orders=deepcopy(orders)))
        return dict(status='READY',orders=orders)
    result=run_next_open_book(session_dates=days,ohlc=inputs['ohlc'],initial_cash=initial['cash'],initial_shares=initial['shares'],fee_bps='0',slippage_bps='5',order_provider=provider)
    if result['status']!='COMPLETE': raise ValueError(result.get('reason'))
    return dict(book=result,trace=trace)


def run(root,contract_path,answer_path,review_path,output):
    if datetime.now(timezone.utc)>=datetime.fromisoformat('2026-10-28T10:45:00+00:00'):raise ValueError('NEW_EXECUTION_DEADLINE_PASSED')
    root=Path(root);frozen,c,answer,pins=validate(root,contract_path,answer_path,review_path)
    case=frozen['case_id'];spec=CASES[case];sid=spec['security_id']
    # Claim output before computation: failed attempts remain inspectable and cannot be overwritten.
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    (output/'attempt.json').write_text(json.dumps(dict(status='STARTED',case_id=case,source_hashes=pins)),encoding='utf-8')
    base=root/BASE
    def load(name):
        raw=(base/name).read_bytes();pins[str(base/name)]=sha256(raw).hexdigest();return json.loads(raw)
    inputs=load('execution_inputs.json');book=load('book.json')
    initial=next(r for r in book['daily_ledger'] if r['date']==spec['days'][0])
    audit=dict(zip(inputs['assembled']['session_dates'][:-1],book['provider_audit']))[spec['days'][0]]
    h=initial['shares'].get(sid,0);q=audit['target_shares'].get(sid,0)
    if (h,q)!=(spec['held'],spec['target']):raise ValueError('FIXED_INITIAL_ANCHOR_CHANGED')
    results={'BASELINE':replay(inputs,book,case_id=case,published=c['availability_upper_utc'])}
    baseline=results['BASELINE']['book']['daily_ledger']
    for row in baseline:
        expected=next(r for r in book['daily_ledger'] if r['date']==row['date'])
        for k in ('cash','shares','equity','dividend_receivable'):
            if row.get(k,'0')!=expected.get(k,'0'):raise ValueError('BASELINE_NOT_EXACT')
    for arm in ('A','B'):
        results[arm]=replay(inputs,book,case_id=case,published=c['availability_upper_utc'],target_transform=lambda target,state:transform(target,h,q,answer,arm,security_id=sid))
    opening=opening_metrics(initial,inputs['ohlc'],results,spec['days'][1]);summaries={}
    for arm,result in results.items():
        ledger=result['book']['daily_ledger'];start=Fraction(initial['equity']);peak=start;dd=Fraction(0)
        for row in ledger:
            value=Fraction(row['equity']);peak=max(peak,value);dd=max(dd,1-value/peak)
        fills=[x for x in result['book']['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED']
        turnover=sum(Fraction(f['price'])*f['quantity'] for f in fills)
        costs=sum(abs(Fraction(f['price'])-Fraction(inputs['ohlc'][f['security_id']][f['date']]['open']))*f['quantity']+Fraction(f['fee']) for f in fills)
        summaries[arm]=dict(local_close_return=str(Fraction(ledger[-1]['equity'])/start-1),local_close_drawdown=str(dd),terminal_delta_vs_baseline=str(Fraction(ledger[-1]['equity'])-Fraction(baseline[-1]['equity'])),fills=fills,turnover_usd=str(turnover),cost_usd=str(costs),final_cash=ledger[-1]['cash'],final_shares=ledger[-1]['shares'])
    for file in [__file__,*DEPENDENCIES]:
        pins[str(file)]=sha256((root/Path(file)).read_bytes()).hexdigest()
    summary=dict(status='FIXED_CROSS_COMPANY_THREE_ARM_COMPLETE',case_id=case,security_id=sid,quality=QUALITY,public_available_at=None,baseline_exact=True,initial_held=h,initial_risk_target=q,execution_session_dates=spec['days'][1:],opening=opening,arms=summaries,source_hashes=pins,limitations=['Official current release-date label with conservative global civil time bound; not certified historical first publication or immutable version.','Known-case development, modern model memory contamination cannot be excluded.','Two active opens; third expiry may repurchase only within original risk and cash.','No new monthly selection; no positive overweight.','Shared pre-execution account gap is not news profit.','No annualization or full-strategy CAGR/drawdown conclusion.'])
    for arm,result in results.items():(output/(arm+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8')
    (output/'attempt.json').write_text(json.dumps(dict(status='COMPLETE',case_id=case,source_hashes=pins)),encoding='utf-8')
    return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--contract',required=True);p.add_argument('--answer',required=True);p.add_argument('--review',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(run(a.root,a.contract,a.answer,a.review,a.output)))
