from copy import deepcopy
from reentry_repair import ReentryRepair
from backtest import historical_dividend_frontier_research as frontier
from backtest.long_market_trend_research_v1 import run_trend
import json
from pathlib import Path
from hashlib import sha256
ROOT=Path(__file__).resolve().parents[2]
def run_reentry(*, assembled, verify_interval, selector, decision_callback=None, baseline=False, execution_guard=None, **kwargs):
    assert not baseline
    signal_path=ROOT/'tmp/qqq_month_end_warmup_20261026_v1/two_window_signal_input_manifest.json'
    source=json.loads(signal_path.read_bytes())
    for name,digest in source['source_hashes'].items():assert sha256((ROOT/name).read_bytes()).hexdigest()==digest
    name='2021_2023' if len(assembled['monthly_inputs'])==36 else '2024_2026'
    signals={r['decision_date']:r for w in source['windows'] if w['name']==name for r in w['inputs']}
    engine=ReentryRepair(close_prices=assembled['close_prices'],verify_interval=verify_interval,source_hashes=assembled['source_hashes'])
    original=frontier.run_next_open_book
    def book(**arguments):
        provider=arguments['order_provider']
        def adjust(**state):
            if execution_guard:execution_guard()
            result=provider(**state)
            return engine.adjust(result,**state)
        arguments['order_provider']=adjust
        return original(**arguments)
    frontier.run_next_open_book=book
    try:result=run_trend(signals=signals,signal_source_hashes=source['source_hashes'],assembled=assembled,selector=selector,decision_callback=decision_callback,**kwargs)
    finally:frontier.run_next_open_book=original
    result['reentry_audit']=engine.audit;result['reentry_locks']=engine.locks;result['reentry_research_only']=True
    return result
