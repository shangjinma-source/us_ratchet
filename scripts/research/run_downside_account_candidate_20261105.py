"""DRAFT fixed same-call downside account runner. PENDING INTEGRATION AND ACTION REVIEW."""
import argparse,json,time,sys,os,importlib.util,gzip
from datetime import datetime,timezone
from zoneinfo import ZoneInfo
from pathlib import Path
from copy import deepcopy
from fractions import Fraction as F
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2];sys.path.insert(0,str(ROOT))
from scripts.run_old_continuous_probe_v1 import validate_selection_binding
from backtest.continuous_guided_account_decision import decide_continuous_guided_for_account
from backtest.monthly_exit_core_research_adapter import MonthlyExitCoreResearchAdapter
from docs.candidates.downside_account_selection_20261105 import decide_observed_for_account,apply_downside_selection
from backtest.research_exact_fraction_json import dumps as exact_dumps
# Separate module instance; never mutate the frozen risk-budget module namespace.
_kernel_spec=importlib.util.spec_from_file_location('downside_private_book_kernel',ROOT/'docs/candidates/qqq_risk_budget_account_runner.py')
kernel=importlib.util.module_from_spec(_kernel_spec);_kernel_spec.loader.exec_module(kernel)

def read(p):return json.loads(Path(p).read_bytes())
def digest(p):return sha256(Path(p).read_bytes()).hexdigest()
def save(p,x):Path(p).write_text(exact_dumps(x),encoding='utf-8')
def require(ok,why):
    if not ok:raise ValueError(why)
def check(pins):
    for name,h in pins.items():require(digest(ROOT/name)==h,'SOURCE_CHANGED:'+name)


