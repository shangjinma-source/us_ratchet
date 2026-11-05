"""Fixed price-pattern daily proxy. New account runs; no production mutations."""
import argparse,json,time
from pathlib import Path
from fractions import Fraction as F
from decimal import Decimal,localcontext
from hashlib import sha256
from copy import deepcopy
from backtest.research_exact_fraction_json import loads,dumps
from docs.candidates.pullback_daily_engine_20261105 import run_account
from scripts.research import run_momentum_account_20261105 as original
ROOT=Path(__file__).resolve().parents[2]
TRAINING={'2021_2023':'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json','2024_2026':'tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json'}
TERMINAL={'research:security:alxn':'2021-07-20','research:security:mxim':'2021-08-25','research:security:xlnx':'2022-02-11','research:security:sgen':'2023-12-13','security:0001353283:848637104':'2024-03-15','security:0001013462:03662Q105':'2025-07-16','security:0001618921:931427108':'2025-08-27'}

def need(ok,reason):
    if not ok:raise ValueError(reason)
def save(path,value):path.write_text(dumps(value),encoding='utf8')
def decimal(x):
    q=F(x);return Decimal(q.numerator)/Decimal(q.denominator)

def compile_signals(document,window):
    assembled=document['assembled'];days=assembled['session_dates'];bars=document['ohlc'];plans={p['decision_date']:p for p in assembled['monthly_inputs']}
    source=json.loads((ROOT/TRAINING[window]).read_bytes());training={}
    for outer in source['windows']:
        w=outer.get('window',outer);training[w.get('decision_cutoff',w.get('decision_date'))]=w
    result={};coverage=[];breakouts={};states={};domain={}
    with localcontext() as ctx:
        ctx.prec=40
        for index,day in enumerate(days[:-1]):
            if day in plans:
                plan=plans[day];domain=plan['search_arguments']['metadata'];candidates={c['security_id']:c for c in training[day]['candidates'] if c.get('security_id')};states={}
                for sid in plan['search_arguments']['prices']:
                    closes=[decimal(x) for x in candidates[sid]['training_close']];need(len(closes)==253,'253_TRAINING_REQUIRED')
                    scale=decimal(plan['search_arguments']['prices'][sid])/closes[-1];closes=[p*scale for p in closes];emas={};prior21=None
                    for n in (9,21,50):
                        value=sum(closes[:n])/n
                        for j,price in enumerate(closes[n:],n):
                            if n==21 and j==len(closes)-1:prior21=value
                            value+=(price-value)*Decimal(2)/Decimal(n+1)
                        emas[n]=value
                    states[sid]=dict(history=closes,ema=emas,prior21=prior21)
            else:
                installed={(e['date'],e['security_id']) for e in assembled['actions'] if e['type']=='split_identity'}
                for transition in document.get('dated_identity_transitions',[]):
                    old=transition['old_sid'];new=transition['new_sid']
                    if transition['date']!=day or (day,old) in installed:continue
                    ratio=decimal(transition['share_ratio'])
                    if old in states:
                        state=states.pop(old);state['history']=[p/ratio for p in state['history']];state['ema']={n:v/ratio for n,v in state['ema'].items()};states[new]=state
                        if old in domain:domain=deepcopy(domain);domain[new]=deepcopy(domain.pop(old))
                    breakouts.pop(old,None)
                for e in assembled['actions']:
                    if e['date']==day and e['type']=='merger':
                        states.pop(e['security_id'],None);breakouts.pop(e['security_id'],None)
                    if e['date']==day and e['type'] in ('split','split_identity'):
                        sid=e['security_id'];new=e.get('new_security_id',sid);ratio=decimal(e['new_shares'])/decimal(e['old_shares'])
                        if sid in states:
                            state=states.pop(sid);state['history']=[p/ratio for p in state['history']];state['ema']={n:v/ratio for n,v in state['ema'].items()};states[new]=state
                            if new!=sid and sid in domain:domain=deepcopy(domain);domain[new]=domain.pop(sid)
                        breakouts.pop(sid,None)
                for sid in list(states):
                    if sid in TERMINAL and day>TERMINAL[sid]:states.pop(sid);breakouts.pop(sid,None)
                for sid,state in states.items():
                    need(sid in bars and day in bars[sid],'MISSING_LEGAL_DAILY_PRICE:'+day+':'+sid)
                    value=decimal(bars[sid][day]['close']);state['prior21']=state['ema'][21];state['history'].append(value)
                    for n in (9,21,50):state['ema'][n]+=(value-state['ema'][n])*Decimal(2)/Decimal(n+1)
            entries=[];ema9={};eligible=[]
            for sid,state in states.items():
                if sid not in domain or (sid in TERMINAL and day>TERMINAL[sid]):continue
                need(sid in bars and day in bars[sid],'MISSING_LEGAL_ANCHOR_PRICE:'+day+':'+sid)
                eligible.append(sid);ema9[sid]=str(state['ema'][9]);bar=bars[sid][day];close=decimal(bar['close']);low=decimal(bar['low']);high=decimal(bar['high']);e=state['ema']
                before=days[max(0,index-20):index]
                if len(before)<20 or any(d not in bars[sid] for d in before):continue
                # Convert each old OHLC into today's nominal split coordinate.
                def adjusted(old,field):
                    value=decimal(bars[sid][old][field])
                    for action in assembled['actions']:
                        if action['security_id']==sid and action['type']=='split' and old<action['date']<=day:value*=decimal(action['old_shares'])/decimal(action['new_shares'])
                    return value
                trend=e[9]>e[21]>e[50] and e[21]>state['prior21']
                prior=breakouts.get(sid)
                if prior and 1<=index-prior['index']<=5:
                    prior['low']=min(prior['low'],low)
                    if trend and low<=e[9]<close and close>e[21] and high-low<prior['range'] and close>adjusted(days[index-1],'high'):
                        entries.append(dict(security_id=sid,issuer_id=domain[sid]['issuer_id'],stop=str(prior['low']),rank_return=str(state['history'][-1]/state['history'][-64]-1),breakout_date=prior['day'],confirmation_date=day));del breakouts[sid]
                if close>max(adjusted(d,'high') for d in before) and trend:breakouts[sid]=dict(index=index,day=day,range=high-low,low=Decimal('Infinity'))
            nextday=days[index+1]
            transition_old={t['old_sid'] for t in document.get('dated_identity_transitions',[]) if t['date']==nextday}
            effective=[sid for sid in eligible if (sid not in TERMINAL or nextday<=TERMINAL[sid]) and sid not in transition_old]
            entries=[e for e in entries if e['security_id'] in effective]
            result[day]=dict(eligible=sorted(eligible),effective_eligible=sorted(effective),ema9=ema9,entries=entries)
            coverage.append(dict(date=day,eligible=len(eligible),entry_signals=len(entries)))
    return result,coverage

