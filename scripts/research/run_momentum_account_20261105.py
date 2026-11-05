"""Isolated fixed-roster account launcher; no run without reviewed action hooks."""
import argparse, importlib.util, json, os, time
from copy import deepcopy
from hashlib import sha256
from pathlib import Path
from backtest.research_exact_fraction_json import dumps as exact_dumps
from docs.candidates.momentum_account_decision_20261105 import make_decider, ROSTER_PATH, ROSTER_SHA, CORE
from docs.candidates.momentum_action_bridge_20261105 import build_provider, ActionRisk
from docs.candidates.momentum_cash_merger_settlement_20261105 import run_book
from docs.candidates.momentum_split_admission_20261105 import FixedSplitAdmission
from docs.candidates.downside_resume_chain_20261105 import append_ordinary_artifact
from docs.candidates.momentum_absence_20261105 import append_review
from docs.candidates import momentum_sgen_admission_20261105 as sgen
from scripts.research import inventory_momentum_actions_20261105 as inventory
ROOT=Path(__file__).resolve().parents[2]
NAME='scripts/research/run_momentum_account_20261105.py'

def need(ok,reason):
    if not ok:raise ValueError(reason)

def read(path):return json.loads((ROOT/path).read_bytes())
def digest(path):return sha256((ROOT/path).read_bytes()).hexdigest()
def save(path,value):
    temporary=path.with_name(path.name+'.writing');temporary.write_text(exact_dumps(value),encoding='utf8');temporary.replace(path)

def check(pins):
    for path,value in pins.items():
        need((ROOT/path).resolve().is_relative_to(ROOT),'SOURCE_OUTSIDE_REPO')
        need(digest(path)==value,'SOURCE_CHANGED:'+path)

def prepare_actions(*,window,document,prices,review,pins,freeze):
    if window=='2021_2023':
        document['prepared_input_candidate']=deepcopy(document['prepared'])
        names=['tmp/momentum_early_dividends_20261105/supplement.json']
    else:
        names=['tmp/momentum_late_dividends_20261105/supplement.json','tmp/amat_202408_t1_resolution_20261105/supplement.json']
    def require_pins(extra):
        need(all(freeze['source_hashes'].get(path)==value for path,value in extra.items()),'ACTION_NOT_PREFROZEN')
        check(extra);pins.update(extra)
    for name in names:
        artifact=read(name);require_pins({name:digest(name),**artifact['source_hashes']})
        append_ordinary_artifact(document,review,artifact)
    if window=='2024_2026':require_pins(append_review(document,review)['source_hashes'])
    splits=FixedSplitAdmission();require_pins(splits.source_hashes)
    document=splits.install(document,window)
    if window=='2021_2023':document,review=sgen_prepare(document=document,review=review,pins=pins,freeze=freeze)
    return document,review

def sgen_prepare(*,document,review,pins,freeze):
    extra=sgen.install(document)
    need(all(freeze['source_hashes'].get(path)==value for path,value in extra.items()),'SGEN_NOT_PREFROZEN')
    check(extra);pins.update(extra)
    return document,review

def sgen_admit(*,gate,document,arguments,selected,active):
    return sgen.admit(gate,document['assembled']['actions'])

def action_gate(*,window,arguments,selected,until,active,document,prices,review,legacy,proof):
    if window=='2021_2023':
        gate=inventory.exposed_action_blockers(arguments,selected,until,prices,review,active,document['dividend_events'])
        gate=FixedSplitAdmission().admit(gate,document,window)
        gate=sgen_admit(gate=gate,document=document,arguments=arguments,selected=selected,active=active)
    else:
        gate=inventory.exposure_gate(document,arguments,selected,until,active)
        gate=inventory.admit_reviewed_dividends(gate,review,document['dividend_events'])
        gate=inventory.admit_period_absence(gate,review)
        gate=legacy.admit(gate,proof)
        gate=FixedSplitAdmission().admit(gate,document,window)
    return gate