def run(window,output):
    raise RuntimeError("DRAFT_PENDING_INTEGRATION_AND_ACTION_REVIEW")
    started=time.monotonic();out=ROOT/output;out.mkdir(parents=True,exist_ok=False)
    recent=window=='2024_2026';name='old_continuous_baseline_20261026_v9' if recent else 'recent_continuous_baseline_20261026_v7'
    price_name='old_window_execution_prices_20261026' if recent else 'recent_execution_prices_20261026'
    base=ROOT/'tmp'/name;document=read(base/'execution_inputs.json');baseline=read(base/'book.json');assembled=document['assembled'];dates=assembled['session_dates'];months=31 if recent else 36
    prior_path=ROOT/f'tmp/trend_{window}_20261026_v1/execution_inputs.json';prior=read(prior_path);review=prior['action_review']
    price_path=ROOT/'tmp'/price_name/'execution_prices_v1.json';prices=read(price_path)
    require(prior['baseline_execution_inputs']==document,'BASELINE_MISMATCH');require(digest(price_path)==prior['execution_input_hashes']['prices'],'PRICE_BINDING_MISMATCH')
    require(baseline['status']=='COMPLETE' and len(assembled['monthly_inputs'])==months,'FIXED_WINDOW_REQUIRED')
    check(assembled['source_hashes']);check(document.get('action_source_hashes',{}));check(review['source_hashes'])
    sources=[base/'execution_inputs.json',base/'book.json',prior_path,price_path,Path(__file__),ROOT/'docs/candidates/downside_account_execution_contract_20261105.md',ROOT/'docs/candidates/downside_account_selection_20261105.py',ROOT/'docs/candidates/qqq_risk_budget_account_runner.py',ROOT/'core/monthly_peak_exit.py',ROOT/'backtest/historical_dividend_frontier_research.py',ROOT/'backtest/historical_dividend_next_open_book_research.py',ROOT/'backtest/monthly_exit_core_research_adapter.py']
    pins={p.relative_to(ROOT).as_posix():digest(p) for p in sources};pins.update(assembled['source_hashes']);pins.update(document.get('action_source_hashes',{}));pins.update(review['source_hashes'])
    supplement_path=ROOT/'tmp/equal_four_20261105/source_review/admitted_supplement.json'
    supplement=read(supplement_path);check(supplement['source_hashes'])
    review['rows'].extend(deepcopy(supplement['review_rows'][window]));document['dividend_events'].extend(deepcopy(supplement['dividend_events'][window]))
    pins[supplement_path.relative_to(ROOT).as_posix()]=digest(supplement_path);pins.update(supplement['source_hashes'])
    training_path=ROOT/('tmp/old_window_source_reuse_20261026/unified_raw_compilation_v4.json' if recent else 'tmp/qqq_20201231_anchor_20261025/recent_training_windows_v1.json')
    training=read(training_path);check(training['source_hashes']);pins.update(training['source_hashes']);pins[training_path.relative_to(ROOT).as_posix()]=digest(training_path)
    training_windows={}
    for outer in training['windows']:
        item=outer.get('window',outer);day=item.get('decision_cutoff',item.get('decision_date'));training_windows[day]=item
    qprices={}
    for name in ('tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
        body=(ROOT/name).read_bytes();pins[name]=digest(ROOT/name);body=json.loads(gzip.decompress(body) if body[:2]==b'\x1f\x8b' else body)['chart']['result'][0]
        for stamp,close in zip(body['timestamp'],body['indicators']['quote'][0]['close']):
            if close is None:continue
            day=datetime.fromtimestamp(stamp,tz=timezone.utc).astimezone(ZoneInfo('America/New_York')).date().isoformat();value=F(str(close))
            require(day not in qprices or qprices[day]==value,'QQQ_OVERLAP_CHANGED');qprices[day]=value
    for name in ('backtest/downside_candidate_observer_integer_research.py','backtest/downside_daily_integer_candidate.py','backtest/research_exact_fast_search_observed.py','backtest/saved_quantity_candidate_comparison_observed.py','backtest/research_exact_fast_guided_observed.py','backtest/research_exact_fraction_json.py','scripts/audit_capped_training_frontier.py','scripts/research/preflight_downside_frontier_20261105.py'):
        pins[name]=digest(ROOT/name)
    manifest=read(ROOT/'research_contracts/research_archive_20261026/trend_fixed_candidate_v1_manifest.json')['base_file_dependencies']
    for name in (training_path.relative_to(ROOT).as_posix(),'tmp/qqq_month_end_warmup_20261026_v1/QQQ.response.bin','data/cache/research/current_raw_capture_20261014_v1/QQQ.response.bin'):
        require(pins[name]==manifest[name],'FROZEN_INPUT_CHANGED:'+name)
    sidecars={};returns_by_day={};qqq_by_day={}
    legacy=None
    if recent:
        ap=ROOT/'tmp/two_stage_bull_bear_20261029/wbd_local_review/legacy_absence_adapter.py';require(digest(ap)=='2016ac8bfc802ae3042bd7592e3a897bcb0568c88a79161a8de05d58dc8f3aa5','LEGACY_PIN')
        spec=importlib.util.spec_from_file_location('equal_four_legacy',ap);legacy=importlib.util.module_from_spec(spec);spec.loader.exec_module(legacy);proof=legacy.certify(ROOT,dates);pins.update(proof['source_hashes']);pins[ap.relative_to(ROOT).as_posix()]=digest(ap)
    for plan in assembled['monthly_inputs']:
        args=plan['search_arguments'];require(args['max_objective_evaluations']==8192 and str(args['fee_bps'])=='0' and args['fixed_seed']=='fresh-quantity-20261014-v1','RULE_CHANGED')
    contract=dict(status='STARTED',pid=os.getpid(),window=window,start=dates[0],end=dates[-1],maximum_new_searches=months,seconds=10800,monthly_seconds=600,source_hashes=pins,initial_cash='20000',fee_bps='0',slippage_bps='5',serialization_policy='RESEARCH_EXACT_FRACTION_HEX_JSON_V1',candidate='SAME_CALL_OBSERVED_DOWNSIDE_QQQ_V1',full_pit=False,oos=False)
    save(out/'contract.json',contract);print('STARTED',os.getpid(),window,flush=True)
    budget=dict(new=0,reused=0);arguments={};decision_dates=[p['decision_date'] for p in assembled['monthly_inputs']]+[dates[-1]]
    def guard():require(time.monotonic()-started<10800,'FIXED_TIME_LIMIT')
    def select(**args):
        guard();day=args['decision_date'];arguments[day]=deepcopy(args);month_started=time.monotonic()
        def monthly_guard():guard();require(time.monotonic()-month_started<600,'MONTHLY_TIME_LIMIT')
        require(budget['new']<months,'SEARCH_LIMIT');budget['new']+=1;save(out/'search_budget.json',budget)
        item=training_windows[day];training_dates=item['training_dates']
        require(len(training_dates)==253 and training_dates==sorted(set(training_dates)) and training_dates[-1]==day,'TRAINING_DATE_DOMAIN')
        candidates={c['security_id']:c for c in item['candidates'] if c.get('security_id')};domain=args['search_arguments']['prices'];returns={}
        for sid in domain:
            monthly_guard();values=list(map(F,candidates[sid]['training_close']));require(len(values)==253 and all(v>0 for v in values),'TRAINING_PRICE_DOMAIN')
            returns[sid]=dict(zip(training_dates[1:],[b/a-1 for a,b in zip(values,values[1:])]))
        reference=dict(zip(training_dates[1:],[qprices[b]/qprices[a]-1 for a,b in zip(training_dates,training_dates[1:])]))
        raw,sidecar=decide_observed_for_account(stock_returns=returns,qqq_reference=reference,research_source_hashes=pins,guard=monthly_guard,**args)
        validate_selection_binding(raw,args)
        sidecars[day]=sidecar;returns_by_day[day]=returns;qqq_by_day[day]=reference
        save(out/(day+'.selection.json'),dict(arguments=args,raw_selection=raw));save(out/(day+'.sidecar.json'),sidecar);monthly_guard();return raw
    def rerank(raw):
        selected=previous[1](raw);day=raw['decision_date'];args=arguments[day];until=decision_dates[decision_dates.index(day)+1];active=dates[dates.index(day)+1]
        selected=apply_downside_selection(raw=raw,sidecar=sidecars[day],stock_returns=returns_by_day[day],qqq_reference=qqq_by_day[day],research_source_hashes=pins)
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