def run(window,output,first_only=False):
    started=time.monotonic();out=(ROOT/output).resolve();need(out.is_relative_to(ROOT/'tmp'),'TMP_OUTPUT');out.mkdir(parents=True,exist_ok=False)
    freeze=json.loads((ROOT/'research_contracts/momentum_account_execution_20261105/freeze.json').read_bytes());original.check(freeze['source_hashes']);original.inventory.PINS.clear()
    document,prices,review,legacy,proof=original.inventory.inputs(window,original.read(freeze['inventory_base_freeze']));pins={**original.inventory.PINS,**freeze['source_hashes']}
    document,review=original.prepare_actions(window=window,document=document,prices=prices,review=review,pins=pins,freeze=freeze)
    from docs.candidates.pullback_dividends_20261105 import append_review as append_dividends
    extra=append_dividends(document,review,window);pins.update(extra['source_hashes']);save(out/'additional_dividends.json',extra)
    if window=='2024_2026':
        from docs.candidates.pullback_absence_20261105 import append_review as append_absence
        extra=append_absence(document,review);pins.update(extra['source_hashes']);save(out/'additional_absence.json',extra)
    from docs.candidates.pullback_short_official_review_20261105 import append_review as append_official
    extra=append_official(document,review,window);pins.update(extra['source_hashes']);save(out/'additional_short_official.json',extra)
    for name in ['docs/candidates/pullback_short_official_review_20261105.py','docs/candidates/pullback_dividends_20261105.py','docs/candidates/pullback_absence_20261105.py',__file__,'docs/candidates/pullback_daily_engine_20261105.py','docs/candidates/pullback_execution_contract_20261105.md',TRAINING[window],'docs/alxn_merger_evidence_20261025.md','docs/recent_monthly_price_coverage_20261025.md','tmp/alxn_economic_events_20261025/schema_mapping.json','docs/old_holdings_lifecycle_gate_20261026.md']:
        path=Path(name);path=path if path.is_absolute() else ROOT/path;pins[path.relative_to(ROOT).as_posix()]=sha256(path.read_bytes()).hexdigest()
    save(out/'contract.json',dict(window=window,source_hashes=pins,initial_cash='20000',variants=['full_trail','half_3r'],scope='DAILY_PRICE_PATTERN_PROXY_NO_VOLUME_OR_MARKETCAP',deadline='2026-11-05T22:30:00+08:00',first_only=first_only))
    signals,coverage=compile_signals(document,window);save(out/'signals.json',signals);save(out/'coverage.json',coverage);save(out/'execution_inputs.json',dict(document=document,review=review))
    gate_cache={};split_admission=original.FixedSplitAdmission()
    def gate(previous,day,shares,entries):
        args=dict(decision_date=previous,account_state=dict(shares=shares))
        # Only cash/risk/slot-valid planned entry quantities; no marker shares.
        target={**shares,**{e['security_id']:shares.get(e['security_id'],0)+e['quantity'] for e in entries}}
        key=(previous,day,tuple(sorted(shares.items())),tuple(sorted(target.items())))
        if key not in gate_cache:
            if window=='2021_2023':
                value=original.inventory.exposed_action_blockers(args,dict(target_quantities=target),day,prices,review,day,document['dividend_events'])
                value=split_admission.admit(value,document,window)
                if 'research:security:sgen' in value['exposed']:value=original.sgen_admit(gate=value,document=document,arguments=args,selected=dict(target_quantities=target),active=day)
            else:
                value=original.inventory.exposure_gate(document,args,dict(target_quantities=target),day,day)
                value=original.inventory.admit_reviewed_dividends(value,review,document['dividend_events']);value=original.inventory.admit_period_absence(value,review);value=legacy.admit(value,proof);value=split_admission.admit(value,document,window)
            gate_cache[key]=value
            if not value['admitted']:save(out/('failure_gate_'+day+'.json'),value)
        return deepcopy(gate_cache[key])
    summaries=[]
    for variant in (('full_trail',) if first_only else ('full_trail','half_3r')):
        for delay in ([0] if first_only else ([0,1,5] if window=='2021_2023' else [0])):
            book=run_account(session_dates=document['assembled']['session_dates'],ohlc=document['ohlc'],signals=signals,actions=document['assembled']['actions'],dividend_events=document['dividend_events'],gate=gate,variant=variant,settlement_delay=delay)
            name=variant+'_D'+str(delay);save(out/(name+'.book.json'),book);summaries.append(dict(name=name,status=book['status'],reason=book['reason'],sessions=len(book['daily_ledger']),fills=len(book['order_log']),total_return=book['total_return'],maximum_drawdown=book['maximum_drawdown']))
    original.check(pins);save(out/'summary.json',dict(window=window,results=summaries,elapsed_seconds=time.monotonic()-started));print(json.dumps(summaries))

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--window',required=True,choices=['2021_2023','2024_2026']);p.add_argument('--output',required=True);p.add_argument('--first-only',action='store_true');a=p.parse_args();run(a.window,a.output,a.first_only)