def run_scenario(*,window,delay,output,freeze):
    start=time.monotonic();output.mkdir(parents=True,exist_ok=False)
    inventory.PINS.clear()
    old_freeze=read(freeze['inventory_base_freeze']);check(old_freeze['source_hashes'])
    document,prices,review,legacy,proof=inventory.inputs(window,old_freeze)
    pins={**inventory.PINS,**freeze['source_hashes']}
    need(all(k in freeze['source_hashes'] and freeze['source_hashes'][k]==v for k,v in inventory.PINS.items()),'INPUTS_NOT_PREFROZEN')
    document,review=prepare_actions(window=window,document=document,prices=prices,review=review,pins=pins,freeze=freeze)
    assembled=document['assembled'];dates=assembled['session_dates'];plans=assembled['monthly_inputs']
    count={'2021_2023':36,'2024_2026':31}[window]
    need(len(plans)==count,'FIXED_MONTH_COUNT')
    for plan in plans:
        plan['source_hashes'].update({ROSTER_PATH:ROSTER_SHA,CORE:pins[CORE]})
    decider=make_decider(root=ROOT,window=window)
    next_month={p['decision_date']:(plans[i+1]['decision_date'] if i+1<len(plans) else dates[-1]) for i,p in enumerate(plans)}
    decisions=[]
    def guard():need(time.monotonic()-start<freeze['seconds_per_scenario'],'FIXED_TIME_LIMIT')
    def select(**arguments):
        guard();day=arguments['decision_date'];need(day not in decisions and len(decisions)<count,'ONE_SIZING_PER_MONTH')
        selected=decider(**arguments);decisions.append(day)
        save(output/(day+'.selection.json'),dict(arguments=arguments,selected=selected))
        gate=action_gate(window=window,arguments=arguments,selected=selected,until=next_month[day],active=dates[dates.index(day)+1],document=document,prices=prices,review=review,legacy=legacy,proof=proof)
        save(output/(day+'.exposure.json'),gate)
        need(gate['admitted'],'ACTUAL_ACCOUNT_ACTION_GATE_BLOCKED:'+day)
        return selected
    spec=importlib.util.spec_from_file_location('private_momentum_kernel',ROOT/'docs/candidates/qqq_risk_budget_account_runner.py')
    kernel=importlib.util.module_from_spec(spec);spec.loader.exec_module(kernel)
    kernel.decide_continuous_guided_for_account=select
    kernel.rerank=lambda result:result
    kernel.build_cost_monthly_quantity_provider=build_provider
    def book_callback(**kwargs):
        provider=kwargs['order_provider']
        def guarded(**state):guard();return provider(**state)
        kwargs['order_provider']=guarded
        return run_book(settlement_delay=delay,**kwargs)
    kernel.run_next_open_book=book_callback
    contract=dict(schema='FIXED_MOMENTUM_ACCOUNT_V1',window=window,settlement_delay=delay,source_hashes=pins,initial_cash='20000',fee_bps='0',slippage_bps='5',search_calls=0,maximum_target_sizings=count,pid=os.getpid(),full_pit=False,oos=False)
    save(output/'contract.json',contract)
    save(output/'execution_inputs.json',dict(document=document,review=review))
    try:
        book=kernel.run_frontier_capped_next_open(assembled=assembled,ohlc=document['ohlc'],initial_cash='20000',fee_bps='0',slippage_bps='5',risk=ActionRisk(assembled['actions']),max_new_searches=count,dividend_events=document['dividend_events'])
        # Kernel counts callback invocations as searches; name these honestly.
        book['target_sizing_calls']=book.pop('new_searches');book.pop('reused_searches');book['search_calls']=0
        save(output/'book.json',book);check(pins)
        summary=dict(status=book['status'],reason=book.get('reason'),completed_sessions=len(book['daily_ledger']),required_sessions=len(dates)-1,search_calls=0,target_sizing_calls=len(decisions),elapsed_seconds=time.monotonic()-start,settlement_delay=delay,independently_reviewed=False)
        save(output/'summary.json',summary);return summary
    except Exception as error:
        save(output/'failure.json',dict(error=repr(error),target_sizing_calls=len(decisions),search_calls=0,elapsed_seconds=time.monotonic()-start));raise

def run(*,window,output,freeze_path):
    freeze=read(freeze_path)
    need(freeze.get('schema')=='FIXED_MOMENTUM_EXECUTION_V1' and freeze.get('status')=='READY_FOR_REVIEWED_EXECUTION','EXECUTION_NOT_AUTHORIZED')
    need(freeze['source_hashes'].get(NAME)==digest(NAME),'RUNNER_NOT_FROZEN');check(freeze['source_hashes'])
    need(freeze['early_delays']==[0,1,5] and freeze['late_delays']==[0],'FIXED_ALL_DELAY_SCENARIOS')
    root=(ROOT/output).resolve();need(root.is_relative_to(ROOT/'tmp'),'ISOLATED_OUTPUT_REQUIRED');root.mkdir(parents=True,exist_ok=False)
    summaries=[]
    for delay in (freeze['early_delays'] if window=='2021_2023' else freeze['late_delays']):
        summaries.append(run_scenario(window=window,delay=delay,output=root/('D'+str(delay)),freeze=freeze))
    save(root/'all_scenarios.json',dict(window=window,scenarios=summaries,selection_of_best_delay_forbidden=True))

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--window',choices=['2021_2023','2024_2026'],required=True);parser.add_argument('--output',required=True);parser.add_argument('--freeze',required=True)
    args=parser.parse_args();run(window=args.window,output=args.output,freeze_path=args.freeze)
