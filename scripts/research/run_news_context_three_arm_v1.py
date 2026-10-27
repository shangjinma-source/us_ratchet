"""One fixed two-release context ablation; no model calls and no parameter search."""
import argparse
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json,re
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.research.run_news_early_three_arm_v1 import transform,SID
from scripts.research.run_news_preopen_execution_probe_v1 import replay,opening_metrics


def quote_in_source(quote,text):
    if not isinstance(quote,str) or not quote.strip():return False
    return re.sub(r'\s+',' ',quote).strip() in re.sub(r'\s+',' ',text).strip()


def validate(root,contract_path,answer_path,review_path):
    root=Path(root);pins={}
    def raw(path):
        path=Path(path);path=path if path.is_absolute() else root/path
        data=path.read_bytes();pins[str(path)]=sha256(data).hexdigest();return data
    def read(path):return json.loads(raw(path))
    frozen=read(contract_path);fh=sha256(raw(contract_path)).hexdigest()
    if fh!='37a4cdbfeb304bc8d99f21400aa7222d78983ae2048d4340a7f6efe55fb01a70':raise ValueError('FROZEN_CONTEXT_CHANGED')
    answer=read(answer_path);review=read(review_path)
    required={'mechanical_pass_as_defined_by_validator':True,'action_evidence_contiguous_pass':True,'semantic_pass':True,'development_replay_permitted':True,'production_authorized':False,'automatic_adoption_authorized':False}
    if review.get('status')!='DEVELOPMENT_REPLAY_ONLY_SEMANTIC_PASS' or any(review.get(k) is not v for k,v in required.items()):raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
    reviewed={}
    for path,digest in review['source_hashes'].items():
        if sha256(raw(path)).hexdigest()!=digest:raise ValueError('REVIEWED_FILE_CHANGED')
        reviewed[str((root/path).resolve())]=digest
    for path in (contract_path,answer_path):
        if reviewed.get(str((root/path).resolve()))!=sha256(raw(path)).hexdigest():raise ValueError('REVIEW_BINDING_MISSING')
    folder=Path(contract_path).parent
    combined=read(folder/'combined_public_input.json');prompt_raw=raw(folder/'combined_prompt.txt')
    if sha256(raw(folder/'combined_public_input.json')).hexdigest()!=frozen['input_sha256'] or sha256(prompt_raw).hexdigest()!=frozen['prompt_sha256']:raise ValueError('FROZEN_PROMPT_INPUT_CHANGED')
    receipt=read(folder/'run1/receipt.json')
    if receipt.get('status')!='PENDING_INDEPENDENT_SEMANTIC_REVIEW' or receipt.get('production_authorized') is not False:raise ValueError('MODEL_RECEIPT_STATUS')
    if read(folder/'run1/raw_answer.json')!=answer:raise ValueError('RAW_ANSWER_CHANGED')
    if receipt['contract_sha256']!=fh or receipt['answer_sha256']!=sha256(raw(answer_path)).hexdigest() or receipt['input_sha256']!=frozen['input_sha256']:raise ValueError('MODEL_RECEIPT_BINDING')
    prompt=(root/folder/'combined_prompt.txt').read_text(encoding='utf-8')+json.dumps(combined,ensure_ascii=False)
    if sha256(prompt.encode()).hexdigest()!=receipt['prompt_sha256']:raise ValueError('COMPLETE_PROMPT_CHANGED')
    if sha256(raw(folder/'run1/execution_source.py')).hexdigest()!=frozen['runner_sha256']:raise ValueError('MODEL_EXECUTION_SOURCE_CHANGED')
    prior=read(folder/'source_contract.json');early_path='tmp/news_early_mrna_20211104_input_20261028/source_contract.json';early=read(early_path)
    if sha256(raw(folder/'source_contract.json')).hexdigest()!=frozen['prior_source_contract_sha256'] or sha256(raw(early_path)).hexdigest()!=frozen['source_contract_sha256']:raise ValueError('SOURCE_CONTRACT_CHANGED')
    for contract in (prior,early):
        for path,digest in contract['source_hashes'].items():
            if sha256(raw(path)).hexdigest()!=digest:raise ValueError('ORIGINAL_SOURCE_CHANGED')
    sources={s['id']:s for s in combined['sources']}
    if len(sources)!=2 or set(sources)!={prior['event_id'],early['event_id']}:raise ValueError('SOURCE_DOMAIN_CHANGED')
    for source,contract,field in ((sources[prior['event_id']],prior,'text_path'),(sources[early['event_id']],early,'full_text_path')):
        text=(root/contract[field]).read_text(encoding='utf-8');raw(contract[field])
        if source['text']!=text or sha256(text.encode()).hexdigest()!=source['text_sha256'] or receipt['source_text_hashes'][source['id']]!=source['text_sha256']:raise ValueError('SOURCE_TEXT_CHANGED')
    if answer['source_id']!=early['event_id']:raise ValueError('ANSWER_EVENT_CHANGED')
    for section in ('shared_facts','A_direct','B_signal'):
        items=answer[section] if section=='shared_facts' else answer[section]['evidence']
        if not items:raise ValueError('EMPTY_EVIDENCE')
        for item in items:
            sid=item.get('source_id');quote=item.get('exact_quote') if section=='shared_facts' else item.get('quote')
            if sid not in sources or not quote_in_source(quote,sources[sid]['text']):raise ValueError('NONCONTIGUOUS_OR_WRONG_SOURCE_QUOTE')
    for arm in ('A','B'):transform({SID:33},33,33,answer,arm)
    early['replay_admission']={'path':'INDEPENDENT_REVIEWED_CONTEXT_DEVELOPMENT','mechanical_pass_whitespace_normalized':True,'raw_exact_all_quotes':False,'independent_agent_semantic_review':True,'context_only_change':True}
    return early,answer,pins

