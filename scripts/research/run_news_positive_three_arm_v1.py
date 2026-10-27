"""Fixed July positive-event control. No inference, no positive leverage or tuning."""
import argparse,json
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.research.run_news_early_three_arm_v1 import transform,SID
from scripts.research.run_news_context_three_arm_v1 import quote_in_source
from scripts.research.run_news_preopen_execution_probe_v1 import replay,opening_metrics


def validate(root,contract_path,answer_path,review_path):
    root=Path(root);pins={}
    def raw(path):
        path=Path(path);path=path if path.is_absolute() else root/path
        data=path.read_bytes();pins[str(path)]=sha256(data).hexdigest();return data
    def read(path):return json.loads(raw(path))
    frozen=read(contract_path);fh=sha256(raw(contract_path)).hexdigest()
    if fh!='6635f4af76441ba40a92cdef219aaa471b7909166ecbea93f9c680de99b8bdd0':raise ValueError('FIXED_CONTRACT_CHANGED')
    folder=Path(contract_path).parent;source=read(folder/'source_contract.json');answer=read(answer_path);review=read(review_path)
    if review.get('status')!='DEVELOPMENT_REPLAY_ONLY_SEMANTIC_PASS' or review.get('semantic_pass') is not True or review.get('development_replay_permitted') is not True or review.get('production_authorized') is not False:raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
    approved={}
    for path,digest in review['source_hashes'].items():
        if sha256(raw(path)).hexdigest()!=digest:raise ValueError('REVIEW_SOURCE_CHANGED')
        approved[str((root/path).resolve())]=digest
    for path in (contract_path,answer_path):
        if approved.get(str((root/path).resolve()))!=sha256(raw(path)).hexdigest():raise ValueError('REVIEW_BINDING_MISSING')
    if sha256(raw(folder/'source_contract.json')).hexdigest()!=frozen['source_contract_sha256']:raise ValueError('SOURCE_CONTRACT_CHANGED')
    if source['event_id']!='MRNA_20210715_SP500_RELEASE' or source['initial_account_close']!='2021-07-15' or source['published_at']!='2021-07-15T19:01:00-04:00':raise ValueError('WRONG_EVENT')
    for path,digest in source['source_hashes'].items():
        if sha256(raw(path)).hexdigest()!=digest:raise ValueError('ORIGINAL_SOURCE_CHANGED')
    record=read(folder/'public_input.json');receipt=read(folder/'run1/receipt.json')
    if sha256(raw(folder/'public_input.json')).hexdigest()!=frozen['input_sha256'] or sha256(raw(folder/'prompt_template.txt')).hexdigest()!=frozen['prompt_sha256']:raise ValueError('INPUT_PROMPT_CHANGED')
    if receipt['contract_sha256']!=fh or receipt['answer_sha256']!=sha256(raw(answer_path)).hexdigest() or receipt['input_sha256']!=frozen['input_sha256']:raise ValueError('RECEIPT_CHANGED')
    if receipt.get('status')!='PENDING_INDEPENDENT_SEMANTIC_REVIEW' or receipt.get('production_authorized') is not False:raise ValueError('RECEIPT_STATUS')
    prompt=(root/folder/'prompt_template.txt').read_text(encoding='utf-8')+json.dumps(record,ensure_ascii=False)
    if sha256(prompt.encode()).hexdigest()!=receipt['prompt_sha256']:raise ValueError('COMPLETE_PROMPT_CHANGED')
    if sha256(raw(folder/'execution_source.py')).hexdigest()!=frozen['runner_sha256']:raise ValueError('EXECUTION_SOURCE_CHANGED')
    if read(folder/'run1/raw_answer.json')!=answer:raise ValueError('ANSWER_CHANGED')
    raw(source['full_text_path']);text=(root/source['full_text_path']).read_text(encoding='utf-8')
    if text!=record['text'] or sha256(text.encode()).hexdigest()!=source['full_text_sha256'] or record['text_sha256']!=source['full_text_sha256']:raise ValueError('BODY_CHANGED')
    if answer['source_id']!=source['event_id']:raise ValueError('ANSWER_SOURCE_CHANGED')
    for section in ('shared_facts','A_direct','B_signal'):
        items=answer[section] if section=='shared_facts' else answer[section]['evidence']
        if not items:raise ValueError('EMPTY_EVIDENCE')
        for item in items:
            quote=item.get('exact_quote') if section=='shared_facts' else item.get('quote')
            if item.get('source_id')!=source['event_id'] or not quote_in_source(quote,text):raise ValueError('QUOTE_NOT_IN_SOURCE')
    for arm in ('A','B'):transform({SID:41},41,41,answer,arm)
    source['replay_admission']={'path':'INDEPENDENT_REVIEWED_POSITIVE_CONTROL','positive_weighting':False,'known_outcome_development_case':True}
    return source,answer,pins

