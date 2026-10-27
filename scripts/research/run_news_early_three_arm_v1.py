"""One fixed early-release development experiment. No model or network calls."""
import argparse
from copy import deepcopy
from fractions import Fraction
from hashlib import sha256
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[2]))
from scripts.research.run_news_preopen_execution_probe_v1 import replay,opening_metrics
SID='research:security:mrna'


def retained_fraction(value):
    if type(value) is not str: raise ValueError('RATIONAL_STRING_REQUIRED')
    n=Fraction(value)
    if not 0<=n<=1: raise ValueError('FRACTION_RANGE')
    return n


def transform(q, h_initial, q_initial, answer, arm):
    result=deepcopy(q); amount=q.get(SID,0)
    if arm=='BASELINE': return result
    if arm=='B':
        signal=answer['B_signal']
        if signal['direction'] not in ('NEGATIVE','NEUTRAL','POSITIVE','ABSTAIN') or signal['materiality'] not in ('HIGH','MODERATE','UNCERTAIN'): raise ValueError('SIGNAL_INVALID')
        result[SID]=amount//2 if signal['direction']=='NEGATIVE' and signal['materiality']=='HIGH' else amount
        return result
    if arm!='A': raise ValueError('ARM_INVALID')
    a=answer['A_direct'];action=a['action'];buy=retained_fraction(a['buy_fraction']);hold=retained_fraction(a['holding_fraction'])
    if action in ('KEEP','ABSTAIN') and (buy,hold)==(1,1): cap=amount
    elif action=='PAUSE_BUY' and (buy,hold)==(0,1): cap=h_initial
    elif action=='REDUCE_BUY' and 0<buy<1 and hold==1: cap=h_initial+int(max(q_initial-h_initial,0)*buy)
    elif action=='REDUCE_HOLDING' and buy==0 and 0<hold<1: cap=int(h_initial*hold)
    elif action=='EXIT' and (buy,hold)==(0,0):cap=0
    else:raise ValueError('ACTION_FRACTIONS_INCONSISTENT')
    result[SID]=min(amount,cap)
    return result


def verify_action_evidence(answer,text,source_id):
    for section in ('A_direct','B_signal'):
        evidence=answer[section].get('evidence')
        if not isinstance(evidence,list) or not evidence:raise ValueError('ACTION_EVIDENCE_REQUIRED')
        for item in evidence:
            quote=item.get('quote')
            if item.get('source_id')!=source_id or not isinstance(quote,str) or not quote.strip() or quote not in text:raise ValueError('ACTION_QUOTE_NOT_EXACT')