def run(root,contract_path,answer_path,review_path,output):
    root=Path(root);c,answer,pins=validate(root,contract_path,answer_path,review_path)
    base=root/'tmp/recent_continuous_baseline_20261026_v7'
    def load(name):
        raw=(base/name).read_bytes();pins[str(base/name)]=sha256(raw).hexdigest();return json.loads(raw)
    inputs=load('execution_inputs.json');book=load('book.json')
    initial=next(r for r in book['daily_ledger'] if r['date']=='2021-11-03')
    audit=dict(zip(inputs['assembled']['session_dates'][:-1],book['provider_audit']))['2021-11-03']
    h=initial['shares'].get(SID,0);q=audit['target_shares'].get(SID,0)
    results={}
    for arm in ('BASELINE','A','B'):
        results[arm]=replay(inputs,book,'NO_CHANGE',published=c['published_at'],initial_date=c['initial_account_close'],target_transform=lambda target,state:transform(target,h,q,answer,arm))
    baseline=results['BASELINE']['book']['daily_ledger']
    for row in baseline:
        expected=next(r for r in book['daily_ledger'] if r['date']==row['date'])
        for k in ('cash','shares','equity','dividend_receivable'):
            if row.get(k,'0')!=expected.get(k,'0'):raise ValueError('BASELINE_NOT_EXACT')
    opening=opening_metrics(initial,inputs['ohlc'],results,'2021-11-04');summaries={}
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
    summary=dict(status='FIXED_CONTEXT_THREE_ARM_COMPLETE',admission=c['replay_admission'],baseline_exact=True,initial_held=h,initial_risk_target=q,opening=opening,arms=summaries,source_hashes=pins,limitations=['Known-outcome development sample, not holdout.','A and B same public source, but different fixed action mappings.','Positive B is neutral factor one; positive overweight not tested.','Two opens active; third expiry respects original risk; no new monthly selection.','Close-to-open gap is shared and not avoidable news profit.','No annualization or claim of preserved CAGR or improved full-strategy drawdown.'])
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    for arm,result in results.items():(output/(arm+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--contract',required=True);p.add_argument('--answer',required=True);p.add_argument('--review',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(run(a.root,a.contract,a.answer,a.review,a.output)))