def run(root,contract_path,answer_path,review_path,output):
    root=Path(root);c,answer,pins=validate(root,contract_path,answer_path,review_path)
    base=root/'tmp/recent_continuous_baseline_20261026_v7'
    def load(name):
        raw=(base/name).read_bytes();pins[str(base/name)]=sha256(raw).hexdigest();return json.loads(raw)
    inputs=load('execution_inputs.json');book=load('book.json')
    initial=next(r for r in book['daily_ledger'] if r['date']=='2021-07-15')
    audit=dict(zip(inputs['assembled']['session_dates'][:-1],book['provider_audit']))['2021-07-15']
    h=initial['shares'].get(SID,0);q=audit['target_shares'].get(SID,0)
    results={}
    for arm in ('BASELINE','A','B'):
        results[arm]=replay(inputs,book,'NO_CHANGE',published=c['published_at'],initial_date=c['initial_account_close'],target_transform=lambda target,state:transform(target,h,q,answer,arm))
    baseline=results['BASELINE']['book']['daily_ledger']
    for row in baseline:
        expected=next(r for r in book['daily_ledger'] if r['date']==row['date'])
        for k in ('cash','shares','equity','dividend_receivable'):
            if row.get(k,'0')!=expected.get(k,'0'):raise ValueError('BASELINE_NOT_EXACT')
    opening=opening_metrics(initial,inputs['ohlc'],results,'2021-07-16');summaries={}
    for arm,result in results.items():
        ledger=result['book']['daily_ledger'];start=Fraction(initial['equity']);peak=start;dd=Fraction(0)
        for row in ledger:
            value=Fraction(row['equity']);peak=max(peak,value);dd=max(dd,1-value/peak)
        fills=[x for x in result['book']['order_log'] if x['event']=='ASSUMED_NEXT_OPEN_FILLED']
        turnover=sum(Fraction(f['price'])*f['quantity'] for f in fills)
        costs=sum(abs(Fraction(f['price'])-Fraction(inputs['ohlc'][f['security_id']][f['date']]['open']))*f['quantity']+Fraction(f['fee']) for f in fills)
        summaries[arm]=dict(local_close_return=str(Fraction(ledger[-1]['equity'])/start-1),local_close_drawdown=str(dd),terminal_delta_vs_baseline=str(Fraction(ledger[-1]['equity'])-Fraction(baseline[-1]['equity'])),fills=fills,turnover_usd=str(turnover),cost_usd=str(costs),final_cash=ledger[-1]['cash'],final_shares=ledger[-1]['shares'])
    for file in (__file__,'scripts/research/run_news_preopen_execution_probe_v1.py','scripts/research/run_news_early_three_arm_v1.py','scripts/research/run_news_context_three_arm_v1.py','backtest/monthly_exit_core_research_adapter.py','backtest/historical_dividend_next_open_book_research.py'):
        pins[str(file)]=sha256(Path(file).read_bytes()).hexdigest()
    summary=dict(status='FIXED_POSITIVE_THREE_ARM_COMPLETE',admission=c['replay_admission'],baseline_exact=True,initial_held=h,initial_risk_target=q,opening=opening,arms=summaries,source_hashes=pins,limitations=['Window ends July20; July21 index inclusion effective session is NOT evaluated.','Known-outcome development sample, not holdout.','A and B same public source, but different fixed action mappings.','Positive B is neutral factor one; positive overweight not tested.','Two opens active; third expiry respects original risk; no new monthly selection.','Close-to-open gap is shared and not avoidable news profit.','No annualization or claim of preserved CAGR or improved full-strategy drawdown.'])
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    for arm,result in results.items():(output/(arm+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--contract',required=True);p.add_argument('--answer',required=True);p.add_argument('--review',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(run(a.root,a.contract,a.answer,a.review,a.output)))