def validate(root,contract_path,answer_path,review_path):
    root=Path(root);pins={}
    def read(path):
        path=Path(path);path=path if path.is_absolute() else root/path
        raw=path.read_bytes();pins[str(path)]=sha256(raw).hexdigest();return json.loads(raw),sha256(raw).hexdigest()
    c,ch=read(contract_path);answer,ah=read(answer_path);review,_=read(review_path)
    manual=review.get('status')=='DEVELOPMENT_REPLAY_ONLY_WITH_EXPLICIT_RAW_FAILURE'
    reviewed={}
    if manual:
        required={'raw_mechanical_pass':False,'raw_answer_unchanged':True,'action_evidence_exact_pass':True,'semantic_pass':True,'development_replay_permitted':True,'production_authorized':False,'automatic_mechanical_admission_permitted':False}
        if any(review.get(k) is not v for k,v in required.items()):raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
        for path,digest in review.get('source_hashes',{}).items():
            actual=root/path
            if sha256(actual.read_bytes()).hexdigest()!=digest:raise ValueError('REVIEWED_SOURCE_CHANGED')
            reviewed[str(actual.resolve())]=digest;pins[path]=digest
        for path,digest in ((contract_path,ch),(answer_path,ah)):
            if reviewed.get(str((root/path).resolve()))!=digest:raise ValueError('REVIEW_ANSWER_BINDING_REQUIRED')
    elif review.get('status')!='APPROVED_FOR_FIXED_REPLAY' or review.get('mechanical_pass') is not True or review.get('semantic_pass') is not True or review.get('source_contract_sha256')!=ch or review.get('answer_sha256')!=ah:raise ValueError('INDEPENDENT_REVIEW_REQUIRED')
    frozen_path='tmp/news_early_mrna_20211104_input_20261028/frozen_experiment_contract.json'
    frozen,fh=read(frozen_path)
    approved_hash=reviewed.get(str((root/frozen_path).resolve())) if manual else review.get('frozen_experiment_contract_sha256')
    if fh!='2813bb0d96a98ab6a64121506e81399893e1b7e843ebf06899688fcdd69d1e16' or approved_hash!=fh or frozen.get('source_contract_sha256')!=ch:raise ValueError('FROZEN_EXPERIMENT_CHANGED')
    if c.get('event_id')!='MRNA_20211104_EARNINGS_RELEASE' or c.get('initial_account_close')!='2021-11-03' or c.get('published_at')!='2021-11-04T07:00:00-04:00' or c.get('processing_latency_seconds')!=120:raise ValueError('FIXED_EARLY_SOURCE_REQUIRED')
    for path,digest in c['source_hashes'].items():
        raw=(root/path).read_bytes()
        if sha256(raw).hexdigest()!=digest:raise ValueError('SOURCE_CHANGED')
        pins[path]=digest
    for field in ('full_text','source_original','public_input','prompt_template'):
        path=c[field+'_path'];digest=c[field+'_sha256']
        raw=(root/path).read_bytes(); disk_digest=sha256(raw).hexdigest()
        if field=='full_text':
            text=(root/path).read_text(encoding='utf-8')
            if sha256(text.encode('utf-8')).hexdigest()!=digest:raise ValueError('NORMALIZED_FULL_TEXT_CHANGED')
            public=json.loads((root/c['public_input_path']).read_text(encoding='utf-8'))
            if public['text']!=text:raise ValueError('MODEL_TEXT_MISMATCH')
        elif field=='prompt_template':
            if sha256((root/path).read_text(encoding='utf-8').encode('utf-8')).hexdigest()!=digest:raise ValueError('NORMALIZED_PROMPT_CHANGED')
        elif disk_digest!=digest:raise ValueError('EARLY_INPUT_CHANGED')
        pins[path]=disk_digest
    # Mechanical/semantic opinion is independently reviewed; runner binds the
    # exact reviewed answer and does not silently replace it with old SEC output.
    if answer.get('source_id')!=c['event_id']:raise ValueError('ANSWER_SOURCE_MISMATCH')
    text=(root/c['full_text_path']).read_text(encoding='utf-8')
    verify_action_evidence(answer,text,c['event_id'])
    c['replay_admission']={'path':'OFFLINE_REVIEWED_ACTION_EVIDENCE' if manual else 'AUTOMATIC_AND_INDEPENDENT_REVIEW','raw_mechanical_pass':not manual,'independent_agent_semantic_review':True,'full_text_normalized_sha256':c['full_text_sha256']}
    for arm in ('A','B'):transform({SID:33},33,33,answer,arm)
    return c,answer,pins


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
    for file in (__file__,'scripts/research/run_news_preopen_execution_probe_v1.py','backtest/monthly_exit_core_research_adapter.py','backtest/historical_dividend_next_open_book_research.py'):
        pins[str(file)]=sha256(Path(file).read_bytes()).hexdigest()
    summary=dict(status='FIXED_EARLY_THREE_ARM_COMPLETE',admission=c['replay_admission'],baseline_exact=True,initial_held=h,initial_risk_target=q,opening=opening,arms=summaries,source_hashes=pins,limitations=['Known-outcome development sample, not holdout.','A and B same public source, but different fixed action mappings.','Positive B is neutral factor one; positive overweight not tested.','Two opens active; third expiry respects original risk; no new monthly selection.','Close-to-open gap is shared and not avoidable news profit.','No annualization or claim of preserved CAGR or improved full-strategy drawdown.'])
    output=Path(output);output.mkdir(parents=True,exist_ok=False)
    for arm,result in results.items():(output/(arm+'.json')).write_text(json.dumps(result,indent=2),encoding='utf-8')
    (output/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf-8');return summary

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--root',default='.');p.add_argument('--contract',required=True);p.add_argument('--answer',required=True);p.add_argument('--review',required=True);p.add_argument('--output',required=True);a=p.parse_args()
    print(json.dumps(run(a.root,a.contract,a.answer,a.review,a.output)))
