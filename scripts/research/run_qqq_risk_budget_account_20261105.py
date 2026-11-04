"""Fixed original V27 plus QQQ 63-day risk budget experiment, isolated from production."""
import argparse,json,time,sys,os,importlib.util
from pathlib import Path
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.run_old_continuous_probe_v1 import validate_selection_binding
from backtest.continuous_guided_account_decision import decide_continuous_guided_for_account
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from docs.candidates.qqq_risk_budget_selection import apply_risk_budget_selection
from docs.candidates.qqq_risk_budget_offline_limits import configure_offline_fraction_serialization
from docs.candidates import qqq_risk_budget_account_runner as kernel

def read(p):return json.loads(Path(p).read_bytes())
def digest(p):return sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(json.dumps(x,indent=2),encoding='utf-8')
def require(ok,why):
    if not ok:raise ValueError(why)
def check(pins):
    for name,h in pins.items():require(digest(ROOT/name)==h,'SOURCE_CHANGED:'+name)


def run(window,output):
    serialization_policy=configure_offline_fraction_serialization()
    started=time.monotonic();out=ROOT/output;out.mkdir(parents=True,exist_ok=False)
    recent=window=='2024_2026';name='old_continuous_baseline_20261026_v9' if recent else 'recent_continuous_baseline_20261026_v7'
    price_name='old_window_execution_prices_20261026' if recent else 'recent_execution_prices_20261026'
    base=ROOT/'tmp'/name;document=read(base/'execution_inputs.json');baseline=read(base/'book.json');assembled=document['assembled'];dates=assembled['session_dates'];months=31 if recent else 36
    prior_path=ROOT/f'tmp/trend_{window}_20261026_v1/execution_inputs.json';prior=read(prior_path);review=prior['action_review']
    price_path=ROOT/'tmp'/price_name/'execution_prices_v1.json';prices=read(price_path)
    require(prior['baseline_execution_inputs']==document,'BASELINE_MISMATCH');require(digest(price_path)==prior['execution_input_hashes']['prices'],'PRICE_BINDING_MISMATCH')
    require(baseline['status']=='COMPLETE' and len(assembled['monthly_inputs'])==months,'FIXED_WINDOW_REQUIRED')
    check(assembled['source_hashes']);check(document.get('action_source_hashes',{}));check(review['source_hashes'])
    sources=[base/'execution_inputs.json',base/'book.json',prior_path,price_path,Path(__file__),ROOT/'docs/candidates/qqq_risk_budget_account_contract_20261105.md',ROOT/'docs/candidates/qqq_risk_budget_exact.py',ROOT/'docs/candidates/qqq_risk_budget_account_runner.py',ROOT/'core/monthly_peak_exit.py',ROOT/'backtest/historical_dividend_frontier_research.py',ROOT/'backtest/historical_dividend_next_open_book_research.py',ROOT/'backtest/monthly_exit_core_research_adapter.py']
    pins={p.relative_to(ROOT).as_posix():digest(p) for p in sources};pins.update(assembled['source_hashes']);pins.update(document.get('action_source_hashes',{}));pins.update(review['source_hashes'])
    supplement_path=ROOT/'tmp/equal_four_20261105/source_review/admitted_supplement.json'
    supplement=read(supplement_path);check(supplement['source_hashes'])
    review['rows'].extend(deepcopy(supplement['review_rows'][window]));document['dividend_events'].extend(deepcopy(supplement['dividend_events'][window]))
    pins[supplement_path.relative_to(ROOT).as_posix()]=digest(supplement_path);pins.update(supplement['source_hashes'])
    risk_path=ROOT/'tmp/risk_budget_64d_inventory_20261105/risk_inputs.json'
    require(digest(risk_path)=='c1fbdb4891d573be29657238dc8f4718d7685edb6769edbada1e3ceeae1c4592','REVIEWED_RISK_INPUT_PIN_CHANGED')
    risk_document=read(risk_path);check(risk_document['source_hashes'])
    pins[risk_path.relative_to(ROOT).as_posix()]=digest(risk_path);pins.update(risk_document['source_hashes'])
    helper=ROOT/'docs/candidates/qqq_risk_budget_selection.py';pins[helper.relative_to(ROOT).as_posix()]=digest(helper)
    limits=ROOT/'docs/candidates/qqq_risk_budget_offline_limits.py';pins[limits.relative_to(ROOT).as_posix()]=digest(limits)
    risk_rows=[r for r in risk_document['windows'] if r['window']==('later' if recent else 'early')]
    require(len(risk_rows)==months and len({r['decision_date'] for r in risk_rows})==months,'RISK_MONTH_DOMAIN')
    risk_inputs={r['decision_date']:r for r in risk_rows}
    legacy=None
    if recent:
        ap=ROOT/'tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py';require(digest(ap)=='2016ac8bfc802ae3042bd7592e3a897bcb0568c88a79161a8de05d58dc8f3aa5','LEGACY_PIN')
        spec=importlib.util.spec_from_file_location('equal_four_legacy',ap);legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy);proof=legacy.certify(ROOT,dates);pins.update(proof['source_hashes']);pins[ap.relative_to(ROOT).as_posix()]=digest(ap)
    for plan in assembled['monthly_inputs']:
        args=plan['search_arguments'];require(args['max_objective_evaluations']==8192 and str(args['fee_bps'])=='0' and args['fixed_seed']=='fresh-quantity-20261014-v1','RULE_CHANGED')
    contract=dict(status='STARTED',pid=os.getpid(),window=window,start=dates[0],end=dates[-1],maximum_new_searches=months,seconds=1800,source_hashes=pins,initial_cash='20000',fee_bps='0',slippage_bps='5',serialization_policy=serialization_policy,candidate='ORIGINAL_MONTHLY_EXIT_WITH_FIXED_63D_QQQ_RISK_BUDGET',full_pit=False,oos=False)
    save(out/'contract.json',contract);print('STARTED',os.getpid(),window,flush=True)
    budget=dict(new=0,reused=0);arguments={};decision_dates=[p['decision_date'] for p in assembled['monthly_inputs']]+[dates[-1]]
    def guard():require(time.monotonic()-started<1800,'FIXED_TIME_LIMIT')
    def select(**args):
        guard();day=args['decision_date'];arguments[day]=deepcopy(args);cached=base/(day+'.selection.json');old=read(cached) if cached.exists() else None
        save(out/'progress.json',dict(day=day,stage='SELECTION',budget=budget,elapsed=time.monotonic()-started))
        if old and old['arguments']==args:raw=old['raw_selection'];budget['reused']+=1
        else:
            require(budget['new']<months,'SEARCH_LIMIT');budget['new']+=1;save(out/'search_budget.json',budget);raw=decide_continuous_guided_for_account(**args)
        validate_selection_binding(raw,args);save(out/(day+'.selection.json'),dict(arguments=args,raw_selection=raw));save(out/'search_budget.json',budget);guard();return raw
    def rerank(raw):
        selected=previous[1](raw);day=raw['decision_date'];args=arguments[day];until=decision_dates[decision_dates.index(day)+1];active=dates[dates.index(day)+1]
        selected=apply_risk_budget_selection(selected=selected,arguments=args,risk_input=risk_inputs[day])
        save(out/(day+'.decision.json'),dict(arguments=args,selected=selected))
        if not recent:
            from scripts.run_recent_continuous_probe import exposed_action_blockers
            gate=exposed_action_blockers(args,selected,until,prices,review,active,document['dividend_events'])
        else:
            from scripts.assemble_old_continuous_inputs_v1 import exposure_gate
            from scripts.run_old_continuous_probe_v4 import admit_reviewed_dividends,admit_period_absence,admit_split_liquidation
            gate=exposure_gate(document,args,selected,until,active);gate=admit_reviewed_dividends(gate,review,document['dividend_events']);gate=admit_period_absence(gate,review);gate=admit_split_liquidation(gate,args,selected,assembled['actions'],active);gate=legacy.admit(gate,proof)
        save(out/(day+'.exposure.json'),gate);require(gate['admitted'],'BRANCH_ACTION_EXPOSURE_NOT_ADMITTED:'+day);return selected
    previous=(kernel.decide_continuous_guided_for_account,kernel.rerank,kernel.run_next_open_book)
    def guarded_book(**kwargs):
        provider=kwargs['order_provider']
        def guarded(**state):guard();return provider(**state)
        kwargs['order_provider']=guarded;return previous[2](**kwargs)
    try:
        kernel.decide_continuous_guided_for_account=select;kernel.rerank=rerank;kernel.run_next_open_book=guarded_book
        risk=MonthlyExitCoreResearchAdapter(assembled['actions'])
        book=kernel.run_frontier_capped_next_open(assembled=assembled,ohlc=document['ohlc'],initial_cash='20000',fee_bps='0',slippage_bps='5',risk=risk,max_new_searches=months,dividend_events=document['dividend_events'])
        save(out/'book.json',book);check(pins)
        summary=dict(status=book['status'],reason=book.get('reason'),completed_sessions=len(book['daily_ledger']),required_sessions=len(dates)-1,searches=budget,elapsed_seconds=time.monotonic()-started,independently_reviewed=False)
        save(out/'summary.json',summary);print(json.dumps(summary),flush=True)
    except Exception as error:
        save(out/'failure.json',dict(status='FAILED',error=repr(error),searches=budget,elapsed_seconds=time.monotonic()-started));raise
    finally:kernel.decide_continuous_guided_for_account,kernel.rerank,kernel.run_next_open_book=previous

if __name__=='__main__':
    parser=argparse.ArgumentParser();parser.add_argument('--window',choices=['2021_2023','2024_2026'],required=True);parser.add_argument('--output',required=True);args=parser.parse_args();run(args.window,args.output)
