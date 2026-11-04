"""Independent B arithmetic: reuse finance checker, reconstruct risk without B code."""
import json,sys
from pathlib import Path
from fractions import Fraction as F
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from backtest.historical_dividend_identity_independent_review_v1 import review as finance_review

def need(ok,reason):
    if not ok:raise ValueError(reason)
def read(p):return json.loads(Path(p).read_bytes())

def risk_review(book,a,lifecycle):
    days=a['session_dates'];ledger=book['daily_ledger'];audits=book['provider_audit']
    need(len(lifecycle)==len(audits)==len(ledger)==len(days)-1,'FULL_RISK_LENGTH')
    need(not a['distribution_events'] and not a['cash_stock_merger_events'],'RISK_ACTION_SCOPE')
    peaks={};exited=set();targets={};month=None;last_epochs={};used_epochs=set();carried_count=0
    for i,(active,record,life) in enumerate(zip(days[1:],audits,lifecycle)):
        day=days[i];shares={} if i==0 else ledger[i-1]['shares'];held={s for s,q in shares.items() if q>0}
        epochs=life['position_epochs'];need(set(epochs)==held,'EPOCH_NOT_ACTUAL_HOLDINGS:'+day)
        for sid in held:
            if sid in last_epochs:need(epochs[sid]==last_epochs[sid],'CONTINUING_EPOCH_CHANGED:'+day)
            else:need(epochs[sid] not in used_epochs,'REENTRY_REUSED_OLD_EPOCH:'+day);used_epochs.add(epochs[sid])
        continuing=held&set(last_epochs);carry={};selection=record.get('selection')
        if selection is not None:
            targets=dict(selection['target_quantities']);carry={s:peaks[s] for s in targets if s in continuing and s in peaks}
            peaks=dict(carry);exited=set();month=day
        for change in record.get('target_adjustments',[]):
            sid=change['security_id'];matches=[e for e in a['actions'] if (e['date'],e['security_id'])==(day,sid)]
            need(len(matches)==1,'ACTION_UNIQUE');e=matches[0]
            need(e['type']=='split' and change.get('new_security_id')==sid,'SAME_ID_SPLIT_REQUIRED')
            ratio=F(e['new_shares'])/F(e['old_shares']);need(ratio>0,'SPLIT_RATIO')
            if selection is None:
                q=F(targets[sid])*ratio;need(q.denominator==1,'INTEGER_TARGET');targets[sid]=int(q)
            if sid in peaks:peaks[sid]/=ratio
            if sid in carry:carry[sid]/=ratio
        need(record.get('action')!='WAIT_POST_ACTION_MARK','UNSUPPORTED_GLOBAL_WAIT')
        need(record['monthly_ceiling']==targets,'CEILING:'+day)
        for sid in targets:
            close=F(a['close_prices'][sid][day]);need(close>0,'POSITIVE_CLOSE')
            peaks[sid]=max(peaks.get(sid,close),close)
            if close*5<=peaks[sid]*4:exited.add(sid)
        expected={s:0 if s in exited else q for s,q in targets.items()}
        need(record['target_shares']==expected,'EFFECTIVE_TARGET:'+day)
        risk=record['risk_overlay'];state=risk.get('state')
        if targets:
            need(state['decision_date']==month and state['session_date']==day,'RISK_DATES')
            need({s:F(v) for s,v in state['peaks'].items()}==peaks,'INDEPENDENT_PEAK:'+day)
            need(set(state['exited'])==exited,'INDEPENDENT_EXIT_LATCH:'+day)
            need({s:F(v) for s,v in state['last_closes'].items()}=={s:F(a['close_prices'][s][day]) for s in targets},'CLOSE_BINDING')
            need(risk['effective_target_quantities']==expected,'OVERLAY_TARGET')
        else:need(risk=={'empty_target':True},'EMPTY_RISK');peaks={};exited=set();month=None
        need(life['day']==day and life['month']==record['target_decision_date'],'LIFECYCLE_DATE')
        need({s:F(p) for s,p in life['carried_peaks'].items()}==carry,'CARRIED_PROOF:'+day)
        carried_count+=bool(carry)
        wanted=sorted((s,'BUY' if expected.get(s,0)>shares.get(s,0) else 'SELL',abs(expected.get(s,0)-shares.get(s,0))) for s in set(expected)|set(shares) if expected.get(s,0)!=shares.get(s,0))
        need(sorted((o['security_id'],o['side'],o['quantity']) for o in record['orders'])==wanted,'ORDER_DIFFERENCE:'+day)
        for o in record['orders']:
            need(o['decision_date']==day and o['active_date']==active and F(o['decision_mark'])==F(a['close_prices'][o['security_id']][day]),'CAUSAL_ORDER_MARK')
        last_epochs=dict(epochs)
    return dict(status='INDEPENDENT_B_PEAK_EXIT_ORDER_PASS',sessions=len(audits),carried_months=carried_count,actual_position_epochs=len(used_epochs))

def run(window):
    p=ROOT/f'tmp/cross_month_held_peak_20261105/{window}';contract=read(p/'contract.json')
    for path,h in contract['source_hashes'].items():need(sha256((ROOT/path).read_bytes()).hexdigest()==h,'SOURCE_CHANGED:'+path)
    book=read(p/'book.json');need(book['status']=='COMPLETE','COMPLETE_BOOK_REQUIRED')
    name='recent_continuous_baseline_20261026_v7' if window=='2021_2023' else 'old_continuous_baseline_20261026_v9'
    d=read(ROOT/f'tmp/{name}/execution_inputs.json');supp=read(ROOT/'tmp/equal_four_20261105/source_review/admitted_supplement.json');d['dividend_events'].extend(supp['dividend_events'][window])
    finance=finance_review(book,d['assembled'],d['ohlc'],initial_cash='20000',dividend_events=d['dividend_events'],verify_selections=True,verify_risk_provider=False,expected_fee_bps='0',expected_slippage_bps='5')
    risk=risk_review(book,d['assembled'],read(p/'peak_lifecycle_audit.json'))
    result=dict(status='INDEPENDENT_B_ACCOUNT_AND_RISK_PASS',finance=finance,risk=risk,source_hashes={str(f.relative_to(ROOT)).replace('\\','/'):sha256(f.read_bytes()).hexdigest() for f in [p/'book.json',p/'peak_lifecycle_audit.json',p/'contract.json',Path(__file__)]},limitations='Conditional supplied data, no independent PIT/OOS or execution guarantee; old monthly resetting risk checker deliberately disabled and replaced by B arithmetic')
    (p/'independent_review.json').write_text(json.dumps(result,indent=2),encoding='utf-8');print(json.dumps(result))
if __name__=='__main__':run(sys.argv[1])
