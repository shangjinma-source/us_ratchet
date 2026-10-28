"""Fixed cross-month reference recovery research; fresh account selection and original action gates."""
import argparse
from copy import deepcopy
from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sys
import time
ROOT=Path(__file__).resolve().parents[2]
sys.path.insert(0,str(ROOT))
from scripts.run_old_continuous_probe_v1 import save,validate_selection_binding
from reentry_repair import run_reentry
from reference_coverage import ReferenceCoverage
from backtest.continuous_guided_account_decision import decide_continuous_guided_for_account
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
WINDOWS={'2021_2023':('recent_continuous_baseline_20261026_v7','recent_execution_prices_20261026','2020-12-31','2023-12-29',36),'2024_2026':('old_continuous_baseline_20261026_v9','old_window_execution_prices_20261026','2023-12-29','2026-07-30',31)}
DEADLINE=datetime(2026,10,28,22,tzinfo=timezone.utc)
def read(p):return json.loads(Path(p).read_bytes())
def digest(p):return sha256(Path(p).read_bytes()).hexdigest()
def require(ok,reason):
    if not ok:raise ValueError(reason)
def check(pins):
    for p,h in pins.items():require(digest(ROOT/p)==h,'SOURCE_CHANGED:'+p)
def run(window,mode,output,seconds,execute=False):
    frozen_path=Path(__file__).with_name('frozen_contract.json');frozen=read(frozen_path);check(frozen['source_hashes'])
    baseline_name,price_name,start,end,months=WINDOWS[window]
    base=ROOT/'tmp'/baseline_name; document=read(base/'execution_inputs.json'); baseline=read(base/'book.json')
    trend_path=ROOT/'tmp'/('trend_'+window+'_20261026_v1')/'execution_inputs.json'; prior=read(trend_path)
    review=prior['action_review']; prices_path=ROOT/'tmp'/price_name/'execution_prices_v1.json';prices=read(prices_path)
    assembled=document['assembled']; dates=assembled['session_dates']
    require((dates[0],dates[-1],len(assembled['monthly_inputs']))==(start,end,months),'FIXED_WINDOW_REQUIRED')
    require(baseline['status']=='COMPLETE','COMPLETE_BASELINE_REQUIRED')
    require(prior['baseline_execution_inputs']==document,'ACTION_REVIEW_BASELINE_MISMATCH')
    require(digest(prices_path)==prior['execution_input_hashes']['prices'],'PRICE_BINDING_MISMATCH')
    check(assembled['source_hashes']);check(document.get('action_source_hashes',{}));check(review['source_hashes'])
    for plan in assembled['monthly_inputs']:
        a=plan['search_arguments'];require(a['max_objective_evaluations']==8192 and str(a['fee_bps'])=='0' and str(a['minimum_cash_buffer'])=='0' and a['fixed_seed']=='fresh-quantity-20261014-v1','SEARCH_RULE_CHANGED')
    binding={'window':window,'mode':mode,'start':start,'end':end,'maximum_new_searches':months,'seconds':seconds,'source_hashes':{str(p.relative_to(ROOT)).replace('\\','/'):digest(p) for p in [base/'execution_inputs.json',base/'book.json',trend_path,prices_path,Path(__file__),Path(__file__).with_name('reentry_repair.py'),Path(__file__).with_name('reference_coverage.py'),Path(__file__).parent/'nvda_cash_reference/review.json',Path(__file__).parent/'nvda_cash_reference/independent_review.json']}}
    binding['source_hashes'][frozen_path.relative_to(ROOT).as_posix()]=digest(frozen_path)
    legacy_admit=None
    if window=='2024_2026':
        import importlib.util
        ap=ROOT/'tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py'
        require(digest(ap)=='2016ac8bfc802ae3042bd7592e3a897bcb0568c88a79161a8de05d58dc8f3aa5','LEGACY_ADAPTER_PIN')
        spec=importlib.util.spec_from_file_location('reentry_wbd_legacy',ap);adapter=importlib.util.module_from_spec(spec);spec.loader.exec_module(adapter)
        proof=adapter.certify(ROOT,dates);legacy_admit=lambda gate:adapter.admit(gate,proof)
        binding['source_hashes'][ap.relative_to(ROOT).as_posix()]=digest(ap);binding['source_hashes'].update(proof['source_hashes'])
    cash_review=read(Path(__file__).parent/'nvda_cash_reference/review.json');check(cash_review['source_hashes'])
    binding.update(mechanism='COMPLETED_CLOSE_EVER_RECOVERED_AFTER_HELD_EXIT_INTENT',fee_bps=0,slippage_bps=5,maximum_new_searches_both_windows=67,no_start_after_utc='2026-10-28T21:40:00Z',stop_utc='2026-10-28T22:00:00Z',reference_cash_review_execution_authorization=False,resume_authorized=False,resume_requirement='Separate reviewed exact-argument checkpoint launcher with cumulative prior search budget; never restart fresh to bypass 67')
    coverage=ReferenceCoverage(window=window,document=document,prices=prices,review=review,source_validator=lambda:check(binding['source_hashes']),reference_cash_review=cash_review,root=ROOT,legacy_absence=legacy_admit)
    if not execute:return {'status':'PREFLIGHT_ONLY','binding':binding}
    require(datetime.now(timezone.utc)<datetime(2026,10,28,21,40,tzinfo=timezone.utc),'NEW_LONG_RUN_CUTOFF');require(0<seconds<=10800,'BOUNDED_SECONDS_REQUIRED')
    output=Path(output);output.mkdir(parents=True,exist_ok=False);save(output/'contract.json',binding)
    budget={'new':0,'reused':0};started=time.monotonic()
    def guard():
        require(datetime.now(timezone.utc)<DEADLINE and time.monotonic()-started<seconds,'TIME_BUDGET_REACHED')
    def selector(**arguments):
        guard()
        day=arguments['decision_date'];p=base/(day+'.selection.json');old=read(p) if p.exists() else None
        if old and old['arguments']==arguments:
            raw=old['raw_selection'];budget['reused']+=1
        else:
            require(mode!='BASELINE','BASELINE_ARGUMENTS_CHANGED');require(budget['new']<months,'SEARCH_LIMIT')
            raw=decide_continuous_guided_for_account(**arguments);budget['new']+=1
        validate_selection_binding(raw,arguments);save(output/(day+'.selection.json'),dict(arguments=arguments,raw_selection=raw));save(output/'search_budget.json',budget);guard();return raw
    decision_dates=[p['decision_date'] for p in assembled['monthly_inputs']]+[dates[-1]]
    def callback(arguments,selected):
        day=arguments['decision_date'];until=decision_dates[decision_dates.index(day)+1];active=dates[dates.index(day)+1]
        save(output/(day+'.decision.json'),dict(arguments=arguments,selected=selected))
        if months==36:
            from scripts.run_recent_continuous_probe import exposed_action_blockers
            gate=exposed_action_blockers(arguments,selected,until,prices,review,active,document['dividend_events'])
        else:
            from scripts.assemble_old_continuous_inputs_v1 import exposure_gate
            from scripts.run_old_continuous_probe_v4 import admit_reviewed_dividends,admit_period_absence,admit_split_liquidation
            gate=exposure_gate(document,arguments,selected,until,active)
            gate=admit_reviewed_dividends(gate,review,document['dividend_events']);gate=admit_period_absence(gate,review)
            gate=admit_split_liquidation(gate,arguments,selected,assembled['actions'],active)
        if legacy_admit:gate=legacy_admit(gate)
        save(output/(day+'.exposure.json'),gate);require(gate['admitted'],'BRANCH_ACTION_EXPOSURE_NOT_ADMITTED:'+day)
    book=run_reentry(baseline=mode=='BASELINE',verify_interval=coverage,execution_guard=guard,assembled=assembled,ohlc=document['ohlc'],initial_cash='20000',fee_bps='0',slippage_bps='5',risk=MonthlyExitCoreResearchAdapter(assembled['actions']),max_new_searches=months,dividend_events=document['dividend_events'],selector=selector,decision_callback=callback)
    save(output/'book.json',book)
    save(output/'reference_coverage_audit.json',coverage.audit)
    exact=None
    if mode=='BASELINE':
        keys=('daily_ledger','order_log','cash','shares','receivable','after_close_records')
        exact={k:book.get(k)==baseline.get(k) for k in keys};require(all(exact.values()),'BASELINE_REPLAY_MISMATCH')
    result=dict(status=book['status'],reason=book.get('reason'),window=window,mode=mode,completed_sessions=len(book['daily_ledger']),required_sessions=len(dates)-1,searches=budget,baseline_exact=exact,independently_reviewed=False,elapsed_seconds=time.monotonic()-started)
    save(output/'summary.json',result);return result
if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--window',choices=WINDOWS,required=True);p.add_argument('--mode',choices=['BASELINE','REENTRY_REPAIR'],required=True);p.add_argument('--output',required=True);p.add_argument('--seconds',type=int,default=7200);p.add_argument('--run',action='store_true');a=p.parse_args();print(json.dumps(run(a.window,a.mode,a.output,a.seconds,a.run)))
