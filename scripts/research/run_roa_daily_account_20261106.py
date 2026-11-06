"""Frozen ROA signals -> independent integer account; stops at first strict gate gap."""
import argparse,json
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from backtest.research_exact_fraction_json import loads,dumps
from docs.candidates.roa_daily_account_20261106 import run_account
from docs.candidates.rsi2_daily_absence_scope_20261106 import scope_review
from scripts.research import run_momentum_account_20261105 as original
ROOT=Path(__file__).resolve().parents[2]
INPUTS={'2021_2023':'tmp/breakout55_account_20261106_early_v2','2024_2026':'tmp/breakout55_account_20261106_late_v3'}
DIAG='tmp/profitability_roa_continuous_20261106_SMA200.json'
def main(output):
    out=(ROOT/output).resolve()
    if not out.is_relative_to(ROOT/'tmp'):raise ValueError('TMP_ONLY')
    out.mkdir(parents=True,exist_ok=False)
    pins={};packs={};prices={};legacy_proofs={};historical_code_changes=[]
    def pin(name):
        raw=(ROOT/name).read_bytes();pins[name]=sha256(raw).hexdigest();return raw
    diagnostic=json.loads(pin(DIAG));original.check(diagnostic['source_hashes']);pins.update(diagnostic['source_hashes'])
    freeze=original.read('research_contracts/momentum_account_execution_20261105/freeze.json')
    for window,folder in INPUTS.items():
        closure=loads(pin(folder+'/source_closure.json').decode('utf8'))
        for name,expected in closure.items():
            actual=sha256((ROOT/name).read_bytes()).hexdigest()
            if actual!=expected:
                if name not in ('scripts/research/run_breakout55_account_20261106.py','docs/candidates/breakout55_daily_engine_20261106.py'):raise ValueError('EVIDENCE_CHANGED:'+name)
                historical_code_changes.append({'path':name,'historical':expected,'current':actual,'not_executed_as_generator':True})
            pins[name]=actual
        historical_name='tmp/breakout55_diagnostic_20261106_'+window+'/contract.json'
        historical=loads(pin(historical_name).decode('utf8'))
        input_name=folder+'/execution_inputs.json';raw=pin(input_name)
        if pins[input_name]!=historical['source_hashes'][input_name]:raise ValueError('HISTORICAL_EXECUTION_SHA_CHANGED')
        packs[window]=loads(raw.decode('utf8'))
        _,prices[window],_,legacy,proof=original.inventory.inputs(window,original.read(freeze['inventory_base_freeze']))
        legacy_proofs[window]=(legacy,proof)
    from docs.candidates.roa_exact_supplements_20261106 import install,admit
    supplement_rows=install(packs,pins)
    pin('docs/candidates/roa_exact_supplements_20261106.py')
    days=sorted(set(d for p in packs.values() for d in p['document']['assembled']['session_dates']))
    bars={};actions=[];dividends=[];seen=set()
    for pack in packs.values():
        doc=pack['document']
        for sid,series in doc['ohlc'].items():
            for date,bar in series.items():
                if date in bars.setdefault(sid,{}) and bars[sid][date]!=bar:raise ValueError('OHLC_CONFLICT:'+sid+date)
                bars[sid][date]=bar
        for event in doc['assembled']['actions']:
            if event not in actions:actions.append(event)
        for event in doc['dividend_events']:
            key=event['event_id']
            if key not in seen:dividends.append(event);seen.add(key)
    selections=sorted(diagnostic['monthly_selection_audit'],key=lambda x:x['cutoff'])
    transitions=diagnostic['results'][0]['transitions'];signals={}
    for previous in days[:-1]:
        selection=max((s for s in selections if s['cutoff']<=previous),key=lambda s:s['cutoff'])
        risk=diagnostic['results'][0]['warmup']['confirmed_anchor_state']
        for transition in transitions:
            if transition['signal_date']<=previous:risk=transition['to_on']
        signals[previous]={'decision_date':selection['cutoff'],'weights':{s['security_id']:'1/10' for s in selection['selected']},'risk_on':risk}
    split=original.FixedSplitAdmission()
    def gate(previous,day,shares,entries):
        window='2021_2023' if day<='2023-12-29' else '2024_2026'
        pack=packs[window];doc=pack['document'];review=pack['review'];legacy,proof=legacy_proofs[window]
        args={'decision_date':previous,'account_state':{'shares':shares}}
        target={**shares,**{e['security_id']:shares.get(e['security_id'],0)+e['quantity'] for e in entries}}
        selected={'target_quantities':target}
        if window=='2021_2023':
            value=original.inventory.exposed_action_blockers(args,selected,day,prices[window],scope_review(review,previous,day),day,doc['dividend_events'])
            value=split.admit(value,doc,window)
        else:
            value=original.inventory.exposure_gate(doc,args,selected,day,day)
            value=original.inventory.admit_reviewed_dividends(value,review,doc['dividend_events'])
            value=original.inventory.admit_period_absence(value,review);value=legacy.admit(value,proof);value=split.admit(value,doc,window)
        value=admit(value,supplement_rows)
        if not value['admitted']:(out/('failure_gate_'+day+'.json')).write_text(dumps(value),encoding='utf8')
        return value
    for name in [__file__,'docs/candidates/roa_daily_account_20261106.py','docs/candidates/roa_daily_account_contract_20261106.md']:
        path=Path(name);name=path.relative_to(ROOT).as_posix() if path.is_absolute() else name;pin(name)
    (out/'freeze.json').write_text(dumps({'source_hashes':pins,'historical_generator_changes':historical_code_changes,'execution':'MONTHLY_PRIOR_CLOSE_NEXT_OPEN_DAILY_MARKET_NEXT_OPEN_PENDING_NEXT_CLOSE','commission':'0 explicit research assumption','slippage_bps':5,'initial_cash':'20000','continuous_account':True,'not_price_diagnostic_account':True}),encoding='utf8')
    (out/'signals.json').write_text(dumps(signals),encoding='utf8')
    book=run_account(session_dates=days,ohlc=bars,signals=signals,actions=actions,dividend_events=dividends,gate=gate)
    book['evidence_status']='RESEARCH_STRICT_GATES_NOT_PRODUCTION';original.check(pins)
    (out/'book.json').write_text(dumps(book),encoding='utf8')
    summary={'status':book['status'],'reason':book['reason'],'sessions':len(book['daily_ledger']),'fills':len(book['order_log']),'metrics_withheld':True,'requested_first':days[1],'requested_last':days[-1]}
    (out/'summary.json').write_text(json.dumps(summary,indent=2),encoding='utf8');print(json.dumps(summary))
if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--output',required=True);main(parser.parse_args().output)

